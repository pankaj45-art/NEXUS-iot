"""Conservative action routing: ordinary questions remain conversational.

Explicit UI tools always win. Automatic routing only recognizes an unambiguous
request to generate an image or perform a supported saved-project operation.
It never manufactures a successful tool result or forces every engineering
question into a workflow.
"""
import json
import re
from .. import entitlements
from ..errors import ApiError
from .circuit_svg import is_circuit_image_request, infer_style

ACTIONS = {'auto', 'chat', 'invention', 'validate', 'report', 'code', 'circuit_visual'}


def choose_action(text, requested='auto'):
    if requested not in ACTIONS:
        raise ApiError(400, 'Unsupported assistant action.', 'invalid_input')
    if requested != 'auto':
        return requested
    if re.match(r'\s*(validate|check) (my|the|this) (saved )?circuit\b', text, re.I):
        return 'validate'
    if re.match(r'\s*(create|generate|design) (a )?new (iot )?(invention|prototype project)\b', text, re.I):
        return 'invention'
    # Circuit image/visual generation — natural language detection
    if is_circuit_image_request(text):
        return 'circuit_visual'
    return 'chat'


def execute(conn, ent, action, text, project_id, cid, mid, opts):
    from . import invention, designs, circuits
    if action == 'invention':
        r = invention.plan(conn, ent, text, project_id=project_id, do_research=bool(opts.get('research')))
        return {'text': json.dumps(r['proposal'], indent=2), 'project_id': r['project_id'], 'tool_result': 'invention', 'proposal': r}

    if action == 'circuit_visual':
        return _execute_circuit_visual(conn, ent, text, project_id, opts)

    if action in ('validate', 'report', 'code'):
        if not project_id:
            raise ApiError(400, 'Select a saved project for this action, or use ordinary chat.', 'project_required')
        p = designs.owned(conn, ent, project_id)
        spec = json.loads(p['spec_json'])
        if action == 'validate':
            entitlements.require_feature(ent, 'tools.circuit_designer')
            r = circuits.validate(spec['circuit'], conn)
            return {'text': json.dumps(r, indent=2), 'project_id': project_id, 'tool_result': 'rule_validation'}
        if action == 'report':
            entitlements.require_feature(ent, 'exports')
            return {'text': designs.report(p, conn), 'project_id': project_id, 'tool_result': 'saved_state_report'}
        r = designs.code_preview(conn, ent, project_id)
        return {'text': 'Proposed driver rebuild (not applied). Review in Code Engineer.\n```diff\n' + r['diff'] + '\n```', 'project_id': project_id, 'tool_result': 'code_preview'}
    raise ApiError(400, 'Action not supported.', 'invalid_input')


def _execute_circuit_visual(conn, ent, text, project_id, opts):
    """Generate a circuit diagram SVG and return it embedded in the chat response."""
    from . import designs
    from .circuit_svg import render_circuit_visual, infer_style
    from .. import seed

    style = opts.get('style') or infer_style(text)

    # Try project context first
    spec = None
    project_slug = None
    if project_id:
        try:
            p = designs.owned(conn, ent, project_id)
            spec = json.loads(p['spec_json'])
            project_slug = p['id']
        except Exception:
            pass

    if spec is None:
        # Try library projects — search for one matching the query
        from .. import hardware as hw
        words = [w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) > 3]
        all_projects = conn.execute(
            "SELECT slug, content_json FROM projects WHERE status='published' ORDER BY is_free DESC, id ASC LIMIT 50"
        ).fetchall()
        best_row = None
        best_score = 0
        for row in all_projects:
            try:
                c = json.loads(row['content_json'])
                haystack = (c.get('title', '') + ' ' + ' '.join(
                    str(b.get('name', '')) for b in c.get('bom', {}).get('items', [])
                )).lower()
                score = sum(1 for w in words if w in haystack)
                if score > best_score:
                    best_score = score
                    best_row = row
                    spec = c
                    project_slug = row['slug']
            except Exception:
                continue

    # Build a minimal spec from scratch if still nothing
    if spec is None:
        spec = {
            'title': 'IoT Project',
            'bom': {'items': []},
            'circuit': {'board': 'ESP32', 'connections': []},
        }

    svg = render_circuit_visual(spec, style=style)

    # Build a human-readable explanation
    board = spec.get('circuit', {}).get('board', 'ESP32')
    conns = spec.get('circuit', {}).get('connections', [])
    bom_items = spec.get('bom', {}).get('items', [])
    title = spec.get('title', 'IoT Project')

    lines = [f"## 📐 Circuit Visual: {title}"]
    lines.append(f"\n**Microcontroller:** {board}")
    if bom_items:
        lines.append(f"**Components ({len(bom_items)}):** " + ', '.join(b.get('name', '?') for b in bom_items[:8]))
    lines.append(f"\n**Diagram style:** {style.replace('auto', 'auto-selected')}")
    lines.append("\n### 🔌 Key Connections\n")
    for conn in conns[:12]:
        if not isinstance(conn, dict):
            continue
        part = conn.get('part', conn.get('from', {}).get('component', ''))
        pin = conn.get('part_pin', conn.get('from', {}).get('pin', ''))
        to_raw = conn.get('to', {})
        to_pin = to_raw.get('pin', '') if isinstance(to_raw, dict) else str(to_raw or '')
        note = conn.get('note', '')
        lines.append(f"- **{part}** `{pin}` → **MCU** `{to_pin}`" + (f" _{note}_" if note else ""))
    lines.append("\n> ⚠️ Always verify pinouts against component datasheets before powering on.")
    if project_slug:
        lines.append(f"\n*Diagram generated from project data · [Open Circuit Studio](#/studio/{project_slug})*")

    return {
        'text': '\n'.join(lines),
        'tool_result': 'circuit_visual',
        'circuit_svg': svg,
        'style': style,
        'project_id': project_id,
        'project_slug': project_slug,
    }

