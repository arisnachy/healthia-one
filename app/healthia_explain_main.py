from __future__ import annotations

from app.main import app, service
from healthia_one.education_video import PatientEducationVideoRouter
from healthia_one.education_video_api import build_education_video_router
from healthia_one.education_video_models import is_acceptance, is_rejection, is_video_request


def _latest_assistant_offered_video(state) -> bool:
    for message in reversed(state.messages):
        if message.role != "assistant":
            continue
        return isinstance((message.metadata or {}).get("education_video_offer"), dict)
    return False


def install_healthia_explain() -> None:
    if getattr(service.gemini, "_healthia_explain_installed", False):
        return

    education = PatientEducationVideoRouter(
        service.settings,
        client_provider=service.gemini._get_client,
        cost_guard=service.gemini.cost_guard,
    )
    original_enhance = service.gemini.enhance

    async def enhance_with_patient_education(state, patient_text, draft):
        offered = _latest_assistant_offered_video(state)
        media_turn = is_video_request(patient_text) or (
            offered and (is_acceptance(patient_text) or is_rejection(patient_text))
        )
        if media_turn:
            media_response = await education.respond(state, patient_text)
            if media_response is not None:
                return media_response
        result = await original_enhance(state, patient_text, draft)
        return education.maybe_attach_offer(state, patient_text, result)

    service.gemini.enhance = enhance_with_patient_education
    service.gemini._healthia_explain_installed = True
    app.state.healthia_explain = education
    app.include_router(build_education_video_router(service))


install_healthia_explain()

__all__ = ["app", "service", "install_healthia_explain"]
