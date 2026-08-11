from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from healthia_one.config import Settings
from healthia_one.gmail_mission_events import GmailWatchState
from healthia_one.gmail_watch_runtime import GmailWatchManager, MemoryGmailWatchDirectory, epoch_ms
from healthia_one.google_connector_runtime import ConnectorResult, GoogleConnectorError
from healthia_one.google_constellation import GrantBundle, build_google_receipt
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_oauth_credentials import GoogleOAuthConnection


NOW = datetime(2026, 8, 10, 5, 0, tzinfo=timezone.utc)


class Guard:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        receipt = build_google_receipt(
            request,
            status="completed",
            resource_id="500",
            safe_summary="renewed",
        )
        return receipt, ConnectorResult(
            resource_id="500",
            safe_summary="renewed",
            data={"historyId": "500", "expiration": str(epoch_ms(NOW + timedelta(days=6)))},
            external_mutation=True,
        )


def manager():
    patient_id = "patient_scheduler"
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    service.runtime.oauth_connection_store.save(
        GoogleOAuthConnection(
            patient_id=patient_id,
            google_account="controlled@example.com",
            google_subject="subject-scheduler",
            granted_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            secret_version_resource="projects/test/secrets/oauth/versions/1",
        )
    )
    service.grant(patient_id, GrantBundle.GMAIL_READ_RELEVANT)
    guard = Guard()
    service.runtime.guarded_executor = guard
    watches = MemoryGmailWatchDirectory()
    watches.save(
        GmailWatchState(
            patient_id=patient_id,
            email_address="controlled@example.com",
            history_id="400",
            expiration_ms=epoch_ms(NOW + timedelta(minutes=10)),
        )
    )
    return GmailWatchManager(
        constellation=service,
        watch_store=watches,
        topic_name="projects/demo/topics/healthia-gmail",
    ), guard


def test_scheduler_schedule_time_becomes_guarded_action_idempotency_window():
    value, guard = manager()
    results = value.renew_due(now=NOW, renewal_window="2026-08-10T05:00:00Z")

    assert results == [("patient_scheduler", "renewed")]
    assert guard.calls[0].payload["renewal_window"] == "2026-08-10T05:00:00Z"


def test_scheduler_window_rejects_header_injection_before_google_call():
    value, guard = manager()
    with pytest.raises(GoogleConnectorError, match="window is invalid"):
        value.renew_due(now=NOW, renewal_window="2026-08-10T05:00:00Z\r\nX-Evil: 1")
    assert guard.calls == []


def test_live_scheduler_verifier_requires_explicit_mutation_flag_and_sanitized_receipt():
    source = Path("scripts/verify_gmail_scheduler_live.py").read_text("utf-8")
    assert "--confirmed-live-run" in source
    assert "patient_key" in source
    assert "secret_material_exposed" in source
    assert "email_address" not in source
    assert "cloudscheduler.googleapis.com/v1" in source
    assert ":run" in source
    assert "second_run_noop" in source
