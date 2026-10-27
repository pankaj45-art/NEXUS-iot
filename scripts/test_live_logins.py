import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

base_url = "https://libraries-cow-moderators-bloomberg.trycloudflare.com"

def test_login(email, password):
    url = base_url + "/api/auth/login"
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            user = data.get("user", {})
            ent = data.get("entitlement", {})
            print(f"[SUCCESS] {email} | Name: {user.get('name')} | Role: {user.get('role')} | Tier: {ent.get('tier')} | Plan: {ent.get('plan')}")
    except Exception as e:
        print(f"[FAILED] {email}: {e}")

if __name__ == "__main__":
    test_login("admin@nexus.local", "PankajAdmin2026!x")
    test_login("pro@nexus.local", "ProUser2026!x")
    test_login("free@nexus.local", "FreeUser2026!x")
