import json

from healthia_one.results import explain_result, parse_result_file


def test_json_result_is_parsed_and_explained_without_diagnosis():
    payload = {"panel": "Demo", "results": [{"name": "LDL", "value": 140, "unit": "mg/dL"}]}
    result = parse_result_file("labs.json", json.dumps(payload).encode())
    explanation = explain_result(result)
    assert result.status == "parsed"
    lowered = explanation.lower()
    assert ("not a diagnosis" in lowered) or ("no un diagnóstico" in lowered)
    assert "LDL" in explanation


def test_pdf_is_not_fabricated():
    result = parse_result_file("scan.pdf", b"%PDF-demo")
    explanation = explain_result(result)
    assert result.status == "pending_multimodal"
    lowered = explanation.lower()
    assert ("will not invent" in lowered) or ("no inventaré" in lowered)
