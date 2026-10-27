"""Single source of truth for access control.

The browser never supplies role/plan/status.  Everything is derived from the
users + subscriptions tables on every request.  Premium endpoints call
``require_feature`` and project queries call ``project_visible_to``.
"""
from __future__ import annotations

import time
from typing import Any

from . import db
from .errors import ApiError

# ---------------------------------------------------------------------------
# Permission matrix (also rendered in the UI and documented in README.md)
# ---------------------------------------------------------------------------
FEATURES: dict[str, dict[str, str]] = {
    # Free tier
    "general_ai": {"tier": "free", "group": "AI", "label": "General AI assistance (limited)"},
    "library.free": {"tier": "free", "group": "Library", "label": "The 15 designated free projects"},
    "learning.basic": {"tier": "free", "group": "Learning", "label": "Beginner learning resources"},
    "workspace.basic": {"tier": "free", "group": "Workspace", "label": "Own saved projects (limited)"},
    "account.manage": {"tier": "free", "group": "Account", "label": "Profile, password, subscription status"},
    "upgrade.view": {"tier": "free", "group": "Billing", "label": "Upgrade / pricing page"},
    # Pro tier
    "library.all": {"tier": "pro", "group": "Library", "label": "Full 100+ project library + downloads"},
    "ai.advanced": {"tier": "pro", "group": "AI", "label": "Advanced AI engineering assistance"},
    "tools.project_generator": {"tier": "pro", "group": "Tools", "label": "AI IoT Project Generator"},
    "tools.circuit_designer": {"tier": "pro", "group": "Tools", "label": "AI Circuit Designer & Validator"},
    "tools.code_engineer": {"tier": "pro", "group": "Tools", "label": "AI Code Engineer"},
    "tools.debugging": {"tier": "pro", "group": "Tools", "label": "AI Debugging Center"},
    "tools.innovation": {"tier": "pro", "group": "Tools", "label": "AI Innovation Discovery"},
    "tools.comparison": {"tier": "pro", "group": "Tools", "label": "Project Comparison & Gap Analysis"},
    "tools.startup_lab": {"tier": "pro", "group": "Tools", "label": "Startup & Product Idea Lab"},
    "tools.research": {"tier": "pro", "group": "Tools", "label": "Advanced Research Assistant"},
    "tools.device_monitoring": {"tier": "pro", "group": "Tools", "label": "Device Monitoring & Diagnostics"},
    "tools.project_docs": {"tier": "pro", "group": "Tools", "label": "Project Management & Documentation"},
    "workspace.full": {"tier": "pro", "group": "Workspace", "label": "Unlimited workspaces, milestones, version history"},
    "exports": {"tier": "pro", "group": "Workspace", "label": "Code / schematic / report exports"},
    "tools.invention": {"tier":"pro","group":"Tools","label":"AI Invention Lab"},
    "tools.images": {"tier":"pro","group":"Tools","label":"AI Image Generation Studio"},
    # Admin tier
    "admin.dashboard": {"tier": "admin", "group": "Admin", "label": "Administrative workspace"},
    "admin.projects": {"tier": "admin", "group": "Admin", "label": "Create/edit/publish/delete any project"},
    "admin.free_designation": {"tier": "admin", "group": "Admin", "label": "Manage the 15 free projects"},
    "admin.users": {"tier": "admin", "group": "Admin", "label": "Manage users, roles and entitlements"},
    "admin.config": {"tier": "admin", "group": "Admin", "label": "AI providers, limits, integrations, plans"},
    "admin.audit": {"tier": "admin", "group": "Admin", "label": "Audit logs, errors, system health"},
    "admin.analytics": {"tier": "admin", "group": "Admin", "label": "Platform analytics"},
}

TIER_ORDER = {"free": 0, "pro": 1, "admin": 2}
ACTIVE_SUBSCRIPTION_STATES = {"active", "trialing"}


def resolve(conn, user_row) -> dict[str, Any]:
    """Compute the effective entitlement for an authenticated user row."""
    now = time.time()
    role = user_row["role"] or "free"
    sub = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id=? ORDER BY updated_at DESC, id DESC LIMIT 1",
        (user_row["id"],),
    ).fetchone()

    plan = "free"
    sub_status = "inactive"
    expires_at = None
    provider = "manual"
    if sub:
        sub_status = sub["status"]
        provider = sub["provider"]
        expires_at = sub["expires_at"]
        expired = expires_at is not None and expires_at <= now
        paid_active = sub_status in ACTIVE_SUBSCRIPTION_STATES and not expired
        if sub_status == "past_due":
            # Grace policy: past_due keeps access for 3 days, then falls back.
            paid_active = (expires_at is not None and expires_at + 3 * 86400 > now)
        if paid_active and sub["plan"] == "pro":
            plan = "pro"
        elif expired and sub_status in ACTIVE_SUBSCRIPTION_STATES:
            sub_status = "expired"

    if role == "admin":
        tier = "admin"
        plan = "admin"
    elif plan == "pro":
        tier = "pro"
    else:
        tier = "free"

    settings = db.get_setting(conn, "limits", {})
    limits = dict(settings.get(tier, {}))
    policy = db.get_setting(conn, "public_free_feature_policy", {}) or {}
    allowed = set(policy.get("allowed_pro_tools", []) or [])

    features = []
    for name, meta in FEATURES.items():
        if TIER_ORDER[meta["tier"]] <= TIER_ORDER[tier]:
            features.append(name)
        elif tier == "free" and name in allowed and meta["group"] == "Tools":
            features.append(name)

    return {
        "user_id": user_row["id"],
        "email": user_row["email"],
        "name": user_row["name"],
        "role": role,
        "tier": tier,
        "plan": plan if plan != "admin" else "admin",
        "subscription_status": sub_status,
        "subscription_provider": provider,
        "subscription_started_at": sub["started_at"] if sub else None,
        "subscription_expires_at": expires_at,
        "limits": limits,
        "features": features,
        "is_pro": tier in ("pro", "admin"),
        "is_admin": tier == "admin",
        "granted_by_policy": sorted(allowed & set(FEATURES)),
    }


def has_feature(ent: dict, feature: str) -> bool:
    if feature not in FEATURES:
        raise ApiError(500, "Unknown feature flag", "config_error")
    return feature in ent["features"]


def require_feature(ent: dict, feature: str) -> None:
    if not has_feature(ent, feature):
        needed = FEATURES[feature]["tier"]
        raise ApiError(
            403,
            "This capability requires a NEXUS Pro subscription."
            if needed == "pro" else "Administrator access is required.",
            "upgrade_required" if needed == "pro" else "forbidden",
            {"feature": feature, "required_tier": needed, "upgrade_url": "/#/upgrade"},
        )


def require_admin(ent: dict) -> None:
    if not ent["is_admin"]:
        raise ApiError(403, "Administrator access is required.", "forbidden")


def project_visible_to(ent: dict, project_row) -> bool:
    """Server-side visibility gate applied to every project query."""
    if ent["is_admin"]:
        return True
    if project_row["status"] != "published":
        return False
    return bool(project_row["is_free"]) or ent["is_pro"]


def library_predicate(ent: dict) -> tuple[str, list]:
    """SQL fragment that enforces visibility inside the query itself."""
    if ent["is_admin"]:
        return "1=1", []
    if ent["is_pro"]:
        return "status='published'", []
    return "status='published' AND is_free=1", []


def usage_snapshot(conn, ent: dict) -> dict:
    now = time.time()
    kinds = {
        "ai_requests_per_day": ("ai_request", 86400),
        "tool_calls_per_day": ("tool_call", 86400),
        "images_per_day": ("image_generation", 86400),
        "projects_created_total": ("project_created", 0),
        "workspace_items": ("workspace_item", 0),
    }
    out = {}
    for limit_key, (kind, window) in kinds.items():
        limit = ent["limits"].get(limit_key, 10 if kind == "image_generation" and ent["is_pro"] else 0 if kind == "image_generation" else -1)
        if limit_key == "workspace_items":
            # Live count of owned rows is the authoritative usage figure.
            used = conn.execute("SELECT COUNT(*) n FROM workspaces WHERE user_id=?",
                                (ent["user_id"],)).fetchone()["n"]
        else:
            used = (db.count_usage_all(conn, ent["user_id"], kind) if window == 0
                    else db.count_usage(conn, ent["user_id"], kind, window))
        out[limit_key] = {"used": used, "limit": limit, "unlimited": limit == -1}
    return out


def consume(conn, ent: dict, kind: str, cost: int = 1, meta: dict | None = None) -> None:
    """Atomic count+reservation; quotas are enforced before external work."""
    limit_key = {"ai_request":"ai_requests_per_day", "tool_call":"tool_calls_per_day",
                 "image_generation":"images_per_day", "project_created":"projects_created_total",
                 "workspace_item":"workspace_items"}.get(kind)
    default = (10 if ent["is_pro"] else 0) if kind == "image_generation" else -1
    limit = ent["limits"].get(limit_key, default)
    own = not conn.in_transaction
    if own: conn.execute("BEGIN IMMEDIATE")
    try:
        used = (db.count_usage_all(conn, ent["user_id"], kind) if limit_key and (limit_key.endswith("total") or kind=="workspace_item")
                else db.count_usage(conn, ent["user_id"], kind, 86400))
        if limit != -1 and used + cost > limit:
            raise ApiError(429, "Usage limit reached for your plan. Check Account & Subscription.", "limit_reached",
                           {"limit_key":limit_key,"used":used,"limit":limit,"upgrade_url":"/#/upgrade" if ent["tier"]=="free" else None})
        db.record_usage(conn, ent["user_id"], kind, cost, meta)
        if own: conn.execute("COMMIT")
    except Exception:
        if own: conn.execute("ROLLBACK")
        raise
