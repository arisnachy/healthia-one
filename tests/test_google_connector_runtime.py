import base64
from email import message_from_bytes

from healthia_one.google_constellation import GoogleAction, GoogleService
from healthia_one.google_connector_runtime import CalendarConnector, GmailConnector, MapsConnector


class FakeTokenProvider:
    def access_token(self, patient_id: str, service: GoogleService) -> str:
        assert patient_id == "patient_demo"
        return "token"


class RecordingTransport:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def call(self, method, url, *, headers=None, body=None):
        self.calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        return self.responses.pop(0) if self.responses else {}


def test_maps_nearby_uses_bounded_radius_and_explicit_field_mask():
    transport = RecordingTransport([{"places": [{"id": "p1"}]}])
    connector = MapsConnector("maps-key", transport=transport)
    result = connector.execute(
        GoogleAction.MAPS_SEARCH_NEARBY,
        {"lat": 19.45, "lng": -70.69, "radius_m": 999999, "max_results": 99},
        idempotency_key="a" * 64,
    )
    call = transport.calls[0]
    assert call["url"].endswith("places:searchNearby")
    assert call["body"]["locationRestriction"]["circle"]["radius"] == 50000
    assert call["body"]["maxResultCount"] == 20
    assert "X-Goog-FieldMask" in call["headers"]
    assert result.data["places"][0]["id"] == "p1"


def test_calendar_create_uses_same_provider_event_id_for_same_action_key():
    transport = RecordingTransport([{}, {}])
    connector = CalendarConnector("patient_demo", FakeTokenProvider(), transport=transport)
    key = "ab" * 32
    payload = {
        "calendar_id": "primary",
        "event": {
            "summary": "Support appointment",
            "start": {"dateTime": "2026-08-12T10:00:00-04:00"},
            "end": {"dateTime": "2026-08-12T11:00:00-04:00"},
        },
    }
    first = connector.execute(GoogleAction.CALENDAR_CREATE_EVENT, payload, idempotency_key=key)
    second = connector.execute(GoogleAction.CALENDAR_CREATE_EVENT, payload, idempotency_key=key)
    first_id = transport.calls[0]["body"]["id"]
    second_id = transport.calls[1]["body"]["id"]
    assert first_id == second_id == first.resource_id == second.resource_id
    assert len(first_id) <= 52


def test_gmail_send_recovers_existing_sent_message_before_duplicate_send():
    transport = RecordingTransport([
        {"messages": [{"id": "already_sent", "threadId": "thread_x"}]},
    ])
    connector = GmailConnector("patient_demo", FakeTokenProvider(), transport=transport)
    result = connector.execute(
        GoogleAction.GMAIL_SEND,
        {"to": ["center@example.org"], "subject": "Appointment", "body": "Please advise."},
        idempotency_key="cd" * 32,
    )
    assert result.recovered_existing is True
    assert result.resource_id == "already_sent"
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert "rfc822msgid" in transport.calls[0]["url"]


def test_gmail_send_embeds_stable_message_id_when_not_previously_sent():
    transport = RecordingTransport([
        {"messages": []},
        {"id": "sent_1", "threadId": "thread_1"},
    ])
    connector = GmailConnector("patient_demo", FakeTokenProvider(), transport=transport)
    key = "ef" * 32
    connector.execute(
        GoogleAction.GMAIL_SEND,
        {"to": ["center@example.org"], "subject": "Appointment", "body": "Please advise."},
        idempotency_key=key,
    )
    send_body = transport.calls[1]["body"]
    raw = base64.urlsafe_b64decode(send_body["raw"].encode("ascii"))
    message = message_from_bytes(raw)
    assert message["Message-ID"] == f"<healthia-{key[:32]}@healthia.one>"
    assert transport.calls[1]["url"].endswith("/messages/send")
