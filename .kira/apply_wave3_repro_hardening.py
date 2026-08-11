from __future__ import annotations

from pathlib import Path

# 1) Cloud demo runtime: preserve the live-proven 60 second Gemini/ADK timeout.
deploy = Path("deployment/deploy-cloud-demo.ps1")
text = deploy.read_text(encoding="utf-8")
if '"HEALTHIA_LLM_TIMEOUT_SECONDS=60",' not in text:
    anchor = '    "HEALTHIA_AI_REQUEST_LIMIT=$RequestLimit",\n'
    if text.count(anchor) != 1:
        raise SystemExit("deploy timeout insertion anchor missing")
    text = text.replace(anchor, anchor + '    "HEALTHIA_LLM_TIMEOUT_SECONDS=60",\n', 1)
    deploy.write_text(text, encoding="utf-8")

# 2) Canonical recorder: assert the shipped conversational English chrome.
recorder = Path("scripts/record_submission_demo.py")
text = recorder.read_text(encoding="utf-8")
old_i18n = '        require("Case-specific questions" in first_block.inner_text(), "clinical block chrome is not English")\n'
new_i18n = (
    '        require("I will ask one useful thing at a time" in first_block.inner_text(), "clinical conversational block chrome is not English")\n'
    '        require(first_block.locator(".clinical-next-question").inner_text() == "Continue", "clinical conversational control is not English")\n'
)
if old_i18n in text:
    if text.count(old_i18n) != 1:
        raise SystemExit("stale recorder i18n assertion is not unique")
    text = text.replace(old_i18n, new_i18n, 1)
elif "clinical conversational block chrome is not English" not in text:
    raise SystemExit("recorder i18n hardening is neither old nor already applied")

old_location = 'Find a clinic that can help with follow-up care in Santiago.'
new_location = 'Find a clinic that can help with follow-up care in Santiago de los Caballeros, Dominican Republic.'
if old_location in text:
    if text.count(old_location) != 1:
        raise SystemExit("demo Santiago location prompt is not unique")
    text = text.replace(old_location, new_location, 1)
elif new_location not in text:
    raise SystemExit("exact demo location hardening is neither old nor already applied")
recorder.write_text(text, encoding="utf-8")

# 3) Shared browser helper: follow the shipped one-question-at-a-time interaction.
helper = Path("scripts/cloud_browser_judge_proof.py")
text = helper.read_text(encoding="utf-8")
old_helper = '''def answer_visible_block(page: Page) -> None:\n    \"\"\"Answer all five contract questions through the patient-visible 2+3 flow.\"\"\"\n    block = page.locator('.clinical-question-block[data-question-source=\"gemini_dynamic\"]').last\n    require(block.locator(\".clinical-question\").count() == 5, \"dynamic clinical block is not exactly five questions\")\n    require(block.locator(\".clinical-question:visible\").count() == 2, \"progressive clinical block must start with two visible questions\")\n    reveal = block.locator(\".clinical-show-all\")\n    require(reveal.is_visible(), \"progressive clinical block has no 2+3 continuation control\")\n    reveal.click()\n    require(block.locator(\".clinical-question:visible\").count() == 5, \"remaining three clinical questions did not reveal\")\n    for field in block.locator(\".clinical-question\").all():\n        field.locator(\".clinical-option\").first.click()\n    submit = block.locator(\".clinical-submit\")\n    require(submit.is_visible(), \"clinical submit did not appear after revealing all five questions\")\n    submit.click()\n'''
new_helper = '''def answer_visible_block(page: Page) -> None:\n    \"\"\"Answer all five Gemini questions through the shipped one-at-a-time conversation UI.\"\"\"\n    block = page.locator('.clinical-question-block[data-question-source=\"gemini_dynamic\"]').last\n    require(block.locator(\".clinical-question\").count() == 5, \"dynamic clinical block is not exactly five questions\")\n    control = block.locator(\".clinical-next-question\")\n    require(control.is_visible(), \"clinical conversational continuation control is missing\")\n    for index in range(5):\n        visible = block.locator(\".clinical-question:visible\")\n        require(visible.count() == 1, f\"clinical conversation must expose exactly one question at turn {index + 1}\")\n        field = visible.first\n        detail = field.locator(\".clinical-detail\")\n        require(detail.is_visible(), f\"clinical free-text answer is missing at turn {index + 1}\")\n        detail.fill(f\"Synthetic demo answer {index + 1}\")\n        expected = \"Send and continue\" if index == 4 else \"Continue\"\n        require(control.inner_text().strip() == expected, f\"clinical control text mismatch at turn {index + 1}\")\n        control.click()\n        if index < 4:\n            page.wait_for_timeout(150)\n            require(block.locator(\".clinical-question:visible\").count() == 1, f\"next clinical question did not advance at turn {index + 1}\")\n'''
if old_helper in text:
    if text.count(old_helper) != 1:
        raise SystemExit("stale 2+3 helper is not unique")
    text = text.replace(old_helper, new_helper, 1)
elif "shipped one-at-a-time conversation UI" not in text:
    raise SystemExit("browser helper hardening is neither old nor already applied")
helper.write_text(text, encoding="utf-8")

# 4) Lock the live findings into a compact regression contract.
test = Path("tests/test_wave3_repro_hardening.py")
test.write_text('''from __future__ import annotations\n\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_wave3_cloud_demo_uses_live_proven_adk_timeout() -> None:\n    deploy = (ROOT / "deployment/deploy-cloud-demo.ps1").read_text(encoding="utf-8")\n    assert '"HEALTHIA_LLM_TIMEOUT_SECONDS=60",' in deploy\n\n\ndef test_wave3_recorder_matches_shipped_conversational_clinical_ui() -> None:\n    recorder = (ROOT / "scripts/record_submission_demo.py").read_text(encoding="utf-8")\n    helper = (ROOT / "scripts/cloud_browser_judge_proof.py").read_text(encoding="utf-8")\n    assert "I will ask one useful thing at a time" in recorder\n    assert '.clinical-next-question' in recorder\n    assert "Case-specific questions" not in recorder\n    assert "shipped one-at-a-time conversation UI" in helper\n    assert "patient-visible 2+3 flow" not in helper\n    assert '.clinical-show-all' not in helper\n    assert '.clinical-submit' not in helper\n\n\ndef test_wave3_places_story_uses_unambiguous_patient_supplied_search_location() -> None:\n    recorder = (ROOT / "scripts/record_submission_demo.py").read_text(encoding="utf-8")\n    assert "Find a clinic that can help with follow-up care in Santiago de los Caballeros, Dominican Republic." in recorder\n\n\ndef test_location_consent_auto_resumes_the_same_safe_adk_tool() -> None:\n    chat = (ROOT / "healthia_one/google_mission_chat.py").read_text(encoding="utf-8")\n    assert "GoogleMissionToolFacade" in chat\n    assert "discover_care_options(consent_mission_id)" in chat\n    assert 'action="resume_google_health_mission_after_location_consent"' in chat\n    assert '"external_mutation_performed": False' in chat\n''', encoding="utf-8")

print("KIRA_WAVE3_REPRO_HARDENING_STAGED")
