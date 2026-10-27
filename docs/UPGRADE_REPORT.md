# NEXUS IoT — engineering workstation upgrade report

**25 October 2026 · build 9 repair · existing repository upgraded in place**

## Overall result

A connected, runnable workstation has been implemented inside the existing
`/home/user/nexus-iot` application. The Python/SQLite/vanilla-JavaScript stack and
existing user data/library/workflows were retained. This is **not a declaration
that live integrations or physical hardware have passed acceptance**: no real AI,
image or search credentials are configured in this environment.

The app is running on **0.0.0.0:8000**. Reopen/reload the port-8000 preview for build 9.


## Build 10 UI follow-up — engineering wallpaper and contextual guidance

The existing frontend now has a same-origin SVG engineering wallpaper, subtle animated aura
with `prefers-reduced-motion` support, improved hero treatment, and a responsive five-step
workflow on the dashboard. A top-bar **Help & guides** modal changes its instructions and
recommended next links based on the current route. It includes safety/reliability boundaries
for AI, circuits, generated images, and research. Asset loading and guide presence are covered
by the frontend regression test. Real Chromium browser validation could not be rerun in this
execution environment because the Playwright Chromium executable is not installed.

## 1. Offline/repetitive assistant root cause

The actual old request path was:

`dashboard Ask → POST /api/assistant → tools.run_tool → general_assistant`

- Persisted provider was `offline`; encrypted API key was empty; no provider key was
  present in the server environment. No genuine model call was possible.
- Live calls were additionally gated on `ent.is_pro`, blocking Free from online AI.
- The default answer was a repeated component/reference checklist, regardless of topic.
- Provider exceptions became successful-looking `offline_fallback` output.
- There were no persisted conversations/history or selected-project context assembly.

These are repaired in backend services, not just renamed in the UI. Free and Pro can
call the configured model subject to limits. Missing/failed providers now produce typed,
honest errors. Explicit deterministic catalog/rule functions remain available separately.
See [UPGRADE_AUDIT.md](UPGRADE_AUDIT.md).

## 2. What was implemented

| Area | Working implementation | Boundary / qualification |
|---|---|---|
| Online AI service | OpenAI-compatible + real Ollama adapters; server-held write-only encrypted keys; independent models/capabilities; health probe; bounded requests; HTTP error types | **No real credentials currently configured.** “Configured” is not “reachable.” |
| Assistant | General-purpose model messages, persistent conversation UUIDs, bounded chronological history, selected-project context, text/code attachments, real upstream streaming relayed as SSE, polling resume, retry/cancel | No generic chat fallback. PDF/vision ingestion and native autonomous model function-calls are not implemented. |
| Orchestration | Conversational by default; explicit UI actions and unambiguous image/search/validation commands call real services | Conservative command routing, not an unrestricted autonomous agent. Important unsupported stages are reported. |
| Private projects | Versioned `nexus.project/1`, stable UUID/owner, isolated requirements/circuit/source/research/tests/debugging, optimistic saves, immutable versions, restore | Owner access persists after subscription expiry; new Pro work/exports still require entitlement. |
| Circuit Studio | Exact-pin SVG editor; component add/remove/drag/inspect; terminal/wire editing; zoom/pan/Fit; wiring table; save; undo/redo; JSON import; SVG/CSV/JSON/source exports | Connection-level design, not PCB CAD or a simulator. Initially 2 board variants + 15 component/support definitions. |
| Canonical circuit | `nexus.circuit/1` graph is the source for nets, wiring, diagram, rules, managed source constants and supported driver initialization | Unsupported parts are rejected or remain explicit blockers; no invented pinouts. Reviewed custom definitions are inert and immutable/versioned. |
| Validation | Missing pins, exact endpoint validity, rails/logic, ADC/input-only pins, GPIO conflicts, grounds, I2C conflicts/pull-ups, MQ-2 divider, pump driver/flyback, gate pulldown and assumed power capacity | Rule results are not electrical safety certification, simulation or physical proof. Unknown ratings still need bench confirmation. |
| Circuit ↔ code | Managed pin region; pin edits preserve unrelated user source; component topology changes flag driver work; rebuild diff/explicit apply; graph-derived I2C SDA/SCL initialization | No arbitrary source execution. User-removed pin markers cause mismatch, not forced source replacement. |
| Online Code Engineer | Project-specific source/algorithm proposals from the real configured model, full-source/diff/dependencies/manual-work output, preserved proposal history and explicit apply | Requires a model. Canonical-pin edits by the model are rejected; generated code remains uncompiled/unverified. |
| Invention Lab | Model-generated structured requirements/architecture/components beyond the stored library, optional real research, constrained graph/driver baseline/guide, persistent projects, reviewable iterations and history | Unknown components/specialized processing remain named manual work, not fake implementation. No global novelty claim. |
| Image Studio | Real independent image endpoint adapter, actual image-byte validation/storage, conversation/project association, authenticated display/download/history, prompt-based regenerate/variation, Pro limits | **No image provider configured.** No placeholder substitution, pixel editing, or claim that concept art is a circuit. |
| Research | Configurable Tavily/SearXNG, retrieved evidence or explicitly curated links, saved search runs/project references | Live search not configured. No invented citations or complete patent/novelty guarantee. |
| Pro workspace | Fourteen connected workflow entry points; original ten deterministic tools retained with persisted runs | Online tools require credentials; a page loading is not counted as a real-model acceptance pass. |
| UI | Restrained dark workstation, optional saved light theme, responsive Studio/assistant/code layouts, loading/error/verification states | No external CDN/fonts/assets. Protected exports/images use authenticated fetch, including preview fallback. |

### Required distinct-circuit case

- **A — irrigation:** 8 component instances, 14 exact-pin connections; soil ADC +
  MOSFET gate driver, gate resistor/pulldown, pump, flyback diode, supply and board.
- **B — gas alert prototype:** 6 instances, 11 connections; MQ-2 heater supply and
  analog divider + active buzzer module, supply and board.
- Their component sets, connections, wiring tables and firmware differ.
- Repeated switching and full reloads restore the correct saved project in Chromium.
- Pin changes synchronize the dependent source region and preserve custom source edits.
- These are **educational low-voltage prototypes, not physically tested systems**.
  The gas prototype is not a certified detector; no flammable-gas test is instructed.

## 3. Project library and existing functionality

**117 distinct published records · 25 categories · exactly 15 designated Free projects.**
The existing structured library compiler, board/part corpus and protected detail/diagram/
source/export routes remain. Regression checks cover required content sections, static
pin/code consistency and all seeded validation results. This establishes structural/static
checks, **not** compilation/physical verification of 117 builds. Raspberry Pi examples
remain explicitly documented driver scaffolds. Existing learning modules, telemetry,
workspaces, audited admin project/user/subscription management and Stripe signature
verification were preserved. Unsupported library-to-Studio forks fail explicitly instead
of silently substituting another circuit.

## 4. Authorization and data preservation

- DB-derived Free/Pro/Admin entitlements on protected routes/queries; Pro is not admin.
- Free sees only the designated 15; guessed premium URLs remain blocked server-side.
- Private projects/conversations/jobs/attachments/images are owner-filtered, including
  downloads and versions. Admin does not implicitly read another user's private design.
- New Pro features reuse centralized feature checks and atomic quota reservations.
- Subscription expiry blocks new premium work/library retrieval, preserves own saved data.
- Providers/custom definitions are admin-only with CSRF; keys are never returned/logged.
- Protected files use `no-store`; preview cookies/bearer/query fallback applies to every
  resource, including SSE, SVG, wiring exports and images.
- Existing SQLite was backed up before migration; no user history was globally cleared.
  Migration is additive and startup seeding preserves existing records/edits.
- Stripe is still unconfigured; no payment or premium activation is simulated.

## 5. Tests actually executed

### Original build-6 regression baseline — **53 total: 51 passed, 2 skipped/blocked**

`python3 -m unittest discover -s tests -v`

The two skipped tests require a real chat/image provider and explicit live-test opt-in.
They are **not counted as passed**. Tests include the original authorization/library/
billing/tool regressions plus real HTTP adapter parsing with an explicitly local test
double; missing keys; 401/model/quota/outage errors; streaming/history; context isolation;
A/B persistence; pin sync/custom-source preservation; I2C remapping; revision conflicts;
versions; rule failures; novel structured proposals; image-byte storage/association/
limits; file restrictions; secret masking; private ownership; expiry; concurrent quotas;
and explicit no-compiler/no-simulator status.

### Chromium browser acceptance — **21 checks passed**

`python3 tests/browser_acceptance.py`

Isolated temporary DB, real browser and explicitly local API fixtures. Checks include:
login, UI design creation, drag/save, component add/undo/redo, exact wire edits, validation,
source editing/sync, A/B switch/reload, missing-model errors, HTTP/SSE display, protected
image display/history, source-diff approval, novel-proposal persistence/history, conversation
URL/history/reload, all 14 Pro entries, provider panels, library, mobile viewport, and the
cookie-less/bearer-stripped preview fallback for project/wiring/SVG. No uncaught browser
runtime errors in the final run. A mobile overflow found during testing was repaired.

**Local fixtures prove transport/storage/UI behavior, not genuine model relevance or
actual external image generation. No fixture configuration/data was installed in the
user's live database.** Evidence: [qa/browser-results.json](qa/browser-results.json),
`tests/last-run.txt`; screenshots under `docs/qa/` are labelled QA evidence.

### Syntax / live checks

- Final running-server HTTP smoke checks: **24 passed**, including build-6 modules, login/logout, query-session protected endpoints, all six library exports/SVG, `no-store` and unauthenticated export rejection. Evidence: `docs/qa/live-server-smoke.json`.
- Python compile checks for backend/provider/service modules: passed.
- `node --check` for all three JavaScript modules: passed.
- `scripts/verify_integrations.py --run-live --images`: **BLOCKED — missing credentials**;
  see [LIVE_INTEGRATION_STATUS.json](LIVE_INTEGRATION_STATUS.json).
- Real Arduino compilation: **not run — toolchain absent**.
- Electrical simulation: **not run — simulator absent**.
- Physical hardware acceptance: **not run — hardware absent**.

## 6. Remaining acceptance gaps and required configuration

**Priority before claiming online completion:** securely configure chat and image providers,
then run the real six-question/history/image acceptance script and manually review the
actual answers for relevance and quality. Provider adapter/UI success with a fixture is
not a substitute for that test. Configure web search separately if live retrieval is needed.

Broader component coverage, specialized firmware algorithms, physical packaging/power
measurements, real compiler/simulator integration, native model tool-calling, vision/PDF,
pixel-image editing and distributed job execution remain future engineering work. Existing
limitations are visible rather than simulated. See [LIMITATIONS.md](LIMITATIONS.md).

## 7. Exact launch/configuration instructions

```bash
cd /home/user/nexus-iot
python3 run.py
# Open the port-8000 live preview (or localhost:8000 on your own machine).
```

Then **Admin → AI Providers**: configure Chat and Image separately; keys are write-only.
Do not paste real secrets into this conversation. Secure CLI alternative:

```bash
python3 scripts/configure_ai.py --kind chat --provider openai_compatible \
  --model YOUR_ACTUAL_MODEL --base-url https://api.openai.com/v1
python3 scripts/configure_ai.py --kind image --provider openai_compatible \
  --model gpt-image-1 --base-url https://api.openai.com/v1
# Each prompts securely for its key. Verify actual provider support/model names.
python3 scripts/verify_integrations.py --run-live --images
```

For first installation without existing data: `python3 scripts/bootstrap_admin.py <email>`.
See [WORKSTATION.md](WORKSTATION.md) for Ollama, environment configuration, usage limits,
component definitions, workflow instructions, tests and safe deployment guidance.

## 8. Resume map

- `nexus/providers/`: provider contracts/adapters/config.
- `nexus/services/`: chat/jobs/circuits/designs/invention/code_ai/images/research.
- `nexus/workstation_api.py`: additive authenticated routes.
- `nexus/migrations.py`: additive schema migration 1.
- `web/workstation.js`, `web/studio.js`: connected new screens/editor.
- Existing `api.py`, `tools.py`, library/compiler/auth/billing/telemetry remain integrated.
- No rebuild is needed to continue: configure providers, run live acceptance, then expand
  component/driver coverage and actual verification facilities in the saved codebase.


### Source delivery

`/home/user/NEXUS-IoT-Workstation.zip` contains application source, documentation and
tests, **not** the user database, backup, session data or app secret. The live workspace
keeps existing user data. A fresh ZIP installation must bootstrap its own administrator
and configure its own credentials; library seeding is automatic on startup.


## Build 7 follow-up — direct API-key setup

The main navigation now includes **AI & API Keys**, with dashboard/top-bar shortcuts
and a one-step **Save & Connect** form. It verifies the actual configured streaming
or non-streaming model path before activating encrypted credentials. It requires no
server restart, protects existing settings on failure, and offers explicit optional
image-provider setup. Non-admin users retain read-only connection status.

Validation: **62 automated tests: 60 passed, 2 real-provider tests skipped**;
**25 Chromium checks passed**, including new key entry, activation, cleared key fields,
rejected-key preservation and downstream chat. Tests used an explicit local provider;
no test key or fake provider was configured in the live app. External AI still requires
the user's actual provider key. See `API_KEYS.md`.


## Build 8 follow-up — Google Gemini

Added a distinct **Google Gemini** option, direct Google AI Studio key link, default
Google endpoint/model and server-side Gemini HTTP/SSE profile. No OpenAI API balance
is involved. Google key/model access and available quota are still required; selected
models have a limited free tier, not unlimited access. Gemini chat does not claim image
generation or live Google Search capabilities. Existing image settings are untouched.

Security: vendor/endpoint changes cannot silently reuse old keys; switching presets
clears typed key material. Failed test-before-save preserves previous settings.
Exhausted API balances are now distinct non-retryable `quota_exhausted` errors rather
than misleading transient rate-limit retries or streaming advice.

Validation: **71 automated tests: 69 passed, 2 real-provider tests skipped** and
**30 Chromium checks passed**. Nine new tests cover Gemini transport, health, key
isolation, defaults, encryption, environment separation and quota handling. Five new
browser checks cover Gemini setup, key safety, activation/reload, Assistant and mobile.
These use explicit local fixtures; no genuine Gemini answer is claimed without a key.
The running build-8 smoke test confirmed deployment and preserved live settings.


## Build 9 repair — unreadable responses, slow model and actual Gemini proof

The saved Google key was accepted for model listing. The selected 3.8 Flash model
repeatedly timed out; native **3.5 Flash-Lite** returned real non-streaming/streaming
replies promptly. Gemini now uses the native Google API with x-goog-api-key headers,
and legacy endpoint URLs/key reuse are preserved safely. No OpenAI credits are used.

Connection checks now return HTTP 202 in milliseconds and run as persisted background
jobs, with polling/resume/cancel. Secrets exist only in worker RAM until encrypted
activation; no raw credentials are included in jobs/events. Admin/CSRF, owned job
visibility, duplicate/capacity bounds, atomic quotas, late cancellation, revoked admin
and newer-configuration preservation remain enforced. Saved-provider health also
runs in the background. The JSON decoder never treats malformed HTTP 200 as success
or echoes raw HTML, and unknown transport outcomes no longer falsely assert rollback.

**Actual live verification:** the background route acknowledged in 0.005 seconds,
received a real Google response and activated the existing key in about 1 second.
The existing Assistant then displayed a relevant, real C-recursion reply in 1.88
seconds. Only the new QA conversation/session was removed; user records and the
server-held credential were preserved. Reports: `qa/gemini-live-activation.json`,
`qa/gemini-live-assistant.json`. A cropped screenshot contains only that QA question
and answer, no user history or key. The private pre-fix DB backup is excluded from source.

Regression: **78 Python tests: 76 passed, 2 opt-in live tests skipped**; **32 Chromium
checks**; **10 JSON/protocol checks**. Explicit HTML 504 and HTML 200 reproduction,
background reload, native SSE, cancellation, stale writes and secret isolation passed.
Other topics, image generation, search, billing and hardware were not newly certified.

## Follow-up Circuit Studio enhancement (2026-10-25)

- Added `POST /api/circuits/guidance`, a read-only authenticated endpoint for graph-derived assembly guidance.
- Added Circuit Studio's **Build guide** action with ordered exact-terminal connections, required unconnected-terminal list, blocking rule errors, warnings, component documentation, and a grouped bill of materials with quantities.
- Made this read-only guide available to authenticated users on all tiers; existing edit/validation/export entitlement checks remain unchanged.
- Added regression tests for the guide's graph fidelity, BOM quantity accounting, safety-first step and authentication.
- See `docs/CIRCUIT_BUILD_GUIDE.md` for behavior and limitations.

## Engineering pack upgrade (2026-10-25)

- Added authenticated `GET /api/designs/{id}/engineering-pack`, scoped to the owning user. It combines the saved project requirements/architecture, exact graph-derived pin-to-pin wiring, bill of materials, step-by-step assembly guidance, component references, static validation findings, firmware, and research references into one JSON package.
- Added a **Download engineering pack** action to the project overview. The exported artifact includes an explicit verification status that compilation, simulation, and physical hardware testing have not been performed by the export operation.
- Updated the frontend-serving regression assertion to match the current `v=11` asset cache version.
- Verification: Python test suite 80 passed / 2 skipped; frontend response checks 10 passed; Python compilation and JavaScript syntax checks passed. Browser acceptance remains blocked when Playwright Chromium is unavailable.


## Maintenance update — Image/Research Studio removal and circuit catalog expansion

- Removed Image Studio and Research & Innovation from primary navigation; removed image generation and web-search actions from the AI assistant action selector and automatic routing. The conversational assistant remains available for engineering questions.
- Added reviewed terminal definitions for HC-SR04, HC-SR501 PIR, single-channel relay modules, SG90 servo, SSD1306 OLED, MPU-6050, DS3231, BH1750, analog sound and rain sensors, push button, potentiometer, breadboard, jumper wires, decoupling capacitors, and a protected-cell reminder entry.
- Each catalog entry documents model/revision uncertainties and electrical precautions. Catalog availability does not imply a generated driver exists or that the circuit has been physically verified.
