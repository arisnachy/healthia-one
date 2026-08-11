from pathlib import Path

ADK = Path('healthia_one/google_mission_adk.py')
TEST = Path('tests/test_google_mission_conversation_autonomy.py')

text = ADK.read_text(encoding='utf-8')

old_auth = '''        requires_authorization = mission.state in {
            MissionState.AWAITING_AUTHORIZATION,
            MissionState.FOLLOWUP_AUTHORIZATION_PENDING,
        }
        authorization_kind = ""
        if mission.state == MissionState.FOLLOWUP_AUTHORIZATION_PENDING:
            authorization_kind = "create_followup_task"
        elif mission.state == MissionState.AWAITING_AUTHORIZATION:
            if mission.selected_slot is not None:
                authorization_kind = "finalize_selected_appointment"
            elif mission.provider_email:
                authorization_kind = "contact_selected_provider"
        next_action = {
'''
new_auth = '''        boundary = mission.tool_outputs.get("authorization_boundary")
        boundary = dict(boundary) if isinstance(boundary, dict) else {}
        boundary_kind = str(boundary.get("kind") or "")
        requires_authorization = mission.state in {
            MissionState.AWAITING_AUTHORIZATION,
            MissionState.FOLLOWUP_AUTHORIZATION_PENDING,
        } or bool(boundary_kind)
        authorization_kind = ""
        if mission.state == MissionState.FOLLOWUP_AUTHORIZATION_PENDING:
            authorization_kind = "create_followup_task"
        elif mission.state == MissionState.AWAITING_AUTHORIZATION:
            if mission.selected_slot is not None:
                authorization_kind = "finalize_selected_appointment"
            elif mission.provider_email:
                authorization_kind = "contact_selected_provider"
        elif boundary_kind:
            authorization_kind = boundary_kind
        next_action = {
'''
if text.count(old_auth) != 1:
    raise SystemExit('authorization result anchor mismatch')
text = text.replace(old_auth, new_auth, 1)

old_next = '''        }.get(mission.state, "inspect_mission")
        return GoogleMissionToolResult(
'''
new_next = '''        }.get(mission.state, "inspect_mission")
        if boundary_kind == "maps_location_for_mission":
            next_action = "authorize_location_for_mission"
        return GoogleMissionToolResult(
'''
if text.count(old_next) != 1:
    raise SystemExit('next action anchor mismatch')
text = text.replace(old_next, new_next, 1)

old_discover = '''        candidates = mission.tool_outputs.get("place_candidates") or []
        location_mode = str((mission.tool_outputs.get("location_evidence") or {}).get("mode") or "location")
        return self._result(
            mission,
            summary=(
                f"Found {len(candidates)} place candidate(s) using {location_mode}. Search/proximity evidence is not a clinical referral."
            ),
'''
new_discover = '''        candidates = mission.tool_outputs.get("place_candidates") or []
        location_mode = str((mission.tool_outputs.get("location_evidence") or {}).get("mode") or "location")
        boundary = mission.tool_outputs.get("authorization_boundary")
        boundary = dict(boundary) if isinstance(boundary, dict) else {}
        if str(boundary.get("kind") or "") == "maps_location_for_mission":
            public_summary = (
                "Google Places lookup is paused until the patient explicitly authorizes location lookup for this mission; "
                "no Places search was performed."
            )
        else:
            public_summary = (
                f"Found {len(candidates)} place candidate(s) using {location_mode}. "
                "Search/proximity evidence is not a clinical referral."
            )
        return self._result(
            mission,
            summary=public_summary,
'''
if text.count(old_discover) != 1:
    raise SystemExit('discover summary anchor mismatch')
text = text.replace(old_discover, new_discover, 1)

class_anchor = '\n\nclass AdkGoogleMissionRuntime:\n'
helper = '''\n\ndef _coerce_function_tool_result(value: Any) -> dict[str, Any]:
    """Normalize ADK FunctionResponse payloads without trusting model prose."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        return {}
    nested = value.get("result")
    if hasattr(nested, "model_dump"):
        nested = nested.model_dump(mode="json")
    if isinstance(nested, dict):
        return dict(nested)
    return dict(value)


def _boundary_plan_from_tool_response(function_name: str, response: Any) -> dict[str, Any] | None:
    """Return immediately from a real tool-produced human boundary.

    ADK emits function-response events before the model's post-tool prose turn.
    Once deterministic policy has reached an exact human authorization boundary,
    another model round cannot make further external progress and may only add
    latency. Build the patient-visible structured plan from durable tool truth.
    """
    result = _coerce_function_tool_result(response)
    mission_id = str(result.get("mission_id") or "").strip()
    authorization_kind = str(result.get("authorization_kind") or "").strip()
    if not mission_id or not bool(result.get("requires_authorization")) or not authorization_kind:
        return None
    state = str(result.get("state") or "blocked")
    next_action = str(result.get("next_action") or "request_human_authorization")
    summary = str(result.get("public_summary") or "").strip()
    if not summary:
        summary = "HealthIA reached a verified human authorization boundary and stopped before external execution."
    ui_action = None
    if authorization_kind == "maps_location_for_mission":
        ui_action = {
            "type": "authorize_google_location",
            "mission_id": mission_id,
            "ttl_minutes": 30,
            "label_es": "Autorizar ubicación para esta misión",
            "label_en": "Authorize location for this mission",
        }
    return {
        "intent": "continue_mission",
        "mission_id": mission_id,
        "state": state,
        "next_action": next_action,
        "requires_human_authorization": True,
        "authorization_kind": authorization_kind,
        "patient_message": summary,
        "ui_action": ui_action,
        "_boundary_source": f"tool_response:{function_name}",
    }
'''
if text.count(class_anchor) != 1:
    raise SystemExit('runtime class anchor mismatch')
text = text.replace(class_anchor, helper + class_anchor, 1)

old_loop = '''            for part in parts:
                function_call = getattr(part, "function_call", None)
                name = str(getattr(function_call, "name", "") or "").strip()
                if name and name in self.tool_names() and name not in executed_tools:
                    executed_tools.append(name)
            text_parts = [
'''
new_loop = '''            for part in parts:
                function_call = getattr(part, "function_call", None)
                name = str(getattr(function_call, "name", "") or "").strip()
                if name and name in self.tool_names() and name not in executed_tools:
                    executed_tools.append(name)

                function_response = getattr(part, "function_response", None)
                response_name = str(getattr(function_response, "name", "") or "").strip()
                response_payload = getattr(function_response, "response", None)
                if response_name and response_name in self.tool_names():
                    if response_name not in executed_tools:
                        executed_tools.append(response_name)
                    boundary_payload = _boundary_plan_from_tool_response(response_name, response_payload)
                    if boundary_payload is not None:
                        boundary_payload["_execution"] = {
                            "session_id": session_id,
                            "executed_tools": list(executed_tools),
                            "tool_count": len(executed_tools),
                            "stopped_at_real_boundary": True,
                        }
                        return boundary_payload
            text_parts = [
'''
if text.count(old_loop) != 1:
    raise SystemExit('ADK event loop anchor mismatch')
text = text.replace(old_loop, new_loop, 1)
ADK.write_text(text, encoding='utf-8')

test = TEST.read_text(encoding='utf-8').rstrip()
addition = r'''


def test_adk_tool_response_short_circuits_exact_location_authorization_boundary() -> None:
    from healthia_one.google_mission_adk import _boundary_plan_from_tool_response

    plan = _boundary_plan_from_tool_response(
        "discover_care_options",
        {
            "result": {
                "ok": True,
                "mission_id": "gmission_demo",
                "state": "blocked",
                "next_action": "authorize_location_for_mission",
                "requires_authorization": True,
                "authorization_kind": "maps_location_for_mission",
                "public_summary": "Google Places lookup is paused; no Places search was performed.",
                "data": {"candidates": []},
            }
        },
    )
    assert plan is not None
    assert plan["mission_id"] == "gmission_demo"
    assert plan["state"] == "blocked"
    assert plan["requires_human_authorization"] is True
    assert plan["authorization_kind"] == "maps_location_for_mission"
    assert plan["next_action"] == "authorize_location_for_mission"
    assert plan["ui_action"]["type"] == "authorize_google_location"
    assert "no Places search" in plan["patient_message"]
    assert plan["_boundary_source"] == "tool_response:discover_care_options"


def test_adk_tool_response_does_not_short_circuit_without_real_authorization_boundary() -> None:
    from healthia_one.google_mission_adk import _boundary_plan_from_tool_response

    assert _boundary_plan_from_tool_response(
        "discover_care_options",
        {
            "result": {
                "mission_id": "gmission_demo",
                "state": "awaiting_selection",
                "next_action": "patient_or_context_selects_candidate",
                "requires_authorization": False,
                "authorization_kind": "",
                "public_summary": "Found two place candidates.",
            }
        },
    ) is None


def test_adk_runtime_reads_function_response_events_and_returns_before_post_tool_model_round() -> None:
    source = (ROOT / "healthia_one/google_mission_adk.py").read_text(encoding="utf-8")
    assert 'getattr(part, "function_response", None)' in source
    assert '_boundary_plan_from_tool_response(response_name, response_payload)' in source
    assert '"stopped_at_real_boundary": True' in source
    assert 'return boundary_payload' in source
    assert '"Google Places lookup is paused until the patient explicitly authorizes location lookup for this mission; "' in source
    assert '"no Places search was performed."' in source
'''
if 'test_adk_tool_response_short_circuits_exact_location_authorization_boundary' in test:
    raise SystemExit('boundary short-circuit tests already present')
TEST.write_text(test + addition + '\n', encoding='utf-8')
