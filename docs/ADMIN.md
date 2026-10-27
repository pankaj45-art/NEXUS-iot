# Administrator guide

All admin endpoints require a session whose **server-derived** role is `admin`. The SPA
hides admin navigation from non-admins, but hiding is cosmetic — `require_admin()` runs on
every `/api/admin/*` handler.

## Signing in

```bash
python3 scripts/bootstrap_admin.py admin@example.com
python3 run.py
# open http://localhost:8000, sign in, click "Admin Workspace"
```

## Tabs

### Overview
Live counts: users, active Pro, published projects, drafts, free projects, tool runs/24h,
devices, telemetry rows, AI/payment integration status, recent audit events.

### Projects
All records and statuses. Create a draft (a complete structured record is compiled from the
catalog), edit title/category/difficulty/status/quality, validate the circuit, duplicate,
publish/unpublish/archive/delete.

**Publication gate:** the Publish action refuses when the quality status is below
`project_quality.minimum_status_for_publish` (default `Technically reviewed`), when a
required A–J section is missing, or when the circuit validator reports ERROR issues. A
direct `PATCH` to `status=published` applies the same gate.

Quality statuses: `Draft`, `Content incomplete`, `Technically reviewed`,
`Ready for publication`, `Physically tested`. The last one requires real dated test evidence;
the seeded library never sets it.

### The Free 15
Reorder with ↑/↓, remove, or add any **already published** project, then **Save
designation**. `PUT /api/admin/free-projects` accepts at most 15 slugs, writes `is_free`
and `free_rank`, and audits the change. Free users see exactly these rows. No code change or
restart is required.

### Users
Search users; set role (`free`/`pro`/`admin`), grant Pro for N days, set subscription status,
revoke Pro, or disable an account. All changes are audited. The last active admin cannot be
demoted. Users' private workspaces are not visible here.

### AI & Config
- AI provider: `offline` (default) or `openai_compatible`, base URL, model, enable flag,
  write-only API key (encrypted at rest), and **Test connection**.
- Plans & payments: plan name, price, currency, interval, trial days. Credentials are read
  from environment variables only.
- Usage limits: per-tier JSON (AI requests/day, tool calls/day, workspaces, projects,
  max code chars).
- Free feature policy: open individual Pro tools to Free users without a code change.
- Integrations: MQTT broker/topic/enable; HTTP ingest is always enabled.
- Category taxonomy: rename/add the 25 library categories at runtime (one per line).
  Per-project tags are editable in Projects → Edit.
- Quality gate: minimum status for publication.

No admin API returns an API key, password hash, session token or webhook secret. Only masked
hints. Admin audit details are passed through `security.redact()` before display.

### Analytics
Server-recorded project views over 30 days: most-viewed projects, views by category and
tier, daily views and tool-run counts. No client-side analytics or tracking pixels.

### Usage & Audit
Per-user usage, 30-day daily aggregates, and the audit log (actor, action, target, time,
IP). Security events such as `security.privilege_escalation_attempt` and
`billing.webhook_rejected` appear here.

### Quality & Health
DB `PRAGMA integrity_check`, integration flags, environment presence flags (never values),
recent security events, and a per-project quality report (missing sections, circuit errors,
possible hardcoded credentials, missing functional tests, readiness).

## CLI reference

```bash
python3 scripts/bootstrap_admin.py admin@example.com
python3 scripts/manage.py list-users
python3 scripts/manage.py entitle user@example.com pro --days 30
python3 scripts/manage.py revoke user@example.com
python3 scripts/manage.py set-role user@example.com free|pro|admin
python3 scripts/manage.py set-password user@example.com
python3 scripts/manage.py reseed
```

## Operational notes

- Secrets: `NEXUS_SECRET` (or `data/.app_secret`) is required to decrypt admin-entered API
  keys. Back it up together with the database.
- Sessions: random 256-bit tokens stored as SHA-256 digests; cookies HMAC-signed; CSRF
  double-submit; 14-day TTL configurable via `NEXUS_SESSION_TTL`.
- Passwords: PBKDF2-HMAC-SHA256, 240,000 iterations, per-user salt. Login is rate-limited
  to 12 failures per IP per 15 minutes.
- Logs: request lines are truncated and never include cookies, tokens or bodies. Errors log
  only the exception type and path.
