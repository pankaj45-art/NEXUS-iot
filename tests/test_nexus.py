"""NEXUS IoT integration + content-quality tests.

Run from the project root:

    python3 -m unittest discover -s tests -v
    # or: pytest -q tests

Tests use an isolated temporary SQLite database; they never touch the running
application's data.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus import ai, api, billing, config, db, diagram, export, seed, tools  # noqa: E402
from nexus.compiler import compile_spec  # noqa: E402
from nexus.data import ALL_SPECS, CATEGORY_ORDER, validate_specs  # noqa: E402
from nexus import hardware  # noqa: E402
from nexus.security import json_dumps, pbkdf2  # noqa: E402


class FakeHandler:
    client_address = ("127.0.0.1", 5555)


def call(method, path, body=None, session=None, extra=None, raw=None, csrf=True):
    """Exercise the real API dispatcher without a socket."""
    split = urlsplit(path)
    headers = {"Host": "localhost", "Content-Type": "application/json",
               "X-Forwarded-For": "127.0.0.1"}
    if session:
        cookies = "; ".join(f"{k}={v}" for k, v in session.items() if v)
        headers["Cookie"] = cookies
        if csrf and session.get("nexus_csrf"):
            headers["X-CSRF-Token"] = session["nexus_csrf"]
    headers.update(extra or {})
    payload = raw if raw is not None else (json_dumps(body).encode() if body is not None else b"")
    ctx = api.Context(FakeHandler(), method, split.path, split.query, payload, headers)
    try:
        status, resp_headers, data = api.dispatch(ctx)
    finally:
        ctx.close()
    out = session if session is not None else {}
    setc = resp_headers.get("Set-Cookie", [])
    if isinstance(setc, str):
        setc = [setc]
    for line in setc:
        first = line.split(";", 1)[0]
        if "=" in first:
            k, v = first.split("=", 1)
            if "Max-Age=0" in line:
                out.pop(k, None)
            else:
                out[k] = v
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        parsed = data.decode("utf-8", "replace")
    return status, resp_headers, parsed, out


class NexusTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.real_db_path = config.DB_PATH
        config.DB_PATH = Path(cls.tmp.name) / "test.db"
        db.init_db()
        conn = db.connect()
        cls.seed_result = seed.seed_projects(conn)
        now = time.time()
        conn.execute("INSERT INTO users(email,name,password_hash,role,created_at,updated_at) "
                     "VALUES (?,?,?, 'admin', ?,?)",
                     ("admin@test.local", "Admin", pbkdf2("AdminPass2026!x"), now, now))
        cls.admin_id = conn.execute("SELECT id FROM users WHERE email='admin@test.local'").fetchone()["id"]
        conn.execute("INSERT INTO subscriptions(user_id,plan,status,provider,created_at,updated_at) "
                     "VALUES (?, 'free', 'inactive', 'manual', ?, ?)", (cls.admin_id, now, now))
        conn.close()

    @classmethod
    def tearDownClass(cls):
        config.DB_PATH = cls.real_db_path
        cls.tmp.cleanup()

    def register(self, email):
        status, _, data, sess = call("POST", "/api/auth/register",
                                     {"email": email, "name": "Tester", "password": "FreePass2026!x"})
        self.assertEqual(status, 201, data)
        return sess

    def admin(self):
        status, _, data, sess = call("POST", "/api/auth/login",
                                     {"email": "admin@test.local", "password": "AdminPass2026!x"})
        self.assertEqual(status, 200, data)
        return sess

    # ----------------------------------------------------------------- basic
    def test_01_public_config_and_health(self):
        s, _, d, _ = call("GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertEqual(d["status"], "ok")
        s, _, d, _ = call("GET", "/api/config/public")
        self.assertEqual(s, 200)
        self.assertEqual(d["library"]["total_published"], len(ALL_SPECS))
        self.assertEqual(d["library"]["free_projects"], 15)
        self.assertEqual(len(d["library"]["categories"]), len(CATEGORY_ORDER))
        self.assertFalse(d["payments"]["configured"])
        self.assertFalse(d["ai"]["configured"])
        self.assertIn("not configured", d["ai"]["message"].lower())
        self.assertGreaterEqual(len(d["permission_matrix"]), 25)

    def test_02_frontend_is_served(self):
        server_source = (ROOT / "nexus" / "server.py").read_text(encoding="utf-8")
        self.assertIn("Content-Security-Policy", server_source)
        html = (config.WEB_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("app.js", html)
        js_path = config.WEB_DIR / "app.js"
        self.assertTrue(js_path.exists())
        js = js_path.read_text(encoding="utf-8")
        # No bare API navigation: exports/diagrams must use the authenticated
        # fetch path or a 401 JSON body will be shown instead of the content.
        self.assertNotIn('href="/api/', js)
        self.assertNotIn('src="/api/', js)
        self.assertIn("sessionFetch", js)
        self.assertIn("openExport", js)
        self.assertIn("hydrateDiagrams", js)
        # Build 10 visual upgrade: a real local SVG wallpaper and contextual
        # guides are served by the same-origin app, with no third-party asset.
        self.assertIn('id="help-guide"', js)
        self.assertNotIn("admin@nexus.local", js)
        self.assertNotIn("AdminPass2026!x", js)
        self.assertNotIn('id="a-demo"', js)
        self.assertIn("function openHelpGuide()", js)
        self.assertIn("HELP_GUIDES", js)
        self.assertIn("guide-path", js)
        css = (config.WEB_DIR / "app.css").read_text(encoding="utf-8")
        self.assertIn("/engineering-wallpaper.svg", css)
        self.assertIn("nexus-aura-breathe", css)
        wallpaper = config.WEB_DIR / "engineering-wallpaper.svg"
        self.assertTrue(wallpaper.exists())
        import xml.etree.ElementTree as ET
        self.assertEqual(ET.parse(wallpaper).getroot().tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("v=13", html)
        neural = (config.WEB_DIR / "neural-wallpaper.js").read_text(encoding="utf-8")
        self.assertIn("startNeuralWallpaper", neural)
        self.assertIn("prefers-reduced-motion", neural)

    def test_03_cookieless_preview_session_fallback(self):
        """Embedded previews may block cookies; the same server-side session must
        still authenticate via a bearer token, with CSRF and revocation intact."""
        s, h, d, _ = call("POST", "/api/auth/login",
                          {"email": "admin@test.local", "password": "AdminPass2026!x"},
                          extra={"X-Forwarded-Proto": "https", "Host": "8000-demo.e2b.app"})
        self.assertEqual(s, 200, d)
        token, csrf = d["session_token"], d["csrf"]
        self.assertTrue(token and csrf)
        self.assertTrue(d["signed_cookie"].startswith(token))
        self.assertTrue(d["session"]["authenticated"])
        self.assertEqual(d["session"]["user"]["role"], "admin")
        self.assertIn("usage", d["session"])
        self.assertEqual(d["config"]["library"]["total_published"], len(ALL_SPECS))
        self.assertIn("build", d["config"])
        setc = " ".join(h.get("Set-Cookie", []))
        self.assertIn("SameSite=None", setc)
        self.assertIn("Secure", setc)
        bearer = {"Authorization": "Bearer " + token}
        s, _, d, _ = call("GET", "/api/auth/me", extra=bearer)
        self.assertEqual(s, 200)
        self.assertTrue(d["authenticated"])
        self.assertEqual(d["user"]["role"], "admin")
        s, _, d, _ = call("GET", "/api/admin/overview", extra=bearer)
        self.assertEqual(s, 200, d)
        # CSRF still applies to state-changing requests using the fallback.
        s, _, d, _ = call("POST", "/api/profile", {"name": "No Cookies"}, extra=bearer)
        self.assertEqual(s, 403, d)
        s, _, d, _ = call("POST", "/api/profile", {"name": "No Cookies"},
                          extra={**bearer, "X-CSRF-Token": csrf})
        self.assertEqual(s, 200, d)
        # A random token cannot impersonate anyone.
        s, _, d, _ = call("GET", "/api/auth/me", extra={"Authorization": "Bearer " + "x" * 40})
        self.assertFalse(d["authenticated"])
        # Revocation invalidates the fallback too.
        s, _, d, _ = call("POST", "/api/auth/logout", {},
                          extra={**bearer, "X-CSRF-Token": csrf})
        self.assertEqual(s, 200, d)
        s, _, d, _ = call("GET", "/api/auth/me", extra=bearer)
        self.assertFalse(d["authenticated"])

    def test_04_query_transport_fallback(self):
        """A preview proxy may strip Authorization and block cookies entirely."""
        s, _, d, _ = call("POST", "/api/auth/login",
                          {"email": "admin@test.local", "password": "AdminPass2026!x"})
        self.assertEqual(s, 200, d)
        token, csrf = d["session_token"], d["csrf"]
        # No cookie, no header: unauthenticated.
        s, _, d2, _ = call("GET", "/api/projects")
        self.assertEqual(s, 401, d2)
        # Query token restores the same server-side session.
        s, _, d2, _ = call("GET", "/api/projects?nx_session=" + token)
        self.assertEqual(s, 200, d2)
        s, _, d2, _ = call("GET", "/api/admin/overview?nx_session=" + token)
        self.assertEqual(s, 200, d2)
        # CSRF can ride in the body when headers are stripped.
        s, _, d2, _ = call("POST", "/api/profile?nx_session=" + token,
                          {"name": "Query Session", "nx_csrf": csrf})
        self.assertEqual(s, 200, d2)
        # A forged token is refused.
        s, _, d2, _ = call("GET", "/api/projects?nx_session=" + "z" * 40)
        self.assertEqual(s, 401, d2)
        call("POST", "/api/auth/logout?nx_session=" + token, {"nx_csrf": csrf})

    # ------------------------------------------------------------- entitlement
    def test_10_free_visibility_is_enforced_server_side(self):
        sess = self.register("free1@test.local")
        s, _, d, _ = call("GET", "/api/projects", session=sess)
        self.assertEqual(s, 200)
        self.assertEqual(d["total"], 15)
        self.assertEqual(d["locked_count"], len(ALL_SPECS) - 15)
        for item in d["items"]:
            self.assertTrue(item["is_free"])
        conn = db.connect()
        pro_slug = conn.execute("SELECT slug FROM projects WHERE is_free=0 LIMIT 1").fetchone()["slug"]
        conn.close()
        s, _, d, _ = call("GET", "/api/projects/" + pro_slug, session=sess)
        self.assertEqual(s, 403)
        self.assertEqual(d["error"]["code"], "upgrade_required")
        # No protected fields leak in the error.
        self.assertNotIn("content", json.dumps(d))
        for suffix in ("", "/diagram.svg", "/download?kind=code", "/download?kind=json"):
            s, _, _, _ = call("GET", "/api/projects/" + pro_slug + suffix, session=sess)
            self.assertEqual(s, 403, suffix)
        # Searching for a Pro title returns nothing for a free account.
        conn = db.connect()
        title = conn.execute("SELECT title FROM projects WHERE slug=?", (pro_slug,)).fetchone()["title"]
        conn.close()
        s, _, d, _ = call("GET", "/api/projects?q=" + title.replace(" ", "%20"), session=sess)
        self.assertEqual(d["total"], 0)

    def test_11_profile_cannot_self_promote(self):
        sess = self.register("free2@test.local")
        s, _, d, _ = call("POST", "/api/profile", {"name": "Hacker", "role": "admin",
                                                   "plan": "pro", "status": "active"}, session=sess)
        self.assertEqual(s, 200)
        s, _, d, _ = call("GET", "/api/auth/me", session=sess)
        self.assertEqual(d["entitlement"]["role"], "free")
        self.assertEqual(d["entitlement"]["tier"], "free")
        self.assertNotIn("library.all", d["entitlement"]["features"])
        a = self.admin()
        s, _, d, _ = call("GET", "/api/admin/audit", session=a)
        self.assertTrue(any("privilege_escalation" in x["action"] for x in d["logs"]))

    def test_12_free_cannot_use_admin_or_pro_tools(self):
        sess = self.register("free3@test.local")
        for path in ("/api/admin/overview", "/api/admin/projects", "/api/admin/users", "/api/admin/config"):
            s, _, _, _ = call("GET", path, session=sess)
            self.assertEqual(s, 403, path)
        s, _, _, _ = call("POST", "/api/tools/circuit_designer", {"board": "esp32"}, session=sess)
        self.assertEqual(s, 403)
        s, _, _, _ = call("POST", "/api/billing/checkout", {}, session=sess)
        self.assertEqual(s, 409)  # payments not configured, never pretends a payment
        s, _, d, _ = call("POST", "/api/assistant", {"question": "How do I wire a DHT22?"}, session=sess)
        self.assertEqual(s, 503)  # new policy: no fabricated/offline chat answer
        self.assertEqual(d["error"]["code"], "provider_not_configured")
        self.assertNotIn("result", d)

    def test_13_expiry_and_cancellation_remove_pro(self):
        sess = self.register("expiry@test.local")
        conn = db.connect()
        uid = conn.execute("SELECT id FROM users WHERE email='expiry@test.local'").fetchone()["id"]
        conn.close()
        a = self.admin()
        s, _, d, _ = call("PATCH", f"/api/admin/users/{uid}", {"grant_pro": True, "days": 30}, session=a)
        self.assertEqual(s, 200)
        s, _, d, _ = call("GET", "/api/projects", session=sess)
        self.assertEqual(d["total"], len(ALL_SPECS))
        conn = db.connect()
        conn.execute("UPDATE subscriptions SET expires_at=? WHERE user_id=?", (time.time() - 10, uid))
        conn.close()
        s, _, d, _ = call("GET", "/api/auth/me", session=sess)
        self.assertEqual(d["entitlement"]["tier"], "free")
        self.assertEqual(d["entitlement"]["subscription_status"], "expired")
        s, _, d, _ = call("GET", "/api/projects", session=sess)
        self.assertEqual(d["total"], 15)
        # Personal data survives.
        s, _, d, _ = call("POST", "/api/workspaces", {"name": "Kept workspace"}, session=sess)
        self.assertEqual(s, 201)

    def test_14_pro_is_not_admin(self):
        sess = self.register("pro@test.local")
        conn = db.connect()
        uid = conn.execute("SELECT id FROM users WHERE email='pro@test.local'").fetchone()["id"]
        conn.close()
        a = self.admin()
        call("PATCH", f"/api/admin/users/{uid}", {"grant_pro": True, "days": 30}, session=a)
        s, _, d, _ = call("GET", "/api/auth/me", session=sess)
        self.assertEqual(d["entitlement"]["tier"], "pro")
        self.assertFalse(d["entitlement"]["is_admin"])
        s, _, _, _ = call("GET", "/api/admin/overview", session=sess)
        self.assertEqual(s, 403)
        s, _, _, _ = call("PATCH", f"/api/admin/users/{uid}", {"role": "admin"}, session=sess)
        self.assertEqual(s, 403)

    def test_15_user_settings_are_private_and_validated(self):
        sess = self.register("settings@test.local")
        s, _, d, _ = call("GET", "/api/settings", session=sess)
        self.assertEqual(s, 200)
        self.assertEqual(d["settings"]["units"], "metric")
        s, _, d, _ = call("PATCH", "/api/settings",
                          {"units": "imperial", "default_board": "picow", "theme": "light",
                           "notifications": False, "role": "admin", "plan": "pro"}, session=sess)
        self.assertEqual(s, 200)
        self.assertEqual(d["settings"]["units"], "imperial")
        self.assertEqual(d["settings"]["default_board"], "picow")
        self.assertFalse(d["settings"]["notifications"])
        self.assertNotIn("role", d["settings"])
        s, _, d, _ = call("GET", "/api/auth/me", session=sess)
        self.assertEqual(d["entitlement"]["role"], "free")
        s, _, _, _ = call("PATCH", "/api/settings", {"units": "furlongs"}, session=sess)
        self.assertEqual(s, 400)
        other = self.register("settings2@test.local")
        s, _, d, _ = call("GET", "/api/settings", session=other)
        self.assertEqual(d["settings"]["units"], "metric")

    def test_16_learning_module_and_project_creation_limit(self):
        sess = self.register("learn@test.local")
        s, _, d, _ = call("GET", "/api/learning", session=sess)
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(d["modules"]), 5)
        known = {r["url"] for r in hardware.REFERENCES}
        for module in d["modules"]:
            self.assertTrue(module["quiz"]["q"])
            for ref in module["refs"]:
                self.assertIn(ref, known)
        for i in range(3):
            s, _, _, _ = call("POST", "/api/workspaces", {"name": f"WS {i}"}, session=sess)
            self.assertEqual(s, 201)
        s, _, d, _ = call("POST", "/api/workspaces", {"name": "WS 4"}, session=sess)
        self.assertEqual(s, 429)  # free projects_created_total = 3
        self.assertEqual(d["error"]["code"], "limit_reached")
        s, _, d, _ = call("GET", "/api/usage", session=sess)
        self.assertEqual(d["usage"]["workspace_items"]["used"], 3)
        self.assertEqual(d["usage"]["projects_created_total"]["used"], 3)

    # ---------------------------------------------------------------- payments
    def test_20_webhook_requires_valid_signature(self):
        secret = "whsec_test_secret"
        old = (config.STRIPE_SECRET_KEY, config.STRIPE_WEBHOOK_SECRET, config.STRIPE_PRICE_ID)
        config.STRIPE_SECRET_KEY, config.STRIPE_WEBHOOK_SECRET, config.STRIPE_PRICE_ID = "sk_test_x", secret, "price_test"
        conn = db.connect()
        platform = db.get_setting(conn, "platform", {})
        platform["payments"]["provider"] = "stripe"
        db.set_setting(conn, "platform", platform)
        conn.close()
        try:
            payload = json_dumps({"type": "checkout.session.completed", "data": {"object": {
                "client_reference_id": "999999", "payment_status": "paid",
                "customer": "cus_test", "subscription": "sub_test"}}}).encode()
            s, _, d, _ = call("POST", "/api/billing/webhook", raw=payload,
                              extra={"Stripe-Signature": "t=1,v1=deadbeef"})
            self.assertEqual(s, 400)
            ts = str(int(time.time()))
            sig = hmac.new(secret.encode(), (ts + ".").encode() + payload, hashlib.sha256).hexdigest()
            s, _, d, _ = call("POST", "/api/billing/webhook", raw=payload,
                              extra={"Stripe-Signature": f"t={ts},v1={sig}"})
            self.assertEqual(s, 200, d)
            self.assertTrue(d["received"])
            # A front-end success redirect never grants access.
            sess = self.register("redirect@test.local")
            s, _, d, _ = call("GET", "/api/auth/me", session=sess)
            self.assertEqual(d["entitlement"]["tier"], "free")
        finally:
            config.STRIPE_SECRET_KEY, config.STRIPE_WEBHOOK_SECRET, config.STRIPE_PRICE_ID = old
            conn = db.connect()
            platform = db.get_setting(conn, "platform", {})
            platform["payments"]["provider"] = "none"
            db.set_setting(conn, "platform", platform)
            conn.close()

    # ------------------------------------------------------------------ admin
    def test_30_admin_project_lifecycle(self):
        a = self.admin()
        s, _, d, _ = call("POST", "/api/admin/projects", {"slug": "qa-draft", "title": "QA Draft",
                                                          "summary": "A test draft", "parts": ["bme280"],
                                                          "board": "esp32", "comms": "wifi_mqtt"}, session=a)
        self.assertEqual(s, 201, d)
        pid = d["id"]
        s, _, d, _ = call("POST", f"/api/admin/projects/{pid}/action", {"action": "publish"}, session=a)
        self.assertEqual(s, 409)  # quality gate
        s, _, d, _ = call("POST", f"/api/admin/projects/{pid}/action",
                          {"action": "quality", "quality_status": "Technically reviewed"}, session=a)
        self.assertEqual(s, 200)
        s, _, d, _ = call("POST", f"/api/admin/projects/{pid}/action", {"action": "publish"}, session=a)
        self.assertEqual(s, 200)
        s, _, d, _ = call("POST", f"/api/admin/projects/{pid}/action", {"action": "duplicate"}, session=a)
        self.assertEqual(s, 200)
        copy_id = d["new_id"]
        call("DELETE", f"/api/admin/projects/{copy_id}", session=a)
        call("DELETE", f"/api/admin/projects/{pid}", session=a)

    def test_31_free_designation_reorder(self):
        a = self.admin()
        s, _, d, _ = call("GET", "/api/admin/free-projects", session=a)
        slugs = [x["slug"] for x in d["designated"]]
        self.assertEqual(len(slugs), 15)
        slugs[0], slugs[1] = slugs[1], slugs[0]
        s, _, d, _ = call("PUT", "/api/admin/free-projects", {"slugs": slugs}, session=a)
        self.assertEqual(s, 200)
        s, _, d, _ = call("GET", "/api/admin/free-projects", session=a)
        self.assertEqual([x["slug"] for x in d["designated"]], slugs)
        s, _, _, _ = call("PUT", "/api/admin/free-projects", {"slugs": slugs + ["extra"]}, session=a)
        self.assertEqual(s, 400)

    def test_32_admin_config_never_returns_secrets(self):
        a = self.admin()
        s, _, d, _ = call("PATCH", "/api/admin/config",
                          {"ai": {"provider": "offline", "api_key": "sk-super-secret-1234567890"}}, session=a)
        self.assertEqual(s, 200)
        s, _, d, _ = call("GET", "/api/admin/config", session=a)
        text = json.dumps(d)
        self.assertNotIn("sk-super-secret-1234567890", text)
        self.assertNotIn("api_key_encrypted", text)
        self.assertIn("hint", text)

    def test_33_admin_categories_tags_and_analytics(self):
        a = self.admin()
        s, _, d, _ = call("GET", "/api/admin/config", session=a)
        original = d["categories"]
        self.assertEqual(len(original), 25)
        renamed = list(original)
        renamed[0] = "Renamed Category QA"
        s, _, d, _ = call("PATCH", "/api/admin/config", {"categories": renamed}, session=a)
        self.assertEqual(s, 200)
        s, _, d, _ = call("GET", "/api/categories")
        self.assertEqual(d["categories"][0]["name"], "Renamed Category QA")
        call("PATCH", "/api/admin/config", {"categories": original}, session=a)
        # Tags on a project
        conn = db.connect()
        pid = conn.execute("SELECT id FROM projects WHERE slug='esp32-led-control'").fetchone()["id"]
        conn.close()
        s, _, d, _ = call("PATCH", f"/api/admin/projects/{pid}", {"tags": ["qa", "beginner"]}, session=a)
        self.assertEqual(s, 200)
        conn = db.connect()
        tags = json.loads(conn.execute("SELECT tags FROM projects WHERE id=?", (pid,)).fetchone()["tags"])
        conn.close()
        self.assertEqual(tags, ["qa", "beginner"])
        # Analytics records real project views
        sess = self.register("views@test.local")
        call("GET", "/api/projects/esp32-led-control", session=sess)
        call("GET", "/api/projects/dht22-temperature-humidity", session=sess)
        s, _, d, _ = call("GET", "/api/admin/analytics", session=a)
        self.assertEqual(s, 200)
        self.assertGreaterEqual(d["total_project_views"], 2)
        self.assertTrue(any(x["slug"] == "esp32-led-control" for x in d["top_projects"]))

    # ------------------------------------------------------------------- tools
    def test_40_all_pro_tools_work_offline(self):
        sess = self.register("protools@test.local")
        conn = db.connect()
        uid = conn.execute("SELECT id FROM users WHERE email='protools@test.local'").fetchone()["id"]
        conn.close()
        call("PATCH", f"/api/admin/users/{uid}", {"grant_pro": True, "days": 30}, session=self.admin())
        cases = {
            "project_generator": {"problem": "Remote greenhouse tank level", "components": "ESP32, ultrasonic, LoRa"},
            "circuit_designer": {"board": "esp32", "components": "bme280, relay, oled"},
            "code_engineer": {"mode": "review", "platform": "esp32", "code": "void setup(){delay(5000);}"},
            "debugging": {"error": "Guru Meditation Error: Core 1 panic", "session_key": "qa"},
            "innovation": {"topic": "LoRa duty cycle"},
            "comparison": {"items": [{"name": "A", "cost": 4}, {"name": "B", "cost": 7}]},
            "startup_lab": {"industry": "agriculture", "problem": "water waste"},
            "research": {"query": "ESP32 ADC2 I2C"},
            "device_monitoring": {"action": "status"},
            "project_docs": {"action": "report"},
        }
        for name, body in cases.items():
            with self.subTest(tool=name):
                s, _, d, _ = call("POST", "/api/tools/" + name, body, session=sess)
                self.assertEqual(s, 200, (name, d))
                self.assertEqual(d["result"]["mode"], "offline")
                self.assertIn("run_id", d["result"])
        s, _, d, _ = call("GET", "/api/tools/runs", session=sess)
        self.assertGreaterEqual(len(d["runs"]), 10)

    def test_41_debugging_does_not_repeat_failed_fixes(self):
        sess = self.register("debug@test.local")
        conn = db.connect()
        uid = conn.execute("SELECT id FROM users WHERE email='debug@test.local'").fetchone()["id"]
        conn.close()
        call("PATCH", f"/api/admin/users/{uid}", {"grant_pro": True, "days": 30}, session=self.admin())
        body = {"error": "Guru Meditation Error: Core 1 panic", "session_key": "pump-1",
                "record_fix": "Check the 3.3 V rail with an oscilloscope during actuator/Wi-Fi activity",
                "outcome": "failed"}
        call("POST", "/api/tools/debugging", body, session=sess)
        s, _, d, _ = call("POST", "/api/tools/debugging",
                          {"error": "Guru Meditation Error: Core 1 panic", "session_key": "pump-1"}, session=sess)
        self.assertEqual(s, 200)
        self.assertGreater(d["result"]["attempts_tracked"], 0)
        diag = d["result"]["diagnoses"][0]
        self.assertTrue(diag["previously_tried"])
        self.assertNotIn(body["record_fix"], diag["fixes"])

    def test_42_device_ingest_labels_real_vs_simulated(self):
        sess = self.register("devices@test.local")
        conn = db.connect()
        uid = conn.execute("SELECT id FROM users WHERE email='devices@test.local'").fetchone()["id"]
        conn.close()
        call("PATCH", f"/api/admin/users/{uid}", {"grant_pro": True, "days": 30}, session=self.admin())
        s, _, d, _ = call("POST", "/api/devices", {"name": "Node A"}, session=sess)
        self.assertEqual(s, 201)
        token, did = d["token"], d["id"]
        s, _, d, _ = call("POST", "/api/ingest/" + token,
                          {"samples": [{"key": "temp", "value": 22.5, "unit": "C"}]})
        self.assertEqual(s, 200, d)
        self.assertEqual(d["source"], "real")
        s, _, d, _ = call("POST", "/api/tools/device_monitoring",
                          {"action": "simulate", "device_id": did}, session=sess)
        self.assertEqual(s, 200)
        self.assertEqual(len(d["result"]["simulated_series"]), 30)
        self.assertTrue(all(x["source"] == "simulated" for x in d["result"]["simulated_series"]))
        s, _, d, _ = call("GET", f"/api/telemetry/{did}", session=sess)
        self.assertTrue(any(x["source"] == "real" for x in d["samples"]))
        self.assertTrue(any(x["source"] == "simulated" for x in d["samples"]))

    # -------------------------------------------------------- content quality
    def test_50_library_specs_are_unique_and_complete(self):
        self.assertEqual(validate_specs(), [])
        self.assertGreaterEqual(len(ALL_SPECS), 100)
        self.assertEqual(len({s["slug"] for s in ALL_SPECS}), len(ALL_SPECS))
        self.assertEqual(len({s["title"] for s in ALL_SPECS}), len(ALL_SPECS))
        self.assertEqual(sum(1 for s in ALL_SPECS if s.get("free")), 15)
        cats = {s["category"] for s in ALL_SPECS}
        self.assertEqual(cats, set(CATEGORY_ORDER))
        diffs = {s["difficulty"] for s in ALL_SPECS}
        self.assertEqual(diffs, {"Beginner", "Intermediate", "Advanced"})

    def test_51_every_project_has_all_sections_and_valid_circuit(self):
        required = {"overview", "bom", "architecture", "circuit", "procedure", "code",
                    "troubleshooting", "testing", "deliverables", "quality"}
        for s in ALL_SPECS:
            with self.subTest(project=s["slug"]):
                c = compile_spec(s)
                self.assertTrue(required.issubset(c.keys()))
                self.assertTrue(c["circuit"]["validation"]["passed"])
                self.assertGreaterEqual(len(c["bom"]["mandatory"]), 2)
                self.assertGreaterEqual(len(c["procedure"]), 18)
                self.assertGreaterEqual(len(c["testing"]["functional_tests"]), 3)
                self.assertIn("NOT hardware-tested", c["code"]["status"])
                self.assertFalse(c["quality"]["physical_test_confirmed"])
                self.assertGreater(len(c["deliverables"]["references"]), 3)

    def test_52_firmware_is_consistent_and_has_no_real_credentials(self):
        import re
        for s in ALL_SPECS:
            with self.subTest(project=s["slug"]):
                c = compile_spec(s)
                code = c["code"]["code"]
                self.assertNotRegex(code, r"@[A-Z0-9_]+@")
                self.assertNotRegex(code, r'(?:ssid|password|token|api_key)\s*=\s*"(?!YOUR_)[A-Za-z0-9_\-]{8,}"')
                if s["comms"].startswith("wifi") and c["code"]["language"].startswith("Arduino"):
                    self.assertIn("YOUR_WIFI_SSID", code)
                if c["code"]["language"].startswith("Python"):
                    compile(code, "<generated>", "exec")
                else:
                    self.assertEqual(code.count("{"), code.count("}"))
                    self.assertEqual(code.count("("), code.count(")"))
                # Every numeric GPIO macro in the firmware must come from the
                # same pin assignment that produced the wiring table.
                if c["code"]["language"].startswith("Arduino"):
                    assigned = {str(v) for roles in c["meta"]["pins"].values() for v in roles.values()}
                    for m in re.finditer(r"#define\s+\w+\s+([0-9]+)\s*(?:;|$|\r)", code):
                        self.assertIn(m.group(1), assigned)
        # References come only from the curated real documentation corpus,
        # board/part/transport documentation in the catalog, or the spec.
        known = {r["url"] for r in hardware.REFERENCES}
        known |= {p["docs"] for p in hardware.PARTS.values() if p.get("docs")}
        known |= {b["docs"] for b in hardware.BOARDS.values() if b.get("docs")}
        known |= {d["docs"] for d in __import__("nexus.codegen", fromlist=["COMMS"]).COMMS.values()}
        known |= {r for s in ALL_SPECS for r in s.get("refs", [])}
        for s in ALL_SPECS:
            for ref in compile_spec(s)["deliverables"]["references"]:
                self.assertIn(ref["url"], known)

    def test_53_diagram_and_exports_are_generated(self):
        c = compile_spec(ALL_SPECS[0])
        svg = diagram.render_svg(c)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("</svg>", svg)
        for kind in ("markdown", "code", "json", "wiring", "bom", "svg"):
            name, ctype, data = export.render_download(c, kind)
            self.assertTrue(data)
            self.assertTrue(name.startswith(c["slug"]))

    def test_54_ai_corpus_never_invents_citations(self):
        refs = ai.references_for("I2C pull-ups ESP32 ADC2", 10)
        known = {r["url"] for r in hardware.REFERENCES}
        self.assertTrue(all(r["url"] in known for r in refs))
        self.assertTrue(all(r["url"].startswith("https://") for r in refs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
