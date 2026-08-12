from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wave4_resource_cards_surface_google_maps_and_truth_boundary() -> None:
    script = (ROOT / "web/icons.js").read_text(encoding="utf-8")

    assert "/api/google-constellation/missions/" in script
    assert "place_candidates" in script
    assert "googleMapsUri" in script
    assert "Google Maps" in script
    assert 'target="_blank"' in script
    assert 'rel="noopener noreferrer"' in script
    assert "Verifiable candidates · not a clinical referral" in script
    assert "Resultados verificables · no son una referencia clínica" in script
    assert "is-selected" in script


def test_wave4_resource_ui_translates_legacy_receipt_for_english_demo() -> None:
    script = (ROOT / "web/icons.js").read_text(encoding="utf-8")

    assert "Comprobante de misión" in script
    assert "Mission receipt" in script
    assert "Recorded temporary mission-scoped location consent" in script
    assert "Searched for verifiable resources in Google Places" in script
    assert "I need your permission to use location for this mission in Google Places" in script


def test_wave4_resource_ui_invalidates_stale_mission_cache_after_chat_settles() -> None:
    script = (ROOT / "web/icons.js").read_text(encoding="utf-8")

    assert "healthia:chat-settled" in script
    assert "resourceCache.clear()" in script
    assert "delete node.dataset.wave4Resources" in script
    assert "panel.dataset.missionId=missionId" in script
    assert "node.dataset.missionId===missionId" in script

    settled_listener = script.split("healthia:chat-settled", 1)[1].split("healthia:locale-changed", 1)[0]
    assert "resourceCache.clear()" in settled_listener
    assert "hydrateResources" in settled_listener
