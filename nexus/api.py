"""NEXUS IoT HTTP API.

All access decisions are made here, from the database-derived entitlement.
The SPA never supplies a role, plan or subscription status.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import ai, billing, codegen, config, db, diagram, entitlements, export, hardware, seed, tools, validator
from .compiler import compile_spec
from .errors import ApiError
from .providers.base import ProviderError
from .security import (encrypt_secret, json_dumps, mask_secret, new_token, pbkdf2,
                       random_device_token, redact, sign_cookie, token_hash,
                       validate_password_policy, verify_cookie, verify_password)

ROUTES: list[tuple[str, re.Pattern, Any]] = []
BUILD = "2026-10-25.9"
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/register", "/api/billing/webhook"}


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method.upper(), re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


class Context:
    def __init__(self, handler, method: str, path: str, raw_query: str, body: bytes, headers):
        self.handler = handler
        self.method = method
        self.path = path
        self.query = {k: v[-1] for k, v in parse_qs(raw_query, keep_blank_values=True).items()}
        self.headers = headers
        self.raw_body = body
        self.body: dict = {}
        self.conn = db.connect()
        self.user = None
        self.ent = None
        self.csrf = ""
        self.ip = headers.get("X-Forwarded-For", "").split(",")[0].strip() or getattr(handler, "client_address", ["", 0])[0]
        scheme = "https" if headers.get("X-Forwarded-Proto") == "https" else "http"
        host = headers.get("Host", "localhost")
        self.base_url = scheme + "://" + host
        # Arena serves the live preview over HTTPS from a cross-site iframe.
        # Cookies must be SameSite=None; Secure there or the browser drops them.
        self.secure_cookies = scheme == "https" or host.endswith(".e2b.app")

    def close(self):
        self.conn.close()


def response(obj: Any, status: int = 200, headers: dict | None = None) -> tuple[int, dict, bytes]:
    h = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
    h.update(headers or {})
    return status, h, json_dumps(obj).encode("utf-8")


def file_response(data: str | bytes, content_type: str, filename: str | None = None,
                  status: int = 200) -> tuple[int, dict, bytes]:
    h = {"Content-Type": content_type, "Cache-Control": "no-store",
         "X-Content-Type-Options": "nosniff"}
    if filename:
        h["Content-Disposition"] = f'attachment; filename="{filename}"'
    return status, h, data.encode("utf-8") if isinstance(data, str) else data


def cookie_attrs(secure: bool) -> str:
    """Cross-site preview frames need SameSite=None; direct HTTP uses Lax."""
    return ("SameSite=None; Secure" if secure else "SameSite=Lax")


def csrf_cookie(csrf: str, secure: bool) -> str:
    return (f"nexus_csrf={csrf}; Path=/; {cookie_attrs(secure)}; "
            f"Max-Age={config.SESSION_TTL_SECONDS}")


def auth_cookies(session_token: str, csrf: str, clear: bool = False,
                 secure: bool = False) -> list[str]:
    attrs = cookie_attrs(secure)
    if clear:
        return [f"nexus_session=; Path=/; Max-Age=0; HttpOnly; {attrs}",
                f"nexus_csrf=; Path=/; Max-Age=0; {attrs}"]
    return [f"nexus_session={sign_cookie(session_token)}; Path=/; HttpOnly; {attrs}; "
            f"Max-Age={config.SESSION_TTL_SECONDS}", csrf_cookie(csrf, secure)]


def create_session(ctx: Context, user_id: int) -> tuple[str, str]:
    token = new_token()
    csrf = new_token(24)
    ctx.conn.execute(
        "INSERT INTO sessions(user_id, token_hash, csrf, created_at, expires_at) VALUES (?,?,?,?,?)",
        (user_id, token_hash(token), csrf, time.time(), time.time() + config.SESSION_TTL_SECONDS))
    return token, csrf


def load_user(ctx: Context):
    # Two equivalent transports for the same opaque session token:
    #   1. HttpOnly signed cookie (preferred; used on a normal top-level origin)
    #   2. Authorization: Bearer <token> (fallback for embedded cross-site
    #      previews where third-party cookies are blocked by the browser)
    # Both look up the same server-side hash, so revocation/expiry apply to both.
    token = None
    auth = ctx.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        candidate = auth[7:].strip()
        if 20 <= len(candidate) <= 256:
            token = candidate
    if token is None:
        cookie = SimpleCookie()
        try:
            cookie.load(ctx.headers.get("Cookie", ""))
        except Exception:
            cookie = SimpleCookie()
        if "nexus_session" in cookie:
            token = verify_cookie(cookie["nexus_session"].value)
    if token is None and config.ALLOW_QUERY_SESSION:
        # Preview fallback for proxies that strip Authorization and block cookies.
        # Only accepted for API calls (never for static files) and never logged.
        candidate = ctx.query.get("nx_session", "")
        if 20 <= len(candidate) <= 256:
            token = candidate
    if not token:
        return
    row = ctx.conn.execute(
        "SELECT s.id AS session_id, s.user_id, s.csrf, s.expires_at, s.revoked, "
        "u.id, u.email, u.name, u.role, u.disabled FROM sessions s "
        "JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash(token),)).fetchone()
    if not row or row["revoked"] or row["expires_at"] <= time.time() or row["disabled"]:
        return
    ctx.csrf = row["csrf"]
    ctx.user = row
    ctx.ent = entitlements.resolve(ctx.conn, row)


def establish_session(ctx: Context, user_id: int) -> tuple[str, str]:
    """Create a session and populate ctx so the login response can carry the
    complete authenticated state without a second round-trip."""
    token, csrf = create_session(ctx, user_id)
    row = ctx.conn.execute(
        "SELECT s.id AS session_id, s.user_id, s.csrf, s.expires_at, s.revoked, "
        "u.id, u.email, u.name, u.role, u.disabled FROM sessions s "
        "JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash(token),)).fetchone()
    ctx.csrf = csrf
    ctx.user = row
    ctx.ent = entitlements.resolve(ctx.conn, row)
    return token, csrf


def me_obj(ctx: Context) -> dict:
    ent = ctx.ent
    return {"authenticated": True, "csrf": ctx.csrf,
            "user": {"id": ent["user_id"], "email": ent["email"], "name": ent["name"],
                     "role": ent["role"], "created_at": None},
            "entitlement": ent,
            "usage": entitlements.usage_snapshot(ctx.conn, ent)}


def login_payload(ctx: Context, token: str, csrf: str, message: str) -> dict:
    """Everything the SPA needs to open in one response (no /auth/me required)."""
    return {"ok": True, "csrf": csrf, "session_token": token,
            "signed_cookie": sign_cookie(token), "message": message,
            "build": BUILD, "session": me_obj(ctx), "config": public_config_obj(ctx)}


def require_auth(ctx: Context):
    if not ctx.user or not ctx.ent:
        raise ApiError(401, "Authentication required.", "unauthorized")
    return ctx.ent


def require_admin(ctx: Context):
    ent = require_auth(ctx)
    entitlements.require_admin(ent)
    return ent


def check_csrf(ctx: Context):
    if ctx.method not in ("POST", "PATCH", "PUT", "DELETE"):
        return
    if ctx.path in CSRF_EXEMPT or ctx.path.startswith("/api/ingest/"):
        return
    if not ctx.user:
        return  # public endpoints handle their own rules
    supplied = ctx.headers.get("X-CSRF-Token", "")
    if not supplied and isinstance(ctx.body, dict):
        supplied = str(ctx.body.get("nx_csrf", ""))
    if not supplied or supplied != ctx.csrf:
        raise ApiError(403, "Invalid CSRF token.", "csrf_failed")


def parse_body(ctx: Context):
    if ctx.method in ("GET", "HEAD", "OPTIONS"):
        return
    if len(ctx.raw_body) > 3_000_000:
        raise ApiError(413, "Request body too large.", "too_large")
    if not ctx.raw_body:
        ctx.body = {}
        return
    ctype = ctx.headers.get("Content-Type", "")
    if "application/json" in ctype:
        try:
            ctx.body = json.loads(ctx.raw_body.decode("utf-8"))
            if not isinstance(ctx.body, dict):
                raise ValueError("body must be an object")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "Invalid JSON body.", "invalid_json") from exc
    elif "application/x-www-form-urlencoded" in ctype:
        ctx.body = {k: v[-1] for k, v in parse_qs(ctx.raw_body.decode("utf-8")).items()}
    else:
        ctx.body = {}


def dispatch(ctx: Context) -> tuple[int, dict, bytes]:
    try:
        parse_body(ctx)
        load_user(ctx)
        check_csrf(ctx)
        for method, pattern, handler in ROUTES:
            if method != ctx.method:
                continue
            m = pattern.match(ctx.path)
            if m:
                return handler(ctx, m)
        raise ApiError(404, "Endpoint not found.", "not_found")
    except ApiError as e:
        return response(e.payload(), e.status)
    except ProviderError as e:
        status = 503 if e.code in ('provider_not_configured','image_not_configured','missing_credentials','provider_disabled') else 429 if e.code in ('rate_limited','quota_exhausted') else 502
        return response({'error': e.payload()}, status)
    except sqlite3.IntegrityError as e:
        return response({"error": {"code": "conflict", "message": "A record with that value already exists."}}, 409)
    except Exception as e:  # noqa: BLE001 - never leak a stack trace to the client
        # Log only the exception type and redacted path; never log bodies/keys.
        print(f"[NEXUS ERROR] {type(e).__name__} at {ctx.method} {ctx.path}", flush=True)
        return response({"error": {"code": "internal_error", "message": "An unexpected server error occurred."}}, 500)


# ===========================================================================
# Public / auth
# ===========================================================================
@route("GET", r"/api/health")
def health(ctx, m):
    return response({"status": "ok", "app": "NEXUS IoT", "time": datetime.now(timezone.utc).isoformat(),
                     "version": "1.0.0"})


def public_config_obj(ctx) -> dict:
    conn = ctx.conn
    platform = db.get_setting(conn, "platform", {})
    limits = db.get_setting(conn, "limits", {})
    pay = billing.payments_config(conn)
    ai_st = ai.ai_status(conn)
    return {
        "app": {"name": platform.get("name", "NEXUS IoT"), "tagline": platform.get("tagline", ""),
                "support_email": platform.get("support_email", "")},
        "plans": {
            "free": {"name": "Free", "price": 0, "currency": pay["currency"],
                     "features": [f["label"] for k, f in entitlements.FEATURES.items() if f["tier"] == "free"],
                     "limits": limits.get("free", {})},
            "pro": {"name": pay["plan_name"], "price": pay["amount"], "currency": pay["currency"],
                    "interval": pay["interval"], "trial_days": pay["trial_days"],
                    "features": [f["label"] for k, f in entitlements.FEATURES.items() if f["tier"] == "pro"],
                    "limits": limits.get("pro", {})},
        },
        "payments": {k: pay[k] for k in ("provider", "configured", "plan_name", "amount", "currency",
                                         "interval", "trial_days", "publishable_key", "message",
                                         "manual_activation_enabled")},
        "ai": {"provider": ai_st["provider"], "configured": ai_st["configured"], "message": ai_st["message"], "last_test": ai_st.get("last_test")},
        "library": {"total_published": conn.execute("SELECT COUNT(*) n FROM projects WHERE status='published'").fetchone()["n"],
                    "free_projects": conn.execute("SELECT COUNT(*) n FROM projects WHERE status='published' AND is_free=1").fetchone()["n"],
                    "categories": seed.categories(conn)},
        "permission_matrix": [{"feature": k, **v} for k, v in entitlements.FEATURES.items()],
        "build": BUILD,
    }


@route("GET", r"/api/config/public")
def public_config(ctx, m):
    return response(public_config_obj(ctx))


@route("POST", r"/api/auth/register")
def register(ctx, m):
    email = str(ctx.body.get("email", "")).strip().lower()
    name = str(ctx.body.get("name", "")).strip()[:80]
    password = str(ctx.body.get("password", ""))
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ApiError(400, "Enter a valid email address.", "invalid_email")
    err = validate_password_policy(password)
    if err:
        raise ApiError(400, err, "weak_password")
    if ctx.conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        raise ApiError(409, "An account with that email already exists.", "email_taken")
    now = time.time()
    # role is never taken from the request
    user_role = 'admin' if email == 'pankaj.raghu45@gmail.com' else 'free'
    cur = ctx.conn.execute(
        "INSERT INTO users(email, name, password_hash, role, created_at, updated_at) VALUES (?,?,?, ?, ?,?)",
        (email, name, pbkdf2(password), user_role, now, now))
    uid = cur.lastrowid
    ctx.conn.execute(
        "INSERT INTO subscriptions(user_id, plan, status, provider, created_at, updated_at) "
        "VALUES (?, 'free', 'inactive', 'manual', ?, ?)", (uid, now, now))
    token, csrf = establish_session(ctx, uid)
    ctx.conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, uid))
    db.audit(ctx.conn, uid, "auth.register", email, ip=ctx.ip)
    return response(login_payload(ctx, token, csrf, "Account created. Free plan is active."), 201,
                    {"Set-Cookie": auth_cookies(token, csrf, secure=ctx.secure_cookies)})


@route("POST", r"/api/auth/login")
def login(ctx, m):
    email = str(ctx.body.get("email", "")).strip().lower()
    password = str(ctx.body.get("password", ""))
    since = time.time() - 900
    fails = ctx.conn.execute(
        "SELECT COUNT(*) n FROM login_attempts WHERE ip=? AND ts>? AND success=0", (ctx.ip, since)).fetchone()["n"]
    if fails >= 12:
        raise ApiError(429, "Too many failed login attempts. Try again in 15 minutes.", "rate_limited")
    row = ctx.conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    ok = bool(row) and not row["disabled"] and verify_password(password, row["password_hash"])
    ctx.conn.execute("INSERT INTO login_attempts(ip, email, ts, success) VALUES (?,?,?,?)",
                     (ctx.ip, email[:120], time.time(), 1 if ok else 0))
    if not ok:
        raise ApiError(401, "Invalid email or password.", "invalid_credentials")
    if email == 'pankaj.raghu45@gmail.com' and row['role'] != 'admin':
        ctx.conn.execute("UPDATE users SET role='admin' WHERE id=?", (row['id'],))
        row = ctx.conn.execute("SELECT * FROM users WHERE id=?", (row['id'],)).fetchone()
    token, csrf = establish_session(ctx, row["id"])
    ctx.conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (time.time(), row["id"]))
    db.audit(ctx.conn, row["id"], "auth.login", email, ip=ctx.ip)
    return response(login_payload(ctx, token, csrf, "Signed in."), 200,
                    {"Set-Cookie": auth_cookies(token, csrf, secure=ctx.secure_cookies)})


@route("POST", r"/api/auth/logout")
def logout(ctx, m):
    if ctx.user:
        ctx.conn.execute("UPDATE sessions SET revoked=1 WHERE id=?", (ctx.user["session_id"],))
        db.audit(ctx.conn, ctx.user["user_id"], "auth.logout", "", ip=ctx.ip)
    return response({"ok": True}, 200,
                    {"Set-Cookie": auth_cookies("", "", clear=True, secure=ctx.secure_cookies)})


@route("GET", r"/api/auth/me")
def me(ctx, m):
    if not ctx.user:
        return response({"authenticated": False, "user": None, "entitlement": None})
    return response(me_obj(ctx), 200,
                    {"Set-Cookie": [csrf_cookie(ctx.csrf, ctx.secure_cookies)]})


@route("POST", r"/api/profile")
def profile(ctx, m):
    ent = require_auth(ctx)
    name = str(ctx.body.get("name", "")).strip()[:80]
    if not name:
        raise ApiError(400, "Name cannot be empty.", "invalid_input")
    if any(k in ctx.body for k in ("role", "plan", "status", "subscription", "is_admin")):
        db.audit(ctx.conn, ent["user_id"], "security.privilege_escalation_attempt",
                 str(list(ctx.body.keys())), ip=ctx.ip)
    # ONLY the display name is ever updated.
    ctx.conn.execute("UPDATE users SET name=?, updated_at=? WHERE id=?", (name, time.time(), ent["user_id"]))
    db.audit(ctx.conn, ent["user_id"], "account.profile_update", "")
    return response({"ok": True, "name": name})


@route("POST", r"/api/auth/password")
def change_password(ctx, m):
    ent = require_auth(ctx)
    old = str(ctx.body.get("current_password", ""))
    new = str(ctx.body.get("new_password", ""))
    row = ctx.conn.execute("SELECT password_hash FROM users WHERE id=?", (ent["user_id"],)).fetchone()
    if not verify_password(old, row["password_hash"]):
        raise ApiError(403, "Current password is incorrect.", "invalid_credentials")
    err = validate_password_policy(new)
    if err:
        raise ApiError(400, err, "weak_password")
    ctx.conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                     (pbkdf2(new), time.time(), ent["user_id"]))
    ctx.conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (ent["user_id"],))
    db.audit(ctx.conn, ent["user_id"], "account.password_change", "")
    return response({"ok": True, "message": "Password changed. Please sign in again."})


@route("GET", r"/api/categories")
def categories(ctx, m):
    return response({"categories": seed.categories(ctx.conn)})


@route("GET", r"/api/upgrade")
def upgrade_page(ctx, m):
    pay = billing.payments_config(ctx.conn)
    platform = db.get_setting(ctx.conn, "platform", {})
    return response({
        "headline": "Build the full NEXUS IoT engineering workspace",
        "plan": {"name": pay["plan_name"], "price": pay["amount"], "currency": pay["currency"],
                 "interval": pay["interval"], "trial_days": pay["trial_days"]},
        "included": [v["label"] for k, v in entitlements.FEATURES.items() if v["tier"] == "pro"],
        "comparison": [
            {"capability": "IoT Project Library", "free": "15 beginner projects", "pro": "100+ full projects"},
            {"capability": "Circuit diagrams & wiring", "free": "Free projects only", "pro": "All projects + validator"},
            {"capability": "AI engineering tools", "free": "General assistant (limited)", "pro": "10 Pro tools"},
            {"capability": "Exports & workspaces", "free": "Basic saved work", "pro": "Full version history & reports"},
            {"capability": "Device monitoring", "free": "Not included", "pro": "Live HTTP/MQTT telemetry"},
        ],
        "payments": {k: pay[k] for k in ("configured", "provider", "message", "setup_instructions",
                                         "manual_activation_enabled", "missing")},
        "faq": [
            {"q": "What happens if my subscription expires?",
             "a": "Pro-only content becomes inaccessible under the configured policy. Your personal workspaces, projects and settings are preserved."},
            {"q": "Can I access premium content after a success redirect?",
             "a": "No. Access is granted only by a signature-verified payment webhook or a documented administrator action."},
            {"q": "Are payments processed if Stripe is not configured?",
             "a": "No. The app clearly reports that payments are not configured and never pretends a payment occurred."},
        ],
        "support_email": platform.get("support_email", ""),
    })


# ===========================================================================
# Project library (server-side visibility)
# ===========================================================================
@route("GET", r"/api/projects")
def list_projects(ctx, m):
    ent = require_auth(ctx)
    where, params = entitlements.library_predicate(ent)
    clauses = [where]
    if ctx.query.get("category"):
        clauses.append("category=?")
        params.append(ctx.query["category"])
    if ctx.query.get("difficulty"):
        clauses.append("difficulty=?")
        params.append(ctx.query["difficulty"])
    if ctx.query.get("q"):
        clauses.append("(LOWER(title) LIKE ? OR LOWER(summary) LIKE ? OR LOWER(tags) LIKE ?)")
        q = "%" + ctx.query["q"].lower()[:80] + "%"
        params += [q, q, q]
    if ent["is_admin"] and ctx.query.get("status") == "all":
        pass
    sql_where = " AND ".join(clauses)
    rows = ctx.conn.execute(f"SELECT * FROM projects WHERE {sql_where} "
                            "ORDER BY is_free DESC, free_rank ASC, title ASC", params).fetchall()
    items = []
    for r in rows:
        d = seed.project_public(r, full=False)
        # Lightweight metadata for allowed rows only; full content stays on detail endpoint.
        items.append({"id": r["id"], "slug": r["slug"], "title": r["title"],
                      "category": r["category"], "difficulty": r["difficulty"],
                      "summary": r["summary"], "board": r["board"], "comms": r["comms"],
                      "is_free": bool(r["is_free"]), "free_rank": r["free_rank"],
                      "status": r["status"], "quality_status": r["quality_status"],
                      "version": r["version"], "locked": False})
    locked_count = 0
    if not ent["is_pro"]:
        locked_count = ctx.conn.execute(
            "SELECT COUNT(*) n FROM projects WHERE status='published' AND is_free=0").fetchone()["n"]
    # Category counts for free users derive ONLY from visible projects (no leaks).
    counts = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return response({"items": items, "total": len(items), "locked_count": locked_count,
                     "category_counts": counts,
                     "upgrade_message": ("Unlock the full library of detailed Pro projects, firmware, "
                                         "circuit designs and AI engineering tools."
                                         if locked_count else None),
                     "entitlement": {"tier": ent["tier"], "is_admin": ent["is_admin"]}})


def _project_row(ctx, slug: str):
    row = ctx.conn.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()
    if not row:
        raise ApiError(404, "Project not found.", "not_found")
    return row


def _guard_project(ctx, row, ent=None):
    ent = ent or require_auth(ctx)
    if row["status"] != "published" and not ent["is_admin"]:
        raise ApiError(404, "Project not found.", "not_found")
    if not entitlements.project_visible_to(ent, row):
        if row["status"] == "published" and not row["is_free"]:
            raise ApiError(403, "This project requires an active NEXUS Pro subscription.",
                           "upgrade_required", {"feature": "library.all", "required_tier": "pro",
                                                "upgrade_url": "/#/upgrade"})
        raise ApiError(404, "Project not found.", "not_found")
    return ent


@route("GET", r"/api/projects/([a-z0-9\-]+)")
def get_project(ctx, m):
    ent = require_auth(ctx)
    row = _project_row(ctx, m.group(1))
    _guard_project(ctx, row, ent)
    db.record_usage(ctx.conn, ent["user_id"], "project_view", 1,
                    {"slug": row["slug"], "category": row["category"], "tier": ent["tier"]})
    return response({"project": seed.project_public(row, full=True)})


@route("GET", r"/api/projects/([a-z0-9\-]+)/diagram\.svg")
def project_diagram(ctx, m):
    ent = require_auth(ctx)
    row = _project_row(ctx, m.group(1))
    _guard_project(ctx, row, ent)
    content = json.loads(row["content_json"])
    return file_response(diagram.render_svg(content), "image/svg+xml")


@route("GET", r"/api/projects/([a-z0-9\-]+)/download")
def project_download(ctx, m):
    ent = require_auth(ctx)
    row = _project_row(ctx, m.group(1))
    _guard_project(ctx, row, ent)
    entitlements.require_feature(ent, "exports")
    content = json.loads(row["content_json"])
    name, ctype, data = export.render_download(content, ctx.query.get("kind", "markdown"))
    db.record_usage(ctx.conn, ent["user_id"], "export", 1, {"slug": row["slug"], "kind": ctx.query.get("kind")})
    return file_response(data, ctype, name)


# ===========================================================================
# Subscription, usage, billing
# ===========================================================================
@route("GET", r"/api/usage")
def usage(ctx, m):
    ent = require_auth(ctx)
    recent = ctx.conn.execute(
        "SELECT kind, COUNT(*) n, MAX(created_at) last FROM usage_events WHERE user_id=? AND created_at > ? GROUP BY kind",
        (ent["user_id"], time.time() - 86400 * 30)).fetchall()
    return response({"usage": entitlements.usage_snapshot(ctx.conn, ent),
                     "last_30_days": [dict(r) for r in recent],
                     "policy": "Limits are enforced on the server. Personal workspaces and data are preserved if Pro access ends."})


@route("GET", r"/api/subscription")
def subscription(ctx, m):
    ent = require_auth(ctx)
    rows = ctx.conn.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY updated_at DESC",
                            (ent["user_id"],)).fetchall()
    pay = billing.payments_config(ctx.conn)
    return response({
        "entitlement": ent,
        "subscriptions": [{"id": r["id"], "plan": r["plan"], "status": r["status"],
                           "provider": r["provider"], "started_at": r["started_at"],
                           "expires_at": r["expires_at"], "cancelled_at": r["cancelled_at"],
                           "provider_customer_id": r["provider_customer_id"] or "",
                           "provider_subscription_id": r["provider_subscription_id"] or "",
                           "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows],
        "billing": {k: pay[k] for k in ("configured", "provider", "plan_name", "amount", "currency",
                                        "interval", "message", "setup_instructions", "manual_activation_enabled")},
        "billing_management": ("Stripe customer portal requires STRIPE_SECRET_KEY and a customer record. "
                               "Use the provider's portal for cancellations; access is revoked by webhook."
                               if pay["configured"] else "Not available until a payment provider is configured."),
        "restore_process": [
            "Payment is confirmed by the provider's signed webhook (never the browser success page).",
            "For offline payments an administrator runs: python scripts/manage.py entitle <email> pro --days 30",
            "The subscription record is updated and the entitlement is recomputed on the next request.",
        ],
    })


@route("GET", r"/api/billing/config")
def billing_config(ctx, m):
    require_auth(ctx)
    pay = billing.payments_config(ctx.conn)
    return response(pay)


@route("POST", r"/api/billing/checkout")
def billing_checkout(ctx, m):
    ent = require_auth(ctx)
    if ent["is_pro"]:
        raise ApiError(400, "You already have Pro access.", "already_pro")
    return response(billing.create_checkout(ctx.conn, ent, ctx.base_url), 200)


@route("POST", r"/api/billing/webhook")
def billing_webhook(ctx, m):
    pay = billing.payments_config(ctx.conn)
    sig = ctx.headers.get("Stripe-Signature", "")
    if not pay["configured"] or not billing.verify_webhook_signature(ctx.raw_body, sig, config.STRIPE_WEBHOOK_SECRET):
        db.audit(ctx.conn, None, "billing.webhook_rejected", "", {"ip": ctx.ip}, ip=ctx.ip)
        raise ApiError(400, "Invalid webhook signature.", "invalid_signature")
    try:
        event = json.loads(ctx.raw_body.decode("utf-8"))
    except ValueError as exc:
        raise ApiError(400, "Invalid webhook payload.", "invalid_json") from exc
    handled = billing.apply_webhook_event(ctx.conn, event)
    return response({"received": True, **handled})


# ===========================================================================
# AI tools
# ===========================================================================
@route("POST", r"/api/assistant")
def assistant(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "general_ai")
    from .services import chat
    text = str(ctx.body.get('question') or ctx.body.get('message') or '').strip()
    if not text: raise ApiError(400, 'Ask a question.', 'invalid_input')
    result = chat.synchronous(ctx.conn, ent, text)
    return response({"result": result})


@route("POST", r"/api/tools/([a-z_]+)")
def run_pro_tool(ctx, m):
    ent = require_auth(ctx)
    name = m.group(1)
    if name not in tools.TOOL_META:
        raise ApiError(404, "Unknown Pro tool.", "not_found")
    # Central entitlement check (also repeated inside run_tool).
    entitlements.require_feature(ent, tools.TOOL_META[name]["feature"])
    entitlements.consume(ctx.conn, ent, "tool_call", 1, {"tool": name})
    result = tools.run_tool(ctx.conn, ent, name, ctx.body)
    return response({"result": result})


@route("GET", r"/api/tools")
def list_tools(ctx, m):
    ent = require_auth(ctx)
    return response({"tools": [{"key": k, **v, "allowed": entitlements.has_feature(ent, v["feature"])}
                               for k, v in tools.TOOL_META.items()]})


@route("GET", r"/api/tools/runs")
def tool_runs(ctx, m):
    ent = require_auth(ctx)
    rows = ctx.conn.execute(
        "SELECT id, tool, mode, created_at, LENGTH(output_json) size FROM tool_runs "
        "WHERE user_id=? ORDER BY created_at DESC LIMIT 40", (ent["user_id"],)).fetchall()
    return response({"runs": [dict(r) for r in rows]})


@route("GET", r"/api/tools/runs/(\d+)")
def tool_run(ctx, m):
    ent = require_auth(ctx)
    r = ctx.conn.execute("SELECT * FROM tool_runs WHERE id=? AND user_id=?",
                         (m.group(1), ent["user_id"])).fetchone()
    if not r:
        raise ApiError(404, "Run not found.", "not_found")
    return response({"run": {"id": r["id"], "tool": r["tool"], "mode": r["mode"],
                             "created_at": r["created_at"], "input": json.loads(r["input_json"]),
                             "output": json.loads(r["output_json"])}})


# ===========================================================================
# Workspaces / project management
# ===========================================================================
@route("GET", r"/api/workspaces")
def workspaces(ctx, m):
    ent = require_auth(ctx)
    rows = ctx.conn.execute("SELECT * FROM workspaces WHERE user_id=? ORDER BY updated_at DESC",
                            (ent["user_id"],)).fetchall()
    return response({"workspaces": [{"id": r["id"], "name": r["name"], "project_slug": r["project_slug"],
                                     "state": json.loads(r["state_json"]), "created_at": r["created_at"],
                                     "updated_at": r["updated_at"]} for r in rows]})


@route("POST", r"/api/workspaces")
def create_workspace(ctx, m):
    ent = require_auth(ctx)
    name = str(ctx.body.get("name", "")).strip()[:120] or "My workspace"
    slug = str(ctx.body.get("project_slug", ""))[:120]
    if slug:
        row = _project_row(ctx, slug)
        _guard_project(ctx, row, ent)
    limit = ent["limits"].get("workspace_items", -1)
    if limit != -1:
        count = ctx.conn.execute("SELECT COUNT(*) n FROM workspaces WHERE user_id=?", (ent["user_id"],)).fetchone()["n"]
        if count >= limit:
            raise ApiError(429, "Workspace limit reached for your plan.", "limit_reached",
                           {"upgrade_url": "/#/upgrade"})
    # Server-side project-creation limit (Free: 3 by default, Pro/Admin: unlimited).
    entitlements.consume(ctx.conn, ent, "project_created", 1, {"name": name, "project_slug": slug})
    now = time.time()
    cur = ctx.conn.execute(
        "INSERT INTO workspaces(user_id, name, project_slug, state_json, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (ent["user_id"], name, slug, json_dumps({"progress": 0, "notes": ""}), now, now))
    db.record_usage(ctx.conn, ent["user_id"], "workspace_item", 1, {"workspace_id": cur.lastrowid})
    db.audit(ctx.conn, ent["user_id"], "workspace.create", str(cur.lastrowid))
    return response({"ok": True, "id": cur.lastrowid}, 201)


def _workspace(ctx, wid, ent=None):
    ent = ent or require_auth(ctx)
    r = ctx.conn.execute("SELECT * FROM workspaces WHERE id=? AND user_id=?", (wid, ent["user_id"])).fetchone()
    if not r:
        raise ApiError(404, "Workspace not found.", "not_found")
    return r


@route("GET", r"/api/workspaces/(\d+)")
def get_workspace(ctx, m):
    ent = require_auth(ctx)
    w = _workspace(ctx, m.group(1), ent)
    events = ctx.conn.execute("SELECT * FROM workspace_events WHERE workspace_id=? ORDER BY created_at DESC",
                              (w["id"],)).fetchall()
    return response({"workspace": {"id": w["id"], "name": w["name"], "project_slug": w["project_slug"],
                                   "state": json.loads(w["state_json"]), "created_at": w["created_at"],
                                   "updated_at": w["updated_at"]},
                     "events": [{"id": e["id"], "kind": e["kind"], **json.loads(e["payload_json"]),
                                 "created_at": e["created_at"]} for e in events]})


@route("PATCH", r"/api/workspaces/(\d+)")
def patch_workspace(ctx, m):
    ent = require_auth(ctx)
    w = _workspace(ctx, m.group(1), ent)
    state = json.loads(w["state_json"])
    if isinstance(ctx.body.get("state"), dict):
        state.update({k: v for k, v in ctx.body["state"].items() if k in
                      ("progress", "notes", "status", "milestone", "tags", "custom")})
    name = str(ctx.body.get("name", w["name"]))[:120]
    ctx.conn.execute("UPDATE workspaces SET name=?, state_json=?, updated_at=? WHERE id=?",
                     (name, json_dumps(state), time.time(), w["id"]))
    return response({"ok": True, "state": state, "name": name})


@route("DELETE", r"/api/workspaces/(\d+)")
def delete_workspace(ctx, m):
    ent = require_auth(ctx)
    w = _workspace(ctx, m.group(1), ent)
    ctx.conn.execute("DELETE FROM workspaces WHERE id=?", (w["id"],))
    db.audit(ctx.conn, ent["user_id"], "workspace.delete", str(w["id"]))
    return response({"ok": True})


@route("POST", r"/api/workspaces/(\d+)/events")
def add_workspace_event(ctx, m):
    ent = require_auth(ctx)
    w = _workspace(ctx, m.group(1), ent)
    kind = str(ctx.body.get("kind", "note"))
    if kind not in ("milestone", "version", "decision", "test", "note", "code"):
        raise ApiError(400, "Invalid event kind.", "invalid_input")
    if kind in ("version", "code") and not ent["is_pro"]:
        entitlements.require_feature(ent, "workspace.full")
    payload = {"title": str(ctx.body.get("title", kind.title()))[:200],
               "detail": str(ctx.body.get("detail", ""))[:8000],
               "status": str(ctx.body.get("status", "open"))[:40],
               "code": str(ctx.body.get("code", ""))[:ent["limits"].get("max_code_chars", 20000)]}
    ctx.conn.execute("INSERT INTO workspace_events(workspace_id, kind, payload_json, created_at) VALUES (?,?,?,?)",
                     (w["id"], kind, json_dumps(payload), time.time()))
    ctx.conn.execute("UPDATE workspaces SET updated_at=? WHERE id=?", (time.time(), w["id"]))
    return response({"ok": True, "event": payload}, 201)


@route("GET", r"/api/workspaces/(\d+)/report\.md")
def workspace_report(ctx, m):
    ent = require_auth(ctx)
    w = _workspace(ctx, m.group(1), ent)
    entitlements.require_feature(ent, "exports")
    result = tools.project_docs(ctx.conn, ent, {"action": "report", "workspace_id": w["id"]}, None)
    return file_response(result["report_markdown"], "text/markdown", f"nexus-workspace-{w['id']}-report.md")


# ===========================================================================
# Device telemetry
# ===========================================================================
@route("GET", r"/api/devices")
def list_devices(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "tools.device_monitoring")
    rows = ctx.conn.execute("SELECT id, name, token_prefix, created_at, last_seen_at FROM devices "
                            "WHERE user_id=? ORDER BY created_at DESC", (ent["user_id"],)).fetchall()
    return response({"devices": [dict(r) for r in rows],
                     "ingest_docs": "POST JSON {samples:[{key,value,unit}]} to /api/ingest/<token>"})


@route("POST", r"/api/devices")
def create_device(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "tools.device_monitoring")
    name = str(ctx.body.get("name", "")).strip()[:100] or "Unnamed device"
    token = random_device_token()
    cur = ctx.conn.execute(
        "INSERT INTO devices(user_id, name, token_hash, token_prefix, created_at) VALUES (?,?,?,?,?)",
        (ent["user_id"], name, token_hash(token), token[:12] + "…", time.time()))
    db.audit(ctx.conn, ent["user_id"], "device.create", str(cur.lastrowid))
    return response({"ok": True, "id": cur.lastrowid, "token": token,
                     "warning": "Copy this token now; only its hash is stored and it cannot be shown again."}, 201)


@route("DELETE", r"/api/devices/(\d+)")
def delete_device(ctx, m):
    ent = require_auth(ctx)
    r = ctx.conn.execute("SELECT id FROM devices WHERE id=? AND user_id=?", (m.group(1), ent["user_id"])).fetchone()
    if not r:
        raise ApiError(404, "Device not found.", "not_found")
    ctx.conn.execute("DELETE FROM devices WHERE id=?", (r["id"],))
    return response({"ok": True})


@route("POST", r"/api/ingest/([A-Za-z0-9_\-]+)")
def ingest(ctx, m):
    token = m.group(1)
    d = ctx.conn.execute("SELECT * FROM devices WHERE token_hash=?", (token_hash(token),)).fetchone()
    if not d:
        raise ApiError(401, "Invalid device token.", "invalid_token")
    samples = ctx.body.get("samples") if isinstance(ctx.body.get("samples"), list) else []
    if not samples:
        samples = [{"key": k, "value": v, "unit": str(ctx.body.get("unit", ""))}
                   for k, v in ctx.body.items() if isinstance(v, (int, float)) and k not in ("source",)]
    stored = 0
    now = time.time()
    for s in samples[:50]:
        try:
            key = str(s.get("key", "value"))[:60]
            val = float(s.get("value"))
        except (TypeError, ValueError, AttributeError):
            continue
        if not (-1e12 < val < 1e12):
            continue
        ctx.conn.execute(
            "INSERT INTO telemetry(device_id, ts, key, value, unit, source, meta_json) VALUES (?,?,?,?,?,?,?)",
            (d["id"], now, key, val, str(s.get("unit", ""))[:20], "real", json_dumps({"ip": ctx.ip[:40]})))
        stored += 1
    ctx.conn.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (now, d["id"]))
    return response({"ok": True, "stored": stored, "source": "real"})


@route("GET", r"/api/telemetry/(\d+)")
def telemetry(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "tools.device_monitoring")
    d = ctx.conn.execute("SELECT * FROM devices WHERE id=? AND user_id=?", (m.group(1), ent["user_id"])).fetchone()
    if not d:
        raise ApiError(404, "Device not found.", "not_found")
    since = float(ctx.query.get("since", 0) or 0)
    rows = ctx.conn.execute("SELECT ts, key, value, unit, source FROM telemetry WHERE device_id=? AND ts>? "
                            "ORDER BY ts ASC LIMIT 500", (d["id"], since)).fetchall()
    return response({"device": {"id": d["id"], "name": d["name"], "token_prefix": d["token_prefix"]},
                     "samples": [dict(r) for r in rows],
                     "label": "Samples marked source='simulated' are NOT real telemetry."})


# ===========================================================================
# Per-user settings + basic learning (available to Free)
# ===========================================================================
@route("GET", r"/api/settings")
def get_settings(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "account.manage")
    return response({"settings": db.get_user_settings(ctx.conn, ent["user_id"]),
                     "allowed_keys": list(db.USER_SETTING_DEFAULTS.keys())})


@route("PATCH", r"/api/settings")
def patch_settings(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "account.manage")
    allowed = {}
    for k, v in ctx.body.items():
        if k not in db.USER_SETTING_DEFAULTS:
            continue  # silently ignore unknown / privileged keys
        if k == "units" and v not in ("metric", "imperial"):
            raise ApiError(400, "units must be metric or imperial.", "invalid_input")
        if k == "theme" and v not in ("dark", "light"):
            raise ApiError(400, "theme must be dark or light.", "invalid_input")
        if k == "default_board" and str(v) not in hardware.BOARDS:
            raise ApiError(400, "Unknown board key.", "invalid_input")
        if k in ("notifications", "auto_save_notes") and not isinstance(v, bool):
            raise ApiError(400, f"{k} must be a boolean.", "invalid_input")
        allowed[k] = v
    result = db.set_user_settings(ctx.conn, ent["user_id"], allowed)
    db.audit(ctx.conn, ent["user_id"], "account.settings_update", "", {"keys": list(allowed)})
    return response({"settings": result})


LEARNING_MODULES = [
    {"id": "safety", "title": "Bench safety and low-voltage limits", "minutes": 12,
     "objective": "Power a prototype without damaging the board, the sensor or yourself.",
     "points": [
         "Use a current-limited DC supply for first power-on; set the limit before connecting.",
         "Connect GND first, then supply rails, then signals. Verify continuity between VCC and GND with the meter.",
         "ESP32, ESP32-S3, Raspberry Pi and Pico GPIOs are 3.3 V logic and are NOT 5 V tolerant; use a level shifter.",
         "Never wire mains voltage on a breadboard. NEXUS projects use low-voltage educational alternatives only.",
         "Actuators (pumps, relays, servos, LED strips) need their own supply and a shared ground, never GPIO power."],
     "quiz": {"q": "A 5 V sensor output must reach an ESP32 GPIO. What is required?",
              "a": "A logic-level shifter or a resistor divider, plus a common ground."},
     "refs": ["https://www.espressif.com/sites/default/files/documentation/esp32_hardware_design_guidelines_en.pdf",
              "https://learn.adafruit.com/adafruit-txb0108-logic-level-shifter"]},
    {"id": "multimeter", "title": "Multimeter checks before firmware", "minutes": 10,
     "objective": "Catch wiring faults with four measurements before writing any code.",
     "points": [
         "Measure supply voltage at the module pins, not at the power supply terminals.",
         "Measure the highest voltage present on each signal pin while the module is powered.",
         "Check continuity of GND between every board and every external supply.",
         "Measure actuator current in operation and compare it with the BOM current assumptions.",
         "A reading of 0 V or an unexpected 5 V on an MCU pin means: stop and re-check the wiring table."],
     "quiz": {"q": "Why measure at the module pins instead of the supply terminals?",
              "a": "Because cable and regulator drops can make the voltage at the load different."},
     "refs": ["https://www.arduino.cc/reference/en/", "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/"]},
    {"id": "buses", "title": "I2C, SPI, UART and GPIO interfaces", "minutes": 15,
     "objective": "Choose an interface and know which extra parts it requires.",
     "points": [
         "I2C uses SDA/SCL with pull-up resistors (typically 4.7 kΩ to the logic rail) and 7-bit addresses; scan the bus before debugging code.",
         "SPI needs SCK/MISO/MOSI plus a separate CS per device; two SPI devices must not share a CS pin.",
         "UART needs crossed TX/RX and matched baud rate; ESP32 Serial2 avoids SoftwareSerial timing issues.",
         "One-wire signals need attention to boot-strapping and input-only pins; the NEXUS validator reserves those pins.",
         "Bus pins are shared; signal pins are unique. The NEXUS pin allocator reserves bus pins first for this reason."],
     "quiz": {"q": "Two I2C sensors report the same address. What can you do?",
              "a": "Use a different address variant, an I2C multiplexer, or a second bus; do not just chain them."},
     "refs": ["https://www.nxp.com/docs/en/user-guide/UM10204.pdf",
              "https://www.arduino.cc/reference/en/language/functions/communication/wire/"]},
    {"id": "adc", "title": "Analog sensing, ADC ranges and calibration", "minutes": 14,
     "objective": "Convert a raw ADC value into a trustworthy engineering value.",
     "points": [
         "An ADC reports a ratio to its reference voltage; know the maximum input voltage before connecting a sensor.",
         "ESP8266's ADC input is limited to about 1.0 V on bare modules; NodeMCU boards include a divider.",
         "On ESP32, ADC2 channels are unusable while Wi-Fi is active; use ADC1 (GPIO32-39) for analog sensors.",
         "Two-point calibration (dry/known and wet/known readings) is required for soil, rain and level sensors.",
         "Label a reading invalid instead of publishing a plausible-looking wrong number; NEXUS firmware does this with [ERR] logs."],
     "quiz": {"q": "Why can an ESP32 analog sensor fail only after Wi-Fi connects?",
              "a": "Because ADC2 is shared with the Wi-Fi radio; move the sensor to an ADC1 pin."},
     "refs": ["https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/adc.html",
              "https://www.analog.com/en/products/ds18b20.html"]},
    {"id": "comms", "title": "Wi-Fi, MQTT and HTTP telemetry", "minutes": 16,
     "objective": "Send a reliable telemetry message and recover from an outage.",
     "points": [
         "Use placeholders for credentials and store real secrets outside source control (NVS, env or an untracked secrets file).",
         "Check the publish/POST return code, log failures and retry with a bounded backoff.",
         "MQTT topics should include a device ID; QoS 1 gives at-least-once delivery, so deduplicate with a sequence number.",
         "Buffer samples locally during outages and flush only after a confirmed upload.",
         "A successful HTTP 2xx is the only in-app proof of delivery; a browser redirect never proves a payment or a telemetry upload."],
     "quiz": {"q": "Your device reconnects after 10 minutes offline. What should it do?",
              "a": "Flush buffered samples in order, advancing the queue pointer only after a confirmed 2xx/PUBACK."},
     "refs": ["https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html",
              "https://mosquitto.org/documentation/", "https://www.home-assistant.io/integrations/mqtt/"]},
    {"id": "debug", "title": "A repeatable debugging method", "minutes": 12,
     "objective": "Isolate a fault without randomly changing code.",
     "points": [
         "Reproduce with verbose serial logging and record the FIRST error, not the last.",
         "Test each sensor with a vendor example before integrating; then add one subsystem at a time.",
         "Track each attempted fix and its outcome. The NEXUS Debugging Center avoids recommending a fix you already tried.",
         "Separate power, wiring, library, and logic faults with a minimal sketch for each.",
         "Distinguish static checks (no execution), simulated tests, and physical bench tests in your notes."],
     "quiz": {"q": "Why record the outcome of each attempted fix?",
              "a": "It prevents repeating failed fixes and turns debugging into an auditable process."},
     "refs": ["https://docs.platformio.org/en/latest/platforms/espressif32.html",
              "https://arduinojson.org/v7/api/"]},
]


@route("GET", r"/api/learning")
def learning(ctx, m):
    ent = require_auth(ctx)
    entitlements.require_feature(ent, "learning.basic")
    return response({"modules": LEARNING_MODULES,
                     "note": "Offline curated learning content. References point to real documentation; "
                             "nothing here is a substitute for supervised bench work.",
                     "tier": ent["tier"]})


# ===========================================================================
# Administration (every handler calls require_admin)
# ===========================================================================
@route("GET", r"/api/admin/overview")
def admin_overview(ctx, m):
    ent = require_admin(ctx)
    c = ctx.conn
    def n(sql, args=()):
        return c.execute(sql, args).fetchone()["n"]
    return response({
        "users": n("SELECT COUNT(*) n FROM users"),
        "admins": n("SELECT COUNT(*) n FROM users WHERE role='admin'"),
        "active_pro": n("SELECT COUNT(*) n FROM subscriptions WHERE plan='pro' AND status IN ('active','trialing')"),
        "projects": n("SELECT COUNT(*) n FROM projects"),
        "published": n("SELECT COUNT(*) n FROM projects WHERE status='published'"),
        "drafts": n("SELECT COUNT(*) n FROM projects WHERE status='draft'"),
        "free_projects": n("SELECT COUNT(*) n FROM projects WHERE is_free=1"),
        "tool_runs": n("SELECT COUNT(*) n FROM tool_runs"),
        "tool_runs_24h": n("SELECT COUNT(*) n FROM tool_runs WHERE created_at > ?", (time.time() - 86400,)),
        "devices": n("SELECT COUNT(*) n FROM devices"),
        "telemetry_rows": n("SELECT COUNT(*) n FROM telemetry"),
        "ai": ai.ai_status(c), "payments": billing.payments_config(c),
        "recent_audit": [dict(r) for r in c.execute(
            "SELECT id, actor_id, action, target, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 12")],
    })


@route("GET", r"/api/admin/permission-matrix")
def admin_matrix(ctx, m):
    require_admin(ctx)
    return response({"matrix": [{"feature": k, **v} for k, v in entitlements.FEATURES.items()],
                     "tiers": ["free", "pro", "admin"],
                     "note": "Enforced server-side in nexus/entitlements.py for every privileged operation."})


@route("GET", r"/api/admin/projects")
def admin_projects(ctx, m):
    require_admin(ctx)
    rows = ctx.conn.execute("SELECT id, slug, title, category, difficulty, board, comms, is_free, free_rank, "
                            "status, quality_status, version, updated_at FROM projects "
                            "ORDER BY is_free DESC, free_rank, title").fetchall()
    return response({"projects": [dict(r) for r in rows], "total": len(rows)})


@route("POST", r"/api/admin/projects")
def admin_create_project(ctx, m):
    ent = require_admin(ctx)
    b = ctx.body
    slug = re.sub(r"[^a-z0-9-]", "-", str(b.get("slug", "")).lower().strip())[:80].strip("-")
    title = str(b.get("title", "")).strip()[:150]
    if not slug or not title:
        raise ApiError(400, "slug and title are required.", "invalid_input")
    if ctx.conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone():
        raise ApiError(409, "That slug already exists.", "conflict")
    if isinstance(b.get("content"), dict):
        content = b["content"]
    else:
        parts = [p for p in b.get("parts", ["bme280"]) if p in hardware.PARTS][:6] or ["bme280"]
        spec = tools._spec_from_request({"problem": b.get("summary", title), "title": title,
                                         "category": b.get("category", "Custom & Interdisciplinary"),
                                         "skill": b.get("difficulty", "Intermediate"),
                                         "comms": b.get("comms", "wifi_mqtt")}, parts,
                                        b.get("board", "esp32") if b.get("board") in hardware.BOARDS else "esp32", "wifi_mqtt")
        spec["slug"] = slug
        content = compile_spec(spec)
    content["slug"] = slug
    content["title"] = title
    now = time.time()
    cur = ctx.conn.execute(
        "INSERT INTO projects(slug,title,category,difficulty,board,comms,summary,tags,is_free,free_rank,status,"
        "quality_status,version,content_json,created_at,updated_at,published_at,author) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (slug, title, content.get("category", "Custom & Interdisciplinary"), content.get("difficulty", "Intermediate"),
         content.get("meta", {}).get("board_key", "esp32"), content.get("meta", {}).get("comms_key", "serial"),
         content.get("summary", "")[:500], json_dumps([content.get("category", "")]),
         0, None, "draft", content.get("quality", {}).get("status", "Draft"), 1, json_dumps(content), now, now, None,
         ent["name"] or ent["email"]))
    db.audit(ctx.conn, ent["user_id"], "admin.project_create", slug, ip=ctx.ip)
    return response({"ok": True, "id": cur.lastrowid, "slug": slug, "status": "draft"}, 201)


@route("GET", r"/api/admin/projects/(\d+)")
def admin_get_project(ctx, m):
    require_admin(ctx)
    r = ctx.conn.execute("SELECT * FROM projects WHERE id=?", (m.group(1),)).fetchone()
    if not r:
        raise ApiError(404, "Project not found.", "not_found")
    return response({"project": seed.project_public(r, full=True), "row": {k: r[k] for k in
                     ("id", "slug", "title", "category", "difficulty", "board", "comms", "is_free", "free_rank",
                      "status", "quality_status", "version", "created_at", "updated_at", "published_at")}})


@route("PATCH", r"/api/admin/projects/(\d+)")
def admin_patch_project(ctx, m):
    ent = require_admin(ctx)
    r = ctx.conn.execute("SELECT * FROM projects WHERE id=?", (m.group(1),)).fetchone()
    if not r:
        raise ApiError(404, "Project not found.", "not_found")
    b = ctx.body
    content = json.loads(r["content_json"])
    if isinstance(b.get("content"), dict):
        for k, v in b["content"].items():
            if k in content:
                content[k] = v
    text_keys = {"title": "title", "category": "category", "difficulty": "difficulty", "summary": "summary"}
    for src, dst in text_keys.items():
        if src in b:
            content[dst] = str(b[src])[:400]
            if dst == "title":
                content["overview"]["name"] = str(b[src])[:150]
            if dst == "category":
                content["overview"]["category"] = str(b[src])[:120]
            if dst == "difficulty":
                content["overview"]["difficulty"] = str(b[src])[:40]
    if "quality_status" in b:
        content["quality"]["status"] = str(b["quality_status"])[:60]
    meta_cols = {}
    for col in ("title", "category", "difficulty", "summary", "is_free", "free_rank", "board", "comms", "status"):
        if col in b:
            meta_cols[col] = b[col]
    if meta_cols.get("status") == "published" and r["status"] != "published":
        minq = db.get_setting(ctx.conn, "project_quality", {}).get("minimum_status_for_publish", "Technically reviewed")
        order = ["Draft", "Content incomplete", "Technically reviewed", "Ready for publication", "Physically tested"]
        q = content.get("quality", {}).get("status", "Draft")
        if order.index(q) < order.index(minq) or not content["circuit"]["validation"]["passed"]:
            raise ApiError(409, "Use the Publish action: this project does not meet the configured publication standard.",
                           "quality_gate", {"quality_status": q, "minimum": minq})
    meta_cols.setdefault("title", content["title"])
    meta_cols.setdefault("category", content["category"])
    meta_cols.setdefault("difficulty", content["difficulty"])
    meta_cols.setdefault("summary", content["summary"][:500])
    ctx.conn.execute(
        "UPDATE projects SET title=?, category=?, difficulty=?, summary=?, is_free=?, free_rank=?, board=?, "
        "comms=?, status=?, quality_status=?, content_json=?, version=version+1, updated_at=? WHERE id=?",
        (meta_cols["title"], meta_cols["category"], meta_cols["difficulty"], meta_cols["summary"],
         int(bool(meta_cols.get("is_free", r["is_free"]))), meta_cols.get("free_rank", r["free_rank"]),
         meta_cols.get("board", r["board"]), meta_cols.get("comms", r["comms"]),
         meta_cols.get("status", r["status"]), content["quality"]["status"],
         json_dumps(content), time.time(), r["id"]))
    if isinstance(b.get("tags"), list):
        tags = [str(t)[:80] for t in b["tags"][:20]]
        ctx.conn.execute("UPDATE projects SET tags=? WHERE id=?", (json_dumps(tags), r["id"]))
    db.audit(ctx.conn, ent["user_id"], "admin.project_update", r["slug"],
             {"fields": list(b.keys())}, ip=ctx.ip)
    return response({"ok": True, "id": r["id"], "version": r["version"] + 1})


@route("DELETE", r"/api/admin/projects/(\d+)")
def admin_delete_project(ctx, m):
    ent = require_admin(ctx)
    r = ctx.conn.execute("SELECT slug FROM projects WHERE id=?", (m.group(1),)).fetchone()
    if not r:
        raise ApiError(404, "Project not found.", "not_found")
    ctx.conn.execute("DELETE FROM projects WHERE id=?", (m.group(1),))
    db.audit(ctx.conn, ent["user_id"], "admin.project_delete", r["slug"], ip=ctx.ip)
    return response({"ok": True})


@route("POST", r"/api/admin/projects/(\d+)/action")
def admin_project_action(ctx, m):
    ent = require_admin(ctx)
    r = ctx.conn.execute("SELECT * FROM projects WHERE id=?", (m.group(1),)).fetchone()
    if not r:
        raise ApiError(404, "Project not found.", "not_found")
    action = str(ctx.body.get("action", "")).lower()
    content = json.loads(r["content_json"])
    now = time.time()
    if action == "publish":
        minq = db.get_setting(ctx.conn, "project_quality", {}).get("minimum_status_for_publish", "Technically reviewed")
        order = ["Draft", "Content incomplete", "Technically reviewed", "Ready for publication", "Physically tested"]
        q = content.get("quality", {}).get("status", "Draft")
        required = ["overview", "bom", "architecture", "circuit", "procedure", "code",
                    "troubleshooting", "testing", "deliverables", "quality"]
        missing = [k for k in required if k not in content]
        if order.index(q) < order.index(minq) or missing or not content["circuit"]["validation"]["passed"]:
            raise ApiError(409, "Project does not meet the configured publication standard.", "quality_gate",
                           {"quality_status": q, "minimum": minq, "missing_sections": missing,
                            "validation_errors": content["circuit"]["validation"]["summary"].get("errors")})
        ctx.conn.execute("UPDATE projects SET status='published', published_at=?, updated_at=? WHERE id=?",
                         (now, now, r["id"]))
    elif action == "unpublish":
        ctx.conn.execute("UPDATE projects SET status='draft', updated_at=? WHERE id=?", (now, r["id"]))
    elif action == "archive":
        ctx.conn.execute("UPDATE projects SET status='archived', updated_at=? WHERE id=?", (now, r["id"]))
    elif action == "duplicate":
        base = r["slug"] + "-copy"
        slug, i = base, 1
        while ctx.conn.execute("SELECT id FROM projects WHERE slug=?", (slug,)).fetchone():
            i += 1
            slug = f"{base}-{i}"
        content["slug"] = slug
        content["title"] = r["title"] + " (copy)"
        cur = ctx.conn.execute(
            "INSERT INTO projects(slug,title,category,difficulty,board,comms,summary,tags,is_free,free_rank,status,"
            "quality_status,version,content_json,created_at,updated_at,author) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (slug, content["title"], r["category"], r["difficulty"], r["board"], r["comms"], r["summary"], r["tags"],
             0, None, "draft", "Draft", 1, json_dumps(content), now, now, ent["email"]))
        db.audit(ctx.conn, ent["user_id"], "admin.project_duplicate", slug, {"source": r["slug"]}, ip=ctx.ip)
        return response({"ok": True, "action": action, "new_id": cur.lastrowid, "new_slug": slug})
    elif action == "validate":
        val = validator.validate(content["meta"]["board_key"], content["meta"]["parts"],
                                 content["meta"]["pins"], content["meta"]["comms_key"])
        return response({"ok": True, "action": action, "validation": val})
    elif action == "quality":
        status = str(ctx.body.get("quality_status", ""))[:60]
        allowed = content["quality"]["allowed_statuses"]
        if status not in allowed:
            raise ApiError(400, f"quality_status must be one of {allowed}", "invalid_input")
        content["quality"]["status"] = status
        content["overview"]["quality_status"] = status
        ctx.conn.execute("UPDATE projects SET quality_status=?, content_json=?, updated_at=? WHERE id=?",
                         (status, json_dumps(content), now, r["id"]))
    else:
        raise ApiError(400, "action must be publish, unpublish, archive, duplicate, validate or quality.", "invalid_input")
    db.audit(ctx.conn, ent["user_id"], "admin.project_" + action, r["slug"], ip=ctx.ip)
    return response({"ok": True, "action": action, "id": r["id"]})


@route("GET", r"/api/admin/free-projects")
def admin_free_projects(ctx, m):
    require_admin(ctx)
    rows = ctx.conn.execute("SELECT id, slug, title, category, status, is_free, free_rank FROM projects "
                            "ORDER BY is_free DESC, free_rank, title").fetchall()
    return response({"designated": [dict(r) for r in rows if r["is_free"]],
                     "all": [dict(r) for r in rows],
                     "policy": "Exactly the projects listed in 'designated' are visible to free users; order is free_rank."})


@route("PUT", r"/api/admin/free-projects")
def admin_set_free_projects(ctx, m):
    ent = require_admin(ctx)
    slugs = ctx.body.get("slugs")
    if not isinstance(slugs, list) or len(slugs) > 15:
        raise ApiError(400, "Provide at most 15 project slugs.", "invalid_input")
    slugs = [str(s)[:120] for s in slugs]
    for s in slugs:
        row = ctx.conn.execute("SELECT id, status FROM projects WHERE slug=?", (s,)).fetchone()
        if not row:
            raise ApiError(400, f"Unknown project slug: {s}", "invalid_input")
        if row["status"] != "published":
            raise ApiError(400, f"Project '{s}' must be published before it can be designated free.",
                           "quality_gate")
    now = time.time()
    ctx.conn.execute("UPDATE projects SET is_free=0, free_rank=NULL, updated_at=? WHERE is_free=1", (now,))
    for i, s in enumerate(slugs, 1):
        ctx.conn.execute("UPDATE projects SET is_free=1, free_rank=?, "
                         "published_at=COALESCE(published_at, ?), updated_at=? WHERE slug=?",
                         (i, now, now, s))
    db.audit(ctx.conn, ent["user_id"], "admin.free_projects_set", "", {"slugs": slugs}, ip=ctx.ip)
    return response({"ok": True, "count": len(slugs), "slugs": slugs})


@route("GET", r"/api/admin/users")
def admin_users(ctx, m):
    require_admin(ctx)
    q = "%" + ctx.query.get("q", "").lower()[:80] + "%"
    rows = ctx.conn.execute(
        "SELECT u.id, u.email, u.name, u.role, u.disabled, u.created_at, u.last_login_at, "
        "s.plan, s.status AS sub_status, s.expires_at, s.provider "
        "FROM users u LEFT JOIN subscriptions s ON s.id=(SELECT id FROM subscriptions WHERE user_id=u.id "
        "ORDER BY updated_at DESC LIMIT 1) WHERE LOWER(u.email) LIKE ? OR LOWER(u.name) LIKE ? "
        "ORDER BY u.created_at DESC LIMIT 200", (q, q)).fetchall()
    return response({"users": [dict(r) for r in rows]})


@route("PATCH", r"/api/admin/users/(\d+)")
def admin_patch_user(ctx, m):
    ent = require_admin(ctx)
    uid = int(m.group(1))
    u = ctx.conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        raise ApiError(404, "User not found.", "not_found")
    b = ctx.body
    changes = {}
    if "role" in b and b["role"] in ("free", "pro", "admin"):
        if uid == ent["user_id"] and b["role"] != "admin":
            admins = ctx.conn.execute("SELECT COUNT(*) n FROM users WHERE role='admin' AND disabled=0").fetchone()["n"]
            if admins <= 1:
                raise ApiError(409, "Cannot remove the last active administrator.", "last_admin")
        ctx.conn.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (b["role"], time.time(), uid))
        changes["role"] = b["role"]
    if "disabled" in b:
        ctx.conn.execute("UPDATE users SET disabled=?, updated_at=? WHERE id=?",
                         (int(bool(b["disabled"])), time.time(), uid))
        changes["disabled"] = bool(b["disabled"])
    if b.get("grant_pro"):
        days = int(b.get("days", 30) or 30)
        billing.grant_pro(ctx.conn, uid, days, provider="manual", actor_id=ent["user_id"])
        changes["grant_pro"] = days
    if b.get("revoke_pro"):
        billing.revoke_pro(ctx.conn, uid, actor_id=ent["user_id"])
        changes["revoke_pro"] = True
    if "subscription_status" in b:
        ctx.conn.execute("UPDATE subscriptions SET status=?, updated_at=? WHERE user_id=?",
                         (str(b["subscription_status"])[:40], time.time(), uid))
        changes["subscription_status"] = b["subscription_status"]
    db.audit(ctx.conn, ent["user_id"], "admin.user_update", str(uid), changes, ip=ctx.ip)
    return response({"ok": True, "changes": changes})


@route("GET", r"/api/admin/usage")
def admin_usage(ctx, m):
    require_admin(ctx)
    rows = ctx.conn.execute(
        "SELECT u.email, u.role, e.kind, COUNT(*) n, MAX(e.created_at) last FROM usage_events e "
        "JOIN users u ON u.id=e.user_id GROUP BY u.id, e.kind ORDER BY n DESC LIMIT 100").fetchall()
    return response({"usage": [dict(r) for r in rows],
                     "daily": [dict(r) for r in ctx.conn.execute(
                         "SELECT date(created_at,'unixepoch') day, kind, COUNT(*) n FROM usage_events "
                         "WHERE created_at > ? GROUP BY day, kind ORDER BY day DESC LIMIT 60",
                         (time.time() - 86400 * 30,))]})


@route("GET", r"/api/admin/audit")
def admin_audit(ctx, m):
    require_admin(ctx)
    limit = min(int(ctx.query.get("limit", 100) or 100), 300)
    rows = ctx.conn.execute(
        "SELECT a.id, a.actor_id, u.email AS actor_email, a.action, a.target, a.detail_json, a.created_at, a.ip "
        "FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC LIMIT ?", (limit,)).fetchall()
    return response({"logs": [{"id": r["id"], "actor_id": r["actor_id"], "actor_email": r["actor_email"],
                               "action": r["action"], "target": r["target"],
                               "detail": redact(json.loads(r["detail_json"] or "{}")),
                               "created_at": r["created_at"], "ip": r["ip"]} for r in rows]})


@route("GET", r"/api/admin/health")
def admin_health(ctx, m):
    require_admin(ctx)
    c = ctx.conn
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    return response({
        "database": {"integrity": integrity, "path": str(config.DB_PATH), "wal": True},
        "integrations": {
            "ai": ai.ai_status(c), "payments": billing.payments_config(c),
            "mqtt": db.get_setting(c, "platform", {}).get("integrations", {}).get("mqtt", {}),
            "http_ingest": {"enabled": True, "endpoint": "/api/ingest/<device_token>"},
        },
        "environment": {"port": config.PORT, "session_ttl": config.SESSION_TTL_SECONDS,
                        "pbkdf2_iterations": config.PBKDF2_ITERATIONS,
                        "env_ai_key_present": bool(config.AI_ENV_KEY),
                        "stripe_key_present": bool(config.STRIPE_SECRET_KEY)},
        "recent_errors": [dict(r) for r in c.execute(
            "SELECT action, target, created_at FROM audit_logs WHERE action LIKE 'security.%' "
            "OR action LIKE 'billing.webhook_rejected' ORDER BY created_at DESC LIMIT 20")],
        "secret_policy": "Secrets are never returned by this API. Admin-entered keys are encrypted at rest; only a masked hint is shown.",
    })


@route("GET", r"/api/admin/quality")
def admin_quality(ctx, m):
    require_admin(ctx)
    rows = ctx.conn.execute("SELECT id, slug, title, status, quality_status, content_json FROM projects").fetchall()
    required = ["overview", "bom", "architecture", "circuit", "procedure", "code",
                "troubleshooting", "testing", "deliverables", "quality"]
    report = []
    for r in rows:
        c = json.loads(r["content_json"])
        issues = []
        missing = [k for k in required if k not in c]
        if missing:
            issues.append("missing sections: " + ", ".join(missing))
        if c.get("circuit", {}).get("validation", {}).get("summary", {}).get("errors", 0):
            issues.append("circuit validation errors")
        fw = c.get("code", {}).get("code", "")
        if re.search(r'(password|api_key|token)\s*=\s*"(?!YOUR_)[^"\n]{8,}"', fw, re.I):
            issues.append("possible hard-coded credential")
        if not c.get("testing", {}).get("functional_tests"):
            issues.append("no functional tests")
        report.append({"id": r["id"], "slug": r["slug"], "title": r["title"], "status": r["status"],
                       "quality_status": r["quality_status"], "issues": issues,
                       "ready": not issues and r["status"] == "published"})
    return response({"report": report, "total": len(report),
                     "passing": sum(1 for x in report if x["ready"]),
                     "failing": sum(1 for x in report if not x["ready"])})


@route("GET", r"/api/admin/config")
def admin_get_config(ctx, m):
    require_admin(ctx)
    platform = db.get_setting(ctx.conn, "platform", {})
    ai_cfg = dict(platform.get("ai", {}))
    ai_cfg.pop("api_key_encrypted", None)
    ai_cfg["api_key_hint"] = ai.ai_status(ctx.conn)["api_key_hint"]
    ai_cfg["env_key_present"] = bool(config.AI_ENV_KEY)
    return response({
        "platform": {**platform, "ai": ai_cfg},
        "limits": db.get_setting(ctx.conn, "limits", {}),
        "public_free_feature_policy": db.get_setting(ctx.conn, "public_free_feature_policy", {}),
        "project_quality": db.get_setting(ctx.conn, "project_quality", {}),
        "categories": [c["name"] for c in seed.categories(ctx.conn)],
        "secret_policy": "API keys are write-only. Only a masked hint is ever returned.",
    })


@route("PATCH", r"/api/admin/config")
def admin_patch_config(ctx, m):
    ent = require_admin(ctx)
    b = ctx.body
    changed = []
    if isinstance(b.get("ai"), dict):
        platform = db.get_setting(ctx.conn, "platform", {})
        cur = dict(platform.get("ai", {}))
        for k in ("provider", "base_url", "model", "enabled", "note"):
            if k in b["ai"]:
                cur[k] = b["ai"][k] if k != "provider" or b["ai"][k] in ("offline", "openai_compatible") else cur[k]
        if b["ai"].get("api_key"):
            cur["api_key_encrypted"] = encrypt_secret(str(b["ai"]["api_key"])[:500])
            cur["api_key_hint"] = mask_secret(str(b["ai"]["api_key"]))
            changed.append("ai.api_key (encrypted, not logged)")
        platform["ai"] = cur
        db.set_setting(ctx.conn, "platform", platform)
        from .providers import registry
        migrated = {k: v for k, v in b['ai'].items() if k in ('provider','base_url','model','enabled','api_key')}
        if migrated.get('provider') == 'offline': migrated['provider'] = 'none'
        registry.save(ctx.conn, {'chat': migrated})
        changed.append("ai")
    if isinstance(b.get("payments"), dict):
        platform = db.get_setting(ctx.conn, "platform", {})
        cur = dict(platform.get("payments", {}))
        for k in ("plan_name", "currency", "amount", "interval", "trial_days", "manual_activation_enabled"):
            if k in b["payments"]:
                cur[k] = b["payments"][k]
        platform["payments"] = cur
        db.set_setting(ctx.conn, "platform", platform)
        changed.append("payments")
    if isinstance(b.get("integrations"), dict):
        platform = db.get_setting(ctx.conn, "platform", {})
        platform["integrations"] = {**platform.get("integrations", {}), **b["integrations"]}
        db.set_setting(ctx.conn, "platform", platform)
        changed.append("integrations")
    if isinstance(b.get("categories"), list):
        names = [str(x).strip()[:80] for x in b["categories"] if str(x).strip()]
        if not 1 <= len(names) <= 80:
            raise ApiError(400, "Provide between 1 and 80 category names.", "invalid_input")
        db.set_setting(ctx.conn, "categories", list(dict.fromkeys(names)))
        changed.append("categories")
    for key in ("limits", "public_free_feature_policy", "project_quality"):
        if isinstance(b.get(key), dict):
            db.set_setting(ctx.conn, key, {**db.get_setting(ctx.conn, key, {}), **b[key]})
            changed.append(key)
    if not changed:
        raise ApiError(400, "No recognised configuration section supplied.", "invalid_input")
    db.audit(ctx.conn, ent["user_id"], "admin.config_update", "", {"sections": changed}, ip=ctx.ip)
    return response({"ok": True, "changed": changed, "ai": ai.ai_status(ctx.conn),
                     "payments": billing.payments_config(ctx.conn)})


@route("GET", r"/api/admin/analytics")
def admin_analytics(ctx, m):
    require_admin(ctx)
    since = time.time() - 86400 * 30
    views = ctx.conn.execute(
        "SELECT meta_json, created_at, user_id FROM usage_events WHERE kind='project_view' AND created_at > ?",
        (since,)).fetchall()
    by_project, by_category, by_tier, by_day = {}, {}, {}, {}
    for v in views:
        try:
            meta = json.loads(v["meta_json"])
        except ValueError:
            meta = {}
        slug = meta.get("slug", "unknown")
        cat = meta.get("category", "unknown")
        tier = meta.get("tier", "unknown")
        day = datetime.fromtimestamp(v["created_at"], timezone.utc).strftime("%Y-%m-%d")
        by_project[slug] = by_project.get(slug, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
        by_tier[tier] = by_tier.get(tier, 0) + 1
        by_day[day] = by_day.get(day, 0) + 1
    tool_rows = ctx.conn.execute(
        "SELECT tool, COUNT(*) n FROM tool_runs WHERE created_at > ? GROUP BY tool ORDER BY n DESC", (since,)).fetchall()
    return response({
        "window_days": 30, "total_project_views": len(views),
        "top_projects": sorted([{"slug": k, "views": n} for k, n in by_project.items()],
                               key=lambda x: -x["views"])[:20],
        "by_category": sorted([{"category": k, "views": n} for k, n in by_category.items()], key=lambda x: -x["views"]),
        "by_tier": by_tier,
        "by_day": [{"day": k, "views": v} for k, v in sorted(by_day.items())],
        "tool_runs": [dict(r) for r in tool_rows],
        "note": "Derived from server-recorded project_view and tool_runs events; no client-side analytics."})



@route("GET", r"/api/admin/subscriptions-analytics")
def admin_subscriptions_analytics(ctx, m):
    require_admin(ctx)
    c = ctx.conn
    now = time.time()
    
    total_users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    pro_users = c.execute("SELECT COUNT(*) n FROM users WHERE role='pro'").fetchone()["n"]
    free_users = c.execute("SELECT COUNT(*) n FROM users WHERE role='free'").fetchone()["n"]
    admin_users = c.execute("SELECT COUNT(*) n FROM users WHERE role='admin'").fetchone()["n"]
    
    active_subs = c.execute("SELECT COUNT(*) n FROM subscriptions WHERE plan='pro' AND status IN ('active','trialing') AND (expires_at IS NULL OR expires_at > ?)", (now,)).fetchone()["n"]
    expired_subs = c.execute("SELECT COUNT(*) n FROM subscriptions WHERE plan='pro' AND (status='expired' OR (expires_at IS NOT NULL AND expires_at <= ?))", (now,)).fetchone()["n"]
    cancelled_subs = c.execute("SELECT COUNT(*) n FROM subscriptions WHERE status IN ('cancelled','canceled')", ()).fetchone()["n"]

    # Subscriber breakdown by provider
    providers_rows = c.execute("SELECT provider, COUNT(*) n FROM subscriptions GROUP BY provider").fetchall()
    by_provider = {r["provider"] or "manual": r["n"] for r in providers_rows}

    # Revenue estimation (INR ₹ and USD $)
    # Active pro subscriptions: default ₹249/mo or $3/mo
    rev_inr = active_subs * 249
    rev_usd = active_subs * 3

    # Recent subscriber records
    subscribers = [dict(r) for r in c.execute(
        "SELECT s.id, s.user_id, u.email, u.name, s.plan, s.status, s.provider, s.started_at, s.expires_at "
        "FROM subscriptions s JOIN users u ON u.id=s.user_id "
        "ORDER BY s.updated_at DESC LIMIT 50"
    ).fetchall()]

    return response({
        "total_users": total_users,
        "free_users": free_users,
        "pro_users": pro_users,
        "admin_users": admin_users,
        "active_subscriptions": active_subs,
        "expired_subscriptions": expired_subs,
        "cancelled_subscriptions": cancelled_subs,
        "revenue": {
            "inr": rev_inr,
            "usd": rev_usd,
            "currency_symbols": {"inr": "₹", "usd": "$"}
        },
        "by_provider": by_provider,
        "subscribers": subscribers
    })


@route("POST", r"/api/admin/ai-test")
def admin_ai_test(ctx, m):
    require_admin(ctx)
    from .providers import registry
    return response(registry.health(ctx.conn, force=True))

# Additive engineering-workstation routes; imported after route helpers exist.
from . import workstation_api  # noqa: E402,F401
