# API key setup — build 9: Google Gemini and other providers

1. Reload the port-8000 live preview and sign in as the administrator.
2. Open **AI & API Keys** in the main navigation (or the **Add API key** shortcut
   in the top bar/dashboard). Direct application route: `#/ai-settings`.
3. Choose **Google Gemini** (recommended for this setup), **OpenAI**, another
   **OpenAI-compatible API**, or **Ollama**. For Gemini, create your key at
   https://aistudio.google.com/apikey; an OpenAI key cannot be used with Gemini.
4. Paste your real provider API key into the masked **API key** field. Do not
   paste secrets into this chat. Check the model/deployment ID your account supports.
5. Click **Save & Connect**. It makes a real request using the chosen model and
   streaming setting, then encrypts/saves the working configuration. A successful
   test displays **Connected** and enables chat immediately—no server restart.
6. Open **AI Assistant** and ask a new question. The same chat connection powers
   Invention Lab and online Code Engineer, subject to plan permissions and limits.

## Google Gemini — no OpenAI balance needed

Choose **Google Gemini**, paste your own Google AI Studio key, then **Save & Connect**.
The app automatically selects Google's documented endpoint:
`https://generativelanguage.googleapis.com/v1beta` and `gemini-3.5-flash-lite`.
The model remains editable; other models may be entered manually, subject to
project access. Google currently documents a limited free tier for selected models;
quota, account eligibility and data-use terms apply. This is not unlimited free usage.
An OpenAI credit balance is not used for a Google Gemini request.

The native Google generateContent/streamGenerateContent HTTP/SSE adapter calls Google directly, not an OpenAI proxy. Legacy /v1beta/openai URLs remain compatible and are mapped to the native endpoint.
Gemini's small verification/health calls allow a bounded thinking-token budget;
the old 32-token OpenAI probe is not assumed suitable for a reasoning model.
Only text chat/streaming are enabled by this integration. It does not imply live
Google Search grounding, image generation, electrical simulation or hardware tests.
Existing independent image settings are left untouched.

No prior vendor's saved/typed key is silently reused after a provider or endpoint
change. Failed Gemini verification preserves the last saved working configuration.
API secrets remain encrypted server-side, masked/write-only in admin responses.

### Optional environment setup

Use your service manager or a hidden local configuration prompt; do not paste a
real key into this chat or put it in a shell command/history:

- `NEXUS_AI_PROVIDER=gemini`
- `GEMINI_API_KEY` from your secret manager
- `NEXUS_AI_MODEL=gemini-3.5-flash-lite`

Alternatively use `python3 scripts/configure_ai.py --provider gemini --model gemini-3.5-flash-lite`;
the CLI prompts without echoing the key. DB settings activate without restart;
environment changes require restarting the process. Existing admin overrides win.
Google keys are not substituted into the OpenAI image adapter.

Official sources checked 25 October 2026:
[1](https://ai.google.dev/gemini-api/docs/openai) ·
[7](https://ai.google.dev/gemini-api/docs/api-key) ·
[Pricing](https://ai.google.dev/gemini-api/docs/pricing).

## Other providers

For OpenAI, the form starts with `https://api.openai.com/v1` and `gpt-4o-mini`;
change the model if your API account uses another supported model. Other gateways
need their own trusted base URL/model under **Endpoint & streaming settings**.
If a compatible gateway does not stream, turn streaming off before testing.
Use a valid API key with provider API access and sufficient billing/quota; a normal
consumer chat subscription is not a replacement for a provider API credential.

## Optional services

- **Image Studio:** for an OpenAI-compatible image provider, explicitly check **also configure Image Studio with this key**
  and select a supported image model, or configure a separate image provider in
  the advanced section. A chat test is not an image-generation test.
- **Web research:** configure Tavily or SearXNG in the advanced section for live
  search. Curated documentation remains available without it.
- Neither of these optional settings blocks ordinary online chat.
- Hardware tests, electrical simulation and unsupported component drivers cannot
  be supplied by an API key. These remain accurately labelled limitations.

## Safety and behavior

Only administrators can edit the platform-wide key. Other accounts see connection
status without key access. Secrets are POSTed in the request body, encrypted on the
server and never returned as raw values or saved in browser storage. Blank means
reuse an existing saved key for that same adapter and endpoint. Failed verification does not overwrite
a working configuration. **Save settings, verify later** explicitly reports unverified,
not connected. Connection status is scoped to the tested key/model/endpoint and its
last-test timestamp; it does not promise that an upstream provider stays available.

## Build 9 repair and actual verification

The previously auto-selected 3.8 Flash model timed out. The saved key could list
Google models and produced real replies with **Gemini 3.5 Flash-Lite**, so it did
not need replacement. The live workspace is now connected using that model.
A real streamed C-recursion answer was also displayed through AI Assistant;
only that newly created QA conversation was removed afterward.

**Save & Connect** now returns a job ID immediately (HTTP 202), then follows short
status requests. A slow upstream request no longer holds one browser POST open
until the preview gateway times out. Reload this page to resume an active check;
cancel is explicit, and failed/cancelled/stale checks do not overwrite current
settings. Candidate keys remain in worker RAM until successful encrypted activation;
no raw key is written to job rows, events or browser storage. A server restart marks
unfinished jobs interrupted and requires retry, rather than pretending success.

Malformed/HTML replies, including HTTP 200, are rejected with the HTTP status and an
**unknown outcome** warning. Raw gateway bodies are never echoed. The app no longer
asserts that settings were preserved merely because a response could not be read.
Use **Recheck recent status** before starting another request.

Validation: **78 automated tests (76 passed, 2 opt-in live tests skipped)**,
**32 isolated Chromium checks**, **10 frontend protocol checks**, plus the separate
**real Google background activation and live Assistant/browser check**. The real
reports in `docs/qa/gemini-live-activation.json` and `gemini-live-assistant.json`
contain no credentials. The broader six-topic/image/hardware acceptance is not
claimed by this one real chat check.
