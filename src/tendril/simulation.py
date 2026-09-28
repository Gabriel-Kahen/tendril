"""Local developmental execution, independent adult assays, and replay records."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import mujoco as mj
import numpy as np

from .config import SimulationConfig
from .genome import genome_id, validate_genome
from .physics import World
from .signals import advance_signals

DESCRIPTOR_VERSION = 1


@lru_cache(maxsize=1)
def source_version():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def develop(world):
    """Execute each mature site's local rule; no task/body-plan instructions."""
    contacts = world.contact_segments()
    for s in list(world.segments):
        m = world.modules[s.module]
        if s.grown or world.data.time - s.born < m["growth_age"]:
            continue
        if world.joint_strain(s) > m["strain_limit"]:
            continue
        if m["contact_required"] and s.id not in contacts:
            continue
        # Differentiation produces actual volume elements with elastic mechanics.
        if m["tissue"]:
            world.add_tissue(s.id)
        if s.depth < m["max_depth"]:
            for child in m["children"]:
                world.grow(s.id, child["module"], child["direction"])
        s.grown = True
        if m["attach_radius"] > 0:
            positions = world.positions()
            adjacent = {s.id, s.parent} | {
                v.id for v in world.segments if v.parent == s.id
            }
            candidates = [
                (np.linalg.norm(positions[s.id] - p), i)
                for i, p in enumerate(positions)
                if i not in adjacent
            ]
            for distance, i in sorted(candidates):
                if distance <= m["attach_radius"] and world.attach(s.id, i):
                    break


def clone(world):
    copy = World.__new__(World)
    for key, value in world.__dict__.items():
        if key not in ("model", "data"):
            setattr(copy, key, deepcopy(value))
    model, data = world.compile()
    world.transfer(model, data)
    copy.model, copy.data = model, data
    return copy


def center(world):
    ids = [
        i for i in range(1, world.model.nbody) if world.model.body(i).name != "object"
    ]
    mass = world.model.body_mass[ids]
    return np.average(world.data.xipos[ids], axis=0, weights=mass)


def apply_force(world, force, segment=0):
    body = world.model.body(f"s{segment}").id
    mj.mj_applyFT(
        world.model,
        world.data,
        np.array(force, dtype=float),
        np.zeros(3),
        world.data.xipos[body],
        body,
        world.data.qfrc_applied,
    )


def advance(world, seconds, phase, frames, growth=False, perturbation=None):
    c = world.config
    next_control = world.data.time
    next_growth = world.data.time
    next_frame = world.data.time
    steps = int(math.ceil(seconds / c.timestep))
    for step in range(steps):
        world.data.qfrc_applied[:] = 0
        if perturbation:
            perturbation(world, step * c.timestep)
        if growth and world.data.time + 1e-9 >= next_growth:
            develop(world)
            next_growth += c.growth_interval
        if world.data.time + 1e-9 >= next_control:
            world.control()
            next_control += c.control_interval
        world.step()
        advance_signals(world, c.timestep)
        if world.data.warning.number.any():
            frames.append(world.frame(phase))
            return ["engine_warning"]
        if world.data.time + 1e-9 >= next_frame:
            frames.append(world.frame(phase))
            next_frame += c.frame_interval
            reasons = world.validity()
            if reasons:
                return reasons
    frames.append(world.frame(phase))
    return world.validity()


def assay(adult, kind, seed, frames):
    w = clone(adult)
    c = w.config
    initial_center = center(w)
    initial_positions = w.positions()
    initial_spent, initial_work, initial_external = w.spent, w.work, w.external_work
    signals_start = [s.signal for s in w.segments]
    rng = np.random.default_rng(seed)
    angle = rng.uniform(-math.pi, math.pi)
    direction = np.array([math.cos(angle), math.sin(angle), 0.0])
    highest = int(np.argmax(initial_positions[:, 2]))
    if kind == "object":
        # Place the standardized object beside the organism with a clear gap.
        p = initial_positions[int(np.argmax(initial_positions[:, 0]))].copy()
        p += [0.065, 0, 0]
        p[2] = max(0.026, p[2])
        before = w.energy()
        w.data.joint("object_free").qpos[:3] = p
        w.data.joint("object_free").qvel[:] = 0
        mj.mj_forward(w.model, w.data)
        w.events.append(
            {
                "type": "assay_object_placement",
                "time": float(w.data.time),
                "external_energy": w.energy() - before,
                "position": p.tolist(),
            }
        )
    object_start = w.data.body("object").xpos.copy()

    def perturb(world, t):
        if kind == "push" and 0.2 <= t < 0.2 + c.timestep:
            apply_force(world, direction * c.push_impulse / c.timestep)
        if kind == "load" and 0.2 <= t < c.assay_seconds * 0.75:
            apply_force(world, [0, 0, -c.load_force], highest)

    reasons = advance(w, c.assay_seconds, kind, frames, perturbation=perturb)
    final = center(w)
    source = initial_positions - initial_positions.mean(axis=0)
    target = w.positions()
    target -= target.mean(axis=0)
    u, _, vt = np.linalg.svd(source.T @ target)
    correction = np.diag([1.0, 1.0, np.linalg.det(u @ vt)])
    distances = np.linalg.norm(source @ u @ correction @ vt - target, axis=1)
    metrics = {
        "signals_start": signals_start,
        "signals_end": [s.signal for s in w.segments],
        "center_start": initial_center.tolist(),
        "center_end": final.tolist(),
        "simulated_seconds": float(w.data.time - adult.data.time),
        "displacement": float(np.linalg.norm((final - initial_center)[:2])),
        "height": float(final[2]),
        "deformation": float(np.mean(distances)),
        "object_displacement": float(
            np.linalg.norm((w.data.body("object").xpos - object_start)[:2])
        ),
        "energy_spent": w.spent - initial_spent,
        "actuator_work": w.work - initial_work,
        "external_work": w.external_work - initial_external,
        "final_energy": w.energy(),
        "minimum_tissue_volume_ratio": w.tissue_min_volume,
        "maximum_tissue_strain": w.tissue_max_strain,
        "floor_contacts": w.floor_contacts - adult.floor_contacts,
        "self_contacts": w.self_contacts - adult.self_contacts,
        "max_penetration": w.max_contact_penetration,
        "valid": not reasons,
        "reasons": reasons,
    }
    return metrics, w


def evaluate(genome, config=None, seed=0, out=None):
    validate_genome(genome)
    c = SimulationConfig.from_dict(config)
    started = time.perf_counter()
    frames, assays = [], {}
    w = World(genome, c)
    frames.append(w.frame("juvenile"))
    reasons = w.validity() or advance(
        w, c.juvenile_seconds, "juvenile", frames, growth=True
    )
    juvenile = {
        "energy": w.energy(),
        "spent": w.spent,
        "mass": w.mass(),
        "actual_seconds": float(w.data.time),
        "minimum_tissue_volume_ratio": w.tissue_min_volume,
        "maximum_tissue_strain": w.tissue_max_strain,
        "actuator_work": w.work,
        "growth_energy": w.growth_energy,
        "segments": len(w.segments),
        "tissues": len(w.tissues),
        "links": len(w.links),
    }
    all_events = deepcopy(w.events)
    if not reasons:
        for i, kind in enumerate(("baseline", "push", "load", "object")):
            metrics, trial = assay(w, kind, seed + i, frames)
            assays[kind] = metrics
            reasons.extend(f"{kind}:{r}" for r in metrics["reasons"])
            all_events.extend(
                {**e, "phase": kind} for e in trial.events[len(w.events) :]
            )
    positions = w.positions()
    span = np.ptp(positions, axis=0)
    children = [sum(v.parent == s.id for v in w.segments) for s in w.segments]
    structure = [
        len(w.segments) / c.max_segments,
        len(w.links) / max(1, len(w.segments)),
        float(sum(n > 1 for n in children) / len(children)),
        *np.minimum(span, 2.0).tolist(),
        len(w.tissues) / max(1, c.max_tissues),
    ]
    baseline = assays.get("baseline", {})
    push = assays.get("push", {})
    load = assays.get("load", {})
    obj = assays.get("object", {})
    motion = baseline.get("displacement", 0.0)
    # Separate capability axes: no global weighted score or mandatory locomotion.
    support = max(0.0, load.get("height", 0.0))
    recovery = 0.0
    if baseline and push:
        recovery = 1 / (
            1 + np.linalg.norm(np.array(push["center_end"]) - baseline["center_end"])
        )
    manipulation = obj.get("object_displacement", 0.0)
    efficiency = 1 / (1 + baseline.get("energy_spent", 0.0) / max(w.mass(), 1e-9))
    capabilities = dict(
        motion=motion,
        support=support,
        recovery=float(recovery),
        manipulation=manipulation,
        efficiency=efficiency,
    )
    behavior = [
        motion,
        support,
        float(recovery),
        manipulation,
        baseline.get("deformation", 0.0),
        push.get("deformation", 0.0),
        baseline.get("energy_spent", 0.0) / max(c.energy_budget, 1e-9),
    ]
    elapsed = time.perf_counter() - started
    result = {
        "id": genome_id(genome),
        "genome": genome,
        "seed": seed,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
        "descriptor_version": DESCRIPTOR_VERSION,
        "descriptors": {"structure": structure, "behavior": behavior},
        "capabilities": capabilities,
        "assays": assays,
        "juvenile": juvenile,
        "accounting": {
            "initial_mass": w.initial_mass,
            "final_mass": w.mass(),
            "initial_energy": w.initial_energy,
            "growth_energy": w.growth_energy,
            "juvenile_actuator_work": w.work,
            "juvenile_positive_actuator_work": w.positive_work,
            "juvenile_spent": w.spent,
            "edit_seconds": w.edit_seconds,
            "max_penetration": w.max_contact_penetration,
        },
        "timing": {
            "wall_seconds": elapsed,
            "simulated_seconds": float(w.data.time)
            + sum(a["simulated_seconds"] for a in assays.values()),
        },
        "versions": {
            "mujoco": mj.__version__,
            "numpy": np.__version__,
            "python": platform.python_version(),
            "source_sha256": source_version(),
        },
        "config": c.to_dict(),
    }
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for name, value in [
            ("genome", genome),
            ("config", c.to_dict()),
            ("result", result),
        ]:
            write_json(out / f"{name}.json", value)
        for name, values in [("frames", frames), ("events", all_events)]:
            (out / f"{name}.jsonl").write_text(
                "".join(json.dumps(v, allow_nan=False) + "\n" for v in values)
            )
        (out / "adult.xml").write_text(w.xml())
        mj.mj_saveModel(w.model, str(out / "adult.mjb"))
        np.savez_compressed(
            out / "adult_state.npz",
            qpos=w.data.qpos,
            qvel=w.data.qvel,
            time=w.data.time,
            ctrl=w.data.ctrl,
            act=w.data.act,
            qacc_warmstart=w.data.qacc_warmstart,
        )
    return result
