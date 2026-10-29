"""
RAL refusal records (Revision 7).

KEFC decides on planning knowledge only. RAL checks each handed-over step
against its toolpath pattern's declared input contract
(GCodeGenerator.refusal_for); a step it would have to guess for is not
serialised. Each refusal is fed back into the expert-validation store as
serialisation_input_missing, the same feedback path as the post-simulation
findings, and the accounting is asserted: handed = serialised + refused, and
every refusal has a store record.
"""
import json
from typing import Dict, List

REFUSAL_REASON_CODE = "serialisation_input_missing"


def refusal_detail(refusal: Dict) -> str:
    entity = refusal["source_entity"]
    return json.dumps({
        "step_number": refusal["step_number"],
        "operation": refusal["operation"],
        "kind": refusal["kind"],
        "missing_inputs": refusal["missing_inputs"],
        "required_inputs": refusal["required_inputs"],
        "source_entity": {"feature_id": entity["feature_id"], "feature_type": entity["feature_type"],
                          "feature_dimensions": entity["feature_dimensions"]},
    }, ensure_ascii=False)


def record_refusals(refusals: List[Dict], store) -> List[str]:
    """Write one serialisation_input_missing request per refusal; returns
    the request ids. Get-or-create, so a rerun does not duplicate them."""
    ids = []
    for r in refusals:
        entity = r["source_entity"]
        req = store.create_request(
            feature_id=entity["feature_id"], feature_type=entity["feature_type"],
            reason_code=REFUSAL_REASON_CODE, operation=r.get("ontology_operation") or r["operation"],
            detail=refusal_detail(r))
        r["request_id"] = req.request_id
        ids.append(req.request_id)
    if refusals:
        store.save()
    return ids


def check_ral_accounting(handed: List[Dict], serialised: List[Dict], refusals: List[Dict], store) -> Dict:
    """Raise unless handed == serialised + refused (as step sets) and every
    refusal has a serialisation_input_missing record in the store."""
    handed_ids = [s["step_number"] for s in handed]
    serialised_ids = [s["step_number"] for s in serialised]
    refused_ids = [r["step_number"] for r in refusals]
    problems = []
    if sorted(handed_ids) != sorted(serialised_ids + refused_ids) or set(serialised_ids) & set(refused_ids):
        problems.append(f"handed {sorted(handed_ids)} != serialised {serialised_ids} + refused {refused_ids}")
    unrecorded = [r["step_number"] for r in refusals
                  if store.find_resolution(r["source_entity"]["feature_id"],
                                           r.get("ontology_operation") or r["operation"],
                                           REFUSAL_REASON_CODE) is None]
    if unrecorded:
        problems.append(f"refusals without a store record: steps {unrecorded}")
    result = {"handed": len(handed_ids), "serialised": len(serialised_ids), "refused": len(refused_ids),
              "serialised_steps": serialised_ids, "refused_steps": refused_ids,
              "unrecorded_refusals": unrecorded, "passed": not problems, "problems": problems}
    if problems:
        raise RuntimeError("RAL accounting failed: " + "; ".join(problems))
    return result
