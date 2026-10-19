"""医生工作台概览数据。"""
from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from backend import db
from backend.api.auth import login_required
from backend.services import agent, personalization as per, rag

bp = Blueprint("dashboard", __name__)


@bp.get("/dashboard/overview")
@login_required
def overview():
    patients = db.query("SELECT * FROM patients")
    conds = db.query("SELECT patient_id, name FROM conditions WHERE status='active'")
    cond_map = {}
    for c in conds:
        cond_map.setdefault(c["patient_id"], []).append(c["name"])
    med_map = {}
    for m in db.query("SELECT * FROM medications"):
        med_map.setdefault(m["patient_id"], []).append(m)

    risk_counter = Counter()
    disease_counter = Counter()
    bp_rates, glu_rates, maturities = [], [], []
    focus = []
    alerts_total = 0

    for p in patients:
        cond_objs = [{"name": n} for n in cond_map.get(p["id"], [])]
        feats = per.compute_features(p, cond_objs, med_map.get(p["id"], []))
        score, level, reasons = per.compute_risk(p, cond_objs, med_map.get(p["id"], []), feats)
        feats["risk_reasons"] = reasons
        risk_counter[level] += 1
        for n in cond_map.get(p["id"], []):
            disease_counter[n] += 1
        if feats.get("bp_control_rate"):
            bp_rates.append(feats["bp_control_rate"])
        if feats.get("glucose_control_rate"):
            glu_rates.append(feats["glucose_control_rate"])
        m = per.maturity(feats)
        maturities.append(m["score"])
        alerts_total += feats.get("open_alerts", 0)
        if level in ("critical", "high"):
            focus.append({
                "id": p["id"], "name": p["name"], "age": per.patient_age(p),
                "gender": p["gender"], "risk_level": level,
                "risk_label": per.RISK_CN.get(level, ""),
                "risk_score": score, "avatar_color": p["avatar_color"],
                "conditions": cond_map.get(p["id"], []),
                "bp": feats.get("bp_latest"), "glucose": feats.get("glucose_latest"),
                "control_rate": feats.get("bp_control_rate") or feats.get("glucose_control_rate") or 0,
                "open_alerts": feats.get("open_alerts", 0),
                "reasons": reasons[:2],
            })

    focus.sort(key=lambda x: -x["risk_score"])
    plan_total = db.query("SELECT COUNT(*) c FROM care_plans", one=True)["c"]
    plan_adh = db.query("SELECT AVG(adherence) a FROM care_plans", one=True)["a"] or 0

    # 近 14 天新增记录（活跃度）：优先读日聚合表，避免全表扫描
    activity_map = {r["day"]: r["c"] for r in db.query(
        "SELECT day, SUM(cnt) c FROM metric_daily WHERE day >= ? GROUP BY day",
        ((datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d"),))}
    activity = []
    for i in range(13, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        c = activity_map.get(day)
        if c is None:
            c = db.query("SELECT COUNT(*) c FROM metrics WHERE substr(measured_at,1,10)=?",
                         (day,), one=True)["c"]
        activity.append({"date": day[5:], "count": c})

    # 设备接入概览
    device_rows = db.query("SELECT patient_id, status, last_seen FROM devices")
    online = 0
    for d in device_rows:
        if d["last_seen"]:
            try:
                if (datetime.now() - datetime.strptime(d["last_seen"][:19], "%Y-%m-%d %H:%M:%S")
                        ).total_seconds() < 180:
                    online += 1
            except ValueError:
                pass
    device_patients = len({d["patient_id"] for d in device_rows if d["patient_id"]})
    device_today = db.query(
        "SELECT COUNT(*) c FROM metrics WHERE device_sn IS NOT NULL AND substr(measured_at,1,10)=?",
        (datetime.now().strftime("%Y-%m-%d"),), one=True)["c"]

    # 病种达标率
    disease_stats = []
    for name, cnt in disease_counter.most_common(6):
        vals = []
        for p in patients:
            if name in cond_map.get(p["id"], []):
                f = per.compute_features(p, [{"name": n} for n in cond_map[p["id"]]],
                                         med_map.get(p["id"], []))
                r = f.get("bp_control_rate") if "高血压" in name else f.get("glucose_control_rate")
                if r:
                    vals.append(r)
        disease_stats.append({"name": name, "count": cnt,
                              "control_rate": round(sum(vals) / len(vals), 1) if vals else 0})

    recent_alerts = db.query(
        """SELECT a.*, p.name, p.avatar_color FROM alerts a JOIN patients p ON p.id=a.patient_id
           WHERE a.status='open'
           ORDER BY CASE a.level WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, a.created_at DESC
           LIMIT 6""")

    return jsonify({"ok": True, "data": {
        "kpi": {
            "patients": len(patients),
            "high_risk": risk_counter["critical"] + risk_counter["high"],
            "alerts": alerts_total,
            "bp_control": round(sum(bp_rates) / len(bp_rates), 1) if bp_rates else 0,
            "glucose_control": round(sum(glu_rates) / len(glu_rates), 1) if glu_rates else 0,
            "followup_rate": round(plan_adh * 100, 1),
            "maturity": round(sum(maturities) / len(maturities), 1) if maturities else 0,
            "plans": plan_total,
            "devices": len(device_rows),
            "devices_online": online,
            "device_patients": device_patients,
            "device_today": device_today,
        },
        "risk": {
            "critical": risk_counter["critical"], "high": risk_counter["high"],
            "medium": risk_counter["medium"], "low": risk_counter["low"],
        },
        "diseases": disease_stats,
        "focus": focus[:6],
        "alerts": recent_alerts,
        "activity": activity,
        "kb": rag.kb_stats(),
        "devices_recent": db.query(
            "SELECT d.id, d.device_sn, d.name, d.status, d.last_seen, d.patient_id, "
            "p.name AS patient_name FROM devices d LEFT JOIN patients p ON p.id=d.patient_id "
            "ORDER BY (d.last_seen IS NULL), d.last_seen DESC LIMIT 5"),
        "agent": {
            "provider": db.get_agent_config().get("provider"),
            "model": db.get_agent_config().get("model"),
        },
    }})
