"""Scheduled growing 3D branch: contraction, contacts, closure, adult push.

Run: .venv/bin/python scripts/probe_branch.py --out runs/branch-probe
The legal schedule was found by exploratory fixture search, not evolution.
"""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import mujoco
import numpy as np

from tendril.config import SimulationConfig
from tendril.genome import seed_genome
from tendril.physics import World
from tendril.simulation import apply_force, write_json

SCHEDULE = [
    (0.0, 0, [0.020588802227547193, 0.7845375055886484, -0.6197394642489508]),
    (0.02, 1, [-0.48800888619762606, -0.19885031073203177, 0.8498858046313791]),
    (0.04, 2, [-0.18774590984356038, 0.10254320985900423, -0.9768502256993268]),
    (0.06, 3, [0.1131508777374394, -0.5050952343394637, 0.8556142139508959]),
    (0.08, 2, [-0.4153238934163758, -0.028009050362604974, 0.9092422981005932]),
    (0.10, 4, [0.7038180209047886, 0.12908141609750837, -0.698554351119459]),
]


def run(dt, out, tissue=False, tissue_young=50000.0):
    genome = seed_genome(1)
    genome["modules"][0].update(stiffness=0.02, amplitude=0.15, damping=0.01)
    config = SimulationConfig(
        timestep=dt, seed_height=0.2, max_segments=8, tissue_young=tissue_young
    )
    world = World(genome, config)
    frames, edits, reasons = [], [], set()
    next_edit, control_step = 0, max(1, round(config.control_interval / dt))
    adult_segments = None
    start = time.perf_counter()
    for step in range(round(1.3 / dt)):
        t = step * dt
        if next_edit < len(SCHEDULE) and t + dt / 2 >= SCHEDULE[next_edit][0]:
            _, parent, direction = SCHEDULE[next_edit]
            old_joints = {
                world.model.joint(j).name: (
                    world.data.joint(j).qpos.copy(),
                    world.data.joint(j).qvel.copy(),
                )
                for j in range(world.model.njnt)
            }
            accepted = world.grow(parent, "m0", direction)
            edits.append(
                dict(
                    operation="extend",
                    time_s=t,
                    accepted=accepted,
                    qpos_error=max(
                        float(np.max(abs(world.data.joint(name).qpos - q)))
                        for name, (q, v) in old_joints.items()
                    ),
                    qvel_error=max(
                        float(np.max(abs(world.data.joint(name).qvel - v)))
                        for name, (q, v) in old_joints.items()
                    ),
                )
            )
            next_edit += 1
            if not accepted:
                reasons.add("fixture_growth_rejected")
                break
        if step == round(0.12 / dt):
            edits.append(
                dict(operation="attach", time_s=t, accepted=world.attach(5, 6))
            )
        if tissue and step == round(0.14 / dt):
            edits.append(
                dict(operation="tissue", time_s=t, accepted=world.add_tissue(0))
            )
        if step == round(0.16 / dt):
            adult_segments = len(world.segments)
        if step % control_step == 0:
            world.control()
        world.data.qfrc_applied[:] = 0
        if step == round(0.6 / dt):
            apply_force(world, [0.005 / dt, -0.002 / dt, 0.001 / dt])
        world.step()
        if step % max(1, round(0.02 / dt)) == 0:
            phase = "juvenile" if t < 0.16 else "adult"
            frames.append(world.frame(phase))
            reasons.update(world.validity())
    reasons.update(world.validity())
    if not all(edit["accepted"] for edit in edits):
        reasons.add("fixture_edit_rejected")
    elapsed = time.perf_counter() - start
    offsets = world.positions() - world.positions()[0]
    result = dict(
        mujoco=mujoco.__version__,
        config=asdict(config),
        tissue=tissue,
        simulated_seconds=float(world.data.time),
        wall_seconds=elapsed,
        realtime_factor=float(world.data.time / elapsed),
        edits=edits,
        valid=not reasons,
        reasons=sorted(reasons),
        segments=len(world.segments),
        links=len(world.links),
        tissues=len(world.tissues),
        spatial_rank=int(np.linalg.matrix_rank(offsets)),
        adult_growth_paused=adult_segments == len(world.segments),
        floor_contacts=world.floor_contacts,
        nonadjacent_self_contacts=world.self_contacts,
        maximum_penetration_m=world.max_contact_penetration,
        tissue_min_volume_ratio=world.tissue_min_volume,
        tissue_max_principal_green_strain=world.tissue_max_strain,
        signed_actuator_work_j=world.work,
        positive_actuator_work_j=world.positive_work,
        external_work_j=world.external_work,
        charged_energy_j=world.spent,
        growth_energy_delta_j=world.growth_energy,
        final_energy_j=world.energy(),
        final_positions=world.positions().tolist(),
        limitations=[
            "Prescribed legal schedule, not a developmental genome result.",
            "Compliant contact admits measured penetration.",
            "Growth energy and momentum are logged; full energy balance remains open.",
        ],
    )
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "result.json", result)
    write_json(out / "genome.json", genome)
    write_json(out / "config.json", asdict(config))
    for name, rows in [("events", world.events), ("frames", frames)]:
        (out / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows)
        )
    (out / "adult.xml").write_text(world.xml())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("runs/branch-probe"))
    parser.add_argument("--timestep", type=float, default=0.001)
    parser.add_argument(
        "--mixed",
        action="store_true",
        help="Add true tetrahedral tissue at .14 seconds",
    )
    parser.add_argument(
        "--tissue-young", type=float, default=SimulationConfig().tissue_young
    )
    args = parser.parse_args()
    results = [
        run(dt, args.out / f"dt-{dt:g}", args.mixed, args.tissue_young)
        for dt in (args.timestep, args.timestep / 2)
    ]
    summary = [
        {
            k: r[k]
            for k in (
                "valid",
                "reasons",
                "realtime_factor",
                "segments",
                "links",
                "tissues",
                "spatial_rank",
                "floor_contacts",
                "nonadjacent_self_contacts",
                "maximum_penetration_m",
                "tissue_min_volume_ratio",
                "tissue_max_principal_green_strain",
            )
        }
        for r in results
    ]
    write_json(args.out / "comparison.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
