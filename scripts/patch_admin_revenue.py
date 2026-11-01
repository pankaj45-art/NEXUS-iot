from pathlib import Path

fpath = Path(__file__).parent.parent / "web" / "app.js"
text = fpath.read_text(encoding="utf-8")

# 1. Update ADMIN_TABS to include 'revenue'
old_tabs = "['overview', 'Overview'], ['projects', 'Projects'], ['free', 'The Free 15'], ['users', 'Users'],\n['config', 'AI & Config'], ['usage', 'Usage & Audit'], ['analytics', 'Analytics'], ['quality', 'Quality & Health']];"
new_tabs = "['overview', 'Overview'], ['revenue', '💰 Subscriptions & Revenue'], ['projects', 'Projects'], ['free', 'The Free 15'], ['users', 'Users'],\n['config', 'AI & Config'], ['usage', 'Usage & Audit'], ['analytics', 'Analytics'], ['quality', 'Quality & Health']];"

# 2. Add router branch in viewAdmin()
old_router = "if (tab === 'overview') el.innerHTML = await adminOverview();\n    else if (tab === 'projects') el.innerHTML = await adminProjects();"
new_router = "if (tab === 'overview') el.innerHTML = await adminOverview();\n    else if (tab === 'revenue') el.innerHTML = await adminRevenue();\n    else if (tab === 'projects') el.innerHTML = await adminProjects();"

# 3. Add adminRevenue function
revenue_fn = """
async function adminRevenue() {
  const d = await api('/api/admin/subscriptions-analytics');
  return `
    <div class="grid g4 mb">
      ${stat('₹' + Number(d.revenue.inr).toLocaleString(), 'Est. Revenue (INR)')}
      ${stat('$' + Number(d.revenue.usd).toLocaleString(), 'Est. Revenue (USD)')}
      ${stat(d.active_subscriptions, 'Active Pro Subscribers')}
      ${stat(d.total_users, 'Total Users (' + d.free_users + ' Free / ' + d.pro_users + ' Pro)')}
    </div>
    <div class="grid g2 mb">
      <div class="card">
        <h3>Payment Gateway & Methods</h3>
        <p class="tiny muted">Supported Legally Permitted Methods in India & Globally:</p>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">
          <span class="badge green">UPI (GPay / PhonePe / Paytm / BHIM)</span>
          <span class="badge green">Credit & Debit Cards (RuPay / Visa / MC)</span>
          <span class="badge green">Net Banking (50+ Indian Banks)</span>
          <span class="badge violet">Samsung Galaxy Store IAP (SDK v6.0)</span>
          <span class="badge blue">Stripe Global (Cards / Wallets)</span>
        </div>
        <h4 class="mt">RBI Subscription & Renewal Compliance</h4>
        <p class="tiny muted">Compliant with RBI e-mandate framework for recurring card & UPI transactions. Explicit customer renewal consent verified at the end of each billing period.</p>
      </div>
      <div class="card">
        <h3>Subscribers by Provider</h3>
        ${Object.entries(d.by_provider || {}).map(([p, cnt]) => `
          <div class="row between py-s" style="border-bottom:1px solid rgba(255,255,255,0.06);">
            <span class="mono">${esc(p)}</span>
            <b>${cnt} users</b>
          </div>
        `).join('')}
      </div>
    </div>
    <div class="card mb">
      <div class="row between">
        <h3>Subscriber Directory & Entitlements</h3>
        <span class="tiny muted">${(d.subscribers || []).length} recorded subscriptions</span>
      </div>
      ${table(d.subscribers || [], [
        ['email', 'User Email'],
        ['name', 'Name'],
        ['plan', 'Plan', v => badge(v.toUpperCase(), v === 'pro' ? 'violet' : '')],
        ['status', 'Payment Status', v => badge(v, v === 'active' ? 'green' : v === 'expired' ? 'rose' : 'amber')],
        ['provider', 'Provider'],
        ['expires_at', 'Expires', v => fmtDate(v)]
      ])}
    </div>
  `;
}
"""

if old_tabs in text and old_router in text:
    text = text.replace(old_tabs, new_tabs, 1)
    text = text.replace(old_router, new_router, 1)
    # Insert adminRevenue function right before adminProjects
    text = text.replace("async function adminProjects() {", revenue_fn + "\nasync function adminProjects() {", 1)
    fpath.write_text(text, encoding="utf-8")
    print("SUCCESS: app.js updated with Subscriptions & Revenue admin tab")
else:
    print("FAILED TO MATCH TARGETS IN app.js")
