"""
Expert Validation Store
=========================
Stores KEFC's exception-gate requests and expert feedback as a JSON artifact
(`output/expert_validation_requests.json`). KEFC is the only writer of new requests; a
human (or a future review UI) edits `status`/`resolution_note` on an existing request
between runs.

Expert Validation is exception-based (see AGENTS.md): most manufacturing plan steps
should reach `auto_approved` without ever creating a request here. A request is only
created when KEFC's exception gate fires — see `kefc_controller.py`.

Persistence: the store loads `output_path` on construction if it already exists, so a
human's prior decision (editing a request's `status` to `expert_approved` and re-saving
the JSON file between pipeline runs) is honored on the next run instead of being
silently discarded. `create_request` is get-or-create, keyed on
`(feature_id, operation, reason_code)`: re-encountering the same exception reuses the
existing request (and its resolution, if any) rather than minting a fresh
`requires_review` request with a new id every run — that reuse is what makes the
request/feedback loop actually bilateral instead of a one-way write.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

STATUSES = (
    "requires_review",
    "auto_approved",
    "expert_approved",
    "expert_rejected",
    "knowledge_update_suggested",
)

REASON_CODES = (
    "missing_knowledge",       # no rule/ontology fact could be found
    "low_confidence_mapping",  # CFRM's feature->ontology mapping confidence too low
    "rule_conflict",           # two rules produced disagreeing values
    "unsafe_value",            # inferred value violates machine safety_limits
    "unresolved_mapping",      # feature type has no corresponding ontology class
    "machine_incompatible",    # operation not in the target machine's supportsOperation
    "orientation_incompatible",  # tool axis the operation needs is not an achievable tool orientation
    "serialisation_unsupported",  # machine can present the tool, but RAL's serialisation profile cannot express it
    "critical_simulation_finding",  # post-simulation finding (e.g. critical tool wear)
    "serialisation_input_missing",  # RAL feedback: an approved step lacks a plan input its toolpath needs; not serialised
)

# Reason codes where the already-computed parameters are trustworthy and an
# expert_approved resolution alone is enough to unblock RAL. missing_knowledge /
# unresolved_mapping / machine_incompatible / rule_conflict have no computed
# parameters to approve — resolving those requires an actual ontology/rule
# update (knowledge_update_suggested), not just a rubber stamp; see
# kefc_controller.py's use of this set. rule_conflict in particular: when two
# SWRL-inferred cutting-parameter sets disagree, kefc_controller.py leaves
# `parameters` empty ({}) rather than picking one — a bare expert_approved
# stamp must not be enough to unblock RAL for a step with no real parameters,
# or RAL's last-resort default= fallbacks would silently invent the values
# no one actually reasoned about.
APPROVABLE_WITHOUT_NEW_DATA = frozenset({
    "unsafe_value", "low_confidence_mapping", "critical_simulation_finding",
})


@dataclass
class ExpertValidationRequest:
    request_id: str
    feature_id: int
    feature_type: str
    operation: Optional[str]
    reason_code: str
    detail: str
    status: str = "requires_review"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolution_note: Optional[str] = None


class ExpertValidationStore:
    """One store per pipeline run, but its state persists across runs via
    `output_path` — see module docstring. Call `save()` after all requests
    are created/updated to persist to `output/expert_validation_requests.json`."""

    def __init__(self, output_path: str):
        self.output_path = output_path
        self._requests: Dict[str, ExpertValidationRequest] = {}
        self._counter = 0
        self._load()

    def _load(self):
        if not os.path.exists(self.output_path):
            return
        try:
            with open(self.output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        for row in data.get("requests", []):
            req = ExpertValidationRequest(**row)
            self._requests[req.request_id] = req
            suffix = req.request_id.rsplit("_", 1)[-1]
            if suffix.isdigit():
                self._counter = max(self._counter, int(suffix))

    def _find_existing(self, feature_id: int, operation: Optional[str],
                        reason_code: str) -> Optional[ExpertValidationRequest]:
        for req in self._requests.values():
            if (req.feature_id == feature_id and req.operation == operation
                    and req.reason_code == reason_code):
                return req
        return None

    def create_request(self, feature_id: int, feature_type: str, reason_code: str,
                        detail: str, operation: Optional[str] = None) -> ExpertValidationRequest:
        """Get-or-create: reuses an existing request (and its resolution) for
        the same (feature_id, operation, reason_code) rather than minting a
        duplicate every run."""
        if reason_code not in REASON_CODES:
            raise ValueError(f"Unknown reason_code: {reason_code!r}. Must be one of {REASON_CODES}")
        existing = self._find_existing(feature_id, operation, reason_code)
        if existing is not None:
            return existing
        self._counter += 1
        request_id = f"evr_{self._counter:04d}"
        req = ExpertValidationRequest(
            request_id=request_id, feature_id=feature_id, feature_type=feature_type,
            operation=operation, reason_code=reason_code, detail=detail,
        )
        self._requests[request_id] = req
        return req

    def find_resolution(self, feature_id: int, operation: Optional[str],
                         reason_code: str) -> Optional[ExpertValidationRequest]:
        """Look up a prior request for this exact exception without creating
        one. Used by KEFC to check "has a human already ruled on this?"
        before deciding a step's validation_status."""
        return self._find_existing(feature_id, operation, reason_code)

    def apply_feedback(self, request_id: str, decision: str, note: Optional[str] = None) -> ExpertValidationRequest:
        if decision not in ("expert_approved", "expert_rejected", "knowledge_update_suggested"):
            raise ValueError(f"Invalid decision: {decision!r}")
        req = self._requests[request_id]
        req.status = decision
        req.resolved_at = datetime.now(timezone.utc).isoformat()
        req.resolution_note = note
        return req

    def has_open_exceptions(self, feature_id: int) -> bool:
        return any(
            r.feature_id == feature_id and r.status == "requires_review"
            for r in self._requests.values()
        )

    def all_requests(self) -> List[ExpertValidationRequest]:
        return list(self._requests.values())

    def summary(self) -> Dict:
        counts = {status: 0 for status in STATUSES}
        for req in self._requests.values():
            counts[req.status] = counts.get(req.status, 0) + 1
        return {
            "total_requests": len(self._requests),
            "by_status": counts,
        }

    def save(self):
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "summary": self.summary(),
                    "requests": [asdict(r) for r in self._requests.values()],
                },
                f, indent=2,
            )
