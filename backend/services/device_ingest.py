"""设备体征接入：报文解析、校验、入库、预警、日聚合。

同时服务于 MQTT 网关与 HTTP 模拟接口，二者共用同一条入库管道。
"""
import json
import re
import threading
from datetime import datetime, timedelta

import config
from backend import db
from backend.services import agent, personalization as per

# 字段别名（统一小写比较），覆盖常见家用体征设备的命名习惯
ALIASES = {
    "sbp": ("sbp", "sys", "systolic", "bp_sys", "bpsys", "血压高压", "收缩压", "high"),
    "dbp": ("dbp", "dia", "diastolic", "bp_dia", "bpdia", "血压低压", "舒张压", "low"),
    "heart_rate": ("heart_rate", "heartrate", "hr", "pulse", "pulse_rate", "心率", "脉率"),
    "spo2": ("spo2", "spo", "oxy", "oxygen", "oxygen_saturation", "血氧", "血氧饱和度"),
    "temp": ("temp", "temperature", "body_temp", "bodytemperature", "体温"),
    "hrv": ("hrv", "rmssd", "sdnn", "心率变异性"),
    "resp_rate": ("resp_rate", "resprate", "rr", "respiration", "呼吸", "呼吸频率"),
}

_ALIAS_INDEX = {a: k for k, names in ALIASES.items() for a in names}

# 报文里可能出现的元信息
META_KEYS = ("battery", "battery_level", "signal", "rssi", "firmware", "fw", "model", "vendor")

_RISK_LOCK = threading.Lock()
_RISK_LAST = {}
RISK_THROTTLE_SEC = 45


VITAL_LABELS = {"sbp": "收缩压", "dbp": "舒张压", "heart_rate": "心率", "spo2": "血氧",
                "temp": "体温", "hrv": "HRV", "resp_rate": "呼吸"}

# 不同类型设备的可测指标（序列号中的类型段，如 MB-BP-1001）
DEVICE_METRICS = {
    "BP": ("sbp", "dbp", "heart_rate", "hrv"),
    "OX": ("spo2", "heart_rate", "resp_rate"),
    "TM": ("temp",),
    "TH": ("temp",),
    "WR": ("heart_rate", "spo2", "hrv", "temp"),
}


def metrics_for(device_sn):
    """按设备序列号推断可测指标，未知类型返回全部体征。"""
    up = (device_sn or "").upper()
    for key, metrics in DEVICE_METRICS.items():
        if f"-{key}-" in up or up.startswith(key + "-"):
            return metrics
    return ("sbp", "dbp", "heart_rate", "spo2", "temp", "hrv", "resp_rate")


def fmt_vitals(vitals):
    """把体征字典格式化为可读摘要（只展示实际入库的指标）。"""
    parts = []
    for k in ("sbp", "dbp", "heart_rate", "spo2", "temp", "hrv", "resp_rate"):
        v = vitals.get(k)
        if v is None:
            continue
        unit = per.METRIC_META[k]["unit"]
        if k == "sbp":
            dbp = vitals.get("dbp")
            parts.append(f"血压 {v:.0f}/{(dbp or 0):.0f}")
            continue
        if k == "dbp":
            continue
        digits = 1 if k in ("temp", "hrv") else 0
        if unit == "%":
            parts.append(f"{VITAL_LABELS[k]} {v:.0f}%")
        elif unit == "℃":
            parts.append(f"{VITAL_LABELS[k]} {v:.1f}℃")
        else:
            parts.append(f"{VITAL_LABELS[k]} {v:.{digits}f} {unit}")
    return " · ".join(parts)


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    try:
        f = float(str(v).strip().replace("℃", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return f


def _parse_time(value):
    if value in (None, ""):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        ts = float(value)
        if ts > 1e11:  # 毫秒
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s = str(value).strip().replace("T", " ").replace("Z", "")
    s = re.sub(r"\.\d+", "", s)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%H:%M:%S":
                now = datetime.now()
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _flatten(obj, out=None):
    """把嵌套一层的 JSON 展平，便于统一取字段（bp.sbp / vitals.hr）。"""
    out = {} if out is None else out
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        if isinstance(v, dict):
            _flatten(v, out)
        out.setdefault(str(k).lower(), v)
    return out


def parse_payload(raw, topic="", cfg=None):
    """解析设备报文，返回 {device_sn, patient_id, measured_at, vitals, meta, error}。"""
    cfg = cfg if cfg is not None else db.get_mqtt_config()
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", "ignore")
        except Exception:
            raw = ""
    raw = (raw or "").strip()
    result = {"device_sn": None, "patient_id": None, "measured_at": None,
              "vitals": {}, "meta": {}, "error": None}

    data = {}
    fmt = (cfg.get("payload_format") or "json").lower()
    if fmt == "csv" or (raw and raw[0] not in "{[" and "=" in raw):
        for part in re.split(r"[,;\s]+", raw):
            if "=" in part:
                k, v = part.split("=", 1)
                data[k.strip().lower()] = v.strip()
            elif ":" in part:
                k, v = part.split(":", 1)
                data[k.strip().lower()] = v.strip()
    else:
        try:
            obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            result["error"] = f"JSON 解析失败：{e}"
            return result
        if isinstance(obj, list):
            obj = obj[-1] if obj else {}
        data = _flatten(obj)

    # 设备标识：报文优先，其次取自主题（medbuddy/<sn>/vitals）
    sn = None
    for k in ("device_sn", "device_id", "deviceid", "sn", "mac", "imei", "gateway_sn"):
        if data.get(k):
            sn = str(data[k]).strip()
            break
    if not sn and topic:
        parts = [p for p in topic.split("/") if p]
        if len(parts) >= 2 and parts[-1] in ("vitals", "data", "report"):
            sn = parts[-2]
        elif parts:
            sn = parts[-1]
    sn = re.sub(r"[^A-Za-z0-9_\-.:]", "", sn or "")[:64]
    result["device_sn"] = sn or None

    pid = None
    for k in ("patient_id", "patientid", "pid"):
        if data.get(k) is not None:
            try:
                pid = int(float(data[k]))
            except (TypeError, ValueError):
                pid = None
            break
    result["patient_id"] = pid

    result["measured_at"] = _parse_time(
        data.get("ts") or data.get("timestamp") or data.get("time")
        or data.get("measured_at") or data.get("measure_time"))

    for key, value in data.items():
        metric = _ALIAS_INDEX.get(key)
        if not metric:
            continue
        num = _num(value)
        if num is not None:
            result["vitals"].setdefault(metric, num)

    for k in META_KEYS:
        if data.get(k) is not None:
            result["meta"][k] = data[k]

    if not result["device_sn"]:
        result["error"] = "缺少设备序列号（payload.device_sn 或 topic 中的设备段）"
    elif not result["vitals"]:
        result["error"] = "未识别到有效体征字段"
    return result


def _quality(metric, value):
    lo, hi = per.METRIC_SUSPECT.get(metric, per.METRIC_RANGES.get(metric, (-1e9, 1e9)))
    return "ok" if lo <= value <= hi else "suspect"


def _get_or_create_device(sn, cfg, topic=""):
    row = db.query("SELECT * FROM devices WHERE device_sn=?", (sn,), one=True)
    if row:
        return row, False
    if cfg.get("auto_register") not in ("1", 1, True):
        return None, False
    did = db.execute(
        "INSERT INTO devices(device_sn,name,model,status,created_at) VALUES(?,?,?,'offline',?)",
        (sn, f"未命名设备 {sn[-4:]}", "自动发现", db.now()),
    )
    db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
               (sn, "bind", "自动注册（auto_register=1）"))
    db.audit("mqtt-gateway", "device_auto_register", f"device:{sn}", topic or "-")
    return db.query("SELECT * FROM devices WHERE id=?", (did,), one=True), True


def _bind_patient(device, payload_pid):
    """设备已绑定则沿用绑定关系；未绑定时允许报文携带 patient_id 自助绑定。"""
    if device.get("patient_id"):
        return device["patient_id"], None
    if payload_pid:
        exists = db.query("SELECT id FROM patients WHERE id=?", (payload_pid,), one=True)
        if exists:
            db.execute("UPDATE devices SET patient_id=?, bound_at=? WHERE id=?",
                       (payload_pid, db.now(), device["id"]))
            db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
                       (device["device_sn"], "bind", f"报文自助绑定患者 #{payload_pid}"))
            return payload_pid, None
    return None, "设备未绑定患者，数据已留存但未计入健康档案"


def _dedupe(conn, sn, metric, measured_at, window):
    row = conn.execute(
        "SELECT COUNT(*) c FROM metrics WHERE device_sn=? AND metric_type=? "
        "AND abs(strftime('%s',measured_at)-strftime('%s',?))<=?",
        (sn, metric, measured_at, window),
    ).fetchone()
    return bool(row and row[0])


ALERT_RULES = (
    # (metric, 条件, level, type, 标题模板, 建议)
    ("sbp", lambda v: v >= 180, "critical", "血压", "收缩压 {v:.0f} mmHg 达危急值",
     "达到高血压急症阈值，请立即静卧复测，伴胸痛/呼吸困难请拨打 120。"),
    ("sbp", lambda v: v >= 160, "high", "血压", "收缩压 {v:.0f} mmHg 明显升高",
     "连续监测偏高，请当日联系签约医生评估用药方案。"),
    ("spo2", lambda v: v < 88, "critical", "血氧", "血氧饱和度 {v:.0f}%，达危急值",
     "立即检查设备佩戴与呼吸状况，必要时拨打 120。"),
    ("spo2", lambda v: v < 92, "high", "血氧", "血氧饱和度 {v:.0f}% 偏低",
     "保持坐位休息、避免活动，慢阻肺患者按医嘱使用氧疗，1 小时后复测。"),
    ("temp", lambda v: v >= 39.0, "high", "体温", "体温 {v:.1f}℃ 高热",
     "多饮水、物理降温，若伴意识改变或呼吸困难请立即就医。"),
    ("temp", lambda v: v >= 37.5, "medium", "体温", "体温 {v:.1f}℃ 发热",
     "观察是否伴随咳嗽、乏力等症状，每 4 小时复测一次。"),
    ("heart_rate", lambda v: v > 130, "high", "心率", "心率 {v:.0f} 次/分，明显增快",
     "静息 5 分钟后复测，若持续增快并伴胸闷心悸请就医。"),
    ("heart_rate", lambda v: v < 45, "high", "心率", "心率 {v:.0f} 次/分，明显减慢",
     "警惕药物过量或传导阻滞，伴头晕黑朦请立即就医。"),
    ("hrv", lambda v: v < 15, "medium", "HRV", "心率变异性 {v:.0f} ms 偏低",
     "近期压力或疲劳可能偏大，建议保证睡眠并复测，持续偏低请复诊。"),
)

ALERT_DEDUPE_MIN = 30


def evaluate(metric, value):
    """单指标阈值判读，供手工录入与设备上报共用。返回 (level, title, advice) 或 None。"""
    for m, cond, level, _atype, title_tpl, advice in ALERT_RULES:
        if m == metric and cond(value):
            return level, title_tpl.format(v=value), advice
    return None


def _make_alerts(conn, patient_id, sn, vitals, measured_at):
    created = []
    for metric, cond, level, atype, title_tpl, advice in ALERT_RULES:
        v = vitals.get(metric)
        if v is None or not cond(v):
            continue
        title = title_tpl.format(v=v)
        dup = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE patient_id=? AND title=? "
            "AND created_at >= datetime('now','localtime',?)",
            (patient_id, title, f"-{ALERT_DEDUPE_MIN} minutes"),
        ).fetchone()[0]
        if dup:
            continue
        conn.execute(
            "INSERT INTO alerts(patient_id,level,type,title,detail,status) VALUES(?,?,?,?,?,'open')",
            (patient_id, level, atype, title,
             f"设备 {sn} 于 {measured_at} 上报：{advice}"),
        )
        created.append(title)
    return created


def _refresh_risk(patient_id):
    now = datetime.now()
    with _RISK_LOCK:
        last = _RISK_LAST.get(patient_id)
        if last and (now - last).total_seconds() < RISK_THROTTLE_SEC:
            return False
        _RISK_LAST[patient_id] = now
    try:
        agent.refresh_risk(patient_id)
        return True
    except Exception:
        return False


def ingest(parsed, topic="", raw="", cfg=None):
    """写入一条已解析报文。返回 {status, metric_count, alerts, error, patient_id}。"""
    cfg = cfg or db.get_mqtt_config()
    sn = parsed.get("device_sn")
    out = {"status": "invalid", "metric_count": 0, "alerts": [], "error": parsed.get("error"),
           "patient_id": None, "device_sn": sn}
    if not sn:
        return out

    device, _created = _get_or_create_device(sn, cfg, topic)
    if not device:
        out["error"] = "设备未登记且未开启自动注册"
        return out

    pid, bind_err = _bind_patient(device, parsed.get("patient_id"))
    out["patient_id"] = pid
    if bind_err:
        out["error"] = bind_err

    vitals, rejected = {}, []
    for metric, value in (parsed.get("vitals") or {}).items():
        if metric not in per.METRIC_META:
            continue
        lo, hi = per.METRIC_RANGES.get(metric, (-1e9, 1e9))
        if not (lo <= value <= hi):
            rejected.append(f"{metric}={value}")
            continue
        vitals[metric] = value

    measured_at = parsed.get("measured_at") or db.now()
    meta = parsed.get("meta") or {}
    conn = db.get_db()
    day = measured_at[:10]
    inserted, dup = 0, 0

    if pid and vitals:
        window = int(cfg.get("dedupe_seconds") or 2)
        rows, touched = [], []
        for metric, value in vitals.items():
            if _dedupe(conn, sn, metric, measured_at, window):
                dup += 1
                continue
            rows.append((pid, metric, value, None, per.METRIC_META[metric]["unit"],
                         measured_at, "device", "", sn, _quality(metric, value)))
            touched.append(metric)
        if rows:
            conn.executemany(
                "INSERT OR IGNORE INTO metrics(patient_id,metric_type,value,value2,unit,"
                "measured_at,source,note,device_sn,quality) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
            conn.commit()
            inserted = len(rows)
            for metric in touched:
                db.refresh_daily(pid, metric, day, conn=conn)

    status = "ok" if inserted else ("ignored" if not pid else "ok")
    if not pid:
        status = "ignored"
    elif not vitals:
        status = "invalid"
        out["error"] = out["error"] or ("指标超出合理量程：" + "，".join(rejected) if rejected
                                        else "无数值可入库")

    summary = fmt_vitals(vitals) if vitals else ""
    conn.execute(
        "INSERT INTO device_readings(device_sn,patient_id,topic,payload,metric_count,summary,"
        "status,error,received_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (sn, pid, topic or "", (raw or "")[:8000], inserted, summary, status,
         out["error"] or "", db.now()),
    )
    device_status = "online" if status in ("ok", "ignored") else "error"
    conn.execute(
        "UPDATE devices SET status=?, last_seen=?, last_topic=?, "
        "battery=COALESCE(?,battery), signal=COALESCE(?,signal), "
        "firmware=COALESCE(?,firmware), model=COALESCE(?,model), "
        "reading_count=reading_count+?, error_count=error_count+? WHERE id=?",
        (device_status, db.now(), topic or "",
         _num(meta.get("battery") if meta.get("battery") is not None else meta.get("battery_level")),
         _num(meta.get("signal") if meta.get("signal") is not None else meta.get("rssi")),
         meta.get("firmware") or meta.get("fw"), meta.get("model"),
         inserted, 0 if status == "ok" else 1, device["id"]),
    )
    conn.commit()

    out.update({"status": status, "metric_count": inserted, "summary": summary,
                "rejected": rejected})
    if inserted and pid:
        out["alerts"] = _make_alerts(conn, pid, sn, vitals, measured_at)
        conn.commit()
        _refresh_risk(pid)
    if dup:
        out["duplicate"] = dup
    return out


def inject(patient_id, vitals, device_sn=None, measured_at=None, topic="", raw=None):
    """直接注入一组体征（模拟器 / 演示用），复用同一条入库管道。"""
    payload = {
        "device_sn": device_sn,
        "patient_id": patient_id,
        "measured_at": measured_at or db.now(),
        "vitals": {k: v for k, v in vitals.items() if v is not None},
        "meta": {},
    }
    return ingest(payload, topic=topic or f"medbuddy/{device_sn}/vitals",
                  raw=raw if raw is not None else json.dumps(
                      {"device_sn": device_sn, "patient_id": patient_id, "vitals": vitals},
                      ensure_ascii=False))


# ---------------- 模拟器：无硬件时生成可信数据 ----------------
def baseline_for(patient_id):
    """按患者最近数据推断基线，模拟器据此生成连续体征。"""
    base = {"heart_rate": 74, "spo2": 97, "temp": 36.5, "hrv": 38, "sbp": 130, "dbp": 82}
    for metric in base:
        row = db.query(
            "SELECT AVG(value) a FROM (SELECT value FROM metrics WHERE patient_id=? "
            "AND metric_type=? ORDER BY measured_at DESC LIMIT 7)", (patient_id, metric), one=True)
        if row and row["a"]:
            base[metric] = round(row["a"], 2 if metric == "temp" else 1)
    return base


def simulate(device, count=6, step_minutes=4):
    """为设备生成一组带时间间隔的连续测量，返回入库结果列表。

    按设备类型只上报它能测的指标：体温计不会报血压，血氧仪不报血糖。
    """
    import random

    sn = device["device_sn"]
    pid = device.get("patient_id")
    if not pid:
        return {"inserted": 0, "error": "设备未绑定患者"}
    base = baseline_for(pid)
    allowed = metrics_for(sn)
    out = []
    for i in range(count - 1, -1, -1):
        at = (datetime.now() - timedelta(minutes=step_minutes * i)).strftime("%Y-%m-%d %H:%M:%S")
        vitals = {
            "heart_rate": max(45, min(140, base["heart_rate"] + random.gauss(0, 4))),
            "spo2": max(86, min(100, base["spo2"] + random.gauss(0, 1.1))),
            "temp": round(max(35.4, min(39.2, base["temp"] + random.gauss(0, 0.12))), 1),
            "hrv": max(8, base["hrv"] + random.gauss(0, 5)),
            "sbp": max(90, min(200, base["sbp"] + random.gauss(0, 6))),
            "dbp": max(55, min(120, base["dbp"] + random.gauss(0, 4))),
            "resp_rate": max(12, min(28, base.get("resp_rate", 18) + random.gauss(0, 1.5))),
        }
        vitals = {k: round(v, 1 if k != "heart_rate" else 0)
                  for k, v in vitals.items() if k in allowed}
        out.append(inject(pid, vitals, device_sn=sn, measured_at=at))
    return {"inserted": sum(r.get("metric_count", 0) for r in out),
            "readings": len(out), "results": out[-2:]}


def prune_readings(days=None):
    days = int(days or db.get_mqtt_config().get("retention_days") or 30)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with db.standalone() as conn:
        cur = conn.execute("DELETE FROM device_readings WHERE received_at < ?", (cutoff,))
        removed = cur.rowcount
    return removed


def rebuild_daily():
    """全量重建日聚合（迁移后或数据修复时调用）。"""
    with db.standalone() as conn:
        conn.execute("DELETE FROM metric_daily")
        rows = conn.execute(
            "SELECT patient_id, metric_type, substr(measured_at,1,10) d, AVG(value) a, "
            "MIN(value) mn, MAX(value) mx, COUNT(*) c FROM metrics "
            "GROUP BY patient_id, metric_type, d").fetchall()
        for r in rows:
            last = conn.execute(
                "SELECT value FROM metrics WHERE patient_id=? AND metric_type=? "
                "AND substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1",
                (r["patient_id"], r["metric_type"], r["d"])).fetchone()
            conn.execute(
                "INSERT INTO metric_daily(patient_id,metric_type,day,avg_value,min_value,max_value,"
                "last_value,cnt) VALUES(?,?,?,?,?,?,?,?)",
                (r["patient_id"], r["metric_type"], r["d"], round(r["a"], 3),
                 r["mn"], r["mx"], last["value"] if last else None, r["c"]))
    return len(rows)
