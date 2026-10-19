"""个性化引擎：时序特征、风险分层、达标率、长期记忆抽取、个性化成熟度。"""
import math
import re
from datetime import datetime, timedelta

from backend import db

METRIC_META = {
    "sbp": {"name": "收缩压", "unit": "mmHg", "group": "血压"},
    "dbp": {"name": "舒张压", "unit": "mmHg", "group": "血压"},
    "glucose": {"name": "血糖", "unit": "mmol/L", "group": "血糖"},
    "hba1c": {"name": "糖化血红蛋白", "unit": "%", "group": "血糖"},
    "weight": {"name": "体重", "unit": "kg", "group": "体格"},
    "heart_rate": {"name": "心率", "unit": "次/分", "group": "心血管"},
    "spo2": {"name": "血氧饱和度", "unit": "%", "group": "呼吸"},
    "temp": {"name": "体温", "unit": "℃", "group": "体征"},
    "hrv": {"name": "心率变异性", "unit": "ms", "group": "心血管"},
    "resp_rate": {"name": "呼吸频率", "unit": "次/分", "group": "呼吸"},
    "ldl": {"name": "低密度脂蛋白", "unit": "mmol/L", "group": "血脂"},
    "egfr": {"name": "肾小球滤过率", "unit": "mL/min", "group": "肾功能"},
    "uric_acid": {"name": "尿酸", "unit": "μmol/L", "group": "代谢"},
    "steps": {"name": "日步数", "unit": "步", "group": "行为"},
}

# 设备上报的合理量程（超出即判为无效报文，不入库）
METRIC_RANGES = {
    "sbp": (50, 300), "dbp": (20, 200), "glucose": (1.0, 40.0),
    "heart_rate": (25, 250), "spo2": (50, 100), "temp": (30.0, 45.0),
    "hrv": (1, 400), "resp_rate": (5, 60), "weight": (20, 300),
}

# 边缘值：入库但标记 quality=suspect，不参与风险计分
METRIC_SUSPECT = {
    "heart_rate": (35, 200), "spo2": (70, 100), "temp": (34.0, 42.0),
    "sbp": (70, 260), "dbp": (35, 150), "hrv": (5, 250), "resp_rate": (7, 45),
}

# 设备测量基线（用于「个人基线偏离」提示）
BASELINE_METRICS = ("sbp", "dbp", "heart_rate", "spo2", "temp", "hrv")

RISK_CN = {"critical": "极高危", "high": "高危", "medium": "中危", "low": "低危"}


def _rows(patient_id, mtype, days):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return db.query(
        "SELECT * FROM metrics WHERE patient_id=? AND metric_type=? AND measured_at>=? ORDER BY measured_at",
        (patient_id, mtype, since),
    )


def _since(days):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _avg(rows):
    vals = [r["value"] for r in rows]
    return sum(vals) / len(vals) if vals else None


def _slope(rows):
    if len(rows) < 3:
        return 0.0
    n = len(rows)
    xs = list(range(n))
    ys = [r["value"] for r in rows]
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def bp_target(patient, conditions):
    age = patient_age(patient)
    names = [c["name"] for c in conditions]
    if age >= 80:
        return "140/90"
    if any("肾病" in n or "糖尿病" in n for n in names):
        return "130/80"
    return "140/90"


def glucose_target(conditions):
    names = [c["name"] for c in conditions]
    if any("糖尿病" in n for n in names):
        return (4.4, 7.0)
    return (3.9, 6.1)


def patient_age(patient):
    bd = patient.get("birth_date")
    if not bd:
        return 60
    try:
        d = datetime.strptime(bd[:10], "%Y-%m-%d")
        return int((datetime.now() - d).days / 365.25)
    except Exception:
        return 60


def compute_features(patient, conditions, medications, alerts=None):
    pid = patient["id"]
    p = patient
    feats = {"metric_counts": {}, "series": {}}

    # 血压
    sbp_rows = _rows(pid, "sbp", 30)
    dbp_map = {r["measured_at"]: r["value"] for r in _rows(pid, "dbp", 30)}
    bp_pairs = [(r["measured_at"], r["value"], dbp_map.get(r["measured_at"])) for r in sbp_rows]
    bp_pairs = [x for x in bp_pairs if x[2] is not None]
    if sbp_rows:
        last = sbp_rows[-1]
        feats["bp_latest"] = {
            "sbp": last["value"], "dbp": dbp_map.get(last["measured_at"], 0),
            "measured_at": last["measured_at"], "source": "家庭自测" if last["source"] == "home" else "门诊",
        }
        feats["bp_avg7"] = {
            "sbp": _avg(_rows(pid, "sbp", 7)) or last["value"],
            "dbp": _avg(_rows(pid, "dbp", 7)) or 0,
        }
        feats["bp_max30"] = max(r["value"] for r in sbp_rows)
        feats["bp_slope"] = round(_slope(sbp_rows), 3)

        tgt = bp_target(p, conditions)
        t_sbp, t_dbp = [float(x) for x in tgt.split("/")]
        ok = sum(1 for _, s, d in bp_pairs if s < t_sbp and d < t_dbp)
        feats["bp_target"] = tgt
        feats["bp_control_rate"] = round(100 * ok / len(bp_pairs), 1) if bp_pairs else 0
        feats["bp_pairs_30d"] = len(bp_pairs)
        feats["bp_in_range"] = bool(bp_pairs and bp_pairs[-1][1] < t_sbp and bp_pairs[-1][2] < t_dbp)

    # 血糖
    g_rows = _rows(pid, "glucose", 30)
    if g_rows:
        last = g_rows[-1]
        lo, hi = glucose_target(conditions)
        feats["glucose_latest"] = {"value": last["value"], "measured_at": last["measured_at"],
                                   "note": last["note"] or ""}
        feats["glucose_avg7"] = _avg(_rows(pid, "glucose", 7))
        feats["glucose_slope"] = round(_slope(g_rows), 4)
        fasting = [r for r in g_rows if (r["note"] or "") == "空腹"]
        basis_rows = fasting if len(fasting) >= 3 else g_rows
        ok = sum(1 for r in basis_rows if lo <= r["value"] <= hi)
        feats["glucose_control_rate"] = round(100 * ok / len(basis_rows), 1) if basis_rows else 0
        feats["glucose_control_basis"] = "空腹" if len(fasting) >= 3 else "总体"
        feats["glucose_target"] = f"{lo}-{hi}"

    h_rows = _rows(pid, "hba1c", 180)
    if h_rows:
        feats["hba1c"] = h_rows[-1]["value"]
        feats["hba1c_date"] = h_rows[-1]["measured_at"]

    l_rows = _rows(pid, "ldl", 365)
    if l_rows:
        feats["ldl"] = l_rows[-1]["value"]

    w_rows = _rows(pid, "weight", 90)
    if len(w_rows) >= 2:
        feats["weight_trend"] = round(w_rows[-1]["value"] - w_rows[0]["value"], 1)
        feats["weight_latest"] = w_rows[-1]["value"]
    elif w_rows:
        feats["weight_latest"] = w_rows[-1]["value"]

    def _vital(mtype):
        rows = _rows(pid, mtype, 30)
        if not rows:
            return None
        last = rows[-1]
        recent = [r for r in rows if r["measured_at"] >= _since(7)]
        return {
            "latest": last["value"],
            "avg7": round(_avg(recent), 2) if recent else None,
            "min": min(r["value"] for r in rows),
            "max": max(r["value"] for r in rows),
            "at": last["measured_at"],
            "source": last.get("source") or "home",
            "device_sn": last.get("device_sn"),
        }

    hr = _vital("heart_rate")
    if hr:
        feats["hr"] = hr
        feats["hr_latest"] = hr["latest"]
    sp = _vital("spo2")
    if sp:
        feats["spo2"] = sp
        feats["spo2_latest"] = sp["latest"]
    temp = _vital("temp")
    if temp:
        feats["temp"] = temp
        feats["temp_latest"] = temp["latest"]
    hrv = _vital("hrv")
    if hrv:
        feats["hrv"] = hrv
        feats["hrv_latest"] = hrv["latest"]
    rr = _vital("resp_rate")
    if rr:
        feats["resp_rate"] = rr

    eg = _rows(pid, "egfr", 365)
    if eg:
        feats["egfr"] = eg[-1]["value"]

    # 依从性（用药平均 + 随访完成）
    if medications:
        adh = [m.get("adherence") or 0 for m in medications]
        feats["med_adherence"] = round(100 * sum(adh) / len(adh), 1)
    else:
        feats["med_adherence"] = 0
    feats["missed_med_days"] = round(30 * (1 - feats["med_adherence"] / 100), 1)

    # 记录频次与连续性
    total = db.query("SELECT COUNT(*) c FROM metrics WHERE patient_id=?", (pid,), one=True)["c"]
    feats["metric_count"] = total
    days = (datetime.now() - datetime.strptime(
        (p.get("enrolled_at") or datetime.now().strftime("%Y-%m-%d"))[:10], "%Y-%m-%d")).days + 1
    feats["managed_days"] = max(1, days)
    since30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    active_days = db.query(
        "SELECT COUNT(DISTINCT substr(measured_at,1,10)) c FROM metrics "
        "WHERE patient_id=? AND measured_at>=?", (pid, since30)
    )[0]["c"]
    feats["active_days"] = active_days
    feats["record_density"] = round(100 * active_days / min(30, feats["managed_days"]), 1)

    # 设备接入情况（个性化成熟度的新维度：自动化数据占比）
    dev = db.query(
        "SELECT COUNT(*) c, COUNT(DISTINCT device_sn) n, MAX(measured_at) last FROM metrics "
        "WHERE patient_id=? AND device_sn IS NOT NULL AND device_sn<>''", (pid,), one=True)
    feats["device_metric_count"] = dev["c"] or 0
    feats["device_count"] = dev["n"] or 0
    feats["device_last_at"] = dev["last"]
    feats["device_share"] = round(100 * feats["device_metric_count"] / total, 1) if total else 0
    dev_today = db.query(
        "SELECT COUNT(*) c FROM metrics WHERE patient_id=? AND device_sn IS NOT NULL "
        "AND substr(measured_at,1,10)=?", (pid, datetime.now().strftime("%Y-%m-%d")), one=True)["c"]
    feats["device_today"] = dev_today

    # 会话与记忆
    feats["chat_turns"] = db.query(
        "SELECT COUNT(*) c FROM messages m JOIN conversations c ON c.id=m.conversation_id "
        "WHERE c.patient_id=? AND m.role='user'", (pid,), one=True)["c"]
    feats["memory_count"] = db.query(
        "SELECT COUNT(*) c FROM memories WHERE patient_id=?", (pid,), one=True)["c"]
    feats["followup_done"] = db.query(
        "SELECT COUNT(*) c FROM care_plans WHERE patient_id=? AND status='done'", (pid,), one=True)["c"]
    if alerts is not None:
        feats["open_alerts"] = len([a for a in alerts if a["status"] == "open"])
    else:
        feats["open_alerts"] = db.query(
            "SELECT COUNT(*) c FROM alerts WHERE patient_id=? AND status='open'", (pid,), one=True)["c"]
    return feats


def compute_risk(patient, conditions, medications, feats):
    """0-100 复合风险分，返回 (score, level, reasons)。"""
    score, reasons = 0.0, []
    age = patient_age(patient)

    if age >= 75:
        score += 10
        reasons.append(f"年龄 {age} 岁，属高龄人群")
    elif age >= 65:
        score += 6
        reasons.append(f"年龄 {age} 岁")

    bp = feats.get("bp_avg7")
    if bp:
        excess = max(0, bp["sbp"] - 130)
        s = min(25, excess * 0.7)
        score += s
        if bp["sbp"] >= 160:
            reasons.append(f"近 7 天平均收缩压 {bp['sbp']:.0f} mmHg，明显高于目标")
        elif bp["sbp"] >= 140:
            reasons.append(f"近 7 天平均收缩压 {bp['sbp']:.0f} mmHg，未达标")
        if feats.get("bp_control_rate", 100) < 50:
            score += 6
            reasons.append(f"家庭血压达标率仅 {feats['bp_control_rate']:.0f}%")

    if feats.get("glucose_avg7"):
        g = feats["glucose_avg7"]
        if g >= 11.1:
            score += 18
            reasons.append(f"平均血糖 {g:.1f} mmol/L 显著升高")
        elif g >= 7.0:
            score += 10
            reasons.append(f"平均血糖 {g:.1f} mmol/L 高于目标")
        elif g < 3.9:
            score += 14
            reasons.append("存在低血糖风险")

    if feats.get("hba1c"):
        h = feats["hba1c"]
        if h >= 9:
            score += 14
            reasons.append(f"糖化血红蛋白 {h:.1f}%，控制不佳")
        elif h >= 7:
            score += 7
            reasons.append(f"糖化血红蛋白 {h:.1f}%，未达标")

    if feats.get("ldl") and feats["ldl"] >= 3.4:
        score += 6
        reasons.append(f"低密度脂蛋白 {feats['ldl']:.2f} mmol/L 偏高")

    # 设备连续监测体征
    tp = feats.get("temp") or {}
    if tp.get("latest") is not None:
        t = tp["latest"]
        if t >= 38.5:
            score += 10
            reasons.append(f"体温 {t:.1f}℃，存在发热")
        elif t >= 37.3:
            score += 5
            reasons.append(f"体温 {t:.1f}℃，低热待观察")
    sp = feats.get("spo2") or {}
    if sp.get("latest") is not None:
        if sp["latest"] < 90:
            score += 12
            reasons.append(f"血氧 {sp['latest']:.0f}%，明显偏低")
        elif sp["latest"] < 94:
            score += 7
            reasons.append(f"血氧 {sp['latest']:.0f}%，低于正常范围")
    hrv_b = feats.get("hr") or {}
    if hrv_b.get("latest") is not None:
        if hrv_b["latest"] > 110:
            score += 6
            reasons.append(f"静息心率 {hrv_b['latest']:.0f} 次/分，偏快")
        elif hrv_b["latest"] < 50:
            score += 6
            reasons.append(f"静息心率 {hrv_b['latest']:.0f} 次/分，偏慢")

    if feats.get("med_adherence", 100) < 70:
        score += 10
        reasons.append(f"用药依从性 {feats['med_adherence']:.0f}%，存在漏服")
    elif feats.get("med_adherence", 100) < 85:
        score += 4

    if feats.get("open_alerts"):
        score += min(12, feats["open_alerts"] * 6)
        reasons.append(f"有 {feats['open_alerts']} 条未处理预警")

    if len(conditions) >= 2:
        score += 8
        reasons.append("多病共存：" + "、".join(c["name"] for c in conditions))
    elif len(conditions) == 1:
        score += 3

    if any("肾病" in c["name"] or "冠心病" in c["name"] for c in conditions):
        score += 8
    if (patient.get("smoking") or "") in ("current", "daily"):
        score += 5
        reasons.append("目前吸烟")

    score = max(0, min(100, round(score, 1)))
    level = "critical" if score >= 70 else "high" if score >= 50 else "medium" if score >= 30 else "low"
    return score, level, reasons


def maturity(feats):
    """个性化成熟度 0-100（新增设备自动采集维度）。"""
    days = feats.get("managed_days", 1)
    m = (25 * min(1, days / 90)
         + 22 * min(1, feats.get("metric_count", 0) / 60)
         + 13 * min(1, feats.get("chat_turns", 0) / 20)
         + 18 * min(1, feats.get("memory_count", 0) / 12)
         + 10 * min(1, feats.get("followup_done", 0) / 6)
         + 12 * min(1, feats.get("device_metric_count", 0) / 120))
    m = round(min(100, m), 1)
    stage = "起步期" if m < 35 else "成长期" if m < 65 else "成熟期"
    return {"score": m, "stage": stage}


MEMORY_PATTERNS = [
    ("preference", [r"(?:我|本人)?(?:比较|更)?(?:喜欢|爱吃|偏好|习惯吃)([^，。；！？]{2,20})",
                    r"(?:不爱吃|不吃|吃不了|受不了)([^，。；！？]{2,16})"]),
    ("barrier", [r"(记不住|总是忘|老是忘|容易忘|漏服|没时间|不方便|太麻烦|买不到|担心副作用)"]),
    ("goal", [r"(?:想|希望|目标|打算)([^，。；！？]{2,30})"]),
    ("fact", [r"(过敏|从事|上夜班|独居|和家人|住在)([^，。；！？]{0,20})"]),
]


def extract_memories(patient_id, text, source="chat"):
    """从用户话语中抽取长期记忆（按分句保留上下文），去重后入库。返回新增条数。"""
    added = 0
    existing = db.query("SELECT content, kind FROM memories WHERE patient_id=?", (patient_id,))
    seen = [m["content"] for m in existing]
    clauses = [c.strip(" ，,、") for c in re.split(r"[。！？；\n]", text or "") if c.strip()]
    for clause in clauses:
        if not (4 <= len(clause) <= 120):
            continue
        for kind, patterns in MEMORY_PATTERNS:
            if not any(re.search(p, clause) for p in patterns):
                continue
            if any(clause[:12] in s or s[:12] in clause for s in seen):
                break
            db.execute(
                "INSERT INTO memories(patient_id,kind,content,confidence,weight,source) "
                "VALUES(?,?,?,?,?,?)",
                (patient_id, kind, clause[:120], 0.75, 1.0, source),
            )
            seen.append(clause)
            added += 1
            break
    return added


def memory_brief(patient_id, limit=8):
    rows = db.query(
        "SELECT * FROM memories WHERE patient_id=? ORDER BY weight DESC, use_count DESC, id DESC LIMIT ?",
        (patient_id, limit),
    )
    kind_cn = {"fact": "情况", "preference": "偏好", "barrier": "困难", "goal": "目标"}
    for r in rows:
        r["kind_cn"] = kind_cn.get(r["kind"], "信息")
    return rows


def touch_memories(ids):
    for i in ids:
        db.execute("UPDATE memories SET use_count=use_count+1, last_used_at=? WHERE id=?", (db.now(), i))


def profile_narrative(patient, conditions, feats, memories):
    age = patient_age(patient)
    gender = patient.get("gender") or ""
    conds = "、".join(c["name"] for c in conditions) or "尚未确诊慢病"
    parts = [f"{patient['name']}，{age} 岁{gender}性，在管诊断：{conds}。"]
    if feats.get("bp_avg7"):
        parts.append(
            f"近 7 天平均血压 {feats['bp_avg7']['sbp']:.0f}/{feats['bp_avg7']['dbp']:.0f} mmHg，"
            f"达标率 {feats.get('bp_control_rate', 0):.0f}%。"
        )
    if feats.get("hba1c"):
        parts.append(f"糖化血红蛋白 {feats['hba1c']:.1f}%。")
    vitals = []
    if feats.get("hr"):
        vitals.append(f"心率 {feats['hr']['latest']:.0f} 次/分")
    if feats.get("spo2"):
        vitals.append(f"血氧 {feats['spo2']['latest']:.0f}%")
    if feats.get("temp"):
        vitals.append(f"体温 {feats['temp']['latest']:.1f}℃")
    if feats.get("hrv"):
        vitals.append(f"HRV {feats['hrv']['latest']:.0f} ms")
    if vitals:
        parts.append("设备监测：" + "，".join(vitals) + "。")
    if feats.get("med_adherence"):
        parts.append(f"用药依从性约 {feats['med_adherence']:.0f}%。")
    if feats.get("record_density"):
        parts.append(f"近 30 天记录覆盖 {feats['record_density']:.0f}% 的天数。")
    if memories:
        pref = [m["content"] for m in memories if m["kind"] == "preference"]
        barr = [m["content"] for m in memories if m["kind"] == "barrier"]
        if pref:
            parts.append("个人偏好：" + "；".join(pref[:2]) + "。")
        if barr:
            parts.append("已知困难：" + "；".join(barr[:2]) + "。")
    if (patient.get("allergies") or "").strip():
        parts.append(f"过敏史：{patient['allergies']}。")
    return "".join(parts)


def build_followup_plan(patient, conditions, feats, risk_level):
    """按病种与风险生成随访计划建议（智能体产出的可采纳方案）。"""
    names = [c["name"] for c in conditions]
    cadence = {"critical": "每周 1 次", "high": "每 2 周 1 次", "medium": "每月 1 次", "low": "每 3 个月 1 次"}
    goals = []
    if "高血压" in names or feats.get("bp_latest"):
        goals.append(f"家庭血压每周 ≥5 天，达标目标 {feats.get('bp_target', '140/90')} mmHg")
    if "糖尿病" in names or feats.get("glucose_latest"):
        goals.append("空腹血糖控制在 4.4–7.0 mmol/L，每 3 个月复查糖化血红蛋白")
    if "血脂异常" in names or (feats.get("ldl") or 0) >= 3.4:
        goals.append("低密度脂蛋白降至 2.6 mmol/L 以下，低脂饮食")
    if "慢性肾病" in names:
        goals.append("每月复查肾功能与尿蛋白，限制蛋白摄入 0.8 g/kg/日")
    if "慢阻肺" in names:
        goals.append("坚持呼吸训练，每年接种流感疫苗，急性加重及时就诊")
    if not goals:
        goals.append("建立家庭监测习惯，每周记录 3 次以上指标")
    return {
        "title": f"{'/'.join(names) or '慢病'}规范管理计划",
        "cadence": cadence.get(risk_level, "每月 1 次"),
        "goals": goals,
    }
