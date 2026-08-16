from __future__ import annotations

from fastapi.testclient import TestClient

from healthia_one.judge_mode import app


client = TestClient(app)


def test_judge_mode_is_public_read_only_synthetic_evidence_surface() -> None:
    health = client.get('/healthz')
    assert health.status_code == 200
    payload = health.json()
    assert payload['mode'] == 'judge_read_only_synthetic'
    assert payload['mutations'] is False
    assert payload['model_calls'] is False
    assert payload['secrets'] is False

    proof = client.get('/api/proof')
    assert proof.status_code == 200
    data = proof.json()
    assert data['boundary_count'] == 5
    assert data['model_calls_for_trigger'] == 0
    assert data['judge_mode'] == 'read_only_synthetic_evidence'

    state = client.get('/api/synthetic-state')
    assert state.status_code == 200
    assert state.json()['truth_boundary'].startswith('Read-only synthetic evidence surface')

    assert client.post('/api/proof').status_code == 405
    assert client.post('/api/synthetic-state').status_code == 405


def test_judge_home_makes_autonomy_and_truth_boundary_immediately_legible() -> None:
    page = client.get('/')
    assert page.status_code == 200
    text = page.text
    assert 'HealthIA noticed the follow-up was overdue. Nobody prompted it.' in text
    assert '5' in text and 'durable boundaries' in text
    assert 'JUDGE MODE · READ ONLY · SYNTHETIC' in text
    assert 'does not autonomously diagnose' in text
    assert 'Private GCS' in text
    assert 'Pub/Sub' in text
