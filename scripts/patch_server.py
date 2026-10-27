import os

server_path = r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\nexus\server.py"
with open(server_path, "r", encoding="utf-8") as f:
    c = f.read()

target = """def main():
    db.init_db()
    conn = db.connect()
    try:
        from .services.jobs import recover
        recover(conn)
        result = seed.seed_projects(conn)
        print(f"[NEXUS] Library: {result['total']} specs; inserted {result['inserted']}, "
              f"skipped {result['skipped']} (existing records preserved).", flush=True)
    finally:
        conn.close()"""

replacement = """def ensure_admin(conn):
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
        print(f"[NEXUS] Existing Super Admin verified: {row['email']}", flush=True)

def main():
    db.init_db()
    conn = db.connect()
    try:
        from .services.jobs import recover
        recover(conn)
        result = seed.seed_projects(conn)
        print(f"[NEXUS] Library: {result['total']} specs; inserted {result['inserted']}, "
              f"skipped {result['skipped']} (existing records preserved).", flush=True)
        ensure_admin(conn)
    finally:
        conn.close()"""

if target in c:
    c = c.replace(target, replacement)
    with open(server_path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Added ensure_admin to nexus/server.py!")
else:
    print("Target not found, might already be updated.")
