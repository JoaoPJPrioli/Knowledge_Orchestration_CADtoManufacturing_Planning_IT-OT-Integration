"""Shared paths for the Revision 3 experiments.

The experiments never modify the pipeline repository. They import its modules
read-only, and any change of behaviour needed for an experiment is applied by
wrapping or monkeypatching inside the experiment process.

Default layout (this repository):

    pipeline/        the orchestration pipeline (final implementation)
    ground_truth/    geometric, drawing, and physical references
    experiments/     this folder

Override the locations with the environment variables JIII_REPO and JIII_GROUNDTRUTH.
"""
import os
import sys

EXP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get(
    "JIII_REPO",
    os.path.normpath(os.path.join(EXP_ROOT, "..", "pipeline")),
)
REPO_SRC = os.path.join(REPO, "src")
RUNS = os.path.join(EXP_ROOT, "runs")
RESULTS = os.path.join(EXP_ROOT, "results")
REFERENCE_RUN = os.path.join(RUNS, "reference")

# Ground-truth references (read-only inputs).
GROUNDTRUTH = os.environ.get(
    "JIII_GROUNDTRUTH",
    os.path.normpath(os.path.join(EXP_ROOT, "..", "ground_truth")),
)


def use_repo():
    """Put the repository's src/ on sys.path (read-only use)."""
    if not os.path.isdir(REPO_SRC):
        raise SystemExit(f"Pipeline repository not found at {REPO!r}; set JIII_REPO.")
    if REPO_SRC not in sys.path:
        sys.path.insert(0, REPO_SRC)
    return REPO_SRC
