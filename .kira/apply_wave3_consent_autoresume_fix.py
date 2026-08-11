from __future__ import annotations

from pathlib import Path

SOURCE = Path("healthia_one/google_mission_chat.py")
TEST = Path("tests/test_google_mission_location_consent.py")
MARKER = "resume_google_health_mission_after_location_consent"
TEST_MARKER = "test_conversational_location_consent_immediately_resumes_safe_places_discovery"

source = SOURCE.read_text(encoding="utf-8")
if MARKER not in source:
    old_import = "from healthia_one.google_mission_adk import AdkGoogleMissionRuntime\n"
    new_import = "from healthia_one.google_mission_adk import AdkGoogleMissionRuntime, GoogleMissionToolFacade\n"
    if source.count(old_import) != 1:
        raise SystemExit("Google mission ADK import anchor not found exactly once")
    source = source.replace(old_import, new_import, 1)

    anchor = "        location_consent_granted, consent_mission_id = self._grant_explicit_location_consent(state, patient_text)\n        if not self.adk.ready:\n"
    block = '''        location_consent_granted, consent_mission_id = self._grant_explicit_location_consent(state, patient_text)\n\n        # Exact mission-scoped location consent is the last human boundary before\n        # the already-planned read-only Places lookup. Resume the same ADK tool\n        # deterministically instead of asking Gemini to reinterpret the consent turn.\n        if location_consent_granted and consent_mission_id:\n            tool_result = GoogleMissionToolFacade(\n                constellation=self.constellation,\n                patient_id=state.profile.id,\n                patient_text=patient_text,\n            ).discover_care_options(consent_mission_id)\n            consent_mission = self.constellation.load_mission(state.profile.id, consent_mission_id)\n            candidates = (consent_mission.tool_outputs or {}).get("place_candidates") or []\n            boundary = (consent_mission.tool_outputs or {}).get("authorization_boundary") or {}\n            state_name = str(consent_mission.state)\n            search_completed = not boundary and state_name == "awaiting_selection"\n            next_action = (\n                "patient_or_context_selects_candidate"\n                if candidates\n                else "refine_search_or_location"\n            )\n            english = "authorize" in _normalize(patient_text) or "location" in _normalize(patient_text)\n            if search_completed and candidates:\n                lead = (\n                    f"Your location permission was applied only to this mission. I resumed the authorized Google Places search and found {len(candidates)} candidate(s). Choose the option you prefer."\n                    if english else\n                    f"Tu permiso de ubicación quedó limitado a esta misión. Reanudé la búsqueda autorizada en Google Places y encontré {len(candidates)} opción(es). Elige la que prefieras."\n                )\n            elif search_completed:\n                lead = (\n                    "Your location permission was applied only to this mission. I completed the authorized Google Places search, but it returned no candidates; I will not invent one."\n                    if english else\n                    "Tu permiso de ubicación quedó limitado a esta misión. Completé la búsqueda autorizada en Google Places, pero no devolvió candidatos; no voy a inventar uno."\n                )\n            else:\n                lead = (\n                    "Your mission-scoped location permission was recorded, but the authorized Google Places lookup could not complete. I did not invent a result."\n                    if english else\n                    "Tu permiso de ubicación quedó registrado sólo para esta misión, pero la búsqueda autorizada en Google Places no pudo completarse. No inventé resultados."\n                )\n            receipt = {\n                "mission_id": consent_mission_id,\n                "state": state_name,\n                "outcome": "advanced" if search_completed else "blocked",\n                "next_action": next_action,\n                "requires_human_authorization": False,\n                "authorization_kind": "",\n                "executed_steps": [\n                    "Registró consentimiento temporal de ubicación para esta misión",\n                    (\n                        "Buscó opciones verificables en Google Places"\n                        if search_completed else\n                        "Intentó la búsqueda autorizada en Google Places"\n                    ),\n                ],\n                "tool_count": 1,\n                "durable_mission": True,\n            }\n            audit(\n                state,\n                actor="google_adk_policy",\n                action="resume_google_health_mission_after_location_consent",\n                resource_type="google_health_mission",\n                resource_id=consent_mission_id,\n                details={\n                    "state": state_name,\n                    "candidate_count": len(candidates),\n                    "search_completed": search_completed,\n                    "executed_tool": "discover_care_options",\n                    "external_mutation": False,\n                },\n            )\n            return ChatResponse(\n                message=ChatMessage(\n                    patient_id=state.profile.id,\n                    role="assistant",\n                    author="HealthIA",\n                    content=f"{lead}\\n\\n{_receipt_markdown(receipt)}",\n                    metadata={\n                        "google_constellation": True,\n                        "google_mission_id": consent_mission_id,\n                        "google_mission_state": state_name,\n                        "google_mission_next_action": next_action,\n                        "requires_human_authorization": False,\n                        "authorization_kind": "",\n                        "health_os_control": True,\n                        "autonomy_policy": "advance_until_human_or_external_event_boundary",\n                        "public_action_receipt": receipt,\n                        "external_action_executed": search_completed,\n                        "external_mutation_performed": False,\n                        "policy_executed_tool": "discover_care_options",\n                    },\n                )\n            )\n\n        if not self.adk.ready:\n'''
    if source.count(anchor) != 1:
        raise SystemExit("Consent response insertion anchor not found exactly once")
    source = source.replace(anchor, block, 1)
    SOURCE.write_text(source, encoding="utf-8")

text = TEST.read_text(encoding="utf-8")
if TEST_MARKER not in text:
    text += r'''


def test_conversational_location_consent_immediately_resumes_safe_places_discovery() -> None:
    import asyncio

    from healthia_one.google_connector_runtime import ConnectorResult
    from healthia_one.google_constellation import GoogleGrant, build_google_receipt
    from healthia_one.google_mission_chat import GoogleMissionConversationRouter
    from healthia_one.models import ChatMessage, PatientState

    class _PlacesExecutor:
        def execute(self, request, _grants):
            places = [
                {"id": "place-a", "displayName": {"text": "Clinic A"}, "formattedAddress": "Synthetic A"},
                {"id": "place-b", "displayName": {"text": "Clinic B"}, "formattedAddress": "Synthetic B"},
            ]
            receipt = build_google_receipt(
                request,
                status="completed",
                safe_summary="Found 2 synthetic place candidates.",
            )
            return receipt, ConnectorResult(safe_summary=receipt.safe_summary, data={"places": places})

    class _Constellation:
        def __init__(self, patient_id: str):
            self.store = MemoryMissionStore()
            self.coordinator = HealthIAGoogleMissionCoordinator(_PlacesExecutor(), store=self.store)
            self._grants = []
            self.patient_id = patient_id

        def load_mission(self, patient_id: str, mission_id: str):
            assert patient_id == self.patient_id
            mission = self.store.load(patient_id, mission_id)
            if mission is None:
                raise KeyError(mission_id)
            return mission

        def grant(self, patient_id: str, bundle, *, enabled=True, mission_id="", ttl_minutes=None):
            assert patient_id == self.patient_id
            grant = GoogleGrant.mission_scoped(
                patient_id=patient_id,
                bundle=bundle,
                mission_id=mission_id,
                ttl_minutes=ttl_minutes or 30,
            )
            grant.enabled = enabled
            self._grants.append(grant)
            return grant

        def grants(self, patient_id: str):
            assert patient_id == self.patient_id
            return [item.model_copy(deep=True) for item in self._grants]

    class _AdkMustNotInterpretConsent:
        ready = True

        async def run(self, **_kwargs):
            raise AssertionError("Exact location consent must deterministically resume the safe ADK Places tool")

    state = PatientState()
    constellation = _Constellation(state.profile.id)
    mission = constellation.coordinator.create_navigation_mission(
        patient_id=state.profile.id,
        condition_or_need="follow-up care",
        provider_query="clinic",
        location_text="Santiago de los Caballeros, Dominican Republic",
    )
    mission = constellation.coordinator.discover(mission, [])
    assert mission.state == MissionState.BLOCKED
    assert mission.tool_outputs["authorization_boundary"]["kind"] == "maps_location_for_mission"

    state.messages.append(
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="Location permission is required.",
            metadata={"google_mission_id": mission.id, "authorization_kind": "maps_location_for_mission"},
        )
    )
    router = GoogleMissionConversationRouter.__new__(GoogleMissionConversationRouter)
    router.settings = None
    router.constellation = constellation
    router.adk = _AdkMustNotInterpretConsent()

    response = asyncio.run(router.respond(state, "I authorize my location for this mission."))
    persisted = constellation.load_mission(state.profile.id, mission.id)
    candidates = persisted.tool_outputs.get("place_candidates") or []

    assert persisted.state == MissionState.AWAITING_SELECTION
    assert "authorization_boundary" not in persisted.tool_outputs
    assert len(candidates) == 2
    assert response.message.metadata["google_mission_state"] == "awaiting_selection"
    assert response.message.metadata["google_mission_next_action"] == "patient_or_context_selects_candidate"
    assert response.message.metadata["requires_human_authorization"] is False
    assert response.message.metadata["external_action_executed"] is True
    assert response.message.metadata["external_mutation_performed"] is False
    assert response.message.metadata["policy_executed_tool"] == "discover_care_options"
    receipt = response.message.metadata["public_action_receipt"]
    assert receipt["tool_count"] == 1
    assert any("ubicación" in step.lower() for step in receipt["executed_steps"])
    assert any("places" in step.lower() for step in receipt["executed_steps"])
'''
    TEST.write_text(text, encoding="utf-8")

print("KIRA_WAVE3_CONSENT_AUTORESUME_PATCH_STAGED")
