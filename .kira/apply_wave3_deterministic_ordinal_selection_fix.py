from pathlib import Path

CHAT = Path('healthia_one/google_mission_chat.py')
TEST = Path('tests/test_google_mission_conversation_autonomy.py')

text = CHAT.read_text(encoding='utf-8')

helper_anchor = '''def _is_location_consent(patient_text: str) -> bool:\n    normalized = _normalize(patient_text)\n    return any(re.search(pattern, normalized) for pattern in _LOCATION_CONSENT_PATTERNS)\n\n\ndef should_consider_google_mission'''
helper_replacement = '''def _is_location_consent(patient_text: str) -> bool:\n    normalized = _normalize(patient_text)\n    return any(re.search(pattern, normalized) for pattern in _LOCATION_CONSENT_PATTERNS)\n\n\ndef _explicit_candidate_ordinal_index(patient_text: str) -> int | None:\n    """Resolve only an explicit bounded ordinal choice; never infer one from prose."""\n    normalized = re.sub(r"[.!?]+$", "", _normalize(patient_text)).strip()\n    normalized = re.sub(r"\\s+", " ", normalized)\n    patterns = (\n        (0, r"(?:no[, ]+)?(?:the )?first(?: one)?"),\n        (1, r"(?:no[, ]+)?(?:the )?second(?: one)?"),\n        (2, r"(?:no[, ]+)?(?:the )?third(?: one)?"),\n        (0, r"(?:no[, ]+)?(?:el |la )?(?:primero|primera)"),\n        (1, r"(?:no[, ]+)?(?:el |la )?(?:segundo|segunda)"),\n        (2, r"(?:no[, ]+)?(?:el |la )?(?:tercero|tercera)"),\n    )\n    for index, pattern in patterns:\n        if re.fullmatch(pattern, normalized):\n            return index\n    return None\n\n\ndef should_consider_google_mission'''
if text.count(helper_anchor) != 1:
    raise SystemExit('ordinal helper anchor mismatch')
text = text.replace(helper_anchor, helper_replacement, 1)

respond_anchor = '''        if not should_consider_google_mission(state, patient_text):\n            return None\n\n        location_consent_granted, consent_mission_id = self._grant_explicit_location_consent(state, patient_text)\n'''
respond_replacement = '''        if not should_consider_google_mission(state, patient_text):\n            return None\n\n        # A numbered choice over an already-discovered durable candidate list is\n        # deterministic patient intent, not a planning problem. Apply it directly\n        # instead of spending a Gemini round to translate "the second one" into 1.\n        ordinal_index = _explicit_candidate_ordinal_index(patient_text)\n        ordinal_mission_id = latest_google_mission_id(state)\n        if ordinal_index is not None and ordinal_mission_id:\n            try:\n                ordinal_mission = self.constellation.load_mission(state.profile.id, ordinal_mission_id)\n            except (KeyError, PermissionError):\n                ordinal_mission = None\n            candidates = (ordinal_mission.tool_outputs or {}).get("place_candidates") or [] if ordinal_mission else []\n            if ordinal_mission is not None and str(ordinal_mission.state) == "awaiting_selection" and candidates:\n                english = bool(re.search(r"\\b(first|second|third)\\b", _normalize(patient_text)))\n                if ordinal_index >= len(candidates):\n                    lead = (\n                        "That numbered option is not available in the current verified candidate list. I did not select a different place."\n                        if english else\n                        "Esa opción numerada no existe en la lista verificada actual. No seleccioné otro lugar."\n                    )\n                    receipt = {\n                        "mission_id": ordinal_mission_id,\n                        "state": str(ordinal_mission.state),\n                        "outcome": "blocked",\n                        "next_action": "choose_available_discovered_candidate",\n                        "requires_human_authorization": False,\n                        "authorization_kind": "",\n                        "executed_steps": [],\n                        "tool_count": 0,\n                        "durable_mission": True,\n                    }\n                    return ChatResponse(\n                        message=ChatMessage(\n                            patient_id=state.profile.id,\n                            role="assistant",\n                            author="HealthIA",\n                            content=f"{lead}\\n\\n{_receipt_markdown(receipt)}",\n                            metadata={\n                                "google_constellation": True,\n                                "google_mission_id": ordinal_mission_id,\n                                "google_mission_state": str(ordinal_mission.state),\n                                "google_mission_next_action": "choose_available_discovered_candidate",\n                                "requires_human_authorization": False,\n                                "authorization_kind": "",\n                                "public_action_receipt": receipt,\n                                "external_action_executed": False,\n                                "external_mutation_performed": False,\n                                "response_locale": "en" if english else "es",\n                            },\n                        )\n                    )\n\n                tool_result = GoogleMissionToolFacade(\n                    constellation=self.constellation,\n                    patient_id=state.profile.id,\n                    patient_text=patient_text,\n                ).select_discovered_candidate(ordinal_mission_id, ordinal_index)\n                selected_mission = self.constellation.load_mission(state.profile.id, ordinal_mission_id)\n                selected_place = selected_mission.selected_place or {}\n                expected_place = candidates[ordinal_index]\n                selection_verified = bool(selected_place) and str(selected_place.get("id") or "") == str(expected_place.get("id") or "")\n                if not bool(tool_result.get("ok")) or not selection_verified:\n                    raise RuntimeError("Deterministic candidate selection did not persist the exact requested discovered option")\n                ordinal_label = ("first", "second", "third")[ordinal_index] if english else ("primera", "segunda", "tercera")[ordinal_index]\n                lead = (\n                    f"I selected the {ordinal_label} verified option from this mission's Google Places results. I did not invent contact details or perform an external write."\n                    if english else\n                    f"Seleccioné la {ordinal_label} opción verificada de los resultados de Google Places de esta misión. No inventé datos de contacto ni hice una escritura externa."\n                )\n                receipt = {\n                    "mission_id": ordinal_mission_id,\n                    "state": str(selected_mission.state),\n                    "outcome": "advanced",\n                    "next_action": "continue_with_selected_candidate",\n                    "requires_human_authorization": False,\n                    "authorization_kind": "",\n                    "executed_steps": [\n                        "Applied the patient's exact candidate selection" if english else "Aplicó la selección exacta del paciente"\n                    ],\n                    "tool_count": 1,\n                    "durable_mission": True,\n                }\n                audit(\n                    state,\n                    actor="google_deterministic_policy",\n                    action="select_google_mission_candidate_by_explicit_ordinal",\n                    resource_type="google_health_mission",\n                    resource_id=ordinal_mission_id,\n                    details={\n                        "candidate_index": ordinal_index,\n                        "selection_verified": True,\n                        "executed_tool": "select_discovered_candidate",\n                        "external_mutation": False,\n                        "model_interpretation_required": False,\n                    },\n                )\n                return ChatResponse(\n                    message=ChatMessage(\n                        patient_id=state.profile.id,\n                        role="assistant",\n                        author="HealthIA",\n                        content=f"{lead}\\n\\n{_receipt_markdown(receipt)}",\n                        metadata={\n                            "google_constellation": True,\n                            "google_mission_id": ordinal_mission_id,\n                            "google_mission_state": str(selected_mission.state),\n                            "google_mission_next_action": "continue_with_selected_candidate",\n                            "requires_human_authorization": False,\n                            "authorization_kind": "",\n                            "health_os_control": True,\n                            "autonomy_policy": "advance_until_human_or_external_event_boundary",\n                            "public_action_receipt": receipt,\n                            "external_action_executed": False,\n                            "external_mutation_performed": False,\n                            "policy_executed_tool": "select_discovered_candidate",\n                            "deterministic_candidate_index": ordinal_index,\n                            "response_locale": "en" if english else "es",\n                        },\n                    )\n                )\n\n        location_consent_granted, consent_mission_id = self._grant_explicit_location_consent(state, patient_text)\n'''
if text.count(respond_anchor) != 1:
    raise SystemExit('respond ordinal insertion anchor mismatch')
text = text.replace(respond_anchor, respond_replacement, 1)
CHAT.write_text(text, encoding='utf-8')

test = TEST.read_text(encoding='utf-8').rstrip()
addition = r'''


def test_explicit_candidate_ordinal_parser_is_bounded_and_bilingual() -> None:
    from healthia_one.google_mission_chat import _explicit_candidate_ordinal_index

    assert _explicit_candidate_ordinal_index("The first one.") == 0
    assert _explicit_candidate_ordinal_index("The second one.") == 1
    assert _explicit_candidate_ordinal_index("No, the third one") == 2
    assert _explicit_candidate_ordinal_index("la primera") == 0
    assert _explicit_candidate_ordinal_index("No, la segunda") == 1
    assert _explicit_candidate_ordinal_index("el tercero") == 2
    assert _explicit_candidate_ordinal_index("the second clinic near me") is None
    assert _explicit_candidate_ordinal_index("second opinion") is None


def test_explicit_ordinal_selection_bypasses_adk_and_persists_exact_discovered_candidate() -> None:
    import asyncio
    from healthia_one.google_mission_chat import GoogleMissionConversationRouter
    from healthia_one.google_mission_runtime import MemoryMissionStore, MissionState
    from healthia_one.google_navigation_coordinator import HealthIAGoogleMissionCoordinator
    from healthia_one.models import ChatMessage, PatientState

    class _MustNotExecuteProvider:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("No provider connector is needed to select an already discovered candidate")

    class _Constellation:
        def __init__(self, patient_id: str):
            self.patient_id = patient_id
            self.store = MemoryMissionStore()
            self.coordinator = HealthIAGoogleMissionCoordinator(_MustNotExecuteProvider(), store=self.store)
        def load_mission(self, patient_id: str, mission_id: str):
            assert patient_id == self.patient_id
            value = self.store.load(patient_id, mission_id)
            if value is None:
                raise KeyError(mission_id)
            return value
        def grants(self, patient_id: str):
            assert patient_id == self.patient_id
            return []

    class _AdkMustNotInterpretOrdinal:
        ready = True
        async def run(self, **_kwargs):
            raise AssertionError("An explicit ordinal candidate choice must not require Gemini interpretation")

    state = PatientState()
    constellation = _Constellation(state.profile.id)
    mission = constellation.coordinator.create_navigation_mission(
        patient_id=state.profile.id,
        condition_or_need="follow-up care",
        provider_query="clinic",
        location_text="Santiago de los Caballeros, Dominican Republic",
    )
    mission.state = MissionState.AWAITING_SELECTION
    mission.tool_outputs["place_candidates"] = [
        {"id": "place-a", "displayName": {"text": "Clinic A"}, "formattedAddress": "Synthetic A"},
        {"id": "place-b", "displayName": {"text": "Clinic B"}, "formattedAddress": "Synthetic B"},
        {"id": "place-c", "displayName": {"text": "Clinic C"}, "formattedAddress": "Synthetic C"},
    ]
    constellation.store.save(mission)
    state.messages.append(
        ChatMessage(
            role="assistant",
            author="HealthIA",
            content="I found three verified options.",
            metadata={
                "google_mission_id": mission.id,
                "google_mission_state": "awaiting_selection",
                "google_mission_next_action": "patient_or_context_selects_candidate",
            },
        )
    )

    router = GoogleMissionConversationRouter.__new__(GoogleMissionConversationRouter)
    router.settings = None
    router.constellation = constellation
    router.adk = _AdkMustNotInterpretOrdinal()
    response = asyncio.run(router.respond(state, "The second one."))
    persisted = constellation.load_mission(state.profile.id, mission.id)

    assert persisted.selected_place["id"] == "place-b"
    assert response.message.metadata["google_mission_id"] == mission.id
    assert response.message.metadata["deterministic_candidate_index"] == 1
    assert response.message.metadata["policy_executed_tool"] == "select_discovered_candidate"
    assert response.message.metadata["external_action_executed"] is False
    assert response.message.metadata["external_mutation_performed"] is False
    receipt = response.message.metadata["public_action_receipt"]
    assert receipt["tool_count"] == 1
    assert any("selection" in str(step).lower() or "selección" in str(step).lower() for step in receipt["executed_steps"])
'''
if 'test_explicit_ordinal_selection_bypasses_adk_and_persists_exact_discovered_candidate' in test:
    raise SystemExit('ordinal selection regression already exists')
TEST.write_text(test + addition + '\n', encoding='utf-8')
