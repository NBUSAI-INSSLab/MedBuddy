# MedBuddy · 社区慢病管理平台

面向社区医疗点的慢病管理平台：以 **Flask + Vue 3** 为骨架，内置 **本地知识库检索增强（RAG）智能体**、**MQTT 体征设备接入**、**饮食照片自动分析** 与 **多专家数字人会诊**，为每位居民提供随历史数据积累而逐步个性化的健康服务。

![Python](https://img.shields.io/badge/Python-3.11+-3b6ea5)
![Flask](https://img.shields.io/badge/Flask-3.x-0f766e)
![Vue](https://img.shields.io/badge/Vue-3-42b883)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 一、角色与功能

平台按 **管理员 / 医生 / 患者** 三种角色划分工作台，登录后自动进入对应首页。

| 模块 | 管理员 | 医生 | 患者 |
| --- | :-: | :-: | :-: |
| 首页概览 | ✓ | ✓ | ✓ |
| 患者档案（全景档案 / 指标 / 预警 / 饮食） | ✓ | ✓ | — |
| 医疗知识（本地知识库） | ✓ | — | — |
| 用户管理 | ✓ | — | — |
| 专家管理（专家 · 专家团 · 知识库 / 技能 / MCP 配置） | ✓ | — | — |
| 平台配置（智能体 · 设备接入 · 主题） | ✓ | — | — |
| 我的健康（指标 / 预警 / 饮食打卡） | — | — | ✓ |
| 专家会诊 | — | — | ✓ |
| 顶栏主题切换 | ✓ | ✓ | ✓ |

- **患者端**：只看自己的健康数据；每日拍照上传饮食照片，由本地算法自动识别餐盘构成并给出病种化建议；可就慢病问题召唤单专家咨询或提交专家团会诊。
- **医生端**：管理签约居民档案、体征趋势、预警处置与饮食记录，无系统级配置权限。
- **管理员端**：维护用户、知识库、专家资源与平台参数。

## 二、核心能力

### 1. 本地知识库 + 智能体

- 知识库文档入库后切分为片段，建立 **BM25 + 字符 n-gram 向量** 的混合检索索引，完全本地运行，无需外部向量库。
- 智能体链路：`意图识别 → 安全门禁 → 患者上下文注入 → 混合检索 → SSE 流式生成 → 后置校验 → 记忆回写`。
- 支持三种模型来源：内置离线规则引擎（默认，零依赖）、OpenAI 兼容接口（如 SiliconFlow / DeepSeek）、本地 Ollama。API Key 在「平台配置 · 智能体」中填写，不落盘到代码。
- 患者上下文包含档案、近期指标、预警、饮食记录与历史对话摘要，历史数据越多，检索与回答越贴合本人。

### 2. MQTT 体征设备接入

- 网关线程订阅 `medbuddy/+/vitals`，`+` 为设备序列号；支持 JSON / CSV 报文、QoS、TLS、去重窗口与原始报文保留天数。
- 指标覆盖 **收缩压 / 舒张压 / 心率 / 血氧 / 体温 / 心率变异性 / 呼吸频率**。
- 未登记设备可开启自动建档；写入时同步刷新日聚合表 `metric_daily` 并触发阈值预警。
- 患者维度隔离：患者只能查看与操作本人设备，医护人员可跨患者管理。

报文示例：

```bash
mosquitto_pub -h 127.0.0.1 -p 1883 -t medbuddy/MB-BP-1001/vitals \
  -m '{"sbp":128,"dbp":82,"heart_rate":74,"spo2":97,"temp":36.5,"hrv":42}'
```

### 3. 饮食照片分析（纯本地，无需视觉模型）

基于 Pillow 与 HSV 色彩统计，无需上传到任何云端：

- 以桌面参考色定位餐盘外圈，剔除高亮低饱和中性色（白瓷盘）、暗部阴影与边缘干扰，完成盘内区域分割；
- 按色相与饱和度分类 **蔬菜 / 主食 / 蛋白 / 油脂酱汁** 四类占比，结合密度与铺满度估算热量与钠含量；
- 输出结构评分、分级、发现项与按病种（高血压 / 糖尿病 / 高血脂等）定制的建议，并附置信度；
- 用户填写的文字描述与视觉结果按 6:4 融合，结果随记录持久化。

### 4. 多专家数字人会诊

- 专家由管理员创建，可配置 **人设与专科、从业年限、知识库文档范围、技能清单、外部工具（MCP）**；
- 专家团按成员顺序发言，后序专家继承前序意见，形成多视角讨论；
- 会诊采用 SSE 逐字流式推送（`speaker` / `delta` 事件），安全门禁命中时由首位专家优先输出急救指引；
- 每位专家仅检索被授权的知识库文档，技能与工具会写入系统提示词并展示在会话元信息中。

### 5. 主题与体验

- 内置 5 套主题（橙 / 橙蓝 / 蓝 / 绿 / 黑灰）与自定义主色，登录页与工作台即时生效；
- 纯前端主题变量注入，无需构建，刷新后保持；
- 顶栏提供主题选择浮层，医生与管理员可直接切换。

## 三、技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3.11+ / Flask 3.x，应用工厂 + 蓝图，统一挂载 `/api` |
| 数据库 | SQLite（WAL 模式、行工厂、standalone 连接管理），自动迁移补列 |
| 前端 | Vue 3（本地 `vue.global.prod.js`，无构建步骤）+ 原生 CSS 变量主题 |
| 检索 | jieba 分词 + BM25 + 字符 n-gram 余弦相似度混合排序 |
| 设备 | paho-mqtt 网关线程，MQTT 3.1.1 |
| 图像 | Pillow + NumPy（HSV 分割与色彩统计） |
| 文档 | pypdf 解析 PDF，纯文本 / Markdown 直接入库 |

## 四、目录结构

```
MedBuddy/
├── app.py                    # Flask 入口：应用工厂、蓝图注册、静态资源回退
├── config.py                 # 全局配置：默认模型/主题/MQTT/体征指标
├── backend/
│   ├── db.py                 # 建表、迁移、连接管理、日聚合
│   ├── seed.py               # 演示数据（12 位居民 / 指标 / 预警 / 会话）
│   ├── api/                  # auth patients dashboard chat kb settings devices users
│   │                         # diet expert expert_admin
│   └── services/             # rag / agent / safety / mqtt_gateway / device_ingest
│                             # experts / expert_meta / diet_vision / guidelines
├── frontend/
│   ├── index.html
│   ├── css/app.css           # 主题变量、布局、各页面样式
│   ├── js/app.js             # 路由、导航、登录注册、主题切换
│   ├── js/pages.*.js         # 各页面视图（overview/patients/chat/kb/settings/
│   │                         # devices/users/diet/portal/expert/experts_admin）
│   └── assets/vue.global.prod.js
├── tests/                    # 95 项接口与集成测试
├── tools/render_check.js     # jsdom 渲染校验（无头环境下的页面自检）
├── docs/调研与设计方案.md      # 方案设计与调研记录
└── data/                     # 运行时生成：数据库、知识库、上传照片
```

## 五、快速开始

```bash
git clone https://github.com/NBUSAI-INSSLab/MedBuddy.git
cd MedBuddy

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
python app.py
```

打开 <http://127.0.0.1:5000>。首次启动会自动建库、写入演示数据、播种内置知识库与专家，并打印知识库索引片段数。

### 演示账号

| 角色 | 账号 | 密码 | 说明 |
| --- | --- | --- | --- |
| 医生 | `doctor` | `doctor123` | 签约医生，可管理全部居民 |
| 患者 | `patient` | `patient123` | 居民视角，含指标、饮食、会诊 |
| 管理员 | `admin` | `admin123` | 全局配置与专家管理 |
| 患者 | `zhangguiying` | `123456` | 演示患者（默认停用，可在用户管理中启用） |

### 测试

```bash
python -m unittest discover -s tests -v
node tools/render_check.js            # 页面渲染自检（需 npm i jsdom）
node tools/render_check.js theme      # 主题切换场景
node tools/render_check.js experts-form
```

## 六、接口概览

所有接口统一以 `/api` 为前缀，采用会话 Cookie 鉴权。

| 分组 | 主要端点 |
| --- | --- |
| 认证 | `POST /api/auth/login` `/register` `/logout`，`GET /api/auth/me` |
| 患者 | `GET/POST /api/patients`，全景档案、指标、预警处置、饮食、记忆、管理方案 |
| 概览 | `GET /api/dashboard/overview` |
| 智能体 | `POST /api/chat/stream`（SSE），`/api/conversations` 会话 CRUD |
| 知识库 | `/api/kb/documents` 增删查，`/api/kb/search`，`/api/kb/rebuild`，`/api/kb/stats` |
| 设备 | `/api/devices` CRUD，`/api/devices/<id>/readings` 读数，`/api/device-readings` 明细 |
| 饮食（患者） | `POST /api/my/diet/photo` 照片分析，`GET /api/my/diet` 打卡记录 |
| 专家 | `GET /api/expert/roster`，会话 CRUD，`POST /api/expert/sessions/<id>/stream` |
| 专家管理 | `/api/admin/experts`、`/api/admin/expert-teams` 全套 CRUD 与 `/status`（仅管理员） |
| 用户管理 | `/api/users` 全套（仅管理员） |
| 平台配置 | `/api/settings/agent`、`/api/settings/mqtt`（含 `/test` `/restart` `/status`）、`PUT /api/auth/theme` |

## 七、安全与合规

- 默认仅监听 `127.0.0.1`，部署到内网时请置于反向代理之后并更换 `SECRET_KEY`；
- 所有写操作按角色校验，患者数据按 `patient_id` 隔离；
- 智能体不做疾病诊断、不调整处方剂量，涉及用药变更一律建议由签约医生评估；
- 演示数据为虚构内容，不含真实个人健康信息。

## 八、License

[MIT](LICENSE) © 2026 智能网络与感知系统实验室
