from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from healthia_one.models import MedicationPlan, PatientProfile, PatientState, ReproductiveHealth


DOSE_RE = re.compile(r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>mg|mcg|µg|g|ml|mL|UI|IU)\b", re.IGNORECASE)
FREQUENCY_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"cada\s+24\s*h(?:oras)?|una\s+vez\s+al\s+d[ií]a|diari[oa]", re.I), 1.0, "cada 24 horas"),
    (re.compile(r"cada\s+12\s*h(?:oras)?|dos\s+veces\s+al\s+d[ií]a", re.I), 2.0, "cada 12 horas"),
    (re.compile(r"cada\s+8\s*h(?:oras)?|tres\s+veces\s+al\s+d[ií]a", re.I), 3.0, "cada 8 horas"),
    (re.compile(r"cada\s+6\s*h(?:oras)?|cuatro\s+veces\s+al\s+d[ií]a", re.I), 4.0, "cada 6 horas"),
]
ROUTE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(v[ií]a\s+)?oral\b|\bvo\b", re.I), "oral"),
    (re.compile(r"\bsubcut[aá]ne[oa]\b|\bsc\b", re.I), "subcutánea"),
    (re.compile(r"\bintramuscular\b|\bim\b", re.I), "intramuscular"),
    (re.compile(r"\bintravenos[oa]\b|\biv\b", re.I), "intravenosa"),
    (re.compile(r"\bt[oó]pic[oa]\b", re.I), "tópica"),
    (re.compile(r"\binhalad[oa]\b", re.I), "inhalada"),
]
FORM_WORDS = {
    "tableta": "tableta",
    "tabletas": "tableta",
    "comprimido": "comprimido",
    "cápsula": "cápsula",
    "capsula": "cápsula",
    "jarabe": "jarabe",
    "solución": "solución",
    "solucion": "solución",
    "inyección": "inyección",
    "inyeccion": "inyección",
}


def age_years(birth_date: date | None, today: date | None = None) -> int | None:
    """Return age only when the patient actually supplied a birth date."""
    if birth_date is None:
        return None
    today = today or date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def calculate_bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if weight_kg is None or height_cm is None or height_cm <= 0:
        return None
    return round(weight_kg / ((height_cm / 100) ** 2), 1)


def nutritional_status(*, bmi: float | None, profile: PatientProfile) -> str:
    if bmi is None:
        return "Sin dato"
    if profile.reproductive_health.pregnancy_status == "pregnant":
        return "Requiere evaluación específica del embarazo"
    age = age_years(profile.birth_date)
    if age is None:
        return "Requiere edad para clasificar"
    if age < 18:
        return "Requiere percentiles por edad y sexo"
    if bmi < 18.5:
        return "Bajo peso"
    if bmi < 25:
        return "Peso adecuado"
    if bmi < 30:
        return "Preobesidad"
    if bmi < 35:
        return "Obesidad clase I"
    if bmi < 40:
        return "Obesidad clase II"
    return "Obesidad clase III"


def pregnancy_summary(reproductive: ReproductiveHealth, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    result: dict[str, Any] = {
        "status": reproductive.pregnancy_status,
        "last_menstrual_period": reproductive.last_menstrual_period,
        "estimated_due_date": reproductive.estimated_due_date,
        "gestational_age_weeks": None,
        "gestational_age_days": None,
        "postpartum_day": None,
        "postpartum_active": False,
        "dating_note": "",
    }
    if reproductive.pregnancy_status == "pregnant":
        lmp = reproductive.last_menstrual_period
        due = reproductive.estimated_due_date
        if lmp:
            days = max((today - lmp).days, 0)
            result["gestational_age_weeks"] = days // 7
            result["gestational_age_days"] = days % 7
            result["estimated_due_date"] = due or lmp + timedelta(days=280)
            result["dating_note"] = (
                "Estimación por fecha de última menstruación; debe confirmarse con el profesional y la ecografía indicada."
            )
        elif due:
            days = 280 - (due - today).days
            if days >= 0:
                result["gestational_age_weeks"] = days // 7
                result["gestational_age_days"] = days % 7
            result["dating_note"] = "Estimación calculada desde la fecha probable de parto registrada."
    if reproductive.pregnancy_status == "postpartum" and reproductive.delivery_date:
        postpartum_day = max((today - reproductive.delivery_date).days, 0)
        result["postpartum_day"] = postpartum_day
        result["postpartum_active"] = postpartum_day <= 42
        result["dating_note"] = (
            "Puerperio temprano dentro de las primeras seis semanas. Mantener seguimiento materno y del recién nacido."
            if postpartum_day <= 42
            else "La fecha registrada supera las primeras seis semanas posparto."
        )
    return result


def normalize_medication_text(text: str) -> MedicationPlan:
    original = " ".join(text.strip().split())
    if len(original) < 2:
        raise ValueError("Medication text is required")
    dose_match = DOSE_RE.search(original)
    dose_value = None
    dose_unit = ""
    strength = ""
    if dose_match:
        dose_value = float(dose_match.group("value").replace(",", "."))
        dose_unit = dose_match.group("unit").lower().replace("µ", "mc")
        strength = f"{dose_value:g} {dose_unit}"
    route = "oral"
    for pattern, candidate in ROUTE_PATTERNS:
        if pattern.search(original):
            route = candidate
            break
    frequency = None
    schedule = ""
    for pattern, candidate_frequency, candidate_schedule in FREQUENCY_PATTERNS:
        if pattern.search(original):
            frequency = candidate_frequency
            schedule = candidate_schedule
            break
    dosage_form = ""
    lowered = original.lower()
    for word, normalized in FORM_WORDS.items():
        if word in lowered:
            dosage_form = normalized
            break
    name_part = original
    if dose_match:
        name_part = original[: dose_match.start()].strip(" -,")
    if not name_part:
        name_part = original.split()[0]
    return MedicationPlan(
        original_text=original,
        name=name_part[:160],
        strength=strength,
        dose_value=dose_value,
        dose_unit=dose_unit,
        dosage_form=dosage_form,
        route=route,
        schedule=schedule,
        frequency_times_per_day=frequency,
        instructions="Verificar nombre, dosis, vía y frecuencia antes de confirmar.",
        verification_status="unverified",
    )


def vital_snapshot(state: PatientState) -> dict[str, Any]:
    vital = state.vitals[-1] if state.vitals else None
    weight = state.weights[-1] if state.weights else None
    bmi = calculate_bmi(weight.weight_kg if weight else None, state.profile.height_cm)
    return {
        "blood_pressure": (
            f"{vital.systolic}/{vital.diastolic}" if vital and vital.systolic and vital.diastolic else None
        ),
        "heart_rate_bpm": vital.pulse if vital else None,
        "respiratory_rate_rpm": vital.respiratory_rate if vital else None,
        "blood_glucose_mg_dl": vital.blood_glucose_mg_dl if vital else None,
        "cholesterol_mg_dl": vital.cholesterol_mg_dl if vital else None,
        "oxygen_saturation_percent": vital.oxygen_saturation if vital else None,
        "temperature_c": vital.temperature_c if vital else None,
        "weight_kg": weight.weight_kg if weight else None,
        "height_cm": state.profile.height_cm,
        "bmi": bmi,
        "nutritional_status": nutritional_status(bmi=bmi, profile=state.profile),
        "measured_at": vital.measured_at if vital else (weight.measured_at if weight else None),
    }


def profile_summary(state: PatientState) -> dict[str, Any]:
    active_meds = [item.model_dump(mode="json") for item in state.medication_plans if item.active]
    return {
        "profile": state.profile.model_dump(mode="json"),
        "age_years": age_years(state.profile.birth_date),
        "vitals": vital_snapshot(state),
        "pregnancy": pregnancy_summary(state.profile.reproductive_health),
        "medications": active_meds,
        "family_member_count": len(state.family_members),
        "document_count": len(state.documents),
    }
