"""Patch web/app.js to support Razorpay UPI/Cards alongside Stripe."""
from pathlib import Path

app_path = Path("web/app.js")
content = app_path.read_text(encoding="utf-8")

old_view = """async function viewUpgrade() {
  const d = await api('/api/upgrade');
  const c = state.config;
  $('#view').innerHTML = pageHead(d.headline, 'Transparent pricing, honest payment status, and no fake checkout flows.') +
    `<div class="grid g2 mb"><div class="card"><h3>Free</h3><div class="score">$0</div><p class="tiny muted">forever</p>
      <ul>${d.comparison.map(x => `<li>${esc(x.capability)}: <b>${esc(x.free)}</b></li>`).join('')}</ul>
      ${state.me.entitlement.is_pro ? badge('You have Pro', 'green') : '<span class="badge">Current plan</span>'}</div>
      <div class="card" style="border-color:var(--violet)"><div class="row between"><h3>${esc(d.plan.name)}</h3>${badge('PRO', 'violet')}</div>
      <div class="score">${esc(d.plan.currency)} ${esc(d.plan.price)}</div><p class="tiny muted">per ${esc(d.plan.interval)}${d.plan.trial_days ? ' · ' + d.plan.trial_days + '-day trial' : ''}</p>
      <ul>${d.included.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      ${d.payments.configured ? (state.me.entitlement.is_pro ? badge('Active', 'green') : '<button class="btn primary" id="checkout">Continue to secure checkout</button>') : `<div class="notice warn">${esc(d.payments.message)}</div>`}
      </div></div>
    ${!d.payments.configured ? `<div class="card mb"><h3>Payment setup instructions</h3><p class="tiny muted">Missing environment variables: ${esc((d.payments.missing || []).join(', ') || 'none')}</p><ol>${d.payments.setup_instructions.map(x => `<li>${esc(x)}</li>`).join('')}</ol><p class="tiny dim">No payment is processed until this is configured. Manual activation after a confirmed offline payment is available to administrators.</p></div>` : ''}
    <div class="card"><h3>Comparison</h3>${table(d.comparison, [['capability', 'Capability'], ['free', 'Free'], ['pro', 'Pro']])}</div>
    <div class="section-title">FAQ</div><div class="grid g3">${d.faq.map(f => `<div class="card soft"><b>${esc(f.q)}</b><p class="tiny muted mt-s">${esc(f.a)}</p></div>`).join('')}</div>
    <p class="tiny dim mt">Questions? ${esc(d.support_email || '')}</p>`;
  $('#checkout')?.addEventListener('click', async () => {
    try { const r = await api('/api/billing/checkout', { method: 'POST', body: {} }); location.href = r.checkout_url; }
    catch (e) { toast(e, 'err'); }
  });
  if (new URLSearchParams(location.hash.split('?')[1] || '').get('checkout') === 'success') {
    setTimeout(() => toast('If payment completed, access is granted only after the verified webhook arrives.', ''), 400);
  }
}"""

new_view = """async function viewUpgrade() {
  const d = await api('/api/upgrade');
  const c = state.config;
  const isPro = state.me.entitlement?.is_pro;
  const pay = d.payments || {};

  let buttonsHtml = '';
  if (isPro) {
    buttonsHtml = badge('Active Pro Subscription', 'green');
  } else if (pay.configured) {
    buttonsHtml = '<div style=\"display:flex;flex-direction:column;gap:0.6rem;margin-top:1rem\">';
    if (pay.razorpay_configured) {
      buttonsHtml += `<button class=\"btn primary\" id=\"checkout-razorpay\" style=\"background:linear-gradient(135deg,#0284c7,#2563eb);border:none;padding:0.75rem 1.25rem;font-weight:700\">⚡ Pay with UPI / Cards (₹${pay.amount_inr || 299} / mo)</button>`;
    }
    if (pay.stripe_configured || (!pay.razorpay_configured && pay.configured)) {
      buttonsHtml += `<button class=\"btn ${pay.razorpay_configured ? 'soft' : 'primary'}\" id=\"checkout\" style=\"padding:0.75rem 1.25rem\">Pay with Stripe / International Card ($${d.plan.price} / mo)</button>`;
    }
    buttonsHtml += '</div>';
  } else {
    buttonsHtml = `<div class=\"notice warn\">${esc(pay.message)}</div>`;
  }

  $('#view').innerHTML = pageHead(d.headline, 'Transparent pricing, honest payment status, and no fake checkout flows.') +
    `<div class=\"grid g2 mb\"><div class=\"card\"><h3>Free</h3><div class=\"score\">$0</div><p class=\"tiny muted\">forever</p>
      <ul>${d.comparison.map(x => `<li>${esc(x.capability)}: <b>${esc(x.free)}</b></li>`).join('')}</ul>
      ${isPro ? badge('You have Pro', 'green') : '<span class=\"badge\">Current plan</span>'}</div>
      <div class=\"card\" style=\"border-color:var(--violet)\"><div class=\"row between\"><h3>${esc(d.plan.name)}</h3>${badge('PRO', 'violet')}</div>
      <div class=\"score\">${pay.razorpay_configured ? '₹' + (pay.amount_inr || 299) : esc(d.plan.currency) + ' ' + esc(d.plan.price)}</div><p class=\"tiny muted\">per ${esc(d.plan.interval)}${d.plan.trial_days ? ' · ' + d.plan.trial_days + '-day trial' : ''}</p>
      <ul>${d.included.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      ${buttonsHtml}
      </div></div>
    ${!pay.configured ? `<div class=\"card mb\"><h3>Payment setup instructions</h3><p class=\"tiny muted\">Missing environment variables: ${esc((pay.missing || []).concat(pay.missing_razorpay || []).join(', ') || 'none')}</p><ol>${(pay.setup_instructions || []).map(x => `<li>${esc(x)}</li>`).join('')}</ol><p class=\"tiny dim\">No payment is processed until this is configured. Manual activation after a confirmed offline payment is available to administrators.</p></div>` : ''}
    <div class=\"card\"><h3>Comparison</h3>${table(d.comparison, [['capability', 'Capability'], ['free', 'Free'], ['pro', 'Pro']])}</div>
    <div class=\"section-title\">FAQ</div><div class=\"grid g3\">${d.faq.map(f => `<div class=\"card soft\"><b>${esc(f.q)}</b><p class=\"tiny muted mt-s\">${esc(f.a)}</p></div>`).join('')}</div>
    <p class=\"tiny dim mt\">Questions? ${esc(d.support_email || '')}</p>`;

  $('#checkout')?.addEventListener('click', async () => {
    try { const r = await api('/api/billing/checkout', { method: 'POST', body: {} }); location.href = r.checkout_url; }
    catch (e) { toast(e, 'err'); }
  });

  $('#checkout-razorpay')?.addEventListener('click', async () => {
    try {
      const order = await api('/api/billing/razorpay/order', { method: 'POST', body: {} });
      if (!window.Razorpay) {
        await new Promise((resolve, reject) => {
          const s = document.createElement('script');
          s.src = 'https://checkout.razorpay.com/v1/checkout.js';
          s.onload = resolve;
          s.onerror = () => reject(new Error('Failed to load Razorpay checkout script.'));
          document.head.appendChild(s);
        });
      }
      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'NEXUS IoT',
        description: order.plan_name,
        order_id: order.order_id,
        prefill: { email: order.user_email, name: order.user_name },
        theme: { color: '#00d4ff' },
        handler: async (resp) => {
          try {
            await api('/api/billing/razorpay/verify', {
              method: 'POST',
              body: { order_id: resp.razorpay_order_id, payment_id: resp.razorpay_payment_id, signature: resp.razorpay_signature }
            });
            toast('Payment verified! Welcome to NEXUS Pro.', 'ok');
            setTimeout(() => { location.hash = '#/subscription'; location.reload(); }, 1200);
          } catch (err) {
            toast(err, 'err');
          }
        }
      });
      rzp.open();
    } catch (e) {
      toast(e, 'err');
    }
  });

  if (new URLSearchParams(location.hash.split('?')[1] || '').get('checkout') === 'success') {
    setTimeout(() => toast('If payment completed, access is granted only after the verified webhook arrives.', ''), 400);
  }
}"""

content_norm = content.replace("\r\n", "\n")
old_view_norm = old_view.replace("\r\n", "\n")
new_view_norm = new_view.replace("\r\n", "\n")

if old_view_norm in content_norm:
    new_content_norm = content_norm.replace(old_view_norm, new_view_norm, 1)
    if "\r\n" in content:
        app_path.write_text(new_content_norm.replace("\n", "\r\n"), encoding="utf-8")
    else:
        app_path.write_text(new_content_norm, encoding="utf-8")
    print("SUCCESS: Patched web/app.js with dual Razorpay/Stripe checkout")
else:
    print("ERROR: old_view not found in web/app.js")
