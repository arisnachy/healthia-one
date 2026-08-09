from datetime import datetime, timezone

from healthia_one.autopilot_events import MemoryEventOutboxStore
from healthia_one.autopilot_scheduler import enqueue_scheduled_refreshes, period_key
from healthia_one.opportunity_integration import _permission_response, radar_permissions
from healthia_one.opportunity_permissions import MemoryRadarPermissionStore
from healthia_one.service import seed_state


def unique_state(patient_id: str):
    state = seed_state()
    state.profile.id = patient_id
    state.profile.confirmed_conditions = ["Hipertensión arterial"]
    return state


def test_radar_permissions_are_off_by_default():
    permissions = MemoryRadarPermissionStore().load("patient_permission_default")

    assert permissions.scientific_enabled is False
    assert permissions.resource_enabled is False


def test_scheduler_enqueues_nothing_without_explicit_opt_in():
    state = unique_state("patient_scheduler_off")
    permissions = MemoryRadarPermissionStore()
    outbox = MemoryEventOutboxStore()
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)

    scientific = enqueue_scheduled_refreshes(
        [state], permission_store=permissions, outbox_store=outbox, mode="scientific", now=now
    )
    resources = enqueue_scheduled_refreshes(
        [state], permission_store=permissions, outbox_store=outbox, mode="resources", now=now
    )

    assert scientific == []
    assert resources == []


def test_scientific_schedule_is_weekly_and_deduplicated():
    state = unique_state("patient_scheduler_science")
    permissions = MemoryRadarPermissionStore()
    value = permissions.load(state.profile.id)
    value.scientific_enabled = True
    permissions.save(value)
    outbox = MemoryEventOutboxStore()
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)

    first = enqueue_scheduled_refreshes(
        [state], permission_store=permissions, outbox_store=outbox, mode="scientific", now=now
    )
    second = enqueue_scheduled_refreshes(
        [state], permission_store=permissions, outbox_store=outbox, mode="scientific", now=now
    )

    assert len(first) == 1
    assert second == []
    assert first[0].payload["scientific_scan"] is True
    assert first[0].payload["resource_scan"] is False
    assert first[0].payload["period_key"] == period_key("scientific", now)


def test_resource_schedule_is_monthly_and_separately_opted_in():
    state = unique_state("patient_scheduler_resources")
    permissions = MemoryRadarPermissionStore()
    value = permissions.load(state.profile.id)
    value.resource_enabled = True
    permissions.save(value)
    outbox = MemoryEventOutboxStore()
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)

    first = enqueue_scheduled_refreshes(
        [state], permission_store=permissions, outbox_store=outbox, mode="resources", now=now
    )
    same_month = enqueue_scheduled_refreshes(
        [state], permission_store=permissions, outbox_store=outbox, mode="resources", now=datetime(2026, 8, 20, tzinfo=timezone.utc)
    )

    assert len(first) == 1
    assert same_month == []
    assert first[0].payload["scientific_scan"] is False
    assert first[0].payload["resource_scan"] is True
    assert first[0].payload["country"] == ""


def test_chat_can_enable_and_disable_scientific_radar_explicitly():
    state = unique_state("patient_chat_permission_science")

    enabled = _permission_response(state, "Activa el radar científico")
    assert enabled is not None
    assert enabled.message.metadata["scientific_radar_enabled"] is True
    assert radar_permissions().load(state.profile.id).scientific_enabled is True

    disabled = _permission_response(state, "Desactiva el radar científico")
    assert disabled is not None
    assert disabled.message.metadata["scientific_radar_enabled"] is False
    assert radar_permissions().load(state.profile.id).scientific_enabled is False


def test_radar_disable_intents_outrank_positive_substrings_for_resources():
    state = unique_state("patient_chat_permission_resources")

    enabled = _permission_response(state, "Activa el radar de ayudas")
    assert enabled is not None
    assert enabled.message.metadata["resource_radar_enabled"] is True

    disabled = _permission_response(state, "Desactiva el radar de ayudas")
    assert disabled is not None
    assert disabled.message.metadata["resource_radar_enabled"] is False
    assert radar_permissions().load(state.profile.id).resource_enabled is False


def test_english_radar_opt_out_remains_explicit_and_fail_closed():
    state = unique_state("patient_chat_permission_english")

    assert _permission_response(state, "enable scientific radar").message.metadata["scientific_radar_enabled"] is True
    assert _permission_response(state, "disable scientific radar").message.metadata["scientific_radar_enabled"] is False
    assert _permission_response(state, "enable assistance radar").message.metadata["resource_radar_enabled"] is True
    assert _permission_response(state, "disable assistance radar").message.metadata["resource_radar_enabled"] is False
