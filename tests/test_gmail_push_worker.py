import base64
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from healthia_one.gmail_mission_events import GmailWatchState
from healthia_one.gmail_push_worker import create_app


def envelope(email="patient@example.com", history="101"):
    payload = json.dumps({"emailAddress": email, "historyId": history}).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return {"message": {"data": encoded, "messageId": "pubsub_1"}}


class Watches:
    def __init__(self, watch=None):
        self.watch = watch
        self.lookups = []

    def load_by_email(self, email):
        self.lookups.append(email)
        return self.watch


class Bridge:
    def __init__(self, missions=None, error=None):
        self.missions = missions or []
        self.error = error
        self.calls = []

    def process(self, patient_id, payload):
        self.calls.append((patient_id, payload))
        if self.error:
            raise self.error
        return self.missions


class Manager:
    def __init__(self):
        self.renew_calls = 0
        self.ensure_calls = []

    def renew_due(self):
        self.renew_calls += 1
        return [("patient_demo", "renewed")]

    def ensure_watch(self, patient_id, force=False):
        self.ensure_calls.append((patient_id, force))
        return (
            GmailWatchState(
                patient_id=patient_id,
                email_address="patient@example.com",
                history_id="200",
                expiration_ms=9999999999999,
            ),
            "renewed",
        )


def runtime(watch=None, *, bridge=None, manager=None):
    return SimpleNamespace(
        watch_store=Watches(watch),
        bridge=bridge or Bridge(),
        watch_manager=manager or Manager(),
    )


def test_malformed_pubsub_payload_is_acked_without_initializing_cloud_runtime():
    calls = []

    def forbidden_runtime():
        calls.append(True)
        raise AssertionError("malformed payload must be rejected before cloud clients initialize")

    client = TestClient(create_app(forbidden_runtime))
    response = client.post("/events/gmail-push", json={"message": {"data": ""}})
    assert response.status_code == 204
    assert calls == []


def test_unknown_mailbox_is_acked_without_reading_gmail_history():
    worker = runtime(watch=None)
    client = TestClient(create_app(lambda: worker))
    response = client.post("/events/gmail-push", json=envelope(email="unknown@example.com"))
    assert response.status_code == 204
    assert worker.watch_store.lookups == ["unknown@example.com"]
    assert worker.bridge.calls == []


def test_known_mailbox_routes_only_to_patient_bound_bridge():
    watch = GmailWatchState(
        patient_id="patient_demo",
        email_address="patient@example.com",
        history_id="100",
    )
    mission = SimpleNamespace(id="gmission_1")
    bridge = Bridge(missions=[mission])
    worker = runtime(watch=watch, bridge=bridge)
    client = TestClient(create_app(lambda: worker))

    response = client.post("/events/gmail-push", json=envelope())
    assert response.status_code == 200
    assert response.json() == {"status": "processed", "resumed_missions": ["gmission_1"], "count": 1}
    assert bridge.calls[0][0] == "patient_demo"


def test_transient_bridge_failure_returns_retryable_503_without_sensitive_detail():
    watch = GmailWatchState(
        patient_id="patient_demo",
        email_address="patient@example.com",
        history_id="100",
    )
    worker = runtime(watch=watch, bridge=Bridge(error=RuntimeError("secret mailbox detail")))
    client = TestClient(create_app(lambda: worker))

    response = client.post("/events/gmail-push", json=envelope())
    assert response.status_code == 503
    assert "RuntimeError" in response.json()["detail"]
    assert "secret mailbox detail" not in response.text


def test_private_scheduler_and_bootstrap_hooks_use_watch_manager_only():
    manager = Manager()
    worker = runtime(manager=manager)
    client = TestClient(create_app(lambda: worker))

    renewed = client.post("/scheduled/renew-gmail-watches")
    assert renewed.status_code == 200
    assert renewed.json()["renewed_count"] == 1
    assert manager.renew_calls == 1

    ensured = client.post("/internal/ensure-watch", json={"patient_id": "patient_demo", "force": True})
    assert ensured.status_code == 200
    assert ensured.json()["email_address"] == "patient@example.com"
    assert ensured.json()["secret_material_exposed"] is False
    assert manager.ensure_calls == [("patient_demo", True)]
