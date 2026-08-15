from __future__ import annotations

import hashlib

from healthia_one.config import Settings
from healthia_one.google_constellation import (
    GrantBundle,
    GoogleAction,
    GoogleActionRequest,
    GoogleGrant,
    GoogleService,
    build_idempotency_key,
)
from healthia_one.google_constellation_singleton import get_google_constellation_service
from healthia_one.google_constellation_store import GoogleActionAuthorization, build_action_intent_key
from healthia_one.google_oauth_credentials import service_scope_present
from healthia_one.guardian_context import GuardianAssessment
from healthia_one.guardian_notifications import GuardianEmailDraft, plan_guardian_notification
from healthia_one.models import MissionStatus, PatientState


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class GuardianEmailDispatcher:
    """Send one bounded Guardian update to the patient through connected Gmail.

    The standing patient consent flags are the product-level authorization to
    communicate proactively. Each actual Gmail mutation is still narrowed to one
    patient + one Guardian mission + one exact recipient/subject/body by a durable
    GoogleActionAuthorization before it reaches the existing guarded connector.

    This dispatcher intentionally sends only to ``state.profile.email``. It cannot
    contact a clinician, family member, provider or arbitrary third party. Those
    actions continue to require their existing mission-scoped human authorization.
    """

    def __init__(self, settings: Settings, *, constellation=None) -> None:
        self.settings = settings
        self.constellation = constellation or get_google_constellation_service(settings)

    @staticmethod
    def _validate_patient_boundary(
        state: PatientState,
        assessment: GuardianAssessment,
        draft: GuardianEmailDraft,
        mission_id: str,
    ) -> None:
        if draft.patient_id != state.profile.id:
            raise PermissionError("Guardian email patient boundary mismatch")
        if draft.mission_id != mission_id:
            raise PermissionError("Guardian email mission boundary mismatch")
        recipient = str(draft.recipient or "").strip().lower()
        profile_email = str(state.profile.email or "").strip().lower()
        if not profile_email or recipient != profile_email:
            raise PermissionError("Guardian email may only be sent to the patient's own profile email")
        if draft.contains_precise_location or draft.changes_treatment or draft.diagnostic_claim:
            raise PermissionError("Guardian email content crossed a protected clinical/privacy boundary")
        if any(key in assessment.context for key in ("latitude", "longitude", "lat", "lng")):
            raise PermissionError("Guardian email cannot be generated from precise location context")
        mission = next((item for item in state.missions if item.id == mission_id), None)
        if mission is None or mission.patient_id != state.profile.id:
            raise PermissionError("Guardian mission is not present in canonical patient state")
        if mission.status == MissionStatus.CANCELLED:
            raise PermissionError("Cancelled Guardian missions cannot trigger email")

    def _ensure_mission_gmail_grant(self, state: PatientState, mission_id: str) -> GoogleGrant:
        """Derive the narrow Gmail capability from explicit Guardian auto-send consent.

        The OAuth provider scope is checked separately. This HealthIA grant is
        mission-scoped so the Guardian email consent cannot become a blanket
        authorization for unrelated provider contact.
        """
        runtime = self.constellation.runtime
        existing = next(
            (
                grant
                for grant in runtime.grant_store.list_for_patient(state.profile.id)
                if grant.bundle == GrantBundle.GMAIL_SEND
                and grant.is_active_for(state.profile.id, mission_id)
                and (grant.mission_id == mission_id or not grant.mission_id)
            ),
            None,
        )
        if existing is not None:
            return existing
        grant = GoogleGrant(
            id=_stable_id("grant", state.profile.id, mission_id, "guardian_email"),
            patient_id=state.profile.id,
            bundle=GrantBundle.GMAIL_SEND,
            enabled=True,
            mission_id=mission_id,
        )
        runtime.grant_store.save(grant)
        return grant

    def dispatch(
        self,
        state: PatientState,
        assessment: GuardianAssessment,
        *,
        event_id: str,
        mission_id: str,
    ) -> dict:
        plan = plan_guardian_notification(state, assessment, mission_id=mission_id)
        draft = plan.email
        if not assessment.notify_patient:
            return {"status": "skipped_not_requested", "sent": 0, "recovered": 0}
        if draft is None:
            return {"status": "skipped_no_patient_email", "sent": 0, "recovered": 0}
        if draft.delivery_mode != "eligible_auto_send":
            return {
                "status": "skipped_auto_send_not_consented",
                "sent": 0,
                "recovered": 0,
                "draft_id": draft.id,
            }

        self._validate_patient_boundary(state, assessment, draft, mission_id)
        runtime = self.constellation.runtime
        connection = runtime.oauth_connection_store.load(state.profile.id)
        if connection is None or not connection.enabled:
            return {
                "status": "skipped_google_account_not_connected",
                "sent": 0,
                "recovered": 0,
                "draft_id": draft.id,
            }
        if not service_scope_present(connection, GoogleService.GMAIL):
            return {
                "status": "skipped_google_gmail_scope_missing",
                "sent": 0,
                "recovered": 0,
                "draft_id": draft.id,
            }

        self._ensure_mission_gmail_grant(state, mission_id)
        payload = {
            "to": [draft.recipient],
            "subject": draft.subject,
            "body": draft.body,
            # Connector ignores these fields, but keeping them in the material
            # payload binds the authorization/idempotency fingerprint to the exact
            # Guardian event and standing-consent basis.
            "healthia_guardian_event_id": event_id,
            "healthia_consent_basis": list(draft.consent_basis),
        }
        unsigned = GoogleActionRequest(
            patient_id=state.profile.id,
            mission_id=mission_id,
            action=GoogleAction.GMAIL_SEND,
            payload=payload,
        )
        intent_key = build_action_intent_key(unsigned)
        authorization_id = _stable_id("gauth", state.profile.id, mission_id, event_id, draft.id)
        authorization_store = runtime.authorization_store
        existing_auth = authorization_store.get(state.profile.id, authorization_id)
        request = unsigned.model_copy(update={"standing_authorization_id": authorization_id})
        prior_receipt = runtime.receipt_store.get(state.profile.id, build_idempotency_key(request))
        if prior_receipt is not None and prior_receipt.status == "completed":
            return {
                "status": "recovered_existing",
                "sent": 0,
                "recovered": 1,
                "draft_id": draft.id,
                "receipt_id": prior_receipt.id,
                "provider_message_id": prior_receipt.resource_id,
                "authorization_id": prior_receipt.authorization_id,
                "recipient_is_patient_profile": True,
                "sender_is_connected_google_account": True,
                "diagnosis_claimed": False,
                "treatment_changed": False,
                "precise_location_disclosed": False,
            }

        if existing_auth is None:
            authorization_store.save(
                GoogleActionAuthorization(
                    id=authorization_id,
                    patient_id=state.profile.id,
                    mission_id=mission_id,
                    action=GoogleAction.GMAIL_SEND,
                    intent_key=intent_key,
                    one_time=True,
                    expires_at=None,
                )
            )
        elif not existing_auth.usable_for(
            patient_id=state.profile.id,
            mission_id=mission_id,
            action=GoogleAction.GMAIL_SEND,
            intent_key=intent_key,
        ):
            raise PermissionError("Guardian Gmail authorization is no longer usable for this exact event")

        receipt, outcome = runtime.guarded_executor.execute(request)
        if receipt.status != "completed":
            return {
                "status": f"blocked_{receipt.status}",
                "sent": 0,
                "recovered": 0,
                "draft_id": draft.id,
                "receipt_id": receipt.id,
                "safe_summary": receipt.safe_summary,
            }
        recovered = bool(outcome and outcome.recovered_existing)
        return {
            "status": "recovered_existing" if recovered else "sent",
            "sent": 0 if recovered else 1,
            "recovered": 1 if recovered else 0,
            "draft_id": draft.id,
            "receipt_id": receipt.id,
            "provider_message_id": receipt.resource_id,
            "authorization_id": receipt.authorization_id,
            "recipient_is_patient_profile": True,
            "sender_is_connected_google_account": True,
            "diagnosis_claimed": False,
            "treatment_changed": False,
            "precise_location_disclosed": False,
        }
