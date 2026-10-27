from pathlib import Path

path = Path(__file__).resolve().parent.parent / "nexus" / "server.py"
content = path.read_text(encoding="utf-8")

old_snippet = """def ensure_admin(conn):
    import time
    from .security import pbkdf2
    email = os.environ.get("NEXUS_ADMIN_EMAIL", "admin@nexus.local").strip().lower()
    password = os.environ.get("NEXUS_ADMIN_PASSWORD", "PankajAdmin2026!x")
    name = os.environ.get("NEXUS_ADMIN_NAME", "Pankaj (Platform Super Admin)")
    now = time.time()
    row = conn.execute("SELECT id, email, role FROM users WHERE role='admin'").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (email, name, pbkdf2(password), "admin", now, now)
        )
        conn.commit()
        print(f"[NEXUS] Bootstrapped Super Admin: {email} ({name})", flush=True)
    else:
        print(f"[NEXUS] Existing Super Admin verified: {row['email']}", flush=True)"""

new_snippet = """def ensure_admin(conn):
    import time
    from .security import pbkdf2
    email = os.environ.get("NEXUS_ADMIN_EMAIL", "admin@nexus.local").strip().lower()
    password = os.environ.get("NEXUS_ADMIN_PASSWORD", "PankajAdmin2026!x")
    name = os.environ.get("NEXUS_ADMIN_NAME", "Pankaj (Platform Super Admin)")
    now = time.time()
    row = conn.execute("SELECT id, email, role FROM users WHERE role='admin'").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (email, name, pbkdf2(password), "admin", now, now)
        )
        print(f"[NEXUS] Bootstrapped Super Admin: {email} ({name})", flush=True)
    else:
        print(f"[NEXUS] Existing Super Admin verified: {row['email']}", flush=True)

    pro = conn.execute("SELECT id FROM users WHERE email='pro@nexus.local'").fetchone()
    if not pro:
        cur = conn.execute(
            "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            ("pro@nexus.local", "Pro IoT Engineer", pbkdf2("ProUser2026!x"), "pro", now, now)
        )
        pro_id = cur.lastrowid
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan, status, provider, started_at, expires_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (pro_id, "pro", "active", "manual", now, now + 86400 * 365, now, now)
        )
        print("[NEXUS] Bootstrapped Pro Demo Account: pro@nexus.local", flush=True)

    free = conn.execute("SELECT id FROM users WHERE email='free@nexus.local'").fetchone()
    if not free:
        conn.execute(
            "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            ("free@nexus.local", "Community Engineer", pbkdf2("FreeUser2026!x"), "free", now, now)
        )
        print("[NEXUS] Bootstrapped Free Demo Account: free@nexus.local", flush=True)

    conn.commit()"""

# Normalize CRLF and LF
content_norm = content.replace("\r\n", "\n")
old_norm = old_snippet.replace("\r\n", "\n")
new_norm = new_snippet.replace("\r\n", "\n")

if old_norm in content_norm:
    content_norm = content_norm.replace(old_norm, new_norm)
    path.write_text(content_norm, encoding="utf-8")
    print("SUCCESS: server.py updated")
else:
    print("WARNING: snippet not matched exactly")
