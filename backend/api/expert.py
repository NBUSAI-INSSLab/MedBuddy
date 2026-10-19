"""专家会诊：数字人专家、多学科专家团、会诊会话与 SSE 流式作答。"""
import json
import time

from flask import Blueprint, Response, jsonify, request, session, stream_with_context

from backend import db
from backend.api.auth import current_user, login_required
from backend.services import agent, experts, llm, rag, safety

bp = Blueprint("expert", __name__)


def _pid_of(data=None):
    data = data or {}
    u = current_user()
    pid = data.get("patient_id") or u.get("patient_id")
    if pid and u.get("role") == "patient" and u.get("patient_id") != pid:
        return None, (jsonify({"ok": False, "error": "无权查看其他患者的会诊"}), 403)
    if not pid:
        return None, (jsonify({"ok": False, "error": "当前账号未绑定患者档案"}), 400)
    return int(pid), None


def _target_name(target):
    return target.get("name") if target else "专家会诊"


def _session_row(sid):
    return db.query("SELECT * FROM expert_sessions WHERE id=?", (sid,), one=True)


def _session_summary(sess):
    target, _ = experts.resolve(sess["target_type"], sess["target_id"])
    last = db.query(
        "SELECT content, created_at FROM expert_messages WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (sess["id"],), one=True)
    cnt = db.query("SELECT COUNT(*) c FROM expert_messages WHERE session_id=?",
                   (sess["id"],), one=True)["c"]
    return {
        "id": sess["id"], "patient_id": sess["patient_id"],
        "target_type": sess["target_type"], "target_id": sess["target_id"],
        "title": sess["title"], "created_at": sess["created_at"], "updated_at": sess["updated_at"],
        "target": target, "target_name": _target_name(target),
        "last_message": (last["content"][:70] if last else ""),
        "message_count": cnt,
    }


def _session_detail(sess):
    rows = db.query("SELECT * FROM expert_messages WHERE session_id=? ORDER BY id", (sess["id"],))
    for r in rows:
        r["meta"] = json.loads(r["meta_json"]) if r["meta_json"] else {}
    target, speakers = experts.resolve(sess["target_type"], sess["target_id"])
    return {
        "session": _session_summary(sess),
        "messages": rows,
        "speakers": [experts.public_expert(e) for e in speakers],
    }


def _insert_message(sid, role, speaker, content, meta=None):
    return db.execute(
        "INSERT INTO expert_messages(session_id,role,speaker_id,speaker_name,speaker_title,"
        "content,meta_json) VALUES(?,?,?,?,?,?,?)",
        (sid, role, speaker.get("id") if speaker else None,
         speaker.get("name") if speaker else None,
         speaker.get("title") if speaker else None,
         content, json.dumps(meta or {}, ensure_ascii=False)),
    )


def _speaker_event(speaker):
    return {k: speaker.get(k) for k in ("id", "name", "initials", "title", "dept",
                                        "org", "color", "color2", "role_key")}


@bp.get("/expert/roster")
@login_required
def roster():
    pid, err = _pid_of()
    if err:
        return err
    ctx = agent.load_patient(pid)
    if not ctx:
        return jsonify({"ok": False, "error": "患者不存在"}), 404
    sessions = db.query(
        "SELECT * FROM expert_sessions WHERE patient_id=? ORDER BY updated_at DESC LIMIT 20", (pid,))
    experts_list, teams = experts.roster()
    counts = {}
    for s in sessions:
        counts[s["target_id"]] = counts.get(s["target_id"], 0) + 1
    return jsonify({"ok": True, "data": {
        "experts": experts_list, "teams": teams,
        "sessions": [_session_summary(s) for s in sessions],
        "counts": counts,
        "patient": {
            "id": ctx["patient"]["id"], "name": ctx["patient"]["name"],
            "age": ctx["age"], "gender": ctx["patient"].get("gender"),
            "conditions": [c["name"] for c in ctx["conditions"]],
            "risk": ctx["risk"], "narrative": ctx["narrative"],
            "bp": ctx["features"].get("bp_latest"),
            "glucose": ctx["features"].get("glucose_latest"),
            "med_count": len(ctx["medications"]),
        },
    }})


@bp.post("/expert/sessions")
@login_required
def create_session():
    data = request.get_json(silent=True) or {}
    pid, err = _pid_of(data)
    if err:
        return err
    target_type = data.get("target_type") or "expert"
    target_id = (data.get("target_id") or "").strip()
    if target_type not in ("expert", "team"):
        return jsonify({"ok": False, "error": "会诊类型不正确"}), 400
    target, speakers = experts.resolve(target_type, target_id)
    if not target:
        return jsonify({"ok": False, "error": "专家或专家团不存在"}), 404
    ctx = agent.load_patient(pid)
    if not ctx:
        return jsonify({"ok": False, "error": "患者不存在"}), 404

    topic = (data.get("topic") or "").strip()[:40]
    title = topic or f"{target['name']}会诊"
    sid = db.execute(
        "INSERT INTO expert_sessions(patient_id,user_id,target_type,target_id,title) "
        "VALUES(?,?,?,?,?)",
        (pid, session["uid"], target_type, target_id, title),
    )
    if target_type == "team":
        for e, line in experts.team_greetings(ctx, target):
            _insert_message(sid, "expert", e, line, {"greeting": True})
    else:
        _insert_message(sid, "expert", speakers[0], experts.greeting(ctx, speakers[0]),
                        {"greeting": True})
    db.audit(current_user()["name"], "expert_session", f"patient:{pid}",
             f"{target_type}:{target_id} {title}")
    return jsonify({"ok": True, "data": _session_detail(_session_row(sid))})


@bp.get("/expert/sessions/<int:sid>")
@login_required
def get_session(sid):
    s = _session_row(sid)
    if not s:
        return jsonify({"ok": False, "error": "会诊记录不存在"}), 404
    pid, err = _pid_of({"patient_id": s["patient_id"]})
    if err:
        return err
    return jsonify({"ok": True, "data": _session_detail(s)})


@bp.delete("/expert/sessions/<int:sid>")
@login_required
def delete_session(sid):
    s = _session_row(sid)
    if not s:
        return jsonify({"ok": False, "error": "会诊记录不存在"}), 404
    pid, err = _pid_of({"patient_id": s["patient_id"]})
    if err:
        return err
    db.execute("DELETE FROM expert_messages WHERE session_id=?", (sid,))
    db.execute("DELETE FROM expert_sessions WHERE id=?", (sid,))
    db.audit(current_user()["name"], "expert_session_delete", f"patient:{s['patient_id']}", f"session:{sid}")
    return jsonify({"ok": True})


@bp.post("/expert/sessions/<int:sid>/stream")
@login_required
def stream(sid):
    s = _session_row(sid)
    if not s:
        return jsonify({"ok": False, "error": "会诊记录不存在"}), 404
    pid, err = _pid_of({"patient_id": s["patient_id"]})
    if err:
        return err
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "请输入会诊问题"}), 400
    if len(question) > 1000:
        return jsonify({"ok": False, "error": "问题过长，请精简到 1000 字以内"}), 400

    ctx = agent.load_patient(pid)
    if not ctx:
        return jsonify({"ok": False, "error": "患者不存在"}), 404
    target, speakers = experts.resolve(s["target_type"], s["target_id"])
    if not target or not speakers:
        return jsonify({"ok": False, "error": "会诊对象已下线"}), 404
    team = target if s["target_type"] == "team" else None

    history = db.query(
        "SELECT role, content FROM expert_messages WHERE session_id=? ORDER BY id DESC LIMIT 8",
        (sid,))[::-1]
    history = [{"role": "user" if h["role"] == "user" else "assistant", "content": h["content"]}
               for h in history]
    _insert_message(sid, "user", None, question)
    db.execute("UPDATE expert_sessions SET updated_at=? WHERE id=?", (db.now(), sid))

    actor = current_user()["name"]
    cfg = db.get_agent_config()
    safety_res = {"hit": False}
    if str(cfg.get("enable_safety", "1")) == "1":
        safety_res = safety.check(pid, question, safety.latest_metrics(pid))
    def gen():
        yield "event: meta\ndata: %s\n\n" % json.dumps({
            "session_id": sid, "target": target,
            "team": bool(team), "speakers": [_speaker_event(e) for e in speakers],
        }, ensure_ascii=False)

        prior = []
        message_ids = []
        if safety_res.get("hit"):
            sp = speakers[0]
            yield "event: speaker\ndata: %s\n\n" % json.dumps(_speaker_event(sp), ensure_ascii=False)
            text = safety.emergency_answer(ctx["patient"]["name"], safety_res)
            for piece in agent._chunk_text(text, 24):
                yield "event: delta\ndata: %s\n\n" % json.dumps({"text": piece}, ensure_ascii=False)
            mid = _insert_message(sid, "expert", sp, text,
                                  {"provider": "safety", "flags": ["emergency"], "citations": []})
            message_ids.append(mid)
        else:
            for idx, expert in enumerate(speakers):
                started = time.time()
                # 每位专家只检索自己绑定的知识库；未绑定则用全库
                chunks = rag.search(question, patient=ctx, top_k=3,
                                    doc_ids=expert.get("kb_doc_ids") or None)
                yield "event: speaker\ndata: %s\n\n" % json.dumps(
                    _speaker_event(expert), ensure_ascii=False)
                answer = ""
                flags = []
                produced = False
                try:
                    if cfg.get("provider") == "builtin":
                        iterator = experts.stream_builtin(
                            ctx, question, expert, prior=prior,
                            team_name=team["name"] if team else None)
                    else:
                        messages = experts.build_messages(
                            ctx, chunks, question, expert, history,
                            team=team, prior=prior)
                        iterator = llm.stream_chat(messages, cfg,
                                                   ctx=dict(ctx, chunks=chunks), question=question)
                    for piece in iterator:
                        produced = True
                        answer += piece
                        yield "event: delta\ndata: %s\n\n" % json.dumps({"text": piece}, ensure_ascii=False)
                    if cfg.get("provider") != "builtin" and not produced:
                        raise llm.LLMError("模型未返回内容")
                except llm.LLMError as e:
                    if not produced:
                        flags.append("llm_fallback")
                        note = f"> 在线模型暂不可用（{str(e)[:60]}），已切换会诊规则引擎。\n\n"
                        answer += note
                        yield "event: delta\ndata: %s\n\n" % json.dumps({"text": note}, ensure_ascii=False)
                        for piece in experts.stream_builtin(
                                ctx, question, expert, prior=prior,
                                team_name=team["name"] if team else None):
                            answer += piece
                            yield "event: delta\ndata: %s\n\n" % json.dumps({"text": piece}, ensure_ascii=False)

                before = len(answer)
                answer = experts.append_sources(answer, chunks)
                unknown = safety.check_drugs(answer, ctx["medications"])
                if unknown:
                    flags.append("drug_out_of_list")
                    answer += ("\n\n> 提示：" + "、".join(unknown[:3]) +
                               " 不在您当前的用药清单内，请勿自行购买服用。")
                if "不能替代" not in answer:
                    answer += "\n\n" + experts.DISCLAIMER
                if len(answer) > before:
                    for piece in agent._chunk_text(answer[before:], 30):
                        yield "event: delta\ndata: %s\n\n" % json.dumps({"text": piece}, ensure_ascii=False)

                latency = int((time.time() - started) * 1000)
                meta = {
                    "provider": cfg.get("provider"),
                    "model": cfg.get("model") if cfg.get("provider") != "builtin" else "会诊规则引擎",
                    "latency_ms": latency, "flags": flags, "citations": chunks,
                    "team": team["name"] if team else None,
                    "skills": [s["name"] for s in (expert.get("skills") or [])],
                    "tools": [t["name"] for t in (expert.get("tools") or [])],
                    "kb": len(expert.get("kb_doc_ids") or []),
                }
                mid = _insert_message(sid, "expert", expert, answer.strip(), meta)
                message_ids.append(mid)
                prior.append(f"{expert['name']}（{expert['dept']}）：{answer.strip()[:180]}")

        db.execute("UPDATE expert_sessions SET updated_at=? WHERE id=?", (db.now(), sid))
        db.audit(actor, "expert_consult", f"patient:{pid}",
                 f"session:{sid} q={question[:60]} speakers={len(message_ids)}")
        yield "event: done\ndata: %s\n\n" % json.dumps({
            "message_ids": message_ids, "speakers": [e["name"] for e in speakers],
            "safety": safety_res,
        }, ensure_ascii=False)
        yield "event: end\ndata: {}\n\n"

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})
