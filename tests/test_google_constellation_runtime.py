from healthia_one.config import Settings
from healthia_one.google_constellation import GrantBundle, GoogleAction
from healthia_one.google_constellation_runtime import build_google_constellation_service
from healthia_one.google_mission_runtime import GoogleHealthMission, MissionKind


def test_memory_runtime_builds_without_cloud_credentials_or_secret_manager_access(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    mission = GoogleHealthMission(
        patient_id="patient_demo",
        kind=MissionKind.CARE_NAVIGATION,
        title="Arrange care",
    )
    service.coordinator.store.save(mission)

    grant = service.grant("patient_demo", GrantBundle.GMAIL_SEND)
    authorization = service.authorize(
        "patient_demo",
        mission.id,
        GoogleAction.GMAIL_SEND,
        ttl_minutes=5,
    )

    assert grant.patient_id == "patient_demo"
    persisted = service.runtime.authorization_store.get("patient_demo", authorization.id)
    assert persisted is not None
    assert persisted.mission_id == mission.id
    assert persisted.action == GoogleAction.GMAIL_SEND
    loaded = service.load_mission("patient_demo", mission.id)
    assert loaded.action_authorizations[str(GoogleAction.GMAIL_SEND)] == authorization.id


def test_authorization_cannot_be_created_for_another_patients_mission(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    mission = GoogleHealthMission(patient_id="patient_a", kind=MissionKind.CARE_NAVIGATION, title="Arrange care")
    service.coordinator.store.save(mission)

    try:
        service.authorize("patient_b", mission.id, GoogleAction.GMAIL_SEND)
        assert False, "foreign patient authorization should fail"
    except KeyError:
        pass


def test_revoked_healthia_grant_is_persistently_disabled(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    service = build_google_constellation_service(Settings(store_backend="memory", llm_backend="mock"))
    grant = service.grant("patient_demo", GrantBundle.CALENDAR_READ)
    revoked = service.revoke_grant("patient_demo", grant.id)
    assert revoked.enabled is False
    values = service.grants("patient_demo")
    assert len(values) == 1
    assert values[0].enabled is False
