"""Extra configuration for Reviewer 1, Comment 5 (and Reviewer 2, Comment 2):
read dimensions stated only in a record's free-text description.

Eleven of the 18 serialiser refusals of the reference run concern drawing
records whose dimensions appear only in prose ("a diameter of 24mm (R12) and a
length of 46.5mm"). This configuration fills an EMPTY structured dimension set
from explicit phrases in the description and nothing else: no default, no
unit conversion beyond millimetres, and a record whose phrases disagree
(a diameter and a radius that do not match) is left empty. Every value it
adds is marked with dimensions_source = 'free_text'.

Run as a pipeline configuration (the repository is not modified; the parser
is wrapped in-process before main.py is imported):

    python r1_5_programme_feasibility/free_text_dimensions.py runs/free_text_dimensions
"""
import os
import re
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import REPO, use_repo  # noqa: E402

NUM = r"(\d+(?:\.\d+)?)\s*mm"
PATTERNS = (
    ("Ø", re.compile(r"\bdiameter of\s+" + NUM, re.I)),
    ("R", re.compile(r"\bradius of\s+" + NUM, re.I)),
    ("R", re.compile(r"\(R(\d+(?:\.\d+)?)\)")),
    ("L", re.compile(r"\blength of\s+" + NUM, re.I)),
    ("L", re.compile(NUM + r"\s+long\b", re.I)),
    ("W", re.compile(r"\bwidth of\s+" + NUM, re.I)),
    ("W", re.compile(NUM + r"\s+wide\b", re.I)),
)


def dimensions_from_text(text: str):
    """Explicitly stated dimensions, or {} when none or when they disagree."""
    found = {}
    for key, pat in PATTERNS:
        for m in pat.finditer(text or ""):
            v = float(m.group(1))
            if key in found and abs(found[key] - v) > 1e-9:
                return {}  # two different values for one quantity: do not guess
            found[key] = v
    if "Ø" in found and "R" in found and abs(found["Ø"] - 2 * found["R"]) > 1e-6:
        return {}
    return found


def enrich(records):
    n = 0
    for r in records:
        if not r.get("dimensions"):
            d = dimensions_from_text(r.get("description", ""))
            if d:
                r["dimensions"] = d
                r["dimensions_source"] = "free_text"
                n += 1
    return n


def main(out_dir):
    use_repo()
    import feature_parser
    original = feature_parser.parse_feature_file

    def parse_with_free_text(path):
        recs = original(path)
        enrich(recs)
        return recs
    feature_parser.parse_feature_file = parse_with_free_text
    if os.path.exists(out_dir):
        raise SystemExit(f"{out_dir} exists; delete it to re-run from a cleared store")
    os.makedirs(out_dir)
    out_dir = os.path.abspath(out_dir)
    cwd = os.getcwd()
    os.chdir(REPO)
    sys.argv = ["main.py", "--output-dir", out_dir]
    try:
        runpy.run_path(os.path.join(REPO, "main.py"), run_name="__main__")
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    main(sys.argv[1])
