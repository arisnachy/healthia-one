from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/final-live-english-demo.yml").read_text(encoding="utf-8")
RECORDER = (ROOT / "scripts/record_final_wave4_winner_demo.py").read_text(encoding="utf-8")
NARRATION = (ROOT / "scripts/final_wave4_winner_narration.txt").read_text(encoding="utf-8")


def test_winner_demo_deploys_exact_candidate_with_real_maps_secret() -> None:
    assert "Prove checked-out SHA is the candidate SHA" in WORKFLOW
    assert "HEALTHIA_EXACT_HEAD_PASS" in WORKFLOW
    assert "HEALTHIA_EXACT_REVISION_BOUND" in WORKFLOW
    assert "GOOGLE_MAPS_API_KEY=${MAPS_SECRET_NAME}:latest" in WORKFLOW
    assert "--no-allow-unauthenticated" in WORKFLOW
    assert "--min 0" in WORKFLOW
    assert "--max 1" in WORKFLOW


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
    ):
        assert marker in RECORDER
    assert 'record_video_dir=str(video_dir)' in RECORDER
    assert '"live_app_only": True' in RECORDER
    assert '"static_screenshots_used": False' in RECORDER
    assert "set_input_files(str(pdf_path))" in RECORDER


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
    assert "gcloud services enable" not in WORKFLOW
    assert "VOICE_PART_1" not in WORKFLOW
    assert "VOICE_PART_2" not in WORKFLOW
    assert "your health should never start over" in NARRATION.lower()
    assert "the second one" in NARRATION.lower()
    assert "authorization is not execution evidence" in NARRATION.lower()
    assert "nobody prompted it" in NARRATION.lower()


def test_publication_happens_only_after_cutlock_and_is_anonymously_reverified() -> None:
    cutlock = WORKFLOW.index("CUTLOCK — reject unsupported or weak winner demo")
    publish = WORKFLOW.index("Publish winner video as stable GitHub Release")
    public_proof = WORKFLOW.index("Prove public winner video is anonymous and byte-identical")
    assert cutlock < publish < public_proof
    assert "gh release upload" in WORKFLOW
    assert "--clobber" in WORKFLOW
    assert "curl --fail --location --silent --show-error \"$public_url\"" in WORKFLOW
    assert "HEALTHIA_PUBLIC_WINNER_VIDEO_PASS" in WORKFLOW
    assert "SOURCE_HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}" in WORKFLOW
    assert "'source_sha':os.environ['SOURCE_HEAD_SHA']" in WORKFLOW
    assert "'source_sha':os.environ.get('GITHUB_SHA'" not in WORKFLOW


def test_demo_removes_temporary_cloud_service_even_on_failure() -> None:
    assert "Remove temporary Cloud Run video service" in WORKFLOW
    tail = WORKFLOW.split("Remove temporary Cloud Run video service", 1)[1]
    assert "if: always()" in tail
    assert "gcloud run services delete" in tail
