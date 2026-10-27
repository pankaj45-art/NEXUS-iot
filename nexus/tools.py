"""Ten Pro engineering tools + the free general assistant.

Every tool has a complete offline workflow.  When a live LLM is configured,
``ai.enrich`` adds a narrative layer but never replaces the deterministic,
verifiable core (pin maps, validation rules, scores, telemetry data).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from . import ai, codegen, config, db, hardware, validator
from .compiler import compile_spec
from .errors import ApiError
from .security import json_dumps, mask_secret

TOOL_META = {
    "project_generator": {"name": "AI IoT Project Generator", "feature": "tools.project_generator",
                          "description": "Turn a problem, parts list, budget and skill level into a complete project specification, wiring and firmware."},
    "circuit_designer": {"name": "AI Circuit Designer & Validator", "feature": "tools.circuit_designer",
                         "description": "Generate/edit a pin map, validate voltages, level shifting and common wiring mistakes, emit matching config."},
    "code_engineer": {"name": "AI Code Engineer", "feature": "tools.code_engineer",
                      "description": "Generate, explain, review and refactor ESP32/Arduino/Raspberry Pi/Pico firmware."},
    "debugging": {"name": "AI Debugging Center", "feature": "tools.debugging",
                  "description": "Analyse compiler errors, logs and circuit descriptions; remember what already failed."},
    "innovation": {"name": "AI Innovation Discovery", "feature": "tools.innovation",
                   "description": "Research documented technology limits and propose engineering directions with real sources."},
    "comparison": {"name": "Project Comparison & Gap Analysis", "feature": "tools.comparison",
                   "description": "Compare designs by components, cost, power, reliability, accuracy, security and limitations."},
    "startup_lab": {"name": "Startup & Product Idea Lab", "feature": "tools.startup_lab",
                    "description": "Business opportunities, MVP sizing, cost bands and validation plans with transparent scores."},
    "research": {"name": "Advanced Research Assistant", "feature": "tools.research",
                 "description": "Source discovery, technical summaries, reference tracking and report generation."},
    "device_monitoring": {"name": "Device Monitoring & Diagnostics", "feature": "tools.device_monitoring",
                          "description": "Live HTTP/MQTT telemetry, alerts, logs and clearly labelled simulated data."},
    "project_docs": {"name": "Project Management & Documentation", "feature": "tools.project_docs",
                     "description": "Milestones, versions, decisions, test results and reports generated from the saved state."},
}

PLATFORM_BOARDS = {
    "esp32": "esp32", "esp32-s3": "esp32s3", "esp32s3": "esp32s3", "esp32-cam": "esp32cam",
    "arduino": "uno", "arduino uno": "uno", "uno": "uno",
    "raspberry pi": "rpi4", "raspberry pi 4": "rpi4", "rpi": "rpi4",
    "pico": "picow", "pico w": "picow", "rp2040": "picow",
    "stm32": "uno", "esp8266": "esp8266", "nodemcu": "esp8266",
}


def _text(payload: dict, key: str, default: str = "", limit: int = 6000) -> str:
    v = payload.get(key, default)
    if isinstance(v, (list, dict)):
        v = json.dumps(v)
    return str(v)[:limit]


def _match_parts(text: str, explicit: list | None = None) -> list[str]:
    """Map free-text component names to real catalog keys."""
    found: list[str] = []
    for key in (explicit or []):
        k = str(key).strip().lower().replace(" ", "_")
        if k in hardware.PARTS and k not in found:
            found.append(k)
    hay = text.lower()
    for key, p in hardware.PARTS.items():
        if key in found or p["group"] in ("Passive", "Power", "Interface"):
            continue
        aliases = [key.replace("_", " "), p["name"].split(" (")[0].lower()]
        if any(a and a in hay for a in aliases):
            found.append(key)
    return found[:6]


def _spec_from_request(p: dict, parts: list[str], board: str, comms: str) -> dict:
    problem = _text(p, "problem") or _text(p, "description") or "Build a useful IoT prototype."
    outcome = _text(p, "outcome") or "A working, documented low-voltage IoT prototype with telemetry."
    skill = _text(p, "skill", "Beginner").title()
    difficulty = skill if skill in ("Beginner", "Intermediate", "Advanced") else "Intermediate"
    numeric = {"temperature", "humidity", "pressure", "lux", "light_raw", "soil_pct", "rain_pct",
               "level_pct", "turbidity_pct", "tds_ppm", "ph_value", "pressure_bar", "leak_pct",
               "gas_index", "co_index", "sound_index", "vib_index", "temp_raw", "uv_mw_cm2",
               "distance_cm", "flow_lpm", "pm25", "pm10", "co2", "tvoc", "voltage_v", "current_ma",
               "power_w", "current_a", "weight_g", "ax", "ay", "az", "vibration_g", "irValue",
               "obj_temp", "amb_temp", "lat", "lng", "reg_value", "jpeg_bytes", "rms", "bpm"}
    fields = [n for k in parts for n, _ in hardware.PARTS.get(k, {}).get("fields", []) if n in numeric]
    first = fields[0] if fields else "millis()"
    logic = (
        f"// Auto-generated from the request. Verify pin defines against the wiring table.\n"
        f"char buf[220];\n"
        f"snprintf(buf, sizeof(buf), \"{{\\\"request\\\":\\\"generated\\\",\\\"value\\\":%.2f,\\\"ts_ms\\\":%lu}}\", "
        f"(float){first}, (unsigned long)millis());\n"
        f"payload = String(buf);"
    )
    slug = "generated-" + re.sub(r"[^a-z0-9]+", "-", problem.lower())[:40].strip("-") or "generated-project"
    return {
        "slug": slug, "title": _text(p, "title", "Generated IoT Project")[:120],
        "category": _text(p, "category", "Custom & Interdisciplinary"),
        "difficulty": difficulty, "board": board, "parts": parts, "comms": comms,
        "problem": problem, "outcome": outcome,
        "objectives": ["Validate the problem and requirements", "Assemble and wire the selected parts", "Test and document the result"],
        "use_cases": [_text(p, "use_case", "Engineering prototype"), "Field trial", "Learning exercise"],
        "algorithm": _text(p, "algorithm", "Sample sensors on a fixed interval, validate ranges, build a JSON payload and transmit with bounded retries."),
        "logic": logic,
        "tests": ["Verify each sensor against a known reference", "Verify telemetry arrives after a network outage", "Verify fail-safe output on invalid data"],
        "fails": ["Sensor disconnected | Verify the bus and power rails.", "Wrong pin | Compare wiring table and firmware defines.", "Network offline | Confirm buffering and reconnect."],
        "hours": 8, "advanced": difficulty == "Advanced", "status": "draft",
        "quality": "Content incomplete",
        "summary": problem[:200], "skills": None, "prereqs": None, "free": False,
        "free_rank": None, "pins": {}, "cloud": "", "calibration": "", "deployment": "",
        "safety": "", "limitations": "", "improvements": [], "optional_parts": [],
        "refs": [], "logic_placeholder": True,
    }


# ---------------------------------------------------------------------------
# Tool 1 - AI IoT Project Generator
# ---------------------------------------------------------------------------
def project_generator(conn, ent, p, cfg) -> dict:
    problem = _text(p, "problem") or _text(p, "description")
    if not problem:
        raise ApiError(400, "Describe the problem or project you want to generate.", "invalid_input")
    parts_text = _text(p, "components") or _text(p, "available_components")
    explicit = p.get("parts") if isinstance(p.get("parts"), list) else []
    parts = _match_parts(problem + " " + parts_text, explicit) or ["bme280"]
    plat = _text(p, "platform", "esp32").lower()
    board = PLATFORM_BOARDS.get(plat, "esp32")
    comms = _text(p, "comms", "wifi_mqtt").lower()
    if comms not in codegen.COMMS:
        comms = "wifi_mqtt"
    budget = _text(p, "budget", "not specified")
    skill = _text(p, "skill", "Beginner")

    # Regeneration: merge the previous request and recompute only affected parts.
    regenerate = p.get("regenerate_parts") if isinstance(p.get("regenerate_parts"), list) else []
    previous = None
    if p.get("run_id"):
        row = conn.execute("SELECT input_json FROM tool_runs WHERE id=? AND user_id=? AND tool='project_generator'",
                           (p["run_id"], ent["user_id"])).fetchone()
        if row:
            previous = json.loads(row["input_json"])
            if previous:
                merged = dict(previous)
                merged.update({k: v for k, v in p.items() if k != "run_id"})
                p = merged
                problem = _text(p, "problem") or problem
                parts_text = _text(p, "components") or parts_text
                parts = _match_parts(problem + " " + parts_text, explicit) or parts
                plat = _text(p, "platform", plat).lower()
                board = PLATFORM_BOARDS.get(plat, board)
                comms = _text(p, "comms", comms).lower()

    spec = _spec_from_request(p, parts, board, comms)
    content = compile_spec(spec)
    affected = regenerate or ["overview", "bom", "architecture", "circuit", "procedure", "code", "testing", "deliverables"]
    section_map = {
        "overview": "overview", "bom": "bom", "architecture": "architecture", "circuit": "circuit",
        "procedure": "procedure", "code": "code", "testing": "testing", "deliverables": "deliverables",
        "wiring": "circuit", "firmware": "code", "documentation": "deliverables",
    }
    selected = {}
    for a in affected:
        key = section_map.get(a)
        if key:
            selected[key] = content[key]
    if not selected:
        selected = {k: content[k] for k in ("overview", "bom", "architecture", "circuit", "procedure", "code", "testing")}

    result = {
        "tool": "project_generator", "title": spec["title"],
        "inputs": {"problem": problem, "components": [hardware.PARTS[k]["name"] for k in parts],
                   "budget": budget, "skill": skill, "platform": board, "comms": comms,
                   "regenerated_sections": affected, "previous_run_merged": bool(previous)},
        "spec": spec, "sections": selected,
        "validation": content["circuit"]["validation"],
        "quality_status": content["quality"]["status"],
        "notes": ["Generated content is a DRAFT. It is statically reviewed, not hardware-tested.",
                  "Prices are indicative bands with stated assumptions; verify current supplier quotes."],
        "next_actions": ["Review the wiring table against real module pinouts", "Replace calibration placeholders",
                         "Save the generated project to a workspace to track versions"],
    }
    system = "You are a senior IoT hardware engineer. Be concise, technically precise and never invent sources."
    prompt = f"A user asks: {problem}. Components: {result['inputs']['components']}. Budget: {budget}. Skill: {skill}. " \
             f"Give 5 concise engineering recommendations and 3 risks for this project. Do not invent datasheets."
    return ai.enrich(conn, result, system, prompt)


# ---------------------------------------------------------------------------
# Tool 2 - Circuit Designer & Validator
# ---------------------------------------------------------------------------
def circuit_designer(conn, ent, p, cfg) -> dict:
    plat = _text(p, "board", "esp32").lower()
    board = PLATFORM_BOARDS.get(plat, plat if plat in hardware.BOARDS else "esp32")
    parts_text = _text(p, "components") or _text(p, "description")
    explicit = p.get("parts") if isinstance(p.get("parts"), list) else []
    parts = _match_parts(parts_text, explicit) or ["bme280"]
    overrides = p.get("pin_overrides") if isinstance(p.get("pin_overrides"), dict) else {}
    comms = _text(p, "comms", "wifi_mqtt").lower()
    pins = hardware.assign_pins(board, parts, overrides)
    val = validator.validate(board, parts, pins, comms)
    defines = []
    for key, roles in pins.items():
        part = hardware.PARTS.get(key)
        if not part:
            continue
        for role, pin in roles.items():
            if str(pin).isdigit() or str(pin).startswith(("A", "D")):
                defines.append(f"#define {re.sub(r'[^A-Z0-9_]', '_', key.upper())}_{role} {pin}")
    result = {
        "tool": "circuit_designer",
        "board": hardware.BOARDS[board]["name"],
        "components": [hardware.PARTS[k]["name"] for k in parts],
        "pin_map": pins,
        "wiring_table": val["wiring"],
        "issues": val["issues"],
        "summary": val["summary"], "passed": val["passed"],
        "code_config": "\n".join(defines),
        "support_parts_required": [hardware.PARTS[k]["name"] for k in parts
                                   if hardware.PARTS[k]["group"] in ("Passive", "Interface", "Power")],
        "checks_performed": ["GPIO collision detection", "Boot/strapping and input-only pin rules",
                             "3.3 V / 5 V logic compatibility", "ADC2 + Wi-Fi conflict", "I2C address conflicts",
                             "Current budget and external supply", "Required pull-ups / dividers / flyback protection"],
        "verification_steps": ["Confirm module pinouts against the linked datasheets, not memory.",
                               "Measure the highest signal voltage at each MCU pin before powering.",
                               "Re-run validation after any pin change; keep wiring table and firmware in sync."],
    }
    prompt = f"Review this circuit plan for {hardware.BOARDS[board]['name']} with {result['components']}. " \
             f"Issues: {[i['message'] for i in val['issues']]}. Give 4 concise hardware-verification steps. " \
             f"Do not invent component specifications."
    return ai.enrich(conn, result, "You are an electronics design reviewer. Never invent datasheet values.", prompt)


# ---------------------------------------------------------------------------
# Tool 3 - Code Engineer
# ---------------------------------------------------------------------------
def code_engineer(conn, ent, p, cfg) -> dict:
    mode = _text(p, "mode", "generate").lower()
    plat = _text(p, "platform", "esp32").lower()
    board = PLATFORM_BOARDS.get(plat, "esp32")
    code = _text(p, "code", "", limit=60000)
    limits = ent["limits"].get("max_code_chars", 20000)
    if len(code) > limits:
        raise ApiError(413, f"Code exceeds your plan limit of {limits} characters.", "limit_reached")

    if mode in ("generate", "refactor"):
        desc = _text(p, "description") or _text(p, "problem") or code[:400] or "Sensor telemetry node"
        parts = _match_parts(desc + " " + _text(p, "components")) or ["bme280"]
        spec = _spec_from_request({"problem": desc, "platform": plat,
                                   "comms": _text(p, "comms", "wifi_mqtt"), "skill": _text(p, "skill", "Intermediate")},
                                  parts, board, "wifi_mqtt")
        fw = codegen.generate_firmware(spec, parts, hardware.assign_pins(board, parts), spec["comms"])
        result = {
            "tool": "code_engineer", "mode": mode, "platform": hardware.BOARDS[board]["name"],
            "language": fw["language"], "code": fw["code"], "libraries": fw["libraries"],
            "config_placeholders": fw["config_placeholders"], "upload": fw["upload_instructions"],
            "expected_output": fw["expected_output"], "code_status": fw["status"],
            "refactor_notes": ["Non-blocking timing, explicit timeouts, range checks and reconnect logic are included.",
                               "Replace all YOUR_* placeholders before compiling.",
                               "If refactoring user code, compare the two versions line by line before uploading."] if mode == "refactor" else [],
            "supported_platforms": sorted(set(PLATFORM_BOARDS.values())),
        }
    elif mode in ("review", "explain"):
        if not code:
            raise ApiError(400, "Provide code to analyse.", "invalid_input")
        findings = []

        def add(sev, title, detail, fix):
            findings.append({"severity": sev, "title": title, "detail": detail, "fix": fix})

        secret_patterns = [r'(ssid|password|token|api[_-]?key)\s*=\s*"(?!YOUR_)[^"]{4,}"',
                           r'Bearer\s+[A-Za-z0-9_\-]{12,}']
        if any(re.search(pat, code, re.I) for pat in secret_patterns):
            add("critical", "Possible hard-coded credential",
                "A credential-like literal was found in the source.", "Move secrets to NVS/env/untracked secrets.h and rotate the exposed value.")
        if re.search(r"\bdelay\s*\(\s*\d{4,}", code):
            add("warning", "Long blocking delay",
                "A delay longer than ~1 s blocks reconnection and watchdog feeding.", "Use a millis() state machine.")
        if "WiFi" in code and not re.search(r"(WiFi\.status|reconnect|WL_CONNECTED)", code):
            add("warning", "No Wi-Fi reconnect logic", "The code never checks link state.", "Add a bounded reconnect loop with backoff.")
        if re.search(r"(client\.publish|http\.POST|mqtt\.publish)", code) and not re.search(r"(if\s*\(.*publish|state\(\)|HTTP\s|code\s*<)", code):
            add("warning", "Unchecked publish result", "Failures would be silent.", "Check the return code and log an error.")
        if "analogRead" in code and "ADC2" not in code and "32" not in code:
            add("info", "Verify ADC channel", "On ESP32, ADC2 channels fail while Wi-Fi is active.", "Use ADC1 (GPIO32-35) for analog sensors.")
        if re.search(r"String\s+\w+\s*[+=]", code) and "reserve" not in code:
            add("info", "Heap fragmentation risk", "Repeated String concatenation can fragment heap on long runs.", "Prefer snprintf into fixed char buffers, or reserve() capacity.")
        if "pulseIn(" in code and "30000" not in code:
            add("warning", "Unbounded pulseIn", "A missing echo can stall the loop.", "Pass a timeout (e.g. 30000UL) and handle zero.")
        if not re.search(r"(isnan|timeout|\[ERR\]|error)", code, re.I):
            add("warning", "No sensor error handling", "Invalid readings may propagate into control decisions.", "Check NaN/timeouts and fail safe.")
        if not findings:
            add("ok", "No rule violations detected", "Static checks passed; this is not a substitute for compilation.", "Compile for the target board and bench-test.")
        lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith("//")]
        result = {
            "tool": "code_engineer", "mode": mode,
            "findings": findings, "finding_count": len(findings),
            "summary": {"lines": len(code.splitlines()), "characters": len(code),
                        "critical": sum(1 for f in findings if f["severity"] == "critical"),
                        "warnings": sum(1 for f in findings if f["severity"] == "warning")},
            "explanation": ([f"Line {i+1}: {l[:120]}" for i, l in enumerate(lines[:25])] if mode == "explain" else []),
            "checks": ["Credential literals", "Blocking delays", "Reconnect behaviour", "Publish error handling",
                       "ADC2/Wi-Fi conflict", "String heap usage", "Sensor error handling", "Unbounded pulseIn"],
            "disclaimer": "Static review only. No compilation or hardware execution was performed.",
        }
    else:
        raise ApiError(400, "mode must be generate, explain, review or refactor.", "invalid_input")

    prompt = f"Platform: {plat}. Mode: {mode}. Summarise 4 firmware improvements for this code. " \
             f"Code excerpt: {code[:1500] or result.get('code','')[:1500]}"
    return ai.enrich(conn, result, "You are an embedded firmware reviewer. Never claim code was compiled or tested.", prompt)


# ---------------------------------------------------------------------------
# Tool 4 - Debugging Center
# ---------------------------------------------------------------------------
DEBUG_RULES = [
    (r"fatal error: .*\.h: no such file|was not declared|no matching function",
     "Missing library or incompatible library version",
     ["Install the exact library version from the Code tab", "Check the board core version", "Clean the build cache"]),
    (r"timed out waiting for packet header|failed to connect to esp32|no serial port",
     "Board not detected / upload failure",
     ["Use a data USB cable", "Install the CH340/CP210x driver", "Hold BOOT during upload", "Check boot-strapping GPIOs"]),
    (r"guru meditation|brownout|rst:0x|coredump|load prohibited",
     "Crash or brownout",
     ["Check the 3.3 V rail with an oscilloscope during actuator/Wi-Fi activity",
      "Add bulk capacitance and a separate actuator supply", "Decode the backtrace with addr2line"]),
    (r"nan|-127|85\.0|disconnected|invalid reading",
     "Invalid sensor reading",
     ["Verify the sensor's pull-up and power", "Discard the power-on reset value", "Print raw values and compare with the datasheet"]),
    (r"rc=-2|mqtt.*refused|connection refused|no route to host",
     "MQTT / network failure",
     ["Verify broker host/port and DNS", "Check credentials and ACLs", "Increase the MQTT buffer size"]),
    (r"wifi.*fail|wl_no_ssid_avail|wrong password|disconnected from wifi",
     "Wi-Fi association failure",
     ["Use a 2.4 GHz SSID without a captive portal", "Check SSID/password placeholders", "Move closer to the AP"]),
    (r"i2c|0x[0-9a-f]{2}.*not found|begin\(.*\) failed|scanner",
     "I2C bus problem",
     ["Run an I2C scanner", "Check SDA/SCL and 3.3 V/5 V logic", "Add 4.7 kΩ pull-ups or shorten the bus"]),
    (r"pulsein|timeout|no echo|ultrasonic",
     "Sensor timing timeout",
     ["Add a pulseIn timeout", "Check the ECHO divider", "Use a flat, hard target"]),
    (r"undefined reference|ld returned|collect2: error",
     "Linker error",
     ["Add the missing library source/header", "Check for duplicate library versions", "Match the board core"]),
    (r"sd.*fail|card mount failed|begin\(\) failed",
     "SD card failure",
     ["Format FAT32", "Check 3.3 V level shifting and CS", "Add 100 µF decoupling"]),
    (r"avrdude|stk500|sync error",
     "AVR programmer sync error",
     ["Select the correct COM port and board", "Remove shields during upload", "Check the bootloader"]),
]


def debugging(conn, ent, p, cfg) -> dict:
    error_text = _text(p, "error") or _text(p, "log") or _text(p, "compiler_output")
    circuit = _text(p, "circuit", "")
    symptom = _text(p, "symptom", "")
    session_key = _text(p, "session_key", "") or "default"
    if not (error_text or symptom):
        raise ApiError(400, "Provide a compiler error, log, test failure or symptom.", "invalid_input")
    blob = (error_text + " " + symptom + " " + circuit).lower()
    tried = conn.execute(
        "SELECT fix, outcome FROM debug_attempts WHERE user_id=? AND session_key=? ORDER BY created_at DESC LIMIT 50",
        (ent["user_id"], session_key)).fetchall()
    tried_fixes = [r["fix"] for r in tried]
    diagnoses = []
    for pattern, title, steps in DEBUG_RULES:
        if re.search(pattern, blob, re.I):
            fresh = [s for s in steps if s not in tried_fixes]
            diagnoses.append({
                "issue": title, "matched_pattern": pattern,
                "confidence": "rule-match (not statistically estimated)",
                "evidence": "Keyword pattern matched in the supplied log/description.",
                "diagnostics": ["Reproduce with verbose logging", "Check the wiring table and firmware defines", "Isolate the failing subsystem"],
                "fixes": fresh or steps,
                "previously_tried": [s for s in steps if s in tried_fixes],
                "repeated_fix_warning": not fresh,
            })
    if not diagnoses:
        diagnoses.append({
            "issue": "No known pattern matched", "matched_pattern": "", "confidence": "low",
            "evidence": "The offline rule engine has no rule for this text.",
            "diagnostics": ["Capture the exact compiler output including the first error",
                            "Note board, core version and library versions", "Test each sensor with a vendor example"],
            "fixes": ["Reduce to a minimal sketch that reproduces the fault", "Add serial checkpoints", "Check power and wiring"],
            "previously_tried": [], "repeated_fix_warning": False,
        })
    # Safe "test execution": static checks on the pasted text only, never arbitrary code.
    tests = [
        {"name": "Secrets in pasted log", "result": "FAIL" if re.search(r"(sk-[A-Za-z0-9]{10,}|Bearer\s+[A-Za-z0-9._-]{12,})", error_text) else "PASS",
         "note": "If FAIL, rotate the exposed credential before sharing the log again."},
        {"name": "Board/core identified", "result": "PASS" if re.search(r"esp32|esp8266|uno|pico|rpi|stm32|arduino", blob) else "UNKNOWN",
         "note": "Include the board name for better rules."},
        {"name": "Timeout/bounded retry present in pasted code",
         "result": "PASS" if re.search(r"timeout|30000|setTimeout|while\s*\(.*millis", blob) else "UNKNOWN",
         "note": "Static text check only - no code was executed."},
    ]
    result = {
        "tool": "debugging", "session_key": session_key,
        "input_summary": {"error_chars": len(error_text), "symptom": symptom[:200], "circuit": circuit[:200]},
        "diagnoses": diagnoses,
        "attempts_tracked": len(tried),
        "avoided_repeated_fixes": sum(1 for d in diagnoses if d["previously_tried"]),
        "static_tests": tests,
        "next_steps": ["Apply ONE fix at a time", "Record the outcome with outcome=fixed|failed",
                       "Re-run this tool with the same session_key to avoid repeated suggestions"],
        "disclaimer": "Rule-based static analysis. Nothing was compiled or executed on your hardware.",
    }
    if p.get("record_fix"):
        conn.execute(
            "INSERT INTO debug_attempts(user_id, session_key, symptom, fix, outcome, created_at) VALUES (?,?,?,?,?,?)",
            (ent["user_id"], session_key, (symptom or error_text)[:500],
             _text(p, "record_fix")[:300], _text(p, "outcome", "unverified")[:40], time.time()))
    prompt = f"A user reports: {(error_text or symptom)[:1500]}. Circuit: {circuit[:500]}. " \
             f"Suggest 3 additional diagnostic steps not already in: {[d['issue'] for d in diagnoses]}."
    return ai.enrich(conn, result, "You are an embedded debugging assistant. Never claim you ran code on hardware.", prompt)


# ---------------------------------------------------------------------------
# Tool 5 - Innovation Discovery
# ---------------------------------------------------------------------------
def innovation(conn, ent, p, cfg) -> dict:
    topic = _text(p, "topic") or _text(p, "technology") or _text(p, "problem")
    if not topic:
        raise ApiError(400, "Provide a technology, product or problem to research.", "invalid_input")
    refs = ai.references_for(topic, 7)
    corpus_facts = []
    for ref in refs:
        corpus_facts.append(f"{ref['title']} documents {', '.join(ref['topics'][:3])} ({ref['url']}).")
    limits = [
        "Low-cost MOS gas sensors are cross-sensitive to humidity/temperature and are not safety-certified detectors (see MQ/CCS811 notes in the component catalog).",
        "ESP32 ADC2 is unusable while Wi-Fi is active; analog sensing must use ADC1 (Espressif ADC documentation).",
        "Optical PM sensors over-read at high relative humidity; correction models require local calibration (Sensor.Community SDS011 notes).",
        "eCO₂ from VOC sensors is an estimate, not NDIR CO₂ measurement (Sciosense CCS811 / Sensirion SCD30 documentation).",
        "NIST IR 8425 and the OWASP IoT Top 10 identify hardcoded/default credentials and missing update mechanisms as recurring IoT weaknesses.",
    ]
    directions = [
        {"direction": "Sensor fusion with explicit uncertainty", "why": "Single low-cost sensors have documented cross-sensitivities.",
         "mvp": "Combine two complementary sensors and publish QA flags with raw values.", "risk": "Fusion can hide faults; keep raw channels."},
        {"direction": "Edge preprocessing with offline buffering", "why": "Network outages and cloud cost dominate remote deployments.",
         "mvp": "Local ring buffer + bounded retry + a documented queue cap.", "risk": "Flash wear and clock drift."},
        {"direction": "Security-by-default provisioning", "why": "NIST IR 8425 and OWASP IoT Top 10 target credential and update weaknesses.",
         "mvp": "Per-device credentials, signed OTA, credential-expiry monitor.", "risk": "Key management complexity."},
        {"direction": "Power-aware duty cycling", "why": "Battery life is usually the binding constraint for remote nodes.",
         "mvp": "Measure real sleep current and power-gate sensors.", "risk": "Wake-up latency and missed events."},
    ]
    result = {
        "tool": "innovation", "topic": topic,
        "research_summary": f"The offline corpus contains {len(refs)} matching documentation sources for '{topic}'. "
                            f"Facts below are traceable to those sources or to NEXUS's component catalog; ideas are hypotheses.",
        "sources": refs,
        "documented_limitations": limits,
        "engineering_directions": directions,
        "facts_vs_hypotheses": ai.split_facts_hypotheses(
            corpus_facts + limits,
            [d["direction"] + " could improve this area, but requires validation." for d in directions]),
        "validation_plan": ["Bench-test one direction with a measurable acceptance criterion",
                            "Compare against a reference instrument", "Publish raw data and a negative result if it fails"],
        "citation_policy": "Only URLs from the curated NEXUS documentation corpus are returned. No sources or citations are invented.",
    }
    prompt = f"Research topic: {topic}. Using only these sources: {[r['url'] for r in refs]}, " \
             f"write a 150-word technical summary separating documented facts from hypotheses. Do not add new citations."
    return ai.enrich(conn, result, "You are a rigorous engineering researcher. Never invent sources or citations.", prompt)


# ---------------------------------------------------------------------------
# Tool 6 - Comparison & Gap Analysis
# ---------------------------------------------------------------------------
def comparison(conn, ent, p, cfg) -> dict:
    items = p.get("items") if isinstance(p.get("items"), list) else []
    if len(items) < 2:
        raise ApiError(400, "Provide at least two items to compare.", "invalid_input")
    criteria = [
        ("components", 0.12, "lower"), ("cost", 0.18, "lower"), ("power", 0.16, "lower"),
        ("accuracy", 0.18, "higher"), ("reliability", 0.16, "higher"),
        ("architecture", 0.10, "higher"), ("security", 0.10, "higher"),
    ]
    norm = []
    for it in items[:6]:
        d = {"name": _text(it, "name", "Unnamed")[:100], "raw": {}}
        for key, _, _ in criteria:
            v = it.get(key, 5)
            try:
                d["raw"][key] = float(v)
            except (TypeError, ValueError):
                d["raw"][key] = 5.0
        norm.append(d)
    for key, weight, direction in criteria:
        vals = [d["raw"][key] for d in norm]
        lo, hi = min(vals), max(vals)
        for d in norm:
            if hi - lo < 1e-9:
                d[key] = 0.5
            else:
                r = (d["raw"][key] - lo) / (hi - lo)
                d[key] = r if direction == "higher" else 1 - r
    for d in norm:
        d["score"] = round(sum(d[k] * w for k, w, _ in criteria), 3)
    ranking = sorted(norm, key=lambda x: -x["score"])
    gaps = []
    for key, weight, direction in criteria:
        best = max(d["raw"][key] for d in norm) if direction == "higher" else min(d["raw"][key] for d in norm)
        for d in norm:
            if d["raw"][key] != best:
                gaps.append({"item": d["name"], "criterion": key, "weight": weight,
                             "current": d["raw"][key], "best_in_set": best,
                             "action": f"Improve {key}: document a measurement, then close the gap with a targeted redesign.",
                             "evidence": "User-supplied input; values are not independently verified."})
    result = {
        "tool": "comparison", "criteria": [{"name": k, "weight": w, "direction": d} for k, w, d in criteria],
        "table": [{"name": d["name"], **d["raw"], "weighted_score": d["score"]} for d in norm],
        "ranking": [d["name"] for d in ranking],
        "gaps": gaps[:20],
        "improvement_plan": [
            {"step": 1, "action": "Verify every user-supplied number with a measurement or a supplier quote", "owner": "engineering"},
            {"step": 2, "action": f"Prototype the highest-weight gap: {gaps[0]['criterion'] if gaps else 'none'}", "owner": "engineering"},
            {"step": 3, "action": "Re-score after a bench test and publish raw data", "owner": "QA"},
        ],
        "assumptions": ["All numeric inputs are on a user-defined 0-10 scale (higher = better unless noted).",
                        "Weights are fixed and shown above; they are configurable by an administrator, not learned.",
                        "Scores are relative to this comparison set only - they are NOT absolute quality ratings.",
                        "No product claims were verified against external benchmarks."],
        "disclaimer": "Transparent weighted sum, not a statistical model or a success probability.",
    }
    prompt = f"Comparison: {json.dumps(result['table'])}. Gaps: {[g['criterion'] for g in gaps[:8]]}. " \
             f"Give 4 concise, evidence-bounded improvement actions."
    return ai.enrich(conn, result, "You are a product engineer. Never present unverified estimates as measured facts.", prompt)


# ---------------------------------------------------------------------------
# Tool 7 - Startup & Product Idea Lab
# ---------------------------------------------------------------------------
def startup_lab(conn, ent, p, cfg) -> dict:
    industry = _text(p, "industry", "agriculture")
    problem = _text(p, "problem", "monitor remote assets")
    budget = _text(p, "budget", "$5,000")
    region = _text(p, "region", "unspecified")
    ideas = [
        {"name": f"Low-cost {industry} telemetry subscription",
         "customer_problem": problem,
         "alternatives": ["Manual inspection", "Existing industrial SCADA", "Spreadsheet + phone calls"],
         "differentiator": "Transparent calibration metadata and offline-first buffering at a hobby-hardware price point.",
         "mvp": "3 pilot nodes, one gateway, a dashboard and a documented calibration procedure.",
         "cost_band": "$25-$120 per node in components (indicative bands, not live prices) + gateway + cloud hosting",
         "validation_plan": ["10 customer interviews", "Deploy 3 pilots for 30 days", "Measure data completeness > 95 % and false-alert rate"],
         },
        {"name": f"{industry.title()} maintenance advisory service",
         "customer_problem": "Unplanned equipment downtime with no early signal",
         "alternatives": ["Reactive repairs", "OEM service contracts", "Manual vibration routes"],
         "differentiator": "Explainable z-score anomaly flags instead of an opaque black-box model.",
         "mvp": "One vibration/power sensor per asset, weekly PDF report, technician feedback loop.",
         "cost_band": "$40-$150 per monitored asset in components + installation labour",
         "validation_plan": ["Compare alerts with technician findings", "Track precision of alerts over 60 days", "Interview 5 site managers"],
         },
        {"name": "Retrofit compliance & audit logger",
         "customer_problem": "Missing time-stamped evidence for temperature, water or air-quality conditions",
         "alternatives": ["Paper logbooks", "Expensive certified loggers", "Consumer apps"],
         "differentiator": "Cheap, tamper-evident local logging with clear non-certified positioning.",
         "mvp": "SD-card logger with RTC, CSV export and a signed checksum per row.",
         "cost_band": "$20-$70 per logger; certification costs excluded",
         "validation_plan": ["Compare with a reference instrument", "Legal/regulatory review for the target market", "Pilot with 2 customers"],
         },
    ]
    scored = []
    for i, idea in enumerate(ideas):
        # Transparent additive score, 0-100. No probability of success is implied.
        components = {"problem_severity": 18 + (i * 2), "willingness_evidence": 10,
                      "technical_feasibility": 22, "cost_fit": 15 if "5,000" in budget else 12,
                      "differentiation": 12, "regulatory_burden_inverse": 8 if i != 2 else 4}
        score = sum(components.values())
        scored.append({**idea, "viability_score": min(score, 100),
                       "score_breakdown": components,
                       "score_meaning": "Additive heuristic (0-100) over six assumed factors; NOT a probability of success.",
                       "key_assumptions": [f"Region: {region}", f"Available budget: {budget}",
                                           "Component prices are indicative bands, not quotes",
                                           "No customer interviews or sales data have been provided - willingness_evidence is a placeholder."]})
    result = {
        "tool": "startup_lab", "industry": industry, "problem": problem,
        "opportunities": scored,
        "comparison_of_alternatives": ["Manual/pen-and-paper: cheapest, no live data",
                                       "Industrial SCADA: capable but high integration cost",
                                       "Consumer apps: convenient but poor sensor provenance"],
        "cost_model": {"hardware": "$25-$150 per node (indicative)",
                       "cloud": "Varies with sample rate; state assumptions before pricing",
                       "labour": "Largest cost - installation and calibration",
                       "certification": "Excluded; can dominate regulated markets"},
        "validation_plan": ["Run 10 problem interviews before building", "Pre-sell a pilot", "Define one measurable success metric",
                            "Publish a negative result if pilots fail"],
        "disclaimer": "Scores are transparent heuristics with stated assumptions. No success probability, revenue forecast or market-size claim is made.",
    }
    prompt = f"Industry: {industry}. Problem: {problem}. Budget: {budget}. Region: {region}. " \
             f"For these three ideas give the strongest falsifiable assumption for each. Do not invent market statistics."
    return ai.enrich(conn, result, "You are a cautious product strategist. Never invent market data or success probabilities.", prompt)


# ---------------------------------------------------------------------------
# Tool 8 - Advanced Research Assistant
# ---------------------------------------------------------------------------
def research(conn, ent, p, cfg) -> dict:
    query = _text(p, "query") or _text(p, "topic")
    if not query:
        raise ApiError(400, "Provide a research query.", "invalid_input")
    refs = ai.references_for(query, 8)
    sections = []
    for ref in refs:
        sections.append({"heading": ref["title"],
                         "summary": f"Documentation reference covering: {', '.join(ref['topics'])}. "
                                    f"Use the primary source to confirm exact electrical limits and versions.",
                         "url": ref["url"]})
    # Reference tracking
    tracked = []
    for r in refs:
        conn.execute(
            "INSERT INTO usage_events(user_id, kind, cost, created_at, meta_json) VALUES (?,?,?,?,?)",
            (ent["user_id"], "reference_view", 0, time.time(),
             json_dumps({"ref_id": r["id"], "query": query[:200]})))
        tracked.append(r["id"])
    md = [f"# NEXUS Research Report: {query}", "",
          f"Generated: {datetime.now(timezone.utc).isoformat()}",
          f"Mode: offline documentation corpus (no invented citations)", "",
          "## Scope", "", f"Query: {query}", "",
          "## Sources and summaries", ""]
    for s in sections:
        md += [f"### {s['heading']}", "", s["summary"], "", f"Source: {s['url']}", ""]
    md += ["## Open questions", "", "- Exact electrical limits must be confirmed in the linked primary source.",
           "- Library versions and board revisions must be verified before build.", "",
           "## References", ""] + [f"- {r['title']} - {r['url']}" for r in refs]
    result = {
        "tool": "research", "query": query, "sources": refs, "sections": sections,
        "tracked_reference_ids": tracked,
        "report_markdown": "\n".join(md),
        "reference_count": len(refs),
        "method": "Deterministic keyword matching against the curated NEXUS corpus of real documentation URLs.",
        "citation_policy": "No sources are invented. If the corpus has no match, the report says so.",
    }
    prompt = f"Research query: {query}. Using ONLY these sources: {[r['url'] for r in refs]}, " \
             f"write a structured 200-word technical summary with an explicit limitations section."
    return ai.enrich(conn, result, "You are a research librarian and engineer. Never fabricate a citation.", prompt)


# ---------------------------------------------------------------------------
# Tool 9 - Device Monitoring & Diagnostics
# ---------------------------------------------------------------------------
def device_monitoring(conn, ent, p, cfg) -> dict:
    action = _text(p, "action", "status").lower()
    platform = db.get_setting(conn, "platform", {})
    integrations = platform.get("integrations", {})
    devices = conn.execute(
        "SELECT id, name, token_prefix, created_at, last_seen_at FROM devices WHERE user_id=? ORDER BY created_at DESC",
        (ent["user_id"],)).fetchall()
    mqtt = integrations.get("mqtt", {})
    mqtt_status = {
        "configured": bool(config.MQTT_BROKER or mqtt.get("broker")),
        "broker": (mqtt.get("broker") or config.MQTT_BROKER or ""),
        "topic": mqtt.get("topic") or config.MQTT_TOPIC,
        "enabled": bool(mqtt.get("enabled")),
        "message": "HTTP ingest is always available. MQTT bridging requires a broker credential and the optional paho-mqtt package; "
                   "see README > Device Monitoring.",
    }
    result = {
        "tool": "device_monitoring", "action": action,
        "integrations": {"http_ingest": integrations.get("http_ingest", {"enabled": True}), "mqtt": mqtt_status},
        "devices": [dict(d) for d in devices],
        "mode": "offline", "ai_provider": "NEXUS rule engine", "model": "telemetry rule engine",
        "real_vs_simulated": "Every sample has a source column: 'real' (POST /api/ingest/<token>) or 'simulated' (explicitly labelled).",
    }
    if action == "simulate":
        device_id = p.get("device_id")
        row = conn.execute("SELECT id FROM devices WHERE id=? AND user_id=?", (device_id, ent["user_id"])).fetchone()
        if not row:
            raise ApiError(404, "Create a device first.", "not_found")
        import math
        now = time.time()
        series = []
        for i in range(30):
            v = 22.0 + 3.0 * math.sin((now + i * 60) / 600.0) + (0.4 if i % 7 == 0 else 0)
            series.append({"ts": now - (30 - i) * 60, "key": "temperature_c", "value": round(v, 2),
                           "unit": "C", "source": "simulated"})
            conn.execute(
                "INSERT INTO telemetry(device_id, ts, key, value, unit, source, meta_json) VALUES (?,?,?,?,?,?,?)",
                (row["id"], series[-1]["ts"], "temperature_c", series[-1]["value"], "C", "simulated", "{}"))
        result["simulated_series"] = series
        result["warning"] = "These samples are SIMULATED and are stored with source='simulated'. Never present them as real telemetry."
        return result

    if action in ("status", "diagnose"):
        series_by_device = {}
        for d in devices:
            rows = conn.execute(
                "SELECT ts, key, value, unit, source FROM telemetry WHERE device_id=? ORDER BY ts DESC LIMIT 60",
                (d["id"],)).fetchall()
            series_by_device[str(d["id"])] = [dict(r) for r in reversed(rows)]
        result["series"] = series_by_device
        if action == "diagnose":
            alerts = []
            for d in devices:
                rows = series_by_device[str(d["id"])]
                if not rows:
                    alerts.append({"device": d["name"], "severity": "info", "message": "No telemetry yet.",
                                   "action": "POST a sample to /api/ingest/<token> or generate labelled simulated data."})
                    continue
                latest = rows[-1]
                age = time.time() - latest["ts"]
                if age > 900:
                    alerts.append({"device": d["name"], "severity": "warning",
                                   "message": f"Last sample is {int(age/60)} min old - device may be offline.",
                                   "action": "Check power, Wi-Fi, and the ingest token."})
                vals = [r["value"] for r in rows if r["key"] == latest["key"]]
                if len(vals) > 5 and max(vals) - min(vals) < 1e-6:
                    alerts.append({"device": d["name"], "severity": "warning",
                                   "message": f"{latest['key']} is flatlined - possible stuck sensor.",
                                   "action": "Compare with a reference instrument and check the sensor wiring."})
                if latest["source"] == "simulated":
                    alerts.append({"device": d["name"], "severity": "info",
                                   "message": "Newest sample is SIMULATED.",
                                   "action": "Do not use simulated data for operational decisions."})
            result["alerts"] = alerts
            result["diagnostics_note"] = "Diagnostics run on stored samples only; no device commands were sent."
    return result


# ---------------------------------------------------------------------------
# Tool 10 - Project Management & Documentation
# ---------------------------------------------------------------------------
def project_docs(conn, ent, p, cfg) -> dict:
    action = _text(p, "action", "report").lower()
    wid = p.get("workspace_id")
    ws = None
    if wid:
        ws = conn.execute("SELECT * FROM workspaces WHERE id=? AND user_id=?", (wid, ent["user_id"])).fetchone()
        if not ws:
            raise ApiError(404, "Workspace not found.", "not_found")
    if action in ("milestone", "version", "decision", "test", "note", "code"):
        if not ws:
            raise ApiError(400, "workspace_id is required to record an event.", "invalid_input")
        payload = {"title": _text(p, "title", action.title())[:200],
                   "detail": _text(p, "detail", "")[:8000],
                   "status": _text(p, "status", "open")[:40],
                   "code": _text(p, "code", "")[:ent["limits"].get("max_code_chars", 20000)] if action == "code" else ""}
        conn.execute(
            "INSERT INTO workspace_events(workspace_id, kind, payload_json, created_at) VALUES (?,?,?,?)",
            (ws["id"], action, json_dumps(payload), time.time()))
        conn.execute("UPDATE workspaces SET updated_at=? WHERE id=?", (time.time(), ws["id"]))
        result = {"tool": "project_docs", "action": action, "recorded": payload, "workspace_id": ws["id"]}
        return ai.enrich(conn, result, "You are a documentation assistant.", "Summarise this project event in one sentence.")

    if not ws:
        row = conn.execute("SELECT * FROM workspaces WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
                           (ent["user_id"],)).fetchone()
        ws = row
    events = []
    if ws:
        events = [{"kind": e["kind"], **json.loads(e["payload_json"]), "created_at": e["created_at"]}
                  for e in conn.execute(
                      "SELECT * FROM workspace_events WHERE workspace_id=? ORDER BY created_at ASC", (ws["id"],))]
    state = json.loads(ws["state_json"]) if ws else {}
    grouped = {k: [e for e in events if e["kind"] == k]
               for k in ("milestone", "version", "decision", "test", "note", "code")}
    md = [f"# Project Report: {ws['name'] if ws else 'No workspace yet'}", "",
          f"Generated: {datetime.now(timezone.utc).isoformat()}", "",
          "## 1. Current state", "", f"Linked library project: `{ws['project_slug'] if ws else 'none'}`",
          "```json", json.dumps(state, indent=2)[:4000], "```", "",
          f"## 2. Milestones ({len(grouped['milestone'])})", ""]
    md += [f"- [{e.get('status','open')}] {e.get('title','')}: {e.get('detail','')}" for e in grouped["milestone"]] or ["- None recorded"]
    md += ["", f"## 3. Versions ({len(grouped['version'])})", ""]
    md += [f"- {e.get('title','')}: {e.get('detail','')}" for e in grouped["version"]] or ["- None recorded"]
    md += ["", f"## 4. Decisions ({len(grouped['decision'])})", ""]
    md += [f"- {e.get('title','')}: {e.get('detail','')}" for e in grouped["decision"]] or ["- None recorded"]
    md += ["", f"## 5. Test results ({len(grouped['test'])})", ""]
    md += [f"- {e.get('title','')}: {e.get('status','open')} - {e.get('detail','')}" for e in grouped["test"]] or ["- None recorded"]
    md += ["", "## 6. Saved code snapshots", ""]
    for e in grouped["code"]:
        md += [f"### {e.get('title','snapshot')}", "", "```cpp", e.get("code", "")[:6000], "```", ""]
    md += ["## 7. Limitations", "", "- This report reflects only what was actually saved in the workspace.",
           "- No physical test evidence is implied unless a test event records it.", ""]
    report = "\n".join(md)
    if ws:
        conn.execute(
            "INSERT INTO workspace_events(workspace_id, kind, payload_json, created_at) VALUES (?,?,?,?)",
            (ws["id"], "note", json_dumps({"title": "Generated report",
                                           "detail": f"{len(report)} characters generated from {len(events)} saved events."}), time.time()))
    result = {
        "tool": "project_docs", "action": "report",
        "workspace": {"id": ws["id"], "name": ws["name"], "project_slug": ws["project_slug"]} if ws else None,
        "event_count": len(events), "grouped_events": {k: len(v) for k, v in grouped.items()},
        "report_markdown": report,
        "download": f"/api/workspaces/{ws['id']}/report.md" if ws else None,
        "note": "Generated from the workspace's actual saved state; nothing is fabricated.",
    }
    return ai.enrich(conn, result, "You are a technical writer.",
                     "Given this workspace state, list 3 documentation improvements. Do not invent test results.")


# ---------------------------------------------------------------------------
# Free general assistant (limited)
# ---------------------------------------------------------------------------
def general_assistant(conn, ent, p, cfg) -> dict:
    from .services import chat
    return chat.synchronous(conn, ent, _text(p, "question") or _text(p, "message"))


DISPATCH = {
    "project_generator": project_generator, "circuit_designer": circuit_designer,
    "code_engineer": code_engineer, "debugging": debugging, "innovation": innovation,
    "comparison": comparison, "startup_lab": startup_lab, "research": research,
    "device_monitoring": device_monitoring, "project_docs": project_docs,
    "general_assistant": general_assistant,
}


def run_tool(conn, ent, name: str, payload: dict) -> dict:
    if name not in DISPATCH:
        raise ApiError(404, "Unknown tool.", "not_found")
    meta = TOOL_META.get(name)
    if meta:
        from .entitlements import require_feature
        require_feature(ent, meta["feature"])
    cfg = ai.get_ai_config(conn)
    result = DISPATCH[name](conn, ent, payload, cfg)
    mode = result.get("mode", "offline")
    conn.execute(
        "INSERT INTO tool_runs(user_id, tool, input_json, output_json, mode, created_at) VALUES (?,?,?,?,?,?)",
        (ent["user_id"], name, json_dumps(payload), json_dumps(result), mode, time.time()))
    result["run_id"] = conn.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
    return result
