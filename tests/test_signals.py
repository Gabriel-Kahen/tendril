import math
from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from tendril.config import SimulationConfig
from tendril.genome import seed_genome
from tendril.physics import World
from tendril.signals import advance_signals
from tendril.simulation import advance, assay, develop


def network(values, parents, *, diffusion=0.2, decay=0.1, emission=0):
    return SimpleNamespace(
        segments=[
            SimpleNamespace(id=i, parent=parent, module="m", signal=value)
            for i, (value, parent) in enumerate(zip(values, parents))
        ],
        links=[],
        modules={"m": {"signal_emit": emission}},
        config=SimpleNamespace(signal_diffusion=diffusion, signal_decay=decay),
    )


def signals(world):
    return np.array([site.signal for site in world.segments])


def test_isolated_source_and_decay_follow_analytic_solution():
    world = network([0.2], [None], decay=0.4, emission=0.3)
    advance_signals(world, 1.7)
    expected = 0.2 * math.exp(-0.4 * 1.7) + 0.3 / 0.4 * (1 - math.exp(-0.4 * 1.7))
    np.testing.assert_allclose(signals(world), [expected], atol=1e-14)


def test_two_site_diffusion_conserves_sum_and_matches_analytic_difference():
    world = network([1, -0.5], [None, 0], diffusion=0.7, decay=0)
    advance_signals(world, 0.8)
    difference = 1.5 * math.exp(-2 * 0.7 * 0.8)
    np.testing.assert_allclose(
        signals(world), [0.25 + difference / 2, 0.25 - difference / 2]
    )
    assert abs(sum(signals(world)) - 0.5) < 1e-14


def test_disconnected_components_and_large_diffusion_preserve_constant_modes():
    world = network([1, 1, -0.2, -0.2], [None, 0, None, 2], diffusion=1e12, decay=0)
    advance_signals(world, 1)
    np.testing.assert_allclose(signals(world), [1, 1, -0.2, -0.2], atol=1e-12)


def test_loop_changes_transport_without_double_counting_tree_edges():
    base = network([1, 0, 0], [None, 0, 1], decay=0)
    duplicate, loop = deepcopy(base), deepcopy(base)
    duplicate.links = [SimpleNamespace(a=0, b=1)]
    loop.links = [SimpleNamespace(a=0, b=2)]
    for world in (base, duplicate, loop):
        advance_signals(world, 0.5)
    np.testing.assert_allclose(signals(base), signals(duplicate), atol=1e-14)
    assert loop.segments[2].signal > base.segments[2].signal
    assert abs(sum(signals(loop)) - 1) < 1e-14


def test_elapsed_time_partition_does_not_change_unsaturated_dynamics():
    whole = network([0.1, 0.7, -0.3], [None, 0, 0], emission=0.2)
    pieces = deepcopy(whole)
    advance_signals(whole, 0.7)
    for _ in range(7):
        advance_signals(pieces, 0.1)
    np.testing.assert_allclose(signals(whole), signals(pieces), atol=1e-13)
    saturated = network([4.9], [None], emission=1, decay=0)
    advance_signals(saturated, 10)
    assert saturated.segments[0].signal == 5


def physical_world():
    genome = seed_genome(4)
    genome["modules"][0].update(
        signal_emit=1,
        signal_gain=1,
        amplitude=0,
        strain_gain=0,
        contact_gain=0,
        growth_age=0.1,
        max_depth=2,
    )
    return World(
        genome, SimulationConfig.from_dict({"seed_height": 0.8, "assay_seconds": 0.05})
    )


def test_newborn_starts_at_zero_without_advancing_existing_signals():
    world = physical_world()
    world.segments[0].signal = 0.7
    assert world.grow(0, world.segments[0].module, [0, 0, 1])
    np.testing.assert_array_equal(signals(world), [0.7, 0])
    develop(world)
    np.testing.assert_array_equal(signals(world), [0.7, 0])
    advance_signals(world, 0.01)
    assert world.segments[1].signal > 0


def test_adult_signaling_drives_control_while_topology_stays_fixed():
    world = physical_world()
    assert world.grow(0, world.segments[0].module, [0, 0, 1])
    assert not advance(world, 0.05, "adult", [], growth=False)
    assert len(world.segments) == 2 and not world.links and not world.tissues
    assert np.all(signals(world) > 0)
    assert np.all(world.previous_control < 0)


def test_assays_inherit_signals_and_evolve_without_mutating_adult():
    adult = physical_world()
    adult.segments[0].signal = 0.2
    first, first_world = assay(adult, "baseline", 1, [])
    second, second_world = assay(adult, "push", 2, [])
    assert first["signals_start"] == second["signals_start"] == [0.2]
    assert first["signals_end"][0] > 0.2
    np.testing.assert_allclose(signals(first_world), signals(second_world), atol=1e-14)
    assert adult.segments[0].signal == 0.2
