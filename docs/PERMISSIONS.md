# Permission matrix, entitlements and enforcement

## Single source of truth

`nexus/entitlements.py` holds `FEATURES` — the permission matrix — plus `resolve()`,
`has_feature()`, `require_feature()`, `require_admin()`, `project_visible_to()`,
`library_predicate()`, `usage_snapshot()` and `consume()`. New Pro tools are added to this
matrix and automatically inherit the same authorization. The browser never supplies a role,
plan or status: `load_user()` resolves the session from the DB and `resolve()` derives the
effective tier from `users` + `subscriptions` on every request.

## Matrix (27 features)

| Feature | Free | Pro | Admin |
|---|:---:|:---:|:---:|
| `general_ai` — limited general AI assistance | ✅ | ✅ | ✅ |
| `library.free` — the 15 designated free projects | ✅ | ✅ | ✅ |
| `learning.basic` — 6 curated learning modules | ✅ | ✅ | ✅ |
| `workspace.basic` — own saved projects (limited) | ✅ | ✅ | ✅ |
| `account.manage` — profile, password, own saved preferences, subscription status | ✅ | ✅ | ✅ |
| `upgrade.view` — pricing / upgrade page | ✅ | ✅ | ✅ |
| `library.all` — full 100+ project library | ❌ | ✅ | ✅ |
| `ai.advanced` — advanced AI assistance | ❌ | ✅ | ✅ |
| `tools.project_generator` | ❌ | ✅ | ✅ |
| `tools.circuit_designer` | ❌ | ✅ | ✅ |
| `tools.code_engineer` | ❌ | ✅ | ✅ |
| `tools.debugging` | ❌ | ✅ | ✅ |
| `tools.innovation` | ❌ | ✅ | ✅ |
| `tools.comparison` | ❌ | ✅ | ✅ |
| `tools.startup_lab` | ❌ | ✅ | ✅ |
| `tools.research` | ❌ | ✅ | ✅ |
| `tools.device_monitoring` | ❌ | ✅ | ✅ |
| `tools.project_docs` | ❌ | ✅ | ✅ |
| `workspace.full` — unlimited workspaces + version history | ❌ | ✅ | ✅ |
| `exports` — code / wiring / BOM / Markdown / JSON / SVG | ❌ | ✅ | ✅ |
| `admin.dashboard` | ❌ | ❌ | ✅ |
| `admin.projects` | ❌ | ❌ | ✅ |
| `admin.free_designation` | ❌ | ❌ | ✅ |
| `admin.users` | ❌ | ❌ | ✅ |
| `admin.config` | ❌ | ❌ | ✅ |
| `admin.audit` | ❌ | ❌ | ✅ |
| `admin.analytics` | ❌ | ❌ | ✅ |

**Pro is not admin.** A Pro user receives no admin feature and cannot open any
`/api/admin/*` endpoint. The last active administrator cannot be demoted.

Administrators may open an individual Pro tool to free users at runtime with
`public_free_feature_policy.allowed_pro_tools` (Admin → AI & Config). This is an explicit,
audited policy change, not a client-side flag.

## Where enforcement happens

| Surface | Enforcement |
|---|---|
| `GET /api/projects` | SQL `library_predicate()`: Free → `status='published' AND is_free=1`; Pro → `status='published'`; Admin → all. Locked rows are never serialized. |
| `GET /api/projects/<slug>` | `project_visible_to()`; locked → generic `403 upgrade_required` with no protected fields. Draft → `404` (no existence leak). |
| `GET /api/projects/<slug>/diagram.svg`, `/download` | Same gate **plus** `exports` feature for downloads. Files are generated server-side from `content_json`. |
| `POST /api/tools/<name>` | `require_feature(ent, "tools.<name>")` in the API **and** inside `run_tool()`; `consume()` enforces daily tool/AI limits. |
| `POST /api/assistant` | `require_feature(general_ai)` + daily AI request limit. |
| `POST /api/admin/*`, `GET /api/admin/*` | `require_admin()` at the top of every handler. |
| `POST /api/profile` | Only `name` is updated; `role`/`plan`/`status` keys are ignored and logged. |
| `GET/PATCH /api/settings` | Per-user whitelist (`units`, `default_board`, `notifications`, `theme`, `auto_save_notes`); unknown/privileged keys are dropped. |
| `GET /api/learning` | `learning.basic`; returns curated modules with real documentation URLs. |
| `POST /api/billing/webhook` | No session; HMAC-SHA256 signature verified against the server secret. |
| `POST /api/ingest/<token>` | Device token hash lookup; no user session required. |
| State-changing requests | HMAC-signed session cookie + double-submit CSRF token (`X-CSRF-Token`). |

## Subscription states

`subscriptions` stores `user_id, plan, status, provider, provider_customer_id,
provider_subscription_id, started_at, expires_at, cancelled_at, created_at, updated_at`.

- `active` / `trialing` with `expires_at` in the future → Pro.
- `past_due` → Pro for a documented **3-day grace window**, then Free.
- `cancelled`, `expired`, `unpaid`, `inactive`, or active-but-expired → Free. An active row
  whose expiry has passed is reported as `expired`.
- `admin` role always resolves to the admin tier, independent of subscription.

Expiry/cancellation removes Pro-only access but **preserves** workspaces, tool runs,
devices, settings and saved projects. Limits are configurable per tier in the `settings`
table:

| Limit | Free (default) | Pro | Admin |
|---|---|---|---|
| AI requests / day | 8 | 250 | 500 |
| Tool calls / day | 0 (no Pro tools) | 400 | 1000 |
| Workspaces | 5 | unlimited | unlimited |
| Created projects (total) | 3 | unlimited | unlimited |
| Max code chars | 4,000 | 60,000 | 120,000 |

## Payment trust model

1. User clicks **Continue to secure checkout** → server creates a Stripe Checkout Session
   with `client_reference_id=<user id>`.
2. User pays on Stripe's hosted page.
3. Stripe POSTs a signed webhook → server verifies `Stripe-Signature`, then grants Pro only
   for `payment_status=paid` or a verified `active`/`trialing` subscription.
4. The success redirect (`/#/subscription?checkout=success`) is informational only.

Never trust a frontend success flag. If Stripe is unconfigured, checkout returns
`409 payments_not_configured` with setup instructions. Manual activation after a confirmed
offline payment is the documented `scripts/manage.py entitle` path and is audited.


## New private engineering resources (build 6)

- General online assistant: all authenticated tiers; daily request limit, real provider
  configuration required. No artificial Pro-only model gate.
- Free basic design creation: at most two high-level supported components/request,
  within the shared created-project limit. Free users can read their own saved designs
  and edit requirements; advanced graph/source editing and exports are Pro.
- Pro: Invention Lab, advanced Studio/validation, online source proposals, image
  generation (default 10 attempts/day), research and version restore. These use the
  centralized `tools.invention`, `tools.images`, existing tool and export feature checks.
- Every UUID design, version, job, conversation, attachment and image is owner-filtered.
  Pro and admin accounts cannot guess another user's private UUID to bypass ownership.
- Provider/component configuration: admin only, CSRF checked. Key entry is write-only,
  encrypted; public config/health/audit never return keys.
- Expiry: new premium work and premium library retrieval/export stop; previously saved
  own design/image state is retained. Pro never becomes admin.
