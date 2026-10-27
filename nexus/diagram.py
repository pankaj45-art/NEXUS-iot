"""Generate a project-specific SVG block diagram from the architecture model."""
from __future__ import annotations

import html

W, H = 1120, 470
COLORS = {
    "power": ("#f59e0b", "#fff7ed"), "sensor": ("#22d3ee", "#ecfeff"),
    "controller": ("#8b5cf6", "#f5f3ff"), "logic": ("#6366f1", "#eef2ff"),
    "output": ("#f43f5e", "#fff1f2"), "comms": ("#14b8a6", "#ecfdf5"),
    "cloud": ("#3b82f6", "#eff6ff"),
}
POS = {
    "power": (40, 40), "sensors": (40, 180), "mcu": (330, 180),
    "logic": (330, 40), "outputs": (330, 320), "comms": (620, 180), "cloud": (900, 180),
}
BOX_W, BOX_H = 240, 96


def render_svg(content: dict) -> str:
    diagram = content.get("architecture", {}).get("diagram", {})
    nodes = diagram.get("nodes", [])
    edges = diagram.get("edges", [])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="100%" role="img" '
        f'aria-label="System block diagram for {html.escape(content.get("title", "project"))}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
        '<path d="M0,0 L10,4 L0,8 z" fill="#64748b"/></marker>'
        '<style><![CDATA['
        '.box{rx:12;ry:12;stroke-width:2;} .t{font-family:Inter,Segoe UI,Arial,sans-serif;font-size:15px;'
        'fill:#0f172a;font-weight:600;} .lbl{font-family:Inter,Segoe UI,Arial,sans-serif;font-size:11px;fill:#475569;}'
        '.edge{stroke:#64748b;stroke-width:2;fill:none;marker-end:url(#arrow);}'
        '.title{font-family:Inter,Segoe UI,Arial,sans-serif;font-size:17px;fill:#e2e8f0;font-weight:700;}'
        ']]></style></defs>',
        f'<rect width="{W}" height="{H}" fill="#0b1220"/>',
        f'<text class="title" x="28" y="26">NEXUS IoT · {html.escape(content.get("title", "Project"))} — system architecture</text>',
    ]
    centers = {}
    for n in nodes:
        nid = n.get("id")
        x, y = POS.get(nid, (40, 40))
        stroke, fill = COLORS.get(n.get("type"), ("#94a3b8", "#f8fafc"))
        centers[nid] = (x, y)
        parts.append(f'<rect class="box" x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" fill="{fill}" stroke="{stroke}"/>')
        lines = str(n.get("label", "")).split("\n")
        for i, line in enumerate(lines[:4]):
            ty = y + 28 + i * 19
            parts.append(f'<text class="t" x="{x+14}" y="{ty}">{html.escape(line[:34])}</text>')
    for e in edges:
        a, b = centers.get(e.get("from")), centers.get(e.get("to"))
        if not a or not b:
            continue
        ax, ay = a[0] + BOX_W / 2, a[1] + BOX_H / 2
        bx, by = b[0] + BOX_W / 2, b[1] + BOX_H / 2
        dx, dy = bx - ax, by - ay
        if abs(dx) > abs(dy):
            sx, sy = ax + (BOX_W / 2 if dx > 0 else -BOX_W / 2), ay
            ex, ey = bx - (BOX_W / 2 if dx > 0 else -BOX_W / 2), by
        else:
            sx, sy = ax, ay + (BOX_H / 2 if dy > 0 else -BOX_H / 2)
            ex, ey = bx, by - (BOX_H / 2 if dy > 0 else -BOX_H / 2)
        parts.append(f'<path class="edge" d="M{sx:.0f},{sy:.0f} L{ex:.0f},{ey:.0f}"/>')
        label = str(e.get("label", ""))[:26]
        if label:
            mx, my = (sx + ex) / 2, (sy + ey) / 2 - 7
            parts.append(f'<text class="lbl" x="{mx:.0f}" y="{my:.0f}" text-anchor="middle" '
                         f'style="paint-order:stroke;stroke:#0b1220;stroke-width:5px">{html.escape(label)}</text>')
    parts.append(f'<text class="lbl" x="28" y="{H-16}" style="fill:#94a3b8">'
                 'Generated from this project\'s BOM, pin map and transport. Verify all pinouts against the linked datasheets.</text>')
    parts.append("</svg>")
    return "".join(parts)
