# Honest limitations and safety notes

NEXUS IoT is a serious engineering workspace, but it does not pretend to be something it
is not. Please read this before building anything.

## Code status

Every generated sketch/script is labelled **“Statically reviewed – NOT hardware-tested.”**
No project in the seeded library has been built, powered or measured on physical hardware
in this environment. `quality.physical_test_confirmed` is `false` for all 117 records.
Automated checks cover: balanced braces/parentheses, Python syntax, no unresolved tokens,
no duplicate declarations, pin/firmware consistency, no hardcoded credentials. They do
**not** replace compiling for a real board core or a bench test.

Before applying power:

1. Compare every wiring-table row with the **actual module silkscreen** and the linked
   datasheet. Board revisions differ.
2. Measure every signal voltage with a multimeter. ESP32/Raspberry Pi/Pico GPIOs are
   **not 5 V tolerant**.
3. Use a current-limited supply for first power-on and verify common ground.
4. Install the exact library versions listed in the Code tab. API changes break builds.
5. Replace all `YOUR_*` placeholders and `TODO` calibration constants with measured values.

## Electrical and calibration caveats

- Indicative constants (`DRY_RAW`, `WET_RAW`, `CAL_FACTOR`, K-factors, tank geometry,
  `ANEMO_FACTOR`, `BATTERY_AH`, `CRED_EXPIRY_EPOCH`, etc.) are **placeholders**, not
  measured values. Calibrate against a known reference before trusting any number.
- Price bands are 2024-era single-unit hobby estimates in USD, not live quotes.
- ESP8266 has one 1.0 V-max ADC; the catalog flags divider requirements. ESP32 ADC2 is
  unusable while Wi-Fi is active; the validator warns about this.
- Low-cost MOS gas sensors (MQ-2, MQ-7, MQ-135) are cross-sensitive and are **not**
  certified detectors. CCS811 eCO₂ is a VOC-derived estimate, not NDIR CO₂. Optical PM
  sensors over-read at high humidity; correction coefficients are local assumptions.
- Raspberry Pi firmware is a documented scaffold with driver `TODO` stubs — it is valid
  Python 3 but needs the real sensor libraries wired in before deployment.

## High-risk domains

Mains electricity, hazardous gases, healthcare and similar domains use **safe low-voltage
educational alternatives**. Nothing here is a certified safety device, medical device,
fire alarm, or a substitute for professional engineering. Wellness/health prototypes carry
explicit `medical_device: false` flags and must not be used for diagnosis. Mains-powered
examples avoid mains wiring entirely; where a 230 V topic appears, the design uses low
voltage and states the limitation.

## AI honesty

- **General conversational AI:** real configured OpenAI-compatible or Ollama calls,
  for Free as well as Pro (with limits). No key/provider = explicit configuration error.
  No hardcoded chat answer, silent fallback or domain restriction.
- **Deterministic basic functions:** catalog lookup, circuit rules, static source checks,
  learning and the retained legacy tools. They are not a general-purpose language model.
- **Online model failures:** typed errors, persisted failed messages/jobs and retry
  controls. Legacy optional enrichment reports a separate provider error.
- **Citations:** real configured Tavily/SearXNG search, or explicitly labelled curated
  links. Search snippets are not proof of novelty. The model's untraceable source IDs are
  not accepted as retrieved evidence.
- **Startup Lab:** the 0–100 viability score is an additive, fully disclosed heuristic over
  six assumed factors. It is **not** a probability of success, a revenue forecast or market
  data. No market statistics are invented.
- **Debugging Center:** rule-based static analysis. It never executes your code or claims to
  have tested hardware.

## Device monitoring

- Real samples arrive through `POST /api/ingest/<token>` and are stored with
  `source='real'`. Simulated samples are stored with `source='simulated'` and displayed in
  a different colour. Never present simulated data as operational evidence.
- HTTP ingest is always available. MQTT bridging requires `paho-mqtt` and a broker; the UI
  reports `NOT CONFIGURED` when absent. No silent fake telemetry is generated.

## Payments

- Without Stripe credentials, **no payment is processed** and no entitlement is granted.
  The UI says payments are not configured and shows setup steps.
- Access is granted only by a signature-verified webhook or an audited admin/CLI action
  after a confirmed payment — never by a browser redirect.

## Security

- Passwords are PBKDF2-HMAC-SHA256 with 240k iterations; sessions are random 256-bit
  tokens stored as digests with HMAC-signed cookies and CSRF double-submit.
- Admin-entered API keys are encrypted at rest with an app-secret-derived keystream. Back
  up `data/.app_secret` (or `NEXUS_SECRET`) with the database or those keys cannot be
  decrypted.
- Admin UI and audit logs never display secrets, password hashes or payment credentials.
- The stdlib server should be deployed behind a TLS reverse proxy for production HTTPS.
- To work inside embedded previews that block third-party cookies, the login response also
  returns the opaque session token and the SPA keeps it in `sessionStorage` (in memory only
  if storage is blocked). This is equivalent to the cookie session — same server-side hash,
  CSRF, expiry and revocation — but any script running on the page could read it. The CSP
  permits same-origin scripts only and there are no third-party assets. For a hardened
  deployment, remove `session_token` from the two auth responses to force cookie-only auth.
- In embedded previews that strip the `Authorization` header and block cookies, the SPA
  falls back to a session token in the request query string. The server never logs query
  strings, but proxies in front of it might. Disable with `NEXUS_ALLOW_QUERY_SESSION=0`.

## Scope

The platform does not provide: certified hardware test reports, live supplier pricing,
automatic PCB fabrication files for every project, a full Modbus/LoRaWAN stack, or a
production-grade message broker. Where a feature is a scaffold (e.g. Raspberry Pi driver
stubs, MQTT bridge), it is explicitly labelled as such.


## Connected workstation scope (build 6)

- Circuit Studio currently supports two documented ESP32 board variants and 15
  component/support definitions. The 7-board/73-part legacy catalog remains in place.
  Arbitrary sensors are **not** assigned invented pinouts. Admin-reviewed custom metadata
  can be added via the protected component API; no driver is magically created.
- Diagrams are exact-pin connection drawings, not PCB layouts, SPICE simulation or
  certified schematics. Arduino toolchain, electrical simulator and real hardware are
  absent. Static tests do not establish electrical safety.
- Firmware has a managed pin region. Pin moves preserve unrelated edits; component
  changes require review/rebuild. Online source proposals are reviewed as diffs before
  explicit application. Library Raspberry Pi examples remain documented driver scaffolds.
- Invention proposals are model-generated requirements with constrained supported
  circuits/driver templates. Specialized algorithms can be proposed by the online Code
  Engineer; they still need local compilation/engineering review. Unsupported parts and
  manual work remain named, and an incomplete design is not presented as tested.
- Image generation needs an independent provider/model/key selection. Only actual
  PNG/JPEG/WebP bytes are stored, protected by owner checks. Prompt variations are new
  generations, not pixel editing. Artistic images are not wiring instructions.
- Vision, PDF extraction, native model function-calls, pixel edits, arbitrary driver
  synthesis, automatic patent completeness and PCB fabrication output are not implemented.
  Text/code attachments and explicit command routing are available.
- Cancellation is best-effort: streaming stops on the next readable delta; non-streaming
  external calls can remain in flight until timeout and may incur upstream charges.
- The stdlib worker runner is single-process, bounded (2 active jobs/account, 16 total).
  Jobs/events persist; a restart marks unfinished jobs interrupted for honest retry,
  not automatic replay of potentially billable requests. Horizontal multi-worker
  deployment requires an external job queue and session-safe production hosting.
- External image URLs must be HTTPS/public-address targets; redirects are not followed.
  Provider base URLs are admin/server-controlled to permit local Ollama/SearXNG servers.
  Never grant provider-configuration privileges to untrusted users.
- Protected assets use `Cache-Control: no-store` so expiry/logout cannot be bypassed by
  a private browser cache. Read access to previously saved **own** design/image data is
  retained after expiry; new premium work and protected library exports are denied.


New stored secrets use versioned, separate HMAC-derived encryption/MAC subkeys; legacy
values remain readable. The zero-dependency storage primitive is not a substitute for
an independently audited KMS/secret manager. For hardened production deployments,
prefer server-injected secret-manager environment values, least-privilege service accounts
and an infrastructure security review. No penetration-test certification is implied.
