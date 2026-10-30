"""Zero-dependency threaded HTTP server for NEXUS IoT."""
from __future__ import annotations

import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import api, config, db, seed

# The live preview is embedded in a cross-site iframe. If the frame has an
# opaque origin, its relative fetches are treated as cross-origin by the browser,
# so explicitly allow the known preview/Arena origins (never a wildcard with
# credentials). Same-origin requests simply ignore these headers.
CORS_ORIGIN = re.compile(
    r"^https://([a-z0-9-]+\.)*(e2b\.app|arena\.ai)$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    re.IGNORECASE)

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8", ".png": "image/png",
    ".jpg": "image/jpeg", ".ico": "image/x-icon", ".woff2": "font/woff2",
    ".md": "text/markdown; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "NEXUS/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Never log cookies, tokens or query strings with secrets.
        try:
            line = fmt % args
            if '"' in line and " " in line:
                line = line.split('"')[0].strip() + ' "request"'
            sys.stdout.write(f"[NEXUS] {self.address_string()} {line}\n")
        except Exception:
            pass

    def _send(self, status, headers, body):
        self.send_response(status)
        for k, v in headers.items():
            if isinstance(v, (list, tuple)):
                for item in v:
                    self.send_header(k, str(item))
            else:
                self.send_header(k, str(v))
        origin = self.headers.get("Origin", "")
        # A fully sandboxed frame reports Origin: null and cannot send cookies;
        # allow it without credentials (the SPA uses its bearer fallback there).
        if origin == "null":
            self.send_header("Access-Control-Allow-Origin", "null")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, X-CSRF-Token, Authorization")
            self.send_header("Access-Control-Allow-Methods",
                             "GET, POST, PATCH, PUT, DELETE, OPTIONS")
            self.send_header("Vary", "Origin")
        elif origin and CORS_ORIGIN.match(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, X-CSRF-Token, Authorization")
            self.send_header("Access-Control-Allow-Methods",
                             "GET, POST, PATCH, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition")
            self.send_header("Vary", "Origin")
        elif origin:
            # Unknown embedding host: allow the read without ever allowing
            # credentials. The SPA's bearer fallback still works here.
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, X-CSRF-Token, Authorization")
            self.send_header("Access-Control-Allow-Methods",
                             "GET, POST, PATCH, PUT, DELETE, OPTIONS")
            self.send_header("Vary", "Origin")
        streaming = not isinstance(body, (bytes, bytearray))
        if not streaming:
            self.send_header("Content-Length", str(len(body)))
        else:
            self.close_connection = True
        # NOTE: no X-Frame-Options / frame-ancestors directive: the Arena live
        # preview embeds this app in a sandboxed cross-origin iframe. A production
        # reverse proxy should add an explicit frame-ancestors allowlist.
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Include this server's own host explicitly: in an opaque-origin frame
        # 'self' is opaque, which would otherwise block /app.js and /api calls.
        host = self.headers.get("Host", "").split(",")[0].strip()
        own = ""
        if re.match(r"^[A-Za-z0-9.-]+(?::\d+)?$", host):
            own = f" http://{host} https://{host}"
        self.send_header("Content-Security-Policy",
                         f"default-src 'self'{own}; script-src 'self'{own}; "
                         f"style-src 'self'{own} 'unsafe-inline'; "
                         f"img-src 'self'{own} data: blob:; connect-src 'self'{own}; "
                         f"font-src 'self'{own}")
        self.end_headers()
        if self.command != "HEAD":
            try:
                if streaming:
                    for chunk in body:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # Client closed the event stream; job remains persisted and may
                # be followed by polling or explicitly cancelled.
                pass

    def do_OPTIONS(self):
        self._send(204, {"Allow": "GET, POST, PATCH, PUT, DELETE, OPTIONS"}, b"")

    def _handle(self, method):
        parsed = urlparse(self.path)
        path = unquote_path = parsed.path
        # Normalise to prevent path traversal in the static handler.
        if path.startswith("/api/"):
            if os.environ.get("NEXUS_DEBUG") == "1":
                keys = {k.lower() for k in self.headers.keys()}
                print(f"[NEXUS REQ] {method} {path} origin={self.headers.get('Origin', '-')!r} "
                      f"cookie={'cookie' in keys} bearer={'authorization' in keys} "
                      f"csrf={'x-csrf-token' in keys} xfp={self.headers.get('X-Forwarded-Proto', '-')}",
                      flush=True)
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 3_000_000:
                self._send(413, {"Content-Type": "application/json"},
                           b'{"error":{"code":"too_large","message":"Request body too large."}}')
                return
            raw = self.rfile.read(length) if length else b""
            ctx = api.Context(self, method, path, parsed.query, raw, self.headers)
            try:
                status, headers, body = api.dispatch(ctx)
            finally:
                ctx.close()
            self._send(status, headers, body)
            return
        if path.startswith("/ingest/"):
            path = "/api" + path
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length else b""
            ctx = api.Context(self, method, path, parsed.query, raw, self.headers)
            try:
                status, headers, body = api.dispatch(ctx)
            finally:
                ctx.close()
            self._send(status, headers, body)
            return
        if method not in ("GET", "HEAD"):
            self._send(405, {"Content-Type": "application/json"},
                       b'{"error":{"code":"method_not_allowed","message":"Method not allowed."}}')
            return
        self._static(path)

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        target = (config.WEB_DIR / rel).resolve()
        try:
            target.relative_to(config.WEB_DIR.resolve())
        except ValueError:
            self._send(403, {"Content-Type": "text/plain"}, b"Forbidden")
            return
        if not target.exists() or target.is_dir():
            if "." not in rel:  # SPA routes
                target = config.WEB_DIR / "index.html"
            else:
                self._send(404, {"Content-Type": "text/plain"}, b"Not found")
                return
        ctype = MIME.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self._send(200, {"Content-Type": ctype,
                         "Cache-Control": "no-store" if target.suffix in (".html", ".js", ".css") else "public, max-age=3600"}, data)

    do_GET = lambda self: self._handle("GET")  # noqa: E731
    do_HEAD = lambda self: self._handle("HEAD")  # noqa: E731
    do_POST = lambda self: self._handle("POST")  # noqa: E731
    do_PATCH = lambda self: self._handle("PATCH")  # noqa: E731
    do_PUT = lambda self: self._handle("PUT")  # noqa: E731
    do_DELETE = lambda self: self._handle("DELETE")  # noqa: E731


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def ensure_admin(conn):
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

    conn.commit()

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
        conn.close()
    server = Server((config.HOST, config.PORT), Handler)
    print(f"[NEXUS] NEXUS IoT ready on http://{config.HOST}:{config.PORT}", flush=True)
    print(f"[NEXUS] Data: {config.DB_PATH}", flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n[NEXUS] Shutting down.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
