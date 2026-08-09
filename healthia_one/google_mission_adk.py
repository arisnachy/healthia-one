from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from healthia_one.google_constellation_runtime import GoogleConstellationService
from healthia_one.google_mission_runtime import MissionState


class GoogleMissionToolResult(BaseModel):
    ok: bool
    mission_id: str = ""
    state: str = ""
    next_action: str = ""
    requires_authorization: bool = False
    authorization_kind: str = ""
    public_summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class GoogleMissionToolFacade:
    """Narrow ADK tool surface over the deterministic mission coordinator.

    This facade exposes no grant creation, OAuth connection, authorization
    creation, Gmail raw send, Calendar raw insert, Drive raw write or Tasks raw
    write. Gemini can plan and advance an already authorized mission; it cannot
    manufacture consent.
    """

    def __init__(
        self,
        *,
        constellation: GoogleConstellationService,
        patient_id: str,
        authorized_location: dict[str, float] | None = None,
    ) -> None:
        self.constellation = constellation
        self.patient_id = patient_id
        self.authorized_location = dict(authorized_location or {})

    def _load(self, mission_id: str):
        return self.constellation.load_mission(self.patient_id, mission_id)

    def _result(self, mission, *, summary: str = "", data: dict[str, Any] | None = None) -> dict:
        state = str(mission.state)
        requires_authorization = mission.state == MissionState.AWAITING_AUTHORIZATION
        authorization_kind = ""
        if requires_authorization:
            if mission.selected_slot is not None:
                authorization_kind = "finalize_selected_appointment"
            elif mission.provider_email:
                authorization_kind = "contact_selected_provider"
        next_action = {
            MissionState.RECEIVED: "discover_care_options",
            MissionState.DISCOVERING: "wait_for_discovery",
            MissionState.AWAITING_SELECTION: "patient_or_context_selects_candidate",
            MissionState.AWAITING_AUTHORIZATION: "request_human_authorization",
            MissionState.CONTACTING: "wait_for_connector_receipt",
            MissionState.AWAITING_EXTERNAL_EVENT: "wait_for_event_driven_reply",
            MissionState.SLOT_OFFERED: "patient_selects_offered_slot",
            MissionState.SCHEDULING: "wait_for_calendar_receipt",
            MissionState.FOLLOWUP_CREATED: "inspect_followup_state",
            MissionState.COMPLETED: "mission_complete",
            MissionState.BLOCKED: "explain_blocker_or_choose_alternative",
            MissionState.FAILED: "inspect_failure_before_retry",
        }.get(mission.state, "inspect_mission")
        return GoogleMissionToolResult(
            ok=mission.state not in {MissionState.FAILED},
            mission_id=mission.id,
            state=state,
            next_action=next_action,
            requires_authorization=requires_authorization,
            authorization_kind=authorization_kind,
            public_summary=summary,
            data=data or {},
        ).model_dump(mode="json")

    def inspect_google_health_mission(self, mission_id: str) -> dict:
        mission = self._load(mission_id)
        candidates = mission.tool_outputs.get("place_candidates") or []
        return self._result(
            mission,
            summary="Loaded the patient-scoped Google health mission.",
            data={
                "title": mission.title,
                "kind": str(mission.kind),
                "condition_or_need": mission.condition_or_need,
                "candidate_count": len(candidates),
                "candidate_names": [
                    str((item.get("displayName") or {}).get("text") or item.get("formattedAddress") or "")[:160]
                    for item in candidates[:8]
                ],
                "selected_place": {
                    "id": str(mission.selected_place.get("id") or ""),
                    "name": str((mission.selected_place.get("displayName") or {}).get("text") or ""),
                    "address": str(mission.selected_place.get("formattedAddress") or ""),
                },
                "has_provider_email": bool(mission.provider_email),
                "offered_slots": [item.model_dump(mode="json") for item in mission.offered_slots],
                "required_documents": list(mission.required_documents),
                "calendar_event_id": mission.calendar_event_id,
                "task_count": len(mission.task_ids),
                "recent_public_events": [item.model_dump(mode="json") for item in mission.public_events[-8:]],
            },
        )

    def start_navigation_mission(self, condition_or_need: str, provider_query: str) -> dict:
        lat = self.authorized_location.get("lat")
        lng = self.authorized_location.get("lng")
        if lat is None or lng is None:
            return GoogleMissionToolResult(
                ok=False,
                state="location_required",
                next_action="ask_patient_to_share_location_or_choose_a_place_text_search_flow",
                public_summary=(
                    "HealthIA does not have patient-authorized coordinates for this mission. "
                    "The model must not invent latitude/longitude."
                ),
            ).model_dump(mode="json")
        mission = self.constellation.coordinator.create_navigation_mission(
            patient_id=self.patient_id,
            condition_or_need=str(condition_or_need)[:240],
            provider_query=str(provider_query)[:240],
            lat=float(lat),
            lng=float(lng),
        )
        return self._result(
            mission,
            summary="Created a patient-scoped navigation mission from authorized location evidence.",
        )

    def discover_care_options(self, mission_id: str, radius_m: int = 10000) -> dict:
        mission = self._load(mission_id)
        mission = self.constellation.coordinator.discover(
            mission,
            self.constellation.grants(self.patient_id),
            radius_m=min(max(int(radius_m), 100), 50000),
        )
        candidates = mission.tool_outputs.get("place_candidates") or []
        return self._result(
            mission,
            summary=(
                f"Found {len(candidates)} nearby candidate(s). Proximity is navigation evidence, not a clinical referral."
            ),
            data={
                "candidates": [
                    {
                        "index": index,
                        "id": str(item.get("id") or ""),
                        "name": str((item.get("displayName") or {}).get("text") or "")[:160],
                        "address": str(item.get("formattedAddress") or "")[:300],
                        "maps_uri": str(item.get("googleMapsUri") or "")[:500],
                        "website": str(item.get("websiteUri") or "")[:500],
                        "phone": str(item.get("nationalPhoneNumber") or "")[:120],
                    }
                    for index, item in enumerate(candidates[:8])
                ]
            },
        )

    def select_discovered_candidate(self, mission_id: str, candidate_index: int) -> dict:
        mission = self._load(mission_id)
        candidates = mission.tool_outputs.get("place_candidates") or []
        if candidate_index < 0 or candidate_index >= len(candidates):
            return GoogleMissionToolResult(
                ok=False,
                mission_id=mission.id,
                state=str(mission.state),
                next_action="choose_a_candidate_index_returned_by_discover_care_options",
                public_summary="The requested candidate index is not part of this mission's discovery results.",
            ).model_dump(mode="json")
        mission = self.constellation.coordinator.select_provider(
            mission,
            place=candidates[candidate_index],
            provider_email="",
        )
        return self._result(
            mission,
            summary="Selected the exact discovered place candidate without inventing contact details.",
        )

    def check_calendar_window(self, mission_id: str, time_min: str, time_max: str, time_zone: str) -> dict:
        mission = self._load(mission_id)
        mission = self.constellation.coordinator.check_availability(
            mission,
            self.constellation.grants(self.patient_id),
            time_min=time_min,
            time_max=time_max,
            time_zone=time_zone,
        )
        return self._result(
            mission,
            summary="Checked the patient's authorized Calendar availability without creating or changing an event.",
            data={"freebusy": mission.tool_outputs.get("calendar_freebusy") or {}},
        )

    def contact_selected_provider(self, mission_id: str, subject: str, body: str) -> dict:
        mission = self._load(mission_id)
        try:
            mission = self.constellation.coordinator.contact_selected_provider(
                mission,
                self.constellation.grants(self.patient_id),
                subject=subject,
                body=body,
            )
        except ValueError as exc:
            return GoogleMissionToolResult(
                ok=False,
                mission_id=mission.id,
                state=str(mission.state),
                next_action="resolve_verified_provider_contact",
                public_summary=str(exc),
            ).model_dump(mode="json")
        return self._result(
            mission,
            summary=(
                "Provider contact advanced only if an exact durable authorization matched the destination, subject and body."
            ),
        )

    def select_offered_slot(self, mission_id: str, slot_index: int) -> dict:
        mission = self._load(mission_id)
        if slot_index < 0 or slot_index >= len(mission.offered_slots):
            return GoogleMissionToolResult(
                ok=False,
                mission_id=mission.id,
                state=str(mission.state),
                next_action="choose_a_provider_offered_slot_index",
                public_summary="The requested slot was not explicitly offered in the mission-linked provider reply.",
            ).model_dump(mode="json")
        mission = self.constellation.coordinator.choose_slot(mission, mission.offered_slots[slot_index])
        return self._result(
            mission,
            summary="Selected one exact provider-offered appointment slot; no calendar mutation occurred.",
        )

    def finalize_selected_appointment(
        self,
        mission_id: str,
        summary: str,
        time_zone: str,
        create_followup_task: bool = True,
    ) -> dict:
        mission = self._load(mission_id)
        try:
            mission = self.constellation.coordinator.finalize_appointment(
                mission,
                self.constellation.grants(self.patient_id),
                summary=summary,
                time_zone=time_zone,
                create_followup_task=create_followup_task,
            )
        except ValueError as exc:
            return GoogleMissionToolResult(
                ok=False,
                mission_id=mission.id,
                state=str(mission.state),
                next_action="inspect_mission",
                public_summary=str(exc),
            ).model_dump(mode="json")
        return self._result(
            mission,
            summary="Finalized only those Calendar/Tasks mutations whose exact action payloads had durable patient authorization.",
        )


MISSION_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["navigate_care", "continue_mission", "inspect_only", "not_applicable"],
        },
        "mission_id": {"type": "string"},
        "state": {"type": "string"},
        "next_action": {"type": "string"},
        "requires_human_authorization": {"type": "boolean"},
        "authorization_kind": {"type": "string"},
        "patient_message": {"type": "string", "maxLength": 900},
        "ui_action": {"type": ["object", "null"]},
    },
    "required": [
        "intent",
        "mission_id",
        "state",
        "next_action",
        "requires_human_authorization",
        "authorization_kind",
        "patient_message",
        "ui_action",
    ],
}


class AdkGoogleMissionRuntime:
    """Gemini/ADK semantic planner over high-level mission tools only."""

    def __init__(self, settings, *, constellation: GoogleConstellationService) -> None:
        self.settings = settings
        self.constellation = constellation
        self._session_service = None
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return bool(self.settings.llm_backend == "gemini_api" and self.settings.adk_ready)

    @staticmethod
    def tool_names() -> tuple[str, ...]:
        return (
            "inspect_google_health_mission",
            "start_navigation_mission",
            "discover_care_options",
            "select_discovered_candidate",
            "check_calendar_window",
            "contact_selected_provider",
            "select_offered_slot",
            "finalize_selected_appointment",
        )

    async def _sessions(self):
        if self._session_service is None:
            async with self._lock:
                if self._session_service is None:
                    from google.adk.sessions import InMemorySessionService

                    self._session_service = InMemorySessionService()
        return self._session_service

    async def run(
        self,
        *,
        patient_id: str,
        patient_text: str,
        conversation_context: str,
        authorized_location: dict[str, float] | None = None,
    ) -> dict | None:
        if not self.ready:
            return None

        from google.adk.agents import LlmAgent
        from google.adk.models.google_llm import Gemini
        from google.adk.runners import Runner
        from google.genai import types

        facade = GoogleMissionToolFacade(
            constellation=self.constellation,
            patient_id=patient_id,
            authorized_location=authorized_location,
        )
        tools = [getattr(facade, name) for name in self.tool_names()]
        instruction = """
You are HealthIA's Google Health Mission planner. You operate ABOVE deterministic mission policy.
Use tools only when the patient's message is actually about finding care/resources, continuing a navigation mission, contacting a previously selected provider, or finishing an offered appointment.

Hard boundaries:
- You have NO tool that grants Google permissions, connects OAuth, or creates patient authorization. Never claim you authorized yourself.
- Never invent latitude/longitude, a provider email, a place, an appointment offer, a document, or a Google receipt.
- Nearby Places results are candidates, never proof of clinical appropriateness.
- A provider can be contacted only when the deterministic mission already holds a verified/entered destination and an exact patient authorization for the exact message payload.
- A Calendar/Tasks mutation can occur only when the deterministic guard has exact payload-bound authorization.
- If a tool returns requires_authorization=true, stop external execution and explain the precise human action that needs approval.
- If a mission waits for an external Gmail event, do not poll or fabricate a response.
- Never expose OAuth tokens, Secret Manager references, private chain-of-thought, or unrelated mailbox/contact data.
- Clinical emergencies are handled before this runtime; do not reinterpret safety decisions here.
Return only the requested JSON planning object after using tools as needed.
""".strip()

        agent = LlmAgent(
            name="healthia_google_mission_planner",
            model=Gemini(
                model=self.settings.model,
                retry_options=types.HttpRetryOptions(attempts=2),
            ),
            description="Plans and advances patient-authorized Google health navigation missions.",
            instruction=instruction,
            tools=tools,
            generate_content_config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=min(int(self.settings.ai_max_output_tokens), 1400),
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                response_mime_type="application/json",
                response_json_schema=MISSION_PLAN_SCHEMA,
            ),
        )

        session_service = await self._sessions()
        app_name = "healthia_google_mission"
        session_id = f"gmission-{uuid4().hex}"
        await session_service.create_session(
            app_name=app_name,
            user_id=patient_id,
            session_id=session_id,
        )
        runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
        prompt = {
            "patient_message": patient_text,
            "conversation_context": conversation_context[:6000],
            "location_available": bool(
                authorized_location
                and authorized_location.get("lat") is not None
                and authorized_location.get("lng") is not None
            ),
            "policy": "Use mission tools, not raw Google APIs. Never authorize an action yourself.",
        }

        final_text = ""
        last_text = ""
        message = types.Content(
            role="user",
            parts=[types.Part(text=json.dumps(prompt, ensure_ascii=False, default=str))],
        )
        async for event in runner.run_async(
            user_id=patient_id,
            session_id=session_id,
            new_message=message,
        ):
            content = getattr(event, "content", None)
            text_parts = [
                str(getattr(part, "text", "") or "")
                for part in (getattr(content, "parts", None) or [])
                if getattr(part, "text", None) and not getattr(part, "thought", False)
            ]
            if text_parts:
                last_text = "".join(text_parts).strip()
            is_final = getattr(event, "is_final_response", None)
            if callable(is_final) and is_final() and text_parts:
                final_text = "".join(text_parts).strip()

        final_text = final_text or last_text
        if not final_text.strip():
            return None
        try:
            payload = json.loads(final_text)
        except json.JSONDecodeError:
            start = final_text.find("{")
            end = final_text.rfind("}")
            if start < 0 or end <= start:
                return None
            payload = json.loads(final_text[start : end + 1])
        return payload if isinstance(payload, dict) else None
