"""Small, bounded developmental programs and concrete, replayable variations.

Directions are expressed in a site's local 3D frame. Module references may be
recursive; age, depth, material and simulation budgets bound their execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from copy import deepcopy

BOUNDS = {
    "length": (0.035, 0.3),
    "radius": (0.004, 0.035),
    "stiffness": (0.005, 2.0),
    "damping": (0.001, 0.2),
    "amplitude": (0.0, 0.3),
    "frequency": (0.0, 4.0),
    "phase": (-math.pi, math.pi),
    "strain_gain": (-2.0, 2.0),
    "contact_gain": (-2.0, 2.0),
    "signal_gain": (-2.0, 2.0),
    "signal_emit": (-1.0, 1.0),
    "growth_age": (0.05, 3.0),
    "max_depth": (0, 8),
    "strain_limit": (0.01, 5.0),
    "attach_radius": (0.0, 0.3),
}
MAX_MODULES, MAX_CHILDREN = 24, 6


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def genome_id(genome: dict) -> str:
    return hashlib.sha256(canonical(genome).encode()).hexdigest()[:20]


def seed_genome(seed: int = 0) -> dict:
    """A reproducible branching seed, not a prebuilt locomotion controller."""
    rng = random.Random(seed)
    module = dict(
        id="m0",
        length=0.12,
        radius=0.012,
        stiffness=0.08,
        damping=0.015,
        amplitude=0.03,
        frequency=1.0,
        phase=rng.uniform(-math.pi, math.pi),
        strain_gain=0.0,
        contact_gain=0.0,
        signal_gain=0.0,
        signal_emit=0.0,
        growth_age=0.25,
        max_depth=3,
        strain_limit=1.5,
        contact_required=False,
        attach_radius=0.12,
        tissue=False,
        children=[
            {"module": "m0", "direction": [0.55, 0.25, 1.0]},
            {"module": "m0", "direction": [-0.4, -0.6, 0.8]},
        ],
    )
    return {"version": 1, "root": "m0", "modules": [module]}


def validate_genome(genome: dict) -> None:
    """Reject malformed programs before they reach either physics or guidance."""
    if (
        not isinstance(genome, dict)
        or type(genome.get("version")) is not int
        or genome.get("version") != 1
    ):
        raise ValueError("genome version must be 1")
    modules = genome.get("modules")
    if not isinstance(modules, list) or not 1 <= len(modules) <= MAX_MODULES:
        raise ValueError(f"genome requires 1–{MAX_MODULES} modules")
    if any(not isinstance(m, dict) for m in modules):
        raise ValueError("modules must be objects")
    ids = [m.get("id") for m in modules]
    if any(not isinstance(i, str) or not i or len(i) > 80 for i in ids):
        raise ValueError("module IDs must be nonempty short strings")
    if len(set(ids)) != len(ids) or genome.get("root") not in ids:
        raise ValueError("module IDs must be unique and root must exist")
    for module in modules:
        for field, (low, high) in BOUNDS.items():
            value = module.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(
                    f"{module['id']}.{field} must be finite in [{low}, {high}]"
                )
        if not isinstance(module["max_depth"], int):
            raise ValueError("max_depth must be an integer")
        for flag in ("contact_required", "tissue"):
            if not isinstance(module.get(flag), bool):
                raise ValueError(f"{flag} must be boolean")
        children = module.get("children")
        if not isinstance(children, list) or len(children) > MAX_CHILDREN:
            raise ValueError(f"children must be a list of at most {MAX_CHILDREN}")
        for child in children:
            if not isinstance(child, dict) or child.get("module") not in ids:
                raise ValueError("child must reference an existing module")
            d = child.get("direction")
            if (
                not isinstance(d, list)
                or len(d) != 3
                or any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    or abs(v) > 4
                    for v in d
                )
                or sum(v * v for v in d) < 1e-10
            ):
                raise ValueError("direction must be a nonzero bounded finite 3-vector")
    try:
        canonical(genome)
    except (TypeError, ValueError) as exc:
        raise ValueError("genome must be finite JSON") from exc


def _fresh_id(modules):
    ids = {m["id"] for m in modules}
    return next(f"m{i}" for i in range(MAX_MODULES + 1) if f"m{i}" not in ids)


def _direction(rng):
    return [rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)]


def _edit(genome, rng, kind, donor):
    offspring = deepcopy(genome)
    modules = offspring["modules"]
    m = rng.choice(modules)
    ids = [v["id"] for v in modules]
    detail = m["id"]
    if kind == "numeric":
        field = rng.choice(list(BOUNDS))
        low, high = BOUNDS[field]
        old = m[field]
        if field == "max_depth":
            m[field] = max(low, min(high, old + rng.choice([-1, 1])))
        else:
            m[field] = max(low, min(high, old + rng.gauss(0, (high - low) * 0.12)))
        detail += f".{field}: {old:.6g} -> {m[field]:.6g}"
    elif kind == "direction" and m["children"]:
        c = rng.choice(m["children"])
        c["direction"] = _direction(rng)
        detail += f" local direction -> {c['direction']}"
    elif kind == "duplicate" and len(modules) < MAX_MODULES:
        copied = deepcopy(m)
        copied["id"] = _fresh_id(modules)
        # Self references stay within the duplicated module, preserving its motif.
        for c in copied["children"]:
            if c["module"] == m["id"]:
                c["module"] = copied["id"]
        modules.append(copied)
        if m["children"]:
            rng.choice(m["children"])["module"] = copied["id"]
        else:
            m["children"].append({"module": copied["id"], "direction": _direction(rng)})
        detail += f" duplicated as {copied['id']}, linked from source"
    elif kind == "delete" and len(modules) > 1:
        deleted = rng.choice([x for x in modules if x["id"] != offspring["root"]])
        modules.remove(deleted)
        for module in modules:
            module["children"] = [
                c for c in module["children"] if c["module"] != deleted["id"]
            ]
        detail = f"delete {deleted['id']} and incoming developmental references"
    elif kind == "rewire" and m["children"]:
        c = rng.choice(m["children"])
        c["module"] = rng.choice(ids)
        detail += f" child reference -> {c['module']}"
    elif kind == "branch" and len(m["children"]) < MAX_CHILDREN:
        m["children"].append({"module": rng.choice(ids), "direction": _direction(rng)})
        detail += " add local branch"
    elif kind == "prune" and m["children"]:
        del m["children"][rng.randrange(len(m["children"]))]
        detail += " remove local branch"
    elif kind == "passive":
        m["amplitude"] = m["strain_gain"] = m["contact_gain"] = m["signal_gain"] = 0.0
        detail += " remove active contraction and feedback; preserve passive mechanics"
    elif kind == "differentiate":
        field = rng.choice(["tissue", "contact_required"])
        m[field] = not m[field]
        detail += f".{field} -> {m[field]}"
    elif kind == "recombine" and donor:
        copied = deepcopy(rng.choice(donor["modules"]))
        source_id = copied["id"]
        copied["id"] = m["id"]
        # Import a whole module and its controller; remap external references locally.
        for c in copied["children"]:
            c["module"] = copied["id"] if c["module"] == source_id else rng.choice(ids)
        modules[modules.index(m)] = copied
        detail += f" replace with donor {genome_id(donor)} module {source_id}"
    return offspring, detail


def candidates(
    genome: dict, seed: int, count: int = 32, donor: dict | None = None
) -> list[dict]:
    """Generate unique legal concrete edits; selectors all receive this same pool."""
    validate_genome(genome)
    if donor is not None:
        validate_genome(donor)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 255:
        raise ValueError("candidate count must be an integer in [1,255]")
    rng = random.Random(seed)
    kinds = [
        "numeric",
        "direction",
        "duplicate",
        "delete",
        "rewire",
        "branch",
        "prune",
        "passive",
        "differentiate",
    ] + (["recombine"] if donor else [])
    pool, seen = [], {genome_id(genome)}
    attempts = 0
    while len(pool) < count and attempts < count * 100:
        kind = (
            kinds[attempts % len(kinds)] if attempts < len(kinds) else rng.choice(kinds)
        )
        attempts += 1
        result, detail = _edit(genome, rng, kind, donor)
        validate_genome(result)
        key = genome_id(result)
        if key in seen:
            continue
        seen.add(key)
        pool.append({"id": key, "kind": kind, "description": detail, "genome": result})
    if len(pool) != count:
        raise RuntimeError("failed to generate requested unique candidate pool")
    return pool
