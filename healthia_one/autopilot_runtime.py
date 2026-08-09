from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from healthia_one.autopilot_claims import EventClaimStore, MemoryEventClaimStore
from healthia_one.autopilot_receipts import AutopilotReceipt, AutopilotReceiptStore
from healthia_one.models import PatientState, new_id
from healthia_one.opportunity_autopilot import (
    ApplicationPacket,
    Discovery,
    DiscoveryStatus,
    EvidenceTier,
    OpportunityVault,
    add_discovery,
    evaluate_program_eligibility,
    opportunity_snapshot,
    prepare_application,
    register_program,
    sync_watch_topics,
    upsert_application,
)
from healthia_one.opportunity_store import OpportunityStore
from healthia_one.research_radar import GroundedResourceRadar, ScientificRadar, candidate_to_discovery


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutopilotEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    patient_id: str
    event_type: Literal[
        "patient_state_changed",
        "result.persisted",
        "family_history.changed",
        "medication.changed",
        "appointment.changed",
        "scheduled.discovery_refresh",
        "manual.discovery_refresh",
        "manual.resource_refresh",
        "prepare_application",
    ]
    occurred_at: datetime = Field(default_factory=utc_now)
    subject_id: str = ""
    condition: str = ""
    program_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class AutopilotAction(BaseModel):
    action: str
    status: Literal["planned", "completed", "skipped", "blocked"]
    reason: str
    resource_id: str = ""


class AutopilotRunReport(BaseModel):
    event_id: str
    duplicate: bool = False
    actions: list[AutopilotAction] = Field(default_factory=list)
    discoveries_added: list[str] = Field(default_factory=list)
    programs_added: list[str] = Field(default_factory=list)
    applications_updated: list[str] = Field(default_factory=list)
    cost_class: Literal["zero_llm", "bounded_paid_search"] = "zero_llm"
    snapshot: dict[str, Any] = Field(default_factory=dict)


def event_key(event: AutopilotEvent) -> str:
    raw = f"{event.patient_id}|{event.id}|{event.event_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _topic_relevance(topic_condition: str, title: str, abstract: str) -> float:
    """Score within a source query, not across the open web.

    A candidate returned by PubMed/Europe PMC/ClinicalTrials for this exact topic
    already has query provenance. Keep a conservative floor so a Spanish topic
    such as "autismo" does not reject an English title containing "autism" merely
    because lexical overlap is zero. Exact lexical support can raise the score.
    """
    condition_tokens = {item for item in topic_condition.lower().replace("-", " ").split() if len(item) >= 3}
    haystack = f"{title} {abstract}".lower()
    if not condition_tokens:
        return 0.35
    matches = sum(1 for token in condition_tokens if token in haystack)
    lexical = matches / max(len(condition_tokens), 1)
    exact_bonus = 0.2 if topic_condition.lower() in haystack else 0
    return min(1.0, max(0.35, lexical + exact_bonus))


def _interrupt_score(discovery: Discovery) -> float:
    tier_weight = {
        EvidenceTier.GUIDELINE: 0.88,
        EvidenceTier.SYSTEMATIC_REVIEW: 0.78,
        EvidenceTier.RANDOMIZED_TRIAL: 0.75,
        EvidenceTier.REGULATORY_UPDATE: 0.9,
        EvidenceTier.CLINICAL_TRIAL: 0.55,
        EvidenceTier.OBSERVATIONAL: 0.45,
        EvidenceTier.CASE_SERIES: 0.25,
        EvidenceTier.PREPRINT: 0.18,
        EvidenceTier.UNKNOWN: 0.2,
        EvidenceTier.OFFICIAL_PROGRAM: 0.8,
        EvidenceTier.COMMUNITY_RESOURCE: 0.55,
    }
    score = tier_weight.get(discovery.source.evidence_tier, 0.2)
    score = (score * 0.7) + (discovery.relevance_score * 0.3)
    if discovery.relation != "self":
        score -= 0.08
    return max(0, min(round(score, 3), 1))


class OpportunityAutopilot:
    """Durable event-to-opportunity engine.

    A leased patient-scoped claim is acquired before work starts. The claim is
    completed only after state and optional public receipt persistence succeed.
    Exceptions mark the claim FAILED, so a redelivery can retry instead of being
    silently discarded. Model/network work remains explicit per run.
    """

    def __init__(
        self,
        store: OpportunityStore,
        *,
        scientific_radar: ScientificRadar | None = None,
        resource_radar: GroundedResourceRadar | None = None,
        claim_store: EventClaimStore | None = None,
        receipt_store: AutopilotReceiptStore | None = None,
    ) -> None:
        self.store = store
        self.scientific_radar = scientific_radar
        self.resource_radar = resource_radar
        self.claim_store = claim_store or MemoryEventClaimStore()
        self.receipt_store = receipt_store

    def load(self, patient_id: str) -> OpportunityVault:
        return self.store.load(patient_id)

    def _select_topics(self, vault: OpportunityVault, event: AutopilotEvent) -> list:
        topics = [item for item in vault.watch_topics if item.enabled]
        if event.subject_id:
            topics = [item for item in topics if item.subject_id == event.subject_id]
        if event.condition:
            normalized = event.condition.lower().strip()
            topics = [item for item in topics if item.condition.lower().strip() == normalized]
        topics.sort(key=lambda item: (item.relation != "self", item.created_at))
        return topics[:4]

    def _save_receipt(self, event: AutopilotEvent, claim_id: str, report: AutopilotRunReport) -> None:
        if self.receipt_store is None:
            return
        receipt = AutopilotReceipt(
            id=claim_id,
            patient_id=event.patient_id,
            event_id=event.id,
            event_type=event.event_type,
            status="completed",
            cost_class=report.cost_class,
            actions=[item.model_dump(mode="json") for item in report.actions],
            discovery_ids=list(report.discoveries_added),
            program_ids=list(report.programs_added),
            application_ids=list(report.applications_updated),
        )
        self.receipt_store.save(receipt)

    def _process_claimed(
        self,
        state: PatientState,
        event: AutopilotEvent,
        *,
        claim_id: str,
        claim_attempt: int,
        allow_scientific_network: bool,
        allow_paid_resource_search: bool,
    ) -> AutopilotRunReport:
        vault = self.store.load(event.patient_id)
        sync_watch_topics(vault, state)
        report = AutopilotRunReport(event_id=event.id)
        report.actions.append(
            AutopilotAction(
                action="claim_event",
                status="completed",
                reason=f"Durable event claim acquired (attempt {claim_attempt}).",
            )
        )

        topics = self._select_topics(vault, event)
        report.actions.append(
            AutopilotAction(
                action="sync_watch_topics",
                status="completed",
                reason=f"{len(vault.watch_topics)} monitored topics are available; {len(topics)} selected for this event.",
            )
        )

        if event.event_type in {"scheduled.discovery_refresh", "manual.discovery_refresh"}:
            if not allow_scientific_network or self.scientific_radar is None:
                report.actions.append(
                    AutopilotAction(
                        action="scientific_scan",
                        status="skipped",
                        reason="Scientific network scan is disabled for this run; zero model spend.",
                    )
                )
            else:
                for topic in topics:
                    for candidate in self.scientific_radar.scan(topic, per_source=3):
                        relevance = _topic_relevance(topic.condition, candidate.title, candidate.abstract)
                        if relevance < 0.25:
                            continue
                        discovery = candidate_to_discovery(
                            topic,
                            candidate,
                            relevance_score=relevance,
                            interrupt_score=0,
                        )
                        discovery.interrupt_score = _interrupt_score(discovery)
                        if add_discovery(vault, discovery):
                            report.discoveries_added.append(discovery.id)
                report.actions.append(
                    AutopilotAction(
                        action="scientific_scan",
                        status="completed",
                        reason=(
                            f"Added {len(report.discoveries_added)} deduplicated evidence items. "
                            "PubMed/Europe PMC/ClinicalTrials retrieval itself uses no Gemini call."
                        ),
                    )
                )

        if event.event_type in {"manual.resource_refresh", "scheduled.discovery_refresh"}:
            if not allow_paid_resource_search or self.resource_radar is None:
                report.actions.append(
                    AutopilotAction(
                        action="resource_scan",
                        status="skipped",
                        reason="Paid grounded resource search was not authorized for this run.",
                    )
                )
            else:
                report.cost_class = "bounded_paid_search"
                country = str(event.payload.get("country") or "")
                region = str(event.payload.get("region") or "")
                locality = str(event.payload.get("locality") or "")
                for topic in topics:
                    for program in self.resource_radar.search_programs(
                        topic,
                        country=country,
                        region=region,
                        locality=locality,
                    ):
                        if register_program(vault, program):
                            report.programs_added.append(program.id)
                report.actions.append(
                    AutopilotAction(
                        action="resource_scan",
                        status="completed",
                        reason=f"Added {len(report.programs_added)} official-domain program candidates.",
                    )
                )

        if event.event_type == "prepare_application":
            program = next((item for item in vault.programs if item.id == event.program_id), None)
            if program is None:
                report.actions.append(
                    AutopilotAction(
                        action="prepare_application",
                        status="blocked",
                        reason="Program is not present in the patient's opportunity vault.",
                    )
                )
            else:
                decision = evaluate_program_eligibility(state, program)
                packet = prepare_application(state, program, decision)
                upsert_application(vault, packet)
                report.applications_updated.append(packet.id)
                report.actions.append(
                    AutopilotAction(
                        action="prepare_application",
                        status="completed" if str(packet.status) != "blocked" else "blocked",
                        reason=(
                            f"Eligibility matched={len(decision.matched)}, unmet={len(decision.unmet)}, "
                            f"unknown={len(decision.unknown)}; missing documents={len(packet.missing_documents)}."
                        ),
                        resource_id=packet.id,
                    )
                )

        # Compatibility index only. The authoritative idempotency state is the
        # leased claim store and this marker is written only after work succeeds.
        if claim_id not in vault.processed_event_keys:
            vault.processed_event_keys.append(claim_id)
        self.store.save(vault)
        report.snapshot = opportunity_snapshot(vault)
        self._save_receipt(event, claim_id, report)
        self.claim_store.complete(event.patient_id, claim_id)
        return report

    def process(
        self,
        state: PatientState,
        event: AutopilotEvent,
        *,
        allow_scientific_network: bool = False,
        allow_paid_resource_search: bool = False,
    ) -> AutopilotRunReport:
        if event.patient_id != state.profile.id:
            raise PermissionError("Autopilot event patient does not match authorized patient state.")

        claim_id = event_key(event)
        claim_result = self.claim_store.claim(
            claim_id=claim_id,
            patient_id=event.patient_id,
            event_id=event.id,
            event_type=event.event_type,
        )
        if claim_result.duplicate_completed:
            vault = self.store.load(event.patient_id)
            return AutopilotRunReport(
                event_id=event.id,
                duplicate=True,
                actions=[
                    AutopilotAction(
                        action="claim_event",
                        status="skipped",
                        reason="Durable claim already completed; redelivery has no side effects.",
                    )
                ],
                snapshot=opportunity_snapshot(vault),
            )
        if claim_result.busy:
            vault = self.store.load(event.patient_id)
            return AutopilotRunReport(
                event_id=event.id,
                actions=[
                    AutopilotAction(
                        action="claim_event",
                        status="blocked",
                        reason="Another worker currently owns an unexpired lease for this event.",
                    )
                ],
                snapshot=opportunity_snapshot(vault),
            )

        try:
            return self._process_claimed(
                state,
                event,
                claim_id=claim_id,
                claim_attempt=claim_result.claim.attempts,
                allow_scientific_network=allow_scientific_network,
                allow_paid_resource_search=allow_paid_resource_search,
            )
        except Exception as exc:
            self.claim_store.fail(event.patient_id, claim_id, f"{type(exc).__name__}: {exc}")
            raise

    def next_notice(self, patient_id: str, *, minimum_interrupt_score: float = 0.72) -> Discovery | None:
        vault = self.store.load(patient_id)
        candidates = [
            item
            for item in vault.discoveries
            if item.status == DiscoveryStatus.NEW and item.interrupt_score >= minimum_interrupt_score
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item.interrupt_score, item.created_at), reverse=True)
        return candidates[0]

    def mark_discovery_seen(self, patient_id: str, discovery_id: str, *, save: bool = False) -> None:
        vault = self.store.load(patient_id)
        discovery = next((item for item in vault.discoveries if item.id == discovery_id), None)
        if discovery is None:
            raise KeyError(discovery_id)
        discovery.status = DiscoveryStatus.SAVED if save else DiscoveryStatus.ACTIONED
        self.store.save(vault)

    def prepare_application(
        self,
        state: PatientState,
        program_id: str,
    ) -> ApplicationPacket:
        event = AutopilotEvent(
            patient_id=state.profile.id,
            event_type="prepare_application",
            program_id=program_id,
        )
        report = self.process(state, event)
        if not report.applications_updated:
            raise ValueError("Application could not be prepared.")
        vault = self.store.load(state.profile.id)
        packet_id = report.applications_updated[-1]
        return next(item for item in vault.applications if item.id == packet_id)

    def recent_receipts(self, patient_id: str, *, limit: int = 20) -> list[AutopilotReceipt]:
        if self.receipt_store is None:
            return []
        return self.receipt_store.list_recent(patient_id, limit=limit)
