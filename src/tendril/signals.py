"""Bounded regulatory dynamics on the body's undirected connection graph."""

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=128)
def _propagators(count, edges, seconds, diffusion, decay):
    """Exact source/decay/diffusion propagation between topology edits."""
    laplacian = np.zeros((count, count))
    for a, b in edges:
        laplacian[a, a] += 1
        laplacian[b, b] += 1
        laplacian[a, b] -= 1
        laplacian[b, a] -= 1
    eigenvalues, basis = np.linalg.eigh(laplacian)
    tolerance = 1e-12 * max(1.0, float(np.max(eigenvalues)))
    eigenvalues[np.abs(eigenvalues) < tolerance] = 0.0
    rates = decay + diffusion * np.maximum(eigenvalues, 0)
    attenuation = np.exp(-rates * seconds)
    source = np.full(count, seconds)
    nonzero = rates > 0
    source[nonzero] = -np.expm1(-rates[nonzero] * seconds) / rates[nonzero]
    return (basis * attenuation) @ basis.T, (basis * source) @ basis.T


def advance_signals(world, seconds):
    """Advance signed local state in elapsed physical time, independently of growth.

    Tree joints and accepted loop connections conduct signals equally. These are
    dimensionless regulatory variables, not a material or energy reservoir.
    Saturation is applied at each physics step; it is not a conservation law.
    """
    if not np.isfinite(seconds) or seconds < 0:
        raise ValueError("signal elapsed time must be finite and nonnegative")
    if seconds == 0:
        return
    sites = world.segments
    indices = {site.id: index for index, site in enumerate(sites)}
    edges = set()
    for site in sites:
        if site.parent is not None:
            a, b = indices[site.id], indices[site.parent]
            edges.add((a, b) if a < b else (b, a))
    for link in world.links:
        a, b = indices[link.a], indices[link.b]
        edges.add((a, b) if a < b else (b, a))
    propagation, source = _propagators(
        len(sites),
        tuple(sorted(edges)),
        seconds,
        world.config.signal_diffusion,
        world.config.signal_decay,
    )
    old = np.array([site.signal for site in sites])
    emission = np.array([world.modules[site.module]["signal_emit"] for site in sites])
    updated = (propagation @ old + source @ emission).clip(-5, 5)
    for site, value in zip(sites, updated):
        site.signal = float(value)
