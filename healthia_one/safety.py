from __future__ import annotations

import re
from dataclasses import dataclass

from healthia_one.language import current_requested_locale, resolve_response_locale
from healthia_one.models import RiskLevel, VitalRecord


@dataclass(frozen=True)
class SafetyDecision:
    level: RiskLevel
    message: str
    must_stop_normal_flow: bool = False


URGENT_PATTERNS = {
    "chest_pain": re.compile(r"\b(dolor (?:fuerte )?en el pecho|presión en el pecho|severe chest pain|chest pain|chest pressure)\b", re.I),
    "breathing": re.compile(r"\b(no puedo respirar|falta de aire intensa|me ahogo|cannot breathe|can't breathe|severe shortness of breath|gasping for air)\b", re.I),
    "neurologic": re.compile(
        r"\b(cara desviada|debilidad de un lado|no puedo hablar|habla arrastrada|pérdida súbita de visión|face droop|one[- ]sided weakness|cannot speak|can't speak|slurred speech|sudden vision loss)\b",
        re.I,
    ),
    "self_harm": re.compile(r"\b(quiero morir|hacerme daño|suicid\w*|want to die|hurt myself|kill myself|suicid\w*)\b", re.I),
}


def _locale_for_text(message: str) -> str:
    return resolve_response_locale(message, requested_locale=current_requested_locale(), profile_locale="en")


def _text(locale: str, en: str, es: str) -> str:
    return es if locale == "es" else en


def assess_text(message: str) -> SafetyDecision:
    matched = [name for name, pattern in URGENT_PATTERNS.items() if pattern.search(message)]
    if matched:
        locale = _locale_for_text(message)
        return SafetyDecision(
            level=RiskLevel.URGENT,
            must_stop_normal_flow=True,
            message=_text(
                locale,
                (
                    "What you describe may require immediate care. Do not wait for another HealthIA response: "
                    "use local emergency services or seek in-person emergency evaluation now. Do not drive yourself if you feel unstable."
                ),
                (
                    "Lo que describes puede requerir atención inmediata. No esperes una respuesta adicional de HealthIA: "
                    "busca servicios de emergencia locales o una evaluación presencial ahora. No conduzcas si te sientes inestable."
                ),
            ),
        )
    return SafetyDecision(RiskLevel.INFO, "No deterministic urgent-language trigger detected.")


def assess_vital(vital: VitalRecord) -> SafetyDecision:
    locale = "es" if current_requested_locale() == "es" else "en"
    if vital.systolic is not None and vital.diastolic is not None:
        if vital.systolic >= 180 or vital.diastolic >= 120:
            symptoms = {item.lower() for item in vital.symptoms}
            if symptoms:
                return SafetyDecision(
                    RiskLevel.URGENT,
                    _text(
                        locale,
                        "The recorded blood pressure is extremely high and symptoms were reported. Seek urgent evaluation now.",
                        "La presión registrada es extremadamente alta y reportaste síntomas. Busca evaluación urgente ahora.",
                    ),
                    True,
                )
            return SafetyDecision(
                RiskLevel.PRIORITY,
                _text(
                    locale,
                    (
                        "The recorded blood pressure is extremely high. Repeat it after five minutes of rest with correct technique and seek prompt clinical guidance; "
                        "if neurologic symptoms, chest pain, or shortness of breath appear, use emergency services."
                    ),
                    (
                        "La presión registrada es extremadamente alta. Repite la medición tras cinco minutos de reposo con técnica correcta y busca orientación clínica inmediata; "
                        "si aparecen síntomas neurológicos, dolor de pecho o falta de aire, usa emergencias."
                    ),
                ),
                True,
            )
        if vital.systolic >= 160 or vital.diastolic >= 100:
            return SafetyDecision(
                RiskLevel.PRIORITY,
                _text(
                    locale,
                    "The measurement is well above the usual target. Repeat it with correct technique and contact the clinical team soon.",
                    "La medición está muy por encima del objetivo habitual. Conviene repetirla con técnica correcta y contactar al equipo clínico pronto.",
                ),
            )
    if vital.oxygen_saturation is not None and vital.oxygen_saturation < 90:
        return SafetyDecision(
            RiskLevel.URGENT,
            _text(
                locale,
                "The recorded oxygen saturation is very low. Seek urgent evaluation, especially with shortness of breath, confusion, or bluish coloration.",
                "La saturación registrada es muy baja. Busca evaluación urgente, especialmente si presentas falta de aire, confusión o coloración azulada.",
            ),
            True,
        )
    return SafetyDecision(RiskLevel.INFO, "No deterministic vital-sign escalation threshold met.")