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
        req = request.Request(
            url,
            data=encoded,
            method=method,
            headers={
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if encoded is not None else {}),
                **(headers or {}),
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except Exception as exc:
            raise GoogleConnectorError(f"Google API request failed: {type(exc).__name__}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise GoogleConnectorError("Google API returned a non-JSON response") from exc


class OAuthConnectorBase:
    service: GoogleService

    def __init__(self, access_token: str, transport: JsonTransport | None = None) -> None:
        self.access_token = access_token
        self.transport = transport or JsonTransport()

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


class CalendarConnector(OAuthConnectorBase):
    service = GoogleService.CALENDAR

    @staticmethod
    def _stable_event_id(idempotency_key: str) -> str:
        # Calendar event IDs accept base32hex-style lowercase letters/digits.
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
        return ConnectorResult(safe_summary=f"Loaded {len(connections)} authorized contact(s).", data=data)


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
            if marker not in notes:
                body["notes"] = (notes + "\n\n" + marker).strip()
            query = parse.quote(idempotency_key)
            existing = self.transport.call("GET", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks?showCompleted=true&showHidden=true&maxResults=100", headers=self.headers)
            for task in existing.get("items") or []:
                if idempotency_key in str(task.get("notes") or ""):
                    return ConnectorResult(resource_id=str(task.get("id") or ""), safe_summary="Recovered the existing Google task for this mission action.", data=task, external_mutation=True, recovered_existing=True)
            data = self.transport.call("POST", f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist}/tasks", headers=self.headers, body=body)
            return ConnectorResult(resource_id=str(data.get("id") or ""), safe_summary="Created the authorized Google task.", data=data, external_mutation=True)
        raise GoogleConnectorError(f"Unsupported Tasks action: {action}")


class RawGoogleExecutor:
    def __init__(self, connectors: list[GoogleConnector] | None = None) -> None:
        self.connectors: dict[GoogleService, GoogleConnector] = {
            connector.service: connector for connector in (connectors or [])
        }

    def execute(self, request: GoogleActionRequest, *, idempotency_key: str) -> ConnectorResult:
        connector = self.connectors.get(request.service)
        if connector is None:
            raise GoogleConnectorError(f"No connector registered for {request.service.value}")
        return connector.execute(request.action, request.payload, idempotency_key=idempotency_key)


class GuardedGoogleExecutor:
    def __init__(self, *, grant_store, receipt_store: ReceiptStore, raw_executor: RawGoogleExecutor, authorization_store=None) -> None:
        self.grant_store = grant_store
        self.receipt_store = receipt_store
        self.raw_executor = raw_executor
        self.authorization_store = authorization_store

    def execute(self, request: GoogleActionRequest) -> tuple[GoogleActionReceipt, ConnectorResult | None]:
        grants = self.grant_store.list_for_patient(request.patient_id)
        decision = authorize_google_action(request, grants)
        idempotency_key = build_idempotency_key(request)
        existing_receipt = self.receipt_store.get(request.patient_id, idempotency_key)
        if existing_receipt is not None and existing_receipt.status == "completed":
            return existing_receipt, ConnectorResult(
                resource_id=existing_receipt.resource_id,
                safe_summary=existing_receipt.safe_summary,
                evidence_ids=list(existing_receipt.evidence_ids),
                external_mutation=True,
                recovered_existing=True,
            )
        if not decision.allowed:
            receipt = build_google_receipt(request, decision, idempotency_key=idempotency_key)
            self.receipt_store.save(receipt)
            return receipt, None
        if decision.explicit_authorization_required:
            authorization_id = str(request.explicit_authorization_id or request.standing_authorization_id or "").strip()
            authorization = (
                self.authorization_store.get(request.patient_id, authorization_id)
                if self.authorization_store is not None and authorization_id
                else None
            )
            if authorization is None or not authorization.usable_for(
                patient_id=request.patient_id,
                mission_id=request.mission_id,
                action=request.action,
                intent_key=build_action_intent_key(request),
            ):
                receipt = build_google_receipt(
                    request,
                    decision.model_copy(update={"allowed": False, "reason": "External mutation authorization is missing, expired, already used, or does not match this exact intent."}),
                    idempotency_key=idempotency_key,
                )
                self.receipt_store.save(receipt)
                return receipt, None
            authorization_id = authorization.id
        else:
            authorization_id = ""
        result = self.raw_executor.execute(request, idempotency_key=idempotency_key)
        receipt = build_google_receipt(
            request,
            decision,
            idempotency_key=idempotency_key,
            resource_id=result.resource_id,
            status="completed",
            authorization_id=authorization_id,
            safe_summary=result.safe_summary,
            evidence_ids=result.evidence_ids,
        )
        self.receipt_store.save(receipt)
        if decision.explicit_authorization_required and self.authorization_store is not None and authorization_id:
            authorization.mark_used(receipt.id)
            self.authorization_store.save(authorization)
        return receipt, result
