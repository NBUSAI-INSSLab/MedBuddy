"""SQLite 数据访问层：建表、连接管理、通用查询。"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from flask import g

import config

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL,                -- doctor | patient | admin
    display_name TEXT NOT NULL,
    title TEXT,
    phone TEXT,
    patient_id INTEGER,
    theme TEXT DEFAULT 'green',
    status TEXT DEFAULT 'active',      -- active | disabled
    last_login_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    gender TEXT,
    birth_date TEXT,
    phone TEXT,
    city TEXT,
    occupation TEXT,
    height_cm REAL,
    weight_kg REAL,
    blood_type TEXT,
    allergies TEXT,
    family_history TEXT,
    smoking TEXT,
    drinking TEXT,
    exercise TEXT,
    salt_intake TEXT,
    sleep_quality TEXT,
    risk_level TEXT DEFAULT 'low',      -- critical | high | medium | low
    risk_score REAL DEFAULT 0,
    doctor_id INTEGER,
    enrolled_at TEXT,
    avatar_color TEXT,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    icd_code TEXT,
    name TEXT NOT NULL,
    severity TEXT,
    diagnosed_at TEXT,
    status TEXT DEFAULT 'active',
    target_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_cond_pid ON conditions(patient_id);

CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    drug_name TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    timing TEXT,
    start_date TEXT,
    end_date TEXT,
    adherence REAL DEFAULT 0.8,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_med_pid ON medications(patient_id);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    metric_type TEXT NOT NULL,
    value REAL NOT NULL,
    value2 REAL,
    unit TEXT,
    measured_at TEXT NOT NULL,
    source TEXT DEFAULT 'home',
    note TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_metric_pid ON metrics(patient_id, metric_type, measured_at);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    level TEXT NOT NULL,               -- critical | high | medium
    type TEXT,
    title TEXT,
    detail TEXT,
    status TEXT DEFAULT 'open',        -- open | handled
    created_at TEXT DEFAULT (datetime('now','localtime')),
    handled_at TEXT,
    handled_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_pid ON alerts(patient_id, status);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    user_id INTEGER,
    title TEXT,
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_conv_pid ON conversations(patient_id);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,                -- user | assistant | system
    content TEXT NOT NULL,
    citations_json TEXT,
    meta_json TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_msg_cid ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    kind TEXT NOT NULL,                -- fact | preference | barrier | goal
    content TEXT NOT NULL,
    confidence REAL DEFAULT 0.7,
    weight REAL DEFAULT 1.0,
    source TEXT,
    use_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_pid ON memories(patient_id);

CREATE TABLE IF NOT EXISTS care_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    goals_json TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'active',
    adherence REAL DEFAULT 0,
    next_visit TEXT,
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS kb_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,
    doc_type TEXT,
    source TEXT,
    version TEXT,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ready',
    content TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    idx INTEGER,
    heading TEXT,
    content TEXT NOT NULL,
    tokens INTEGER,
    vector_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunk_doc ON kb_chunks(doc_id);

CREATE TABLE IF NOT EXISTS kb_query_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    query TEXT,
    hits_json TEXT,
    top_score REAL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    actor TEXT,
    action TEXT,
    target TEXT,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------------- 设备接入（MQTT） ----------------
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_sn TEXT UNIQUE NOT NULL,
    name TEXT,
    model TEXT,
    vendor TEXT,
    patient_id INTEGER,
    status TEXT DEFAULT 'offline',      -- online | offline | error
    battery REAL,
    signal REAL,
    firmware TEXT,
    last_seen TEXT,
    last_topic TEXT,
    reading_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    bound_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_device_patient ON devices(patient_id);
CREATE INDEX IF NOT EXISTS idx_device_status ON devices(status, last_seen);

-- 原始报文（可追溯、可重放、按保留天数清理）
CREATE TABLE IF NOT EXISTS device_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_sn TEXT NOT NULL,
    patient_id INTEGER,
    topic TEXT,
    payload TEXT,
    metric_count INTEGER DEFAULT 0,
    summary TEXT,                       -- 已入库体征的可读摘要
    status TEXT DEFAULT 'ok',           -- ok | ignored | invalid
    error TEXT,
    received_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reading_device ON device_readings(device_sn, received_at);
CREATE INDEX IF NOT EXISTS idx_reading_time ON device_readings(received_at);

CREATE TABLE IF NOT EXISTS device_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_sn TEXT,
    event TEXT,                          -- connect | disconnect | ingest | bind | error
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_dev_event_time ON device_events(created_at);

-- 日聚合：低频查询（30/90 天趋势、概览活跃度）不再扫明细表
CREATE TABLE IF NOT EXISTS metric_daily (
    patient_id INTEGER NOT NULL,
    metric_type TEXT NOT NULL,
    day TEXT NOT NULL,
    avg_value REAL,
    min_value REAL,
    max_value REAL,
    last_value REAL,
    cnt INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (patient_id, metric_type, day)
);

-- ---------------- 饮食管理 ----------------
CREATE TABLE IF NOT EXISTS diet_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    log_date TEXT NOT NULL,             -- YYYY-MM-DD
    meal TEXT NOT NULL,                 -- breakfast | lunch | dinner | snack
    foods TEXT NOT NULL,
    calories REAL,                      -- 估算或手填 kcal
    sodium REAL,                        -- 估算或手填 mg
    note TEXT,
    source TEXT DEFAULT 'manual',       -- manual | photo
    image_path TEXT,                    -- 相对 UPLOAD_DIR 的照片路径
    analysis TEXT,                      -- 照片分析结果 JSON
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_diet_pid_date ON diet_logs(patient_id, log_date);
CREATE INDEX IF NOT EXISTS idx_diet_date ON diet_logs(log_date);

-- ---------------- 数字人专家与专家团（管理员可配置） ----------------
CREATE TABLE IF NOT EXISTS expert_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,          -- 会诊对象的稳定标识
    name TEXT NOT NULL,
    initials TEXT,
    title TEXT,
    dept TEXT,
    org TEXT,
    role_key TEXT DEFAULT 'gp',         -- 离线作答的专科模板
    years INTEGER DEFAULT 10,
    cases TEXT,
    tags TEXT,                          -- JSON 数组
    intro TEXT,
    style TEXT,
    greeting TEXT,
    questions TEXT,                     -- JSON 数组
    color TEXT DEFAULT '#0f766e',
    color2 TEXT DEFAULT '#0d9488',
    skills TEXT,                        -- JSON 数组，技能 key
    kb_doc_ids TEXT,                    -- JSON 数组，绑定的知识库文档
    mcp_tools TEXT,                     -- JSON 数组 [{key,name,desc,builtin}]
    status TEXT DEFAULT 'active',       -- active | paused
    sort INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_expert_profile_status ON expert_profiles(status, sort);

CREATE TABLE IF NOT EXISTS expert_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    desc TEXT,
    tags TEXT,
    scenario TEXT,
    member_codes TEXT,                  -- JSON 数组，成员专家 code，按发言顺序
    skills TEXT,
    kb_doc_ids TEXT,
    mcp_tools TEXT,
    status TEXT DEFAULT 'active',
    sort INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_expert_team_status ON expert_teams(status, sort);

-- ---------------- 专家会诊 ----------------
CREATE TABLE IF NOT EXISTS expert_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    user_id INTEGER,
    target_type TEXT NOT NULL,          -- expert | team
    target_id TEXT NOT NULL,
    title TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_expert_sess_pid ON expert_sessions(patient_id, updated_at);

CREATE TABLE IF NOT EXISTS expert_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,                 -- user | expert
    speaker_id TEXT,
    speaker_name TEXT,
    speaker_title TEXT,
    content TEXT NOT NULL,
    meta_json TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_expert_msg_sid ON expert_messages(session_id);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """轻量迁移：为已存在的库补齐新列，避免删库重建。"""
    ucols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    for name, ddl in (
        ("phone", "ALTER TABLE users ADD COLUMN phone TEXT"),
        ("status", "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'"),
        ("last_login_at", "ALTER TABLE users ADD COLUMN last_login_at TEXT"),
    ):
        if name not in ucols:
            conn.execute(ddl)
    conn.execute("UPDATE users SET status='active' WHERE status IS NULL OR status=''")
    # 旧主题 ID 迁移到新配色方案
    for old, new in config.LEGACY_THEME_MAP.items():
        conn.execute("UPDATE users SET theme=? WHERE theme=?", (new, old))
    conn.execute("UPDATE users SET theme='green' WHERE theme IS NULL OR theme=''")

    rcols = {r[1] for r in conn.execute("PRAGMA table_info(device_readings)")}
    if "summary" not in rcols:
        conn.execute("ALTER TABLE device_readings ADD COLUMN summary TEXT")

    dcols = {r[1] for r in conn.execute("PRAGMA table_info(diet_logs)")}
    for name, ddl in (
        ("source", "ALTER TABLE diet_logs ADD COLUMN source TEXT DEFAULT 'manual'"),
        ("image_path", "ALTER TABLE diet_logs ADD COLUMN image_path TEXT"),
        ("analysis", "ALTER TABLE diet_logs ADD COLUMN analysis TEXT"),
    ):
        if name not in dcols:
            conn.execute(ddl)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(metrics)")}
    for name, ddl in (
        ("device_sn", "ALTER TABLE metrics ADD COLUMN device_sn TEXT"),
        ("quality", "ALTER TABLE metrics ADD COLUMN quality TEXT DEFAULT 'ok'"),
    ):
        if name not in cols:
            conn.execute(ddl)
    conn.executescript(
        "CREATE INDEX IF NOT EXISTS idx_metrics_pid_time ON metrics(patient_id, measured_at);"
        "CREATE INDEX IF NOT EXISTS idx_metrics_type_time ON metrics(metric_type, measured_at);"
        "CREATE INDEX IF NOT EXISTS idx_metrics_source ON metrics(source, measured_at);"
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_metric_device "
        "  ON metrics(device_sn, metric_type, measured_at) WHERE device_sn IS NOT NULL;"
        "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role, status);"
    )
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_patient "
            "ON users(patient_id) WHERE patient_id IS NOT NULL"
        )
    except sqlite3.IntegrityError:
        # 历史数据里同一档案绑定了多个账号时跳过，由用户管理页手工整理
        pass


@contextmanager
def standalone():
    """后台线程（MQTT 网关）使用的独立连接，不依赖 Flask 应用上下文。"""
    conn = sqlite3.connect(config.DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    rid = cur.lastrowid
    cur.close()
    return rid


def executemany(sql, seq):
    db = get_db()
    db.executemany(sql, seq)
    db.commit()


def get_setting(key, default=None):
    row = query("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row["value"] if row else default


def set_setting(key, value):
    execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_agent_config():
    raw = get_setting("agent_config")
    cfg = dict(config.DEFAULT_AGENT_CONFIG)
    if raw:
        try:
            cfg.update(json.loads(raw))
        except Exception:
            pass
    return cfg


def save_agent_config(cfg: dict):
    set_setting("agent_config", json.dumps(cfg, ensure_ascii=False))


def get_mqtt_config():
    raw = get_setting("mqtt_config")
    cfg = dict(config.DEFAULT_MQTT_CONFIG)
    if raw:
        try:
            cfg.update(json.loads(raw))
        except Exception:
            pass
    return cfg


def save_mqtt_config(cfg: dict):
    set_setting("mqtt_config", json.dumps(cfg, ensure_ascii=False))


def refresh_daily(patient_id, metric_type, day, conn=None):
    """重算某患者某指标某天的日聚合（单日数据量小，代价可控）。"""
    if conn is not None:
        _refresh_daily_on(conn, patient_id, metric_type, day)
        return
    with standalone() as c:
        _refresh_daily_on(c, patient_id, metric_type, day)


def _refresh_daily_on(conn, patient_id, metric_type, day):
    row = conn.execute(
        "SELECT AVG(value) a, MIN(value) mn, MAX(value) mx, COUNT(*) c, "
        "(SELECT value FROM metrics WHERE patient_id=? AND metric_type=? "
        " AND substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1) last "
        "FROM metrics WHERE patient_id=? AND metric_type=? AND substr(measured_at,1,10)=?",
        (patient_id, metric_type, day, patient_id, metric_type, day),
    ).fetchone()
    if not row or not row["c"]:
        conn.execute("DELETE FROM metric_daily WHERE patient_id=? AND metric_type=? AND day=?",
                     (patient_id, metric_type, day))
        return
    conn.execute(
        "INSERT INTO metric_daily(patient_id,metric_type,day,avg_value,min_value,max_value,"
        "last_value,cnt,updated_at) VALUES(?,?,?,?,?,?,?,?,datetime('now','localtime')) "
        "ON CONFLICT(patient_id,metric_type,day) DO UPDATE SET avg_value=excluded.avg_value,"
        "min_value=excluded.min_value,max_value=excluded.max_value,"
        "last_value=excluded.last_value,cnt=excluded.cnt,updated_at=excluded.updated_at",
        (patient_id, metric_type, day, round(row["a"], 3), row["mn"], row["mx"],
         row["last"], row["c"]),
    )


def audit(actor, action, target="", detail="", user_id=None):
    try:
        execute(
            "INSERT INTO audit_log(user_id,actor,action,target,detail) VALUES(?,?,?,?,?)",
            (user_id, actor, action, target, detail[:2000]),
        )
    except Exception:
        pass


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
