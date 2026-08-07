from __future__ import annotations

from healthia_one.identity import AuthPrincipal
from healthia_one.models import (
    CarePlan,
    ChatMessage,
    PatientConsent,
    PatientProfile,
    PatientState,
)


def bind_state_identity(
    state: PatientState,
    uid: str,
    *,
    display_name: str = "",
    email: str = "",
) -> PatientState:
    """Bind all patient-owned records to one verified immutable uid."""

    state.profile.id = uid
    if display_name:
        state.profile.display_name = display_name
    if email:
        state.profile.email = email
    for collection_name in (
        "vitals",
        "weights",
        "activity",
        "results",
        "family_members",
        "documents",
        "medication_plans",
        "medication_checkins",
        "appointments",
        "goals",
        "missions",
        "mission_runs",
        "mission_artifacts",
        "messages",
        "audit_events",
        "device_observations",
    ):
        for item in getattr(state, collection_name, []):
            if hasattr(item, "patient_id"):
                item.patient_id = uid
    return state


def new_identity_state(principal: AuthPrincipal) -> PatientState:
    """Create an assumption-free account state for a newly authenticated user."""

    name = principal.display_name or (principal.email.split("@", 1)[0] if principal.email else "Paciente")
    profile = PatientProfile(
        id=principal.uid,
        display_name=name,
        legal_name="",
        birth_date=None,
        sex_at_birth="unknown",
        height_cm=None,
        email=principal.email,
        allergies=[],
        medications=[],
        confirmed_conditions=[],
        care_plan=CarePlan(conditions=[]),
        consented_signal_types=[],
    )
    consent = PatientConsent(
        proactive_enabled=False,
        signal_types=[],
        allow_urgent_safety_bypass=True,
    )
    state = PatientState(profile=profile, consent=consent)
    state.messages = [
        ChatMessage(
            patient_id=principal.uid,
            role="assistant",
            author="HealthIA",
            content=(
                f"Hola, {name}. Esta cuenta empieza sin antecedentes clínicos asumidos. "
                "Puedes contarme qué necesitas, completar tu perfil o cargar datos que quieras autorizar."
            ),
        )
    ]
    return state
