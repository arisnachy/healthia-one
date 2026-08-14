from pathlib import Path


def test_judge_docs_describe_healthia_explain_without_overclaiming_replacement_proof() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    devpost = Path("docs/DEVPOST_SUBMISSION.md").read_text(encoding="utf-8")
    architecture = Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    evidence = Path("docs/EVIDENCE.md").read_text(encoding="utf-8")

    for document in (readme, devpost, architecture, evidence):
        assert "HealthIA Explain" in document
        assert "Gemini 2.5 Pro TTS" in document
        assert "Veo 3.1 Fast" in document

    assert "31758267226" in evidence  # real Veo proof
    assert "31764094573" in evidence  # real Gemini TTS proof
    assert "31767221658" in evidence  # integrated deterministic gate

    # Preserve the truth boundary until a new Cloud/video proof is recorded.
    assert "does not by itself claim" in evidence
    assert "refreshed Cloud/video proof" in devpost
    assert "fresh Cloud/video proof required" in readme


def test_architecture_keeps_phi_out_of_veo_and_patient_values_controlled() -> None:
    architecture = Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "Veo receives only a generic visual prompt" in architecture
    assert "Controlled HealthIA cards" in architecture
    assert "patient/mission Google grant + receipt boundary" in architecture
