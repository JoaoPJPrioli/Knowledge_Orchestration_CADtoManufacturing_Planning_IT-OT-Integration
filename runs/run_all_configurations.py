"""Run the eight pipeline configurations reported in the manuscript (Table 10 and Section 5.1),
each in one invocation of main.py into a new folder, so that the expert-validation request counts
always come from a cleared store; then run the pipeline's test suite.

Usage (from the repository root):
    python runs/run_all_configurations.py <output folder>

Requirements: Python 3.12 or 3.13 with pipeline/requirements.txt installed, and OpenJDK 25 as the
`java` on the PATH, or the environment variable SKL_JAVA_EXE set to a Java 25 executable. Under
OpenJDK 21 the reasoner fails with UnsupportedClassVersionError and the pipeline aborts by design.

The folder runs/ next to this script holds the archived outputs of these eight configurations
(reference, four ablations, the second material, the second machine, and the second machine with
the serialisation-profile check disabled), produced by the same commands on the authors' host.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(os.path.dirname(HERE), "pipeline")

CONFIGS = {
    "reference": [],
    "ablation_type_gate": ["--ablation", "type_gate"],
    "ablation_orientation_gate": ["--ablation", "orientation_gate"],
    "ablation_kefc_gate": ["--ablation", "kefc_gate"],
    "ablation_swap_sources": ["--ablation", "swap_sources"],
    "material_aluminum": ["--material", "aluminum_6061"],
    "machine_mill_turn": ["--machine", "cnc_mill_turn"],
    "machine_mill_turn_ablation_serialisation_profile": ["--machine", "cnc_mill_turn", "--ablation", "serialisation_profile"],
}


def main(out_root):
    out_root = os.path.abspath(out_root)
    os.makedirs(out_root, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    timing = {}
    for name, args in CONFIGS.items():
        out = os.path.join(out_root, name)
        if os.path.exists(out):
            raise SystemExit(f"{out} exists; every configuration must run into a new folder (cleared store).")
        os.makedirs(out)
        t0 = time.time()
        p = subprocess.run([sys.executable, "main.py", "--output-dir", out, *args], cwd=PIPELINE, env=env,
                           capture_output=True, text=True, input="", encoding="utf-8", errors="replace")
        wall = time.time() - t0
        with open(os.path.join(out, "run.log"), "w", encoding="utf-8") as fh:
            fh.write(p.stdout + "\n--- STDERR ---\n" + p.stderr)
        timing[name] = {"returncode": p.returncode, "wall_clock_s": round(wall, 2),
                        "pellet_s": [round(float(x), 2) for x in re.findall(r"Pellet took ([\d.]+)", p.stdout + p.stderr)],
                        "args": args}
        print(name, timing[name], flush=True)
        with open(os.path.join(out_root, "timing.json"), "w", encoding="utf-8") as fh:
            json.dump(timing, fh, indent=1)
    t0 = time.time()
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]
    p = subprocess.run(cmd, cwd=PIPELINE, env=env, capture_output=True, text=True, input="",
                       encoding="utf-8", errors="replace")
    with open(os.path.join(out_root, "pytest_pipeline.log"), "w", encoding="utf-8") as fh:
        fh.write(" ".join(cmd[1:]) + "\n" + p.stdout + "\n--- STDERR ---\n" + p.stderr)
    with open(os.path.join(out_root, "pytest_timing.json"), "w", encoding="utf-8") as fh:
        json.dump({"returncode": p.returncode, "wall_clock_s": round(time.time() - t0, 1)}, fh)
    print("pytest", p.returncode, [ln for ln in p.stdout.splitlines() if "passed" in ln or "failed" in ln][-1:], flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
