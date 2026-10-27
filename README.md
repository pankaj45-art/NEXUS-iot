# NEXUS IoT — connected engineering workstation

**Existing application upgraded in place.** Python/SQLite + vanilla ES modules, no
mandatory runtime dependencies. Includes a general-purpose online-provider chat
pipeline, persistent conversations, interactive exact-pin Circuit Studio, versioned
private projects, code editing/diff review, Invention Lab, protected real image-provider
integration, research, telemetry and the preserved **117-project library (15 Free)**.

> **Live workspace status (build 9):** Google Gemini 3.5 Flash-Lite was connected
> and a genuine streamed reply was verified through AI Assistant. Images and live
> web search are not verified/configured by this repair. The downloadable source
> excludes all private credentials and still needs its own provider setup.
>
> **Build 10 UI refresh:** added a local, animated-aura engineering wallpaper, contextual
> Help & guides on every signed-in workspace, and a dashboard workflow that teaches users
> how to move from idea → circuit → firmware → test. This is a frontend update; it does not
> imply that external image/search credentials or physical hardware have been verified.
>
> **Upgrade results and exact limits:** [docs/UPGRADE_REPORT.md](docs/UPGRADE_REPORT.md).
> **New setup/workflows:** [docs/WORKSTATION.md](docs/WORKSTATION.md).
> **Audit/root causes:** [docs/UPGRADE_AUDIT.md](docs/UPGRADE_AUDIT.md).

---

## Connect online AI — new API key section

Open **AI & API Keys** in the main navigation, choose **Google Gemini** or your provider,
paste your own API key, check the model,
and click **Save & Connect**. This tests the real model connection before saving and
activates it immediately; no environment editing or restart. A failed test preserves
previous settings. Images and live search are optional, separate services.
[Exact setup instructions](docs/API_KEYS.md). Current app build: **9**.

## 1. Quick start (2 minutes)

Requirements: **Python 3.10+** (tested on 3.13). No mandatory `pip install` — the server is
built entirely on the Python standard library.

```bash
cd nexus-iot
python3 -m unittest discover -s tests -v     # 78 tests: 76 passed, 2 opt-in live tests skipped
python3 scripts/bootstrap_admin.py admin@example.com   # interactive password prompt
python3 run.py
```

Open **http://localhost:8000**. The server binds `0.0.0.0:8000` by default, so the Arena
live preview works without configuration. On first boot it creates:

- `data/nexus.db` — SQLite database (WAL, foreign keys)
- `data/.app_secret` — random app secret for cookie signing and encryption at rest
- the settings rows and the entire 117-project library (idempotent; existing admin edits
  are never overwritten on restart)

Register a free account in the UI, or sign in with the administrator you bootstrapped.
The bootstrap CLI is the **only** way to create the first admin: there is no HTTP endpoint
that can create or promote an administrator, and no hardcoded production password.

**Fresh ZIP note:** no populated database or pre-created administrator is included in the source archive. Create your own administrator with `python3 scripts/bootstrap_admin.py admin@example.com`, or register a normal user in the UI. The bootstrap CLI is the only supported first-admin path. Do not delete a populated database. Back up `data/nexus.db` together with `.app_secret`; changing the encryption secret without migration can make saved provider keys unreadable.

**If you are using the embedded live preview:** embedded frames can
block cookies and strip the `Authorization` header, so the app ships three session
transports (signed cookie → bearer header → query token, the last used only after a `401`),
all resolving to the same server-side hashed session with identical CSRF, expiry and
revocation. The login response also carries the full session + config, so no follow-up
request is needed to open the workspace. Static assets are versioned and `no-store`.

| Symptom in the preview | What to do |
|---|---|
| Sign-in loops back to the form | Close and reopen the **port-8000 live preview** (not an `index.html` file preview). The tiny line at the bottom of the sign-in card must read `NEXUS · ready`; if it doesn't, you are running a cached page. |
| Red **"Authentication required."** after sign-in | The workspace opened but your proxy stripped the session. The SPA now retries automatically with the query fallback and shows a **Preview session** badge in the top bar. Reload once to pick up `app.js?v=10`. |
| Blank / endless "Loading…" | Use **Open NEXUS in a new tab** at the bottom of the sign-in card; top-level tabs have no iframe cookie restrictions. |

See `docs/ARCHITECTURE.md` → *Session transport* and `docs/SETUP.md` → *Troubleshooting*.
Set `NEXUS_ALLOW_QUERY_SESSION=0` in production to disable the fallback.

For a non-interactive bootstrap (CI/containers):

```bash
NEXUS_ADMIN_EMAIL=admin@example.com NEXUS_ADMIN_PASSWORD='<strong-password>' \
  python3 scripts/bootstrap_admin.py admin@example.com
```

---

## 2. What is actually implemented

### Three access levels

| Tier | Library | Tools | Workspace | Admin |
|---|---|---|---|---|
| **Free** | Exactly the 15 designated beginner projects (full descriptions, objectives, BOM, wiring, code, tests) + 6 learning modules | Limited general AI assistant | Up to 5 saved workspaces, 3 created projects, 8 AI requests/day, own server-side preferences | ❌ |
| **Pro** | All 117 published projects + code/BOM/wiring/markdown/JSON/SVG exports | 14 connected workflows + retained deterministic tools | Unlimited workspaces, versions, decisions, tests, reports | ❌ |
| **Admin** | All records incl. drafts/archived | All tools | All tools | Full protected workspace |

Free users also get six curated **Learning basics** modules (bench safety, multimeter checks,
buses, ADC/calibration, MQTT/HTTP telemetry and a repeatable debugging method), real
per-user saved **preferences**, and a usage/limits page.

The entitlement is derived **on every request** from `users.role` + the latest
`subscriptions` row (`nexus/entitlements.py`). Browser-supplied `role`, `plan` or `status`
fields are ignored and logged as a privilege-escalation attempt. Every Pro tool checks
`require_feature()`; every project query uses `library_predicate()` in SQL; every download,
image, export and detail request calls `project_visible_to()`. A locked project returns a
generic `403` with **no title, summary, BOM, diagram or code** — not even through a guessed
URL, search query, devtools or direct API call.

See **[docs/PERMISSIONS.md](docs/PERMISSIONS.md)** for the full permission matrix and the
entitlement lifecycle.

### IoT Project Library — 117 records

25 categories, beginner/intermediate/advanced mix, no duplicated templates. Each published
project is compiled from a project-specific spec into a structured record with sections A–J:

**Overview** (unique slug, category, difficulty, problem, objectives, use cases, expected
outcome, build time + assumptions, prerequisites, skills, status/visibility) ·
**BOM** (name, qty, purpose, specs, alternatives, price band + currency + assumptions,
voltage/current, compatibility notes, mandatory vs optional) ·
**Architecture** (project-specific SVG block diagram, subsystems, data flow, comms, power,
cloud/mobile, storage/processing) · **Circuit** (board-specific pin map, wiring table,
pull-ups/downs, level shifting, drivers, interfaces, voltage compatibility checks, current
budget, reasons, uncertain items + verification steps) · **Procedure** (18 steps, 19 for
advanced, including security/reliability/maintenance) · **Code** (Arduino C++ or Python 3,
libraries + versions, placeholders, pin defines consistent with the wiring table, sensing,
processing, comms, error handling, reconnection, comments, upload/run instructions,
expected logs, static tests) · **Troubleshooting** · **Testing** (simulated/static/physical
explicitly distinguished) · **Deliverables** · **Quality status**.

Every project passes the rule-based circuit validator (no ERROR issues). Firmware is marked
**“Statically reviewed – NOT hardware-tested.”** No project claims to have been physically
tested; `quality.physical_test_confirmed` is `false` everywhere. Prices are labelled
indicative bands, not live quotes. Credentials are always `YOUR_WIFI_SSID`,
`YOUR_WIFI_PASSWORD`, `YOUR_MQTT_USER`, `YOUR_API_TOKEN`, etc.

The 15 free beginner projects are curated in `nexus/data/specs_free.py`: ESP32 LED control,
DHT22 temperature/humidity, automatic night lamp, soil moisture monitoring, smart plant
watering, ultrasonic distance, motion detection alert, room temperature dashboard, basic
air-quality indicator, water-tank level monitoring, door-open alert, Wi-Fi LED, low-voltage
energy measurement demo, rain alert, and a simple IoT sensor dashboard. Mains/gas/healthcare
topics use safe low-voltage educational alternatives with explicit limitations.

**Admin can replace and reorder the free 15 at runtime** (Admin → The Free 15, or
`PUT /api/admin/free-projects`) — no code change needed.

### Retained ten deterministic engineering tools (compatibility workflows)

| # | Tool | What it really does |
|---|---|---|
| 1 | AI IoT Project Generator | Builds a full project from a problem/parts/budget/skill request using the compiler (BOM, wiring, firmware, tests); supports partial regeneration of only affected sections using a previous run id. |
| 2 | AI Circuit Designer & Validator | Assigns real board pins, produces a wiring table, runs 8 rule families (collisions, strapping/input-only pins, ADC2+Wi-Fi, logic levels, I2C conflicts, current budget, passives, 5 V hosts), emits matching firmware defines. |
| 3 | AI Code Engineer | generate / explain / review / refactor for ESP32, ESP32-S3, Arduino Uno, ESP8266, Pico W and Raspberry Pi. Static review checks credentials, blocking delays, reconnects, publish results, `String` heap use, `pulseIn` timeouts and sensor error handling. |
| 4 | AI Debugging Center | Pattern-matches compiler errors/logs, tracks prior attempts in `debug_attempts`, and **does not repeat fixes already tried**; runs safe static tests on pasted text (never executes code). |
| 5 | AI Innovation Discovery | Documented limitations + engineering directions, explicitly separated facts/hypotheses, real citations from the curated corpus. |
| 6 | Project Comparison & Gap Analysis | Transparent weighted-sum scoring with visible weights, assumptions and a ranked gap list — not an opaque model. |
| 7 | Startup & Product Idea Lab | Three opportunities with MVP, cost bands, alternatives, validation plans, and an additive 0–100 heuristic score with its full breakdown. **No unsupported success probabilities.** |
| 8 | Advanced Research Assistant | Source discovery from a 28-URL real documentation corpus, summaries, reference tracking and a Markdown report. **No invented citations.** |
| 9 | Device Monitoring & Diagnostics | Real telemetry via `POST /api/ingest/<token>`, HTTP/MQTT integration status, charts, stale/flatline/outlier alerts, and explicitly labelled simulated samples (`source='simulated'`). |
| 10 | Project Management & Documentation | Records milestones, versions, decisions, tests and code snapshots, then generates a professional report **from the actual saved workspace state**. |

Results are persisted (`tool_runs`) and can be re-opened. These legacy calculations
use catalog/rules and are explicitly labelled deterministic. Optional online enrichment
has a separate `provider_error` on failure. It is never a fallback conversational answer.
The new Assistant/Invention/Image/online-Code workflows require actual configured providers;
see [WORKSTATION.md](docs/WORKSTATION.md) for their connected workflows.

### Subscription & billing (honest by design)

- The `subscriptions` table stores user ID, plan, status, start/expiry, provider, provider
  customer/subscription IDs, cancellation and timestamps. Limits are per-tier and
  configurable in Admin → AI & Config.
- The pricing/upgrade page, subscription status page, usage/limits display and billing entry
  point are all live.
- **Stripe is used only when `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and
  `STRIPE_PRICE_ID` are configured.** Checkout creates a real Stripe Checkout Session over
  HTTPS. Access is granted **only** by an HMAC-SHA256-signature-verified webhook
  (`Stripe-Signature`) or a documented admin/CLI action. A browser success redirect grants
  nothing.
- If payments are **not configured**, the app says so clearly and shows setup instructions;
  it never pretends a payment occurred.
- Expired, cancelled or invalid subscriptions lose Pro-only access but keep personal
  workspaces, projects and settings. `past_due` has a documented 3-day grace window.
- Documented entitlement restoration after a confirmed offline payment:
  `python3 scripts/manage.py entitle user@example.com pro --days 30`.

### Administration

Separate protected workspace, server-side `require_admin()` on every privileged operation:
manage all published/unpublished/draft/archived projects (create, edit, duplicate, publish,
unpublish, archive, delete, validate, quality status), categories/difficulty/metadata,
the free-15 designation/order, the category taxonomy and per-project tags,
users/roles/subscriptions, AI providers/models/limits, plans/pricing, integrations,
audit logs, quality/publication gate, usage and per-project view analytics.
Admin UI and logs never expose passwords, API keys or payment credentials: secrets are
write-only, encrypted at rest (`security.encrypt_secret`) and masked when read.

---

## 3. Configuration

Copy `.env.example` to your environment (or export variables). All are optional.

| Variable | Purpose |
|---|---|
| `NEXUS_SECRET` | Stable app secret for cookie signing + at-rest key encryption. Auto-generated if absent. |
| `PORT`, `HOST` | Default `8000`, `0.0.0.0` (live-preview friendly). |
| `NEXUS_DATA_DIR`, `NEXUS_DB_PATH` | Data/DB location. Default `./data`. |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `NEXUS_AI_MODEL` | Real OpenAI-compatible chat. Without credentials, conversational AI reports not configured; named basic functions still run. |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID` | Optional live payments. |
| `NEXUS_MQTT_BROKER`, `NEXUS_MQTT_PORT`, `NEXUS_MQTT_TOPIC`, `NEXUS_MQTT_USER`, `NEXUS_MQTT_PASSWORD` | Optional MQTT bridge settings. |
| `NEXUS_ADMIN_EMAIL`, `NEXUS_ADMIN_PASSWORD` | First-admin bootstrap (prefer the interactive prompt). |

Runtime settings (plan price, trial days, limits, AI provider/model, free-feature policy,
quality gate, integrations) are stored in the `settings` table and editable from the admin
workspace. Environment values always win for secret material.

See **[docs/SETUP.md](docs/SETUP.md)**, **[docs/ADMIN.md](docs/ADMIN.md)**,
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** and
**[docs/LIMITATIONS.md](docs/LIMITATIONS.md)**.

---

## 4. Project layout

```
run.py                     entry point (python3 run.py)
nexus/
  config.py                env-driven config + default settings
  db.py                    SQLite schema + global/user settings + usage/audit helpers
  security.py              PBKDF2, sessions, CSRF, HMAC cookies, secret encryption, redaction
  errors.py                typed API errors
  entitlements.py          CENTRAL permission matrix + visibility + usage limits
  hardware.py              7 board profiles, 73 components, pin assignment, 28 real docs
  validator.py             rule-based circuit validation + wiring table
  codegen.py               Arduino C++ / Python firmware generator
  compiler.py              compact spec -> complete A-J project record
  diagram.py               project-specific SVG block diagram
  export.py                server-side Markdown/CSV/JSON/code/SVG exports
  seed.py                  idempotent library seeding + visibility serialization
  billing.py               Stripe checkout + signature-verified webhook + entitlements
  ai.py                    legacy compatibility + explicit provider status/errors
  tools.py                 10 Pro tools + free general assistant
  api.py                   all HTTP routes and authorization
  server.py                threaded stdlib HTTP server + static SPA
  data/spec_base.py        compact spec DSL + 25 categories
  data/specs_free.py       15 curated free beginner specs
  data/specs_pro_a..d.py   102 distinct Pro specs
web/                       index.html, app.css, app.js, favicon.svg (no external assets)
scripts/bootstrap_admin.py secure first-admin CLI
scripts/manage.py          entitle/revoke/roles/passwords/reseed CLI
tests/test_nexus.py        preserved authorization/library regression tests
tests/test_workstation.py  conversation/provider/circuit/image/security tests
tests/browser_acceptance.py  isolated Chromium acceptance (optional Playwright)
docs/                      setup, permissions, admin, architecture, limitations
```

---

## 5. Tests

```bash
python3 -m unittest discover -s tests -v
# or: pytest -q tests
```

The original regression tests cover: public config, frontend presence, cookie-less preview sessions, free visibility (including direct API,
export, diagram and search leakage), self-promotion attempts, admin isolation, Pro≠admin, private/validated user settings,
learning modules, enforced project-creation limits, admin-managed categories and tags,
project-view analytics,
expiry/cancellation, signed webhook verification + no success-redirect granting, admin
project lifecycle with quality gate, free-15 reorder, secret non-disclosure, **all ten Pro
tools** in offline mode, debugging fix memory, real vs simulated telemetry, library
uniqueness/completeness, all-section/circuit validation across 117 projects, firmware/credential
consistency, exports/diagrams and citation integrity. Tests use an isolated temporary DB.

---

## 6. Safety, honesty and limitations

- **No project is claimed as hardware-tested.** Firmware is statically reviewed; the
  quality status is explicit and `physical_test_confirmed=false`.
- Electrical details are generated from a documented board/component catalog. Where a value
  is uncertain (e.g. ADC scaling, K-factors, board pinouts) it is marked `TODO` with a
  verification step. Always verify with a multimeter and the linked datasheet.
- Mains electricity, hazardous gas, medical and other high-risk topics use low-voltage
  educational alternatives with clear limitation statements. Nothing here is a certified
  safety or medical device.
- Prices are indicative bands, not live quotes. LLM output, when enabled, is a narrative
  layer for legacy deterministic tools. New conversational and source-generation
  services use real provider responses; they never substitute generic fallback output.
- Research/innovation tools only cite URLs from the curated documentation corpus. No
  citations are invented. Startup scores are transparent heuristics, never probabilities.
- Device monitoring clearly labels `real` vs `simulated` samples. MQTT bridging requires
  the optional `paho-mqtt` package; HTTP ingest works without it.

Full details: **[docs/LIMITATIONS.md](docs/LIMITATIONS.md)**.

---

## 7. License / credits

Built with the Python standard library. Documentation references point to official
Espressif, Arduino, Raspberry Pi, NXP, OASIS, Adafruit, Bosch, Sensirion, TI, Semtech,
Mosquitto, Home Assistant, ThingSpeak, OWASP, NIST, WHO, PlatformIO and ArduinoJson
resources. All product names belong to their respective owners.
