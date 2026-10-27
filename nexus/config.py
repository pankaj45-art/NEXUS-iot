"""Central configuration for NEXUS IoT.

Secrets are read from the environment.  Everything else is stored in the
``settings`` database table so administrators can change it at runtime.
Environment values always win for secret material (defence in depth).
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = Path(os.environ.get("NEXUS_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("NEXUS_DB_PATH", DATA_DIR / "nexus.db")).resolve()
EXPORT_DIR = DATA_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")


def _app_secret() -> bytes:
    """Return a stable application secret.

    A random secret is generated and persisted on first boot if the operator
    did not supply one.  This is used for cookie signing and at-rest
    encryption of admin-entered API keys.  Production deployments should set
    NEXUS_SECRET from a secret manager instead.
    """
    env = os.environ.get("NEXUS_SECRET")
    if env:
        return env.encode("utf-8")
    path = DATA_DIR / ".app_secret"
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip().encode("utf-8")


APP_SECRET = _app_secret()
SESSION_TTL_SECONDS = int(os.environ.get("NEXUS_SESSION_TTL", 60 * 60 * 24 * 14))
PBKDF2_ITERATIONS = 240_000
# Embedded preview fallback (query-string session token). Set to "0" in
# production to force cookie/bearer-only authentication.
ALLOW_QUERY_SESSION = os.environ.get("NEXUS_ALLOW_QUERY_SESSION", "1") != "0"

# ---------------------------------------------------------------------------
# Optional integrations.  All are disabled unless credentials are supplied.
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_API_BASE = "https://api.stripe.com/v1"

# Provider-specific credentials must not be mixed when both vendors are set.
OPENAI_ENV_KEY = os.environ.get("OPENAI_API_KEY") or ""
GEMINI_ENV_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
AI_ENV_PROVIDER = os.environ.get("NEXUS_AI_PROVIDER", "").strip().lower()
if not AI_ENV_PROVIDER and GEMINI_ENV_KEY and not (OPENAI_ENV_KEY or os.environ.get("NEXUS_AI_API_KEY")):
    AI_ENV_PROVIDER = "gemini"
if AI_ENV_PROVIDER == "gemini":
    AI_ENV_KEY = GEMINI_ENV_KEY or os.environ.get("NEXUS_AI_API_KEY") or ""
    AI_ENV_BASE = os.environ.get("NEXUS_AI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta"
    AI_ENV_MODEL = os.environ.get("NEXUS_AI_MODEL") or "gemini-3.5-flash-lite"
else:
    AI_ENV_KEY = OPENAI_ENV_KEY or os.environ.get("NEXUS_AI_API_KEY") or ""
    AI_ENV_BASE = os.environ.get("OPENAI_BASE_URL") or os.environ.get("NEXUS_AI_BASE_URL") or "https://api.openai.com/v1"
    AI_ENV_MODEL = os.environ.get("NEXUS_AI_MODEL") or ("llama3.2" if AI_ENV_PROVIDER == "ollama" else "gpt-4o-mini")
AI_TIMEOUT = float(os.environ.get("NEXUS_AI_TIMEOUT", "30"))

# Image generation is configured independently from chat: a provider may
# support text but not images (and vice versa).
IMAGE_ENV_KEY = os.environ.get("NEXUS_IMAGE_API_KEY") or ""
IMAGE_ENV_BASE = os.environ.get("NEXUS_IMAGE_BASE_URL") or ""
IMAGE_ENV_MODEL = os.environ.get("NEXUS_IMAGE_MODEL") or "gpt-image-1"
IMAGE_ENV_PROVIDER = os.environ.get("NEXUS_IMAGE_PROVIDER", "").strip().lower()
IMAGE_TIMEOUT = float(os.environ.get("NEXUS_IMAGE_TIMEOUT", "90"))

# Optional web-search provider for the research tools.  Without one, research
# uses only the curated corpus of real documentation URLs.
SEARCH_ENV_PROVIDER = os.environ.get("NEXUS_SEARCH_PROVIDER", "none").strip().lower()
SEARCH_ENV_KEY = os.environ.get("NEXUS_SEARCH_API_KEY") or ""
SEARCH_ENV_BASE = os.environ.get("NEXUS_SEARCH_BASE_URL") or ""
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"

MQTT_BROKER = os.environ.get("NEXUS_MQTT_BROKER", "")
MQTT_PORT = int(os.environ.get("NEXUS_MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("NEXUS_MQTT_TOPIC", "nexus/devices/#")
MQTT_USER = os.environ.get("NEXUS_MQTT_USER", "")
MQTT_PASSWORD = os.environ.get("NEXUS_MQTT_PASSWORD", "")

DEFAULT_SETTINGS = {
    "platform": {
        "name": "NEXUS IoT",
        "tagline": "AI-powered IoT engineering workspace",
        "support_email": "support@nexus-iot.local",
        "ai": {
            "provider": "offline",  # offline | openai_compatible
            "base_url": AI_ENV_BASE,
            "model": AI_ENV_MODEL,
            "api_key_encrypted": "",
            "api_key_hint": "",
            "enabled": True,
            "note": "Offline engine is deterministic and fully functional; it does not call an LLM.",
        },
        "payments": {
            "provider": "stripe" if STRIPE_SECRET_KEY else "none",
            "plan_name": "NEXUS Pro",
            "currency": "USD",
            "amount": 3.0,
            "interval": "month",
            "trial_days": 0,
            "manual_activation_enabled": True,
        },
        "integrations": {
            "mqtt": {"enabled": False, "broker": MQTT_BROKER, "port": MQTT_PORT, "topic": MQTT_TOPIC},
            "http_ingest": {"enabled": True},
        },
    },
    "limits": {
        "free": {
            "ai_requests_per_day": 8,
            "projects_created_total": 3,
            "workspace_items": 5,
            "tool_calls_per_day": 0,
            "max_code_chars": 4000,
        },
        "pro": {
            "ai_requests_per_day": 250,
            "projects_created_total": -1,
            "workspace_items": -1,
            "tool_calls_per_day": 400,
            "max_code_chars": 60000,
        },
        "admin": {
            "ai_requests_per_day": 500,
            "projects_created_total": -1,
            "workspace_items": -1,
            "tool_calls_per_day": 1000,
            "max_code_chars": 120000,
        },
    },
    "public_free_feature_policy": {
        # Administrators may open a Pro tool to free users without a code
        # change.  Empty by default: every Pro tool stays Pro.
        "allowed_pro_tools": [],
    },
    "project_quality": {
        "minimum_status_for_publish": "Technically reviewed",
        "require_all_sections": True,
    },
}
