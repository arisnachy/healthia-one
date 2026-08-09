from __future__ import annotations

from datetime import date

import pytest

from healthia_one.autopilot_runtime import AutopilotEvent, OpportunityAutopilot
from healthia_one.models import (
    ClinicalDocument,
    DocumentCategory,
    FamilyCondition,
    FamilyMember,
    MedicationPlan,
    PatientState,
)
from healthia_one.opportunity_autopilot import (
    AssistanceProgram,
    Discovery,
    DiscoveryKind,
    EvidenceTier,
    ProgramRequirement,
    RequiredDocument,
    SourceCitation,
    authorize_external_submission,
    derive_watch_topics,
    discovery_fingerprint,
    evaluate_program_eligibility,
    mark_patient_reviewed,
    record_submission_receipt,
    register_program,
    therapeutic_comparison,
)
from healthia_one.opportunity_chat import OpportunityChatController
from healthia_one.opportunity_store import MemoryOpportunityStore
from healthia_one.research_radar import ResearchCandidate


def patient_state() -> PatientState:
    state = PatientState()
    state.profile.id = "patient_aris"
    state.profile.display_name = "Aris"
    state.profile.legal_name = "Aris Example"
    state.profile.email = "aris@example.com"
    state.profile.phone = "+1 809 555 0100"
    state.profile.address = "Santiago, Dominican Republic"
    state.profile.locale = "es-DO"
    state.profile.birth_date = date(1982, 2, 20)
    state.profile.confirmed_conditions = ["Hipertensión arterial"]
    state.profile.personal_history.chronic_conditions = ["Hipertensión arterial"]
    state.family_members = [
        FamilyMember(
            display_name="Hijo",
            relation="hijo",
            generation=1,
            conditions=[FamilyCondition(name="Autismo", confirmed=True)],
        )
    ]
    state.medication_plans = [
        MedicationPlan(
            name="Losartán",
            strength="50 mg",
            schedule="cada 24 horas",
            purpose="Control de presión arterial",
            verification_status="professional_confirmed",
        )
    ]
    return state


def test_watch_topics_preserve_patient_vs_family_scope():
    topics = derive_watch_topics(patient_state())
    assert len(topics) == 2

    hypertension = next(item for item in topics if "Hipertensión" in item.condition)
    autism = next(item for item in topics if item.condition == "Autismo")

    assert hypertension.relation == "self"
    assert hypertension.subject_id == "patient_aris"
    assert autism.relation == "hijo"
    assert autism.subject_label == "Hijo"
    assert autism.source == "genogram"


class FakeScientificRadar:
    def scan(self, topic, *, per_source=3):
        if topic.condition != "Autismo":
            return []
        return [
            ResearchCandidate(
                source_name="PubMed",
                source_id="PMID:123",
                title="Autism family support randomized trial",
                url="https://pubmed.ncbi.nlm.nih.gov/123/",
                publisher="Synthetic Journal",
                abstract="Autism family support intervention randomized trial with caregiver outcomes.",
                evidence_tier=EvidenceTier.RANDOMIZED_TRIAL,
                peer_reviewed=True,
                official=True,
                source_claims=["Caregiver support outcomes were measured."],
            )
        ]


def test_autopilot_is_idempotent_and_scientific_scan_is_not_chat_spam():
    state = patient_state()
    store = MemoryOpportunityStore()
    autopilot = OpportunityAutopilot(store, scientific_radar=FakeScientificRadar())
    event = AutopilotEvent(
        id="evt_same",
        patient_id=state.profile.id,
        event_type="manual.discovery_refresh",
        condition="Autismo",
    )

    first = autopilot.process(state, event, allow_scientific_network=True)
    second = autopilot.process(state, event, allow_scientific_network=True)

    assert len(first.discoveries_added) == 1
    assert second.duplicate is True
    assert not second.discoveries_added

    vault = autopilot.load(state.profile.id)
    assert len(vault.discoveries) == 1
    discovery = vault.discoveries[0]
    assert discovery.relation == "hijo"
    assert discovery.interrupt_score < 1
    assert discovery.changes_care_now is False


def assistance_program() -> AssistanceProgram:
    return AssistanceProgram(
        id="program_autism_support",
        title="Family Autism Support Benefit",
        provider="Official Support Agency",
        kind=DiscoveryKind.GOVERNMENT_BENEFIT,
        url="https://example.gov/program/autism",
        country="DO",
        benefit_summary="Synthetic family-support benefit for tests.",
        condition_terms=["Autismo"],
        requirements=[
            ProgramRequirement(
                key="country",
                label="Resident in Dominican Republic",
                rule={"type": "country", "value": "Dominican Republic"},
            ),
            ProgramRequirement(
                key="caregiver",
                label="Caregiver of a child with autism",
                rule={"type": "caregiver_of_condition", "value": "Autismo"},
            ),
        ],
        required_documents=[
            RequiredDocument(
                key="identity",
                label="Identity document",
                accepted_categories=[DocumentCategory.IDENTITY],
                keywords=["identity", "cedula", "cédula"],
            ),
            RequiredDocument(
                key="diagnosis",
                label="Supporting diagnosis document",
                accepted_categories=[DocumentCategory.CONSULTATION, DocumentCategory.OTHER],
                keywords=["autismo", "diagnostico", "diagnóstico"],
            ),
        ],
        submission_method="portal",
        submission_destination="https://example.gov/apply",
    )


def test_program_eligibility_never_invents_missing_documents():
    state = patient_state()
    state.documents = [
        ClinicalDocument(
            title="Cédula",
            filename="cedula.pdf",
            category=DocumentCategory.IDENTITY,
            tags=["identity"],
        )
    ]
    decision = evaluate_program_eligibility(state, assistance_program())

    assert decision.likely_eligible is True
    assert len(decision.matched) == 2
    assert decision.unmet == []
    assert decision.missing_documents == ["Supporting diagnosis document"]


def test_locale_alone_never_proves_residence():
    state = patient_state()
    state.profile.address = ""
    decision = evaluate_program_eligibility(state, assistance_program())

    assert decision.likely_eligible is None
    assert "Resident in Dominican Republic" in decision.unknown
    assert "Caregiver of a child with autism" in decision.matched


def test_application_requires_missing_document_patient_review_and_explicit_send_authorization():
    state = patient_state()
    state.documents = [
        ClinicalDocument(
            title="Cédula",
            filename="cedula.pdf",
            category=DocumentCategory.IDENTITY,
            tags=["identity"],
        )
    ]
    store = MemoryOpportunityStore()
    autopilot = OpportunityAutopilot(store)
    vault = store.load(state.profile.id)
    register_program(vault, assistance_program())
    store.save(vault)

    packet = autopilot.prepare_application(state, "program_autism_support")
    assert packet.missing_documents == ["Supporting diagnosis document"]

    with pytest.raises(ValueError):
        authorize_external_submission(packet, authorized=True)

    state.documents.append(
        ClinicalDocument(
            title="Informe diagnóstico autismo",
            filename="autismo.pdf",
            category=DocumentCategory.CONSULTATION,
            tags=["autismo", "diagnóstico"],
        )
    )
    packet = autopilot.prepare_application(state, "program_autism_support")
    packet = mark_patient_reviewed(packet, confirmed=True)
    packet = authorize_external_submission(packet, authorized=True)
    assert str(packet.status) == "ready_to_submit"

    packet = record_submission_receipt(packet, "receipt-123")
    assert str(packet.status) == "submitted"
    assert packet.receipt == "receipt-123"


def test_therapeutic_comparison_is_source_grounded_and_does_not_change_medication():
    state = patient_state()
    source = SourceCitation(
        source_id="PMID:456",
        title="New hypertension therapy trial",
        url="https://pubmed.ncbi.nlm.nih.gov/456/",
        publisher="Synthetic Journal",
        evidence_tier=EvidenceTier.RANDOMIZED_TRIAL,
        peer_reviewed=True,
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
        summary="A synthetic new treatment trial.",
        why_relevant="Matches hypertension.",
        source=source,
        potential_benefits=["Lower endpoint rate in the source study."],
        source_claims=["Compared a new therapy with standard treatment."],
    )

    comparison = therapeutic_comparison(state, discovery)

    assert comparison["patient_specific_claim"] is False
    assert comparison["requires_professional_review"] is True
    assert comparison["current_medications"][0]["name"] == "Losartán"
    assert "never authorizes" in comparison["safety"]


def test_chat_can_manage_program_prefill_and_missing_documents():
    state = patient_state()
    store = MemoryOpportunityStore()
    autopilot = OpportunityAutopilot(store)
    vault = store.load(state.profile.id)
    register_program(vault, assistance_program())
    store.save(vault)

    controller = OpportunityChatController(autopilot)
    result = controller.handle(state, "Completa el formulario de Family Autism Support Benefit")

    assert result is not None
    assert result.action == "application_prefilled"
    assert "Supporting diagnosis document" in result.content
