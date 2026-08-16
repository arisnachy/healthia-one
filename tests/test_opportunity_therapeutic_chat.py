from healthia_one.autopilot_runtime import OpportunityAutopilot
from healthia_one.opportunity_autopilot import (
    Discovery,
    DiscoveryKind,
    EvidenceTier,
    SourceCitation,
    add_discovery,
    discovery_fingerprint,
)
from healthia_one.opportunity_chat import OpportunityChatController
from healthia_one.opportunity_store import MemoryOpportunityStore
from healthia_one.service import seed_state


def test_chat_compares_new_therapy_with_recorded_medication_without_prescribing():
    state = seed_state()
    store = MemoryOpportunityStore()
    autopilot = OpportunityAutopilot(store)
    vault = store.load(state.profile.id)
    source = SourceCitation(
        source_id="PMID:healthia-demo",
        title="Synthetic hypertension therapy randomized trial",
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        publisher="PubMed",
        evidence_tier=EvidenceTier.RANDOMIZED_TRIAL,
        official=True,
    )
    discovery = Discovery(
        fingerprint=discovery_fingerprint(
            source_id=source.source_id,
            title=source.title,
            condition="Hipertensión arterial",
            subject_id=state.profile.id,
        ),
        kind=DiscoveryKind.THERAPEUTIC,
        title=source.title,
        condition="Hipertensión arterial",
        subject_id=state.profile.id,
        subject_label=state.profile.display_name,
        summary="Synthetic trial used only for regression testing.",
        why_relevant="Matches the patient's confirmed hypertension topic.",
        source=source,
        potential_benefits=["The source reports improvement in its primary endpoint."],
        limitations=["The source does not establish individual suitability."],
        source_claims=["Compared a new therapy with standard treatment."],
    )
    assert add_discovery(vault, discovery)
    store.save(vault)

    response = OpportunityChatController(autopilot).handle(
        state,
        "Compáralo con mi medicación",
    )

    assert response is not None
    assert response.action == "therapeutic_comparison"
    assert "Losartán" in response.content
    assert "no inicia, suspende, sustituye ni cambia dosis" in response.content
    assert "https://pubmed.ncbi.nlm.nih.gov/12345678/" in response.content
