from datetime import datetime, timedelta, timezone

from healthia_one.control import export_patient_state, finding_allowed, in_quiet_hours, snooze_consent
from healthia_one.models import ClinicalDocument, PatientConsent, ProactiveFinding, RiskLevel
from healthia_one.patient_control import maybe_control_response
from healthia_one.service import seed_state


def finding(level: RiskLevel = RiskLevel.INFO, key: str = "weight:test") -> ProactiveFinding:
    return ProactiveFinding(
        key=key,
        title="Test",
        risk_level=level,
        summary="Synthetic",
        why_it_matters="Synthetic",
        next_action="Synthetic",
    )


def test_disabled_proactivity_blocks_nonurgent_but_not_authorized_urgent():
    state = seed_state()
    state.consent.proactive_enabled = False
    allowed, reason = finding_allowed(state, finding(), datetime.now(timezone.utc))
    urgent_allowed, urgent_reason = finding_allowed(state, finding(RiskLevel.URGENT), datetime.now(timezone.utc))
    assert not allowed and reason == "proactive_disabled"
    assert urgent_allowed and urgent_reason == "urgent_safety_bypass"


def test_quiet_hours_wrap_midnight():
    consent = PatientConsent(quiet_hours_start="22:00", quiet_hours_end="07:00")
    assert in_quiet_hours(consent, datetime(2026, 8, 5, 23, 0, tzinfo=timezone.utc))
    assert in_quiet_hours(consent, datetime(2026, 8, 5, 6, 30, tzinfo=timezone.utc))
    assert not in_quiet_hours(consent, datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc))


def test_snooze_and_muted_rule_block_interventions():
    state = seed_state()
    now = datetime.now(timezone.utc)
    snooze_consent(state, 24, now)
    allowed, reason = finding_allowed(state, finding(), now + timedelta(hours=1))
    assert not allowed and reason == "snoozed"
    state.consent.snoozed_until = None
    state.consent.muted_rule_prefixes = ["weight:"]
    allowed, reason = finding_allowed(state, finding(key="weight:gain"), now)
    assert not allowed and reason == "muted_rule"


def test_export_removes_internal_storage_paths():
    state = seed_state()
    state.documents.append(ClinicalDocument(title="Synthetic", filename="note.txt", storage_path="uploads/private/note.txt"))
    payload = export_patient_state(state)
    assert "storage_path" not in payload["documents"][0]
    assert payload["export"]["contains_binary_files"] is False


def test_control_chat_uses_bastion_and_public_action_target():
    response = maybe_control_response(seed_state(), "Muéstrame mis permisos de privacidad y auditoría")
    assert response is not None
    assert response.mission.mission_type == "patient_control"
    assert response.message.metadata["action_target"] == "control"
    assert any(step.agent == "BASTION" for step in response.message.agent_plan)
