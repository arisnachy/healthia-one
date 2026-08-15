from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from healthia_one.control import audit
from healthia_one.education_video import PatientEducationVideoRouter
from healthia_one.education_video_models import (
    MEDICATION_CHANGE_PATTERNS,
    EducationFact,
    EducationVideoPlan,
    normalize,
)
from healthia_one.models import PatientState


_SAFE_MEDICATION_CHANGE_CONTEXTS = (
    r"\b(?:do not|don't|should not|never)\s+(?:stop taking|increase|decrease|double|change your dose)\b",
    r"\b(?:no|nunca)\s+(?:suspendas?|dejes de tomar|aumentes?|reduzcas?|dupliques?)\b",
    r"\b(?:nao|não|nunca)\s+(?:pare de tomar|aumente|reduza|duplique|mude a dose)\b",
    r"\b(?:ne|jamais)\s+(?:arretez|augmentez|reduisez|doublez)\b",
)


def _crosses_medication_change_boundary(value: str) -> bool:
    """Reject treatment-changing instructions while allowing explicit safety negations."""
    scrubbed = normalize(value)
    for pattern in _SAFE_MEDICATION_CHANGE_CONTEXTS:
        scrubbed = re.sub(pattern, " ", scrubbed)
    return any(re.search(pattern, scrubbed) for pattern in MEDICATION_CHANGE_PATTERNS)


def harden_plan_for_delivery(
    plan: EducationVideoPlan,
    facts: list[EducationFact],
    patient_name: str,
) -> EducationVideoPlan:
    """Enforce privacy boundaries by degrading recoverable model variance to safer UI.

    This function never invents a patient fact. Unknown fact references are removed.
    A Veo scene that contains a patient value, number, empty prompt, or exceeds the
    one-scene Veo budget becomes a controlled HealthIA card instead.
    """
    safe = plan.model_copy(deep=True)
    allowed = {item.key for item in facts}
    safe.patient_fact_keys = [key for key in safe.patient_fact_keys if key in allowed]

    private_tokens = {normalize(patient_name)} if patient_name else set()
    private_tokens.update(normalize(item.value) for item in facts if item.value)

    veo_used = False
    for scene in safe.scenes:
        if scene.visual_kind != "veo":
            scene.veo_prompt = ""
            continue

        prompt = normalize(scene.veo_prompt)
        unsafe_prompt = (
            not prompt
            or veo_used
            or any(token and token in prompt for token in private_tokens)
            or bool(re.search(r"\b\d+(?:[./-]\d+)*\b", prompt))
        )
        if unsafe_prompt:
            scene.visual_kind = "card"
            scene.veo_prompt = ""
            continue
        veo_used = True

    return safe


def validate_hardened_plan(
    plan: EducationVideoPlan,
    facts: list[EducationFact],
    patient_name: str,
) -> EducationVideoPlan:
    """Second fail-closed barrier after deterministic recovery."""
    allowed = {item.key for item in facts}
    if any(key not in allowed for key in plan.patient_fact_keys):
        raise ValueError("Education plan referenced a patient fact outside the authorized evidence set")

    private_tokens = {normalize(patient_name)} if patient_name else set()
    private_tokens.update(normalize(item.value) for item in facts if item.value)
    veo_count = 0

    for scene in plan.scenes:
        combined = f"{scene.heading} {scene.body} {scene.narration}"
        if _crosses_medication_change_boundary(combined):
            raise ValueError("Education plan crossed the medication-change safety boundary")

        if scene.visual_kind != "veo":
            continue
        veo_count += 1
        prompt = normalize(scene.veo_prompt)
        if not prompt:
            raise ValueError("Veo scene requires a generic prompt")
        if any(token and token in prompt for token in private_tokens):
            raise ValueError("Patient-specific information must never be sent to Veo")
        if re.search(r"\b\d+(?:[./-]\d+)*\b", prompt):
            raise ValueError("Exact numbers are not allowed in Veo education prompts")

    if veo_count > 1:
        raise ValueError("HealthIA Explain allows at most one Veo scene per video")
    return plan


class ResilientPatientEducationVideoRouter(PatientEducationVideoRouter):
    """Production router with one bounded structured-plan retry and safe degradation."""

    async def _plan(
        self,
        state: PatientState,
        topic: str,
        locale: str,
        duration_seconds: int,
        facts: list[EducationFact],
    ) -> EducationVideoPlan:
        planner = self._planner or self._gemini_plan
        attempts = 1 if self._planner is not None else 2
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                plan = await planner(state, topic, locale, duration_seconds, facts)
                plan = harden_plan_for_delivery(plan, facts, state.profile.display_name)
                return validate_hardened_plan(plan, facts, state.profile.display_name)
            except (ValueError, ValidationError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    raise
                audit(
                    state,
                    actor="healthia",
                    action="retry_patient_education_video_plan",
                    resource_type="patient_education_video",
                    resource_id=state.profile.id,
                    details={
                        "attempt": attempt + 2,
                        "error_type": type(exc).__name__,
                        "safe_retry": True,
                    },
                )

        if last_error is not None:
            raise last_error
        raise RuntimeError("HealthIA Explain plan recovery ended without a plan")


__all__ = [
    "ResilientPatientEducationVideoRouter",
    "harden_plan_for_delivery",
    "validate_hardened_plan",
]
