"""全局配置。"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
KB_DIR = os.path.join(DATA_DIR, "kb")
DB_PATH = os.path.join(DATA_DIR, "medbuddy.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 饮食照片上传限制
MAX_UPLOAD_MB = 8

SECRET_KEY = "medbuddy-local-demo-secret"

# 默认智能体配置（首次启动写入 settings 表）
DEFAULT_AGENT_CONFIG = {
    "provider": "builtin",              # builtin | openai_compatible | ollama
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "",
    "model": "Qwen/Qwen3-8B",
    "embedding_model": "",              # 留空则使用本地 n-gram 向量
    "temperature": 0.4,
    "max_tokens": 900,
    "top_k": 4,
    "enable_safety": "1",
    "system_prompt": (
        "你是社区慢病管理平台的家庭智能助手，服务于基层医生与签约居民。"
        "必须基于提供的【患者档案】【指标数据】【知识库证据】回答，不得编造数值或指南条文。"
        "回答使用简体中文，结构清晰：先给结论，再给依据与可执行步骤，最后提示需要就医的情形。"
        "不进行疾病诊断，不调整处方剂量，涉及用药变更一律建议由签约医生评估。"
    ),
}

# 默认 MQTT 接入配置（写入 settings 表，可在「平台配置 · 设备接入」修改）
DEFAULT_MQTT_CONFIG = {
    "enabled": "0",                       # 1 启动网关，0 关闭
    "host": "127.0.0.1",
    "port": 1883,
    "client_id": "medbuddy-gateway",
    "username": "",
    "password": "",
    "tls": "0",                           # 1 启用 TLS（自签证书不校验）
    "qos": 1,
    "topic": "medbuddy/+/vitals",         # + 位置为设备序列号
    "payload_format": "json",             # json | csv
    "auto_register": "1",                 # 未登记设备自动建档
    "retention_days": 30,                 # 原始报文保留天数
    "dedupe_seconds": 2,                  # 同设备同指标去重窗口
}

# 网关支持的体征指标（MQTT / 手工录入共用）
VITAL_KEYS = ("sbp", "dbp", "heart_rate", "spo2", "temp", "hrv", "resp_rate")

PRESET_THEMES = [
    {"id": "orange", "name": "橙色", "primary": "#ea580c", "primaryDark": "#c2410c",
     "primaryLight": "#ffedd5", "accent": "#9a3412", "dual": False},
    {"id": "orangeblue", "name": "橙蓝", "primary": "#ea580c", "primaryDark": "#c2410c",
     "primaryLight": "#ffedd5", "accent": "#1d4ed8", "accentSoft": "#dbeafe", "dual": True},
    {"id": "blue", "name": "蓝色", "primary": "#2563eb", "primaryDark": "#1d4ed8",
     "primaryLight": "#dbeafe", "accent": "#1e3a8a", "dual": False},
    {"id": "green", "name": "绿色", "primary": "#16a34a", "primaryDark": "#15803d",
     "primaryLight": "#dcfce7", "accent": "#14532d", "dual": False},
    {"id": "graphite", "name": "黑灰", "primary": "#334155", "primaryDark": "#0f172a",
     "primaryLight": "#e2e8f0", "accent": "#09090b", "dual": False},
]

ROLE_META = {
    "admin": {"name": "管理员", "desc": "平台配置、用户管理、医疗知识与首页概览"},
    "doctor": {"name": "医生", "desc": "患者管理、智能助手与医疗知识"},
    "patient": {"name": "患者", "desc": "本人档案、设备接入、饮食拍照、智能助手与专家会诊"},
}

LEGACY_THEME_MAP = {"mint": "green", "ocean": "blue", "amber": "orange",
                    "violet": "blue", "sunset": "orange"}
