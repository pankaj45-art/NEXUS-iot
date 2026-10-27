/* Secure, discoverable provider setup. Keys are only sent in POST JSON bodies. */
export function createAPIKeyPanel(h) {
  const { $, $$, esc, api, state, pageHead, badge, toast, go, fmtDate } = h;
  const GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta';
  const GEMINI_MODEL = 'gemini-3.5-flash-lite';
  const normalized = v => String(v || '').trim().replace(/\/+$/, '').replace(/^https:\/\/generativelanguage\.googleapis\.com\/v1beta\/openai$/, GEMINI_BASE);
  const providerFor = preset => preset === 'gemini' ? 'gemini' : preset === 'ollama' ? 'ollama' : 'openai_compatible';
  return async function viewProviders() {
    const admin = state.me.entitlement.is_admin;
    if (!admin) {
      const s = await api('/api/ai/status');
      $('#view').innerHTML = `${pageHead('AI & API Keys', 'Online AI connection status')}
        <div class="card"><h3>${s.chat.configured ? 'Chat provider is configured' : 'An administrator needs to connect AI'}</h3><p class="muted">Only an administrator can change the shared platform API key. Free and Pro accounts can use the configured chat model within their plan limits.</p><p>${esc(s.chat.provider)} / ${esc(s.chat.model)}</p><a class="btn primary sm" href="#/assistant">Open AI Assistant</a></div>`;
      return;
    }
    let cfg = await api('/api/admin/providers');
    const chat = cfg.chat;
    const isCustom = chat.provider === 'openai_compatible' && chat.base_url.replace(/\/$/, '') !== 'https://api.openai.com/v1';
    const initial = chat.provider === 'none' || chat.provider === 'gemini' ? 'gemini' : chat.provider === 'ollama' ? 'ollama' : isCustom ? 'custom' : 'openai';
    const checked = chat.last_test?.ok;
    $('#view').innerHTML = `${pageHead('AI & API Keys', 'Connect your model once. Assistant, Invention Lab and online Code Engineer use it immediately.')}
      <div class="api-setup-layout">
        <form id="ai-connect-form" class="card api-connect-card" autocomplete="off">
          <div class="eyebrow">ONLINE AI / QUICK SETUP</div><h2>Paste your API key to connect AI</h2>
          <p class="muted">No environment editing or server restart is needed. <b>Save & Connect</b> runs a real model request in the background before activating your settings. Progress survives reloading this page.</p>
          <fieldset class="connect-fields" id="connect-inputs"><label class="field"><span>AI provider</span><select id="connect-preset"><option value="gemini" ${initial === 'gemini' ? 'selected' : ''}>Google Gemini</option><option value="openai" ${initial === 'openai' ? 'selected' : ''}>OpenAI</option><option value="custom" ${initial === 'custom' ? 'selected' : ''}>Other OpenAI-compatible API</option><option value="ollama" ${initial === 'ollama' ? 'selected' : ''}>Ollama (a real local model server)</option></select></label>
          <div id="connect-gemini-help" class="notice mt-s" ${initial === 'gemini' ? '' : 'hidden'}><b>Connect with your Google AI Studio key</b><p class="tiny">No OpenAI balance is needed. <a id="connect-get-gemini-key" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Create a Gemini API key ↗</a>, then paste it below. Google's free tier is limited by model, project and account eligibility; it is not unlimited. <a href="https://ai.google.dev/gemini-api/docs/pricing" target="_blank" rel="noopener noreferrer">Pricing &amp; data-use terms ↗</a></p></div>
          <label class="field"><span>API key <span id="connect-key-note" class="muted">${chat.api_key_set ? '· encrypted key saved; leave blank to reuse' : '· required for cloud AI'}</span></span>
            <div class="connect-key-control"><input id="connect-api-key" type="password" autocomplete="new-password" spellcheck="false" maxlength="4096" placeholder="Paste your provider API key here" aria-label="AI provider API key"><button type="button" class="btn sm" id="connect-show-key" aria-pressed="false">Show</button></div>
          </label>
          <label class="field"><span>Model / deployment ID</span><input id="connect-model" value="${esc(chat.provider !== 'none' ? chat.model : GEMINI_MODEL)}" required maxlength="160" list="connect-model-suggestions" placeholder="Model available to your API account"></label><datalist id="connect-model-suggestions"><option value="gemini-3.8-flash"></option><option value="gemini-3.5-flash-lite"></option></datalist>
          <details id="connect-advanced" ${['custom','ollama'].includes(initial) ? 'open' : ''}><summary>Endpoint & streaming settings</summary><label class="field mt"><span>Trusted provider base URL</span><input id="connect-base-url" value="${esc(chat.provider !== 'none' ? chat.base_url : GEMINI_BASE)}" placeholder="https://api.openai.com/v1" required></label><label class="check-row"><input type="checkbox" id="connect-streaming" ${chat.provider === 'none' || chat.capabilities?.streaming !== false ? 'checked' : ''}> Enable streaming (turn off for a non-streaming compatible gateway)</label><p class="tiny muted">Your key is sent only to this server and the selected trusted provider. Use HTTPS for remote API-key services.</p></details>
          <details class="mt" id="connect-image-options"><summary>Optional: also configure Image Studio with this key</summary><label class="check-row"><input type="checkbox" id="connect-enable-images"> Use this provider/key for image generation too</label><label class="field"><span>Image model (your provider must support it)</span><input id="connect-image-model" value="${esc(cfg.image.provider !== 'none' ? cfg.image.model : 'gpt-image-1')}" maxlength="160"></label><p class="tiny muted">Chat and image permissions are separate. The connection test verifies chat only; an actual Image Studio generation verifies images. This option leaves existing image settings untouched unless checked.</p></details>
          </fieldset><div class="row mt"><button class="btn primary" type="submit" id="connect-save-test">Save & Connect</button><button class="btn sm" type="button" id="connect-save-only">Save settings, verify later</button><button class="btn sm danger" type="button" id="connect-cancel" hidden>Cancel check</button></div>
          <div id="connect-result" class="mt" role="status" aria-live="polite"></div>
          <p class="tiny muted mt">Keys are encrypted on the backend, never returned by the API, and never stored in browser storage. Blank fields keep a saved key only for the same provider and endpoint. A failed test keeps your previous connection settings.</p>
        </form>
        <aside class="stack">
          <div class="card"><div class="eyebrow">CURRENT SAVED CONNECTION</div><h3 id="connect-status-title">${checked ? 'Last connection test passed' : chat.provider !== 'none' && chat.api_key_set ? 'Saved · awaiting a connection test' : 'Ready for your API key'}</h3><div id="connect-status-detail"><p>${chat.provider === 'none' ? 'No provider has been activated yet.' : esc(chat.provider) + ' / ' + esc(chat.model)}</p><p class="muted">${checked ? 'Verified ' + esc(fmtDate(chat.last_test.checked_at)) : 'Paste a real provider key, check the model, then select Save & Connect.'}</p></div><a class="btn sm ${checked ? 'primary' : ''}" href="#/assistant" id="connect-open-assistant">Open AI Assistant →</a></div>
          <div class="card"><h3>What this enables</h3><ul class="connect-checklist"><li>General-purpose online questions and conversations</li><li>Project-aware help and source proposals</li><li>AI Invention Lab architecture/design proposals</li></ul><p class="tiny muted">Your plan permissions and usage limits still apply. Hardware tests and simulations are not unlocked by an API key.</p></div>
          <div class="card"><h3>Other services are optional</h3><p class="tiny muted"><b>Images:</b> ${cfg.image.api_key_set && cfg.image.enabled && cfg.image.provider !== 'none' ? 'configured; test with a real image request' : 'add a supported image provider/key in advanced settings'}.</p><p class="tiny muted"><b>Web search:</b> ${cfg.web_search.enabled && cfg.web_search.provider !== 'none' ? 'configured' : 'add a search provider below; curated references remain available'}.</p><p class="tiny muted">Neither image generation nor web search setup blocks ordinary chat. Missing credentials, model permissions and API-account billing/quota problems are reported honestly.</p></div>
        </aside>
      </div>
      <details class="card mt" id="advanced-provider-settings"><summary>Image generation, web search & advanced provider configuration</summary>
        <div class="grid g3 mt">${['chat', 'image', 'web_search'].map(kind => { const s = cfg[kind]; return `<form class="card provider-form" data-kind="${kind}"><div class="eyebrow">${kind === 'chat' ? 'CHAT SETTINGS' : kind === 'image' ? 'IMAGE API KEY' : 'WEB SEARCH API KEY'}</div><h3>${{ chat: 'Chat model', image: 'Image generation', web_search: 'Search service' }[kind]}</h3><label class="field"><span>Adapter</span><select name="provider">${(kind === 'chat' ? ['none', 'openai_compatible', 'gemini', 'ollama'] : kind === 'image' ? ['none', 'openai_compatible'] : ['none', 'tavily', 'searxng']).map(k => `<option ${s.provider === k ? 'selected' : ''}>${k}</option>`).join('')}</select></label><label class="field"><span>Base URL</span><input name="base_url" value="${esc(s.base_url || '')}" placeholder="${kind === 'web_search' ? 'https://api.tavily.com' : 'https://api.openai.com/v1'}"></label>${kind !== 'web_search' ? `<label class="field"><span>Actual model ID</span><input name="model" value="${esc(s.model || '')}"></label>` : ''}<label class="field"><span>API key (write-only) ${s.api_key_set ? '· key saved' : '· not set'}</span><input name="api_key" type="password" autocomplete="new-password" placeholder="Paste your provider key"></label><label class="check-row"><input type="checkbox" name="enabled" ${s.enabled ? 'checked' : ''}> Enabled</label>${kind === 'chat' ? `<label class="check-row"><input type="checkbox" name="streaming" ${s.capabilities?.streaming !== false ? 'checked' : ''}> Streaming supported</label>` : ''}<button class="btn primary sm mt" type="submit">Save ${kind === 'web_search' ? 'search' : kind} settings</button><div class="provider-save-status mt-s tiny"></div></form>`; }).join('')}</div>
        <div class="row between mt"><p class="tiny muted">Test the saved chat configuration. A short real request may incur provider charges.</p><button class="btn sm" id="provider-test">Test saved chat connection</button></div><div id="provider-health" class="mt"></div>
      </details>`;
    const root = $('#ai-connect-form');
    const alive = () => root.isConnected;
    function updateKeyState() {
      const selected = providerFor($('#connect-preset').value), local = selected === 'ollama';
      const reuse = cfg.chat.api_key_set && selected === cfg.chat.provider && normalized($('#connect-base-url').value) === normalized(cfg.chat.base_url);
      $('#connect-api-key').disabled = local;
      $('#connect-api-key').required = !local && !reuse;
      $('#connect-key-note').textContent = local ? '· no cloud key; a running model server is required' : reuse ? '· encrypted key saved for this endpoint; leave blank to reuse' : selected === 'gemini' ? '· paste your Google Gemini key, not an OpenAI key' : '· paste your real provider key';
    }
    function applyPreset(event) {
      const preset = $('#connect-preset').value, local = preset === 'ollama', gemini = preset === 'gemini';
      if (event) {
        // Never carry a typed key into another vendor's request accidentally.
        $('#connect-api-key').value = ''; $('#connect-api-key').type = 'password';
        $('#connect-show-key').textContent = 'Show'; $('#connect-show-key').setAttribute('aria-pressed', 'false');
        if (preset === 'openai') { $('#connect-base-url').value = 'https://api.openai.com/v1'; $('#connect-model').value = 'gpt-4o-mini'; }
        if (gemini) { $('#connect-base-url').value = GEMINI_BASE; $('#connect-model').value = GEMINI_MODEL; }
        if (local) { $('#connect-base-url').value = 'http://127.0.0.1:11434'; $('#connect-model').value = 'llama3.2'; }
        if (preset === 'custom') { $('#connect-base-url').value = ''; $('#connect-model').value = ''; }
        $('#connect-streaming').checked = true;
      }
      $('#connect-enable-images').disabled = local || gemini;
      if (local || gemini) $('#connect-enable-images').checked = false;
      $('#connect-image-options').hidden = local || gemini;
      $('#connect-gemini-help').hidden = !gemini;
      $('#connect-model-suggestions').innerHTML = gemini ? '<option value="gemini-3.8-flash"></option><option value="gemini-3.5-flash-lite"></option>' : '';
      if (event) $('#connect-result').innerHTML = '';
      if (event || !$('#connect-advanced').dataset.initialized) $('#connect-advanced').open = ['custom', 'ollama'].includes(preset);
      $('#connect-advanced').dataset.initialized = '1';
      updateKeyState();
    }
    applyPreset();
    $('#connect-preset').onchange = applyPreset;
    $('#connect-base-url').oninput = updateKeyState;
    $('#connect-show-key').onclick = e => { const input = $('#connect-api-key'), show = input.type === 'password'; input.type = show ? 'text' : 'password'; e.target.textContent = show ? 'Hide' : 'Show'; e.target.setAttribute('aria-pressed', show ? 'true' : 'false'); };
    let activeJob = '', busy = false;
    const terminal = ['complete','failed','cancelled','interrupted'];
    const setBusy = value => {
      busy = value;
      if (!alive()) return;
      $('#connect-inputs').disabled = value;
      $('#connect-save-test').disabled = $('#connect-save-only').disabled = value;
      $('#connect-cancel').hidden = !value || !activeJob;
    };
    const clearTypedKey = () => {
      $('#connect-api-key').value = ''; $('#connect-api-key').type = 'password';
      $('#connect-show-key').textContent = 'Show'; $('#connect-show-key').setAttribute('aria-pressed','false');
    };
    function showError(e, savedAck=false) {
      if (!alive() || e.routeChanged) return;
      const code = e.data?.code, unknown = savedAck || e.outcomeUnknown || !e.status;
      const preserved = !unknown && e.data?.detail?.previous_configuration_preserved === true;
      const guidance = code === 'quota_exhausted' ? 'The provider reports no API credits or billing quota. Changing streaming will not add credits.' : code === 'rate_limited' ? 'Check your provider project/model limits and retry when quota is available.' : code === 'auth_failed' ? 'Check the key and its API/project permissions. Gemini needs a Google AI Studio key.' : code === 'invalid_model' ? 'Choose a model available to your API project. Try the suggested Flash-Lite model.' : code === 'timeout' || code === 'provider_unavailable' ? 'The provider was slow or unavailable. Try Gemini 3.5 Flash-Lite; your existing key can be reused for the same Google endpoint.' : 'Check the specific error above and the saved connection status.';
      $('#connect-result').innerHTML = `<div class="notice danger"><b>${savedAck ? 'Settings saved; status refresh failed' : unknown ? 'Could not confirm the connection' : 'AI connection was not activated'}</b><p>${esc(e.message)}</p><p class="tiny">${unknown ? 'The server may still finish the check. Recheck recent status before starting another request; a gateway failure is not proof that settings were preserved.' : (preserved ? 'Previous settings were preserved. ' : 'Connection status needs review. ') + guidance}</p><button class="btn sm" type="button" id="connect-recheck">Recheck recent status</button></div>`;
      $('#connect-recheck').onclick = () => resumeRecent(true);
    }
    async function waitJob(jid, progress) {
      activeJob = jid; setBusy(true);
      const start = Date.now(); let transient = 0;
      while (alive() && Date.now()-start < 300000) {
        try {
          const j = await api('/api/jobs/'+jid);
          transient=0;
          if (!alive()) return null;
          if (terminal.includes(j.state)) {
            if (j.state === 'complete') return j.output;
            const e = new Error(j.error?.message || 'Connection check '+j.state+'.');
            e.data = j.error || {}; e.status = e.data.status || 502;
            e.outcomeUnknown = ['internal_error','server_restarted'].includes(e.data.code);
            throw e;
          }
          progress?.(j);
        } catch (e) {
          if (!alive() || e.routeChanged) return null;
          if (e.outcomeUnknown && ++transient <= 3) { progress?.({state:'reconnecting'}); }
          else { if (!e.data?.detail) e.outcomeUnknown=true; throw e; }
        }
        await new Promise(r=>setTimeout(r,500));
      }
      if (!alive()) return null;
      const e=new Error('The connection check is still running. Reopen this page to follow its saved status.'); e.outcomeUnknown=true; throw e;
    }
    async function showSaved(r) {
      if (!alive()) return;
      cfg = await api('/api/admin/providers'); state.config = await api('/api/config/public');
      if (!alive()) return;
      applyPreset();
      const current = !r.connected || (cfg.chat.provider===r.provider && cfg.chat.model===r.model && cfg.chat.last_test?.checked_at===r.last_test?.checked_at);
      if (!current) { $('#connect-result').innerHTML='<div class="notice warn">This check completed, but newer settings are now active. Reload to view the current saved connection.</div>'; return; }
      $('#connect-result').innerHTML = `<div class="notice ${r.connected ? 'connect-success' : 'warn'}"><b>${esc(r.message)}</b><p class="tiny mt-s">${esc(r.image_message)}</p>${r.connected ? '<a class="btn primary sm mt-s" href="#/assistant">Start online AI chat →</a>' : ''}</div>`;
      $('#connect-status-title').textContent=r.connected ? 'Connected · model test passed' : 'Key saved · not yet verified';
      $('#connect-status-detail').innerHTML=`<p>${esc(r.provider)} / ${esc(r.model)}</p><p class="tiny muted">${r.connected ? 'A real provider response was received at '+esc(fmtDate(r.last_test.checked_at)) : 'Use Save & Connect to verify the saved credential.'} No restart required.</p>`;
      $('#connect-open-assistant').classList.toggle('primary',r.connected);
      const shell=$('#shell-ai-link'); if(shell){shell.textContent=r.connected?'AI connected':'AI configured';shell.className='badge '+(r.connected?'green':'amber');}
    }
    const progress = j => {
      if (alive()) $('#connect-result').innerHTML=`<div class="notice"><b>${j.state==='reconnecting'?'Reconnecting to check status…':'Testing connection in background…'}</b><p class="tiny">The browser is not waiting on a long provider request. You can leave and reopen this page; the result is saved. Settings are not activated until the model responds.</p></div>`;
    };
    async function follow(jid) {
      let savedAck=false;
      try { const r=await waitJob(jid,progress); if(r && alive()) {savedAck=!!r.saved;clearTypedKey();await showSaved(r);} }
      catch(e){showError(e,savedAck);}
      finally{activeJob='';setBusy(false);}
    }
    async function resumeRecent(explicit=false) {
      if (busy) return;
      try {
        const list=await api('/api/jobs?kind=provider_connect'); if(!alive())return;
        const recent=list.jobs.find(j=>!terminal.includes(j.state)) || (explicit ? list.jobs.find(j=>Date.now()/1000-j.created_at<600) : null);
        if(recent){progress(recent);await follow(recent.id);}
        else if(explicit) $('#connect-result').innerHTML='<div class="notice warn">No recent connection check was found for this account. Review the current saved connection before retrying.</div>';
      }catch(e){if(explicit)showError(e);}
    }
    async function save(verify) {
      if (busy || !root.reportValidity()) return;
      const payload={provider:providerFor($('#connect-preset').value),api_key:$('#connect-preset').value==='ollama'?'':$('#connect-api-key').value,
        model:$('#connect-model').value.trim(),base_url:$('#connect-base-url').value.trim(),streaming:$('#connect-streaming').checked,verify,
        enable_images:$('#connect-enable-images').checked,image_model:$('#connect-image-model').value.trim()};
      setBusy(true); $('#connect-result').innerHTML='<div class="notice">'+(verify?'Starting a real background model check…':'Saving encrypted settings…')+'</div>';
      let savedAck=false;
      try {
        const r=await api(verify?'/api/admin/providers/connect/start':'/api/admin/providers/connect',{method:'POST',body:payload});
        if(!alive())return;
        if(verify){if(!r.job_id){const e=new Error('Server did not acknowledge a background check.');e.outcomeUnknown=true;throw e;}clearTypedKey();await follow(r.job_id);}
        else{savedAck=!!r.saved;clearTypedKey();await showSaved(r);}
      }catch(e){showError(e,savedAck);}
      finally{if(!activeJob)setBusy(false);}
    }
    root.onsubmit=e=>{e.preventDefault();save(true);}; $('#connect-save-only').onclick=()=>save(false);
    $('#connect-cancel').onclick=async()=>{if(activeJob){try{await api('/api/jobs/'+activeJob+'/cancel',{method:'POST',body:{}});if(alive())$('#connect-result').innerHTML='<div class="notice warn">Cancellation requested. Waiting for the server to confirm; upstream usage may already have occurred.</div>';}catch(e){showError(e);}}};
    // Only job IDs and safe results are fetched; keys never enter browser storage.
    resumeRecent();
    $$('.provider-form').forEach(form => {
      if (form.dataset.kind !== 'chat') return;
      form.querySelector('[name="provider"]').onchange = e => {
        const provider = e.target.value;
        form.querySelector('[name="api_key"]').value = '';
        if (provider === 'gemini') { form.querySelector('[name="base_url"]').value = GEMINI_BASE; form.querySelector('[name="model"]').value = GEMINI_MODEL; }
        if (provider === 'openai_compatible') { form.querySelector('[name="base_url"]').value = 'https://api.openai.com/v1'; form.querySelector('[name="model"]').value = 'gpt-4o-mini'; }
        if (provider === 'ollama') { form.querySelector('[name="base_url"]').value = 'http://127.0.0.1:11434'; form.querySelector('[name="model"]').value = 'llama3.2'; }
      };
    });
    $$('.provider-form').forEach(form => form.onsubmit = async e => {
      e.preventDefault(); const kind = form.dataset.kind, f = new FormData(form);
      const patch = { provider: f.get('provider'), base_url: f.get('base_url').trim(), enabled: f.has('enabled') };
      if (kind !== 'web_search') patch.model = f.get('model').trim();
      if (f.get('api_key').trim()) patch.api_key = f.get('api_key').trim();
      if (kind === 'chat') patch.capabilities = { streaming: f.has('streaming') };
      try { await api('/api/admin/providers', { method: 'PATCH', body: { [kind]: patch } }); if (!form.isConnected) return; form.querySelector('[name="api_key"]').value = ''; $('.provider-save-status', form).textContent = 'Saved securely. Verify with a real request.'; state.config = await api('/api/config/public'); toast('Provider settings saved', 'ok'); }
      catch (e) { if (form.isConnected) $('.provider-save-status', form).textContent = e.message; }
    });
    $('#provider-test').onclick = async e => {
      if(busy)return; e.target.disabled=true; $('#provider-health').innerHTML='<p class="muted">Testing the saved provider in the background…</p>';
      try { const started=await api('/api/admin/providers/test/start',{method:'POST',body:{}}); const r=await waitJob(started.job_id); if(r&&alive())$('#provider-health').innerHTML=`<div class="notice ${r.online?'connect-success':'danger'}">${esc(r.message)}</div><pre>${esc(JSON.stringify(r,null,2))}</pre>`; }
      catch(error){if(alive())$('#provider-health').innerHTML=`<div class="notice danger">${esc(error.message)}</div>`;}
      finally{activeJob='';setBusy(false);if(alive())e.target.disabled=false;}
    };
  };
}
