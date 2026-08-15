from __future__ import annotations

from typing import Any

from healthia_one.gmail_mission_events import (
    GmailHistoryReader,
    GmailPushNotification,
    GmailWatchStore,
    MissionResolver,
    ReplyInterpreter,
    decode_gmail_pubsub_push,
    utc_now,
)
from healthia_one.google_mission_runtime import GoogleHealthMissionCoordinator


class GmailCompositeEventBridge:
    """Advance one Gmail history cursor only after all HealthIA handlers succeed.

    Gmail watch/history is mailbox-scoped. HealthIA has two narrowly bounded
    consumers of that stream:

    * administrative Google missions (provider/benefit/appointment threads), and
    * Guardian emails sent to the patient for a specific durable HealthMission.

    Processing them in one bridge prevents either consumer from advancing the
    shared history cursor before the other has had a chance to inspect the same
    newly-added message. Unrelated mailbox threads remain ignored.
    """

    def __init__(
        self,
        *,
        watch_store: GmailWatchStore,
        mission_resolver: MissionResolver,
        coordinator: GoogleHealthMissionCoordinator,
        history_reader_factory,
        interpreter: ReplyInterpreter,
        guardian_reply_handler,
    ) -> None:
        self.watch_store = watch_store
        self.mission_resolver = mission_resolver
        self.coordinator = coordinator
        self.history_reader_factory = history_reader_factory
        self.interpreter = interpreter
        self.guardian_reply_handler = guardian_reply_handler

    @staticmethod
    def _validate_watch(patient_id: str, notification: GmailPushNotification, watch):
        if watch is None or not watch.enabled:
            raise PermissionError("No active Gmail watch is registered for this patient")
        if notification.email_address != watch.email_address.lower():
            raise PermissionError("Gmail push mailbox does not match the patient-authorized watch")
        if watch.patient_id != patient_id:
            raise PermissionError("Gmail watch patient boundary mismatch")

    async def process(self, patient_id: str, envelope: dict[str, Any]) -> list[Any]:
        notification = decode_gmail_pubsub_push(envelope)
        watch = self.watch_store.load(patient_id)
        self._validate_watch(patient_id, notification, watch)
        if int(notification.history_id) <= int(watch.history_id):
            return []

        reader: GmailHistoryReader = self.history_reader_factory(patient_id)
        changes, latest = reader.added_messages(watch.history_id)
        resumed: list[Any] = []
        seen_threads: set[str] = set()
        for change in changes:
            if change.thread_id in seen_threads:
                continue
            seen_threads.add(change.thread_id)
            thread = reader.thread(change.thread_id)

            administrative = self.mission_resolver.waiting_by_thread(patient_id, change.thread_id)
            if administrative is not None:
                signal = self.interpreter.interpret(
                    administrative,
                    thread,
                    message_id=change.message_id,
                    history_id=change.history_id or notification.history_id,
                )
                resumed.append(self.coordinator.ingest_gmail_reply(administrative, signal))
                continue

            guardian = await self.guardian_reply_handler.handle(
                patient_id,
                thread,
                message_id=change.message_id,
                history_id=change.history_id or notification.history_id,
                thread_id=change.thread_id,
            )
            if guardian is not None:
                resumed.append(guardian)

        # The cursor advances only after every mission-linked handler completes.
        # Any exception causes Pub/Sub/Cloud Run retry against the old cursor.
        watch.history_id = max(str(latest), notification.history_id, key=int)
        watch.updated_at = utc_now()
        self.watch_store.save(watch)
        return resumed
