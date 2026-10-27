# Architecture

## Stack

- **Backend:** Python 3.10+ standard library (`http.server.ThreadingHTTPServer` +
  `sqlite3`), no framework, no mandatory dependencies.
- **Frontend:** vanilla ES-module SPA (`web/app.js`), CSS with no external assets, hash
  router, all API calls relative to the same origin.
- **Database:** SQLite, WAL, foreign keys, additive versioned migrations (original tables preserved).
- Project views are recorded as `project_view` usage events and surfaced in Admin →
  Analytics; the free project-creation limit is enforced by `consume()` before any
  workspace row is inserted.
- **Why zero dependencies?** The runtime environment cannot guarantee `pip install`
  persistence. Using only the stdlib makes the delivered folder runnable anywhere.

## Request lifecycle

```
Browser ──relative /api/...──> nexus/server.py Handler._handle()
   └─> api.Context(method, path, query, body, headers) → opens one SQLite connection
        └─> api.dispatch()
             ├─ parse_body (3 MB cap, JSON or form)
             ├─ load_user (signed HttpOnly cookie OR Bearer token → sessions → users)
             ├─ check_csrf (double-submit X-CSRF-Token for state changes)
             ├─ route match → handler
             │    ├─ require_auth / require_admin / require_feature
             │    ├─ entitlements.resolve() from DB users + subscriptions
             │    ├─ library_predicate() / project_visible_to() inside every query
             │    └─ business logic
             └─ response(status, headers, JSON/bytes) → security headers → browser
```

Security headers on every response: CSP (`default-src 'self'`, no inline scripts),
`X-Content-Type-Options: nosniff`, `Referrer-Policy`, and `Cache-Control: no-store` for API
JSON. `X-Frame-Options` / `frame-ancestors` are intentionally omitted so the Arena live
preview can embed the app in its sandboxed iframe; a production reverse proxy should add
an explicit `frame-ancestors` allowlist for its own domain. All dynamic content is HTML-escaped in the SPA.

### Session transport

`POST /api/auth/login|register` creates one row in `sessions` (opaque token stored only as a
SHA-256 hash) and returns it two ways: an HMAC-signed `HttpOnly` cookie, and a
`session_token` value in the JSON body. `load_user()` accepts either the cookie or
`Authorization: Bearer <token>`; both resolve to the same hashed server-side session, so
expiry, revocation, role changes and CSRF apply identically. On a normal top-level origin
the cookie is `SameSite=Lax`; behind an HTTPS preview proxy it is
`SameSite=None; Secure` because the frame is cross-site. The SPA keeps the token in
`sessionStorage` (with a guarded in-memory fallback for opaque-origin sandboxes) and sends
both `Authorization` and `X-CSRF-Token` on every request. CORS is allowed only for the
known preview/Arena origins, never a wildcard with credentials; `Origin: null` frames are
allowed **without** credentials. Returning the token in the login body is what makes the
app usable when a browser blocks third-party cookies — it is never written to logs, and
CSRF is still required for every state-changing request. The login/register response also
carries the **complete** `session` (user, entitlement, usage) and the public `config`, plus
a signed cookie value and a `build` marker. The SPA therefore opens the workspace from that
single response and does not need a follow-up `/api/auth/me` request — so a preview proxy
that drops cookies, custom headers or `Set-Cookie` cannot bounce the user back to sign-in.
As a third transport the SPA also writes the signed cookie from JS when the frame permits it.
Static assets are versioned (`/app.js?v=5`) and served `no-store` to defeat stale cached
copies of the SPA in embedded previews. `NEXUS_DEBUG=1` logs only request method, path and
header *names* (never values) for diagnosing preview transports.

If a preview proxy also strips `Authorization` **and** blocks cookies, the SPA detects the
resulting `401` and retries that request with `?nx_session=<token>`; a successful retry
switches the SPA to "query transport" for the rest of the session (shown as a **Preview
session** badge in the top bar). `load_user()` accepts that token through the same hashed
session lookup, and state-changing requests carry `nx_csrf` in the JSON body when the
CSRF header is unavailable. This fallback is used only after the secure transports fail,
is never written to logs (the server logs the path, not the query string), and is never
used for static files. `Referrer-Policy: strict-origin-when-cross-origin` and the
same-origin CSP prevent the token leaking to third parties. Exports (`/download?kind=...`)
and the generated SVG diagram are **never** plain `<a href>`/`<img src>` API links: the SPA
fetches them through `sessionFetch()` and shows the text in a modal or injects the SVG via a
blob URL, so they inherit the same transports, entitlement check and 401 fallback. For a production deployment,
set `NEXUS_ALLOW_QUERY_SESSION=0` to disable this fallback entirely.

For a hardened production deployment you may disable the bearer fallback by removing
`session_token` from the two auth responses; cookie-based auth then works unchanged.

## Database schema (summary)

`users` · `subscriptions` · `sessions` · `settings` · `projects` · `usage_events` ·
`tool_runs` · `workspaces` · `workspace_events` · `devices` · `telemetry` ·
`audit_logs` · `debug_attempts` · `login_attempts` · `user_settings`.

`projects.content_json` holds the complete structured A–J record; metadata columns
(`slug,title,category,difficulty,board,comms,is_free,free_rank,status,quality_status,
version,...`) are indexed for fast visibility-filtered queries.

## Content pipeline

```
data/spec_base.py  S(...) DSL + 25 categories
data/specs_free.py 15 curated free specs
data/specs_pro_*.py 102 distinct Pro specs
        │
        ▼
compiler.compile_spec(spec)
   ├─ hardware.assign_pins(board, parts)      # reserves I2C/SPI/UART/CS buses first
   ├─ validator.validate(...)                 # 8 rule families, wiring table, issues
   ├─ codegen.generate_firmware(...)          # Arduino C++ or Python 3 from the SAME pins
   ├─ _steps(...) / troubleshooting / testing/ deliverables / quality
   └─ returns structured content dict (~54 KB average)
        │
        ▼
seed.seed_projects() → projects table (idempotent; admin edits preserved)
        │
        ├─ diagram.render_svg(content)        # project-specific SVG block diagram
        ├─ export.render_download(...)        # Markdown / CSV / JSON / code / SVG
        └─ api.py project endpoints           # visibility gated
```

Because BOM, wiring table, pin map and firmware are all derived from one
`assign_pins()` result, they stay mutually consistent. Tests verify every numeric pin macro
in the firmware exists in the same pin assignment as the wiring table, that Python
firmware parses, that Arduino braces/parens balance, and that no unresolved `@TOKEN@`
remains.

## AI engine

`ai.py` exposes `get_ai_config()`, `ai_status()`, `llm_complete()`, `enrich()`,
`references_for()` and `split_facts_hypotheses()`.

- **Offline (default):** deterministic rule engine built on `hardware.py` (73 components,
  7 board profiles), `validator.py`, `codegen.py` and a 28-URL real documentation corpus.
  It is fully functional and never pretends to be an LLM.
- **Live (optional):** an OpenAI-compatible `/chat/completions` call with a 25 s timeout.
  Its output is a labelled `llm_narrative`; deterministic values are never replaced.
  On failure legacy enrichment reports a separate `provider_error`; online chat itself fails honestly and never returns a fallback answer.
- Secrets come from the environment or an admin-entered, encrypted-at-rest value. They are
  never returned by the API or logged.

`tools.py` implements the 10 Pro tools plus the free general assistant. `run_tool()`
persists input, output and mode in `tool_runs`, so results are re-openable and auditable.

## Payments

`billing.py`: Stripe Checkout Session creation over `urllib` (form-encoded),
`verify_webhook_signature()` with HMAC-SHA256 + timestamp tolerance + constant-time compare,
`apply_webhook_event()` mapping verified events to `grant_pro()` / `revoke_pro()` /
`past_due`. No Stripe SDK required. Checkout is disabled with an explanatory `409` when
credentials are missing.

## Live preview

`HOST=0.0.0.0`, `PORT=8000`. `server.py` serves `web/` with SPA fallback and correct MIME
types. No CDN, external font, external stylesheet or absolute API URL is used, so the
sandboxed iframe preview and proxied preview host both work. The CSP lists the request's own
host explicitly (as well as `'self'`) because a fully sandboxed frame has an opaque origin;
`do_OPTIONS` returns CORS headers for preview origins so relative API calls work there too.

## Known design trade-offs

- Arduino sketches are **statically reviewed**, not compiled: no Arduino toolchain is
  installed in this environment. Library versions and board-core API differences (e.g.
  `ledcSetup` vs `ledcAttach` on ESP32 core 3.x) are called out inline.
- The stdlib HTTP server is threaded and suitable for development/small deployments. Put
  it behind a TLS reverse proxy (nginx/Caddy) for production; the app itself sets secure
  cookie flags and security headers but does not terminate TLS.
- MQTT bridging needs the optional `paho-mqtt` package; HTTP ingest works without it and
  the UI states the difference.


## Connected services (build 6)

`nexus/providers/{base,registry,openai_compat,ollama}.py` owns provider contracts,
write-only encrypted configuration, independent capabilities, bounded HTTP/SSE calls
and typed failures. `services/chat.py` builds chronological conversation history and
only the selected owned UUID project's context. `services/jobs.py` persists jobs and
SSE deltas, supports event polling/cancellation and bounded worker reservations.

`migrations.py` adds engineering projects/immutable versions, conversations/messages,
jobs/events, generated images, text attachments and reviewed component definitions.
No existing library/workspace/user record is overwritten. SQL owner predicates apply
to every private resource; administrators do not implicitly read another user's private
engineering project. `workstation_api.py` extends the existing authenticated dispatcher.

`services/circuits.py` defines `nexus.circuit/1`: stable component IDs/models/positions,
exact terminal edges, board configuration and metadata. Nets, wiring, SVG, rule findings
and managed source constants derive from that graph. `services/designs.py` stores a
`nexus.project/1` spec with requirements, circuit, firmware, build guide, references,
tests and debugging notes. Saves use optimistic revisions and atomic immutable snapshots.

`services/invention.py` asks the configured model for structured requirements and
supported component IDs; unknowns remain explicit. `code_ai.py` proposes source and a
diff, rejects changed canonical pins, and never runs code. `images.py` calls the real
independent image service, validates actual image bytes and stores protected assets.
`research.py` performs configured external search or explicitly labels curated matching.

The frontend remains the same SPA: `app.js` retains existing screens; `workstation.js`
and `studio.js` add connected engineering screens. All protected resources use the
shared session fetch transports, including streamed job events, exports and images.
All rendered model/file text is escaped; generated images are authenticated data URIs.
