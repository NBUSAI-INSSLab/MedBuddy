"""平台配置：模型、主题、审计、系统状态。"""
import json
import os

from flask import Blueprint, jsonify, request

import config as app_config
from backend import db
from backend.api.auth import current_user, login_required
from backend.services import llm, rag

bp = Blueprint("settings", __name__)


def _mask(key):
    if not key:
        return ""
    return key[:4] + "•" * max(4, len(key) - 8) + key[-4:] if len(key) > 8 else "•" * len(key)


@bp.get("/settings/agent")
@login_required
def get_agent():
    cfg = db.get_agent_config()
    safe = dict(cfg)
    safe["api_key"] = _mask(cfg.get("api_key", ""))
    safe["has_key"] = bool(cfg.get("api_key"))
    return jsonify({"ok": True, "data": safe})


@bp.put("/settings/agent")
@login_required
def save_agent():
    data = request.get_json(silent=True) or {}
    cfg = db.get_agent_config()
    for k in ("provider", "base_url", "model", "embedding_model", "system_prompt"):
        if k in data:
            cfg[k] = (data[k] or "").strip()
    for k in ("temperature", "max_tokens", "top_k"):
        if k in data:
            try:
                cfg[k] = float(data[k]) if k == "temperature" else int(data[k])
            except (TypeError, ValueError):
                pass
    if "enable_safety" in data:
        cfg["enable_safety"] = "1" if data["enable_safety"] else "0"
    key = data.get("api_key")
    if key is not None and "•" not in key:
        cfg["api_key"] = key.strip()
    db.save_agent_config(cfg)
    db.audit(current_user()["name"], "save_agent_config", cfg.get("provider", ""),
             f"model={cfg.get('model')}")
    if data.get("rebuild_kb"):
        rag.rebuild_all(cfg)
    return jsonify({"ok": True, "data": {"saved": True}})


@bp.post("/settings/agent/test")
@login_required
def test_agent():
    data = request.get_json(silent=True) or {}
    cfg = db.get_agent_config()
    override = {k: v for k, v in data.items() if k in cfg}
    if override.get("api_key") and "•" in str(override["api_key"]):
        override.pop("api_key")
    cfg.update(override)
    ok, msg, latency = llm.test_connection(cfg)
    db.audit(current_user()["name"], "test_agent", cfg.get("provider", ""), msg)
    return jsonify({"ok": True, "data": {"success": ok, "message": msg, "latency_ms": latency}})


@bp.get("/settings/themes")
def themes():
    return jsonify({"ok": True, "data": app_config.PRESET_THEMES})


@bp.get("/audit")
@login_required
def audit_list():
    limit = min(200, int(request.args.get("limit", 80)))
    rows = db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    return jsonify({"ok": True, "data": rows})


@bp.get("/system/status")
@login_required
def system_status():
    cfg = db.get_agent_config()
    stats = rag.kb_stats()
    db_size = os.path.getsize(app_config.DB_PATH) if os.path.exists(app_config.DB_PATH) else 0
    idx = rag.ensure_index()
    return jsonify({"ok": True, "data": {
        "db_size_mb": round(db_size / 1024 / 1024, 2),
        "patients": db.query("SELECT COUNT(*) c FROM patients", one=True)["c"],
        "metrics": db.query("SELECT COUNT(*) c FROM metrics", one=True)["c"],
        "messages": db.query("SELECT COUNT(*) c FROM messages", one=True)["c"],
        "memories": db.query("SELECT COUNT(*) c FROM memories", one=True)["c"],
        "documents": stats["documents"], "chunks": stats["chunks"],
        "indexed": len(idx["chunks"]),
        "provider": cfg.get("provider"), "model": cfg.get("model"),
        "embedding": cfg.get("embedding_model") or "本地 n-gram 向量（内置）",
        "version": "1.0.0",
    }})
