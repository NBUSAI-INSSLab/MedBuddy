"""MedBuddy 慢病管理平台 —— Flask 入口。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, send_from_directory, session

import config
from backend import db as database
from backend.api import (auth, chat, dashboard, devices, diet as diet_api, expert as expert_api,
                         expert_admin, kb, patients, settings as settings_api, users as users_api)
from backend.seed import seed_if_empty
from backend.services import device_ingest, experts as expert_service, mqtt_gateway, rag


def create_app():
    app = Flask(__name__, static_folder=None, template_folder=None)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["JSON_AS_ASCII"] = False
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.json.ensure_ascii = False

    database.init_db()
    app.teardown_appcontext(database.close_db)

    for bp in (auth.bp, patients.bp, dashboard.bp, chat.bp, kb.bp, settings_api.bp,
               devices.bp, users_api.bp, diet_api.bp, expert_api.bp, expert_admin.bp):
        app.register_blueprint(bp, url_prefix="/api")

    with app.app_context():
        seeded = seed_if_empty()
        expert_service.ensure_seed()
        rag.ensure_index(force=True)
        print(f"[MedBuddy] 数据初始化：{'已写入演示数据' if seeded else '使用现有数据'}；"
              f"知识库索引 {len(rag.ensure_index()['chunks'])} 片段")
        # 设备接入网关（配置启用时在后台连接 Broker，不阻塞启动）
        mqtt_gateway.gateway.autostart(app)
        st = mqtt_gateway.gateway.status()
        print(f"[MedBuddy] 设备网关：{'运行中' if st['running'] else '未启用'} · {st['broker']} · {st['topic']}")

        # 老库补建日聚合 + 清理过期原始报文（不影响明细指标）
        if (database.query("SELECT COUNT(*) c FROM metric_daily", one=True)["c"] == 0
                and database.query("SELECT COUNT(*) c FROM metrics", one=True)["c"] > 0):
            print(f"[MedBuddy] 重建日聚合 {device_ingest.rebuild_daily()} 条")
        removed = device_ingest.prune_readings()
        if removed:
            print(f"[MedBuddy] 清理过期设备报文 {removed} 条")

    @app.get("/")
    def index():
        return send_from_directory(config.FRONTEND_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        full = os.path.join(config.FRONTEND_DIR, path)
        if os.path.isfile(full):
            return send_from_directory(config.FRONTEND_DIR, path)
        return send_from_directory(config.FRONTEND_DIR, "index.html")

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"ok": False, "error": "接口不存在"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"ok": False, "error": f"服务器错误：{e}"}), 500

    @app.after_request
    def no_cache(resp):
        if resp.mimetype in ("text/html", "text/css", "application/javascript", "text/event-stream"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    print("[MedBuddy] 访问 http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
