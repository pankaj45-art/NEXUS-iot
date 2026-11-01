from pathlib import Path

fpath = Path(__file__).parent.parent / "web" / "studio.js"
text = fpath.read_text(encoding="utf-8")

# 1. Add import at the top
imp_old = "/* Exact-pin SVG editor. Graph is the only editable source of electrical truth. */\nexport function createCircuitStudio(h) {"
imp_new = "/* Exact-pin SVG editor. Graph is the only editable source of electrical truth. */\nimport { createDigitalTwin3D } from './digital-twin-3d.js';\nexport function createCircuitStudio(h) {"

# 2. Add 3D Twin button to toolbar
tb_old = '<button class="btn sm" id="studio-guide">Build guide</button></div></div>'
tb_new = '<button class="btn sm" id="studio-guide">Build guide</button><button class="btn sm" id="studio-3d-twin" style="color:#38bdf8;font-weight:700;">🎲 3D Digital Twin</button></div></div>'

# 3. Add click handler
hnd_old = "$('#studio-export').onclick = () => { if (dirty) toast('Export uses the saved revision. Save first to include current edits.'); shared.exportDesign(id, $('#studio-export-kind').value); };"
hnd_new = """const twin3D = createDigitalTwin3D(h);
    $('#studio-3d-twin').onclick = () => { twin3D.open3DModal(graph, project.name || 'Circuit Design'); };
    $('#studio-export').onclick = () => { if (dirty) toast('Export uses the saved revision. Save first to include current edits.'); shared.exportDesign(id, $('#studio-export-kind').value); };"""

if imp_old in text and tb_old in text and hnd_old in text:
    text = text.replace(imp_old, imp_new, 1)
    text = text.replace(tb_old, tb_new, 1)
    text = text.replace(hnd_old, hnd_new, 1)
    fpath.write_text(text, encoding="utf-8")
    print("SUCCESS: studio.js updated with 3D Digital Twin button & modal")
else:
    print("FAILED TO MATCH TARGETS IN studio.js")
