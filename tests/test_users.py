"""用户注册与用户管理接口测试（独立临时库）。"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP_DIR = tempfile.mkdtemp(prefix="medbuddy_users_")
import config  # noqa: E402

config.DB_PATH = os.path.join(TMP_DIR, "test.db")

from app import create_app  # noqa: E402
from backend import db  # noqa: E402


class UserApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        with cls.app.app_context():
            cls.c = cls.app.test_client()
            cls.c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            cls.doc = cls.app.test_client()
            cls.doc.post("/api/auth/login", json={"username": "doctor", "password": "doctor123"})

    def tearDown(self):
        with self.app.app_context():
            db.execute("DELETE FROM users WHERE username LIKE 't\\_%' ESCAPE '\\'")
            db.execute("DELETE FROM patients WHERE name LIKE '测试%'")

    # ---------- 权限 ----------
    def test_requires_login(self):
        with self.app.app_context():
            fresh = self.app.test_client()
            self.assertEqual(fresh.get("/api/users").status_code, 401)

    def test_patient_cannot_list_users(self):
        with self.app.app_context():
            pc = self.app.test_client()
            pc.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
            self.assertEqual(pc.get("/api/users").status_code, 403)

    def test_doctor_cannot_access_user_admin(self):
        """用户管理仅对管理员开放，医生访问一律 403。"""
        self.assertEqual(self.doc.get("/api/users").status_code, 403)
        self.assertEqual(self.doc.get("/api/users/options").status_code, 403)
        r = self.doc.post("/api/users", json={
            "username": "t_admin2", "password": "123456", "display_name": "测试医生建号",
            "role": "patient", "patient_id": 1})
        self.assertEqual(r.status_code, 403)

    # ---------- 查询 ----------
    def test_list_users(self):
        r = self.c.get("/api/users")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertGreaterEqual(d["stats"]["total"], 3)
        self.assertGreaterEqual(d["stats"]["doctor"], 1)
        names = [x["username"] for x in d["items"]]
        self.assertIn("doctor", names)
        # 管理员可管理全部账号
        admin_row = [x for x in d["items"] if x["role"] == "admin"][0]
        self.assertTrue(admin_row["manageable"])

    def test_filter_by_role_and_keyword(self):
        d = self.c.get("/api/users?role=patient").get_json()["data"]
        self.assertTrue(all(x["role"] == "patient" for x in d["items"]))
        d2 = self.c.get("/api/users?q=江先亮").get_json()["data"]
        self.assertTrue(any(x["username"] == "doctor" for x in d2["items"]))

    # ---------- 新建 / 编辑 ----------
    def test_create_patient_account(self):
        opts = self.c.get("/api/users/options").get_json()["data"]
        free = [p for p in opts if not p["bound_user"]]
        self.assertTrue(free)
        target = free[0]
        r = self.c.post("/api/users", json={
            "username": "t_patient1", "password": "abc123", "display_name": "测试居民",
            "role": "patient", "patient_id": target["id"], "phone": "13800001111"})
        self.assertEqual(r.status_code, 200, r.get_json())
        d = self.c.get("/api/users?q=t_patient1").get_json()["data"]["items"][0]
        self.assertEqual(d["patient_name"], target["name"])
        self.assertEqual(d["status"], "active")

    def test_create_patient_requires_profile(self):
        r = self.c.post("/api/users", json={
            "username": "t_nobind", "password": "abc123", "display_name": "测试无档案",
            "role": "patient"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("档案", r.get_json()["error"])

    def test_duplicate_username(self):
        r = self.c.post("/api/users", json={
            "username": "doctor", "password": "abc123", "display_name": "测试重复"})
        self.assertEqual(r.status_code, 409)

    def test_bound_profile_conflict(self):
        r = self.c.post("/api/users", json={
            "username": "t_conflict", "password": "abc123", "display_name": "测试冲突",
            "role": "patient", "patient_id": 1})
        self.assertEqual(r.status_code, 400)
        self.assertIn("绑定", r.get_json()["error"])

    def test_update_then_disable_blocks_login(self):
        opts = [p for p in self.c.get("/api/users/options").get_json()["data"]
                if not p["bound_user"]]
        uid = self.c.post("/api/users", json={
            "username": "t_status", "password": "abc123", "display_name": "测试停用",
            "role": "patient", "patient_id": opts[0]["id"]}).get_json()["data"]["id"]
        r = self.c.put("/api/users/%d" % uid, json={
            "display_name": "测试停用改", "role": "patient",
            "patient_id": opts[0]["id"], "status": "disabled"})
        self.assertEqual(r.status_code, 200, r.get_json())
        with self.app.app_context():
            fresh = self.app.test_client()
            bad = fresh.post("/api/auth/login", json={"username": "t_status", "password": "abc123"})
            self.assertEqual(bad.status_code, 403)
            self.assertIn("停用", bad.get_json()["error"])

    def test_reset_password(self):
        opts = [p for p in self.c.get("/api/users/options").get_json()["data"]
                if not p["bound_user"]]
        uid = self.c.post("/api/users", json={
            "username": "t_pwd", "password": "abc123", "display_name": "测试改密",
            "role": "patient", "patient_id": opts[0]["id"]}).get_json()["data"]["id"]
        d = self.c.post("/api/users/%d/password" % uid, json={}).get_json()["data"]
        self.assertEqual(len(d["password"]), 8)
        with self.app.app_context():
            fresh = self.app.test_client()
            ok = fresh.post("/api/auth/login",
                            json={"username": "t_pwd", "password": d["password"]})
            self.assertEqual(ok.status_code, 200)

    def test_cannot_delete_self(self):
        me = self.c.get("/api/auth/me").get_json()["data"]
        r = self.c.delete("/api/users/%d" % me["id"])
        self.assertEqual(r.status_code, 400)

    def test_delete_account(self):
        opts = [p for p in self.c.get("/api/users/options").get_json()["data"]
                if not p["bound_user"]]
        uid = self.c.post("/api/users", json={
            "username": "t_delete", "password": "abc123", "display_name": "测试删除",
            "role": "patient", "patient_id": opts[0]["id"]}).get_json()["data"]["id"]
        self.assertEqual(self.c.delete("/api/users/%d" % uid).status_code, 200)
        self.assertEqual(self.c.put("/api/users/%d" % uid, json={}).status_code, 404)

    # ---------- 注册 ----------
    def test_register_creates_account_and_profile(self):
        with self.app.app_context():
            fresh = self.app.test_client()
            r = fresh.post("/api/auth/register", json={
                "username": "t_reg1", "password": "123456", "name": "测试新居民",
                "phone": "13912340001", "gender": "男", "city": "宁波"})
            self.assertEqual(r.status_code, 200, r.get_json())
            d = r.get_json()["data"]
            self.assertTrue(d["created_profile"])
            self.assertEqual(d["role"], "patient")
            # 注册后已自动登录
            self.assertEqual(fresh.get("/api/auth/me").status_code, 200)
            prof = fresh.get("/api/my/profile")
            self.assertEqual(prof.status_code, 200)
            self.assertEqual(prof.get_json()["data"]["profile"]["name"], "测试新居民")

    def test_register_binds_existing_profile(self):
        with self.app.app_context():
            free = db.query(
                "SELECT p.* FROM patients p LEFT JOIN users u ON u.patient_id=p.id "
                "WHERE u.id IS NULL AND p.name='王卫东'", one=True)
            self.assertIsNotNone(free)
            fresh = self.app.test_client()
            r = fresh.post("/api/auth/register", json={
                "username": "t_reg2", "password": "123456", "name": free["name"],
                "phone": free["phone"]})
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertFalse(r.get_json()["data"]["created_profile"])
            self.assertEqual(r.get_json()["data"]["patient_id"], free["id"])

    def test_register_rejects_bad_phone(self):
        with self.app.app_context():
            fresh = self.app.test_client()
            r = fresh.post("/api/auth/register", json={
                "username": "t_reg3", "password": "123456", "name": "测试坏号码",
                "phone": "12345"})
            self.assertEqual(r.status_code, 400)

    def test_register_rejects_short_password(self):
        with self.app.app_context():
            fresh = self.app.test_client()
            r = fresh.post("/api/auth/register", json={
                "username": "t_reg4", "password": "123", "name": "测试短密码",
                "phone": "13912340004"})
            self.assertEqual(r.status_code, 400)

    def test_register_duplicate_username(self):
        with self.app.app_context():
            fresh = self.app.test_client()
            r = fresh.post("/api/auth/register", json={
                "username": "doctor", "password": "123456", "name": "测试重名",
                "phone": "13912340005"})
            self.assertEqual(r.status_code, 409)

    def test_register_same_name_wrong_phone(self):
        with self.app.app_context():
            fresh = self.app.test_client()
            r = fresh.post("/api/auth/register", json={
                "username": "t_reg5", "password": "123456", "name": "王卫东",
                "phone": "13912340006"})
            self.assertEqual(r.status_code, 409)
            self.assertIn("手机号", r.get_json()["error"])

    # ---------- 管理员 ----------
    def test_admin_can_create_doctor(self):
        with self.app.app_context():
            ac = self.app.test_client()
            ac.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            r = ac.post("/api/users", json={
                "username": "t_doctor1", "password": "abc123", "display_name": "测试医生",
                "role": "doctor", "title": "全科"})
            self.assertEqual(r.status_code, 200, r.get_json())
            d = ac.get("/api/users?q=t_doctor1").get_json()["data"]["items"][0]
            self.assertEqual(d["role"], "doctor")
            self.assertTrue(d["manageable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
