"""安全门禁：红旗症状识别 + 危急值判定。"""
from datetime import datetime, timedelta

from backend import db

RED_FLAG_TERMS = [
    ("胸痛", "胸痛/胸闷持续不缓解，需排除急性冠脉综合征"),
    ("胸闷", "胸闷明显，需警惕心肌缺血"),
    ("呼吸困难", "呼吸困难提示心肺功能失代偿"),
    ("喘不上", "呼吸困难提示心肺功能失代偿"),
    ("意识模糊", "意识改变属急危重症表现"),
    ("昏迷", "意识丧失需立即急救"),
    ("晕厥", "晕厥可能为心源性或低血糖所致"),
    ("说话不清", "言语不清需排除脑卒中"),
    ("口角歪斜", "口角歪斜需排除脑卒中"),
    ("半身", "单侧肢体无力需排除脑卒中"),
    ("抽搐", "抽搐需急诊处理"),
    ("自杀", "存在自伤风险，需立即心理危机干预"),
    ("不想活", "存在自伤风险，需立即心理危机干预"),
    ("大出血", "活动性出血需急诊处理"),
]

CRITICAL_TEXT = [
    ("血压 200", "血压显著升高"),
    ("180/110", "达到高血压急症阈值"),
]

COMMON_DRUGS = [
    "氨氯地平", "硝苯地平", "缬沙坦", "厄贝沙坦", "氯沙坦", "培哚普利", "依那普利",
    "美托洛尔", "比索洛尔", "氢氯噻嗪", "吲达帕胺", "呋塞米", "螺内酯",
    "二甲双胍", "格列美脲", "格列齐特", "西格列汀", "利格列汀", "达格列净", "恩格列净",
    "阿卡波糖", "胰岛素", "甘精胰岛素", "门冬胰岛素",
    "阿托伐他汀", "瑞舒伐他汀", "辛伐他汀", "非诺贝特", "依折麦布",
    "阿司匹林", "氯吡格雷", "替格瑞洛", "华法林", "利伐沙班",
    "缬沙坦氨氯地平", "沙美特罗", "噻托溴铵", "布地奈德", "孟鲁司特",
    "别嘌醇", "非布司他", "碳酸钙", "骨化三醇", "复方丹参滴丸",
]


def latest_metrics(patient_id):
    out = {}
    for t in ("sbp", "dbp", "glucose", "heart_rate", "spo2", "hba1c"):
        row = db.query(
            "SELECT value, measured_at FROM metrics WHERE patient_id=? AND metric_type=? "
            "ORDER BY measured_at DESC LIMIT 1", (patient_id, t), one=True)
        if row:
            out[t] = row
    return out


def check(patient_id, text, metrics=None):
    """返回 {hit, level, title, reasons, actions, evidence}。"""
    m = metrics if metrics is not None else latest_metrics(patient_id)
    reasons, evidence = [], []

    for term, why in RED_FLAG_TERMS:
        if term in text:
            reasons.append(why)
            evidence.append(f"您提到「{term}」")

    sbp = (m.get("sbp") or {}).get("value")
    dbp = (m.get("dbp") or {}).get("value")
    glu = (m.get("glucose") or {}).get("value")
    hr = (m.get("heart_rate") or {}).get("value")
    spo2 = (m.get("spo2") or {}).get("value")

    if sbp and dbp and (sbp >= 180 or dbp >= 110):
        reasons.append("血压达到高血压急症阈值")
        evidence.append(f"最近血压 {sbp:.0f}/{dbp:.0f} mmHg")
    if glu is not None and glu < 3.9:
        reasons.append("低血糖，需立即处理")
        evidence.append(f"最近血糖 {glu:.1f} mmol/L")
    if glu is not None and glu > 16.7:
        reasons.append("血糖显著升高，警惕高血糖危象")
        evidence.append(f"最近血糖 {glu:.1f} mmol/L")
    if hr and hr > 120:
        reasons.append("静息心率过快")
        evidence.append(f"最近心率 {hr:.0f} 次/分")
    if spo2 and spo2 < 90:
        reasons.append("血氧饱和度偏低")
        evidence.append(f"最近血氧 {spo2:.0f}%")

    if not reasons:
        return {"hit": False}

    return {
        "hit": True,
        "level": "critical",
        "title": "检测到需要立即处理的危险信号",
        "reasons": reasons,
        "evidence": evidence,
        "actions": [
            "如症状正在发生且较严重，请立即拨打 120 或前往最近医院急诊",
            "保持安静休息，采取坐位或半卧位，不要自行加服药物",
            "立即测量并记录血压/血糖/血氧，便于医生判断",
            "同步通知您的签约医生或家属",
        ],
    }


def emergency_answer(patient_name, result):
    lines = [f"**{patient_name}，请先停下手中的事，这可能是需要立即处理的紧急情况。**", ""]
    lines.append("**判断依据**")
    for e in result.get("evidence", []):
        lines.append(f"- {e}")
    for r in result.get("reasons", []):
        lines.append(f"- {r}")
    lines.append("")
    lines.append("**现在马上做**")
    for a in result.get("actions", []):
        lines.append(f"- {a}")
    lines.append("")
    lines.append("**不要做**")
    lines.append("- 不要自行加服降压药或降糖药，避免血压/血糖骤降")
    lines.append("- 不要独自驾车前往医院")
    lines.append("")
    lines.append("以上为平台安全规则自动触发的提示，不替代急救指导。症状缓解后请当天联系签约医生复诊。")
    return "\n".join(lines)


def check_drugs(answer, medications):
    """返回回答中出现但不在患者用药清单内的药名。"""
    own = " ".join(m["drug_name"] for m in medications)
    unknown = []
    for d in COMMON_DRUGS:
        if d in answer and d not in own:
            unknown.append(d)
    return unknown
