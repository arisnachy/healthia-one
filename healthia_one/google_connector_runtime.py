from __future__ import annotations

import base64
import json
from email.message import EmailMessage
from typing import Any, Protocol
from urllib import parse, request

from pydantic import BaseModel, Field

from healthia_one.google_constellation import (
    GoogleAction,
    GoogleActionReceipt,
    GoogleActionRequest,
    GoogleGrant,
    GoogleService,
    authorize_google_action,
    build_google_receipt,
    build_idempotency_key,
)


class GoogleConnectorError(RuntimeError):
    pass


class AccessTokenProvider(Protocol):
    def access_token(self, patient_id: str, service: GoogleService) -> str:
        ...


class GoogleConnector(Protocol):
    service: GoogleService

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> "ConnectorResult":
        ...


class ReceiptStore(Protocol):
    def get(self, patient_id: str, idempotency_key: str) -> GoogleActionReceipt | None:
        ...

    def save(self, receipt: GoogleActionReceipt) -> None:
        ...


class ConnectorResult(BaseModel):
    resource_id: str = ""
    safe_summary: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    external_mutation: bool = False
    recovered_existing: bool = False


class MemoryReceiptStore:
    def __init__(self) -> None:
        self._values: dict[tuple[str, str], GoogleActionReceipt] = {}

    def get(self, patient_id: str, idempotency_key: str) -> GoogleActionReceipt | None:
        value = self._values.get((patient_id, idempotency_key))
        return value.model_copy(deep=True) if value else None

    def save(self, receipt: GoogleActionReceipt) -> None:
        self._values[(receipt.patient_id, receipt.idempotency_key)] = receipt.model_copy(deep=True)


class JsonTransport:
    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def call(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        merged = {"Accept": "application/json", **(headers or {})}
        if encoded is not None:
            merged.setdefault("Content-Type", "application/json")
        req = request.Request(url, data=encoded, headers=merged, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:  # pragma: no cover - live network
                raw = response.read()
        except Exception as exc:  # pragma: no cover - live network
            raise GoogleConnectorError(f"Google API request failed: {type(exc).__name__}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise GoogleConnectorError("Google API returned invalid JSON") from exc


def _bearer(token: str) -> dict[str, str]:
    if not token:
        raise GoogleConnectorError("Google OAuth access token is unavailable for this patient/service")
    return {"Authorization": f"Bearer {token}"}


class MapsConnector:
    service = GoogleService.MAPS

    def __init__(self, api_key: str, transport: JsonTransport | None = None) -> None:
        self.api_key = api_key
        self.transport = transport or JsonTransport()

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if not self.api_key:
            raise GoogleConnectorError("GOOGLE_MAPS_API_KEY is not configured")
        if action == GoogleAction.MAPS_SEARCH_NEARBY:
            lat = float(payload["lat"])
            lng = float(payload["lng"])
            radius = min(max(float(payload.get("radius_m", 5000)), 100), 50000)
            max_results = min(max(int(payload.get("max_results", 5)), 1), 20)
            field_mask = str(
                payload.get("field_mask")
                or "places.id,places.displayName,places.formattedAddress,places.location,places.googleMapsUri,places.websiteUri,places.nationalPhoneNumber"
            )
            body: dict[str, Any] = {
                "maxResultCount": max_results,
                "rankPreference": str(payload.get("rank_preference") or "DISTANCE"),
                "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius}},
            }
            included_types = [str(item) for item in payload.get("included_types", []) if str(item).strip()]
            if included_types:
                body["includedTypes"] = included_types[:50]
            result = self.transport.call(
                "POST",
                "https://places.googleapis.com/v1/places:searchNearby",
                headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": field_mask},
                body=body,
            )
            places = result.get("places") or []
            return ConnectorResult(
                safe_summary=f"Found {len(places)} nearby place candidate(s).",
                data={"places": places, "field_mask": field_mask},
            )
        if action == GoogleAction.MAPS_PLACE_DETAILS:
            place_id = str(payload["place_id"])
            fields = str(payload.get("fields") or "id,displayName,formattedAddress,location,googleMapsUri,websiteUri,nationalPhoneNumber,regularOpeningHours")
            url = f"https://places.googleapis.com/v1/places/{parse.quote(place_id, safe='')}?fields={parse.quote(fields, safe=',')}"
            result = self.transport.call("GET", url, headers={"X-Goog-Api-Key": self.api_key})
            return ConnectorResult(resource_id=place_id, safe_summary="Loaded selected place details.", data=result)
        if action == GoogleAction.MAPS_ROUTE:
            body = {
                "origin": {"location": {"latLng": {"latitude": float(payload["origin_lat"]), "longitude": float(payload["origin_lng"])}}},
                "destination": {"location": {"latLng": {"latitude": float(payload["destination_lat"]), "longitude": float(payload["destination_lng"])}}},
                "travelMode": str(payload.get("travel_mode") or "DRIVE"),
            }
            result = self.transport.call(
                "POST",
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline"},
                body=body,
            )
            return ConnectorResult(safe_summary="Calculated travel route.", data=result)
        raise GoogleConnectorError(f"Unsupported Maps action: {action}")


class OAuthConnectorBase:
    service: GoogleService

    def __init__(self, patient_id: str, token_provider: AccessTokenProvider, transport: JsonTransport | None = None) -> None:
        self.patient_id = patient_id
        self.token_provider = token_provider
        self.transport = transport or JsonTransport()

    @property
    def headers(self) -> dict[str, str]:
        return _bearer(self.token_provider.access_token(self.patient_id, self.service))


class CalendarConnector(OAuthConnectorBase):
    service = GoogleService.CALENDAR

    @staticmethod
    def _stable_event_id(idempotency_key: str) -> str:
        raw = bytes.fromhex(idempotency_key)
        return base64.b32hexencode(raw).decode("ascii").lower().rstrip("=")[:52]

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action == GoogleAction.CALENDAR_FREEBUSY:
            calendars = payload.get("calendar_ids") or [payload.get("calendar_id") or "primary"]
            body = {
                "timeMin": payload["time_min"],
                "timeMax": payload["time_max"],
                "timeZone": payload.get("time_zone"),
                "items": [{"id": str(item)} for item in calendars],
            }
            result = self.transport.call("POST", "https://www.googleapis.com/calendar/v3/freeBusy", headers=self.headers, body=body)
            return ConnectorResult(safe_summary="Checked calendar availability.", data=result)
        calendar_id = parse.quote(str(payload.get("calendar_id") or "primary"), safe="")
        if action == GoogleAction.CALENDAR_CREATE_EVENT:
            body = dict(payload.get("event") or {})
            body.setdefault("id", self._stable_event_id(idempotency_key))
            url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
            result = self.transport.call("POST", url, headers=self.headers, body=body)
            return ConnectorResult(
                resource_id=str(result.get("id") or body["id"]),
                safe_summary="Created the authorized calendar event.",
                data=result,
                external_mutation=True,
            )
        event_id = parse.quote(str(payload["event_id"]), safe="")
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}"
        if action == GoogleAction.CALENDAR_UPDATE_EVENT:
            result = self.transport.call("PATCH", url, headers=self.headers, body=dict(payload.get("event") or {}))
            return ConnectorResult(resource_id=event_id, safe_summary="Updated the authorized calendar event.", data=result, external_mutation=True)
        if action == GoogleAction.CALENDAR_CANCEL_EVENT:
            result = self.transport.call("DELETE", url, headers=self.headers)
            return ConnectorResult(resource_id=event_id, safe_summary="Cancelled the authorized calendar event.", data=result, external_mutation=True)
        raise GoogleConnectorError(f"Unsupported Calendar action: {action}")


class GmailConnector(OAuthConnectorBase):
    service = GoogleService.GMAIL

    @staticmethod
    def _message_id(idempotency_key: str) -> str:
        return f"<healthia-{idempotency_key[:32]}@healthia.one>"

    @staticmethod
    def _thread_evidence(data: dict[str, Any]) -> list[str]:
        thread_id = str(data.get("threadId") or "").strip()
        return [f"gmail_thread:{thread_id}"] if thread_id else []

    def _raw_message(self, payload: dict[str, Any], idempotency_key: str) -> str:
        msg = EmailMessage()
        msg["To"] = ", ".join(str(item) for item in payload.get("to", []))
        if payload.get("cc"):
            msg["Cc"] = ", ".join(str(item) for item in payload.get("cc", []))
        msg["Subject"] = str(payload.get("subject") or "HealthIA")
        msg["Message-ID"] = self._message_id(idempotency_key)
        if payload.get("in_reply_to"):
            msg["In-Reply-To"] = str(payload["in_reply_to"])
            msg["References"] = str(payload["in_reply_to"])
        msg.set_content(str(payload.get("body") or ""))
        return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    def _find_sent(self, idempotency_key: str) -> dict[str, Any] | None:
        query = parse.quote(f"in:sent rfc822msgid:{self._message_id(idempotency_key)}")
        data = self.transport.call("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={query}&maxResults=1", headers=self.headers)
        messages = data.get("messages") or []
        return messages[0] if messages else None

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action == GoogleAction.GMAIL_READ_THREAD:
            thread_id = parse.quote(str(payload["thread_id"]), safe="")
            data = self.transport.call("GET", f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}?format=full", headers=self.headers)
            return ConnectorResult(resource_id=thread_id, safe_summary="Loaded the mission-linked Gmail thread.", data=data)
        if action == GoogleAction.GMAIL_WATCH:
            topic = str(payload["topic_name"])
            body: dict[str, Any] = {"topicName": topic}
            if payload.get("label_ids"):
                body["labelIds"] = [str(item) for item in payload["label_ids"]]
                body["labelFilterBehavior"] = str(payload.get("label_filter_behavior") or "INCLUDE")
            data = self.transport.call("POST", "https://gmail.googleapis.com/gmail/v1/users/me/watch", headers=self.headers, body=body)
            return ConnectorResult(resource_id=str(data.get("historyId") or ""), safe_summary="Enabled Gmail push watch for the authorized mailbox scope.", data=data, external_mutation=True)
        raw = self._raw_message(payload, idempotency_key)
        if action == GoogleAction.GMAIL_DRAFT:
            data = self.transport.call("POST", "https://gmail.googleapis.com/gmail/v1/users/me/drafts", headers=self.headers, body={"message": {"raw": raw, **({"threadId": payload["thread_id"]} if payload.get("thread_id") else {})}})
            return ConnectorResult(resource_id=str(data.get("id") or ""), safe_summary="Created the Gmail draft.", data=data)
        if action in {GoogleAction.GMAIL_SEND, GoogleAction.GMAIL_REPLY}:
            existing = self._find_sent(idempotency_key)
            if existing:
                return ConnectorResult(
                    resource_id=str(existing.get("id") or ""),
                    safe_summary="Recovered an already-sent Gmail message for this mission action.",
                    evidence_ids=self._thread_evidence(existing),
                    data=existing,
                    external_mutation=True,
                    recovered_existing=True,
                )
            message: dict[str, Any] = {"raw": raw}
            if payload.get("thread_id"):
                message["threadId"] = str(payload["thread_id"])
            data = self.transport.call("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", headers=self.headers, body=message)
            return ConnectorResult(
                resource_id=str(data.get("id") or ""),
                safe_summary="Sent the authorized Gmail message.",
                evidence_ids=self._thread_evidence(data),
                data=data,
                external_mutation=True,
            )
        raise GoogleConnectorError(f"Unsupported Gmail action: {action}")


class PeopleConnector(OAuthConnectorBase):
    service = GoogleService.PEOPLE

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action not in {GoogleAction.PEOPLE_READ_CONTACTS, GoogleAction.PEOPLE_RESOLVE_CONTACT}:
            raise GoogleConnectorError(f"Unsupported People action: {action}")
        fields = str(payload.get("person_fields") or "names,emailAddresses,phoneNumbers,relations,metadata")
        page_size = min(max(int(payload.get("page_size", 100)), 1), 1000)
        url = f"https://people.googleapis.com/v1/people/me/connections?personFields={parse.quote(fields, safe=',')}&pageSize={page_size}"
        data = self.transport.call("GET", url, headers=self.headers)
        connections = data.get("connections") or []
        if action == GoogleAction.PEOPLE_RESOLVE_CONTACT:
            needle = str(payload.get("query") or "").strip().casefold()
            matches = []
            for person in connections:
                names = [str(item.get("displayName") or "") for item in person.get("names") or []]
                emails = [str(item.get("value") or "") for item in person.get("emailAddresses") or []]
                phones = [str(item.get("value") or "") for item in person.get("phoneNumbers") or []]
                haystack = " ".join([*names, *emails, *phones]).casefold()
                if needle and needle in haystack:
                    matches.append(person)
            return ConnectorResult(safe_summary=f"Found {len(matches)} contact candidate(s); no clinical family relationship was inferred.", data={"matches": matches})
        return ConnectorResult(safe_summary=f"Loaded {len(connections)} authorized contact(s); no clinical family relationship was inferred.", data=data)


class DriveConnector(OAuthConnectorBase):
    service = GoogleService.DRIVE

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        if action not in {GoogleAction.DRIVE_EXPORT_FILE, GoogleAction.DRIVE_UPDATE_EXPORT}:
            raise GoogleConnectorError(f"Unsupported Drive action: {action}")
        if action == GoogleAction.DRIVE_UPDATE_EXPORT:
            file_id = parse.quote(str(payload["file_id"]), safe="")
            data = self.transport.call("PATCH", f"https://www.googleapis.com/drive/v3/files/{file_id}", headers=self.headers, body=dict(payload.get("metadata") or {}))
            return ConnectorResult(resource_id=file_id, safe_summary="Updated the authorized Drive export metadata.", data=data, external_mutation=True)
        q = parse.quote(f"appProperties has {{ key='healthiaKey' and value='{idempotency_key}' }}")
        existing = self.transport.call("GET", f"https://www.googleapis.com/drive/v3/files?q={q}&fields=files(id,name,webViewLink)&pageSize=1", headers=self.headers)
        files = existing.get("files") or []
        if files:
            return ConnectorResult(resource_id=str(files[0].get("id") or ""), safe_summary="Recovered the existing Drive export for this mission action.", data=files[0], external_mutation=True, recovered_existing=True)
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("name", str(payload.get("name") or "HealthIA export"))
        metadata.setdefault("appProperties", {})["healthiaKey"] = idempotency_key
        data = self.transport.call("POST", "https://www.googleapis.com/drive/v3/files?fields=id,name,webViewLink", headers=self.headers, body=metadata)
        return ConnectorResult(resource_id=str(data.get("id") or ""), safe_summary="Created the authorized Drive export container.", data=data, external_mutation=True)


class TasksConnector(OAuthConnectorBase):
    service = GoogleService.TASKS

    def execute(self, action: GoogleAction, payload: dict[str, Any], *, idempotency_key: str) -> ConnectorResult:
        tasklist = parse.quote(str(payload.get("tasklist") or "@default"), safe="")
        if action == GoogleAction.TASKS_CREATE:
            body = dict(payload.get("task") or {})
            notes = str(body.get("notes") or "")
            marker = f"HealthIA-Key: {idempotency_key}"
            body["notes"] = f"{notes}\n\n{marker}".strip()
            data = self.transport.call("POST", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks", headers=self.headers, body=body)
            return ConnectorResult(resource_id=str(data.get("id") or ""), safe_summary="Created the authorized follow-up task.", data=data, external_mutation=True)
        task_id = parse.quote(str(payload["task_id"]), safe="")
        url = f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks/{task_id}"
        body = dict(payload.get("task") or {})
        if action == GoogleAction.TASKS_COMPLETE:
            body["status"] = "completed"
        if action in {GoogleAction.TASKS_UPDATE, GoogleAction.TASKS_COMPLETE}:
            data = self.transport.call("PATCH", url, headers=self.headers, body=body)
            return ConnectorResult(resource_id=task_id, safe_summary="Updated the authorized follow-up task.", data=data, external_mutation=True)
        raise GoogleConnectorError(f"Unsupported Tasks action: {action}")


class GoogleActionExecutor:
    def __init__(self, *, connectors: dict[GoogleService, GoogleConnector], receipt_store: ReceiptStore | None = None) -> None:
        self.connectors = connectors
        self.receipt_store = receipt_store or MemoryReceiptStore()

    def execute(self, request_value: GoogleActionRequest, grants: list[GoogleGrant]) -> tuple[GoogleActionReceipt, ConnectorResult | None]:
        decision = authorize_google_action(request_value, grants)
        key = build_idempotency_key(request_value)
        prior = self.receipt_store.get(request_value.patient_id, key)
        if prior and prior.status == "completed":
            return prior, ConnectorResult(resource_id=prior.resource_id, safe_summary=prior.safe_summary, recovered_existing=True)
        if not decision.allowed:
            receipt = build_google_receipt(request_value, status="blocked", safe_summary=decision.reason)
            self.receipt_store.save(receipt)
            return receipt, None
        connector = self.connectors.get(request_value.service)
        if connector is None:
            receipt = build_google_receipt(request_value, status="blocked", safe_summary=f"{request_value.service} connector is not configured.")
            self.receipt_store.save(receipt)
            return receipt, None
        try:
            outcome = connector.execute(request_value.action, request_value.payload, idempotency_key=key)
        except Exception as exc:
            receipt = build_google_receipt(request_value, status="failed", safe_summary=f"{request_value.service} action failed closed: {type(exc).__name__}.")
            self.receipt_store.save(receipt)
            raise
        receipt = build_google_receipt(
            request_value,
            status="completed",
            resource_id=outcome.resource_id,
            safe_summary=outcome.safe_summary,
            evidence_ids=outcome.evidence_ids,
        )
        self.receipt_store.save(receipt)
        return receipt, outcome
