"""饮食照片分析。

不依赖外部视觉模型，全部在本地完成，离线可用：
1. 读取照片、纠正 EXIF 方向，缩放到分析分辨率；
2. 以餐盘外圈颜色作为背景参考，分离"食物像素"与盘面；
3. 按 HSV 色相把食物像素归为蔬菜 / 主食 / 优质蛋白 / 油脂酱汁四类；
4. 结合食物铺满比例、患者饮食处方与病种，估算热量、钠与结构评分；
5. 输出可解释的构成、结论与改进建议（含置信度）。

说明：颜色统计只能给出"构成"层面的估算，不能识别具体菜名与烹饪用油量，
因此结果标注为参考值，并在低置信度时提示用户补充文字描述。
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime

from PIL import Image, ImageOps, UnidentifiedImageError

import config

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "MPO"}
MAX_SIDE = 1000
ANALYZE_SIDE = 120

CATEGORY_META = {
    "veg": {"name": "蔬菜类", "color": "#16a34a", "icon": "food"},
    "staple": {"name": "主食类", "color": "#d97706", "icon": "grid"},
    "protein": {"name": "优质蛋白", "color": "#dc2626", "icon": "activity"},
    "sauce": {"name": "油脂酱汁", "color": "#7c3aed", "icon": "drop"},
    "other": {"name": "其他", "color": "#64748b", "icon": "grid"},
}

# 每 1% 画面占比对应的热量（kcal），由常见家常菜的能量密度标定
ENERGY_WEIGHT = {"veg": 1.6, "staple": 8.6, "protein": 9.0, "sauce": 13.0}


class PhotoError(ValueError):
    """照片不可用（格式、尺寸、内容）。"""


def _classify(h: int, s: int, v: int) -> str:
    """把 HSV（PIL 0–255 量纲）像素归入食物类别。"""
    if v < 55:
        return "sauce"                       # 深色酱汁、焦糊
    if s < 40:
        return "staple" if v >= 105 else "sauce"
    if s < 58:
        return "staple" if v >= 110 else "sauce"
    if h <= 16 or h >= 232:                  # 红：番茄、胡萝卜、红肉
        if v >= 160 and s >= 120:
            return "veg"
        return "protein"
    if h <= 45:                              # 橙黄：红烧肉、煎蛋、酱汁
        if h <= 24:
            return "protein"                 # 红棕多为肉类
        return "sauce" if (s >= 150 and v < 190) else "protein"
    if h <= 65:                              # 黄绿：蛋、豆制品、玉米
        return "protein" if v >= 140 else "staple"
    if h <= 175:                             # 绿、青
        return "veg"
    return "veg"                             # 紫甘蓝、茄子


def _median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 0


def _ring_color(img):
    """取图片外圈颜色，作为餐盘/桌面的背景参考。"""
    w, h = img.size
    px = img.load()
    rs, gs, bs = [], [], []
    step = max(1, min(w, h) // 60)
    band = max(1, min(w, h) // 22)
    for x in range(0, w, step):
        for y in list(range(0, band, max(1, step // 2))) + list(range(h - band, h, max(1, step // 2))):
            r, g, b = px[x, y]
            rs.append(r); gs.append(g); bs.append(b)
    for y in range(0, h, step):
        for x in list(range(0, band, max(1, step // 2))) + list(range(w - band, w, max(1, step // 2))):
            r, g, b = px[x, y]
            rs.append(r); gs.append(g); bs.append(b)
    return _median(rs), _median(gs), _median(bs)


def _dist(c1, c2):
    return abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2])


def _rgb_hsv(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return h * 255, s * 255, v * 255


def _analyze_pixels(img):
    """逐像素分离盘面与食物，返回 (占比字典, 食物铺满比例)。

    背景判定：与画面外圈颜色接近（餐盘/桌面），或极端高亮低饱和（白瓷盘，
    含渐变过渡区）。白米饭因偏黄、饱和度略高会被保留在主食里；
    散碎的青菜叶按自身色相归类，不会被平均色稀释。
    """
    w, h = img.size
    ring = _ring_color(img)
    rgb = img.load()
    hpx = img.convert("HSV").load()

    counts = {k: 0 for k in CATEGORY_META}
    food = 0
    total = 0
    pad = max(2, int(min(w, h) * 0.12))
    cx, cy = w / 2.0, h / 2.0
    for x in range(pad, w - pad):
        for y in range(pad, h - pad):
            total += 1
            c = rgb[x, y]
            hh, ss, vv = hpx[x, y]
            neutral_bright = vv >= 236 and (max(c) - min(c)) <= 10
            dark_shadow = vv < 62 and ss < 60
            # 外圈颜色只作为画面边缘的背景参考，避免把居中的浅色食物误当桌面
            edge = max(abs(x - cx) / cx, abs(y - cy) / cy) > 0.72
            if (edge and _dist(c, ring) < 22) or neutral_bright or dark_shadow:
                continue
            food += 1
            counts[_classify(hh, ss, vv)] += 1

    shares = {}
    if food:
        for k, n in counts.items():
            shares[k] = round(n * 100.0 / food, 1)
    else:
        shares = {k: 0.0 for k in CATEGORY_META}
    food_ratio = round(food / total, 3) if total else 0.0
    return shares, food_ratio


def _sharpness(img):
    from PIL import ImageFilter
    gray = img.convert("L").filter(ImageFilter.FIND_EDGES)
    gray = gray.resize((64, 64))
    vals = list(gray.getdata())
    mean = sum(vals) / len(vals)
    return (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5


def _dominant(shares):
    ordered = sorted(((v, k) for k, v in shares.items() if k != "other"), reverse=True)
    return ordered[0][1] if ordered else "other"


def _energy(shares, food_ratio):
    """按构成占比与铺满程度估算热量（kcal）。"""
    portion = max(0.8, min(1.5, food_ratio / 0.5))
    raw = sum(shares[k] * w for k, w in ENERGY_WEIGHT.items())
    return int(round(raw * portion / 10.0) * 10), round(portion, 2)


def _sodium(shares):
    raw = 320 + shares["sauce"] * 30 + shares["protein"] * 3.2 + shares["staple"] * 2.2
    return int(round(raw / 10.0) * 10)


def _score(shares):
    veg, staple, protein, sauce = shares["veg"], shares["staple"], shares["protein"], shares["sauce"]
    score = 0
    score += 30 if veg >= 35 else 24 if veg >= 25 else 14 if veg >= 15 else 6
    score += 25 if 18 <= staple <= 45 else 18 if staple < 18 or staple <= 55 else 9
    score += 25 if 15 <= protein <= 40 else 17 if 10 <= protein < 15 or 40 < protein <= 50 else 8
    score += 20 if sauce <= 12 else 13 if sauce <= 22 else 5
    return max(0, min(100, score))


def _grade(score):
    if score >= 85:
        return "优秀", "ok"
    if score >= 70:
        return "良好", "ok"
    if score >= 55:
        return "一般", "warn"
    return "待改善", "bad"


def _findings(shares, kcal, sodium, flags, plan):
    veg, staple, protein, sauce = shares["veg"], shares["staple"], shares["protein"], shares["sauce"]
    out = []

    def add(level, title, text):
        out.append({"level": level, "title": title, "text": text})

    if veg >= 35:
        add("ok", "蔬菜充足", f"蔬菜约占 {veg:.0f}%，膳食纤维与钾的摄入有保障。")
    elif veg >= 22:
        add("warn", "蔬菜略少", f"蔬菜约占 {veg:.0f}%，建议再加半碗深色蔬菜。")
    else:
        add("bad", "蔬菜偏少", f"蔬菜仅约 {veg:.0f}%，建议每餐至少两拳头蔬菜。")

    if staple > 55:
        add("bad", "主食偏多", f"主食约占 {staple:.0f}%，可先吃菜和蛋白，主食减掉四分之一。")
    elif 18 <= staple <= 45:
        add("ok", "主食适量", f"主食约占 {staple:.0f}%，与处方定量接近。")
    elif staple < 18:
        add("warn", "主食偏少", "主食过少容易餐后饥饿，可在加餐补一份水果或酸奶。")

    if protein < 12:
        add("bad", "蛋白不足", f"蛋白类仅约 {protein:.0f}%，建议加 1 个鸡蛋或 50 g 鱼、瘦肉。")
    elif protein <= 40:
        add("ok", "蛋白合适", f"蛋白类约占 {protein:.0f}%，接近一掌心。")
    else:
        add("warn", "蛋白偏多", "单餐蛋白偏多，可把一部分留到下一餐。")

    if sauce > 22:
        add("bad", "油盐偏重", f"深色酱汁与油光约占 {sauce:.0f}%，钠估算约 {sodium} mg，已超过单餐建议。")
    elif sauce <= 12:
        add("ok", "清淡少油", f"油脂酱汁约占 {sauce:.0f}%，烹调方式较清淡。")

    if flags.get("ckd") and protein > 25:
        add("warn", "需限蛋白", "肾功能不全时单餐蛋白宜控制在 15–20 g，请按肾内科方案调整。")
    if flags.get("dm") and staple > 45:
        add("warn", "主食需定量", "糖尿病配餐建议每餐主食生重 50–75 g，先菜后饭。")
    if flags.get("htn") and sodium > plan.get("sodium", 2000) / 3 * 1.4:
        add("warn", "钠偏高", "高血压人群单餐钠建议不超过 600 mg，少用酱油与腌制品。")
    return out


def _suggestions(shares, flags):
    veg, staple, protein, sauce = shares["veg"], shares["staple"], shares["protein"], shares["sauce"]
    out = []
    if veg < 25:
        out.append("下一餐先保证一份深色蔬菜（菠菜、西兰花、油麦菜约 150–200 g）。")
    if staple > 45:
        out.append("主食减至一拳头，优先杂粮饭、荞麦面，避免白粥配咸菜。")
    if protein < 12:
        out.append("补一份优质蛋白：水煮蛋、清蒸鱼、豆腐或无糖酸奶。")
    if sauce > 22:
        out.append("把酱汁单独放小碟蘸着吃，或改用醋、柠檬、香辛料提味。")
    if flags.get("htn"):
        out.append("今天余下两餐控制在少盐口味，避免腌制品与加工肉。")
    if flags.get("dm"):
        out.append("餐后 2 小时测一次血糖，观察这一餐的主食量是否合适。")
    if flags.get("ckd"):
        out.append("蔬菜先焯水再炒，少喝菜汤，减少钾与磷的摄入。")
    if not out:
        out.append("结构均衡，保持这个搭配；继续拍照记录，建议会越来越贴合您的口味。")
    return out[:4]


def analyze(path, patient=None, age=None, conditions=None, plan=None):
    """分析一张饮食照片，返回结构化结果。"""
    from backend.services import diet as diet_svc

    plan = plan or {}
    names = [c["name"] if isinstance(c, dict) else str(c) for c in (conditions or [])]
    flags = diet_svc._flags(names)

    with Image.open(path) as raw:
        img = ImageOps.exif_transpose(raw).convert("RGB")
    small = img.copy()
    small.thumbnail((ANALYZE_SIDE, ANALYZE_SIDE))
    shares, food_ratio = _analyze_pixels(small)
    sharp = _sharpness(small)

    conf = 0.55
    if food_ratio >= 0.3:
        conf += 0.12
    if sharp >= 14:
        conf += 0.1
    if max(shares.values()) >= 30:
        conf += 0.08
    conf = round(min(0.88, conf), 2)

    kcal, portion = _energy(shares, food_ratio)
    sodium = _sodium(shares)
    score = _score(shares)
    grade, level = _grade(score)
    dominant = _dominant(shares)
    dom_name = CATEGORY_META[dominant]["name"]

    if food_ratio < 0.16:
        summary = ("照片中未识别到明显的餐盘区域，可能拍摄距离过远或光线不足。"
                   "建议俯拍整盘、让食物占画面 60% 以上后重拍，或补充文字描述。")
        conf = min(conf, 0.35)
    else:
        summary = (f"这一餐以{dom_name}为主，蔬菜约 {shares['veg']:.0f}%、"
                   f"主食约 {shares['staple']:.0f}%、蛋白约 {shares['protein']:.0f}%；"
                   f"估算 {kcal} kcal、钠 {sodium} mg，结构{grade}。")

    categories = []
    for key in ("veg", "staple", "protein", "sauce"):
        meta = CATEGORY_META[key]
        categories.append({
            "key": key, "name": meta["name"], "color": meta["color"],
            "share": shares[key],
            "energy": int(round(shares[key] * ENERGY_WEIGHT[key] * portion / 10.0) * 10),
        })

    return {
        "engine": "local-color-v1",
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dominant": dominant,
        "dominant_name": dom_name,
        "shares": shares,
        "categories": categories,
        "food_ratio": food_ratio,
        "portion": portion,
        "sharpness": round(sharp, 1),
        "confidence": conf,
        "estimated": {"kcal": kcal, "sodium": sodium},
        "score": score,
        "grade": grade,
        "level": level,
        "summary": summary,
        "findings": _findings(shares, kcal, sodium, flags, plan),
        "suggestions": _suggestions(shares, flags),
        "patient": {"age": age, "conditions": names},
        "disclaimer": "本结果由照片色彩与结构在本地估算，仅用于饮食记录与趋势参考，不能替代营养师评估。",
    }


# ---------------- 文件处理 ----------------
def save_upload(file_storage, patient_id):
    """校验并保存上传的饮食照片，返回 (相对路径, 元信息)。"""
    raw = file_storage.read()
    if not raw:
        raise PhotoError("没有收到照片，请重新选择")
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise PhotoError(f"照片不能超过 {config.MAX_UPLOAD_MB} MB")
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.load()
    except (UnidentifiedImageError, OSError):
        raise PhotoError("无法识别该图片，请上传 JPG 或 PNG 格式的照片")
    if probe.format not in ALLOWED_FORMATS:
        raise PhotoError("仅支持 JPG、PNG、WEBP 格式的照片")
    width, height = probe.size
    if min(width, height) < 200:
        raise PhotoError("图片分辨率过低，请上传清晰一些的照片")

    img = ImageOps.exif_transpose(probe).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))

    day = datetime.now().strftime("%Y-%m-%d")
    name = f"{day}-{uuid.uuid4().hex[:10]}.jpg"
    rel_dir = os.path.join("diet", str(patient_id))
    abs_dir = os.path.join(config.UPLOAD_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    abs_path = os.path.join(abs_dir, name)
    img.save(abs_path, "JPEG", quality=85, optimize=True)
    rel = os.path.join(rel_dir, name).replace("\\", "/")
    return rel, {"width": width, "height": height, "bytes": len(raw),
                 "saved_bytes": os.path.getsize(abs_path)}


def photo_abspath(rel_path):
    """把相对路径解析为绝对路径，并阻止目录穿越。"""
    if not rel_path:
        return None
    root = os.path.abspath(config.UPLOAD_DIR)
    full = os.path.abspath(os.path.join(root, rel_path))
    return full if full.startswith(root + os.sep) else None
