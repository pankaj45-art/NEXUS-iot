/* Exact-pin SVG editor. Graph is the only editable source of electrical truth. */
import { createDigitalTwin3D } from './digital-twin-3d.js';
export function createCircuitStudio(h) {
  const { $, $$, esc, api, toast, modal, closeModal, go, state, pageHead, badge, table } = h;
  const clone = x => JSON.parse(JSON.stringify(x));
  async function view(id, shared) {
    const ps = await shared.selectedProjects();
    if (!id) id = ps[0]?.id;
    if (!id) {
      $('#view').innerHTML = pageHead('Circuit Studio', 'A project-scoped, exact-pin engineering workspace.') + `<div class="empty card"><h2>Create your first circuit design</h2><p>Add a board and supported components, inspect connections, validate rules, and generate matching firmware.</p><button class="btn primary" id="studio-new-empty">＋ Create design</button></div>`;
      $('#studio-new-empty').onclick = shared.newProject; return;
    }
    let project = await api('/api/designs/' + id), graph = clone(project.spec.circuit);
    const catResult = await api('/api/components'), cat = catResult.components;
    let validation = project.validation, selected = '', selectedEdge = '', pending = null, dirty = false, stale = false;
    let past = [], future = [], zoom = 0.7, pan = { x: 0, y: 0 }, dragging = null;
    const canEdit = state.me.entitlement.features.includes('tools.circuit_designer');
    $('#view').innerHTML = `${pageHead('Circuit Studio', 'Exact-pin connections · canonical graph · saved separately for every project')}
      <div class="studio-projectbar"><select id="studio-project">${shared.projectOptions(ps, id)}</select><div class="row"><span class="tiny muted" id="studio-save-state">Saved revision ${project.revision}</span><a class="btn sm" href="#/projects/${id}">Build guide</a><a class="btn sm" href="#/assistant?project=${id}">Ask AI</a><button class="btn primary sm" id="studio-save" ${canEdit ? '' : 'disabled'}>Save design</button></div></div>
      ${!canEdit ? '<div class="notice warn mb">Read-only/basic project guidance. Advanced circuit editing, rule workflows and exports require Pro. Your own saved data remains accessible.</div>' : ''}
      <div class="studio-toolbar"><div class="row"><button class="btn sm" id="studio-undo" title="Undo last graph edit">↶ Undo</button><button class="btn sm" id="studio-redo">↷ Redo</button><span class="toolbar-separator"></span><button class="btn sm" id="studio-zoomout">−</button><span class="mono tiny" id="studio-zoom">70%</span><button class="btn sm" id="studio-zoomin">＋</button><button class="btn sm" id="studio-fit">Fit</button></div><div class="row"><button class="btn sm" id="studio-import">Import JSON</button><input type="file" id="studio-import-file" accept=".json,application/json" hidden><select id="studio-export-kind"><option value="svg">Connection SVG</option><option value="json">Project JSON</option><option value="wiring">Wiring CSV</option><option value="code">Firmware</option></select><button class="btn sm" id="studio-export">Export saved</button><button class="btn sm" id="studio-validate">Validate graph</button><button class="btn sm" id="studio-guide">Build guide</button><button class="btn sm" id="studio-3d-twin" style="color:#38bdf8;font-weight:700;">🎲 3D Digital Twin</button></div></div>
      <div class="studio-layout"><aside class="component-library"><div class="panel-heading">COMPONENT LIBRARY <span class="tiny muted">${Object.keys(cat).length}</span></div><input id="component-search" placeholder="Find a supported component…" aria-label="Search component library"><div id="component-list"></div><p class="tiny muted studio-library-note">Click to add. Only documented definitions are supported. An unknown part is not silently substituted.</p><button class="btn sm" id="studio-new">＋ New project</button></aside>
      <div class="circuit-center"><div class="canvas-status"><span><i class="status-dot"></i> CONNECTION DIAGRAM <span class="muted">/ NOT PCB OR SIMULATION</span></span><span id="canvas-stats"></span></div><div class="circuit-stage" id="circuit-stage" tabindex="0" aria-label="Interactive exact-pin circuit editor"></div><div class="canvas-help"><span id="canvas-help-text">Drag components · click two terminal dots to connect · wheel to zoom · Shift-drag background to pan</span><button class="btn ghost sm" id="cancel-connect" hidden>Cancel connection</button></div></div>
      <aside class="circuit-inspector"><div class="panel-heading">INSPECTOR</div><div id="circuit-properties"><div class="muted tiny">Select a component, terminal or wire to inspect its actual definition and connections.</div></div></aside></div>
      <div class="studio-bottom"><div class="card"><div class="row between"><h3>Wiring table</h3><span id="wiring-status" class="tiny muted">Derived from exact graph edges</span></div><div id="studio-wiring"></div></div><div class="card"><div class="row between"><h3>Validation findings</h3><span id="validation-status"></span></div><div id="studio-findings"></div></div></div>
      <section class="card mt" id="studio-build-guide" hidden aria-live="polite"></section>
      <div class="card mt"><div class="row between"><div><h3>Circuit ↔ firmware</h3><p class="tiny muted">Saving pin edits updates only the managed configuration region. Adding/replacing components flags driver work; unrelated source edits are kept.</p></div><a class="btn" href="#/code/${id}">Open Code Engineer →</a></div><div id="studio-sync">${project.spec.firmware.mismatch ? '<div class="notice warn">Saved firmware drivers do not match the current component topology. Review a rebuild diff.</div>' : '<div class="tiny muted">Saved graph fingerprint: ' + esc(project.validation.fingerprint) + ' · source status: ' + esc(project.spec.firmware.status) + '</div>'}</div></div>`;
    const stage = $('#circuit-stage');
    function pinCoords(n, p) { const pins = cat[n.model].pins, i = pins.findIndex(x => x.id === p); return { x: n.position.x + (i % 2 ? 210 : 0), y: n.position.y + 52 + Math.floor(i / 2) * 23 }; }
    function nodeHeight(n) { return Math.max(95, 67 + Math.ceil(cat[n.model].pins.length / 2) * 23); }
    function before() { past.push(clone(graph)); if (past.length > 60) past.shift(); future = []; }
    function changed() { dirty = stale = true; $('#studio-save-state').textContent = '● Unsaved graph · based on r' + project.revision; $('#studio-save-state').className = 'tiny amber'; draw(); inspector(); bottom(); }
    function endpoints() { return graph.components.flatMap(n => cat[n.model].pins.map(p => ({ value: n.id + '::' + p.id, label: n.id + ' . ' + p.id + ' · ' + p.type }))); }
    function draw() {
      const index = Object.fromEntries(graph.components.map(n => [n.id, n]));
      const edges = graph.connections.map(e => {
        const a = pinCoords(index[e.from.component], e.from.pin), b = pinCoords(index[e.to.component], e.to.pin), mid = (a.x + b.x) / 2;
        const d = `M${a.x} ${a.y} H${mid} V${b.y} H${b.x}`;
        const ground = [e.from.pin, e.to.pin].includes('GND'), power = [e.from.pin, e.to.pin].some(p => ['3V3', '5V', 'VCC', 'VIN', '+'].includes(p));
        return `<g data-wire="${esc(e.id)}"><path d="${d}" class="circuit-wire ${selectedEdge === e.id ? 'selected' : ''} ${ground ? 'ground' : power ? 'power' : ''}"></path><path d="${d}" class="wire-hit"></path></g>`;
      }).join('');
      const nodes = graph.components.map(n => `<g class="circuit-node ${selected === n.id ? 'selected' : ''} ${n.model.startsWith('board:') ? 'board' : ''}" data-component="${esc(n.id)}"><rect x="${n.position.x}" y="${n.position.y}" width="210" height="${nodeHeight(n)}" rx="8"/><rect class="node-header" x="${n.position.x}" y="${n.position.y}" width="210" height="40" rx="8"/><text class="node-title" x="${n.position.x + 12}" y="${n.position.y + 17}">${esc(n.id)}</text><text class="node-model" x="${n.position.x + 12}" y="${n.position.y + 32}">${esc(n.model)}</text>${cat[n.model].pins.map((p, i) => { const xy = pinCoords(n, p.id), right = i % 2; return `<g class="terminal ${pending?.component === n.id && pending?.pin === p.id ? 'pending' : ''}" data-pin="${esc(p.id)}" data-owner="${esc(n.id)}"><circle cx="${xy.x}" cy="${xy.y}" r="7" class="terminal-hit"/><circle cx="${xy.x}" cy="${xy.y}" r="4" class="terminal-dot ${p.type === 'ground' ? 'ground' : p.type.startsWith('power') ? 'power' : ''}"/><text x="${xy.x + (right ? -11 : 11)}" y="${xy.y + 4}" text-anchor="${right ? 'end' : 'start'}">${esc(p.id)}</text></g>`; }).join('')}</g>`).join('');
      stage.innerHTML = `<svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg"><defs><pattern id="studio-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="var(--grid-dot)"/></pattern></defs><rect width="100%" height="100%" fill="url(#studio-grid)"/><g transform="translate(${pan.x},${pan.y}) scale(${zoom})">${edges}${nodes}</g></svg>`;
      $('#canvas-stats').textContent = `${graph.components.length} components / ${graph.connections.length} connections`;
      $('#studio-zoom').textContent = Math.round(zoom * 100) + '%'; $('#studio-undo').disabled = !past.length || !canEdit; $('#studio-redo').disabled = !future.length || !canEdit;
      $('#cancel-connect').hidden = !pending;
      $('#canvas-help-text').textContent = pending ? `Connecting ${pending.component}.${pending.pin} → click the destination terminal` : 'Drag components · click two terminal dots to connect · wheel zoom · Shift-drag / middle-drag to pan';
    }
    function inspector() {
      const area = $('#circuit-properties');
      if (selectedEdge) {
        const e = graph.connections.find(e => e.id === selectedEdge); if (!e) { selectedEdge = ''; return inspector(); }
        const options = (ep) => endpoints().map(o => `<option value="${esc(o.value)}" ${o.value === ep.component + '::' + ep.pin ? 'selected' : ''}>${esc(o.label)}</option>`).join('');
        area.innerHTML = `<h4>Connection ${esc(e.id)}</h4><label class="field"><span>From exact terminal</span><select id="edge-from">${options(e.from)}</select></label><label class="field"><span>To exact terminal</span><select id="edge-to">${options(e.to)}</select></label><div class="row"><button class="btn primary sm" id="edge-apply" ${!canEdit ? 'disabled' : ''}>Update wire</button><button class="btn danger sm" id="edge-delete" ${!canEdit ? 'disabled' : ''}>Delete</button></div>`;
        $('#edge-apply').onclick = () => { const a = $('#edge-from').value.split('::'), b = $('#edge-to').value.split('::'); if (a.join() === b.join()) return toast('Choose two different terminals.', 'err'); before(); e.from = { component: a[0], pin: a[1] }; e.to = { component: b[0], pin: b[1] }; changed(); };
        $('#edge-delete').onclick = () => { before(); graph.connections = graph.connections.filter(w => w.id !== e.id); selectedEdge = ''; changed(); }; return;
      }
      const n = graph.components.find(n => n.id === selected);
      if (!n) { area.innerHTML = '<div class="inspector-empty"><div class="visual-glyph">⌘</div><p>Select a component to inspect pins, electrical assumptions and the documentation source.</p><p class="tiny">A circuit rule pass does not mean safe, simulated or physically tested.</p></div>'; return; }
      const d = cat[n.model];
      area.innerHTML = `<h4>${esc(d.name)}</h4><p class="mono tiny muted">${esc(n.id)} · ${esc(n.model)}</p><label class="field"><span>Instance label</span><input id="component-label" value="${esc(n.label || n.id)}" ${!canEdit ? 'disabled' : ''}></label><div class="property-grid"><div><small>Supply assumption</small><b>${d.supply_v == null ? 'Not specified' : esc(d.supply_v) + ' V'}</b></div><div><small>Current assumption</small><b>${d.current_ma == null ? 'Unverified' : esc(d.current_ma) + ' mA'}</b></div></div><p class="tiny muted mt">${esc(d.notes || '')}</p><a href="${esc(d.reference)}" target="_blank" rel="noopener noreferrer" class="tiny">Datasheet / documentation ↗</a><h4 class="mt">Exact terminals</h4>${d.pins.map(p => `<div class="pin-property"><code>${esc(p.id)}</code><small>${esc(p.type)}${p.voltage == null ? '' : ' · ' + esc(p.voltage) + ' V'}${p.required ? '' : ' · optional'}</small></div>`).join('')}<p class="tiny muted mt">${esc(d.verification || 'Review the actual module revision.')}</p><button class="btn sm danger mt" id="component-delete" ${!canEdit || n.model.startsWith('board:') ? 'disabled' : ''}>Remove component & connected wires</button>`;
      $('#component-label').onchange = e => { before(); n.label = e.target.value.slice(0, 80); changed(); };
      $('#component-delete').onclick = () => { before(); graph.components = graph.components.filter(x => x.id !== n.id); graph.connections = graph.connections.filter(e => e.from.component !== n.id && e.to.component !== n.id); selected = ''; changed(); };
    }
    function bottom() {
      const wires = graph.connections.map(e => ({ id: e.id, from: e.from.component + '.' + e.from.pin, to: e.to.component + '.' + e.to.pin }));
      $('#studio-wiring').innerHTML = table(wires, [['id', 'Wire'], ['from', 'From'], ['to', 'To'], ['id', 'Inspect', v => `<button class="btn ghost sm inspect-wire" data-wire="${esc(v)}">Select</button>`]]);
      $$('.inspect-wire').forEach(b => b.onclick = () => { selectedEdge = b.dataset.wire; selected = ''; inspector(); draw(); });
      $('#validation-status').innerHTML = stale ? badge('Not checked after edit', 'amber') : badge(validation.passed ? 'Rules: no errors' : 'Errors found', validation.passed ? 'green' : 'rose');
      $('#studio-findings').innerHTML = `${stale ? '<p class="tiny amber">These findings refer to the last checked graph. Click Validate graph to evaluate current edits.</p>' : ''}<div class="findings-list">${validation.issues.map(i => `<details class="finding ${i.severity}" ${i.severity === 'error' ? 'open' : ''}><summary><span class="finding-dot"></span>${esc(i.code)} · ${esc(i.message)}</summary><p class="tiny">Evidence: ${esc(i.evidence)}</p><p>${esc(i.fix)}</p></details>`).join('')}</div><p class="tiny muted mt-s">${validation.status} · simulation: ${validation.simulation}</p>`;
    }
    function library() {
      const search = $('#component-search').value.toLowerCase();
      $('#component-list').innerHTML = Object.entries(cat).filter(([k, d]) => !k.startsWith('board:') && (k + d.name).toLowerCase().includes(search)).map(([k, d]) => `<button class="component-tile" data-model="${esc(k)}" ${!canEdit ? 'disabled' : ''} draggable="${canEdit ? 'true' : 'false'}"><span class="component-symbol">${d.interface === 'analog' ? '◒' : d.interface === 'i2c' ? '▥' : d.interface === 'spi' ? '▤' : d.interface === 'uart' ? '⇄' : d.interface === 'motor' ? '⚙' : d.interface === 'power' ? '⚡' : '▫'}</span><div><b>${esc(d.name)}</b><small>${esc(d.interface || 'discrete')} · ${d.pins.length} terminals</small></div><span class="add-component">＋</span></button>`).join('');
      $$('.component-tile').forEach(b => {
        b.onclick = () => {
          const model = b.dataset.model; let i = 1, cid = model.replace(/[^A-Za-z0-9_-]/g, '_'); if (!/^[A-Za-z]/.test(cid)) cid = 'part_' + cid;
          let unique = cid; while (graph.components.some(n => n.id === unique)) unique = cid + '_' + (++i);
          before(); graph.components.push({ id: unique, model, label: cat[model].name, position: { x: Math.round((stage.clientWidth / 2 - pan.x) / zoom), y: Math.round((stage.clientHeight / 2 - pan.y) / zoom) } }); selected = unique; selectedEdge = ''; changed();
          toast('Added unwired component. Connect its required terminals, validate, then review firmware driver changes.');
        };
        b.ondragstart = e => {
          if (!canEdit) { e.preventDefault(); return; }
          e.dataTransfer.setData('text/plain', b.dataset.model);
          e.dataTransfer.effectAllowed = 'copy';
        };
      });
    }
    function fit() {
      const xs = graph.components.map(n => n.position.x), ys = graph.components.map(n => n.position.y), minx = Math.min(...xs) - 40, miny = Math.min(...ys) - 40;
      const width = Math.max(...xs) + 260 - minx, height = Math.max(...graph.components.map(n => n.position.y + nodeHeight(n))) + 40 - miny;
      zoom = Math.max(0.16, Math.min(1.1, stage.clientWidth / width, stage.clientHeight / height)); pan = { x: (stage.clientWidth - width * zoom) / 2 - minx * zoom, y: (stage.clientHeight - height * zoom) / 2 - miny * zoom }; draw();
    }
    stage.onpointerdown = e => {
      if (e.target.closest('[data-pin]')) return;
      const n = e.target.closest('[data-component]'), wire = e.target.closest('[data-wire]');
      if (e.button === 1 || e.shiftKey || (!n && !wire)) { dragging = { type: 'pan', x: e.clientX, y: e.clientY, start: { ...pan } }; stage.setPointerCapture(e.pointerId); e.preventDefault(); return; }
      if (n) { selected = n.dataset.component; selectedEdge = ''; inspector(); if (canEdit) { const node = graph.components.find(n => n.id === selected); dragging = { type: 'node', node, x: e.clientX, y: e.clientY, start: { ...node.position }, before: clone(graph), moved: false }; stage.setPointerCapture(e.pointerId); } draw(); }
      else if (wire) { selectedEdge = wire.dataset.wire; selected = ''; inspector(); draw(); }
    };
    stage.onpointermove = e => { if (!dragging) return; const dx = e.clientX - dragging.x, dy = e.clientY - dragging.y;
      if (dragging.type === 'pan') pan = { x: dragging.start.x + dx, y: dragging.start.y + dy };
      else { dragging.moved = Math.abs(dx) + Math.abs(dy) > 2; dragging.node.position = { x: Math.max(-4000, Math.min(4000, Math.round(dragging.start.x + dx / zoom))), y: Math.max(-4000, Math.min(4000, Math.round(dragging.start.y + dy / zoom))) }; }
      draw();
    };
    stage.onpointerup = e => { if (dragging?.type === 'node' && dragging.moved) { past.push(dragging.before); future = []; dirty = true; $('#studio-save-state').textContent = '● Unsaved layout · r' + project.revision; } dragging = null; try { stage.releasePointerCapture(e.pointerId); } catch (e) {} draw(); };
    stage.onclick = e => {
      const terminal = e.target.closest('[data-pin]'); if (!terminal || !canEdit) return;
      const ep = { component: terminal.dataset.owner, pin: terminal.dataset.pin };
      if (!pending) { pending = ep; selected = ep.component; selectedEdge = ''; inspector(); draw(); return; }
      if (pending.component === ep.component && pending.pin === ep.pin) { pending = null; draw(); return; }
      const same = (a, b) => a.component === b.component && a.pin === b.pin;
      if (graph.connections.some(w => (same(w.from, pending) && same(w.to, ep)) || (same(w.to, pending) && same(w.from, ep)))) { pending = null; draw(); return toast('These exact terminals are already connected.'); }
      before(); graph.connections.push({ id: 'wire_' + cryptoID(), from: pending, to: ep }); pending = null; changed();
    };
    stage.onwheel = e => { e.preventDefault(); const rect = stage.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top; const next = Math.max(0.15, Math.min(2, zoom * (e.deltaY < 0 ? 1.12 : 0.89))); pan.x = x - (x - pan.x) * next / zoom; pan.y = y - (y - pan.y) * next / zoom; zoom = next; draw(); };
    // Drag-and-drop: drag a component tile from the library and drop onto the canvas
    stage.ondragover = e => { if (!canEdit) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; };
    stage.ondragenter = e => { if (!canEdit) return; e.preventDefault(); stage.classList.add('drag-over'); };
    stage.ondragleave = e => { stage.classList.remove('drag-over'); };
    stage.ondrop = e => {
      e.preventDefault(); stage.classList.remove('drag-over');
      if (!canEdit) return;
      const model = e.dataTransfer.getData('text/plain');
      if (!model || !cat[model]) return;
      const rect = stage.getBoundingClientRect();
      const x = Math.round((e.clientX - rect.left - pan.x) / zoom);
      const y = Math.round((e.clientY - rect.top - pan.y) / zoom);
      let cid = model.replace(/[^A-Za-z0-9_-]/g, '_'); if (!/^[A-Za-z]/.test(cid)) cid = 'part_' + cid;
      let unique = cid, i = 1; while (graph.components.some(n => n.id === unique)) unique = cid + '_' + (++i);
      before();
      graph.components.push({ id: unique, model, label: cat[model].name, position: { x, y } });
      selected = unique; selectedEdge = ''; changed();
      toast('Dropped ' + cat[model].name + '. Connect its terminals to complete the circuit.');
    };
    $('#cancel-connect').onclick = () => { pending = null; draw(); }; stage.onkeydown = e => { if (e.key === 'Escape') { pending = null; draw(); } };
    $('#studio-undo').onclick = () => { if (past.length) { future.push(clone(graph)); graph = past.pop(); changed(); } };
    $('#studio-redo').onclick = () => { if (future.length) { past.push(clone(graph)); graph = future.pop(); changed(); } };
    $('#studio-zoomout').onclick = () => { zoom = Math.max(0.15, zoom / 1.2); draw(); }; $('#studio-zoomin').onclick = () => { zoom = Math.min(2, zoom * 1.2); draw(); }; $('#studio-fit').onclick = fit;
    $('#component-search').oninput = library; $('#studio-new').onclick = () => { if (!dirty || confirm('Leave unsaved circuit edits?')) shared.newProject(); };
    $('#studio-project').onchange = e => { if (e.target.value && (!dirty || confirm('Switch projects and discard unsaved edits?'))) go('#/studio/' + e.target.value); else e.target.value = id; };
    $('#studio-save').onclick = async e => {
      if (!canEdit) return; e.target.disabled = true;
      try { project = await api('/api/designs/' + id, { method: 'PATCH', body: { revision: project.revision, patch: { circuit: graph }, summary: 'Circuit graph / layout edits' } }); graph = clone(project.spec.circuit); validation = project.validation; dirty = stale = false;
        $('#studio-save-state').textContent = 'Saved revision ' + project.revision; $('#studio-save-state').className = 'tiny muted'; $('#studio-sync').innerHTML = `<div class="notice ${project.sync.requires_regeneration ? 'warn' : ''}">${esc(project.sync.reason || 'Saved graph; electrical configuration unchanged.')}</div>`; bottom(); draw(); toast('Circuit saved to this project', 'ok');
      } catch (e) { toast(e, 'err'); } $('#studio-save').disabled = false;
    };
    $('#studio-validate').onclick = async e => { e.target.disabled = true; try { validation = await api('/api/circuits/validate', { method: 'POST', body: { circuit: graph } }); stale = false; bottom(); toast(validation.passed ? 'Rule checks have no errors. Physical verification still required.' : 'Circuit errors found; inspect the findings.', validation.passed ? 'ok' : 'err'); } catch (e) { toast(e, 'err'); } e.target.disabled = false; };
    $('#studio-guide').onclick = async e => {
      if (dirty) return toast('Save the circuit first so the guide matches the saved project, or validate your current graph before saving.', 'err');
      e.target.disabled = true;
      try {
        const guide = await api('/api/circuits/guidance', { method: 'POST', body: { circuit: graph } });
        const area = $('#studio-build-guide'); area.hidden = false;
        const list = items => items.length ? `<ul>${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p class="tiny muted">None detected by the current rule checks.</p>';
        area.innerHTML = `<div class="row between"><div><h3>Step-by-step physical build guide</h3><p class="tiny muted">Graph fingerprint ${esc(guide.graph_fingerprint)} · ${guide.component_count} components · ${guide.connection_count} connections</p></div><span class="badge ${guide.ready_for_power ? 'green' : 'rose'}">${guide.ready_for_power ? 'No rule blockers found' : 'Resolve blockers first'}</span></div><p class="notice warn">This guide describes the current saved graph. It is not a simulation or a physical safety certification. Assemble with power disconnected.</p><h4>Assembly sequence</h4><ol>${guide.steps.map(x => `<li><b>${esc(x.title)}</b><p>${esc(x.instruction)}</p></li>`).join('')}</ol><h4>Required terminals still unconnected (${guide.unconnected_required_terminals.length})</h4>${list(guide.unconnected_required_terminals.map(x => `${x.component} (${x.model}) · ${x.pin} — ${x.role}`))}<h4>Blocking errors (${guide.blocking_errors.length})</h4>${list(guide.blocking_errors.map(x => `${x.code}: ${x.message} Fix: ${x.fix}`))}<h4>Warnings and confirmations (${guide.warnings.length})</h4>${list(guide.warnings.map(x => `${x.code}: ${x.message} Next: ${x.fix}`))}<h4>Bill of materials (${guide.bill_of_materials.length} distinct item types)</h4><div class="table-wrap"><table><thead><tr><th>Component</th><th>Quantity</th><th>Assumed current each</th><th>Documentation</th></tr></thead><tbody>${guide.bill_of_materials.map(x => `<tr><td><b>${esc(x.name)}</b><small class="muted">${esc(x.model)}</small></td><td>${x.quantity}</td><td>${x.estimated_current_ma_each == null ? 'Unverified' : esc(x.estimated_current_ma_each) + ' mA'}</td><td><a target="_blank" rel="noopener noreferrer" href="${esc(x.reference)}">Reference ↗</a></td></tr>`).join('')}</tbody></table></div><h4>Component notes</h4>${guide.component_notes.map(x => `<details><summary>${esc(x.component)} · ${esc(x.name)}</summary><p>${esc(x.notes || 'No additional catalog note.')}</p><a target="_blank" rel="noopener noreferrer" href="${esc(x.reference)}">Manufacturer / reference documentation ↗</a></details>`).join('')}<p class="tiny muted">${esc(guide.status)}. Verify the actual module, current, polarity, protection and datasheet before powering.</p>`;
        area.scrollIntoView({behavior:'smooth', block:'start'});
      } catch (err) { toast(err, 'err'); }
      e.target.disabled = false;
    };
    const twin3D = createDigitalTwin3D(h);
    $('#studio-3d-twin').onclick = () => { twin3D.open3DModal(graph, project.name || 'Circuit Design'); };
    $('#studio-export').onclick = () => { if (dirty) toast('Export uses the saved revision. Save first to include current edits.'); shared.exportDesign(id, $('#studio-export-kind').value); };
    $('#studio-import').onclick = () => { if (!canEdit) return toast('Advanced editing requires Pro.', 'err'); $('#studio-import-file').click(); };
    $('#studio-import-file').onchange = async e => { const file = e.target.files[0]; if (!file) return; if (file.size > 1500000) return toast('JSON import limit: 1.5 MB', 'err'); try { const data = JSON.parse(await file.text()), g = data.schema === 'nexus.project/1' ? data.circuit : data; const v = await api('/api/circuits/validate', { method: 'POST', body: { circuit: g } }); if (!confirm('Replace the editor graph with this validated-format import? It will not be saved until you press Save.')) return; before(); graph = clone(g); validation = v; selected = selectedEdge = ''; pending = null; changed(); stale = false; bottom(); fit(); } catch (e) { toast(e, 'err'); } };
    library(); inspector(); bottom(); fit();
    let lastWidth=stage.clientWidth;
    const resize = new ResizeObserver(() => {
      if(!stage.isConnected){ resize.disconnect(); return; }
      if(Math.abs(stage.clientWidth-lastWidth)>30){lastWidth=stage.clientWidth;fit();}
    });
    resize.observe(stage);
  }
  function cryptoID() { try { return crypto.randomUUID().slice(0, 8); } catch (e) { return Math.random().toString(36).slice(2, 10); } }
  return { view };
}
