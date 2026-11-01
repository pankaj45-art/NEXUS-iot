"""Optimize boot and dashboard load performance in web/app.js."""
from pathlib import Path

app_path = Path("web/app.js")
content = app_path.read_text(encoding="utf-8")

old_boot = """async function boot(full = true) {
  if (stored('nexus_transport') === 'query') state.transport = 'query';
  try {
    state.config = await api('/api/config/public');
    const me = await api('/api/auth/me');
    state.me = me.authenticated ? me : null;
    state.csrf = me.csrf || state.csrf || stored(CSRF_KEY) || cookie('nexus_csrf');
    if (me.csrf) store(CSRF_KEY, me.csrf);
    if (!me.authenticated) {
      unstore(SESSION_KEY); unstore(CSRF_KEY); unstore('nexus_transport');
      state.csrf = ''; state.transport = 'auto';
    }
  } catch (e) {
    $('#app').innerHTML = `<div class=\"boot\"><div class=\"notice danger\">Cannot reach the NEXUS API: ${esc(e.message)}</div></div>`;
    return;
  }
  if (!state.me) {
    // GUEST MODE: allow free browsing without forced login
    const hash = location.hash;
    if (hash.startsWith('#/register')) { authView('register'); return; }
    if (hash.startsWith('#/login')) { authView('login'); return; }
    // Derive free feature list from public config
    const freeFeatures = (state.config?.permission_matrix || []).filter(f => f.tier === 'free').map(f => f.feature);
    state.me = {
      authenticated: false, is_guest: true,
      user: { name: 'Guest', email: '' },
      entitlement: {
        tier: 'free', plan: 'guest', is_pro: false, is_admin: false,
        features: freeFeatures.length ? freeFeatures : ['library.browse', 'library.free_projects'],
        usage: { ai_requests_per_day: { used: 0, limit: 0, unlimited: false } }
      },
      usage: { ai_requests_per_day: { used: 0, limit: 0, unlimited: false } }
    };
  }
  if (location.hash.startsWith('#/login') || location.hash.startsWith('#/register')) replaceHash('#/dashboard');
  try { const prefs = await api('/api/settings').catch(() => ({})); document.documentElement.dataset.theme = prefs.settings?.theme || 'dark'; } catch (e) {}
  try { await renderRoute(); }
  catch (e) { $('#app').innerHTML = `<div class=\"boot\"><div class=\"notice danger\">Workspace failed to start: ${esc(e.message)}</div></div>`; }
}"""

new_boot = """async function boot(full = true) {
  if (stored('nexus_transport') === 'query') state.transport = 'query';
  try {
    try {
      const cached = localStorage.getItem('nexus_public_config');
      if (cached) state.config = JSON.parse(cached);
    } catch (_) {}

    const [cfg, me] = await Promise.all([
      api('/api/config/public'),
      api('/api/auth/me')
    ]);
    state.config = cfg;
    try { localStorage.setItem('nexus_public_config', JSON.stringify(cfg)); } catch (_) {}
    state.me = me.authenticated ? me : null;
    state.csrf = me.csrf || state.csrf || stored(CSRF_KEY) || cookie('nexus_csrf');
    if (me.csrf) store(CSRF_KEY, me.csrf);
    if (!me.authenticated) {
      unstore(SESSION_KEY); unstore(CSRF_KEY); unstore('nexus_transport');
      state.csrf = ''; state.transport = 'auto';
    }
  } catch (e) {
    $('#app').innerHTML = `<div class=\"boot\"><div class=\"notice danger\">Cannot reach the NEXUS API: ${esc(e.message)}</div></div>`;
    return;
  }
  if (!state.me) {
    // GUEST MODE: allow free browsing without forced login
    const hash = location.hash;
    if (hash.startsWith('#/register')) { authView('register'); return; }
    if (hash.startsWith('#/login')) { authView('login'); return; }
    // Derive free feature list from public config
    const freeFeatures = (state.config?.permission_matrix || []).filter(f => f.tier === 'free').map(f => f.feature);
    state.me = {
      authenticated: false, is_guest: true,
      user: { name: 'Guest', email: '' },
      entitlement: {
        tier: 'free', plan: 'guest', is_pro: false, is_admin: false,
        features: freeFeatures.length ? freeFeatures : ['library.browse', 'library.free_projects'],
        usage: { ai_requests_per_day: { used: 0, limit: 0, unlimited: false } }
      },
      usage: { ai_requests_per_day: { used: 0, limit: 0, unlimited: false } }
    };
  }
  if (location.hash.startsWith('#/login') || location.hash.startsWith('#/register')) replaceHash('#/dashboard');
  api('/api/settings').then(prefs => {
    if (prefs?.settings?.theme) document.documentElement.dataset.theme = prefs.settings.theme;
  }).catch(() => {});
  try { await renderRoute(); }
  catch (e) { $('#app').innerHTML = `<div class=\"boot\"><div class=\"notice danger\">Workspace failed to start: ${esc(e.message)}</div></div>`; }
}"""

old_dash = """async function viewDashboard() {
  const me = state.me, ent = me.entitlement;
  const [projs, runs, ws] = await Promise.all([
    api('/api/projects'), api('/api/tools/runs').catch(() => ({ runs: [] })), api('/api/workspaces').catch(() => ({ workspaces: [] }))
  ]);"""

new_dash = """async function viewDashboard() {
  const me = state.me, ent = me.entitlement;
  const isGuest = me.is_guest || !me.authenticated;
  const [projs, runs, ws] = await Promise.all([
    isGuest ? Promise.resolve({ items: [] }) : api('/api/projects').catch(() => ({ items: [] })),
    api('/api/tools/runs').catch(() => ({ runs: [] })),
    api('/api/workspaces').catch(() => ({ workspaces: [] }))
  ]);"""

content_norm = content.replace("\r\n", "\n")
old_boot_norm = old_boot.replace("\r\n", "\n")
new_boot_norm = new_boot.replace("\r\n", "\n")
old_dash_norm = old_dash.replace("\r\n", "\n")
new_dash_norm = new_dash.replace("\r\n", "\n")

if old_boot_norm in content_norm and old_dash_norm in content_norm:
    content_norm = content_norm.replace(old_boot_norm, new_boot_norm, 1)
    content_norm = content_norm.replace(old_dash_norm, new_dash_norm, 1)
    if "\r\n" in content:
        app_path.write_text(content_norm.replace("\n", "\r\n"), encoding="utf-8")
    else:
        app_path.write_text(content_norm, encoding="utf-8")
    print("SUCCESS: Optimized boot and dashboard in web/app.js")
else:
    print(f"ERROR: old_boot_norm in content: {old_boot_norm in content_norm}, old_dash_norm in content: {old_dash_norm in content_norm}")
