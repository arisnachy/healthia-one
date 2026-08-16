from datetime import timedelta

from healthia_one.google_action_guard import GuardedGoogleActionExecutor
from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleActionRequest, GoogleGrant, GoogleService
from healthia_one.google_connector_runtime import ConnectorResult, GoogleActionExecutor
from healthia_one.google_constellation_store import (
    GoogleActionAuthorization,
    MemoryGoogleAuthorizationStore,
    MemoryGoogleGrantStore,
    MemoryGoogleReceiptStore,
    build_action_intent_key,
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


def request(auth_id: str, *, body: str = "Please advise.") -> GoogleActionRequest:
    return GoogleActionRequest(
        patient_id="patient_a",
        mission_id="mission_a",
        action=GoogleAction.GMAIL_SEND,
        payload={"to": ["center@example.org"], "subject": "Appointment", "body": body},
        explicit_authorization_id=auth_id,
    )


def authorization(auth_id: str, request_value: GoogleActionRequest, **overrides) -> GoogleActionAuthorization:
    values = {
        "id": auth_id,
        "patient_id": request_value.patient_id,
        "mission_id": request_value.mission_id,
        "action": request_value.action,
        "intent_key": build_action_intent_key(request_value),
    }
    values.update(overrides)
    return GoogleActionAuthorization(**values)


def test_nonexistent_authorization_id_is_not_a_permission():
    guard, connector, *_ = setup_guard()
    receipt, outcome = guard.execute(request("made_up_auth"))
    assert receipt.status == "blocked"
    assert outcome is None
    assert connector.calls == 0


def test_foreign_patient_or_mission_authorization_is_blocked():
    guard, connector, _, _, authorizations = setup_guard()
    req = request("auth_foreign")
    authorizations.save(
        authorization("auth_foreign", req, patient_id="patient_b")
    )
    receipt, _ = guard.execute(req)
    assert receipt.status == "blocked"
    assert connector.calls == 0

    req2 = request("auth_wrong_mission")
    authorizations.save(
        authorization("auth_wrong_mission", req2, mission_id="mission_b")
    )
    receipt2, _ = guard.execute(req2)
    assert receipt2.status == "blocked"
    assert connector.calls == 0


def test_expired_and_wrong_action_authorizations_are_blocked():
    guard, connector, _, _, authorizations = setup_guard()
    req = request("auth_expired")
    authorizations.save(
        authorization(
            "auth_expired",
            req,
            expires_at=utc_now() - timedelta(seconds=1),
        )
    )
    receipt, _ = guard.execute(req)
    assert receipt.status == "blocked"

    req2 = request("auth_calendar")
    authorizations.save(
        authorization(
            "auth_calendar",
            req2,
            action=GoogleAction.CALENDAR_CREATE_EVENT,
        )
    )
    receipt2, _ = guard.execute(req2)
    assert receipt2.status == "blocked"
    assert connector.calls == 0


def test_authorized_payload_cannot_be_changed_after_patient_approval():
    guard, connector, _, _, authorizations = setup_guard()
    approved = request("auth_exact", body="Please advise.")
    authorizations.save(authorization("auth_exact", approved))

    tampered = request("auth_exact", body="Send the entire medical record instead.")
    receipt, outcome = guard.execute(tampered)

    assert receipt.status == "blocked"
    assert outcome is None
    assert connector.calls == 0
    assert "exact action payload" in receipt.safe_summary


def test_one_time_authorization_is_consumed_after_success_but_completed_replay_is_safe():
    guard, connector, _, _, authorizations = setup_guard()
    req = request("auth_once")
    authorizations.save(
        authorization("auth_once", req, one_time=True)
    )
    first, outcome = guard.execute(req)
    assert first.status == "completed"
    assert outcome is not None
    assert connector.calls == 1
    consumed = authorizations.get("patient_a", "auth_once")
    assert consumed is not None and consumed.consumed_at is not None

    second, recovered = guard.execute(req)
    assert second.idempotency_key == first.idempotency_key
    assert recovered is not None and recovered.recovered_existing is True
    assert connector.calls == 1
