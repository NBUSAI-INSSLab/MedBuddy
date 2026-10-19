"""设备接入接口：设备台账、绑定、原始报文、MQTT 配置与运行状态。"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from backend import db
from backend.api.auth import current_user, login_required
from backend.services import device_ingest, mqtt_gateway, personalization as per

bp = Blueprint("devices", __name__)

VITAL_ORDER = ("sbp", "dbp", "heart_rate", "spo2", "temp", "hrv", "resp_rate")


def _require_staff():
    u = current_user()
    if u.get("role") not in ("doctor", "admin"):
        return jsonify({"ok": False, "error": "仅医护人员可执行该操作"}), 403
    return None


def _self_pid():
    """患者账号对应本人的健康档案 ID；其他角色返回 None。"""
    u = current_user()
    return u.get("patient_id") if u.get("role") == "patient" else None


def _device_owned(row):
    """患者只能操作绑定到本人档案的设备；医护/管理员不受限。"""
    u = current_user()
    if u.get("role") == "patient":
        return bool(u.get("patient_id")) and row.get("patient_id") == u.get("patient_id")
    return u.get("role") in ("doctor", "admin")


def _no_profile():
    return jsonify({"ok": False, "error": "当前账号未绑定健康档案，无法接入设备"}), 400


def _fmt_vitals(vitals):
    return device_ingest.fmt_vitals(vitals)


def _device_brief(row, latest_reading=None):
    last = row.get("last_seen")
    online = False
    if last:
        try:
            online = (datetime.now() - datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() < 180
        except ValueError:
            online = False
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = db.query(
        "SELECT COUNT(*) c FROM metrics WHERE device_sn=? AND substr(measured_at,1,10)=?",
        (row["device_sn"], today), one=True)["c"]
    patient = db.query("SELECT id,name,avatar_color,risk_level FROM patients WHERE id=?",
                       (row["patient_id"],), one=True) if row.get("patient_id") else None
    item = {
        "id": row["id"], "device_sn": row["device_sn"], "name": row["name"],
        "model": row["model"], "vendor": row["vendor"],
        "patient_id": row.get("patient_id"),
        "patient_name": patient["name"] if patient else None,
        "patient_avatar": patient["avatar_color"] if patient else None,
        "status": "online" if online else (row.get("status") or "offline"),
        "battery": row.get("battery"), "signal": row.get("signal"),
        "firmware": row.get("firmware"), "last_seen": last,
        "reading_count": row.get("reading_count") or 0,
        "today_count": today_count,
        "bound_at": row.get("bound_at"),
        "latest": None,
    }
    if latest_reading:
        item["latest"] = latest_reading
    return item


@bp.get("/devices")
@login_required
def list_devices():
    cfg = db.get_mqtt_config()
    pid = _self_pid()
    if pid:
        rows = db.query(
            "SELECT * FROM devices WHERE patient_id=? ORDER BY status='offline', id", (pid,))
    else:
        rows = db.query("SELECT * FROM devices ORDER BY (patient_id IS NULL), status='offline', id")
    items = []
    for r in rows:
        last = db.query(
            "SELECT payload, received_at, status, error, summary FROM device_readings "
            "WHERE device_sn=? ORDER BY id DESC LIMIT 1", (r["device_sn"],), one=True)
        latest = None
        if last:
            text = last["summary"]
            at = last["received_at"]
            if not text and last["payload"]:
                parsed = device_ingest.parse_payload(last["payload"], "", cfg)
                text = _fmt_vitals(parsed.get("vitals") or {})
                at = parsed.get("measured_at") or at
            if text:
                latest = {"text": text, "at": at, "status": last["status"]}
        items.append(_device_brief(r, latest))

    today = datetime.now().strftime("%Y-%m-%d")
    since_24h = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    if pid:
        summary = {
            "total": len(items),
            "online": sum(1 for i in items if i["status"] == "online"),
            "bound": len(items),
            "unbound": 0,
            "today_readings": db.query(
                "SELECT COUNT(*) c FROM metrics WHERE device_sn IN "
                "(SELECT device_sn FROM devices WHERE patient_id=?) "
                "AND substr(measured_at,1,10)=?", (pid, today), one=True)["c"],
            "alerts_24h": db.query(
                "SELECT COUNT(*) c FROM alerts WHERE patient_id=? AND created_at >= ?",
                (pid, since_24h), one=True)["c"],
            "mode": "patient",
        }
    else:
        summary = {
            "total": len(items),
            "online": sum(1 for i in items if i["status"] == "online"),
            "bound": sum(1 for i in items if i["patient_id"]),
            "unbound": sum(1 for i in items if not i["patient_id"]),
            "today_readings": db.query(
                "SELECT COUNT(*) c FROM metrics WHERE device_sn IS NOT NULL AND substr(measured_at,1,10)=?",
                (today,), one=True)["c"],
            "alerts_24h": db.query(
                "SELECT COUNT(*) c FROM alerts WHERE created_at >= ?", (since_24h,), one=True)["c"],
            "mode": "staff",
        }
    return jsonify({"ok": True, "data": {"items": items, "summary": summary,
                                         "gateway": mqtt_gateway.gateway.status(cfg)}})


@bp.post("/devices")
@login_required
def create_device():
    data = request.get_json(silent=True) or {}
    sn = (data.get("device_sn") or "").strip()
    if not sn:
        return jsonify({"ok": False, "error": "设备序列号不能为空"}), 400
    if len(sn) > 40 or not all(c.isalnum() or c in "-_" for c in sn):
        return jsonify({"ok": False, "error": "序列号只能包含字母、数字、连字符或下划线"}), 400
    if db.query("SELECT id FROM devices WHERE device_sn=?", (sn,), one=True):
        return jsonify({"ok": False, "error": "该设备已登记"}), 400

    pid = _self_pid()
    if pid:
        if not db.query("SELECT id FROM patients WHERE id=?", (pid,), one=True):
            return _no_profile()
        # 患者自行接入的设备一律归属本人，不接受前端传入的 patient_id
    else:
        pid = data.get("patient_id") or None
        if pid and not db.query("SELECT id FROM patients WHERE id=?", (pid,), one=True):
            return jsonify({"ok": False, "error": "患者不存在"}), 400

    did = db.execute(
        "INSERT INTO devices(device_sn,name,model,vendor,patient_id,status,bound_at) "
        "VALUES(?,?,?,?,?,'offline',?)",
        (sn, data.get("name") or f"设备 {sn[-4:]}", data.get("model") or "",
         data.get("vendor") or "", pid, db.now() if pid else None))
    db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
               (sn, "bind", f"登记接入，绑定患者 {pid or '无'}"))
    db.audit(current_user()["name"], "device_create", f"device:{sn}", f"patient={pid}")
    return jsonify({"ok": True, "data": {"id": did}})


@bp.put("/devices/<int:did>")
@login_required
def update_device(did):
    row = db.query("SELECT * FROM devices WHERE id=?", (did,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "设备不存在"}), 404
    if not _device_owned(row):
        return jsonify({"ok": False, "error": "无权修改该设备"}), 403
    data = request.get_json(silent=True) or {}
    fields = {}
    for k in ("name", "model", "vendor", "device_sn"):
        if k in data and str(data[k]).strip():
            fields[k] = str(data[k]).strip()
    # 患者账号不允许把设备改绑到他人
    if "patient_id" in data and not _self_pid():
        pid = data.get("patient_id") or None
        if pid and not db.query("SELECT id FROM patients WHERE id=?", (pid,), one=True):
            return jsonify({"ok": False, "error": "患者不存在"}), 400
        fields["patient_id"] = pid
        fields["bound_at"] = db.now() if pid else None
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE devices SET {sets} WHERE id=?", list(fields.values()) + [did])
        if "patient_id" in fields:
            db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
                       (row["device_sn"], "bind", f"绑定调整为患者 {fields['patient_id'] or '解除'}"))
    db.audit(current_user()["name"], "device_update", f"device:{row['device_sn']}",
             json.dumps(fields, ensure_ascii=False))
    return jsonify({"ok": True})


@bp.delete("/devices/<int:did>")
@login_required
def delete_device(did):
    row = db.query("SELECT * FROM devices WHERE id=?", (did,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "设备不存在"}), 404
    if not _device_owned(row):
        return jsonify({"ok": False, "error": "无权删除该设备"}), 403
    db.execute("DELETE FROM device_readings WHERE device_sn=?", (row["device_sn"],))
    db.execute("DELETE FROM devices WHERE id=?", (did,))
    db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
               (row["device_sn"], "unbind", "设备已解除接入（历史指标保留）"))
    db.audit(current_user()["name"], "device_delete", f"device:{row['device_sn']}", "")
    return jsonify({"ok": True})


@bp.post("/devices/<int:did>/simulate")
@login_required
def simulate_device(did):
    row = db.query("SELECT * FROM devices WHERE id=?", (did,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "设备不存在"}), 404
    if not _device_owned(row):
        return jsonify({"ok": False, "error": "无权操作该设备"}), 403
    data = request.get_json(silent=True) or {}
    count = max(1, min(48, int(data.get("count") or 6)))
    res = device_ingest.simulate(row, count=count)
    if res.get("error"):
        return jsonify({"ok": False, "error": res["error"]}), 400
    db.audit(current_user()["name"], "device_simulate", f"device:{row['device_sn']}",
             f"{count} 组体征")
    return jsonify({"ok": True, "data": res})


@bp.get("/devices/<int:did>/readings")
@login_required
def device_readings(did):
    row = db.query("SELECT * FROM devices WHERE id=?", (did,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "设备不存在"}), 404
    if not _device_owned(row):
        return jsonify({"ok": False, "error": "无权查看该设备"}), 403
    limit = min(200, int(request.args.get("limit", 40)))
    rows = db.query(
        "SELECT id, payload, topic, metric_count, summary, status, error, received_at "
        "FROM device_readings WHERE device_sn=? ORDER BY id DESC LIMIT ?", (row["device_sn"], limit))
    cfg = db.get_mqtt_config()
    out = []
    for r in rows:
        parsed = device_ingest.parse_payload(r["payload"], r["topic"] or "", cfg)
        out.append({"id": r["id"], "at": parsed.get("measured_at") or r["received_at"],
                    "received_at": r["received_at"], "topic": r["topic"],
                    "status": r["status"], "error": r["error"], "count": r["metric_count"],
                    "text": r["summary"] or _fmt_vitals(parsed.get("vitals") or {})})
    return jsonify({"ok": True, "data": out})


@bp.get("/device-readings")
@login_required
def recent_readings():
    limit = min(60, int(request.args.get("limit", 20)))
    pid = _self_pid()
    base = ("SELECT r.id, r.device_sn, r.payload, r.topic, r.metric_count, r.summary, r.status, "
            "r.received_at, d.name, d.patient_id, p.name pname FROM device_readings r "
            "LEFT JOIN devices d ON d.device_sn=r.device_sn "
            "LEFT JOIN patients p ON p.id=r.patient_id ")
    if pid:
        rows = db.query(base + "WHERE d.patient_id=? ORDER BY r.id DESC LIMIT ?", (pid, limit))
    else:
        rows = db.query(base + "ORDER BY r.id DESC LIMIT ?", (limit,))
    cfg = db.get_mqtt_config()
    out = []
    for r in rows:
        parsed = device_ingest.parse_payload(r["payload"], r["topic"] or "", cfg)
        out.append({
            "id": r["id"], "device_sn": r["device_sn"], "device_name": r["name"] or r["device_sn"],
            "patient_id": r["patient_id"], "patient_name": r["pname"],
            "at": parsed.get("measured_at") or r["received_at"], "status": r["status"],
            "text": r["summary"] or _fmt_vitals(parsed.get("vitals") or {}),
            "count": r["metric_count"],
        })
    return jsonify({"ok": True, "data": out})


# ---------------- MQTT 配置 ----------------
@bp.get("/settings/mqtt")
@login_required
def get_mqtt_config():
    cfg = dict(db.get_mqtt_config())
    cfg["has_password"] = bool(cfg.get("password"))
    cfg["password"] = "•" * 8 if cfg.get("password") else ""
    return jsonify({"ok": True, "data": cfg})


@bp.put("/settings/mqtt")
@login_required
def save_mqtt_config():
    denied = _require_staff()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    cfg = db.get_mqtt_config()
    for k in ("host", "client_id", "topic", "payload_format"):
        if k in data:
            cfg[k] = str(data[k]).strip()
    for k in ("port", "qos", "retention_days", "dedupe_seconds"):
        if k in data:
            try:
                cfg[k] = int(data[k])
            except (TypeError, ValueError):
                pass
    for k in ("enabled", "tls", "auto_register"):
        if k in data:
            cfg[k] = "1" if str(data[k]) in ("1", "True", "true", "on") else "0"
    if data.get("username") is not None:
        cfg["username"] = str(data["username"]).strip()
    pwd = data.get("password")
    if pwd is not None and "•" not in str(pwd):
        cfg["password"] = str(pwd)
    if not cfg.get("topic"):
        cfg["topic"] = "medbuddy/+/vitals"
    if cfg.get("port") in (0, None):
        cfg["port"] = 1883
    db.save_mqtt_config(cfg)
    mqtt_gateway.gateway.restart(cfg)
    db.audit(current_user()["name"], "save_mqtt_config", cfg.get("host", ""),
             f"topic={cfg.get('topic')} enabled={cfg.get('enabled')}")
    return jsonify({"ok": True, "data": {"saved": True,
                                         "gateway": mqtt_gateway.gateway.status(cfg)}})


@bp.post("/settings/mqtt/test")
@login_required
def test_mqtt():
    data = request.get_json(silent=True) or {}
    cfg = db.get_mqtt_config()
    for k in ("host", "client_id", "topic", "payload_format", "username"):
        if k in data:
            cfg[k] = str(data[k]).strip()
    for k in ("port", "qos"):
        if k in data:
            try:
                cfg[k] = int(data[k])
            except (TypeError, ValueError):
                pass
    for k in ("tls",):
        if k in data:
            cfg[k] = "1" if str(data[k]) in ("1", "True", "true", "on") else "0"
    if data.get("password") and "•" not in str(data["password"]):
        cfg["password"] = data["password"]
    ok, msg, ms = mqtt_gateway.gateway.test_connection(cfg)
    db.audit(current_user()["name"], "test_mqtt", cfg.get("host", ""), msg)
    return jsonify({"ok": True, "data": {"success": ok, "message": msg, "latency_ms": ms}})


@bp.post("/settings/mqtt/restart")
@login_required
def restart_gateway():
    denied = _require_staff()
    if denied:
        return denied
    cfg = db.get_mqtt_config()
    mqtt_gateway.gateway.restart(cfg)
    return jsonify({"ok": True, "data": mqtt_gateway.gateway.status(cfg)})


@bp.get("/settings/mqtt/status")
@login_required
def mqtt_status():
    cfg = db.get_mqtt_config()
    st = mqtt_gateway.gateway.status(cfg)
    st["devices"] = db.query("SELECT COUNT(*) c FROM devices", one=True)["c"]
    st["events"] = db.query(
        "SELECT device_sn, event, detail, created_at FROM device_events ORDER BY id DESC LIMIT 12")
    st["last_readings"] = db.query(
        "SELECT COUNT(*) c FROM device_readings WHERE received_at >= ?",
        ((datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),), one=True)["c"]
    return jsonify({"ok": True, "data": st})
