import mujoco as mj
import numpy as np
import pytest

from tendril.config import SimulationConfig
from tendril.genome import seed_genome
from tendril.physics import World
from tendril.simulation import develop


def active_contacts(world):
    return [
        contact
        for contact in world.data.contact
        if contact.exclude == 0 and contact.efc_address >= 0
    ]


def test_tissue_floor_contact_reaches_owner_and_muscle_controller():
    genome = seed_genome()
    genome["modules"][0].update(
        amplitude=0, contact_gain=0.5, strain_gain=0, signal_gain=0
    )
    world = World(genome, SimulationConfig())
    assert world.grow(0, "m0", [0, 0, 1])
    assert world.add_tissue(1)
    # Turn the rods horizontal: only the outer tissue face reaches the floor.
    world.data.joint("root").qpos[:] = [0, 0, 0.051, 2**-0.5, 0, 2**-0.5, 0]
    world.data.time = world.config.activation_ramp
    mj.mj_forward(world.model, world.data)

    contacts = active_contacts(world)
    assert contacts
    assert all(contact.geom.tolist() == [0, -1] for contact in contacts)
    tissue = mj.mj_name2id(world.model, mj.mjtObj.mjOBJ_FLEX, "tissue1")
    assert all(contact.flex.tolist() == [-1, tissue] for contact in contacts)
    assert world.contact_segments() == {1}
    world.control()
    np.testing.assert_allclose(world.data.ctrl, -0.5 * world.config.muscle_force)
    world.modules["m0"].update(
        contact_required=True, growth_age=0.1, max_depth=1, attach_radius=0
    )
    develop(world)
    assert world.segments[1].grown
    assert not world.segments[0].grown


def test_link_floor_contact_reaches_both_endpoints_only():
    world = World(seed_genome(), SimulationConfig())
    assert world.grow(0, "m0", [1, 0, 1])
    assert world.grow(0, "m0", [-1, 0, 1])
    assert world.attach(1, 2)
    # Isolate the finite-radius link's real collision response from its supports.
    for segment in world.segments:
        world.model.geom(f"g{segment.id}").contype[:] = 0
        world.model.geom(f"g{segment.id}").conaffinity[:] = 0
    world.data.joint("root").qpos[2] -= world.positions()[1, 2] - 0.002
    mj.mj_forward(world.model, world.data)

    contacts = active_contacts(world)
    assert contacts
    assert all(contact.geom.tolist() == [0, -1] for contact in contacts)
    link = mj.mj_name2id(world.model, mj.mjtObj.mjOBJ_FLEX, "link0")
    assert all(contact.flex.tolist() == [-1, link] for contact in contacts)
    assert world.contact_segments() == {1, 2}


@pytest.mark.parametrize("margin,height", [(0, 0.011), (0.01, 0.017)])
def test_capsule_floor_contact_includes_force_generating_margin(margin, height):
    world = World(seed_genome(), SimulationConfig())
    world.model.geom("g0").margin[:] = margin
    world.data.joint("root").qpos[2] = height
    mj.mj_forward(world.model, world.data)
    contacts = active_contacts(world)
    assert len(contacts) == 1
    assert contacts[0].geom.tolist() == [0, world.model.geom("g0").id]
    assert contacts[0].flex.tolist() == [-1, -1]
    assert world.contact_segments() == {0}


def test_solver_excluded_contact_does_not_trigger_feedback():
    genome = seed_genome()
    # Binary-exact dimensions produce an exact touching pair, with no penetration.
    genome["modules"][0].update(length=0.125, radius=0.015625)
    world = World(genome, SimulationConfig())
    world.data.joint("root").qpos[2] = 0.015625
    mj.mj_forward(world.model, world.data)
    capsule_contacts = [
        c for c in world.data.contact if world.model.geom("g0").id in c.geom
    ]
    assert len(capsule_contacts) == 1
    assert capsule_contacts[0].dist == 0
    assert capsule_contacts[0].exclude == 1
    assert capsule_contacts[0].efc_address == -1
    assert world.contact_segments() == set()
