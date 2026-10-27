import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nexus.security import verify_password

conn = sqlite3.connect(ROOT / "data" / "nexus.db")
cur = conn.cursor()
cur.execute("SELECT email, password_hash, role FROM users WHERE role='admin'")
row = cur.fetchone()

print("Admin user in DB:")
print("  Email:", row[0])
print("  Role:", row[2])
print("  Matches 'PankajAdmin2026!x':", verify_password("PankajAdmin2026!x", row[1]))
conn.close()
