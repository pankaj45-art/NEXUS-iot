import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus.security import pbkdf2

conn = sqlite3.connect(ROOT / "data" / "nexus.db")
conn.row_factory = sqlite3.Row
now = time.time()

# 1. Ensure Super Admin (Pankaj)
admin = conn.execute("SELECT id FROM users WHERE email='admin@nexus.local'").fetchone()
if not admin:
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("admin@nexus.local", "Pankaj (Platform Super Admin)", pbkdf2("PankajAdmin2026!x"), "admin", now, now)
    )
    admin_id = cur.lastrowid
    print(f"Created Admin (Pankaj): admin@nexus.local (id: {admin_id})")
else:
    admin_id = admin["id"]
    conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (pbkdf2("PankajAdmin2026!x"), now, admin_id))
    print(f"Updated Admin (Pankaj): admin@nexus.local (id: {admin_id})")

# 2. Ensure Pro User
pro = conn.execute("SELECT id FROM users WHERE email='pro@nexus.local'").fetchone()
if not pro:
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("pro@nexus.local", "Pro IoT Engineer", pbkdf2("ProUser2026!x"), "pro", now, now)
    )
    pro_id = cur.lastrowid
    conn.execute(
        "INSERT INTO subscriptions (user_id, plan, status, provider, started_at, expires_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (pro_id, "pro", "active", "manual", now, now + 86400 * 365, now, now)
    )
    print(f"Created Pro User: pro@nexus.local (id: {pro_id})")
else:
    pro_id = pro["id"]
    conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (pbkdf2("ProUser2026!x"), now, pro_id))
    # Ensure active pro subscription
    sub = conn.execute("SELECT id FROM subscriptions WHERE user_id=? AND plan='pro'", (pro_id,)).fetchone()
    if not sub:
        conn.execute(
            "INSERT INTO subscriptions (user_id, plan, status, provider, started_at, expires_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (pro_id, "pro", "active", "manual", now, now + 86400 * 365, now, now)
        )
    else:
        conn.execute("UPDATE subscriptions SET status='active', expires_at=? WHERE id=?", (now + 86400 * 365, sub["id"]))
    print(f"Updated Pro User: pro@nexus.local (id: {pro_id})")

# 3. Ensure Free User
free = conn.execute("SELECT id FROM users WHERE email='free@nexus.local'").fetchone()
if not free:
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("free@nexus.local", "Community Engineer", pbkdf2("FreeUser2026!x"), "free", now, now)
    )
    free_id = cur.lastrowid
    print(f"Created Free User: free@nexus.local (id: {free_id})")
else:
    free_id = free["id"]
    conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (pbkdf2("FreeUser2026!x"), now, free_id))
    print(f"Updated Free User: free@nexus.local (id: {free_id})")

conn.commit()
conn.close()
print("All accounts seeded successfully!")
