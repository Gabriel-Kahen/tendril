"""Regression probes for material, actuation, topology and replay accounting."""

from dataclasses import replace

import mujoco as mj
import numpy as np
import pytest

from tendril.config import SimulationConfig
from tendril.genome import seed_genome
from tendril.physics import World
from tendril.simulation import center, develop, evaluate


def test_seed_over_material_budget_is_not_a_valid_organism():
    result = evaluate(
        seed_genome(),
        {"max_mass": 0.001, "juvenile_seconds": 0, "assay_seconds": 0.002},
    )
    assert result["accounting"]["initial_mass"] > 0.001
    assert not result["valid"]
    assert "material_budget_exceeded" in result["reasons"]


def test_absorbing_muscles_cannot_refund_supplying_muscles():
    w = World(seed_genome(), SimulationConfig(timestep=0.0001))
    assert w.grow(0, "m0", [0.8, 0.2, 1.0])
    w.data.joint("j1").qvel[:] = [1.0, 0.3, 0.0]
    w.data.time = 1.0
    w.previous_control[:] = -0.3
    mj.mj_forward(w.model, w.data)
    velocity = w.data.actuator_velocity.copy()
    length = w.data.actuator_length.copy()
    assert np.any(velocity > 0) and np.any(velocity < 0)
    before = w.spent
    w.step()
    per_muscle = w.data.actuator_force * (w.data.actuator_length - length)
    supplied = float(np.maximum(per_muscle, 0).sum())
    absorbed = float(np.maximum(-per_muscle, 0).sum())
    assert supplied > 0 and absorbed > 0
    assert w.positive_work == pytest.approx(supplied, rel=1e-10)
    operating_cost = float(np.abs(w.data.ctrl).sum()) * 0.001 * w.config.timestep
    assert w.spent - before == pytest.approx(supplied + operating_cost, rel=1e-9)
    assert w.spent - before > max(0.0, float(per_muscle.sum())) + operating_cost


def test_center_of_mass_accounts_for_deforming_unpinned_tissue():
    w = World(seed_genome(), SimulationConfig())
    assert w.add_tissue(0)
    previous = center(w).copy()
    for i in range(1, w.model.nbody):
        if w.model.body(i).name.startswith("tissue") and w.model.body_jntnum[i]:
            joint = w.model.body_jntadr[i]
            w.data.qpos[w.model.jnt_qposadr[joint]] += 0.015
            break
    else:
        pytest.fail("tissue has no movable material")
    mj.mj_forward(w.model, w.data)
    ids = [i for i in range(1, w.model.nbody) if w.model.body(i).name != "object"]
    expected = np.average(w.data.xipos[ids], axis=0, weights=w.model.body_mass[ids])
    np.testing.assert_allclose(center(w), expected, atol=1e-12)
    assert np.linalg.norm(center(w) - previous) > 1e-5
    assert sum(w.model.body_mass[ids]) == pytest.approx(w.mass())


def test_budget_failure_preserves_live_developmental_site_identity():
    genome = seed_genome()
    genome["modules"][0]["growth_age"] = 0.05
    w = World(genome, SimulationConfig(energy_budget=0.35))
    w.data.time = 0.1
    root = w.segments[0]
    develop(w)
    assert any(e.get("reason") == "material_or_energy_budget" for e in w.events)
    assert w.segments[0] is root
    assert root.grown
    before = len(w.events)
    develop(w)
    assert len(w.events) == before


def test_evaluation_binary_preserves_runtime_brace_rest_geometry(tmp_path, monkeypatch):
    import tendril.simulation as simulation

    captured = []

    class BracedWorld(World):
        def __init__(self, genome, config):
            super().__init__(genome, config)
            assert self.grow(0, "m0", [0.8, 0, 1])
            assert self.grow(0, "m0", [-0.8, 0.5, 1])
            self.data.joint("j1").qpos[:] = [np.cos(0.15), 0, np.sin(0.15), 0]
            mj.mj_forward(self.model, self.data)
            assert self.attach(1, 2)
            captured.append(self.model.flexedge_length0.copy())

    monkeypatch.setattr(simulation, "World", BracedWorld)
    evaluate(
        seed_genome(), {"juvenile_seconds": 0, "assay_seconds": 0.002}, out=tmp_path
    )
    binary = mj.MjModel.from_binary_path(str(tmp_path / "adult.mjb"))
    np.testing.assert_array_equal(binary.flexedge_length0, captured[0])
    # The edit happened away from default joint pose: merely recompiling XML loses it.
    plain_xml = mj.MjModel.from_xml_path(str(tmp_path / "adult.xml"))
    assert not np.allclose(plain_xml.flexedge_length0, captured[0], atol=1e-5)


def test_first_acceleration_from_rest_is_charged_mechanical_work():
    w = World(seed_genome(), SimulationConfig(timestep=0.002))
    assert w.grow(0, "m0", [0.8, 0.2, 1.0])
    w.previous_control[:] = [-3.0, -0.1, -0.1]
    mj.mj_forward(w.model, w.data)
    np.testing.assert_array_equal(w.data.actuator_velocity, np.zeros(w.model.nu))
    before, length = w.spent, w.data.actuator_length.copy()
    w.step()
    work = w.data.actuator_force * (w.data.actuator_length - length)
    assert np.maximum(work, 0).sum() > 1e-10
    assert w.positive_work == pytest.approx(np.maximum(work, 0).sum(), rel=1e-10)
    operating_cost = float(np.abs(w.data.ctrl).sum()) * 0.001 * w.config.timestep
    assert w.spent - before == pytest.approx(w.positive_work + operating_cost, rel=1e-9)


def test_transactional_power_and_energy_cap_advance_only_one_timestep(monkeypatch):
    w = World(seed_genome(), SimulationConfig(timestep=0.01, muscle_power=0.00001))
    assert w.grow(0, "m0", [0.8, 0.2, 1.0])
    w.previous_control[:] = [-3.0, -0.1, -0.1]
    w.config = replace(w.config, energy_budget=w.spent + 1e-8)
    before, clock = w.spent, w.data.time
    length = w.data.actuator_length.copy()
    attempts = []
    original_step = mj.mj_step

    def tracked_step(*args):
        attempts.append(1)
        return original_step(*args)

    monkeypatch.setattr(mj, "mj_step", tracked_step)
    w.step()
    assert (
        len(attempts) >= 2
    )  # Exercise rollback, not merely the preliminary force cap.
    per_muscle = w.data.actuator_force * (w.data.actuator_length - length)
    assert w.data.time == pytest.approx(clock + w.config.timestep)
    assert w.spent <= w.config.energy_budget + 1e-12
    assert (
        np.max(np.abs(per_muscle)) <= w.config.muscle_power * w.config.timestep + 1e-12
    )
    assert w.spent >= before
    for _ in range(10):
        w.step()
        assert w.spent <= w.config.energy_budget + 1e-12
