from copy import deepcopy

import pytest

from tendril.genome import candidates, genome_id, seed_genome, validate_genome


def test_candidates_replay_are_legal_diverse_and_do_not_change_parent():
    parent = seed_genome(3)
    before = deepcopy(parent)
    pool = candidates(parent, 29, 128, seed_genome(10))
    assert pool == candidates(parent, 29, 128, seed_genome(10))
    assert parent == before
    assert len({c["id"] for c in pool}) == 128
    assert {
        "numeric",
        "direction",
        "duplicate",
        "branch",
        "prune",
        "passive",
        "differentiate",
        "recombine",
    } <= {c["kind"] for c in pool}
    for candidate in pool:
        validate_genome(candidate["genome"])
        assert candidate["id"] == genome_id(candidate["genome"])
        assert candidate["genome"] != parent


def test_module_duplication_deletion_and_rewiring():
    parent = next(
        c["genome"]
        for c in candidates(seed_genome(), 0, 32)
        if c["kind"] == "duplicate"
    )
    pool = candidates(parent, 80, 128)
    assert {"delete", "rewire"} <= {c["kind"] for c in pool}
    for candidate in pool:
        validate_genome(candidate["genome"])


@pytest.mark.parametrize(
    "change",
    [
        lambda g: g.update(root="missing"),
        lambda g: g["modules"][0].update(stiffness=float("nan")),
        lambda g: g["modules"][0].update(max_depth=1.5),
        lambda g: g["modules"][0].update(tissue=1),
        lambda g: g["modules"][0]["children"][0].update(direction=[0, 0, 0]),
        lambda g: g["modules"][0]["children"][0].update(direction=[0, float("inf"), 1]),
        lambda g: g["modules"][0]["children"][0].update(module="missing"),
        lambda g: g["modules"].append(deepcopy(g["modules"][0])),
    ],
)
def test_rejects_invalid_programs(change):
    g = seed_genome()
    change(g)
    with pytest.raises(ValueError):
        validate_genome(g)
