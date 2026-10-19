"""患者档案、指标、预警、计划、记忆。"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from backend import db
from backend.api.auth import current_user, login_required
from backend.services import agent, device_ingest, personalization as per, safety

bp = Blueprint("patients", __name__)

# 单条曲线最多返回的原始点数；超过后自动降级为日聚合
SERIES_MAX_POINTS = 400


def _series(pid, mtype):
    n = db.query(
        "SELECT COUNT(*) c FROM metrics WHERE patient_id=? AND metric_type=?",
        (pid, mtype), one=True)["c"]
    if n > SERIES_MAX_POINTS:
        rows = db.query(
            "SELECT avg_value AS value, NULL AS value2, day||' 00:00:00' AS measured_at, "
            "'' AS note, 'daily' AS source, cnt FROM metric_daily "
            "WHERE patient_id=? AND metric_type=? ORDER BY day DESC LIMIT 120", (pid, mtype))
        rows.reverse()
        return rows
    return db.query(
        "SELECT value, value2, measured_at, note, source, device_sn, quality FROM metrics "
        "WHERE patient_id=? AND metric_type=? ORDER BY measured_at", (pid, mtype))


def _brief(p, feats=None, conditions=None):
    latest_bp = db.query(
        "SELECT value, measured_at FROM metrics WHERE patient_id=? AND metric_type='sbp' "
        "ORDER BY measured_at DESC LIMIT 1", (p["id"],), one=True)
    latest_dbp = db.query(
        "SELECT value FROM metrics WHERE patient_id=? AND metric_type='dbp' "
        "ORDER BY measured_at DESC LIMIT 1", (p["id"],), one=True)
    latest_glu = db.query(
        "SELECT value, note FROM metrics WHERE patient_id=? AND metric_type='glucose' "
        "ORDER BY measured_at DESC LIMIT 1", (p["id"],), one=True)
    open_alerts = db.query(
        "SELECT COUNT(*) c FROM alerts WHERE patient_id=? AND status='open'", (p["id"],), one=True)["c"]
    bp = None
    if latest_bp:
        bp = {"sbp": latest_bp["value"], "dbp": latest_dbp["value"] if latest_dbp else None,
              "at": latest_bp["measured_at"]}
    return {
        "id": p["id"], "name": p["name"], "gender": p["gender"],
        "age": per.patient_age(p), "phone": p["phone"], "city": p["city"],
        "risk_level": p["risk_level"], "risk_score": p["risk_score"],
        "risk_label": per.RISK_CN.get(p["risk_level"], ""),
        "conditions": [c["name"] for c in (conditions or [])],
        "avatar_color": p["avatar_color"],
        "enrolled_at": p["enrolled_at"],
        "latest_bp": bp,
        "latest_glucose": {"value": latest_glu["value"], "note": latest_glu["note"]} if latest_glu else None,
        "open_alerts": open_alerts,
        "managed_days": (datetime.now() - datetime.strptime(p["enrolled_at"][:10], "%Y-%m-%d")).days + 1
        if p.get("enrolled_at") else 0,
    }


@bp.get("/patients")
@login_required
def list_patients():
    q = (request.args.get("q") or "").strip()
    risk = request.args.get("risk") or ""
    disease = request.args.get("disease") or ""
    page = max(1, int(request.args.get("page", 1)))
    size = min(50, int(request.args.get("size", 20)))

    sql = "SELECT * FROM patients WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR phone LIKE ? OR city LIKE ?)"
        args += [f"%{q}%"] * 3
    if risk:
        sql += " AND risk_level=?"
        args.append(risk)
    if disease:
        sql += " AND id IN (SELECT patient_id FROM conditions WHERE name LIKE ?)"
        args.append(f"%{disease}%")
    sql += " ORDER BY CASE risk_level WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id"

    rows = db.query(sql, args)
    total = len(rows)
    rows = rows[(page - 1) * size: page * size]

    cond_map = {}
    for c in db.query("SELECT patient_id, name FROM conditions WHERE status='active'"):
        cond_map.setdefault(c["patient_id"], []).append(c)
    items = [_brief(p, conditions=cond_map.get(p["id"], [])) for p in rows]
    return jsonify({"ok": True, "data": {"items": items, "total": total, "page": page, "size": size}})


@bp.get("/patients/<int:pid>")
@login_required
def get_patient(pid):
    b = agent.load_patient(pid)
    if not b:
        return jsonify({"ok": False, "error": "患者不存在"}), 404
    p = b["patient"]
    feats = b["features"]
    series = {}
    for t in ("sbp", "dbp", "glucose", "weight", "hba1c", "heart_rate", "spo2",
              "temp", "hrv", "resp_rate", "ldl", "egfr"):
        rows = _series(pid, t)
        if rows:
            series[t] = rows
    plan = b["care_plan"]
    if plan:
        plan["goals"] = plan.get("goals", [])
    data = {
        "profile": _brief(p, feats, b["conditions"]),
        "patient": {k: p[k] for k in ("name", "gender", "birth_date", "phone", "city", "occupation",
                                      "height_cm", "weight_kg", "blood_type", "allergies",
                                      "family_history", "smoking", "drinking", "exercise",
                                      "salt_intake", "sleep_quality", "note")},
        "age": b["age"],
        "conditions": b["conditions"],
        "medications": b["medications"],
        "features": feats,
        "risk": b["risk"],
        "maturity": b["maturity"],
        "memories": b["memories"],
        "narrative": b["narrative"],
        "alerts": b["alerts"],
        "plan": plan,
        "series": series,
        "devices": db.query(
            "SELECT id, device_sn, name, model, vendor, status, last_seen, battery, signal, "
            "reading_count FROM devices WHERE patient_id=? ORDER BY id", (pid,)),
        "followup_plan": per.build_followup_plan(p, b["conditions"], feats, b["risk"]["level"]),
    }
    return jsonify({"ok": True, "data": data})


@bp.post("/patients/<int:pid>/metrics")
@login_required
def add_metric(pid):
    data = request.get_json(silent=True) or {}
    mtype = data.get("metric_type")
    if mtype not in per.METRIC_META:
        return jsonify({"ok": False, "error": "不支持的指标类型"}), 400
    try:
        value = float(data.get("value"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "数值格式不正确"}), 400
    measured_at = data.get("measured_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source = data.get("source") or "home"
    db.execute(
        "INSERT INTO metrics(patient_id,metric_type,value,value2,unit,measured_at,source,note,quality) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (pid, mtype, value, None, per.METRIC_META[mtype]["unit"], measured_at,
         source, data.get("note") or "", "ok"),
    )
    db.refresh_daily(pid, mtype, measured_at[:10])
    # 即时预警：与设备上报共用一套阈值规则
    meta = per.METRIC_META[mtype]
    alert = None
    hit = device_ingest.evaluate(mtype, value)
    if hit:
        level, title, advice = hit
        alert = (level, meta["group"], title, advice)
    elif mtype == "glucose" and value < 3.9:
        alert = ("critical", "血糖", f"低血糖 {value:.1f} mmol/L", "立即补充 15g 碳水化合物，15 分钟后复测。")
    elif mtype == "glucose" and value > 16.7:
        alert = ("high", "血糖", f"血糖 {value:.1f} mmol/L 显著升高", "警惕高血糖危象，建议当日就医。")
    if alert:
        db.execute("INSERT INTO alerts(patient_id,level,type,title,detail,status) VALUES(?,?,?,?,?,'open')",
                   (pid,) + alert)
    risk = agent.refresh_risk(pid)
    db.audit(current_user()["name"], "add_metric", f"patient:{pid}", f"{meta['name']}={value}")
    return jsonify({"ok": True, "data": {"risk": risk, "alert": bool(alert)}})


@bp.post("/patients/<int:pid>/alerts/<int:aid>/handle")
@login_required
def handle_alert(pid, aid):
    data = request.get_json(silent=True) or {}
    db.execute("UPDATE alerts SET status='handled', handled_at=?, handled_by=? WHERE id=? AND patient_id=?",
               (db.now(), current_user()["name"], aid, pid))
    db.audit(current_user()["name"], "handle_alert", f"alert:{aid}", data.get("note", "已处理"))
    agent.refresh_risk(pid)
    return jsonify({"ok": True})


@bp.post("/patients/<int:pid>/memories")
@login_required
def add_memory(pid):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "内容不能为空"}), 400
    mid = db.execute(
        "INSERT INTO memories(patient_id,kind,content,confidence,weight,source) VALUES(?,?,?,?,?,?)",
        (pid, data.get("kind") or "fact", content, 0.9, 1.2, "manual"),
    )
    db.audit(current_user()["name"], "add_memory", f"patient:{pid}", content)
    return jsonify({"ok": True, "data": {"id": mid}})


@bp.delete("/patients/<int:pid>/memories/<int:mid>")
@login_required
def del_memory(pid, mid):
    db.execute("DELETE FROM memories WHERE id=? AND patient_id=?", (mid, pid))
    return jsonify({"ok": True})


@bp.post("/patients/<int:pid>/plan")
@login_required
def save_plan(pid):
    data = request.get_json(silent=True) or {}
    title = data.get("title") or "慢病管理计划"
    goals = data.get("goals") or []
    next_visit = data.get("next_visit") or (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    db.execute("UPDATE care_plans SET status='done' WHERE patient_id=? AND status='active'", (pid,))
    db.execute(
        "INSERT INTO care_plans(patient_id,title,goals_json,start_date,end_date,status,adherence,"
        "next_visit,created_by) VALUES(?,?,?,?,?,'active',?,?,?)",
        (pid, title, json.dumps(goals, ensure_ascii=False),
         datetime.now().strftime("%Y-%m-%d"),
         (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d"),
         0, next_visit, current_user()["name"]),
    )
    db.audit(current_user()["name"], "save_plan", f"patient:{pid}", title)
    return jsonify({"ok": True})


@bp.get("/patients/<int:pid>/safety-check")
@login_required
def safety_check(pid):
    text = request.args.get("text", "")
    return jsonify({"ok": True, "data": safety.check(pid, text)})


@bp.get("/my/profile")
@login_required
def my_profile():
    u = current_user()
    if not u.get("patient_id"):
        return jsonify({"ok": False, "error": "当前账号未绑定患者"}), 400
    return get_patient(u["patient_id"])
