from scripts.judge_twin_demo import run


def test_living_twin_judge_rehearsal_is_zero_spend_and_closed() -> None:
    result = run()
    assert result["status"] == "PASS"
    assert result["provider_requests"] == 0
    assert all(result["proof"].values())
    assert "Local zero-spend rehearsal" in result["truth_boundary"]
