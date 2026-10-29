"""Run the unmodified pipeline (main.py) into a fresh output directory.

Usage:
    python common/run_pipeline.py reference
    python common/run_pipeline.py <name> [main.py arguments ...]

Each run writes into runs/<name>/ and refuses to reuse an existing directory,
so every run starts from a cleared expert-validation store (the store
persists across runs by design; counts are only comparable from a cleared one).
Requires Java 25 on PATH (Pellet via OWLReady2 0.51).
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.paths import REPO, RUNS  # noqa: E402


def run(name, args=(), runs_dir=RUNS):
    out = os.path.join(runs_dir, name)
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; delete it to re-run from a cleared store")
    os.makedirs(out)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    t0 = time.time()
    p = subprocess.run([sys.executable, "main.py", "--output-dir", out, *args], cwd=REPO,
                       capture_output=True, text=True, input="", env=env,
                       encoding="utf-8", errors="replace")
    wall = time.time() - t0
    with open(os.path.join(out, "run.log"), "w", encoding="utf-8") as fh:
        fh.write(p.stdout + "\n--- STDERR ---\n" + p.stderr)
    meta = {"name": name, "args": list(args), "returncode": p.returncode,
            "wall_clock_s": round(wall, 2),
            "pellet_s": [round(float(x), 2) for x in re.findall(r"Pellet took ([\d.]+)", p.stdout + p.stderr)]}
    with open(os.path.join(out, "run_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    if p.returncode != 0:
        raise SystemExit(f"pipeline run {name} failed (see {out}/run.log)")
    return out, meta


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    print(run(sys.argv[1], sys.argv[2:])[1])
