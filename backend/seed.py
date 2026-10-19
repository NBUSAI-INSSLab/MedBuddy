"""初始化演示数据：账号、12 位患者、指标时序、预警、计划、知识库。"""
import json
import random
from datetime import datetime, timedelta

from backend import db

random.seed(20261019)


def _d(days_ago, hour=8):
    return (datetime.now() - timedelta(days=days_ago)).strftime(f"%Y-%m-%d {hour:02d}:%M:00")


KB_DOCS = [
    {
        "title": "中国高血压防治指南（2024年修订版）核心要点",
        "category": "高血压",
        "doc_type": "guideline",
        "source": "中国高血压防治指南修订委员会",
        "version": "2024",
        "content": """# 高血压的诊断与分级

## 诊断标准
在未使用降压药物的情况下，非同日 3 次测量诊室血压，收缩压 ≥140 mmHg 和（或）舒张压 ≥90 mmHg，可诊断为高血压。家庭血压监测的诊断阈值为 ≥135/85 mmHg，24 小时动态血压平均值为 ≥130/80 mmHg。收缩压 ≥140 mmHg 且舒张压 <90 mmHg 为单纯收缩期高血压，多见于老年人。

## 血压水平分级
1 级高血压：收缩压 140–159 mmHg 或舒张压 90–99 mmHg。
2 级高血压：收缩压 160–179 mmHg 或舒张压 100–109 mmHg。
3 级高血压：收缩压 ≥180 mmHg 或舒张压 ≥110 mmHg。
当收缩压与舒张压分属不同级别时，以较高的级别为准。

# 降压目标

## 一般人群
一般高血压患者应降至 <140/90 mmHg；能耐受者和部分高危及以上患者可进一步降至 <130/80 mmHg。65–79 岁老年人首先降至 <150/90 mmHg，若耐受良好可降至 <140/90 mmHg。

## 高龄与合并症
80 岁及以上老年人降至 <150/90 mmHg 即可，避免过度降压导致脑灌注不足。合并糖尿病、慢性肾脏病、冠心病或心力衰竭者，目标为 <130/80 mmHg，但舒张压不宜低于 60 mmHg。

# 非药物干预
限制钠盐摄入，每人每日食盐不超过 5 g，注意酱油、腌制品、加工食品中的隐性钠。增加富钾食物（新鲜蔬菜、水果、豆类）。控制体重，体质指数维持在 18.5–23.9 kg/m²，腰围男性 <90 cm、女性 <85 cm。每周进行 5–7 天、每次 30 分钟中等强度有氧运动，如快走、慢跑、游泳、骑车。戒烟并避免二手烟，限制饮酒。保证每晚 7–8 小时睡眠，处理焦虑与打鼾问题。

# 药物治疗原则

## 起始与联合
常用五大类降压药：钙通道阻滞剂、血管紧张素转换酶抑制剂、血管紧张素受体拮抗剂、利尿剂、β 受体阻滞剂。血压 ≥160/100 mmHg 或高于目标值 20/10 mmHg 时，起始即可联合两种药物，优先推荐单片复方制剂以提高依从性。

## 服药时间与漏服
长效制剂每日一次，建议早晨固定时间服用；除非动态血压提示夜间高血压，一般不常规改为睡前服药。漏服时若距下次服药时间超过一半，可补服；临近下次服药则跳过，不可加倍服用。

# 家庭血压监测
推荐使用经过验证的上臂式电子血压计。测量前静坐 5 分钟，避免吸烟、饮咖啡和憋尿；坐位，背部有支撑，上臂与心脏同高，袖带下缘距肘窝 2–3 cm。每次测 2–3 遍，间隔 1 分钟，取平均值。初诊或调整方案期间连续测量 7 天，每天早晚各一次；稳定期每周至少测量 1–3 天。

# 随访与转诊
血压达标且稳定者每 3 个月随访一次；未达标或调整方案者每 2–4 周随访。随访内容包括血压、服药依从性、不良反应、生活方式与靶器官损害评估。出现收缩压 ≥180 mmHg 或舒张压 ≥110 mmHg 并伴胸痛、呼吸困难、意识改变、视物模糊时，按高血压急症处理，立即转诊。

# 常见误区
没有症状不等于血压正常，多数高血压患者无症状。降压药不会成瘾，不应因血压正常自行停药。保健品不能替代降压药物。血压波动明显时应记录测量时间与情境，交给医生判断，而不是自行加药。""",
    },
    {
        "title": "国家基层糖尿病防治管理指南（2024）要点",
        "category": "糖尿病",
        "doc_type": "guideline",
        "source": "国家基层糖尿病防治管理办公室",
        "version": "2024",
        "content": """# 诊断与分型

## 诊断标准
具有典型糖尿病症状（多饮、多尿、多食、体重下降）且随机血糖 ≥11.1 mmol/L，或空腹血糖 ≥7.0 mmol/L，或口服葡萄糖耐量试验 2 小时血糖 ≥11.1 mmol/L，或糖化血红蛋白 ≥6.5%，即可诊断。无典型症状者需改日复查确认。空腹血糖 6.1–6.9 mmol/L 为空腹血糖受损，属于糖尿病前期。

# 控制目标

## 一般成人
空腹血糖 4.4–7.0 mmol/L，非空腹血糖 <10.0 mmol/L，糖化血红蛋白 <7.0%。年轻、病程短、无并发症者可更严格（糖化 <6.5%）；高龄、有严重低血糖史、预期寿命有限者可放宽至 <8.0%。

## 老年患者
65 岁以上健康状况良好者糖化血红蛋白目标 <7.0%–7.5%；合并多种疾病或认知功能下降者 <8.0%；临终关怀阶段以避免症状性高血糖为主。老年人应优先避免低血糖，而非追求严格达标。

# 生活方式干预
主食定量，粗细搭配，全谷物和杂豆占主食的 1/3；限制精制糖与含糖饮料。蛋白质来源以鱼、禽、蛋、瘦肉、豆制品为主。每日蔬菜 500 g 左右，深色蔬菜占一半。进餐顺序建议先蔬菜、再蛋白质、最后主食，有助于降低餐后血糖波动。每周至少 150 分钟中等强度有氧运动，配合 2–3 次抗阻训练，避免连续两天不运动。

# 降糖药物

## 常用药物特点
二甲双胍是多数 2 型糖尿病患者的一线用药，随餐或餐后服用可减少胃肠道反应。磺脲类（格列美脲、格列齐特）促胰岛素分泌，低血糖风险较高，老年人慎用。DPP-4 抑制剂低血糖风险低。SGLT-2 抑制剂（达格列净、恩格列净）对心肾有保护作用，但需注意泌尿生殖道感染与脱水风险。合并动脉粥样硬化性心血管疾病、心力衰竭或慢性肾脏病者，优先考虑 SGLT-2 抑制剂或 GLP-1 受体激动剂。

## 胰岛素使用
口服药控制不佳、急性并发症、围手术期或妊娠期需胰岛素治疗。基础胰岛素起始剂量按体重计算，需根据空腹血糖逐步调整。注射部位应轮换，避免同一部位反复注射导致脂肪增生。

# 低血糖识别与处理
血糖 <3.9 mmol/L 即为低血糖，表现为心慌、出汗、手抖、饥饿感、头晕，严重者可出现意识模糊、抽搐、昏迷。清醒患者立即口服 15 g 碳水化合物（如 150 ml 果汁、3–4 块方糖），15 分钟后复测，仍低则重复。不要用巧克力或含油脂食物急救，吸收过慢。意识障碍者禁止喂食，立即送医并静脉推注葡萄糖。

# 监测与并发症筛查
使用口服药者每周监测 2–4 次指尖血糖，方案调整期或胰岛素治疗者需增加频次。每 3 个月检测糖化血红蛋白。每年检查眼底、尿白蛋白/肌酐比值、肾功能、足部感觉与血管、血脂与血压。糖尿病患者每年至少进行一次足部检查，每日自查足部有无破损、水疱与颜色改变。

# 随访安排
血糖达标者每 3 个月随访一次；未达标或调整治疗者每 2–4 周随访。随访应评估血糖记录、低血糖事件、体重、血压、用药依从性与生活方式执行情况。出现反复低血糖、血糖持续 >16.7 mmol/L、恶心呕吐、呼吸有烂苹果味时，警惕酮症酸中毒，须急诊处理。""",
    },
    {
        "title": "中国血脂管理指南（2023）要点",
        "category": "血脂异常",
        "doc_type": "guideline",
        "source": "中国血脂管理指南修订联合专家委员会",
        "version": "2023",
        "content": """# 血脂检测与目标

## 检测项目
基本血脂检测包括总胆固醇、甘油三酯、低密度脂蛋白胆固醇（LDL-C）和高密度脂蛋白胆固醇。40 岁以上成年人每年至少检测一次；动脉粥样硬化性心血管疾病患者每 3–6 个月复查。

## LDL-C 目标分层
低危人群 LDL-C <3.4 mmol/L；中危 <2.6 mmol/L；高危 <1.8 mmol/L 且较基线下降 ≥50%；极高危 <1.4 mmol/L 且下降 ≥50%；超高危 <1.0 mmol/L 且下降 ≥50%。糖尿病合并高血压、慢性肾脏病或吸烟者通常属于高危及以上。

# 生活方式干预
减少饱和脂肪和反式脂肪摄入，少吃动物内脏、肥肉、油炸食品与糕点。每日烹调油 25 g 以内，优先植物油。增加膳食纤维，每日 25–30 g，多吃燕麦、豆类、蔬菜。每周吃 2 次鱼类。规律运动、控制体重、戒烟限酒。甘油三酯明显升高者应严格限制酒精与精制糖。

# 他汀类药物

## 使用原则
他汀是降低 LDL-C 的基石药物。起始中等强度他汀，如阿托伐他汀 10–20 mg 或瑞舒伐他汀 5–10 mg，每日一次，睡前或固定时间服用。用药 4–6 周后复查血脂与肝功能，根据结果调整。LDL-C 不达标可联合依折麦布或 PCSK9 抑制剂。

## 安全性监测
服药期间出现不明原因的肌肉疼痛、乏力、酱油色尿，应及时检测肌酸激酶。转氨酶升高不超过正常上限 3 倍时通常可继续观察，不必立即停药。他汀不耐受者需在医生指导下换药，不可自行停用。

# 甘油三酯升高
甘油三酯 ≥5.6 mmol/L 时急性胰腺炎风险显著增加，需严格戒酒、低脂饮食，并在医生指导下使用贝特类药物。贝特类与他汀联用需警惕肌病风险，应在医生监测下进行。

# 复查与随访
生活方式干预者 3–6 个月复查血脂；药物治疗者调药后 4–6 周复查，达标后每 3–6 个月复查。复查项目包括血脂、肝功能、肌酸激酶（有症状时）。同时评估血压、血糖与体重，因为血脂异常常与代谢综合征并存。""",
    },
    {
        "title": "慢性肾脏病早期筛查与基层管理",
        "category": "慢性肾病",
        "doc_type": "consensus",
        "source": "中华医学会肾脏病学分会",
        "version": "2023",
        "content": """# 定义与分期

## 诊断依据
肾脏结构或功能异常持续超过 3 个月，包括尿白蛋白/肌酐比值 ≥30 mg/g、尿沉渣异常、影像学异常，或肾小球滤过率（eGFR）<60 mL/min/1.73m²，即可诊断慢性肾脏病。按 eGFR 分为 G1–G5 期：G1 ≥90，G2 60–89，G3a 45–59，G3b 30–44，G4 15–29，G5 <15 mL/min。

## 高危人群
糖尿病、高血压、高尿酸血症、肥胖、老年人、有肾脏病家族史、长期使用肾毒性药物者，应每年筛查尿白蛋白/肌酐比值与血肌酐。

# 血压与血糖管理
慢性肾脏病患者血压目标一般 <130/80 mmHg，优先使用血管紧张素转换酶抑制剂或受体拮抗剂，并在用药后 1–2 周复查血肌酐与血钾。血肌酐较基线上升超过 30% 需评估是否减量。糖尿病患者糖化血红蛋白目标个体化，多为 <7.0%，但 G4–G5 期患者需放宽并警惕低血糖。

# 饮食管理
限制钠盐，每日食盐 <5 g。蛋白质摄入 0.8 g/kg/日，以优质蛋白为主；透析患者需增加至 1.0–1.2 g/kg/日。G3 期起限制磷摄入，少食加工食品、动物内脏、浓肉汤。高钾风险患者（G4 期以上或使用保钾药物）需限制香蕉、橙子、土豆、菌菇等高钾食物，并定期监测血钾。

# 避免肾损伤
避免自行服用非甾体抗炎药（如布洛芬、双氯芬酸）、氨基糖苷类抗生素和含马兜铃酸的中草药。使用造影剂前后需评估肾功能并充分水化。腹泻、发热、食欲差导致脱水时，应及时就医并暂停可能加重肾损伤的药物。不要盲目服用"补肾"保健品。

# 随访与转诊
G1–G2 期每年复查 eGFR 与尿蛋白；G3 期每 3–6 个月复查；G4 期每 1–3 个月复查，并评估贫血、钙磷代谢与酸中毒。出现 eGFR 快速下降（每年下降 >5 mL/min）、血钾 >5.5 mmol/L、难以控制的水肿或血压、明显贫血时，应转诊肾内科。""",
    },
    {
        "title": "慢性阻塞性肺疾病基层诊疗指南要点",
        "category": "慢阻肺",
        "doc_type": "guideline",
        "source": "中华医学会呼吸病学分会",
        "version": "2024",
        "content": """# 诊断与评估

## 诊断标准
有呼吸困难、慢性咳嗽或咳痰、危险因素暴露史（吸烟、粉尘、生物燃料）者，应进行肺功能检查。吸入支气管舒张剂后第一秒用力呼气容积与用力肺活量比值 <0.70，可确诊持续气流受限。

## 症状评估
常用 mMRC 呼吸困难量表与 CAT 评分评估症状。mMRC ≥2 分或 CAT ≥10 分提示症状明显。每年急性加重 ≥2 次或 ≥1 次导致住院，属急性加重高风险。

# 稳定期治疗

## 吸入药物
长效支气管舒张剂是核心治疗。长效抗胆碱能药物（噻托溴铵）可减少急性加重；长效 β2 受体激动剂与吸入糖皮质激素联合适用于频繁急性加重且血嗜酸粒细胞升高者。吸入装置的正确使用直接决定疗效，每次随访应检查吸入手法。

## 非药物干预
戒烟是延缓肺功能下降最有效的措施。每年接种流感疫苗，符合条件者接种肺炎球菌疫苗。进行肺康复训练，包括缩唇呼吸、腹式呼吸与下肢耐力训练，每周 3–5 次。长期家庭氧疗适用于静息血氧 ≤88% 或合并肺心病者，每日吸氧不少于 15 小时。

# 急性加重的识别与处理
呼吸困难加重、痰量增多、痰液变脓是急性加重的典型表现。出现口唇发紫、意识改变、无法完整说话、下肢水肿加重、血氧 <90% 时需立即就医。急性加重期应在医生指导下短期增加支气管舒张剂、使用抗生素与口服糖皮质激素，避免自行长期使用激素。

# 日常监测与随访
稳定期每 3–6 个月随访，评估症状、吸入技术、急性加重次数与肺功能。建议患者记录每日症状与血氧。冬季注意保暖、避免雾霾天外出、远离油烟与二手烟。体重下降明显者需加强营养，少食多餐，保证优质蛋白摄入。""",
    },
    {
        "title": "冠心病二级预防与心脏康复",
        "category": "冠心病",
        "doc_type": "guideline",
        "source": "中华医学会心血管病学分会",
        "version": "2023",
        "content": """# 二级预防核心措施

## 抗血小板治疗
冠心病患者长期服用阿司匹林，剂量通常 75–100 mg/日。支架植入术后需按医嘱进行双联抗血小板治疗，持续时间由医生根据支架类型与出血风险决定，不可自行提前停药，否则可能发生支架内血栓。

## 调脂与稳定斑块
LDL-C 目标 <1.8 mmol/L，极高危患者 <1.4 mmol/L。坚持服用他汀，即使血脂"正常"也不可自行停药，因为他汀同时具有稳定斑块的作用。

## 控制心率与血压
β 受体阻滞剂可降低心肌耗氧，静息心率控制在 55–60 次/分较为理想。血压目标 <130/80 mmHg。合并糖尿病者需控制血糖，糖化血红蛋白 <7.0%。

# 心脏康复运动处方
运动前需进行心肺运动试验或 6 分钟步行试验评估。处方包括热身 5–10 分钟、有氧运动 20–40 分钟（快走、骑车，强度为最大心率的 50%–70%）、放松 5–10 分钟，每周 3–5 次。运动中出现胸痛、胸闷、头晕、心悸或明显气短应立即停止。避免清晨寒冷时段剧烈运动与突然用力。

# 警示症状与急救
胸骨后压榨性疼痛持续超过 15 分钟、含服硝酸甘油不缓解，或伴大汗、恶心、呼吸困难、放射至左肩或下颌，应高度怀疑急性心肌梗死，立即拨打 120。不要自行驾车，不要反复含服硝酸甘油超过 3 次。家中可备硝酸甘油，注意避光保存并定期更换。

# 随访
病情稳定者每 3–6 个月随访，评估症状、血压心率、血脂、血糖、运动耐量与用药依从性。每年复查心电图、心脏超声；根据症状决定是否复查冠脉影像。合并焦虑抑郁者应同步干预，情绪应激是心绞痛发作的重要诱因。""",
    },
    {
        "title": "慢病生活方式干预处方：膳食、运动、戒烟与睡眠",
        "category": "生活方式",
        "doc_type": "protocol",
        "source": "平台临床营养与运动专家组",
        "version": "2025",
        "content": """# 膳食处方

## 通用原则
食物多样，谷类为主，粗细搭配。每日蔬菜 300–500 g，水果 200–350 g，奶类 300 ml。优先选择鱼、禽、蛋、瘦肉，减少肥肉与加工肉制品。每日烹调油 25–30 g，食盐不超过 5 g。规律进餐，避免暴饮暴食与夜间加餐。

## 高血压
重点限钠补钾。少用酱油、蚝油、豆瓣酱、咸菜、火腿、方便面。可用醋、柠檬、葱姜蒜、香草替代部分咸味。多吃菠菜、土豆、香蕉、豆类等富钾食物，但肾功能不全者需遵医嘱。

## 糖尿病
主食定量并优先低升糖指数食物，如燕麦、糙米、荞麦、杂豆。避免粥类煮得过烂，因为糊化程度越高升糖越快。水果放在两餐之间，每次 100–150 g，优先苹果、梨、柚子、草莓。血糖控制不佳时暂用黄瓜、番茄替代水果。

## 血脂异常
限制饱和脂肪，少吃动物油、黄油、肥肉、动物内脏。反式脂肪常见于起酥面包、饼干、奶茶植脂末。增加深海鱼、坚果（每日一小把）、燕麦与豆制品。

# 运动处方

## 评估与强度
运动前评估血压、血糖与心血管风险。中等强度以"能说话但不能唱歌"为宜，心率约为（220−年龄）×60%–70%。每周累计至少 150 分钟。

## 分病种要点
高血压患者避免憋气用力的举重与突然爆发性运动，血压 >180/110 mmHg 时暂停运动。糖尿病患者避免空腹运动，随身携带糖果，注射胰岛素者避开注射部位剧烈活动。慢阻肺患者以步行、太极、呼吸操为主，运动中采用缩唇呼吸。冠心病患者需在康复评估后制定处方。

# 戒烟
明确戒烟日，移除家中烟具，避免饮酒与吸烟场景。烟瘾发作时可饮水、咀嚼无糖口香糖、深呼吸或短时快走，通常 3–5 分钟可缓解。必要时在医生指导下使用尼古丁替代或伐尼克兰。戒烟后体重可能上升 2–4 kg，应通过增加运动与控制零食应对，不要因此复吸。

# 睡眠与心理
固定起床时间比固定入睡时间更重要。睡前 1 小时停止使用手机，卧室保持黑暗安静，温度 20–24℃。打鼾严重伴白天嗜睡者应筛查睡眠呼吸暂停，这与难治性高血压密切相关。长期焦虑抑郁会降低用药依从性并升高血压血糖，必要时接受专业心理干预。""",
    },
    {
        "title": "家庭血压与血糖监测操作规范",
        "category": "监测规范",
        "doc_type": "protocol",
        "source": "平台护理部",
        "version": "2025",
        "content": """# 家庭血压监测

## 设备选择
选择经过国际标准验证的上臂式电子血压计，袖带宽度需与上臂围匹配。不建议使用腕式血压计作为诊断依据。每 1–2 年校准一次。

## 测量步骤
测量前 30 分钟内不吸烟、不喝咖啡或浓茶、不运动，排空膀胱，静坐休息 5 分钟。坐位，双脚平放，背部靠椅，上臂裸露并放在桌面上，袖带中心与心脏同高，下缘距肘窝 2–3 cm。测量期间不说话、不看手机。连续测 2 次，间隔 1 分钟，取平均值；若两次差异 >5 mmHg，加测第三次。

## 记录与频次
初诊或调药期连续 7 天，每天早晨服药前与晚上睡前各测一次。稳定期每周 1–3 天。记录收缩压、舒张压、心率、测量时间，以及是否服药、有无不适。就诊时携带完整记录，不要只报最高值。

## 常见误差
袖带过松读数偏高，过紧偏低；说话可使收缩压升高 5–10 mmHg；膀胱充盈可升高 10 mmHg；上臂低于心脏水平读数偏高。左右臂血压差异 >10 mmHg 时应固定测量较高一侧并告知医生。

# 血糖监测

## 指尖血糖
洗手擦干后采血，避免用力挤压手指导致组织液稀释。首选无名指或中指侧面，轮换部位。空腹血糖指禁食 8–10 小时后，餐后 2 小时血糖从第一口饭开始计时。

## 监测节奏
仅口服药治疗且血糖稳定者每周 2–4 次，可轮换空腹与餐后。胰岛素治疗或方案调整期每天 2–4 次，包括空腹、餐后与睡前。出现心慌出汗等低血糖症状时随时加测。每 3 个月检测糖化血红蛋白，反映近 2–3 个月平均血糖。

## 记录要点
记录血糖值、时间、与进餐的关系、用药情况、运动与特殊事件（如感冒、应酬）。连续血糖监测设备可提供趋势曲线，但指尖血糖仍用于校准与低血糖确认。

# 数据上传与预警
平台会在收到指标后自动判读：收缩压 ≥180 或舒张压 ≥110 mmHg、血糖 <3.9 或 >16.7 mmol/L、血氧 <90%、静息心率 >120 次/分时触发预警，并通知签约医生。单次异常不必恐慌，先复测确认；连续异常或伴症状应及时就医。""",
    },
    {
        "title": "老年多重用药安全与用药依从性管理",
        "category": "用药安全",
        "doc_type": "consensus",
        "source": "中国老年医学学会",
        "version": "2024",
        "content": """# 多重用药风险

## 定义与现状
同时使用 5 种及以上药物称为多重用药。老年人常同时患有高血压、糖尿病、冠心病、骨关节病，跨科室开药容易重复、相互作用与累积不良反应。

## 常见风险组合
降压药与利尿剂联用可能导致体位性低血压与电解质紊乱。非甾体抗炎药可削弱降压药效果并损伤肾脏。阿司匹林与活血类中成药同用增加出血风险。多种含相同成分的复方感冒药叠加可导致对乙酰氨基酚过量。

# 用药精简原则
定期进行用药核查，列出所有处方药、非处方药、保健品与中成药。无明确适应证的药物应停用；可用一种复方制剂替代多种单药；尽量简化服药频次。任何停药或换药均需医生评估，尤其是 β 受体阻滞剂、抗癫痫药与糖皮质激素，突然停用可能反跳。

# 依从性提升

## 行为策略
把服药与固定日常动作绑定，如刷牙、早餐、睡前关灯。使用分格药盒提前分装一周药物。设置手机闹钟或让家属提醒。与医生沟通，在保证疗效前提下减少服药次数。

## 常见障碍
担心副作用而自行减量：应记录具体不适并复诊，由医生换药而非自行停药。记不住是否已服药：使用药盒或打卡表，不要凭感觉补服。经济负担：可询问是否有集采仿制药或医保目录内替代方案。吞咽困难：询问可否更换剂型，不要自行掰开缓释片或胶囊。

# 漏服处理
漏服后不要加倍补服。一般原则：若距下次服药时间较长（超过用药间隔的一半），可尽快补服；若已接近下次服药时间，则跳过本次。降压药、降糖药、抗凝药的具体处理需遵医嘱，出现头晕、心慌等不适及时测量并联系医生。

# 药物不良反应监测
出现新发头晕、乏力、水肿、皮疹、黑便、肌肉疼痛、心率过慢时，应怀疑药物不良反应，记录出现时间与用药关系并就诊。定期复查肝肾功能、电解质与血常规。保存一份最新用药清单，就诊时主动出示。""",
    },
]


PATIENTS = [
    {
        "name": "陈建国", "gender": "男", "birth_date": "1964-03-12", "phone": "13852002043",
        "city": "宁波市海曙区", "occupation": "企业中层管理", "height_cm": 172, "weight_kg": 82.5,
        "blood_type": "A型", "allergies": "青霉素过敏", "family_history": "父亲高血压、脑卒中",
        "smoking": "已戒烟3年", "drinking": "应酬时饮酒", "exercise": "每周1次快走",
        "salt_intake": "偏咸", "sleep_quality": "入睡困难，平均6小时",
        "conditions": [("I10", "高血压", "2级", 8), ("E11", "2型糖尿病", "中度", 5)],
        "meds": [("苯磺酸氨氯地平片", "5mg", "每日1次", "早餐后", 0.72, "服药后偶有踝部水肿"),
                 ("二甲双胍缓释片", "0.5g", "每日2次", "早晚餐后", 0.65, "餐后服用减少胃肠反应"),
                 ("阿托伐他汀钙片", "20mg", "每晚1次", "睡前", 0.8, "")],
        "base": {"sbp": 152, "dbp": 94, "glucose": 8.1, "hba1c": 8.3, "ldl": 3.2, "weight": 82.5},
        "trend": {"sbp": -4, "glucose": -0.3},
        "days": 210, "adherence": 0.7,
        "memories": [("barrier", "上夜班后经常忘记晚上那次二甲双胍"),
                     ("preference", "爱吃咸菜和腌笃鲜，觉得清淡菜没味道"),
                     ("goal", "希望三个月内把糖化降到7以下"),
                     ("fact", "常年应酬，每周饮酒2-3次")],
        "plan": ("高血压合并2型糖尿病综合管理", ["家庭血压每周≥5天，目标<130/80 mmHg",
                                              "空腹血糖4.4-7.0 mmol/L，3个月复查糖化",
                                              "低密度脂蛋白降至2.6 mmol/L以下"], 0.62, 12),
    },
    {
        "name": "李秀兰", "gender": "女", "birth_date": "1955-09-08", "phone": "13952017712",
        "city": "宁波市鄞州区", "occupation": "退休教师", "height_cm": 158, "weight_kg": 66.0,
        "blood_type": "B型", "allergies": "无", "family_history": "母亲冠心病",
        "smoking": "从不吸烟", "drinking": "不饮酒", "exercise": "每天太极40分钟",
        "salt_intake": "清淡", "sleep_quality": "易醒，平均6.5小时",
        "conditions": [("I10", "高血压", "2级", 12), ("I25", "冠心病", "稳定型", 6)],
        "meds": [("缬沙坦胶囊", "80mg", "每日1次", "早餐后", 0.9, ""),
                 ("美托洛尔缓释片", "47.5mg", "每日1次", "早餐后", 0.88, "静息心率维持55-60次/分"),
                 ("阿司匹林肠溶片", "100mg", "每日1次", "晚餐后", 0.85, ""),
                 ("瑞舒伐他汀钙片", "10mg", "每晚1次", "睡前", 0.9, "")],
        "base": {"sbp": 148, "dbp": 86, "glucose": 5.6, "hba1c": 6.1, "ldl": 2.4, "weight": 66.0},
        "trend": {"sbp": -8}, "days": 420, "adherence": 0.89,
        "memories": [("fact", "独居，女儿每周回来一次"),
                     ("preference", "坚持每天打太极，喜欢社区活动"),
                     ("barrier", "偶尔忘记早上是否已吃降压药")],
        "plan": ("高血压合并冠心病二级预防", ["血压<130/80 mmHg，静息心率55-60次/分",
                                          "LDL-C<1.8 mmol/L", "每周监测血压3天，记录心率"], 0.86, 5),
    },
    {
        "name": "王卫东", "gender": "男", "birth_date": "1971-06-21", "phone": "13752028890",
        "city": "宁波市北仑区", "occupation": "货运司机", "height_cm": 175, "weight_kg": 88.0,
        "blood_type": "O型", "allergies": "无", "family_history": "父亲糖尿病",
        "smoking": "每天吸烟10支", "drinking": "每周2次啤酒", "exercise": "几乎不运动",
        "salt_intake": "偏咸", "sleep_quality": "作息不规律，平均6小时",
        "conditions": [("E11", "2型糖尿病", "中度", 4), ("E78", "血脂异常", "轻度", 3)],
        "meds": [("二甲双胍片", "0.5g", "每日3次", "三餐后", 0.58, "经常因出车漏服"),
                 ("非诺贝特胶囊", "0.2g", "每日1次", "早餐后", 0.6, "")],
        "base": {"sbp": 132, "dbp": 84, "glucose": 9.2, "hba1c": 8.8, "ldl": 3.6, "weight": 88.0},
        "trend": {"glucose": 0.2, "weight": 1.2}, "days": 150, "adherence": 0.58,
        "memories": [("barrier", "跑长途经常错过饭点，药也常忘记吃"),
                     ("preference", "喜欢面食和含糖饮料"),
                     ("fact", "每天吸烟10支，多次想戒没成功")],
        "plan": ("2型糖尿病合并血脂异常管理", ["空腹血糖<7.0 mmol/L，餐后<10 mmol/L",
                                           "每周至少150分钟快走", "戒烟，减少含糖饮料"], 0.55, 9),
    },
    {
        "name": "张桂英", "gender": "女", "birth_date": "1948-01-30", "phone": "13552033321",
        "city": "宁波市江北区", "occupation": "退休", "height_cm": 152, "weight_kg": 58.5,
        "blood_type": "A型", "allergies": "磺胺类过敏", "family_history": "不详",
        "smoking": "从不吸烟", "drinking": "不饮酒", "exercise": "室内走动为主",
        "salt_intake": "偏咸", "sleep_quality": "夜尿2-3次，平均5.5小时",
        "conditions": [("I10", "高血压", "3级", 15), ("N18", "慢性肾脏病", "G3b期", 4),
                        ("E11", "2型糖尿病", "中度", 10)],
        "meds": [("硝苯地平控释片", "30mg", "每日1次", "早餐后", 0.8, ""),
                 ("厄贝沙坦片", "150mg", "每日1次", "早餐后", 0.78, "监测血钾与肌酐"),
                 ("达格列净片", "10mg", "每日1次", "早餐前", 0.75, "注意泌尿感染与脱水"),
                 ("碳酸钙D3片", "600mg", "每日1次", "晚餐后", 0.7, "")],
        "base": {"sbp": 168, "dbp": 92, "glucose": 7.8, "hba1c": 7.9, "ldl": 2.8,
                 "weight": 58.5, "egfr": 38},
        "trend": {"sbp": 2}, "days": 600, "adherence": 0.76,
        "memories": [("fact", "与老伴同住，老伴负责买菜做饭"),
                     ("barrier", "腿脚不便，到社区测血压不方便"),
                     ("preference", "口味重，喜欢咸鱼和酱菜")],
        "plan": ("高血压合并CKD G3b期综合管理", ["血压<130/80 mmHg，避免舒张压<60",
                                              "每月复查肾功能、血钾", "蛋白质0.8g/kg/日，限盐<5g"], 0.7, 7),
    },
    {
        "name": "刘志强", "gender": "男", "birth_date": "1978-11-05", "phone": "13652045567",
        "city": "宁波市镇海区", "occupation": "IT项目经理", "height_cm": 178, "weight_kg": 74.0,
        "blood_type": "AB型", "allergies": "无", "family_history": "无特殊",
        "smoking": "不吸烟", "drinking": "偶尔饮酒", "exercise": "每周跑步3次，每次5公里",
        "salt_intake": "适中", "sleep_quality": "良好，7小时",
        "conditions": [("I10", "高血压", "1级", 2)],
        "meds": [("苯磺酸氨氯地平片", "5mg", "每日1次", "早餐后", 0.95, "")],
        "base": {"sbp": 132, "dbp": 86, "glucose": 5.2, "hba1c": 5.4, "ldl": 2.6, "weight": 74.0},
        "trend": {"sbp": -3}, "days": 90, "adherence": 0.95,
        "memories": [("preference", "喜欢晨跑，关注运动心率"),
                     ("goal", "不想长期吃药，希望生活方式控制")],
        "plan": ("1级高血压生活方式干预", ["血压<130/80 mmHg", "维持每周3次有氧运动",
                                       "3个月评估是否可减药"], 0.9, 21),
    },
    {
        "name": "赵敏", "gender": "女", "birth_date": "1987-04-17", "phone": "18852059012",
        "city": "宁波市海曙区", "occupation": "会计", "height_cm": 163, "weight_kg": 59.0,
        "blood_type": "B型", "allergies": "无", "family_history": "母亲2型糖尿病",
        "smoking": "不吸烟", "drinking": "不饮酒", "exercise": "每周瑜伽2次",
        "salt_intake": "清淡", "sleep_quality": "工作压力大，平均6.5小时",
        "conditions": [("E11", "2型糖尿病", "轻度", 1), ("R73", "空腹血糖受损", "已进展", 3)],
        "meds": [("二甲双胍片", "0.5g", "每日2次", "早晚餐后", 0.88, "")],
        "base": {"sbp": 118, "dbp": 76, "glucose": 6.6, "hba1c": 6.8, "ldl": 2.9, "weight": 59.0},
        "trend": {"glucose": -0.1}, "days": 120, "adherence": 0.88,
        "memories": [("goal", "准备怀孕，担心降糖药影响"),
                     ("preference", "喜欢甜点，下午常喝奶茶")],
        "plan": ("年轻2型糖尿病早期管理", ["糖化<6.5%，空腹<6.1 mmol/L",
                                        "备孕前转诊内分泌专科评估用药", "减少含糖饮料"], 0.82, 14),
    },
    {
        "name": "孙德海", "gender": "男", "birth_date": "1959-07-14", "phone": "13352064432",
        "city": "宁波市鄞州区", "occupation": "退休工人", "height_cm": 170, "weight_kg": 61.0,
        "blood_type": "O型", "allergies": "无", "family_history": "父亲慢阻肺",
        "smoking": "每天吸烟20支", "drinking": "偶尔白酒", "exercise": "散步20分钟",
        "salt_intake": "偏咸", "sleep_quality": "咳嗽影响睡眠",
        "conditions": [("J44", "慢性阻塞性肺疾病", "GOLD 3级", 7), ("I10", "高血压", "1级", 5)],
        "meds": [("噻托溴铵粉吸入剂", "18μg", "每日1次", "上午", 0.72, "需检查吸入手法"),
                 ("沙美特罗替卡松粉吸入剂", "50/250μg", "每日2次", "早晚", 0.68, ""),
                 ("氨氯地平片", "5mg", "每日1次", "早餐后", 0.8, "")],
        "base": {"sbp": 138, "dbp": 82, "glucose": 5.4, "spo2": 92, "weight": 61.0},
        "trend": {"spo2": -1}, "days": 300, "adherence": 0.72,
        "memories": [("barrier", "吸入剂用法一直不太对，觉得没效果"),
                     ("fact", "每年冬季急性加重1-2次"),
                     ("preference", "喜欢在小区下棋，愿意出门活动")],
        "plan": ("慢阻肺稳定期管理", ["坚持规范吸入治疗，复核吸入手法",
                                   "每年流感疫苗，冬季防寒", "血氧<90%及时就诊"], 0.68, 10),
    },
    {
        "name": "周慧", "gender": "女", "birth_date": "1968-12-02", "phone": "15952076678",
        "city": "宁波市北仑区", "occupation": "超市店长", "height_cm": 160, "weight_kg": 70.0,
        "blood_type": "A型", "allergies": "无", "family_history": "姐姐糖尿病",
        "smoking": "不吸烟", "drinking": "不饮酒", "exercise": "每天站立工作8小时",
        "salt_intake": "适中", "sleep_quality": "良好，7小时",
        "conditions": [("E11", "2型糖尿病", "中度", 3), ("E78", "血脂异常", "轻度", 2)],
        "meds": [("西格列汀片", "100mg", "每日1次", "早餐前", 0.9, ""),
                 ("阿托伐他汀钙片", "10mg", "每晚1次", "睡前", 0.85, "")],
        "base": {"sbp": 126, "dbp": 78, "glucose": 6.9, "hba1c": 7.1, "ldl": 3.1, "weight": 70.0},
        "trend": {"glucose": -0.05}, "days": 240, "adherence": 0.9,
        "memories": [("preference", "喜欢跳广场舞，晚上常去"),
                     ("goal", "想把体重减到65公斤")],
        "plan": ("2型糖尿病合并血脂异常管理", ["糖化<7.0%", "LDL-C<2.6 mmol/L",
                                         "每周广场舞4次，减重5kg"], 0.85, 18),
    },
    {
        "name": "吴国强", "gender": "男", "birth_date": "1952-02-25", "phone": "13852081123",
        "city": "宁波市海曙区", "occupation": "退休干部", "height_cm": 168, "weight_kg": 76.0,
        "blood_type": "B型", "allergies": "无", "family_history": "兄长心梗",
        "smoking": "已戒烟10年", "drinking": "不饮酒", "exercise": "每天散步30分钟",
        "salt_intake": "偏咸", "sleep_quality": "早醒，平均6小时",
        "conditions": [("I25", "冠心病", "支架术后", 5), ("I10", "高血压", "2级", 20),
                        ("E11", "2型糖尿病", "中度", 12)],
        "meds": [("阿司匹林肠溶片", "100mg", "每日1次", "早餐后", 0.92, ""),
                 ("氯吡格雷片", "75mg", "每日1次", "早餐后", 0.9, "支架术后双联抗血小板"),
                 ("美托洛尔缓释片", "95mg", "每日1次", "早餐后", 0.88, ""),
                 ("瑞舒伐他汀钙片", "20mg", "每晚1次", "睡前", 0.9, ""),
                 ("二甲双胍缓释片", "1.0g", "每日2次", "早晚餐后", 0.82, "")],
        "base": {"sbp": 145, "dbp": 80, "glucose": 7.4, "hba1c": 7.4, "ldl": 1.6, "weight": 76.0},
        "trend": {"sbp": -2}, "days": 720, "adherence": 0.9,
        "memories": [("fact", "5年前植入2枚支架，长期双抗"),
                     ("barrier", "散步时偶有胸闷，休息后缓解，未及时报告"),
                     ("preference", "喜欢喝浓茶")],
        "plan": ("冠心病支架术后二级预防", ["LDL-C<1.4 mmol/L", "静息心率55-60次/分",
                                        "血压<130/80 mmHg", "出现胸痛持续15分钟立即120"], 0.88, 3),
    },
    {
        "name": "郑小梅", "gender": "女", "birth_date": "1981-08-09", "phone": "18652097789",
        "city": "宁波市镇海区", "occupation": "小学教师", "height_cm": 165, "weight_kg": 62.0,
        "blood_type": "O型", "allergies": "花粉过敏", "family_history": "父亲高血压",
        "smoking": "不吸烟", "drinking": "不饮酒", "exercise": "每周游泳2次",
        "salt_intake": "清淡", "sleep_quality": "良好，7小时",
        "conditions": [("I10", "高血压", "1级", 1)],
        "meds": [],
        "base": {"sbp": 138, "dbp": 88, "glucose": 5.0, "hba1c": 5.3, "ldl": 2.8, "weight": 62.0},
        "trend": {}, "days": 35, "adherence": 1.0,
        "memories": [("fact", "体检时发现血压偏高，平时没有症状"),
                     ("goal", "希望通过减盐和运动把血压降下来")],
        "plan": ("新发1级高血压生活方式干预", ["限盐<5g/日，DASH饮食", "每周有氧运动150分钟",
                                         "连续记录家庭血压7天"], 0.4, 25),
    },
    {
        "name": "何文斌", "gender": "男", "birth_date": "1993-05-16", "phone": "15052103345",
        "city": "宁波市鄞州区", "occupation": "程序员", "height_cm": 180, "weight_kg": 92.0,
        "blood_type": "A型", "allergies": "无", "family_history": "祖父糖尿病",
        "smoking": "不吸烟", "drinking": "偶尔饮酒", "exercise": "几乎不运动",
        "salt_intake": "偏咸", "sleep_quality": "熬夜，平均5.5小时",
        "conditions": [("R73", "空腹血糖受损", "轻度", 1), ("E66", "肥胖", "BMI 28.4", 2)],
        "meds": [],
        "base": {"sbp": 128, "dbp": 84, "glucose": 6.4, "hba1c": 6.2, "ldl": 3.4, "weight": 92.0},
        "trend": {"weight": 0.8}, "days": 60, "adherence": 1.0,
        "memories": [("barrier", "加班多，常点外卖，没时间运动"),
                     ("goal", "想减重10公斤，避免发展成糖尿病")],
        "plan": ("糖尿病前期体重管理", ["减重5%-10%", "每周150分钟运动",
                                     "减少外卖与含糖饮料"], 0.35, 20),
    },
    {
        "name": "马丽", "gender": "女", "birth_date": "1960-10-11", "phone": "13152119987",
        "city": "宁波市江北区", "occupation": "退休护士", "height_cm": 157, "weight_kg": 64.0,
        "blood_type": "AB型", "allergies": "无", "family_history": "母亲糖尿病",
        "smoking": "不吸烟", "drinking": "不饮酒", "exercise": "每天快走40分钟",
        "salt_intake": "清淡", "sleep_quality": "良好，7小时",
        "conditions": [("E11", "2型糖尿病", "中度", 9), ("N18", "慢性肾脏病", "G3a期", 3)],
        "meds": [("二甲双胍片", "0.5g", "每日2次", "早晚餐后", 0.92, "eGFR<45需评估减量"),
                 ("利格列汀片", "5mg", "每日1次", "早餐前", 0.9, ""),
                 ("阿托伐他汀钙片", "10mg", "每晚1次", "睡前", 0.9, "")],
        "base": {"sbp": 130, "dbp": 78, "glucose": 7.2, "hba1c": 7.3, "ldl": 2.5,
                 "weight": 64.0, "egfr": 52},
        "trend": {}, "days": 500, "adherence": 0.92,
        "memories": [("fact", "自己是退休护士，对指标比较了解"),
                     ("preference", "饮食控制得比较严格，坚持快走"),
                     ("barrier", "担心二甲双胍伤肾，曾自行减量")],
        "plan": ("糖尿病合并CKD G3a期管理", ["糖化<7.5%，避免低血糖",
                                          "每3个月复查eGFR与尿蛋白", "蛋白质0.8g/kg/日"], 0.88, 8),
    },
]


def _gen_metrics(pid, cfg):
    rows = []
    base = cfg["base"]
    days = cfg["days"]
    trend = cfg.get("trend", {})
    step = 2 if days <= 120 else 3

    for i, ago in enumerate(range(days, 0, -step)):
        frac = 1 - ago / max(days, 1)
        tag = datetime.now() - timedelta(days=ago)
        if "sbp" in base:
            sbp = base["sbp"] + trend.get("sbp", 0) * frac + random.gauss(0, 6)
            dbp = base["dbp"] + random.gauss(0, 4)
            sbp, dbp = max(95, min(205, sbp)), max(55, min(120, dbp))
            rows.append((pid, "sbp", round(sbp), None, "mmHg", _d(ago, 7), "home", ""))
            rows.append((pid, "dbp", round(dbp), None, "mmHg", _d(ago, 7), "home", ""))
        if "glucose" in base and i % 2 == 0:
            g = base["glucose"] + trend.get("glucose", 0) * frac + random.gauss(0, 0.7)
            g = max(3.2, min(18, g))
            note = "空腹" if i % 4 == 0 else "餐后2小时"
            rows.append((pid, "glucose", round(g, 1), None, "mmol/L", _d(ago, 8), "home", note))
        if "weight" in base and i % 7 == 0:
            w = base["weight"] + trend.get("weight", 0) * frac + random.gauss(0, 0.4)
            rows.append((pid, "weight", round(w, 1), None, "kg", _d(ago, 7), "home", ""))
        if "spo2" in base and i % 3 == 0:
            sp = base["spo2"] + trend.get("spo2", 0) * frac + random.gauss(0, 1.2)
            rows.append((pid, "spo2", round(min(99, sp)), None, "%", _d(ago, 9), "device", ""))
        if i % 10 == 0:
            rows.append((pid, "heart_rate", round(72 + random.gauss(0, 6)), None, "次/分", _d(ago, 7), "device", ""))

    if "hba1c" in base:
        for k, ago in enumerate(range(days, -1, -90)):
            rows.append((pid, "hba1c", round(base["hba1c"] - 0.05 * k + random.gauss(0, 0.15), 1),
                         None, "%", _d(max(0, ago), 9), "clinic", "静脉血"))
    if "ldl" in base:
        for k, ago in enumerate(range(days, -1, -120)):
            rows.append((pid, "ldl", round(base["ldl"] + random.gauss(0, 0.12), 2),
                         None, "mmol/L", _d(max(0, ago), 9), "clinic", ""))
    if "egfr" in base:
        for k, ago in enumerate(range(days, -1, -100)):
            rows.append((pid, "egfr", round(base["egfr"] - k * 0.4 + random.gauss(0, 2), 1),
                         None, "mL/min", _d(max(0, ago), 9), "clinic", ""))
    return rows


def _gen_alerts(pid, metrics):
    """根据最近异常值生成预警。"""
    latest = {}
    for m in metrics:
        latest[m[1]] = m[2]
    alerts = []
    sbp = latest.get("sbp")
    if sbp and sbp >= 160:
        alerts.append((pid, "high", "血压", f"血压升高至 {sbp} mmHg",
                       f"最近一次家庭血压收缩压 {sbp} mmHg，连续偏高，建议 3 天内复测并联系医生。", "open"))
    elif sbp and sbp >= 150:
        alerts.append((pid, "medium", "血压", f"血压未达标（{sbp} mmHg）",
                       "近期血压高于目标值，建议复核服药依从性与限盐执行情况。", "open"))
    g = latest.get("glucose")
    if g and g >= 11.1:
        alerts.append((pid, "high", "血糖", f"血糖显著升高 {g} mmol/L",
                       "餐后血糖明显升高，需评估饮食结构与用药方案。", "open"))
    elif g and g < 3.9:
        alerts.append((pid, "critical", "血糖", f"低血糖 {g} mmol/L",
                       "出现低血糖记录，需立即处理并排查降糖方案。", "open"))
    sp = latest.get("spo2")
    if sp and sp < 92:
        alerts.append((pid, "high", "血氧", f"血氧偏低 {sp}%",
                       "家庭血氧低于 92%，注意慢阻肺急性加重风险。", "open"))
    if not alerts:
        alerts.append((pid, "medium", "随访", "常规随访待完成",
                       "本季度随访任务尚未完成，请安排电话或门诊随访。", "open"))
    return alerts


def _seed_devices():
    """演示用设备台账与近 3 天设备体征（体现设备自动采集与个性化成熟度提升）。"""
    import random
    from backend.services import device_ingest
    from backend.services.personalization import METRIC_META

    specs = [
        {"sn": "MB-BP-1001", "name": "客厅血压计", "model": "OMRON HEM-7361T", "vendor": "欧姆龙",
         "pid": 1, "battery": 86, "signal": -58,
         "metrics": ["sbp", "dbp", "heart_rate", "hrv", "spo2", "temp"],
         "base": {"sbp": 152, "dbp": 96, "heart_rate": 78, "hrv": 26, "spo2": 97, "temp": 36.5}},
        {"sn": "MB-WR-2002", "name": "家庭智能手环", "model": "HUAWEI Band 9", "vendor": "华为",
         "pid": 2, "battery": 64, "signal": -71, "metrics": ["heart_rate", "spo2", "hrv", "temp"],
         "base": {"heart_rate": 82, "spo2": 96, "hrv": 22, "temp": 36.6}},
        {"sn": "MB-OX-5005", "name": "卧室指夹血氧仪", "model": "Yuwell YX306", "vendor": "鱼跃",
         "pid": 1, "battery": 72, "signal": -63, "metrics": ["spo2", "heart_rate", "resp_rate"],
         "base": {"spo2": 97, "heart_rate": 76, "resp_rate": 17}},
        {"sn": "MB-TM-6006", "name": "红外体温计", "model": "BRAUN BNT400", "vendor": "博朗",
         "pid": 1, "battery": 88, "signal": -70, "metrics": ["temp"],
         "base": {"temp": 36.4}},
        {"sn": "MB-OX-3003", "name": "家庭指夹血氧仪", "model": "Yuwell YX306", "vendor": "鱼跃",
         "pid": 4, "battery": 41, "signal": -66, "metrics": ["spo2", "heart_rate", "resp_rate"],
         "base": {"spo2": 92, "heart_rate": 88, "resp_rate": 21}},
        {"sn": "MB-TH-4004", "name": "备用体温计", "model": "Midea MT-502", "vendor": "美的",
         "pid": None, "battery": 95, "signal": -80, "metrics": ["temp"],
         "base": {"temp": 36.5}},
    ]
    for d in specs:
        did = db.execute(
            "INSERT INTO devices(device_sn,name,model,vendor,patient_id,status,battery,signal,"
            "firmware,last_seen,bound_at,reading_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (d["sn"], d["name"], d["model"], d["vendor"], d["pid"],
             "online" if d["pid"] else "offline", d["battery"], d["signal"], "v1.4.2",
             db.now() if d["pid"] else _d(2, 15), _d(30, 10) if d["pid"] else None, 0),
        )
        if not d["pid"]:
            continue
        rows, raws, count = [], [], 0
        for hours_ago in range(72, -1, -6):
            at = (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")
            vitals = {}
            for m in d["metrics"]:
                v = d["base"][m] + random.gauss(0, 1.6 if m != "hrv" else 4)
                if m == "temp":
                    v = round(max(36.0, min(37.4, v)), 1)
                elif m == "hrv":
                    v = round(max(12, v))
                elif m == "resp_rate":
                    v = round(max(10, min(30, v)))
                elif m == "spo2":
                    v = round(max(88, min(100, v)))
                elif m == "heart_rate":
                    v = round(max(50, min(120, v)))
                else:
                    v = round(max(70, v))
                vitals[m] = v
            for m, v in vitals.items():
                rows.append((d["pid"], m, v, None, METRIC_META[m]["unit"],
                             at, "device", "", d["sn"], "ok"))
                count += 1
            if hours_ago <= 12:
                raws.append((d["sn"], d["pid"], f"medbuddy/{d['sn']}/vitals",
                             json.dumps({"device_sn": d["sn"], "patient_id": d["pid"],
                                         "ts": at, "vitals": vitals}, ensure_ascii=False),
                             len(vitals), device_ingest.fmt_vitals(vitals), "ok", "", at))
        db.executemany(
            "INSERT OR IGNORE INTO metrics(patient_id,metric_type,value,value2,unit,measured_at,"
            "source,note,device_sn,quality) VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        db.executemany(
            "INSERT INTO device_readings(device_sn,patient_id,topic,payload,metric_count,summary,"
            "status,error,received_at) VALUES(?,?,?,?,?,?,?,?,?)", raws)
        db.execute("UPDATE devices SET reading_count=? WHERE id=?", (len(raws), did))
        db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
                   (d["sn"], "connect", "MQTT 已连接，订阅 medbuddy/+/vitals"))
    device_ingest.rebuild_daily()


def seed_if_empty():
    if db.query("SELECT COUNT(*) c FROM patients", one=True)["c"] > 0:
        return False

    # 账号
    db.execute("INSERT INTO users(username,password,role,display_name,title,phone,patient_id,theme,status) "
               "VALUES('doctor','doctor123','doctor','江先亮','社区慢病管理医师','13800000001',NULL,'orangeblue','active')")
    db.execute("INSERT INTO users(username,password,role,display_name,title,phone,patient_id,theme,status) "
               "VALUES('admin','admin123','admin','系统管理员','平台运维','13800000002',NULL,'graphite','active')")
    db.execute("INSERT INTO users(username,password,role,display_name,title,phone,patient_id,theme,status) "
               "VALUES('patient','patient123','patient','陈建国','签约居民','13852002043',1,'green','active')")
    # 已停用的患者账号，用于演示用户管理中的启停与重置密码
    db.execute("INSERT INTO users(username,password,role,display_name,title,phone,patient_id,theme,status) "
               "VALUES('zhangguiying','123456','patient','张桂英','签约居民','13552033321',4,'blue','disabled')")

    # 知识库
    for doc in KB_DOCS:
        from backend.services import rag
        rag.ingest_document(doc["title"], doc["content"], doc["category"], doc["doc_type"],
                            doc["source"], doc["version"])

    colors = ["#0d9488", "#2563eb", "#ea580c", "#7c3aed", "#db2777", "#0891b2",
              "#65a30d", "#c2410c", "#4f46e5", "#0f766e", "#b45309", "#9333ea"]

    for idx, p in enumerate(PATIENTS):
        enrolled = (datetime.now() - timedelta(days=p["days"])).strftime("%Y-%m-%d")
        pid = db.execute(
            """INSERT INTO patients(name,gender,birth_date,phone,city,occupation,height_cm,weight_kg,
               blood_type,allergies,family_history,smoking,drinking,exercise,salt_intake,sleep_quality,
               doctor_id,enrolled_at,avatar_color,note)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
            (p["name"], p["gender"], p["birth_date"], p["phone"], p["city"], p["occupation"],
             p["height_cm"], p["weight_kg"], p["blood_type"], p["allergies"], p["family_history"],
             p["smoking"], p["drinking"], p["exercise"], p["salt_intake"], p["sleep_quality"],
             enrolled, colors[idx % len(colors)], ""),
        )
        for icd, name, sev, years in p["conditions"]:
            db.execute(
                "INSERT INTO conditions(patient_id,icd_code,name,severity,diagnosed_at,status,target_json) "
                "VALUES(?,?,?,?,?,'active','{}')",
                (pid, icd, name, sev,
                 (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")),
            )
        for drug, dose, freq, timing, adh, note in p["meds"]:
            db.execute(
                "INSERT INTO medications(patient_id,drug_name,dosage,frequency,timing,start_date,"
                "adherence,notes) VALUES(?,?,?,?,?,?,?,?)",
                (pid, drug, dose, freq, timing,
                 (datetime.now() - timedelta(days=min(p["days"], 365))).strftime("%Y-%m-%d"),
                 adh, note),
            )
        rows = _gen_metrics(pid, p)
        db.executemany(
            "INSERT INTO metrics(patient_id,metric_type,value,value2,unit,measured_at,source,note) "
            "VALUES(?,?,?,?,?,?,?,?)", rows)
        for a in _gen_alerts(pid, rows):
            db.execute("INSERT INTO alerts(patient_id,level,type,title,detail,status) VALUES(?,?,?,?,?,?)", a)
        for kind, content in p["memories"]:
            db.execute(
                "INSERT INTO memories(patient_id,kind,content,confidence,weight,source) VALUES(?,?,?,?,?,?)",
                (pid, kind, content, 0.8, 1.0, "seed"))
        title, goals, adh, next_days = p["plan"]
        db.execute(
            """INSERT INTO care_plans(patient_id,title,goals_json,start_date,end_date,status,adherence,
               next_visit,created_by) VALUES(?,?,?,?,?,'active',?,?,'江先亮')""",
            (pid, title, json.dumps(goals, ensure_ascii=False), enrolled,
             (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d"), adh,
             (datetime.now() + timedelta(days=next_days)).strftime("%Y-%m-%d")),
        )

    # 演示设备台账与近 3 天设备体征（先入库，风险分层才能用上设备体征）
    _seed_devices()

    # 重新计算每位患者的风险分层并写回
    from backend.services import agent
    for p in db.query("SELECT id FROM patients"):
        agent.refresh_risk(p["id"])

    # 演示会话（陈建国，含历史，体现"越用越懂"）
    cid = db.execute(
        "INSERT INTO conversations(patient_id,user_id,title,created_at,updated_at) VALUES(1,1,?,?,?)",
        ("最近血糖和用药咨询", _d(8, 20), _d(8, 20)))
    db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",
               (cid, "user", "最近晚上老是忘记吃二甲双胍，血糖是不是因为这个才高？"))
    db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",
               (cid, "assistant",
                "您近 7 天平均空腹血糖 8.1 mmol/L，确实高于 4.4–7.0 mmol/L 的目标区间。"
                "二甲双胍缓释片建议随晚餐服用，如果经常漏服，可以和医生讨论把晚间剂量合并到早餐后，"
                "但不要自行加倍补服。可以先连续记录 5 天晚餐后血糖，复诊时带给医生看。"))
    db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",
               (cid, "user", "我早上血压也高，是不是要加药？"))
    db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",
               (cid, "assistant",
                "您近 7 天平均血压 152/94 mmHg，目标为 130/80 mmHg，仍未达标。是否加药需要医生结合"
                "家庭血压记录、心率与肾功能判断，不建议自行加量。请先做到每天早晚各测一次并记录，"
                "同时把腌菜、咸鱼换成新鲜蔬菜，两周后复诊评估。"))
    db.execute("UPDATE conversations SET summary=? WHERE id=?",
               ("患者此前咨询漏服二甲双胍与晨间血压偏高，已建议记录血糖血压、限盐并复诊评估用药。", cid))
    return True
