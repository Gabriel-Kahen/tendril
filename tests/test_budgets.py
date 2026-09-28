import json

import pytest

from tendril.budgets import MAX_INPUT_TOKENS, PINNED_MODEL, RESERVED_USD, RequestBudget
from tendril.guidance import GuidanceError


def attempt(path, number=1, usage=None, model=PINNED_MODEL, pending=False):
    record = {
        "request_hash": "abc", "attempt": number,
        "request": {"model": PINNED_MODEL},
        "response": {"model": model, "usage": usage},
        "error": "request_in_progress" if pending else None,
    }
    directory = path / "attempts"
    directory.mkdir(exist_ok=True)
    (directory / f"abc-{number:06d}.json").write_text(json.dumps(record))
    (path / "abc.json").write_text(json.dumps(record))
    return record


def test_full_context_reservation_and_pending_attempt_survive_restart(tmp_path):
    budget = RequestBudget(tmp_path, max_api_requests=1, max_api_cost_usd=RESERVED_USD)
    reserve = budget.reservation({"model": PINNED_MODEL})
    assert reserve["reserved_usd"] == RESERVED_USD
    assert reserve["max_input_tokens"] == MAX_INPUT_TOKENS
    attempt(tmp_path, pending=True)
    restarted = RequestBudget(tmp_path, max_api_cost_usd=RESERVED_USD)
    assert restarted.summary()["requests"] == 1  # canonical cache is a mirror
    assert restarted.summary()["conservative_api_cost_usd"] == RESERVED_USD
    with pytest.raises(GuidanceError, match="dollar limit"):
        restarted.reservation({"model": PINNED_MODEL})
    with pytest.raises(GuidanceError, match="request limit"):
        budget.reservation({"model": PINNED_MODEL})


def test_only_valid_pinned_usage_releases_reservation(tmp_path):
    attempt(tmp_path, usage={"input_tokens": 100, "output_tokens": 0})
    budget = RequestBudget(tmp_path, max_api_cost_usd=RESERVED_USD + 0.0000042)
    summary = budget.summary()
    assert summary["known_usage_cost_usd"] == pytest.approx(0.0000042)
    assert summary["requests_with_unknown_cost"] == 0
    assert budget.reservation({"model": PINNED_MODEL})["reserved_usd"] == RESERVED_USD


@pytest.mark.parametrize("usage", [
    None, {}, {"input_tokens": True, "output_tokens": 0},
    {"input_tokens": 1.5, "output_tokens": 0},
    {"input_tokens": -1, "output_tokens": 0},
    {"input_tokens": MAX_INPUT_TOKENS + 1, "output_tokens": 0},
    {"input_tokens": 1, "output_tokens": -1},
])
def test_uncertain_usage_keeps_full_reservation(tmp_path, usage):
    attempt(tmp_path, usage=usage)
    summary = RequestBudget(tmp_path).summary()
    assert summary["known_usage_cost_usd"] == 0
    assert summary["requests_with_unknown_cost"] == 1
    assert summary["conservative_api_cost_usd"] == RESERVED_USD


def test_model_mismatch_keeps_reservation_and_unpriced_requests_are_blocked(tmp_path):
    attempt(tmp_path, usage={"input_tokens": 1, "output_tokens": 0}, model="jev-latest")
    budget = RequestBudget(tmp_path, max_api_cost_usd=1)
    assert budget.summary()["conservative_api_cost_usd"] == RESERVED_USD
    with pytest.raises(GuidanceError, match="pinned"):
        budget.reservation({"model": "jev-latest"})


def test_malformed_ledger_stops_admission(tmp_path):
    (tmp_path / "bad.json").write_text("not json")
    with pytest.raises(GuidanceError, match="malformed"):
        RequestBudget(tmp_path).reservation({"model": PINNED_MODEL})


@pytest.mark.parametrize("limits", [
    {"max_api_requests": True}, {"max_api_requests": 1.5},
    {"max_api_requests": -1}, {"max_api_cost_usd": float("inf")},
    {"max_api_cost_usd": -1}, {"max_wall_seconds": float("nan")},
])
def test_invalid_limits_rejected(tmp_path, limits):
    with pytest.raises(ValueError):
        RequestBudget(tmp_path, **limits)
