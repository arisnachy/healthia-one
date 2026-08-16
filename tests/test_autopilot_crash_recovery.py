import pytest

from healthia_one.autopilot_claims import MemoryEventClaimStore
from healthia_one.autopilot_receipts import MemoryAutopilotReceiptStore
from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot, event_key
from healthia_one.opportunity_autopilot import EvidenceTier
from healthia_one.opportunity_store import MemoryOpportunityStore
from healthia_one.research_radar import ResearchCandidate
from healthia_one.service import seed_state


class FailOnceScientificRadar:
    def __init__(self):
        self.calls = 0

    def scan(self, topic, *, per_source=3):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("synthetic worker crash")
        return [
            ResearchCandidate(
                source_name="PubMed",
                source_id="PMID:recovery",
                title=f"New evidence for {topic.condition}",
                url="https://pubmed.ncbi.nlm.nih.gov/123/",
                publisher="Synthetic Journal",
                abstract=f"Evidence about {topic.condition}.",
                evidence_tier=EvidenceTier.SYSTEMATIC_REVIEW,
                official=True,
            )
        ]


def test_failed_event_is_retryable_and_only_completion_becomes_duplicate():
    state = seed_state()
    state.profile.confirmed_conditions = ["Hipertensión arterial"]
    claims = MemoryEventClaimStore()
    receipts = MemoryAutopilotReceiptStore()
    radar = FailOnceScientificRadar()
    autopilot = OpportunityAutopilot(
        MemoryOpportunityStore(),
        scientific_radar=radar,
        claim_store=claims,
        receipt_store=receipts,
    )
    event = AutopilotEvent(
        id="event_crash_retry",
        patient_id=state.profile.id,
        event_type="manual.discovery_refresh",
        subject_id=state.profile.id,
        condition="Hipertensión arterial",
    )
    claim_id = event_key(event)

    with pytest.raises(RuntimeError, match="synthetic worker crash"):
        autopilot.process(state, event, allow_scientific_network=True)

    failed = claims.get(state.profile.id, claim_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert receipts.list_recent(state.profile.id) == []

    recovered = autopilot.process(state, event, allow_scientific_network=True)
    assert recovered.duplicate is False
    assert len(recovered.discoveries_added) == 1

    completed = claims.get(state.profile.id, claim_id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.attempts == 2

    saved_receipts = receipts.list_recent(state.profile.id)
    assert len(saved_receipts) == 1
    assert saved_receipts[0].event_id == event.id
    assert saved_receipts[0].status == "completed"
    assert saved_receipts[0].discovery_ids == recovered.discoveries_added
    assert all("thought" not in str(action).lower() for action in saved_receipts[0].actions)

    redelivery = autopilot.process(state, event, allow_scientific_network=True)
    assert redelivery.duplicate is True
    assert radar.calls == 2
    assert len(receipts.list_recent(state.profile.id)) == 1


def test_unexpired_claim_blocks_parallel_worker_without_side_effects():
    state = seed_state()
    claims = MemoryEventClaimStore()
    receipts = MemoryAutopilotReceiptStore()
    autopilot = OpportunityAutopilot(
        MemoryOpportunityStore(),
        claim_store=claims,
        receipt_store=receipts,
    )
    event = AutopilotEvent(
        id="event_parallel",
        patient_id=state.profile.id,
        event_type="patient_state_changed",
    )
    claim_id = event_key(event)
    claimed = claims.claim(
        claim_id=claim_id,
        patient_id=state.profile.id,
        event_id=event.id,
        event_type=event.event_type,
        lease_seconds=120,
    )
    assert claimed.acquired is True

    blocked = autopilot.process(state, event)

    assert blocked.duplicate is False
    assert blocked.actions[0].status == "blocked"
    assert receipts.list_recent(state.profile.id) == []
