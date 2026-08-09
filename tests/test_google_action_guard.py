from datetime import timedelta

from healthia_one.google_action_guard import GuardedGoogleActionExecutor
from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleActionRequest, GoogleGrant, GoogleService
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor
from healthia_one.google_constellation_store import (
    GoogleActionAuthorization,
    MemoryGoogleAuthorizationStore,
    MemoryGoogleGrantStore,
    MemoryGoogleReceiptStore,
    utc_now,
)


class SendConnector:
    service = GoogleService.GMAIL

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, action, payload, *, idempotency_key):
        self.calls += 1
        return ConnectorResult(
            resource_id="msg_1",
            safe_summary="Sent authorized Gmail message.",
            data={"id": "msg_1", "threadId": "thread_1"},
            external_mutation=True,
        )


def setup_guard():
    connector = SendConnector()
    grants = MemoryGoogleGrantStore()
    receipts = MemoryGoogleReceiptStore()
    authorizations = MemoryGoogleAuthorizationStore()
    raw = GoogleActionExecutor(connectors={GoogleService.GMAIL: connector}, receipt_store=receipts)
    guard = GuardedGoogleActionExecutor(
        executor=raw,
        grant_store=grants,
        authorization_store=authorizations,
        receipt_store=receipts,
    )
    grants.save(GoogleGrant(patient_id="patient_a", bundle=GrantBundle.GMAIL_SEND))
    return guard, connector, grants, receipts, authorizations


def request(auth_id: str) -> GoogleActionRequest:
    return GoogleActionRequest(
        patient_id="patient_a",
        mission_id="mission_a",
        action=GoogleAction.GMAIL_SEND,
        payload={"to": ["center@example.org"], "subject": "Appointment", "body": "Please advise."},
        explicit_authorization_id=auth_id,
    )


def test_nonexistent_authorization_id_is_not_a_permission():
    guard, connector, *_ = setup_guard()
    receipt, outcome = guard.execute(request("made_up_auth"))
    assert receipt.status == "blocked"
    assert outcome is None
    assert connector.calls == 0


def test_foreign_patient_or_mission_authorization_is_blocked():
    guard, connector, _, _, authorizations = setup_guard()
    auth = GoogleActionAuthorization(
        id="auth_foreign",
        patient_id="patient_b",
        mission_id="mission_a",
        action=GoogleAction.GMAIL_SEND,
    )
    authorizations.save(auth)
    receipt, _ = guard.execute(request("auth_foreign"))
    assert receipt.status == "blocked"
    assert connector.calls == 0

    auth2 = GoogleActionAuthorization(
        id="auth_wrong_mission",
        patient_id="patient_a",
        mission_id="mission_b",
        action=GoogleAction.GMAIL_SEND,
    )
    authorizations.save(auth2)
    receipt2, _ = guard.execute(request("auth_wrong_mission"))
    assert receipt2.status == "blocked"
    assert connector.calls == 0


def test_expired_and_wrong_action_authorizations_are_blocked():
    guard, connector, _, _, authorizations = setup_guard()
    authorizations.save(
        GoogleActionAuthorization(
            id="auth_expired",
            patient_id="patient_a",
            mission_id="mission_a",
            action=GoogleAction.GMAIL_SEND,
            expires_at=utc_now() - timedelta(seconds=1),
        )
    )
    receipt, _ = guard.execute(request("auth_expired"))
    assert receipt.status == "blocked"

    authorizations.save(
        GoogleActionAuthorization(
            id="auth_calendar",
            patient_id="patient_a",
            mission_id="mission_a",
            action=GoogleAction.CALENDAR_CREATE_EVENT,
        )
    )
    receipt2, _ = guard.execute(request("auth_calendar"))
    assert receipt2.status == "blocked"
    assert connector.calls == 0


def test_one_time_authorization_is_consumed_after_success_but_completed_replay_is_safe():
    guard, connector, _, _, authorizations = setup_guard()
    authorizations.save(
        GoogleActionAuthorization(
            id="auth_once",
            patient_id="patient_a",
            mission_id="mission_a",
            action=GoogleAction.GMAIL_SEND,
            one_time=True,
        )
    )
    first, outcome = guard.execute(request("auth_once"))
    assert first.status == "completed"
    assert outcome is not None
    assert connector.calls == 1
    consumed = authorizations.get("patient_a", "auth_once")
    assert consumed is not None and consumed.consumed_at is not None

    # Same mission action replays the durable receipt before re-consuming auth.
    second, recovered = guard.execute(request("auth_once"))
    assert second.idempotency_key == first.idempotency_key
    assert recovered is not None and recovered.recovered_existing is True
    assert connector.calls == 1
