"""Replicated Jev-guided experiments, with measured diversity and request costs.

Replicates vary seeds while retaining the same physical and search settings.
Reports describe variation; they do not establish a guidance advantage.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from copy import deepcopy
from pathlib import Path

from .budgets import RequestBudget
from .guidance import require_credentials
from .search import CAPABILITIES, DEFAULTS, _configuration, _invariants, run_search


def _write(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def _spread(vectors):
    if not vectors:
        return {"count": 0, "dimensions": 0, "axis_range": [], "rms_radius": 0.0}
    dimensions = len(vectors[0])
    if any(len(v) != dimensions for v in vectors):
        raise ValueError("descriptor dimensions differ in saved run")
    axes = list(zip(*vectors))
    means = [statistics.fmean(axis) for axis in axes]
    variance = statistics.fmean(
        sum((x - m) ** 2 for x, m in zip(v, means)) for v in vectors
    )
    return {
        "count": len(vectors),
        "dimensions": dimensions,
        "axis_range": [max(axis) - min(axis) for axis in axes],
        "rms_radius": math.sqrt(variance),
    }


def _guidance_cost(records, pricing, cache_dir=None):
    # Attempts include paid requests whose selection or later physics failed.
    # A canonical cache file mirrors an attempt; it is never another request.
    calls, referenced = {}, set()
    cache_hits = ledger_requests = 0
    for record in records:
        audit = record.get("guidance", {})
        if audit.get("strategy") != "jev":
            continue
        cache_hits += bool(audit.get("cache_hit"))
        identity = (audit.get("request_hash"), audit.get("attempt"))
        referenced.add(identity)
        if not audit.get("cache_hit"):
            calls[identity] = {
                "usage": audit.get("usage"),
                "elapsed_seconds": audit.get("elapsed_seconds", 0.0),
                "error": None,
            }
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        attempted_hashes = set()
        for path in sorted((cache_dir / "attempts").glob("*.json")):
            record = json.loads(path.read_text())
            request_hash, attempt = record.get("request_hash"), record.get("attempt")
            if (
                not isinstance(request_hash, str)
                or type(attempt) is not int
                or attempt < 1
                or path.stem != f"{request_hash}-{attempt:06d}"
            ):
                raise ValueError(f"invalid guidance attempt ledger entry: {path.name}")
            attempted_hashes.add(request_hash)
            calls.pop((request_hash, None), None)
            response = record.get("response")
            calls[(request_hash, attempt)] = {
                "usage": response.get("usage") if isinstance(response, dict) else None,
                "elapsed_seconds": record.get("elapsed_seconds", 0.0),
                "error": record.get("error"),
            }
            ledger_requests += 1
        for path in sorted(cache_dir.glob("*.json")):
            record = json.loads(path.read_text())
            request_hash = record.get("request_hash")
            if not isinstance(request_hash, str) or request_hash != path.stem:
                raise ValueError(f"invalid guidance request ledger entry: {path.name}")
            if request_hash in attempted_hashes:
                continue
            response = record.get("response")
            calls[(request_hash, record.get("attempt"))] = {
                "usage": response.get("usage") if isinstance(response, dict) else None,
                "elapsed_seconds": record.get("elapsed_seconds", 0.0),
                "error": record.get("error"),
            }
            ledger_requests += 1
    usage = {"input_tokens": 0, "output_tokens": 0}
    unknown = 0
    for call in calls.values():
        measured = call.get("usage")
        if not isinstance(measured, dict) or any(
            type(measured.get(k)) is not int or measured[k] < 0 for k in usage
        ):
            unknown += 1
            continue
        for key in usage:
            usage[key] += measured[key]
    cost = None
    if not calls:
        cost = 0.0
    elif pricing is not None and not unknown:
        cost = (
            usage["input_tokens"] * pricing["input_per_million"]
            + usage["output_tokens"] * pricing["output_per_million"]
        ) / 1_000_000
    return {
        "requests": len(calls),
        "cache_hits": cache_hits,
        "request_ledger_source": "run-local attempts, canonical cache for older runs, completed evaluation audits",
        "ledger_requests": ledger_requests,
        "orphaned_requests": sum(
            identity not in referenced and (identity[0], None) not in referenced
            for identity in calls
        ),
        "requests_with_errors": sum(bool(c["error"]) for c in calls.values()),
        "requests_with_transport_errors": sum(
            bool(c["error"]) and c["usage"] is None for c in calls.values()
        ),
        "known_usage": usage,
        "requests_with_unknown_usage": unknown,
        "request_wall_seconds": sum(c["elapsed_seconds"] for c in calls.values()),
        "estimated_api_cost": cost,
        "pricing": pricing,
        "admission_accounting": RequestBudget(cache_dir).summary()
        if cache_dir is not None else None,
        "cost_note": "Request attempts include failed, interrupted or uncheckpointed batches; "
        "cache replays are not additional requests. A copied external cache would "
        "include its original usage. Cost requires supplied prices and complete "
        "recorded usage; provider billing remains authoritative.",
    }


def _metrics(path, summary, invocation_seconds, pricing):
    records = [
        json.loads(line)
        for line in (path / "evaluations.jsonl").read_text().splitlines()
        if line
    ]
    archives = json.loads((path / "archives.json").read_text())
    valid = [r for r in records if r["valid"]]
    views = {}
    for view, bins in archives.items():
        members = {r["id"]: r for peers in bins.values() for r in peers}
        views[view] = {
            "niches": len(bins),
            "members": len(members),
            "spread": _spread([r["descriptors"][view] for r in members.values()]),
        }
    timing = [r.get("timing", {}) for r in records]
    return {
        "evaluations": len(records),
        "valid": len(valid),
        "valid_fraction": len(valid) / max(1, len(records)),
        "archives": views,
        "capabilities": {
            k: {
                "max": max((r["capabilities"][k] for r in valid), default=None),
                "median": statistics.median([r["capabilities"][k] for r in valid])
                if valid
                else None,
            }
            for k in CAPABILITIES
        },
        "costs": {
            "search_wall_seconds_this_invocation": summary[
                "wall_seconds_this_invocation"
            ],
            "replicate_wall_seconds_this_invocation": invocation_seconds,
            "summed_evaluator_wall_seconds": sum(
                t.get("wall_seconds", 0.0) for t in timing
            ),
            "reported_simulated_seconds": sum(
                t.get("simulated_seconds", 0.0) for t in timing
            ),
            "guidance": _guidance_cost(records, pricing, path / "guidance"),
        },
        "guided": summary["guided"],
        "mutations": summary["mutations"],
        "run_directory": str(path),
    }


def replicate_jev(config: dict, out: Path, seeds=(0, 1, 2)) -> dict:
    """Run independent Jev-guided searches with equal evaluation limits.

    Optional guidance_pricing is {input_per_million, output_per_million, currency}.
    Supplied prices are descriptive; admission uses the pinned model's price.
    API caps apply to each seed's persisted ledger. Wall deadlines reset per
    invocation and are checked at work boundaries, without killing active work.
    Set resume=True to resume each existing run; unavailable guidance stops execution.
    """
    seeds = tuple(seeds)
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in seeds)
    ):
        raise ValueError("seeds must be unique nonnegative integers")
    common = deepcopy(config)
    pricing = common.pop("guidance_pricing", None)
    common = _configuration(common)
    require_credentials()
    if pricing is not None:
        if not isinstance(pricing, dict) or not isinstance(
            pricing.get("currency"), str
        ):
            raise ValueError(
                "guidance_pricing requires currency and per-million input/output prices"
            )
        for field in ("input_per_million", "output_per_million"):
            value = pricing.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"invalid guidance pricing {field}")
    out = Path(out)
    manifest_path = out / "replication_config.json"
    if common["resume"] and not manifest_path.exists():
        raise ValueError("resume requested but replication manifest is missing")
    if manifest_path.exists():
        if not common["resume"]:
            raise ValueError(
                "replication already exists; use resume or a new directory"
            )
        previous = json.loads(manifest_path.read_text())
        if (
            _invariants(previous["common_config"]) != _invariants(common)
            or previous["seeds"] != list(seeds)
            or previous["guidance_pricing"] != pricing
        ):
            raise ValueError("replication settings changed; use a new directory")
    manifest = {
        "schema": 2,
        "common_config": common,
        "strategy": "jev",
        "seeds": list(seeds),
        "guidance_pricing": pricing,
        "matching": "Same simulation settings, evaluation limit, candidate count, "
        "initial population and batch size. Independent seeds vary developmental "
        "programs, candidate pools, parent choices and assay perturbations.",
        "budget": {
            "evaluations_per_run": common.get("evaluations", DEFAULTS["evaluations"]),
            "wall_time_limit_enforced": False,
            "wall_time_admission_limit_enforced": common["max_wall_seconds"] is not None,
            "max_wall_seconds_per_invocation": common["max_wall_seconds"],
            "api_request_limit_enforced": common["max_api_requests"] is not None,
            "max_api_requests_per_run": common["max_api_requests"],
            "api_cost_limit_enforced": common["max_api_cost_usd"] is not None,
            "max_api_cost_usd_per_run": common["max_api_cost_usd"],
            "scope": "API limits cover each seed's full persisted attempt ledger; "
            "wall time admits work at boundaries per invocation, with possible "
            "in-flight overruns. Replicates do not share a dollar cap.",
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    _write(manifest_path, manifest)
    runs = []
    for seed in seeds:
        path = out / f"seed-{seed}"
        run_config = {
            **common,
            "seed": seed,
            "resume": common["resume"] and (path / "checkpoint.json").exists(),
        }
        started = time.perf_counter()
        summary = run_search(run_config, path)
        metrics = _metrics(path, summary, time.perf_counter() - started, pricing)
        runs.append({"strategy": "jev", "seed": seed, **metrics})
        _write(out / "runs.json", runs)

    def describe(values):
        return {
            "mean": statistics.fmean(values),
            "sample_standard_deviation": statistics.stdev(values)
            if len(values) > 1
            else None,
            "values": values,
        }

    aggregates = {
        "replicates": len(runs),
        "valid_fraction": describe([r["valid_fraction"] for r in runs]),
        "wall_seconds": describe(
            [r["costs"]["replicate_wall_seconds_this_invocation"] for r in runs]
        ),
        "archives": {
            view: {
                "niches": describe([r["archives"][view]["niches"] for r in runs]),
                "rms_radius": describe(
                    [r["archives"][view]["spread"]["rms_radius"] for r in runs]
                ),
            }
            for view in ("structure", "behavior")
        },
    }
    report = {
        "schema": 2,
        "design": manifest,
        "runs": runs,
        "aggregates": aggregates,
        "interpretation": "Descriptive results only. Archive occupancy depends on descriptor "
        "scales and niche width. Spread is computed in those recorded descriptor "
        "units. Evaluation budgets are matched; wall time and API cost are "
        "measured separately. No unguided comparison or guidance advantage is measured.",
    }
    _write(out / "replication.json", report)
    return report
