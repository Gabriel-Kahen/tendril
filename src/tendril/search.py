"""Replayable development/behavior archives with local capability competition.

No global fitness ranking exists. Structural niches preserve developmental
diversity; behavior niches keep local Pareto alternatives. When crowded, the
least distinctive descriptor is removed. Parent sampling alternates descriptor
views and samples niches equally.
"""

from __future__ import annotations

import json
import math
import platform
import random
import time
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

from .budgets import LIMITS, PINNED_MODEL, RequestBudget, validate_limits
from .genome import candidates, canonical, genome_id, seed_genome, validate_genome
from .guidance import GuidanceError, require_credentials, select_jev

CAPABILITIES = ("support", "motion", "recovery", "manipulation", "efficiency")
DEFAULTS = dict(
    seed=0,
    evaluations=32,
    initial_population=4,
    candidate_count=32,
    batch_size=1,
    workers=1,
    strategy="jev",
    niche_width=0.25,
    niche_capacity=4,
    novelty_neighbors=5,
    model=PINNED_MODEL,
    max_api_requests=None,
    max_api_cost_usd=None,
    max_wall_seconds=None,
    simulation={},
    resume=False,
)


def _save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def _distance(a, b):
    if len(a) != len(b):
        raise ValueError("descriptor dimensions changed within a run")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _dominates(a, b):
    return all(a.get(k, 0) >= b.get(k, 0) for k in CAPABILITIES) and any(
        a.get(k, 0) > b.get(k, 0) for k in CAPABILITIES
    )


class Archive:
    """Fixed-width descriptor niches; widths/scales are experimental parameters."""

    def __init__(self, view, width=0.25, capacity=4, neighbors=5, bins=None):
        if view not in ("structure", "behavior") or width <= 0 or capacity < 2:
            raise ValueError(
                "archive requires known view, positive width, capacity >= 2"
            )
        self.view, self.width, self.capacity, self.neighbors = (
            view,
            width,
            capacity,
            neighbors,
        )
        self.bins = bins or {}

    @property
    def members(self):
        return [record for records in self.bins.values() for record in records]

    def key(self, record):
        return ",".join(
            str(math.floor(v / self.width)) for v in record["descriptors"][self.view]
        )

    def novelty(self, record):
        distances = sorted(
            _distance(record["descriptors"][self.view], m["descriptors"][self.view])
            for m in self.members
        )
        return (
            sum(distances[: self.neighbors]) / min(len(distances), self.neighbors)
            if distances
            else 0.0
        )

    def add(self, record):
        if not record["valid"]:
            return False
        key = self.key(record)
        peers = self.bins.setdefault(key, [])
        if any(p["id"] == record["id"] for p in peers):
            return False
        # Keep the original structural pioneer even if all its muscles are passive.
        protected = peers[:1] if self.view == "structure" else []
        competitors = peers[len(protected) :]
        if self.view == "behavior" and any(
            _dominates(p["capabilities"], record["capabilities"]) for p in competitors
        ):
            return False
        retained = protected + [
            p
            for p in competitors
            if self.view == "structure"
            or not _dominates(record["capabilities"], p["capabilities"])
        ]
        retained.append(record)
        while len(retained) > self.capacity:
            removable = range(len(protected), len(retained))
            # Preserve extremes/isolated forms within the niche, without a global objective.
            victim = min(
                removable,
                key=lambda i: (
                    min(
                        _distance(
                            retained[i]["descriptors"][self.view],
                            other["descriptors"][self.view],
                        )
                        for j, other in enumerate(retained)
                        if i != j
                    ),
                    -retained[i]["evaluation"],
                ),
            )
            retained.pop(victim)
        self.bins[key] = retained
        return any(p["id"] == record["id"] for p in retained)

    def sample(self, rng):
        key = rng.choice(sorted(self.bins))
        return rng.choice(self.bins[key])


def _default_evaluate(genome, config, seed, out):
    from .simulation import evaluate

    return evaluate(genome, config, seed, out=out)


def _evaluate_job(job):
    """Top-level picklable worker; workers never select parents or touch archives."""
    genome, config, seed, path = job
    return _default_evaluate(genome, config, seed, Path(path))


def _check_result(result):
    if not isinstance(result, dict) or not isinstance(result.get("valid"), bool):
        raise ValueError("evaluator must return a validity decision")
    if not isinstance(result.get("reasons"), list):
        raise ValueError("evaluator must return reasons")
    if result["valid"]:
        for view in ("structure", "behavior"):
            values = result.get("descriptors", {}).get(view)
            if (
                not isinstance(values, list)
                or not values
                or any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                    for v in values
                )
            ):
                raise ValueError(
                    f"evaluator must return finite {view} descriptor vector"
                )
        for key in CAPABILITIES:
            value = result.get("capabilities", {}).get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ValueError(f"evaluator must return finite capability {key}")
    canonical(result)


def _configuration(config):
    result = deepcopy(DEFAULTS)
    result.update(config)
    validate_limits(result)
    if result["max_api_cost_usd"] is not None and result["model"] != PINNED_MODEL:
        raise ValueError("max_api_cost_usd requires pinned model jev-1.13.0")
    for name in (
        "evaluations",
        "initial_population",
        "candidate_count",
        "batch_size",
        "workers",
        "niche_capacity",
        "novelty_neighbors",
    ):
        if (
            isinstance(result[name], bool)
            or not isinstance(result[name], int)
            or result[name] < 1
        ):
            raise ValueError(f"{name} must be a positive integer")
    if result["niche_capacity"] < 2 or result["candidate_count"] > 255:
        raise ValueError("niche_capacity >= 2 and candidate_count <= 255 are required")
    if result["strategy"] != "jev":
        raise ValueError("strategy must be jev; unguided search is not supported")
    if "guided_fraction" in result:
        if (
            isinstance(result["guided_fraction"], bool)
            or result["guided_fraction"] != 1
        ):
            raise ValueError("guided_fraction must be 1; every candidate requires Jev")
        result.pop("guided_fraction")
    if not math.isfinite(result["niche_width"]) or result["niche_width"] <= 0:
        raise ValueError("niche_width must be positive and finite")
    if any("key" in key.lower() or "token" in key.lower() for key in result):
        raise ValueError(
            "credentials do not belong in persisted experiment configuration"
        )
    return result


def _invariants(config):
    return {
        k: v for k, v in config.items()
        if k not in ("resume", "evaluations", "workers", *LIMITS)
    }


def _restore_random_state(value):
    return tuple(_restore_random_state(v) if isinstance(v, list) else v for v in value)


def _versions():
    from .simulation import source_version

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: version(name) for name in ("mujoco", "numpy", "scipy")},
        "source_sha256": source_version(),
        "genome_schema": 1,
        "descriptor_schema": 1,
        "search_schema": 2,
    }


def run_search(config: dict, out: Path, evaluator=None) -> dict:
    """Run/resume a seeded search; an evaluator returns measured rollout summaries.

    Evaluation limits are total including previous checkpoints. Results are consumed
    in submission order, so OS worker scheduling cannot change archive decisions.
    Parallel generations use batch_size; every evaluated program is selected by Jev.
    """
    config = _configuration(config)
    require_credentials()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoint.json"
    rng = random.Random(config["seed"])
    records, history, guided, mutation_count = [], {}, 0, 0
    archives = {
        view: Archive(
            view,
            config["niche_width"],
            config["niche_capacity"],
            config["novelty_neighbors"],
        )
        for view in ("structure", "behavior")
    }
    if config["resume"]:
        if not checkpoint.exists():
            raise ValueError("resume requested but checkpoint is missing")
        version_path = out / "versions.json"
        if (
            not version_path.exists()
            or json.loads(version_path.read_text()) != _versions()
        ):
            raise ValueError(
                "resume source, engine, runtime, or schema versions differ from the original run"
            )
        previous = json.loads(checkpoint.read_text())
        if _invariants(previous["config"]) != _invariants(config):
            raise ValueError("resume configuration differs from checkpoint")
        rng.setstate(_restore_random_state(previous["random_state"]))
        records, history = previous["records"], previous["history"]
        guided, mutation_count = previous["guided"], previous["mutation_count"]
        for view in archives:
            archives[view].bins = previous["archives"][view]
        # Rebuild this derived log from the atomic checkpoint after an interrupted write.
        (out / "evaluations.jsonl").write_text(
            "".join(canonical(r) + "\n" for r in records)
        )
    elif checkpoint.exists() or (out / "evaluations.jsonl").exists():
        raise ValueError("output already contains a run; use resume or a new directory")
    _save(out / "config.json", config)
    if not config["resume"]:
        _save(out / "versions.json", _versions())

    def save_checkpoint():
        _save(
            checkpoint,
            {
                "config": config,
                "random_state": rng.getstate(),
                "records": records,
                "history": history,
                "guided": guided,
                "mutation_count": mutation_count,
                "archives": {view: archive.bins for view, archive in archives.items()},
            },
        )

    # Even the first failed Jev request leaves a resumable pre-selection state.
    if not config["resume"]:
        save_checkpoint()
    started = time.perf_counter()
    budget = RequestBudget(out / "guidance", **{key: config[key] for key in LIMITS})
    status, stop_reason = "failed", None

    def save_summary():
        summary = {
            "evaluations": len(records),
            "valid": sum(r["valid"] for r in records),
            "guided": len(records),
            "mutations": len(records),
            "niches": {view: len(a.bins) for view, a in archives.items()},
            "members": {view: len(a.members) for view, a in archives.items()},
            "strategy": config["strategy"],
            "status": status,
            "stop_reason": stop_reason,
            "budget": budget.summary(),
            "wall_seconds_this_invocation": time.perf_counter() - started,
            "checkpoint": str(checkpoint),
            "measured_guidance_advantage": None,
        }
        _save(out / "summary.json", summary)
        return summary

    executor = (
        ProcessPoolExecutor(config["workers"])
        if config["workers"] > 1 and evaluator is None
        else None
    )
    try:
        while len(records) < config["evaluations"]:
            budget.check_time()
            jobs, proposed = [], []
            count = min(config["batch_size"], config["evaluations"] - len(records))
            for offset in range(count):
                budget.check_time()
                index = len(records) + offset
                proposal_seed, rollout_seed = rng.randrange(2**32), rng.randrange(2**32)
                view = ("structure", "behavior")[index % 2]
                parent, donor = None, None
                if index < config["initial_population"] or not archives[view].members:
                    base = seed_genome(proposal_seed)
                    context = {"genome": base}
                    pool = candidates(base, proposal_seed, config["candidate_count"])
                else:
                    parent = archives[view].sample(rng)
                    donor = archives[view].sample(rng)
                    pool = candidates(
                        parent["genome"],
                        proposal_seed,
                        config["candidate_count"],
                        donor["genome"],
                    )
                    context = {
                        **parent,
                        "lineage": {
                            key: parent.get(key)
                            for key in ("id", "parent", "donor", "edit", "evaluation")
                        },
                    }
                # History is observed archive admission, never a survival verdict by Jev.
                context["mutation_history"] = history
                # Completed observations describe these trials, not untested edits.
                context["recent_trials"] = [
                    {key: record[key] for key in (
                        "id", "edit", "valid", "reasons", "juvenile",
                        "descriptors", "capabilities",
                    ) if key in record}
                    for record in records[-8:]
                ]
                selected, audit = select_jev(
                    pool, context, proposal_seed, out / "guidance", config["model"],
                    request_budget=budget,
                )
                guided += 1
                mutation_count += 1
                genome = selected["genome"]
                validate_genome(genome)
                path = out / "specimens" / f"{index:06d}"
                path.mkdir(parents=True, exist_ok=True)
                lineage = {
                    "evaluation": index,
                    "proposal_seed": proposal_seed,
                    "seed": rollout_seed,
                    "parent": parent["id"] if parent else None,
                    "donor": donor["id"] if donor else None,
                    "selection_view": view,
                    "guidance": audit,
                    "candidate_ids": [c["id"] for c in pool],
                    "edit": next(
                        (
                            {k: c[k] for k in ("id", "kind", "description")}
                            for c in pool
                            if c["genome"] == genome
                        ),
                        None,
                    ),
                }
                _save(
                    path / "proposal.json",
                    {"lineage": lineage, "candidates": pool, "genome": genome},
                )
                proposed.append((genome, lineage, path))
                jobs.append((genome, config["simulation"], rollout_seed, str(path)))
            budget.check_time()
            results = (
                list(executor.map(_evaluate_job, jobs))
                if executor
                else [
                    (evaluator or _default_evaluate)(g, c, s, out=Path(p))
                    for g, c, s, p in jobs
                ]
            )
            for (genome, lineage, path), result in zip(proposed, results):
                _check_result(result)
                result = deepcopy(result)
                result.update(lineage)
                result["genome"] = genome
                result["id"] = f"{lineage['evaluation']:06d}-{genome_id(genome)}"
                result["novelty"] = {
                    view: archive.novelty(result) if result["valid"] else None
                    for view, archive in archives.items()
                }
                result["admissions"] = {
                    view: archive.add(result) for view, archive in archives.items()
                }
                kind = lineage["edit"]["kind"]
                score = history.setdefault(kind, {"attempts": 0, "admissions": 0})
                score["attempts"] += 1
                score["admissions"] += int(any(result["admissions"].values()))
                _save(path / "result.json", result)
                records.append(result)
            save_checkpoint()
            with (out / "evaluations.jsonl").open("a") as stream:
                for record in records[-len(results) :]:
                    stream.write(canonical(record) + "\n")
            _save(out / "archives.json", {view: a.bins for view, a in archives.items()})
        status = "complete"
    except GuidanceError as exc:
        status, stop_reason = "stopped", str(exc)
        save_summary()
        raise
    finally:
        if executor:
            executor.shutdown(wait=True, cancel_futures=True)
    return save_summary()
