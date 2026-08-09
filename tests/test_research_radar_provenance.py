from healthia_one.opportunity_autopilot import (
    AssistanceProgram,
    DiscoveryKind,
    ProgramRequirement,
    WatchTopic,
    evaluate_program_eligibility,
)
from healthia_one.research_radar import EuropePmcSource, PubMedSource
from healthia_one.service import seed_state


class FakePubMedTransport:
    def json(self, url):
        assert "esearch.fcgi" in url
        return {"esearchresult": {"idlist": ["123"]}}

    def text(self, url):
        assert "efetch.fcgi" in url
        return """
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>123</PMID>
              <Article>
                <ArticleTitle>Randomized trial of a synthetic intervention</ArticleTitle>
                <Abstract><AbstractText>Structured abstract text.</AbstractText></Abstract>
                <Journal>
                  <Title>Synthetic Journal</Title>
                  <JournalIssue><PubDate><Year>2026</Year><Month>Aug</Month><Day>01</Day></PubDate></JournalIssue>
                </Journal>
                <PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """


class FakeEuropePmcTransport:
    def json(self, url):
        return {
            "resultList": {
                "result": [
                    {
                        "source": "MED",
                        "id": "456",
                        "title": "Systematic review of a synthetic intervention",
                        "abstractText": "Synthetic abstract.",
                        "journalTitle": "Synthetic Journal",
                        "firstPublicationDate": "2026-08-01",
                        "pubType": "systematic review",
                        "isPreprint": False,
                    }
                ]
            }
        }


def topic():
    return WatchTopic(
        subject_id="patient_demo",
        subject_label="Patient",
        relation="self",
        condition="hypertension",
        source="manual",
    )


def test_pubmed_indexing_does_not_claim_peer_review_without_explicit_proof():
    candidate = PubMedSource(transport=FakePubMedTransport()).search(topic())[0]

    assert candidate.evidence_tier == "randomized_trial"
    assert candidate.peer_reviewed is False
    assert candidate.raw["peer_review_status"] == "unknown"


def test_europe_pmc_non_preprint_does_not_claim_peer_review_without_explicit_proof():
    candidate = EuropePmcSource(transport=FakeEuropePmcTransport()).search(topic())[0]

    assert candidate.evidence_tier == "systematic_review"
    assert candidate.peer_reviewed is False
    assert candidate.raw["peer_review_status"] == "unknown"


def test_unverified_grounded_requirements_can_never_produce_eligibility():
    state = seed_state()
    program = AssistanceProgram(
        title="Synthetic candidate program",
        provider="Synthetic Government",
        kind=DiscoveryKind.GOVERNMENT_BENEFIT,
        url="https://example.gov/program",
        requirements=[
            ProgramRequirement(
                key="source_verification",
                label="Verify official program requirements against the source/form",
                rule={"type": "unknown", "source_verification_required": True},
            )
        ],
    )

    decision = evaluate_program_eligibility(state, program)

    assert decision.likely_eligible is None
    assert decision.matched == []
    assert decision.unmet == []
    assert decision.unknown == ["Verify official program requirements against the source/form"]
