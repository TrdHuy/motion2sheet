from __future__ import annotations

from typing import Any

from .contracts import GenerationPlan, SelectedReference


class MetadataBuilder:
    def build(
        self,
        *,
        animation: dict[str, Any],
        plan: GenerationPlan,
        reference: SelectedReference,
    ) -> dict[str, Any]:
        reference_use = dict(plan.reference_use)
        reference_use["selectedReferences"] = [
            {
                "animationHash": reference.animation_hash,
                "name": reference.name,
                "score": reference.score,
            }
        ]
        return {
            "name": animation["id"],
            "intent": plan.intent,
            "phases": list(plan.phases),
            "keyPoses": list(plan.key_poses),
            "weightTransfer": dict(plan.weight_transfer),
            "bodyMechanics": dict(plan.body_mechanics),
            "referenceUse": reference_use,
        }
