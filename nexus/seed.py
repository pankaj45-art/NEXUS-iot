"""Idempotent seeding of the IoT Project Library.

Existing rows (including admin edits) are preserved: seeding only inserts
missing slugs.  Use --force via scripts/reseed_library.py to rebuild.
"""
from __future__ import annotations

import json
import time

from . import db
from .compiler import compile_spec
from .data import ALL_SPECS, CATEGORY_ORDER, validate_specs
from .security import json_dumps


def seed_projects(conn, force: bool = False) -> dict:
    problems = validate_specs()
    if problems:
        raise RuntimeError("Project library specification is invalid: " + "; ".join(problems[:5]))

    inserted = updated = skipped = 0
    now = time.time()
    for spec in ALL_SPECS:
        content = compile_spec(spec)
        row = conn.execute("SELECT id, status, is_free FROM projects WHERE slug=?", (spec["slug"],)).fetchone()
        values = (
            spec["slug"], spec["title"], spec["category"], spec["difficulty"],
            spec["board"], spec["comms"], content["summary"],
            json_dumps([spec["category"], spec["difficulty"], spec["board"], spec["comms"]]),
            1 if spec.get("free") else 0, spec.get("free_rank"),
            spec.get("status", "published"), content["quality"]["status"],
            json_dumps(content), now, now,
            now if spec.get("status", "published") == "published" else None,
        )
        if row is None:
            conn.execute(
                "INSERT INTO projects(slug,title,category,difficulty,board,comms,summary,tags,"
                "is_free,free_rank,status,quality_status,content_json,created_at,updated_at,published_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            inserted += 1
        elif force:
            conn.execute(
                "UPDATE projects SET title=?,category=?,difficulty=?,board=?,comms=?,summary=?,tags=?,"
                "is_free=?,free_rank=?,status=?,quality_status=?,content_json=?,updated_at=?,published_at=?,"
                "version=version+1 WHERE slug=?", values[1:13] + (values[14], values[15], spec["slug"]))
            updated += 1
        else:
            skipped += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped,
            "total": len(ALL_SPECS), "categories": len(CATEGORY_ORDER),
            "validation_problems": problems}


def categories(conn) -> list[dict]:
    """Admin-managed category taxonomy; defaults to the 25 curated categories."""
    managed = db.get_setting(conn, "categories", None)
    if isinstance(managed, dict):
        names = managed.get("names", CATEGORY_ORDER)
    elif isinstance(managed, list) and managed:
        names = [str(x) for x in managed]
    else:
        names = list(CATEGORY_ORDER)
    rows = conn.execute(
        "SELECT category, COUNT(*) AS total FROM projects WHERE status='published' GROUP BY category"
    ).fetchall()
    counts = {r["category"]: r["total"] for r in rows}
    seen, result = set(), []
    for name in list(names) + list(counts.keys()):
        if name and name not in seen:
            seen.add(name)
            result.append({"name": name, "published": counts.get(name, 0)})
    return result


def project_public(row, full: bool = True) -> dict:
    """Serialize a project row for the API, with a strict visibility boundary."""
    if not full:
        # Locked teaser: NO title, summary, category, diagram or content leaks.
        return {"locked": True, "id": "pro-" + str(row["id"]).zfill(4),
                "message": "Pro project - subscribe to unlock the full library."}
    content = json.loads(row["content_json"])
    return {
        "id": row["id"], "slug": row["slug"], "title": row["title"],
        "category": row["category"], "difficulty": row["difficulty"],
        "board": row["board"], "comms": row["comms"], "summary": row["summary"],
        "tags": json.loads(row["tags"] or "[]"),
        "is_free": bool(row["is_free"]), "free_rank": row["free_rank"],
        "status": row["status"], "quality_status": row["quality_status"],
        "version": row["version"], "updated_at": row["updated_at"],
        "content": content,
    }
