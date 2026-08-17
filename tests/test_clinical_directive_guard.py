import pytest

from healthia_one.clinical_planner import normalize_dynamic_question_block
from healthia_one.gemini import CLINICAL_QUESTION_SYSTEM_INSTRUCTION


def payload(first_prompt: str, first_options: list[str] | None = None) -> dict:
    return {
        "questions": [
            {
                "id": "medicacion",
                "prompt": first_prompt,
                "options": first_options or ["No", "Sí, uno", "Sí, varios"],
                "multiple": False,
            },
            {
                "id": "fiebre",
                "prompt": "¿Has tenido fiebre o escalofríos desde que comenzó?",
                "options": ["No", "Fiebre", "Fiebre con escalofríos"],
                "multiple": False,
            },
            {
                "id": "dolor",
                "prompt": "¿Dónde sientes dolor además de la molestia principal?",
                "options": ["En ningún otro lugar", "Bajo vientre", "Espalda o costado"],
                "multiple": False,
            },
            {
                "id": "vomitos",
                "prompt": "¿Has tenido vómitos o dificultad para retener líquidos?",
                "options": ["No", "Una vez", "Varias veces"],
                "multiple": False,
            },
            {
                "id": "sangre",
                "prompt": "¿Has notado sangre visible o un empeoramiento rápido?",
                "options": ["No", "Sangre visible", "Empeoramiento rápido"],
                "multiple": False,
            },
        ]
    }


def test_medication_history_question_is_not_mistaken_for_prescribing() -> None:
    block = normalize_dynamic_question_block(
        payload("¿Toma algún medicamento o antibiótico actualmente?"),
        1,
    )
    assert block["questions"][0]["prompt"].startswith("¿Toma")


def test_direct_medication_command_remains_blocked() -> None:
    with pytest.raises(ValueError, match="indicación clínica no permitida"):
        normalize_dynamic_question_block(payload("Toma ciprofloxacino 500 mg cada 12 horas."), 1)


def test_stop_or_dose_change_commands_remain_blocked() -> None:
    for directive in ("Suspenda el medicamento actual.", "Aumente la dosis del medicamento."):
        with pytest.raises(ValueError, match="indicación clínica no permitida"):
            normalize_dynamic_question_block(payload(directive), 1)


def test_gemini_contract_requires_questions_and_nonimperative_first_person_options() -> None:
    instruction = CLINICAL_QUESTION_SYSTEM_INSTRUCTION
    assert "pregunta explícita entre signos ¿?" in instruction
    assert "respuestas factuales del paciente en primera persona" in instruction
    assert 'Ningún prompt u opción puede comenzar con "toma"' in instruction
