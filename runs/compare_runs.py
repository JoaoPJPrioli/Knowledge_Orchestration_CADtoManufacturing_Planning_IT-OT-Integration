"""Compare regenerated pipeline outputs with the archived runs in this folder, ignoring time stamps,
host paths, durations, line endings, and the key order of JSON embedded in strings.

Usage (from the repository root):
    python runs/compare_runs.py runs <folder written by run_all_configurations.py>
"""
import json, os, re, sys
A, B = sys.argv[1], sys.argv[2]
# The only keys that differ between hosts and runs: time stamps, the Java executable, and output paths.
VOLATILE = {"created_at", "timestamp", "simulation_timestamp", "java_exe", "source", "gcode_files"}
def norm(x, key=""):
    if isinstance(x, dict):
        return {k: norm(v, k) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [norm(v, key) for v in x]
    if isinstance(x, str) and x[:1] in "{[":
        try:
            return norm(json.loads(x), key)   # JSON embedded in a string: compare as data, not as text
        except ValueError:
            pass
    if isinstance(x, str):
        x = re.sub(r"[A-Za-z]:\\[^\s\"']*|<repository>[^\s\"']*|/tmp/[^\s\"']*|/home/[^\s\"']*", "<path>", x)
        x = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+Z?|\d{4}-\d\d-\d\d \d\d:\d\d(:\d\d)?", "<ts>", x)
    return x
def first_diff(a, b, p=""):
    if type(a) != type(b): return f"{p}: type {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b: return f"{p}/{k}: missing on one side"
            d = first_diff(a[k], b[k], f"{p}/{k}")
            if d: return d
        return None
    if isinstance(a, list):
        if len(a) != len(b): return f"{p}: length {len(a)} vs {len(b)}"
        for i, (u, v) in enumerate(zip(a, b)):
            d = first_diff(u, v, f"{p}[{i}]")
            if d: return d
        return None
    return None if a == b else f"{p}: {str(a)[:80]!r} vs {str(b)[:80]!r}"
FILES = ["features.json", "manufacturing_plan.json", "expert_validation_requests.json", "ral_refusals.json", "summary.json",
         "provenance_report.json", "parameter_fidelity.json", "dimension_fidelity.json", "envelope_excursions.json",
         "sparql_results.json", "motor_shaft_1001_validation.json", "motor_shaft_1001_simulation.json", "reasoning_report.json"]
bad = 0
for cfg in sorted(d for d in os.listdir(A) if os.path.isdir(os.path.join(A, d))):
    out = []
    for f in FILES:
        pa, pb = os.path.join(A, cfg, f), os.path.join(B, cfg, f)
        if not os.path.exists(pa) or not os.path.exists(pb):
            out.append(f"{f}: missing ({os.path.exists(pa)}, {os.path.exists(pb)})"); continue
        d = first_diff(norm(json.load(open(pa, encoding="utf-8"))), norm(json.load(open(pb, encoding="utf-8"))))
        if d: out.append(f"{f}: {d}")
    na = open(os.path.join(A, cfg, "motor_shaft_1001.nc"), encoding="utf-8", newline=None).read().splitlines()
    nb = open(os.path.join(B, cfg, "motor_shaft_1001.nc"), encoding="utf-8", newline=None).read().splitlines()
    na2 = [l for l in na if not re.search(r"(DATE|TIME|GENERATED|\d{4}-\d\d-\d\d)", l, re.I)]
    nb2 = [l for l in nb if not re.search(r"(DATE|TIME|GENERATED|\d{4}-\d\d-\d\d)", l, re.I)]
    if na2 != nb2:
        diffs = [(i, x, y) for i, (x, y) in enumerate(zip(na2, nb2)) if x != y][:2]
        out.append(f"programme: {len(na2)} vs {len(nb2)} lines; first differences {diffs}")
    print(f"{cfg}: {'identical' if not out else 'DIFFERENT'}")
    for o in out: print("   ", o)
    bad += bool(out)
print("configurations with differences:", bad)
