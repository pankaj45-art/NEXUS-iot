"""Provider registry: configuration, capability negotiation and health.

All secrets live here (server-side only).  ``public_view()`` returns a write-only
description that is safe to send to the browser: it never contains a key, and
keys are stored encrypted at rest with the app-secret-derived keystream.
"""
from __future__ import annotations

import time
from typing import Any

from .. import config, db
from ..security import decrypt_secret, encrypt_secret, mask_secret
from .base import CAPABILITIES, ChatProvider, NullProvider, ProviderError
from .ollama import OllamaProvider
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatProvider

SETTINGS_KEY = "ai_providers"
_HEALTH_CACHE: dict[str, tuple[float, dict]] = {}
_HEALTH_TTL = 45.0

PROVIDERS: dict[str, type[ChatProvider]] = {
    "none": NullProvider,
    "openai_compatible": OpenAICompatProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}

# Capabilities each adapter family genuinely supports.  Vision/web/tool-calls
# are opt-in and only exposed when the configured model actually has them.
DEFAULT_CAPS = {
    "openai_compatible": {"chat": True, "streaming": True, "image_generation": True,
                          "vision": False, "embeddings": False, "tool_calls": False,
                          "web_search": False},
    "gemini": {"chat": True, "streaming": True, "image_generation": False,
               "vision": False, "embeddings": False, "tool_calls": False, "web_search": False},
    "ollama": {"chat": True, "streaming": True, "image_generation": False,
               "vision": False, "embeddings": False, "tool_calls": False,
               "web_search": False},
    "none": {c: False for c in CAPABILITIES},
}


def _chat_defaults() -> dict:
    provider = (config.AI_ENV_PROVIDER or ("openai_compatible" if config.AI_ENV_KEY else "none"))
    return {
        "provider": provider,
        "base_url": config.OLLAMA_BASE_URL if provider == "ollama" else config.AI_ENV_BASE,
        "model": config.AI_ENV_MODEL,
        "api_key_encrypted": encrypt_secret(config.AI_ENV_KEY) if config.AI_ENV_KEY else "",
        "enabled": True,
        "timeout": float(config.AI_TIMEOUT),
        "max_retries": 1,
        "capabilities": dict(DEFAULT_CAPS.get(provider, DEFAULT_CAPS["none"])),
    }


def _image_defaults() -> dict:
    key = config.IMAGE_ENV_KEY or (config.OPENAI_ENV_KEY if config.AI_ENV_PROVIDER == "gemini" else config.AI_ENV_KEY)
    provider = config.IMAGE_ENV_PROVIDER or ("openai_compatible" if config.IMAGE_ENV_KEY else "none")
    return {
        "provider": provider,
        "base_url": config.IMAGE_ENV_BASE or ("https://api.openai.com/v1" if config.AI_ENV_PROVIDER == "gemini" else config.AI_ENV_BASE),
        "model": config.IMAGE_ENV_MODEL,
        "api_key_encrypted": encrypt_secret(key) if key else "",
        "enabled": bool(key) and provider != "none",
        "timeout": float(config.IMAGE_TIMEOUT),
        "max_retries": 0,
        "default_size": "1024x1024",
    }


def defaults() -> dict:
    return {
        "chat": _chat_defaults(),
        "image": _image_defaults(),
        "web_search": {
            "provider": config.SEARCH_ENV_PROVIDER,
            "base_url": config.SEARCH_ENV_BASE,
            "api_key_encrypted": encrypt_secret(config.SEARCH_ENV_KEY) if config.SEARCH_ENV_KEY else "",
            "enabled": bool(config.SEARCH_ENV_KEY),
        },
        "policy": {
            # Offline deterministic output is allowed ONLY for these explicitly
            # named basic functions.  It is never substituted for a failed chat.
            "offline_basic_functions": [
                "component_lookup", "datasheet_references", "circuit_validation",
                "learning_modules", "firmware_static_checks",
            ],
            "allow_offline_chat_fallback": False,
            "daily_image_limit_free": 0,
            "daily_image_limit_pro": 10,
        },
    }


def load(conn) -> dict:
    """Merge persisted admin settings over env-derived defaults."""
    d = defaults()
    saved = db.get_setting(conn, SETTINGS_KEY, {}) or {}
    if not saved:
        legacy = (db.get_setting(conn, "platform", {}) or {}).get("ai", {})
        # Preserve an existing configured provider/key, but do not let the old
        # default 'offline' override a genuinely configured environment.
        if legacy.get("provider") == "openai_compatible":
            d["chat"].update({k: v for k, v in legacy.items() if k != "api_key_hint"})
    for section in ("chat", "image", "web_search", "policy"):
        if isinstance(saved.get(section), dict):
            merged = dict(d[section])
            merged.update(saved[section])
            if section in ("chat", "image", "web_search") and isinstance(saved[section].get("capabilities"), dict):
                caps = dict(d[section].get("capabilities", {}))
                caps.update(saved[section]["capabilities"])
                merged["capabilities"] = caps
            d[section] = merged
    return d


def credential_scope(provider: str, base_url: str) -> tuple:
    """Blank keys may be reused only for the same adapter AND endpoint."""
    base = str(base_url or '').strip().rstrip('/')
    if provider == 'gemini' and base == 'https://generativelanguage.googleapis.com/v1beta/openai':
        base = base[:-7]
    return str(provider), base


def save(conn, patch: dict) -> dict:
    """Persist a partial patch.  Blank/masked API keys mean 'keep existing'."""
    current = load(conn)
    for section in ("chat", "image", "web_search", "policy"):
        if not isinstance(patch.get(section), dict):
            continue
        incoming = dict(patch[section])
        if section in ("chat", "image", "web_search"):
            before = current[section]
            provider = incoming.get('provider', before.get('provider', 'none'))
            if credential_scope(provider, incoming.get('base_url', before.get('base_url', ''))) != credential_scope(before.get('provider'), before.get('base_url')):
                # Never forward an OpenAI key to Gemini (or another endpoint)
                # just because the new key field was left blank.
                current[section]['api_key_encrypted'] = ''
            if section == 'chat' and provider != before.get('provider'):
                current[section]['capabilities'] = dict(DEFAULT_CAPS.get(provider, DEFAULT_CAPS['none']))
        if section == 'chat' and isinstance(incoming.get('capabilities'), dict):
            incoming['capabilities'] = {**current[section].get('capabilities', {}), **incoming['capabilities']}
        if "api_key" in incoming:
            new_key = str(incoming.pop("api_key") or "").strip()
            # A masked hint or empty value must not overwrite the stored key.
            if new_key and "…" not in new_key and "***" not in new_key:
                current[section]["api_key_encrypted"] = encrypt_secret(new_key)

        current[section].update(incoming)
    db.set_setting(conn, SETTINGS_KEY, current)
    _HEALTH_CACHE.clear()
    return current


def _decrypt(section: dict) -> dict:
    out = dict(section)
    enc = out.pop("api_key_encrypted", "")
    key = ""
    if enc:
        try:
            key = decrypt_secret(enc)
        except ValueError:
            key = ""
    out["api_key"] = key
    return out


def build(kind: str, conn) -> ChatProvider:
    """Return a configured adapter for ``chat`` or ``image``."""
    settings = load(conn)
    section = _decrypt(settings.get(kind, {}))
    provider_name = section.get("provider", "none")
    cls = PROVIDERS.get(provider_name)
    if cls is None:
        # Misconfiguration must not break login/admin access. A null adapter
        # reports the exact problem rather than making public config return 500.
        section['configuration_error'] = f"Unknown provider '{provider_name}'. Available: {', '.join(PROVIDERS)}."
        return NullProvider(section)
    if provider_name in ("openai_compatible", "gemini"):
        caps = dict(DEFAULT_CAPS[provider_name])
        caps.update(section.get("capabilities") or {})
        section["capabilities"] = caps
    adapter = cls(section)
    if kind == 'chat':
        adapter.supports = tuple(c for c in adapter.supports if c != 'image_generation')
    return adapter


def chat_provider(conn) -> ChatProvider:
    return build("chat", conn)


def image_provider(conn) -> ChatProvider:
    return build("image", conn)


def chat_config(conn) -> dict:
    """Backward-compatible flat config used by the legacy tool layer."""
    s = load(conn)["chat"]
    dec = _decrypt(s)
    return {
        "provider": dec.get("provider", "none"),
        "base_url": dec.get("base_url", ""),
        "model": dec.get("model", ""),
        "enabled": bool(dec.get("enabled", True)),
        "api_key": dec.get("api_key", ""),
        "api_key_hint": mask_secret(dec.get("api_key", "")),
        "timeout": dec.get("timeout", 30),
        "max_retries": dec.get("max_retries", 1),
        "capabilities": dec.get("capabilities", {}),
        "env_key_present": bool(config.AI_ENV_KEY),
        "note": dec.get("note", ""),
    }


def capability_map(conn) -> dict[str, bool]:
    out = {c: False for c in CAPABILITIES}
    chat = chat_provider(conn)
    if chat.configured() and not chat.missing():
        for k, v in chat.capabilities().items():
            out[k] = out[k] or bool(v)
    img = image_provider(conn)
    if img.configured() and not img.missing() and "image_generation" in img.supports:
        out["image_generation"] = True
    ws = load(conn)["web_search"]
    out["web_search"] = bool(ws.get("enabled") and ws.get("provider") != "none")
    return out


def health(conn, *, force: bool = False) -> dict:
    """Real reachability probe with a short cache; never logs credentials."""
    cached = _HEALTH_CACHE.get("health")
    if cached and not force and time.time() - cached[0] < _HEALTH_TTL:
        return dict(cached[1])
    chat = chat_provider(conn)
    img = image_provider(conn)
    cfg = load(conn)
    chat_h = chat.health()
    image_h = {
        "provider": img.name, "model": img.model,
        "configured": not bool(img.missing()) and img.configured() and "image_generation" in img.supports,
        "enabled": img.configured(), "missing": img.missing(),
        "reachable": None,  # not probed: image models cannot be tested with chat ping
    }
    if img.name == "none":
        image_h["error"] = {"code": "provider_not_configured",
                            "message": "No image-generation provider configured."}
    caps = capability_map(conn)
    configured = chat_h.get("configured") and chat_h.get("reachable") is not False and not chat_h.get("error")
    result = {
        "checked_at": time.time(),
        "chat": chat_h,
        "image": image_h,
        "web_search": {"provider": cfg["web_search"].get("provider", "none"),
                       "enabled": bool(cfg["web_search"].get("enabled"))},
        "capabilities": caps,
        "policy": cfg["policy"],
        "online": bool(configured and chat_h.get("reachable")),
        "status": ("online" if configured and chat_h.get("reachable") else
                   "misconfigured" if chat_h.get("missing") else
                   "unreachable" if chat_h.get("reachable") is False else "not_configured"),
        "message": _health_message(chat_h, caps),
        "setup": SETUP_INSTRUCTIONS,
    }
    _HEALTH_CACHE["health"] = (time.time(), result)
    return dict(result)


def _health_message(chat_h: dict, caps: dict) -> str:
    if chat_h.get("missing"):
        return ("AI provider is not configured. Missing: " + ", ".join(chat_h["missing"]) +
                ". Set OPENAI_API_KEY + NEXUS_AI_MODEL, or configure Admin > AI Providers.")
    if chat_h.get("error"):
        return "AI provider check failed: " + str(chat_h["error"].get("message", "unknown error"))
    if chat_h.get("reachable"):
        return ("Online AI is connected (" + str(chat_h.get("provider")) + " / " +
                str(chat_h.get("model")) + "). Streaming: " +
                ("yes" if caps.get("streaming") else "no") + ".")
    return "AI provider reachability has not been verified."


SETUP_INSTRUCTIONS = {
    "gemini": [
        "Create a Gemini API key at https://aistudio.google.com/apikey.",
        "Open AI & API Keys, choose Google Gemini, paste the key, then Save & Connect.",
        "Default endpoint: https://generativelanguage.googleapis.com/v1beta/openai.",
        "Choose a model available to your Google project. Free-tier access has model/account limits.",
        "For environment setup: NEXUS_AI_PROVIDER=gemini, GEMINI_API_KEY and NEXUS_AI_MODEL.",
        "Gemini text chat is independent of image generation and live web search.",
    ],
    "openai_compatible": [
        "Set OPENAI_API_KEY (or NEXUS_AI_API_KEY) in the server environment.",
        "Optionally set OPENAI_BASE_URL / NEXUS_AI_BASE_URL for a compatible gateway.",
        "Set NEXUS_AI_MODEL to a model the endpoint actually serves (e.g. gpt-4o-mini).",
        "Alternatively paste the key into Admin > AI Providers (stored encrypted, write-only).",
        "Restart the server, then use Admin > AI Providers > Test connection.",
    ],
    "ollama": [
        "Install and start Ollama on the server host.",
        "Run: ollama pull <model> (e.g. ollama pull llama3.2).",
        "Set NEXUS_AI_PROVIDER=ollama and NEXUS_AI_MODEL=<model>.",
        "Set OLLAMA_BASE_URL if Ollama is not on http://127.0.0.1:11434.",
    ],
    "image": [
        "Set NEXUS_IMAGE_PROVIDER=openai_compatible and NEXUS_IMAGE_MODEL (e.g. gpt-image-1).",
        "Set NEXUS_IMAGE_API_KEY (falls back to OPENAI_API_KEY) and NEXUS_IMAGE_BASE_URL.",
        "Or configure the Image tab in Admin > AI Providers.",
    ],
    "web_search": [
        "Set NEXUS_SEARCH_PROVIDER=tavily (or searxng) and NEXUS_SEARCH_API_KEY.",
        "Without it, research uses only NEXUS's curated real documentation corpus.",
    ],
}


def public_view(conn) -> dict:
    """Safe for the browser: no secrets, masked hints only."""
    cfg = load(conn)
    out: dict[str, Any] = {"chat": {}, "image": {}, "web_search": {}, "policy": cfg["policy"],
                           "providers": list(PROVIDERS)}
    for kind in ("chat", "image", "web_search"):
        s = _decrypt(cfg[kind])
        out[kind] = {k: v for k, v in s.items() if k != "api_key"}
        out[kind]["api_key_hint"] = mask_secret(s.get("api_key", ""))
        out[kind]["api_key_set"] = bool(s.get("api_key"))
    from ..services.connections import last_check
    out['chat']['last_test'] = last_check(conn)
    return out
