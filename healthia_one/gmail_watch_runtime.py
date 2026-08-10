from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Protocol

from healthia_one.gmail_mission_events import (
    FirestoreGmailWatchStore,
    GmailWatchState,
    MemoryGmailWatchStore,
)
from healthia_one.google_connector_runtime import GoogleConnectorError
from healthia_one.google_constellation import GoogleAction, GoogleActionRequest
from healthia_one.google_constellation_runtime import GoogleConstellationService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def epoch_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


class GmailWatchDirectory(Protocol):
    def load(self, patient_id: str) -> GmailWatchState | None: ...
    def save(self, state: GmailWatchState) -> None: ...
    def load_by_email(self, email_address: str) -> GmailWatchState | None: ...
    def expiring_before(self, cutoff_ms: int) -> list[GmailWatchState]: ...


class MemoryGmailWatchDirectory(MemoryGmailWatchStore):
    def load_by_email(self, email_address: str) -> GmailWatchState | None:
        needle = str(email_address or "").strip().lower()
        matches = [
            value
            for value in self._values.values()
            if value.enabled and value.email_address.strip().lower() == needle
        ]
        if len(matches) > 1:
            raise RuntimeError("Multiple patient Gmail watches are bound to the same mailbox")
        return matches[0].model_copy(deep=True) if matches else None

    def expiring_before(self, cutoff_ms: int) -> list[GmailWatchState]:
        result = []
        for value in self._values.values():
            if not value.enabled:
                continue
            if value.expiration_ms is None or int(value.expiration_ms) <= int(cutoff_ms):
                result.append(value.model_copy(deep=True))
        return sorted(result, key=lambda item: (item.expiration_ms or 0, item.patient_id))


class FirestoreGmailWatchDirectory(FirestoreGmailWatchStore):
    def load_by_email(self, email_address: str) -> GmailWatchState | None:
        needle = str(email_address or "").strip().lower()
        query = (
            self.client.collection(self.COLLECTION)
            .where("email_address", "==", needle)
            .where("enabled", "==", True)
            .limit(2)
        )
        matches = [GmailWatchState.model_validate(item.to_dict()) for item in query.stream()]
        if len(matches) > 1:
            raise RuntimeError("Multiple patient Gmail watches are bound to the same mailbox")
        return matches[0] if matches else None

    def expiring_before(self, cutoff_ms: int) -> list[GmailWatchState]:
        # Query only enabled operational watch metadata, then filter expiration
        # client-side to avoid requiring a composite Firestore index for a small
        # once-daily renewal scan. No message content or clinical state is read.
        query = self.client.collection(self.COLLECTION).where("enabled", "==", True)
        values = [GmailWatchState.model_validate(item.to_dict()) for item in query.stream()]
        result = [
            item
            for item in values
            if item.expiration_ms is None or int(item.expiration_ms) <= int(cutoff_ms)
        ]
        return sorted(result, key=lambda item: (item.expiration_ms or 0, item.patient_id))


def build_gmail_watch_directory(settings) -> GmailWatchDirectory:
    if settings.store_backend == "firestore":
        return FirestoreGmailWatchDirectory(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None)
    return MemoryGmailWatchDirectory()


class GmailWatchManager:
    """Create/renew Gmail push watches without polling the mailbox.

    The mailbox identity comes from the patient's enabled OAuth connection, not
    from a caller-provided email. The read-relevant HealthIA grant and OAuth Gmail
    scope remain independently enforced by the existing Google action guard/token
    provider. `renewal_window` changes the idempotency fingerprint but is ignored
    by the Gmail connector payload sent to Google.
    """

    def __init__(
        self,
        *,
        constellation: GoogleConstellationService,
        watch_store: GmailWatchDirectory,
        topic_name: str,
        renew_before_hours: int = 24,
    ) -> None:
        self.constellation = constellation
        self.watch_store = watch_store
        self.topic_name = str(topic_name or "").strip()
        self.renew_before_hours = min(max(int(renew_before_hours), 1), 72)

    def _mailbox(self, patient_id: str) -> str:
        connection = self.constellation.runtime.oauth_connection_store.load(patient_id)
        if connection is None or not connection.enabled:
            raise GoogleConnectorError("Google account is not connected for this patient")
        mailbox = str(connection.google_account or "").strip().lower()
        if not mailbox or "@" not in mailbox:
            raise GoogleConnectorError("Connected Google account has no usable mailbox identity")
        return mailbox

    def due(self, watch: GmailWatchState | None, *, now: datetime | None = None) -> bool:
        if watch is None or not watch.enabled or watch.expiration_ms is None:
            return True
        current = now or utc_now()
        cutoff = current + timedelta(hours=self.renew_before_hours)
        return int(watch.expiration_ms) <= epoch_ms(cutoff)

    def ensure_watch(
        self,
        patient_id: str,
        *,
        force: bool = False,
        now: datetime | None = None,
    ) -> tuple[GmailWatchState, str]:
        if not self.topic_name.startswith("projects/") or "/topics/" not in self.topic_name:
            raise GoogleConnectorError("Gmail Pub/Sub topic must be a full projects/.../topics/... resource")
        current = now or utc_now()
        mailbox = self._mailbox(patient_id)
        existing = self.watch_store.load(patient_id)
        if existing and existing.email_address.strip().lower() != mailbox:
            # Account changed: never reuse an old mailbox cursor for a new account.
            existing.enabled = False
            existing.updated_at = current
            self.watch_store.save(existing)
            existing = None
        if not force and not self.due(existing, now=current):
            return existing, "unchanged"

        # Scheduled daily renewal remains idempotent for the day. An explicit
        # force is an operator repair and must reach Gmail instead of recovering
        # a stale daily receipt that may move the history cursor backwards.
        renewal_window = (
            current.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            if force
            else current.strftime("%Y-%m-%d")
        )
        request_value = GoogleActionRequest(
            patient_id=patient_id,
            mission_id=f"gmail_watch:{patient_id}",
            action=GoogleAction.GMAIL_WATCH,
            payload={
                "topic_name": self.topic_name,
                "label_ids": ["INBOX"],
                "label_filter_behavior": "INCLUDE",
                "renewal_window": renewal_window,
            },
        )
        receipt, outcome = self.constellation.runtime.guarded_executor.execute(request_value)
        if receipt.status != "completed" or outcome is None:
            raise GoogleConnectorError(receipt.safe_summary or "Gmail watch renewal was blocked")

        data = outcome.data or {}
        history_id = str(data.get("historyId") or receipt.resource_id or "").strip()
        expiration_raw = data.get("expiration")
        expiration_ms = int(expiration_raw) if str(expiration_raw or "").isdigit() else None
        if not history_id.isdigit():
            raise GoogleConnectorError("Gmail watch returned no valid historyId")
        if expiration_ms is None:
            # A completed idempotent replay may not carry connector body data.
            # Keep the watch valid for event processing but mark expiration unknown
            # so the next scheduler window retries rather than pretending longevity.
            expiration_ms = None

        watch = GmailWatchState(
            patient_id=patient_id,
            email_address=mailbox,
            history_id=history_id,
            expiration_ms=expiration_ms,
            enabled=True,
            updated_at=current,
        )
        self.watch_store.save(watch)
        return watch, "renewed"

    def renew_due(self, *, now: datetime | None = None) -> list[tuple[str, str]]:
        current = now or utc_now()
        cutoff = epoch_ms(current + timedelta(hours=self.renew_before_hours))
        results: list[tuple[str, str]] = []
        for watch in self.watch_store.expiring_before(cutoff):
            connection = self.constellation.runtime.oauth_connection_store.load(watch.patient_id)
            mailbox = str(connection.google_account or "").strip().lower() if connection else ""
            if connection is None or not connection.enabled or mailbox != watch.email_address.strip().lower():
                # Disconnect/account switch is a terminal state for the old watch,
                # not a scheduler-wide retry condition. Disable metadata without
                # touching Gmail or Secret Manager.
                watch.enabled = False
                watch.updated_at = current
                self.watch_store.save(watch)
                results.append((watch.patient_id, "disabled_disconnected"))
                continue
            # The directory already selected only due watches, so the scheduled
            # path can retain its daily idempotency key. `force=True` is reserved
            # for an explicit operator repair.
            renewed, status = self.ensure_watch(watch.patient_id, force=False, now=current)
            results.append((renewed.patient_id, status))
        return results
