"""管理员配置专家数字人与专家团：人设、知识库、技能与外部工具（MCP）。"""
import json
import secrets

from flask import Blueprint, jsonify, request

from backend import db
from backend.api.auth import current_user, roles_required
from backend.services import expert_meta, experts

bp = Blueprint("expert_admin", __name__)

MAX_ITEMS = 12


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    text = str(value)
    for sep in ("\n", "，", ",", "、", ";"):
        text = text.replace(sep, "\n")
    return [x.strip() for x in text.split("\n") if x.strip()]


def _int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _clean_tools(items):
    out, seen = [], set()
    for item in (items if isinstance(items, list) else _as_list(items)):
        if isinstance(item, str):
            key = item.strip()
            if not key or key in seen:
                continue
            base = expert_meta.MCP_MAP.get(key)
            if base:
                out.append(dict(base))
                seen.add(key)
            continue
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        name = str(item.get("name") or "").strip()
        if not key and name:
            key = "custom_" + secrets.token_hex(4)
        if not key or key in seen:
            continue
        base = expert_meta.MCP_MAP.get(key, {})
        out.append({
            "key": key,
            "name": name or base.get("name") or key,
            "desc": str(item.get("desc") or base.get("desc") or "").strip(),
            "builtin": bool(base.get("builtin", False)),
            "custom": key not in expert_meta.MCP_MAP,
        })
        seen.add(key)
        if len(out) >= MAX_ITEMS:
            break
    return out


def _clean_skills(items):
    out, seen = [], set()
    for key in _as_list(items):
        key = str(key).strip()
        if key and key in expert_meta.SKILL_MAP and key not in seen:
            out.append(key)
            seen.add(key)
    return out


def _clean_kb(items):
    out = []
    for x in _as_list(items):
        did = _int(x, 0)
        if did and did not in out:
            out.append(did)
    if out:
        marks = ",".join("?" * len(out))
        valid = {r["id"] for r in db.query(
            f"SELECT id FROM kb_documents WHERE id IN ({marks})", out)}
        out = [d for d in out if d in valid]
    return out


def _payload(data, current=None):
    current = current or {}
    name = str(data.get("name") or current.get("name") or "").strip()
    if len(name) < 2:
        return None, "专家姓名至少 2 个字"
    role_key = str(data.get("role_key") or current.get("role_key") or "gp")
    if role_key not in {r["key"] for r in expert_meta.ROLE_CATALOG}:
        role_key = "gp"
    tags = _as_list(data.get("tags")) if "tags" in data else current.get("tags", [])
    questions = (_as_list(data.get("questions")) if "questions" in data
                 else current.get("questions", []))
    fields = {
        "name": name,
        "initials": str(data.get("initials") or name[:1])[:2],
        "title": str(data.get("title") or current.get("title") or "")[:60],
        "dept": str(data.get("dept") or current.get("dept") or "")[:40],
        "org": str(data.get("org") or current.get("org") or "")[:60],
        "role_key": role_key,
        "years": max(0, min(60, _int(data.get("years", current.get("years", 10)), 10))),
        "cases": str(data.get("cases") or current.get("cases") or "")[:20],
        "tags": [str(t)[:16] for t in tags][:8],
        "intro": str(data.get("intro") or current.get("intro") or "")[:240],
        "style": str(data.get("style") or current.get("style") or "")[:80],
        "greeting": str(data.get("greeting") or current.get("greeting") or "")[:200],
        "questions": [str(q)[:40] for q in questions][:5],
        "color": str(data.get("color") or current.get("color") or "#0f766e")[:9],
        "color2": str(data.get("color2") or current.get("color2") or "#0d9488")[:9],
        "skills": _clean_skills(data["skills"]) if "skills" in data
        else current.get("skills", []),
        "kb_doc_ids": _clean_kb(data["kb_doc_ids"]) if "kb_doc_ids" in data
        else current.get("kb_doc_ids", []),
        "mcp_tools": _clean_tools(data["mcp_tools"]) if "mcp_tools" in data
        else current.get("mcp_tools", []),
        "status": "paused" if str(data.get("status") or current.get("status")) == "paused" else "active",
        "sort": _int(data.get("sort", current.get("sort", 99)), 99),
    }
    return fields, None


def _current_expert(row):
    """把数据库行还原为可回填的表单结构（技能/工具保持原始 key）。"""
    def raw(key):
        try:
            val = json.loads(row[key] or "[]")
            return val if isinstance(val, list) else []
        except (TypeError, ValueError):
            return []
    return {
        "name": row["name"], "title": row["title"], "dept": row["dept"], "org": row["org"],
        "role_key": row["role_key"], "years": row["years"], "cases": row["cases"],
        "tags": raw("tags"), "intro": row["intro"], "style": row["style"],
        "greeting": row["greeting"], "questions": raw("questions"),
        "color": row["color"], "color2": row["color2"],
        "skills": raw("skills"), "kb_doc_ids": raw("kb_doc_ids"), "mcp_tools": raw("mcp_tools"),
        "status": row["status"], "sort": row["sort"],
    }


def _row_expert(eid):
    return db.query("SELECT * FROM expert_profiles WHERE id=?", (eid,), one=True)


def _row_team(tid):
    return db.query("SELECT * FROM expert_teams WHERE id=?", (tid,), one=True)


def _expert_detail(e):
    return {
        "db_id": e["db_id"], "code": e["id"], "name": e["name"], "initials": e["initials"],
        "title": e["title"], "dept": e["dept"], "org": e["org"], "role_key": e["role_key"],
        "years": e["years"], "cases": e["cases"], "tags": e["tags"], "intro": e["intro"],
        "style": e["style"], "greeting": e["greeting"], "questions": e["questions"],
        "color": e["color"], "color2": e["color2"], "status": e["status"],
        "skills": e["skills"], "tools": e["tools"], "kb_docs": e["kb_docs"],
        "kb_doc_ids": e["kb_doc_ids"], "mcp_tools": e["raw_tools"],
        "sessions": db.query(
            "SELECT COUNT(*) c FROM expert_sessions WHERE target_type='expert' AND target_id=?",
            (e["id"],), one=True)["c"],
    }


def _team_detail(t):
    return {
        "db_id": t["db_id"], "code": t["id"], "name": t["name"], "desc": t["desc"],
        "tags": t["tags"], "scenario": t["scenario"], "status": t["status"],
        "member_ids": t["member_ids"], "members": t["members"],
        "skills": t["skills"], "tools": t["tools"], "kb_docs": t["kb_docs"],
        "kb_doc_ids": t["kb_doc_ids"], "mcp_tools": t["raw_tools"],
        "sessions": db.query(
            "SELECT COUNT(*) c FROM expert_sessions WHERE target_type='team' AND target_id=?",
            (t["id"],), one=True)["c"],
    }


@bp.get("/admin/experts")
@roles_required("admin")
def overview():
    exps = [_expert_detail(e) for e in experts.all_experts(include_paused=True)]
    teams = [_team_detail(t) for t in experts.all_teams(include_paused=True,
                                                        experts=experts.all_experts(True))]
    kb = db.query("SELECT id,title,category,doc_type FROM kb_documents ORDER BY category, id")
    used_kb = set()
    for item in exps + teams:
        used_kb.update(item["kb_doc_ids"])
    stats = {
        "experts": len(exps), "teams": len(teams),
        "paused": sum(1 for x in exps + teams if x["status"] == "paused"),
        "kb_bound": len(used_kb),
        "skills": len({s["key"] for item in exps + teams for s in item["skills"]}),
        "tools": len({t["key"] for item in exps + teams for t in item["tools"]}),
        "sessions": db.query("SELECT COUNT(*) c FROM expert_sessions", one=True)["c"],
    }
    return jsonify({"ok": True, "data": {
        "experts": exps, "teams": teams, "stats": stats,
        "catalog": {
            "skills": expert_meta.SKILL_CATALOG,
            "mcp": expert_meta.MCP_CATALOG,
            "roles": expert_meta.ROLE_CATALOG,
            "kb": kb,
        },
    }})


@bp.post("/admin/experts")
@roles_required("admin")
def create_expert():
    data = request.get_json(silent=True) or {}
    fields, err = _payload(data)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    if db.query("SELECT id FROM expert_profiles WHERE name=?", (fields["name"],), one=True):
        return jsonify({"ok": False, "error": "已有同名专家，请换一个姓名"}), 400
    code = "exp_" + secrets.token_hex(5)
    eid = db.execute(
        "INSERT INTO expert_profiles(code,name,initials,title,dept,org,role_key,years,cases,tags,"
        "intro,style,greeting,questions,color,color2,skills,kb_doc_ids,mcp_tools,status,sort) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (code, fields["name"], fields["initials"], fields["title"], fields["dept"],
         fields["org"], fields["role_key"], fields["years"], fields["cases"],
         json.dumps(fields["tags"], ensure_ascii=False), fields["intro"], fields["style"],
         fields["greeting"], json.dumps(fields["questions"], ensure_ascii=False),
         fields["color"], fields["color2"],
         json.dumps(fields["skills"], ensure_ascii=False),
         json.dumps(fields["kb_doc_ids"]),
         json.dumps(fields["mcp_tools"], ensure_ascii=False),
         fields["status"], fields["sort"]))
    db.audit(current_user()["name"], "expert_create", f"expert:{code}", fields["name"])
    return jsonify({"ok": True, "data": {"db_id": eid, "code": code}})


@bp.put("/admin/experts/<int:eid>")
@roles_required("admin")
def update_expert(eid):
    row = _row_expert(eid)
    if not row:
        return jsonify({"ok": False, "error": "专家不存在"}), 404
    current = _current_expert(row)
    data = request.get_json(silent=True) or {}
    fields, err = _payload(data, current)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    dup = db.query("SELECT id FROM expert_profiles WHERE name=? AND id<>?",
                   (fields["name"], eid), one=True)
    if dup:
        return jsonify({"ok": False, "error": "已有同名专家，请换一个姓名"}), 400
    db.execute(
        "UPDATE expert_profiles SET name=?,initials=?,title=?,dept=?,org=?,role_key=?,years=?,"
        "cases=?,tags=?,intro=?,style=?,greeting=?,questions=?,color=?,color2=?,skills=?,"
        "kb_doc_ids=?,mcp_tools=?,status=?,sort=?,updated_at=? WHERE id=?",
        (fields["name"], fields["initials"], fields["title"], fields["dept"], fields["org"],
         fields["role_key"], fields["years"], fields["cases"],
         json.dumps(fields["tags"], ensure_ascii=False), fields["intro"], fields["style"],
         fields["greeting"], json.dumps(fields["questions"], ensure_ascii=False),
         fields["color"], fields["color2"],
         json.dumps(fields["skills"], ensure_ascii=False),
         json.dumps(fields["kb_doc_ids"]),
         json.dumps(fields["mcp_tools"], ensure_ascii=False),
         fields["status"], fields["sort"], db.now(), eid))
    db.audit(current_user()["name"], "expert_update", f"expert:{row['code']}", fields["name"])
    return jsonify({"ok": True})


@bp.post("/admin/experts/<int:eid>/status")
@roles_required("admin")
def toggle_expert(eid):
    row = _row_expert(eid)
    if not row:
        return jsonify({"ok": False, "error": "专家不存在"}), 404
    status = "paused" if row["status"] == "active" else "active"
    db.execute("UPDATE expert_profiles SET status=?,updated_at=? WHERE id=?",
               (status, db.now(), eid))
    db.audit(current_user()["name"], "expert_status", f"expert:{row['code']}", status)
    return jsonify({"ok": True, "data": {"status": status}})


@bp.delete("/admin/experts/<int:eid>")
@roles_required("admin")
def delete_expert(eid):
    row = _row_expert(eid)
    if not row:
        return jsonify({"ok": False, "error": "专家不存在"}), 404
    used = db.query(
        "SELECT COUNT(*) c FROM expert_sessions WHERE target_type='expert' AND target_id=?",
        (row["code"],), one=True)["c"]
    if used:
        return jsonify({"ok": False,
                        "error": f"该专家已有 {used} 次会诊记录，建议改为「停用」而不是删除"}), 400
    for t in db.query("SELECT id,member_codes FROM expert_teams"):
        codes = [c for c in experts._json_list(t["member_codes"]) if c != row["code"]]
        db.execute("UPDATE expert_teams SET member_codes=? WHERE id=?",
                   (json.dumps(codes, ensure_ascii=False), t["id"]))
    db.execute("DELETE FROM expert_profiles WHERE id=?", (eid,))
    db.audit(current_user()["name"], "expert_delete", f"expert:{row['code']}", row["name"])
    return jsonify({"ok": True})


@bp.post("/admin/expert-teams")
@roles_required("admin")
def create_team():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if len(name) < 2:
        return jsonify({"ok": False, "error": "专家团名称至少 2 个字"}), 400
    if db.query("SELECT id FROM expert_teams WHERE name=?", (name,), one=True):
        return jsonify({"ok": False, "error": "已有同名专家团"}), 400
    members = [c for c in _as_list(data.get("member_ids") or data.get("member_codes"))
               if db.query("SELECT id FROM expert_profiles WHERE code=?", (c,), one=True)]
    if not members:
        return jsonify({"ok": False, "error": "请至少选择一位专家作为成员"}), 400
    code = "team_" + secrets.token_hex(5)
    tid = db.execute(
        "INSERT INTO expert_teams(code,name,desc,tags,scenario,member_codes,skills,kb_doc_ids,"
        "mcp_tools,status,sort) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (code, name, str(data.get("desc") or "")[:300],
         json.dumps([str(x)[:16] for x in _as_list(data.get("tags"))][:8], ensure_ascii=False),
         str(data.get("scenario") or "")[:160],
         json.dumps(members, ensure_ascii=False),
         json.dumps(_clean_skills(data.get("skills", [])), ensure_ascii=False),
         json.dumps(_clean_kb(data.get("kb_doc_ids", []))),
         json.dumps(_clean_tools(data.get("mcp_tools", [])), ensure_ascii=False),
         "paused" if str(data.get("status")) == "paused" else "active",
         _int(data.get("sort"), 99)))
    db.audit(current_user()["name"], "team_create", f"team:{code}", name)
    return jsonify({"ok": True, "data": {"db_id": tid, "code": code}})


@bp.put("/admin/expert-teams/<int:tid>")
@roles_required("admin")
def update_team(tid):
    row = _row_team(tid)
    if not row:
        return jsonify({"ok": False, "error": "专家团不存在"}), 404
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or row["name"]).strip()
    if len(name) < 2:
        return jsonify({"ok": False, "error": "专家团名称至少 2 个字"}), 400
    if db.query("SELECT id FROM expert_teams WHERE name=? AND id<>?", (name, tid), one=True):
        return jsonify({"ok": False, "error": "已有同名专家团"}), 400
    members = [c for c in _as_list(data.get("member_ids", experts._json_list(row["member_codes"])))
               if db.query("SELECT id FROM expert_profiles WHERE code=?", (c,), one=True)]
    if not members:
        return jsonify({"ok": False, "error": "请至少选择一位专家作为成员"}), 400
    db.execute(
        "UPDATE expert_teams SET name=?,desc=?,tags=?,scenario=?,member_codes=?,skills=?,"
        "kb_doc_ids=?,mcp_tools=?,status=?,sort=?,updated_at=? WHERE id=?",
        (name, str(data.get("desc", row["desc"]) or "")[:300],
         json.dumps([str(x)[:16] for x in _as_list(data.get("tags", experts._json_list(row["tags"])))][:8],
                    ensure_ascii=False),
         str(data.get("scenario", row["scenario"]) or "")[:160],
         json.dumps(members, ensure_ascii=False),
         json.dumps(_clean_skills(data.get("skills", experts._json_list(row["skills"]))),
                    ensure_ascii=False),
         json.dumps(_clean_kb(data.get("kb_doc_ids", experts._json_list(row["kb_doc_ids"])))),
         json.dumps(_clean_tools(data.get("mcp_tools", experts._json_list(row["mcp_tools"]))),
                    ensure_ascii=False),
         "paused" if str(data.get("status", row["status"])) == "paused" else "active",
         _int(data.get("sort", row["sort"]), 99), db.now(), tid))
    db.audit(current_user()["name"], "team_update", f"team:{row['code']}", name)
    return jsonify({"ok": True})


@bp.post("/admin/expert-teams/<int:tid>/status")
@roles_required("admin")
def toggle_team(tid):
    row = _row_team(tid)
    if not row:
        return jsonify({"ok": False, "error": "专家团不存在"}), 404
    status = "paused" if row["status"] == "active" else "active"
    db.execute("UPDATE expert_teams SET status=?,updated_at=? WHERE id=?",
               (status, db.now(), tid))
    db.audit(current_user()["name"], "team_status", f"team:{row['code']}", status)
    return jsonify({"ok": True, "data": {"status": status}})


@bp.delete("/admin/expert-teams/<int:tid>")
@roles_required("admin")
def delete_team(tid):
    row = _row_team(tid)
    if not row:
        return jsonify({"ok": False, "error": "专家团不存在"}), 404
    used = db.query(
        "SELECT COUNT(*) c FROM expert_sessions WHERE target_type='team' AND target_id=?",
        (row["code"],), one=True)["c"]
    if used:
        return jsonify({"ok": False,
                        "error": f"该专家团已有 {used} 次会诊记录，建议改为「停用」而不是删除"}), 400
    db.execute("DELETE FROM expert_teams WHERE id=?", (tid,))
    db.audit(current_user()["name"], "team_delete", f"team:{row['code']}", row["name"])
    return jsonify({"ok": True})
