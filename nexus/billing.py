"""Subscription & payment layer.

Stripe is used ONLY when all required credentials are configured.  Paid
access is granted exclusively by a signature-verified webhook or a documented
admin/CLI action - never by a browser success redirect.  No secrets are
returned by the API or written to logs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config, db
from .errors import ApiError
from .security import json_dumps, safe_equal


def payments_config(conn) -> dict:
    platform = db.get_setting(conn, "platform", {})
    pay = platform.get("payments", {})
    provider = pay.get("provider", "none")
    secret = config.STRIPE_SECRET_KEY
    webhook = config.STRIPE_WEBHOOK_SECRET
    price = config.STRIPE_PRICE_ID

    stripe_configured = bool(secret and webhook and price)
    razorpay_configured = bool(config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET)

    if provider == "stripe" and not stripe_configured:
        provider = "incomplete"
    elif provider == "razorpay" and not razorpay_configured:
        provider = "incomplete"
    elif razorpay_configured and not stripe_configured:
        provider = "razorpay"
    elif stripe_configured:
        provider = "stripe"

    configured = stripe_configured or razorpay_configured
    return {
        "provider": provider,
        "configured": configured,
        "stripe_configured": stripe_configured,
        "razorpay_configured": razorpay_configured,
        "razorpay_key_id": config.RAZORPAY_KEY_ID,
        "plan_name": pay.get("plan_name", "NEXUS Pro"),
        "amount": pay.get("amount", 3.0),
        "currency": pay.get("currency", "USD"),
        "amount_inr": pay.get("amount_inr", 299.0),
        "currency_inr": "INR",
        "interval": pay.get("interval", "month"),
        "trial_days": pay.get("trial_days", 0),
        "publishable_key": config.STRIPE_PUBLISHABLE_KEY,
        "manual_activation_enabled": bool(pay.get("manual_activation_enabled", True)),
        "missing": [n for n, v in (("STRIPE_SECRET_KEY", secret), ("STRIPE_WEBHOOK_SECRET", webhook),
                                   ("STRIPE_PRICE_ID", price)) if not v],
        "missing_razorpay": [n for n, v in (("RAZORPAY_KEY_ID", config.RAZORPAY_KEY_ID),
                                            ("RAZORPAY_KEY_SECRET", config.RAZORPAY_KEY_SECRET)) if not v],
        "message": ("Payment checkout is configured and verified by secure signatures."
                    if configured else
                    "Payments are NOT configured. An administrator can activate Pro "
                    "manually after an offline/confirmed payment using scripts/manage.py entitle."),
        "setup_instructions": [
            "For India & UPI direct bank settlement: Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.",
            "For International cards: Set STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID and STRIPE_PUBLISHABLE_KEY.",
            "Funds are settled directly to your registered bank account automatically.",
        ],
    }


def create_checkout(conn, ent: dict, base_url: str) -> dict:
    pc = payments_config(conn)
    if not pc["configured"]:
        raise ApiError(409, pc["message"], "payments_not_configured",
                       {"setup_instructions": pc["setup_instructions"],
                        "manual_activation": pc["manual_activation_enabled"]})
    user = conn.execute("SELECT email FROM users WHERE id=?", (ent["user_id"],)).fetchone()
    form = {
        "mode": "subscription",
        "success_url": base_url.rstrip("/") + "/#/subscription?checkout=success",
        "cancel_url": base_url.rstrip("/") + "/#/upgrade?checkout=cancelled",
        "client_reference_id": str(ent["user_id"]),
        "customer_email": user["email"] if user else "",
        "line_items[0][price]": config.STRIPE_PRICE_ID,
        "line_items[0][quantity]": "1",
        "subscription_data[metadata][nexus_user_id]": str(ent["user_id"]),
    }
    if pc["trial_days"]:
        form["subscription_data[trial_period_days]"] = str(pc["trial_days"])
    req = urllib.request.Request(
        config.STRIPE_API_BASE + "/checkout/sessions",
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={"Authorization": "Bearer " + config.STRIPE_SECRET_KEY,
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            session = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Stripe error bodies can contain request details; log only the status.
        raise ApiError(502, f"Payment provider rejected the checkout request (HTTP {exc.code}).",
                       "payment_provider_error") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(502, "Payment provider is unreachable. No payment was processed.",
                       "payment_provider_error") from exc
    db.audit(conn, ent["user_id"], "billing.checkout_created", session.get("id", ""),
             {"plan": pc["plan_name"]})
    return {"checkout_url": session.get("url"), "session_id": session.get("id"),
            "message": "Complete payment on the provider's hosted page. Access is granted only after a verified webhook."}


def create_razorpay_order(conn, ent: dict, amount_inr: float = 299.0) -> dict:
    """Create a verified Razorpay order for direct UPI/Card/Netbanking settlement."""
    if not (config.RAZORPAY_KEY_ID and config.RAZORPAY_KEY_SECRET):
        raise ApiError(409, "Razorpay is not configured on this server.", "razorpay_not_configured")
    user = conn.execute("SELECT email, name FROM users WHERE id=?", (ent["user_id"],)).fetchone()
    amount_paise = int(amount_inr * 100)
    receipt = f"nexus_{ent['user_id']}_{int(time.time())}"
    payload = json_dumps({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt,
        "notes": {"nexus_user_id": str(ent["user_id"]), "email": user["email"] if user else ""}
    }).encode("utf-8")
    import base64
    auth_header = "Basic " + base64.b64encode(f"{config.RAZORPAY_KEY_ID}:{config.RAZORPAY_KEY_SECRET}".encode("utf-8")).decode("utf-8")
    req = urllib.request.Request(
        config.RAZORPAY_API_BASE + "/orders",
        data=payload,
        headers={"Authorization": auth_header, "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            order = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ApiError(502, f"Razorpay rejected order creation (HTTP {exc.code}).", "payment_provider_error") from exc
    except Exception as exc:
        raise ApiError(502, "Razorpay provider is unreachable.", "payment_provider_error") from exc
    db.audit(conn, ent["user_id"], "billing.razorpay_order_created", order.get("id", ""), {"amount_inr": amount_inr})
    return {
        "order_id": order.get("id"),
        "amount": amount_paise,
        "currency": "INR",
        "key_id": config.RAZORPAY_KEY_ID,
        "user_email": user["email"] if user else "",
        "user_name": user["name"] if user else "",
        "plan_name": "NEXUS Pro (30 Days)"
    }


def verify_razorpay_payment(conn, ent: dict, order_id: str, payment_id: str, signature: str) -> dict:
    """Verify Razorpay payment signature and grant Pro access immediately."""
    if not config.RAZORPAY_KEY_SECRET:
        raise ApiError(409, "Razorpay secret key is not configured.", "razorpay_not_configured")
    if not (order_id and payment_id and signature):
        raise ApiError(400, "Missing order_id, payment_id, or signature.", "invalid_arguments")
    expected = hmac.new(
        config.RAZORPAY_KEY_SECRET.encode("utf-8"),
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    if not safe_equal(expected, signature):
        db.audit(conn, ent["user_id"], "billing.razorpay_verification_failed", order_id, {"payment_id": payment_id})
        raise ApiError(400, "Razorpay payment signature verification failed.", "invalid_signature")
    res = grant_pro(conn, ent["user_id"], days=30, provider="razorpay", customer_id="", subscription_id=payment_id)
    db.audit(conn, ent["user_id"], "billing.razorpay_payment_verified", order_id, {"payment_id": payment_id})
    return {"verified": True, "result": res}


def verify_razorpay_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify X-Razorpay-Signature header against the webhook payload."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return safe_equal(expected, signature)


def apply_razorpay_webhook_event(conn, event: dict) -> dict:
    """Map a verified Razorpay event to entitlement grant/revoke."""
    etype = event.get("event", "")
    payload_data = (event.get("payload") or {}).get("payment", {}).get("entity", {}) or \
                   (event.get("payload") or {}).get("order", {}).get("entity", {}) or \
                   (event.get("payload") or {}).get("subscription", {}).get("entity", {})
    notes = payload_data.get("notes") or {}
    uid_str = notes.get("nexus_user_id")
    uid = None
    if uid_str and str(uid_str).isdigit():
        uid = int(uid_str)
    handled = {"event": etype, "changed": False, "user_id": uid}
    if etype in ("payment.captured", "order.paid", "subscription.charged", "subscription.activated"):
        if uid:
            grant_pro(conn, uid, days=30, provider="razorpay", subscription_id=payload_data.get("id", ""))
            handled["changed"] = True
    elif etype in ("subscription.cancelled", "subscription.halted"):
        if uid:
            revoke_pro(conn, uid, status="cancelled")
            handled["changed"] = True
    db.audit(conn, None, "billing.razorpay_webhook", etype, {"user_id": uid, "changed": handled["changed"]})
    return handled


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str, tolerance: int = 300) -> bool:
    """Stripe-Signature: t=<unix>,v1=<hex hmac of '{t}.{payload}'>."""
    if not sig_header or not secret:
        return False
    parts = {}
    for chunk in sig_header.split(","):
        if "=" in chunk:
            k, v = chunk.strip().split("=", 1)
            parts.setdefault(k, []).append(v)
    ts = (parts.get("t") or [""])[0]
    if not ts.isdigit():
        return False
    if abs(time.time() - int(ts)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), (ts + ".").encode() + payload, hashlib.sha256).hexdigest()
    return any(safe_equal(expected, sig) for sig in parts.get("v1", []))


def grant_pro(conn, user_id: int, days: int | None = 30, *, provider: str = "manual",
              customer_id: str = "", subscription_id: str = "", status: str = "active",
              actor_id: int | None = None) -> dict:
    now = time.time()
    row = conn.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
                       (user_id,)).fetchone()
    expires = now + days * 86400 if days else None
    if row:
        conn.execute(
            "UPDATE subscriptions SET plan='pro', status=?, provider=?, provider_customer_id=?, "
            "provider_subscription_id=?, started_at=?, expires_at=?, cancelled_at=NULL, updated_at=? WHERE id=?",
            (status, provider, customer_id or row["provider_customer_id"],
             subscription_id or row["provider_subscription_id"], row["started_at"] or now,
             expires, now, row["id"]))
    else:
        conn.execute(
            "INSERT INTO subscriptions(user_id, plan, status, provider, provider_customer_id, "
            "provider_subscription_id, started_at, expires_at, created_at, updated_at) "
            "VALUES (?, 'pro', ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, status, provider, customer_id, subscription_id, now, expires, now, now))
    db.audit(conn, actor_id or user_id, "entitlement.grant_pro", str(user_id),
             {"provider": provider, "days": days, "status": status})
    return {"user_id": user_id, "plan": "pro", "status": status, "expires_at": expires}


def revoke_pro(conn, user_id: int, status: str = "cancelled", actor_id: int | None = None) -> dict:
    now = time.time()
    conn.execute(
        "UPDATE subscriptions SET plan='free', status=?, cancelled_at=?, expires_at=?, updated_at=? WHERE user_id=?",
        (status, now, now, now, user_id))
    db.audit(conn, actor_id or user_id, "entitlement.revoke_pro", str(user_id), {"status": status})
    return {"user_id": user_id, "plan": "free", "status": status}


def apply_webhook_event(conn, event: dict) -> dict:
    """Map a verified provider event to an entitlement change."""
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    handled = {"event": etype, "changed": False, "user_id": None}

    def find_user():
        uid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("nexus_user_id")
        if uid and str(uid).isdigit():
            exists = conn.execute("SELECT id FROM users WHERE id=?", (int(uid),)).fetchone()
            return int(uid) if exists else None
        cust = obj.get("customer") or obj.get("customer_id")
        if cust:
            r = conn.execute("SELECT user_id FROM subscriptions WHERE provider_customer_id=? LIMIT 1", (cust,)).fetchone()
            if r:
                return r["user_id"]
        return None

    uid = find_user()
    handled["user_id"] = uid
    if etype == "checkout.session.completed":
        # Only a *paid* session grants access; a success page redirect never does.
        if uid and obj.get("payment_status") in ("paid", "no_payment_required"):
            pc = payments_config(conn)
            grant_pro(conn, uid, 30 if pc["interval"] == "month" else 365,
                      provider="stripe", customer_id=obj.get("customer") or "",
                      subscription_id=obj.get("subscription") or "")
            handled["changed"] = True
        else:
            handled["reason"] = "payment_status not paid or no matching user"
    elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
        if uid:
            st = obj.get("status", "")
            if st in ("active", "trialing"):
                period_end = obj.get("current_period_end")
                days = max(1, int((period_end - time.time()) / 86400)) if period_end else 30
                grant_pro(conn, uid, days, provider="stripe",
                          customer_id=obj.get("customer") or "",
                          subscription_id=obj.get("id") or "", status=st)
                handled["changed"] = True
            elif st in ("canceled", "cancelled", "unpaid", "incomplete_expired"):
                revoke_pro(conn, uid, status="cancelled")
                handled["changed"] = True
    elif etype == "invoice.payment_failed":
        if uid:
            conn.execute(
                "UPDATE subscriptions SET status='past_due', updated_at=? WHERE user_id=?",
                (time.time(), uid))
            db.audit(conn, None, "billing.payment_failed", str(uid), {"provider": "stripe"})
            handled["changed"] = True
            handled["reason"] = "past_due grace policy applied"
    db.audit(conn, None, "billing.webhook", etype, {"user_id": uid, "changed": handled["changed"]})
    return handled
