"""智能体编排：安全门禁 → 上下文装配 → 混合检索 → 生成 → 后置校验 → 记忆回写。"""
import json
import re
import time
from datetime import datetime

from backend import db
from backend.services import llm, personalization as per, rag, safety

DISCLAIMER = "以上内容基于平台记录与公开指南整理，不能替代医生面诊；用药调整请遵医嘱。"


def load_patient(patient_id):
    p = db.query("SELECT * FROM patients WHERE id=?", (patient_id,), one=True)
    if not p:
        return None
    conditions = db.query("SELECT * FROM conditions WHERE patient_id=? AND status='active'", (patient_id,))
    for c in conditions:
        if c.get("target_json"):
            try:
                c["targets"] = json.loads(c["target_json"])
            except Exception:
                c["targets"] = {}
    meds = db.query("SELECT * FROM medications WHERE patient_id=? ORDER BY id", (patient_id,))
    alerts = db.query(
        "SELECT * FROM alerts WHERE patient_id=? ORDER BY CASE level WHEN 'critical' THEN 0 "
        "WHEN 'high' THEN 1 ELSE 2 END, created_at DESC", (patient_id,))
    plan = db.query(
        "SELECT * FROM care_plans WHERE patient_id=? ORDER BY id DESC LIMIT 1", (patient_id,), one=True)
    if plan and plan.get("goals_json"):
        try:
            plan["goals"] = json.loads(plan["goals_json"])
        except Exception:
            plan["goals"] = []
    feats = per.compute_features(p, conditions, meds, alerts)
    score, level, reasons = per.compute_risk(p, conditions, meds, feats)
    feats["risk_reasons"] = reasons
    memories = per.memory_brief(patient_id)
    return {
        "patient": p,
        "age": per.patient_age(p),
        "conditions": conditions,
        "medications": meds,
        "alerts": [a for a in alerts if a["status"] == "open"],
        "care_plan": plan,
        "features": feats,
        "risk": {"score": score, "level": level, "reasons": reasons,
                 "label": per.RISK_CN.get(level, level)},
        "maturity": per.maturity(feats),
        "memories": memories,
        "narrative": per.profile_narrative(p, conditions, feats, memories),
    }


def refresh_risk(patient_id):
    bundle = load_patient(patient_id)
    if not bundle:
        return None
    db.execute("UPDATE patients SET risk_level=?, risk_score=? WHERE id=?",
               (bundle["risk"]["level"], bundle["risk"]["score"], patient_id))
    return bundle["risk"]


def _fmt_metric_rows(feats):
    rows = []
    if feats.get("bp_avg7"):
        b = feats["bp_avg7"]
        latest = feats.get("bp_latest") or {}
        rows.append(
            f"血压：近7天均值 {b['sbp']:.0f}/{b['dbp']:.0f} mmHg，"
            f"最新 {latest.get('sbp', 0):.0f}/{latest.get('dbp', 0):.0f} mmHg，"
            f"目标 <{feats.get('bp_target', '140/90')} mmHg，达标率 {feats.get('bp_control_rate', 0):.0f}%"
        )
    if feats.get("glucose_latest"):
        g = feats["glucose_latest"]
        rows.append(
            f"血糖：最新 {g['value']:.1f} mmol/L，近7天均值 "
            f"{(feats.get('glucose_avg7') or 0):.1f} mmol/L，目标 {feats.get('glucose_target', '4.4-7.0')} mmol/L，"
            f"达标率 {feats.get('glucose_control_rate', 0):.0f}%"
        )
    if feats.get("hba1c"):
        rows.append(f"糖化血红蛋白：{feats['hba1c']:.1f}%（{feats.get('hba1c_date', '')[:10]}）")
    if feats.get("ldl"):
        rows.append(f"低密度脂蛋白：{feats['ldl']:.2f} mmol/L")
    if feats.get("weight_latest"):
        trend = feats.get("weight_trend")
        rows.append(f"体重：{feats['weight_latest']:.1f} kg" + (f"，近30天 {trend:+.1f} kg" if trend is not None else ""))
    if feats.get("hr_latest"):
        rows.append(f"静息心率：{feats['hr_latest']:.0f} 次/分")
    if feats.get("spo2_latest"):
        rows.append(f"血氧：{feats['spo2_latest']:.0f}%")
    if feats.get("egfr"):
        rows.append(f"eGFR：{feats['egfr']:.0f} mL/min")
    rows.append(f"用药依从性：{feats.get('med_adherence', 0):.0f}%；近30天记录覆盖 {feats.get('record_density', 0):.0f}% 天数")
    return rows


def build_context_block(ctx, chunks):
    p = ctx["patient"]
    lines = ["【患者档案】"]
    lines.append(
        f"{p['name']}，{ctx['age']}岁{p.get('gender') or ''}，"
        f"身高 {p.get('height_cm') or '-'} cm，体重 {p.get('weight_kg') or '-'} kg；"
        f"风险分层：{ctx['risk']['label']}（{ctx['risk']['score']:.0f}/100）；"
        f"在管 {ctx['features'].get('managed_days', 1)} 天。"
    )
    lines.append("诊断：" + ("、".join(c["name"] for c in ctx["conditions"]) or "无"))
    if p.get("allergies"):
        lines.append("过敏史：" + p["allergies"])
    if p.get("family_history"):
        lines.append("家族史：" + p["family_history"])
    life = []
    for k, label in (("smoking", "吸烟"), ("drinking", "饮酒"), ("exercise", "运动"),
                     ("salt_intake", "口味"), ("sleep_quality", "睡眠")):
        if p.get(k):
            life.append(f"{label}={p[k]}")
    if life:
        lines.append("生活方式：" + "，".join(life))

    lines.append("\n【在用药物】")
    if ctx["medications"]:
        for m in ctx["medications"]:
            lines.append(f"- {m['drug_name']} {m['dosage'] or ''} {m['frequency'] or ''} {m['timing'] or ''}（依从性 {int((m['adherence'] or 0) * 100)}%）")
    else:
        lines.append("- 无长期用药记录")

    lines.append("\n【近期指标】")
    for r in _fmt_metric_rows(ctx["features"]):
        lines.append("- " + r)

    if ctx["alerts"]:
        lines.append("\n【待处理预警】")
        for a in ctx["alerts"][:4]:
            lines.append(f"- [{a['level']}] {a['title']}（{a['created_at'][:10]}）")

    mems = ctx["memories"]
    if mems:
        lines.append("\n【长期记忆（跨会话）】")
        for m in mems:
            lines.append(f"- [{m['kind_cn']}] {m['content']}")

    if chunks:
        lines.append("\n【知识库证据】")
        for i, c in enumerate(chunks, 1):
            head = f"{c['title']}·{c['heading']}" if c.get("heading") else c["title"]
            lines.append(f"[{i}] 《{head}》（相关度 {c['score']:.2f}）\n{c['content']}")
    else:
        lines.append("\n【知识库证据】\n（未检索到相关知识条目）")
    return "\n".join(lines)


def build_messages(ctx, chunks, question, history, cfg):
    system = cfg.get("system_prompt") or ""
    system += (
        "\n\n回答规则："
        "\n1. 先直接回答问题，再给依据与可执行步骤；"
        "\n2. 引用知识库时用 [1][2] 标注，不得编造未给出的指南内容；"
        "\n3. 数值必须来自【近期指标】，不要臆造；"
        "\n4. 涉及用药只讨论患者当前清单内药物，剂量调整一律建议医生评估；"
        "\n5. 若证据不足，明确说明并建议复诊；"
        "\n6. 全文 350 字以内，使用简体中文与短段落。"
    )
    user = build_context_block(ctx, chunks) + "\n\n【用户问题】\n" + question
    messages = [{"role": "system", "content": system}]
    for h in history[-8:]:
        messages.append({"role": h["role"], "content": h["content"][:600]})
    messages.append({"role": "user", "content": user})
    return messages


def _append_sources(answer, chunks):
    if not chunks:
        if "知识库" not in answer:
            answer += "\n\n**说明**：知识库中暂未检索到与本次问题直接相关的条目，以上建议以通用管理原则为主，建议下次复诊时与医生确认。"
        return answer
    cited = set(re.findall(r"\[(\d+)\]", answer))
    if not cited:
        answer += "\n\n**参考依据**"
        for i, c in enumerate(chunks, 1):
            head = f"{c['title']}·{c['heading']}" if c.get("heading") else c["title"]
            answer += f"\n[{i}] 《{head}》"
    return answer


def _postprocess(answer, ctx, chunks, flags):
    if chunks:
        answer = _append_sources(answer, chunks)
    unknown = safety.check_drugs(answer, ctx["medications"])
    if unknown:
        flags.append("drug_out_of_list")
        answer += (
            "\n\n> 提示：回答中提到的 " + "、".join(unknown[:3]) +
            " 不在您当前的用药清单内，请勿自行购买服用，需由签约医生评估。"
        )
    if "不能替代" not in answer:
        answer += "\n\n" + DISCLAIMER
    return answer


def _chunk_text(text, size=18):
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= size and ch in "。；\n，、！？":
            yield buf
            buf = ""
    if buf:
        yield buf


def summarize_if_needed(conversation_id):
    """中期记忆：超过 8 条消息时压缩更早内容为摘要。"""
    rows = db.query("SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,))
    if len(rows) <= 8:
        return
    earlier = rows[:-6]
    user_msgs = [r["content"] for r in earlier if r["role"] == "user"]
    if not user_msgs:
        return
    summary = "患者此前主要咨询：" + "；".join(m[:40] for m in user_msgs[:5])
    db.execute("UPDATE conversations SET summary=? WHERE id=?", (summary[:500], conversation_id))


def stream_answer(patient_id, question, conversation_id, actor="医生"):
    """生成器，产出 {"event":..., "data":...}，最后写入助手消息。"""
    started = time.time()
    ctx = load_patient(patient_id)
    if not ctx:
        yield {"event": "error", "data": {"message": "患者不存在"}}
        return

    cfg = db.get_agent_config()
    flags = []
    safety_res = {"hit": False}
    if str(cfg.get("enable_safety", "1")) == "1":
        safety_res = safety.check(patient_id, question, safety.latest_metrics(patient_id))

    if safety_res.get("hit"):
        chunks = []
        answer_prefix = ""
        text = safety.emergency_answer(ctx["patient"]["name"], safety_res)
        flags.append("emergency")
        messages = []
    else:
        chunks = rag.search(question, patient=ctx, top_k=int(cfg.get("top_k", 4)))
        history = db.query(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 10",
            (conversation_id,))[::-1]
        messages = build_messages(ctx, chunks, question, history, cfg)
        text = None

    meta = {
        "provider": cfg.get("provider"),
        "model": cfg.get("model") if cfg.get("provider") != "builtin" else "内置推理引擎",
        "patient": {
            "id": ctx["patient"]["id"], "name": ctx["patient"]["name"],
            "age": ctx["age"], "gender": ctx["patient"].get("gender"),
            "risk": ctx["risk"], "maturity": ctx["maturity"],
            "conditions": [c["name"] for c in ctx["conditions"]],
            "narrative": ctx["narrative"],
        },
        "memories": ctx["memories"],
        "safety": safety_res,
        "features": {
            k: v for k, v in ctx["features"].items()
            if k in ("bp_avg7", "bp_latest", "bp_control_rate", "bp_target", "glucose_avg7",
                     "glucose_latest", "glucose_control_rate", "hba1c", "ldl",
                     "med_adherence", "record_density", "managed_days", "metric_count",
                     "chat_turns", "memory_count", "risk_reasons")
        },
        "evidence_count": len(chunks),
    }
    yield {"event": "meta", "data": meta}

    answer = ""
    if safety_res.get("hit"):
        for piece in _chunk_text(text, 22):
            answer += piece
            yield {"event": "delta", "data": {"text": piece}}
            time.sleep(0.01)
    else:
        produced = False
        try:
            for piece in llm.stream_chat(messages, cfg, ctx=dict(ctx, chunks=chunks), question=question):
                produced = True
                answer += piece
                yield {"event": "delta", "data": {"text": piece}}
        except llm.LLMError as e:
            if not produced:
                flags.append("llm_fallback")
                note = f"> 在线模型不可用（{str(e)[:80]}），已切换内置推理引擎。\n\n"
                answer += note
                yield {"event": "delta", "data": {"text": note}}
                for piece in llm.stream_builtin(dict(ctx, chunks=chunks), question):
                    answer += piece
                    yield {"event": "delta", "data": {"text": piece}}

    before = len(answer)
    answer = _postprocess(answer, ctx, chunks, flags)
    if len(answer) > before:
        for piece in _chunk_text(answer[before:], 30):
            yield {"event": "delta", "data": {"text": piece}}

    latency = int((time.time() - started) * 1000)
    answer = answer.strip()
    msg_id = db.execute(
        "INSERT INTO messages(conversation_id, role, content, citations_json, meta_json) "
        "VALUES(?,?,?,?,?)",
        (conversation_id, "assistant", answer,
         json.dumps(chunks, ensure_ascii=False),
         json.dumps({"provider": meta["provider"], "model": meta["model"],
                     "latency_ms": latency, "flags": flags,
                     "evidence": len(chunks)}, ensure_ascii=False)),
    )
    db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), conversation_id))

    added = per.extract_memories(patient_id, question)
    per.touch_memories([m["id"] for m in ctx["memories"][:4]])
    summarize_if_needed(conversation_id)
    refresh_risk(patient_id)

    db.audit(actor, "agent_chat", f"patient:{patient_id}",
             f"q={question[:80]} evidence={len(chunks)} provider={meta['provider']} "
             f"latency={latency}ms flags={flags}")

    yield {
        "event": "done",
        "data": {
            "message_id": msg_id,
            "latency_ms": latency,
            "flags": flags,
            "citations": chunks,
            "new_memories": added,
            "maturity": per.maturity(per.compute_features(
                ctx["patient"], ctx["conditions"], ctx["medications"]))["score"],
            "provider": meta["provider"],
            "model": meta["model"],
        },
    }
