"""AI compatibility layer. Chat failures are errors, never generic fallback answers.

Legacy engineering tools retain explicitly labelled deterministic workflows.
Optional online enrichment is separate and its failures are exposed as failed
provider calls, not as successful model output.
"""
from __future__ import annotations
import re
from . import hardware
from .providers import registry
from .providers.base import ChatMessage, ProviderError


def get_ai_config(conn):
    return registry.chat_config(conn)


def ai_status(conn):
    from .services.connections import last_check
    cfg = get_ai_config(conn)
    p = registry.chat_provider(conn)
    return {"provider": p.name, "model": p.model, "base_url": p.base_url,
            "api_key_hint": cfg.get("api_key_hint", ""),
            "env_key_present": cfg.get("env_key_present", False),
            "enabled": p.configured(), "configured": p.configured() and not p.missing(),
            "reachable": None, "last_test": last_check(conn), "capabilities": registry.capability_map(conn),
            "message": ("Provider configured; use Test connection to verify reachability. No silent chat fallback."
                        if p.configured() and not p.missing() else
                        "Online AI is not configured. Add a provider/model/API key in Admin > AI Providers. "
                        "Catalog lookup, circuit rules and static checks remain available as explicit basic functions.")}


def llm_complete(cfg, system, prompt, max_tokens=900):
    cls = registry.PROVIDERS.get(cfg.get("provider"))
    if not cls:
        raise ProviderError("provider_not_configured", "No online provider configured.")
    p = cls(cfg)
    r = p.chat([ChatMessage("user", prompt[:20000])], system=system, max_tokens=max_tokens)
    return r.text, r.provider


def enrich(conn, result, system, prompt):
    cfg = get_ai_config(conn)
    result.update(mode="offline", ai_provider=cfg["provider"], model="NEXUS deterministic engineering tools")
    result["ai_note"] = "Deterministic catalog/rule-based output; no live model response is implied."
    if registry.chat_provider(conn).configured() and not registry.chat_provider(conn).missing():
        try:
            text, mode = llm_complete(cfg, system, prompt)
            result.update(llm_narrative=text, mode=mode, model=cfg["model"])
        except ProviderError as exc:
            result["provider_error"] = exc.payload()
            result["ai_warning"] = "Online enrichment failed. Only the explicitly labelled deterministic calculation is shown. " + exc.message
    return result


def references_for(query: str, limit: int = 6):
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    scored = [(sum(2 for w in words if w in (r["title"] + ' ' + ' '.join(r["topics"])).lower()), r)
              for r in hardware.REFERENCES]
    scored.sort(key=lambda x: -x[0])
    return [dict(r) for score, r in scored[:limit] if score > 0]


def split_facts_hypotheses(facts, hypotheses):
    return {"facts": [{"statement": f, "basis": "Component catalog / documentation / supplied input"} for f in facts],
            "hypotheses": [{"statement": h, "status": "unverified - requires bench or market validation"} for h in hypotheses],
            "disclaimer": "Verify evidence using the linked documentation. Hypotheses are unverified."}
