from pathlib import Path

fpath = Path(__file__).parent.parent / "nexus" / "api.py"
text = fpath.read_text(encoding="utf-8")

sub_analytics_route = '''
@route("GET", r"/api/admin/subscriptions-analytics")
def admin_subscriptions_analytics(ctx, m):
    require_admin(ctx)
    c = ctx.conn
    now = time.time()
    
    total_users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
    pro_users = c.execute("SELECT COUNT(*) n FROM users WHERE role='pro'").fetchone()["n"]
    free_users = c.execute("SELECT COUNT(*) n FROM users WHERE role='free'").fetchone()["n"]
    admin_users = c.execute("SELECT COUNT(*) n FROM users WHERE role='admin'").fetchone()["n"]
    
    active_subs = c.execute("SELECT COUNT(*) n FROM subscriptions WHERE plan='pro' AND status IN ('active','trialing') AND (expires_at IS NULL OR expires_at > ?)", (now,)).fetchone()["n"]
    expired_subs = c.execute("SELECT COUNT(*) n FROM subscriptions WHERE plan='pro' AND (status='expired' OR (expires_at IS NOT NULL AND expires_at <= ?))", (now,)).fetchone()["n"]
    cancelled_subs = c.execute("SELECT COUNT(*) n FROM subscriptions WHERE status IN ('cancelled','canceled')", ()).fetchone()["n"]

    # Subscriber breakdown by provider
    providers_rows = c.execute("SELECT provider, COUNT(*) n FROM subscriptions GROUP BY provider").fetchall()
    by_provider = {r["provider"] or "manual": r["n"] for r in providers_rows}

    # Revenue estimation (INR ₹ and USD $)
    # Active pro subscriptions: default ₹249/mo or $3/mo
    rev_inr = active_subs * 249
    rev_usd = active_subs * 3

    # Recent subscriber records
    subscribers = [dict(r) for r in c.execute(
        "SELECT s.id, s.user_id, u.email, u.name, s.plan, s.status, s.provider, s.started_at, s.expires_at "
        "FROM subscriptions s JOIN users u ON u.id=s.user_id "
        "ORDER BY s.updated_at DESC LIMIT 50"
    ).fetchall()]

    return response({
        "total_users": total_users,
        "free_users": free_users,
        "pro_users": pro_users,
        "admin_users": admin_users,
        "active_subscriptions": active_subs,
        "expired_subscriptions": expired_subs,
        "cancelled_subscriptions": cancelled_subs,
        "revenue": {
            "inr": rev_inr,
            "usd": rev_usd,
            "currency_symbols": {"inr": "₹", "usd": "$"}
        },
        "by_provider": by_provider,
        "subscribers": subscribers
    })
'''

anchor = '@route("POST", r"/api/admin/ai-test")'
if anchor in text and "/api/admin/subscriptions-analytics" not in text:
    text = text.replace(anchor, sub_analytics_route + "\n\n" + anchor, 1)
    fpath.write_text(text, encoding="utf-8")
    print("SUCCESS: Added subscriptions-analytics endpoint to api.py")
else:
    print("Already added or anchor not found")
