"""Reviewer 1, Comment 3 (with Reviewer 3, Comment 4): how well do the assigned
confidences predict decision-relevant correctness, and what would a
data-supported confidence look like on this part?

Outcome per reconciled entity: its label induces the operation family that
the physical feature requires (Level M of the Revision 2 audit,
results_v2.json). Compared predictors:
  * policy: the confidence the pipeline assigns (S for merges, 1.0 for
    primary-only, 0.4 for secondary-only);
  * base rate: the leave-one-out rate of correct entities over all entities;
  * empirical class rate, leave-one-out with add-one smoothing,
    c = (k - y + 1) / (n - 1 + 2), for two class definitions: the
    reconciliation class (the policy's own classes) and the set of agents
    that reported the entity (independent of which agent is called primary).

Metrics: Brier score; and at the pipeline's review threshold (0.5), how many
wrong-family entities would be routed to review and how many correct ones.
Both role assignments (reference and swapped) are evaluated.

This is an in-sample probe on 22 entities of one part. Leave-one-out keeps an
entity's own outcome out of its estimate, but it is not an out-of-sample
calibration; that needs repeated extraction runs on further parts.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from common.paths import GROUNDTRUTH, RESULTS  # noqa: E402

THRESHOLD = 0.5


def load(which="two_level"):
    res = json.load(open(os.path.join(GROUNDTRUTH, "results_v2.json"), encoding="utf-8"))
    src = res["two_level"] if which == "reference" else res["swap_sources"]["two_level"]
    out = []
    for e in src["entities"]:
        agents = sorted({s.split(" #")[0] for s in e["sources"]})
        out.append({"id": e["entity_id"], "class": e["reconciliation"], "agents": "+".join(agents),
                    "policy": float(e["confidence"]), "y": 1 if e["M"]["verdict"] == "correct family" else 0})
    return out


def loo(entities, key):
    est = []
    for e in entities:
        same = [x for x in entities if x[key] == e[key] and x is not e]
        k = sum(x["y"] for x in same)
        est.append((k + 1) / (len(same) + 2))
    return est


def base_rate(entities):
    n = len(entities)
    k = sum(e["y"] for e in entities)
    return [(k - e["y"]) / (n - 1) for e in entities]


def brier(p, y):
    return sum((a - b) ** 2 for a, b in zip(p, y)) / len(y)


def routing(p, y):
    review = [i for i, v in enumerate(p) if v < THRESHOLD]
    wrong = [i for i, v in enumerate(y) if v == 0]
    return {"reviewed": len(review), "wrong_entities": len(wrong),
            "wrong_routed_to_review": sum(1 for i in review if y[i] == 0),
            "correct_routed_to_review": sum(1 for i in review if y[i] == 1)}


def evaluate(entities):
    y = [e["y"] for e in entities]
    preds = {"policy": [e["policy"] for e in entities], "base_rate_loo": base_rate(entities),
             "reconciliation_class_loo": loo(entities, "class"), "agent_set_loo": loo(entities, "agents")}
    return {"entities": len(entities), "correct": sum(y),
            "predictors": {k: {"brier": round(brier(v, y), 4), "routing": routing(v, y),
                               "range": [round(min(v), 3), round(max(v), 3)]} for k, v in preds.items()},
            "per_entity": [{**e, **{k: round(v[i], 3) for k, v in preds.items()}} for i, e in enumerate(entities)]}


def main():
    res = {"reference": evaluate(load("reference")), "swapped_roles": evaluate(load("swap"))}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "r1_3_calibration_probe.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    L = ["# R1-3: confidence against decision-relevant correctness (in-sample probe, 22 entities)", "",
         "| Roles | Predictor | Brier | Range | Reviewed at c < 0.5 | Wrong routed to review | Correct routed to review |",
         "|---|---|---|---|---|---|---|"]
    for roles, r in res.items():
        for k, v in r["predictors"].items():
            ro = v["routing"]
            L.append(f"| {roles} | {k} | {v['brier']:.3f} | {v['range'][0]} to {v['range'][1]} | {ro['reviewed']} | "
                     f"{ro['wrong_routed_to_review']} of {ro['wrong_entities']} | {ro['correct_routed_to_review']} |")
    with open(os.path.join(RESULTS, "r1_3_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return res


if __name__ == "__main__":
    main()
    print(open(os.path.join(RESULTS, "r1_3_summary.md"), encoding="utf-8").read())
