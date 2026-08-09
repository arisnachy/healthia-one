from __future__ import annotations

from typing import Any


def provider_contact_payload(mission, *, subject: str, body: str) -> dict[str, Any]:
    email = str(mission.provider_email or "").strip()
    if not email:
        raise ValueError("Selected provider has no verified/entered email destination")
    return {
        "to": [email],
        "subject": str(subject),
        "body": str(body),
    }


def calendar_event_payload(mission, *, summary: str, time_zone: str) -> dict[str, Any]:
    slot = mission.selected_slot
    if slot is None:
        raise ValueError("No provider-offered slot is selected")
    event = {
        "summary": str(summary),
        "location": str(mission.selected_place.get("formattedAddress") or ""),
        "description": f"HealthIA mission {mission.id}. No diagnosis details are placed in the title.",
        "start": {"dateTime": slot.start, "timeZone": str(time_zone)},
        "end": {"dateTime": slot.end, "timeZone": str(time_zone)},
    }
    return {"calendar_id": "primary", "event": event}


def followup_task_payload(mission) -> dict[str, Any]:
    slot = mission.selected_slot
    if slot is None:
        raise ValueError("No provider-offered slot is selected")
    return {
        "tasklist": "@default",
        "task": {
            "title": "Prepare for health appointment",
            "notes": "Review required documents and questions in HealthIA before the appointment.",
            "due": slot.start,
        },
    }
