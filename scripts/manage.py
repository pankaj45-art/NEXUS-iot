#!/usr/bin/env python3
"""Entitlement and maintenance CLI.

    python3 scripts/manage.py list-users
    python3 scripts/manage.py entitle user@example.com pro --days 30
    python3 scripts/manage.py revoke user@example.com
    python3 scripts/manage.py set-role user@example.com free|pro|admin
    python3 scripts/manage.py set-password user@example.com
    python3 scripts/manage.py reseed

'entitle' is the documented manual restore path after a CONFIRMED offline
payment. Every change is written to the audit log.
"""
from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus import billing, db, seed  # noqa: E402
from nexus.security import pbkdf2, validate_password_policy  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="NEXUS IoT maintenance CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-users")
    e = sub.add_parser("entitle")
    e.add_argument("email")
    e.add_argument("plan", choices=["pro", "free"])
    e.add_argument("--days", type=int, default=30)
    r = sub.add_parser("revoke")
    r.add_argument("email")
    sr = sub.add_parser("set-role")
    sr.add_argument("email")
    sr.add_argument("role", choices=["free", "pro", "admin"])
    sp = sub.add_parser("set-password")
    sp.add_argument("email")
    sub.add_parser("reseed")
    args = ap.parse_args()

    db.init_db()
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if args.cmd == "list-users":
            for u in conn.execute(
                "SELECT u.id,u.email,u.role,u.disabled,s.plan,s.status,s.expires_at FROM users u "
                "LEFT JOIN subscriptions s ON s.id=(SELECT id FROM subscriptions WHERE user_id=u.id "
                "ORDER BY updated_at DESC LIMIT 1) ORDER BY u.id"):
                print(dict(u))
        elif args.cmd in ("entitle", "revoke", "set-role", "set-password"):
            u = conn.execute("SELECT id FROM users WHERE email=?", (args.email.lower(),)).fetchone()
            if not u:
                print("User not found:", args.email)
                sys.exit(1)
            uid = u["id"]
            if args.cmd == "entitle":
                if args.plan == "pro":
                    out = billing.grant_pro(conn, uid, args.days, provider="manual", actor_id=uid)
                    print("Granted:", out, "(audited; recomputed on next request)")
                else:
                    print("Revoked:", billing.revoke_pro(conn, uid, actor_id=uid))
            elif args.cmd == "revoke":
                print("Revoked:", billing.revoke_pro(conn, uid, actor_id=uid))
            elif args.cmd == "set-role":
                conn.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (args.role, time.time(), uid))
                db.audit(conn, uid, "cli.set_role", args.email, {"role": args.role})
                print("Role set to", args.role)
            else:
                pw = getpass.getpass("New password: ") if sys.stdin.isatty() else input("New password: ")
                err = validate_password_policy(pw)
                if err:
                    print("Password policy:", err)
                    sys.exit(1)
                conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                             (pbkdf2(pw), time.time(), uid))
                conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (uid,))
                print("Password changed; sessions revoked.")
        elif args.cmd == "reseed":
            designation = [(r["slug"], r["free_rank"]) for r in conn.execute(
                "SELECT slug, free_rank FROM projects WHERE is_free=1 ORDER BY free_rank")]
            out = seed.seed_projects(conn, force=True)
            for slug, rank in designation:
                conn.execute("UPDATE projects SET is_free=1, free_rank=? WHERE slug=?", (rank, slug))
            print("Reseeded:", out, "- free designation preserved:", len(designation))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
