from __future__ import annotations

from healthia_one.models import ChatResponse, RiskLevel


SOCIAL_ONLY = {
    "hola",
    "buenas",
    "buenos dias",
    "buenos días",
    "buenas tardes",
    "buenas noches",
    "gracias",
    "muchas gracias",
    "ok",
    "okay",
}


def should_use_patient_chat_model(patient_text: str, draft: ChatResponse) -> bool:
    """Spend a chat-model call only when probabilistic understanding adds value.

    Clinical interview blocks are generated dynamically and therefore remain model
    eligible. A deterministic action target means the requested tool/data route is
    already resolved, so sending the same result through Gemini would add cost
    without changing the action. Short social messages also stay local.
    """

    if draft.message.risk_level == RiskLevel.URGENT:
        return False
    interview = draft.message.metadata.get("clinical_interview")
    if isinstance(interview, dict):
        return True
    if draft.message.metadata.get("action_target"):
        return False
    normalized = " ".join(str(patient_text or "").lower().strip().split())
    if normalized.strip(".!¡¿? ") in SOCIAL_ONLY:
        return False
    return True
