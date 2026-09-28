# Project handoff

Updated September 27, 2026. Read README.md, IMPLEMENTATION.md and relevant findings before changes.

## Current state

Tendril is runnable research software using Python 3.12 and MuJoCo 3.14.0. SOFA was investigated first; the tested Python bindings lacked the needed topology insertion calls. MuJoCo passed explicit compilation/state-transfer tests and combined growing-body fixtures. Newton was not benchmarked.

The system implements genuinely 3D local development during contraction, elastic articulated branches, collidable loop connections, volumetric tetrahedral tissue, local feedback/signaling, material and energy budgets, independent adult assays, diversity archives, legal mutation/recombination, required Jev selection, parallel CPU evaluation, replay records and a 3D playback gallery. There is no global scalar fitness champion.

This does not establish open-ended evolution, sophisticated behavior, calibrated biological tissue, or a Jev advantage. See VALIDATION.md for measured evidence and IMPLEMENTATION.md for conventions and limitations.

## Run and continue

```sh
uv sync --python 3.12 --extra test
uv run pytest -q
uv run tendril run --genome configs/mixed-genome.json --config configs/mixed-organism.json --seed 1 --out runs/mixed-example
uv run tendril evolve --config configs/evolution.json --out runs/evolution
uv run tendril gallery runs
```

The default experiment uses four CPU workers, 64 evaluations, three seconds of development and four independent two-second adult assays per valid body. Integration steps are 0.5 ms. Tissue makes rollouts appreciably more expensive. No NVIDIA hardware or GPU simulation is required.

The historical unguided validation search (from before the Jev-only decision) is saved locally in `runs/release/evolution`: 24 evaluations, 20 valid, eight structural niches and two behavioral niches. It includes valid evolved tissue-bearing bodies. Generated runs are ignored by git. The curated mixed-body genome/configuration are checked in as reproducible inputs.

Resume accepts a larger evaluation limit but refuses changed source fingerprints, runtime versions or experiment settings before modifying a checkpoint:

```sh
uv run tendril evolve --config configs/evolution.json --out runs/evolution --resume --evaluations 256
```

After changing simulation/search source, start a new experiment. Do not bypass the fingerprint check to blend different physical evaluators. The invocation wall-time field in summary.json describes the most recent invocation, including a no-op resume.

## Decisions to preserve

- Keep growth, mechanics, collisions, descriptors and playback genuinely 3D.
- Discover diverse coherent organisms rather than silently replacing the experiment with a single-task optimizer.
- Preserve developmental stepping stones and passive precursors alongside local capability competition.
- Jev's selection prompt prioritizes novelty over immediate performance or usefulness, with explicit value for simple, passive and unfinished stepping stones. See JEV_ARCHITECTURE.md for the exact instruction; archive rules remain as documented.
- Simulation supplies physical evidence. Jev selects every evolutionary candidate but never judges survival. No unguided/adaptive mode or random fallback is supported.
- New material enters from an explicit comoving external reservoir. Log supplied mass, momentum, signed mechanical-energy changes and charged fabrication/work.
- Reject transient tissue strain/inversion failures by checking every physical step, not only saved frames.
- Keep code inspectable and save seeds, versions, candidate pools, edits, physical accounting, configurations and lineage.
- Never commit credentials, conversation dumps or generated bulk data.

## Important implementation details

Fresh engine models transfer named state explicitly. Generated tissue joints receive stable names. New connections use live geometry as their rest length, and existing connections keep their original rest lengths. Adult binary models preserve runtime rest overrides that exported XML alone does not.

MuJoCo's reported potential energy omits the tested volumetric flex elastic term. The implementation adds its engine-consistent energy and tests its gradient against engine forces; it does not double-count 1D flex energy. Positive muscle work is charged separately per actuator from actual timestep displacement, with bounded-force retries for power/energy limits.

Regulatory state advances at every physical step, including adulthood, through tree and loop connections. Tissue contacts report to their supporting site; flexible-link contacts report to both ends. Only solver-active contacts enter this boolean feedback. See FEEDBACK_MODEL.md for model equations and limits.

Each adult assay starts from the same saved adult state, including its independently copied regulatory signals. Saved playback phases have independent time origins. Archive admission uses the primary evaluation; use `tendril verify` for replay, half-timestep and changed-perturbation evidence.

The efficiency pass removes redundant warning-view iteration, endpoint computation, signal-edge sorting, unchanged-frame DOM updates and tissue mesh allocation. Seven paired fixture runs have exactly equal saved trajectories and physical results; the full mixed-body pair uses 12.5% less wall time. Physics settings and checks are unchanged. See EFFICIENCY.md for scope, measurements and rejected memory/latency tradeoffs.

A second pass removes redundant position-array copies/reads and generic signal-clipping dispatch. It adds no persistent cache or changed numerical operation. JEV_ARCHITECTURE.md sketches the actual choice → simulation → archive loop, including API boundaries and remaining live-validation work.

The Jev HTTPS adapter has passed live authenticated selection with `jev-1.13.0` and usage reporting. CLI credentials come from the process environment or a private owner-only key file outside the repository. Request/dollar limits survive resume, with conservative reservations written before dispatch. The wall limit gates new requests/batches and allows in-flight work to finish. Missing/invalid guidance stops with resumable state. See LIVE_READINESS.md for current evidence. Historical unguided runs remain inspectable but cannot resume under the new policy.

The September 27 live integration run completed 16 Jev-selected evaluations, including archived-parent choices and checkpoint continuation; one organism passed all physical checks. Initial failures now inform mutation history and the last eight completed trial summaries supplied to Jev. Rounded probability totals are validated against their reported precision. All 140 tests pass. The low valid fraction remains a research limitation, not a reason to relax physical gates.

## Next research work

1. Tighten compliant contact relative to body thickness: current fixtures have approximately 5–7 mm penetration against an 8 mm gate and 12 mm capsule radius.
2. Expand morphology/material/timestep tests and independent physical references. Current soft tissue is a small-strain elastic substrate; arbitrary remeshing and tissue fusion are not implemented.
3. Run longer replicated searches; inspect whether descriptor niches retain meaningful diversity rather than stationary variants. Recheck promising bodies before interpreting capability.
4. Add robust archive qualification and improve novelty context. Measure physical capability/diversity across longer guided runs without claiming a baseline advantage.

Routine authorized development should proceed without repeated approval requests. Distinguish implementation, fixture evidence and scientific hypotheses.
