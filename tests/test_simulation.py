import json
from copy import deepcopy

import numpy as np

from tendril.genome import seed_genome
from tendril.simulation import evaluate


def fixture_genome(passive=False):
    genome = seed_genome(7)
    module = genome["modules"][0]
    module.update(growth_age=0.05, max_depth=1, attach_radius=0)
    if passive:
        module.update(amplitude=0, strain_gain=0, contact_gain=0, signal_gain=0)
    return genome


def fixture_config():
    return dict(
        timestep=0.001, juvenile_seconds=0.12, assay_seconds=0.35, frame_interval=0.02
    )


def without_timings(result):
    result = deepcopy(result)
    result.pop("timing")
    result["accounting"].pop("edit_seconds")
    return result


def test_replay_preserves_all_nontiming_results(tmp_path):
    genome, config = fixture_genome(), fixture_config()
    first = evaluate(genome, config, seed=19, out=tmp_path / "first")
    second = evaluate(genome, config, seed=19, out=tmp_path / "second")
    assert first["valid"], first["reasons"]
    assert without_timings(first) == without_timings(second)
    for filename in ("genome.json", "config.json", "frames.jsonl"):
        assert (tmp_path / "first" / filename).read_bytes() == (
            tmp_path / "second" / filename
        ).read_bytes()


def test_adult_assays_share_initial_state_and_pause_growth(tmp_path):
    result = evaluate(fixture_genome(), fixture_config(), seed=5, out=tmp_path)
    assert result["valid"], result["reasons"]
    assert set(result["assays"]) == {"baseline", "push", "load", "object"}
    starts = [v["center_start"] for v in result["assays"].values()]
    np.testing.assert_allclose(starts, np.tile(starts[0], (4, 1)), rtol=0, atol=0)
    assert result["juvenile"]["segments"] > 1
    frames = [
        json.loads(line)
        for line in (tmp_path / "frames.jsonl").read_text().splitlines()
    ]
    adults = [f for f in frames if f["phase"] != "juvenile"]
    assert adults
    assert all(len(f["segments"]) == result["juvenile"]["segments"] for f in adults)
    assert result["assays"]["push"]["external_work"] != 0
    assert result["assays"]["load"]["external_work"] != 0


def test_passive_precursor_is_evaluable_without_actuator_work():
    result = evaluate(fixture_genome(passive=True), fixture_config(), seed=3)
    assert result["valid"], result["reasons"]
    assert result["juvenile"]["segments"] > 1
    assert result["juvenile"]["actuator_work"] == 0
    for metrics in result["assays"].values():
        assert metrics["actuator_work"] == 0
        assert metrics["energy_spent"] == 0
