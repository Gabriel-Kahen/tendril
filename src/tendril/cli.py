"""Explicit commands for experiments, verification, replay, and inspection."""

import argparse
import json
import sys
from pathlib import Path

from .genome import seed_genome
from .simulation import evaluate, write_json


def load(path):
    return json.loads(Path(path).read_text()) if path else {}


def parser():
    cli = argparse.ArgumentParser(prog="tendril", description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="write a reproducible inherited program")
    seed.add_argument("--seed", type=int, default=0)
    seed.add_argument("--out", type=Path, required=True)
    seed.add_argument("--tissue", action="store_true")
    roll = commands.add_parser(
        "run", help="develop one organism and run independent adult assays"
    )
    roll.add_argument("--genome", type=Path)
    roll.add_argument("--config", type=Path)
    roll.add_argument("--seed", type=int, default=0)
    roll.add_argument("--out", type=Path, required=True)
    evolve = commands.add_parser(
        "evolve", help="run or resume Jev-guided diversity-preserving evolution"
    )
    evolve.add_argument("--config", type=Path, required=True)
    evolve.add_argument("--out", type=Path, required=True)
    evolve.add_argument("--resume", action="store_true")
    evolve.add_argument("--evaluations", type=int)
    evolve.add_argument(
        "--key-file",
        type=Path,
        help="private API key file (default: ~/.config/tendril/typesafe.key); "
        "TYPESAFE_API_KEY takes precedence",
    )
    replicate = commands.add_parser(
        "replicate", help="run independent Jev-guided experiments across seeds"
    )
    replicate.add_argument("--config", type=Path, required=True)
    replicate.add_argument("--out", type=Path, required=True)
    replicate.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    replicate.add_argument(
        "--key-file",
        type=Path,
        help="private API key file (default: ~/.config/tendril/typesafe.key); "
        "TYPESAFE_API_KEY takes precedence",
    )
    verify = commands.add_parser(
        "verify", help="replay, timestep-refine, and perturb a saved specimen"
    )
    verify.add_argument("specimen", type=Path)
    verify.add_argument("--out", type=Path, required=True)
    view = commands.add_parser(
        "gallery", help="serve an offline 3D gallery of saved experiments"
    )
    view.add_argument("directory", type=Path)
    view.add_argument("--port", type=int, default=8765)
    view.add_argument("--host", default="127.0.0.1")
    native = commands.add_parser(
        "inspect", help="open saved adult model in MuJoCo native viewer"
    )
    native.add_argument("specimen", type=Path)
    return cli


def verification(specimen, out):
    import numpy as np

    original = load(specimen / "result.json")
    config = original["config"]
    genome = original["genome"]
    out.mkdir(parents=True, exist_ok=True)
    reports = {}
    variants = [
        ("replay", config, original["seed"]),
        (
            "half-timestep",
            {**config, "timestep": config["timestep"] / 2},
            original["seed"],
        ),
        ("perturbation", config, original["seed"] + 100003),
    ]
    for name, c, seed in variants:
        result = evaluate(genome, c, seed, out / name)
        reports[name] = {
            "valid": result["valid"],
            "reasons": result["reasons"],
            "capabilities": result["capabilities"],
            "capability_delta": {
                k: result["capabilities"][k] - v
                for k, v in original["capabilities"].items()
            },
            "same_structure": np.allclose(
                result["descriptors"]["structure"],
                original["descriptors"]["structure"],
                atol=1e-10,
            ),
        }
    reports["replay"]["same_capabilities"] = all(
        abs(v) < 1e-10 for v in reports["replay"]["capability_delta"].values()
    )
    report = {
        "specimen": str(specimen),
        "variants": reports,
        "note": "Timestep and perturbation differences are reported, not automatically declared robust.",
    }
    write_json(out / "verification.json", report)
    return report


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "seed":
            genome = seed_genome(args.seed)
            if args.tissue:
                genome["modules"][0]["tissue"] = True
            args.out.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.out, genome)
            result = {"genome": str(args.out)}
        elif args.command == "run":
            if (args.out / "result.json").exists():
                raise ValueError(
                    "specimen already exists; choose a new output directory"
                )
            result = evaluate(
                load(args.genome) if args.genome else seed_genome(args.seed),
                load(args.config),
                args.seed,
                args.out,
            )
            result = {
                k: result[k]
                for k in ("valid", "reasons", "juvenile", "capabilities", "timing")
            }
        elif args.command == "evolve":
            from .credentials import load_cli_credentials
            from .search import run_search

            load_cli_credentials(args.key_file)
            config = load(args.config)
            if args.resume:
                config["resume"] = True
            if args.evaluations is not None:
                config["evaluations"] = args.evaluations
            result = run_search(config, args.out)
        elif args.command == "replicate":
            from .credentials import load_cli_credentials
            from .experiments import replicate_jev

            load_cli_credentials(args.key_file)
            result = replicate_jev(load(args.config), args.out, args.seeds)
        elif args.command == "verify":
            result = verification(args.specimen, args.out)
        elif args.command == "gallery":
            from .gallery import serve

            serve(args.directory, args.host, args.port)
            return
        else:
            import time

            import mujoco as mj
            import mujoco.viewer
            import numpy as np

            model = mj.MjModel.from_binary_path(str(args.specimen / "adult.mjb"))
            data = mj.MjData(model)
            state = np.load(args.specimen / "adult_state.npz")
            for key in ("qpos", "qvel", "ctrl", "act", "qacc_warmstart"):
                getattr(data, key)[:] = state[key]
            data.time = float(state["time"])
            mj.mj_forward(model, data)
            with mujoco.viewer.launch_passive(model, data) as viewer:
                while viewer.is_running():
                    viewer.sync()
                    time.sleep(0.03)
            return
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"tendril: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
