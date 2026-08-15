from __future__ import annotations

from healthia_one.autopilot_events import MemoryEventOutboxStore
from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot
from healthia_one.autopilot_worker import process_outbox_event
from healthia_one.config import Settings
from healthia_one.fcm_registration import MemoryFCMRegistrationStore, build_registration
from healthia_one.google_connector_runtime import ConnectorResult
from healthia_one.google_constellation import GoogleAction
from healthia_one.guardian_delivery import (
    GuardianFCMConnector,
    GuardianPushDispatcher,
    MemoryGuardianDeliveryStore,
)
from healthia_one.opportunity_store import MemoryOpportunityStore
from healthia_one.service import seed_state


class FakeGuardianDispatcher:
    def __init__(self) -> None:
        self.calls = []

    def dispatch(self, state, *, event_id: str, mission_id: str):
        self.calls.append((state.profile.id, event_id, mission_id))
        return {"status": "completed", "sent": 1, "recovered": 0}


async def test_guardian_outbox_event_wakes_worker_and_dispatches_after_durable_processing() -> None:
    state = seed_state()
    outbox = MemoryEventOutboxStore()
    engine = OpportunityAutopilot(MemoryOpportunityStore())
    dispatcher = FakeGuardianDispatcher()
    event = AutopilotEvent(
        id="event_guardian_wake",
        patient_id=state.profile.id,
        event_type="patient_state_changed",
        payload={
            "source": "guardian_context",
            "mission_id": "mission_guardian_1",
            "notification_requested": True,
            "human_boundary": True,
        },
    )
    outbox.put(event)

    async def load_patient(patient_id):
        assert patient_id == state.profile.id
        return state

    first = await process_outbox_event(
        event.id,
        outbox_store=outbox,
        engine=engine,
        state_loader=load_patient,
        guardian_dispatcher=dispatcher,
    )
    second = await process_outbox_event(
        event.id,
        outbox_store=outbox,
        engine=engine,
        state_loader=load_patient,
        guardian_dispatcher=dispatcher,
    )

    assert first["status"] == "processed"
    assert first["guardian_delivery"]["sent"] == 1
    assert dispatcher.calls == [(state.profile.id, event.id, "mission_guardian_1")]
    assert second["status"] == "duplicate_processed"
    assert len(dispatcher.calls) == 1


class FakeAdcTokenProvider:
    def token(self, scopes):
        assert "https://www.googleapis.com/auth/firebase.messaging" in scopes
        return "adc-token"


class RecordingTransport:
    def __init__(self) -> None:
        self.calls = []

    def call(self, method, url, *, headers=None, body=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        return {"name": "projects/demo/messages/guardian-1"}


def test_guardian_fcm_is_data_only_phi_neutral_and_carries_stable_proof() -> None:
    transport = RecordingTransport()
    connector = GuardianFCMConnector(
        project_id="healthia-demo",
        token_provider=FakeAdcTokenProvider(),
        transport=transport,
    )
    result = connector.execute(
        GoogleAction.FCM_SEND_MISSION_NOTIFICATION,
        {
            "device_token": "device-token-value",
            "mission_id": "mission_1",
            "event_type": "guardian_update",
            "proof_id": "guardian:12345678",
        },
        idempotency_key="a" * 64,
    )

    message = transport.calls[0]["body"]["message"]
    assert "notification" not in message
    assert message["data"]["kind"] == "healthia_update"
    assert message["data"]["proof_id"] == "guardian:12345678"
    assert message["data"]["mission_id"] == "mission_1"
    assert result.resource_id.endswith("guardian-1")


class FakeFCMConnector:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, action, payload, *, idempotency_key):
        self.calls.append((action, dict(payload), idempotency_key))
        return ConnectorResult(
            resource_id="projects/demo/messages/1",
            safe_summary="sent",
            external_mutation=True,
        )


def test_guardian_push_requires_double_opt_in_and_recovers_receipt_on_redelivery() -> None:
    state = seed_state()
    state.consent.signal_types.append("guardian_push")
    registrations = MemoryFCMRegistrationStore()
    registrations.save(
        build_registration(
            patient_id=state.profile.id,
            connection_id="connection_1",
            device_id="device_1",
            registration_token="a-valid-registration-token-123",
        ),
        allow_reenable=True,
    )
    receipts = MemoryGuardianDeliveryStore()
    connector = FakeFCMConnector()
    dispatcher = GuardianPushDispatcher(
        Settings(store_backend="memory"),
        registrations=registrations,
        receipts=receipts,
        connector=connector,
    )

    first = dispatcher.dispatch(state, event_id="event_guardian_1", mission_id="mission_guardian_1")
    second = dispatcher.dispatch(state, event_id="event_guardian_1", mission_id="mission_guardian_1")

    assert first["sent"] == 1
    assert first["recovered"] == 0
    assert second["sent"] == 0
    assert second["recovered"] == 1
    assert len(connector.calls) == 1
    payload = connector.calls[0][1]
    assert payload["proof_id"].startswith("guardian:")
    assert payload["kind"] == "healthia_update"


def test_guardian_push_does_nothing_without_guardian_push_signal_opt_in() -> None:
    state = seed_state()
    dispatcher = GuardianPushDispatcher(
        Settings(store_backend="memory"),
        registrations=MemoryFCMRegistrationStore(),
        receipts=MemoryGuardianDeliveryStore(),
        connector=FakeFCMConnector(),
    )

    result = dispatcher.dispatch(state, event_id="event_guardian_2", mission_id="mission_guardian_2")

    assert result["status"] == "skipped_not_authorized"
    assert result["sent"] == 0
