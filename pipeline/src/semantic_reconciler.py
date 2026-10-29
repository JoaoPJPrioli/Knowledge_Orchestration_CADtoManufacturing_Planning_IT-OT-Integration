"""
Semantic Reconciler (CFRM)
============================
Case Formalization & Reconciliation Module. Takes KINM's normalized feature dicts
(from `feature_parser.py`, as assembled by `main.py`) and maps each one to an SKL
ontology individual (`skl_repository.py`), building the batch that gets reasoned over
once by Pellet.

CFRM does not decide operations, tools, or cutting parameters — it decides *what a
feature is* (which ontology class it instantiates) and flags anything it can't resolve
confidently for KEFC. KEFC (`kefc_controller.py`) is the only consumer that turns SKL's
reasoned facts into a manufacturing plan.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from skl_repository import SKLRepository

LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass
class ReconciledFeature:
    feature_id: int
    feature_type: str
    source_feature: Dict
    skl_individual: object
    confidence: float
    unmapped: bool
    low_confidence: bool
    reason: Optional[str] = None


class SemanticReconciler:
    """One instance per pipeline run. Owns the SKLRepository for that run."""

    def __init__(self, material_key: str = "steel_1045", machine_key: str = "cnc_lathe",
                 skl_repository: Optional[SKLRepository] = None):
        self.material_key = material_key
        self.machine_key = machine_key
        self.repo = skl_repository or SKLRepository(machine_key=machine_key)

    def reconcile(self, features: List[Dict]) -> List[ReconciledFeature]:
        reconciled = []
        for feature in features:
            feature_id = feature["id"]
            feature_type = feature["type"]

            individual, mapping_confidence = self.repo.create_feature_individual(
                feature_id, feature_type,
                material_key=self.material_key, machine_key=self.machine_key,
            )

            # match_confidence comes from feature_parser.py's consensus-voting
            # reconciliation (Eq. 2 in the manuscript) when present; features
            # loaded without cross-source reconciliation default to full
            # confidence — this field is what CFRM inherited from KINM, not
            # something CFRM computes itself.
            source_confidence = feature.get("match_confidence", 1.0)
            combined_confidence = min(mapping_confidence, source_confidence)

            unmapped = mapping_confidence == 0.0
            low_confidence = (not unmapped) and combined_confidence < LOW_CONFIDENCE_THRESHOLD

            reason = None
            if unmapped:
                reason = f"Feature type {feature_type!r} has no corresponding SKL ontology class."
            elif low_confidence:
                reason = (
                    f"Combined mapping confidence {combined_confidence:.2f} is below "
                    f"the {LOW_CONFIDENCE_THRESHOLD} threshold."
                )

            reconciled.append(ReconciledFeature(
                feature_id=feature_id,
                feature_type=feature_type,
                source_feature=feature,
                skl_individual=individual,
                confidence=combined_confidence,
                unmapped=unmapped,
                low_confidence=low_confidence,
                reason=reason,
            ))

        self.repo.reason()
        return reconciled
