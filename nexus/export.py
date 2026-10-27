"""Server-side export builders. All exports are gated by project visibility."""
from __future__ import annotations

import json


def project_markdown(c: dict) -> str:
    o = c["overview"]
    out = [f"# {o['name']}", "", f"**Project ID:** `{o['id']}`  ",
           f"**Category:** {o['category']} · **Difficulty:** {o['difficulty']}  ",
           f"**Board:** {c['board']} · **Transport:** {c['comms']}  ",
           f"**Quality status:** {o['quality_status']} · **Visibility:** {o['publication_visibility']}", "",
           "## 1. Overview", "", o["summary"], "", f"**Problem statement:** {o['problem_statement']}", "",
           f"**Expected outcome:** {o['expected_outcome']}", "",
           f"**Estimated build time:** {o['estimated_build_time_hours']} h ({o['build_time_assumptions']})", "",
           "### Objectives", ""]
    out += [f"- {x}" for x in o["objectives"]]
    out += ["", "### Practical use cases", ""] + [f"- {x}" for x in o["practical_use_cases"]]
    out += ["", "### Prerequisites", ""] + [f"- {x}" for x in o["prerequisites"]]
    out += ["", "### Required skills", ""] + [f"- {x}" for x in o["required_skills"]]

    out += ["", "## 2. Bill of materials", "", c["bom"]["price_disclaimer"], "",
            "| # | Component | Qty | Purpose | Specs | Est. price | Mandatory |",
            "|---|---|---|---|---|---|---|"]
    for i, b in enumerate(c["bom"]["mandatory"], 1):
        out.append(f"| {i} | {b['name']} | {b['quantity']} | {b['purpose']} | {b['specifications']} | "
                   f"{b['estimated_price']} | {'yes' if b['mandatory'] else 'support'} |")
    out += ["", "### Optional upgrades", ""] + [f"- {b['name']}: {b['purpose']}" for b in c["bom"]["optional_upgrades"]]

    a = c["architecture"]
    out += ["", "## 3. Architecture", "", "```text"]
    for n in a["diagram"]["nodes"]:
        out.append(f"[{n['type'].upper():10s}] {n['label'].replace(chr(10), ' / ')}")
    out += ["", "Data flow:"] + [f"  {e['from']} --{e['label']}--> {e['to']}" for e in a["diagram"]["edges"]]
    out += ["```", ""]
    for s in a["subsystems"]:
        out += [f"**{s['name']}** — {s['role']}", ""]
    out += ["**Data flow**", ""] + [f"{i+1}. {x}" for i, x in enumerate(a["data_flow"])]
    out += ["", f"**Communication:** {json.dumps(a['communication_architecture'], indent=2)}", "",
            f"**Power:** {json.dumps(a['power_architecture'], indent=2)}", "",
            f"**Cloud:** {a['cloud_integration']}", "", f"**Storage:** {a['storage_processing']}"]

    ci = c["circuit"]
    out += ["", "## 4. Circuit and wiring", "", f"**Selected board:** {ci['selected_board']['name']} "
            f"({ci['selected_board']['logic_voltage']} V logic) — {ci['selected_board']['documentation']}", "",
            ci["selected_board"]["notes"], "", "### Wiring table", "",
            "| Component | Pin | Connect to | Note |", "|---|---|---|---|"]
    for w in ci["connections"]:
        out.append(f"| {w['part']} | {w['part_pin']} | {w['to']} | {w['note'][:160]} |")
    out += ["", "### Pull-ups / pull-downs", ""] + [f"- {x}" for x in ci["pullups_pulldowns"]]
    out += ["", "### Level shifting", ""] + [f"- {x}" for x in ci["level_shifting"]]
    out += ["", "### Voltage compatibility checks", ""] + [f"- {x}" for x in ci["voltage_compatibility_checks"]]
    out += ["", "### Power & current", ""] + [f"- {x}" for x in ci["power_current_considerations"]]
    out += ["", "### Uncertain / verification items", ""] + [f"- {x}" for x in ci["uncertain_parts"]]
    out += ["", "### Why these connections", ""] + [f"- {x}" for x in ci["why_connections"]]
    out += ["", f"Diagram: `{ci['schematic']['url']}`", ""]

    out += ["## 5. Implementation procedure", ""]
    for s in c["procedure"]:
        out += [f"### {s['step']}. {s['title']}", ""] + [f"- {d}" for d in s["details"]] + \
               ["", f"**Verification:** {s['verification']}", ""]

    fw = c["code"]
    out += ["## 6. Complete source code", "", f"**Language:** {fw['language']}  ",
            f"**Status:** {fw['status']}  ", f"**Core/toolchain:** {fw['board_core']}", "",
            "**Libraries:** " + ("; ".join(fw["libraries"]) or "core only"), "",
            "**Configuration placeholders:** " + (", ".join(fw["config_placeholders"]) or "none"), "",
            "```cpp" if fw["language"].startswith("Arduino") else "```python", fw["code"], "```", "",
            "**Upload:** " + fw["upload_instructions"], "", "**Expected output / sample log:**", "", "```text",
            fw["sample_log"], "```", ""]
    out += ["**Review notes:**", ""] + [f"- {x}" for x in fw["review_notes"]]

    out += ["", "## 7. Troubleshooting", ""]
    for t in c["troubleshooting"]:
        out += [f"### {t['issue']}", "", f"- **Symptoms:** {t['symptoms']}",
                f"- **Possible causes:** {t['possible_causes']}",
                f"- **Diagnostics:** {'; '.join(t['diagnostics'])}",
                f"- **Corrective actions:** {'; '.join(t['corrective_actions'])}", ""]

    ts = c["testing"]
    out += ["## 8. Testing and verification", "", "### Pre-power checklist", ""] + \
           [f"- {x}" for x in ts["pre_power_checklist"]]
    out += ["", "### Component tests", "", "| Component | Test | Expected | Calibration |", "|---|---|---|---|"]
    for t in ts["component_tests"]:
        out.append(f"| {t['component']} | {t['test']} | {t['expected']} | {t['calibration']} |")
    out += ["", "### Functional tests", ""] + \
           [f"- **{t['name']}:** {t['procedure']} → {t['expected_result']}" for t in ts["functional_tests"]]
    out += ["", "### Error conditions", ""] + [f"- {x}" for x in ts["error_conditions"]]
    out += ["", "### Performance checks", ""] + [f"- {x}" for x in ts["performance_checks"]]
    out += ["", "### Safety", ""] + [f"- {x}" for x in ts["safety_considerations"]]
    out += ["", "### Acceptance criteria", ""] + [f"- {x}" for x in ts["acceptance_criteria"]]
    out += ["", "### Validation status", ""] + [f"- **{k}:** {v}" for k, v in ts["validation_status"].items()]

    d = c["deliverables"]
    out += ["", "## 9. Final deliverables", "", "**Setup & operating instructions:**", ""] + \
           [f"- {x}" for x in d["setup_operating_instructions"]]
    out += ["", "**Expected results:**", ""] + [f"- {x}" for x in d["expected_results"]]
    out += ["", "**Limitations:**", ""] + [f"- {x}" for x in d["limitations"]]
    out += ["", "**Improvement opportunities:**", ""] + [f"- {x}" for x in d["improvement_opportunities"]]
    out += ["", "**References (real documentation URLs):**", ""] + \
           [f"- {r['title']} — {r['url']}" for r in d["references"]]
    q = c["quality"]
    out += ["", "## 10. Project quality status", "", f"**Status:** {q['status']}", "",
            f"**Evidence:** {q['evidence']}", "", "**Checks:**", ""] + \
           [f"- {'PASS' if x['passed'] else 'FAIL'} — {x['name']}" for x in q["checks"]]
    out += ["", "---", "", "Exported from NEXUS IoT. Content is protected; do not redistribute without permission.", ""]
    return "\n".join(out)


def render_download(content: dict, kind: str) -> tuple[str, str, str]:
    slug = content["slug"]
    if kind == "json":
        return f"{slug}.json", "application/json", json.dumps(content, indent=2, ensure_ascii=False)
    if kind == "code":
        fw = content["code"]
        ext = "py" if fw["language"].startswith("Python") else "ino"
        return f"{slug}.{ext}", "text/plain", fw["code"]
    if kind == "markdown":
        return f"{slug}.md", "text/markdown", project_markdown(content)
    if kind == "wiring":
        lines = ["component,part_pin,connect_to,note"]
        for w in content["circuit"]["connections"]:
            def esc(v):
                return '"' + str(v).replace('"', '""') + '"'
            lines.append(",".join(esc(w[k]) for k in ("part", "part_pin", "to", "note")))
        return f"{slug}-wiring.csv", "text/csv", "\n".join(lines)
    if kind == "bom":
        lines = ["name,quantity,purpose,specifications,estimated_price,mandatory,documentation"]
        for b in content["bom"]["mandatory"]:
            def esc(v):
                return '"' + str(v).replace('"', '""') + '"'
            lines.append(",".join(esc(b[k]) for k in ("name", "quantity", "purpose", "specifications",
                                                       "estimated_price", "mandatory", "documentation")))
        return f"{slug}-bom.csv", "text/csv", "\n".join(lines)
    if kind == "svg":
        from .diagram import render_svg
        return f"{slug}-diagram.svg", "image/svg+xml", render_svg(content)
    from .errors import ApiError
    raise ApiError(400, "Unknown export kind. Use code, markdown, json, wiring, bom or svg.", "invalid_input")
