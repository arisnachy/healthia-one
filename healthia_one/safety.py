from __future__ import annotations

import re
from dataclasses import dataclass

from healthia_one.models import RiskLevel, VitalRecord


@dataclass(frozen=True)
class SafetyDecision:
    level: RiskLevel
    message: str
    must_stop_normal_flow: bool = False


URGENT_PATTERNS = {
    "chest_pain": re.compile(r"\b(dolor (?:fuerte )?en el pecho|presión en el pecho)\b", re.I),
    "breathing": re.compile(r"\b(no puedo respirar|falta de aire intensa|me ahogo)\b", re.I),
    "neurologic": re.compile(
        r"\b(cara desviada|debilidad de un lado|no puedo hablar|habla arrastrada|pérdida súbita de visión)\b",
        re.I,
    ),
    "self_harm": re.compile(r"\b(quiero morir|hacerme daño|suicid)\w*\b", re.I),
}


def assess_text(message: str) -> SafetyDecision:
    matched = [name for name, pattern in URGENT_PATTERNS.items() if pattern.search(message)]
    if matched:
        return SafetyDecision(
            level=RiskLevel.URGENT,
            must_stop_normal_flow=True,
            message=(
                "Lo que describes puede requerir atención inmediata. No esperes una respuesta "
                "adicional de HealthIA: busca servicios de emergencia locales o una evaluación "
                "presencial ahora. No conduzcas si te sientes inestable."
            ),
        )
    return SafetyDecision(RiskLevel.INFO, "No deterministic urgent-language trigger detected.")


def assess_vital(vital: VitalRecord) -> SafetyDecision:
    if vital.systolic is not None and vital.diastolic is not None:
        if vital.systolic >= 180 or vital.diastolic >= 120:
            symptoms = {item.lower() for item in vital.symptoms}
            if symptoms:
                return SafetyDecision(
                    RiskLevel.URGENT,
                    "La presión registrada es extremadamente alta y reportaste síntomas. "
                    "Busca evaluación urgente ahora.",
                    True,
                )
            return SafetyDecision(
                RiskLevel.PRIORITY,
                "La presión registrada es extremadamente alta. Repite la medición tras cinco "
                "minutos de reposo con técnica correcta y busca orientación clínica inmediata; "
                "si aparecen síntomas neurológicos, dolor de pecho o falta de aire, usa emergencias.",
                True,
            )
        if vital.systolic >= 160 or vital.diastolic >= 100:
            return SafetyDecision(
                RiskLevel.PRIORITY,
                "La medición está muy por encima del objetivo habitual. Conviene repetirla con "
                "técnica correcta y contactar al equipo clínico pronto.",
            )
    if vital.oxygen_saturation is not None and vital.oxygen_saturation < 90:
        return SafetyDecision(
            RiskLevel.URGENT,
            "La saturación registrada es muy baja. Busca evaluación urgente, especialmente si "
            "presentas falta de aire, confusión o coloración azulada.",
            True,
        )
    return SafetyDecision(RiskLevel.INFO, "No deterministic vital-sign escalation threshold met.")
