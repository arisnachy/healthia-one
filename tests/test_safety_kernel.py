from datetime import timedelta

import pytest

from healthia_one.google_constellation import GoogleAction, GoogleActionRequest, build_idempotency_key
from healthia_one.safety_kernel import HealthIASafetyKernel, MemoryHealthActionTicketStore, utc_now


def _request(*, body: str = "hello") -> GoogleActionRequest:
    return GoogleActionRequest(
        patient_id="patient_a",
        mission_id="mission_a",
        action=GoogleAction.GMAIL_SEND,
        payload={"to": ["center@example.org"], "subject": "Follow-up", "body": body},
        explicit_authorization_id="auth_a",
    )


def test_ticket_is_exact_intent_and_one_time():
    store = MemoryHealthActionTicketStore()
    kernel = HealthIASafetyKernel(store)
    req = _request()
    key = build_idempotency_key(req)

    ticket = kernel.issue(req, authorization_id="auth_a", idempotency_key=key)
    consumed = kernel.consume(ticket, req, idempotency_key=key)

    assert consumed.consumed_at is not None
    assert consumed.patient_id == "patient_a"
    assert consumed.mission_id == "mission_a"
    with pytest.raises(PermissionError, match="already consumed"):
        kernel.consume(ticket, req, idempotency_key=key)


def test_ticket_cannot_authorize_tampered_payload():
    store = MemoryHealthActionTicketStore()
    kernel = HealthIASafetyKernel(store)
    approved = _request(body="hello")
    ticket = kernel.issue(
        approved,
        authorization_id="auth_a",
        idempotency_key=build_idempotency_key(approved),
    )
    tampered = _request(body="send the entire record")

    with pytest.raises(PermissionError, match="intent mismatch"):
        kernel.consume(ticket, tampered, idempotency_key=build_idempotency_key(approved))


def test_expired_ticket_fails_closed():
    store = MemoryHealthActionTicketStore()
    kernel = HealthIASafetyKernel(store)
    req = _request()
    key = build_idempotency_key(req)
    ticket = kernel.issue(req, authorization_id="auth_a", idempotency_key=key)
    stored = store.get(ticket.patient_id, ticket.id)
    assert stored is not None
    stored.expires_at = utc_now() - timedelta(seconds=1)
    store.save(stored)

    with pytest.raises(PermissionError, match="expired"):
        kernel.consume(stored, req, idempotency_key=key)


def test_mutating_action_requires_patient_authorization_before_ticket():
    store = MemoryHealthActionTicketStore()
    kernel = HealthIASafetyKernel(store)
    req = _request()

    with pytest.raises(PermissionError, match="explicit action authorization"):
        kernel.issue(req, authorization_id="", idempotency_key=build_idempotency_key(req))


def test_ticket_links_trace_attempt_and_connector_receipt_without_conflating_them():
    store = MemoryHealthActionTicketStore()
    kernel = HealthIASafetyKernel(store)
    req = _request()
    key = build_idempotency_key(req)
    trace_id = "0123456789abcdef0123456789abcdef"
    ticket = kernel.issue(
        req,
        authorization_id="auth_a",
        idempotency_key=key,
        trace_id=trace_id,
    )
    kernel.consume(ticket, req, idempotency_key=key)

    linked = kernel.record_outcome(ticket, receipt_id="receipt_123", status="completed")
    assert linked.trace_id == trace_id
    assert linked.id != linked.receipt_id
    assert linked.receipt_id == "receipt_123"
    assert linked.outcome_status == "completed"
    assert linked.status == "consumed"


def test_ticket_rejects_noncanonical_trace_id():
    store = MemoryHealthActionTicketStore()
    kernel = HealthIASafetyKernel(store)
    req = _request()

    with pytest.raises(ValueError, match="32-hex trace id"):
        kernel.issue(
            req,
            authorization_id="auth_a",
            idempotency_key=build_idempotency_key(req),
            trace_id="not-a-trace",
        )
