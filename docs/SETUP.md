# Installation & setup guide

## Requirements

- Python 3.10 or newer (standard library only). Tested on Python 3.13.
- A modern browser for the SPA. No Node.js build step; `web/` is plain HTML/CSS/JS.
- Optional: `paho-mqtt==2.1.0` only if you want an MQTT bridge for device telemetry.
- Optional: Stripe account + API keys for real checkout.
- Optional: an OpenAI-compatible API key for live LLM enrichment of Pro tools.

## 1. Install

```bash
git clone <your-repo> nexus-iot        # or unzip the delivered folder
cd nexus-iot
python3 --version
# No pip install needed. Optional:
# python3 -m pip install paho-mqtt==2.1.0
```

The application creates its own data directory (`./data`) and an app secret on first boot.
For production, set `NEXUS_SECRET` from a secret manager instead:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
export NEXUS_SECRET=<the-output>
```

## 2. Bootstrap the first administrator

```bash
python3 scripts/bootstrap_admin.py admin@example.com
# prompts for a password with getpass; enforces >=10 chars, upper, lower, digit
```

Non-interactive (containers / CI):

```bash
NEXUS_ADMIN_EMAIL=admin@example.com NEXUS_ADMIN_PASSWORD='a-strong-password' \
  python3 scripts/bootstrap_admin.py admin@example.com
```

The command refuses to run without a TTY when no password is supplied, and never uses a
default password. Promoting an existing user to admin is possible with the same command.
Every bootstrap is written to the audit log.

## 3. Run

```bash
python3 run.py
# [NEXUS] Library: 117 specs; inserted 117 ...
# [NEXUS] NEXUS IoT ready on http://0.0.0.0:8000
```

Open `http://localhost:8000`. The host is `0.0.0.0` so proxied/live-preview environments
work. Frontend API calls are all **relative URLs** (`/api/...`), so no CORS or hardcoded
host is required.

Useful environment overrides:

```bash
PORT=8080 HOST=0.0.0.0 NEXUS_DATA_DIR=/var/lib/nexus python3 run.py
```

## 4. Verify

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/config/public | python3 -m json.tool | head -30
python3 -m unittest discover -s tests -v
```

## 5. Configure AI (optional)

Without any key, all 10 Pro tools and the free assistant run on NEXUS's **deterministic
offline engine**. To add an LLM narrative layer:

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1     # or any compatible endpoint
export NEXUS_AI_MODEL=gpt-4o-mini
python3 run.py
```

Or in **Admin → AI & Config**, set provider=`openai_compatible`, base URL, model, and paste
an API key. The key is encrypted at rest with an HMAC-derived keystream and never returned
by any API; only a masked hint (e.g. `sk-…abcd`) is shown. Use **Test connection** to verify.
If a live call fails, online chat returns an explicit provider error (never a generic fallback). Legacy deterministic tool output
still stands.

## 6. Configure payments (optional but required for real checkout)

1. Create a recurring **Price** in Stripe. Copy its ID.
2. Set all four variables:

```bash
export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_PUBLISHABLE_KEY=pk_test_...
export STRIPE_PRICE_ID=price_...
export STRIPE_WEBHOOK_SECRET=whsec_...
```

3. In Stripe, add a webhook endpoint pointing to:

```
POST https://your-domain/api/billing/webhook
```

with events: `checkout.session.completed`, `customer.subscription.updated`,
`customer.subscription.deleted`, `invoice.payment_failed`.

4. Restart the server. The upgrade page will now show a live **Continue to secure checkout**
button, and `/api/config/public` will report `payments.configured: true`.

**Security model:** the browser success URL is only a landing page. It does not grant access.
The webhook verifies `HMAC-SHA256(timestamp + "." + raw_body)` against
`STRIPE_WEBHOOK_SECRET` with a 5-minute tolerance and constant-time comparison. Only a
`checkout.session.completed` with `payment_status=paid` (or a verified active/trialing
subscription event) grants Pro. Failed invoices set `past_due`; subscription deletion
revokes Pro. A replayed or malformed signature is rejected and audited as
`billing.webhook_rejected`.

If Stripe is **not** configured, the upgrade page says so, lists the missing variables and
gives setup instructions. No simulated payment ever grants access.

### Manual / offline payment restoration

After a **confirmed** payment outside Stripe:

```bash
python3 scripts/manage.py entitle user@example.com pro --days 30
python3 scripts/manage.py revoke user@example.com
python3 scripts/manage.py list-users
```

These are audited and take effect on the next request (entitlements are recomputed per
request). Equivalent action is available in Admin → Users (`Grant Pro`).

## 7. Device telemetry

HTTP ingest works with zero dependencies:

```bash
# Create a device in Pro Workspace → Device Monitoring (copy the token once).
curl -X POST http://localhost:8000/api/ingest/<DEVICE_TOKEN> \
  -H 'Content-Type: application/json' \
  -d '{"samples":[{"key":"temperature_c","value":24.6,"unit":"C"}]}'
```

For MQTT, install `paho-mqtt` and configure
`NEXUS_MQTT_BROKER`/`NEXUS_MQTT_PORT`/`NEXUS_MQTT_TOPIC`/`NEXUS_MQTT_USER`/
`NEXUS_MQTT_PASSWORD`, or set them in Admin → AI & Config → Integrations. The UI clearly
states when MQTT is not configured. Simulated samples are always stored with
`source='simulated'`.

## 8. Maintenance

```bash
python3 scripts/manage.py reseed       # rebuild all 117 records from specs,
                                       # preserving the admin's free-15 designation
python3 scripts/manage.py set-password user@example.com
python3 scripts/manage.py set-role user@example.com pro
```

Back up `data/nexus.db` (and `.app_secret`) together — encrypted admin API keys cannot be
decrypted without the app secret. The database uses WAL; use `sqlite3 data/nexus.db
".backup backup.db"` for a consistent snapshot.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `Address already in use` | `PORT=8001 python3 run.py` or stop the other process. |
| Login loops back to sign-in | Embedded previews can block third-party cookies. The SPA supports a server-issued bearer token and a restricted query-token fallback for preview sessions. If the session still does not persist, use **Open NEXUS in a new tab** on the sign-in card. If no admin exists, create one using `python3 scripts/bootstrap_admin.py admin@example.com`. |
| `403 CSRF token` | The SPA sends `X-CSRF-Token` from the `nexus_csrf` cookie, the login response, or session storage. Hard-refresh the page, then sign in again. |
| Raw `{"error":{"code":"unauthorized"...}}` when clicking an export or diagram | Reload the latest preview assets (`app.js?v=10`). Exports/diagrams are fetched through the authenticated SPA instead of a bare API link. |
| Admin UI shows "Payments not configured" | Expected. See §6. |
| Provider error / AI setup required | Configure Admin → AI Providers and run the real connection test. No generic chat fallback is returned; named basic/rule functions remain available. |
| Library count changed after reseed | `reseed` restores the 117 specs but preserves free designation; admin-created extra projects remain. |


## Connected workstation upgrade

See [WORKSTATION.md](WORKSTATION.md) for independent chat/image/search configuration,
secure local key-entry CLI, migration notes, canonical design workflows and exact live
acceptance commands. Online chat is no longer replaced by generic offline responses.
The build marker is **6**; reload the live preview to load the new modules.
