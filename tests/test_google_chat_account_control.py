from pathlib import Path

from healthia_one.models import PatientState
from healthia_one.orchestrator import respond


CONTINUITY = Path("web/continuity.js").read_text(encoding="utf-8")
ACCOUNT = Path("web/account.js").read_text(encoding="utf-8")


def test_spanish_chat_google_connect_is_health_os_control_not_mission_or_external_action():
    response = respond(PatientState(), "Conecta mi cuenta Google")
    metadata = response.message.metadata
    assert metadata["ui_action"] == {"type": "open_google_connection"}
    assert metadata["health_os_control"] is True
    assert metadata["external_action_executed"] is False
    assert metadata.get("google_mission_candidate") is not True
    assert response.mission is None
    assert "no conectará" in response.message.content.lower()


def test_disconnect_language_only_opens_controls_and_does_not_disconnect_by_chat():
    response = respond(PatientState(), "Desconecta Google")
    metadata = response.message.metadata
    assert metadata["ui_action"]["type"] == "open_google_connection"
    assert metadata["external_action_executed"] is False
    assert response.mission is None
    assert "no conectará, desconectará ni autorizará nada" in response.message.content.lower()


def test_english_chat_google_control_is_bounded_ui_action():
    response = respond(PatientState(), "Connect my Google account")
    assert response.message.metadata["ui_action"] == {"type": "open_google_connection"}
    assert response.message.metadata["external_action_executed"] is False
    assert "will not connect, disconnect, or authorize anything by itself" in response.message.content.lower()


def test_deterministic_clinical_safety_still_precedes_google_account_control():
    response = respond(
        PatientState(),
        "Tengo dolor fuerte en el pecho y falta de aire; conecta mi cuenta Google",
    )
    assert response.message.risk_level.value == "urgent"
    assert response.message.metadata.get("ui_action", {}).get("type") != "open_google_connection"
    assert response.message.metadata.get("google_mission_candidate") is not True


def test_frontend_google_ui_action_dispatches_only_internal_open_event():
    assert 'action.type === "open_google_connection"' in CONTINUITY
    assert 'new CustomEvent("healthia:open-google-connection"' in CONTINUITY
    assert 'window.location.assign("/api/google-constellation/oauth/connect")' not in CONTINUITY
    assert 'document.addEventListener("healthia:open-google-connection"' in ACCOUNT
    assert "openGoogleConnectionSurface" in ACCOUNT


def test_unknown_chat_ui_action_fails_closed_in_controller():
    marker = 'else if (action.type === "open_google_connection")'
    start = CONTINUITY.index(marker)
    tail = CONTINUITY[start:start + 900]
    assert "else {\n        return false;\n      }" in tail
