from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from healthia_one.models import AuditEvent, PatientConsent, PatientState, ProactiveFinding, RiskLevel


def patient_now(state: PatientState, now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    try:
        return current.astimezone(ZoneInfo(state.profile.timezone))
    except Exception:
        return current


def in_quiet_hours(consent: PatientConsent, local_now: datetime) -> bool:
    start_hour, start_minute = map(int, consent.quiet_hours_start.split(":"))
    end_hour, end_minute = map(int, consent.quiet_hours_end.split(":"))
    current = local_now.hour * 60 + local_now.minute
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def finding_allowed(
    state: PatientState,
    finding: ProactiveFinding,
    now: datetime | None = None,
    *,
    manual_requested: bool = False,
) -> tuple[bool, str]:
    """Return whether an intervention may surface and the most specific reason.

    HealthIA is quiet by default. Explicit patient choices such as snooze/mute are
    still evaluated before the general proactive-off policy so the audit trail can
    explain the patient's own preference instead of collapsing everything into a
    generic `proactive_disabled` reason. A patient-requested manual review remains
    allowed because it is not unsolicited proactive messaging.
    """
    consent = state.consent
    if finding.risk_level == RiskLevel.URGENT and consent.allow_urgent_safety_bypass:
        return True, "urgent_safety_bypass"
    if manual_requested:
        return True, "manual_review_requested"

    current = now or datetime.now(timezone.utc)
    if consent.snoozed_until and current < consent.snoozed_until:
        return False, "snoozed"
    if any(finding.key.startswith(prefix) for prefix in consent.muted_rule_prefixes):
        return False, "muted_rule"
    if not consent.proactive_enabled:
        return False, "proactive_disabled"
    if in_quiet_hours(consent, patient_now(state, current)):
        return False, "quiet_hours"
    return True, "allowed"


def sync_consent_to_profile(state: PatientState) -> None:
    state.profile.consented_signal_types = list(dict.fromkeys(state.consent.signal_types))
    state.consent.updated_at = datetime.now(timezone.utc)


def snooze_consent(state: PatientState, hours: int, now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    state.consent.snoozed_until = current + timedelta(hours=hours)
    state.consent.updated_at = current
    return state.consent.snoozed_until


def audit(
    state: PatientState,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str = "",
    outcome: str = "success",
    details: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        patient_id=state.profile.id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        details=details or {},
    )
    state.audit_events.append(event)
    if len(state.audit_events) > 1000:
        state.audit_events = state.audit_events[-1000:]
    return event


def export_patient_state(state: PatientState) -> dict:
    payload = state.model_dump(mode="json")
    for document in payload.get("documents", []):
        document.pop("storage_path", None)
    payload["export"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format": "HealthIA ONE patient export v1",
        "contains_binary_files": False,
        "truth_boundary": "Patient-controlled export of structured data and document metadata.",
    }
    return payload
