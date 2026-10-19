"""专家能力目录：技能、外部工具（MCP）与专科模板。"""

SKILL_CATALOG = [
    {"key": "metric_review", "name": "指标解读", "desc": "读懂家庭监测的血压、血糖、血氧趋势与达标率", "icon": "trend"},
    {"key": "risk_triage", "name": "风险分诊", "desc": "识别红旗症状与危急值，判断就医紧迫程度", "icon": "shield"},
    {"key": "med_check", "name": "用药核对", "desc": "核对服药时间、依从性、重复用药与相互作用", "icon": "pill"},
    {"key": "diet_rx", "name": "饮食处方", "desc": "按病种、体重与口味生成可执行的一日三餐", "icon": "food"},
    {"key": "exercise_rx", "name": "运动处方", "desc": "给出运动类型、强度、频次与停止信号", "icon": "activity"},
    {"key": "followup", "name": "随访计划", "desc": "安排复查节奏、监测频次与随访要点", "icon": "calendar"},
    {"key": "referral", "name": "转诊建议", "desc": "判断需要上转的专科、时机与准备材料", "icon": "arrow"},
    {"key": "education", "name": "健康教育", "desc": "用通俗语言讲清机制、误区与自我管理", "icon": "book"},
    {"key": "emotion", "name": "情绪支持", "desc": "识别焦虑抑郁信号并给出调节与求助路径", "icon": "heart"},
    {"key": "sleep", "name": "睡眠管理", "desc": "评估打鼾、失眠与夜间血压/血糖波动", "icon": "clock"},
]

MCP_CATALOG = [
    {"key": "vitals_query", "name": "家庭体征查询", "desc": "读取血压计、血氧仪、手环的实时数据", "builtin": True},
    {"key": "metric_trend", "name": "指标趋势分析", "desc": "计算近 7/30/90 天趋势、达标率与异常点", "builtin": True},
    {"key": "guideline_search", "name": "指南全文检索", "desc": "在本地指南库中按语义检索证据段落", "builtin": True},
    {"key": "medication_db", "name": "药品说明书库", "desc": "查询适应证、禁忌、相互作用与剂量上限", "builtin": False},
    {"key": "lab_parse", "name": "检验报告解析", "desc": "上传检验单后自动提取关键指标与趋势", "builtin": False},
    {"key": "risk_model", "name": "心脑血管风险模型", "desc": "调用 10 年 ASCVD 风险预测并给出分层", "builtin": False},
    {"key": "appointment", "name": "预约挂号", "desc": "对接社区门诊号源，代患者预约与改约", "builtin": False},
    {"key": "followup_call", "name": "智能随访外呼", "desc": "按随访计划发起电话或短信触达", "builtin": False},
    {"key": "wearable_sync", "name": "可穿戴设备同步", "desc": "拉取手环睡眠、步数与心率变异性", "builtin": False},
]

ROLE_CATALOG = [
    {"key": "cardio", "name": "心血管内科", "desc": "血压、冠心病与心血管风险"},
    {"key": "endo", "name": "内分泌科", "desc": "糖尿病、血糖波动与体重管理"},
    {"key": "nutrition", "name": "临床营养科", "desc": "医学营养治疗与配餐落地"},
    {"key": "pharmacy", "name": "临床药学", "desc": "多重用药、依从性与相互作用"},
    {"key": "nephro", "name": "肾内科", "desc": "慢性肾脏病与心肾共病"},
    {"key": "gp", "name": "全科医学", "desc": "综合管理、随访与转诊协调"},
]

DEFAULT_SKILLS_BY_ROLE = {
    "cardio": ["metric_review", "risk_triage", "med_check", "referral", "followup"],
    "endo": ["metric_review", "diet_rx", "med_check", "followup", "education"],
    "nutrition": ["diet_rx", "education", "metric_review"],
    "pharmacy": ["med_check", "education", "followup"],
    "nephro": ["metric_review", "med_check", "referral", "diet_rx"],
    "gp": ["risk_triage", "followup", "referral", "education", "emotion"],
}

DEFAULT_MCP_BY_ROLE = {
    "cardio": ["vitals_query", "metric_trend", "guideline_search", "risk_model"],
    "endo": ["vitals_query", "metric_trend", "guideline_search", "lab_parse"],
    "nutrition": ["guideline_search", "metric_trend"],
    "pharmacy": ["medication_db", "guideline_search"],
    "nephro": ["lab_parse", "guideline_search", "metric_trend"],
    "gp": ["vitals_query", "metric_trend", "guideline_search", "appointment", "followup_call"],
}

DEFAULT_KB_CATEGORIES_BY_ROLE = {
    "cardio": ["高血压", "冠心病", "血脂异常", "监测规范"],
    "endo": ["糖尿病", "血脂异常", "监测规范"],
    "nutrition": ["糖尿病", "慢性肾病", "生活方式"],
    "pharmacy": ["用药安全", "高血压", "糖尿病"],
    "nephro": ["慢性肾病", "高血压", "糖尿病"],
    "gp": [],  # 全库检索
}

SKILL_MAP = {s["key"]: s for s in SKILL_CATALOG}
MCP_MAP = {m["key"]: m for m in MCP_CATALOG}
