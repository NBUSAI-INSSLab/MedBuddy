"""专家会诊：数字人专家、多学科专家团与会诊作答。

专家不是泛化客服：每位数字人都有固定专科、沟通风格与作答边界，
会诊时统一注入患者全景档案、饮食处方与本地指南证据。
"""
import json
import time

from backend import db
from backend.services import diet, expert_meta, llm

EXPERTS = [
    {
        "id": "cardio_chen", "name": "陈志远", "initials": "陈",
        "title": "主任医师 · 心血管内科", "dept": "心血管内科",
        "org": "市第一人民医院", "role_key": "cardio", "years": 26, "cases": "3200+",
        "tags": ["高血压", "冠心病", "血压波动"],
        "intro": "擅长难治性高血压与冠心病二级预防，习惯用家庭血压曲线判断是否需要调药。",
        "style": "先看数据再下结论，说话稳、不绕弯",
        "greeting": "我是陈志远，心内科医生。已经看过您的血压和用药记录，我们直接说重点。",
        "questions": ["我的血压为什么忽高忽低？", "最近有点胸闷，需要马上就医吗？", "降压药可以改到晚上吃吗？"],
        "color": "#b91c1c", "color2": "#f97316",
    },
    {
        "id": "endo_lin", "name": "林静", "initials": "林",
        "title": "副主任医师 · 内分泌科", "dept": "内分泌科",
        "org": "市第一人民医院", "role_key": "endo", "years": 18, "cases": "2600+",
        "tags": ["2型糖尿病", "血糖波动", "体重管理"],
        "intro": "专注基层糖尿病个体化治疗，尤其关注老年患者的低血糖风险与用药简化。",
        "style": "耐心细致，喜欢把指标拆成一天里的具体动作",
        "greeting": "我是林静，内分泌科医生。血糖的问题不用急，我们一条一条捋清楚。",
        "questions": ["空腹血糖偏高怎么办？", "最近总是餐后犯困，正常吗？", "血糖降到多少可以减药？"],
        "color": "#7c3aed", "color2": "#2563eb",
    },
    {
        "id": "nutrition_zhou", "name": "周敏", "initials": "周",
        "title": "注册营养师 · 临床营养科", "dept": "临床营养科",
        "org": "市第一人民医院", "role_key": "nutrition", "years": 12, "cases": "4100+",
        "tags": ["医学营养治疗", "控盐控糖", "外食策略"],
        "intro": "擅长把指南里的克数翻译成一日三餐，帮患者在真实生活里吃得下去、坚持得住。",
        "style": "务实、具体，先改最容易的一口",
        "greeting": "我是周敏，营养师。我不主张一下子全改，先从您每天都会吃到的那几样下手。",
        "questions": ["帮我看看一天三顿怎么吃？", "在外面吃饭怎么控盐？", "水果到底能不能吃？"],
        "color": "#0d9488", "color2": "#22c55e",
    },
    {
        "id": "pharmacy_wu", "name": "吴涛", "initials": "吴",
        "title": "副主任药师 · 临床药学", "dept": "临床药学",
        "org": "市第一人民医院", "role_key": "pharmacy", "years": 15, "cases": "5300+",
        "tags": ["多重用药", "服药依从性", "药物相互作用"],
        "intro": "专门处理“药太多、时间太乱、吃了不舒服”的问题，帮患者把用药方案变简单。",
        "style": "条理清楚，喜欢用时间轴讲服药",
        "greeting": "我是吴涛，临床药师。您现在的每一种药，我都会看它该什么时候吃、和什么不能一起吃。",
        "questions": ["几种药可以一起吃吗？", "漏服了一次要不要补？", "吃药后脚踝水肿正常吗？"],
        "color": "#0369a1", "color2": "#0ea5e9",
    },
    {
        "id": "nephro_he", "name": "何雪", "initials": "何",
        "title": "副主任医师 · 肾内科", "dept": "肾内科",
        "org": "市第一人民医院", "role_key": "nephro", "years": 14, "cases": "1800+",
        "tags": ["慢性肾脏病", "蛋白尿", "心肾共病"],
        "intro": "关注高血压、糖尿病背后的肾脏保护，擅长在多重目标之间找平衡。",
        "style": "谨慎、重视长期风险，会把“为什么”讲明白",
        "greeting": "我是何雪，肾内科医生。我会重点看您的肾功能和蛋白尿，帮您守住肾脏这条线。",
        "questions": ["肾功能还能恢复吗？", "饮食上要不要限制蛋白？", "哪些止痛药不能吃？"],
        "color": "#4338ca", "color2": "#8b5cf6",
    },
    {
        "id": "gp_luo", "name": "罗建国", "initials": "罗",
        "title": "主任医师 · 全科医学", "dept": "全科医学",
        "org": "社区卫生服务中心", "role_key": "gp", "years": 22, "cases": "6800+",
        "tags": ["综合管理", "慢阻肺", "随访转诊"],
        "intro": "在社区一线做慢病管理二十余年，擅长把专科意见汇总成患者做得到的计划。",
        "style": "像家庭医生一样唠家常，但关键节点不含糊",
        "greeting": "我是罗建国，全科医生。专科的意见我来帮您翻译成日常能执行的安排。",
        "questions": ["下次什么时候复查？", "平时需要注意哪些信号？", "几种慢病一起管怎么排优先级？"],
        "color": "#b45309", "color2": "#f59e0b",
    },
]

TEAMS = [
    {
        "id": "htn_team", "name": "高血压多学科专家团",
        "desc": "血压控制不佳、波动大或合并多重用药时，由心内科牵头，营养与药学同步介入。",
        "members": ["cardio_chen", "nutrition_zhou", "pharmacy_wu"],
        "tags": ["难治性高血压", "限盐落地", "联合用药"],
        "scenario": "适合：血压反复不达标、晨峰明显、服药时间混乱的患者。",
    },
    {
        "id": "dm_team", "name": "糖尿病一体化专家团",
        "desc": "从降糖方案、一日三餐到用药安全，三位专家围绕同一份血糖记录给出配套建议。",
        "members": ["endo_lin", "nutrition_zhou", "pharmacy_wu"],
        "tags": ["血糖波动", "低血糖风险", "饮食处方"],
        "scenario": "适合：空腹或餐后血糖反复、体重增加、担心低血糖的患者。",
    },
    {
        "id": "cardiorenal_team", "name": "心肾共病专家团",
        "desc": "高血压、糖尿病合并慢性肾脏病时，在降压、降糖与护肾之间找平衡。",
        "members": ["cardio_chen", "nephro_he", "pharmacy_wu"],
        "tags": ["心肾共病", "蛋白尿", "用药安全"],
        "scenario": "适合：eGFR 下降、尿蛋白阳性、需要长期联合用药的患者。",
    },
]

DISCLAIMER = "以上为多学科会诊意见，不能替代线下面诊；用药调整请由签约医生结合完整检查评估。"

INTRO_BY_ROLE = {
    "cardio": "我从心血管风险的角度看这份档案。",
    "endo": "我重点看血糖控制与低血糖风险。",
    "nutrition": "我负责把饮食处方落到一日三餐。",
    "pharmacy": "我来核对用药时间、依从性和相互作用。",
    "nephro": "我关注肾功能与心肾共病风险。",
    "gp": "我负责把各位的意见汇总成可执行的随访计划。",
}


# ---------------------------------------------------------------- 数据读写

def _json_list(raw):
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (TypeError, ValueError):
        return []


def _skills_of(raw):
    out = []
    for key in _json_list(raw):
        meta = expert_meta.SKILL_MAP.get(key)
        out.append({"key": key,
                    "name": meta["name"] if meta else str(key),
                    "desc": meta["desc"] if meta else "",
                    "icon": meta["icon"] if meta else "sparkles"})
    return out


def _tools_of(raw):
    out = []
    for item in _json_list(raw):
        if isinstance(item, str):
            meta = expert_meta.MCP_MAP.get(item)
            if not meta:
                continue
            out.append(dict(meta))
        elif isinstance(item, dict) and item.get("key"):
            base = expert_meta.MCP_MAP.get(item["key"], {})
            out.append({
                "key": item["key"],
                "name": item.get("name") or base.get("name") or item["key"],
                "desc": item.get("desc") or base.get("desc") or "",
                "builtin": bool(item.get("builtin", base.get("builtin", False))),
                "custom": bool(item.get("custom", item["key"] not in expert_meta.MCP_MAP)),
            })
    return out


def _kb_of(raw):
    ids = []
    for x in _json_list(raw):
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = db.query(f"SELECT id,title,category FROM kb_documents WHERE id IN ({marks})", ids)
    order = {did: i for i, did in enumerate(ids)}
    rows.sort(key=lambda r: order.get(r["id"], 999))
    return rows


def _expert_from_row(r):
    tags = [str(x) for x in _json_list(r["tags"])]
    questions = [str(x) for x in _json_list(r["questions"])]
    kb_docs = _kb_of(r["kb_doc_ids"])
    return {
        "id": r["code"], "db_id": r["id"], "name": r["name"],
        "initials": r["initials"] or (r["name"] or "专")[:1],
        "title": r["title"] or "", "dept": r["dept"] or "", "org": r["org"] or "",
        "role_key": r["role_key"] or "gp", "years": r["years"] or 0,
        "cases": r["cases"] or "", "tags": tags, "intro": r["intro"] or "",
        "style": r["style"] or "", "greeting": r["greeting"] or f"我是{r['name']}，我们直接说重点。",
        "questions": questions, "color": r["color"] or "#0f766e",
        "color2": r["color2"] or "#0d9488", "status": r["status"] or "active",
        "skills": _skills_of(r["skills"]), "tools": _tools_of(r["mcp_tools"]),
        "kb_docs": kb_docs, "kb_doc_ids": [d["id"] for d in kb_docs],
        "raw_tools": _json_list(r["mcp_tools"]),
    }


def _team_from_row(r, experts_by_code):
    codes = [str(x) for x in _json_list(r["member_codes"])]
    members = [experts_by_code[c] for c in codes if c in experts_by_code]
    kb_docs = _kb_of(r["kb_doc_ids"])
    return {
        "id": r["code"], "db_id": r["id"], "name": r["name"], "desc": r["desc"] or "",
        "tags": [str(x) for x in _json_list(r["tags"])],
        "scenario": r["scenario"] or "", "status": r["status"] or "active",
        "member_ids": [m["id"] for m in members], "members": members,
        "skills": _skills_of(r["skills"]), "tools": _tools_of(r["mcp_tools"]),
        "kb_docs": kb_docs, "kb_doc_ids": [d["id"] for d in kb_docs],
        "raw_tools": _json_list(r["mcp_tools"]),
    }


def all_experts(include_paused=False):
    sql = "SELECT * FROM expert_profiles"
    if not include_paused:
        sql += " WHERE status='active'"
    sql += " ORDER BY sort, id"
    return [_expert_from_row(r) for r in db.query(sql)]


def all_teams(include_paused=False, experts=None):
    sql = "SELECT * FROM expert_teams"
    if not include_paused:
        sql += " WHERE status='active'"
    sql += " ORDER BY sort, id"
    experts = experts if experts is not None else all_experts(include_paused=False)
    by_code = {e["id"]: e for e in experts}
    return [_team_from_row(r, by_code) for r in db.query(sql)]


def find_expert(code):
    r = db.query("SELECT * FROM expert_profiles WHERE code=?", (code,), one=True)
    return _expert_from_row(r) if r else None


def find_team(code):
    r = db.query("SELECT * FROM expert_teams WHERE code=?", (code,), one=True)
    if not r:
        return None
    return _team_from_row(r, {e["id"]: e for e in all_experts(include_paused=True)})


def public_expert(e):
    return {
        "id": e["id"], "name": e["name"], "initials": e["initials"],
        "title": e["title"], "dept": e["dept"], "org": e["org"],
        "tags": e["tags"], "intro": e["intro"], "style": e["style"],
        "years": e["years"], "cases": e["cases"], "questions": e["questions"],
        "color": e["color"], "color2": e["color2"], "online": e["status"] == "active",
        "type": "expert", "role_key": e["role_key"],
        "skills": e["skills"], "tools": e["tools"], "kb_count": len(e["kb_docs"]),
    }


def public_team(t):
    return {
        "id": t["id"], "name": t["name"], "desc": t["desc"], "tags": t["tags"],
        "scenario": t["scenario"], "type": "team", "member_ids": t["member_ids"],
        "members": [{"id": m["id"], "name": m["name"], "initials": m["initials"],
                     "title": m["title"], "dept": m["dept"], "color": m["color"],
                     "color2": m["color2"]} for m in t["members"]],
        "skills": t["skills"], "tools": t["tools"], "kb_count": len(t["kb_docs"]),
    }


def roster():
    experts = all_experts()
    return [public_expert(e) for e in experts], [public_team(t) for t in all_teams(experts=experts)]


def resolve(target_type, target_id):
    if target_type == "team":
        t = find_team(target_id)
        if not t:
            return None, []
        return public_team(t), t["members"]
    e = find_expert(target_id)
    return (public_expert(e), [e]) if e else (None, [])


def ensure_seed():
    """首次启动写入内置专家与专家团；已有配置不覆盖。"""
    if not db.query("SELECT id FROM expert_profiles LIMIT 1"):
        for i, e in enumerate(EXPERTS):
            cats = expert_meta.DEFAULT_KB_CATEGORIES_BY_ROLE.get(e["role_key"], [])
            kb_ids = []
            if cats:
                marks = ",".join("?" * len(cats))
                kb_ids = [r["id"] for r in db.query(
                    f"SELECT id FROM kb_documents WHERE category IN ({marks}) ORDER BY id", cats)]
            db.execute(
                "INSERT INTO expert_profiles(code,name,initials,title,dept,org,role_key,years,cases,"
                "tags,intro,style,greeting,questions,color,color2,skills,kb_doc_ids,mcp_tools,status,sort) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)",
                (e["id"], e["name"], e["initials"], e["title"], e["dept"], e["org"],
                 e["role_key"], e["years"], e["cases"],
                 json.dumps(e["tags"], ensure_ascii=False),
                 e["intro"], e["style"], e["greeting"],
                 json.dumps(e["questions"], ensure_ascii=False),
                 e["color"], e["color2"],
                 json.dumps(expert_meta.DEFAULT_SKILLS_BY_ROLE.get(e["role_key"], []), ensure_ascii=False),
                 json.dumps(kb_ids),
                 json.dumps([dict(expert_meta.MCP_MAP[k]) for k in
                             expert_meta.DEFAULT_MCP_BY_ROLE.get(e["role_key"], [])
                             if k in expert_meta.MCP_MAP], ensure_ascii=False),
                 i * 10))
    if not db.query("SELECT id FROM expert_teams LIMIT 1"):
        for i, t in enumerate(TEAMS):
            db.execute(
                "INSERT INTO expert_teams(code,name,desc,tags,scenario,member_codes,skills,kb_doc_ids,"
                "mcp_tools,status,sort) VALUES(?,?,?,?,?,?,?,?,?,'active',?)",
                (t["id"], t["name"], t["desc"],
                 json.dumps(t["tags"], ensure_ascii=False), t["scenario"],
                 json.dumps(t["members"], ensure_ascii=False),
                 json.dumps(["metric_review", "referral", "followup"], ensure_ascii=False),
                 json.dumps([]),
                 json.dumps([dict(expert_meta.MCP_MAP[k]) for k in
                             ("vitals_query", "metric_trend", "guideline_search")], ensure_ascii=False),
                 i * 10))


def _bp_text(feats):
    bp = feats.get("bp_latest")
    if not bp:
        return "暂无近期血压记录"
    rate = feats.get("bp_control_rate")
    text = f"最近血压 {bp['sbp']:.0f}/{bp['dbp']:.0f} mmHg"
    if rate is not None:
        text += f"，近 7 天达标率 {rate:.0f}%"
    return text


def _glucose_text(feats):
    g = feats.get("glucose_latest")
    if not g:
        return "暂无近期血糖记录"
    text = f"最近血糖 {g['value']:.1f} mmol/L"
    if feats.get("hba1c"):
        text += f"，糖化血红蛋白 {feats['hba1c']:.1f}%"
    return text


def _med_text(ctx):
    meds = ctx.get("medications") or []
    if not meds:
        return "目前没有长期用药记录"
    return "、".join(f"{m['drug_name']}（{m['dosage'] or ''}{m['frequency'] or ''}）".strip() for m in meds[:5])


def greeting(ctx, expert):
    """每位数字人的个性化开场白：带上患者真实数据，而不是通用欢迎语。"""
    p = ctx["patient"]
    f = ctx["features"]
    name = p["name"]
    role = expert["role_key"]
    if role == "cardio":
        body = f"{name}您好，{_bp_text(f)}。"
        body += "我会先判断血压的波动模式，再看心脏风险，不会只凭一次读数下结论。"
    elif role == "endo":
        body = f"{name}您好，{_glucose_text(f)}。"
        body += f"您目前用药依从性 {f.get('med_adherence', 0):.0f}%，我们把血糖和日常动作对应起来看。"
    elif role == "nutrition":
        salt = p.get("salt_intake") or "未评估"
        height = float(p.get("height_cm") or 0)
        weight = float(p.get("weight_kg") or 0)
        bmi = round(weight / ((height / 100) ** 2), 1) if height and weight else "—"
        body = f"{name}您好，我看过您的饮食记录，口味「{salt}」，BMI {bmi}。"
        body += "我先给您一份能照着买的配餐，再按您的习惯微调。"
    elif role == "pharmacy":
        body = f"{name}您好，您目前在用 {len(ctx.get('medications') or [])} 种药，依从性 {f.get('med_adherence', 0):.0f}%。"
        body += "我会把服药时间、漏服处理和相互作用逐条讲清楚。"
    elif role == "nephro":
        egfr = f.get("egfr")
        body = f"{name}您好，最近 eGFR {egfr:.0f} mL/min。" if egfr else f"{name}您好，目前还没有肾功能记录。"
        body += "我会重点看肾脏保护，以及哪些药需要避开。"
    else:
        body = f"{name}您好，您的风险分层是{ctx['risk']['label']}，在管 {f.get('managed_days', 0)} 天。"
        body += "我帮您把几件最重要的事排出先后顺序。"
    return body + "\n\n" + expert["greeting"]


def team_greetings(ctx, team):
    ids = team.get("member_ids") or [m["id"] if isinstance(m, dict) else m
                                     for m in team.get("members", [])]
    by_code = {e["id"]: e for e in all_experts(include_paused=True)}
    out = []
    for e in [by_code[m] for m in ids if m in by_code]:
        first = greeting(ctx, e).split("\n")[0]
        out.append((e, f"{INTRO_BY_ROLE.get(e['role_key'], '')}{first}\n\n{e['greeting']}"))
    return out


def _diet_numbers(ctx):
    try:
        plan = diet.build_plan(ctx["patient"], ctx["age"], ctx["conditions"], ctx["features"])
        return plan
    except Exception:
        return None


def builtin_answer(ctx, question, expert, prior=None, team_name=None):
    """离线规则作答：所有数值来自患者档案，不同专科给出不同侧重。"""
    p = ctx["patient"]
    f = ctx["features"]
    conds = [c["name"] for c in ctx.get("conditions") or []]
    role = expert["role_key"]
    name = p["name"]
    prior = prior or []
    lead = f"我是{expert['name']}，{expert['dept']}。"
    if prior:
        lead += "前面几位已经把整体情况讲过了，我补充" + expert["dept"] + "这一块。"
    lines = [lead]

    if role == "cardio":
        lines.append(f"**我的判断**\n{name}，{_bp_text(f)}。")
        if f.get("hr_latest"):
            lines.append(f"静息心率 {f['hr_latest']:.0f} 次/分。")
        if (f.get("bp_control_rate") or 100) < 60:
            lines.append("血压达标率不足六成，先别急着自行加药。要先排除测量姿势、时段和漏服的影响，再看 7 天曲线是否真的偏高。")
        else:
            lines.append("目前血压总体可控，维持现有方案，重点放在清晨血压和季节变化时的复测。")
        if any("冠心病" in c for c in conds):
            ldl = f.get("ldl")
            lines.append("冠心病方面，" + (f"低密度脂蛋白 {ldl:.2f} mmol/L，需要按高危目标管理。" if ldl else "建议复查血脂，明确低密度脂蛋白是否达标。"))
        lines.append("**可以这样做**\n"
                     "- 连续 7 天早晚各测 2 次血压，测前静坐 5 分钟，记录时间和是否服药\n"
                     "- 食盐控制在每日 5 g 以内，腌制品、挂面汤尽量不碰\n"
                     "- 快走等中等强度运动每周 5 次、每次 30 分钟，避免清晨过早晨练\n"
                     "- 出现胸痛持续 15 分钟不缓解、呼吸困难或晕厥，立即拨打 120")
    elif role == "endo":
        g = f.get("glucose_latest")
        lines.append(f"**我的判断**\n{name}，{_glucose_text(f)}。")
        if f.get("glucose_control_rate") is not None:
            lines.append(f"近 7 天{ f.get('glucose_control_basis', '空腹')}达标率 {f['glucose_control_rate']:.0f}%。")
        if g and g["value"] < 4.4:
            lines.append("近期血糖偏低，先排查是否进食不足、运动过量或降糖药剂量偏大，低血糖比高血糖更危险。")
        elif f.get("hba1c") and f["hba1c"] >= 7:
            lines.append("糖化血红蛋白仍未达标，说明近 3 个月整体血糖偏高，需要从饮食、运动和用药三方面一起看。")
        else:
            lines.append("整体血糖尚可，接下来重点减少餐后波动，而不是一味追求更低的数字。")
        lines.append("**可以这样做**\n"
                     "- 主食每餐生重 50–75 g，先吃蔬菜和蛋白，最后吃主食\n"
                     "- 每周挑 2–3 天测餐后 2 小时血糖，找出让自己升得快的食物\n"
                     "- 血糖 <3.9 mmol/L 时立即补充 15 g 碳水，15 分钟后复测\n"
                     "- 不要自行停用降糖药；出现反复低血糖请带记录复诊")
    elif role == "nutrition":
        plan = _diet_numbers(ctx)
        if plan:
            lines.append(f"**您的饮食处方**\n按 {ctx['age']} 岁、{plan['weight']:.0f} kg、BMI {plan['bmi']} 计算："
                         f"每日能量约 {plan['energy']} kcal，食盐 ≤{plan['salt']} g，蛋白质 {plan['protein']} g，饮水 {plan['water']} ml。")
            im = plan["meals"]
            lines.append("三餐按 25% / 35% / 30% 分配，另留 10% 加餐："
                         f"早餐约 {im[0]['energy']} kcal，午餐约 {im[1]['energy']} kcal，晚餐约 {im[2]['energy']} kcal。")
            if plan["condition_notes"]:
                lines.append("**针对您的病种**\n" + "\n".join(f"- {n['name']}：{n['text']}" for n in plan["condition_notes"]))
        else:
            lines.append("**饮食原则**\n少盐、控油、主食定量，每餐一掌心优质蛋白、两拳头蔬菜。")
        salt = p.get("salt_intake") or ""
        if "咸" in salt:
            lines.append("您口味偏咸，建议用 2 周逐步减盐：先把咸菜减半，再用醋、柠檬、葱姜蒜提味，味觉会慢慢适应。")
        lines.append("**今天就能做**\n"
                     "- 买一个 2 g 限盐勺，全天不超过 3 勺\n"
                     "- 外卖选蒸煮炖，汤汁不拌饭，额外要一份青菜\n"
                     "- 水果放在两餐之间，每次 100–150 g，不喝果汁")
    elif role == "pharmacy":
        meds = ctx.get("medications") or []
        lines.append(f"**用药清单核对**\n{_med_text(ctx)}。当前依从性 {f.get('med_adherence', 0):.0f}%。")
        if meds:
            tips = []
            for m in meds[:4]:
                tips.append(f"- {m['drug_name']}：{m['frequency'] or '按医嘱'}，{m['timing'] or '固定时间服用'}")
            lines.append("\n".join(tips))
        lines.append("**容易出问题的点**\n"
                     "- 降压药、降糖药不要因为某天数值正常就自行停用\n"
                     "- 漏服时若接近下一次服药时间，跳过即可，不要加倍补服\n"
                     "- 感冒止痛尽量避开布洛芬、双氯芬酸等非甾体抗炎药，尤其肾功能下降时\n"
                     "- 服用阿司匹林、他汀后若出现黑便、肌肉酸痛，及时联系医生")
        if (f.get("med_adherence") or 100) < 70:
            lines.append(f"您近 30 天依从性 {f['med_adherence']:.0f}%，建议用一周药盒按早、晚分装，把服药和刷牙绑定。")
    elif role == "nephro":
        egfr = f.get("egfr")
        lines.append(f"**我的判断**\n" + (f"{name}，最近 eGFR {egfr:.0f} mL/min。" if egfr else f"{name}，目前缺少肾功能数据，建议尽快复查肌酐与尿白蛋白/肌酐比值。"))
        if any("肾脏" in c for c in conds):
            lines.append("已有慢性肾脏病时，目标不是把指标拉回完全正常，而是延缓下降、避免急性打击。")
        lines.append("**护肾要点**\n"
                     "- 血压尽量稳定在 <130/80 mmHg，避免大幅波动\n"
                     "- 蛋白质按 0.8 g/kg 标准体重控制，主食部分用低蛋白米或麦淀粉替代\n"
                     "- 少喝浓汤、少吃加工食品，控制磷与钾；水果每天 100–150 g\n"
                     "- 避免自行服用止痛药、成分不明的中成药和保健品，做增强 CT 前主动告知医生肾功能")
    else:
        lines.append(f"**整体判断**\n{name}，风险分层{ctx['risk']['label']}，在管 {f.get('managed_days', 0)} 天，"
                     f"合并 {('、'.join(conds) or '暂无明确诊断')}。")
        alerts = ctx.get("alerts") or []
        if alerts:
            lines.append(f"目前有 {len(alerts)} 条待处理预警，最近一条是「{alerts[0]['title']}」，这是当前最优先要处理的。")
        lines.append("**优先级排序**\n"
                     "- 先把血压/血糖的家庭监测固定下来，连续 7 天比偶尔测一次有用\n"
                     "- 再把用药时间简化，减少漏服\n"
                     "- 饮食只改最容易的一口：限盐或主食定量，不要一次全改\n"
                     "- 每 3 个月复查糖化血红蛋白、血脂、肾功能与尿蛋白")

    if team_name:
        lines.append(f"**团队补充**\n本次由{team_name}共同会诊，其他专家还会从各自专业角度补充，最终请以签约医生的整合方案为准。")
    else:
        lines.append(f"**需要留意**\n如果症状突然加重或出现意识改变、胸痛、呼吸困难，请立即就医，不要等待线上回复。")

    lines.append(DISCLAIMER)
    return "\n\n".join(lines)


def stream_builtin(ctx, question, expert, prior=None, team_name=None):
    text = builtin_answer(ctx, question, expert, prior=prior, team_name=team_name)
    buf = ""
    for ch in text:
        buf += ch
        if len(buf) >= 14 and ch in "。；\n，、！？":
            yield buf
            buf = ""
            time.sleep(0.012)
    if buf:
        yield buf


def system_prompt(expert, team=None, prior=None):
    team_line = ""
    if team:
        names = "、".join(m["name"] for m in team["members"])
        team_line = (
            f"\n本次是多学科会诊，团队为「{team['name']}」，成员：{names}。"
            "只补充你专业范围内、其他成员没讲到的内容，不要重复开场白。"
        )
        if prior:
            team_line += "\n前序专家意见摘要：\n" + "\n".join(prior[-3:])
    skills = "、".join(s["name"] for s in (expert.get("skills") or [])) or "综合咨询"
    tools = "、".join(t["name"] for t in (expert.get("tools") or [])) or "无"
    return (
        f"你是{expert['name']}，{expert['title']}，任职于{expert['org']}。"
        f"专业方向：{'、'.join(expert['tags'])}。沟通风格：{expert['style']}。"
        f"\n本次会诊启用的技能：{skills}；已授权的外部工具（MCP）：{tools}。"
        "\n你正在慢病管理平台上为一位签约居民做会诊，回答必须结合给出的患者档案数据。"
        "\n规则："
        "\n1. 先给出专业判断，再给 3 条可执行建议，必要时说明需要补充什么检查；"
        "\n2. 数值只能引用档案中已有的数据，不得编造；"
        "\n3. 不调整患者当前药物的具体剂量，涉及调药一律建议签约医生评估；"
        "\n4. 只回答你专业范围内的问题，超出范围时明确建议转诊对应专科；"
        "\n5. 全文 300 字以内，简体中文，短段落，可用小标题与短列表。"
        + team_line
    )


def build_messages(ctx, chunks, question, expert, history, team=None, prior=None):
    from backend.services import agent

    system = system_prompt(expert, team=team, prior=prior)
    system += "\n6. 若引用了知识库内容，用 [1][2] 标注，不得编造指南原文。"
    user = agent.build_context_block(ctx, chunks) + "\n\n【患者问题】\n" + question
    messages = [{"role": "system", "content": system}]
    for h in (history or [])[-8:]:
        messages.append({"role": h["role"], "content": h["content"][:600]})
    messages.append({"role": "user", "content": user})
    return messages


def append_sources(answer, chunks):
    if not chunks or "参考依据" in answer:
        return answer
    cited = any(f"[{i}]" in answer for i in range(1, len(chunks) + 1))
    if cited:
        return answer
    lines = ["", "**参考依据**"]
    for i, c in enumerate(chunks, 1):
        head = f"{c['title']}·{c['heading']}" if c.get("heading") else c["title"]
        lines.append(f"[{i}] 《{head}》")
    return answer + "\n".join(lines)
