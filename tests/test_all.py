"""MedBuddy 测试套件：单元 + 接口 + 智能体 + 个性化。

运行：.venv/Scripts/python.exe tests/test_all.py
使用独立临时数据库，不影响演示数据。
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DIR = tempfile.mkdtemp(prefix="medbuddy_test_")
import config  # noqa: E402

config.DB_PATH = os.path.join(TMP_DIR, "test.db")
config.UPLOAD_DIR = os.path.join(TMP_DIR, "uploads")
os.makedirs(config.UPLOAD_DIR, exist_ok=True)

from app import create_app  # noqa: E402
from backend import db  # noqa: E402
from backend.services import agent, llm, personalization as per, rag, safety  # noqa: E402

APP = create_app()


def parse_sse(body):
    events, cur = [], {"event": "message", "data": []}
    for line in body.split("\n"):
        if line.startswith("event:"):
            cur["event"] = line[6:].strip()
        elif line.startswith("data:"):
            cur["data"].append(line[5:].strip())
        elif line == "" and cur["data"]:
            try:
                payload = json.loads("\n".join(cur["data"]))
            except Exception:
                payload = {}
            events.append((cur["event"], payload))
            cur = {"event": "message", "data": []}
    return events


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = APP.test_client()
        r = cls.c.post("/api/auth/login", json={"username": "doctor", "password": "doctor123"})
        assert r.status_code == 200, r.get_data(as_text=True)
        cls.cookie_ready = True


class TestUnit(Base):
    def test_split_document_keeps_heading(self):
        text = "# 高血压\n\n## 测量方法\n静坐 5 分钟后测量。" * 30
        parts = rag.split_document(text)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(isinstance(h, str) and body for h, body in parts))
        self.assertTrue(any("测量方法" in h for h, _ in parts))

    def test_tokenize_filters_punctuation(self):
        toks = rag.tokenize("血压 ≥140/90 mmHg，需要复测。")
        self.assertIn("血压", toks)
        self.assertNotIn("，", toks)

    def test_intent_detection(self):
        self.assertEqual(llm.detect_intent("我老是忘记吃二甲双胍怎么办"), "medication")
        self.assertEqual(llm.detect_intent("平时饮食要注意什么"), "diet")
        self.assertEqual(llm.detect_intent("最近血压控制得怎么样"), "metric")

    def test_risk_score_and_level(self):
        p = {"id": 999, "birth_date": "1950-01-01", "enrolled_at": "2025-01-01", "smoking": "current"}
        conds = [{"name": "高血压"}, {"name": "慢性肾脏病"}]
        feats = {"bp_avg7": {"sbp": 172, "dbp": 104}, "bp_control_rate": 10,
                 "glucose_avg7": 12.4, "hba1c": 9.6, "med_adherence": 50,
                 "open_alerts": 2, "metric_count": 40}
        score, level, reasons = per.compute_risk(p, conds, [], feats)
        self.assertGreaterEqual(score, 70)
        self.assertEqual(level, "critical")
        self.assertTrue(reasons)

    def test_maturity_grows_with_data(self):
        low = per.maturity({"managed_days": 1, "metric_count": 0, "chat_turns": 0,
                            "memory_count": 0, "followup_done": 0})
        high = per.maturity({"managed_days": 180, "metric_count": 120, "chat_turns": 40,
                             "memory_count": 20, "followup_done": 8})
        self.assertLess(low["score"], high["score"])
        self.assertEqual(low["stage"], "起步期")
        self.assertEqual(high["stage"], "成熟期")

    def test_safety_red_flag(self):
        res = safety.check(1, "今天突然胸痛，喘不上气", metrics={})
        self.assertTrue(res["hit"])
        self.assertTrue(res["actions"])

    def test_safety_critical_value(self):
        res = safety.check(1, "有点头晕", {"sbp": {"value": 186}, "dbp": {"value": 112}})
        self.assertTrue(res["hit"])

    def test_safety_normal(self):
        res = safety.check(1, "我想了解饮食怎么安排", {"sbp": {"value": 128}, "dbp": {"value": 78}})
        self.assertFalse(res["hit"])


class TestApi(Base):
    def test_requires_login(self):
        fresh = APP.test_client()
        self.assertEqual(fresh.get("/api/patients").status_code, 401)

    def test_login_failure(self):
        fresh = APP.test_client()
        r = fresh.post("/api/auth/login", json={"username": "doctor", "password": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_patient_list_and_filters(self):
        d = self.c.get("/api/patients").get_json()["data"]
        self.assertEqual(d["total"], 12)
        hi = self.c.get("/api/patients?risk=high").get_json()["data"]
        self.assertTrue(all(p["risk_level"] == "high" for p in hi["items"]))
        q = self.c.get("/api/patients?q=陈建国").get_json()["data"]
        self.assertEqual(q["total"], 1)
        dm = self.c.get("/api/patients?disease=糖尿病").get_json()["data"]
        self.assertGreater(dm["total"], 0)

    def test_patient_detail_shape(self):
        d = self.c.get("/api/patients/1").get_json()["data"]
        for key in ("profile", "conditions", "medications", "features", "risk",
                    "maturity", "memories", "series", "plan", "followup_plan"):
            self.assertIn(key, d)
        self.assertTrue(d["risk"]["reasons"])
        self.assertIn("sbp", d["series"])

    def test_add_metric_triggers_critical_alert(self):
        before = self.c.get("/api/patients/5").get_json()["data"]["alerts"]
        r = self.c.post("/api/patients/5/metrics",
                        json={"metric_type": "sbp", "value": 188, "note": "复测"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["data"]["alert"])
        after = self.c.get("/api/patients/5").get_json()["data"]["alerts"]
        self.assertGreater(len(after), len(before))

    def test_invalid_metric_rejected(self):
        r = self.c.post("/api/patients/5/metrics", json={"metric_type": "xx", "value": 1})
        self.assertEqual(r.status_code, 400)

    def test_handle_alert(self):
        alerts = self.c.get("/api/patients/5").get_json()["data"]["alerts"]
        aid = alerts[0]["id"]
        r = self.c.post(f"/api/patients/5/alerts/{aid}/handle", json={"note": "test"})
        self.assertEqual(r.status_code, 200)
        remain = self.c.get("/api/patients/5").get_json()["data"]["alerts"]
        self.assertNotIn(aid, [a["id"] for a in remain])

    def test_dashboard(self):
        d = self.c.get("/api/dashboard/overview").get_json()["data"]
        self.assertEqual(sum(d["risk"].values()), 12)
        self.assertTrue(d["diseases"])
        self.assertEqual(len(d["activity"]), 14)
        self.assertGreater(d["kb"]["chunks"], 50)

    def test_kb_list_and_search(self):
        d = self.c.get("/api/kb/documents").get_json()["data"]
        self.assertGreaterEqual(len(d["items"]), 9)
        s = self.c.post("/api/kb/search", json={"query": "家庭血压怎么测量", "top_k": 3}).get_json()["data"]
        self.assertTrue(s["results"])
        self.assertIn("血压", s["results"][0]["content"] + s["results"][0]["title"])

    def test_kb_cross_disease_filtered(self):
        # 陈建国无慢性肾病，饮食检索不应命中肾病指南
        s = self.c.post("/api/kb/search",
                        json={"query": "饮食上要注意什么", "patient_id": 1, "top_k": 6}).get_json()["data"]
        cats = [r["category"] for r in s["results"]]
        self.assertNotIn("慢性肾病", cats)

    def test_kb_upload_and_delete(self):
        content = "# 测试规范\n\n## 随访频次\n稳定期患者每三个月随访一次，记录血压与用药情况。" * 8
        r = self.c.post("/api/kb/documents", json={
            "title": "测试文档", "content": content, "category": "综合管理", "doc_type": "protocol"})
        self.assertEqual(r.status_code, 200)
        did = r.get_json()["data"]["id"]
        self.assertGreater(r.get_json()["data"]["chunks"], 0)
        s = self.c.post("/api/kb/search", json={"query": "稳定期多久随访一次"}).get_json()["data"]
        self.assertTrue(any(x["doc_id"] == did for x in s["results"]))
        self.c.delete(f"/api/kb/documents/{did}")
        self.assertNotIn(did, [d["id"] for d in self.c.get("/api/kb/documents").get_json()["data"]["items"]])

    def test_settings_roundtrip(self):
        d = self.c.get("/api/settings/agent").get_json()["data"]
        self.assertIn("provider", d)
        payload = {"provider": "builtin", "top_k": 5, "enable_safety": True}
        self.assertEqual(self.c.put("/api/settings/agent", json=payload).status_code, 200)
        self.assertEqual(self.c.get("/api/settings/agent").get_json()["data"]["top_k"], 5)
        self.c.put("/api/settings/agent", json={"top_k": 4})

    def test_agent_connection_test_builtin(self):
        r = self.c.post("/api/settings/agent/test", json={"provider": "builtin"}).get_json()["data"]
        self.assertTrue(r["success"])

    def test_system_status(self):
        d = self.c.get("/api/system/status").get_json()["data"]
        self.assertEqual(d["patients"], 12)
        self.assertGreater(d["metrics"], 500)


class TestAgent(Base):
    def _ask(self, q, pid=1):
        r = self.c.post("/api/chat/stream", json={"patient_id": pid, "message": q})
        self.assertEqual(r.status_code, 200)
        return parse_sse(r.get_data(as_text=True))

    def test_stream_has_meta_deltas_done(self):
        events = self._ask("最近血压控制得怎么样")
        names = [e[0] for e in events]
        self.assertIn("meta", names)
        self.assertIn("delta", names)
        self.assertIn("done", names)
        meta = next(e[1] for e in events if e[0] == "meta")
        self.assertIn("patient", meta)
        self.assertIn("maturity", meta["patient"])
        text = "".join(e[1].get("text", "") for e in events if e[0] == "delta")
        self.assertGreater(len(text), 120)
        done = next(e[1] for e in events if e[0] == "done")
        self.assertTrue(done["citations"])

    def test_answer_uses_patient_data(self):
        events = self._ask("我最近血糖怎么样")
        text = "".join(e[1].get("text", "") for e in events if e[0] == "delta")
        self.assertIn("陈建国", text)
        self.assertTrue("mmol/L" in text or "血糖" in text)

    def test_emergency_short_circuit(self):
        events = self._ask("我现在胸痛，喘不上气")
        text = "".join(e[1].get("text", "") for e in events if e[0] == "delta")
        self.assertIn("120", text)
        done = next(e[1] for e in events if e[0] == "done")
        self.assertIn("emergency", done["flags"])
        self.assertFalse(done["citations"])

    def test_citations_have_sources(self):
        events = self._ask("家庭血压应该怎么测")
        done = next(e[1] for e in events if e[0] == "done")
        self.assertTrue(done["citations"])
        first = done["citations"][0]
        for k in ("title", "heading", "content", "score"):
            self.assertIn(k, first)
        self.assertLessEqual(first["score"], 1.0)

    def test_memory_extracted_and_maturity_grows(self):
        before = self.c.get("/api/patients/3").get_json()["data"]
        events = self._ask("我上夜班总是忘记吃药，而且特别爱吃甜的", pid=3)
        done = next(e[1] for e in events if e[0] == "done")
        self.assertGreaterEqual(done["new_memories"], 1)
        after = self.c.get("/api/patients/3").get_json()["data"]
        self.assertGreater(after["features"]["memory_count"], before["features"]["memory_count"])

    def test_conversation_persisted(self):
        events = self._ask("复诊前需要准备什么")
        conv = next(e[1] for e in events if e[0] == "conversation")
        cid = conv["conversation_id"]
        d = self.c.get(f"/api/conversations/{cid}/messages").get_json()["data"]
        roles = [m["role"] for m in d["messages"]]
        self.assertEqual(roles[-2:], ["user", "assistant"])
        self.assertTrue(d["messages"][-1]["citations"])

    def test_llm_fallback_to_builtin(self):
        cfg = self.c.get("/api/settings/agent").get_json()["data"]
        self.c.put("/api/settings/agent", json={
            "provider": "openai_compatible", "base_url": "http://127.0.0.1:9/v1",
            "model": "none", "api_key": "x"})
        try:
            events = self._ask("我平时饮食要注意什么")
            done = next(e[1] for e in events if e[0] == "done")
            self.assertIn("llm_fallback", done["flags"])
            text = "".join(e[1].get("text", "") for e in events if e[0] == "delta")
            self.assertGreater(len(text), 100)
        finally:
            self.c.put("/api/settings/agent", json={"provider": "builtin"})

    def test_unknown_question_states_no_evidence(self):
        events = self._ask("我的牙套需要调整吗")
        text = "".join(e[1].get("text", "") for e in events if e[0] == "delta")
        self.assertIn("不能替代", text)


class TestPersonalization(Base):
    def test_memories_list_and_manual_add(self):
        r = self.c.post("/api/patients/6/memories", json={"content": "每周三晚上要上夜班", "kind": "fact"})
        mid = r.get_json()["data"]["id"]
        d = self.c.get("/api/patients/6").get_json()["data"]
        self.assertIn(mid, [m["id"] for m in d["memories"]])
        self.c.delete(f"/api/patients/6/memories/{mid}")

    def test_followup_plan_generated_by_disease(self):
        d = self.c.get("/api/patients/4").get_json()["data"]
        fp = d["followup_plan"]
        self.assertTrue(fp["goals"])
        self.assertIn("肾", " ".join(fp["goals"]) + fp["title"])

    def test_patient_portal_binding(self):
        pc = APP.test_client()
        pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        d = pc.get("/api/my/profile").get_json()["data"]
        self.assertEqual(d["profile"]["name"], "陈建国")
        me = pc.get("/api/auth/me").get_json()["data"]
        self.assertEqual(me["role"], "patient")

    def test_theme_saved(self):
        r = self.c.put("/api/auth/theme", json={"theme": "blue"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/api/auth/me").get_json()["data"]["theme"], "blue")
        self.c.put("/api/auth/theme", json={"theme": "green"})


class TestDiet(Base):
    def test_plan_matches_conditions(self):
        d = self.c.get("/api/patients/1/diet").get_json()["data"]
        plan = d["plan"]
        self.assertGreater(plan["energy"], 1200)
        self.assertLessEqual(plan["salt"], 5)
        self.assertEqual(len(plan["meals"]), 4)
        self.assertTrue(any("高血压" in n["name"] for n in plan["condition_notes"]))
        self.assertTrue(plan["principles"])
        self.assertTrue(plan["foods"]["recommend"] and plan["foods"]["limit"])

    def test_ckd_limits_protein(self):
        d = self.c.get("/api/patients/4/diet").get_json()["data"]
        plan = d["plan"]
        self.assertTrue(any("肾脏" in n["name"] for n in plan["condition_notes"]))
        self.assertIn("低蛋白", " ".join(plan["meals"][1]["dishes"]))
        self.assertLessEqual(plan["protein"], 70)

    def test_add_log_with_estimate_and_summary(self):
        r = self.c.post("/api/patients/5/diet/logs",
                        json={"meal": "lunch", "foods": "米饭、清蒸鱼、炒青菜", "note": "外食"})
        body = r.get_json()
        self.assertTrue(body["ok"])
        data = body["data"]
        self.assertGreater(data["calories"], 0)
        self.assertGreater(data["sodium"], 0)
        self.assertTrue(data["estimated"])
        d = self.c.get("/api/patients/5/diet").get_json()["data"]
        ids = [l["id"] for l in d["logs"]]
        self.assertIn(data["id"], ids)
        self.assertEqual(d["summary"]["today_kcal"], data["calories"])
        self.c.delete(f"/api/patients/5/diet/logs/{data['id']}")

    def test_invalid_meal_rejected(self):
        r = self.c.post("/api/patients/5/diet/logs", json={"meal": "midnight", "foods": "泡面"})
        self.assertEqual(r.status_code, 400)

    def test_patient_cannot_read_other_diet(self):
        pc = APP.test_client()
        pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        mine = pc.get("/api/my/profile").get_json()["data"]["profile"]["id"]
        other = 1 if mine != 1 else 2
        self.assertEqual(pc.get(f"/api/patients/{other}/diet").status_code, 403)
        self.assertEqual(pc.get(f"/api/patients/{mine}/diet").status_code, 200)


class TestExpert(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pc = APP.test_client()
        cls.pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        cls.pid = cls.pc.get("/api/my/profile").get_json()["data"]["profile"]["id"]

    def test_roster_has_experts_and_teams(self):
        d = self.pc.get("/api/expert/roster").get_json()["data"]
        self.assertEqual(len(d["experts"]), 6)
        self.assertEqual(len(d["teams"]), 3)
        self.assertTrue(all(e["online"] for e in d["experts"]))
        self.assertEqual(d["patient"]["name"], "陈建国")
        team = d["teams"][0]
        self.assertEqual(len(team["members"]), 3)
        self.assertTrue(team["member_ids"])

    def test_expert_session_greeting_is_personalized(self):
        d = self.pc.post("/api/expert/sessions",
                         json={"target_type": "expert", "target_id": "cardio_chen"}).get_json()["data"]
        msgs = d["messages"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "expert")
        self.assertEqual(msgs[0]["speaker_name"], "陈志远")
        self.assertIn("陈建国", msgs[0]["content"])
        self.pid_session = d["session"]["id"]

    def test_team_consult_streams_each_speaker(self):
        d = self.pc.post("/api/expert/sessions",
                         json={"target_type": "team", "target_id": "dm_team"}).get_json()["data"]
        sid = d["session"]["id"]
        self.assertEqual(len(d["messages"]), 3)
        r = self.pc.post(f"/api/expert/sessions/{sid}/stream",
                         json={"message": "我最近空腹血糖偏高，饮食怎么调整？"})
        self.assertEqual(r.status_code, 200)
        events = parse_sse(r.get_data(as_text=True))
        speakers = [e[1]["name"] for e in events if e[0] == "speaker"]
        self.assertEqual(speakers, ["林静", "周敏", "吴涛"])
        text = "".join(e[1].get("text", "") for e in events if e[0] == "delta")
        self.assertGreater(len(text), 400)
        self.assertIn("不能替代", text)
        detail = self.pc.get(f"/api/expert/sessions/{sid}").get_json()["data"]
        roles = [m["role"] for m in detail["messages"]]
        self.assertEqual(roles.count("user"), 1)
        self.assertEqual(roles.count("expert"), 6)
        self.pc.delete(f"/api/expert/sessions/{sid}")

    def test_patient_cannot_open_others_session(self):
        dc = APP.test_client()
        dc.post("/api/auth/login", json={"username": "doctor", "password": "doctor123"})
        other_pid = 2 if self.pid != 2 else 3
        d = dc.post("/api/expert/sessions",
                    json={"patient_id": other_pid, "target_type": "expert",
                          "target_id": "endo_lin"}).get_json()["data"]
        sid = d["session"]["id"]
        self.assertEqual(self.pc.get(f"/api/expert/sessions/{sid}").status_code, 403)
        dc.delete(f"/api/expert/sessions/{sid}")

    def test_unknown_target_rejected(self):
        r = self.pc.post("/api/expert/sessions",
                         json={"target_type": "expert", "target_id": "not_exists"})
        self.assertEqual(r.status_code, 404)


class TestExpertAdmin(Base):
    """管理员配置专家：人设、知识库、技能与 MCP 工具。"""

    created_experts = []
    created_teams = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ac = APP.test_client()
        r = cls.ac.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        cls.pc = APP.test_client()
        cls.pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        cls.pid = cls.pc.get("/api/my/profile").get_json()["data"]["profile"]["id"]

    @classmethod
    def tearDownClass(cls):
        with APP.app_context():
            for eid in cls.created_experts:
                db.execute("DELETE FROM expert_profiles WHERE id=?", (eid,))
            for tid in cls.created_teams:
                db.execute("DELETE FROM expert_teams WHERE id=?", (tid,))

    def _catalog(self):
        return self.ac.get("/api/admin/experts").get_json()["data"]

    def test_admin_overview_exposes_config(self):
        d = self._catalog()
        self.assertGreaterEqual(len(d["experts"]), 6)
        self.assertTrue(d["catalog"]["skills"])
        self.assertGreaterEqual(len(d["catalog"]["mcp"]), 6)
        cardio = [e for e in d["experts"] if e["code"] == "cardio_chen"][0]
        self.assertTrue(cardio["skills"])
        self.assertTrue(cardio["tools"])
        self.assertTrue(cardio["kb_doc_ids"])
        self.assertTrue(all(isinstance(x, int) for x in cardio["kb_doc_ids"]))
        self.assertIn("desc", d["catalog"]["skills"][0])

    def test_non_admin_cannot_manage_experts(self):
        self.assertEqual(self.c.get("/api/admin/experts").status_code, 403)
        self.assertEqual(self.pc.get("/api/admin/experts").status_code, 403)
        r = self.c.post("/api/admin/experts", json={"name": "越权专家"})
        self.assertEqual(r.status_code, 403)

    def test_create_expert_with_skills_kb_and_mcp(self):
        kb = self._catalog()["catalog"]["kb"]
        r = self.ac.post("/api/admin/experts", json={
            "name": "测试老年医学科", "title": "主治医师 · 老年医学科", "dept": "老年医学科",
            "org": "社区卫生服务中心", "role_key": "gp", "years": 9,
            "tags": "跌倒风险,多重用药", "intro": "关注老年综合评估。", "style": "耐心",
            "greeting": "我是测试医生。", "questions": "怎么防跌倒？\n吃药太多怎么办？",
            "skills": ["risk_triage", "med_check"],
            "kb_doc_ids": [kb[0]["id"]],
            "mcp_tools": [{"key": "vitals_query"},
                          {"key": "custom_fall", "name": "跌倒风险问卷", "desc": "评估量表"}],
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        code, eid = r.get_json()["data"]["code"], r.get_json()["data"]["db_id"]
        self.created_experts.append(eid)
        d = self._catalog()
        row = [e for e in d["experts"] if e["code"] == code][0]
        self.assertEqual([s["name"] for s in row["skills"]], ["风险分诊", "用药核对"])
        self.assertEqual([x["name"] for x in row["tools"]], ["家庭体征查询", "跌倒风险问卷"])
        self.assertEqual(len(row["kb_docs"]), 1)
        self.assertEqual(row["kb_doc_ids"], [kb[0]["id"]])
        # 患者端立即出现，且能力随专家下发
        roster = self.pc.get("/api/expert/roster").get_json()["data"]["experts"]
        mine = [e for e in roster if e["id"] == code][0]
        self.assertEqual(len(mine["skills"]), 2)
        self.assertEqual(mine["kb_count"], 1)
        self.assertEqual(len(mine["questions"]), 2)

    def test_update_and_pause_expert(self):
        r = self.ac.post("/api/admin/experts", json={"name": "测试停用专家", "role_key": "gp",
                                                     "skills": ["education"]})
        eid = r.get_json()["data"]["db_id"]
        code = r.get_json()["data"]["code"]
        self.created_experts.append(eid)
        r = self.ac.put(f"/api/admin/experts/{eid}", json={"name": "测试停用专家改", "years": 12})
        self.assertEqual(r.status_code, 200)
        row = [e for e in self._catalog()["experts"] if e["code"] == code][0]
        self.assertEqual(row["name"], "测试停用专家改")
        self.assertEqual(row["years"], 12)
        self.ac.post(f"/api/admin/experts/{eid}/status", json={})
        roster = self.pc.get("/api/expert/roster").get_json()["data"]["experts"]
        self.assertNotIn(code, [e["id"] for e in roster])
        self.ac.post(f"/api/admin/experts/{eid}/status", json={})
        roster = self.pc.get("/api/expert/roster").get_json()["data"]["experts"]
        self.assertIn(code, [e["id"] for e in roster])

    def test_team_create_requires_members(self):
        r = self.ac.post("/api/admin/expert-teams", json={"name": "测试空团队"})
        self.assertEqual(r.status_code, 400)
        r = self.ac.post("/api/admin/expert-teams", json={
            "name": "测试老年共病团队", "desc": "测试用", "scenario": "场景",
            "tags": ["测试"], "member_ids": ["cardio_chen", "pharmacy_wu"],
            "skills": ["followup"], "mcp_tools": ["vitals_query"],
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        code, tid = r.get_json()["data"]["code"], r.get_json()["data"]["db_id"]
        self.created_teams.append(tid)
        teams = self.pc.get("/api/expert/roster").get_json()["data"]["teams"]
        team = [x for x in teams if x["id"] == code][0]
        self.assertEqual(team["member_ids"], ["cardio_chen", "pharmacy_wu"])
        d = self.pc.post("/api/expert/sessions",
                         json={"target_type": "team", "target_id": code}).get_json()["data"]
        self.assertEqual([m["speaker_name"] for m in d["messages"]], ["陈志远", "吴涛"])
        self.pc.delete(f"/api/expert/sessions/{d['session']['id']}")
        # 已产生会诊记录的团队不允许直接删除
        d2 = self.pc.post("/api/expert/sessions",
                          json={"target_type": "team", "target_id": code}).get_json()["data"]
        self.assertEqual(self.ac.delete(f"/api/admin/expert-teams/{tid}").status_code, 400)
        self.pc.delete(f"/api/expert/sessions/{d2['session']['id']}")
        self.assertEqual(self.ac.delete(f"/api/admin/expert-teams/{tid}").status_code, 200)
        self.created_teams.remove(tid)

    def test_expert_answer_uses_bound_kb_and_records_capabilities(self):
        kb = self._catalog()["catalog"]["kb"]
        picked = [d for d in kb if d["category"] == "慢性肾病"]
        r = self.ac.post("/api/admin/experts", json={
            "name": "测试限库专家", "role_key": "nephro", "skills": ["metric_review"],
            "kb_doc_ids": [picked[0]["id"]], "mcp_tools": ["lab_parse"],
        })
        code, eid = r.get_json()["data"]["code"], r.get_json()["data"]["db_id"]
        self.created_experts.append(eid)
        d = self.pc.post("/api/expert/sessions",
                         json={"target_type": "expert", "target_id": code}).get_json()["data"]
        sid = d["session"]["id"]
        r = self.pc.post(f"/api/expert/sessions/{sid}/stream",
                         json={"message": "肾功能下降要注意什么？"})
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)   # 消费 SSE，确保生成器执行完毕
        self.assertIn("event: done", body)
        detail = self.pc.get(f"/api/expert/sessions/{sid}").get_json()["data"]
        meta = detail["messages"][-1]["meta"]
        self.assertEqual(meta["skills"], ["指标解读"])
        self.assertEqual(meta["tools"], ["检验报告解析"])
        self.assertEqual(meta["kb"], 1)
        for c in meta.get("citations") or []:
            self.assertEqual(c["doc_id"], picked[0]["id"])
        self.pc.delete(f"/api/expert/sessions/{sid}")

    def test_invalid_payload_rejected(self):
        r = self.ac.post("/api/admin/experts", json={"name": "短"})
        self.assertEqual(r.status_code, 400)
        r = self.ac.post("/api/admin/experts", json={"name": "测试重复名", "role_key": "gp"})
        eid = r.get_json()["data"]["db_id"]
        self.created_experts.append(eid)
        r = self.ac.post("/api/admin/experts", json={"name": "测试重复名", "role_key": "gp"})
        self.assertEqual(r.status_code, 400)


def make_meal_image(main_color=(34, 139, 34)):
    """生成一张白盘 + 三块食物的合成图，用于照片分析测试。"""
    from PIL import Image, ImageDraw
    import io
    img = Image.new("RGB", (640, 480), (245, 245, 242))
    d = ImageDraw.Draw(img)
    d.ellipse((40, 30, 600, 450), fill=(252, 252, 250), outline=(225, 225, 222), width=4)
    d.ellipse((80, 110, 300, 370), fill=main_color)          # 蔬菜
    d.ellipse((320, 110, 470, 370), fill=(238, 234, 220))    # 米饭
    d.ellipse((480, 140, 580, 340), fill=(122, 74, 44))      # 肉类
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    buf.seek(0)
    return buf


class TestDietPhoto(Base):
    def setUp(self):
        self.pc = APP.test_client()
        self.pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        prof = self.pc.get("/api/my/profile").get_json()["data"]["profile"]
        self.pid = prof["id"]

    def _upload(self, hint="杂粮饭、清蒸鱼、炒青菜"):
        return self.pc.post(
            f"/api/patients/{self.pid}/diet/photo",
            data={"photo": (make_meal_image(), "meal.jpg"), "meal": "lunch",
                  "hint": hint},
            content_type="multipart/form-data")

    def test_upload_photo_returns_analysis_and_saves_log(self):
        r = self._upload()
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()["data"]
        a = data["analysis"]
        self.assertEqual(a["engine"], "local-color-v1")
        self.assertGreater(a["confidence"], 0.3)
        self.assertTrue(0 <= a["score"] <= 100)
        self.assertEqual(len(a["categories"]), 4)
        self.assertTrue(a["findings"])
        self.assertGreater(a["estimated"]["kcal"], 100)
        self.assertGreater(a["estimated"]["sodium"], 100)
        self.assertTrue(a["suggestions"])
        self.assertEqual(data["meal"], "lunch")

        d = self.pc.get(f"/api/patients/{self.pid}/diet").get_json()["data"]
        row = [l for l in d["logs"] if l["id"] == data["id"]][0]
        self.assertTrue(row["has_photo"])
        self.assertEqual(row["source"], "photo")
        self.assertTrue(row["image_url"])
        self.assertGreaterEqual(d["summary"]["photo_days"], 1)
        # 照片可通过鉴权接口取回
        img = self.pc.get(row["image_url"])
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img.mimetype, "image/jpeg")
        self.pc.delete(f"/api/patients/{self.pid}/diet/logs/{data['id']}")

    def test_rejects_non_image(self):
        with open(__file__, "rb") as fh:
            r = self.pc.post(
                f"/api/patients/{self.pid}/diet/photo",
                data={"photo": (fh, "note.txt"), "meal": "lunch"},
                content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_requires_meal(self):
        r = self.pc.post(
            f"/api/patients/{self.pid}/diet/photo",
            data={"photo": (make_meal_image(), "meal.jpg")},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_patient_cannot_upload_for_others(self):
        other = 1 if self.pid != 1 else 2
        r = self.pc.post(
            f"/api/patients/{other}/diet/photo",
            data={"photo": (make_meal_image(), "meal.jpg"), "meal": "lunch"},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 403)

    def test_photo_visible_to_doctor_with_json(self):
        r = self._upload("米饭、红烧肉、炒青菜")
        lid = r.get_json()["data"]["id"]
        d = self.c.get(f"/api/patients/{self.pid}/diet").get_json()["data"]
        row = [l for l in d["logs"] if l["id"] == lid][0]
        self.assertIsInstance(row["analysis"], dict)
        self.assertIn("findings", row["analysis"])
        self.c.delete(f"/api/patients/{self.pid}/diet/logs/{lid}")


class TestDeviceScope(Base):
    def setUp(self):
        self.pc = APP.test_client()
        self.pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        self.pid = self.pc.get("/api/my/profile").get_json()["data"]["profile"]["id"]

    def test_patient_sees_only_own_devices(self):
        d = self.pc.get("/api/devices").get_json()["data"]
        self.assertEqual(d["summary"]["mode"], "patient")
        self.assertGreaterEqual(len(d["items"]), 1)
        self.assertTrue(all(x["patient_id"] == self.pid for x in d["items"]))
        doc = self.c.get("/api/devices").get_json()["data"]
        self.assertEqual(doc["summary"]["mode"], "staff")
        self.assertGreaterEqual(len(doc["items"]), len(d["items"]))

    def test_patient_create_device_binds_self(self):
        r = self.pc.post("/api/devices", json={
            "device_sn": "MB-TEST-P1", "name": "测试血氧仪", "patient_id": 99})
        self.assertEqual(r.status_code, 200, r.get_json())
        did = r.get_json()["data"]["id"]
        row = self.pc.get("/api/devices").get_json()["data"]["items"]
        mine = [x for x in row if x["id"] == did][0]
        self.assertEqual(mine["patient_id"], self.pid)
        self.pc.delete(f"/api/devices/{did}")

    def test_patient_cannot_touch_others_device(self):
        doc_devices = self.c.get("/api/devices").get_json()["data"]["items"]
        other = [x for x in doc_devices if x["patient_id"] != self.pid]
        self.assertTrue(other)
        did = other[0]["id"]
        self.assertEqual(self.pc.put(f"/api/devices/{did}", json={"name": "改个名"}).status_code, 403)
        self.assertEqual(self.pc.post(f"/api/devices/{did}/simulate", json={}).status_code, 403)
        self.assertEqual(self.pc.get(f"/api/devices/{did}/readings").status_code, 403)
        self.assertEqual(self.pc.delete(f"/api/devices/{did}").status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
