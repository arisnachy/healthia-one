from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "web" / "opportunities-ui.js").read_text(encoding="utf-8")
AUTH = (ROOT / "healthia_one" / "auth_web.py").read_text(encoding="utf-8")
API = (ROOT / "healthia_one" / "opportunity_api.py").read_text(encoding="utf-8")


def test_discoveries_is_a_first_class_health_os_view():
    assert 'data-open="discoveries"' in HTML
    assert 'id="view-discoveries"' in HTML
    assert 'id="discoveriesList"' in HTML
    assert 'id="opportunityProgramList"' in HTML
    assert 'id="opportunityReceiptList"' in HTML
    assert '<script src="/assets/opportunities-ui.js" defer></script>' in HTML


def test_discoveries_ui_is_chat_first_and_source_visible():
    assert "/api/opportunities" in JS
    assert "Original source" in JS
    assert "Official source" in JS
    assert "data-opportunity-chat-es" in JS
    assert "Compare it with my medication" in JS
    assert "Prepare the application" in JS
    assert "private reasoning" in JS


def test_opportunity_api_inherits_patient_auth_boundary():
    # Opportunity routes are mounted after the existing auth middleware but are
    # never added to the public allowlist.
    assert "app.include_router(build_opportunity_router(service))" in AUTH
    public_block = AUTH.split("public_exact = {", 1)[1].split("}", 1)[0]
    assert "/api/opportunities" not in public_block


def test_application_authorization_never_pretends_external_delivery_happened():
    assert '"external_action_performed": False' in API
    assert "durable receipt" in API
    assert "READY_TO_SUBMIT" in API or "ready" in API.lower()
