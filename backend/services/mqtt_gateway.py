"""MQTT 网关：订阅设备体征主题，解析后写入平台。

设计要点：
- 后台线程由 paho 的 loop_start 托管，Flask 启动时不阻塞；
- 每条报文在 Flask 应用上下文中入库，复用 ORM/服务层与风险计算；
- 断线自动重连（1s 起指数退避），配置变更后热重启；
- 运行指标（连接状态、消息数、错误数、最后报文时间）供前端展示。
"""
import ssl
import threading
import time
from datetime import datetime

from backend import db
from backend.services import device_ingest

try:
    import paho.mqtt.client as mqtt
    HAS_PAHO = True
except ImportError:  # 未安装依赖时降级，不影响平台其他功能
    mqtt = None
    HAS_PAHO = False


class Gateway:
    def __init__(self):
        self.app = None
        self.client = None
        self.cfg = {}
        self._lock = threading.RLock()
        self.stats = {
            "messages": 0, "readings": 0, "errors": 0, "alerts": 0,
            "last_message_at": None, "last_error": None,
            "connected_at": None, "reconnects": 0,
        }
        self.connected = False
        self.started_at = None
        self.topic = ""
        self.broker = ""

    # ---------------- 生命周期 ----------------
    def autostart(self, app):
        self.app = app
        try:
            cfg = db.get_mqtt_config()
        except Exception as e:
            self.stats["last_error"] = f"读取配置失败：{e}"
            return
        if str(cfg.get("enabled")) in ("1", "True", "true"):
            self.start(cfg)
        else:
            self.topic = cfg.get("topic", "")
            self.broker = f"{cfg.get('host')}:{cfg.get('port')}"

    def start(self, cfg=None):
        if not HAS_PAHO:
            self.stats["last_error"] = "未安装 paho-mqtt，执行 pip install paho-mqtt 后重启"
            return False
        with self._lock:
            if self.client is not None:
                self.stop()
            cfg = cfg or db.get_mqtt_config()
            self.cfg = dict(cfg)
            self.topic = cfg.get("topic") or "medbuddy/+/vitals"
            self.broker = f"{cfg.get('host')}:{cfg.get('port')}"
            client_id = (cfg.get("client_id") or "medbuddy-gateway") + "-" + str(int(time.time()) % 10000)
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id,
                                     clean_session=True, protocol=mqtt.MQTTv311)
            except Exception:
                client = mqtt.Client(client_id=client_id, clean_session=True, protocol=mqtt.MQTTv311)

            if cfg.get("username"):
                client.username_pw_set(cfg.get("username"), cfg.get("password") or "")
            if str(cfg.get("tls")) in ("1", "True", "true"):
                client.tls_set(cert_reqs=ssl.CERT_NONE)
                client.tls_insecure_set(True)
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            try:
                client.connect_async(cfg.get("host") or "127.0.0.1", int(cfg.get("port") or 1883), keepalive=30)
                client.loop_start()
            except Exception as e:
                self.stats["last_error"] = f"启动失败：{e}"
                self.stats["errors"] += 1
                return False
            self.client = client
            self.started_at = db.now()
            self.stats["last_error"] = None
            return True

    def stop(self):
        with self._lock:
            client, self.client = self.client, None
            self.connected = False
            if client is None:
                return
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass

    def restart(self, cfg=None):
        self.stop()
        cfg = cfg or db.get_mqtt_config()
        self.topic = cfg.get("topic") or ""
        self.broker = f"{cfg.get('host')}:{cfg.get('port')}"
        if str(cfg.get("enabled")) in ("1", "True", "true"):
            return self.start(cfg)
        return True

    # ---------------- paho 回调 ----------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        code = getattr(reason_code, "value", reason_code)
        if code == 0:
            self.connected = True
            self.stats["connected_at"] = db.now()
            qos = int(self.cfg.get("qos") or 1)
            client.subscribe(self.topic, qos=qos)
            self._log_event(None, "connect", f"{self.broker} 订阅 {self.topic} (QoS{qos})")
        else:
            self.connected = False
            self.stats["errors"] += 1
            self.stats["last_error"] = f"连接被拒绝：{reason_code}"
            self._log_event(None, "error", self.stats["last_error"])

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        self.stats["reconnects"] += 1
        self._log_event(None, "disconnect", f"断开：{reason_code}")

    def _on_message(self, client, userdata, msg):
        raw = msg.payload
        topic = msg.topic
        self.stats["messages"] += 1
        self.stats["last_message_at"] = db.now()
        try:
            if self.app is None:
                raise RuntimeError("网关未绑定应用上下文")
            with self.app.app_context():
                parsed = device_ingest.parse_payload(raw, topic, self.cfg)
                res = device_ingest.ingest(parsed, topic=topic, raw=raw.decode("utf-8", "ignore"),
                                           cfg=self.cfg)
                if res.get("status") == "ok":
                    self.stats["readings"] += res.get("metric_count", 0)
                    self.stats["alerts"] += len(res.get("alerts") or [])
                else:
                    self.stats["errors"] += 1
                    if res.get("error"):
                        self.stats["last_error"] = res["error"]
        except Exception as e:  # 网关线程绝不能因单条报文退出
            self.stats["errors"] += 1
            self.stats["last_error"] = f"处理失败：{e}"
            try:
                if self.app is not None:
                    with self.app.app_context():
                        db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
                                   (None, "error", str(e)[:300]))
            except Exception:
                pass

    def _log_event(self, sn, event, detail):
        try:
            if self.app is not None:
                with self.app.app_context():
                    db.execute("INSERT INTO device_events(device_sn,event,detail) VALUES(?,?,?)",
                               (sn, event, (detail or "")[:500]))
        except Exception:
            pass

    # ---------------- 对外状态 ----------------
    def status(self, cfg=None):
        cfg = cfg or self.cfg or {}
        return {
            "available": HAS_PAHO,
            "running": self.client is not None,
            "connected": bool(self.client is not None and self.connected),
            "broker": self.broker or f"{cfg.get('host', '')}:{cfg.get('port', '')}",
            "topic": self.topic or cfg.get("topic", ""),
            "started_at": self.started_at,
            "stats": dict(self.stats),
            "server_time": db.now(),
        }

    def test_connection(self, cfg):
        """阻塞式连通性测试，不改变正在运行的网关。"""
        if not HAS_PAHO:
            return False, "未安装 paho-mqtt，请先执行 pip install paho-mqtt", 0
        t0 = time.time()
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                 client_id=(cfg.get("client_id") or "medbuddy-test") + "-probe",
                                 protocol=mqtt.MQTTv311)
        except Exception:
            client = mqtt.Client(client_id="medbuddy-test-probe", protocol=mqtt.MQTTv311)
        try:
            if cfg.get("username"):
                client.username_pw_set(cfg.get("username"), cfg.get("password") or "")
            if str(cfg.get("tls")) in ("1", "True", "true"):
                client.tls_set(cert_reqs=ssl.CERT_NONE)
                client.tls_insecure_set(True)
            client.connect(cfg.get("host") or "127.0.0.1", int(cfg.get("port") or 1883), keepalive=10)
            client.loop_start()
            time.sleep(0.6)
            client.loop_stop()
            client.disconnect()
            ms = int((time.time() - t0) * 1000)
            return True, f"已连上 {cfg.get('host')}:{cfg.get('port')}，可订阅 {cfg.get('topic')}", ms
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return False, f"连接失败：{e}", ms


gateway = Gateway()
