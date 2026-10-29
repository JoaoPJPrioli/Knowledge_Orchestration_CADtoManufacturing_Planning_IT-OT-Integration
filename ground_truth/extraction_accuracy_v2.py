"""
Extraction and reconciliation accuracy, revision 2: two conventions, two levels.
===============================================================================
Evaluation only. Copy of analysis/extraction_accuracy.py (R1) extended.

(a) R1 convention, unchanged code (function ``r1_main``, verbatim from R1), run
    against the corrected references: step_reference_v2.json (R01 to R10
    identical to R1; the key additionally carries its end-radius anchors, which
    the R1 ``anchors`` function ignores) and drawing_reference_v2.json (D04
    corrected, D06 now dimensioned and therefore no longer implicit).

(b) Two-level audit.
    Level G, geometric grounding. A STEP-derived record is grounded when its
    absolute location lies within MAX_DIST = 10 mm of an anchor of a B-Rep
    feature and, where the record states a diameter, that diameter agrees within
    10 % with the diameter attached to the anchor (feature diameter; key width
    for the key centre and top face; 2 x end radius for the key end-radius
    axes). Anchors: feature centre, axial ends (turned and drilled features),
    key centre, key top-face centre (y = 15), and the two key end-radius axis
    points on the top plane (0, 15, 127.5) and (0, 15, 159.5). Among admissible
    anchors the match minimises d + |dD| + |dL|; the label does not enter the
    match. Drawing-derived records carry no frame and are grounded frame-free:
    the drawing feature with the most dimensioned values (diameter, small
    diameter, width, length, end radius, end-centre distance, height, height
    above chord) present in the record wins, ties broken by label tier then
    reference order; with no dimensional hit the R1 drawing rule applies.
    The label is then scored exact / same-family / other-family with the
    pipeline's own type-similarity tiers (feature_parser.calculate_type_
    similarity: 1.0 exact, 0.7 same family, otherwise other), extended by one
    geometric equivalence (Boss ~ Key: the B-Rep key is a raised boss).
    Level M, operation-family correctness for the physical part
    (physical_reference.json: IEC 60072-1 frame-90 D-end with milled keyway
    and M8 centre thread). Each label maps to the operation families its
    feature-to-operation SWRL rules assert (parsed from machining_rules.swrl).
    A grounded record or entity is correct when its label's families contain
    the family the physical feature requires, wrong otherwise; an ungrounded
    one is "no such feature". A plan step is correct when its operation is the
    required family, or an auxiliary family of that feature while the entity's
    label also yields the required family.

Usage:
    python extraction_accuracy_v2.py <repo_dir> <run_output_dir> step_reference_v2.json \
        drawing_reference_v2.json physical_reference.json <out.json> [<swap_run_dir>]
"""
import contextlib
import io
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(sys.argv[1], "src"))
from feature_parser import parse_feature_file  # noqa: E402

STEP_FILES = ["features_eixo_step_Gemini31Pro.txt", "features_eixo_step_Gemini35flash.txt"]
DRAW_FILES = ["draw_features_eixo_Gemini31Pro.txt", "draw_features_eixo_Gemini35flash.txt"]
AGENT = {STEP_FILES[0]: "STEP-A (primary)", STEP_FILES[1]: "STEP-B (secondary)",
         DRAW_FILES[0]: "DRW-A (primary)", DRAW_FILES[1]: "DRW-B (secondary)"}

SYNONYMS = {"step": {"step", "cylinder"}, "cylinder": {"step", "cylinder"}}
# related labels: same physical feature, different operation family
RELATED = {("boss", "key"), ("hole", "blind hole"), ("hole", "counterbore"), ("hole", "chamfer"),
           ("bore", "blind hole"), ("bore", "counterbore"), ("bore", "chamfer"), ("bore", "hole"),
           ("through hole", "blind hole"), ("through hole", "hole"), ("blind hole", "hole")}
MAX_DIST = 10.0


def type_rank(label, ref):
    a, b = label.lower(), ref["type"].lower()
    aliases = {x.lower() for x in ref.get("aliases", [])}
    if a == b or a in aliases or b in SYNONYMS.get(a, set()):
        return 0
    if (a, b) in RELATED or (b, a) in RELATED:
        return 1
    return 2


def rec_diameter(rec):
    d = rec.get("dimensions", {})
    if "Ø" in d:
        return float(d["Ø"])
    if "R" in d:
        return 2 * float(d["R"])
    return None


def rec_length(rec):
    d = rec.get("dimensions", {})
    return float(d["L"]) if "L" in d else None


def anchors(ref):
    c = ref["centre"]
    pts = [tuple(c)]
    if "z_min" in ref and ref["type"] != "Key":
        pts.append((0.0, 0.0, ref["z_max"]))
        pts.append((0.0, 0.0, ref["z_min"]))
    if ref["type"] == "Key":
        pts.append((c[0], ref["y_max"], c[2]))
    return pts


def dist(p, q):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))


def loc(rec):
    l = rec.get("absolute_location", {})
    return (float(l.get("X", 0)), float(l.get("Y", 0)), float(l.get("Z", 0)))


def match_step_record(rec, refs):
    best = None
    for ref in refs:
        rank = type_rank(rec["type"], ref)
        d_centre = dist(loc(rec), tuple(ref["centre"]))
        d = min(dist(loc(rec), a) for a in anchors(ref))
        if d > MAX_DIST:
            continue
        dD = None
        if rec_diameter(rec) is not None and ref.get("diameter") is not None:
            dD = abs(rec_diameter(rec) - ref["diameter"])
        dL = None
        if rec_length(rec) is not None and ref.get("length") is not None:
            dL = abs(rec_length(rec) - ref["length"])
        if rank == 2:
            ok_d = dD is not None and dD <= 0.1 * ref["diameter"]
            ok_l = dL is None or dL <= 0.5 * ref["length"]
            if not (ok_d and ok_l):
                continue
        cost = d + (dD or 0.0) + (dL or 0.0) + 5 * rank
        cand = dict(ref_id=ref["ref_id"], ref_type=ref["type"], type_rank=rank,
                    distance_to_centre=round(d_centre, 3), distance_to_nearest_anchor=round(d, 3),
                    diameter_error=None if dD is None else round(dD, 3),
                    length_error=None if dL is None else round(dL, 3), cost=cost)
        if best is None or cost < best["cost"]:
            best = cand
    return best


def numbers_in(text):
    return [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)", text)]


def match_drawing_record(rec, refs):
    nums = numbers_in(rec.get("description", ""))
    for v in rec.get("dimensions", {}).values():
        if isinstance(v, (int, float)):
            nums.append(float(v))
    desc = rec.get("description", "")
    radii = [float(x) for x in re.findall(r"R\s?(\d+(?:\.\d+)?)", desc)]
    radii += [float(x) for x in re.findall(r"radius of (\d+(?:\.\d+)?)", desc)]
    nums += [2 * r for r in radii]

    def has(v):
        return v is not None and any(abs(n - v) < 0.051 for n in nums)

    cands = [r for r in refs if type_rank(rec["type"], r) <= 1 and not r.get("implicit")]
    scored = []
    for r in cands:
        hits = sum(1 for key in ("diameter", "width", "length") if has(r.get(key)))
        scored.append((type_rank(rec["type"], r), -hits, r))
    scored.sort(key=lambda t: (t[0], t[1]))
    if not scored:
        return None
    rank, neg_hits, r = scored[0]
    if -neg_hits == 0 and len(cands) > 1:
        # several type-compatible candidates and no dimensional evidence: unmatched
        return None
    covered = [c["ref_id"] for c in cands if c is not r and type_rank(rec["type"], c) <= 1
               and any(has(c.get(k)) for k in ("diameter", "width", "length")) and c["ref_id"][:3] == r["ref_id"][:3]]
    errors = {}
    for key in ("diameter", "width", "length"):
        if r.get(key) is None:
            continue
        stated = None
        # the stated value is the number of that kind in the description, if any
        if key == "diameter" and radii:
            stated = 2 * radii[0]
        elif key == "diameter":
            m = re.search(r"diameter of (\d+(?:\.\d+)?)", rec.get("description", ""))
            stated = float(m.group(1)) if m else None
        elif key == "width":
            m = re.search(r"(\d+(?:\.\d+)?)\s?mm wide|width of (\d+(?:\.\d+)?)", rec.get("description", ""))
            stated = float(m.group(1) or m.group(2)) if m else None
        elif key == "length":
            m = re.search(r"length of (\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s?mm long", rec.get("description", ""))
            stated = float(m.group(1) or m.group(2)) if m else None
        if stated is not None:
            errors[key] = round(abs(stated - r[key]), 3)
    return dict(ref_id=r["ref_id"], ref_type=r["type"], type_rank=rank, covered=covered, stated_errors=errors)


def r1_main(repo, run_out, step_ref_path, draw_ref_path, out=None):
    step_refs = json.load(open(step_ref_path))["features"]
    draw_refs = json.load(open(draw_ref_path))["features"]
    data_dir = os.path.join(repo, "data", "motor_data")

    records = []
    for fname in STEP_FILES + DRAW_FILES:
        for rec in parse_feature_file(os.path.join(data_dir, fname)):
            rec["source_file"] = fname
            rec["agent"] = AGENT[fname]
            rec["family"] = "STEP" if fname in STEP_FILES else "DRAWING"
            refs = step_refs if rec["family"] == "STEP" else draw_refs
            m = match_step_record(rec, refs) if rec["family"] == "STEP" else match_drawing_record(rec, refs)
            rec["match"] = m
            records.append(rec)

    # ---- per-agent metrics ---------------------------------------------
    per_agent = {}
    for fname in STEP_FILES + DRAW_FILES:
        recs = [r for r in records if r["source_file"] == fname]
        refs = step_refs if fname in STEP_FILES else [r for r in draw_refs if not r.get("implicit")]
        matched = [r for r in recs if r["match"]]
        found = set()
        for r in matched:
            found.add(r["match"]["ref_id"])
            found.update(r["match"].get("covered", []))
        entry = {
            "agent": AGENT[fname], "records": len(recs), "denote_real_feature": len(matched),
            "false_positives": len(recs) - len(matched),
            "type_exact": sum(1 for r in matched if r["match"]["type_rank"] == 0),
            "type_related_other_operation": sum(1 for r in matched if r["match"]["type_rank"] == 1),
            "type_wrong": sum(1 for r in matched if r["match"]["type_rank"] == 2),
            "reference_features": len(refs), "reference_found": len(found),
            "precision": round(len(matched) / len(recs), 3) if recs else None,
            "recall": round(len(found) / len(refs), 3) if refs else None,
        }
        if fname in STEP_FILES:
            dc = [r["match"]["distance_to_centre"] for r in matched]
            da = [r["match"]["distance_to_nearest_anchor"] for r in matched]
            dD = [r["match"]["diameter_error"] for r in matched if r["match"]["diameter_error"] is not None]
            dL = [r["match"]["length_error"] for r in matched if r["match"]["length_error"] is not None]
            entry.update({
                "pos_error_centre_mm": {"mean": round(sum(dc) / len(dc), 2), "median": round(sorted(dc)[len(dc) // 2], 2), "max": round(max(dc), 2)} if dc else None,
                "pos_error_anchor_mm": {"mean": round(sum(da) / len(da), 2), "median": round(sorted(da)[len(da) // 2], 2), "max": round(max(da), 2)} if da else None,
                "diameter_error_mm": {"n": len(dD), "mean": round(sum(dD) / len(dD), 3), "max": round(max(dD), 3)} if dD else None,
                "length_error_mm": {"n": len(dL), "mean": round(sum(dL) / len(dL), 3), "max": round(max(dL), 3)} if dL else None,
            })
        per_agent[fname] = entry

    # ---- reconciled entities -------------------------------------------
    feats = json.load(open(os.path.join(run_out, "features.json")))
    plan = json.load(open(os.path.join(run_out, "manufacturing_plan.json")))
    by_key = {(r["source_file"], r["id"]): r for r in records}

    def src_records(e):
        if e.get("reconciliation") == "merged":
            p, s = e["source_primary"], e["source_secondary"]
            return [by_key[(p["source_file"], p["source_id"])], by_key[(s["source_file"], s["source_id"])]]
        return [by_key[(e["source_file"], e["source_id"])]]

    entities = []
    for e in feats:
        srcs = src_records(e)
        matches = [r["match"] for r in srcs]
        real = any(m for m in matches)
        ref_ids = sorted({m["ref_id"] for m in matches if m})
        # an entity denotes a real feature if any of its sources does; its type is
        # the primary label, scored against the primary source's match (or any)
        primary_match = matches[0] if matches[0] else (matches[1] if len(matches) > 1 else None)
        ent = {
            "entity_id": e["id"], "type": e["type"], "reconciliation": e["reconciliation"],
            "confidence": round(e.get("match_confidence", 0), 3), "sources": [(r["source_file"], r["id"], r["type"]) for r in srcs],
            "denotes_real_feature": real, "reference": ref_ids,
            "type_rank": primary_match["type_rank"] if primary_match else None,
            "partner_sources_disagree": (e.get("reconciliation") == "merged" and
                                         ((matches[0] is None) != (matches[1] is None) or
                                          (matches[0] and matches[1] and matches[0]["ref_id"] != matches[1]["ref_id"]))),
        }
        # attribute corruption in merged entities: compare merged Z and L against the reference
        if e.get("reconciliation") == "merged" and primary_match and e.get("absolute_location"):
            ref = next((r for r in step_refs + draw_refs if r["ref_id"] == primary_match["ref_id"]), None)
            if ref and "centre" in ref:
                ent["merged_distance_to_nearest_anchor"] = round(min(dist(loc(e), a) for a in anchors(ref)), 3)
                ent["primary_distance_to_nearest_anchor"] = round(min(dist(loc(srcs[0]), a) for a in anchors(ref)), 3)
            if ref and ref.get("length") is not None and rec_length(e) is not None:
                ent["merged_length_error"] = round(abs(rec_length(e) - ref["length"]), 3)
                ent["primary_length_error"] = None if rec_length(srcs[0]) is None else round(abs(rec_length(srcs[0]) - ref["length"]), 3)
        entities.append(ent)

    per_class = {}
    for cls in ("merged", "primary_only", "secondary_only"):
        es = [x for x in entities if x["reconciliation"] == cls]
        per_class[cls] = {
            "entities": len(es), "denote_real_feature": sum(1 for x in es if x["denotes_real_feature"]),
            "type_exact": sum(1 for x in es if x["type_rank"] == 0),
            "type_related_other_operation": sum(1 for x in es if x["type_rank"] == 1),
            "type_wrong": sum(1 for x in es if x["type_rank"] == 2),
            "policy_confidence": {"merged": "S", "primary_only": 1.0, "secondary_only": 0.4}[cls],
            "observed_existence_rate": round(sum(1 for x in es if x["denotes_real_feature"]) / len(es), 3) if es else None,
            "mean_assigned_confidence": round(sum(x["confidence"] for x in es) / len(es), 3) if es else None,
        }

    # ---- consequences in the plan --------------------------------------
    ent_by_id = {x["entity_id"]: x for x in entities}
    step_rows = []
    for s in plan:
        ent = ent_by_id[s["feature_id"]]
        step_rows.append({
            "step": s["step_number"], "feature_id": s["feature_id"], "feature_type": s["feature_type"],
            "operation": s["operation"], "status": s["validation_status"],
            "feature_denotes_real_feature": ent["denotes_real_feature"], "feature_type_rank": ent["type_rank"],
        })
    approved = [r for r in step_rows if r["status"] in ("auto_approved", "expert_approved")]
    withheld = [r for r in step_rows if r["status"] == "requires_review"]
    plan_summary = {
        "steps": len(step_rows), "approved": len(approved), "withheld": len(withheld),
        "approved_steps_on_nonexistent_features": [r["step"] for r in approved if not r["feature_denotes_real_feature"]],
        "approved_steps_on_mistyped_features": [r["step"] for r in approved if r["feature_denotes_real_feature"] and r["feature_type_rank"] in (1, 2)],
        "withheld_steps_on_nonexistent_features": [r["step"] for r in withheld if not r["feature_denotes_real_feature"]],
        "withheld_steps_on_real_features": [r["step"] for r in withheld if r["feature_denotes_real_feature"]],
    }

    result = {"records": records, "per_agent": per_agent, "entities": entities,
              "per_reconciliation_class": per_class, "plan": plan_summary, "plan_steps": step_rows}
    if out:
        json.dump(result, open(out, "w"), indent=2, ensure_ascii=False, default=str)
    _ret = result

    # ---- console report -------------------------------------------------
    print("=== raw records ===")
    for r in records:
        m = r["match"]
        if m is None:
            print(f"{r['agent']:18s} #{r['id']:<2d} {r['type']:13s} -> FALSE POSITIVE (no reference feature)")
        elif r["family"] == "STEP":
            print(f"{r['agent']:18s} #{r['id']:<2d} {r['type']:13s} -> {m['ref_id']} {m['ref_type']:12s} rank={m['type_rank']} "
                  f"d_centre={m['distance_to_centre']:6.2f} d_anchor={m['distance_to_nearest_anchor']:6.2f} "
                  f"dD={m['diameter_error']} dL={m['length_error']}")
        else:
            print(f"{r['agent']:18s} #{r['id']:<2d} {r['type']:13s} -> {m['ref_id']} {m['ref_type']:12s} rank={m['type_rank']} "
                  f"covers={m['covered']} stated_errors={m['stated_errors']}")
    print("\n=== per agent ===")
    for k, v in per_agent.items():
        print(json.dumps(v))
    print("\n=== reconciled entities ===")
    for x in entities:
        print(x)
    print("\n=== per reconciliation class ===")
    print(json.dumps(per_class, indent=1))
    print("\n=== plan consequences ===")
    print(json.dumps(plan_summary, indent=1))
    return _ret


from feature_parser import calculate_type_similarity  # noqa: E402

G_EXTRA_SAME = {("boss", "key")}
DVALS = ("diameter", "diameter_small", "width", "length", "end_radius", "end_centre_distance",
         "height", "height_above_chord")
TIER_RANK = {"exact": 0, "same-family": 1, "other-family": 2}
OPFAM = {"RoughTurningOp": "turning", "FinishTurningOp": "turning", "FacingOp": "facing",
         "DrillingOp": "drilling", "BoringOp": "boring", "CounterboringOp": "counterboring",
         "ChamferingOp": "chamfering", "GroovingOp": "grooving", "MillingOp": "milling"}
CLASS_LABEL = {"Step": "step", "Cylinder": "cylinder", "ChamferFeature": "chamfer", "BlindHole": "blind hole",
               "HoleFeature": "hole", "Bore": "bore", "Counterbore": "counterbore", "Boss": "boss",
               "ThroughHole": "through hole", "Slot": "slot", "Groove": "groove", "KeyFeature": "key"}


def label_ops(swrl_path):
    ops = {}
    for line in open(swrl_path, encoding="utf-8"):
        m = re.match(r"\s*(\w+):\s*(\w+)\(\?f\)\s*->\s*requiresOperation\(\?f,\s*(\w+)\)", line)
        if m:
            ops.setdefault(CLASS_LABEL[m.group(2)], set()).add(OPFAM[m.group(3)])
    return ops


def g_tier(label, ref_type):
    a, b = label.lower(), ref_type.lower()
    if a == b:
        return "exact"
    t = calculate_type_similarity(label, ref_type)
    if t >= 1.0:
        return "exact"
    if t >= 0.7 or (a, b) in G_EXTRA_SAME or (b, a) in G_EXTRA_SAME:
        return "same-family"
    return "other-family"


def g_anchors(ref):
    c = tuple(ref["centre"])
    if ref["type"] == "Key":
        pts = [("key centre", c, ref["width"]), ("key top face", (c[0], ref["y_max"], c[2]), ref["width"])]
        for e in ref["end_cylinders"]:
            pts.append((f"key end-radius axis z={e['z']}", tuple(e["anchor_top"]), 2 * e["radius"]))
        return pts
    pts = [("centre", c, ref.get("diameter"))]
    if "z_min" in ref:
        pts += [("z_max", (0.0, 0.0, ref["z_max"]), ref.get("diameter")),
                ("z_min", (0.0, 0.0, ref["z_min"]), ref.get("diameter"))]
    return pts


def rec_width(rec):
    d = rec.get("dimensions", {})
    return float(d["W"]) if "W" in d else None


def g_match_step(rec, refs):
    best = None
    D, L = rec_diameter(rec), rec_length(rec)
    for ref in refs:
        for name, p, aD in g_anchors(ref):
            d = dist(loc(rec), p)
            if d > MAX_DIST:
                continue
            dD = abs(D - aD) if (D is not None and aD is not None) else None
            if dD is not None and dD > 0.1 * aD:
                continue
            refL = ref.get("length") if not name.startswith("key end") else None
            dL = abs(L - refL) if (L is not None and refL is not None) else None
            cost = d + (dD or 0.0) + (dL or 0.0)
            if best is None or cost < best["cost"]:
                W = rec_width(rec)
                best = dict(ref_id=ref["ref_id"], ref_type=ref["type"], anchor=name,
                            distance_to_anchor=round(d, 3), distance_to_centre=round(dist(loc(rec), tuple(ref["centre"])), 3),
                            diameter_error=None if dD is None else round(dD, 3),
                            length_error=None if dL is None else round(dL, 3),
                            length_consistent=None if dL is None else dL <= 0.5 * refL,
                            width_error=None if (W is None or ref.get("width") is None) else round(abs(W - ref["width"]), 3),
                            cost=round(cost, 3), tier=g_tier(rec["type"], ref["type"]))
    return best


def _numbers(rec):
    desc = rec.get("description", "")
    nums = numbers_in(desc)
    for v in rec.get("dimensions", {}).values():
        if isinstance(v, (int, float)):
            nums.append(float(v))
    radii = [float(x) for x in re.findall(r"R\s?(\d+(?:\.\d+)?)", desc)]
    radii += [float(x) for x in re.findall(r"radius of (\d+(?:\.\d+)?)", desc)]
    return nums + [2 * r for r in radii], radii


def _stated(rec, key):
    desc = rec.get("description", "")
    _, radii = _numbers(rec)
    pats = {"diameter": r"diameter of (\d+(?:\.\d+)?)",
            "width": r"(\d+(?:\.\d+)?)\s?mm wide|width of (\d+(?:\.\d+)?)",
            "length": r"length of (\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s?mm long",
            "height": r"height of (\d+(?:\.\d+)?)|protruding (\d+(?:\.\d+)?)\s?mm"}
    if key == "diameter" and radii:
        return 2 * radii[0]
    m = re.search(pats[key], desc)
    if not m:
        return None
    return float(next(g for g in m.groups() if g))


def g_match_drawing(rec, refs, r1_match):
    nums, _ = _numbers(rec)

    def has(v):
        return v is not None and any(abs(n - v) < 0.051 for n in nums)
    live = [r for r in refs if not r.get("implicit")]
    scored = []
    for i, r in enumerate(live):
        hits = [k for k in DVALS if has(r.get(k))]
        scored.append((-len(hits), TIER_RANK[g_tier(rec["type"], r["type"])], i, r, hits))
    scored.sort(key=lambda t: t[:3])
    neg, _, _, r, hits = scored[0]
    rule = "dimensional evidence"
    if neg == 0:
        if not r1_match:
            return None
        r = next(x for x in live if x["ref_id"] == r1_match["ref_id"])
        hits, rule = [], "R1 rule (single type-compatible candidate, no dimensional evidence)"
    covered = [s[3]["ref_id"] for s in scored if s[3] is not r and s[0] == neg and neg < 0
               and s[3]["ref_id"][:3] == r["ref_id"][:3]]
    errors, transcribed = {}, {}
    for key in ("diameter", "width", "length", "height"):
        if r.get(key) is None:
            continue
        st = _stated(rec, key)
        if st is None:
            continue
        errors[key] = round(abs(st - r[key]), 3)
        if errors[key] > 0.051:
            # value copied from another dimension of the same feature, assigned to the wrong quantity
            src = [k for k in DVALS if r.get(k) is not None and abs(r[k] - st) < 0.051]
            if src:
                transcribed[key] = {"stated": st, "is_drawn_value_of": src}
    return dict(ref_id=r["ref_id"], ref_type=r["type"], hits=hits, rule=rule, covered=covered,
                stated_errors=errors, transcribed_misassigned=transcribed, tier=g_tier(rec["type"], r["type"]))


def stats(v, nd=2):
    return {"n": len(v), "mean": round(sum(v) / len(v), nd), "max": round(max(v), nd)} if v else None


def m_verdict(label, ref_id, phys_of, ops):
    if ref_id is None:
        return dict(verdict="no such feature", phys_id=None, label_ops=sorted(ops.get(label.lower(), [])))
    p = phys_of[ref_id]
    lo = ops.get(label.lower(), set())
    req = set(p["required"])
    v = "correct family" if req <= lo else "wrong family"
    return dict(verdict=v, phys_id=p["phys_id"], required=sorted(req), label_ops=sorted(lo),
                extra_ops=sorted(lo - req - set(p["auxiliary"])))


def two_level(repo, run_out, step_refs, draw_refs, phys, ops, r1res):
    phys_of = {}
    for p in phys["features"]:
        for rid in p["brep"] + p["drawing"]:
            phys_of[rid] = p
    data_dir = os.path.join(repo, "data", "motor_data")
    r1rec = {(r["source_file"], r["id"]): r for r in r1res["records"]}
    records = []
    for fname in STEP_FILES + DRAW_FILES:
        for rec in parse_feature_file(os.path.join(data_dir, fname)):
            rec["source_file"], rec["agent"] = fname, AGENT[fname]
            rec["family"] = "STEP" if fname in STEP_FILES else "DRAWING"
            r1m = r1rec[(fname, rec["id"])]["match"]
            rec["r1_match"] = r1m
            g = g_match_step(rec, step_refs) if rec["family"] == "STEP" else g_match_drawing(rec, draw_refs, r1m)
            rec["G"] = g
            rec["M"] = m_verdict(rec["type"], g["ref_id"] if g else None, phys_of, ops)
            records.append(rec)

    per_agent = {}
    for fname in STEP_FILES + DRAW_FILES:
        recs = [r for r in records if r["source_file"] == fname]
        refs = step_refs if fname in STEP_FILES else [r for r in draw_refs if not r.get("implicit")]
        g = [r for r in recs if r["G"]]
        foundG = set()
        for r in g:
            foundG.add(r["G"]["ref_id"]); foundG.update(r["G"].get("covered", []))
        mcorrect = [r for r in recs if r["M"]["verdict"] == "correct family"]
        physM = set()
        for r in mcorrect:
            physM.add(r["M"]["phys_id"])
            for c in r["G"].get("covered", []):
                pc = phys_of[c]
                if set(pc["required"]) <= ops.get(r["type"].lower(), set()):
                    physM.add(pc["phys_id"])
        nphys = len([p for p in phys["features"] if (p["brep"] if fname in STEP_FILES else p["drawing"])])
        e = {"agent": AGENT[fname], "records": len(recs), "G_grounded": len(g), "G_ungrounded": len(recs) - len(g),
             "G_precision": round(len(g) / len(recs), 3),
             "G_tier_exact": sum(r["G"]["tier"] == "exact" for r in g),
             "G_tier_same_family": sum(r["G"]["tier"] == "same-family" for r in g),
             "G_tier_other_family": sum(r["G"]["tier"] == "other-family" for r in g),
             "G_reference_features": len(refs), "G_reference_found": len(foundG), "G_recall": round(len(foundG) / len(refs), 3),
             "M_correct_family": len(mcorrect), "M_wrong_family": sum(r["M"]["verdict"] == "wrong family" for r in recs),
             "M_no_such_feature": sum(r["M"]["verdict"] == "no such feature" for r in recs),
             "M_precision": round(len(mcorrect) / len(recs), 3),
             "M_physical_features_covered_correct_family": sorted(physM),
             "M_physical_recall": f"{len(physM)} of {nphys} ({nphys} physical features with a counterpart in this source family; P07d thread has none)",
             "M_physical_recall_value": round(len(physM) / nphys, 3)}
        if fname in STEP_FILES:
            e["pos_error_anchor_mm"] = stats([r["G"]["distance_to_anchor"] for r in g])
            e["pos_error_centre_mm"] = stats([r["G"]["distance_to_centre"] for r in g])
            e["diameter_error_mm"] = stats([r["G"]["diameter_error"] for r in g if r["G"]["diameter_error"] is not None], 3)
            e["length_error_mm"] = stats([r["G"]["length_error"] for r in g if r["G"]["length_error"] is not None], 3)
            e["length_inconsistent_records"] = [r["id"] for r in g if r["G"]["length_consistent"] is False]
        else:
            errs = [(r["id"], k, v) for r in g for k, v in r["G"]["stated_errors"].items() if v > 0.051]
            e["stated_dimension_errors"] = errs
            e["transcribed_but_misassigned"] = [(r["id"], r["G"]["transcribed_misassigned"]) for r in g if r["G"]["transcribed_misassigned"]]
        per_agent[fname] = e

    feats = json.load(open(os.path.join(run_out, "features.json"), encoding="utf-8"))
    plan = json.load(open(os.path.join(run_out, "manufacturing_plan.json"), encoding="utf-8"))
    by_key = {(r["source_file"], r["id"]): r for r in records}
    r1ent = {x["entity_id"]: x for x in r1res["entities"]}

    def srcs_of(e):
        if e.get("reconciliation") == "merged":
            p, s = e["source_primary"], e["source_secondary"]
            return [by_key[(p["source_file"], p["source_id"])], by_key[(s["source_file"], s["source_id"])]]
        return [by_key[(e["source_file"], e["source_id"])]]

    ref_by_id = {r["ref_id"]: r for r in step_refs + draw_refs}
    entities = []
    for e in feats:
        ss = srcs_of(e)
        gm = next((s["G"] for s in ss if s["G"]), None)
        fam = ss[0]["family"]
        ent = {"entity_id": e["id"], "type": e["type"], "family": fam, "reconciliation": e["reconciliation"],
               "confidence": round(e.get("match_confidence", 0), 3),
               "sources": [f'{s["agent"].split()[0]} #{s["id"]} {s["type"]}' for s in ss],
               "R1_denotes_real_feature": r1ent[e["id"]]["denotes_real_feature"],
               "R1_type_rank": r1ent[e["id"]]["type_rank"],
               "G_grounded": gm is not None, "G_ref": gm["ref_id"] if gm else None,
               "G_anchor": gm.get("anchor") if gm else None,
               "G_tier": g_tier(e["type"], gm["ref_type"]) if gm else None}
        ent["M"] = m_verdict(e["type"], ent["G_ref"], phys_of, ops)
        if e["reconciliation"] == "merged":
            ent["merge_partner_refs"] = [s["G"]["ref_id"] if s["G"] else None for s in ss]
            if fam == "STEP" and gm:
                ref = ref_by_id[gm["ref_id"]]
                anc = [p for _, p, _ in g_anchors(ref)]
                ent["attribute_audit"] = {
                    "primary_location": list(loc(ss[0])), "secondary_location": list(loc(ss[1])), "merged_location": list(loc(e)),
                    "primary_distance_to_anchor": round(min(dist(loc(ss[0]), a) for a in anc), 3),
                    "merged_distance_to_anchor": round(min(dist(loc(e), a) for a in anc), 3),
                    "reference_length": ref.get("length"),
                    "primary_length": rec_length(ss[0]), "secondary_length": rec_length(ss[1]), "merged_length": rec_length(e),
                    "primary_length_error": None if rec_length(ss[0]) is None or ref.get("length") is None else round(abs(rec_length(ss[0]) - ref["length"]), 3),
                    "merged_length_error": None if rec_length(e) is None or ref.get("length") is None else round(abs(rec_length(e) - ref["length"]), 3),
                    "secondary_grounded_to": ss[1]["G"]["ref_id"] if ss[1]["G"] else None}
        entities.append(ent)

    # duplicate flags: physical feature already covered by another entity
    phys_step_family = {x["M"]["phys_id"] for x in entities if x["family"] == "STEP" and x["M"]["phys_id"]}
    first_in_family = {}
    for x in sorted(entities, key=lambda t: t["entity_id"]):
        k = (x["family"], x["M"]["phys_id"])
        x["duplicate_of_entity_same_family"] = first_in_family.get(k) if x["M"]["phys_id"] else None
        first_in_family.setdefault(k, x["entity_id"])
        x["duplicates_STEP_family"] = x["family"] == "DRAWING" and x["M"]["phys_id"] in phys_step_family

    classes = {}
    for cls in ("merged", "primary_only", "secondary_only"):
        es = [x for x in entities if x["reconciliation"] == cls]
        n = len(es)
        classes[cls] = {"entities": n, "assigned_confidence": {"merged": "S", "primary_only": 1.0, "secondary_only": 0.4}[cls],
                        "mean_assigned_confidence": round(sum(x["confidence"] for x in es) / n, 3),
                        "R1_existence": sum(x["R1_denotes_real_feature"] for x in es),
                        "G_grounded": sum(x["G_grounded"] for x in es),
                        "G_grounded_exact_label": sum(x["G_tier"] == "exact" for x in es),
                        "M_correct_family": sum(x["M"]["verdict"] == "correct family" for x in es),
                        "entity_ids_M_wrong": [x["entity_id"] for x in es if x["M"]["verdict"] != "correct family"]}
        for k in ("R1_existence", "G_grounded", "G_grounded_exact_label", "M_correct_family"):
            classes[cls][k + "_rate"] = round(classes[cls][k] / n, 3)
    ordering = {}
    for k in ("R1_existence_rate", "G_grounded_rate", "G_grounded_exact_label_rate", "M_correct_family_rate"):
        p, s = classes["primary_only"][k], classes["secondary_only"][k]
        ordering[k] = {"primary_only": p, "secondary_only": s, "merged": classes["merged"][k],
                       "primary_over_secondary": "supported" if p > s else ("not supported (tied)" if p == s else "reversed")}

    ent_by = {x["entity_id"]: x for x in entities}
    steps = []
    for s in plan:
        x = ent_by[s["feature_id"]]
        op = s["operation"]
        fam_op = {"rough_turning": "turning", "finish_turning": "turning"}.get(op, op)
        if not x["G_grounded"]:
            mv = "no such feature"
        else:
            p = phys_of[x["G_ref"]]
            req = set(p["required"])
            if fam_op in req:
                mv = "correct family"
            elif fam_op in p["auxiliary"] and req <= ops.get(x["type"].lower(), set()):
                mv = "correct family"
            else:
                mv = "wrong family"
        steps.append({"step": s["step_number"], "entity": x["entity_id"], "label": x["type"], "family": x["family"],
                      "operation": op, "operation_rule": s.get("operation_selection_rule_id"),
                      "tool_rule": s.get("tool_selection_rule_id"), "status": s["validation_status"],
                      "approved": s["validation_status"] in ("auto_approved", "expert_approved"),
                      "R1_verdict": ("phantom" if not x["R1_denotes_real_feature"] else ("correct" if x["R1_type_rank"] == 0 else "mistyped")),
                      "G_verdict": ("grounded" if x["G_grounded"] else "not grounded"), "G_ref": x["G_ref"], "G_tier": x["G_tier"],
                      "phys_id": x["M"]["phys_id"], "required": x["M"].get("required"), "M_verdict": mv,
                      "duplicates_STEP_family": x["duplicates_STEP_family"],
                      "duplicate_of_entity_same_family": x["duplicate_of_entity_same_family"]})

    def tally(rows):
        return {v: sum(r["M_verdict"] == v for r in rows) for v in ("correct family", "wrong family", "no such feature")}
    ap = [r for r in steps if r["approved"]]; wh = [r for r in steps if not r["approved"]]
    plan_summary = {"steps": len(steps), "approved": len(ap), "withheld": len(wh),
                    "M_approved": tally(ap), "M_withheld": tally(wh),
                    "G_approved": {t: sum(r["G_tier"] == t for r in ap) for t in TIER_RANK},
                    "G_withheld": {t: sum(r["G_tier"] == t for r in wh) for t in TIER_RANK},
                    "G_not_grounded": {"approved": sum(not r["G_ref"] for r in ap), "withheld": sum(not r["G_ref"] for r in wh)},
                    "R1_approved": {v: sum(r["R1_verdict"] == v for r in ap) for v in ("correct", "mistyped", "phantom")},
                    "R1_withheld": {v: sum(r["R1_verdict"] == v for r in wh) for v in ("correct", "mistyped", "phantom")},
                    "approved_duplicates_STEP_family": [r["step"] for r in ap if r["duplicates_STEP_family"]],
                    "approved_M_wrong_steps": [r["step"] for r in ap if r["M_verdict"] == "wrong family"],
                    "withheld_M_correct_steps": [r["step"] for r in wh if r["M_verdict"] == "correct family"],
                    "physical_features_with_correct_family_approved_step": sorted({r["phys_id"] for r in ap if r["M_verdict"] == "correct family"}),
                    "physical_features_without_correct_family_approved_step": sorted({p["phys_id"] for p in phys["features"]} - {r["phys_id"] for r in ap if r["M_verdict"] == "correct family"})}
    return {"records": records, "per_agent": per_agent, "entities": entities, "per_reconciliation_class": classes,
            "ordering": ordering, "plan_steps": steps, "plan": plan_summary}


def main(repo, run_out, step_ref_path, draw_ref_path, phys_path, out, swap_run=None):
    step_refs = json.load(open(step_ref_path))["features"]
    draw_refs = json.load(open(draw_ref_path, encoding="utf-8"))["features"]
    phys = json.load(open(phys_path, encoding="utf-8"))
    ops = label_ops(os.path.join(repo, "knowledge", "rules", "machining_rules.swrl"))
    res = {"inputs": {"step_reference": os.path.basename(step_ref_path), "drawing_reference": os.path.basename(draw_ref_path),
                      "physical_reference": os.path.basename(phys_path), "run": run_out, "swap_run": swap_run},
           "label_operation_families": {k: sorted(v) for k, v in sorted(ops.items())}}
    with contextlib.redirect_stdout(io.StringIO()):
        r1 = r1_main(repo, run_out, step_ref_path, draw_ref_path)
    res["R1_convention_corrected_reference"] = r1
    res["two_level"] = two_level(repo, run_out, step_refs, draw_refs, phys, ops, r1)
    if swap_run:
        with contextlib.redirect_stdout(io.StringIO()):
            r1s = r1_main(repo, swap_run, step_ref_path, draw_ref_path)
        tl = two_level(repo, swap_run, step_refs, draw_refs, phys, ops, r1s)
        res["swap_sources"] = {"R1_convention_corrected_reference": {k: r1s[k] for k in ("entities", "per_reconciliation_class", "plan", "plan_steps")},
                               "two_level": {k: tl[k] for k in ("entities", "per_reconciliation_class", "ordering", "plan_steps", "plan")}}
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=lambda o: sorted(o) if isinstance(o, set) else str(o))
    tl = res["two_level"]
    print(json.dumps({"plan": tl["plan"], "ordering": tl["ordering"]}, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:])
