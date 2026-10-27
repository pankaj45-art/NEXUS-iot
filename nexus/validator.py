"""Rule-based circuit / hardware validation.

The same engine validates the 100+ seeded projects and powers the Pro
"Circuit Designer & Validator" tool.  It only asserts what the component
catalog actually knows; unknown hardware produces an explicit verification
step rather than a fabricated pass.
"""
from __future__ import annotations

from collections import defaultdict

from . import hardware


def validate(board_key: str, part_keys: list[str], pins: dict | None = None,
             comms: str = "serial") -> dict:
    """Return {issues: [...], wiring: [...], summary: {...}, passed: bool}."""
    issues: list[dict] = []
    pins = pins or hardware.assign_pins(board_key, part_keys)
    b = hardware.BOARDS.get(board_key)
    if not b:
        return {"issues": [{"severity": "error", "code": "UNKNOWN_BOARD",
                            "message": f"Unknown board '{board_key}'. Pinout must be verified manually."}],
                "wiring": [], "summary": {}, "passed": False}

    parts = {}
    for key in part_keys:
        if key not in hardware.PARTS:
            issues.append({"severity": "error", "code": "UNKNOWN_PART",
                           "message": f"Unknown component '{key}'; no electrical data to validate."})
            continue
        parts[key] = hardware.PARTS[key]

    def add(sev, code, msg, fix=""):
        issues.append({"severity": sev, "code": code, "message": msg, "fix": fix})

    # 1. unique-pin collisions ------------------------------------------------
    owners: dict[str, list[str]] = defaultdict(list)
    shared_bus = set()
    for p in parts.values():
        if p["iface"] == "i2c":
            shared_bus |= {str(b["i2c"]["SDA"]), str(b["i2c"]["SCL"])}
        if p["iface"] == "spi":
            shared_bus |= {str(v) for v in b["spi"].values()}
    for key, roles in pins.items():
        if key not in parts:
            continue
        p = parts[key]
        for role, pin in roles.items():
            pin = str(pin)
            if not pin.isdigit() and not pin.startswith(("A", "D")):
                continue  # labels such as ADC_EXTERNAL / BUS / I2S0
            kind = dict(p["signals"]).get(role, "bus")
            if kind in ("uart_rx", "uart_tx", "spi_cs") or pin in shared_bus:
                continue
            owners[pin].append(f"{key}.{role}")
    for pin, users in owners.items():
        if len(users) > 1:
            add("error", "PIN_CONFLICT", f"GPIO {pin} is assigned to multiple signals: {', '.join(users)}.",
                "Move one signal to a free GPIO and update the wiring table and firmware defines together.")

    # 2. board-specific electrical constraints --------------------------------
    for key, roles in pins.items():
        if key not in parts:
            continue
        p = parts[key]
        for role, pin in roles.items():
            pin = str(pin)
            if not pin.isdigit() and not pin.startswith(("A", "D")):
                if pin == "ADC_EXTERNAL":
                    add("error", "NO_ADC", f"{b['name']} has no usable ADC for {p['name']}.",
                        "Add an external I2C ADC such as ADS1115 and divide the signal below its input range.")
                continue
            kind = dict(p["signals"]).get(role, "")
            is_bus = pin in shared_bus or kind in ("uart_rx", "uart_tx", "spi_cs")
            if pin in b.get("reserved", []) and not is_bus:
                add("error", "RESERVED_PIN", f"GPIO {pin} ({key}.{role}) is a boot/flash/strapping pin on {b['name']}.",
                    "Use a free GPIO from the board's safe pool.")
            if pin in b.get("input_only", []) and kind in ("digital_out", "pwm_out"):
                add("error", "INPUT_ONLY", f"GPIO {pin} is input-only but {key}.{role} requires an output.",
                    "Use an output-capable GPIO.")
            if comms in ("wifi_mqtt", "wifi_http", "ble") and kind == "analog_in" and pin in b.get("adc2", []):
                add("error", "ADC2_WIFI", f"GPIO {pin} is an ADC2 channel; the ESP32 ADC2 is unusable while Wi-Fi is active.",
                    "Move the analog input to an ADC1 channel (GPIO32-35 on ESP32).")

    # 3. logic-level compatibility -------------------------------------------
    for key, p in parts.items():
        if p["logic_v"] > b["logic_v"] + 0.1:
            has_shifter = "level_shifter" in part_keys
            if p.get("level_shift") or p["iface"] in ("digital", "pwm", "uart"):
                if not has_shifter:
                    add("error", "LEVEL_MISMATCH",
                        f"{p['name']} uses {p['logic_v']:.1f} V logic; {b['name']} GPIO is {b['logic_v']:.1f} V only.",
                        "Insert a bidirectional level shifter (or a resistor divider on an output-only signal) and re-check the wiring table.")
        if p["logic_v"] + 0.1 < b["logic_v"] and p["iface"] in ("spi", "i2c", "uart", "digital"):
            if "level_shifter" not in part_keys:
                add("warning", "LEVEL_MISMATCH_5V_HOST",
                    f"{b['name']} drives {b['logic_v']:.1f} V signals into {p['name']} ({p['logic_v']:.1f} V logic).",
                    "Use a level shifter or a 5 V-tolerant module; verify the module's own onboard regulator/shifter first.")

    # 4. passive / support component requirements -----------------------------
    keyset = set(part_keys)
    need = {
        "ds18b20": ("r4k7", "4.7 kΩ pull-up between DATA and VCC"),
        "led": ("r220", "220 Ω series resistor on each LED"),
        "ws2812b": ("cap100", "1000 µF bulk capacitor across the strip supply"),
        "pump": ("cap100", "flyback diode (1N4007) across the pump and a bulk capacitor"),
        "valve": ("cap100", "flyback diode across the solenoid coil and a bulk capacitor"),
        "fan": ("cap100", "flyback protection and a bulk capacitor"),
        "hcsr04": ("level_shifter", "1 kΩ / 2 kΩ divider on the 5 V ECHO line"),
        "lcd": ("level_shifter", "level shifter for the 5 V I2C backpack"),
    }
    for trigger, (supp, why) in need.items():
        if trigger in keyset and supp not in keyset and not (trigger == "hcsr04" and "r10k" in keyset):
            add("warning", "MISSING_SUPPORT", f"{hardware.PARTS[trigger]['name']} is listed without {why}.",
                f"Add {supp} to the BOM and show it in the wiring table.")
    for heavy in ("relay", "pump", "valve", "fan", "ws2812b", "servo", "gsm"):
        if heavy in keyset and "buck5v" not in keyset:
            add("warning", "POWER_RAIL",
                f"{hardware.PARTS[heavy]['name']} should not be powered from the MCU 3.3 V rail.",
                "Use a separate 5 V / adequate-current supply with a common ground (add buck5v).")
            break
    if "gsm" in keyset and hardware.PARTS["gsm"]["current_ma"] > 1500:
        add("warning", "PEAK_CURRENT", "Cellular modem TX bursts can exceed 2 A.",
            "Provide a 2 A peak supply and place a 1000 µF low-ESR capacitor near the modem VCC pins.")
    if "lora" in keyset:
        add("info", "ANTENNA_REQUIRED", "A matched antenna must be connected before any LoRa transmission.",
            "Verify regional ISM band and duty-cycle limits before transmitting.")
    if any(p.get("group") == "Sensor" and p.get("iface") == "analog" for p in parts.values()):
        if board_key in ("esp32", "esp32s3", "picow", "esp8266"):
            add("info", "ADC_RANGE",
                f"Analog inputs must stay below {b['analog_max_v']:.1f} V on {b['name']}.",
                "Confirm divider ratio and ADC reference voltage with a multimeter before powering.")
    if sum(1 for k, p in parts.items() if p["iface"] == "i2c") >= 2:
        addrs = [p.get("address", "") for p in parts.values() if p["iface"] == "i2c" and p.get("address")]
        add("info", "I2C_BUS", f"Multiple I2C devices share SDA/SCL: {', '.join(addrs) or 'addresses in datasheets'}.",
            "Run an I2C scanner; resolve address conflicts via ADDR jumpers or an I2C multiplexer (TCA9548A).")

    # 5. wiring table ---------------------------------------------------------
    wiring = []
    for key, roles in pins.items():
        if key not in parts:
            continue
        p = parts[key]
        vbus = "3V3" if p["voltage"].startswith(("1.8", "2.4", "2.5", "2.6", "2.7", "3", "3.3")) else "5V"
        if p["iface"] not in ("passive", "power"):
            wiring.append({"part": p["name"], "part_pin": "VCC", "to": vbus,
                           "note": f"Operating range {p['voltage']}; confirm with the module silkscreen."})
            wiring.append({"part": p["name"], "part_pin": "GND", "to": "GND",
                           "note": "Common ground with controller and all supplies."})
        for role, pin in roles.items():
            if role in ("BUS",) or str(pin) == "ADC_EXTERNAL":
                continue
            kind = dict(p["signals"]).get(role, "bus")
            label = f"GPIO{pin}" if str(pin).isdigit() else str(pin)
            if kind == "analog_in":
                label += " (ADC)"
            note = "Shared bus line" if role in ("SDA", "SCL", "SCK", "MISO", "MOSI", "RX", "TX") else p["notes"][:160]
            wiring.append({"part": p["name"], "part_pin": role, "to": label, "note": note})

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {
        "issues": issues,
        "wiring": wiring,
        "summary": {
            "board": b["name"], "logic_voltage": b["logic_v"], "component_count": len(parts),
            "errors": len(errors), "warnings": len(warnings),
            "info": sum(1 for i in issues if i["severity"] == "info"),
            "estimated_5v_budget_ma": sum(p["current_ma"] for p in parts.values()
                                          if p["voltage"].startswith("5") and p["current_ma"] > 20),
        },
        "passed": not errors,
    }
