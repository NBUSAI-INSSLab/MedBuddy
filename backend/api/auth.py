"""认证、注册与用户信息。"""
import re
from functools import wraps

from flask import Blueprint, jsonify, request, session

from backend import db

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
AVATAR_COLORS = ["#0ea5e9", "#f97316", "#22c55e", "#8b5cf6", "#ef4444",
                 "#14b8a6", "#eab308", "#ec4899"]


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("uid"):
            return jsonify({"ok": False, "error": "未登录"}), 401
        return fn(*a, **kw)
    return wrapper


def roles_required(*roles):
    """在 login_required 基础上限制角色。"""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("uid"):
                return jsonify({"ok": False, "error": "未登录"}), 401
            if session.get("role") not in roles:
                return jsonify({"ok": False, "error": "当前账号无权执行该操作"}), 403
            return fn(*a, **kw)
        return wrapper
    return deco


def current_user():
    return {
        "id": session.get("uid"),
        "name": session.get("name"),
        "role": session.get("role"),
        "patient_id": session.get("patient_id"),
        "username": session.get("username"),
    }


def _session_login(row):
    session["uid"] = row["id"]
    session["name"] = row["display_name"]
    session["role"] = row["role"]
    session["patient_id"] = row["patient_id"]
    session["username"] = row["username"]


def _public_user(row):
    return {
        "id": row["id"], "name": row["display_name"], "role": row["role"],
        "patient_id": row["patient_id"], "theme": row["theme"], "title": row["title"],
        "username": row["username"],
    }


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    row = db.query("SELECT * FROM users WHERE username=?", (username,), one=True)
    if not row or row["password"] != password:
        return jsonify({"ok": False, "error": "账号或密码不正确"}), 401
    if (row.get("status") or "active") != "active":
        return jsonify({"ok": False, "error": "该账号已被停用，请联系管理员"}), 403
    db.execute("UPDATE users SET last_login_at=? WHERE id=?", (db.now(), row["id"]))
    _session_login(row)
    db.audit(row["display_name"], "login", row["username"], "登录成功", row["id"])
    return jsonify({"ok": True, "data": _public_user(row)})


@bp.post("/auth/register")
def register():
    """居民自助注册：校验通过后自动建号，并按手机号匹配或新建健康档案。"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    gender = (data.get("gender") or "").strip()
    city = (data.get("city") or "").strip()

    if not USERNAME_RE.match(username):
        return jsonify({"ok": False, "error": "账号需以字母开头，3–20 位字母、数字或下划线"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "密码至少 6 位"}), 400
    if not (2 <= len(name) <= 20):
        return jsonify({"ok": False, "error": "请填写 2–20 个字的真实姓名"}), 400
    if not PHONE_RE.match(phone):
        return jsonify({"ok": False, "error": "请填写正确的 11 位手机号"}), 400
    if db.query("SELECT id FROM users WHERE username=?", (username,), one=True):
        return jsonify({"ok": False, "error": "该账号已被占用，请换一个"}), 409

    patient = db.query(
        "SELECT * FROM patients WHERE name=? AND REPLACE(phone,' ','')=?",
        (name, phone), one=True)
    created_profile = False
    if patient:
        bound = db.query("SELECT id FROM users WHERE patient_id=?", (patient["id"],), one=True)
        if bound:
            return jsonify({"ok": False, "error": "该健康档案已绑定账号，请直接登录或联系医生"}), 409
        pid = patient["id"]
    else:
        same_name = db.query("SELECT * FROM patients WHERE name=? ORDER BY id LIMIT 1",
                             (name,), one=True)
        if same_name:
            bound = db.query("SELECT id FROM users WHERE patient_id=?",
                             (same_name["id"],), one=True)
            if bound:
                return jsonify({"ok": False, "error": "该姓名已有绑定账号，请直接登录或联系医生"}), 409
            return jsonify({"ok": False, "error":
                            "系统中已有同名健康档案，请填写建档时登记的手机号；如号码已变更请联系医生"}), 409
        av = AVATAR_COLORS[int(phone[-1]) % len(AVATAR_COLORS)]
        pid = db.execute(
            "INSERT INTO patients(name,gender,phone,city,risk_level,risk_score,"
            "enrolled_at,avatar_color,note) VALUES(?,?,?,?,'low',0,?,?,?)",
            (name, gender or None, phone, city or None, db.now()[:10], av,
             "居民自助注册，档案待医生完善"),
        )
        created_profile = True

    uid = db.execute(
        "INSERT INTO users(username,password,role,display_name,title,phone,patient_id,theme,status) "
        "VALUES(?,?,'patient',?,?,?,?,?,'active')",
        (username, password, name, "自助注册居民", phone, pid, "green"),
    )
    row = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    _session_login(row)
    db.execute("UPDATE users SET last_login_at=? WHERE id=?", (db.now(), uid))
    db.audit(name, "register", username,
             f"居民自助注册{'（新建档案 #%d）' % pid if created_profile else '（绑定档案 #%d）' % pid}", uid)
    return jsonify({"ok": True, "data": {
        **_public_user(row),
        "created_profile": created_profile, "patient_id": pid,
        "message": "注册成功，已为你创建健康档案" if created_profile
                   else "注册成功，已关联你原有的健康档案",
    }})


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/auth/me")
def me():
    if not session.get("uid"):
        return jsonify({"ok": False, "error": "未登录"}), 401
    row = db.query("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)
    if not row or (row.get("status") or "active") != "active":
        session.clear()
        return jsonify({"ok": False, "error": "未登录"}), 401
    return jsonify({"ok": True, "data": _public_user(row)})


@bp.put("/auth/theme")
@login_required
def set_theme():
    data = request.get_json(silent=True) or {}
    theme = data.get("theme") or "green"
    db.execute("UPDATE users SET theme=? WHERE id=?", (theme, session["uid"]))
    return jsonify({"ok": True, "data": {"theme": theme}})
