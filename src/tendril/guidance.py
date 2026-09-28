"""Required typed Jev edit selection; simulation remains the physical authority.

HTTP contract: https://docs.typesafe.ai/api and /primitives/choice (2026-09-23).
No call occurs merely by importing this module. Keys are read only from the
process environment, never from experiment configuration or cached requests.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .genome import canonical

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.13.0"


class GuidanceError(ValueError):
    """Jev could not provide a legal choice; no rollout may replace it."""


def require_credentials():
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        raise GuidanceError(
            "Jev requires TYPESAFE_API_KEY; no unguided fallback exists"
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the authorization header to a redirected destination.
        return None


def _post(body: dict, timeout: float):
    key = os.environ["TYPESAFE_API_KEY"]
    request = Request(
        ENDPOINT,
        data=canonical(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        return json.loads(response.read())


def _safe_json(value):
    serialized = canonical(value)
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        serialized = serialized.replace(key, "[REDACTED]")
    return serialized


def _save_attempt(record, attempt_path, cache_path):
    serialized = _safe_json(record)
    for target in (attempt_path, cache_path):
        temporary = target.with_suffix(".tmp")
        temporary.write_text(serialized)
        temporary.replace(target)


def _validate_response(response, options):
    if not isinstance(response, dict) or not isinstance(response.get("model"), str):
        raise ValueError("missing resolved model")
    answer = response.get("answers", {}).get("edit", {})
    if answer.get("type") != "choice" or answer.get("choice") not in options:
        raise ValueError("response did not choose a legal edit")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(options):
        raise ValueError("probabilities must cover exactly the candidate pool")
    values = list(probabilities.values()) + [answer.get("confidence")]
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not 0 <= v <= 1
        for v in values
    ):
        raise ValueError("invalid probabilities or confidence")
    mass = math.fsum(probabilities.values())
    if abs(mass - 1.0) > 1e-4:
        # Live Jev replies can round each probability to two decimal places.
        # Accept only distributions compatible with rounding a unit total.
        rounded = all(abs(p - round(p, 2)) < 1e-12 for p in probabilities.values())
        lower = math.fsum(max(0.0, p - 0.005) for p in probabilities.values())
        upper = math.fsum(min(1.0, p + 0.005) for p in probabilities.values())
        if not rounded or not lower - 1e-12 <= 1.0 <= upper + 1e-12:
            raise ValueError("probabilities must sum to one within reported precision")
    if probabilities[answer["choice"]] + 1e-8 < max(probabilities.values()):
        raise ValueError("choice is not a highest-probability option")
    return answer["choice"]


def select_jev(
    pool: list[dict],
    parent: dict,
    seed: int,
    cache_dir: Path,
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
    transport=None,
    request_budget=None,
) -> tuple[dict, dict]:
    """Select a legal edit or raise GuidanceError, preserving every request attempt.

    Successful decisions are reused. Failed attempts can be retried on resume,
    with their audit records retained. A custom transport supports offline tests.
    Error messages contain only local classifications, never remote error text.
    The seed argument is retained for caller compatibility; it cannot select edits.
    """
    if transport is None:
        require_credentials()
    if not 1 <= len(pool) <= 255 or len({c["id"] for c in pool}) != len(pool):
        raise ValueError("Jev needs 1–255 unique candidate IDs")
    body = {
        "model": model,
        "state": {
            "parent": {
                k: parent[k]
                for k in (
                    "genome",
                    "descriptors",
                    "capabilities",
                    "accounting",
                    "reasons",
                    "lineage",
                    "mutation_history",
                    "recent_trials",
                )
                if k in parent
            }
        },
        "questions": {
            "edit": {
                "type": "choice",
                "instructions": "Choose one candidate worth physically testing. "
                "Prioritize novelty over immediate performance or usefulness.\n\n"
                "Value stepping stones: simple, passive, or unfinished forms may open "
                "new directions. Favor opportunities to discover something different "
                "over polishing what already works.\n\n"
                "Judge novelty from the evidence provided. Simulation will determine "
                "physical validity.\n\n"
                "Select one supplied candidate ID.",
                "criteria": {
                    c["id"]: {
                        "kind": c["kind"],
                        "edit": c["description"],
                        "genome": c["genome"],
                    }
                    for c in pool
                },
            }
        },
    }
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(canonical(body).encode()).hexdigest()
    path = cache_dir / f"{digest}.json"
    options = {c["id"]: c for c in pool}
    record = None
    cached = False
    if path.exists():
        try:
            record = json.loads(path.read_text())
            if record.get("request") != body:
                raise GuidanceError("guidance cache request mismatch")
            if not record.get("error"):
                _validate_response(record.get("response"), options)
                cached = True
        except (TypeError, AttributeError, json.JSONDecodeError):
            raise GuidanceError("guidance cache is malformed") from None
        except ValueError as exc:
            if isinstance(exc, GuidanceError):
                raise
            # An old invalid reply is evidence of failure, never a decision.
    if not cached:
        attempts = cache_dir / "attempts"
        attempts.mkdir(exist_ok=True)
        attempt = 1 + len(list(attempts.glob(f"{digest}-*.json")))
        reservation = request_budget.reservation(body) if request_budget else None
        record = {
            "request_hash": digest,
            "attempt": attempt,
            "request": body,
            "endpoint": ENDPOINT,
            "response": None,
            "error": "request_in_progress",
            "elapsed_seconds": 0.0,
            "reservation": reservation,
        }
        attempt_path = attempts / f"{digest}-{attempt:06d}.json"
        # A crash after dispatch must still leave a potentially billed attempt.
        _save_attempt(record, attempt_path, path)
        started = time.perf_counter()
        try:
            record["response"] = (transport or _post)(body, timeout)
            record["error"] = None
            try:
                record["response"] = json.loads(_safe_json(record["response"]))
            except (ValueError, TypeError):
                # Invalid JSON (including NaN) must not prevent the failure audit.
                record["response"] = None
                record["response_not_json"] = True
            try:
                _validate_response(record["response"], options)
            except (ValueError, TypeError, AttributeError):
                record["error"] = "invalid_response"
        except HTTPError as exc:
            record["error"] = f"HTTP {exc.code}"
        except Exception as exc:
            # Remote exceptions can include credentials or bodies in their text.
            record["error"] = type(exc).__name__
        record["elapsed_seconds"] = time.perf_counter() - started
        _save_attempt(record, attempt_path, path)
    if record["error"]:
        raise GuidanceError(
            f"Jev selection stopped ({record['error']}); "
            "resume retries this request without an unguided fallback"
        )
    selected = _validate_response(record["response"], options)
    response = record["response"]
    audit = {
        "strategy": "jev",
        "request_hash": digest,
        "attempt": record.get("attempt", 1),
        "cache_hit": cached,
        "requested_model": model,
        "resolved_model": response.get("model"),
        "usage": response.get("usage"),
        "elapsed_seconds": record["elapsed_seconds"],
        "selected": selected,
        "price": None,
        "probability_sum": math.fsum(response["answers"]["edit"]["probabilities"].values()),
    }
    return options[selected], audit
