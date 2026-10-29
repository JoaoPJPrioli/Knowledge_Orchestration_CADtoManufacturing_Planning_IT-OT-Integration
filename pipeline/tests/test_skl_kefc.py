"""
Test script for the SKL / CFRM / KEFC retrofit (see AGENTS.md, .codex/testing_strategy.md)

Covers: SKL ontology loading, Pellet reasoning + named-rule provenance, CFRM mapping
(including the unmapped-feature exception path), KEFC's exception gate (missing
knowledge, unsafe value), ExpertValidationStore, and the traceable-parameter-shape
extraction gcode_generator.py added for RAL.
"""

import os
import sys

# BASE_DIR is the project root (this file lives in tests/, one level down).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

# Anchored to BASE_DIR rather than a bare "output" so these test artifacts
# always land in prototype_v2/output/ regardless of pytest's invocation cwd.
TEST_OUTPUT_DIR = os.path.join(BASE_DIR, 'tests', 'output')
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from skl_repository import SKLRepository
from semantic_reconciler import SemanticReconciler
from kefc_controller import KEFCController
from expert_validation import ExpertValidationStore
from gcode_generator import GCodeGenerator


def _motor_shaft_features():
    """Reuses main.py's actual KINM path (load_and_parse_features: STEP-pair
    and drawing-pair each reconciled separately via consensus voting, then
    merged with a global id reassignment) instead of raw-concatenating all 4
    source files with no dedup — that used to make this fixture ~2x the size
    of, and structurally different from, what the production pipeline
    (main.py) actually feeds into CFRM/KEFC. See main.load_and_parse_features's
    docstring for why reconciliation runs within each pair, not across them."""
    sys.path.insert(0, BASE_DIR)
    from main import load_and_parse_features

    motor_dir = os.path.join(BASE_DIR, 'data', 'motor_data')
    step_files = [
        os.path.join(motor_dir, 'features_eixo_step_Gemini31Pro.txt'),
        os.path.join(motor_dir, 'features_eixo_step_Gemini35flash.txt'),
    ]
    drawing_files = [
        os.path.join(motor_dir, 'draw_features_eixo_Gemini31Pro.txt'),
        os.path.join(motor_dir, 'draw_features_eixo_Gemini35flash.txt'),
    ]
    return load_and_parse_features(step_files, drawing_files)


def test_skl_ontologies_load():
    """Foundation + specialized ontologies load; expected classes/individuals present."""
    print("=" * 70)
    print("Testing SKL Ontology Loading")
    print("=" * 70)

    repo = SKLRepository()

    assert hasattr(repo.materials_onto, "AISI1045Steel"), "AISI1045Steel individual missing"
    assert hasattr(repo.machines_onto, "CNCLatheFanuc0iTD"), "CNCLatheFanuc0iTD individual missing"
    assert hasattr(repo.tools_onto, "TurningInsertRough"), "a turning tool individual is missing"
    assert hasattr(repo.tools_onto, "DrillBit"), "a drilling tool individual is missing"
    for cls_name in ("Step", "BlindHole", "Counterbore"):
        assert hasattr(repo.process_onto, cls_name), f"{cls_name} class missing from machining_process.owl"

    print(f"  ✓ {len(repo.rules)} SWRL rules parsed from machining_rules.swrl")
    print("  ✓ All expected foundation classes/individuals present")


def test_reasoner_named_rules():
    """Step -> rough+finish turning, BlindHole -> drilling, Counterbore ->
    drilling+counterboring, AISI-1045 feed rate traced to a named rule."""
    print("\n" + "=" * 70)
    print("Testing Pellet Reasoning + Named-Rule Provenance")
    print("=" * 70)

    repo = SKLRepository()
    step_f, _ = repo.create_feature_individual(1, "Step")
    blind_f, _ = repo.create_feature_individual(2, "Blind Hole")
    cb_f, _ = repo.create_feature_individual(3, "Counterbore")
    repo.reason()

    assert repo.reasoning_status == "ok", f"reasoning_status was {repo.reasoning_status!r}"

    step_ops = {o["operation"] for o in repo.get_operations(step_f)}
    assert step_ops == {"RoughTurningOp", "FinishTurningOp"}, f"Step ops were {step_ops}"

    blind_ops = {o["operation"] for o in repo.get_operations(blind_f)}
    assert blind_ops == {"DrillingOp"}, f"BlindHole ops were {blind_ops}"

    cb_ops = {o["operation"] for o in repo.get_operations(cb_f)}
    assert cb_ops == {"DrillingOp", "CounterboringOp"}, f"Counterbore ops were {cb_ops}"

    rough_params = [p for p in repo.get_cutting_parameter_sets(step_f) if p["operation"] == "RoughTurningOp"]
    assert len(rough_params) == 1, "expected exactly one rough-turning parameter set"
    assert rough_params[0]["rule_id"] == "aisi1045_roughturning_params"
    assert rough_params[0]["feed_rate"]["value"] == 0.25, rough_params[0]["feed_rate"]

    print("  ✓ Step -> {RoughTurningOp, FinishTurningOp}")
    print("  ✓ Blind Hole -> {DrillingOp}")
    print("  ✓ Counterbore -> {DrillingOp, CounterboringOp}")
    print(f"  ✓ AISI-1045 rough-turning feed rate traced to rule "
          f"{rough_params[0]['rule_id']!r} = {rough_params[0]['feed_rate']['value']} mm/rev")


def test_unmapped_feature_flagged():
    """A feature type with no SKL class mapping is flagged unmapped, not silently defaulted."""
    print("\n" + "=" * 70)
    print("Testing CFRM Unmapped-Feature Handling")
    print("=" * 70)

    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile([
        {"id": 1, "type": "Step"},
        {"id": 2, "type": "Some Totally Unknown Feature Type"},
    ])

    by_id = {rf.feature_id: rf for rf in reconciled}
    assert not by_id[1].unmapped, "Step should map cleanly"
    assert by_id[2].unmapped, "an unrecognized feature type must be flagged unmapped"
    print(f"  ✓ Unknown feature type correctly flagged: {by_id[2].reason}")


def test_kefc_auto_approval_on_real_case():
    """The real motor-shaft case, reconciled the same way main.py does
    (load_and_parse_features: consensus voting within each STEP-pair/
    drawing-pair under the type-admissibility gate, not raw concatenation of
    all 4 sources): 22 entities -> 32 steps total; 27 auto_approved and handed
    to RAL. KEFC decides on planning knowledge only (Revision 7): the 3
    milling steps (Slot entities reported by the secondary agent only) are
    requires_review on low mapping confidence and because CNCLatheFanuc0iTD
    does not list MillingOp; the 2 drilling steps on the radially orientated
    through-hole records are requires_review because the lathe declares only
    the axial tool orientation. Missing serialisation inputs (e.g. the groove
    without diameters) are not KEFC's decision; RAL refuses those steps."""
    print("\n" + "=" * 70)
    print("Testing KEFC Auto-Approval on the Real Motor-Shaft Case")
    print("=" * 70)

    features = _motor_shaft_features()
    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile(features)

    evr_path = os.path.join(TEST_OUTPUT_DIR, "test_evr_auto_approval.json")
    if os.path.exists(evr_path):
        os.remove(evr_path)  # ExpertValidationStore persists across runs; start clean
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)
    plan = kefc.build_manufacturing_plan(reconciled)

    assert len(features) == 22, f"expected 22 reconciled entities, got {len(features)}"
    assert len(plan["steps"]) == 32, f"expected 32 steps, got {len(plan['steps'])}"
    assert len(plan["approved_steps"]) == 27, f"expected 27 approved steps, got {len(plan['approved_steps'])}"
    withheld = [s["step_number"] for s in plan["steps"] if s["validation_status"] != "auto_approved"]
    assert withheld == [19, 20, 30, 31, 32], withheld
    milling_steps = [s for s in plan["steps"] if s["operation"] == "milling"]
    assert len(milling_steps) == 3 and all(s["validation_status"] == "requires_review" for s in milling_steps)
    withheld_drilling = [(s["step_number"], s["feature_type"]) for s in plan["steps"]
                         if s["operation"] == "drilling" and s["validation_status"] == "requires_review"]
    assert withheld_drilling == [(19, "Through Hole"), (20, "Through Hole")]
    grooving = [s for s in plan["steps"] if s["operation"] == "grooving"]
    assert len(grooving) == 1 and grooving[0]["validation_status"] == "auto_approved"
    codes = {r.reason_code for r in store.all_requests()}
    assert codes == {"low_confidence_mapping", "machine_incompatible", "orientation_incompatible"}, codes
    assert plan["expert_validation_summary"]["total_requests"] == 11, plan["expert_validation_summary"]

    print(f"  ✓ {len(plan['steps'])} steps ({len(plan['approved_steps'])} approved for RAL); "
          f"3 milling and 2 radial drilling steps gated as requires_review")


def test_kefc_missing_knowledge_exception():
    """A feature type with zero inferred operations must route to expert
    validation (missing_knowledge), not silently default to any operation."""
    print("\n" + "=" * 70)
    print("Testing KEFC Missing-Knowledge Exception Gate")
    print("=" * 70)

    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile([{"id": 1, "type": "Totally Unmapped Type"}])

    store = ExpertValidationStore(os.path.join(TEST_OUTPUT_DIR, "test_evr_missing_knowledge.json"))
    kefc = KEFCController(reconciler.repo, store)
    plan = kefc.build_manufacturing_plan(reconciled)

    assert len(plan["steps"]) == 0, "an unmapped feature must not silently produce a step"
    requests = store.all_requests()
    assert len(requests) == 1
    assert requests[0].reason_code == "unresolved_mapping"
    assert requests[0].status == "requires_review"

    print(f"  ✓ Unmapped feature produced 0 plan steps and 1 expert validation request "
          f"({requests[0].reason_code})")


def test_kefc_unsafe_value_detection():
    """KEFCController._check_unsafe flags a value that exceeds the machine's
    safety limits, independent of which rule produced it."""
    print("\n" + "=" * 70)
    print("Testing KEFC Unsafe-Value Detection")
    print("=" * 70)

    repo = SKLRepository()
    store = ExpertValidationStore(os.path.join(TEST_OUTPUT_DIR, "test_evr_unsafe.json"))
    kefc = KEFCController(repo, store)

    safe_params = {
        "feed_rate": {"value": 0.25, "unit": "mm/rev"},
        "spindle_speed": {"value": 800.0, "unit": "RPM"},
        "depth_of_cut": {"value": 2.0, "unit": "mm"},
    }
    assert kefc._check_unsafe(safe_params) is None, "expected no violation for in-limit values"

    unsafe_params = {
        "feed_rate": {"value": 0.25, "unit": "mm/rev"},
        "spindle_speed": {"value": 9000.0, "unit": "RPM"},  # exceeds hasSafetyMaxRPM (4500)
        "depth_of_cut": {"value": 2.0, "unit": "mm"},
    }
    violation = kefc._check_unsafe(unsafe_params)
    assert violation is not None and "spindle_speed" in violation, violation

    print(f"  ✓ In-limit parameters pass; 9000 RPM correctly flagged: {violation}")


# A Step that carries the dimensions its turning toolpaths need, so the only
# exception is the low-confidence mapping under test.
_LOW_CONF_STEP = {"id": 1, "type": "Step", "match_confidence": 0.2,
                  "dimensions": {"Ø": 24.0, "L": 20.0},
                  "absolute_location": {"X": 0.0, "Y": 0.0, "Z": 100.0}}


def test_kefc_expert_approval_unblocks_step_on_rerun():
    """A low_confidence_mapping exception (in
    expert_validation.APPROVABLE_WITHOUT_NEW_DATA) that a human resolves as
    expert_approved between runs must actually unblock the step on the next
    run — this is the persistence loop finding #9 identified as missing."""
    print("\n" + "=" * 70)
    print("Testing Expert-Approval Persistence Unblocks a Step")
    print("=" * 70)

    reconciler = SemanticReconciler()
    # match_confidence below LOW_CONFIDENCE_THRESHOLD (0.5) forces CFRM to
    # flag this feature as low_confidence.
    reconciled = reconciler.reconcile([_LOW_CONF_STEP])

    evr_path = os.path.join(TEST_OUTPUT_DIR, "test_evr_persistence_unblock.json")
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)
    plan = kefc.build_manufacturing_plan(reconciled)

    assert all(s["validation_status"] == "requires_review" for s in plan["steps"])
    assert len(plan["approved_steps"]) == 0

    # A human resolves the low_confidence_mapping request as expert_approved
    # (e.g. by editing the JSON file, or via apply_feedback in a review UI)
    # and the store is re-saved between runs.
    low_conf_requests = [r for r in store.all_requests() if r.reason_code == "low_confidence_mapping"]
    assert len(low_conf_requests) >= 1
    for req in low_conf_requests:
        store.apply_feedback(req.request_id, "expert_approved", note="confirmed correct despite low confidence")
    store.save()

    # Simulate the next pipeline run: fresh repo/reconciler/store instances,
    # store loaded from the same file.
    reconciler2 = SemanticReconciler()
    reconciled2 = reconciler2.reconcile([_LOW_CONF_STEP])
    store2 = ExpertValidationStore(evr_path)
    kefc2 = KEFCController(reconciler2.repo, store2)
    plan2 = kefc2.build_manufacturing_plan(reconciled2)

    assert all(s["validation_status"] == "expert_approved" for s in plan2["steps"]), \
        [s["validation_status"] for s in plan2["steps"]]
    assert len(plan2["approved_steps"]) == len(plan2["steps"])

    print("  ✓ A prior expert_approved resolution correctly unblocks the step on the next run")


def test_rule_conflict_not_approvable_without_new_data():
    """rule_conflict must NOT be in expert_validation.APPROVABLE_WITHOUT_NEW_DATA:
    kefc_controller.py's _build_step leaves `parameters` empty ({}) whenever
    _detect_conflict fires, so a bare expert_approved stamp (with no actual
    replacement parameter values supplied) must not be enough to unblock the
    step for RAL — that would let RAL's _extract_parameter_value fall back to
    its own hardcoded per-operation defaults, i.e. genuinely invented values
    nobody reasoned about. Unlike low_confidence_mapping (a real scenario
    reachable via match_confidence), rule_conflict has no simple end-to-end
    trigger, so this calls KEFCController._resolve_exceptions directly with a
    synthetic rule_conflict exception rather than a scenario that reasons its
    way to one."""
    print("\n" + "=" * 70)
    print("Testing rule_conflict Is Not Approvable Without New Data")
    print("=" * 70)

    from expert_validation import APPROVABLE_WITHOUT_NEW_DATA
    assert "rule_conflict" not in APPROVABLE_WITHOUT_NEW_DATA

    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile([{"id": 1, "type": "Step"}])
    rf = reconciled[0]

    evr_path = os.path.join(TEST_OUTPUT_DIR, "test_evr_rule_conflict.json")
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)

    status = kefc._resolve_exceptions(rf, "RoughTurningOp", [("rule_conflict", "two rules disagreed")])
    assert status == "requires_review", status

    conflict_requests = [r for r in store.all_requests() if r.reason_code == "rule_conflict"]
    assert len(conflict_requests) == 1
    for req in conflict_requests:
        store.apply_feedback(req.request_id, "expert_approved", note="looks fine")
    store.save()

    # Re-check: even after a bare expert_approved stamp, with no replacement
    # parameters ever supplied, the same rule_conflict exception must still
    # require review.
    store2 = ExpertValidationStore(evr_path)
    kefc2 = KEFCController(reconciler.repo, store2)
    status2 = kefc2._resolve_exceptions(rf, "RoughTurningOp", [("rule_conflict", "two rules disagreed")])
    assert status2 == "requires_review", status2

    print("  ✓ rule_conflict stays requires_review even after a bare expert_approved stamp")


def test_expert_validation_store_roundtrip():
    """create_request -> apply_feedback -> summary/save round trip, then
    verify persistence: a fresh ExpertValidationStore pointed at the same
    file loads the resolved status back (this is what makes a human's
    decision, made between pipeline runs, actually reach the next run)."""
    print("\n" + "=" * 70)
    print("Testing ExpertValidationStore")
    print("=" * 70)

    path = os.path.join(TEST_OUTPUT_DIR, "test_evr_roundtrip.json")
    if os.path.exists(path):
        os.remove(path)  # this test asserts on a fresh request; the store persists across runs
    store = ExpertValidationStore(path)
    req = store.create_request(
        feature_id=1, feature_type="Step", reason_code="low_confidence_mapping",
        detail="test", operation="rough_turning",
    )
    assert req.status == "requires_review"
    assert store.has_open_exceptions(1)

    store.apply_feedback(req.request_id, "expert_approved", note="looks fine")
    assert not store.has_open_exceptions(1)
    assert store.summary()["by_status"]["expert_approved"] == 1

    store.save()
    assert os.path.exists(path)

    # Persistence: a new store instance pointed at the same file should load
    # the resolution and get-or-create should return it, not a fresh request.
    reloaded_store = ExpertValidationStore(path)
    reloaded_req = reloaded_store.create_request(
        feature_id=1, feature_type="Step", reason_code="low_confidence_mapping",
        detail="test", operation="rough_turning",
    )
    assert reloaded_req.request_id == req.request_id
    assert reloaded_req.status == "expert_approved"

    print(f"  ✓ Request lifecycle requires_review -> expert_approved persisted to {path}, "
          f"and reloaded correctly by a fresh store instance")


def test_gcode_generator_reads_traceable_parameters():
    """_extract_parameter_value prefers the new {value, unit, source, rule_id,
    ontology_sources, input_facts} shape over the legacy fallback default."""
    print("\n" + "=" * 70)
    print("Testing gcode_generator.py Traceable-Parameter Extraction")
    print("=" * 70)

    generator = GCodeGenerator('steel_1045', 'cnc_lathe')

    traceable = {
        "feed_rate": {
            "value": 0.25, "unit": "mm/rev", "source": "swrl_rule",
            "rule_id": "aisi1045_roughturning_params", "ontology_sources": [], "input_facts": {},
        }
    }
    assert generator._extract_parameter_value(traceable, "feed_rate", default=999.0) == 0.25

    legacy_range = {"feed_rate": {"min": 0.15, "max": 0.4, "default": 0.3}}
    assert generator._extract_parameter_value(legacy_range, "feed_rate", default=999.0) == 0.3

    legacy_plain = {"feed_rate": 0.18}
    assert generator._extract_parameter_value(legacy_plain, "feed_rate", default=999.0) == 0.18

    assert generator._extract_parameter_value({}, "feed_rate", default=999.0) == 999.0

    print("  ✓ Traceable shape, legacy range shape, plain-numeric shape, and the "
          "last-resort fallback all extract correctly")


def test_sparql_examples_all_pass():
    """The full sparql_examples.py pool executes without error, and every
    example flagged expected_nonempty actually returns data, against a real
    triplestore built via the SKL-authoritative path (build_kg_from_skl() +
    populate_decisions_from_kefc() — not the retired ontology.py-driven
    build_manufacturing_kg())."""
    print("\n" + "=" * 70)
    print("Testing Full SPARQL Example Pool")
    print("=" * 70)

    from kg_builder import ManufacturingKG
    from rdf_triplestore import ManufacturingTriplestore
    from sparql_examples import EXAMPLES

    # Use the same merged STEP+drawing feature set main.py's real pipeline
    # runs on (not just the single STEP/31Pro file) — several examples'
    # expected_nonempty flags (e.g. the "cylinder feature" queries) were
    # verified against that full dataset, since drawing-derived feature
    # types like "Cylinder"/"Groove" don't appear in the STEP file alone.
    features = _motor_shaft_features()

    reconciler = SemanticReconciler()
    reconciled = reconciler.reconcile(features)

    evr_path = os.path.join(TEST_OUTPUT_DIR, "test_evr_sparql_examples.json")
    if os.path.exists(evr_path):
        os.remove(evr_path)
    store = ExpertValidationStore(evr_path)
    kefc = KEFCController(reconciler.repo, store)
    kefc_plan = kefc.build_manufacturing_plan(reconciled, material='steel_1045', machine='cnc_lathe')

    kg = ManufacturingKG()
    kg.build_kg_from_skl(features, reconciler.repo)
    kg.populate_decisions_from_kefc(kefc_plan['steps'], reconciled)

    ts = ManufacturingTriplestore()
    ts.import_from_networkx(kg.G)

    failures = []
    empty_when_expected = []
    for i, example in enumerate(EXAMPLES):
        try:
            results = ts.execute_sparql(example['sparql'])
        except Exception as e:
            failures.append((i + 1, example['question'], str(e)))
            continue
        if example.get('expected_nonempty', True) and len(results) == 0:
            empty_when_expected.append((i + 1, example['question']))

    assert not failures, f"{len(failures)}/{len(EXAMPLES)} SPARQL examples failed: {failures[:3]}"
    assert not empty_when_expected, (
        f"{len(empty_when_expected)} examples expected nonempty results but got none: "
        f"{empty_when_expected[:5]}"
    )
    print(f"  ✓ All {len(EXAMPLES)} SPARQL example queries executed without error, "
          f"and every expected-nonempty example returned data")


if __name__ == '__main__':
    test_skl_ontologies_load()
    test_reasoner_named_rules()
    test_unmapped_feature_flagged()
    test_kefc_auto_approval_on_real_case()
    test_kefc_missing_knowledge_exception()
    test_kefc_unsafe_value_detection()
    test_kefc_expert_approval_unblocks_step_on_rerun()
    test_rule_conflict_not_approvable_without_new_data()
    test_expert_validation_store_roundtrip()
    test_gcode_generator_reads_traceable_parameters()
    test_sparql_examples_all_pass()
    print("\n" + "=" * 70)
    print("All SKL/CFRM/KEFC tests passed")
    print("=" * 70)
