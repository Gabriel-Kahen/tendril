from dataclasses import replace

import mujoco as mj
import numpy as np
import pytest

from tendril.config import SimulationConfig
from tendril.elasticity import flex_deformation_metrics
from tendril.genome import seed_genome
from tendril.physics import World


def joint_states(world):
    return {
        world.model.joint(i).name: (
            world.data.joint(i).qpos.copy(),
            world.data.joint(i).qvel.copy(),
        )
        for i in range(world.model.njnt)
    }


def test_growth_preserves_moving_joints_and_time():
    world = World(seed_genome(1), SimulationConfig(timestep=0.001))
    assert world.grow(0, "m0", [1, 0.3, 0.8])
    for _ in range(40):
        world.control()
        world.step()
    before, time = joint_states(world), world.data.time
    assert any(np.linalg.norm(v) > 1e-3 for _, v in before.values())
    assert world.grow(1, "m0", [-0.3, 1, 0.8])
    for name, (position, velocity) in before.items():
        np.testing.assert_array_equal(world.data.joint(name).qpos, position)
        np.testing.assert_array_equal(world.data.joint(name).qvel, velocity)
    assert world.data.time == time
    assert world.events[-1]["position_error"] < 1e-10
    assert world.events[-1]["added_mass"] > 0
    assert world.events[-1]["charge"] > 0


def test_connection_is_finite_thickness_and_stress_free_at_creation():
    world = World(seed_genome(2), SimulationConfig(timestep=0.001))
    assert world.grow(0, "m0", [0.8, 0, 0.5])
    assert world.grow(0, "m0", [-0.4, 0.6, 0.7])
    for _ in range(30):
        world.control()
        world.step()
    old_mass = world.mass()
    assert world.attach(1, 2)
    flex = mj.mj_name2id(world.model, mj.mjtObj.mjOBJ_FLEX, "link0")
    edge = world.model.flex_edgeadr[flex]
    assert world.model.flex_dim[flex] == 1
    assert world.model.flex_radius[flex] > 0
    assert world.model.flex_contype[flex] != 0
    assert world.model.flexedge_length0[edge] == pytest.approx(
        world.data.flexedge_length[edge], abs=1e-10
    )
    assert world.mass() > old_mass
    assert not world.attach(1, 2)


def test_local_growth_has_three_independent_spatial_directions():
    world = World(seed_genome(), SimulationConfig())
    for direction in ([1, 0, 0.3], [0, 1, 0.3], [-0.7, -0.4, 0.8]):
        assert world.grow(0, "m0", direction)
    offsets = world.positions()[1:] - world.positions()[0]
    assert np.linalg.matrix_rank(offsets, tol=1e-8) == 3


def test_true_tissue_has_volume_and_no_initial_inversion():
    world = World(seed_genome(), SimulationConfig(timestep=0.0005))
    assert world.add_tissue(0)
    assert 3 in world.model.flex_dim
    measured = flex_deformation_metrics(world.model, world.data)
    assert measured["volumetric_elements"] >= 6
    assert measured["inverted_elements"] == 0
    assert measured["min_volume_ratio"] == pytest.approx(1, abs=1e-10)
    for _ in range(30):
        world.step()
    assert flex_deformation_metrics(world.model, world.data)["inverted_elements"] == 0
    assert np.isfinite(world.data.qvel).all()


def test_exhausted_budget_stops_muscle_work():
    world = World(seed_genome(), SimulationConfig(timestep=0.001))
    assert world.grow(0, "m0", [0.5, 0.2, 1])
    world.config = replace(world.config, energy_budget=world.spent)
    before = world.spent
    for _ in range(100):
        world.control()
        world.step()
    assert np.all(world.data.ctrl == 0)
    assert world.spent == before
    assert world.work == 0


def test_rejected_growth_restores_physical_state():
    world = World(seed_genome(), SimulationConfig())
    before = joint_states(world)
    world.config = replace(world.config, max_mass=world.mass() + 1e-10)
    assert not world.grow(0, "m0", [0.4, 0.3, 1])
    assert len(world.segments) == 1
    assert world.events[-1]["accepted"] is False
    for name, (position, velocity) in before.items():
        np.testing.assert_array_equal(world.data.joint(name).qpos, position)
        np.testing.assert_array_equal(world.data.joint(name).qvel, velocity)


def test_active_control_respects_small_remaining_energy_budget():
    world = World(seed_genome(4), SimulationConfig(timestep=0.0005))
    assert world.grow(0, "m0", [0.5, 0.2, 1])
    initial = world.spent
    world.config = replace(world.config, energy_budget=initial + 1e-4)
    for step in range(600):
        if step % 20 == 0:
            world.control()
        world.step()
        assert world.spent <= world.config.energy_budget + 1e-10
    assert world.spent > initial


def test_finite_but_crushed_tissue_is_rejected_by_material_gates():
    world = World(seed_genome(), SimulationConfig(timestep=0.0005))
    assert world.add_tissue(0)
    pin_x = float(world.data.flexvert_xpos[:, 0].min())
    # Prescribe 80% compression toward the pinned face, without inversion.
    for body in np.unique(world.model.flex_vertbodyid):
        if not world.model.body(int(body)).name.startswith("tissue"):
            continue
        for j in range(
            world.model.body_jntadr[body],
            world.model.body_jntadr[body] + world.model.body_jntnum[body],
        ):
            if np.array_equal(world.model.jnt_axis[j], [1, 0, 0]):
                world.data.qpos[world.model.jnt_qposadr[j]] = -0.8 * (
                    world.model.body_pos[body, 0] - pin_x
                )
    mj.mj_forward(world.model, world.data)
    assert np.isfinite(world.data.qpos).all()
    measured = flex_deformation_metrics(world.model, world.data, world.flex_reference)
    assert measured["inverted_elements"] == 0
    assert measured["min_volume_ratio"] == pytest.approx(0.2, abs=1e-10)
    assert {"invalid_tissue_volume", "excessive_tissue_strain"} <= set(world.validity())
