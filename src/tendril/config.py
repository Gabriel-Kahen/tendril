"""Explicit, replayable limits; units are metres, kilograms, seconds, joules."""

import math
from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class SimulationConfig:
    timestep: float = 0.0005
    control_interval: float = 0.02
    growth_interval: float = 0.1
    juvenile_seconds: float = 3.0
    assay_seconds: float = 2.0
    frame_interval: float = 0.04
    max_segments: int = 32
    max_tissues: int = 4
    max_mass: float = 2.0
    energy_budget: float = 20.0
    growth_cost_per_kg: float = 5.0
    muscle_force: float = 3.0
    muscle_power: float = 0.3
    muscle_speed: float = 1.0
    activation_ramp: float = 0.2
    max_joint_speed: float = 100.0
    max_penetration: float = 0.008
    max_extent: float = 3.0
    density: float = 600.0
    tissue_young: float = 50000.0
    tissue_poisson: float = 0.3
    tissue_spacing: float = 0.018
    tissue_mass: float = 0.04
    max_tissue_strain: float = 0.25
    min_tissue_volume_ratio: float = 0.5
    muscle_min_fraction: float = 0.35
    seed_height: float = 0.16
    push_impulse: float = 0.02
    load_force: float = 0.1
    signal_diffusion: float = 0.2
    signal_decay: float = 0.1

    @classmethod
    def from_dict(cls, raw=None):
        raw = raw or {}
        unknown = set(raw) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown simulation settings: {sorted(unknown)}")
        value = cls(**raw)
        for key, number in asdict(value).items():
            if (
                not isinstance(number, (int, float))
                or not math.isfinite(number)
                or number < 0
            ):
                raise ValueError(f"Invalid nonnegative setting {key}: {number}")
        for key in (
            "timestep",
            "control_interval",
            "growth_interval",
            "frame_interval",
            "assay_seconds",
            "max_mass",
            "density",
            "activation_ramp",
        ):
            if getattr(value, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if (
            value.control_interval < value.timestep
            or value.growth_interval < value.control_interval
        ):
            raise ValueError(
                "Require physics timestep <= control interval <= growth interval"
            )
        if not 0 <= value.tissue_poisson < 0.5:
            raise ValueError("tissue_poisson must be in [0, .5)")
        if not isinstance(value.max_segments, int) or value.max_segments < 1:
            raise ValueError("max_segments must be a positive integer")
        if not isinstance(value.max_tissues, int):
            raise ValueError("max_tissues must be an integer")
        return value

    def to_dict(self):
        return asdict(self)
