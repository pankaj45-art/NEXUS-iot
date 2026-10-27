# NEXUS engineering-workstation upgrade — audit, 25 October 2026

## Existing system (preserved)
Python stdlib threaded HTTP server + SQLite WAL + vanilla JavaScript SPA; 117
published compiled project records (15 free), authentication, subscriptions,
10 persisted engineering tools, workspaces, audit logs, telemetry and Stripe
webhook verification. No framework replacement is needed. A SQLite backup is
at `backups/pre-workstation-upgrade.sqlite`; no user records are removed.

## Reproduced root causes
Trace: dashboard `#ask-btn` → `POST /api/assistant` → `tools.run_tool()` →
`general_assistant()` → repeated curated-reference boilerplate. `llm_complete()`
is called **only for Pro** and its answer lives in a separate optional field.
The persisted provider is `offline`, its encrypted key is empty, and no AI key
exists in this server environment. Thus no provider call is possible. No
conversation table/history/context exists. Each call sends only a system
message and one user message. Provider failures are caught and labelled as
`offline_fallback` rather than errors; the original generic answer remains.
This is intentional legacy logic, not a network/invalid-model diagnosis.

## Circuit/workspace gaps
The legacy Circuit Designer is a form/report tool: no node/pin graph, canvas,
undo/redo, project-scoped circuit storage, versioned design or managed code
regions. Library pin maps are generated consistently by the compiler, but
user workspaces store notes/progress, not editable circuit graphs. Existing
library/compiler behavior will be retained; new saved engineering designs
will have UUIDs, exact-pin edges, optimistic revisions and immutable versions.

## Integration truth
No online chat, image or web-search credentials are present. Live-provider
acceptance is **blocked by operator configuration**, not passed. Adapter and
error-path integration tests may use an explicitly labelled local test server;
that does not establish public-provider connectivity. Concept art must not be
substituted with stock/placeholder imagery. Hardware was not physically tested.

## Scope and compatibility
Additive migrations preserve existing tables/data. Provider adapters, saved
conversations/jobs, a canonical engineering specification, Circuit Studio,
Invention Lab and protected generated assets live inside the same app and
reuse central entitlement checks. Offline catalog lookup, circuit rules and
static firmware checks remain explicitly named basic functions; they are not
fallback conversational AI. All privileged settings remain server-side.
