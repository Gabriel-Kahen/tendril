# Tendril

**Evolving growing, contractile 3D organisms through novelty and physical constraints.**

Tendril is a runnable research implementation. Inherited local programs grow articulated elastic branches, contract muscle-like cables, form collidable elastic connections, and differentiate genuine volumetric tissue. Physics feeds strain and contact back into development and control. Evolution preserves structural diversity and compares capabilities within behavioral niches.

There is no single target body or global task champion. Passive precursors can survive alongside moving organisms. The aim is to discover diverse, coherent mechanisms with inspectable developmental histories.

**Current status:** the CPU implementation uses MuJoCo 3.14.0 after investigating SOFA and testing the documented growing-body scene. Development, independent adult assays, evolutionary archives, mutation guidance interfaces, replay, and the specimen gallery are implemented. Component and integration tests pass. The initial search runs validate the software; they do **not** establish rich open-ended evolution, calibrated biological tissue, or an advantage from Jev. See [implementation and limits](docs/IMPLEMENTATION.md) and [measured findings](docs/BRANCH_FINDINGS.md).

## Install and run

Requires Linux and Python 3.12; the headless simulator needs no GPU. Dependencies stay in the project's virtual environment. `evolve` and `replicate` require a TypeSafe key. The CLI uses `TYPESAFE_API_KEY` when set, otherwise it reads `~/.config/tendril/typesafe.key`: one raw key, owned by you, with mode `600`. An explicit `--key-file` is also supported. Keep credentials outside the repository; key files are never copied into run records.

```sh
uv sync --python 3.12 --extra test
uv run tendril run --config configs/organism.json --out runs/organism
uv run tendril evolve --config configs/evolution.json --out runs/evolution
uv run tendril gallery runs/evolution
```

Open the local gallery address printed by the last command. A full-window perspective scene shows recorded development and independent adult assays, with lit bodies, actual tissue surfaces and ground shadows. Choose a specimen and scrub or play; Details holds physical records, lineage, mesh display and playback speed. Drag to orbit, shift-drag to pan and scroll to zoom. The gallery is read-only, requires WebGL2, and works offline with its bundled renderer.

To run the validated mixed organism with branches, a loop and volumetric soft tissue:

```sh
uv run tendril run --genome configs/mixed-genome.json --config configs/mixed-organism.json --seed 1 --out runs/tissue
```

Use `configs/feedback-genome.json` with the same configuration for an authored mixed body with continuous regulatory signaling. Both examples are physical fixtures, not evolutionary discoveries.

The default experiment uses four CPU workers and batches of four, with 64 evaluations. All physical limits and search settings are saved with the run. Increase the evaluation budget without changing the experiment:

```sh
uv run tendril evolve --config configs/evolution.json --out runs/evolution --resume --evaluations 256
```

Resume refuses changed code, engine/runtime versions, or experiment settings. A new experiment is required after such changes.

## Verify and replicate

```sh
uv run pytest -q
uv run python scripts/probe_branch.py --out runs/branch-probe
uv run python scripts/probe_branch.py --mixed --timestep .0005 --tissue-young 100000 --out runs/mixed-probe
uv run python scripts/probe_soft.py --out runs/soft-probe
uv run tendril verify runs/evolution/specimens/000000 --out runs/verification
uv run tendril replicate --config configs/evolution.json --seeds 0 1 2 --out runs/replicates
```

Verification reruns the recorded genome/seed, halves the physics timestep, and changes the adult perturbation direction. It reports differences rather than asserting robustness automatically. Replicated Jev searches record wall time, archive diversity, capabilities, and available API usage/costs across seeds. The checked-in experiment pins `jev-1.13.0` and limits each run to 128 API attempts and a $1 conservative API budget. A 3,600-second per-invocation deadline stops admitting requests/batches; in-flight work finishes and can overrun this deadline. Request/dollar accounting persists across resume. Limits apply separately to each replicated seed.

Evolution requires Jev. Set `TYPESAFE_API_KEY` in the process environment; never put it in a run configuration or commit it. Jev selects every evaluated candidate, including initialization, from legal proposals. Random/adaptive search modes and random error fallback are removed. Missing credentials fail before evaluation; API errors or invalid choices stop with a checkpoint for explicit resume. Requests, resolved model versions, responses, usage and failed attempts are logged without credentials. Physics determines survival. Single-organism `run` and `verify` remain physical inspection tools, not alternative search modes. The adapter has passed an authenticated 32-option selection with real usage reporting. Request attempts are recorded before dispatch, so interrupted calls consume a conservative reservation until their usage is known. The dollar gate uses the pinned model’s documented price and maximum context; provider billing remains authoritative. See [live readiness](docs/LIVE_READINESS.md) for end-to-end evidence and remaining research limits.

For the engine's native inspection window, run `uv run tendril inspect runs/organism`. This loads the saved adult binary and state without advancing the simulation. Use the gallery for developmental playback.

## Read next

- [Implementation](docs/IMPLEMENTATION.md): physical conventions, architecture, data, and remaining research limits.
- [Design](docs/DESIGN.md): accepted direction and research proposals.
- [Local feedback model](docs/FEEDBACK_MODEL.md): signaling equations, contact sensing and qualification theory.
- [How Jev guides the process](docs/JEV_ARCHITECTURE.md): a simple architecture sketch, information flow and current limits.
- [Handoff](docs/HANDOFF.md): current working state and next investigations.
- [Validation](docs/VALIDATION.md): test coverage, search results and refinement evidence.
- [Efficiency measurements](docs/EFFICIENCY.md): behavior-preserving changes, exact replay comparisons and rejected tradeoffs.
- [Remaining implementation](docs/NEXT.md): concrete functionality gaps and optional extensions.
- [Engine evaluation](docs/ENGINE_EVALUATION.md): feasibility requirements and evidence.
- [SOFA investigation](docs/SOFA_INVESTIGATION.md), [branch and mixed-body findings](docs/BRANCH_FINDINGS.md), and [volumetric findings](docs/SOFT_BODY_FINDINGS.md).
- [References](docs/REFERENCES.md).

EvoForest supplies architectural inspiration; Tendril's physical evaluator and diversity-preserving search are implemented here. Generated specimens, credentials, and bulk experiment data stay out of version control.
