"""用户管理：账号查询、新建、编辑、重置密码、启停与删除。"""
import random
import string

from flask import Blueprint, jsonify, request

from backend import db
from backend.api.auth import PHONE_RE, USERNAME_RE, current_user, roles_required

bp = Blueprint("users", __name__)

ROLES = {"admin", "doctor", "patient"}
ROLE_CN = {"admin": "管理员", "doctor": "医生", "patient": "患者"}


def _can_manage(actor_role, target_role):
    """账号管理仅由管理员承担，医生与患者不可访问。"""
    return actor_role == "admin"


def _active_admin_count(exclude_id=None):
    sql = "SELECT COUNT(*) c FROM users WHERE role='admin' AND status='active'"
    if exclude_id:
        sql += " AND id<>?"
        return db.query(sql, (exclude_id,), one=True)["c"]
    return db.query(sql, one=True)["c"]


@bp.get("/users")
@roles_required("admin")
def list_users():
    q = (request.args.get("q") or "").strip()
    role = request.args.get("role") or ""
    status = request.args.get("status") or ""
    sql = ("SELECT u.*, p.name patient_name, p.phone patient_phone "
           "FROM users u LEFT JOIN patients p ON p.id=u.patient_id WHERE 1=1")
    args = []
    if q:
        sql += " AND (u.username LIKE ? OR u.display_name LIKE ? OR IFNULL(p.name,'') LIKE ?)"
        args += [f"%{q}%"] * 3
    if role in ROLES:
        sql += " AND u.role=?"
        args.append(role)
    if status in ("active", "disabled"):
        sql += " AND u.status=?"
        args.append(status)
    sql += " ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'doctor' THEN 1 ELSE 2 END, u.id"
    rows = db.query(sql, args)
    me = current_user()

    items = []
    for r in rows:
        items.append({
            "id": r["id"], "username": r["username"], "display_name": r["display_name"],
            "role": r["role"], "role_cn": ROLE_CN.get(r["role"], r["role"]),
            "title": r["title"] or "", "phone": r["phone"] or r["patient_phone"] or "",
            "patient_id": r["patient_id"], "patient_name": r["patient_name"],
            "theme": r["theme"], "status": r["status"] or "active",
            "last_login_at": r["last_login_at"], "created_at": r["created_at"],
            "is_self": r["id"] == me["id"],
            "manageable": _can_manage(me["role"], r["role"]),
        })

    all_rows = db.query("SELECT role, status FROM users")
    stats = {
        "total": len(all_rows),
        "admin": sum(1 for x in all_rows if x["role"] == "admin"),
        "doctor": sum(1 for x in all_rows if x["role"] == "doctor"),
        "patient": sum(1 for x in all_rows if x["role"] == "patient"),
        "active": sum(1 for x in all_rows if (x["status"] or "active") == "active"),
        "disabled": sum(1 for x in all_rows if x["status"] == "disabled"),
        "bound": db.query("SELECT COUNT(*) c FROM users WHERE patient_id IS NOT NULL",
                          one=True)["c"],
    }
    return jsonify({"ok": True, "data": {"items": items, "stats": stats,
                                         "role_meta": ROLE_CN}})


@bp.get("/users/options")
@roles_required("admin")
def user_options():
    """新建/编辑账号时需要的可绑定档案列表。"""
    rows = db.query(
        "SELECT p.id, p.name, p.gender, p.phone, p.risk_level, "
        "(SELECT username FROM users u WHERE u.patient_id=p.id) bound_user "
        "FROM patients p ORDER BY p.id")
    return jsonify({"ok": True, "data": [
        {"id": r["id"], "name": r["name"], "gender": r["gender"], "phone": r["phone"],
         "risk_level": r["risk_level"], "bound_user": r["bound_user"]} for r in rows]})


def _validate_payload(data, editing=None):
    username = (data.get("username") or "").strip() if not editing else None
    password = (data.get("password") or "").strip()
    display_name = (data.get("display_name") or "").strip()
    role = (data.get("role") or "patient").strip()
    phone = (data.get("phone") or "").strip()
    patient_id = data.get("patient_id")

    if editing is None:
        if not USERNAME_RE.match(username or ""):
            return "账号需以字母开头，3–20 位字母、数字或下划线"
    if password and len(password) < 6:
        return "密码至少 6 位"
    if editing is None and not password:
        return "请设置初始密码"
    if not (2 <= len(display_name) <= 20):
        return "请填写 2–20 个字的姓名"
    if role not in ROLES:
        return "角色不合法"
    if phone and not PHONE_RE.match(phone):
        return "手机号格式不正确"
    if role == "patient":
        try:
            patient_id = int(patient_id)
        except (TypeError, ValueError):
            return "患者账号必须绑定一份健康档案"
        if not db.query("SELECT id FROM patients WHERE id=?", (patient_id,), one=True):
            return "绑定的健康档案不存在"
        clash = db.query("SELECT username FROM users WHERE patient_id=? AND id<>?",
                         (patient_id, editing or 0), one=True)
        if clash:
            return f"该档案已绑定账号 {clash['username']}"
    else:
        patient_id = None
    return {"username": username, "password": password, "display_name": display_name,
            "role": role, "phone": phone or None, "patient_id": patient_id,
            "title": (data.get("title") or "").strip() or None}


@bp.post("/users")
@roles_required("admin")
def create_user():
    data = request.get_json(silent=True) or {}
    me = current_user()
    role = (data.get("role") or "patient").strip()
    if not _can_manage(me["role"], role):
        return jsonify({"ok": False, "error": "仅管理员可以创建账号"}), 403
    if USERNAME_RE.match((data.get("username") or "").strip()) and db.query(
            "SELECT id FROM users WHERE username=?", (data["username"].strip(),), one=True):
        return jsonify({"ok": False, "error": "该账号已存在"}), 409
    parsed = _validate_payload(data)
    if isinstance(parsed, str):
        return jsonify({"ok": False, "error": parsed}), 400
    if db.query("SELECT id FROM users WHERE username=?", (parsed["username"],), one=True):
        return jsonify({"ok": False, "error": "该账号已存在"}), 409
    uid = db.execute(
        "INSERT INTO users(username,password,role,display_name,title,phone,patient_id,theme,status) "
        "VALUES(?,?,?,?,?,?,?,?, 'active')",
        (parsed["username"], parsed["password"], parsed["role"], parsed["display_name"],
         parsed["title"], parsed["phone"], parsed["patient_id"],
         "green" if parsed["role"] != "admin" else "blue"),
    )
    db.audit(me["name"], "create_user", parsed["username"],
             f"新建{ROLE_CN[parsed['role']]}账号", me["id"])
    return jsonify({"ok": True, "data": {"id": uid}})


@bp.put("/users/<int:uid>")
@roles_required("admin")
def update_user(uid):
    me = current_user()
    row = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "账号不存在"}), 404
    if uid == me["id"] and row["role"] != "patient":
        data0 = request.get_json(silent=True) or {}
        if (data0.get("status") or row["status"]) != "active" or \
                (data0.get("role") and data0["role"] != row["role"]):
            return jsonify({"ok": False, "error": "不能停用或修改自己的角色"}), 400
    if not _can_manage(me["role"], row["role"]):
        return jsonify({"ok": False, "error": "无权修改该账号"}), 403
    data = request.get_json(silent=True) or {}
    target_role = (data.get("role") or row["role"]).strip()
    if not _can_manage(me["role"], target_role):
        return jsonify({"ok": False, "error": "无权把账号改为该角色"}), 403
    parsed = _validate_payload({**data, "role": target_role}, editing=uid)
    if isinstance(parsed, str):
        return jsonify({"ok": False, "error": parsed}), 400

    if row["role"] == "admin" and target_role != "admin" and _active_admin_count(uid) == 0:
        return jsonify({"ok": False, "error": "系统至少保留一个可用的管理员账号"}), 400
    status = (data.get("status") or row["status"] or "active").strip()
    if status not in ("active", "disabled"):
        status = "active"
    if uid == me["id"] and (status != "active" or target_role != row["role"]):
        return jsonify({"ok": False, "error": "不能停用或修改自己的角色"}), 400
    if row["role"] == "admin" and status != "active" and _active_admin_count(uid) == 0:
        return jsonify({"ok": False, "error": "系统至少保留一个可用的管理员账号"}), 400

    if parsed["password"]:
        db.execute("UPDATE users SET password=? WHERE id=?", (parsed["password"], uid))
    db.execute(
        "UPDATE users SET display_name=?, role=?, title=?, phone=?, patient_id=?, status=? "
        "WHERE id=?",
        (parsed["display_name"], target_role, parsed["title"], parsed["phone"],
         parsed["patient_id"], status, uid),
    )
    db.audit(me["name"], "update_user", row["username"],
             f"更新账号（角色 {ROLE_CN.get(target_role, target_role)}，状态 {status}）", me["id"])
    return jsonify({"ok": True, "data": {"id": uid}})


@bp.post("/users/<int:uid>/password")
@roles_required("admin")
def reset_password(uid):
    me = current_user()
    row = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "账号不存在"}), 404
    if not _can_manage(me["role"], row["role"]):
        return jsonify({"ok": False, "error": "无权重置该账号密码"}), 403
    data = request.get_json(silent=True) or {}
    pwd = (data.get("password") or "").strip()
    generated = False
    if not pwd:
        pwd = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        generated = True
    if len(pwd) < 6:
        return jsonify({"ok": False, "error": "密码至少 6 位"}), 400
    db.execute("UPDATE users SET password=? WHERE id=?", (pwd, uid))
    db.audit(me["name"], "reset_password", row["username"], "重置登录密码", me["id"])
    return jsonify({"ok": True, "data": {"password": pwd, "generated": generated}})


@bp.post("/users/<int:uid>/status")
@roles_required("admin")
def toggle_status(uid):
    me = current_user()
    row = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "账号不存在"}), 404
    if uid == me["id"]:
        return jsonify({"ok": False, "error": "不能停用自己的账号"}), 400
    if not _can_manage(me["role"], row["role"]):
        return jsonify({"ok": False, "error": "无权修改该账号"}), 403
    next_status = "disabled" if (row["status"] or "active") == "active" else "active"
    if next_status == "disabled" and row["role"] == "admin" and _active_admin_count(uid) == 0:
        return jsonify({"ok": False, "error": "系统至少保留一个可用的管理员账号"}), 400
    db.execute("UPDATE users SET status=? WHERE id=?", (next_status, uid))
    db.audit(me["name"], "toggle_user", row["username"],
             "停用账号" if next_status == "disabled" else "启用账号", me["id"])
    return jsonify({"ok": True, "data": {"status": next_status}})


@bp.delete("/users/<int:uid>")
@roles_required("admin")
def delete_user(uid):
    me = current_user()
    row = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not row:
        return jsonify({"ok": False, "error": "账号不存在"}), 404
    if uid == me["id"]:
        return jsonify({"ok": False, "error": "不能删除自己的账号"}), 400
    if not _can_manage(me["role"], row["role"]):
        return jsonify({"ok": False, "error": "无权删除该账号"}), 403
    if row["role"] == "admin" and _active_admin_count() <= 1:
        return jsonify({"ok": False, "error": "系统至少保留一个管理员账号"}), 400
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.audit(me["name"], "delete_user", row["username"], "删除账号", me["id"])
    return jsonify({"ok": True, "data": {"id": uid}})
