"""LLM 适配层。

统一三种后端：
1. openai_compatible —— 硅基流动 / 魔搭 / DeepSeek / 任意 OpenAI 兼容网关（开源在线模型）
2. ollama            —— 本地 Ollama（http://127.0.0.1:11434/v1）
3. builtin           —— 内置规则推理引擎（零依赖、零密钥，离线演示与降级兜底）

对外只暴露 stream_chat() 与 test_connection()。
"""
import json
import re
import time
import urllib.error
import urllib.request

TIMEOUT = 60


class LLMError(Exception):
    pass


def _norm_base(base_url: str) -> str:
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        raise LLMError("未配置接口地址")
    if base_url.endswith("/chat/completions"):
        return base_url
    return base_url + "/chat/completions"


def _post_stream(url, payload, api_key):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def stream_openai_compatible(messages, cfg):
    """流式调用 OpenAI 兼容接口，逐段 yield 文本。"""
    url = _norm_base(cfg.get("base_url"))
    payload = {
        "model": cfg.get("model") or "Qwen/Qwen3-8B",
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.4)),
        "max_tokens": int(cfg.get("max_tokens", 900)),
        "stream": True,
    }
    try:
        resp = _post_stream(url, payload, cfg.get("api_key", ""))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise LLMError(f"模型接口返回 {e.code}：{detail}")
    except Exception as e:
        raise LLMError(f"模型接口连接失败：{e}")

    produced = False
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content") or ""
            if text:
                produced = True
                yield text
    if not produced:
        raise LLMError("模型未返回内容（可能是模型名或配额问题）")


def test_connection(cfg):
    """非流式连通性测试，返回 (ok, message, latency_ms)。"""
    provider = cfg.get("provider", "builtin")
    if provider == "builtin":
        return True, "内置推理引擎可用（离线模式，无需网络）", 0

    url = _norm_base(cfg.get("base_url"))
    payload = {
        "model": cfg.get("model") or "Qwen/Qwen3-8B",
        "messages": [{"role": "user", "content": "回复两个字：正常"}],
        "max_tokens": 12,
        "stream": False,
    }
    started = time.time()
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if cfg.get("api_key"):
            req.add_header("Authorization", f"Bearer {cfg['api_key']}")
        with urllib.request.urlopen(req, timeout=20) as resp:
            obj = json.loads(resp.read().decode("utf-8", "ignore"))
        content = (obj.get("choices") or [{}])[0].get("message", {}).get("content", "")
        latency = int((time.time() - started) * 1000)
        if not content:
            return False, "接口可达但未返回内容，请检查模型名称", latency
        return True, f"连接成功，模型响应正常（{latency}ms）", latency
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        return False, f"鉴权或请求失败 HTTP {e.code}：{detail}", int((time.time() - started) * 1000)
    except Exception as e:
        return False, f"无法连接：{e}", int((time.time() - started) * 1000)


# --------------------------------------------------------------------------
# 内置规则推理引擎
# --------------------------------------------------------------------------

INTENTS = [
    ("medication", ["服药", "用药", "漏服", "停药", "加药", "减药", "剂量", "副作用", "降压药", "降糖药",
                    "胰岛素", "二甲双胍", "氨氯地平", "硝苯地平", "缬沙坦", "厄贝沙坦", "美托洛尔",
                    "他汀", "阿司匹林", "氯吡格雷", "达格列净", "西格列汀", "药"]),
    ("diet", ["饮食", "食谱", "主食", "盐", "钠", "糖", "油", "营养", "水果", "蔬菜", "外卖", "吃"]),
    ("exercise", ["运动", "锻炼", "走路", "跑步", "健身", "太极", "广场舞", "活动量", "散步"]),
    ("metric", ["血压", "血糖", "血脂", "尿酸", "体重", "心率", "指标", "偏高", "偏低", "达标", "多少"]),
    ("symptom", ["头晕", "头痛", "胸闷", "心慌", "乏力", "水肿", "发麻", "疼痛", "失眠", "恶心"]),
    ("followup", ["复诊", "随访", "复查", "检查", "预约", "下次"]),
    ("lifestyle", ["吸烟", "戒烟", "喝酒", "熬夜", "睡眠", "压力", "情绪"]),
]


def detect_intent(text: str) -> str:
    """关键词按长度加权：越具体的词权重越高，避免「吃」把用药问题带偏。"""
    scores = {}
    for name, kws in INTENTS:
        scores[name] = sum(len(k) for k in kws if k in text)
    if "药" in text or any(k in text for k in ("二甲双胍", "氨氯地平", "胰岛素", "他汀")):
        scores["medication"] = scores.get("medication", 0) + 3
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


DRUG_WORDS = ("二甲双胍", "氨氯地平", "硝苯地平", "缬沙坦", "厄贝沙坦", "美托洛尔", "他汀",
              "阿司匹林", "氯吡格雷", "达格列净", "西格列汀", "胰岛素", "格列美脲", "格列齐特",
              "氢氯噻嗪", "呋塞米", "依折麦布", "非诺贝特", "别嘌醇", "噻托溴铵")


def _pick_lines(chunks, keywords, limit=3, exclude_drugs=False, require=None):
    """从检索片段里挑出与关键词最相关的短句，保证建议有出处、不是套话。"""
    lines = []
    for c in chunks:
        for seg in re.split(r"[。\n；;]", c.get("content", "")):
            seg = seg.strip(" ·-—　")
            if seg.startswith("#") or seg.startswith("【"):
                continue
            if not (8 <= len(seg) <= 90) or not any(k in seg for k in keywords):
                continue
            if require and not any(r in seg for r in require):
                continue
            if exclude_drugs and (any(d in seg for d in DRUG_WORDS) or "mg" in seg or "服药" in seg):
                continue
            if seg not in lines:
                lines.append(seg)
            if len(lines) >= limit:
                return lines
    return lines


def builtin_answer(ctx: dict, question: str) -> str:
    """基于结构化上下文生成个性化回答（非随机模板，数值全部来自患者真实数据）。"""
    p = ctx["patient"]
    feats = ctx["features"]
    intent = detect_intent(question)
    chunks = ctx.get("chunks", [])
    memories = ctx.get("memories", [])
    risk = p.get("risk_level", "low")
    risk_cn = {"critical": "极高危", "high": "高危", "medium": "中危", "low": "低危"}.get(risk, "低危")
    name = p["name"]
    conds = "、".join(c["name"] for c in ctx.get("conditions", [])) or "暂无明确诊断"
    out = []

    # 1. 结论
    bp = feats.get("bp_latest")
    glu = feats.get("glucose_latest")
    conclusion = []
    if bp:
        conclusion.append(f"最近一次血压 {bp['sbp']:.0f}/{bp['dbp']:.0f} mmHg")
    if glu:
        conclusion.append(f"最近一次血糖 {glu['value']:.1f} mmol/L")
    lead = f"{name}，您好。结合您在管的{conds}（{risk_cn}）"
    lead += "，" + "，".join(conclusion) + "。" if conclusion else "。"
    out.append(lead)

    # 2. 个体数据解读
    lines = []
    if feats.get("bp_avg7"):
        avg = feats["bp_avg7"]
        target = feats.get("bp_target", "130/80")
        lines.append(
            f"近 7 天平均血压 {avg['sbp']:.0f}/{avg['dbp']:.0f} mmHg，"
            f"控制目标 {target} mmHg，家庭自测达标率 {feats.get('bp_control_rate', 0):.0f}%"
            f"（近 30 天 {feats.get('bp_pairs_30d', 0)} 次测量）"
        )
    if feats.get("glucose_avg7"):
        g = feats["glucose_avg7"]
        lines.append(
            f"近 7 天平均血糖 {g:.1f} mmol/L，{feats.get('glucose_control_basis', '空腹')}达标率 {feats.get('glucose_control_rate', 0):.0f}%"
        )
    if feats.get("weight_trend") is not None:
        t = feats["weight_trend"]
        lines.append(f"体重近 30 天变化 {t:+.1f} kg")
    if lines:
        out.append("**您目前的控制情况**\n" + "\n".join(f"- {x}" for x in lines))

    # 3. 针对意图的建议
    meds = ctx.get("medications", [])
    med_names = "、".join(f"{m['drug_name']}（{m['dosage']}，{m['frequency']}）" for m in meds) or "暂无长期用药记录"

    if intent == "medication":
        body = [f"您当前在用的药物：{med_names}。"]
        tips = _pick_lines(chunks, ["服", "药", "剂量", "晨", "睡前", "漏服"], 3)
        if risk in ("critical", "high"):
            body.append("您的风险分层偏高，**不要自行增减药量或停药**；如出现头晕、乏力、心率过慢等情况，先测血压并联系签约医生。")
        if any("漏服" in m["content"] for m in memories):
            body.append("结合您之前提到过的漏服情况，建议把晚间隔壁药盒放在刷牙位置，或用手机闹钟固定提醒。")
        if tips:
            body.append("指南要点：\n" + "\n".join(f"- {t}" for t in tips))
        out.append("**用药建议**\n" + "\n".join(body))

    elif intent == "diet":
        body = []
        salt = p.get("salt_intake") or "未评估"
        body.append(f"您目前记录的口味偏咸程度为「{salt}」。")
        tips = _pick_lines(chunks, ["盐", "钠", "饮食", "主食", "蛋白", "蔬菜", "油", "糖"], 4, exclude_drugs=True)
        if tips:
            body.append("结合您的病种，饮食上优先做这几件事：\n" + "\n".join(f"- {t}" for t in tips))
        pref = [m["content"] for m in memories if m["kind"] == "preference"]
        if pref:
            body.append(f"另外记得您提过「{pref[0][:40]}」，方案可以在不违背原则的前提下按您的习惯调整。")
        out.append("**饮食调整**\n" + "\n".join(body))

    elif intent == "exercise":
        body = [f"您目前的运动习惯记录为「{p.get('exercise') or '未评估'}」。"]
        tips = _pick_lines(chunks, ["运动", "步行", "有氧", "每周", "分钟", "强度"], 4, exclude_drugs=True)
        if tips:
            body.append("可以参考：\n" + "\n".join(f"- {t}" for t in tips))
        if bp and bp["sbp"] >= 160:
            body.append("当前收缩压偏高，先以低强度步行和呼吸训练为主，避免憋气用力的动作。")
        out.append("**运动方案**\n" + "\n".join(body))

    elif intent == "metric":
        detail = []
        if bp:
            detail.append(f"血压 {bp['sbp']:.0f}/{bp['dbp']:.0f} mmHg（{bp['measured_at'][:16]}，{bp['source']}）")
        if feats.get("bp_max30"):
            m = feats["bp_max30"]
            detail.append(f"近 30 天最高收缩压 {m:.0f} mmHg")
        if glu:
            detail.append(f"血糖 {glu['value']:.1f} mmol/L（{glu['note'] or '自测'}）")
        if feats.get("hba1c"):
            detail.append(f"最近糖化血红蛋白 {feats['hba1c']:.1f}%")
        if feats.get("ldl"):
            detail.append(f"低密度脂蛋白 {feats['ldl']:.2f} mmol/L")
        out.append("**指标解读**\n" + "\n".join(f"- {d}" for d in detail) if detail else "**指标解读**\n目前还没有足够的监测记录，建议先连续记录 7 天。")
        tips = _pick_lines(chunks, ["目标", "控制", "达标", "mmHg", "mmol"], 3)
        if "血压" in question:
            tips = _pick_lines(chunks, ["目标", "控制", "达标", "mmHg"], 3, require=["血压"])
        elif "血糖" in question or "糖化" in question:
            tips = _pick_lines(chunks, ["目标", "控制", "达标", "mmol", "糖化"], 3,
                               require=["血糖", "糖化"])
        if tips:
            out.append("**判读依据**\n" + "\n".join(f"- {t}" for t in tips))

    elif intent == "symptom":
        body = ["先确认是否存在需要立即就医的情况：胸痛持续不缓解、呼吸困难、意识改变、单侧肢体无力或言语不清——出现任一项请立即拨打 120。"]
        tips = _pick_lines(chunks, ["头晕", "症状", "就医", "低血糖", "监测"], 3)
        if tips:
            body.append("结合您的病史：\n" + "\n".join(f"- {t}" for t in tips))
        if glu and glu["value"] < 4.4:
            body.append("您近期血糖偏低，头晕可能与低血糖相关，建议立即测指尖血糖并补充 15g 碳水。")
        elif bp and bp["dbp"] < 60:
            body.append("您近期舒张压偏低，若起身时头晕明显，注意缓慢起身并记录体位性血压。")
        out.append("**症状分析**\n" + "\n".join(body))

    elif intent == "followup":
        plan = ctx.get("care_plan") or {}
        body = []
        if plan:
            body.append(f"当前计划：{plan.get('title')}，下次随访 {plan.get('next_visit') or '待安排'}，计划依从性 {plan.get('adherence', 0) * 100:.0f}%。")
        tips = _pick_lines(chunks, ["随访", "复查", "每", "监测"], 3)
        if tips:
            body.append("复查节奏建议：\n" + "\n".join(f"- {t}" for t in tips))
        open_alerts = ctx.get("alerts", [])
        if open_alerts:
            body.append(f"您还有 {len(open_alerts)} 条待处理提醒，复诊时请主动告知医生。")
        out.append("**复诊安排**\n" + "\n".join(body))

    else:
        tips = _pick_lines(chunks, ["建议", "管理", "控制", "监测", "生活"], 4, exclude_drugs=True)
        body = []
        if tips:
            body.append("\n".join(f"- {t}" for t in tips))
        if memories:
            body.append("结合您以往的情况：" + "；".join(m["content"][:36] for m in memories[:3]))
        out.append("**可以这样做**\n" + "\n".join(body) if body else "**可以这样做**\n先把家庭监测坚持下来，连续记录能让建议越来越贴合您的情况。")

    # 4. 需要关注 / 就医信号
    warn = []
    if risk in ("critical", "high"):
        warn.append("您属于重点管理人群，建议每周至少与签约医生沟通一次。")
    if feats.get("bp_control_rate", 100) < 50:
        warn.append("近期血压达标率不足一半，建议携带 7 天记录复诊，评估是否需要调整方案。")
    if feats.get("missed_med_days", 0) > 3:
        warn.append(f"近 30 天存在约 {feats['missed_med_days']:.0f} 天漏服记录，请与医生讨论简化服药方案。")
    warn.append("以上内容基于平台记录与公开指南整理，不能替代面诊；如症状加重请及时就医。")
    out.append("**需要留意**\n" + "\n".join(f"- {w}" for w in warn))
    return "\n\n".join(out)


def stream_builtin(ctx, question):
    text = builtin_answer(ctx, question)
    # 按标点/长度切片，模拟逐字输出
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= 14 and ch in "。；\n，、！？":
            yield buf
            buf = ""
            time.sleep(0.018)
    if buf:
        yield buf


def stream_chat(messages, cfg, ctx=None, question=""):
    provider = cfg.get("provider", "builtin")
    if provider == "builtin":
        yield from stream_builtin(ctx or {}, question)
        return
    if provider == "ollama" and not cfg.get("base_url"):
        cfg = dict(cfg, base_url="http://127.0.0.1:11434/v1")
    yield from stream_openai_compatible(messages, cfg)
