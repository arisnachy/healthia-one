from __future__ import annotations

import pytest

from healthia_one.result_capabilities import UnsupportedClinicalFormat, capability_manifest, validate_clinical_upload


def test_manifest_is_honest_about_supported_and_missing_routes() -> None:
    manifest = capability_manifest(5_000_000, False)
    assert manifest["clinical_validation"] == "not_validated_by_specialists"
    assert {"dicom", "fhir", "pacs", "lis", "digital_waveform"} <= set(manifest["not_implemented"])
    assert {item["extension"] for item in manifest["supported"]} == {".json", ".csv", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@pytest.mark.parametrize(
    ("filename", "mime", "content", "kind"),
    [
        ("study.dcm", "application/octet-stream", b"x" * 128 + b"DICM", "dicom"),
        ("bundle.json", "application/fhir+json", b'{"resourceType":"Bundle"}', "fhir"),
        ("result.hl7", "text/plain", b"MSH|^~\\&|LIS", "hl7_v2_or_cda"),
        ("ecg.scp", "application/octet-stream", b"wave", "digital_waveform"),
    ],
)
def test_unimplemented_medical_formats_are_explicitly_rejected(filename: str, mime: str, content: bytes, kind: str) -> None:
    with pytest.raises(UnsupportedClinicalFormat) as exc:
        validate_clinical_upload(filename, mime, content)
    assert exc.value.detected_format == kind


def test_supported_signatures_are_checked() -> None:
    assert validate_clinical_upload("report.pdf", "application/pdf", b"%PDF-1.7") == "gemini_multimodal"
    with pytest.raises(UnsupportedClinicalFormat):
        validate_clinical_upload("renamed.pdf", "application/pdf", b"not a pdf")
