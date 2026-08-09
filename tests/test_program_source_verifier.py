import hashlib

from healthia_one.models import FamilyCondition, FamilyMember
from healthia_one.opportunity_autopilot import AssistanceProgram, DiscoveryKind, evaluate_program_eligibility
from healthia_one.program_source_verifier import (
    MemoryProgramVerificationStore,
    OfficialProgramVerifier,
    ProgramSourceArtifact,
)
from healthia_one.service import seed_state


class FakeLoader:
    allowed_domains = {"example.gov"}

    def __init__(self, text: str):
        self.text = text

    def load(self, url: str):
        body = self.text.encode("utf-8")
        return ProgramSourceArtifact(
            url=url,
            final_url=url,
            content_type="text/html",
            sha256=hashlib.sha256(body).hexdigest(),
            size_bytes=len(body),
            text=self.text,
            body=body,
        )


class FakeExtractor:
    def __init__(self, payload):
        self.payload = payload

    def extract(self, artifact, program):
        return self.payload


def family_state():
    state = seed_state()
    state.profile.id = "patient_program_verify"
    state.family_members.append(
        FamilyMember(
            display_name="Hijo",
            relation="hijo",
            generation=1,
            conditions=[FamilyCondition(name="Autismo", confirmed=True)],
        )
    )
    return state


def candidate_program():
    return AssistanceProgram(
        id="program_verified_source",
        title="Family Autism Support",
        provider="Official Support Agency",
        kind=DiscoveryKind.GOVERNMENT_BENEFIT,
        url="https://example.gov/program",
        benefit_summary="Synthetic assistance program for tests.",
    )


def test_literal_html_evidence_can_promote_verified_requirement():
    source = "Applicants must be the caregiver of a child with autism. Apply through the official portal."
    store = MemoryProgramVerificationStore()
    verifier = OfficialProgramVerifier(
        loader=FakeLoader(source),
        extractor=FakeExtractor(
            {
                "requirements": [
                    {
                        "label": "Caregiver of a child with autism",
                        "rule_type": "caregiver_of_condition",
                        "value": "Autismo",
                        "required": True,
                        "evidence_excerpt": "caregiver of a child with autism",
                    }
                ],
                "required_documents": [],
                "deadline": None,
                "submission_method": "portal",
                "submission_destination": "https://example.gov/apply",
                "caveats": [],
            }
        ),
        store=store,
    )

    verification = verifier.verify("patient_program_verify", candidate_program())
    verified_program = verification.apply(candidate_program())
    decision = evaluate_program_eligibility(family_state(), verified_program)

    assert verification.source_sha256
    assert store.get("patient_program_verify", candidate_program().id).source_sha256 == verification.source_sha256
    assert verified_program.requirements[0].rule["type"] == "caregiver_of_condition"
    assert decision.likely_eligible is True
    assert decision.unknown == []


def test_nonexistent_html_quote_is_downgraded_to_unknown():
    verifier = OfficialProgramVerifier(
        loader=FakeLoader("The official page contains no income statement."),
        extractor=FakeExtractor(
            {
                "requirements": [
                    {
                        "label": "Income below a threshold",
                        "rule_type": "age_max",
                        "value": 50,
                        "required": True,
                        "evidence_excerpt": "Applicants must be younger than 50",
                    }
                ],
                "required_documents": [],
                "deadline": None,
                "submission_method": "unknown",
                "submission_destination": "",
                "caveats": [],
            }
        ),
        store=MemoryProgramVerificationStore(),
    )

    verification = verifier.verify("patient_program_verify", candidate_program())
    applied = verification.apply(candidate_program())

    assert verification.requirements[0].source_verification_required is True
    assert applied.requirements[0].rule["type"] == "unknown"


def test_source_without_clear_requirements_stays_blocked_for_eligibility():
    verifier = OfficialProgramVerifier(
        loader=FakeLoader("General information only."),
        extractor=FakeExtractor(
            {
                "requirements": [],
                "required_documents": [],
                "deadline": None,
                "submission_method": "unknown",
                "submission_destination": "",
                "caveats": [],
            }
        ),
        store=MemoryProgramVerificationStore(),
    )

    verification = verifier.verify("patient_program_verify", candidate_program())
    decision = evaluate_program_eligibility(family_state(), verification.apply(candidate_program()))

    assert len(verification.requirements) == 1
    assert verification.requirements[0].source_verification_required is True
    assert decision.likely_eligible is None
    assert "Verify official program requirements manually" in decision.unknown


def test_off_domain_portal_destination_is_discarded():
    verifier = OfficialProgramVerifier(
        loader=FakeLoader("Applicants must be the caregiver of a child with autism."),
        extractor=FakeExtractor(
            {
                "requirements": [
                    {
                        "label": "Caregiver",
                        "rule_type": "caregiver_of_condition",
                        "value": "Autismo",
                        "required": True,
                        "evidence_excerpt": "caregiver of a child with autism",
                    }
                ],
                "required_documents": [],
                "deadline": None,
                "submission_method": "portal",
                "submission_destination": "https://evil.example/apply",
                "caveats": [],
            }
        ),
        store=MemoryProgramVerificationStore(),
    )

    verification = verifier.verify("patient_program_verify", candidate_program())

    assert verification.submission_destination == ""
    assert any("outside" in item for item in verification.caveats)
