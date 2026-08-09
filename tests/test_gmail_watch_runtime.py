from datetime import datetime, timedelta, timezone

import pytest

from healthia_one.config import Settings
from healthia_one.gmail_mission_events import GmailWatchState
from healthia_one.gmail_watch_runtime import GmailWatchManager, MemoryGmailWatchDirectory, epoch_ms
from healthia_one.google_connector_runtime import ConnectorResult, GoogleConnectorError
from healthia_one.google_constellation import GrantBundle, build_google_receipt
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_oauth_credentials import GoogleOAuthConnection


NOW = datetime(2026, 8, 9, 19, 0, tzinfo=timezone.utc)


class WatchGuard:
    def __init__(self, *, history_id="101", expiration_ms=None):
        self.calls = []
        self.history_id = history_id
        self.expiration_ms = expiration_ms or epoch_ms(NOW + timedelta(days=6))

    def execute(self, request):
        self.calls.append(request)
        receipt = build_google_receipt(
            request,
            status="completed",
            resource_id=self.history_id,
            safe_summary="Enabled Gmail push watch for the authorized mailbox scope.",
        )
        return receipt, ConnectorResult(
            resource_id=self.history_id,
            safe_summary=receipt.safe_summary,
            data={"historyId": self.history_id, "expiration": str(self.expiration_ms)},
            external_mutation=True,
        )


def service_with_connection(patient_id="patient_demo", mailbox="patient@example.com"):
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    service.runtime.oauth_connection_store.save(
        GoogleOAuthConnection(
            patient_id=patient_id,
            google_account=mailbox,
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            secret_version_resource="projects/test/secrets/oauth/versions/1",
        )
    )
    service.grant(patient_id, GrantBundle.GMAIL_READ_RELEVANT)
    return service


def test_watch_mailbox_is_bound_to_oauth_connection_not_caller_input():
    service = service_with_connection(mailbox="Actual.Patient@Example.com")
    watches = MemoryGmailWatchDirectory()
    guard = WatchGuard()
    service.runtime.guarded_executor = guard
    manager = GmailWatchManager(
        constellation=service,
        watch_store=watches,
        topic_name="projects/demo/topics/healthia-gmail",
    )

    watch, status = manager.ensure_watch("patient_demo", now=NOW)
    assert status == "renewed"
    assert watch.email_address == "actual.patient@example.com"
    assert watch.history_id == "101"
    assert watches.load_by_email("ACTUAL.PATIENT@example.com").patient_id == "patient_demo"
    assert guard.calls[0].payload["topic_name"] == "projects/demo/topics/healthia-gmail"
    assert guard.calls[0].payload["label_ids"] == ["INBOX"]


def test_watch_not_renewed_when_expiration_is_not_near():
    service = service_with_connection()
    watches = MemoryGmailWatchDirectory()
    watches.save(
        GmailWatchState(
            patient_id="patient_demo",
            email_address="patient@example.com",
            history_id="100",
            expiration_ms=epoch_ms(NOW + timedelta(days=3)),
        )
    )
    guard = WatchGuard()
    service.runtime.guarded_executor = guard
    manager = GmailWatchManager(
        constellation=service,
        watch_store=watches,
        topic_name="projects/demo/topics/healthia-gmail",
        renew_before_hours=24,
    )

    watch, status = manager.ensure_watch("patient_demo", now=NOW)
    assert status == "unchanged"
    assert watch.history_id == "100"
    assert guard.calls == []


def test_expiring_watch_is_renewed_without_mailbox_polling():
    service = service_with_connection()
    watches = MemoryGmailWatchDirectory()
    watches.save(
        GmailWatchState(
            patient_id="patient_demo",
            email_address="patient@example.com",
            history_id="100",
            expiration_ms=epoch_ms(NOW + timedelta(hours=2)),
        )
    )
    guard = WatchGuard(history_id="200")
    service.runtime.guarded_executor = guard
    manager = GmailWatchManager(
        constellation=service,
        watch_store=watches,
        topic_name="projects/demo/topics/healthia-gmail",
        renew_before_hours=24,
    )

    results = manager.renew_due(now=NOW)
    assert results == [("patient_demo", "renewed")]
    assert watches.load("patient_demo").history_id == "200"
    assert len(guard.calls) == 1
    assert guard.calls[0].payload["renewal_window"] == "2026-08-09"


def test_account_change_disables_old_cursor_before_new_watch():
    service = service_with_connection(mailbox="new@example.com")
    watches = MemoryGmailWatchDirectory()
    watches.save(
        GmailWatchState(
            patient_id="patient_demo",
            email_address="old@example.com",
            history_id="80",
            expiration_ms=epoch_ms(NOW + timedelta(days=2)),
        )
    )
    guard = WatchGuard(history_id="300")
    service.runtime.guarded_executor = guard
    manager = GmailWatchManager(
        constellation=service,
        watch_store=watches,
        topic_name="projects/demo/topics/healthia-gmail",
    )

    watch, status = manager.ensure_watch("patient_demo", now=NOW)
    assert status == "renewed"
    assert watch.email_address == "new@example.com"
    assert watch.history_id == "300"


def test_invalid_topic_fails_before_google_action():
    service = service_with_connection()
    guard = WatchGuard()
    service.runtime.guarded_executor = guard
    manager = GmailWatchManager(
        constellation=service,
        watch_store=MemoryGmailWatchDirectory(),
        topic_name="healthia-gmail",
    )
    with pytest.raises(GoogleConnectorError, match="full projects"):
        manager.ensure_watch("patient_demo", now=NOW)
    assert guard.calls == []
