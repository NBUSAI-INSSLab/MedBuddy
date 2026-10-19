"""设备接入（MQTT）测试：报文解析、入库管道、设备台账、真实 Broker 端到端。

运行：.venv/Scripts/python.exe tests/test_mqtt.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DIR = tempfile.mkdtemp(prefix="medbuddy_mqtt_")
import config  # noqa: E402

config.DB_PATH = os.path.join(TMP_DIR, "test.db")

from app import create_app  # noqa: E402
from backend import db  # noqa: E402
from backend.services import device_ingest as di  # noqa: E402
from backend.services import mqtt_gateway  # noqa: E402

APP = create_app()
BROKER_PORT = 18830


class TestParse(unittest.TestCase):
    def test_nested_json_and_aliases(self):
        raw = json.dumps({
            "device_sn": "MB-BP-1", "vitals": {"hr": 71, "bp": {"sbp": 128, "dbp": 79},
                                               "spo2": 98, "temp": 36.6, "hrv": 41}})
        p = di.parse_payload(raw, "medbuddy/MB-BP-1/vitals", {})
        self.assertEqual(p["device_sn"], "MB-BP-1")
        self.assertEqual(p["vitals"]["heart_rate"], 71)
        self.assertEqual(p["vitals"]["sbp"], 128)
        self.assertEqual(p["vitals"]["dbp"], 79)
        self.assertEqual(p["vitals"]["hrv"], 41)
        self.assertIsNone(p["error"])

    def test_flat_uppercase_and_topic_sn(self):
        p = di.parse_payload('{"SBP":"135","DBP":"85","Pulse":80,"SpO2":97}',
                             "medbuddy/MB-X-9/vitals", {})
        self.assertEqual(p["device_sn"], "MB-X-9")
        self.assertEqual(p["vitals"]["sbp"], 135)
        self.assertEqual(p["vitals"]["heart_rate"], 80)
        self.assertEqual(p["vitals"]["spo2"], 97)

    def test_csv_payload(self):
        p = di.parse_payload("hr=88,sbp=142,dbp=90,spo2=95,temp=36.9,hrv=28",
                            "medbuddy/MB-Z/vitals", {"payload_format": "csv"})
        self.assertEqual(p["vitals"]["heart_rate"], 88)
        self.assertEqual(p["vitals"]["temp"], 36.9)
        self.assertEqual(p["vitals"]["dbp"], 90)

    def test_epoch_timestamp(self):
        p = di.parse_payload('{"device_sn":"A1","ts":1729300000,"hr":70}', "t", {})
        self.assertTrue(p["measured_at"].startswith("2024-"))
        self.assertEqual(p["vitals"]["heart_rate"], 70)

    def test_bad_payload_reports_error(self):
        p = di.parse_payload("{not json", "medbuddy/A/vitals", {})
        self.assertIn("JSON", p["error"])
        p2 = di.parse_payload('{"device_sn":"A1","foo":1}', "t", {})
        self.assertIn("有效体征", p2["error"])


class TestIngest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = APP.test_client()
        cls.c.post("/api/auth/login", json={"username": "doctor", "password": "doctor123"})
        # 绑定到 1 号患者的测试设备
        r = cls.c.post("/api/devices", json={"device_sn": "TEST-SN-1", "name": "测试血压计",
                                             "patient_id": 1})
        assert r.status_code == 200, r.get_data(as_text=True)
        cls.dev = [d for d in cls.c.get("/api/devices").get_json()["data"]["items"]
                   if d["device_sn"] == "TEST-SN-1"][0]

    def _publish(self, vitals, sn="TEST-SN-1", ts=None):
        payload = {"device_sn": sn, "patient_id": 1, "vitals": vitals}
        if ts:
            payload["ts"] = ts
        parsed = di.parse_payload(json.dumps(payload), f"medbuddy/{sn}/vitals", {})
        with APP.app_context():
            return di.ingest(parsed, topic=f"medbuddy/{sn}/vitals", raw=json.dumps(payload))

    def test_ingest_writes_metrics(self):
        before = self.c.get("/api/patients/1").get_json()["data"]["features"]["device_metric_count"]
        res = self._publish({"sbp": 138, "dbp": 86, "heart_rate": 74, "spo2": 97,
                             "temp": 36.5, "hrv": 40}, ts="2026-10-18 09:00:00")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["metric_count"], 6)
        after = self.c.get("/api/patients/1").get_json()["data"]["features"]["device_metric_count"]
        self.assertGreater(after, before)
        self.assertTrue(res["summary"].startswith("血压 138/86"))

    def test_range_rejected(self):
        res = self._publish({"sbp": 999, "heart_rate": 70}, ts="2026-10-18 09:05:00")
        self.assertEqual(res["metric_count"], 1)
        self.assertTrue(res["rejected"])
        self.assertIn("sbp", res["rejected"][0])
        with APP.app_context():
            row = db.query("SELECT value FROM metrics WHERE metric_type='sbp' "
                           "AND measured_at='2026-10-18 09:05:00' AND device_sn='TEST-SN-1'",
                           one=True)
        self.assertIsNone(row)

    def test_duplicate_suppressed(self):
        ts = "2026-10-18 09:10:00"
        first = self._publish({"heart_rate": 72}, ts=ts)
        second = self._publish({"heart_rate": 72}, ts=ts)
        self.assertEqual(first["metric_count"], 1)
        self.assertEqual(second["metric_count"], 0)
        self.assertEqual(second.get("duplicate"), 1)

    def test_alert_generated_once(self):
        res = self._publish({"spo2": 85}, ts="2026-10-18 09:20:00")
        self.assertTrue(any("血氧" in a for a in res["alerts"]))
        again = self._publish({"spo2": 85}, ts="2026-10-18 09:25:00")
        self.assertFalse(again["alerts"])  # 30 分钟内同类预警去重

    def test_auto_register_and_self_bind(self):
        parsed = di.parse_payload(json.dumps({
            "device_sn": "AUTO-777", "patient_id": 2, "vitals": {"heart_rate": 68}}),
            "medbuddy/AUTO-777/vitals", {})
        with APP.app_context():
            res = di.ingest(parsed, topic="medbuddy/AUTO-777/vitals", raw=json.dumps(parsed))
        self.assertEqual(res["status"], "ok")
        item = [d for d in self.c.get("/api/devices").get_json()["data"]["items"]
                if d["device_sn"] == "AUTO-777"][0]
        self.assertEqual(item["patient_name"], "李秀兰")

    def test_unbound_device_ignored(self):
        r = self.c.post("/api/devices", json={"device_sn": "NOBODY-1"})
        self.assertEqual(r.status_code, 200)
        parsed = di.parse_payload('{"device_sn":"NOBODY-1","vitals":{"heart_rate":70}}',
                                  "medbuddy/NOBODY-1/vitals", {})
        with APP.app_context():
            res = di.ingest(parsed, topic="medbuddy/NOBODY-1/vitals", raw="{}")
        self.assertEqual(res["status"], "ignored")
        self.assertIn("未绑定", res["error"])

    def test_simulate_endpoint(self):
        r = self.c.post(f"/api/devices/{self.dev['id']}/simulate", json={"count": 3})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["readings"], 3)
        self.assertGreaterEqual(d["inserted"], 12)

    def test_bind_and_unbind(self):
        r = self.c.put(f"/api/devices/{self.dev['id']}", json={"patient_id": 3})
        self.assertEqual(r.status_code, 200)
        item = [d for d in self.c.get("/api/devices").get_json()["data"]["items"]
                if d["id"] == self.dev["id"]][0]
        self.assertEqual(item["patient_name"], "王卫东")
        self.c.put(f"/api/devices/{self.dev['id']}", json={"patient_id": 1})

    def test_daily_rollup_updated(self):
        with APP.app_context():
            row = db.query("SELECT * FROM metric_daily WHERE patient_id=1 AND metric_type='heart_rate' "
                           "AND day='2026-10-18'", one=True)
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row["cnt"], 1)


def _run_broker(loop, broker):
    async def _start():
        await broker.start()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_start())
    threading.Thread(target=loop.run_forever, daemon=True).start()


class TestMqttEndToEnd(unittest.TestCase):
    """真实 Broker：验证网关订阅、报文入库、断线重连。"""

    @classmethod
    def setUpClass(cls):
        try:
            from amqtt.broker import Broker
        except ImportError:
            raise unittest.SkipTest("未安装 amqtt")
        cfg = {"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{BROKER_PORT}",
                                         "max_connections": 20}},
               "sys_interval": 0,
               "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
               "topic-check": {"enabled": False}}
        cls.loop = asyncio.new_event_loop()
        cls.broker = Broker(cfg, loop=cls.loop)
        try:
            _run_broker(cls.loop, cls.broker)
        except Exception as e:
            raise unittest.SkipTest(f"Broker 启动失败：{e}")
        time.sleep(1)
        cls.c = APP.test_client()
        cls.c.post("/api/auth/login", json={"username": "doctor", "password": "doctor123"})
        cls.c.post("/api/devices", json={"device_sn": "E2E-1", "name": "端到端设备", "patient_id": 1})
        cls.c.put("/api/settings/mqtt", json={
            "enabled": "1", "host": "127.0.0.1", "port": BROKER_PORT,
            "topic": "medbuddy/+/vitals", "qos": 1, "payload_format": "json"})
        deadline = time.time() + 8
        while time.time() < deadline:
            if cls.c.get("/api/settings/mqtt/status").get_json()["data"]["connected"]:
                break
            time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.c.put("/api/settings/mqtt", json={"enabled": "0"})
        mqtt_gateway.gateway.stop()

        async def _stop():
            await cls.broker.shutdown()
        try:
            fut = asyncio.run_coroutine_threadsafe(_stop(), cls.loop)
            fut.result(timeout=5)
        except Exception:
            pass
        cls.loop.call_soon_threadsafe(cls.loop.stop)

    def test_gateway_connected(self):
        st = self.c.get("/api/settings/mqtt/status").get_json()["data"]
        self.assertTrue(st["connected"], st)

    def test_publish_reaches_patient(self):
        import paho.mqtt.client as mqtt
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-publisher")
        pub.connect("127.0.0.1", BROKER_PORT)
        pub.loop_start()
        time.sleep(0.4)
        ts = "2026-10-18 21:30:00"
        pub.publish("medbuddy/E2E-1/vitals", json.dumps({
            "device_sn": "E2E-1", "patient_id": 1, "ts": ts,
            "vitals": {"heart_rate": 77, "spo2": 96, "temp": 36.7, "hrv": 35},
            "battery": 90, "signal": -55}, ensure_ascii=False), qos=1)
        deadline = time.time() + 6
        found = None
        while time.time() < deadline:
            with APP.app_context():
                found = db.query(
                    "SELECT * FROM metrics WHERE device_sn='E2E-1' AND measured_at=?", (ts,))
            if found:
                break
            time.sleep(0.3)
        pub.loop_stop()
        pub.disconnect()
        self.assertTrue(found, "MQTT 报文未入库")
        types = {r["metric_type"] for r in found}
        self.assertEqual(types, {"heart_rate", "spo2", "temp", "hrv"})
        st = self.c.get("/api/settings/mqtt/status").get_json()["data"]
        self.assertGreaterEqual(st["stats"]["messages"], 1)
        self.assertGreaterEqual(st["stats"]["readings"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
