from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from healthia_one.google_action_guard import GuardedGoogleActionExecutor, GuardedMissionExecutorAdapter
from healthia_one.google_clinical_cloud_connectors import (
    DocumentAIConnector,
    FCMConnector,
    HealthcareConnector,
    ServerAdcTokenProvider,
    SpeechConnector,
    TextToSpeechConnector,
    VeoConnector,
)
from healthia_one.google_connector_runtime import (
    CalendarConnector,
    DriveConnector,
    GmailConnector,
    GoogleActionExecutor,
    PeopleConnector,
    TasksConnector,
)
from healthia_one.google_constellation import GrantBundle, GoogleAction, GoogleActionRequest, GoogleGrant, GoogleService
from healthia_one.google_constellation_store import (
    FirestoreGoogleAuthorizationStore,
    FirestoreGoogleGrantStore,
    FirestoreGoogleReceiptStore,
    GoogleActionAuthorization,
    MemoryGoogleAuthorizationStore,
    MemoryGoogleGrantStore,
    MemoryGoogleReceiptStore,
    build_action_intent_key,
    utc_now,
)
from healthia_one.google_maps_connector import HealthIAMapsConnector
from healthia_one.google_mission_actions import calendar_event_payload, followup_task_payload, provider_contact_payload
from healthia_one.google_mission_runtime import FirestoreMissionStore, GoogleHealthMission, GoogleHealthMissionCoordinator, MemoryMissionStore
from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator
from healthia_one.google_oauth_credentials import FirestoreOAuthConnectionStore, MemoryOAuthConnectionStore, SecretManagerOAuthTokenProvider


_CURRENT_GOOGLE_PATIENT: ContextVar[str] = ContextVar("healthia_google_patient", default="")


@dataclass
class GoogleConstellationRuntime:
    coordinator: GoogleHealthMissionCoordinator
    grant_store: object
    receipt_store: object
    authorization_store: object
    oauth_connection_store: object
    raw_executor: GoogleActionExecutor
    guarded_executor: GuardedGoogleActionExecutor


class GoogleConstellationService:
    def __init__(self, runtime: GoogleConstellationRuntime) -> None:
        self.runtime = runtime
        self.coordinator = runtime.coordinator

    def load_mission(self, patient_id: str, mission_id: str) -> GoogleHealthMission:
        mission = self.coordinator.store.load(patient_id, mission_id)
        if mission is None:
            raise KeyError(mission_id)
        if mission.patient_id != patient_id:
            raise PermissionError("Google mission does not belong to this patient")
        return mission

    def grant(self, patient_id: str, bundle: GrantBundle, *, enabled: bool = True) -> GoogleGrant:
        grant = GoogleGrant(patient_id=patient_id, bundle=bundle, enabled=enabled)
        self.runtime.grant_store.save(grant)
        return grant

    def grants(self, patient_id: str) -> list[GoogleGrant]:
        return self.runtime.grant_store.list_for_patient(patient_id)

    def authorize(self, patient_id: str, mission_id: str, action: GoogleAction, *, payload: dict[str, Any], ttl_minutes: int = 15, one_time: bool = True) -> GoogleActionAuthorization:
        mission = self.load_mission(patient_id, mission_id)
        exact_request = GoogleActionRequest(patient_id=patient_id, mission_id=mission_id, action=action, payload=dict(payload))
        ttl = min(max(int(ttl_minutes), 1), 1440)
        authorization = GoogleActionAuthorization(
            patient_id=patient_id,
            mission_id=mission_id,
            action=action,
            intent_key=build_action_intent_key(exact_request),
            one_time=one_time,
            expires_at=utc_now() + timedelta(minutes=ttl),
        )
        self.runtime.authorization_store.save(authorization)
        self.coordinator.authorize_action(mission, action, authorization.id)
        return authorization

    def authorize_provider_contact(self, patient_id: str, mission_id: str, *, subject: str, body: str, ttl_minutes: int = 15) -> GoogleActionAuthorization:
        mission = self.load_mission(patient_id, mission_id)
        return self.authorize(patient_id, mission_id, GoogleAction.GMAIL_SEND, payload=provider_contact_payload(mission, subject=subject, body=body), ttl_minutes=ttl_minutes, one_time=True)

    def authorize_appointment_finalize(self, patient_id: str, mission_id: str, *, summary: str, time_zone: str, include_followup_task: bool = True, ttl_minutes: int = 15) -> list[GoogleActionAuthorization]:
        mission = self.load_mission(patient_id, mission_id)
        authorizations = [self.authorize(patient_id, mission_id, GoogleAction.CALENDAR_CREATE_EVENT, payload=calendar_event_payload(mission, summary=summary, time_zone=time_zone), ttl_minutes=ttl_minutes, one_time=True)]
        if include_followup_task:
            authorizations.append(self.authorize(patient_id, mission_id, GoogleAction.TASKS_CREATE, payload=followup_task_payload(mission), ttl_minutes=ttl_minutes, one_time=True))
        return authorizations

    def revoke_grant(self, patient_id: str, grant_id: str) -> GoogleGrant:
        grant = next((item for item in self.runtime.grant_store.list_for_patient(patient_id) if item.id == grant_id), None)
        if grant is None:
            raise KeyError(grant_id)
        grant.enabled = False
        self.runtime.grant_store.save(grant)
        return grant


def _stores(settings):
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
    if settings.store_backend == "firestore":
        return (
            FirestoreGoogleGrantStore(project=project),
            FirestoreGoogleReceiptStore(project=project),
            FirestoreGoogleAuthorizationStore(project=project),
            FirestoreOAuthConnectionStore(project=project),
            FirestoreMissionStore(project=project),
        )
    return MemoryGoogleGrantStore(), MemoryGoogleReceiptStore(), MemoryGoogleAuthorizationStore(), MemoryOAuthConnectionStore(), MemoryMissionStore()


def build_google_constellation_runtime(settings) -> GoogleConstellationRuntime:
    grant_store, receipt_store, authorization_store, oauth_store, mission_store = _stores(settings)
    patient_token_provider = SecretManagerOAuthTokenProvider(connection_store=oauth_store)
    server_token_provider = ServerAdcTokenProvider()
    connectors: dict[GoogleService, object] = {}

    # Cloud Run secret env values can inherit a UTF-8 BOM from legacy Windows
    # provisioning. It is never part of an API key and is invalid in an HTTP
    # header, so remove it defensively at the trust boundary.
    maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip().lstrip("\ufeff")
    if maps_key:
        connectors[GoogleService.MAPS] = HealthIAMapsConnector(maps_key)

    class PatientBoundOAuthProxy:
        def __init__(self, service, connector_type):
            self.service = service
            self.connector_type = connector_type

        def execute(self, action, payload, *, idempotency_key):
            patient_id = _CURRENT_GOOGLE_PATIENT.get()
            if not patient_id:
                raise PermissionError("Patient-bound Google connector missing execution context")
            return self.connector_type(patient_id, patient_token_provider).execute(action, dict(payload), idempotency_key=idempotency_key)

    connectors[GoogleService.CALENDAR] = PatientBoundOAuthProxy(GoogleService.CALENDAR, CalendarConnector)
    connectors[GoogleService.GMAIL] = PatientBoundOAuthProxy(GoogleService.GMAIL, GmailConnector)
    connectors[GoogleService.PEOPLE] = PatientBoundOAuthProxy(GoogleService.PEOPLE, PeopleConnector)
    connectors[GoogleService.DRIVE] = PatientBoundOAuthProxy(GoogleService.DRIVE, DriveConnector)
    connectors[GoogleService.TASKS] = PatientBoundOAuthProxy(GoogleService.TASKS, TasksConnector)

    # Server-side clinical cloud capabilities use the Cloud Run workload identity
    # through ADC. They never read patient OAuth refresh secrets.
    connectors[GoogleService.DOCUMENT_AI] = DocumentAIConnector(token_provider=server_token_provider)
    connectors[GoogleService.HEALTHCARE] = HealthcareConnector(token_provider=server_token_provider)
    connectors[GoogleService.FCM] = FCMConnector(token_provider=server_token_provider)
    connectors[GoogleService.SPEECH] = SpeechConnector(token_provider=server_token_provider)
    connectors[GoogleService.TEXT_TO_SPEECH] = TextToSpeechConnector(token_provider=server_token_provider)
    connectors[GoogleService.VEO] = VeoConnector(token_provider=server_token_provider)

    class PatientContextExecutor(GoogleActionExecutor):
        def execute(self, request_value, grants):
            token = _CURRENT_GOOGLE_PATIENT.set(request_value.patient_id)
            try:
                return super().execute(request_value, grants)
            finally:
                _CURRENT_GOOGLE_PATIENT.reset(token)

    raw = PatientContextExecutor(connectors=connectors, receipt_store=receipt_store)
    guard = GuardedGoogleActionExecutor(executor=raw, grant_store=grant_store, authorization_store=authorization_store, receipt_store=receipt_store)
    coordinator = HealthIAGoogleMissionCoordinator(GuardedMissionExecutorAdapter(guard), store=mission_store)
    return GoogleConstellationRuntime(
        coordinator=coordinator,
        grant_store=grant_store,
        receipt_store=receipt_store,
        authorization_store=authorization_store,
        oauth_connection_store=oauth_store,
        raw_executor=raw,
        guarded_executor=guard,
    )


def build_google_constellation_service(settings) -> GoogleConstellationService:
    return GoogleConstellationService(build_google_constellation_runtime(settings))
