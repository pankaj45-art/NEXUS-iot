"""Patch api.py to include Razorpay billing routes."""
from pathlib import Path

api_path = Path("nexus/api.py")
content = api_path.read_text(encoding="utf-8")

target = """@route("POST", r"/api/billing/webhook")
def billing_webhook(ctx, m):
    pay = billing.payments_config(ctx.conn)
    sig = ctx.headers.get("Stripe-Signature", "")
    if not pay["configured"] or not billing.verify_webhook_signature(ctx.raw_body, sig, config.STRIPE_WEBHOOK_SECRET):
        db.audit(ctx.conn, None, "billing.webhook_rejected", "", {"ip": ctx.ip}, ip=ctx.ip)
        raise ApiError(400, "Invalid webhook signature.", "invalid_signature")
    try:
        event = json.loads(ctx.raw_body.decode("utf-8"))
    except ValueError as exc:
        raise ApiError(400, "Invalid webhook payload.", "invalid_json") from exc
    handled = billing.apply_webhook_event(ctx.conn, event)
    return response({"received": True, **handled})"""

addition = """@route("POST", r"/api/billing/webhook")
def billing_webhook(ctx, m):
    pay = billing.payments_config(ctx.conn)
    sig = ctx.headers.get("Stripe-Signature", "")
    if not pay["configured"] or not billing.verify_webhook_signature(ctx.raw_body, sig, config.STRIPE_WEBHOOK_SECRET):
        db.audit(ctx.conn, None, "billing.webhook_rejected", "", {"ip": ctx.ip}, ip=ctx.ip)
        raise ApiError(400, "Invalid webhook signature.", "invalid_signature")
    try:
        event = json.loads(ctx.raw_body.decode("utf-8"))
    except ValueError as exc:
        raise ApiError(400, "Invalid webhook payload.", "invalid_json") from exc
    handled = billing.apply_webhook_event(ctx.conn, event)
    return response({"received": True, **handled})


@route("POST", r"/api/billing/razorpay/order")
def billing_razorpay_order(ctx, m):
    ent = require_auth(ctx)
    if ent["is_pro"]:
        raise ApiError(400, "You already have Pro access.", "already_pro")
    pay = billing.payments_config(ctx.conn)
    amount_inr = float(pay.get("amount_inr", 299.0))
    return response(billing.create_razorpay_order(ctx.conn, ent, amount_inr), 200)


@route("POST", r"/api/billing/razorpay/verify")
def billing_razorpay_verify(ctx, m):
    ent = require_auth(ctx)
    data = ctx.json()
    order_id = str(data.get("order_id") or "").strip()
    payment_id = str(data.get("payment_id") or "").strip()
    sig = str(data.get("signature") or "").strip()
    return response(billing.verify_razorpay_payment(ctx.conn, ent, order_id, payment_id, sig), 200)


@route("POST", r"/api/billing/razorpay/webhook")
def billing_razorpay_webhook(ctx, m):
    sig = ctx.headers.get("X-Razorpay-Signature", "")
    if not billing.verify_razorpay_webhook_signature(ctx.raw_body, sig, config.RAZORPAY_WEBHOOK_SECRET):
        db.audit(ctx.conn, None, "billing.razorpay_webhook_rejected", "", {"ip": ctx.ip}, ip=ctx.ip)
        raise ApiError(400, "Invalid Razorpay webhook signature.", "invalid_signature")
    try:
        event = json.loads(ctx.raw_body.decode("utf-8"))
    except ValueError as exc:
        raise ApiError(400, "Invalid webhook payload.", "invalid_json") from exc
    handled = billing.apply_razorpay_webhook_event(ctx.conn, event)
    return response({"received": True, **handled})"""

# Normalize
content_norm = content.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
addition_norm = addition.replace("\r\n", "\n")

if target_norm in content_norm:
    new_content_norm = content_norm.replace(target_norm, addition_norm, 1)
    if "\r\n" in content:
        new_content = new_content_norm.replace("\n", "\r\n")
    else:
        new_content = new_content_norm
    api_path.write_text(new_content, encoding="utf-8")
    print("SUCCESS: Patched nexus/api.py with Razorpay routes")
else:
    print("ERROR: Target not found in nexus/api.py")
