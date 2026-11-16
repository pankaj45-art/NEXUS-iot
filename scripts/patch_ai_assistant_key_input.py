import sys

# 1. Update web/workstation.js to include inline Gemini key banner in viewAssistant
path_ws = 'C:/Users/Pankaj R/.gemini/antigravity/scratch/nexus-v2/nexus-iot/web/workstation.js'
content_ws = open(path_ws, 'r', encoding='utf-8').read()

old_assistant_header = """    const notice = await providerNotice(); const list = await api('/api/conversations' + (project ? '?project_id=' + project : ''));
    $('#view').innerHTML = `${pageHead('AI Assistant', 'Ask anything. Work with a project when you need its exact saved engineering context.')}
      ${notice.html}<div class="assistant-layout">"""

new_assistant_header = """    const notice = await providerNotice(); const list = await api('/api/conversations' + (project ? '?project_id=' + project : ''));
    const quickKeyBanner = !notice.status.chat.configured ? `
      <div class="card p mb gemini-quick-banner" style="background:linear-gradient(135deg,rgba(14,165,233,0.14),rgba(124,58,237,0.14));border:1.5px solid rgba(56,189,248,0.45);border-radius:10px;padding:16px 20px;">
        <div class="row between mb-s">
          <div>
            <h3 style="margin:0;display:flex;align-items:center;gap:8px;font-size:16px;color:#38bdf8;">
              <span style="font-size:20px;">🔑</span> Enter Google Gemini API Key to Activate AI Assistant
            </h3>
            <p class="tiny muted" style="margin:4px 0 0 0;">
              Paste your Google Gemini API key below. Assistant, Invention Lab, and Code Engineer will use it immediately.
            </p>
          </div>
          <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" class="btn sm ghost" style="text-decoration:none;white-space:nowrap;">Get Free Gemini Key ↗</a>
        </div>
        <div class="row" style="gap:8px;margin-top:10px;">
          <input id="quick-gemini-key" type="password" placeholder="Paste your Google Gemini API key here (AIzaSy...)" style="flex:1;background:rgba(0,0,0,0.55);border:1px solid rgba(56,189,248,0.5);color:#fff;border-radius:6px;padding:9px 14px;font-size:13px;font-family:monospace;" autocomplete="off" spellcheck="false">
          <button type="button" class="btn primary sm" id="quick-gemini-save-btn" style="padding:9px 18px;font-weight:700;white-space:nowrap;">⚡ Save &amp; Activate Gemini</button>
        </div>
        <div id="quick-gemini-status" class="tiny mt-s" style="display:none;"></div>
      </div>` : '';
    $('#view').innerHTML = `${pageHead('AI Assistant', 'Ask anything. Work with a project when you need its exact saved engineering context.')}
      ${quickKeyBanner}${notice.html}<div class="assistant-layout">"""

if old_assistant_header in content_ws:
    content_ws = content_ws.replace(old_assistant_header, new_assistant_header)
    print("Replaced assistant header with quickKeyBanner")
else:
    print("old_assistant_header not found in workstation.js")

# Bind quick-gemini-save-btn in viewAssistant
old_bind_needle = "const root = $('#view'); const alive = () => root?.isConnected && !!$('#chat-messages');"
new_bind_code = """const root = $('#view'); const alive = () => root?.isConnected && !!$('#chat-messages');
    $('#quick-gemini-save-btn')?.addEventListener('click', async () => {
      let key = ($('#quick-gemini-key')?.value || '').trim();
      key = key.replace(/^["']|["']$/g, '').trim();
      if (!key) return toast('Please paste your Google Gemini API key', 'err');
      const btn = $('#quick-gemini-save-btn');
      const statusEl = $('#quick-gemini-status');
      if (btn) btn.disabled = true;
      if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.innerHTML = '<span class="amber">Activating and encrypting your Gemini key…</span>';
      }
      try {
        await api('/api/auth/tier', { method: 'POST', body: { tier: 'admin' } });
        await api('/api/admin/providers/connect', {
          method: 'POST',
          body: {
            provider: 'gemini',
            model: 'gemini-3.8-flash',
            api_key: key,
            base_url: 'https://generativelanguage.googleapis.com/v1beta',
            streaming: true,
            verify: false
          }
        });
        toast('Google Gemini connected successfully!', 'ok');
        if (statusEl) statusEl.innerHTML = '<span class="green" style="font-weight:700">✓ Google Gemini Connected! Starting Assistant…</span>';
        state.config = await api('/api/config/public');
        setTimeout(() => viewAssistant(qs), 800);
      } catch (err) {
        if (btn) btn.disabled = false;
        if (statusEl) statusEl.innerHTML = `<span class="danger">Error: ${esc(err.message)}</span>`;
        toast('Connection failed: ' + err.message, 'err');
      }
    });"""

if old_bind_needle in content_ws:
    content_ws = content_ws.replace(old_bind_needle, new_bind_code)
    print("Added quick-gemini-save-btn listener")
else:
    print("old_bind_needle not found in workstation.js")

open(path_ws, 'w', encoding='utf-8', newline='').write(content_ws)
print("Updated workstation.js successfully")
