import { decodeAPIResponse } from './api-response.js?v=11';
import { createWorkstation } from './workstation.js?v=11';
import { startNeuralWallpaper } from './neural-wallpaper.js?v=13';
/* NEXUS IoT SPA - vanilla ES modules, no external dependencies. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nl2br = (v) => esc(v).replace(/\n/g, '<br>');
const fmtDate = (t) => t ? new Date(t * 1000).toLocaleString() : '—';
const copy = (t) => {
  try { if (navigator.clipboard?.writeText) { navigator.clipboard.writeText(t); return; } } catch (e) {}
  try {
    const ta = document.createElement('textarea');
    ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
  } catch (e) {}
};

const state = { me: null, config: null, csrf: '', route: null, tab: {}, cache: {}, transport: 'auto' };
// A superseded route intentionally cancels its pending UI reads. This is not a
// provider/network failure and must not become an unhandled promise rejection
// from an event handler on an already detached page. All other errors propagate.
window.addEventListener('unhandledrejection', e => {
  if(e.reason?.routeChanged) e.preventDefault();
});

function cookie(name) {
  try {
    const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : '';
  } catch (e) { return ''; }  // sandboxed opaque-origin frames block document.cookie
}

/* Embedded previews can block cookies AND Web Storage. Keep an in-memory
   fallback so a login still works for the lifetime of the page. */
const memStore = {};
function stored(k) {
  try { const v = sessionStorage.getItem(k); if (v) return v; } catch (e) {}
  return memStore[k] || '';
}
function store(k, v) {
  memStore[k] = v;
  try { sessionStorage.setItem(k, v); } catch (e) {}
}
function unstore(k) {
  delete memStore[k];
  try { sessionStorage.removeItem(k); } catch (e) {}
}
const SESSION_KEY = 'nexus_session_token', CSRF_KEY = 'nexus_csrf';

/* One fetch path for JSON, text exports and SVG diagrams. Every request goes
   through the session transports, so no feature can accidentally bypass auth. */
async function sessionFetch(path, opts = {}) {
  const tok = stored(SESSION_KEY);
  const csrf = state.csrf || stored(CSRF_KEY) || cookie('nexus_csrf');

  const once = async (withQuery) => {
    const headers = { 'Content-Type': 'application/json' };
    // Transport 1: HMAC-signed HttpOnly cookie (set by the server or by JS).
    // Transport 2: Bearer header (works when cookies are blocked).
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    if (csrf) headers['X-CSRF-Token'] = csrf;
    let url = path, body = opts.body;
    // Transport 3: last-resort query token for preview proxies that strip the
    // Authorization header AND block cookies. Used only after a 401 proves the
    // first two transports did not survive. Never written to localStorage or logs.
    if (withQuery && tok) {
      url += (url.includes('?') ? '&' : '?') + 'nx_session=' + encodeURIComponent(tok);
      if (csrf) {
        if (body && typeof body === 'object' && !Array.isArray(body)) body = { ...body, nx_csrf: csrf };
        else if (body === undefined && !['GET', 'HEAD'].includes((opts.method || 'GET').toUpperCase())) {
          body = { nx_csrf: csrf };
        }
      }
    }
    try {
      return await fetch(url, {
        method: opts.method || 'GET', headers, credentials: 'same-origin',
        signal: opts.signal, body: body === undefined ? undefined : JSON.stringify(body)
      });
    } catch (e) { throw new Error('Network error: ' + e.message); }
  };

  let res = await once(state.transport === 'query');
  const authEndpoint = path.startsWith('/api/auth/login') || path.startsWith('/api/auth/register');
  if (res.status === 401 && state.transport !== 'query' && tok && !authEndpoint) {
    const retry = await once(true);
    if (retry.ok) {
      state.transport = 'query';
      try { store('nexus_transport', 'query'); } catch (e) {}
    }
    res = retry;
  }
  return res;
}

async function api(path, opts = {}) {
  const epoch=state.renderEpoch;
  const res = await sessionFetch(path, opts);
  let data;
  try { data = await decodeAPIResponse(res); }
  catch (e) { if (epoch !== state.renderEpoch) e.routeChanged = true; throw e; }
  if(epoch!==state.renderEpoch) { const e=new Error('Navigation changed'); e.routeChanged=true; throw e; }
  return data;
}

async function apiText(path, opts = {}) {
  const res = await sessionFetch(path, opts);
  const text = await res.text();
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = JSON.parse(text)?.error?.message || msg; } catch (e) {}
    throw new Error(msg);
  }
  return text;
}

/* Exports and diagrams are fetched with the session, then shown inside the app.
   A sandboxed iframe usually blocks downloads/plain navigation to API URLs. */
const EXPORT_EXT = { markdown: 'md', code: 'ino', wiring: 'csv', bom: 'csv', json: 'json', svg: 'svg' };
async function openExport(slug, kind) {
  toast('Preparing ' + kind + ' export…');
  try {
    const text = await apiText(`/api/projects/${encodeURIComponent(slug)}/download?kind=${encodeURIComponent(kind)}`);
    const name = `${slug}.${EXPORT_EXT[kind] || 'txt'}`;
    modal(`Export · ${kind}`, `
      <p class="tiny muted">${esc(name)} · generated and entitlement-checked on the server.</p>
      <pre id="exp-text" style="max-height:44vh;overflow:auto">${esc(text)}</pre>
      <div class="row mt"><button class="btn primary sm" id="exp-copy">Copy to clipboard</button>
      <button class="btn sm" id="exp-dl">Download ${esc(name)}</button></div>`, (m) => {
      $('#exp-copy', m).onclick = () => { copy(text); toast('Copied', 'ok'); };
      $('#exp-dl', m).onclick = () => {
        try {
          const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
          const a = document.createElement('a');
          a.href = url; a.download = name; a.style.display = 'none';
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 10000);
        } catch (e) { toast('Download blocked in this frame — use Copy instead.', 'err'); }
      };
    });
  } catch (e) { toast(e, 'err'); }
}

async function hydrateDiagrams() {
  $$('img[data-diagram]').forEach(async (img) => {
    try {
      const svg = await apiText(img.dataset.diagram);
      const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
      if (document.body.contains(img)) {
        img.src = url;
        img.onload = () => setTimeout(() => URL.revokeObjectURL(url), 15000);
      }
    } catch (e) {
      if (document.body.contains(img)) {
        img.parentElement.innerHTML = `<div class="notice warn">Diagram unavailable: ${esc(e.message)}</div>`;
      }
    }
  });
}

function toast(msg, kind = '') {
  // Navigation cancellation is an internal control signal, not a provider error.
  if (msg?.routeChanged) return;
  if (msg && typeof msg === 'object') msg = msg.message || String(msg);
  const el = document.createElement('div');
  el.className = 'toast ' + kind; el.textContent = msg;
  $('#toast-host').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 4200);
}

function modal(title, html, onMount) {
  $('#modal-host').innerHTML = `<div class="modal-bg"><div class="modal"><span class="overlay-close">×</span><h3>${esc(title)}</h3>${html}</div></div>`;
  $('.overlay-close').onclick = closeModal;
  $('.modal-bg').onclick = (e) => { if (e.target.classList.contains('modal-bg')) closeModal(); };
  onMount?.($('.modal'));
}
function closeModal() { $('#modal-host').innerHTML = ''; }

function go(hash) { location.hash = hash; }
function replaceHash(hash) {
  try { history.replaceState(null, '', hash); } catch (e) { location.hash = hash; }
}
function setTab(k, v) { state.tab[k] = v; renderRoute(); }

const badge = (text, cls = '') => `<span class="badge ${cls}">${esc(text)}</span>`;
const tierBadge = (t) => badge(t === 'admin' ? 'ADMIN' : t === 'pro' ? 'PRO' : 'FREE', t === 'admin' ? 'rose' : t === 'pro' ? 'violet' : '');

/* ---------------------------------------------------------------- shell */
function shell() {
  const me = state.me, ent = me?.entitlement;
  const nav = [
    ['#/dashboard', '⌂', 'Dashboard', 'WORKSPACE'],
    ['#/assistant', '✧', 'AI Assistant', ''],
    ['#/ai-settings', '⇄', 'AI & API Keys', ''],
    ['#/projects', '▱', 'My Projects', ''],
    ['#/library', '▤', 'IoT Project Library', ''],
    ['#/invention', '◈', 'AI Invention Lab', 'ENGINEERING'],
    ['#/studio', '⌘', 'Circuit Studio', ''],
    ['#/code', '⌨', 'Code Engineer', ''],
    ['#/tools/device_monitoring', '⌁', 'Device Monitoring', ''],
    ['#/tools', '▦', 'Pro Workspace', 'RESOURCES'],
    ['#/learn', '◎', 'Learning', ''],
    ['#/subscription', '◴', 'Account & Subscription', ''],
  ];
  if (!ent?.is_pro) nav.push(['#/upgrade', '↑', 'Upgrade to Pro', '']);
  if (ent?.is_admin) {
    nav.push(['#/admin', '⚙', 'Admin Dashboard', 'ADMINISTRATION']);
  }
  nav.push(['#/account', '◉', 'Preferences', '']);
  let items = '', last = '';
  for (const [href, ico, label, section] of nav) {
    if (section && section !== last) { items += `<div class="nav-label">${section}</div>`; last = section; }
    const active = (location.hash.startsWith(href) || (href === '#/ai-settings' && location.hash.startsWith('#/providers'))) && (href !== '#/dashboard' || location.hash === '#/dashboard');
    items += `<a class="nav-item ${active ? 'active' : ''}" href="${href}"><span class="ico">${ico}</span><span>${label}</span></a>`;
  }
  const usage = me?.usage?.ai_requests_per_day || { used: 0, limit: -1, unlimited: false };
  const pct = usage.unlimited ? 100 : Math.min(100, (usage.used / Math.max(usage.limit, 1)) * 100);
  return `<div class="shell">
    <div class="nexus-live-wallpaper" aria-hidden="true"><div class="wallpaper-grid"></div><div class="wallpaper-scanline"></div><div class="wallpaper-particles"></div></div>
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">N</div><div><div class="brand-name">NEXUS IoT</div><div class="brand-sub">Engineering Platform</div></div></div>
      <nav class="nav">${items}</nav>
      <div class="sidebar-foot">
        <div class="plan-chip"><div class="row between"><b>${esc(ent?.plan?.toUpperCase() || 'GUEST')} plan</b>${tierBadge(ent?.tier || 'free')}</div>
        <div class="tiny muted mt-s">AI requests today: ${usage.used}${usage.unlimited ? ' / unlimited' : ' / ' + usage.limit}</div>
        <div class="usage-bar"><i style="width:${pct}%"></i></div></div>
        <button class="btn ghost sm mt-s" style="width:100%" id="logout">Sign out</button>
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="search"><input id="global-search" placeholder="Search projects, tools, documentation…"></div>
        <button class="btn sm wallpaper-launch" id="wallpaper-picker" type="button" aria-label="Choose animated wallpaper">✦ <span>Wallpapers</span></button>
        <button class="btn sm help-launch" id="help-guide" type="button" aria-label="Open contextual help and tool guides">? <span>Help & guides</span></button>
        <div class="spacer"></div>
        ${state.transport === 'query' ? badge('Preview session', 'amber') : ''}
        <a id="shell-ai-link" class="badge ${state.config?.ai?.last_test?.recent ? 'green' : 'amber'}" href="#/ai-settings">${state.config?.ai?.last_test?.recent ? 'AI connected' : state.config?.ai?.configured ? 'AI configured' : 'Add API key'}</a>
        ${'<span class="payments-status">' + badge(state.config?.payments?.configured ? 'Payments live' : 'Payments not configured', state.config?.payments?.configured ? 'green' : '') + '</span>'}
        <span class="tiny muted topbar-account">${esc(me?.user?.email || '')}</span>
      </header>
      ${!ent?.is_pro ? `<div class="admob-banner" style="background:rgba(15,23,42,0.95);border-bottom:1px solid rgba(56,189,248,0.2);padding:7px 18px;display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#94a3b8;backdrop-filter:blur(6px);z-index:20;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="background:#f59e0b;color:#0b0f19;font-weight:800;font-size:9.5px;padding:1px 6px;border-radius:3px;letter-spacing:0.04em;">AD</span>
          <span>Google AdMob Partner Banner · Free Tier Active · Upgrade to Pro ($3/mo) for 100% Ad-Free Engineering</span>
        </div>
        <a href="#/upgrade" style="color:#38bdf8;font-weight:700;text-decoration:none;display:flex;align-items:center;gap:4px;">⚡ Upgrade to Pro ($3/mo)</a>
      </div>` : ''}
      <main class="content" id="view"><div class="boot"><div class="spinner"></div></div></main>
    </div></div>`;
}

/* ---------------------------------------------------------------- auth */
function authView(mode) {
  $('#app').innerHTML = `<div class="auth-wrap">
    <div class="auth-left">
      <div class="brand" style="border:0;padding:0 0 30px"><div class="brand-mark">N</div><div><div class="brand-name" style="font-size:20px">NEXUS IoT</div><div class="brand-sub">AI-powered IoT engineering</div></div></div>
      <h1>Build real IoT.<br>From idea to working firmware.</h1>
      <p>A professional engineering workspace with ${state.config?.library?.total_published || '100+' } detailed projects, circuit validation, AI firmware engineering and live device telemetry.</p>
      <div class="mt">
        <div class="feature-line"><b>◈</b><span>100+ technically coherent projects with BOM, wiring tables, firmware and test plans.</span></div>
        <div class="feature-line"><b>◈</b><span>10 Pro AI engineering tools — project generator, circuit validator, debugger and more.</span></div>
        <div class="feature-line"><b>◈</b><span>Role-based access enforced on the server; Pro content never leaks to free accounts.</span></div>
        <div class="feature-line"><b>◈</b><span>Honest quality labels: statically reviewed, never claimed as hardware-tested.</span></div>
      </div>
    </div>
    <div class="auth-right"><div class="auth-card">
      <h2>${mode === 'login' ? 'Welcome back' : 'Create your free account'}</h2>
      <p class="muted tiny mb">${mode === 'login' ? 'Sign in to your NEXUS IoT workspace.' : 'Start with 15 beginner projects. No card required.'}</p>
      <div id="auth-alert"></div>
      ${mode === 'register' ? '<label class="field"><span>Display name</span><input id="a-name" placeholder="Your name"></label>' : ''}
      <label class="field"><span>Email</span><input id="a-email" type="email" placeholder="you@example.com"></label>
      <label class="field"><span>Password</span><input id="a-pass" type="password" placeholder="At least 10 chars, upper, lower, number"></label>
      <button class="btn primary" style="width:100%" id="a-submit">${mode === 'login' ? 'Sign in' : 'Create account'}</button>
      <div class="divider"></div>
      <p class="center tiny muted">${mode === 'login' ? `New here? <a href="#/register">Create a free account</a>` : `Already have an account? <a href="#/login">Sign in</a>`}</p>
      <p class="center tiny dim mt">Session not sticking in this preview? <a href="/?nx=1" target="_blank" rel="noopener">Open NEXUS in a new tab</a>.</p>
      <p class="center tiny dim mt" id="a-status">NEXUS · ready</p>
    </div></div></div>`;
  const status = (t) => { const el = $('#a-status'); if (el) el.textContent = t; };
  const submit = async () => {
    const body = { email: $('#a-email').value.trim(), password: $('#a-pass').value };
    if (mode === 'register') body.name = $('#a-name')?.value.trim() || 'Engineer';
    $('#a-submit').disabled = true;
    status('NEXUS · contacting server…');
    try {
      const r = await api('/api/auth/' + (mode === 'login' ? 'login' : 'register'), { method: 'POST', body });
      status('NEXUS · server answered (' + (r.build || '?') + ')');
      if (r.session_token) store(SESSION_KEY, r.session_token);
      if (r.csrf) { state.csrf = r.csrf; store(CSRF_KEY, r.csrf); }
      // A third transport: set the signed cookie from JS in case the proxy
      // stripped Set-Cookie but the frame is still allowed to write cookies.
      if (r.signed_cookie) {
        try {
          const attrs = 'Path=/; ' + (location.protocol === 'https:' ? 'SameSite=None; Secure' : 'SameSite=Lax');
          document.cookie = 'nexus_session=' + r.signed_cookie + '; ' + attrs;
          document.cookie = 'nexus_csrf=' + r.csrf + '; ' + attrs;
        } catch (e) {}
      }
      // Open immediately from the login response: no second /auth/me request,
      // so a blocked cookie/header cannot send us back to the sign-in form.
      if (r.session && r.session.authenticated) {
        state.me = r.session;
        state.config = r.config || state.config;
        if (location.hash.startsWith('#/login') || location.hash.startsWith('#/register')) replaceHash('#/dashboard');
        status('NEXUS · opening workspace…');
        try {
          await renderRoute();
          toast('Welcome to NEXUS IoT', 'ok');
        } catch (e) {
          $('#app').innerHTML = `<div class="boot"><div class="notice danger">Workspace render failed: ${esc(e.message)}</div></div>`;
        }
        return;
      }
      status('NEXUS · checking session…');
      await boot(false);
      if (!state.me) {
        $('#auth-alert').innerHTML = '<div class="notice danger mb">Signed in, but the session was not retained. Use the "Open NEXUS in a new tab" link below.</div>';
        status('NEXUS · session not retained');
        $('#a-submit').disabled = false;
        return;
      }
      go('#/dashboard'); toast('Welcome to NEXUS IoT', 'ok');
    } catch (e) {
      let alertContent = `<div class="notice danger mb">${esc(e.message)}`;
      if (e.message && e.message.toLowerCase().includes('already exists')) {
        alertContent += `<div class="mt-s tiny"><a href="#/login" style="color:#38bdf8;font-weight:bold;text-decoration:underline;">Click here to Sign In with this email →</a></div>`;
      }
      alertContent += `</div>`;
      $('#auth-alert').innerHTML = alertContent;
      status('NEXUS · error: ' + e.message);
      $('#a-submit').disabled = false;
    }
  };
  $('#a-submit').onclick = submit;
  $('#a-pass').onkeydown = e => { if (e.key === 'Enter') submit(); };
  $('#a-email').focus();
}

/* ---------------------------------------------------------------- helpers */
function bindShell() {
  $('#logout')?.addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST', body: {} }).catch(() => {});
    unstore(SESSION_KEY); unstore(CSRF_KEY); unstore('nexus_transport');
    state.csrf = ''; state.transport = 'auto';
    state.me = null; go('#/login'); boot(false);
  });
  $('#global-search')?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.value.trim()) go('#/library?q=' + encodeURIComponent(e.target.value.trim()));
  });
  $('#help-guide')?.addEventListener('click', openHelpGuide);
  $('#wallpaper-picker')?.addEventListener('click', openWallpaperPicker);
}


const WALLPAPER_PRESETS = [
  { id:'neural', name:'Neural Plexus', desc:'Living synapses, network nodes and flowing telemetry', colors:['#06152a','#00d9ff','#8e72ff'], mode:'neural' },
  { id:'quantum', name:'Quantum Circuit', desc:'Electric-blue PCB paths and pulsing signal routes', colors:['#06121f','#20f4d5','#168cff'], mode:'circuit' },
  { id:'aurora', name:'Data-Flow Aurora', desc:'Cinematic teal-violet data waves and flowing light streams', colors:['#071525','#47ffd1','#b66dff'], mode:'aurora' },
  { id:'cosmos', name:'Deep Space Data', desc:'Cosmic data streams, stars and distant energy rings', colors:['#080b22','#7c8cff','#ff63d8'], mode:'cosmos' },
  { id:'blueprint', name:'Holographic Blueprint', desc:'Precision drafting lines and cool holographic signals', colors:['#061c2a','#7be8ff','#4f9cff'], mode:'blueprint' },
  { id:'fusion', name:'Fusion Reactor', desc:'A warm cyan-gold reactor glow with circulating energy', colors:['#101321','#49f4ff','#ffc36b'], mode:'fusion' }
];
function applyWallpaper(id, announce = true) {
  const preset = WALLPAPER_PRESETS.find(x => x.id === id) || WALLPAPER_PRESETS[0];
  const host = document.querySelector('.nexus-live-wallpaper');
  if (host) host.dataset.wallpaper = preset.id;
  try { localStorage.setItem('nexus_wallpaper_preset', preset.id); } catch (_) {}
  document.querySelectorAll('[data-wallpaper-option]').forEach(el => {
    const active = el.dataset.wallpaperOption === preset.id;
    el.classList.toggle('selected', active); el.setAttribute('aria-pressed', String(active));
  });
  if (announce) toast(`Wallpaper set to ${preset.name}`, 'ok');
}
function openWallpaperPicker() {
  const current = (() => { try { return localStorage.getItem('nexus_wallpaper_preset') || 'aurora'; } catch (_) { return 'neural'; } })();
  const cards = WALLPAPER_PRESETS.map(p => `<button type="button" class="wallpaper-option ${p.id === current ? 'selected' : ''}" data-wallpaper-option="${p.id}" aria-pressed="${p.id === current}" style="--wall-a:${p.colors[1]};--wall-b:${p.colors[2]};--wall-bg:${p.colors[0]}"><span class="wallpaper-thumb ${p.mode}"><i></i><i></i><i></i><b>✦</b></span><span class="wallpaper-option-copy"><strong>${p.name}</strong><small>${p.desc}</small></span><span class="wallpaper-check">✓</span></button>`).join('');
  modal('Live engineering wallpapers', `<p class="muted">Choose a live background for your workspace. Your choice is saved on this browser.</p><div class="wallpaper-gallery">${cards}</div><p class="tiny muted mt">Animations are local, lightweight and decorative; they do not represent real sensor telemetry. Reduced-motion settings are respected.</p>`, m => {
    $$('[data-wallpaper-option]', m).forEach(el => el.addEventListener('click', () => { applyWallpaper(el.dataset.wallpaperOption); closeModal(); }));
  });
}

function tabsHtml(key, tabs, active) {
  return `<div class="tabs">${tabs.map(t => `<div class="tab ${active === t[0] ? 'active' : ''}" data-tab="${esc(t[0])}" data-tabkey="${key}">${esc(t[1])}</div>`).join('')}</div>`;
}
function bindTabs() {
  $$('.tab').forEach(el => el.onclick = () => setTab(el.dataset.tabkey, el.dataset.tab));
}
function pageHead(title, sub, actions = '') {
  return `<div class="row between mb"><div><h1>${esc(title)}</h1><p class="muted" style="margin:0">${sub}</p></div><div class="row">${actions}</div></div>`;
}
function stat(n, l) { return `<div class="stat"><div class="n">${esc(n)}</div><div class="l">${esc(l)}</div></div>`; }
function spinner() { return '<div class="boot" style="height:220px"><div class="spinner"></div><p>Loading…</p></div>'; }

function keyVal(obj) {
  return `<dl class="kv">${Object.entries(obj).map(([k, v]) => `<dt>${esc(k.replace(/_/g, ' '))}</dt><dd>${typeof v === 'object' ? `<span class="mono">${esc(JSON.stringify(v))}</span>` : nl2br(v)}</dd>`).join('')}</dl>`;
}
function table(rows, cols) {
  if (!rows?.length) return '<p class="muted tiny">None</p>';
  return `<div class="table-wrap"><table><thead><tr>${cols.map(c => `<th>${esc(c[1])}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${c[2] ? c[2](r[c[0]], r) : esc(r[c[0]] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function download(name, text, type = 'application/json') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/* ---------------------------------------------------------------- contextual help */
const HELP_GUIDES = [
  { match: '/dashboard', title: 'Getting started', intro: 'Use NEXUS as a guided engineering workflow, from a question to a tested prototype.', steps: ['Ask the AI Assistant to explain the problem and compare approaches.', 'Choose a project from the library or describe a new idea in Invention Lab.', 'Open Circuit Studio and inspect every component, pin and connection.', 'Use Code Engineer to generate or review firmware that matches the circuit.', 'Record tests and unresolved risks before connecting real hardware.'], links: [['AI Assistant', '#/assistant'], ['Project Library', '#/library'], ['Learning basics', '#/learn']] },
  { match: '/assistant', title: 'AI Assistant guide', intro: 'Ask one clear question at a time and provide your board, components, expected behavior and exact error when relevant.', steps: ['Start a new conversation or continue a saved one.', 'Select a project context when you want the assistant to use saved project details.', 'Attach text or code when you need help with existing firmware.', 'Review generated pin numbers, assumptions and references before building.', 'If the provider is unavailable, open AI & API Keys; NEXUS should show the real error rather than invent an answer.'], links: [['Connect AI', '#/ai-settings'], ['Code Engineer', '#/code'], ['Learning basics', '#/learn']] },
  { match: '/studio', title: 'Circuit Studio guide', intro: 'Treat the circuit graph as the source of truth for wiring, validation and supported firmware pin definitions.', steps: ['Open or create a project and confirm the selected board.', 'Add supported components from the component library.', 'Connect exact terminals; inspect each connection and the generated wiring table.', 'Run validation and resolve ERROR findings before wiring hardware.', 'Save a version and export the diagram or wiring table for bench use.'], links: [['My Projects', '#/projects'], ['Project Library', '#/library'], ['Code Engineer', '#/code']] },
  { match: '/invention', title: 'Invention Lab guide', intro: 'Describe a real problem and ask for a testable prototype, not a guaranteed novel or production-ready invention.', steps: ['Describe who has the problem and how it is currently solved.', 'Set your budget, operating conditions, power source and constraints.', 'Review the proposed architecture, parts, circuit and firmware.', 'Check any unknown component ratings and manual work items.', 'Compare existing approaches and test the riskiest assumption first.'], links: [['AI Assistant', '#/assistant'], ['Circuit Studio', '#/studio'], ['Project Library', '#/library']] },
  { match: '/code', title: 'Code Engineer guide', intro: 'Generate or modify firmware in small, reviewable steps.', steps: ['Choose the target board and the actual sensors or modules.', 'Use Generate for a new sketch, Explain to learn code, Review to inspect code, or Refactor to improve it.', 'Check the pin mapping against the saved circuit before applying changes.', 'Review dependency versions, credentials placeholders, and error handling.', 'Compile with the target toolchain and test safely; generated code is not automatically hardware-verified.'], links: [['Circuit Studio', '#/studio'], ['Debugging Center', '#/tools/debugging'], ['AI Assistant', '#/assistant']] },
  { match: '/images', title: 'Image Studio guide', intro: 'Use generated visuals for product concepts and presentation assets, not as verified electrical schematics.', steps: ['Write a specific prompt describing the device, style, view and background.', 'Confirm image generation is configured independently from chat AI.', 'Generate and review the result; retry with more precise instructions if needed.', 'Associate useful concepts with a project when the option is available.', 'For wiring, use Circuit Studio and validated connection data instead of concept art.'], links: [['AI & API Keys', '#/ai-settings'], ['Invention Lab', '#/invention']] },
  { match: '/research', title: 'Research & Innovation guide', intro: 'Separate sourced evidence from hypotheses and your own design assumptions.', steps: ['Write a focused question with the target technology and use case.', 'Check whether live search is configured or results are limited to curated references.', 'Open original sources and verify publication dates, claims and technical details.', 'Save useful evidence with the relevant project.', 'Do not treat a quick search as proof of global patent novelty or freedom to operate.'], links: [['Invention Lab', '#/invention'], ['My Projects', '#/projects']] },
  { match: '/learn', title: 'Learning basics guide', intro: 'Use the short learning modules before working with unfamiliar electronics.', steps: ['Read the objective and key points for a module.', 'Open “Check your understanding” and answer before revealing the explanation.', 'Use the reference links for deeper reading.', 'Apply one concept to a low-voltage sample project.', 'Check voltage, current, polarity and power limits before connecting a board.'], links: [['Project Library', '#/library'], ['Circuit Studio', '#/studio']] },
  { match: '/ai-settings', title: 'AI connection guide', intro: 'Chat, image generation and live web search are separate integrations and may need separate provider credentials.', steps: ['Choose a provider and a model supported by that provider.', 'Enter your own API key in the secure connection form; never paste keys into chat or project code.', 'Use Save & Connect / test and wait for a successful provider response.', 'If the test fails, read the error and verify the key, model, endpoint, quota and network.', 'Configure image and search providers separately if you need those capabilities.'], links: [['AI Assistant', '#/assistant'], ['Image Studio', '#/images'], ['AI Assistant', '#/assistant']] }
];
function openHelpGuide() {
  const hash = (location.hash || '#/dashboard').replace(/^#/, '').split('?')[0];
  const guide = HELP_GUIDES.find(x => hash === x.match || hash.startsWith(x.match + '/')) || {
    title: 'Tool usage & safe workflow',
    intro: 'Every engineering tool has a specific job. Begin with the smallest testable workflow and verify outputs before relying on them.',
    steps: ['Read the tool description and required inputs before running it.', 'Use a saved project when the tool needs circuit, source or test context.', 'Inspect warnings, assumptions, dependency requirements and any manual work.', 'Save results that you need to compare or revisit.', 'Use Learning basics for electronics safety and the relevant tool guide for detailed steps.'],
    links: [['Learning basics', '#/learn'], ['AI Assistant', '#/assistant'], ['Project Library', '#/library']]
  };
  modal(guide.title, `<p class="muted">${esc(guide.intro)}</p><ol class="help-steps">${guide.steps.map(x => `<li>${esc(x)}</li>`).join('')}</ol><div class="divider"></div><h4>Useful next steps</h4><div class="row help-links">${guide.links.map(([label,href]) => `<a class="btn sm" data-help-href="${esc(href)}" href="${esc(href)}">${esc(label)} →</a>`).join('')}</div><p class="tiny muted mt">Engineering outputs are suggestions until reviewed and tested. Circuit rule checks are not a substitute for electrical safety checks or physical validation.</p>`, m => {
    $$('[data-help-href]', m).forEach(a => a.addEventListener('click', e => { e.preventDefault(); const href = a.getAttribute('href'); closeModal(); go(href); }));
  });
}

/* ---------------------------------------------------------------- dashboard */
async function viewDashboard() {
  const me = state.me, ent = me.entitlement;
  const [projs, runs, ws] = await Promise.all([
    api('/api/projects'), api('/api/tools/runs').catch(() => ({ runs: [] })), api('/api/workspaces').catch(() => ({ workspaces: [] }))
  ]);
  $('#view').innerHTML = `
    ${!state.config?.ai?.configured ? `<div class="card ai-connect-banner mb"><div><h3>Bring NEXUS AI online</h3><p class="tiny muted">Add a real provider API key once. Online chat, Invention Lab and Code Engineer use the saved connection immediately.</p></div><a class="btn primary" href="#/ai-settings">${ent.is_admin ? 'Add API key & connect' : 'AI connection status'} →</a></div>` : ''}
    <div class="hero mb">
      <div class="row between"><div><h1>Engineering workspace</h1>
      <p>Learn electronics, validate circuits, generate firmware and monitor devices — from your first LED to a fleet of connected sensors.</p>
      <div class="row mt">${badge((state.config?.library?.total_published || 117) + ' project specs', 'cyan')}${badge('Connected engineering tools', 'violet')}${badge('Server-side entitlements', 'green')}</div></div>
      <div style="min-width:170px">${tierBadge(ent.tier)} <p class="tiny muted mt-s">${esc(ent.subscription_status)} plan · ${ent.is_pro ? 'Full library unlocked' : '15 free projects'}</p></div></div>
    </div>
    <div class="grid g4 mb">
      ${stat(state.config?.library?.total_published ?? '—', 'Published projects')}
      ${stat(projs.items.length, 'Visible to you')}
      ${stat(me.usage?.tool_calls_per_day?.used ?? 0, 'Tool calls today')}
      ${stat(ws.workspaces.length, 'Saved workspaces')}
    </div>
    ${!ent.is_pro ? `<div class="notice warn mb"><b>Unlock the full engineering workspace.</b> Pro adds 100+ detailed projects, engineering tools, exports, version history and live device monitoring. <a href="#/upgrade">See plans →</a></div>` : ''}
    <div class="grid g2">
      <div class="card">
        <div class="section-title">Ask the NEXUS assistant</div>
        <p class="tiny muted">General questions, programming, science, writing and engineering. ${ent.is_pro ? 'Higher limits on your plan.' : `Free plan: ${me.usage?.ai_requests_per_day?.limit ?? 8} requests/day.`}</p>
        <textarea id="ask-q" placeholder="e.g. Why does my ESP32 DHT22 return NaN?"></textarea>
        <div class="row mt-s"><button class="btn primary sm" id="ask-btn">Ask</button><span class="tiny dim">${state.config?.ai?.configured ? 'Configured model · no silent fallback' : 'Online provider needs configuration'}</span></div>
        <pre id="ask-out" class="mt" style="display:none"></pre>
      </div>
      <div class="card">
        <div class="section-title">Quick start</div>
        <div class="stack">
          <a class="btn" href="#/studio">⌘ &nbsp; Open Circuit Studio</a><a class="btn" href="#/invention">◈ &nbsp; Develop a new invention</a><a class="btn" href="#/library">▤ &nbsp; Browse the project library</a>
          <a class="btn" href="#/tools">✦ &nbsp; Explore Pro engineering tools</a>
          <a class="btn" href="#/subscription">◈ &nbsp; Check subscription & usage</a>
          ${ent.is_admin ? '<a class="btn" href="#/admin">⚙ &nbsp; Open admin workspace</a>' : ''}
        </div>
        <div class="divider"></div>
        <div class="section-title">Recent tool runs</div>
        ${runs.runs.length ? table(runs.runs.slice(0, 5), [['tool', 'Tool'], ['mode', 'Mode'], ['created_at', 'When', v => fmtDate(v)]]) : '<p class="muted tiny">No tool runs yet. Open the Pro Workspace to start.</p>'}
      </div>
    </div>
    <div class="card guide-card mt">
      <div class="row between"><div><div class="eyebrow">BUILT-IN TOOL GUIDANCE</div><h3>New to NEXUS IoT?</h3><p class="tiny muted">Follow a guided path from an idea to a circuit, firmware and a test plan. Every workspace has a contextual guide from the Help & guides button above.</p></div><a class="btn primary sm" href="#/learn">Start learning →</a></div>
      <div class="guide-path"><a href="#/assistant"><span>01</span><b>Ask</b><small>Understand the problem</small></a><a href="#/invention"><span>02</span><b>Design</b><small>Plan a solution</small></a><a href="#/studio"><span>03</span><b>Wire</b><small>Validate the circuit</small></a><a href="#/code"><span>04</span><b>Build</b><small>Review firmware</small></a><a href="#/tools/device_monitoring"><span>05</span><b>Test</b><small>Check real behavior</small></a></div>
    </div>
    <div class="section-title">Start with these free projects</div>
    <div class="grid g3">${projs.items.slice(0, 6).map(projectCard).join('')}</div>`;
  $('#ask-btn').onclick = async () => {
    const q = $('#ask-q').value.trim(); if (!q) return;
    $('#ask-btn').disabled = true;
    try {
      const c = await api('/api/conversations', { method: 'POST', body: {} });
      await api(`/api/conversations/${c.id}/messages`, { method: 'POST', body: { message: q } });
      go('#/assistant?conversation=' + c.id);
    } catch (e) { toast(e, 'err'); }
    if ($('#ask-btn')) $('#ask-btn').disabled = false;
  };
}

/* ---------------------------------------------------------------- library */
function projectCard(p) {
  if (p.locked) return `<div class="locked-card"><div class="lock">🔒</div><b>Pro project</b><span class="tiny">Full instructions, diagrams, firmware and files available with Pro.</span></div>`;
  return `<a class="proj-card" href="#/project/${encodeURIComponent(p.slug)}">
    <div class="row between"><div class="row">${p.is_free ? badge('FREE', 'green') : badge('PRO', 'violet')}${badge(p.difficulty, p.difficulty === 'Advanced' ? 'rose' : p.difficulty === 'Intermediate' ? 'amber' : '')}</div>${p.status !== 'published' ? badge(p.status, 'amber') : ''}</div>
    <div class="t">${esc(p.title)}</div><div class="s">${esc(p.summary)}</div>
    <div class="foot"><span class="tag">${esc(p.category)}</span><span class="tag">${esc(p.board)}</span></div></a>`;
}

async function viewLibrary() {
  const q = new URLSearchParams(location.hash.split('?')[1] || '');
  const params = new URLSearchParams();
  if (q.get('q')) params.set('q', q.get('q'));
  if (q.get('category')) params.set('category', q.get('category'));
  if (q.get('difficulty')) params.set('difficulty', q.get('difficulty'));
  if (state.me.entitlement.is_admin && q.get('status') === 'all') params.set('status', 'all');
  const data = await api('/api/projects?' + params.toString());
  const cats = state.config?.library?.categories || [];
  const locked = Array.from({ length: Math.min(data.locked_count || 0, 6) }, () => ({ locked: true }));
  $('#view').innerHTML = pageHead('IoT Project Library',
    `${data.total} projects visible to you${data.locked_count ? ` · ${data.locked_count} more with Pro` : ''} · ${cats.length} categories`,
    `<a class="btn sm" href="#/upgrade">${state.me.entitlement.is_pro ? 'Plan details' : 'Unlock full library'}</a>`) +
    `<div class="card mb"><div class="row">
      <input id="f-q" placeholder="Search titles, summaries, tags…" value="${esc(q.get('q') || '')}" style="flex:2;min-width:200px">
      <select id="f-cat" style="flex:1;min-width:190px"><option value="">All categories</option>${cats.map(c => `<option ${q.get('category') === c.name ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select>
      <select id="f-diff" style="flex:0 0 160px"><option value="">All levels</option>${['Beginner', 'Intermediate', 'Advanced'].map(d => `<option ${q.get('difficulty') === d ? 'selected' : ''}>${d}</option>`).join('')}</select>
      ${state.me.entitlement.is_admin ? `<label class="check"><input type="checkbox" id="f-all" ${q.get('status') === 'all' ? 'checked' : ''}> Include drafts</label>` : ''}
      <button class="btn sm" id="f-go">Apply</button><button class="btn ghost sm" id="f-clear">Clear</button>
    </div></div>
    ${data.upgrade_message ? `<div class="notice mb"><b>${esc(data.upgrade_message)}</b><br><span class="tiny">Locked project names and content are never sent to free accounts — not even through the API.</span> <a href="#/upgrade">Upgrade →</a></div>` : ''}
    <div class="grid g3">${data.items.map(projectCard).join('')}${locked.map(projectCard).join('')}</div>
    ${!data.items.length ? '<div class="empty">No projects match these filters.</div>' : ''}`;
  const apply = () => {
    const p = new URLSearchParams();
    if ($('#f-q').value.trim()) p.set('q', $('#f-q').value.trim());
    if ($('#f-cat').value) p.set('category', $('#f-cat').value);
    if ($('#f-diff').value) p.set('difficulty', $('#f-diff').value);
    if ($('#f-all')?.checked) p.set('status', 'all');
    go('#/library' + (p.toString() ? '?' + p.toString() : ''));
  };
  $('#f-go').onclick = apply;
  $('#f-clear').onclick = () => go('#/library');
  $('#f-q').onkeydown = e => { if (e.key === 'Enter') apply(); };
}

/* ---------------------------------------------------------------- project detail */
const PROJECT_TABS = [
  ['overview', 'Overview'], ['bom', 'Bill of Materials'], ['architecture', 'Architecture'],
  ['circuit', 'Circuit & Wiring'], ['procedure', 'Procedure'], ['code', 'Source Code'],
  ['troubleshooting', 'Troubleshooting'], ['testing', 'Testing'], ['deliverables', 'Deliverables'], ['quality', 'Quality']
];

async function viewProject(slug) {
  let data;
  try { data = await api('/api/projects/' + encodeURIComponent(slug)); }
  catch (e) {
    $('#view').innerHTML = `<div class="card"><h2>${esc(e.message)}</h2>${e.status === 403 ? `<p class="muted">This project's instructions, diagrams, firmware and files are Pro-only.</p><a class="btn primary" href="#/upgrade">See Pro plans</a>` : `<a class="btn" href="#/library">Back to library</a>`}</div>`;
    return;
  }
  const p = data.project, c = p.content, tab = state.tab['project'] || 'overview';
  const canExport = state.me.entitlement.features.includes('exports');
  $('#view').innerHTML = `<div class="row between mb"><div><a class="tiny muted" href="#/library">← IoT Project Library</a>
    <h1 style="margin-top:6px">${esc(p.title)}</h1>
    <div class="row">${p.is_free ? badge('FREE PROJECT', 'green') : badge('PRO PROJECT', 'violet')}${badge(p.category, 'cyan')}${badge(p.difficulty)}${badge(p.quality_status, 'amber')}<span class="tag">v${p.version}</span></div></div>
    <div class="row"><button class="btn sm" id="save-ws">＋ Save to workspace</button>
    ${canExport ? `<div class="row">${['markdown', 'code', 'wiring', 'bom', 'json', 'svg'].map(k => `<button class="btn sm" data-export="${k}" title="Open ${k} export">⬇ ${k}</button>`).join('')}</div>` : badge('Exports: Pro', 'violet')}</div></div>
    ${tabsHtml('project', PROJECT_TABS, tab)}<div id="project-tab">${renderProjectTab(tab, c, p)}</div>`;
  bindTabs();
  $$('#view [data-export]').forEach(b => b.onclick = () => openExport(p.slug, b.dataset.export));
  const studioFork = document.createElement('button'); studioFork.className='btn sm'; studioFork.textContent='Open a supported copy in Circuit Studio';
  $('#save-ws').parentElement.appendChild(studioFork);
  studioFork.onclick = async () => { try { const r=await api('/api/designs/from-library',{method:'POST',body:{slug:p.slug}}); go('#/studio/'+r.id); } catch(e) { toast(e,'err'); } };
  $('#save-ws').onclick = async () => {
    try { await api('/api/workspaces', { method: 'POST', body: { name: p.title, project_slug: p.slug } }); toast('Saved to your workspace', 'ok'); }
    catch (e) { toast(e, 'err'); }
  };
}

function renderProjectTab(tab, c, p) {
  switch (tab) {
    case 'overview': {
      const o = c.overview;
      return `<div class="grid g2"><div class="card"><h3>${esc(o.name)}</h3><p>${esc(o.summary)}</p>
        <h4 class="mt">Problem statement</h4><p class="muted">${esc(o.problem_statement)}</p>
        <h4>Expected outcome</h4><p class="muted">${esc(o.expected_outcome)}</p>
        <h4>Objectives</h4><ol>${o.objectives.map(x => `<li>${esc(x)}</li>`).join('')}</ol>
        <h4>Practical use cases</h4><ul>${o.practical_use_cases.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div class="card"><h4>Project metadata</h4>${keyVal({ 'Project ID': o.id, Category: o.category, Difficulty: o.difficulty, 'Build time': o.estimated_build_time_hours + ' h', 'Build-time assumption': o.build_time_assumptions, Status: o.status, Visibility: o.publication_visibility, 'Quality status': o.quality_status, Board: c.board, Transport: c.comms })}
        <h4 class="mt">Prerequisites</h4><ul>${o.prerequisites.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4>Required skills</h4><div class="chip-row">${o.required_skills.map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div></div></div>`;
    }
    case 'bom': {
      const b = c.bom;
      return `<div class="notice mb">${esc(b.price_disclaimer)}</div>
        <div class="section-title">Mandatory components (${b.mandatory.length})</div>
        ${table(b.mandatory, [['name', 'Component'], ['quantity', 'Qty'], ['purpose', 'Purpose'], ['specifications', 'Specs'], ['estimated_price', 'Est. price'], ['mandatory', 'Required', v => v ? badge('yes', 'green') : badge('support', 'amber')]])}
        <div class="section-title">Optional upgrades</div>
        <div class="grid g3">${b.optional_upgrades.map(o => `<div class="card soft"><b>${esc(o.name)}</b><p class="tiny muted mt-s">${esc(o.purpose)}</p><p class="tiny dim">${esc(o.estimated_price)}</p></div>`).join('')}</div>
        <div class="section-title">Compatibility notes</div>
        ${table(b.mandatory.filter(x => x.compatibility_notes), [['name', 'Component'], ['compatibility_notes', 'Note'], ['documentation', 'Documentation', v => `<a href="${esc(v)}" target="_blank" rel="noopener">datasheet ↗</a>`]])}`;
    }
    case 'architecture': return `<div class="diagram mb"><img alt="System block diagram for ${esc(c.title)}" data-diagram="/api/projects/${encodeURIComponent(c.slug)}/diagram.svg"></div>
      <div class="grid g2"><div class="card"><h3>Subsystems</h3>${c.architecture.subsystems.map(s => `<div class="issue info"><b>${esc(s.name)}</b><p>${esc(s.role)}</p></div>`).join('')}</div>
      <div class="card"><h3>Data flow</h3><ol>${c.architecture.data_flow.map(x => `<li style="margin-bottom:8px">${esc(x)}</li>`).join('')}</ol>
      <h4 class="mt">Communication architecture</h4>${keyVal(c.architecture.communication_architecture)}
      <h4 class="mt">Power architecture</h4>${keyVal(c.architecture.power_architecture)}
      <h4 class="mt">Cloud & storage</h4><p class="muted">${esc(c.architecture.cloud_integration)}</p><p class="muted">${esc(c.architecture.storage_processing)}</p></div></div>`;
    case 'circuit': {
      const ci = c.circuit;
      return `<div class="grid g2 mb"><div class="card"><h3>Selected board</h3><p><b>${esc(ci.selected_board.name)}</b></p><p class="tiny muted">Logic: ${ci.selected_board.logic_voltage} V · <a href="${esc(ci.selected_board.documentation)}" target="_blank" rel="noopener">official docs ↗</a></p>
        <p class="tiny muted">${esc(ci.selected_board.notes)}</p><h4 class="mt">Interfaces</h4><div class="chip-row">${ci.interfaces.map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div>
        <h4 class="mt">Pin mapping</h4><pre>${esc(JSON.stringify(ci.pin_mapping, null, 2))}</pre></div>
        <div class="card"><h3>Electrical checks</h3><h4>Pull-ups / pull-downs</h4><ul>${ci.pullups_pulldowns.map(x => `<li>${esc(x)}</li>`).join('') || '<li class="muted">None required by the catalog rules.</li>'}</ul>
        <h4 class="mt">Level shifting</h4><ul>${ci.level_shifting.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Power & current</h4><ul>${ci.power_current_considerations.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Uncertain parts / verification needed</h4><ul>${ci.uncertain_parts.map(x => `<li>${esc(x)}</li>`).join('') || '<li>None from the catalog rules.</li>'}</ul></div></div>
      <div class="section-title">Wiring table</div>
      ${table(ci.connections, [['part', 'Component'], ['part_pin', 'Pin'], ['to', 'Connect to'], ['note', 'Why / note']])}
      <div class="section-title">Why these connections</div><div class="card"><ul>${ci.why_connections.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
      <div class="section-title">Rule-based validation</div>${issuesHtml(ci.validation.issues)}`;
    }
    case 'procedure': return `<div class="card">${c.procedure.map(s => `<div class="step" data-n="${s.step}"><b>${esc(s.title)}</b><ul>${s.details.map(d => `<li>${esc(d)}</li>`).join('')}</ul><p class="tiny" style="color:var(--green)">✓ ${esc(s.verification)}</p></div>`).join('')}</div>`;
    case 'code': {
      const f = c.code;
      return `<div class="notice warn mb"><b>${esc(f.status)}</b> — never claim hardware testing without a dated test record.</div>
      <div class="grid g2 mb"><div class="card"><h4>Toolchain</h4><p class="tiny muted">${esc(f.board_core)}</p><h4>Libraries</h4><ul>${f.libraries.map(x => `<li>${esc(x)}</li>`).join('') || '<li>Core libraries only</li>'}</ul>
      <h4>Upload</h4><p class="tiny muted">${esc(f.upload_instructions)}</p></div>
      <div class="card"><h4>Configuration placeholders</h4><div class="chip-row">${f.config_placeholders.map(x => `<span class="tag">${esc(x)}</span>`).join('') || '<span class="muted tiny">None</span>'}</div>
      <h4 class="mt">Expected output</h4><pre style="max-height:150px">${esc(f.sample_log)}</pre>
      <h4 class="mt">Review notes</h4><ul>${f.review_notes.map(x => `<li class="tiny">${esc(x)}</li>`).join('')}</ul></div></div>
      <div class="row between mb"><h3>${esc(f.language)} — complete source</h3><button class="btn sm" id="copy-code">Copy code</button></div>
      <pre id="full-code">${esc(f.code)}</pre>`;
    }
    case 'troubleshooting': return `<div class="grid g2">${c.troubleshooting.map(t => `<div class="issue ${t.issue.toLowerCase().includes('project-specific') ? 'warning' : 'info'}"><b>${esc(t.issue)}</b>
      <p><b>Symptoms:</b> ${esc(t.symptoms)}</p><p><b>Causes:</b> ${esc(t.possible_causes)}</p>
      <p><b>Diagnostics:</b> ${esc(t.diagnostics)}</p><p><b>Fix:</b> ${esc(t.corrective_actions)}</p></div>`).join('')}</div>`;
    case 'testing': {
      const t = c.testing;
      return `<div class="grid g2 mb"><div class="card"><h3>Pre-power checklist</h3><ul>${t.pre_power_checklist.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Safety</h4><ul>${t.safety_considerations.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div class="card"><h3>Functional tests</h3>${t.functional_tests.map((x, i) => `<div class="issue ok"><b>${i + 1}. ${esc(x.name)}</b><p>${esc(x.procedure)}</p><p><b>Expected:</b> ${esc(x.expected_result)}</p></div>`).join('')}
        <h4 class="mt">Error conditions</h4><ul>${t.error_conditions.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Performance checks</h4><ul>${t.performance_checks.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></div>
        <div class="section-title">Component tests</div>${table(t.component_tests, [['component', 'Component'], ['test', 'Test'], ['expected', 'Expected'], ['calibration', 'Calibration']])}
        <div class="section-title">Acceptance criteria & validation status</div><div class="card"><ul>${t.acceptance_criteria.map(x => `<li>${esc(x)}</li>`).join('')}</ul>${keyVal(t.validation_status)}</div>`;
    }
    case 'deliverables': {
      const d = c.deliverables;
      return `<div class="grid g2"><div class="card"><h3>Final components</h3><ul>${d.final_components.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Setup & operating instructions</h4><ol>${d.setup_operating_instructions.map(x => `<li>${esc(x)}</li>`).join('')}</ol>
        <h4 class="mt">Final code</h4><p class="mono">${esc(d.final_code.filename)} · ${esc(d.final_code.language)} · ${esc(d.final_code.status)}</p></div>
        <div class="card"><h3>Expected results</h3><ul>${d.expected_results.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Limitations</h4><ul>${d.limitations.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
        <h4 class="mt">Improvement opportunities</h4><ul>${d.improvement_opportunities.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div></div>
        <div class="section-title">References (real documentation)</div><div class="card"><ul>${d.references.map(r => `<li><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a> <span class="tag">${esc(r.type)}</span></li>`).join('')}</ul></div>`;
    }
    case 'quality': {
      const q = c.quality;
      return `<div class="grid g2"><div class="card"><h3>Quality status: ${badge(q.status, 'amber')}</h3><p class="muted">${esc(q.evidence)}</p>
        <h4 class="mt">Allowed statuses</h4><div class="chip-row">${q.allowed_statuses.map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div>
        <h4 class="mt">Minimum for publication</h4><p class="muted">${esc(q.minimum_for_publication)}</p></div>
        <div class="card"><h3>Completeness checks</h3>${q.checks.map(x => `<div class="issue ${x.passed ? 'ok' : 'warning'}"><b>${x.passed ? 'PASS' : 'FAIL'} — ${esc(x.name)}</b></div>`).join('')}</div></div>`;
    }
  }
  return '';
}

function issuesHtml(issues) {
  if (!issues?.length) return '<div class="notice ok">No rule violations detected.</div>';
  return issues.map(i => `<div class="issue ${esc(i.severity)}"><b>${esc(i.severity.toUpperCase())} · ${esc(i.code)}</b><p>${esc(i.message)}</p>${i.fix ? `<p style="color:var(--green)">Fix: ${esc(i.fix)}</p>` : ''}</div>`).join('');
}

/* ---------------------------------------------------------------- learning */
async function viewLearning() {
  const d = await api('/api/learning');
  $('#view').innerHTML = pageHead('Learning basics',
    `${d.modules.length} short modules to build safe, verifiable IoT prototypes. Available on the Free plan.`) +
    `<div class="notice mb">${esc(d.note)}</div>
    <div class="grid g2">${d.modules.map((x, i) => `<div class="card">
      <div class="row between"><b>${i + 1}. ${esc(x.title)}</b>${badge(x.minutes + ' min', 'cyan')}</div>
      <p class="tiny muted">${esc(x.objective)}</p>
      <ul>${x.points.map(p => `<li class="tiny">${esc(p)}</li>`).join('')}</ul>
      <details class="mt-s"><summary class="tiny" style="cursor:pointer;color:var(--cyan)">Check your understanding</summary>
        <p class="tiny mt-s"><b>Q:</b> ${esc(x.quiz.q)}</p><p class="tiny"><b>A:</b> ${esc(x.quiz.a)}</p></details>
      <h4 class="mt">References</h4><ul>${x.refs.map(r => `<li class="tiny"><a href="${esc(r)}" target="_blank" rel="noopener">${esc(r)}</a></li>`).join('')}</ul>
    </div>`).join('')}</div>`;
}

/* ---------------------------------------------------------------- tools */
const TOOL_FORMS = {
  project_generator: [
    { k: 'problem', l: 'Problem / project description', t: 'textarea', ph: 'e.g. A farmer needs to know when a remote water tank is running low…' },
    { k: 'components', l: 'Available components', t: 'text', ph: 'ESP32, ultrasonic sensor, battery, LoRa module' },
    { k: 'budget', l: 'Budget', t: 'text', ph: '$80' },
    { k: 'skill', l: 'Skill level', t: 'select', opts: ['Beginner', 'Intermediate', 'Advanced'] },
    { k: 'outcome', l: 'Desired outcome', t: 'text' },
    { k: 'platform', l: 'Target platform', t: 'select', opts: ['esp32', 'arduino', 'raspberry pi', 'pico', 'esp8266'] },
    { k: 'comms', l: 'Connectivity', t: 'select', opts: ['wifi_mqtt', 'wifi_http', 'lora', 'gsm', 'ble', 'espnow', 'serial', 'sd_local'] },
    { k: 'regenerate_parts', l: 'Regenerate only these sections (comma separated)', t: 'csv', ph: 'code,circuit,testing' },
    { k: 'run_id', l: 'Previous run id (for partial regeneration)', t: 'text' }
  ],
  circuit_designer: [
    { k: 'board', l: 'Board key', t: 'select', opts: ['esp32', 'esp32s3', 'esp8266', 'uno', 'picow', 'rpi4', 'esp32cam'] },
    { k: 'components', l: 'Components', t: 'text', ph: 'bme280, hcsr04, relay, oled' },
    { k: 'comms', l: 'Communication', t: 'select', opts: ['wifi_mqtt', 'wifi_http', 'serial', 'lora', 'rs485'] },
    { k: 'pin_overrides', l: 'Pin overrides (JSON, optional)', t: 'json', ph: '{"bme280":{"SDA":"21"}}' }
  ],
  code_engineer: [
    { k: 'mode', l: 'Mode', t: 'select', opts: ['generate', 'review', 'explain', 'refactor'] },
    { k: 'platform', l: 'Platform', t: 'select', opts: ['esp32', 'esp32-s3', 'arduino', 'raspberry pi', 'pico', 'esp8266'] },
    { k: 'comms', l: 'Connectivity', t: 'select', opts: ['wifi_mqtt', 'wifi_http', 'serial', 'lora'] },
    { k: 'components', l: 'Components / sensors', t: 'text', ph: 'bme280, relay' },
    { k: 'description', l: 'Description', t: 'textarea' },
    { k: 'code', l: 'Existing code (for review / explain / refactor)', t: 'textarea' }
  ],
  debugging: [
    { k: 'error', l: 'Compiler error / log / test failure', t: 'textarea', ph: 'Paste the exact error output…' },
    { k: 'symptom', l: 'Symptom', t: 'text' },
    { k: 'circuit', l: 'Circuit description', t: 'text' },
    { k: 'session_key', l: 'Session key (same key tracks attempts)', t: 'text', ph: 'pump-node-1' },
    { k: 'record_fix', l: 'Record a fix you just tried', t: 'text' },
    { k: 'outcome', l: 'Outcome', t: 'select', opts: ['unverified', 'fixed', 'failed'] }
  ],
  innovation: [{ k: 'topic', l: 'Technology / problem to research', t: 'textarea', ph: 'Low-cost CO2 sensing for classrooms' }],
  comparison: [
    { k: 'items', l: 'Items to compare (JSON array)', t: 'json', ph: '[{"name":"Design A","cost":4,"power":6,"accuracy":5,"reliability":7,"components":5,"architecture":7,"security":4},{"name":"Design B","cost":7,"power":4,"accuracy":8,"reliability":6,"components":6,"architecture":8,"security":7}]' }
  ],
  startup_lab: [
    { k: 'industry', l: 'Industry', t: 'text', ph: 'agriculture' }, { k: 'problem', l: 'Customer problem', t: 'textarea' },
    { k: 'budget', l: 'Budget', t: 'text', ph: '$5,000' }, { k: 'region', l: 'Region', t: 'text' }
  ],
  research: [{ k: 'query', l: 'Research query', t: 'textarea', ph: 'ESP32 ADC2 Wi-Fi limitation and I2C pull-ups' }],
  device_monitoring: [
    { k: 'action', l: 'Action', t: 'select', opts: ['status', 'diagnose', 'simulate'] },
    { k: 'device_id', l: 'Device id (for simulate)', t: 'text' }
  ],
  project_docs: [
    { k: 'action', l: 'Action', t: 'select', opts: ['report', 'milestone', 'version', 'decision', 'test', 'note', 'code'] },
    { k: 'workspace_id', l: 'Workspace id (blank = most recent)', t: 'text' },
    { k: 'title', l: 'Title', t: 'text' }, { k: 'detail', l: 'Detail / test result', t: 'textarea' },
    { k: 'status', l: 'Status', t: 'select', opts: ['open', 'passed', 'failed', 'done'] },
    { k: 'code', l: 'Code snapshot', t: 'textarea' }
  ]
};

function formHtml(fields) {
  return fields.map(f => {
    const id = 'tf-' + f.k;
    if (f.t === 'textarea') return `<label class="field"><span>${esc(f.l)}</span><textarea id="${id}" placeholder="${esc(f.ph || '')}"></textarea></label>`;
    if (f.t === 'select') return `<label class="field"><span>${esc(f.l)}</span><select id="${id}">${f.opts.map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join('')}</select></label>`;
    return `<label class="field"><span>${esc(f.l)}</span><input id="${id}" placeholder="${esc(f.ph || '')}"></label>`;
  }).join('');
}
function readForm(fields) {
  const body = {};
  for (const f of fields) {
    const v = $('#tf-' + f.k)?.value?.trim(); if (!v) continue;
    if (f.t === 'csv') body[f.k] = v.split(',').map(x => x.trim()).filter(Boolean);
    else if (f.t === 'json') { try { body[f.k] = JSON.parse(v); } catch (e) { throw new Error(`Invalid JSON in "${f.l}"`); } }
    else if (f.k === 'device_id' || f.k === 'workspace_id' || f.k === 'run_id') body[f.k] = Number(v) || undefined;
    else body[f.k] = v;
  }
  return body;
}

async function viewTools() {
  const d = await api('/api/tools');
  const connected = [
    ['AI Project Builder', '#/invention', 'Develop requirements, architecture and a constrained new design with a configured model.'],
    ['AI Invention Lab', '#/invention', 'Explore novel concepts, explicit unknowns and trade-offs. Save new designs or review iteration proposals.'],
    ['Advanced Circuit Studio', '#/studio', 'Arrange components, edit exact-pin connections, inspect definitions, save versions and synchronize pin configuration.'],
    ['Circuit & Hardware Validator', '#/studio', 'Rule-check connections, voltage rails, protected analog inputs, power drivers and pin assignments.'],
    ['AI Code Engineer', '#/code', 'Edit saved firmware, synchronize pins, review driver rebuild diffs and request context-aware online help.'],
    ['Debugging & Repair Center', '#/tools/debugging', 'Persist debugging attempts, inspect logs and source, avoid repeating failed fixes.'],
        ['Innovation Gap Analyzer', '#/tools/innovation', 'Separate documented limits from hypotheses and proposed technical improvements.'],
    ['Existing Project Comparator', '#/tools/comparison', 'Compare saved/library design characteristics and expose engineering gaps.'],
    ['Startup & Opportunity Studio', '#/tools/startup_lab', 'Transparent assumptions, viability criteria and market validation plans, not success probabilities.'],
    ['Device Monitoring & Diagnostics', '#/tools/device_monitoring', 'HTTP telemetry ingestion, source-labelled real/simulated samples, logs and diagnostics.'],
    ['Professional Reports & Exports', '#/projects', 'Export exact saved project state, connection SVGs, wiring, JSON and source.'],
    ['Persistent Project Workspace', '#/projects', 'Private UUID projects, saved requirements, circuits, code, research, tests and immutable revisions.'],
      ];
  $('#view').innerHTML = pageHead('Pro Workspace', 'Fourteen connected engineering workflows. Online-model tools require a configured provider; deterministic tools are explicitly labelled.') +
    `<div class="grid g3">${connected.map((t,i)=>`<a class="tool-card" href="${t[1]}"><div class="row between"><span class="tool-num">${String(i+1).padStart(2,'0')} / WORKFLOW</span>${badge(state.me.entitlement.is_pro?'AVAILABLE':'PRO',state.me.entitlement.is_pro?'green':'violet')}</div><div class="t">${t[0]}</div><div class="d">${t[2]}</div></a>`).join('')}</div>
    <details class="card mt"><summary>Retained deterministic engineering tools & existing run history</summary><div class="grid g3 mt">${d.tools.map(t=>`<a class="btn" href="#/tools/${t.key}">${esc(t.name)}</a>`).join('')}</div><p class="tiny muted mt">These legacy catalog/rule-based workflows remain available. Online enrichment is optional and provider failures are displayed separately, never fabricated as a model answer.</p></details>`;
}

function genericResult(key, val, depth = 0) {
  if (val === null || val === undefined) return '';
  if (typeof val === 'string' && (key === 'code' || key === 'report_markdown' || key === 'code_config' || key === 'answer' || key === 'llm_answer' || key === 'llm_narrative' || val.includes('\n'))) {
    return `<div class="result-block"><h4>${esc(key.replace(/_/g, ' '))}</h4><pre style="max-height:340px">${esc(val)}</pre></div>`;
  }
  if (Array.isArray(val)) {
    if (!val.length) return '';
    if (val.every(x => typeof x === 'string' || typeof x === 'number')) {
      return `<div class="result-block"><h4>${esc(key.replace(/_/g, ' '))}</h4><ul>${val.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
    }
    if (depth < 2) {
      const cols = [...new Set(val.flatMap(x => typeof x === 'object' ? Object.keys(x) : []))].slice(0, 6);
      return `<div class="result-block"><h4>${esc(key.replace(/_/g, ' '))} (${val.length})</h4>${table(val, cols.map(c => [c, c.replace(/_/g, ' '), (v) => typeof v === 'object' ? `<span class="mono tiny">${esc(JSON.stringify(v))}</span>` : nl2br(v)]))}</div>`;
    }
  }
  if (typeof val === 'object' && depth < 2) {
    return `<div class="result-block"><h4>${esc(key.replace(/_/g, ' '))}</h4>${Object.entries(val).map(([k, v]) => genericResult(k, v, depth + 1)).join('')}</div>`;
  }
  return `<div class="result-block"><h4>${esc(key.replace(/_/g, ' '))}</h4><p>${nl2br(typeof val === 'object' ? JSON.stringify(val) : val)}</p></div>`;
}

async function renderToolResult(name, r) {
  const skip = new Set(['tool', 'mode', 'ai_provider', 'model', 'run_id', 'ai_note', 'ai_warning', 'llm_narrative']);
  let html = `<div class="row between mb"><div class="row">${badge('run #' + r.run_id, 'cyan')}${badge(r.mode || 'offline', r.mode === 'openai_compatible' ? 'green' : 'amber')}${r.ai_provider ? badge(r.ai_provider, 'violet') : ''}</div>
    <button class="btn sm" id="dl-result">⬇ Download full result (JSON)</button></div>
    ${r.ai_warning ? `<div class="notice warn mb">${esc(r.ai_warning)}</div>` : ''}
    ${r.ai_note ? `<div class="notice mb">${esc(r.ai_note)}</div>` : ''}
    ${r.llm_narrative ? `<div class="card mb"><h4>LLM narrative</h4><p>${nl2br(r.llm_narrative)}</p></div>` : ''}`;

  if (name === 'project_generator') {
    const v = r.validation || {};
    html += `<div class="grid g4 mb">${stat(r.inputs?.components?.length ?? 0, 'Components')}${stat(v.summary?.errors ?? 0, 'Validation errors')}${stat(v.summary?.warnings ?? 0, 'Warnings')}${stat(r.quality_status || 'Draft', 'Quality')}</div>
      <div class="card mb"><h3>${esc(r.title)}</h3><p class="muted">${esc(r.spec?.problem || '')}</p>
      <p class="tiny muted">Platform: ${esc(r.inputs?.platform)} · Transport: ${esc(r.inputs?.comms)} · Budget: ${esc(r.inputs?.budget)} · Skill: ${esc(r.inputs?.skill)}</p>
      ${r.inputs?.previous_run_merged ? badge('Previous run merged for partial regeneration', 'green') : ''}
      <div class="chip-row mt">${(r.inputs?.components || []).map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div></div>`;
    html += `<div class="section-title">Generated sections</div><div class="card">${Object.entries(r.sections || {}).map(([k, v2]) => genericResult(k, v2, 1)).join('')}</div>`;
    html += `<div class="section-title">Circuit validation</div>${issuesHtml(v.issues || [])}`;
  } else if (name === 'circuit_designer') {
    html += `<div class="grid g4 mb">${stat(r.summary?.component_count ?? 0, 'Components')}${stat(r.summary?.errors ?? 0, 'Errors')}${stat(r.summary?.warnings ?? 0, 'Warnings')}${stat(r.passed ? 'PASS' : 'FAIL', 'Verdict')}</div>
      <div class="card mb"><h3>${esc(r.board)}</h3><div class="chip-row">${(r.components || []).map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div>
      <h4 class="mt">Checks performed</h4><ul>${(r.checks_performed || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>
      <div class="section-title">Issues & fixes</div>${issuesHtml(r.issues)}
      <div class="section-title">Wiring table</div>${table(r.wiring_table, [['part', 'Component'], ['part_pin', 'Pin'], ['to', 'Connect to'], ['note', 'Note']])}
      <div class="section-title">Matching firmware configuration</div><pre>${esc(r.code_config || '')}</pre>`;
  } else if (name === 'code_engineer') {
    if (r.code) html += `<div class="card mb"><h3>${esc(r.language)} · ${esc(r.mode)}</h3><p class="tiny muted">${esc(r.code_status)}</p>
      <div class="row"><button class="btn sm" id="copy-gen">Copy generated code</button>${badge(r.platform || '', 'cyan')}</div>
      <pre class="mt">${esc(r.code)}</pre><h4 class="mt">Libraries</h4><ul>${(r.libraries || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      <h4 class="mt">Placeholders</h4><div class="chip-row">${(r.config_placeholders || []).map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div></div>`;
    if (r.findings) html += `<div class="section-title">Static review findings (${r.finding_count})</div>${r.findings.map(f => `<div class="issue ${f.severity === 'critical' ? 'error' : f.severity === 'ok' ? 'ok' : 'warning'}"><b>${esc(f.severity.toUpperCase())} · ${esc(f.title)}</b><p>${esc(f.detail)}</p><p style="color:var(--green)">Fix: ${esc(f.fix)}</p></div>`).join('')}`;
    if (r.explanation?.length) html += `<div class="section-title">Line-by-line explanation</div><div class="card"><ol>${r.explanation.map(x => `<li class="mono tiny">${esc(x)}</li>`).join('')}</ol></div>`;
    if (r.disclaimer) html += `<div class="notice warn mt">${esc(r.disclaimer)}</div>`;
  } else if (name === 'debugging') {
    html += `<div class="grid g3 mb">${stat(r.diagnoses?.length ?? 0, 'Diagnoses')}${stat(r.attempts_tracked ?? 0, 'Attempts tracked')}${stat(r.avoided_repeated_fixes ?? 0, 'Repeats avoided')}</div>`;
    html += (r.diagnoses || []).map(d => `<div class="issue ${d.repeated_fix_warning ? 'warning' : 'info'}"><b>${esc(d.issue)}</b>
      <p><b>Evidence:</b> ${esc(d.evidence)} · ${esc(d.confidence)}</p>
      <p><b>Diagnostics:</b> ${esc(d.diagnostics.join('; '))}</p>
      <p><b>Fixes:</b> ${esc(d.fixes.join('; '))}</p>
      ${d.previously_tried?.length ? `<p style="color:var(--amber)">Already tried (not repeated): ${esc(d.previously_tried.join('; '))}</p>` : ''}</div>`).join('');
    html += `<div class="section-title">Safe static tests</div>${table(r.static_tests, [['name', 'Test'], ['result', 'Result', v => badge(v, v === 'PASS' ? 'green' : 'amber')], ['note', 'Note']])}`;
    html += `<div class="notice mt">${esc((r.next_steps || []).join(' · '))} ${esc(r.disclaimer || '')}</div>`;
  } else if (name === 'innovation' || name === 'research') {
    html += `<div class="card mb"><h3>${esc(r.topic || r.query)}</h3><p class="muted">${esc(r.research_summary || r.method)}</p></div>`;
    if (r.sources) html += `<div class="section-title">Sources (real documentation only)</div>${table(r.sources, [['id', 'ID'], ['title', 'Title'], ['url', 'URL', v => `<a href="${esc(v)}" target="_blank" rel="noopener">open ↗</a>`]])}`;
    if (r.documented_limitations) html += `<div class="section-title">Documented limitations</div><div class="card"><ul>${r.documented_limitations.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
    if (r.engineering_directions) html += `<div class="section-title">Engineering directions</div><div class="grid g2">${r.engineering_directions.map(d => `<div class="card soft"><b>${esc(d.direction)}</b><p class="tiny muted mt-s">${esc(d.why)}</p><p class="tiny"><b>MVP:</b> ${esc(d.mvp)}</p><p class="tiny"><b>Risk:</b> ${esc(d.risk)}</p></div>`).join('')}</div>`;
    if (r.facts_vs_hypotheses) html += `<div class="section-title">Facts vs hypotheses</div><div class="grid g2"><div class="card"><h4>Facts</h4><ul>${r.facts_vs_hypotheses.facts.map(x => `<li>${esc(x.statement)}</li>`).join('')}</ul></div><div class="card"><h4>Hypotheses</h4><ul>${r.facts_vs_hypotheses.hypotheses.map(x => `<li>${esc(x.statement)}</li>`).join('')}</ul></div></div>`;
    if (r.report_markdown) html += `<div class="section-title">Research report</div><div class="result-block"><pre>${esc(r.report_markdown)}</pre><button class="btn sm mt-s" id="dl-md">⬇ Download .md</button></div>`;
    html += `<div class="notice mt">${esc(r.citation_policy || '')}</div>`;
  } else if (name === 'comparison') {
    html += `<div class="card mb"><h3>Weighted comparison</h3>${table(r.table, [['name', 'Item'], ['cost', 'Cost'], ['power', 'Power'], ['accuracy', 'Accuracy'], ['reliability', 'Reliability'], ['security', 'Security'], ['weighted_score', 'Score', v => `<b style="color:var(--cyan)">${esc(v)}</b>`]])}
      <p class="tiny muted mt">Ranking: ${esc((r.ranking || []).join(' → '))}</p></div>
      <div class="section-title">Gap analysis</div>${table(r.gaps, [['item', 'Item'], ['criterion', 'Criterion'], ['weight', 'Weight'], ['current', 'Current'], ['best_in_set', 'Best'], ['action', 'Action']])}
      <div class="card mt"><h4>Assumptions</h4><ul>${(r.assumptions || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><p class="tiny dim">${esc(r.disclaimer)}</p></div>`;
  } else if (name === 'startup_lab') {
    html += `<div class="grid g3">${(r.opportunities || []).map(o => `<div class="card"><div class="row between"><b>${esc(o.name)}</b><span class="score">${esc(o.viability_score)}</span></div>
      <p class="tiny muted">${esc(o.customer_problem)}</p><p class="tiny"><b>MVP:</b> ${esc(o.mvp)}</p><p class="tiny"><b>Cost:</b> ${esc(o.cost_band)}</p>
      <p class="tiny"><b>Alternatives:</b> ${esc((o.alternatives || []).join(', '))}</p>
      <pre style="max-height:150px">${esc(JSON.stringify(o.score_breakdown, null, 2))}</pre>
      <p class="tiny dim">${esc(o.score_meaning)}</p></div>`).join('')}</div>
      <div class="card mt"><h4>Validation plan</h4><ul>${(r.validation_plan || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><p class="tiny dim">${esc(r.disclaimer)}</p></div>`;
  } else if (name === 'project_docs') {
    html += `<div class="card mb"><h3>Report from saved workspace state</h3><p class="tiny muted">Workspace: ${esc(r.workspace?.name || 'none')} · ${esc(r.event_count || 0)} saved events</p>
      <p class="tiny muted">${esc(r.note || '')}</p>${r.download ? `<a class="btn sm" href="${esc(r.download)}">⬇ Download report.md</a>` : ''}</div>
      <pre>${esc(r.report_markdown || '')}</pre>`;
  } else if (name === 'device_monitoring') {
    html += await deviceMonitoringHtml(r);
  } else {
    html += Object.entries(r).filter(([k]) => !skip.has(k)).map(([k, v]) => genericResult(k, v)).join('');
  }
  return html;
}

async function deviceMonitoringHtml(r) {
  let devices = r.devices || [];
  try { devices = (await api('/api/devices')).devices; } catch (e) { }
  let samples = [], chart = '';
  if (devices.length) {
    try {
      const t = await api('/api/telemetry/' + devices[0].id);
      samples = t.samples;
      chart = lineChart(samples);
    } catch (e) { }
  }
  return `<div class="grid g2 mb"><div class="card"><h3>Integrations</h3>
      <p class="tiny">HTTP ingest: ${badge(r.integrations?.http_ingest?.enabled ? 'ENABLED' : 'DISABLED', 'green')}</p>
      <p class="tiny">MQTT: ${badge(r.integrations?.mqtt?.configured ? 'CONFIGURED' : 'NOT CONFIGURED', r.integrations?.mqtt?.configured ? 'green' : 'amber')}</p>
      <p class="tiny muted">${esc(r.integrations?.mqtt?.message || '')}</p>
      <p class="tiny dim">${esc(r.real_vs_simulated)}</p></div>
    <div class="card"><h3>Register a device</h3><div class="row"><input id="dev-name" placeholder="Device name" style="flex:1"><button class="btn primary sm" id="dev-create">Create</button></div>
      <div id="dev-token" class="mt"></div></div></div>
    <div class="section-title">Devices (${devices.length})</div>
    ${devices.length ? table(devices, [['id', 'ID'], ['name', 'Name'], ['token_prefix', 'Token'], ['last_seen_at', 'Last seen', v => v ? fmtDate(v) : 'never'], ['id', 'Actions', v => `<button class="btn sm" data-dsim="${v}">Simulate</button> <button class="btn sm" data-ddiag="${v}">Diagnose</button>`]]) : '<div class="empty">No devices yet. Create one to get an ingest token.</div>'}
    <div class="section-title">Telemetry — ${esc(devices[0]?.name || 'no device')}</div>
    ${samples.length ? `<div class="card">${chart}<p class="tiny muted mt">${samples.filter(s => s.source === 'simulated').length} simulated / ${samples.filter(s => s.source === 'real').length} real samples shown.</p></div>` : '<div class="empty">No samples yet. POST to <code>/api/ingest/&lt;token&gt;</code> or use Simulate (explicitly labelled).</div>'}
    ${(r.alerts || []).map(a => `<div class="issue ${a.severity === 'warning' ? 'warning' : 'info'}"><b>${esc(a.device)} · ${esc(a.message)}</b><p>${esc(a.action)}</p></div>`).join('')}
    <div class="section-title">Ingest example</div><pre>curl -X POST ${esc(location.origin)}/api/ingest/YOUR_DEVICE_TOKEN \
  -H 'Content-Type: application/json' \
  -d '{"samples":[{"key":"temperature_c","value":24.6,"unit":"C"}]}'</pre>`;
}

function lineChart(samples) {
  const pts = samples.slice(-120);
  if (pts.length < 2) return '<p class="muted tiny">Need at least two samples to draw a chart.</p>';
  const vals = pts.map(p => p.value), min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const w = 900, h = 200, pad = 22;
  const xy = pts.map((p, i) => [pad + i * (w - 2 * pad) / (pts.length - 1), h - pad - (p.value - min) / span * (h - 2 * pad)]);
  const path = xy.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const dots = xy.map((p, i) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.5" fill="${pts[i].source === 'simulated' ? '#fbbf24' : '#22d3ee'}"><title>${esc(pts[i].key)}: ${pts[i].value} ${esc(pts[i].unit)} (${pts[i].source})</title></circle>`).join('');
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:210px;background:#081222;border:1px solid var(--line);border-radius:10px">
    <text x="${pad}" y="15" fill="#93a4bd" font-size="11">max ${max.toFixed(2)}</text>
    <text x="${pad}" y="${h - 6}" fill="#93a4bd" font-size="11">min ${min.toFixed(2)} · cyan = real, amber = simulated</text>
    <path d="${path}" fill="none" stroke="#22d3ee" stroke-width="2"/>${dots}</svg>`;
}

async function viewTool(name) {
  const meta = (await api('/api/tools')).tools.find(t => t.key === name);
  if (!meta) { $('#view').innerHTML = '<div class="empty">Unknown tool.</div>'; return; }
  const fields = TOOL_FORMS[name] || [{ k: 'query', l: 'Input', t: 'textarea' }];
  const runs = await api('/api/tools/runs').catch(() => ({ runs: [] }));
  $('#view').innerHTML = `<div class="row between mb"><div><a class="tiny muted" href="#/tools">← Pro Workspace</a><h1 style="margin-top:6px">${esc(meta.name)}</h1><p class="muted" style="margin:0">${esc(meta.description)}</p></div>
    <div class="row">${meta.allowed ? badge('UNLOCKED', 'green') : '<a class="btn primary sm" href="#/upgrade">Unlock with Pro</a>'}</div></div>
    <div class="grid g2"><div class="card"><h3>Input</h3>${formHtml(fields)}
      <div class="row"><button class="btn primary" id="run-btn" ${meta.allowed ? '' : 'disabled'}>Run tool</button>
      <button class="btn sm" id="dl-form">Download form as JSON</button></div></div>
      <div class="card"><h3>How this tool works</h3>
        <p class="tiny muted">Runs on the deterministic NEXUS offline engine: real component catalog, rule-based circuit validation, curated documentation corpus and your saved data. No fabricated sources or success probabilities.</p>
        ${state.config?.ai?.configured ? '<div class="notice ok mt">A live LLM provider is configured; an optional narrative layer will be added.</div>' : '<div class="notice mt">No live AI credentials configured. The offline engine is fully functional.</div>'}
        <h4 class="mt">Recent runs</h4>${runs.runs.filter(x => x.tool === name).length ? table(runs.runs.filter(x => x.tool === name).slice(0, 5), [['id', 'Run'], ['mode', 'Mode'], ['created_at', 'When', v => fmtDate(v)]]) : '<p class="muted tiny">No runs yet.</p>'}
      </div></div>
    <div class="section-title">Result</div><div id="tool-result"><div class="empty">Run the tool to see a structured engineering result.</div></div>`;
  $('#dl-form').onclick = () => { try { download(name + '-input.json', JSON.stringify(readForm(fields), null, 2)); } catch (e) { toast(e, 'err'); } };
  $('#run-btn').onclick = async () => {
    let body; try { body = readForm(fields); } catch (e) { toast(e, 'err'); return; }
    $('#run-btn').disabled = true; $('#tool-result').innerHTML = spinner();
    try {
      const r = await api('/api/tools/' + name, { method: 'POST', body });
      const out = r.result;
      $('#tool-result').innerHTML = await renderToolResult(name, out);
      $('#dl-result')?.addEventListener('click', () => download(name + '-run-' + out.run_id + '.json', JSON.stringify(out, null, 2)));
      $('#dl-md')?.addEventListener('click', () => download('nexus-research-report.md', out.report_markdown || '', 'text/markdown'));
      $('#copy-gen')?.addEventListener('click', () => { copy(out.code || ''); toast('Code copied', 'ok'); });
      bindDeviceActions();
      toast('Tool completed', 'ok');
    } catch (e) {
      $('#tool-result').innerHTML = `<div class="notice danger"><b>${esc(e.message)}</b>${e.status === 403 ? '<p><a href="#/upgrade">Upgrade to Pro →</a></p>' : ''}</div>`;
    }
    $('#run-btn').disabled = false;
  };
}

function bindDeviceActions() {
  $('#dev-create')?.addEventListener('click', async () => {
    try {
      const r = await api('/api/devices', { method: 'POST', body: { name: $('#dev-name').value || 'Device' } });
      $('#dev-token').innerHTML = `<div class="notice ok"><b>Token (copy now):</b><pre style="margin:8px 0">${esc(r.token)}</pre><button class="btn sm" data-copy="${esc(r.token)}">Copy token</button></div>`;
      bindDeviceActions();
      toast('Device created', 'ok');
    } catch (e) { toast(e, 'err'); }
  });
  $$('[data-dsim]').forEach(b => b.onclick = () => simDevice(Number(b.dataset.dsim)));
  $$('[data-ddiag]').forEach(b => b.onclick = () => diagDevice(Number(b.dataset.ddiag)));
  $$('[data-copy]').forEach(b => b.onclick = () => { copy(b.dataset.copy); toast('Token copied', 'ok'); });
}

async function simDevice(id) {
  try {
    await api('/api/tools/device_monitoring', { method: 'POST', body: { action: 'simulate', device_id: id } });
    toast('30 labelled SIMULATED samples stored', 'ok');
    await viewTool('device_monitoring');
  } catch (e) { toast(e, 'err'); }
}

async function diagDevice(id) {
  try {
    const r = await api('/api/tools/device_monitoring', { method: 'POST', body: { action: 'diagnose' } });
    const panel = $('#tool-result');
    if (panel) { panel.innerHTML = await renderToolResult('device_monitoring', r.result); bindDeviceActions(); }
  } catch (e) { toast(e, 'err'); }
}

/* ---------------------------------------------------------------- upgrade / subscription / account */
async function viewUpgrade() {
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
}

async function viewSubscription() {
  const d = await api('/api/subscription'), e = d.entitlement, u = state.me.usage;
  $('#view').innerHTML = pageHead('Subscription & usage', 'Your entitlement is derived from the server-side subscription record on every request.') +
    `<div class="grid g3 mb">${stat(e.plan.toUpperCase(), 'Effective plan')}${stat(e.subscription_status, 'Subscription status')}${stat(e.subscription_expires_at ? new Date(e.subscription_expires_at * 1000).toLocaleDateString() : '—', 'Expires')}</div>
    <div class="grid g2 mb"><div class="card"><h3>Entitlement details</h3>${keyVal({ 'User id': e.user_id, Role: e.role, Tier: e.tier, Plan: e.plan, Status: e.subscription_status, Provider: e.subscription_provider, Started: e.subscription_started_at ? fmtDate(e.subscription_started_at) : '—', Expires: e.subscription_expires_at ? fmtDate(e.subscription_expires_at) : 'no expiry' })}
      <h4 class="mt">Entitled features (${e.features.length})</h4><div class="chip-row">${e.features.map(f => `<span class="tag">${esc(f)}</span>`).join('')}</div></div>
      <div class="card"><h3>Usage & limits</h3>${Object.entries(u).map(([k, v]) => `<div class="mb-s"><div class="row between tiny"><span>${esc(k.replace(/_/g, ' '))}</span><b>${v.used} ${v.unlimited ? '/ unlimited' : '/ ' + v.limit}</b></div><div class="usage-bar"><i style="width:${v.unlimited ? 100 : Math.min(100, v.used / Math.max(v.limit, 1) * 100)}%"></i></div></div>`).join('')}
      <div class="notice mt">${esc(d.billing.message)}</div></div></div>
    <div class="grid g2"><div class="card"><h3>Billing management</h3><p class="muted">${esc(d.billing_management)}</p>
      ${d.billing.configured ? '<button class="btn sm" id="portal">Open provider portal (configure in Stripe dashboard)</button>' : '<p class="tiny muted">Provider portal is unavailable until payments are configured. Cancellations by an administrator are audited.</p>'}
      <h4 class="mt">Restore entitlements after a confirmed payment</h4><ol>${d.restore_process.map(x => `<li>${esc(x)}</li>`).join('')}</ol></div>
      <div class="card"><h3>Subscription history</h3>${d.subscriptions.length ? table(d.subscriptions, [['id', 'ID'], ['plan', 'Plan'], ['status', 'Status'], ['provider', 'Provider'], ['started_at', 'Started', v => fmtDate(v)], ['expires_at', 'Expires', v => fmtDate(v)]]) : '<p class="muted tiny">No subscription records yet.</p>'}
      <h4 class="mt">Policy on expiry</h4><p class="tiny muted">If a subscription expires, is cancelled or becomes invalid, Pro-only content becomes inaccessible while your personal projects, workspaces and settings are preserved. A 3-day grace window applies to past-due invoices.</p></div></div>`;
  $('#portal')?.addEventListener('click', () => toast('Configure a Stripe customer portal URL in the provider dashboard and link it here.', ''));
}

async function viewAccount() {
  const me = state.me;
  $('#view').innerHTML = pageHead('Account', 'Manage your profile and password. Roles and entitlements can never be changed here.') +
    `<div class="grid g2"><div class="card"><h3>Profile</h3>
      <label class="field"><span>Email (read-only)</span><input value="${esc(me.user.email)}" disabled></label>
      <label class="field"><span>Display name</span><input id="p-name" value="${esc(me.user.name)}"></label>
      <button class="btn primary sm" id="p-save">Save profile</button>
      <div class="notice mt">Role, plan and subscription fields submitted in a profile request are ignored and logged as a privilege-escalation attempt.</div></div>
      <div class="card"><h3>Change password</h3>
      <label class="field"><span>Current password</span><input type="password" id="pw-old"></label>
      <label class="field"><span>New password</span><input type="password" id="pw-new"></label>
      <button class="btn sm" id="pw-save">Change password</button>
      <p class="tiny muted mt">Changing your password revokes all active sessions.</p>
      <h4 class="mt">Account data</h4><p class="tiny muted">Your saved workspaces, tool runs and devices belong to your account and are preserved if Pro access ends.</p></div></div>
    <div class="card mt"><h3>Preferences (saved to your account)</h3>
      <div class="grid g3">
        <label class="field"><span>Units</span><select id="set-units"><option value="metric">metric</option><option value="imperial">imperial</option></select></label>
        <label class="field"><span>Default board</span><select id="set-board">${Object.keys({esp32:1,esp32s3:1,esp8266:1,uno:1,picow:1,rpi4:1,esp32cam:1}).map(x => `<option value="${x}">${x}</option>`).join('')}</select></label>
        <label class="field"><span>Theme</span><select id="set-theme"><option value="dark">dark</option><option value="light">light (preview)</option></select></label>
      </div>
      <label class="check"><input type="checkbox" id="set-notes"> Auto-save workspace notes</label>
      <label class="check"><input type="checkbox" id="set-notif"> In-app notifications</label>
      <button class="btn primary sm" id="set-save">Save preferences</button>
      <p class="tiny dim mt-s">These settings are stored per user on the server. Role, plan and subscription status are never accepted from this form.</p></div>`;
  api('/api/settings').then(r => {
    $('#set-units').value = r.settings.units; $('#set-board').value = r.settings.default_board;
    $('#set-theme').value = r.settings.theme; $('#set-notes').checked = !!r.settings.auto_save_notes;
    $('#set-notif').checked = !!r.settings.notifications;
  }).catch(e => toast(e, 'err'));
  $('#set-save').onclick = async () => {
    try {
      await api('/api/settings', { method: 'PATCH', body: {
        units: $('#set-units').value, default_board: $('#set-board').value,
        theme: $('#set-theme').value, auto_save_notes: $('#set-notes').checked,
        notifications: $('#set-notif').checked } });
      document.documentElement.dataset.theme = $('#set-theme').value;
      toast('Preferences saved', 'ok');
    } catch (e) { toast(e, 'err'); }
  };
  $('#p-save').onclick = async () => {
    try { await api('/api/profile', { method: 'POST', body: { name: $('#p-name').value, role: 'admin' } }); await boot(false); toast('Profile saved. Role escalation attempt ignored and audited.', 'ok'); }
    catch (e) { toast(e, 'err'); }
  };
  $('#pw-save').onclick = async () => {
    try { await api('/api/auth/password', { method: 'POST', body: { current_password: $('#pw-old').value, new_password: $('#pw-new').value } }); toast('Password changed; sign in again.', 'ok'); go('#/login'); }
    catch (e) { toast(e, 'err'); }
  };
}

/* ---------------------------------------------------------------- admin */
const ADMIN_TABS = [['overview', 'Overview'], ['projects', 'Projects'], ['free', 'The Free 15'], ['users', 'Users'],
['config', 'AI & Config'], ['usage', 'Usage & Audit'], ['analytics', 'Analytics'], ['quality', 'Quality & Health']];

async function viewAdmin() {
  if (!state.me.entitlement.is_admin) { $('#view').innerHTML = '<div class="notice danger">Administrator access required.</div>'; return; }
  const tab = state.tab['admin'] || 'overview';
  $('#view').innerHTML = pageHead('Administrative workspace', 'Every privileged operation is re-checked on the server. Secrets are never displayed.') +
    tabsHtml('admin', ADMIN_TABS, tab) + '<div id="admin-tab">' + spinner() + '</div>';
  bindTabs();
  const el = $('#admin-tab');
  try {
    if (tab === 'overview') el.innerHTML = await adminOverview();
    else if (tab === 'projects') el.innerHTML = await adminProjects();
    else if (tab === 'free') el.innerHTML = await adminFree();
    else if (tab === 'users') el.innerHTML = await adminUsers();
    else if (tab === 'config') el.innerHTML = await adminConfig();
    else if (tab === 'usage') el.innerHTML = await adminUsage();
    else if (tab === 'analytics') el.innerHTML = await adminAnalytics();
    else el.innerHTML = await adminQuality();
    bindAdmin(tab);
  } catch (e) { el.innerHTML = `<div class="notice danger">${esc(e.message)}</div>`; }
}

async function adminOverview() {
  const d = await api('/api/admin/overview');
  return `<div class="grid g4 mb">${stat(d.users, 'Users')}${stat(d.active_pro, 'Active Pro')}${stat(d.published, 'Published projects')}${stat(d.drafts, 'Drafts')}
    ${stat(d.free_projects, 'Free projects')}${stat(d.tool_runs_24h, 'Tool runs / 24h')}${stat(d.devices, 'Devices')}${stat(d.telemetry_rows, 'Telemetry rows')}</div>
    <div class="grid g2 mb"><div class="card"><h3>Integrations</h3><p class="tiny"><b>AI:</b> ${esc(d.ai.provider)} · ${d.ai.configured ? badge('configured', 'green') : badge('offline engine', 'amber')}</p>
      <p class="tiny muted">${esc(d.ai.message)}</p><p class="tiny"><b>Payments:</b> ${esc(d.payments.provider)} · ${d.payments.configured ? badge('live', 'green') : badge('not configured', 'amber')}</p>
      <p class="tiny muted">${esc(d.payments.message)}</p></div>
      <div class="card"><h3>Recent audit events</h3>${table(d.recent_audit, [['id', 'ID'], ['actor_id', 'Actor'], ['action', 'Action'], ['target', 'Target'], ['created_at', 'When', v => fmtDate(v)]])}</div></div>`;
}

async function adminProjects() {
  const d = await api('/api/admin/projects');
  state.cache.adminProjects = d.projects;
  return `<div class="row between mb"><div class="row"><input id="ap-search" placeholder="Filter projects…" style="width:260px"><button class="btn sm" id="ap-new">＋ New project</button></div><span class="tiny muted">${d.total} total</span></div>
    ${table(d.projects, [['id', 'ID'], ['title', 'Title'], ['category', 'Category'], ['difficulty', 'Level'], ['status', 'Status', v => badge(v, v === 'published' ? 'green' : 'amber')], ['quality_status', 'Quality'], ['is_free', 'Free', v => v ? '★' : ''], ['id', 'Actions', v => `<button class="btn sm" data-edit="${v}">Edit</button>`]])}`;
}

async function adminFree() {
  const d = await api('/api/admin/free-projects');
  state.cache.freeSlugs = d.designated.map(x => x.slug);
  return `<div class="notice mb">${esc(d.policy)} Reorder or replace entries and save — no code change required.</div>
    <div class="grid g2"><div class="card"><h3>Designated free projects</h3><div id="free-list" class="stack">
      ${d.designated.map((x, i) => `<div class="row between card soft" data-slug="${esc(x.slug)}"><span class="tag">${i + 1}</span><span>${esc(x.title)}</span><span class="row"><button class="btn sm" data-move="${esc(x.slug)}" data-dir="-1">↑</button><button class="btn sm" data-move="${esc(x.slug)}" data-dir="1">↓</button><button class="btn sm danger" data-freedel="${esc(x.slug)}">×</button></span></div>`).join('')}</div>
      <div class="row mt"><button class="btn primary sm" id="free-save">Save designation</button><span class="tiny muted" id="free-count">${d.designated.length}/15</span></div></div>
      <div class="card"><h3>Add a project</h3><select id="free-add">${d.all.filter(x => !x.is_free).map(x => `<option value="${esc(x.slug)}">${esc(x.title)}</option>`).join('')}</select>
      <button class="btn sm mt" id="free-add-btn">Add to free list</button>
      <h4 class="mt">Server-side rule</h4><p class="tiny muted">Free users receive only these rows from the library query. Locked projects never return a title, summary, diagram or code through the API.</p></div></div>`;
}

async function adminUsers() {
  const d = await api('/api/admin/users');
  return `<div class="card mb"><h3>Users, roles and entitlements</h3>${table(d.users, [['id', 'ID'], ['email', 'Email'], ['role', 'Role', v => badge(v, v === 'admin' ? 'rose' : v === 'pro' ? 'violet' : '')], ['plan', 'Plan'], ['sub_status', 'Sub status'], ['expires_at', 'Expires', v => fmtDate(v)], ['id', 'Actions', v => `<button class="btn sm" data-user="${v}">Manage</button>`]])}</div>`;
}

async function adminConfig() {
  const [d, tools] = await Promise.all([api('/api/admin/config'), api('/api/tools')]);
  const ai = d.platform.ai || {};
  return `<div class="grid g2"><div class="card"><h3>AI provider</h3>
      <label class="field"><span>Provider</span><select id="c-provider"><option value="offline" ${ai.provider === 'offline' ? 'selected' : ''}>offline (deterministic engine)</option><option value="openai_compatible" ${ai.provider === 'openai_compatible' ? 'selected' : ''}>openai_compatible</option></select></label>
      <label class="field"><span>Base URL</span><input id="c-base" value="${esc(ai.base_url || '')}"></label>
      <label class="field"><span>Model</span><input id="c-model" value="${esc(ai.model || '')}"></label>
      <label class="field"><span>API key (write-only; leave blank to keep current)</span><input type="password" id="c-key" placeholder="${esc(ai.api_key_hint || 'not set')}"></label>
      <label class="check"><input type="checkbox" id="c-enabled" ${ai.enabled ? 'checked' : ''}> AI tools enabled</label>
      <p class="tiny muted">Env key present: ${ai.env_key_present ? 'yes' : 'no'} · ${esc(ai.note || '')}</p>
      <div class="row"><button class="btn sm" id="c-aitest">Test connection</button><span id="c-testout" class="tiny muted"></span></div></div>
      <div class="card"><h3>Plans & payments</h3>
      <label class="field"><span>Plan name</span><input id="c-plan" value="${esc(d.platform.payments?.plan_name || '')}"></label>
      <div class="grid g2"><label class="field"><span>Price</span><input id="c-amount" type="number" value="${esc(d.platform.payments?.amount || 19)}"></label>
      <label class="field"><span>Interval</span><select id="c-interval"><option ${d.platform.payments?.interval === 'month' ? 'selected' : ''}>month</option><option ${d.platform.payments?.interval === 'year' ? 'selected' : ''}>year</option></select></label></div>
      <label class="field"><span>Trial days</span><input id="c-trial" type="number" value="${esc(d.platform.payments?.trial_days || 0)}"></label>
      <p class="tiny muted">Credentials come from environment variables only. Webhook signature verification is mandatory.</p></div>
      <div class="card"><h3>Usage limits (JSON)</h3><textarea id="c-limits" style="min-height:220px">${esc(JSON.stringify(d.limits, null, 2))}</textarea>
      <h4 class="mt">Free feature policy</h4><p class="tiny muted">Open a Pro tool to free users without a code change:</p>
      ${tools.tools.map(t => `<label class="check"><input type="checkbox" class="c-tool" value="${esc(t.feature)}" ${(d.public_free_feature_policy.allowed_pro_tools || []).includes(t.feature) ? 'checked' : ''}> ${esc(t.name)}</label>`).join('')}</div>
      <div class="card"><h3>Integrations & quality gate</h3>
      <label class="check"><input type="checkbox" id="c-mqtt-en" ${d.platform.integrations?.mqtt?.enabled ? 'checked' : ''}> MQTT bridge enabled (requires paho-mqtt)</label>
      <label class="field"><span>MQTT broker</span><input id="c-mqtt-host" value="${esc(d.platform.integrations?.mqtt?.broker || '')}"></label>
      <label class="field"><span>MQTT topic</span><input id="c-mqtt-topic" value="${esc(d.platform.integrations?.mqtt?.topic || '')}"></label>
      <label class="field"><span>Minimum quality for publication</span><select id="c-quality">${['Technically reviewed', 'Ready for publication', 'Physically tested'].map(x => `<option ${d.project_quality.minimum_status_for_publish === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
      <p class="tiny dim">${esc(d.secret_policy)}</p></div>
      <div class="card"><h3>Category taxonomy</h3><p class="tiny muted">One category per line. Renaming or adding a category updates the library navigation and admin metadata without a code change.</p>
      <textarea id="c-categories" style="min-height:260px">${esc((d.categories || []).join('\n'))}</textarea></div></div>
      <div class="row mt"><button class="btn primary" id="c-save">Save configuration</button></div>`;
}

async function adminUsage() {
  const [u, a] = await Promise.all([api('/api/admin/usage'), api('/api/admin/audit')]);
  return `<div class="grid g2"><div class="card"><h3>Usage by user</h3>${table(u.usage, [['email', 'Email'], ['role', 'Role'], ['kind', 'Event'], ['n', 'Count'], ['last', 'Last', v => fmtDate(v)]])}</div>
    <div class="card"><h3>Daily usage (30 days)</h3>${table(u.daily, [['day', 'Day'], ['kind', 'Event'], ['n', 'Count']])}</div></div>
    <div class="section-title">Audit log</div><div class="card">${table(a.logs, [['id', 'ID'], ['actor_email', 'Actor'], ['action', 'Action'], ['target', 'Target'], ['created_at', 'When', v => fmtDate(v)]])}</div>`;
}

async function adminQuality() {
  const [q, h] = await Promise.all([api('/api/admin/quality'), api('/api/admin/health')]);
  return `<div class="grid g3 mb">${stat(q.total, 'Projects checked')}${stat(q.passing, 'Publication-ready')}${stat(q.failing, 'Need attention')}</div>
    <div class="grid g2 mb"><div class="card"><h3>System health</h3>${keyVal({ 'DB integrity': h.database.integrity, 'DB path': h.database.path, 'AI provider': h.integrations.ai.provider, 'AI configured': String(h.integrations.ai.configured), 'Payments': h.integrations.payments.provider, 'Payments configured': String(h.integrations.payments.configured), 'Stripe key env': String(h.environment.stripe_key_present), 'AI key env': String(h.environment.env_ai_key_present), 'HTTP ingest': h.integrations.http_ingest.endpoint, 'PBKDF2 iterations': h.environment.pbkdf2_iterations })}<p class="tiny dim">${esc(h.secret_policy)}</p></div>
      <div class="card"><h3>Recent security / webhook events</h3>${table(h.recent_errors, [['action', 'Action'], ['target', 'Target'], ['created_at', 'When', v => fmtDate(v)]])}</div></div>
    <div class="section-title">Project quality report</div>${table(q.report, [['id', 'ID'], ['title', 'Title'], ['status', 'Status', v => badge(v, v === 'published' ? 'green' : 'amber')], ['quality_status', 'Quality'], ['issues', 'Issues', v => v.length ? esc(v.join('; ')) : badge('clean', 'green')], ['ready', 'Ready', v => v ? '✓' : '—']])}`;
}

async function adminAnalytics() {
  const d = await api('/api/admin/analytics');
  return `<div class="grid g4 mb">${stat(d.total_project_views, 'Project views / 30d')}${stat(d.top_projects.length, 'Projects viewed')}${stat(d.by_category.length, 'Categories viewed')}${stat(d.tool_runs.reduce((a, x) => a + x.n, 0), 'Tool runs / 30d')}</div>
    <div class="grid g2 mb"><div class="card"><h3>Most viewed projects</h3>${table(d.top_projects, [['slug', 'Project'], ['views', 'Views']])}</div>
      <div class="card"><h3>Tool usage</h3>${table(d.tool_runs, [['tool', 'Tool'], ['n', 'Runs']])}</div></div>
    <div class="grid g2"><div class="card"><h3>Views by category</h3>${table(d.by_category, [['category', 'Category'], ['views', 'Views']])}</div>
      <div class="card"><h3>Views by tier</h3>${keyVal(d.by_tier || {none: 'no views yet'})}
      <h4 class="mt">Daily views</h4>${table(d.by_day, [['day', 'Day'], ['views', 'Views']])}</div></div>
    <div class="notice mt">${esc(d.note)}</div>`;
}

function bindAdmin(tab) {
  if (tab === 'projects') {
    $('#ap-search')?.addEventListener('input', e => {
      const q = e.target.value.toLowerCase();
      $$('#admin-tab tbody tr').forEach(tr => tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none');
    });
    $('#ap-new')?.addEventListener('click', () => modal('Create project', `<label class="field"><span>Slug</span><input id="np-slug" placeholder="my-new-iot-project"></label>
      <label class="field"><span>Title</span><input id="np-title"></label><label class="field"><span>Category</span><input id="np-cat" value="Custom & Interdisciplinary"></label>
      <label class="field"><span>Summary / problem</span><textarea id="np-sum"></textarea></label><p class="tiny muted">A full structured draft (BOM, wiring, code, tests) is compiled from the catalog. Publish only after technical review.</p>
      <button class="btn primary" id="np-create">Create draft</button>`, async (m) => {
      $('#np-create', m).onclick = async () => {
        try {
          await api('/api/admin/projects', { method: 'POST', body: { slug: $('#np-slug', m).value, title: $('#np-title', m).value, category: $('#np-cat', m).value, summary: $('#np-sum', m).value } });
          closeModal(); toast('Draft created', 'ok'); setTab('admin', 'projects');
        } catch (e) { toast(e, 'err'); }
      };
    }));
    const editProject = (id) => {
      const p = state.cache.adminProjects.find(x => x.id === id);
      modal('Edit project #' + id, `<label class="field"><span>Title</span><input id="ep-title" value="${esc(p.title)}"></label>
        <label class="field"><span>Category</span><input id="ep-cat" value="${esc(p.category)}"></label>
        <label class="field"><span>Tags (comma separated)</span><input id="ep-tags" placeholder="sensors, mqtt, esp32"></label>
        <label class="field"><span>Difficulty</span><select id="ep-diff">${['Beginner', 'Intermediate', 'Advanced'].map(x => `<option ${p.difficulty === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
        <label class="field"><span>Status</span><select id="ep-status">${['draft', 'published', 'archived'].map(x => `<option ${p.status === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
        <label class="field"><span>Quality status</span><select id="ep-quality">${['Draft', 'Content incomplete', 'Technically reviewed', 'Ready for publication', 'Physically tested'].map(x => `<option ${p.quality_status === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
        <div class="divider"></div><h4>Project actions (server-validated)</h4><div class="row">
        ${['publish', 'unpublish', 'archive', 'duplicate', 'validate'].map(a => `<button class="btn sm" data-act="${a}">${a}</button>`).join('')}
        <button class="btn sm danger" id="ep-delete">delete</button></div><div id="ep-out" class="mt"></div>
        <div class="divider"></div><button class="btn primary" id="ep-save">Save changes</button>`, async (m) => {
        $('#ep-save', m).onclick = async () => {
          try {
            await api('/api/admin/projects/' + id, { method: 'PATCH', body: { title: $('#ep-title', m).value, category: $('#ep-cat', m).value, difficulty: $('#ep-diff', m).value, status: $('#ep-status', m).value, quality_status: $('#ep-quality', m).value,
              tags: $('#ep-tags', m).value.split(',').map(x => x.trim()).filter(Boolean) } });
            closeModal(); toast('Project updated', 'ok'); setTab('admin', 'projects');
          } catch (e) { toast(e, 'err'); }
        };
        $$('[data-act]', m).forEach(b => b.onclick = async () => {
          try {
            const r = await api('/api/admin/projects/' + id + '/action', { method: 'POST', body: b.dataset.act === 'quality' ? { action: 'quality', quality_status: $('#ep-quality', m).value } : { action: b.dataset.act } });
            $('#ep-out', m).innerHTML = `<pre style="max-height:220px">${esc(JSON.stringify(r, null, 2))}</pre>`;
            toast('Action: ' + b.dataset.act, 'ok');
          } catch (e) { $('#ep-out', m).innerHTML = `<div class="notice danger">${esc(e.message)}</div>`; }
        });
        $('#ep-delete', m).onclick = async () => {
          if (!confirm('Delete project #' + id + '? This cannot be undone.')) return;
          try { await api('/api/admin/projects/' + id, { method: 'DELETE' }); closeModal(); toast('Deleted', 'ok'); setTab('admin', 'projects'); }
          catch (e) { toast(e, 'err'); }
        };
      });
    };
    $$('[data-edit]').forEach(b => b.onclick = () => editProject(Number(b.dataset.edit)));
  }
  if (tab === 'free') {
    const moveFree = (slug, dir) => {
      const a = state.cache.freeSlugs, i = a.indexOf(slug), j = i + dir;
      if (i < 0 || j < 0 || j >= a.length) return;
      [a[i], a[j]] = [a[j], a[i]]; setTab('admin', 'free');
    };
    const delFree = (slug) => { state.cache.freeSlugs = state.cache.freeSlugs.filter(x => x != slug); setTab('admin', 'free'); };
    $$('[data-move]').forEach(b => b.onclick = () => moveFree(b.dataset.move, Number(b.dataset.dir)));
    $$('[data-freedel]').forEach(b => b.onclick = () => delFree(b.dataset.freedel));
    $('#free-add-btn')?.addEventListener('click', () => {
      const s = $('#free-add').value;
      if (s && !state.cache.freeSlugs.includes(s) && state.cache.freeSlugs.length < 15) { state.cache.freeSlugs.push(s); setTab('admin', 'free'); }
    });
    $('#free-save')?.addEventListener('click', async () => {
      try { await api('/api/admin/free-projects', { method: 'PUT', body: { slugs: state.cache.freeSlugs } }); toast('Free designation saved', 'ok'); state.config = await api('/api/config/public'); }
      catch (e) { toast(e, 'err'); }
    });
  }
  if (tab === 'users') {
    const manageUser = (id) => modal('Manage user #' + id, `<div class="grid g2"><label class="field"><span>Role</span><select id="mu-role"><option>free</option><option>pro</option><option>admin</option></select></label>
      <label class="field"><span>Grant Pro days</span><input id="mu-days" type="number" value="30"></label></div>
      <label class="field"><span>Subscription status</span><select id="mu-status"><option>active</option><option>cancelled</option><option>expired</option><option>past_due</option><option>inactive</option></select></label>
      <div class="row"><button class="btn primary sm" id="mu-role-btn">Set role</button><button class="btn sm" id="mu-grant">Grant Pro (audited)</button><button class="btn sm" id="mu-status-btn">Set status</button><button class="btn danger sm" id="mu-revoke">Revoke Pro</button></div>
      <p class="tiny muted mt">All changes are written to the audit log. The last active administrator cannot be demoted.</p>`, async (m) => {
      $('#mu-role-btn', m).onclick = () => doUser(id, { role: $('#mu-role', m).value });
      $('#mu-grant', m).onclick = () => doUser(id, { grant_pro: true, days: Number($('#mu-days', m).value) });
      $('#mu-status-btn', m).onclick = () => doUser(id, { subscription_status: $('#mu-status', m).value });
      $('#mu-revoke', m).onclick = () => doUser(id, { revoke_pro: true });
    });
    $$('[data-user]').forEach(b => b.onclick = () => manageUser(Number(b.dataset.user)));
  }
  if (tab === 'config') {
    $('#c-aitest')?.addEventListener('click', async () => {
      try { const r = await api('/api/admin/ai-test', { method: 'POST', body: {} }); $('#c-testout').textContent = `${r.mode}: ${r.sample.slice(0, 60)}`; }
      catch (e) { toast(e, 'err'); }
    });
    $('#c-save')?.addEventListener('click', async () => {
      const body = {
        ai: { provider: $('#c-provider').value, base_url: $('#c-base').value, model: $('#c-model').value, enabled: $('#c-enabled').checked },
        payments: { plan_name: $('#c-plan').value, amount: Number($('#c-amount').value), interval: $('#c-interval').value, trial_days: Number($('#c-trial').value) },
        integrations: { mqtt: { enabled: $('#c-mqtt-en').checked, broker: $('#c-mqtt-host').value, topic: $('#c-mqtt-topic').value } },
        public_free_feature_policy: { allowed_pro_tools: $$('.c-tool:checked').map(x => x.value) },
        project_quality: { minimum_status_for_publish: $('#c-quality').value },
        categories: $('#c-categories').value.split('\n').map(x => x.trim()).filter(Boolean)
      };
      if ($('#c-key').value) body.ai.api_key = $('#c-key').value;
      try { body.limits = JSON.parse($('#c-limits').value); } catch (e) { toast('Limits JSON is invalid', 'err'); return; }
      try { await api('/api/admin/config', { method: 'PATCH', body }); state.config = await api('/api/config/public'); toast('Configuration saved (secrets encrypted at rest)', 'ok'); }
      catch (e) { toast(e, 'err'); }
    });
  }
}
async function doUser(id, body) {
  try { await api('/api/admin/users/' + id, { method: 'PATCH', body }); toast('User updated', 'ok'); closeModal(); setTab('admin', 'users'); }
  catch (e) { toast(e, 'err'); }
}

const workstation = createWorkstation({ $, $$, esc, api, apiText, sessionFetch, toast, modal, closeModal, go, copy, download, state, pageHead, badge, table, fmtDate });

/* ---------------------------------------------------------------- router */
async function renderRoute() {
  if (!state.me) return;
  const epoch=state.renderEpoch=(state.renderEpoch||0)+1;
  if (!document.querySelector('.shell')) { $('#app').innerHTML = shell(); startNeuralWallpaper(); applyWallpaper((() => { try { return localStorage.getItem('nexus_wallpaper_preset') || 'aurora'; } catch (_) { return 'neural'; } })(), false); bindShell(); }
  else { // refresh nav highlighting + plan chip
    const old = $('#app').innerHTML;
    $('#app').innerHTML = shell(); startNeuralWallpaper(); applyWallpaper((() => { try { return localStorage.getItem('nexus_wallpaper_preset') || 'aurora'; } catch (_) { return 'neural'; } })(), false); bindShell();
  }
  const hash = location.hash || '#/dashboard';
  const [path, qs] = hash.replace(/^#/, '').split('?');
  $('#view').innerHTML = spinner();
  window.scrollTo({ top: 0 });
  try {
    if (path === '/' || path === '/dashboard' || path === '') await viewDashboard();
    else if (path === '/assistant') await workstation.viewAssistant(qs || '');
    else if (path === '/projects' || path.startsWith('/projects/')) await workstation.viewProjects(path.split('/')[2]);
    else if (path === '/studio' || path.startsWith('/studio/')) await workstation.viewStudio(path.split('/')[2]);
    else if (path === '/code' || path.startsWith('/code/')) await workstation.viewCode(path.split('/')[2]);
    else if (path === '/invention') await workstation.viewInvention(qs || '');
    else if (path === '/images' || path === '/research') { go('#/assistant'); return; }
    else if (path === '/providers' || path === '/ai-settings') await workstation.viewProviders();
    else if (path === '/library') await viewLibrary();
    else if (path === '/learn') await viewLearning();
    else if (path.startsWith('/project/')) await viewProject(decodeURIComponent(path.slice(9)));
    else if (path === '/tools') await viewTools();
    else if (path.startsWith('/tools/')) await viewTool(path.slice(7));
    else if (path === '/upgrade') await viewUpgrade();
    else if (path === '/subscription') await viewSubscription();
    else if (path === '/account') await viewAccount();
    else if (path === '/admin') await viewAdmin();
    else $('#view').innerHTML = '<div class="empty">Page not found. <a href="#/dashboard">Go to dashboard</a></div>';
    hydrateDiagrams();
    $('pre#full-code')?.parentElement && ($('#copy-code').onclick = () => { copy($('#full-code').textContent); toast('Code copied', 'ok'); });
  } catch (e) {
    if(epoch!==state.renderEpoch || e.routeChanged) return;
    $('#view').innerHTML = `<div class="notice danger"><b>${esc(e.message)}</b>${e.status === 403 ? '<p><a href="#/upgrade">Upgrade to Pro →</a></p>' : ''}</div>`;
  }
}

async function boot(full = true) {
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
    $('#app').innerHTML = `<div class="boot"><div class="notice danger">Cannot reach the NEXUS API: ${esc(e.message)}</div></div>`;
    return;
  }
  if (!state.me) {
    if (location.hash.startsWith('#/register')) authView('register');
    else { authView('login'); if (!location.hash.startsWith('#/login')) replaceHash('#/login'); }
    return;
  }
  if (location.hash.startsWith('#/login') || location.hash.startsWith('#/register')) replaceHash('#/dashboard');
  try { const prefs = await api('/api/settings'); document.documentElement.dataset.theme = prefs.settings?.theme || 'dark'; } catch (e) {}
  try { await renderRoute(); }
  catch (e) { $('#app').innerHTML = `<div class="boot"><div class="notice danger">Workspace failed to start: ${esc(e.message)}</div></div>`; }
}

window.addEventListener('hashchange', () => { if (state.me) renderRoute(); else boot(false); });
boot();
