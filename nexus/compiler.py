"""Compile a compact project specification into the full structured record.

One spec -> overview, BOM, architecture, circuit/wiring, procedure, firmware,
troubleshooting, testing, deliverables and quality status.  Shared structure,
project-specific content: hardware, control logic, tests, failure modes and
deployment notes come from the individual spec, not from a generic template.
"""
from __future__ import annotations

from . import codegen, hardware, validator

CATEGORY_SAFETY = {
    "Water Quality Monitoring": "Probes are for educational water samples only. Do not use the output to certify drinking water.",
    "Water Leakage Detection": "Keep low-voltage electronics away from wet areas; use isolated supplies and drip loops.",
    "Healthcare & Wellness Prototypes": "WELLNESS EDUCATION ONLY. This is not a medical device, must not be used for diagnosis or treatment, and is not a substitute for certified equipment.",
    "Accessibility & Assistive Technology": "Assistive prototypes must not replace a prescribed aid. Validate with the end user and a qualified professional.",
    "Wearable Electronics": "Use a certified, protected LiPo cell and never charge unattended. Skin-contact materials must be biocompatible.",
    "Air Quality Monitoring": "Low-cost gas/particle sensors are indicative, not regulatory-grade. Never use them for life-safety gas alarms.",
    "Smart Lighting & Energy Management": "MAINS WIRING IS EXCLUDED. All switching in these projects is low-voltage DC inside an insulated enclosure; use a qualified electrician for any mains installation.",
    "Industrial IoT": "Prototype hardware is not SIL/PL rated. Never connect it to a safety-critical control loop.",
    "Predictive Maintenance": "Treat anomaly scores as advisory. Verify with a technician before shutting down equipment.",
    "Smart Transportation & Parking": "Deploy only on private property/test tracks; never interfere with public road infrastructure.",
    "Custom & Interdisciplinary": "Review the specific hazards of the deployment environment before building.",
}

CATEGORY_IMPROVEMENTS = {
    "Smart Agriculture & Irrigation": ["Add rain-feedforward control and a flow sensor to detect a stuck pump", "Log soil EC and compensate temperature drift", "Solar supply with sleep scheduling"],
    "Environmental Monitoring": ["Add a calibrated reference sensor for co-location", "Implement sensor-fusion outlier rejection", "Add SD-card buffering for network outages"],
    "Weather Stations & Forecasting": ["Add a radiation shield and proper sensor siting", "Compute dew point and trends", "Use a barometric trend algorithm for short-term nowcasting"],
    "Water Quality Monitoring": ["Add temperature compensation and automatic probe cleaning", "Schedule two-point calibration reminders", "Compare with lab analysis before any decision"],
    "Water Leakage Detection": ["Add cable-break detection with an end-of-line resistor", "Add an automatic shutoff valve", "Send tamper and battery-health heartbeats"],
    "Home Automation": ["Add local manual override independent of Wi-Fi", "Use MQTT discovery for Home Assistant", "Add OTA updates with rollback"],
    "Smart Lighting & Energy Management": ["Add daylight harvesting with PID dimming", "Track kWh with a calibrated meter", "Schedule by occupancy prediction"],
    "Industrial IoT": ["Add Modbus/TLS gateway and watchdog", "Add redundant power and store-and-forward buffering", "Implement role-based device provisioning"],
    "Predictive Maintenance": ["Add FFT features and a baseline model", "Track model drift and false positives", "Add edge inference to reduce bandwidth"],
    "Machine & Equipment Monitoring": ["Add run-hour counters and threshold alerts", "Add isolation for industrial noise", "Add a local HMI with acknowledge button"],
    "Smart Buildings": ["Add occupancy-based HVAC schedules", "Add BACnet/Modbus gateway integration", "Encrypt telemetry end-to-end"],
    "Air Quality Monitoring": ["Add humidity correction for optical PM sensors", "Add a NDIR CO2 reference", "Publish to a public network with proper calibration metadata"],
    "Waste Management": ["Add fill-rate prediction and route optimisation", "Add a tamper switch", "Solar charge monitoring"],
    "Smart Transportation & Parking": ["Add computer-vision spot classification", "Add occupancy-led signage", "Add LoRaWAN backhaul for remote car parks"],
    "Logistics & Asset Tracking": ["Add geofences and shock events", "Add store-and-forward logging", "Use LTE-M/NB-IoT for coverage"],
    "Healthcare & Wellness Prototypes": ["Add clinical-grade validation study", "Add data minimisation and encryption", "Add a clear non-medical disclaimer in the UI"],
    "Accessibility & Assistive Technology": ["Co-design with users and add adjustable thresholds", "Add haptic and audio output modes", "Test under real-world lighting/noise"],
    "Wearable Electronics": ["Add power profiling and sleep states", "Add BLE bonding and encryption", "Validate skin temperature and strap comfort"],
    "Robotics & Automation": ["Add closed-loop PID control", "Add emergency stop and limit switches", "Add odometry fusion"],
    "Edge AI & Sensor Fusion": ["Quantise the model and benchmark latency", "Add drift detection and OTA model updates", "Compare edge vs cloud inference cost"],
    "Low-Power Sensor Networks": ["Measure real sleep current with a power profiler", "Add adaptive sampling", "Add battery-voltage forecasting"],
    "IoT Security & Device Diagnostics": ["Add secure boot and flash encryption", "Add signed OTA and key rotation", "Run an independent penetration test"],
    "Smart Campus Systems": ["Add anonymous aggregate occupancy reporting", "Add offline fallback", "Add per-room calibration"],
    "Remote Monitoring": ["Add store-and-forward with retry budgets", "Add dual-SIM or LoRa fallback", "Add remote diagnostics and watchdog"],
}


def _purpose(part: dict) -> str:
    fields = ", ".join(f"{n} ({u})" for n, u in part["fields"])
    group = part["group"]
    if group == "Sensor":
        return f"Measures {fields or 'a physical quantity'} for the control loop."
    if group == "Actuator":
        return "Physical output controlled by the firmware logic."
    if group == "Display":
        return "Local visual feedback independent of network connectivity."
    if group == "Storage":
        return "Local buffering and data logging when the network is unavailable."
    if group == "Comms":
        return f"Provides the {part['iface'].upper()} transport for telemetry."
    if group == "Interface":
        return "Protects the controller from incompatible logic levels."
    if group == "Power":
        return "Provides an isolated, adequately rated supply rail."
    if group == "Passive":
        return "Required bias, protection or decoupling component."
    return "Supports the signal chain."


def _support_parts(part_keys: list[str], board_key: str) -> list[str]:
    b = hardware.BOARDS[board_key]
    add: list[str] = []
    keys = set(part_keys)

    def need(k):
        if k not in keys:
            add.append(k)
            keys.add(k)

    if "ds18b20" in keys:
        need("r4k7")
    if "led" in keys:
        need("r220")
    heavy = {"relay", "pump", "valve", "fan", "ws2812b", "servo", "gsm"}
    if heavy & keys:
        need("cap100")
        need("buck5v")
    if any((hardware.PARTS.get(k, {}).get("level_shift") and
            hardware.PARTS[k]["logic_v"] > b["logic_v"] + 0.1) or
           (hardware.PARTS.get(k, {}).get("logic_v", b["logic_v"]) + 0.1 < b["logic_v"] and
            hardware.PARTS.get(k, {}).get("iface") in ("spi", "i2c", "uart", "digital"))
           for k in keys):
        need("level_shifter")
    if "hcsr04" in keys and "level_shifter" not in keys:
        need("r10k")
        need("r4k7")
    return add


def _steps(spec: dict, parts: list[str], pins: dict, val: dict, fw: dict) -> list[dict]:
    b = hardware.BOARDS[spec["board"]]
    libs = fw["libraries"]
    sensors = [hardware.PARTS[k]["name"] for k in parts
               if hardware.PARTS.get(k, {}).get("group") == "Sensor"]
    steps = [
        ("Understand the objective",
         [f"Problem: {spec['problem']}",
          f"Expected outcome: {spec['outcome']}",
          "Read the architecture and circuit sections before buying anything; confirm the board's GPIO voltage."],
         "You can state which sensor drives which output and why."),
        ("Prepare the workspace",
         ["Use an ESD-safe, dry, well-lit bench with a current-limited supply.",
          "Have a multimeter, jumper wires, a breadboard and the board's USB cable ready.",
          "Keep a notebook (or the NEXUS workspace) for calibration values and decisions."],
         "Supply current limit is set and the meter reads 0 A with nothing connected."),
        ("Collect and verify components",
         [f"Check every item in the BOM: {', '.join(hardware.PARTS[k]['name'] for k in parts[:6])}"
          + (" ..." if len(parts) > 6 else ""),
          "Confirm module silkscreen voltages and connector pinouts against the linked datasheets.",
          "Reject 5 V-only modules if the required level shifter is missing."],
         "All parts present; 3.3 V/5 V requirements recorded; no counterfeit regulator shortcuts."),
        ("Install software and libraries",
         [f"Install {b['core']}.",
          "Install the libraries listed in the Code tab: " + ("; ".join(libs[:8]) if libs else "core libraries only"),
          "Pin the versions: library API changes are a common cause of compile errors."],
         "A blank sketch compiles and uploads to the selected board."),
        ("Inspect pinouts and electrical requirements",
         [f"Open {b['docs']} and verify the exact board revision pinout.",
          f"Verify ADC range ({b['analog_max_v']} V max) and bus pins: I2C {b['i2c']}, SPI {b['spi']}.",
          "Compare every row of the wiring table with the module markings, not with memory."],
         "Pin mapping matches the wiring table and no boot-strapping pins are used."),
        ("Assemble the circuit with power disconnected",
         ["Connect GND first, then the supply rails, then signals.",
          "Fit the support passives from the BOM (pull-ups, dividers, flyback diode, bulk capacitor).",
          val["summary"].get("board", "") + " - double check orientation of polarised parts."],
         "Continuity test shows no shorts between VCC and GND."),
        ("Check wiring and power requirements",
         [f"Estimated 5 V actuator budget: {val['summary'].get('estimated_5v_budget_ma', 0)} mA; add 30 % headroom.",
          "Verify with the multimeter that every signal pin sees the expected idle voltage.",
          "Confirm common ground between every supply and the controller."],
         "No 5 V signal reaches a 3.3 V GPIO; supply stays within regulation under load."),
        ("Connect the board to the development computer",
         [f"Use the documented upload procedure: {b['upload']}",
          "If the port is missing, install the USB-UART bridge driver and try a different cable."],
         "Serial monitor shows the boot banner at 115200 baud."),
        ("Configure the development environment",
         ["Select the exact board and partition scheme; set Serial Monitor to 115200 baud.",
          "Set the calibration placeholders (DRY_RAW, WET_RAW, CAL_FACTOR, ...) after measuring them.",
          "Never paste real credentials into source files - use local, untracked secrets.h or NVS."],
         "The project compiles with the user's board selection."),
        ("Upload the firmware",
         ["Open the Code tab, copy the complete sketch into the IDE or src/main.cpp (PlatformIO).",
          "Replace every YOUR_* placeholder with local values, then compile and upload.",
          "Watch for library-version errors and resolve them before wiring power."],
         "[BOOT] and [INFO] setup complete appear in the serial log."),
        ("Configure Wi-Fi, MQTT, APIs or cloud services",
         [f"Transport: {codegen.COMMS.get(spec['comms'], codegen.COMMS['serial'])['label']}.",
          "Create a broker/endpoint and device credentials; prefer TLS and per-device identities.",
          "For MQTT, subscribe to the command topic and confirm QoS/retain behaviour."],
         "Device connects and publishes one test message; the broker/dashboard receives it."),
        ("Test individual components",
         [f"Run a minimal example for each sensor: {', '.join(sensors[:4]) or 'see component tests'}.",
          "Check actuator polarity separately with a current-limited supply.",
          "Record the raw values in the workspace for later comparison."],
         "Every sensor returns plausible values; every actuator responds to a direct command."),
        ("Test complete system behaviour",
         ["Run the full firmware and exercise all states: normal, threshold, disconnected and recovery.",
          "Compare the serial payload with the expected output in the Code tab."],
         "End-to-end behaviour matches the acceptance criteria in the Testing tab."),
        ("Calibrate the sensors",
         [spec.get("calibration") or
          "Follow the calibration note in each BOM row; record raw and reference values.",
          "Store calibration constants per device - never copy them from another unit."],
         "Reference measurements agree with the configured tolerance."),
        ("Diagnose common errors",
         ["Work through the Troubleshooting tab: board detection, libraries, wiring, invalid readings, power, network.",
          "Use the AI Debugging Center (Pro) with the exact compiler output and previous attempts."],
         "Each fault has a recorded cause and a verified fix."),
        ("Verify the required outputs",
         ["Confirm payload schema, units, sample interval and alert thresholds.",
          "Check the local display/log if the network is unavailable."],
         "All expected results in the Deliverables tab are observed."),
        ("Save the final code and configuration",
         ["Commit the sketch with the calibration table and an untracked secrets file.",
          "Save the wiring table, test results and decisions into a NEXUS workspace version."],
         "A second person can rebuild the project from the saved artefacts."),
        ("Document limitations and improvements",
         ["Record the limitations and improvement ideas from the Deliverables tab.",
          "Label the build as statically reviewed unless a physical test record exists."],
         "The project quality status in the admin workspace matches reality."),
    ]
    if spec.get("advanced"):
        steps.insert(16, (
            "Deployment, security, reliability and maintenance",
            [spec.get("deployment") or
             "Enable TLS, unique device credentials, a watchdog and signed OTA updates.",
             "Add store-and-forward buffering, a brownout-safe filesystem, and remote diagnostics.",
             "Plan a maintenance interval for recalibration and battery replacement."],
            "The device survives a power cycle and a 30-minute network outage without data loss."))
    return [
        {"step": i + 1, "title": t, "details": d, "verification": v}
        for i, (t, d, v) in enumerate(steps)
    ]


def _troubleshooting(spec: dict, parts: list[str], fw: dict) -> list[dict]:
    b = hardware.BOARDS[spec["board"]]
    out = []

    def add(issue, symptoms, causes, diagnostics, actions):
        out.append({"issue": issue, "symptoms": symptoms, "possible_causes": causes,
                    "diagnostics": diagnostics, "corrective_actions": actions})

    add("Board not detected / cannot upload",
        "No serial port, 'timed out waiting for packet header', or upload retries.",
        ["Wrong USB cable (charge-only)", "Missing USB-UART driver", "Boot-strapping pin held low", "Brownout during upload"],
        ["Check Device Manager / dmesg for the USB-UART VID:PID", "Try a known-good data cable", "Hold BOOT if your board requires it"],
        ["Install the CH340/CP210x driver", "Use a powered USB hub", "Verify GPIO0/GPIO12 strap state", fw["upload_instructions"]])
    add("Compilation error / library version mismatch",
        "'no matching function', 'class has no member', or missing header.",
        ["A library major version changed its API", "Two libraries define the same symbol", "Wrong board core selected"],
        ["Read the first compiler error, not the last", "Compare with the version list in the Code tab", "Compile a library example"],
        ["Pin the documented library versions", "Select the exact board core", "Remove duplicate includes"])
    add("Incorrect wiring or pin assignment",
        "A sensor reads zero/NaN, an actuator never responds.",
        ["SDA/SCL swapped", "Signal on a boot-strapping pin", "Wrong pin constant vs wiring table"],
        ["Compare the wiring table to the actual board markings", "Blink each GPIO and verify with a meter", "Run an I2C scanner"],
        ["Correct the wiring AND the firmware defines as a single change", "Re-run the Circuit Validator (Pro)"])
    add("Sensor returns invalid or stuck readings",
        "NaN, -127 °C, constant 0, or values that never change.",
        ["Missing pull-up", "Sensor not powered", "ADC input above the allowed range", "Insufficient warm-up"],
        ["Measure VCC at the sensor pins", "Check bus with an I2C scanner / logic analyser", "Print raw ADC counts"],
        ["Fit the BOM pull-up/divider", "Add the documented warm-up delay", "Replace the sensor if the raw value stays pinned"])
    add("Power instability / random resets",
        "Brownout detector messages, Wi-Fi resets when a motor starts.",
        ["Actuator powered from the MCU rail", "Missing bulk capacitor", "Undersized USB supply"],
        ["Measure the 3.3 V rail during actuator switching with an oscilloscope", "Check peak current against the BOM"],
        ["Use a separate 5 V supply with common ground", "Add 100–1000 µF low-ESR decoupling", "Add a flyback diode to inductive loads"])
    add("Wi-Fi connection failure",
        "Reconnect loop, no IP address.",
        ["Wrong SSID/password", "2.4 GHz-only radio on a 5 GHz SSID", "Weak signal or captive portal"],
        ["Print WiFi.status()", "Test with a 2.4 GHz phone hotspot"],
        ["Use placeholders from a local secrets file", "Move the antenna clear of metal", "Add a bounded retry with backoff"])
    add("MQTT or API connection failure",
        "rc=-2/5, HTTP 4xx/5xx, or messages missing on the dashboard.",
        ["Wrong host/port/TLS setting", "Rejected credentials", "Topic mismatch", "Oversized payload"],
        ["Use mosquitto_sub to observe the topic", "Check the broker log", "Print the HTTP status code"],
        ["Verify credentials and ACLs", "Increase the MQTT buffer", "Align topic names and payload units"])
    add("Incorrect calibration",
        "Readings are plausible but wrong by a consistent offset or scale.",
        ["Placeholder constants not replaced", "Different sensor unit", "Temperature drift"],
        ["Log raw counts next to a reference instrument at 3 points", "Check the part marking vs the assumed sensitivity"],
        ["Compute a two-point calibration and store it per device", "Add temperature compensation"])
    add("Unexpected output / logic behaves differently",
        "Actuator chatters at a threshold or alerts fire too often.",
        ["No hysteresis", "Float comparison without tolerance", "Race between sensor and control task"],
        ["Log the control inputs and the decision each cycle", "Check timing of the sample interval"],
        ["Add hysteresis and a minimum dwell time", "Clamp inputs and validate ranges"])
    add("Missing dependencies / toolchain problems",
        "Header not found or a PlatformIO build cannot resolve a library.",
        ["Library not declared in platformio.ini", "Conflicting core versions", "Stale build cache"],
        ["Run a clean build", "Inspect the dependency graph"],
        ["Declare exact library versions", "Delete .pio/build and rebuild"])

    # Part-specific troubleshooting from the real catalog data
    for key in parts:
        p = hardware.PARTS.get(key)
        if not p:
            continue
        if p["iface"] == "i2c":
            add(f"{p['name']}: no I2C response",
                "Init error message at boot or repeated 0xFF reads.",
                [f"Wrong address ({p.get('address') or 'see datasheet'})", "SDA/SCL reversed", "Missing pull-ups on a long bus"],
                [f"Run an I2C scanner; expected address {p.get('address') or 'in datasheet'}", "Check SDA/SCL idle at VCC"],
                ["Correct the begin() address", "Shorten the bus / add 4.7 kΩ pull-ups", "Check 3.3 V vs 5 V logic"])
            break
    for key in parts:
        p = hardware.PARTS.get(key)
        if p and p["iface"] == "analog":
            add("Analog reading drifts or clips",
                "Values saturate at 0 or ADC_MAX, or drift with temperature.",
                ["Divider ratio wrong", "Input exceeds the ADC range", "High-impedance source without settling time"],
                [f"Measure the signal voltage at the ADC pin (max {b['analog_max_v']} V)", "Compare raw counts to a known voltage"],
                ["Resize the divider and update the conversion constants", "Add a 100 nF cap and a second ADC read after switching"])
            break

    for i, custom in enumerate(spec.get("fails", [])):
        issue, rest = (custom.split("|", 1) + [""])[:2] if "|" in custom else (custom, "")
        add(f"Project-specific issue {i+1}: {issue.strip()}",
            rest.strip() or "Observed during bench testing of this project.",
            ["Configuration or environment mismatch", "Threshold/calibration mismatch", "Hardware variant difference"],
            ["Reproduce with serial logging enabled", "Compare with the expected result in the Testing tab"],
            ["Apply the fix from the Testing tab and re-run the acceptance test", "Record the attempt in the Debugging Center"])
    return out


def _testing(spec: dict, parts: list[str], val: dict) -> dict:
    b = hardware.BOARDS[spec["board"]]
    component_tests = []
    for key in parts:
        p = hardware.PARTS.get(key)
        if not p or p["iface"] in ("passive", "power"):
            continue
        fields = ", ".join(f"{n} ({u})" for n, u in p["fields"])
        component_tests.append({
            "component": p["name"],
            "test": f"Run the vendor example / read the raw interface and log {fields or 'the raw value'} for 60 s.",
            "expected": "Stable, in-range values; no NaN/timeouts; documented warm-up honoured.",
            "calibration": p["calibration"] or "Confirm with a reference instrument if accuracy matters.",
        })
    return {
        "pre_power_checklist": [
            "No VCC-to-GND short on the assembled board (continuity test).",
            f"All signal levels <= {b['analog_max_v']} V for analog inputs and <= {b['logic_v']} V for digital inputs.",
            "Every level shifter / divider / pull-up / flyback diode from the BOM is fitted.",
            "Actuator supply is separate and current-limited; all grounds are common.",
            "Polarised components, regulators and antenna connections verified.",
        ],
        "component_tests": component_tests,
        "functional_tests": [{"name": f"Functional test {i+1}", "procedure": t,
                              "expected_result": "Behaviour matches the acceptance criteria; serial payload contains the new state."}
                             for i, t in enumerate(spec.get("tests", []))],
        "error_conditions": [
            "Disconnect a sensor mid-run: firmware must log [ERR] and continue, not hang.",
            "Disable Wi-Fi / broker for 5 minutes: buffered or reconnection logic must recover.",
            "Force an out-of-range sensor value: output must fail safe (actuator OFF).",
            "Power-cycle during operation: no corrupt configuration or unsafe output state.",
        ],
        "performance_checks": [
            f"Sample interval as configured ({'5 s default' if spec['board'] != 'rpi4' else 'env-configurable'}); measure jitter over 100 samples.",
            "Measure peak current with a meter; compare against the BOM budget.",
            "Measure end-to-end latency from sensor change to dashboard alert.",
            "Verify memory headroom (free heap) over 24 h to detect leaks.",
        ],
        "safety_considerations": [CATEGORY_SAFETY.get(spec["category"],
                                  "Low-voltage prototype only. Disconnect power before rewiring. Never connect to mains without certified hardware and a qualified electrician.")]
                                 + ([spec["safety"]] if spec.get("safety") else []),
        "acceptance_criteria": [
            "Firmware compiles for the specified board and core version.",
            "All BOM components accounted for in the wiring table and code.",
            "Each functional test passes with the documented expected result.",
            "No unresolved ERROR-severity validation issues remain (" + str(val["summary"].get("errors", 0)) + ").",
            "Secrets are absent from source code; calibration constants are documented.",
        ],
        "validation_status": {
            "simulated": "Not simulated on hardware; behaviour is described analytically.",
            "static_validation": "Statically checked: pin map, logic-level compatibility, BOM/code/wiring consistency, secrets scan.",
            "physical_testing": "NOT PHYSICALLY TESTED. A physical test record must be attached before changing the quality status.",
        },
    }


def _references(spec: dict, parts: list[str]) -> list[dict]:
    b = hardware.BOARDS[spec["board"]]
    seen = set()
    refs = []

    def add(title, url, kind):
        if url and url not in seen:
            seen.add(url)
            refs.append({"title": title, "url": url, "type": kind})

    add(f"{b['name']} official documentation / getting started", b["docs"], "board")
    comm = codegen.COMMS.get(spec["comms"], codegen.COMMS["serial"])
    add(f"{comm['label']} reference documentation", comm["docs"], "communications")
    for key in parts:
        p = hardware.PARTS.get(key)
        if p and p["iface"] not in ("passive", "power"):
            add(f"{p['name']} datasheet / vendor documentation", p["docs"], "component")
    topics = spec["category"].lower().split() + [spec["comms"], spec["board"]]
    for ref in hardware.REFERENCES:
        if any(t in ref["title"].lower() or t in " ".join(ref["topics"]) for t in topics if len(t) > 3):
            add(ref["title"], ref["url"], "engineering reference")
        if len(refs) >= 12:
            break
    for r in spec.get("refs", []):
        add(r.get("title", "Additional reference"), r.get("url", ""), "project reference")
    return refs


def compile_spec(spec: dict) -> dict:
    board_key = spec["board"]
    b = hardware.BOARDS[board_key]
    core_parts = list(spec["parts"])
    support = _support_parts(core_parts, board_key)
    parts = core_parts + support
    pins = hardware.assign_pins(board_key, parts, spec.get("pins"))
    val = validator.validate(board_key, parts, pins, spec["comms"])
    fw = codegen.generate_firmware(spec, parts, pins, spec["comms"])
    comm = codegen.COMMS.get(spec["comms"], codegen.COMMS["serial"])

    optional_keys = list(spec.get("optional_parts", [])) or ["rtc", "sdcard", "oled"]
    optional = []
    for k in optional_keys:
        if k in hardware.PARTS and k not in parts:
            p = hardware.PARTS[k]
            optional.append({
                "name": p["name"], "quantity": 1, "purpose": "Optional upgrade: " + _purpose(p),
                "specifications": f"Interface {p['iface'].upper()}; operating {p['voltage']}",
                "alternatives": p["alternatives"], "estimated_price": p["price_estimate"],
                "price_assumption": "Indicative range; verify with your supplier. Not a live price.",
                "voltage": p["voltage"], "current_ma": p["current_ma"],
                "compatibility_notes": p["notes"], "mandatory": False, "documentation": p["docs"],
            })

    def _baseline(name, purpose, specs, price, docs, notes):
        return {"name": name, "quantity": 1, "purpose": purpose, "specifications": specs,
                "alternatives": "Equivalent part meeting the stated electrical ratings.",
                "estimated_price": price,
                "price_assumption": "Indicative 2024-era street-price band; NOT a live quote.",
                "voltage": "see specifications", "current_ma": 0,
                "compatibility_notes": notes, "mandatory": True, "documentation": docs}

    mandatory = [
        _baseline(b["name"], "Main controller running the generated firmware",
                  f"{b['core']}; {b['logic_v']} V GPIO logic; USB/programming interface",
                  "$4-$35 depending on board", b["docs"],
                  "Confirm the exact board revision pinout; strapping and input-only pins must be avoided."),
        _baseline("Regulated DC supply + USB cable", "Power the controller and peripherals within their ratings",
                  f"5 V / 2 A USB supply (see {b['voltage_note']}); current-limited bench supply for first power-on",
                  "$5-$15", b["docs"],
                  "Never back-power a board through a GPIO; share ground between every supply."),
        _baseline("Breadboard / jumper wires / multimeter", "Prototype the documented wiring and verify voltages before power-on",
                  "22-24 AWG jumpers, solderless breadboard, digital multimeter with continuity test",
                  "$8-$25", "https://www.arduino.cc/reference/en/",
                  "Check continuity and measure every signal voltage before connecting the board."),
    ]
    for k in parts:
        p = hardware.PARTS.get(k)
        if not p:
            continue
        mandatory.append({
            "name": p["name"], "quantity": 1,
            "purpose": _purpose(p) + (" (auto-added support part)" if k in support else ""),
            "specifications": f"Interface {p['iface'].upper()}; operating {p['voltage']}; signal logic {p['logic_v']} V",
            "alternatives": p["alternatives"] or "See the vendor's pin-compatible equivalent.",
            "estimated_price": p["price_estimate"],
            "price_assumption": "Indicative 2024-era street-price band with stated assumption; NOT a live quote.",
            "voltage": p["voltage"], "current_ma": p["current_ma"],
            "compatibility_notes": p["notes"] or "Verify the module revision and silkscreen before wiring.",
            "mandatory": k not in support, "documentation": p["docs"],
        })

    sensor_parts = [hardware.PARTS[k] for k in parts if hardware.PARTS.get(k, {}).get("group") == "Sensor"]
    actuator_parts = [hardware.PARTS[k] for k in parts if hardware.PARTS.get(k, {}).get("group") == "Actuator"]
    comms_parts = [hardware.PARTS[k] for k in parts if hardware.PARTS.get(k, {}).get("group") == "Comms"]
    fields = [f"{n} ({u})" for p in sensor_parts for n, u in p["fields"]]

    cloud = spec.get("cloud") or (
        "MQTT broker + dashboard (e.g. Mosquitto + Node-RED / Home Assistant) and optional time-series DB."
        if spec["comms"] in ("wifi_mqtt", "gsm", "ethernet") else
        "Optional HTTPS endpoint or local dashboard; the device is functional offline."
        if spec["comms"] in ("wifi_http", "ble", "espnow") else
        "Local logging only; a gateway can forward buffered records to the cloud."
    )

    diagram = {
        "nodes": [
            {"id": "power", "label": "Power\n" + ("5 V / 2 A rail + 3.3 V LDO" if any(k in parts for k in ("buck5v", "relay", "pump")) else "USB 5 V -> 3.3 V"), "type": "power"},
            {"id": "sensors", "label": "Sensing\n" + (", ".join(p["name"].split(" (")[0][:22] for p in sensor_parts[:3]) or "digital/analog inputs")[:60], "type": "sensor"},
            {"id": "mcu", "label": b["name"].split(" (")[0] + "\nfirmware + calibration", "type": "controller"},
            {"id": "logic", "label": "Control logic\n" + spec["algorithm"][:44] + ("..." if len(spec["algorithm"]) > 44 else ""), "type": "logic"},
            {"id": "outputs", "label": "Outputs\n" + (", ".join(p["name"].split(" (")[0][:20] for p in actuator_parts[:3]) or "serial / display"), "type": "output"},
            {"id": "comms", "label": comm["label"][:44], "type": "comms"},
            {"id": "cloud", "label": "Dashboard / API\nMQTT · HTTP · storage", "type": "cloud"},
        ],
        "edges": [
            {"from": "power", "to": "mcu", "label": "VCC/GND"},
            {"from": "sensors", "to": "mcu", "label": "I2C/SPI/ADC/GPIO"},
            {"from": "mcu", "to": "logic", "label": "raw values"},
            {"from": "logic", "to": "outputs", "label": "decisions"},
            {"from": "logic", "to": "comms", "label": "JSON payload"},
            {"from": "comms", "to": "cloud", "label": "telemetry"},
        ],
    }

    architecture = {
        "diagram": diagram,
        "subsystems": [
            {"name": "Power", "role": f"{b['voltage_note']} Estimated external 5 V actuator budget: {val['summary'].get('estimated_5v_budget_ma',0)} mA."},
            {"name": "Sensing", "role": "Measures " + (", ".join(fields) if fields else "digital states") + " using: " + ", ".join(p["name"] for p in sensor_parts) + "."},
            {"name": "Control", "role": b["name"] + " runs the sampling, filtering, calibration and decision logic: " + spec["algorithm"]},
            {"name": "Actuation / UI", "role": "Outputs: " + (", ".join(p["name"] for p in actuator_parts) or "serial log / dashboard only")},
            {"name": "Communications", "role": comm["label"] + (" using " + ", ".join(p["name"] for p in comms_parts) if comms_parts else "")},
            {"name": "Storage / cloud", "role": cloud},
        ],
        "data_flow": [
            f"1. {', '.join(p['name'] for p in sensor_parts) or 'Input'} produces raw electrical signals.",
            f"2. {b['name']} reads them over {', '.join(sorted({p['iface'].upper() for p in sensor_parts})) or 'GPIO'} and applies conversion/calibration.",
            f"3. Control logic: {spec['algorithm']}",
            f"4. Firmware builds a JSON payload and drives: {', '.join(p['name'] for p in actuator_parts) or 'serial output'}.",
            f"5. {comm['label']} transports the payload; local display/storage provide an offline fallback.",
            "6. Dashboard/API stores the time series, visualises it and raises alerts against configured thresholds.",
        ],
        "communication_architecture": {
            "transport": comm["label"], "topic_or_endpoint": "nexus/YOUR_DEVICE_ID/telemetry (MQTT) or /telemetry (HTTP)",
            "payload_format": "JSON with device, project, ts and measurement keys with explicit units",
            "qos_reliability": "QoS 1 for MQTT, bounded retry + local buffering for HTTP; reconnection logic in firmware",
            "security": "Per-device credentials, TLS where supported, no secrets in source code",
        },
        "power_architecture": {
            "controller": f"{b['name']} - {b['voltage_note']}",
            "external_supply": "Separate 5 V / adequate-current rail for actuators" if "buck5v" in parts else "USB 5 V supply for the controller",
            "estimated_peak_5v_ma": val["summary"].get("estimated_5v_budget_ma", 0),
            "protection": ", ".join(hardware.PARTS[k]["name"] for k in parts if k in ("r220", "r10k", "r4k7", "cap100", "level_shifter")) or "Series resistors and decoupling as per BOM",
        },
        "cloud_integration": cloud,
        "storage_processing": "Time-series storage at the dashboard/API; local ring buffer or SD card for outage tolerance. Sampling interval is configurable in firmware.",
    }

    uncertainties = [i["message"] + " -> " + i.get("fix", "") for i in val["issues"]
                     if i["severity"] in ("warning", "info")]
    circuit = {
        "selected_board": {"name": b["name"], "logic_voltage": b["logic_v"],
                           "documentation": b["docs"], "notes": b["voltage_note"]},
        "connections": val["wiring"],
        "pin_mapping": {k: v for k, v in pins.items()},
        "pullups_pulldowns": [f"{hardware.PARTS[k]['name']}: {hardware.PARTS[k]['notes']}"
                              for k in parts if k in ("r10k", "r4k7", "ds18b20", "reed", "button")],
        "level_shifting": ([f"Level shifter required and included for {hardware.PARTS[k]['name']} "
                            f"({hardware.PARTS[k]['logic_v']} V -> {b['logic_v']} V GPIO)."
                            for k in parts if hardware.PARTS.get(k, {}).get("level_shift")]
                           or ["All listed modules use logic levels compatible with the selected board."]),
        "interfaces": sorted({hardware.PARTS[k]["iface"].upper() for k in parts if k in hardware.PARTS}),
        "voltage_compatibility_checks": [i["message"] for i in val["issues"]] or ["No rule violations detected in the catalog-based validation."],
        "power_current_considerations": [
            f"Estimated 5 V load: {val['summary'].get('estimated_5v_budget_ma', 0)} mA; add 30 % headroom.",
            f"GPIO recommended current: {b['gpio_current_ma']} mA per pin; use drivers for actuators.",
            "All boards and external supplies share a common ground.",
        ],
        "schematic": {"format": "SVG block/wiring diagram", "url": f"/api/projects/{spec['slug']}/diagram.svg",
                      "note": "Generated from this project's actual BOM, pin map and transport - not a generic image."},
        "why_connections": [
            f"{hardware.PARTS[k]['name']} uses {hardware.PARTS[k]['iface'].upper()} because {hardware.PARTS[k]['notes'] or 'that is its native electrical interface'}."
            for k in parts if k in hardware.PARTS and hardware.PARTS[k]["iface"] not in ("passive", "power")
        ][:8],
        "uncertain_parts": uncertainties[:8] or ["No unresolved catalog-level uncertainties; physical pinout verification is still required."],
        "validation": val,
    }

    procedure = _steps(spec, parts, pins, val, fw)
    troubleshooting = _troubleshooting(spec, parts, fw)
    testing = _testing(spec, parts, val)
    references = _references(spec, parts)

    quality_status = spec.get("quality") or "Technically reviewed"
    checks = [
        {"name": "All 10 content sections present", "passed": True},
        {"name": "BOM, wiring table and firmware share one pin map", "passed": True},
        {"name": "Rule-based circuit validation has no ERROR issues", "passed": val["passed"]},
        {"name": "No real credentials in example code", "passed": "YOUR_" in fw["code"] or fw["language"].startswith("Python")},
        {"name": "Physical hardware test record attached", "passed": False},
    ]

    content = {
        "slug": spec["slug"],
        "title": spec["title"],
        "category": spec["category"],
        "difficulty": spec["difficulty"],
        "summary": spec.get("summary") or (spec["problem"] + " " + spec["outcome"])[:300],
        "board": b["name"],
        "comms": comm["label"],
        "overview": {
            "name": spec["title"], "id": spec["slug"], "category": spec["category"],
            "difficulty": spec["difficulty"], "summary": spec.get("summary") or spec["problem"],
            "problem_statement": spec["problem"], "objectives": spec["objectives"],
            "practical_use_cases": spec["use_cases"], "expected_outcome": spec["outcome"],
            "estimated_build_time_hours": spec["hours"],
            "build_time_assumptions": "Assumes a working toolchain, all parts on hand, and no custom PCB fabrication; add 2-4 h for an enclosure.",
            "prerequisites": spec.get("prereqs") or [
                "Basic soldering/breadboarding and multimeter use",
                f"{b['core']} installed", "Arduino C++ fundamentals" if b["platform"] == "arduino" else "Python 3 fundamentals",
            ],
            "required_skills": spec.get("skills") or (["Schematic reading", "I2C/SPI buses", "Basic control logic", "MQTT/HTTP fundamentals"]
                                                      if spec["difficulty"] == "Advanced" else
                                                      ["Breadboarding", "Serial monitor", "Basic C++ syntax"]),
            "status": spec.get("status", "published"),
            "publication_visibility": "Free" if spec.get("free") else "Pro",
            "quality_status": quality_status,
        },
        "bom": {
            "currency": "USD (indicative)", "price_disclaimer":
                "These are labelled ESTIMATES based on typical 2024 marketplace bands for single-unit hobby modules. No live price feed is used; always obtain a current quote.",
            "mandatory": mandatory, "optional_upgrades": optional,
            "estimated_total_band": "See individual rows; a typical build is $25-$120 depending on sensors, actuators and enclosure.",
        },
        "architecture": architecture,
        "circuit": circuit,
        "procedure": procedure,
        "code": fw,
        "troubleshooting": troubleshooting,
        "testing": testing,
        "deliverables": {
            "final_components": [m["name"] for m in mandatory],
            "final_wiring_table": val["wiring"],
            "final_code": {"filename": "main.py" if fw["language"].startswith("Python") else f"{spec['slug']}.ino",
                           "language": fw["language"], "code": fw["code"], "status": fw["status"]},
            "setup_operating_instructions": [s["title"] + ": " + s["verification"] for s in procedure],
            "expected_results": [t["expected_result"] for t in testing["functional_tests"]] + fw["expected_output"],
            "limitations": ([spec["limitations"]] if spec.get("limitations") else []) + [
                CATEGORY_SAFETY.get(spec["category"], "Educational low-voltage prototype; not certified for safety-critical or regulated use."),
                "Firmware is statically reviewed, not physically tested on the assembled hardware.",
                "Prices are indicative estimates, not live quotes.",
            ],
            "improvement_opportunities": (spec.get("improvements") or []) +
                CATEGORY_IMPROVEMENTS.get(spec["category"], ["Add calibration tracking", "Add local buffering", "Add enclosure and strain relief"]),
            "references": references,
        },
        "quality": {
            "status": quality_status,
            "allowed_statuses": ["Draft", "Content incomplete", "Technically reviewed", "Ready for publication", "Physically tested"],
            "checks": checks,
            "evidence": "No physical hardware test evidence is attached to the seeded library. Status must not be promoted to 'Physically tested' without a dated test record.",
            "physical_test_confirmed": False,
            "minimum_for_publication": "Technically reviewed + all required sections + no ERROR validation issues",
        },
        "meta": {"version": 1, "generated_by": "NEXUS project compiler", "parts": parts,
                 "pins": pins, "comms_key": spec["comms"], "board_key": board_key,
                 "advanced": bool(spec.get("advanced")), "free_rank": spec.get("free_rank")},
    }
    return content
