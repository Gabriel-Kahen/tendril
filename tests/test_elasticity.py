import mujoco
import numpy as np
import pytest

from tendril.elasticity import flex_elastic_energy


def test_energy_gradient_matches_engine_for_multiple_tissues():
    tissues = "".join(
        f'''<flexcomp name="tissue{i}" type="grid" dim="3"
        count="2 2 2" spacing=".04 .04 .04" pos="{i * 0.2} 0 .1" mass=".03">
        <elasticity young="20000" poisson=".3" damping="0"/>
        </flexcomp>'''
        for i in range(2)
    )
    model = mujoco.MjModel.from_xml_string(f"""<mujoco>
        <option integrator="discrete" gravity="0 0 0"><flag energy="enable"/></option>
        <worldbody>{tissues}</worldbody></mujoco>""")
    data = mujoco.MjData(model)
    data.qpos[:] = np.random.default_rng(123).normal(0, 0.0002, model.nq)
    mujoco.mj_forward(model, data)
    force = data.qfrc_spring.copy()
    assert flex_elastic_energy(model, data) > 0
    for index in (0, 10, model.nq - 1):
        original = data.qpos[index]
        energies = []
        for delta in (-1e-7, 1e-7):
            data.qpos[index] = original + delta
            mujoco.mj_forward(model, data)
            energies.append(flex_elastic_energy(model, data))
        data.qpos[index] = original
        gradient = (energies[1] - energies[0]) / 2e-7
        assert -gradient == pytest.approx(force[index], rel=1e-6, abs=1e-8)


def test_one_dimensional_flex_energy_already_in_engine():
    model = mujoco.MjModel.from_xml_string("""<mujoco>
      <option gravity="0 0 0"><flag energy="enable"/></option><worldbody>
      <body name="a"><freejoint/><geom size=".01" mass=".1"/></body>
      <body name="b" pos=".1 0 0"><freejoint/><geom size=".01" mass=".1"/></body>
      </worldbody><deformable><flex dim="1" body="a b" element="0 1" radius=".003">
      <edge stiffness="5"/></flex></deformable></mujoco>""")
    data = mujoco.MjData(model)
    data.qpos[7] = 0.12
    mujoco.mj_forward(model, data)
    assert data.energy[0] == pytest.approx(0.5 * 5 * 0.02**2)
    assert flex_elastic_energy(model, data) == 0


def test_volumetric_strain_recognizes_inversion():
    from tendril.elasticity import flex_deformation_metrics, flex_reference_positions

    model = mujoco.MjModel.from_xml_string("""<mujoco><option integrator="discrete"/>
      <worldbody><flexcomp name="tissue" type="grid" dim="3" count="2 2 2"
      spacing=".04 .04 .04" pos="0 0 .1" mass=".03">
      <elasticity young="20000" poisson=".3" damping="0"/></flexcomp></worldbody></mujoco>""")
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    reference = flex_reference_positions(model)
    assert flex_deformation_metrics(model, data, reference)[
        "min_volume_ratio"
    ] == pytest.approx(1)
    # Mirror all positions about the y-z plane: unit magnitude, negative volume.
    data.qpos[::3] = -2 * reference[:, 0]
    mujoco.mj_forward(model, data)
    measured = flex_deformation_metrics(model, data, reference)
    assert measured["min_volume_ratio"] == pytest.approx(-1)
    assert measured["inverted_elements"] == model.nflexelem


def test_engine_warning_array_preserves_all_warning_checks():
    from tendril.config import SimulationConfig
    from tendril.genome import seed_genome
    from tendril.physics import World
    from tendril.simulation import advance

    for index in range(int(mujoco.mjtWarning.mjNWARNING)):
        world = World(seed_genome(), SimulationConfig())
        assert not world.data.warning.number.any()
        world.data.warning[index].number = 1
        assert any(w.number for w in world.data.warning)
        assert world.data.warning.number.any()
        assert "engine_warning" in world.validity()
        assert advance(world, world.config.timestep, "adult", []) == ["engine_warning"]
