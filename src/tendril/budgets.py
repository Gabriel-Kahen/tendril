"""Run-local request accounting and admission limits, including interrupted calls.

Prices/context are pinned from https://docs.typesafe.ai/models (2026-09-27).
The wall deadline admits work at boundaries; it never kills an in-flight batch.
One search process owns a run directory, including its attempt ledger.
"""

from __future__ import annotations

import json
import math
import time
from decimal import Decimal
from pathlib import Path

from .guidance import GuidanceError

PINNED_MODEL = "jev-1.13.0"
MAX_INPUT_TOKENS = 65536
PRICING = {"input_per_million": 0.042, "output_per_million": 0.0, "currency": "USD"}
RESERVED_USD = float(Decimal(MAX_INPUT_TOKENS) * Decimal("0.042") / 1_000_000)
LIMITS = ("max_api_requests", "max_api_cost_usd", "max_wall_seconds")


def validate_limits(config):
    for name in LIMITS:
        value = config.get(name)
        if value is None:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or (name == "max_api_requests" and type(value) is not int)
        ):
            raise ValueError(f"{name} must be nonnegative and finite (integer for requests)")


def ledger_records(cache_dir):
    """Read each attempt once; canonical caches cover pre-attempt-ledger runs."""
    cache_dir = Path(cache_dir)
    records, attempted = [], set()
    try:
        for path in sorted((cache_dir / "attempts").glob("*.json")):
            record = json.loads(path.read_text())
            digest, attempt = record.get("request_hash"), record.get("attempt")
            if (
                not isinstance(digest, str)
                or type(attempt) is not int
                or attempt < 1
                or path.stem != f"{digest}-{attempt:06d}"
            ):
                raise ValueError("invalid attempt identity")
            attempted.add(digest)
            records.append(record)
        for path in sorted(cache_dir.glob("*.json")):
            record = json.loads(path.read_text())
            digest = record.get("request_hash")
            if not isinstance(digest, str) or digest != path.stem:
                raise ValueError("invalid cache identity")
            if digest not in attempted:
                records.append(record)
    except (OSError, ValueError, TypeError, AttributeError):
        raise GuidanceError("guidance budget ledger is malformed; repair before resuming") from None
    return records


def _cost(record):
    request, response = record.get("request"), record.get("response")
    if not isinstance(request, dict) or request.get("model") != PINNED_MODEL:
        return None, None
    usage = response.get("usage") if isinstance(response, dict) else None
    if (
        record.get("error") != "request_in_progress"
        and isinstance(response, dict)
        and response.get("model") == PINNED_MODEL
        and isinstance(usage, dict)
        and all(type(usage.get(k)) is int and 0 <= usage[k] <= MAX_INPUT_TOKENS
                for k in ("input_tokens", "output_tokens"))
    ):
        measured = Decimal(usage["input_tokens"]) * Decimal("0.042") / 1_000_000
        return measured, measured
    # Missing, malformed or unresolved usage never restores reserved dollars.
    return None, Decimal(str(RESERVED_USD))


class RequestBudget:
    def __init__(self, cache_dir, max_api_requests=None, max_api_cost_usd=None,
                 max_wall_seconds=None):
        self.cache_dir = Path(cache_dir)
        self.limits = dict(zip(LIMITS, (max_api_requests, max_api_cost_usd, max_wall_seconds)))
        validate_limits(self.limits)
        self.started = time.perf_counter()

    def check_time(self):
        limit = self.limits["max_wall_seconds"]
        if limit is not None and time.perf_counter() - self.started >= limit:
            raise GuidanceError("wall-time admission limit reached; resume starts a new invocation deadline")

    def summary(self):
        records = ledger_records(self.cache_dir)
        costs = [_cost(record) for record in records]
        measured = sum((cost for cost, _ in costs if cost is not None), Decimal(0))
        upper = None if any(cap is None for _, cap in costs) else sum(
            (cap for _, cap in costs), Decimal(0)
        )
        return {
            "limits": self.limits,
            "requests": len(records),
            "known_usage_cost_usd": float(measured),
            "requests_with_unknown_cost": sum(cost is None for cost, _ in costs),
            "conservative_api_cost_usd": float(upper) if upper is not None else None,
            "pricing": {"model": PINNED_MODEL, **PRICING},
            "wall_limit_scope": "per invocation, checked before candidate requests and simulation batches; in-flight work may overrun",
            "cost_note": "Unknown or pending pinned-model attempts consume the full context reservation; provider billing remains authoritative.",
        }

    def reservation(self, body):
        """Check ledger before transport; caller must persist this before sending."""
        self.check_time()
        totals = self.summary()
        limit = self.limits["max_api_requests"]
        if limit is not None and totals["requests"] >= limit:
            raise GuidanceError("API request limit reached; increase max_api_requests to resume")
        supported = body.get("model") == PINNED_MODEL
        limit = self.limits["max_api_cost_usd"]
        if limit is not None:
            if not supported or totals["conservative_api_cost_usd"] is None:
                raise GuidanceError("API dollar limit requires pinned jev-1.13.0 pricing for every ledger attempt")
            used = Decimal(str(totals["conservative_api_cost_usd"]))
            if used + Decimal(str(RESERVED_USD)) > Decimal(str(limit)):
                raise GuidanceError("API dollar limit reached; increase max_api_cost_usd to resume")
        return {
            "reserved_usd": RESERVED_USD if supported else None,
            "max_input_tokens": MAX_INPUT_TOKENS if supported else None,
            "pricing": {"model": PINNED_MODEL, **PRICING} if supported else None,
        }
