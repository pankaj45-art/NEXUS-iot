"""Breadboard Wiring & Assembly Coordinate Engine for NEXUS IoT.

Generates precise physical coordinate maps, rail allocations, and jumper guides
for any breadboard type (Full 830, Half 400, Mini 170, MB102 Power Module, Protoboard).
"""
from __future__ import annotations

import re
from typing import Any

BREADBOARD_PROFILES = {
    "full_830": {
        "key": "full_830",
        "name": "Full-Size Solderless Breadboard (830 Tie-Points, MB-102)",
        "rows": 63,
        "cols": "A-E (Left Strip) | F-J (Right Strip)",
        "rails": "Dual +/- Rails on both sides (Outer Blue [-], Inner Red [+])",
        "center_trough": "0.3 inch (7.62mm) center divider for DIP chips / DevKit modules",
        "notes": [
            "Center Rail Split: Many 830-point boards have a physical split at Row 30. Place jumper links between Row 30 and Row 31 for both (+) and (-) rails to ensure continuous power across the entire board.",
            "Place the microcontroller board straddling the center trough (Rows 1-15).",
            "Decoupling: Place a 100nF ceramic capacitor across the power rails near sensitive analog sensors."
        ]
    },
    "half_400": {
        "key": "half_400",
        "name": "Half-Size Solderless Breadboard (400 Tie-Points)",
        "rows": 30,
        "cols": "A-E (Left Strip) | F-J (Right Strip)",
        "rails": "Top and Bottom Power Rails (+ / -)",
        "center_trough": "0.3 inch center divider",
        "notes": [
            "Compact Layout: Microcontroller straddles Rows 1-15; sensors occupy Rows 18-30.",
            "Continuous Rails: Power rails run continuously from Row 1 to Row 30 with no center split.",
            "Use 22 AWG solid-core pre-cut jumpers to keep wiring low-profile and reduce parasitic capacitance."
        ]
    },
    "mini_170": {
        "key": "mini_170",
        "name": "Mini Solderless Breadboard (170 Tie-Points)",
        "rows": 17,
        "cols": "A-E (Left Strip) | F-J (Right Strip)",
        "rails": "No dedicated power rails (Row-direct distribution)",
        "center_trough": "Standard 0.3 inch divider",
        "notes": [
            "Rail-Less Distribution: Designate Row 1 as VCC (3.3V/5V) bus and Row 2 as GND bus.",
            "Ultra-compact: Ideal for sensor breakout prototyping or modular IoT nodes.",
            "Keep wire lengths under 5cm to prevent I2C/SPI signal degradation on compact layouts."
        ]
    },
    "mb102_pwr": {
        "key": "mb102_pwr",
        "name": "MB-102 Breadboard with Dual-Voltage Power Supply Module",
        "rows": 63,
        "cols": "A-E (Left Strip) | F-J (Right Strip)",
        "rails": "Left Rail: 3.3V Regulated | Right Rail: 5.0V Regulated | Common GND",
        "center_trough": "0.3 inch center divider",
        "notes": [
            "Power Module Plug-in: Insert MB-102 regulator into the top power rail pins (Rows 1-4).",
            "Jumper Selectors: Set Left jumper to 3.3V (for ESP32/logic), Right jumper to 5V (for relays/motors/buzzers).",
            "Power Input: 6.5V - 12V DC barrel jack or standard USB-B cable. Push the latching power button ON.",
            "Tie all grounds together: Connect the 3.3V rail (-) to the 5.0V rail (-) for a shared reference ground."
        ]
    },
    "protoboard": {
        "key": "protoboard",
        "name": "Perforated Stripboard / Protoboard (2.54mm Pitch Grid)",
        "rows": 50,
        "cols": "Point-to-point solder pads with power perimeter bus",
        "rails": "Perimeter copper bus lines for VCC and GND",
        "center_trough": "None (continuous pad grid)",
        "notes": [
            "Permanent Assembly: Solder sockets for the MCU rather than direct soldering for easy replacement.",
            "Power Busing: Solder 20-22 AWG bare tinned wire along perimeter for power distribution rails.",
            "Perform continuity check with a digital multimeter before powering on for the first time."
        ]
    }
}


def detect_breadboard_type(text: str) -> str:
    """Detect the requested breadboard profile from user prompt or configuration."""
    t = (text or "").lower()
    if any(k in t for k in ("mb102_pwr", "power supply", "power module", "regulator", "mb-102 power")):
        return "mb102_pwr"
    if any(k in t for k in ("mini", "170", "compact breadboard", "small breadboard")):
        return "mini_170"
    if any(k in t for k in ("half", "400", "half-size", "medium breadboard")):
        return "half_400"
    if any(k in t for k in ("proto", "stripboard", "perfboard", "pcb", "solderable")):
        return "protoboard"
    return "full_830"


def wire_color_for_signal(pin_name: str, purpose: str = "") -> str:
    """Standard electronics wire color convention."""
    p = (pin_name + " " + purpose).upper()
    if any(k in p for k in ("VCC", "3V3", "3.3V", "5V", "VIN", "+", "PWR", "POWER")):
        return "RED"
    if any(k in p for k in ("GND", "GROUND", "-", "0V", "VSS")):
        return "BLACK"
    if any(k in p for k in ("SCL", "CLK", "SCK", "CLOCK")):
        return "YELLOW"
    if any(k in p for k in ("SDA", "MOSI", "SDI")):
        return "GREEN"
    if any(k in p for k in ("MISO", "SDO", "RX", "RXD")):
        return "BLUE"
    if any(k in p for k in ("TX", "TXD", "SIG", "DATA", "OUT", "DO")):
        return "ORANGE"
    if any(k in p for k in ("CS", "SS", "CHIP_SELECT", "EN", "ENABLE", "RST", "RESET")):
        return "PURPLE"
    if any(k in p for k in ("PWM", "ANALOG", "A0", "AO", "ADC")):
        return "WHITE"
    return "GRAY"


def generate_breadboard_wiring_guide(circuit: dict, board_key: str = "esp32", bb_type: str = "full_830") -> str:
    """Generate comprehensive breadboard wiring guide and ASCII diagram for firmware comments."""
    profile = BREADBOARD_PROFILES.get(bb_type, BREADBOARD_PROFILES["full_830"])
    lines = []
    lines.append("/* ========================================================================================")
    lines.append("   NEXUS IoT - COMPLETE BREADBOARD WIRING & PHYSICAL ASSEMBLY GUIDE")
    lines.append(f"   Breadboard: {profile['name']}")
    lines.append(f"   Dimensions: {profile['rows']} Rows | Columns: {profile['cols']}")
    lines.append(f"   Power Rails: {profile['rails']}")
    lines.append("   ========================================================================================")
    lines.append("")
    lines.append("   [POWER RAIL CONNECTIONS]")
    if bb_type == "mb102_pwr":
        lines.append("    * Left Rail (+): 3.3V DC (Set left jumper to 3.3V) -> Powers Microcontroller & Logic")
        lines.append("    * Left Rail (-): Common GND [BLACK WIRE]")
        lines.append("    * Right Rail (+): 5.0V DC (Set right jumper to 5.0V) -> Powers Relays, Servos & Buzzers")
        lines.append("    * Right Rail (-): Common GND [BLACK WIRE] -> Connected to Left Rail (-) via bridge")
    elif bb_type == "mini_170":
        lines.append("    * Row 1 (Cols A-E): Designated 3.3V Power Bus [RED WIRE]")
        lines.append("    * Row 2 (Cols A-E): Designated Common GND Bus [BLACK WIRE]")
    else:
        lines.append("    * Top/Outer Rail (+) [RED]:    Microcontroller 3.3V / 5V pin -> Breadboard Positive Rail")
        lines.append("    * Top/Outer Rail (-) [BLUE]:   Microcontroller GND pin -> Breadboard Negative Rail")

    lines.append("")
    lines.append("   [ASSEMBLY NOTES & PRACTICAL TIPS]")
    for n in profile["notes"]:
        lines.append(f"    * {n}")

    # Extract component connections
    conns = []
    if "connections" in circuit and isinstance(circuit["connections"], list):
        for c in circuit["connections"]:
            if isinstance(c, dict):
                part = c.get("part") or c.get("from", {}).get("component", "Component")
                pin = c.get("part_pin") or c.get("from", {}).get("pin", "PIN")
                to = c.get("to")
                if isinstance(to, dict):
                    to = f"{to.get('component', 'MCU')}.{to.get('pin', 'PIN')}"
                note = c.get("note", "")
                conns.append({
                    "part": str(part),
                    "pin": str(pin),
                    "to": str(to or "MCU Pin"),
                    "note": str(note)
                })

    lines.append("")
    lines.append("   [ROW-BY-ROW COMPONENT PLACEMENT & JUMPER WIRE MAP]")
    lines.append("   " + "-" * 84)
    lines.append(f"   {'Component':<18} | {'Pin':<10} | {'Connects To':<22} | {'Color':<8} | {'Breadboard Loc'}")
    lines.append("   " + "-" * 84)

    # Standard MCU placement
    lines.append(f"   {'Microcontroller':<18} | {'VIN / 3V3':<10} | {'Power Rail (+)':<22} | {'RED':<8} | Row 1-15, Center Divider")
    lines.append(f"   {'Microcontroller':<18} | {'GND':<10} | {'Power Rail (-)':<22} | {'BLACK':<8} | Row 1-15, Center Divider")

    cur_row = 18
    for c in conns:
        if any(k in c["pin"].upper() for k in ("VCC", "3V3", "VIN", "+")):
            target = "Power Rail (+)"
            color = "RED"
            loc = f"Row {cur_row}, Col A -> (+) Rail"
        elif any(k in c["pin"].upper() for k in ("GND", "-", "0V")):
            target = "Power Rail (-)"
            color = "BLACK"
            loc = f"Row {cur_row}, Col A -> (-) Rail"
        else:
            target = c["to"]
            color = wire_color_for_signal(c["pin"], c["note"])
            loc = f"Row {cur_row}, Col B -> MCU Pin"

        lines.append(f"   {c['part'][:18]:<18} | {c['pin'][:10]:<10} | {target[:22]:<22} | {color:<8} | {loc}")
        cur_row = min(profile["rows"], cur_row + 1)

    lines.append("   " + "-" * 84)
    lines.append("   [PRE-POWER SAFETY CHECK]")
    lines.append("    1. Verify NO bridge exists between (+) and (-) rails (0.00 ohms continuity test).")
    lines.append("    2. Check that operating voltages (3.3V vs 5.0V) match each sensor datasheet.")
    lines.append("    3. Plug in USB cable; verify power LED illuminates without thermal buildup.")
    lines.append("   ======================================================================================== */")
    return "\n".join(lines)
