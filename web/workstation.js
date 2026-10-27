/* Connected engineering workstation. No external assets or runtime libraries. */
import { createCircuitStudio } from './studio.js?v=10';
import { createAPIKeyPanel } from './ai-connection.js?v=10';
export function createWorkstation(h) {
  const { $, $$, esc, api, apiText, sessionFetch, toast, modal, closeModal, go, copy, download, state, pageHead, badge, table, fmtDate } = h;
  const studio = createCircuitStudio(h);
  const viewProviders = createAPIKeyPanel(h);
  const json = v => JSON.stringify(v, null, 2);
  const buttons = p => `<a class="btn sm" href="#/studio/${p}">Circuit Studio</a><a class="btn sm" href="#/code/${p}">Code Engineer</a><a class="btn sm" href="#/projects/${p}">Build guide</a><a class="btn sm" href="#/assistant?project=${p}">Ask with context</a>`;
  const warn = msg => `<div class="notice warn">${esc(msg)}</div>`;
  function md(text) {
    // Escape first. Raw model/file HTML is never inserted as markup.
    const blocks = [];
    let t = String(text || '').replace(/```([^\n]*)\n([\s\S]*?)```/g, (_, lang, code) => {
      const k = blocks.length; blocks.push(`<div class="code-label">${esc(lang || 'code')}</div><pre>${esc(code)}</pre>`); return `\u0000${k}\u0000`;
    });
    t = esc(t).replace(/^### (.+)$/gm, '<h4>$1</h4>').replace(/^## (.+)$/gm, '<h3>$1</h3>').replace(/^# (.+)$/gm, '<h2>$1</h2>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
      .replace(/\n/g, '<br>');
    return t.replace(/\u0000(\d+)\u0000/g, (_, k) => blocks[+k]);
  }
  async function selectedProjects() { return (await api('/api/designs')).projects; }
  function projectOptions(ps, selected = '') { return `<option value="">No project · general conversation</option>${ps.map(p => `<option value="${p.id}" ${selected === p.id ? 'selected' : ''}>${esc(p.name)} · r${p.revision}</option>`).join('')}`; }
  async function providerNotice() {
    const s = await api('/api/ai/status');
    return { status: s, html: !s.chat.configured ? `<div class="notice warn mb"><b>Online AI needs configuration.</b> Missing: ${esc(s.chat.missing.join(', '))}. ${state.me.entitlement.is_admin ? '<a class="btn primary sm mt-s" href="#/ai-settings">Add API key & connect AI →</a>' : 'Ask the administrator to configure a provider and model.'} No generic offline answer will be substituted.</div>` : `<div class="provider-strip"><i class="status-dot"></i> ${esc(s.chat.provider)} / ${esc(s.chat.model)} · configured, not a connectivity guarantee · ${s.chat.capabilities.streaming ? 'streaming enabled' : 'non-streaming'}</div>` };
  }
  async function watchJob(jid, onEvent, options = {}) {
    let after = 0, terminal = false; const startHash=location.hash;
    const accept = (kind, data, id) => { if (id && +id <= after) return; if (id) after = +id; onEvent?.(kind, data); if (kind === 'done' || kind === 'error') terminal = true; };
    const end = async () => {
      const j = await api(`/api/jobs/${jid}?after=${after}`);
      for (const e of j.events) accept(e.kind, e.data, e.id);
      if (['complete', 'failed', 'cancelled', 'interrupted'].includes(j.state)) return j;
      return null;
    };
    // Actual upstream streaming deltas are relayed by SSE. If the preview proxy
    // buffers/closes streams, durable event polling resumes from the last ID.
    try {
      const res = await sessionFetch(`/api/jobs/${jid}/events`, { signal: options.signal });
      if (res.ok && res.body?.getReader) {
        const reader = res.body.getReader(), decoder = new TextDecoder(); let pending = '';
        for (;;) {
          const { value, done } = await reader.read(); if (done) break;
          pending += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = pending.indexOf('\n\n')) >= 0) {
            const frame = pending.slice(0, idx); pending = pending.slice(idx + 2);
            let kind = '', data = '', id = 0;
            for (const line of frame.split('\n')) { if (line.startsWith('event:')) kind = line.slice(6).trim(); if (line.startsWith('data:')) data += line.slice(5).trim(); if (line.startsWith('id:')) id = +line.slice(3); }
            if (kind && data) { try { accept(kind, JSON.parse(data), id); } catch (e) { console.warn('Invalid event frame'); } }
          }
          if (terminal) { await reader.cancel(); break; }
        }
      }
    } catch (e) { if (options.signal?.aborted) return null; }
    for (let i = 0; i < 360; i++) {
      if (options.signal?.aborted || location.hash!==startHash) return null;
      const result = await end(); if (result) return result;
      await new Promise(r => setTimeout(r, 750));
    }
    throw new Error('Job is still running. Reopen the conversation/history to check its persisted status.');
  }
  async function imageHydrate(root = document) {
    for (const img of $$('img[data-image-id]', root)) {
      if (img.dataset.loaded) continue; img.dataset.loaded = '1';
      try { const r = await api('/api/images/' + img.dataset.imageId); if (img.isConnected) img.src = r.data_uri; }
      catch (e) { img.outerHTML = warn('Image unavailable: ' + e.message); }
    }
  }

  async function viewAssistant(qs = '') {
    const params = new URLSearchParams(qs), ps = await selectedProjects(), project = params.get('project') || '';
    let cid = params.get('conversation') || '', activeJob = '', lastQuestion = '', lastAction='auto', controller = null;
    const notice = await providerNotice(); const list = await api('/api/conversations' + (project ? '?project_id=' + project : ''));
    $('#view').innerHTML = `${pageHead('AI Assistant', 'Ask anything. Work with a project when you need its exact saved engineering context.')}
      ${notice.html}<div class="assistant-layout"><aside class="convo-list card"><button class="btn primary" id="new-chat">＋ New conversation</button>
      <div class="nav-label">SAVED CONVERSATIONS</div><div id="conversations">${list.conversations.length ? list.conversations.map(c => `<a class="convo-item ${cid === c.id ? 'selected' : ''}" href="#/assistant?conversation=${c.id}${c.project_id ? '&project=' + c.project_id : ''}"><span>${esc(c.title)}</span><small>${c.project_id ? 'Project context' : 'General'} · ${fmtDate(c.updated_at)}</small></a>`).join('') : '<p class="muted tiny">Your conversation history will appear here.</p>'}</div></aside>
      <div class="chat-workspace card"><div class="row between mb"><label class="context-select">Context <select id="chat-project">${projectOptions(ps, project)}</select></label><button class="btn ghost sm" id="delete-chat" ${!cid ? 'disabled' : ''}>Delete conversation</button></div>
      <div id="chat-messages" class="chat-messages" aria-live="polite"><div class="chat-empty"><div class="engineering-orb">N</div><h2>A conversation. An engineering partner.</h2><p>Explain a concept, debug code, explore an unfamiliar idea.<br>Select a project to bring its circuit, code and tests into context.</p><div class="suggestions">${['Explain a programming concept', 'Help me reason through a design', 'Review my project constraints'].map(s => `<button class="btn sm suggestion">${s}</button>`).join('')}</div></div></div>
      <div id="chat-attachments" class="tiny muted"></div><div class="composer"><textarea id="chat-input" rows="3" placeholder="Message NEXUS… (Shift+Enter for a new line)"></textarea>
      <div class="row between"><div class="row"><select id="chat-action" aria-label="Assistant action"><option value="auto">Auto · conversational</option><option value="chat">Answer directly</option><option value="invention">Create / iterate invention</option><option value="validate">Validate saved circuit</option><option value="code">Preview firmware rebuild</option><option value="report">Report from saved state</option></select><button class="btn ghost sm" id="attach-file">Attach text/code</button><input type="file" id="chat-file" hidden></div><div class="row"><button class="btn sm danger" id="stop-chat" hidden>Stop</button><button class="btn primary" id="send-chat">Send ↗</button></div></div></div>
      <div class="tiny muted mt-s">Provider errors are shown as errors. Tools run only for explicit requests. Files: text/code, ≤256 KB; no PDF/vision ingestion yet.</div></div></div>`;
    const root = $('#view'); const alive = () => root?.isConnected && !!$('#chat-messages');
    const renderMessages = async () => {
      if (!cid) return;
      const r = await api('/api/conversations/' + cid); if (!alive()) return;
      $('#chat-project').value = r.conversation.project_id || ''; $('#chat-project').disabled = true;
      $('#delete-chat').disabled = false;
      const freshList=await api('/api/conversations'+(r.conversation.project_id?'?project_id='+r.conversation.project_id:''));
      if(!alive())return;
      $('#conversations').innerHTML=freshList.conversations.map(c=>`<a class="convo-item ${cid===c.id?'selected':''}" href="#/assistant?conversation=${c.id}${c.project_id?'&project='+c.project_id:''}"><span>${esc(c.title)}</span><small>${c.project_id?'Project context':'General'} · ${fmtDate(c.updated_at)}</small></a>`).join('');
      const attach = await api(`/api/conversations/${cid}/attachments`);
      $('#chat-attachments').textContent = attach.attachments.map(f => `▧ ${f.name} (${f.size} chars)`).join(' · ');
      const msgs = r.messages; const lastUser=[...msgs].reverse().find(m=>m.role==='user'); lastQuestion=lastUser?.content||''; lastAction=lastUser?.meta?.action||'auto';
      $('#chat-messages').innerHTML = msgs.filter(m=>m.status!=='streaming').map(m => `<article class="chat-msg ${m.role}"><div class="message-avatar">${m.role === 'user' ? 'U' : 'N'}</div><div class="message-body"><div class="message-meta">${m.role === 'user' ? esc(state.me.user.name || 'You') : 'NEXUS'} ${m.meta.mode === 'online' ? badge('Online · ' + m.meta.model, 'green') : m.meta.tool_result ? badge(m.meta.tool_result, 'cyan') : ''}</div><div class="message-content">${md(m.content)}</div>${m.meta.images?.map(id => `<figure class="chat-image"><img data-image-id="${id}" alt="AI-generated concept visual"><figcaption>Concept only — not an electrical diagram.</figcaption></figure>`).join('') || ''}
        ${m.meta.project_id ? `<div class="row mt-s">${buttons(m.meta.project_id)}</div>` : ''}
        ${m.status !== 'complete' && m.status !== 'streaming' ? `<div class="notice danger">${esc(m.meta.error?.message || 'Request interrupted; no successful answer was substituted.')}</div><button class="btn sm retry-chat">Retry last request</button>` : ''}</div></article>`).join('');
      imageHydrate($('#chat-messages')); $$('.retry-chat').forEach(b => b.onclick = () => send(lastQuestion,lastAction));
      $('#chat-messages').scrollTop = $('#chat-messages').scrollHeight;
      if (r.active_job && !activeJob) follow(r.active_job);
    };
    const ensureConversation = async () => { if (!cid) { const r = await api('/api/conversations', { method: 'POST', body: { project_id: $('#chat-project').value || null } }); cid = r.id; $('#chat-project').disabled = true; try { history.replaceState(null,'','#/assistant?conversation='+cid+($('#chat-project').value?'&project='+$('#chat-project').value:'')); } catch(e) {} } };
    const follow = async jid => {
      activeJob = jid; controller = new AbortController(); $('#send-chat').disabled = true; $('#stop-chat').hidden = false;
      let bubble = document.createElement('article'); bubble.className = 'chat-msg assistant live-msg'; bubble.innerHTML = '<div class="message-avatar">N</div><div class="message-body"><div class="message-meta">NEXUS · processing</div><div class="message-content"><span class="thinking">Waiting for provider / tool…</span></div></div>'; $('#chat-messages').appendChild(bubble);
      let text = '';
      try {
        await watchJob(jid, (kind, data) => { if (!alive() || !bubble.isConnected) return; if (kind === 'delta') { text += data.text || ''; $('.message-content', bubble).textContent = text; $('#chat-messages').scrollTop = $('#chat-messages').scrollHeight; } if (kind === 'error') $('.message-content', bubble).innerHTML = `<div class="notice danger">${esc(data.message)}</div>`; }, { signal: controller.signal });
      } catch (e) { if (alive()) toast(e, 'err'); }
      activeJob = ''; if (alive()) { $('#send-chat').disabled = false; $('#stop-chat').hidden = true; await renderMessages(); }
    };
    const send = async (override,chosenAction) => {
      if (activeJob) return;
      const text = typeof override === 'string' ? override : $('#chat-input').value.trim(); if (!text) return;
      try { await ensureConversation(); const r = await api(`/api/conversations/${cid}/messages`, { method: 'POST', body: { message: text, action: chosenAction || $('#chat-action').value } }); $('#chat-input').value = ''; lastQuestion = text;
        $('#chat-messages .chat-empty')?.remove(); const user = document.createElement('article'); user.className = 'chat-msg user'; user.innerHTML = `<div class="message-avatar">U</div><div class="message-body">${md(text)}</div>`; $('#chat-messages').appendChild(user); await follow(r.job_id);
      } catch (e) { toast(e, 'err'); }
    };
    $('#send-chat').onclick = send;
    $('#chat-input').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
    $('#stop-chat').onclick = async () => { if (activeJob) { await api(`/api/jobs/${activeJob}/cancel`, { method: 'POST', body: {} }); toast('Cancellation requested; upstream usage may already have occurred.'); } };
    $('#new-chat').onclick = () => go('#/assistant?' + (project ? 'project=' + project + '&' : '') + 'new=' + Date.now());
    $('#chat-project').onchange = e => go('#/assistant?project=' + e.target.value);
    $('#delete-chat').onclick = async () => { if (cid && confirm('Delete this conversation and its attached assets?')) { await api('/api/conversations/' + cid, { method: 'DELETE' }); go('#/assistant?new=' + Date.now()); } };
    $$('.suggestion').forEach(b => b.onclick = () => { $('#chat-input').value = b.textContent; $('#chat-input').focus(); });
    $('#attach-file').onclick = () => $('#chat-file').click();
    $('#chat-file').onchange = async e => { const f = e.target.files[0]; if (!f) return; if (f.size > 256000) return toast('Text attachment limit: 256 KB', 'err'); try { await ensureConversation(); await api(`/api/conversations/${cid}/attachments`, { method: 'POST', body: { name: f.name, text: await f.text() } }); await renderMessages(); toast('Attached to this conversation', 'ok'); } catch (e) { toast(e, 'err'); } };
    if (cid) await renderMessages();
  }

  async function newProject() {
    const c = (await api('/api/components')).components;
    const choices = ['soil_cap', 'gas_mq2', 'bme280', 'dht22', 'pump', 'buzzer', 'led'];
    modal('Create a persistent engineering design', `<p class="muted">Manual, explicit supported-component workflow. This does not call an AI model.</p><label class="field"><span>Project name</span><input id="design-name" placeholder="My new prototype"></label><label class="field"><span>Problem / expected behavior</span><textarea id="design-problem" placeholder="What should this device do?"></textarea></label><label class="field"><span>Board</span><select id="design-board"><option value="esp32">ESP32 DevKit V1</option><option value="esp32s3">ESP32-S3 DevKitC-1</option></select></label><div class="field"><span>Components (protection parts are added explicitly)</span><div class="component-checks">${choices.map(k => `<label><input type="checkbox" value="${k}" name="design-parts"> ${esc(c[k].name)}</label>`).join('')}</div></div>${!state.me.entitlement.is_pro ? warn('Free: up to two high-level components and configured project limits. Advanced circuit editing is Pro.') : ''}<button class="btn primary mt" id="create-design">Create & open Circuit Studio</button><div id="create-design-error" class="mt"></div>`, m => {
      $('#create-design', m).onclick = async e => { e.target.disabled = true; try { const r = await api('/api/designs', { method: 'POST', body: { name: $('#design-name', m).value, board: $('#design-board', m).value, components: $$('input[name="design-parts"]:checked', m).map(x => x.value), requirements: { problem: $('#design-problem', m).value } } }); closeModal(); go('#/studio/' + r.id); } catch (e) { $('#create-design-error', m).innerHTML = `<div class="notice danger">${esc(e.message)}</div>`; $('#create-design', m).disabled = false; } };
    });
  }

  async function viewProjects(id) {
    const ps = await selectedProjects();
    if (!id) {
      const legacy = await api('/api/workspaces');
      $('#view').innerHTML = `${pageHead('My Projects', 'Your private, versioned engineering designs. Each project keeps its own circuit, firmware and evidence.', '<button class="btn primary" id="new-design">＋ Create design</button>')}
      <div class="design-list">${ps.length ? ps.map(p => `<article class="design-card card"><div class="design-icon">⌘</div><div class="grow"><div class="row between"><h3><a href="#/projects/${p.id}">${esc(p.name)}</a></h3>${badge('Revision ' + p.revision)}</div><p class="tiny muted">${p.id} · updated ${fmtDate(p.updated_at)}</p><div class="row">${buttons(p.id)}</div></div></article>`).join('') : '<div class="empty card"><h3>No engineering designs yet</h3><p>Create a manual design with supported components, or ask Invention Lab to propose a new one.</p><a class="btn" href="#/invention">Open AI Invention Lab →</a></div>'}</div>
      <div class="row mt"><a class="btn sm" href="#/invention">AI Invention Lab</a><a class="btn sm" href="#/tools/project_docs">Legacy workspaces (${legacy.workspaces.length})</a></div>`;
      $('#new-design').onclick = newProject; return;
    }
    const p = await api('/api/designs/' + id), s = p.spec;
    $('#view').innerHTML = `${pageHead(p.name, `Private project · ${p.id} · revision ${p.revision}`, '<button class="btn danger sm" id="delete-design">Delete</button>')}
    <div class="row mb">${buttons(id)}<a class="btn sm" href="#/invention?project=${id}">Iterate design</a><button class="btn primary sm" id="engineering-pack">Download engineering pack</button></div>
    ${s.firmware.mismatch ? warn('Circuit topology changed. Pin constants were synchronized, but drivers need review/rebuild in Code Engineer.') : ''}
    <div class="grid g2"><div class="card"><h3>Requirements & assumptions</h3><label class="field"><span>Problem</span><textarea id="project-problem">${esc(s.requirements.problem || '')}</textarea></label><label class="field"><span>Constraints / notes</span><textarea id="project-constraints">${esc(s.requirements.constraints || '')}</textarea></label><button class="btn sm primary" id="save-req">Save requirements</button><details class="mt"><summary>Full saved proposal / assumptions</summary><pre>${esc(json(s.requirements))}</pre></details></div><div class="card"><h3>Verification status</h3>${badge('NOT physically tested', 'amber')} ${badge('No simulation run', 'amber')}<p class="muted mt">A rule-check pass is not an electrical safety certificate or proof of buildability.</p><button class="btn sm" id="static-check">Run & record static checks</button><div id="static-result" class="mt">${s.testing.length ? `<pre>${esc(json(s.testing.at(-1)))}</pre>` : '<p class="tiny muted">No recorded test results.</p>'}</div></div></div>
    <div class="card mt"><div class="row between"><h3>Implementation guide</h3><button class="btn sm" id="report-export">Export saved-state report</button></div><p>${esc(s.guide.objective)}</p><h4>Architecture</h4><p>${esc(s.guide.architecture)}</p><h4>Bill of materials</h4>${table(s.guide.bom, [['instance', 'ID'], ['name', 'Component'], ['supply_v', 'Supply V'], ['current_ma_assumed', 'Assumed mA'], ['price', 'Pricing']])}
      <div class="build-steps">${s.guide.assembly.map(step => `<section><span class="step-index">${step.step}</span><div><h4>${esc(step.title)}</h4><p>${esc(step.detail)}</p></div></section>`).join('')}</div><h4>Limitations</h4><ul>${s.guide.limitations.map(x => `<li>${esc(x)}</li>`).join('')}</ul><h4>References</h4>${s.guide.references.map(r => `<p><a href="${esc(r)}" target="_blank" rel="noopener noreferrer">${esc(r)}</a></p>`).join('')}</div>
    <div class="card mt"><h3>Version history</h3><div id="project-versions"></div></div>`;
    $('#save-req').onclick = async () => { try { await api('/api/designs/' + id, { method: 'PATCH', body: { revision: p.revision, patch: { requirements: { ...s.requirements, problem: $('#project-problem').value, constraints: $('#project-constraints').value } } } }); toast('Requirements saved', 'ok'); viewProjects(id); } catch (e) { toast(e, 'err'); } };
    $('#engineering-pack').onclick = async e => { e.target.disabled = true; try { const pack = await api('/api/designs/' + id + '/engineering-pack'); download('nexus-engineering-pack-' + id + '-r' + p.revision + '.json', JSON.stringify(pack, null, 2), 'application/json'); toast('Engineering pack generated from saved project data', 'ok'); } catch (err) { toast(err, 'err'); } finally { e.target.disabled = false; } };
    $('#delete-design').onclick = async () => { if (confirm('Delete this private design and its version history?')) { await api('/api/designs/' + id, { method: 'DELETE' }); go('#/projects'); } };
    $('#static-check').onclick = async e => { e.target.disabled = true; try { const r = await api(`/api/designs/${id}/validate`, { method: 'POST', body: {} }); toast(r.passed ? 'Static checks passed — not hardware validation' : 'Static findings recorded'); viewProjects(id); } catch (e) { toast(e, 'err'); e.target.disabled = false; } };
    $('#report-export').onclick = () => exportDesign(id, 'markdown');
    if (state.me.entitlement.is_pro) {
      const versions = await api(`/api/designs/${id}/versions`);
      $('#project-versions').innerHTML = table(versions.versions, [['revision', 'Revision'], ['summary', 'Change'], ['created_at', 'Saved', fmtDate], ['revision', 'Restore', v => `<button class="btn sm restore-design" data-version="${v}" ${v === p.revision ? 'disabled' : ''}>Restore</button>`]]);
      $$('.restore-design').forEach(b => b.onclick = async () => { if (confirm(`Restore revision ${b.dataset.version} as a new revision?`)) { try { await api(`/api/designs/${id}/restore`, { method: 'POST', body: { version: +b.dataset.version, revision: p.revision } }); viewProjects(id); } catch (e) { toast(e, 'err'); } } });
    } else $('#project-versions').innerHTML = '<p class="muted">Advanced version restore is Pro. Your saved design remains accessible.</p>';
  }
  async function exportDesign(id, kind) {
    try { const text = await apiText(`/api/designs/${id}/export?kind=${kind}`); modal('Export · ' + kind, `<pre id="design-export-text">${esc(text)}</pre><div class="row"><button class="btn sm" id="design-copy">Copy</button><button class="btn primary sm" id="design-download">Download</button></div>`, m => { $('#design-copy', m).onclick = () => { copy(text); toast('Copied', 'ok'); }; $('#design-download', m).onclick = () => download('nexus-' + id + '.' + ({ markdown: 'md', code: 'ino', wiring: 'csv', svg: 'svg', json: 'json' }[kind]), text, kind === 'svg' ? 'image/svg+xml' : 'text/plain'); }); } catch (e) { toast(e, 'err'); }
  }

  async function viewCode(id) {
    const ps = await selectedProjects();
    if (!id) id = ps[0]?.id;
    if (!id) { $('#view').innerHTML = pageHead('Code Engineer', 'Create or open a persistent engineering design first.') + '<button class="btn primary" id="new-code-project">＋ Create project</button>'; $('#new-code-project').onclick = newProject; return; }
    let p = await api('/api/designs/' + id), fw = p.spec.firmware;
    $('#view').innerHTML = `${pageHead('Code Engineer', 'Graph-derived pin configuration. Your source edits are preserved when pins move.')}
    <div class="row between mb"><select id="code-project">${projectOptions(ps, id)}</select><div class="row">${buttons(id)}</div></div>
    ${fw.mismatch ? warn('Circuit/driver mismatch: component topology changed. Review a rebuild diff before replacing source.') : ''}
    <div class="code-workspace"><aside class="card"><div class="nav-label">FILES</div><div class="file-item active">▧ ${esc(fw.filename)}</div><h4 class="mt">Dependencies</h4>${fw.libraries.length ? fw.libraries.map(l => `<p class="tiny muted">${esc(l)}</p>`).join('') : '<p class="tiny muted">ESP32 Arduino core</p>'}<h4 class="mt">Build status</h4>${badge(fw.status, 'amber')}<p class="tiny muted mt">No Arduino compiler or electrical simulator installed. No user code is executed by this server.</p><a class="btn sm" href="#/assistant?project=${id}">Explain / debug with AI</a><a class="btn sm mt-s" href="#/tools/debugging">Repair center</a></aside>
    <div class="card code-main"><div class="row between mb"><span class="mono tiny">firmware.ino <span id="code-dirty" class="amber"></span></span><div class="row"><button class="btn sm" id="copy-source">Copy</button><button class="btn sm" id="preview-rebuild">Preview driver rebuild</button><button class="btn primary sm" id="save-source">Save source</button></div></div>
    <textarea spellcheck="false" id="source-editor" class="source-editor" aria-label="Firmware source editor">${esc(fw.code)}</textarea><div class="row mt-s"><button class="btn sm" id="check-source">Run static checks on saved source</button><button class="btn sm" id="export-source">Export code</button><span class="tiny muted">Graph ${esc(fw.graph_hash)} · revision <span id="code-revision">${p.revision}</span></span></div><div id="code-results" class="mt"></div></div></div>
    <div class="card mt"><h3>Configuration & upload</h3><ol>${fw.instructions.map(i => `<li>${esc(i)}</li>`).join('')}</ol>${fw.warnings.map(w => warn(w)).join('')}</div>`;
    $('#view').insertAdjacentHTML('beforeend', `<div class="card mt"><div class="eyebrow">ONLINE / PROJECT-SPECIFIC FIRMWARE</div><h3>Develop or revise an algorithm with the configured model</h3><p class="tiny muted">The model sees this project's saved circuit, requirements and source. It must preserve the canonical pin region. Proposals are saved and require a diff review before applying; source is never executed on this server.</p><label class="field"><span>Requested behavior or code change</span><textarea id="ai-code-request" placeholder="Describe the algorithm, reliability or communication change. Include required assumptions and constraints."></textarea></label><div class="row"><button class="btn primary sm" id="ai-code-run">Generate source proposal</button><button class="btn sm danger" id="ai-code-cancel" hidden>Cancel</button></div><div id="ai-code-result" class="mt"></div><h4 class="mt">Saved code proposals</h4><div id="ai-code-history"></div></div>`);
    const reviewAI = proposal => {
      if(proposal.project_id!==id) return toast('This proposal belongs to a different project. Open that project to review it.','err');
      modal('Review online firmware proposal', `<div class="notice warn">${esc(proposal.warning)}</div><p>${esc(proposal.summary)}</p><p class="tiny muted">${esc(proposal.provider)} / ${esc(proposal.model)} · source revision ${proposal.source_revision}</p><pre>${esc(proposal.diff || 'No source changes.')}</pre><h4>Remaining manual work</h4><pre>${esc(json(proposal.manual_work))}</pre><button class="btn primary" id="apply-ai-code">Apply reviewed source proposal</button>`, m=> {
        $('#apply-ai-code',m).onclick=async()=>{try{await api('/api/designs/'+id,{method:'PATCH',body:{revision:proposal.source_revision,patch:{firmware:{code:proposal.code,libraries:proposal.libraries}},summary:'Applied reviewed online source proposal'}});closeModal();viewCode(id);}catch(e){toast(e,'err');}};
      });
    };
    const reloadCodeHistory=async()=>{const r=await api('/api/jobs?kind=ai_code');if(!$('#ai-code-history'))return;$('#ai-code-history').innerHTML=r.jobs.map(j=>`<button class="btn sm code-proposal-history" data-job="${j.id}">${fmtDate(j.created_at)} · ${esc(j.state)}</button>`).join('')||'<p class="tiny muted">No source proposals yet.</p>';$$('.code-proposal-history').forEach(b=>b.onclick=async()=>{try{const j=await api('/api/jobs/'+b.dataset.job);if(j.state==='complete')reviewAI(j.output);else modal('Source proposal status',`<pre>${esc(json(j.error.state?j.error:{state:j.state,error:j.error}))}</pre>`);}catch(e){toast(e,'err');}});};
    let codeJob='';
    $('#ai-code-run').onclick=async e=>{e.target.disabled=true;$('#ai-code-cancel').hidden=false;try{const r=await api(`/api/designs/${id}/ai-code`,{method:'POST',body:{request:$('#ai-code-request').value}});codeJob=r.job_id;$('#ai-code-result').innerHTML='<p class="muted">Calling the actual configured model; no source has been changed…</p>';const j=await watchJob(codeJob);if(!j||!$('#ai-code-result'))return;if(j.state!=='complete')throw new Error(j.error.message||j.state);$('#ai-code-result').innerHTML='<div class="notice">Proposal saved. Review the diff before applying.</div>';reviewAI(j.output);await reloadCodeHistory();}catch(error){if($('#ai-code-result'))$('#ai-code-result').innerHTML=`<div class="notice danger">${esc(error.message)}</div>`;}if($('#ai-code-run')){$('#ai-code-run').disabled=false;$('#ai-code-cancel').hidden=true;}};
    $('#ai-code-cancel').onclick=()=>codeJob&&api(`/api/jobs/${codeJob}/cancel`,{method:'POST',body:{}});
    await reloadCodeHistory();
    $('#code-project').onchange = e => { if (e.target.value) go('#/code/' + e.target.value); };
    $('#source-editor').oninput = () => $('#code-dirty').textContent = '• unsaved';
    $('#source-editor').onkeydown = e => { if (e.key === 'Tab') { e.preventDefault(); const a = e.target.selectionStart, b = e.target.selectionEnd; e.target.setRangeText('  ', a, b, 'end'); $('#code-dirty').textContent = '• unsaved'; } };
    $('#copy-source').onclick = () => { copy($('#source-editor').value); toast('Copied', 'ok'); };
    $('#save-source').onclick = async () => { try { p = await api('/api/designs/' + id, { method: 'PATCH', body: { revision: p.revision, patch: { firmware: { code: $('#source-editor').value } }, summary: 'Source edits' } }); $('#code-dirty').textContent = ''; $('#code-revision').textContent = p.revision; toast('Source saved', 'ok'); } catch (e) { toast(e, 'err'); } };
    $('#preview-rebuild').onclick = async () => { try { const r = await api(`/api/designs/${id}/code-preview`, { method: 'POST', body: {} }); modal('Review firmware rebuild', `<p class="notice warn">${esc(r.warning)}</p><pre>${esc(r.diff || 'No source changes.')}</pre><button class="btn primary" id="accept-rebuild">Replace source with reviewed generated version</button>`, m => { $('#accept-rebuild', m).onclick = async () => { try { await api('/api/designs/' + id, { method: 'PATCH', body: { revision: r.revision, patch: { firmware: { code: r.firmware.code, accept_generated: true } }, summary: 'Confirmed driver rebuild' } }); closeModal(); viewCode(id); } catch (e) { toast(e, 'err'); } }; }); } catch (e) { toast(e, 'err'); } };
    $('#check-source').onclick = async () => { try { const r = await api(`/api/designs/${id}/validate`, { method: 'POST', body: {} }); $('#code-results').innerHTML = `<pre>${esc(json(r))}</pre>`; p = await api('/api/designs/' + id); $('#code-revision').textContent = p.revision; } catch (e) { toast(e, 'err'); } };
    $('#export-source').onclick = () => exportDesign(id, 'code');
  }

  async function viewInvention(qs = '') {
    const ps = await selectedProjects(), pid = new URLSearchParams(qs).get('project') || '', notice = await providerNotice(); let jid = '';
    const runs = await api('/api/jobs?kind=invention');
    $('#view').innerHTML = `${pageHead('AI Invention Lab', 'From an unfamiliar problem to a persistent, constrained engineering proposal.')}${notice.html}
      <div class="invention-layout"><div class="card"><div class="eyebrow">01 / DEFINE THE PROBLEM</div><label class="field"><span>New invention or iteration</span><select id="invent-project">${projectOptions(ps, pid)}</select></label><label class="field"><span>What do you want to invent or change?</span><textarea rows="7" id="invent-idea" placeholder="Describe the problem, environment and expected behavior. This does not have to exist in the library."></textarea></label><label class="field"><span>Budget, parts, power, connectivity, size, experience</span><textarea id="invent-constraints" placeholder="List what you know. Missing details become explicit assumptions or clarifying questions."></textarea></label><div class="row mt"><button class="btn primary" id="invent-run">Develop architecture & design ↗</button><button class="btn danger sm" id="invent-cancel" hidden>Cancel</button></div><p class="tiny muted mt">Only supported component definitions can be wired automatically. Unknown sensors remain named blockers, not fabricated pinouts. Major iterations require review before applying.</p></div>
      <div class="card" id="invent-output"><div class="eyebrow">02 / ENGINEERING PROPOSAL</div><div class="empty"><h3>Explore beyond the catalogue</h3><p>The model proposes requirements and components. Circuit rules, matching driver templates, saved-state documentation and a test plan then turn supported portions into a private design.</p><p>Specialized algorithms, physical tests and unavailable components remain explicit engineering work.</p></div></div></div>
      <div class="card mt"><h3>Supported manual workflow</h3><p class="muted">No credentials yet? You can still create a design by selecting documented components, inspect the exact-pin graph and run deterministic rules. This is not presented as online AI.</p><button class="btn sm" id="invent-manual">Create manual design</button></div><div class="card mt"><h3>Saved invention requests</h3><div class="row">${runs.jobs.map(j=>`<button class="btn sm invention-history" data-job="${j.id}">${fmtDate(j.created_at)} · ${esc(j.state)}</button>`).join('')||'<p class="tiny muted">Requests and completed proposals will remain here after reload.</p>'}</div></div>`;
    const showProposal=(o,jobId)=>{
      $('#invent-output').innerHTML = `<div class="eyebrow">PROPOSAL · ${esc(o.proposal.model)}</div><h2>${esc(o.proposal.title)}</h2><p>${esc(o.proposal.problem)}</p>${o.unsupported_components.length ? warn('Unsupported components remain: ' + json(o.unsupported_components)) : ''}<div class="row mt">${buttons(o.project_id)}</div><p class="tiny muted mt">${o.created ? 'Saved as a new private project.' : 'Iteration preview only. Existing circuit and user source are unchanged.'}</p><details open><summary>Architecture & requirements</summary><pre>${esc(json(o.proposal))}</pre></details><details><summary>Circuit validation and remaining work</summary><pre>${esc(json({ validation: o.validation, remaining_work: o.remaining_work, research: o.research }))}</pre></details>${o.source_revision ? `<pre>${esc(json(o.changes))}</pre><button class="btn primary" id="apply-invention">Apply reviewed iteration</button>` : ''}`;
        $('#apply-invention')?.addEventListener('click', async () => { try { const r = await api(`/api/inventions/${jobId}/apply`, { method: 'POST', body: {} }); go('#/studio/' + r.id); } catch (e) { toast(e, 'err'); } });
    };
    $$('.invention-history').forEach(b=>b.onclick=async()=>{try{const j=await api('/api/jobs/'+b.dataset.job);if(j.state==='complete')showProposal(j.output,j.id);else $('#invent-output').innerHTML=`<div class="notice ${j.state==='failed'?'danger':'warn'}">${esc(j.error.message||j.state)}</div>`;}catch(e){toast(e,'err');}});
    $('#invent-manual').onclick = newProject;
    $('#invent-cancel').onclick = async () => { if (jid) await api(`/api/jobs/${jid}/cancel`, { method: 'POST', body: {} }); };
    $('#invent-run').onclick = async e => { e.target.disabled = true; $('#invent-cancel').hidden = false;
      try { const r = await api('/api/inventions', { method: 'POST', body: { idea: $('#invent-idea').value, constraints: $('#invent-constraints').value, project_id: $('#invent-project').value || null, research: false } }); jid = r.job_id; $('#invent-output').innerHTML = '<div class="processing"><div class="spinner"></div><h3>Developing the proposal</h3><p>Calling the configured provider, then checking supported component and circuit rules…</p></div>';
        const job = await watchJob(jid); if (!$('#invent-output')) return;
        if (job.state !== 'complete') throw new Error(job.error.message || job.state);
        showProposal(job.output,jid);
      } catch (error) { if ($('#invent-output')) $('#invent-output').innerHTML = `<div class="notice danger"><b>Design not completed</b><p>${esc(error.message)}</p></div>`; }
      if ($('#invent-run')) { $('#invent-run').disabled = false; $('#invent-cancel').hidden = true; }
    };
  }

  async function viewImages(qs = '') {
    const ps = await selectedProjects(), pid = new URLSearchParams(qs).get('project') || '', status = await api('/api/ai/status'); let jid = '';
    $('#view').innerHTML = `${pageHead('Image Studio', 'Real generated concept visuals, connected to your engineering projects.')}
      ${!status.image.configured ? warn('Image generation is not configured. Missing: ' + status.image.missing.join(', ') + '. Configure the separate image provider/model/key in Admin > AI Providers. No stock or placeholder image is substituted.') : `<div class="provider-strip">${esc(status.image.provider)} / ${esc(status.image.model)} · generation capability configured</div>`}
      <div class="image-studio-layout mt"><div class="card"><div class="eyebrow">CONCEPT / VISUAL EXPLORATION</div><label class="field"><span>Associate with a project</span><select id="image-project">${projectOptions(ps, pid)}</select></label><label class="field"><span>Prompt</span><textarea id="image-prompt" rows="6" placeholder="Describe the subject, intended use, materials, environment and visual detail…"></textarea></label><label class="field"><span>Style</span><input id="image-style" placeholder="e.g. clean industrial product rendering"></label><label class="field"><span>Aspect / image size (model-dependent)</span><select id="image-size"><option value="1024x1024">Square · 1024 × 1024</option><option value="1536x1024">Landscape · GPT image</option><option value="1024x1536">Portrait · GPT image</option><option value="1792x1024">Landscape · DALL·E 3</option><option value="1024x1792">Portrait · DALL·E 3</option></select></label><div class="row"><button class="btn primary" id="image-run">Generate image ↗</button><button class="btn sm danger" id="image-cancel" hidden>Cancel</button></div><p class="tiny muted mt">Premium usage limits apply. Concepts are not verified circuits, PCB layouts or buildability evidence. Prompt revisions create a new image; pixel editing is not implemented.</p></div><div class="card image-result" id="image-result"><div class="empty"><div class="visual-glyph">◇</div><h3>Your generated concept appears here</h3><p>No image is displayed until an actual provider returns valid image bytes.</p></div></div></div>
      <div class="section-title mt">Generated image history</div><div class="image-history" id="image-history"></div>`;
    let reference = '';
    const loadHistory = async () => {
      const r = await api('/api/images' + (pid ? '?project_id=' + pid : '')); if (!$('#image-history')) return;
      $('#image-history').innerHTML = r.images.length ? r.images.map(im => `<article class="card"><img data-image-id="${im.id}" class="history-image" alt="AI-generated project concept"><p>${esc(im.prompt)}</p><div class="tiny muted">${esc(im.meta.model)} · ${fmtDate(im.created_at)}</div><div class="row mt-s"><button class="btn sm revise-image" data-id="${im.id}">Prompt variation</button><button class="btn sm download-image" data-id="${im.id}">Download</button><a class="btn sm" href="#/assistant?conversation=${im.conversation_id}${im.project_id ? '&project=' + im.project_id : ''}">Conversation</a></div></article>`).join('') : '<div class="empty">No generated images yet. Failed/unconfigured requests do not create placeholders.</div>';
      imageHydrate($('#image-history'));
      $$('.revise-image').forEach(b => b.onclick = () => { const im = r.images.find(i => i.id === b.dataset.id); reference = im.id; $('#image-prompt').value = 'Revise the previous concept: '; $('#image-project').value = im.project_id || ''; $('#image-prompt').focus(); toast('Prompt-based new generation selected; not pixel editing.'); });
      $$('.download-image').forEach(b => b.onclick = async () => { const im = await api('/api/images/' + b.dataset.id); const a = document.createElement('a'); a.href = im.data_uri; a.download = 'concept-' + im.id + '.' + im.mime.split('/')[1]; a.click(); toast('Download requested. If your frame blocks it, open NEXUS in a new tab.'); });
    };
    $('#image-project').onchange = e => go('#/images' + (e.target.value ? '?project=' + e.target.value : '?all=1'));
    $('#image-cancel').onclick = async () => { if (jid) await api(`/api/jobs/${jid}/cancel`, { method: 'POST', body: {} }); };
    $('#image-run').onclick = async e => { e.target.disabled = true; $('#image-cancel').hidden = false;
      try { const r = await api('/api/images', { method: 'POST', body: { prompt: $('#image-prompt').value, style: $('#image-style').value, size: $('#image-size').value, project_id: $('#image-project').value || null, reference_id: reference || null } }); jid = r.job_id;
        $('#image-result').innerHTML = '<div class="processing"><div class="spinner"></div><h3>Generating with your provider</h3><p>Waiting for actual image bytes…</p></div>';
        const j = await watchJob(jid); if (!$('#image-result')) return; if (j.state !== 'complete') throw new Error(j.error.message || j.state);
        $('#image-result').innerHTML = `<img class="generated-concept" data-image-id="${j.output.id}" alt="Generated concept"><p class="notice warn mt">${esc(j.output.label)}</p>`; imageHydrate($('#image-result')); await loadHistory(); reference = '';
      } catch (error) { if ($('#image-result')) $('#image-result').innerHTML = `<div class="notice danger"><b>No image generated</b><p>${esc(error.message)}</p></div>`; }
      if ($('#image-run')) { $('#image-run').disabled = false; $('#image-cancel').hidden = true; }
    };
    await loadHistory();
  }

  async function viewResearch(qs = '') {
    const ps = await selectedProjects(), pid = new URLSearchParams(qs).get('project') || '';
    const runs = await api('/api/tools/runs');
    $('#view').innerHTML = `${pageHead('Research & Innovation', 'Traceable references, hypotheses and project-scoped research. No invented citations.')}
      <div class="grid g2"><div class="card"><label class="field"><span>Research question</span><textarea id="research-query" rows="5" placeholder="Describe a design trade-off, technology or unfamiliar sensor…"></textarea></label><label class="field"><span>Save references to project</span><select id="research-project">${projectOptions(ps, pid)}</select></label><button class="btn primary" id="research-run">Find sources</button><div class="divider"></div><div class="stack"><a class="btn" href="#/tools/innovation">Innovation Gap Analyzer</a><a class="btn" href="#/tools/comparison">Existing Project Comparator</a><a class="btn" href="#/tools/startup_lab">Startup & Product Opportunity Studio</a></div></div><div class="card" id="research-result"><h3>Evidence, not novelty guarantees</h3><p class="muted">A configured search provider returns real search results. Otherwise this tool explicitly matches the curated documentation corpus. Neither establishes that an invention is globally unique.</p><h4>Reopen saved searches</h4>${runs.runs.filter(r => r.tool === 'research_search').map(r => `<button class="btn sm research-history" data-run="${r.id}">${fmtDate(r.created_at)} · ${esc(r.mode)}</button>`).join('') || '<p class="tiny muted">No saved searches yet.</p>'}</div></div>`;
    const show = r => { $('#research-result').innerHTML = `<div class="row mb">${badge(r.mode, 'cyan')}</div>${warn(r.limitation)}${r.sources.map(s => `<article class="source-card"><h4><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a></h4><small>${esc(s.id)} · ${esc(s.url)}</small><p>${esc(s.excerpt || 'Curated documentation link; page content was not retrieved by this search.')}</p></article>`).join('') || '<p class="muted mt">No sources matched. Try a specific component or configure live search.</p>'}`; };
    $('#research-run').onclick = async e => { e.target.disabled = true; try { const r = await api('/api/research/search', { method: 'POST', body: { query: $('#research-query').value, project_id: $('#research-project').value || null } }); show(r); } catch (e) { $('#research-result').innerHTML = `<div class="notice danger">${esc(e.message)}</div>`; } $('#research-run').disabled = false; };
    $$('.research-history').forEach(b => b.onclick = async () => { const r = await api('/api/tools/runs/' + b.dataset.run); show(r.run.output); });
  }

  return { viewAssistant, viewProjects, viewCode, viewInvention, viewImages, viewResearch, viewProviders, viewStudio: id => studio.view(id, { newProject, exportDesign, selectedProjects, projectOptions, buttons }), newProject, watchJob };
}
