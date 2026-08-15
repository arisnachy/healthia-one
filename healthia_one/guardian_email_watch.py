from __future__ import annotations

import hashlib
import os
from typing import Callable

from pydantic import BaseModel

from healthia_one.gmail_watch_runtime import GmailWatchManager, build_gmail_watch_directory
from healthia_one.google_connector_runtime import GoogleConnectorError
from healthia_one.google_constellation import GrantBundle, GoogleGrant
from healthia_one.guardian_email_reply import GUARDIAN_EMAIL_REPLY_CONSENT
from healthia_one.models import PatientState


class GuardianReplyWatchStatus(BaseModel):
    ready: bool
    status: str
    mailbox: str = ""
    history_id: str = ""
    expiration_ms: int | None = None


def _stable_grant_id(patient_id: str) -> str:
    digest = hashlib.sha256(f"{patient_id}|guardian_email_replies|gmail_watch".encode("utf-8")).hexdigest()[:24]
    return f"grant_{digest}"


def _has_gmail_read_scope(scopes: list[str]) -> bool:
    normalized = {str(item or "").strip().lower() for item in scopes}
    return any(
        scope in normalized
        for scope in {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://mail.google.com/",
        }
    )


def ensure_guardian_reply_watch(settings, constellation, state: PatientState) -> GuardianReplyWatchStatus:
    """Ensure the event-driven Gmail return channel is operational.

    The patient has already opted into Guardian email replies. This function
    still requires an enabled Google connection with a read-capable Gmail OAuth
    scope and a configured Pub/Sub topic. It grants only the existing
    ``gmail_watch:<patient>`` capability and never reads mailbox content itself.

    Failure is returned as a capability status rather than silently promising a
    reply path that cannot receive events. Callers may still send a normal
    one-way Guardian email, but must omit reply instructions unless ``ready``.
    """
    if GUARDIAN_EMAIL_REPLY_CONSENT not in set(state.consent.signal_types):
        return GuardianReplyWatchStatus(ready=False, status="not_consented")

    runtime = constellation.runtime
    connection = runtime.oauth_connection_store.load(state.profile.id)
    if connection is None or not connection.enabled:
        return GuardianReplyWatchStatus(ready=False, status="google_account_not_connected")
    if not _has_gmail_read_scope(connection.granted_scopes):
        return GuardianReplyWatchStatus(ready=False, status="gmail_read_scope_missing")

    topic_name = os.getenv("HEALTHIA_GMAIL_PUBSUB_TOPIC", "").strip()
    if not topic_name.startswith("projects/") or "/topics/" not in topic_name:
        return GuardianReplyWatchStatus(ready=False, status="gmail_pubsub_topic_not_configured")
    if settings.store_backend != "firestore":
        # The production Gmail worker and dispatcher must share the same durable
        # watch directory. Local memory mode cannot prove that cross-process fact.
        return GuardianReplyWatchStatus(ready=False, status="durable_watch_store_required")

    watch_mission_id = f"gmail_watch:{state.profile.id}"
    existing = next(
        (
            grant
            for grant in runtime.grant_store.list_for_patient(state.profile.id)
            if grant.bundle == GrantBundle.GMAIL_READ_RELEVANT
            and grant.is_active_for(state.profile.id, watch_mission_id)
        ),
        None,
    )
    if existing is None:
        runtime.grant_store.save(
            GoogleGrant(
                id=_stable_grant_id(state.profile.id),
                patient_id=state.profile.id,
                bundle=GrantBundle.GMAIL_READ_RELEVANT,
                enabled=True,
                mission_id=watch_mission_id,
            )
        )

    manager = GmailWatchManager(
        constellation=constellation,
        watch_store=build_gmail_watch_directory(settings),
        topic_name=topic_name,
        renew_before_hours=24,
    )
    try:
        watch, status = manager.ensure_watch(state.profile.id)
    except GoogleConnectorError as exc:
        return GuardianReplyWatchStatus(
            ready=False,
            status=f"watch_not_ready:{type(exc).__name__}",
            mailbox=str(connection.google_account or "").strip().lower(),
        )
    return GuardianReplyWatchStatus(
        ready=True,
        status=status,
        mailbox=watch.email_address,
        history_id=watch.history_id,
        expiration_ms=watch.expiration_ms,
    )
