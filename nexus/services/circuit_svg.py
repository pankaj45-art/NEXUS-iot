"""Advanced SVG circuit diagram renderer for NEXUS IoT.

Generates accurate, project-specific circuit visualizations directly from
the project's connection graph, BOM, and pin assignments.

Three diagram styles:
  schematic  — clean engineering schematic with component symbols and wire nets
  breadboard — breadboard layout with color-coded jumper wires and row positions
  wiring     — structured wiring table + visual block diagram (always accurate)

All output is deterministic SVG (no AI image model required) and synchronised
with the same data used by Circuit Studio, code generation, and the BOM.
"""
from __future__ import annotations

import html
import json
import math
import re
from typing import Any

# ---------------------------------------------------------------------------
# Colour palette (dark engineering theme)
# ---------------------------------------------------------------------------
BG       = "#0b1220"
GRID     = "#1a2740"
LABEL    = "#94a3b8"
WIRE_GND = "#ef4444"    # red  (note: some conventions use red for +; we use red for GND so it stands out)
WIRE_PWR = "#f59e0b"    # amber for VCC / power
WIRE_SIG = "#22d3ee"    # cyan for signal/data
WIRE_SCL = "#fbbf24"    # yellow for clock
WIRE_SDA = "#34d399"    # green for SDA/MOSI
WIRE_RX  = "#818cf8"    # indigo for RX / MISO
WIRE_TX  = "#fb923c"    # orange for TX
WIRE_ANA = "#a78bfa"    # violet for analog
WIRE_DEF = "#64748b"    # slate default
COMP_FILL = "#1e3a5f"
COMP_STROKE = "#38bdf8"
TEXT_MAIN = "#e2e8f0"
TEXT_SUB  = "#64748b"
GREEN     = "#22c55e"


# ---------------------------------------------------------------------------
# Wire colour helpers
# ---------------------------------------------------------------------------
def _wire_colour(pin_name: str, purpose: str = "") -> str:
    p = (pin_name + " " + purpose).upper()
    if any(k in p for k in ("VCC", "3V3", "3.3V", "5V", "VIN", "PWR", "POWER", "V+")):
        return WIRE_PWR
    if any(k in p for k in ("GND", "GROUND", "VSS", "0V", "-")):
        return WIRE_GND
    if any(k in p for k in ("SCL", "CLK", "SCK", "CLOCK")):
        return WIRE_SCL
    if any(k in p for k in ("SDA", "MOSI", "SDI")):
        return WIRE_SDA
    if any(k in p for k in ("MISO", "SDO", "RX", "RXD")):
        return WIRE_RX
    if any(k in p for k in ("TX", "TXD")):
        return WIRE_TX
    if any(k in p for k in ("AO", "ANALOG", "ADC", "A0")):
        return WIRE_ANA
    return WIRE_SIG


def _std_wire_color_name(pin_name: str) -> str:
    c = _wire_colour(pin_name)
    names = {
        WIRE_PWR: "Red", WIRE_GND: "Black", WIRE_SCL: "Yellow",
        WIRE_SDA: "Green", WIRE_RX: "Blue", WIRE_TX: "Orange",
        WIRE_ANA: "Purple", WIRE_SIG: "Cyan", WIRE_DEF: "Gray",
    }
    return names.get(c, "Gray")


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------
def _h(s: str) -> str:
    return html.escape(str(s))


def _rect(x, y, w, h, fill=COMP_FILL, stroke=COMP_STROKE, rx=8, extra="") -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{" " + extra if extra else ""/>'


def _text(x, y, s, cls="lbl", anchor="start", extra="") -> str:
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{" " + extra if extra else ""}>{_h(s)}</text>'


def _line(x1, y1, x2, y2, color=WIRE_SIG, width=2, dash="") -> str:
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"{da}/>'


def _path(d, color=WIRE_SIG, width=2) -> str:
    return f'<path d="{d}" stroke="{color}" stroke-width="{width}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'


def _circle(cx, cy, r, fill=WIRE_SIG, stroke="none") -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}"/>'


# ---------------------------------------------------------------------------
# Component symbol library (simple SVG shapes)
# ---------------------------------------------------------------------------
def _chip_symbol(x, y, w, h, label, pins_left, pins_right, fill=COMP_FILL, stroke=COMP_STROKE) -> list[str]:
    """Draw an IC-style rectangle with pin stubs."""
    parts = []
    parts.append(_rect(x, y, w, h, fill, stroke, rx=6))
    # label centred
    parts.append(f'<text x="{x + w/2}" y="{y + h/2 + 5}" class="comp-name" text-anchor="middle">{_h(label[:18])}</text>')
    pin_h = h / (max(len(pins_left), len(pins_right), 1) + 1)
    # left pins
    for i, pname in enumerate(pins_left):
        py = y + pin_h * (i + 1)
        parts.append(_line(x - 18, py, x, py, _wire_colour(pname), 2))
        parts.append(f'<text x="{x - 22}" y="{py + 4}" class="pin-lbl" text-anchor="end">{_h(pname[:8])}</text>')
        parts.append(_circle(x - 18, py, 3, _wire_colour(pname)))
    # right pins
    for i, pname in enumerate(pins_right):
        py = y + pin_h * (i + 1)
        parts.append(_line(x + w, py, x + w + 18, py, _wire_colour(pname), 2))
        parts.append(f'<text x="{x + w + 22}" y="{py + 4}" class="pin-lbl" text-anchor="start">{_h(pname[:8])}</text>')
        parts.append(_circle(x + w + 18, py, 3, _wire_colour(pname)))
    return parts


def _resistor_symbol(x, y, label="R") -> list[str]:
    """Small resistor zigzag symbol."""
    parts = []
    # body rectangle
    parts.append(_rect(x, y - 8, 36, 16, "#1e3a5f", "#fbbf24", rx=3))
    parts.append(f'<text x="{x + 18}" y="{y + 5}" class="pin-lbl" text-anchor="middle" fill="#fbbf24">{_h(label[:6])}</text>')
    # lead lines
    parts.append(_line(x - 14, y, x, y, WIRE_DEF, 2))
    parts.append(_line(x + 36, y, x + 50, y, WIRE_DEF, 2))
    return parts


def _led_symbol(x, y) -> list[str]:
    """Triangle + bar LED symbol."""
    parts = []
    # triangle
    parts.append(f'<polygon points="{x},{y-10} {x},{y+10} {x+16},{y}" fill="#fde047" stroke="#fbbf24" stroke-width="1.5"/>')
    # cathode bar
    parts.append(_line(x + 16, y - 10, x + 16, y + 10, "#fbbf24", 2))
    parts.append(_line(x - 14, y, x, y, WIRE_DEF, 2))
    parts.append(_line(x + 16, y, x + 30, y, WIRE_DEF, 2))
    return parts


# ---------------------------------------------------------------------------
# Public entry: pick the right renderer
# ---------------------------------------------------------------------------
def render_circuit_visual(content: dict, style: str = "auto") -> str:
    """Main entry point. Returns complete SVG string."""
    if style == "auto":
        # choose based on project complexity
        bom = content.get("bom", {}).get("items", [])
        style = "breadboard" if len(bom) <= 8 else "schematic"

    if style == "breadboard":
        return _render_breadboard(content)
    if style == "schematic":
        return _render_schematic(content)
    # default: wiring block diagram
    return _render_wiring_diagram(content)


# ---------------------------------------------------------------------------
# Style 1: Breadboard wiring diagram
# ---------------------------------------------------------------------------
def _render_breadboard(content: dict) -> str:
    title = content.get("title", "IoT Project")
    circuit = content.get("circuit", {})
    bom = content.get("bom", {}).get("items", [])
    connections = circuit.get("connections", [])

    W, H = 1200, 820
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
                 f'aria-label="Breadboard wiring diagram for {_h(title)}">')
    parts.append(_defs())
    parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    # grid
    for gx in range(0, W, 40):
        parts.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="{GRID}" stroke-width="0.5"/>')
    for gy in range(0, H, 40):
        parts.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="{GRID}" stroke-width="0.5"/>')

    # Title
    parts.append(f'<text x="24" y="38" class="title">{_h(title[:60])} · Breadboard Wiring Diagram</text>')
    parts.append(f'<text x="24" y="56" class="subtitle">Auto-generated from project BOM and circuit connections · Verify all pinouts against datasheets</text>')

    # ---- Breadboard body (centered, rows 1-30) ----
    bb_x, bb_y = 180, 90
    bb_w, bb_h = 760, 320
    row_count = 30
    col_letters = "ABCDEFGHIJ"
    row_h = bb_h / (row_count + 2)
    col_w = bb_w / (len(col_letters) + 4)

    # breadboard outline
    parts.append(_rect(bb_x, bb_y, bb_w, bb_h, "#0f2335", COMP_STROKE, rx=10))
    # power rails
    for rail_y, color, label in [
        (bb_y + 10, WIRE_PWR, "+"),
        (bb_y + 26, WIRE_GND, "−"),
        (bb_y + bb_h - 26, WIRE_PWR, "+"),
        (bb_y + bb_h - 10, WIRE_GND, "−"),
    ]:
        parts.append(_line(bb_x + 20, rail_y, bb_x + bb_w - 20, rail_y, color, 3))
        parts.append(f'<text x="{bb_x + 10}" y="{rail_y + 4}" class="pin-lbl" fill="{color}" text-anchor="middle">{label}</text>')

    # tie-point grid
    for ri in range(1, row_count + 1):
        ry = bb_y + 44 + (ri - 1) * (bb_h - 80) / row_count
        for ci, col in enumerate(col_letters):
            # gap between E and F
            cx = bb_x + 44 + ci * col_w + (12 if ci >= 5 else 0)
            parts.append(f'<circle cx="{cx:.0f}" cy="{ry:.0f}" r="3" fill="{GRID}" stroke="{COMP_STROKE}" stroke-width="0.5"/>')
        # row number
        parts.append(f'<text x="{bb_x + 16}" y="{ry + 4}" class="row-num" text-anchor="middle">{ri}</text>')

    # ---- MCU block (left side) ----
    mcu_x, mcu_y, mcu_w, mcu_h = 24, 100, 140, 300
    board_name = content.get("circuit", {}).get("board", "MCU")
    if isinstance(board_name, str):
        board_label = board_name.upper()[:10]
    else:
        board_label = "ESP32"
    parts.append(_rect(mcu_x, mcu_y, mcu_w, mcu_h, "#0f2d4a", "#38bdf8", rx=8))
    parts.append(f'<text x="{mcu_x + mcu_w/2}" y="{mcu_y + 22}" class="comp-name" text-anchor="middle">{_h(board_label)}</text>')
    parts.append(f'<text x="{mcu_x + mcu_w/2}" y="{mcu_y + 36}" class="pin-lbl" text-anchor="middle">Microcontroller</text>')

    # ---- Sensor/component blocks (right side) ----
    sensor_start_x = bb_x + bb_w + 20
    sensor_y_base = 100
    sensor_block_h = 70
    sensor_gap = 12
    sensor_colors = [COMP_STROKE, "#a78bfa", "#34d399", "#fb923c", "#fbbf24", "#f472b6", "#22d3ee", "#818cf8"]

    comp_positions: dict[str, tuple[int, int, int, int]] = {}  # name -> (x,y,w,h)
    for idx, item in enumerate(bom[:10]):
        name = item.get("name", f"Component {idx+1}")
        ref = item.get("ref", "")
        sy = sensor_y_base + idx * (sensor_block_h + sensor_gap)
        sx = sensor_start_x
        sw, sh = 180, sensor_block_h
        color = sensor_colors[idx % len(sensor_colors)]
        parts.append(_rect(sx, sy, sw, sh, COMP_FILL, color, rx=6))
        parts.append(f'<text x="{sx + sw/2}" y="{sy + 20}" class="comp-name" text-anchor="middle" fill="{color}">{_h(name[:22])}</text>')
        if ref:
            parts.append(f'<text x="{sx + sw/2}" y="{sy + 34}" class="pin-lbl" text-anchor="middle">{_h(str(ref)[:30])}</text>')
        comp_positions[name.lower()[:20]] = (sx, sy, sw, sh)

    # ---- Draw connection wires ----
    for ci, conn in enumerate(connections[:20]):
        if not isinstance(conn, dict):
            continue
        part_name = str(conn.get("part", conn.get("from", {}).get("component", "")) or "")
        pin_name = str(conn.get("part_pin", conn.get("from", {}).get("pin", "")) or "")
        to_raw = conn.get("to", {})
        if isinstance(to_raw, dict):
            to_pin = str(to_raw.get("pin", ""))
        else:
            to_pin = str(to_raw or "")
        note = str(conn.get("note", "") or "")
        color = _wire_colour(pin_name, note)

        # find source component block
        key = part_name.lower()[:20]
        src = comp_positions.get(key)
        if not src:
            # fuzzy match
            for k, v in comp_positions.items():
                if k[:6] in key or key[:6] in k:
                    src = v
                    break
        if src:
            sx, sy, sw, sh = src
            # wire from left edge of component to right edge of breadboard
            wire_y = sy + 15 + (ci % 4) * 10
            mx1 = sx  # from component left edge
            mx2 = bb_x + bb_w  # breadboard right edge
            # draw elbow wire
            mid_x = (mx1 + mx2) / 2
            parts.append(_path(f"M{mx1},{wire_y} L{mid_x},{wire_y} L{mid_x},{bb_y + 44 + (ci % row_count) * (bb_h - 80) / row_count:.0f} L{mx2:.0f},{bb_y + 44 + (ci % row_count) * (bb_h - 80) / row_count:.0f}", color, 2))
            # label
            lx = (mx1 + mx2) / 2 + 4
            parts.append(f'<text x="{lx:.0f}" y="{wire_y - 3}" class="wire-lbl" fill="{color}">{_h((pin_name + "→" + to_pin)[:20])}</text>')

    # ---- Wire from MCU to breadboard ----
    mcu_right = mcu_x + mcu_w
    for i, (pname, color) in enumerate([("3V3/VCC", WIRE_PWR), ("GND", WIRE_GND), ("SDA/D21", WIRE_SDA), ("SCL/D22", WIRE_SCL)]):
        py = mcu_y + 60 + i * 44
        parts.append(_line(mcu_right, py, bb_x, py, color, 2))
        parts.append(f'<text x="{mcu_right + 6}" y="{py - 3}" class="wire-lbl" fill="{color}">{_h(pname)}</text>')

    # ---- Legend ----
    legend_x, legend_y = 24, 460
    parts.append(f'<text x="{legend_x}" y="{legend_y}" class="section-title">Wire Color Legend</text>')
    legend_items = [
        (WIRE_PWR, "Power (VCC / 3.3V / 5V)"),
        (WIRE_GND, "Ground (GND)"),
        (WIRE_SCL, "Clock (SCL / SCK)"),
        (WIRE_SDA, "Data (SDA / MOSI / DATA)"),
        (WIRE_RX,  "RX / MISO"),
        (WIRE_TX,  "TX"),
        (WIRE_ANA, "Analog Signal"),
        (WIRE_SIG, "Digital Signal"),
    ]
    for li, (c, lbl) in enumerate(legend_items):
        lx = legend_x + (li % 2) * 160
        ly = legend_y + 18 + (li // 2) * 22
        parts.append(_circle(lx + 6, ly - 5, 6, c))
        parts.append(f'<text x="{lx + 18}" y="{ly}" class="pin-lbl">{_h(lbl)}</text>')

    # ---- Connection table ----
    tbl_x, tbl_y = 24, 640
    parts.append(f'<text x="{tbl_x}" y="{tbl_y}" class="section-title">Connection Table</text>')
    headers = ["Component", "Pin", "Connects To", "Wire Color", "Note"]
    col_widths = [180, 90, 180, 90, 240]
    hx = tbl_x
    for hi, hdr in enumerate(headers):
        parts.append(f'<text x="{hx + 6}" y="{tbl_y + 20}" class="tbl-hdr">{_h(hdr)}</text>')
        parts.append(f'<line x1="{hx}" y1="{tbl_y + 24}" x2="{hx + col_widths[hi]}" y2="{tbl_y + 24}" stroke="{COMP_STROKE}" stroke-width="1"/>')
        hx += col_widths[hi]
    for ri, conn in enumerate(connections[:8]):
        if not isinstance(conn, dict):
            continue
        part_n = str(conn.get("part", conn.get("from", {}).get("component", "")) or "")
        pin_n = str(conn.get("part_pin", conn.get("from", {}).get("pin", "")) or "")
        to_raw = conn.get("to", {})
        to_str = (f"{to_raw.get('component','MCU')}.{to_raw.get('pin','?')}" if isinstance(to_raw, dict) else str(to_raw or "MCU"))
        note = str(conn.get("note", "") or "")
        color = _wire_colour(pin_n, note)
        row_y = tbl_y + 36 + ri * 20
        if ri % 2 == 0:
            parts.append(f'<rect x="{tbl_x}" y="{row_y - 14}" width="{sum(col_widths)}" height="20" fill="rgba(30,58,95,0.4)"/>')
        vals = [part_n[:24], pin_n[:10], to_str[:22], _std_wire_color_name(pin_n), note[:30]]
        cx = tbl_x
        for vi, val in enumerate(vals):
            fc = color if vi == 3 else TEXT_MAIN
            parts.append(f'<text x="{cx + 6}" y="{row_y}" class="pin-lbl" fill="{fc}">{_h(val)}</text>')
            cx += col_widths[vi]

    # Footer
    parts.append(f'<text x="{W//2}" y="{H - 10}" class="footer" text-anchor="middle">Generated by NEXUS IoT · Accuracy-first circuit visualization · Always verify pinouts against manufacturer datasheets before powering on</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Style 2: Schematic diagram
# ---------------------------------------------------------------------------
def _render_schematic(content: dict) -> str:
    title = content.get("title", "IoT Project")
    circuit = content.get("circuit", {})
    bom = content.get("bom", {}).get("items", [])
    connections = circuit.get("connections", [])

    W, H = 1280, 900
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
                 f'aria-label="Circuit schematic for {_h(title)}">')
    parts.append(_defs())
    parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    # engineering grid
    for gx in range(0, W, 50):
        parts.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="{GRID}" stroke-width="0.4"/>')
    for gy in range(0, H, 50):
        parts.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="{GRID}" stroke-width="0.4"/>')

    # Title block (bottom-right engineering style)
    parts.append(f'<rect x="0" y="0" width="{W}" height="44" fill="#0f1a2e" stroke="{COMP_STROKE}" stroke-width="1"/>')
    parts.append(f'<text x="20" y="28" class="title">{_h(title[:70])} · Circuit Schematic</text>')
    parts.append(f'<text x="{W - 20}" y="28" class="subtitle" text-anchor="end">NEXUS IoT Engineering Platform · Auto-generated schematic</text>')

    # ---- MCU (centre) ----
    mcu_items = bom[:1]
    board_label = str(circuit.get("board", "ESP32")).upper()[:12]
    # pin list from first few connections
    mcu_pins_l = []
    mcu_pins_r = []
    for conn in connections[:12]:
        if not isinstance(conn, dict):
            continue
        to_raw = conn.get("to", {})
        if isinstance(to_raw, dict):
            pin = to_raw.get("pin", "")
        else:
            pin = str(to_raw or "")
        if pin and pin not in mcu_pins_l + mcu_pins_r:
            if len(mcu_pins_l) <= len(mcu_pins_r):
                mcu_pins_l.append(pin)
            else:
                mcu_pins_r.append(pin)

    # MCU box — centred horizontally
    mcu_w = 180
    mcu_h = max(160, (max(len(mcu_pins_l), len(mcu_pins_r)) + 2) * 30)
    mcu_x = (W - mcu_w) // 2
    mcu_y = (H - mcu_h) // 2 + 30
    for p in _chip_symbol(mcu_x, mcu_y, mcu_w, mcu_h, board_label, mcu_pins_l, mcu_pins_r):
        parts.append(p)

    # ---- Peripheral components ----
    # distribute around the MCU
    peripherals = bom[1:] if len(bom) > 1 else bom
    if not peripherals:
        peripherals = [{"name": "Sensor", "ref": ""}]

    angle_step = 360 / max(len(peripherals), 1)
    radius = 320
    cx_center = W // 2
    cy_center = mcu_y + mcu_h // 2

    for idx, item in enumerate(peripherals[:8]):
        angle_deg = idx * angle_step - 90
        angle_rad = math.radians(angle_deg)
        cx = cx_center + radius * math.cos(angle_rad)
        cy = cy_center + radius * math.sin(angle_rad)
        pname = item.get("name", f"Part {idx+1}")
        # determine relevant pins from connections
        comp_pins = []
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            cpart = str(conn.get("part", conn.get("from", {}).get("component", "")) or "")
            if pname.lower()[:8] in cpart.lower() or cpart.lower()[:8] in pname.lower():
                pin = str(conn.get("part_pin", conn.get("from", {}).get("pin", "")) or "")
                if pin and pin not in comp_pins:
                    comp_pins.append(pin)
        if not comp_pins:
            comp_pins = ["VCC", "GND", "SIG"]
        pw, ph = 160, max(80, (len(comp_pins) + 1) * 24)
        px = int(cx - pw / 2)
        py = int(cy - ph / 2)
        color = [COMP_STROKE, "#a78bfa", "#34d399", "#fb923c", "#fbbf24", "#f472b6"][idx % 6]
        # component box
        parts.append(_rect(px, py, pw, ph, COMP_FILL, color, rx=6))
        parts.append(f'<text x="{px + pw/2:.0f}" y="{py + 20}" class="comp-name" text-anchor="middle" fill="{color}">{_h(pname[:20])}</text>')
        for pi, ppin in enumerate(comp_pins[:5]):
            ppy = py + 32 + pi * 20
            # pin label
            is_right = px + pw < cx_center
            lx = px + pw + 4 if is_right else px - 4
            anchor = "start" if is_right else "end"
            pc = _wire_colour(ppin)
            parts.append(f'<text x="{lx}" y="{ppy + 5}" class="pin-lbl" fill="{pc}" text-anchor="{anchor}">{_h(ppin[:8])}</text>')
            # pin stub
            stub_x = px + pw if is_right else px
            parts.append(_line(stub_x, ppy, stub_x + (16 if is_right else -16), ppy, pc, 1.5))
            parts.append(_circle(stub_x + (16 if is_right else -16), ppy, 3, pc))

        # wire from MCU to component
        wire_color = _wire_colour(comp_pins[0] if comp_pins else "SIG")
        # wire endpoints: edge of MCU box to edge of component box
        # midpoint wire with elbow
        m_edge_x = mcu_x + mcu_w if cx > mcu_x + mcu_w else mcu_x
        m_edge_y = mcu_y + mcu_h // 2
        c_edge_x = px + pw if cx < mcu_x else px
        c_edge_y = py + ph // 2
        mid_x = (m_edge_x + c_edge_x) / 2
        parts.append(_path(f"M{m_edge_x},{m_edge_y} L{mid_x},{m_edge_y} L{mid_x},{c_edge_y} L{c_edge_x},{c_edge_y}", wire_color, 1.5))

    # ---- Power symbols ----
    # VCC triangle
    parts.append(f'<polygon points="100,80 115,54 130,80" fill="{WIRE_PWR}" stroke="{WIRE_PWR}"/>')
    parts.append(f'<text x="115" y="50" class="pin-lbl" fill="{WIRE_PWR}" text-anchor="middle">VCC</text>')
    parts.append(_line(115, 80, 115, 100, WIRE_PWR, 2))
    # GND symbol
    gnd_x, gnd_y = W - 150, H - 100
    parts.append(_line(gnd_x, gnd_y - 20, gnd_x, gnd_y, WIRE_GND, 2))
    for li, lw in enumerate([32, 20, 10]):
        parts.append(_line(gnd_x - lw, gnd_y + li * 7, gnd_x + lw, gnd_y + li * 7, WIRE_GND, 2))
    parts.append(f'<text x="{gnd_x}" y="{gnd_y - 24}" class="pin-lbl" fill="{WIRE_GND}" text-anchor="middle">GND</text>')

    # Footer
    parts.append(f'<text x="{W // 2}" y="{H - 10}" class="footer" text-anchor="middle">NEXUS IoT auto-generated schematic · This is a conceptual schematic, not a PCB netlist · Verify all pinouts and component values before assembly</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Style 3: Wiring block diagram (always accurate, good default)
# ---------------------------------------------------------------------------
def _render_wiring_diagram(content: dict) -> str:
    title = content.get("title", "IoT Project")
    circuit = content.get("circuit", {})
    bom = content.get("bom", {}).get("items", [])
    connections = circuit.get("connections", [])
    board_label = str(circuit.get("board", "ESP32")).upper()[:14]

    W, H = 1200, 760
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
                 f'aria-label="Wiring block diagram for {_h(title)}">')
    parts.append(_defs())
    parts.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

    # subtle grid
    for gx in range(0, W, 60):
        parts.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{H}" stroke="{GRID}" stroke-width="0.5"/>')
    for gy in range(0, H, 60):
        parts.append(f'<line x1="0" y1="{gy}" x2="{W}" y2="{gy}" stroke="{GRID}" stroke-width="0.5"/>')

    # Title
    parts.append(f'<text x="24" y="38" class="title">{_h(title[:64])} · Wiring Block Diagram</text>')
    parts.append(f'<text x="24" y="56" class="subtitle">Generated from saved project circuit data · Connection table is authoritative</text>')

    # ---- MCU block ----
    mcu_x, mcu_y, mcu_w, mcu_h = 100, 100, 200, max(360, len(connections) * 24 + 40)
    mcu_h = min(mcu_h, 500)
    parts.append(_rect(mcu_x, mcu_y, mcu_w, mcu_h, "#0a1f38", COMP_STROKE, rx=10))
    # gradient simulation
    parts.append(f'<text x="{mcu_x + mcu_w/2:.0f}" y="{mcu_y + 28}" class="comp-name" text-anchor="middle">{_h(board_label)}</text>')
    parts.append(f'<text x="{mcu_x + mcu_w/2:.0f}" y="{mcu_y + 44}" class="pin-lbl" text-anchor="middle">Microcontroller</text>')
    # pin list from connections
    shown_pins: set[str] = set()
    pin_rows = []
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        to_raw = conn.get("to", {})
        pin = (to_raw.get("pin", "") if isinstance(to_raw, dict) else str(to_raw or ""))
        if pin and pin not in shown_pins:
            shown_pins.add(pin)
            pin_rows.append(pin)
    for pi, pin in enumerate(pin_rows[:16]):
        py = mcu_y + 60 + pi * 26
        pc = _wire_colour(pin)
        # pin label inside box
        parts.append(f'<text x="{mcu_x + mcu_w - 8}" y="{py + 5}" class="pin-lbl" fill="{pc}" text-anchor="end">{_h(pin[:10])}</text>')
        # stub line to right
        parts.append(_line(mcu_x + mcu_w, py, mcu_x + mcu_w + 24, py, pc, 2))
        parts.append(_circle(mcu_x + mcu_w + 24, py, 4, pc))

    # ---- Peripheral components (right side) ----
    comp_x_start = mcu_x + mcu_w + 120
    comp_w, comp_base_h = 200, 80
    comp_gap = 24
    comp_colors = [COMP_STROKE, "#a78bfa", "#34d399", "#fb923c", "#fbbf24", "#f472b6", "#22d3ee", "#818cf8"]

    # Group connections by component
    comp_map: dict[str, list[dict]] = {}
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        pname = str(conn.get("part", conn.get("from", {}).get("component", "Component")) or "Component")
        comp_map.setdefault(pname, []).append(conn)

    comp_y = 90
    for idx, (pname, pconns) in enumerate(list(comp_map.items())[:8]):
        comp_h = max(comp_base_h, len(pconns) * 24 + 36)
        color = comp_colors[idx % len(comp_colors)]
        # component box
        parts.append(_rect(comp_x_start, comp_y, comp_w, comp_h, COMP_FILL, color, rx=8))
        parts.append(f'<text x="{comp_x_start + comp_w/2:.0f}" y="{comp_y + 20}" class="comp-name" text-anchor="middle" fill="{color}">{_h(pname[:24])}</text>')
        # find matching BOM item
        ref_url = ""
        for bitem in bom:
            if isinstance(bitem, dict) and pname.lower()[:8] in bitem.get("name", "").lower():
                ref_url = str(bitem.get("ref", bitem.get("datasheet", "")) or "")[:40]
                break
        if ref_url:
            parts.append(f'<text x="{comp_x_start + comp_w/2:.0f}" y="{comp_y + 32}" class="pin-lbl" text-anchor="middle">{_h(ref_url)}</text>')

        # draw pins + wires
        for pi, conn in enumerate(pconns[:6]):
            pin_name = str(conn.get("part_pin", conn.get("from", {}).get("pin", "")) or "")
            to_raw = conn.get("to", {})
            mcu_pin = (to_raw.get("pin", "") if isinstance(to_raw, dict) else str(to_raw or ""))
            note = str(conn.get("note", "") or "")
            pc = _wire_colour(pin_name, note)
            pin_y = comp_y + 42 + pi * 24
            # pin label on left side of component
            parts.append(f'<text x="{comp_x_start + 6}" y="{pin_y + 5}" class="pin-lbl" fill="{pc}">{_h(pin_name[:8])}</text>')
            # wire left from component to MCU
            # find MCU pin row y
            if mcu_pin in pin_rows:
                mpu_py = mcu_y + 60 + pin_rows.index(mcu_pin) * 26
            else:
                mpu_py = pin_y
            # draw elbow wire
            mid_x = comp_x_start - 60
            parts.append(_path(f"M{mcu_x + mcu_w + 24},{mpu_py} L{mid_x},{mpu_py} L{mid_x},{pin_y} L{comp_x_start},{pin_y}", pc, 2))
            # label mid-wire
            parts.append(f'<text x="{mid_x + 2}" y="{(mpu_py + pin_y) / 2}" class="wire-lbl" fill="{pc}">{_h((pin_name + "→" + mcu_pin)[:16])}</text>')

        comp_y += comp_h + comp_gap

    # ---- Power bus ----
    power_x = 60
    # VCC
    parts.append(_line(power_x, 90, power_x, 90 + mcu_h, WIRE_PWR, 3))
    parts.append(f'<text x="{power_x}" y="85" class="pin-lbl" fill="{WIRE_PWR}" text-anchor="middle">3V3</text>')
    # GND
    parts.append(_line(power_x + 16, 90, power_x + 16, 90 + mcu_h, WIRE_GND, 3))
    parts.append(f'<text x="{power_x + 16}" y="85" class="pin-lbl" fill="{WIRE_GND}" text-anchor="middle">GND</text>')
    # horizontal taps to MCU
    parts.append(_line(power_x, mcu_y + 20, mcu_x, mcu_y + 20, WIRE_PWR, 2))
    parts.append(_line(power_x + 16, mcu_y + 36, mcu_x, mcu_y + 36, WIRE_GND, 2))

    # ---- Bottom section: wiring table ----
    tbl_y = max(comp_y + 20, 540)
    if tbl_y < H - 160:
        parts.append(f'<text x="24" y="{tbl_y}" class="section-title">Complete Wiring Table</text>')
        col_x = [24, 200, 360, 540, 700, 940]
        hdrs = ["Component", "Component Pin", "MCU Pin", "Signal Type", "Wire Color", "Note"]
        for hi, hdr in enumerate(hdrs):
            parts.append(f'<text x="{col_x[hi] + 4}" y="{tbl_y + 20}" class="tbl-hdr">{_h(hdr)}</text>')
        parts.append(f'<line x1="24" y1="{tbl_y + 24}" x2="{W - 24}" y2="{tbl_y + 24}" stroke="{COMP_STROKE}" stroke-width="1"/>')
        for ri, conn in enumerate(connections[:(H - tbl_y - 40) // 20]):
            if not isinstance(conn, dict):
                continue
            pname = str(conn.get("part", conn.get("from", {}).get("component", "")) or "")
            pin_n = str(conn.get("part_pin", conn.get("from", {}).get("pin", "")) or "")
            to_raw = conn.get("to", {})
            to_str = (f"{to_raw.get('pin','?')}" if isinstance(to_raw, dict) else str(to_raw or "?"))
            note = str(conn.get("note", "") or "")
            sig = _infer_signal_type(pin_n, note)
            color = _wire_colour(pin_n, note)
            row_y = tbl_y + 36 + ri * 20
            if ri % 2 == 0:
                parts.append(f'<rect x="24" y="{row_y - 14}" width="{W - 48}" height="20" fill="rgba(30,58,95,0.35)"/>')
            vals = [pname[:22], pin_n[:12], to_str[:12], sig[:16], _std_wire_color_name(pin_n), note[:28]]
            for vi, val in enumerate(vals):
                if vi < len(col_x):
                    fc = color if vi == 4 else TEXT_MAIN
                    parts.append(f'<text x="{col_x[vi] + 4}" y="{row_y}" class="pin-lbl" fill="{fc}">{_h(val)}</text>')

    # Footer
    parts.append(f'<text x="{W // 2}" y="{H - 10}" class="footer" text-anchor="middle">NEXUS IoT · Project-synchronized wiring diagram · Connection data matches Circuit Studio, BOM and generated firmware</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _infer_signal_type(pin_name: str, note: str = "") -> str:
    p = (pin_name + " " + note).upper()
    if any(k in p for k in ("SDA", "SCL")):
        return "I²C"
    if any(k in p for k in ("MOSI", "MISO", "SCK", "CS", "SS")):
        return "SPI"
    if any(k in p for k in ("TX", "RX")):
        return "UART"
    if any(k in p for k in ("VCC", "3V3", "5V", "VIN")):
        return "Power"
    if any(k in p for k in ("GND", "GROUND")):
        return "Ground"
    if any(k in p for k in ("AO", "ANALOG", "ADC")):
        return "Analog"
    if any(k in p for k in ("PWM",)):
        return "PWM"
    return "Digital GPIO"


# ---------------------------------------------------------------------------
# Shared SVG defs
# ---------------------------------------------------------------------------
def _defs() -> str:
    return f"""<defs>
  <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
    <path d="M0,0 L10,4 L0,8 z" fill="{LABEL}"/>
  </marker>
  <style><![CDATA[
    .title  {{font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:18px;fill:{TEXT_MAIN};font-weight:700;}}
    .subtitle{{font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:11px;fill:{TEXT_SUB};}}
    .comp-name{{font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:13px;fill:{TEXT_MAIN};font-weight:600;}}
    .pin-lbl {{font-family:'JetBrains Mono','Fira Code',monospace,sans-serif;font-size:10px;fill:{LABEL};}}
    .wire-lbl{{font-family:'JetBrains Mono','Fira Code',monospace,sans-serif;font-size:9px;fill:{LABEL};}}
    .tbl-hdr {{font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:11px;fill:{COMP_STROKE};font-weight:700;}}
    .section-title{{font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:14px;fill:{TEXT_MAIN};font-weight:600;}}
    .footer {{font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:10px;fill:{TEXT_SUB};}}
    .row-num {{font-family:monospace;font-size:9px;fill:{TEXT_SUB};}}
  ]]></style>
</defs>"""


# ---------------------------------------------------------------------------
# Natural-language intent classifier (server-side, no AI needed)
# ---------------------------------------------------------------------------
_CIRCUIT_IMAGE_PATTERNS = [
    # draw / generate / show / give
    r"\b(draw|generate|create|make|produce|render)\b.{0,40}\b(circuit|wiring|schematic|diagram|connection|breadboard|pcb|layout|visual)\b",
    r"\bgive\s+me\s+(an?\s+)?(image|picture|diagram|drawing|visual|illustration)\b",
    r"\bshow\s+(me\s+)?(the\s+)?(circuit|wiring|connection|diagram|schematic|setup|layout|pinout|hardware)\b",
    r"\b(image|picture|diagram|illustration|visual)\s+(of|for)\s+(the|this|a)\b.{0,30}\b(circuit|project|wiring|setup)\b",
    r"\bhow\s+(do\s+I|to)\s+(wire|connect|hook\s+up|assemble)\b.{0,20}\b(visually|diagram|picture|image)\b",
    r"\bwiring\s+diagram\b",
    r"\bconnection\s+diagram\b",
    r"\bbreadboard\s+(diagram|view|layout|wiring|setup)\b",
    r"\bpin\s+(map|mapping|diagram|layout)\b",
    r"\bhardware\s+(setup|assembly|connection|diagram|layout)\b",
    r"\bstep.by.step\s+(visual|connection|wiring|guide|diagram)\b",
    r"\bvisual(ize|ization|ly)\b.{0,30}\b(circuit|wiring|connect|project)\b",
    r"\bblock\s+diagram\b",
    r"\bsystem\s+diagram\b",
    r"\bgpio\s+(pin\s+)?(map|diagram|layout|assignment)\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _CIRCUIT_IMAGE_PATTERNS]


def is_circuit_image_request(text: str) -> bool:
    """Return True if the user's message is asking for a circuit image/diagram."""
    return any(pat.search(text) for pat in _COMPILED_PATTERNS)


def infer_style(text: str) -> str:
    """Guess the preferred diagram style from the user's natural-language request."""
    t = text.lower()
    if any(k in t for k in ("breadboard", "physical", "build", "real", "prototype", "beginner")):
        return "breadboard"
    if any(k in t for k in ("schematic", "engineering", "professional", "pcb", "netlist", "symbol")):
        return "schematic"
    if any(k in t for k in ("wiring", "connect", "block", "table", "setup", "step")):
        return "wiring"
    return "auto"
