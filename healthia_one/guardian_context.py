from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from healthia_one.models import RiskLevel


class GuardianAssessment(BaseModel):
    """Minimal durable assessment contract promoted to the mainline.

    The broad experimental Guardian context engine remains quarantined.  The
    mainline autonomous-continuity circuit needs only this already-proven,
    serializable contract so a deterministic BP follow-up can cross the durable
    outbox boundary without importing geofence, medication or post-visit logic.
    """

    observation_id: str
    metric: str
    classification: str
    risk_level: RiskLevel = RiskLevel.INFO
    summary: str
    observed: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    inference: str = ""
    hypothesis: str = ""
    confidence: str = "low"
    repeated_pattern: bool = False
    notify_patient: bool = False
    requires_human_review: bool = False
    can_suppress_safety: bool = False
    provenance: list[str] = Field(default_factory=list)
