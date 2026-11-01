from pathlib import Path

fpath = Path(__file__).parent.parent / "nexus" / "server.py"
text = fpath.read_text(encoding="utf-8")

target = '    else:\n        print(f"[NEXUS] Existing Super Admin verified: {row[\'email\']}", flush=True)\n'

replacement = '''    else:
        print(f"[NEXUS] Existing Super Admin verified: {row['email']}", flush=True)

    # Super Admin explicitly designated by Pankaj: pankaj.raghu45@gmail.com
    pankaj_email = "pankaj.raghu45@gmail.com"
    pankaj_row = conn.execute("SELECT id, email, role FROM users WHERE email=?", (pankaj_email,)).fetchone()
    if not pankaj_row:
        conn.execute(
            "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pankaj_email, "Pankaj (Super Admin)", pbkdf2("PankajAdmin2026!x"), "admin", now, now)
        )
        print(f"[NEXUS] Bootstrapped Super Admin: {pankaj_email}", flush=True)
    elif pankaj_row['role'] != 'admin':
        conn.execute("UPDATE users SET role='admin' WHERE email=?", (pankaj_email,))
        print(f"[NEXUS] Promoted {pankaj_email} to Super Admin", flush=True)
'''

if target in text:
    fpath.write_text(text.replace(target, replacement, 1), encoding="utf-8")
    print("SUCCESS: server.py updated with Pankaj Super Admin")
else:
    print("TARGET NOT FOUND")
