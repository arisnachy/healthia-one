from __future__ import annotations

"""Wave 4 resource-navigation intent extensions.

The core Google mission router remains the policy owner. This module only widens
its deterministic entry vocabulary so patient language such as "support groups",
"community resources" or "government assistance" reaches the same durable,
consent-gated Google mission path instead of falling through to a generic reply.
"""

from healthia_one import google_mission_chat


RESOURCE_NAVIGATION_PATTERNS = (
    r"\bbuscame (?:un |una |los |las )?(?:grupo de apoyo|recurso|recursos|servicio social|servicios sociales|ayuda estatal|ayudas estatales).*(?:cerca|alrededor|en )",
    r"\bbusca (?:un |una |los |las )?(?:grupo de apoyo|grupos de apoyo|fundacion|fundaciones|recursos|ayudas|servicios sociales).*(?:cerca|alrededor|en )",
    r"\b(?:grupos? de apoyo|fundaciones?|recursos?|servicios? sociales?|ayudas? estatales?) (?:cerca|alrededor|en )",
    r"\bfind (?:a |an |some )?(?:foundation|support group|support groups|support resources|community resources|social services|government assistance|government support).*(?:near|nearby|around| in )",
    r"\bfind (?:nearby|local) (?:support|community|government|social service|social services|resource|resources|assistance)",
    r"\b(?:support groups?|community resources?|social services?|government assistance|government support) (?:near|nearby|around| in )",
)


def install() -> None:
    existing = tuple(google_mission_chat._NAVIGATION_PATTERNS)
    merged = list(existing)
    for pattern in RESOURCE_NAVIGATION_PATTERNS:
        if pattern not in merged:
            merged.append(pattern)
    google_mission_chat._NAVIGATION_PATTERNS = tuple(merged)


install()
