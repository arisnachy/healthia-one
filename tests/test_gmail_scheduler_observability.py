import json
import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient

from healthia_one.gmail_push_worker import create_app


class Manager:
    def renew_due(self, *, renewal_window=None):
        assert renewal_window == "2026-08-10T05:00:00Z"
        return [("patient_secret_value", "renewed")]


def test_scheduler_operational_log_is_aggregate_only(caplog):
    runtime = SimpleNamespace(watch_manager=Manager())
    client = TestClient(create_app(lambda: runtime))
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post(
            "/scheduled/renew-gmail-watches",
            headers={
                "X-CloudScheduler-ScheduleTime": "2026-08-10T05:00:00Z",
                "X-CloudScheduler-JobName": "projects/demo/locations/us-central1/jobs/healthia-gmail-watch-renewal",
            },
        )
    assert response.status_code == 200
    event = next(json.loads(record.message) for record in caplog.records if "healthia_gmail_watch_scheduler" in record.message)
    assert event == {
        "event": "healthia_gmail_watch_scheduler",
        "processed_count": 1,
        "renewed_count": 1,
        "disabled_disconnected_count": 0,
        "scheduler_request_bound": True,
        "scheduler_job_bound": True,
    }
    rendered = json.dumps(event, sort_keys=True)
    assert "patient_secret_value" not in rendered
    assert "@" not in rendered
    assert "token" not in rendered.lower()
