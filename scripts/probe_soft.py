"""Volumetric MuJoCo feasibility probe; SI units, independent of search.

Run: .venv/bin/python scripts/probe_soft.py --out runs/soft-probe
"""

from __future__ import annotations

import argparse
import itertools
import json
import platform
import time
from pathlib import Path

import mujoco
import numpy as np

from tendril.elasticity import flex_elastic_energy

YOUNG, POISSON, DENSITY = 20000.0, 0.3, 300.0
SPACING, RADIUS = 0.04, 0.002


def mesh(nx: int) -> tuple[np.ndarray, np.ndarray]:
    """Conforming six-tetrahedra decomposition, with stable node numbering."""
    points = np.array(
        [
            (x * SPACING, (y - 1) * SPACING, 0.01 + z * SPACING)
            for x in range(nx)
            for y in range(3)
            for z in range(3)
        ]
    )
    tets = []
    for x, y, z in itertools.product(range(nx - 1), range(2), range(2)):
        for permutation in itertools.permutations(range(3)):
            p = np.array([x, y, z])
            vertices = [p.copy()]
            for axis in permutation:
                p = p.copy()
                p[axis] += 1
                vertices.append(p)
            ids = [int(p[0] * 9 + p[1] * 3 + p[2]) for p in vertices]
            xyz = points[ids]
            if np.linalg.det((xyz[1:] - xyz[0]).T) < 0:
                ids[1], ids[2] = ids[2], ids[1]
            tets.append(ids)
    return points, np.array(tets)


def reference(points, tets):
    basis = (points[tets[:, 1:]] - points[tets[:, :1]]).transpose(0, 2, 1)
    return np.linalg.inv(basis), np.abs(np.linalg.det(basis)) / 6


def nodal_masses(points, tets):
    _, volume = reference(points, tets)
    masses = np.zeros(len(points))
    np.add.at(masses, tets.ravel(), np.repeat(DENSITY * volume / 4, 4))
    return masses


def elasticity(points, tets, actual):
    inv, volume = reference(points, tets)
    current = (actual[tets[:, 1:]] - actual[tets[:, :1]]).transpose(0, 2, 1)
    f = current @ inv
    strain = (f.transpose(0, 2, 1) @ f - np.eye(3)) / 2
    mu = YOUNG / (2 * (1 + POISSON))
    lam = YOUNG * POISSON / ((1 + POISSON) * (1 - 2 * POISSON))
    energy = np.sum(
        volume
        * (
            mu * np.sum(strain**2, axis=(1, 2))
            + 0.5 * lam * np.trace(strain, axis1=1, axis2=2) ** 2
        )
    )
    return float(energy), float(np.min(np.linalg.det(f))), float(np.max(np.abs(strain)))


def xml_model(points, tets, dt):
    fmt = lambda x: " ".join(format(float(v), ".17g") for v in np.asarray(x).ravel())
    masses = nodal_masses(points, tets)
    bodies = []
    for i, (p, mass) in enumerate(zip(points, masses)):
        joints = "".join(
            f'<joint name="n{i}_{a}" type="slide" axis="{fmt(v)}"/>'
            for a, v in enumerate(np.eye(3))
        )
        bodies.append(
            f'<body name="n{i}" pos="{fmt(p)}"><inertial pos="0 0 0" '
            f'mass="{mass:.17g}" diaginertia="1e-8 1e-8 1e-8"/>{joints}</body>'
        )
    names = " ".join(f"n{i}" for i in range(len(points)))
    elements = " ".join(map(str, tets.ravel()))
    return f'''<mujoco model="Tendril volumetric feasibility">
      <option timestep="{dt}" integrator="discrete" solver="Newton" iterations="50">
        <flag energy="enable" autoreset="disable"/>
      </option>
      <worldbody><geom name="floor" type="plane" size="2 2 .1" friction=".8 .01 .001"/>
        {"".join(bodies)}
      </worldbody>
      <deformable><flex name="tissue" dim="3" radius="{RADIUS}" body="{names}" element="{elements}">
        <elasticity young="{YOUNG}" poisson="{POISSON}" damping=".002"/>
        <contact selfcollide="auto" internal="false" friction=".8 .01 .001" solref=".005 1"/>
      </flex></deformable>
    </mujoco>'''


def state(model, data):
    mujoco.mj_forward(model, data)
    return data.flexvert_xpos.copy(), data.qvel.reshape(-1, 3).copy()


def account(model, data, points, tets):
    pos, vel = state(model, data)
    mass = nodal_masses(points, tets)
    elastic, min_j, strain = elasticity(points, tets, pos)
    return dict(
        kinetic_j=float(0.5 * np.sum(mass[:, None] * vel**2)),
        gravitational_j=float(np.sum(mass * pos[:, 2]) * 9.81),
        elastic_j=flex_elastic_energy(model, data),
        continuum_reference_elastic_j=elastic,
        min_volume_ratio=min_j,
        max_green_strain=strain,
        momentum_kg_m_s=np.sum(mass[:, None] * vel, axis=0).tolist(),
        engine_potential_j=float(data.energy[0]),
        engine_kinetic_j=float(data.energy[1]),
    )


def grow(model, data, old_points, old_tets, dt):
    """Append a slab; preserve old rest metric and every existing node state.

    Added nodes inherit displacement/velocity from the previous boundary plane.
    This creates bounded preload instead of resetting old tissue's elastic energy.
    Mass is lumped from new tetrahedra; increases at shared nodes are accounted.
    """
    old_pos, old_vel = state(model, data)
    before = account(model, data, old_points, old_tets)
    points, tets = mesh(len(old_points) // 9 + 1)
    spec = mujoco.MjSpec.from_string(xml_model(points, tets, dt))
    started = time.perf_counter()
    new_model = spec.compile()
    new_data = mujoco.MjData(new_model)
    elapsed = time.perf_counter() - started
    n = len(old_points)
    # A fresh compilation has default state: record this, then explicitly
    # transfer by joint name. Never assume array indices survive general edits.
    raw_pos, raw_vel = state(new_model, new_data)
    raw_error = float(np.max(np.abs(raw_pos[:n] - old_pos)))
    raw_vel_error = float(np.max(np.abs(raw_vel[:n] - old_vel)))
    for joint in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
        target = mujoco.mj_name2id(new_model, mujoco.mjtObj.mjOBJ_JOINT, name)
        new_data.qpos[new_model.jnt_qposadr[target]] = data.qpos[
            model.jnt_qposadr[joint]
        ]
        new_data.qvel[new_model.jnt_dofadr[target]] = data.qvel[model.jnt_dofadr[joint]]
    new_data.time = data.time
    new_data.qpos[3 * n :] = (old_pos[-9:] - old_points[-9:]).ravel()
    new_data.qvel[3 * n :] = old_vel[-9:].ravel()
    after = account(new_model, new_data, points, tets)
    new_pos, new_vel = state(new_model, new_data)
    old_mass, new_mass = nodal_masses(old_points, old_tets), nodal_masses(points, tets)
    mass_added = new_mass - np.pad(old_mass, (0, 9))
    supplied_p = np.sum(mass_added[:, None] * new_vel, axis=0)
    delta_p = np.array(after["momentum_kg_m_s"]) - before["momentum_kg_m_s"]
    kinetic_added = float(0.5 * np.sum(mass_added[:, None] * new_vel**2))
    grav_added = float(np.sum(mass_added * new_pos[:, 2]) * 9.81)
    event = dict(
        time_s=float(data.time),
        compile_wall_s=elapsed,
        old_nodes=n,
        new_nodes=len(points),
        added_mass_kg=float(sum(mass_added)),
        fresh_compile_default_position_error_m=raw_error,
        fresh_compile_default_velocity_error_m_s=raw_vel_error,
        preserved_position_error_m=float(np.max(np.abs(new_pos[:n] - old_pos))),
        preserved_velocity_error_m_s=float(np.max(np.abs(new_vel[:n] - old_vel))),
        momentum_residual_kg_m_s=(delta_p - supplied_p).tolist(),
        supplied_kinetic_j=kinetic_added,
        supplied_gravitational_j=grav_added,
        added_elastic_preload_j=after["elastic_j"] - before["elastic_j"],
        before=before,
        after=after,
    )
    return new_model, new_data, points, tets, event, spec.to_xml()


def probe(dt, duration, out):
    points, tets = mesh(3)
    initial_xml = xml_model(points, tets, dt)
    model = mujoco.MjModel.from_xml_string(initial_xml)
    data = mujoco.MjData(model)
    # Mild nonplanar initial deformation tests the 3D elastic response.
    data.qpos[3 * 26 + 1] = 0.002
    data.qpos[3 * 26 + 2] = 0.001
    rows, events, snapshots = [], [], []
    work, absolute_work, max_force, max_power = 0.0, 0.0, 0.0, 0.0
    max_floor, max_self, min_gap = 0, 0, 0.0
    min_j, max_strain, finite = 1.0, 0.0, True
    initial = account(model, data, points, tets)
    started = time.perf_counter()
    next_growth = 0.15
    sample_stride = max(1, int(0.01 / dt))
    last_xml = initial_xml
    for step in range(round(duration / dt)):
        if data.time + dt / 2 >= next_growth and len(points) < 45:
            model, data, points, tets, event, last_xml = grow(
                model, data, points, tets, dt
            )
            events.append(event)
            next_growth += 0.15
        pos, vel = state(model, data)
        # Internal muscle-like fiber, bounded force, power and shortening.
        a, b = 2, 26
        displacement = pos[b] - pos[a]
        length = np.linalg.norm(displacement)
        axis = displacement / max(length, 1e-12)
        relative_speed = float(np.dot(vel[b] - vel[a], axis))
        amplitude = 0.2 * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * data.time))
        force = (
            0.0
            if length < 0.055
            else min(amplitude, 0.01 / max(abs(relative_speed), 1e-12))
        )
        if relative_speed < -0.25:
            force = 0.0
        data.qfrc_applied[:] = 0
        data.qfrc_applied[3 * a : 3 * a + 3] = force * axis
        data.qfrc_applied[3 * b : 3 * b + 3] = -force * axis
        power = -force * relative_speed
        work += power * dt
        absolute_work += abs(power) * dt
        max_force = max(max_force, force)
        max_power = max(max_power, abs(power))
        mujoco.mj_step(model, data)
        if not np.all(np.isfinite(data.qpos)) or np.max(np.abs(data.qvel)) > 100:
            finite = False
            break
        floor = self_contact = 0
        for contact in data.contact:
            if 0 in contact.geom:
                floor += 1
            if all(x >= 0 for x in contact.flex):
                self_contact += 1
            min_gap = min(min_gap, float(contact.dist))
        max_floor = max(max_floor, floor)
        max_self = max(max_self, self_contact)
        if step % sample_stride == 0:
            measured = account(model, data, points, tets)
            min_j = min(min_j, measured["min_volume_ratio"])
            max_strain = max(max_strain, measured["max_green_strain"])
            rows.append(
                dict(
                    time_s=float(data.time),
                    nodes=len(points),
                    floor_contacts=floor,
                    self_contacts=self_contact,
                    work_j=work,
                    **measured,
                )
            )
            padded = np.full((45, 3), np.nan)
            padded[: len(points)] = data.flexvert_xpos
            snapshots.append(padded)
    wall = time.perf_counter() - started
    final = account(model, data, points, tets)
    result = dict(
        mujoco=mujoco.__version__,
        python=platform.python_version(),
        timestep_s=dt,
        requested_duration_s=duration,
        simulated_s=float(data.time),
        wall_s=wall,
        realtime_factor=float(data.time / wall),
        finite=finite,
        vertices=len(points),
        tetrahedra=len(tets),
        initial=initial,
        final=final,
        growth_events=events,
        max_floor_contacts=max_floor,
        max_self_contacts=max_self,
        minimum_contact_distance_m=min_gap,
        min_volume_ratio=min_j,
        max_green_strain=max_strain,
        signed_actuator_work_j=work,
        absolute_actuator_work_j=absolute_work,
        max_actuator_force_n=max_force,
        max_actuator_power_w=max_power,
        warnings=data.warning.number.tolist(),
        assumptions=dict(
            young_pa=YOUNG,
            poisson=POISSON,
            density_kg_m3=DENSITY,
            contact_radius_m=RADIUS,
            mesh_spacing_m=SPACING,
        ),
        limitations=[
            "Small-strain constitutive material; no arbitrary squash claim.",
            "Self-contact enabled; count determines whether actually exercised.",
            "Contact/friction/Rayleigh losses are not integrated into an energy balance.",
            "Prescribed append policy is a physics probe, not a developmental genome.",
        ],
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (out / "initial.xml").write_text(initial_xml)
    (out / "final.xml").write_text(last_xml)
    np.savez_compressed(
        out / "trajectory.npz", positions=snapshots, times=[r["time_s"] for r in rows]
    )
    return result


def self_contact_probe(dt, out):
    """Two disconnected volumes in one flex isolate the self-contact pathway.

    This is a collision fixture, not evidence that a grown organism can fold.
    """
    base, tets = mesh(3)
    points = np.vstack([base, base + [0.01, 0.015, 0.12]])
    elements = np.vstack([tets, tets + len(base)])
    model = mujoco.MjModel.from_xml_string(xml_model(points, elements, dt))
    data = mujoco.MjData(model)
    max_contacts, minimum_ratio = 0, 1.0
    for step in range(round(0.4 / dt)):
        mujoco.mj_step(model, data)
        max_contacts = max(
            max_contacts, sum(all(x >= 0 for x in c.flex) for c in data.contact)
        )
        if step % 20 == 0:
            measured = account(model, data, points, elements)
            minimum_ratio = min(minimum_ratio, measured["min_volume_ratio"])
    result = dict(
        timestep_s=dt,
        max_same_flex_contacts=max_contacts,
        min_volume_ratio=minimum_ratio,
        finite=bool(np.all(np.isfinite(data.qpos))),
        fixture="Two disconnected tetrahedral blocks belonging to one flex",
        limitation="Collision subsystem test, not grown-organism folding",
    )
    (out / "self-contact.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("runs/soft-probe"))
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--timestep", type=float, default=0.0005)
    args = parser.parse_args()
    if args.duration < 0.4 or args.timestep <= 0:
        parser.error("duration must be >= .4; timestep must be positive")
    results = [
        probe(dt, args.duration, args.out / f"dt-{dt:g}")
        for dt in (args.timestep, args.timestep / 2)
    ]
    summary = [
        {
            key: r[key]
            for key in (
                "timestep_s",
                "finite",
                "vertices",
                "tetrahedra",
                "realtime_factor",
                "max_floor_contacts",
                "max_self_contacts",
                "min_volume_ratio",
                "max_green_strain",
            )
        }
        for r in results
    ]
    (args.out / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    contact = self_contact_probe(args.timestep, args.out)
    print(json.dumps(dict(growth=summary, self_contact_fixture=contact), indent=2))


if __name__ == "__main__":
    main()
