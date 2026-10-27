# Connected workstation — setup and use


## Build 10 — engineering wallpaper and tool guidance

The frontend includes a locally hosted `web/engineering-wallpaper.svg` (no remote image
service or external CDN required) with a dark arc-reactor/circuit aesthetic. A restrained
CSS aura animation is disabled for users who request reduced motion. The wallpaper is a
background layer; foreground cards retain opaque/blurred surfaces for readability.

The top-bar **Help & guides** action opens instructions for the current route. Guides cover
getting started, AI Assistant, Circuit Studio, Invention Lab, Code Engineer, Image Studio,
Research Lab, Learning basics and AI connection setup. The dashboard also includes a linked
five-step workflow. Generated code/circuits still require review and physical validation;
visual design does not imply hardware verification.

## 1. Run the existing app (no new runtime dependencies)

```bash
cd /home/user/nexus-iot
python3 run.py
```

For a downloaded source folder, `cd` to that folder instead. Python 3.10+ is required.
The app binds **0.0.0.0:8000**; use the port-8000 live preview or
`http://localhost:8000` on your machine. Keep `data/nexus.db` and `data/.app_secret`
(or the same `NEXUS_SECRET`) together. Existing users, settings, subscriptions,
workspaces, tool runs and library edits are preserved by additive migration 1.

If installing without existing data, run the protected first-admin CLI:

```bash
python3 scripts/bootstrap_admin.py your-admin@example.com
```

It prompts for a strong password; no production password is embedded in the app.
Reload the app to load the current frontend assets (`app.js?v=10`, `app.css?v=10`, plus versioned workstation modules). The latest UI refresh includes the local engineering wallpaper and contextual Help & guides.

## 2. Enable real general-purpose AI

### Option A: admin UI (recommended)

Choose **Google Gemini** with your Google AI Studio key (no OpenAI balance is involved),
or configure OpenAI/Ollama. Use **AI & API Keys → Save & Connect** for the simple secure flow (see `API_KEYS.md`).
For advanced independent settings, expand the advanced provider section and select `openai_compatible` under **Chat model**,
enter the provider's actual base URL, model/deployment ID and real API key, enable it,
then save. The key field is write-only; blank preserves the previous key.

Click **Test chat connection**. This makes a genuine small provider request and may
incur a small charge. The report distinguishes configured, reachable, disabled,
authentication failure, model failure, quota/rate limit, timeout and outage. Configuration
alone is not proof of reachability. Model failures remain errors; no offline conversation
is substituted. Free users also call the configured model, within their limits.

### Option B: secure local CLI

```bash
python3 scripts/configure_ai.py --kind chat --provider openai_compatible \
  --model YOUR_ACTUAL_MODEL --base-url https://api.openai.com/v1
```

Enter the key at the hidden prompt, not as a shell argument or in chat. This updates
the same encrypted settings that the admin UI uses. No restart is needed for DB settings.

### Option C: environment (when no saved admin override exists)

```bash
export NEXUS_AI_PROVIDER=openai_compatible
export OPENAI_API_KEY='YOUR_REAL_SERVER_SIDE_KEY'
export OPENAI_BASE_URL=https://api.openai.com/v1
export NEXUS_AI_MODEL='YOUR_ACTUAL_MODEL'
python3 run.py
```

`.env.example` is a template, **not automatically loaded**. Export variables through your
shell/service manager or intentionally source your own trusted `.env` file. Persisted
admin settings take precedence over defaults; choose the adapter/model in the admin UI
if you previously saved an explicit disabled/none configuration.

### Ollama alternative

Install/start a real Ollama server and pull an actual model first, then:

```bash
python3 scripts/configure_ai.py --kind chat --provider ollama \
  --model llama3.2 --base-url http://127.0.0.1:11434
```

This is a real model-server call, not an emulated offline chatbot. Ollama's URL is a
**backend** URL; browser code still uses relative `/api/...` paths.

## 3. Configure image generation independently

Chat support does **not** imply image support. Select the image adapter/model/key in
**Admin → AI Providers → Image generation**, or use:

```bash
python3 scripts/configure_ai.py --kind image --provider openai_compatible \
  --model gpt-image-1 --base-url https://api.openai.com/v1
```

Environment alternative:

```bash
export NEXUS_IMAGE_PROVIDER=openai_compatible
export NEXUS_IMAGE_API_KEY='YOUR_REAL_IMAGE_KEY'
export NEXUS_IMAGE_BASE_URL=https://api.openai.com/v1
export NEXUS_IMAGE_MODEL=gpt-image-1
```

When the image provider is explicitly selected, the image key can fall back to
`OPENAI_API_KEY`; **it is not enabled just because chat has a key**. Dimensions and model
names must actually be supported by your endpoint. GPT image uses model-native base64;
DALL·E-style endpoints use `response_format=b64_json` or a protected public HTTPS result.
No stock/placeholder images are substituted. Redirects/private result URLs are rejected.

Use **Image Studio** to choose subject/prompt, style, aspect/size and project. Actual bytes
appear in the conversation and project-filtered image history. Regeneration/variation
is a **new prompt-based generation**, not pixel editing. Image edits and vision are not
implemented in these adapters. Concept art is never a wiring instruction or buildability
proof. Default Pro image allowance: 10 attempts/day; Free has no image-generation access.
Admin can set `images_per_day` in plan limits. Reservation occurs before a real provider
attempt; failed external attempts may still use quota/charge upstream. Missing configuration
does not reserve generation usage.

## 4. Real research

Configure `tavily` with a key, or your own `searxng` instance. In the admin provider panel,
search is separate from chat/images. Without it the tool explicitly says **curated-only**
and only returns matching real documentation links. It does not claim a live search,
full patent search or global novelty. Search results/runs can be reopened and associated
with a private project. Uploaded text/code is separate untrusted reference data; PDF
extraction and image understanding are not implemented.

## 5. End-to-end engineering workflow

1. **My Projects → Create design:** choose ESP32/ESP32-S3 and supported high-level
   components. This is an explicit manual function, not pretend AI. Support/protection
   components are included in the graph. Free basic creation allows two high-level
   components within the configured cumulative project limit.
2. **Circuit Studio:** drag components; click a source terminal dot then a destination
   dot to connect; select wires in the canvas/table to edit/delete exact endpoints.
   Use component search/add/remove, properties, wheel zoom, Shift/background pan, Fit,
   undo/redo, graph validation and Save. JSON import accepts `nexus.circuit/1` or
   `nexus.project/1`; import is unsaved until confirmed/saved. Exports use the saved revision.
3. **Save/switch/reload:** the route contains the stable private project UUID. Every
   switch fetches that project's own graph; no global circuit is reused. Optimistic
   revision conflicts return 409 instead of overwriting another tab's changes.
4. **Code Engineer:** inspect/edit source, dependencies and upload instructions. A managed
   `// <NEXUS:PINS>` region derives only from the saved graph. Pin edits update this region
   without replacing unrelated source. Component changes flag driver work. Preview a
   driver rebuild diff and explicitly accept it; never silently replace custom source.
   I2C driver initialization uses graph-derived SDA/SCL constants as well.
5. **Online Code Engineer:** request a project-specific algorithm/source change with the
   actual model. A saved proposal includes full source, diff, dependencies and remaining
   manual work. A changed canonical pin region is rejected. Review and explicitly apply;
   this is not a successful compilation or hardware test.
6. **Run static checks:** record rule findings, managed-pin/source checks and basic source
   structure. The server does not execute untrusted source. No Arduino toolchain or circuit
   simulator is installed; compilation, simulation and physical testing say **not run**.
7. **Build guide / reports:** requirements, graph-derived BOM/wiring, assembly, dependencies,
   code, configuration, testing plan, troubleshooting, limitations, references and versions
   are saved. Restore creates a new revision. Prices/current assumptions are not live quotes.
8. **AI Assistant:** normal questions stay conversational. Select a saved UUID project to
   include only its requirements, circuit, source, references, tests and debugging notes.
   Use explicit tools when useful; unambiguous image/search/validation commands route to
   actual services. Unsupported capabilities return honest errors. Contexts never merge
   merely because two projects have similar names. Conversation URLs/history persist.
9. **AI Invention Lab:** describe an unfamiliar idea, constraints and optionally research.
   A real model proposes a structured architecture and supported IDs, not a library lookup.
   Supported portions become a new saved graph/driver baseline/guide. Unsupported components
   remain named blockers; specialized algorithms need Code Engineer/manual review. Iterations
   are reviewable proposals; application preserves user source and flags driver changes.
10. **Image Studio:** generate a concept against project requirements, then refer to it from
    the saved project/conversation. Do not copy electrical wiring from the artistic rendering.

### Component library scope and custom definitions

Interactive Studio starts with 2 supported ESP32 variants + 15 component/support definitions.
The preserved legacy library has 7 board profiles/73 parts, but not every legacy part has an
interactive exact-pin definition or executable driver yet. Unsupported library forks return
a clear limitation without creating an unrelated substitute design.

An administrator can POST `model: "custom:<slug>"` and a reviewed, inert metadata
`definition` to `/api/admin/components` through an authenticated/CSRF-protected API client.
Required: `name`, unique documented `pins` (`id`, `type`, `voltage`, `required`), `reference`
(real HTTPS source), `reviewed: true`, voltage/current assumptions, compatibility and notes.
This enables manual graph placement/rules, **not** an invented/executable driver. Confirm
the exact package/module revision with the source; metadata is not bench verification.

## 6. Tests and real integration acceptance

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
node --check web/workstation.js
node --check web/studio.js
```

Optional real Chromium UI acceptance (disposable DB, explicit local provider fixtures):

```bash
python3 -m pip install playwright
python3 -m playwright install --with-deps chromium
python3 tests/browser_acceptance.py
```

Fixture tests prove payload/stream parsing, honest failures, image-byte display and storage,
UI controls, persistence and isolation. **They do not prove a real model is connected or
that a real image has been generated.** Separate opt-in, potentially billable acceptance:

```bash
python3 scripts/verify_integrations.py --run-live --images
# optional unit live smoke checks once env credentials exist:
NEXUS_RUN_LIVE_TESTS=1 python3 -m unittest discover -s tests -v
```

The script asks six distinct questions, saves actual responses for manual relevance review,
checks history and requests actual image bytes with a project/conversation association.
No credentials in this environment means **BLOCKED**, not passed. It uses a disposable DB,
not the production history. Current evidence is in `docs/qa/browser-results.json`,
`tests/last-run.txt`, and `docs/LIVE_INTEGRATION_STATUS.json`.

## 7. Production caveats

Use a TLS reverse proxy, create a unique administrator, protect/back up DB + app secret, restrict
embedding origins, disable preview query-session fallback (`NEXUS_ALLOW_QUERY_SESSION=0`)
and apply infrastructure-level rate/body limits. This stdlib app is single-process with
bounded persisted jobs, not a distributed queue. Cancellation is best-effort; an external
request already in flight can still incur charges. See `LIMITATIONS.md` before field use.
