import json

import pytest

from tendril import experiments
from tendril.cli import main, parser


def test_replicates_only_jev_and_records_each_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(experiments, "require_credentials", lambda: None)
    calls = []

    def search(config, out):
        calls.append(config)
        out.mkdir(parents=True)
        record = {
            "id": "one",
            "valid": True,
            "descriptors": {"structure": [1, 2], "behavior": [3, 4]},
            "capabilities": {k: 0.0 for k in experiments.CAPABILITIES},
        }
        (out / "evaluations.jsonl").write_text(json.dumps(record) + "\n")
        (out / "archives.json").write_text(
            json.dumps({view: {"bin": [record]} for view in ("structure", "behavior")})
        )
        return {"wall_seconds_this_invocation": 0.1, "guided": 1, "mutations": 1}

    monkeypatch.setattr(experiments, "run_search", search)
    report = experiments.replicate_jev(
        {"strategy": "jev", "max_api_requests": 128,
         "max_api_cost_usd": 1, "max_wall_seconds": 3600}, tmp_path, seeds=[2, 8]
    )
    assert [c["seed"] for c in calls] == [2, 8]
    assert all(c["strategy"] == "jev" for c in calls)
    assert report["aggregates"]["replicates"] == 2
    budget = report["design"]["budget"]
    assert budget["api_cost_limit_enforced"] is True
    assert budget["max_api_cost_usd_per_run"] == 1
    assert budget["max_api_requests_per_run"] == 128
    assert budget["wall_time_limit_enforced"] is False
    assert budget["wall_time_admission_limit_enforced"] is True
    assert budget["max_wall_seconds_per_invocation"] == 3600
    assert (tmp_path / "replication.json").exists()
    assert not (tmp_path / "comparison.json").exists()


def test_replicate_requires_key_before_output_creation(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    out = tmp_path / "missing-key"
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        experiments.replicate_jev({"strategy": "jev"}, out)
    assert not out.exists()


def test_cli_has_no_selector_comparison_command(capsys):
    with pytest.raises(SystemExit):
        parser().parse_args(["compare"])
    assert "invalid choice" in capsys.readouterr().err
    arguments = parser().parse_args(
        ["replicate", "--config", "example.json", "--out", "example"]
    )
    assert arguments.seeds == [0, 1, 2]


def test_cli_guidance_error_stops_cleanly(tmp_path, monkeypatch, capsys):
    from tendril import search

    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-only")

    def fail(*args):
        raise ValueError("Jev unavailable; resume the saved checkpoint")

    config = tmp_path / "config.json"
    config.write_text('{"strategy": "jev"}')
    monkeypatch.setattr(search, "run_search", fail)
    with pytest.raises(SystemExit) as error:
        main(["evolve", "--config", str(config), "--out", str(tmp_path / "run")])
    output = capsys.readouterr().err
    assert error.value.code == 2 and "Jev unavailable" in output
    assert "Traceback" not in output


def test_attempt_cost_ledger_counts_retries_once_and_failed_usage(tmp_path):
    attempts = tmp_path / "attempts"
    attempts.mkdir()
    failure = {
        "request_hash": "abc",
        "attempt": 1,
        "response": {"usage": {"input_tokens": 100, "output_tokens": 20}},
        "error": "response chose an invalid edit",
        "elapsed_seconds": 0.2,
    }
    success = {
        "request_hash": "abc",
        "attempt": 2,
        "response": {"usage": {"input_tokens": 110, "output_tokens": 25}},
        "error": None,
        "elapsed_seconds": 0.3,
    }
    for record in (failure, success):
        (attempts / f"abc-{record['attempt']:06d}.json").write_text(json.dumps(record))
    (tmp_path / "abc.json").write_text(json.dumps(success))
    audit = {
        "guidance": {
            "strategy": "jev",
            "request_hash": "abc",
            "attempt": 2,
            "cache_hit": True,
        }
    }
    pricing = {"input_per_million": 2.0, "output_per_million": 4.0}
    result = experiments._guidance_cost([audit, audit], pricing, tmp_path)
    assert result["requests"] == result["ledger_requests"] == 2
    assert result["orphaned_requests"] == result["requests_with_errors"] == 1
    assert result["known_usage"] == {"input_tokens": 210, "output_tokens": 45}
    assert result["estimated_api_cost"] == pytest.approx(0.0006)
    assert result["request_wall_seconds"] == pytest.approx(0.5)
