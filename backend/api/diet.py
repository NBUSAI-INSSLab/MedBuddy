"""饮食管理接口：个性化处方、饮食记录、照片分析与执行度。"""
import json
import os
import re
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from backend import db
from backend.api.auth import current_user, login_required
from backend.services import diet, diet_vision

bp = Blueprint("diet", __name__)

MEAL_KEYS = {m["key"] for m in diet.MEALS}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PHOTO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{10}\.jpg$")

MEAL_CN = {m["key"]: m["name"] for m in diet.MEALS}


def _can_access(pid):
    u = current_user()
    if u.get("role") == "patient" and u.get("patient_id") != pid:
        return False
    return True


def _patient_exists(pid):
    return db.query("SELECT id FROM patients WHERE id=?", (pid,), one=True)


@bp.get("/patients/<int:pid>/diet")
@login_required
def get_diet(pid):
    if not _can_access(pid):
        return jsonify({"ok": False, "error": "无权查看该患者档案"}), 403
    if not _patient_exists(pid):
        return jsonify({"ok": False, "error": "患者不存在"}), 404
    data = diet.build(pid)
    return jsonify({"ok": True, "data": data})


@bp.get("/my/diet")
@login_required
def my_diet():
    """患者端「我的饮食」：只返回本人档案。"""
    u = current_user()
    pid = u.get("patient_id")
    if not pid:
        return jsonify({"ok": False, "error": "当前账号未绑定健康档案"}), 404
    data = diet.build(pid)
    return jsonify({"ok": True, "data": data})


@bp.post("/patients/<int:pid>/diet/logs")
@login_required
def add_log(pid):
    if not _can_access(pid):
        return jsonify({"ok": False, "error": "无权操作该患者档案"}), 403
    data = request.get_json(silent=True) or {}
    meal = (data.get("meal") or "").strip()
    foods = (data.get("foods") or "").strip()
    if meal not in MEAL_KEYS:
        return jsonify({"ok": False, "error": "请选择餐次"}), 400
    if not (2 <= len(foods) <= 300):
        return jsonify({"ok": False, "error": "请填写 2–300 字的饮食内容"}), 400
    log_date = (data.get("log_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    if not DATE_RE.match(log_date):
        return jsonify({"ok": False, "error": "日期格式应为 YYYY-MM-DD"}), 400

    kcal, sodium = data.get("calories"), data.get("sodium")
    estimated = False
    est_kcal, est_na, hit = diet.estimate(foods)
    if kcal in (None, "", 0):
        kcal, estimated = est_kcal, estimated or hit
    if sodium in (None, "", 0):
        sodium, estimated = est_na, estimated or hit
    try:
        kcal = round(float(kcal), 0) if kcal not in (None, "") else None
        sodium = round(float(sodium), 0) if sodium not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "热量或钠的数值格式不正确"}), 400
    if kcal is not None and not (0 <= kcal <= 5000):
        return jsonify({"ok": False, "error": "热量应在 0–5000 kcal 之间"}), 400
    if sodium is not None and not (0 <= sodium <= 15000):
        return jsonify({"ok": False, "error": "钠应在 0–15000 mg 之间"}), 400

    lid = db.execute(
        "INSERT INTO diet_logs(patient_id,log_date,meal,foods,calories,sodium,note,source) "
        "VALUES(?,?,?,?,?,?,?,'manual')",
        (pid, log_date, meal, foods, kcal, sodium, (data.get("note") or "").strip()[:200]),
    )
    db.audit(current_user()["name"], "diet_log", f"patient:{pid}", f"{log_date} {meal} {foods[:60]}")
    return jsonify({"ok": True, "data": {"id": lid, "calories": kcal, "sodium": sodium,
                                          "estimated": estimated}})


@bp.post("/patients/<int:pid>/diet/photo")
@login_required
def upload_photo(pid):
    if not _can_access(pid):
        return jsonify({"ok": False, "error": "无权操作该患者档案"}), 403
    return _upload_photo(pid)


@bp.post("/my/diet/photo")
@login_required
def upload_my_photo():
    """患者端拍照上传：自动落到本人档案。"""
    pid = current_user().get("patient_id")
    if not pid:
        return jsonify({"ok": False, "error": "当前账号未绑定健康档案"}), 404
    return _upload_photo(pid)


def _upload_photo(pid):
    """上传饮食照片 → 本地分析 → 自动写入饮食记录。"""
    if not _patient_exists(pid):
        return jsonify({"ok": False, "error": "患者不存在"}), 404

    file = request.files.get("photo")
    if not file:
        return jsonify({"ok": False, "error": "请选择要上传的饮食照片"}), 400
    meal = (request.form.get("meal") or "").strip()
    if meal not in MEAL_KEYS:
        return jsonify({"ok": False, "error": "请选择这是哪一餐"}), 400
    log_date = (request.form.get("log_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    if not DATE_RE.match(log_date):
        return jsonify({"ok": False, "error": "日期格式应为 YYYY-MM-DD"}), 400
    hint = (request.form.get("hint") or "").strip()[:120]

    try:
        rel, meta = diet_vision.save_upload(file, pid)
    except diet_vision.PhotoError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    from backend.services import agent  # 延迟导入，避免循环依赖

    bundle = agent.load_patient(pid) or {}
    patient = bundle.get("patient") or {}
    plan = diet.build_plan(patient, bundle.get("age") or 0,
                           bundle.get("conditions") or [], bundle.get("features"))
    abs_path = diet_vision.photo_abspath(rel)
    analysis = diet_vision.analyze(abs_path, patient, bundle.get("age"),
                                   bundle.get("conditions") or [], plan)

    kcal = analysis["estimated"]["kcal"]
    sodium = analysis["estimated"]["sodium"]
    if hint:
        est_kcal, est_na, hit = diet.estimate(hint)
        if hit:
            if est_kcal:
                kcal = int(round(kcal * 0.6 + est_kcal * 0.4))
            if est_na:
                sodium = int(round(sodium * 0.6 + est_na * 0.4))
            analysis["text_hint"] = hint
            analysis["fusion"] = "vision+text"
            analysis["summary"] += f" 结合您的文字补充（{hint}）已做修正。"

    foods = "拍照识别：" + "、".join(
        f"{c['name']} {c['share']:.0f}%" for c in analysis["categories"] if c["share"] >= 3)
    if hint:
        foods += f"；补充：{hint}"
    if len(foods) < 4:
        foods = "拍照记录的一餐"

    lid = db.execute(
        "INSERT INTO diet_logs(patient_id,log_date,meal,foods,calories,sodium,note,"
        "source,image_path,analysis) VALUES(?,?,?,?,?,?,?,'photo',?,?)",
        (pid, log_date, meal, foods, kcal, sodium,
         (request.form.get("note") or "").strip()[:200], rel,
         json.dumps(analysis, ensure_ascii=False)),
    )
    db.audit(current_user()["name"], "diet_photo", f"patient:{pid}",
             f"{log_date} {meal} score={analysis['score']} kcal={kcal}")

    analysis["image_url"] = f"/api/patients/{pid}/diet/photos/{rel.split('/')[-1]}"
    return jsonify({"ok": True, "data": {
        "id": lid, "log_date": log_date, "meal": meal, "meal_cn": MEAL_CN.get(meal, meal),
        "calories": kcal, "sodium": sodium, "foods": foods,
        "image_url": analysis["image_url"], "analysis": analysis, "file": meta,
        "summary": diet.build(pid)["summary"],
    }})


@bp.get("/patients/<int:pid>/diet/photos/<name>")
@login_required
def get_photo(pid, name):
    if not _can_access(pid):
        return jsonify({"ok": False, "error": "无权查看该照片"}), 403
    if not PHOTO_RE.match(name or ""):
        return jsonify({"ok": False, "error": "照片不存在"}), 404
    path = diet_vision.photo_abspath(f"diet/{pid}/{name}")
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "error": "照片不存在"}), 404
    return send_file(path, mimetype="image/jpeg", max_age=600)


@bp.delete("/patients/<int:pid>/diet/logs/<int:lid>")
@login_required
def del_log(pid, lid):
    if not _can_access(pid):
        return jsonify({"ok": False, "error": "无权操作该患者档案"}), 403
    row = db.query("SELECT * FROM diet_logs WHERE id=? AND patient_id=?", (lid, pid), one=True)
    if not row:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    if row.get("image_path"):
        path = diet_vision.photo_abspath(row["image_path"])
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    db.execute("DELETE FROM diet_logs WHERE id=? AND patient_id=?", (lid, pid))
    db.audit(current_user()["name"], "diet_log_delete", f"patient:{pid}", f"log:{lid}")
    return jsonify({"ok": True})
