import json

import pytest

import tendril.guidance as guidance
from tendril.guidance import GuidanceError
from tendril.search import CAPABILITIES, Archive, run_search


def reply(body, timeout):
    options = body["questions"]["edit"]["criteria"]
    chosen = next(iter(options))
    return {
        "model": body["model"],
        "answers": {
            "edit": {
                "type": "choice",
                "choice": chosen,
                "confidence": 1.0,
                "probabilities": {key: float(key == chosen) for key in options},
            }
        },
    }


@pytest.fixture(autouse=True)
def offline_jev(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-only")
    monkeypatch.setattr(guidance, "_post", reply)


def stable_records(path):
    records = [json.loads(line) for line in path.read_text().splitlines()]
    for record in records:
        record["guidance"].pop("elapsed_seconds")
        record["guidance"].pop("cache_hit")
    return records


def fake_evaluate(genome, config, seed, out=None):
    m = genome["modules"][0]
    return {
        "valid": True,
        "reasons": [],
        "descriptors": {
            "structure": [len(genome["modules"]), len(m["children"]), m["length"]],
            "behavior": [m["amplitude"], m["phase"]],
        },
        "capabilities": {
            k: m["amplitude"] if k == "motion" else m["stiffness"] for k in CAPABILITIES
        },
        "accounting": {"mass": m["radius"]},
        "seed": seed,
    }


def record(i, descriptor=0.1, **capabilities):
    return {
        "id": str(i),
        "evaluation": i,
        "valid": True,
        "descriptors": {"structure": [descriptor], "behavior": [descriptor]},
        "capabilities": {key: capabilities.get(key, 0.0) for key in CAPABILITIES},
    }


def test_passive_developmental_precursor_and_local_capabilities_survive():
    structure, behavior = Archive("structure"), Archive("behavior")
    precursor = record(0)
    mobile = record(1, 0.15, motion=1)
    support = record(2, 0.2, support=1)
    for r in (precursor, mobile, support):
        structure.add(r)
        behavior.add(r)
    assert precursor in structure.members
    assert mobile in structure.members and support in structure.members
    assert precursor not in behavior.members
    # Competition never crosses descriptor niches.
    distinct = record(3, 10)
    assert behavior.add(distinct) and distinct in behavior.members


def test_invalid_results_cannot_enter_archives():
    archive = Archive("structure")
    r = record(0)
    r["valid"] = False
    assert not archive.add(r) and not archive.members


def test_new_passive_structure_survives_capable_neighbor():
    structure = Archive("structure")
    for r in (record(0, 0.01, motion=10), record(1, 0.05, motion=5)):
        structure.add(r)
    passive = record(2, 0.22)
    assert structure.add(passive)
    assert passive in structure.members


def test_invalid_rollouts_logged_without_polluting_archives(tmp_path):
    def invalid(*args, **kwargs):
        return {"valid": False, "reasons": ["nonfinite state quarantined"]}

    summary = run_search({"evaluations": 3}, tmp_path, invalid)
    assert summary["valid"] == 0
    assert summary["members"] == {"structure": 0, "behavior": 0}
    assert len((tmp_path / "evaluations.jsonl").read_text().splitlines()) == 3


def test_search_resume_exactly_replays_uninterrupted_run(tmp_path):
    config = {
        "evaluations": 12,
        "initial_population": 2,
        "candidate_count": 8,
        "seed": 17,
        "strategy": "jev",
    }
    complete = tmp_path / "complete"
    resumed = tmp_path / "resumed"
    run_search(config, complete, fake_evaluate)
    run_search({**config, "evaluations": 6}, resumed, fake_evaluate)
    result = run_search({**config, "resume": True}, resumed, fake_evaluate)
    assert result["guided"] == result["mutations"] == 12
    assert stable_records(complete / "evaluations.jsonl") == stable_records(
        resumed / "evaluations.jsonl"
    )
    complete_archives = json.loads((complete / "archives.json").read_text())
    resumed_archives = json.loads((resumed / "archives.json").read_text())
    assert {
        view: {key: [r["id"] for r in rows] for key, rows in bins.items()}
        for view, bins in complete_archives.items()
    } == {
        view: {key: [r["id"] for r in rows] for key, rows in bins.items()}
        for view, bins in resumed_archives.items()
    }
    assert len(list((resumed / "specimens").glob("*/proposal.json"))) == 12


def test_every_selection_including_initial_population_uses_jev(tmp_path):
    summary = run_search(
        {"evaluations": 4, "initial_population": 2, "candidate_count": 8},
        tmp_path,
        fake_evaluate,
    )
    proposals = [
        json.loads(p.read_text())
        for p in sorted(tmp_path.glob("specimens/*/proposal.json"))
    ]
    assert summary["guided"] == 4
    for proposal in proposals:
        audit = proposal["lineage"]["guidance"]
        assert audit["strategy"] == "jev"
        assert audit["selected"] in {c["id"] for c in proposal["candidates"]}
        assert "fallback" not in audit and "random_candidate" not in audit
        assert audit["request_hash"]


def test_missing_credentials_prevents_any_evaluation(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY")
    with pytest.raises(GuidanceError, match="TYPESAFE_API_KEY"):
        run_search(
            {}, tmp_path, lambda *args, **kwargs: pytest.fail("evaluated without Jev")
        )


@pytest.mark.parametrize("completed", [0, 2])
def test_failed_selection_stops_without_evaluation_and_resumes(
    tmp_path, monkeypatch, completed
):
    calls = []
    evaluations = []

    def flaky(body, timeout):
        calls.append(body)
        if len(calls) == completed + 2:
            raise TimeoutError("sensitive value must not be logged")
        return reply(body, timeout)

    def track(*args, **kwargs):
        evaluations.append(1)
        return fake_evaluate(*args, **kwargs)

    monkeypatch.setattr(guidance, "_post", flaky)
    config = {"evaluations": 4, "initial_population": 1, "batch_size": 2}
    with pytest.raises(GuidanceError, match="TimeoutError"):
        run_search(config, tmp_path, track)
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert len(evaluations) == len(checkpoint["records"]) == completed
    assert checkpoint["guided"] == completed
    # Retry only the failed request; the earlier successful choice is cached.
    result = run_search({**config, "resume": True}, tmp_path, track)
    assert result["guided"] == result["evaluations"] == len(evaluations) == 4
    assert len(calls) == 5
    records = stable_records(tmp_path / "evaluations.jsonl")
    assert [r["evaluation"] for r in records] == list(range(4))
    assert len(list((tmp_path / "guidance" / "attempts").glob("*.json"))) == 5
    assert "sensitive value" not in "".join(
        p.read_text() for p in (tmp_path / "guidance").rglob("*.json")
    )


def test_overwrite_and_incompatible_resume_are_rejected(tmp_path):
    run_search({"evaluations": 1}, tmp_path, fake_evaluate)
    with pytest.raises(ValueError, match="already contains"):
        run_search({"evaluations": 1}, tmp_path, fake_evaluate)
    with pytest.raises(ValueError, match="differs"):
        run_search(
            {"evaluations": 2, "seed": 2, "resume": True}, tmp_path, fake_evaluate
        )


@pytest.mark.parametrize(
    "config",
    [
        {"guided_fraction": 0.8},
        {"strategy": "random"},
        {"strategy": "adaptive"},
        {"candidate_count": 256},
        {"niche_width": 0},
        {"workers": 0},
        {"strategy": "global_best"},
    ],
)
def test_bad_search_configuration_rejected(tmp_path, config):
    with pytest.raises(ValueError):
        run_search(config, tmp_path, fake_evaluate)


def test_resume_refuses_changed_source_or_engine_versions(tmp_path):
    run_search({"evaluations": 1}, tmp_path, fake_evaluate)
    path = tmp_path / "versions.json"
    recorded = json.loads(path.read_text())
    recorded["source_sha256"] = "different-source"
    path.write_text(json.dumps(recorded))
    with pytest.raises(ValueError, match="versions"):
        run_search({"evaluations": 2, "resume": True}, tmp_path, fake_evaluate)
    assert json.loads(path.read_text()) == recorded


def test_request_cap_preserves_pending_batch_and_cache_replays_are_free(tmp_path):
    config = {"evaluations": 2, "batch_size": 2, "max_api_requests": 1}
    with pytest.raises(GuidanceError, match="request limit"):
        run_search(config, tmp_path, fake_evaluate)
    stopped = json.loads((tmp_path / "summary.json").read_text())
    assert stopped["status"] == "stopped"
    assert stopped["evaluations"] == stopped["guided"] == 0
    assert stopped["budget"]["requests"] == 1
    with pytest.raises(GuidanceError, match="request limit"):
        run_search({**config, "resume": True}, tmp_path, fake_evaluate)
    assert len(list((tmp_path / "guidance" / "attempts").glob("*.json"))) == 1
    completed = run_search(
        {**config, "resume": True, "max_api_requests": 2}, tmp_path, fake_evaluate
    )
    assert completed["evaluations"] == completed["guided"] == 2
    assert completed["budget"]["requests"] == 2


def test_unknown_usage_cost_cap_persists_and_can_be_raised_on_resume(tmp_path):
    from tendril.budgets import RESERVED_USD

    config = {"evaluations": 2, "max_api_cost_usd": RESERVED_USD}
    with pytest.raises(GuidanceError, match="dollar limit"):
        run_search(config, tmp_path, fake_evaluate)
    summary = run_search(
        {**config, "resume": True, "max_api_cost_usd": 2 * RESERVED_USD},
        tmp_path, fake_evaluate,
    )
    assert summary["budget"]["conservative_api_cost_usd"] == 2 * RESERVED_USD
    assert summary["budget"]["known_usage_cost_usd"] == 0
    assert summary["evaluations"] == 2


def test_wall_deadline_stops_next_batch_and_resets_on_resume(tmp_path, monkeypatch):
    import tendril.budgets as budgets

    clock = [0.0]
    monkeypatch.setattr(budgets.time, "perf_counter", lambda: clock[0])

    def slow(*args, **kwargs):
        clock[0] += 11
        return fake_evaluate(*args, **kwargs)

    config = {"evaluations": 2, "max_wall_seconds": 10}
    with pytest.raises(GuidanceError, match="wall-time admission"):
        run_search(config, tmp_path, slow)
    stopped = json.loads((tmp_path / "summary.json").read_text())
    assert stopped["evaluations"] == 1
    assert stopped["wall_seconds_this_invocation"] == 11
    completed = run_search({**config, "resume": True}, tmp_path, slow)
    assert completed["evaluations"] == 2
    assert completed["status"] == "complete"


def test_failed_request_consumes_attempt_cap_across_resume(tmp_path, monkeypatch):
    calls = []

    def unavailable(body, timeout):
        calls.append(body)
        raise TimeoutError("offline failure")

    monkeypatch.setattr(guidance, "_post", unavailable)
    config = {"evaluations": 1, "max_api_requests": 1}
    with pytest.raises(GuidanceError, match="TimeoutError"):
        run_search(config, tmp_path, fake_evaluate)
    with pytest.raises(GuidanceError, match="request limit"):
        run_search({**config, "resume": True}, tmp_path, fake_evaluate)
    assert len(calls) == 1
    assert json.loads((tmp_path / "checkpoint.json").read_text())["records"] == []


@pytest.mark.parametrize("valid", [False, True])
def test_initial_and_reseed_trials_feed_observed_history_to_later_batches(
    tmp_path, monkeypatch, valid
):
    import tendril.search as search

    contexts = []
    select = search.select_jev

    def observe(pool, context, *args, **kwargs):
        contexts.append(json.loads(json.dumps(context)))
        return select(pool, context, *args, **kwargs)

    def evaluate(*args, **kwargs):
        result = fake_evaluate(*args, **kwargs)
        result.update(
            valid=valid,
            reasons=[] if valid else ["tissue strain"],
            juvenile={"maximum_tissue_strain": 0.1 if valid else 0.3},
        )
        return result

    monkeypatch.setattr(search, "select_jev", observe)
    run_search(
        {"evaluations": 12, "batch_size": 2, "candidate_count": 8,
         "initial_population": 12 if valid else 1},
        tmp_path, evaluate,
    )
    records = [json.loads(line) for line in
               (tmp_path / "evaluations.jsonl").read_text().splitlines()]
    assert all(record["parent"] is None for record in records)
    fields = {"id", "edit", "valid", "reasons", "juvenile", "descriptors", "capabilities"}
    for index, context in enumerate(contexts):
        completed = index // 2 * 2
        assert context["recent_trials"] == [
            {key: value for key, value in record.items() if key in fields}
            for record in records[max(0, completed - 8):completed]
        ]
        expected = {}
        for record in records[:completed]:
            count = expected.setdefault(record["edit"]["kind"], {"attempts": 0, "admissions": 0})
            count["attempts"] += 1
            count["admissions"] += int(any(record["admissions"].values()))
        assert context["mutation_history"] == expected
    history = json.loads((tmp_path / "checkpoint.json").read_text())["history"]
    assert sum(count["attempts"] for count in history.values()) == 12
    assert sum(count["admissions"] for count in history.values()) == sum(
        any(record["admissions"].values()) for record in records
    )
    if not valid:
        assert contexts[2]["recent_trials"][0]["reasons"] == ["tissue strain"]
        assert sum(count["admissions"] for count in history.values()) == 0
