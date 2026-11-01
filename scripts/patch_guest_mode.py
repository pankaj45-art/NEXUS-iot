"""Patch app.js to add guest mode in boot() function."""
import sys
from pathlib import Path

APP = Path(__file__).parent.parent / 'web' / 'app.js'
content = APP.read_text(encoding='utf-8')

OLD = (
    "  if (!state.me) {\n"
    "    if (location.hash.startsWith('#/register')) authView('register');\n"
    "    else { authView('login'); if (!location.hash.startsWith('#/login')) replaceHash('#/login'); }\n"
    "    return;\n"
    "  }\n"
    "  if (location.hash.startsWith('#/login') || location.hash.startsWith('#/register')) replaceHash('#/dashboard');\n"
    "  try { const prefs = await api('/api/settings'); document.documentElement.dataset.theme = prefs.settings?.theme || 'dark'; } catch (e) {}\n"
    "  try { await renderRoute(); }\n"
    "  catch (e) { $('#app').innerHTML = `<div class=\"boot\"><div class=\"notice danger\">Workspace failed to start: ${esc(e.message)}</div></div>`; }\n"
    "}\n"
    "\n"
    "window.addEventListener('hashchange', () => { if (state.me) renderRoute(); else boot(false); });\n"
    "boot();\n"
)

NEW = (
    "  if (!state.me) {\n"
    "    // GUEST MODE: allow free browsing without forced login\n"
    "    const hash = location.hash;\n"
    "    if (hash.startsWith('#/register')) { authView('register'); return; }\n"
    "    if (hash.startsWith('#/login')) { authView('login'); return; }\n"
    "    // Derive free feature list from public config\n"
    "    const freeFeatures = (state.config?.permission_matrix || []).filter(f => f.tier === 'free').map(f => f.feature);\n"
    "    state.me = {\n"
    "      authenticated: false, is_guest: true,\n"
    "      user: { name: 'Guest', email: '' },\n"
    "      entitlement: {\n"
    "        tier: 'free', plan: 'guest', is_pro: false, is_admin: false,\n"
    "        features: freeFeatures.length ? freeFeatures : ['library.browse', 'library.free_projects'],\n"
    "        usage: { ai_requests_per_day: { used: 0, limit: 0, unlimited: false } }\n"
    "      },\n"
    "      usage: { ai_requests_per_day: { used: 0, limit: 0, unlimited: false } }\n"
    "    };\n"
    "  }\n"
    "  if (location.hash.startsWith('#/login') || location.hash.startsWith('#/register')) replaceHash('#/dashboard');\n"
    "  try { const prefs = await api('/api/settings').catch(() => ({})); document.documentElement.dataset.theme = prefs.settings?.theme || 'dark'; } catch (e) {}\n"
    "  try { await renderRoute(); }\n"
    "  catch (e) { $('#app').innerHTML = `<div class=\"boot\"><div class=\"notice danger\">Workspace failed to start: ${esc(e.message)}</div></div>`; }\n"
    "}\n"
    "\n"
    "window.addEventListener('hashchange', () => { if (state.me) renderRoute(); else boot(false); });\n"
    "boot();\n"
)

if OLD in content:
    content = content.replace(OLD, NEW)
    APP.write_text(content, encoding='utf-8')
    print('SUCCESS: guest mode patched into app.js')
else:
    print('OLD text not found in app.js')
    # show what the end looks like
    idx = content.rfind('if (!state.me)')
    print(repr(content[idx:idx+600]))
    sys.exit(1)
