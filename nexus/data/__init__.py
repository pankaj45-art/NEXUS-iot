"""Aggregated IoT Project Library specifications."""
from .specs_free import SPECS as FREE
from .specs_pro_a import SPECS as PRO_A
from .specs_pro_b import SPECS as PRO_B
from .specs_pro_c import SPECS as PRO_C
from .specs_pro_d import SPECS as PRO_D

ALL_SPECS = FREE + PRO_A + PRO_B + PRO_C + PRO_D

CATEGORY_ORDER = __import__("nexus.data.spec_base", fromlist=["CATEGORIES"]).CATEGORIES


def validate_specs():
    """Return a list of structural problems (used by admin QA and tests)."""
    problems = []
    slugs, titles = set(), set()
    for s in ALL_SPECS:
        for key in ("slug", "title", "problem", "outcome", "algorithm", "logic"):
            if not s.get(key):
                problems.append(f"{s.get('slug','?')}: missing {key}")
        if s["slug"] in slugs:
            problems.append(f"duplicate slug {s['slug']}")
        if s["title"] in titles:
            problems.append(f"duplicate title {s['title']}")
        slugs.add(s["slug"])
        titles.add(s["title"])
        if len(s.get("tests", [])) < 3:
            problems.append(f"{s['slug']}: fewer than 3 functional tests")
        if len(s.get("fails", [])) < 3:
            problems.append(f"{s['slug']}: fewer than 3 failure modes")
    free = [s for s in ALL_SPECS if s.get("free")]
    if len(free) != 15:
        problems.append(f"expected 15 free projects, found {len(free)}")
    return problems
