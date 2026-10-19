"""智能体会话：会话管理 + SSE 流式对话。"""
import json

from flask import Blueprint, Response, jsonify, request, session, stream_with_context

from backend import db
from backend.api.auth import current_user, login_required
from backend.services import agent

bp = Blueprint("chat", __name__)


@bp.get("/conversations")
@login_required
def list_conversations():
    pid = request.args.get("patient_id", type=int)
    if pid:
        rows = db.query(
            "SELECT * FROM conversations WHERE patient_id=? ORDER BY updated_at DESC", (pid,))
    else:
        rows = db.query("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 50")
    for r in rows:
        last = db.query(
            "SELECT content, created_at FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
            (r["id"],), one=True)
        r["last_message"] = (last["content"][:60] if last else "")
        r["message_count"] = db.query(
            "SELECT COUNT(*) c FROM messages WHERE conversation_id=?", (r["id"],), one=True)["c"]
    return jsonify({"ok": True, "data": rows})


@bp.post("/conversations")
@login_required
def create_conversation():
    data = request.get_json(silent=True) or {}
    pid = data.get("patient_id")
    if not pid:
        return jsonify({"ok": False, "error": "缺少 patient_id"}), 400
    cid = db.execute(
        "INSERT INTO conversations(patient_id,user_id,title) VALUES(?,?,?)",
        (pid, session["uid"], data.get("title") or "新的健康咨询"),
    )
    return jsonify({"ok": True, "data": {"id": cid}})


@bp.delete("/conversations/<int:cid>")
@login_required
def delete_conversation(cid):
    db.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
    db.execute("DELETE FROM conversations WHERE id=?", (cid,))
    return jsonify({"ok": True})


@bp.get("/conversations/<int:cid>/messages")
@login_required
def messages(cid):
    conv = db.query("SELECT * FROM conversations WHERE id=?", (cid,), one=True)
    if not conv:
        return jsonify({"ok": False, "error": "会话不存在"}), 404
    rows = db.query("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,))
    for r in rows:
        r["citations"] = json.loads(r["citations_json"]) if r["citations_json"] else []
        r["meta"] = json.loads(r["meta_json"]) if r["meta_json"] else {}
    return jsonify({"ok": True, "data": {"conversation": conv, "messages": rows}})


@bp.post("/chat/stream")
@login_required
def chat_stream():
    data = request.get_json(silent=True) or {}
    pid = data.get("patient_id")
    question = (data.get("message") or "").strip()
    if not pid or not question:
        return jsonify({"ok": False, "error": "参数不完整"}), 400
    if len(question) > 1000:
        return jsonify({"ok": False, "error": "问题过长，请精简到 1000 字以内"}), 400

    cid = data.get("conversation_id")
    if not cid:
        title = question[:18] + ("…" if len(question) > 18 else "")
        cid = db.execute("INSERT INTO conversations(patient_id,user_id,title) VALUES(?,?,?)",
                         (pid, session["uid"], title))
    db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",
               (cid, "user", question))
    db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), cid))
    actor = current_user()["name"]
    db.audit(actor, "chat_question", f"patient:{pid}", question[:120])

    def gen():
        yield f"event: conversation\ndata: {json.dumps({'conversation_id': cid}, ensure_ascii=False)}\n\n"
        try:
            for evt in agent.stream_answer(pid, question, cid, actor=actor):
                payload = json.dumps(evt["data"], ensure_ascii=False)
                yield f"event: {evt['event']}\ndata: {payload}\n\n"
        except Exception as e:
            err = json.dumps({"message": f"服务异常：{e}"}, ensure_ascii=False)
            yield f"event: error\ndata: {err}\n\n"
        yield "event: end\ndata: {}\n\n"

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})
