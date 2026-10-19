"""个性化饮食管理。

按病种、年龄、身高体重与生活方式测算每日能量与营养素目标，
生成可执行的分餐方案、食物宜忌，并对患者饮食记录做执行度评估。
"""
from datetime import datetime, timedelta

from backend import db

MEALS = [
    {"key": "breakfast", "name": "早餐", "time": "07:00–08:30", "share": 0.25},
    {"key": "lunch", "name": "午餐", "time": "11:30–12:30", "share": 0.35},
    {"key": "dinner", "name": "晚餐", "time": "17:30–18:30", "share": 0.30},
    {"key": "snack", "name": "加餐", "time": "15:00 或睡前 1 小时", "share": 0.10},
]

# 食物关键词 -> (热量 kcal, 钠 mg)，用于饮食记录的粗略估算
FOOD_TABLE = [
    ("米饭", 200, 2), ("杂粮饭", 190, 2), ("馒头", 180, 5), ("面条", 280, 350),
    ("粥", 90, 5), ("燕麦", 150, 3), ("全麦面包", 130, 180), ("包子", 220, 300),
    ("鸡蛋", 75, 70), ("牛奶", 120, 100), ("豆浆", 60, 5), ("酸奶", 90, 60),
    ("鱼", 130, 120), ("虾", 100, 150), ("鸡胸", 130, 60), ("鸡肉", 160, 80),
    ("瘦肉", 150, 60), ("牛肉", 180, 70), ("豆腐", 90, 10), ("豆制品", 110, 300),
    ("蔬菜", 40, 20), ("青菜", 30, 20), ("西兰花", 45, 25), ("菠菜", 35, 80),
    ("黄瓜", 20, 5), ("冬瓜", 20, 5), ("番茄", 30, 10), ("土豆", 110, 10),
    ("苹果", 60, 2), ("香蕉", 90, 1), ("橙子", 60, 1), ("水果", 60, 2),
    ("坚果", 70, 1), ("咸菜", 15, 500), ("腌", 30, 600), ("火腿", 130, 700),
    ("香肠", 180, 800), ("方便面", 450, 1800), ("外卖", 520, 1200),
    ("油炸", 350, 500), ("蛋糕", 250, 150), ("饼干", 120, 120), ("可乐", 140, 10),
    ("饮料", 120, 15), ("酒", 120, 5), ("汤", 60, 400), ("火锅", 600, 2000),
]

CONDITION_RULES = [
    ("高血压", "每日食盐 ≤5 g，警惕酱油、腌菜、挂面、加工肉中的隐性钠；肾功能正常时多选富钾蔬果。"),
    ("糖尿病", "主食定量、粗细搭配；进餐顺序为先蔬菜、再蛋白、最后主食，避免含糖饮料与精制点心。"),
    ("肾脏", "限制蛋白、磷与钾：部分主食替换为低蛋白米或麦淀粉，少喝浓汤，水果控制在 100–150 g/日。"),
    ("冠心病", "减少饱和脂肪与反式脂肪，烹调油 ≤25 g/日，每周吃 2 次鱼，避免动物内脏与肥肉。"),
    ("血脂", "限制油炸食品与糕点，增加膳食纤维（燕麦、豆类、蔬菜），每日 25–30 g。"),
    ("慢阻肺", "少量多餐，保证优质蛋白，避免过饱与产气食物影响呼吸。"),
    ("肥胖", "在目标能量基础上减少 300–500 kcal，先减重 5%–10%，避免极端节食。"),
]


def _flags(condition_names):
    text = "、".join(condition_names)
    return {
        "htn": "高血压" in text,
        "dm": "糖尿病" in text or "血糖" in text,
        "ckd": "肾脏" in text or "肾功能" in text,
        "chd": "冠心病" in text or "心梗" in text,
        "lipid": "血脂" in text,
        "copd": "慢阻肺" in text or "肺" in text,
        "obese": "肥胖" in text,
    }


def _std_weight(height_cm):
    return max(45.0, (height_cm or 165) - 105)


def _meal_plan(flags, energy):
    bf = ["全麦馒头 50 g（生重）" if not flags["dm"] else "杂粮馒头 50 g（生重）",
          "水煮蛋 1 个" if not flags["ckd"] else "蛋清 2 个（弃蛋黄，减少磷）",
          "低脂牛奶 200 ml" if not flags["ckd"] else "低脂牛奶 100 ml",
          "凉拌黄瓜 100 g（少盐、几滴香油）"]
    if flags["dm"]:
        bf.append("无糖豆浆 150 ml（与牛奶二选一）")

    lunch_main = "杂粮饭 55 g（生重）" if flags["dm"] else "杂粮饭 75 g（生重）"
    if flags["ckd"]:
        lunch_main = "低蛋白米饭 75 g（生重）"
    lunch = [lunch_main,
             "清蒸鲈鱼 50 g" if flags["ckd"] else "清蒸鲈鱼 80 g",
             "清炒西兰花 150 g（少油少盐）",
             "番茄蛋汤 1 小碗（用番茄提味，不放盐）",
             "烹调油 8 g（约 2 小勺）"]

    dinner_main = "杂粮饭 50 g（生重）" if flags["dm"] else "杂粮饭 60 g（生重）"
    if flags["ckd"]:
        dinner_main = "低蛋白面条 60 g（生重）"
    dinner = [dinner_main,
              "瘦肉 40 g" if flags["ckd"] else "瘦肉 50 g 或虾仁 60 g",
              "蒜蓉菠菜 200 g（先焯水）" if not flags["ckd"] else "清炒冬瓜 200 g",
              "冬瓜汤 1 小碗（不喝浓汤）",
              "烹调油 7 g"]

    if flags["dm"]:
        snack = ["无糖酸奶 100 g", "黄瓜或番茄 100 g（两餐间隔 >5 小时再加）"]
    elif flags["ckd"]:
        snack = ["苹果 100 g（低钾水果，避免香蕉、橙子）"]
    elif flags["copd"]:
        snack = ["无糖酸奶 100 g", "全麦饼干 2 片"]
    else:
        snack = ["苹果或梨 100 g", "原味坚果 10 g（约一小把）"]

    tips = {
        "breakfast": "起床后先喝 200 ml 温水；先吃蛋白和蔬菜，再吃主食，餐后血糖更平稳。"
                     if flags["dm"] else "早餐不要只吃粥和咸菜，搭配鸡蛋或牛奶能撑到中午。",
        "lunch": "外食优先选蒸、煮、炖，汤汁不拌饭；主食按自己拳头大小控制。"
                 if flags["htn"] or flags["dm"] else "午餐保证一掌心优质蛋白、两拳头蔬菜。",
        "dinner": "晚餐与睡觉间隔 3 小时，七分饱即可；夜间易饿可把部分主食挪到加餐。",
        "snack": "加餐计入全天总能量，不要用饼干、糕点代替水果或奶制品。",
    }
    dishes = {"breakfast": bf, "lunch": lunch, "dinner": dinner, "snack": snack}
    out = []
    for m in MEALS:
        out.append({
            "key": m["key"], "name": m["name"], "time": m["time"],
            "share": int(m["share"] * 100),
            "energy": int(round(energy * m["share"] / 10.0) * 10),
            "dishes": dishes[m["key"]],
            "tip": tips[m["key"]],
        })
    return out


def _foods(flags):
    recommend = [
        {"name": "新鲜蔬菜 500 g/日", "why": "深色蔬菜占一半，提供钾与膳食纤维"},
        {"name": "全谷物与杂豆", "why": "替代 1/3 主食，延缓餐后血糖上升"},
        {"name": "低脂奶或无糖酸奶 300 ml", "why": "补充钙与优质蛋白"},
        {"name": "鱼、禽、蛋、豆制品", "why": "优质蛋白，蒸煮为主"},
    ]
    if flags["ckd"]:
        recommend[0]["why"] = "蔬菜先焯水再炒，减少钾摄入"
        recommend.append({"name": "低蛋白主食（麦淀粉/低蛋白米）", "why": "在保证能量同时减少植物蛋白与磷"})
        recommend.append({"name": "苹果、梨、草莓 100–150 g/日", "why": "相对低钾的水果，避免香蕉、橙子、猕猴桃"})
    else:
        recommend.append({"name": "富钾蔬果（菠菜、番茄、香蕉）", "why": "有助于钠钾平衡，辅助降压"})

    limit = [
        {"name": "腌制品、咸菜、火腿肠", "why": "钠含量高，直接推高血压"},
        {"name": "含糖饮料、糕点、蜜饯", "why": "升糖快，增加甘油三酯"},
        {"name": "动物内脏、肥肉、油炸食品", "why": "饱和脂肪与反式脂肪偏高"},
        {"name": "浓汤、火锅底料、方便面", "why": "隐性盐与磷、嘌呤负荷高"},
        {"name": "酒精", "why": "引起血压与血糖波动，影响睡眠"},
    ]
    if flags["ckd"]:
        limit.append({"name": "高钾水果与坚果", "why": "肾功能下降时排钾能力减弱，需限量"})
    return {"recommend": recommend, "limit": limit}


def _condition_notes(condition_names):
    notes = []
    for name in condition_names:
        for kw, text in CONDITION_RULES:
            if kw in name and not any(n["name"] == name for n in notes):
                notes.append({"name": name, "text": text})
                break
    return notes


def build_plan(patient, age, conditions, features=None):
    """返回可直接渲染的个性化饮食方案。"""
    names = [c["name"] if isinstance(c, dict) else str(c) for c in (conditions or [])]
    flags = _flags(names)
    height = float(patient.get("height_cm") or 165)
    weight = float(patient.get("weight_kg") or 65)
    bmi = weight / ((height / 100) ** 2) if height else 0
    std = _std_weight(height)

    if flags["ckd"]:
        factor = 30
    elif bmi >= 28:
        factor = 25
    elif bmi >= 24:
        factor = 27
    else:
        factor = 30
    if age >= 70 and not flags["ckd"]:
        factor -= 2
    if flags["copd"]:
        factor += 2
    if flags["obese"]:
        factor -= 2
    energy = int(round(std * factor / 50.0) * 50)

    protein_g = (0.8 if flags["ckd"] else 1.2 if flags["copd"] else 1.1 if flags["dm"] else 1.0) * std
    fat_g = energy * 0.25 / 9
    carb_g = max(80.0, (energy - protein_g * 4 - fat_g * 9) / 4)

    if flags["htn"] or flags["ckd"] or flags["chd"]:
        sodium = 1800
    else:
        sodium = 2000
    salt = round(sodium * 2.54 / 1000, 1)
    water = 1500 if (flags["ckd"] or flags["chd"]) else 1700

    nutrients = [
        {"key": "energy", "name": "每日能量", "value": energy, "unit": "kcal",
         "note": f"按标准体重 {std:.0f} kg × {factor} kcal 估算"},
        {"key": "salt", "name": "食盐上限", "value": salt, "unit": "g",
         "note": f"约 1 个啤酒瓶盖平铺，钠 ≤{sodium} mg"},
        {"key": "protein", "name": "蛋白质", "value": round(protein_g), "unit": "g",
         "note": "每餐一掌心，优先鱼禽蛋奶豆" if not flags["ckd"] else "优质蛋白为主，减少植物蛋白"},
        {"key": "carb", "name": "碳水化合物", "value": round(carb_g), "unit": "g",
         "note": "全谷物与杂豆占主食 1/3"},
        {"key": "fat", "name": "脂肪", "value": round(fat_g), "unit": "g",
         "note": "烹调油 ≤25 g/日，少油炸"},
        {"key": "water", "name": "饮水", "value": water, "unit": "ml",
         "note": "分次饮用；心肾功能不全者遵医嘱调整" if (flags["ckd"] or flags["chd"])
                 else "少量多次，不用含糖饮料代替"},
    ]

    principles = []
    if flags["htn"]:
        principles.append("限盐是第一优先级：用限盐勺，出锅前放盐，善用醋、柠檬、香辛料提味。")
    if flags["dm"]:
        principles.append("主食定量：每餐生重 50–75 g，先菜后饭，餐后 2 小时测一次血糖验证。")
    if flags["ckd"]:
        principles.append("低蛋白主食替代部分米面，少喝汤、少吃加工食品，控制磷与钾。")
    if flags["chd"] or flags["lipid"]:
        principles.append("用蒸、煮、炖替代煎炸，每周吃 2 次深海鱼，坚果每日不超过 10 g。")
    if flags["copd"]:
        principles.append("少量多餐，避免过饱顶住膈肌；餐后不要立即平卧。")
    if patient.get("salt_intake") and "咸" in str(patient.get("salt_intake")):
        principles.append("您记录的口味偏咸，建议 2 周内逐步减盐，让味觉慢慢适应。")
    principles.append("饮食记录不必追求完美，连续记录 7 天以上，营养建议才会越来越贴合您。")

    plan = {
        "bmi": round(bmi, 1),
        "weight": weight,
        "std_weight": round(std),
        "energy": energy,
        "salt": salt,
        "sodium": sodium,
        "protein": round(protein_g),
        "carb": round(carb_g),
        "fat": round(fat_g),
        "water": water,
        "nutrients": nutrients,
        "meals": _meal_plan(flags, energy),
        "foods": _foods(flags),
        "condition_notes": _condition_notes(names),
        "principles": principles,
        "flags": flags,
    }
    plan["summary"] = summarize(patient.get("id"), plan)
    return plan


def estimate(foods):
    """按关键词粗略估算热量与钠，返回 (kcal|None, mg|None, 是否估算)。"""
    kcal = 0.0
    sodium = 0.0
    hits = 0
    for kw, k, na in FOOD_TABLE:
        if kw in foods:
            kcal += k
            sodium += na
            hits += 1
    if not hits:
        return None, None, False
    return int(round(kcal)), int(round(sodium)), True


def list_logs(patient_id, days=14):
    import json

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.query(
        "SELECT * FROM diet_logs WHERE patient_id=? AND log_date>=? "
        "ORDER BY log_date DESC, id DESC", (patient_id, since))
    meal_cn = {m["key"]: m["name"] for m in MEALS}
    for r in rows:
        r["meal_cn"] = meal_cn.get(r["meal"], r["meal"])
        analysis = None
        if r.get("analysis"):
            try:
                analysis = json.loads(r["analysis"])
            except (TypeError, ValueError):
                analysis = None
        r["analysis"] = analysis
        r["has_photo"] = bool(r.get("image_path"))
        r["image_url"] = (f"/api/patients/{patient_id}/diet/photos/"
                          f"{r['image_path'].split('/')[-1]}") if r.get("image_path") else None
        if analysis:
            r["photo_score"] = analysis.get("score")
            r["photo_grade"] = analysis.get("grade")
    return rows


def summarize(patient_id, plan):
    today = datetime.now().strftime("%Y-%m-%d")
    logs = list_logs(patient_id, 13)
    week_start = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    week = [r for r in logs if r["log_date"] >= week_start]
    today_logs = [r for r in logs if r["log_date"] == today]
    days = len({r["log_date"] for r in week})
    kcal_vals = [r["calories"] for r in week if r["calories"]]
    na_vals = [r["sodium"] for r in week if r["sodium"]]
    avg_kcal = round(sum(kcal_vals) / len(kcal_vals)) if kcal_vals else 0
    avg_na = round(sum(na_vals) / len(na_vals)) if na_vals else 0
    today_kcal = round(sum(r["calories"] or 0 for r in today_logs))
    today_na = round(sum(r["sodium"] or 0 for r in today_logs))

    photo_rows = [r for r in week if r.get("has_photo")]
    photo_scores = [r["photo_score"] for r in photo_rows if r.get("photo_score") is not None]

    score = 0
    if days:
        score += min(60, days * 60 / 7.0)
        if avg_kcal and abs(avg_kcal - plan["energy"]) <= plan["energy"] * 0.2:
            score += 20
        if avg_na and avg_na <= plan["sodium"]:
            score += 20
    score = int(round(score))

    return {
        "date": today,
        "logged_days": days,
        "score": score,
        "avg_kcal": avg_kcal,
        "avg_sodium": avg_na,
        "today_kcal": today_kcal,
        "today_sodium": today_na,
        "today_logs": today_logs,
        "meal_checked": sorted({r["meal"] for r in today_logs}),
        "energy_target": plan["energy"],
        "sodium_target": plan["sodium"],
        "kcal_pct": min(100, round(today_kcal / plan["energy"] * 100)) if plan["energy"] else 0,
        "sodium_pct": min(100, round(today_na / plan["sodium"] * 100)) if plan["sodium"] else 0,
        "photo_count": len(photo_rows),
        "photo_days": len({r["log_date"] for r in photo_rows}),
        "photo_today": len([r for r in today_logs if r.get("has_photo")]),
        "avg_photo_score": (int(round(sum(photo_scores) / len(photo_scores)))
                            if photo_scores else 0),
    }


def build(patient_id):
    """按患者档案组装完整饮食页数据。"""
    from backend.services import agent  # 延迟导入，避免循环依赖

    bundle = agent.load_patient(patient_id)
    if not bundle:
        return None
    plan = build_plan(bundle["patient"], bundle["age"], bundle["conditions"], bundle["features"])
    return {
        "plan": plan,
        "logs": list_logs(patient_id),
        "summary": plan["summary"],
        "meals_meta": MEALS,
    }
