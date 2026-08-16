from __future__ import annotations


MISSION_TAG_PREFIX = "mission:"


def mission_tag(mission_id: str) -> str:
    return f"{MISSION_TAG_PREFIX}{mission_id}"


def linked_to_mission(document, mission_id: str) -> bool:
    """Return whether stored evidence was explicitly tagged to one mission.

    The mainline BP circuit needs this predicate only to preserve the existing
    human-review closure rule. No evidence-link mutation API is promoted here.
    """
    return mission_tag(mission_id) in set(document.tags)


def linked_mission_ids(document) -> list[str]:
    return [
        tag[len(MISSION_TAG_PREFIX):]
        for tag in document.tags
        if tag.startswith(MISSION_TAG_PREFIX) and len(tag) > len(MISSION_TAG_PREFIX)
    ]
