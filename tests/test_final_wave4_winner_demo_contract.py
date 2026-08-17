from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/final-live-english-demo.yml").read_text(encoding="utf-8")
RECORDER = (ROOT / "scripts/record_final_wave4_winner_demo.py").read_text(encoding="utf-8")
NARRATION = (ROOT / "scripts/final_wave4_winner_narration.txt").read_text(encoding="utf-8")


def test_winner_demo_deploys_exact_candidate_with_real_maps_secret() -> None:
    assert "pull_request:" not in WORKFLOW
    assert "push:" in WORKFLOW
    assert "branches: [main]" in WORKFLOW
    assert "if: github.ref == 'refs/heads/main'" in WORKFLOW
    assert "Prove checked-out SHA is the candidate SHA" in WORKFLOW
    assert "HEALTHIA_EXACT_HEAD_PASS" in WORKFLOW
    assert "HEALTHIA_EXACT_REVISION_BOUND" in WORKFLOW
    assert "GOOGLE_MAPS_API_KEY=${MAPS_SECRET_NAME}:latest" in WORKFLOW
    assert "--no-allow-unauthenticated" in WORKFLOW
    assert "--min-instances 0" in WORKFLOW
    assert "--max-instances 1" in WORKFLOW


def test_validation_and_publication_have_separate_least_privilege_jobs() -> None:
    assert "contents: read" in WORKFLOW
    assert "publish-winner:" in WORKFLOW
    assert "needs: exact-candidate-live-demo" in WORKFLOW
    assert "contents: write" in WORKFLOW
    assert "actions/download-artifact@v4" in WORKFLOW
    publish = WORKFLOW.index("publish-winner:")
    publish_block = WORKFLOW[publish:]
    assert "actions/checkout" not in publish_block
    assert "python scripts/" not in publish_block
    assert "SOURCE_SHA: ${{ github.sha }}" in publish_block


def test_winner_demo_enables_bounded_living_system_with_secret_manager_capability() -> None:
    assert "EVALUATION_SECRET_NAME: healthia-evaluation-access-key" in WORKFLOW
    assert "HEALTHIA_EVALUATION_ENABLED=true" in WORKFLOW
    assert "HEALTHIA_RELEASE_SHA=${SOURCE_SHA}" in WORKFLOW
    assert "HEALTHIA_EVALUATION_ACCESS_KEY=${EVALUATION_SECRET_NAME}:latest" in WORKFLOW
    assert "--min-instances 0" in WORKFLOW
    assert "--max-instances 1" in WORKFLOW
    assert "Materialize evaluator capability in a protected temporary file" in WORKFLOW
    assert "gcloud secrets versions access latest" in WORKFLOW
    assert "HEALTHIA_EVALUATION_ACCESS_KEY_FILE: ${{ runner.temp }}/healthia-evaluation-access-key" in WORKFLOW
    assert "shred -u \"$HEALTHIA_EVALUATION_KEY_FILE\"" in WORKFLOW
    assert "gh release upload \"$RELEASE_TAG\" \"$base/report.json\" \"$base/public-video-proof.json\"" in WORKFLOW


def test_tokens_stay_in_protected_files_and_never_github_outputs_or_curl_argv() -> None:
    assert "HEALTHIA_CLOUD_ID_TOKEN_FILE" in WORKFLOW
    assert "HEALTHIA_JUDGE_ID_TOKEN_FILE" in WORKFLOW
    assert "echo \"token=" not in WORKFLOW
    assert "steps.cloud.outputs.token" not in WORKFLOW
    assert "steps.judge.outputs.token" not in WORKFLOW
    assert 'curl --fail --silent --show-error -H "Authorization: Bearer ${token}"' not in WORKFLOW
    assert 'curl --fail --silent --show-error \\\n            -H "Authorization: Bearer ${access_token}"' not in WORKFLOW
    assert "--config \"$curl_config\"" in WORKFLOW
    assert "--config \"$voices_config\"" in WORKFLOW
    assert "--config \"$request_config\"" in WORKFLOW
    assert 'token_from_file(IDENTITY_TOKEN_FILE' in RECORDER
    assert 'token_from_file(JUDGE_TOKEN_FILE' in RECORDER
    assert 'os.getenv("HEALTHIA_CLOUD_ID_TOKEN"' not in RECORDER
    assert 'os.getenv("HEALTHIA_JUDGE_ID_TOKEN"' not in RECORDER
    assert 'path.unlink()' not in RECORDER


def test_winner_recorder_is_continuous_wave4_taskmaster_story() -> None:
    for marker in (
        '"Find a center for autism support near Santiago de los Caballeros."',
        '"I authorize my location for this mission."',
        '"The second one."',
        '"zero_places_before_mission_scoped_consent"',
        '"same_durable_mission_resumed_after_consent"',
        '"real_google_places_candidates_visible"',
        '"exact_second_candidate_selected_without_model_interpretation"',
        '"multimodal_original_result_and_provenance"',
        '"logout_login_restores_evidence_and_selected_google_mission"',
        '"synthetic_health_connect_event_visible_with_provenance"',
        '"unified_record_and_timeline_visible_after_relogin"',
        '"native_patient_workspace_unifies_twin_missions_activity_and_human_decisions"',
    ):
        assert marker in RECORDER
    assert 'record_video_dir=str(video_dir)' in RECORDER
    assert '"live_app_only": True' in RECORDER
    assert '"static_screenshots_used": False' in RECORDER
    assert "set_input_files(str(pdf_path))" in RECORDER
    assert 'api_post_json(page, "/api/demo/device-sync")' in RECORDER
    assert '.main-nav [data-open="devices"]' in RECORDER
    assert '.main-nav [data-open="timeline"]' in RECORDER
    assert '.main-nav [data-open="living"]' in RECORDER
    assert '"#livingTwinVersion"' in RECORDER
    assert '"#livingEvidenceCount"' in RECORDER
    assert '"#livingMissionCount"' in RECORDER
    assert '"#livingDecisionCount"' in RECORDER
    assert 'page.wait_for_timeout(11_000)' in RECORDER
    assert 'page.wait_for_timeout(10_000)' in RECORDER
    assert 'overlay(page, "HealthIA noticed the follow-up was overdue.' not in RECORDER


def test_recorder_proves_real_living_system_boundary_and_receipt() -> None:
    for marker in (
        'page.goto(f"{BASE_URL}/living"',
        "locked.status == 403",
        'X-HealthIA-Evaluation-Key',
        "patient_eval_living",
        "10 / 14",
        "#systemStatus",
        "WAITING FOR HUMAN",
        "waiting_human",
        "14 / 14",
        'completed_twin.get("version") == 3',
        'completed.get("model_calls") == 0',
        'completed_session.get("release_sha") == CANDIDATE_SHA',
        "living_system_capability_not_persisted_in_browser",
        "living_system_durable_replay_visible",
    ):
        assert marker in RECORDER
    assert '"access_control": "403_without_capability"' in RECORDER
    assert '"capability_transport": "password_input_then_in_memory_only"' in RECORDER
    assert '"X-HealthIA-Evaluation-Key": access_key' in RECORDER
    assert "element => { element.value = ''; }" in RECORDER
    assert '"evaluation_access_key"' not in RECORDER


def test_cutlock_requires_real_candidates_and_no_preconsent_execution() -> None:
    for marker in (
        "zero_places_before_mission_scoped_consent",
        "same_durable_mission_resumed_after_consent",
        "real_google_places_candidates_visible",
        "exact_second_candidate_selected_without_model_interpretation",
        "google_maps_uri_count",
        "candidate_count",
        "HEALTHIA_WINNER_CUTLOCK_PASS",
    ):
        assert marker in WORKFLOW
    assert "candidate_count') or 0) < 2" in WORKFLOW
    assert "google_maps_uri_count') or 0) < 2" in WORKFLOW


def test_winner_narration_requires_named_google_cloud_charon_male_voice() -> None:
    assert "texttospeech.googleapis.com" in WORKFLOW
    assert "gcloud services list" in WORKFLOW
    assert "en-US-Chirp3-HD-Charon" in WORKFLOW
    assert 'ssmlGender == "MALE"' in WORKFLOW
    assert "'gender':'MALE'" in WORKFLOW
    assert "'fallback_used':False" in WORKFLOW
    assert "flite-fallback" not in WORKFLOW
    assert "Named male Google Cloud voice synthesis failed closed" in WORKFLOW
    assert "limit=4300" in WORKFLOW
    assert "tts-request-{index:03d}.json" in WORKFLOW
    assert 'for request in "$request_dir"/tts-request-*.json' in WORKFLOW
    assert "-f concat -safe 0" in WORKFLOW
    assert "gcloud services enable" not in WORKFLOW
    assert "VOICE_PART_1" not in WORKFLOW
    assert "VOICE_PART_2" not in WORKFLOW
    assert "your health should never start over" in NARRATION.lower()
    assert "the second one" in NARRATION.lower()
    assert "authorization is not execution evidence" in NARRATION.lower()
    assert "nobody prompted it" in NARRATION.lower()
    assert "one living system" in NARRATION.lower()
    assert "before the patient types a message" in NARRATION.lower()
    assert "no slide deck and no mock screens" in NARRATION.lower()
    assert "inside the main patient workspace" in NARRATION.lower()
    assert "not a detached demonstration page" in NARRATION.lower()


def test_publication_happens_only_after_cutlock_and_is_anonymously_reverified() -> None:
    cutlock = WORKFLOW.index("CUTLOCK — reject unsupported or weak winner demo")
    publish = WORKFLOW.index("publish-winner:")
    public_proof = WORKFLOW.index("HEALTHIA_PUBLIC_EVIDENCE_SANITIZED_PASS")
    assert cutlock < publish < public_proof
    assert "gh release upload" in WORKFLOW
    assert "--clobber" in WORKFLOW
    assert "curl --fail --location --silent --show-error \"$public_url\"" in WORKFLOW
    assert "HEALTHIA_PUBLIC_WINNER_VIDEO_PASS" in WORKFLOW
    assert "SOURCE_SHA: ${{ github.sha }}" in WORKFLOW
    assert "--arg sha \"$SOURCE_SHA\"" in WORKFLOW
    assert "github.event.pull_request" not in WORKFLOW
    assert "HEALTHIA_PUBLIC_EVIDENCE_SANITIZED_PASS" in WORKFLOW
    assert 'test "$(jq -r \'.source_sha\' "$base/public-video-proof.json")" = "$SOURCE_SHA"' in WORKFLOW


def test_demo_removes_temporary_cloud_service_even_on_failure() -> None:
    assert "Remove temporary Cloud Run video service" in WORKFLOW
    tail = WORKFLOW.split("Remove temporary Cloud Run video service", 1)[1]
    assert "if: always()" in tail
    assert "gcloud run services delete" in tail
