#!/usr/bin/env python3
"""Secure first-administrator bootstrap.

Run on the server (not over HTTP):

    python3 scripts/bootstrap_admin.py admin@example.com

The password is read from NEXUS_ADMIN_PASSWORD or an interactive getpass
prompt. No admin password is hardcoded anywhere in the codebase, and no HTTP
endpoint can create or promote an administrator.
"""
from __future__ import annotations

import getpass
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus import db  # noqa: E402
from nexus.security import pbkdf2, validate_password_policy  # noqa: E402


def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEXUS_ADMIN_EMAIL", "")).strip().lower()
    if not email or "@" not in email:
        print("Usage: python3 scripts/bootstrap_admin.py admin@example.com")
        sys.exit(1)
    password = os.environ.get("NEXUS_ADMIN_PASSWORD", "")
    if not password:
        if not sys.stdin.isatty():
            print("No TTY: set NEXUS_ADMIN_PASSWORD or run interactively. Refusing to use a default password.")
            sys.exit(1)
        password = getpass.getpass("New admin password: ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.")
            sys.exit(1)
    err = validate_password_policy(password)
    if err:
        print("Password policy: " + err)
        sys.exit(1)
    db.init_db()
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT id, role, disabled FROM users WHERE email=?", (email,)).fetchone()
        now = time.time()
        if row:
            if row["role"] == "admin" and not row["disabled"]:
                print(f"{email} is already an administrator. Nothing to do.")
                conn.execute("ROLLBACK")
                return
            conn.execute("UPDATE users SET role='admin', disabled=0, password_hash=?, updated_at=? WHERE id=?",
                         (pbkdf2(password), now, row["id"]))
            uid = row["id"]
            action = "promoted existing user to admin"
        else:
            uid = conn.execute(
                "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) "
                "VALUES (?,?,?, 'admin', ?, ?)", (email, "Administrator", pbkdf2(password), now, now)).lastrowid
            conn.execute("INSERT INTO subscriptions(user_id, plan, status, provider, created_at, updated_at) "
                         "VALUES (?, 'free', 'inactive', 'manual', ?, ?)", (uid, now, now))
            action = "created administrator"
        db.audit(conn, uid, "bootstrap.admin_created", email, {"method": "protected CLI"})
        conn.execute("COMMIT")
        print(f"OK: {action}: {email} (id={uid}). Store the password in a password manager.")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
