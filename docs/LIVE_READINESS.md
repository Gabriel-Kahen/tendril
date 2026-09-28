# Live Jev readiness — September 27, 2026

The actual Jev-guided developmental simulator is operational for bounded research runs. Live selection, real MuJoCo evaluation, archive insertion, continuation from a checkpoint, and API admission limits have been exercised. This is integration evidence, not a demonstration of sustained open-ended discovery or a Jev advantage.

## End-to-end evidence

Local run: `runs/readiness-20260927/evolution-v2` (ignored generated data).

- **16 real Jev-selected candidates**, each selected from 32 legal proposals; no alternate selector or fabricated evaluator.
- **1 physically valid organism**, retained in both archives. The other 15 failed tissue strain and/or contact penetration checks; the thresholds were not relaxed.
- Eight initialization evaluations followed by 8 archived-parent evaluations.
- The normal 0.5 ms integration step, three-second development limit and four independent two-second adult assays were retained. Invalid candidates stop early under the existing physical gates.
- Four CPU workers. The first invocation completed 12 evaluations; explicit resume completed four more.
- Resuming toward evaluation 17 at the 16-request cap stopped before network dispatch. A completed-run resume made no extra requests.
- Pinned model: `jev-1.13.0`. All 16 requests in this run reported usage; estimated input cost is **$0.013707918**, using the documented $0.042/million input-token price (output free). This excludes the separate API probe and earlier failed integration run; provider billing remains authoritative.
- Source fingerprint: `09e30663ca16573adcc7d0a01d52ac23d3ca4248fece7e654fe10a623eba6372`. Source or runtime changes still require a new experiment.

The separate initial API probe succeeded. The first full integration attempt exposed rounded probability totals and missing initialization-failure feedback; that stopped run remains recorded under `runs/readiness-20260927/evolution`.

## Wiring completed

The CLI loads `TYPESAFE_API_KEY` or an owner-only raw key file at `~/.config/tendril/typesafe.key`; `--key-file` overrides the file location. Environment credentials take precedence. Files must be regular, owned by the current user and inaccessible to group/others; symlinks are rejected. Key contents and credential-file paths never enter experiment configuration. Authorization is sent only to the fixed TypeSafe HTTPS endpoint; redirects are refused and echoed credentials are redacted from records/audits.

Jev sees the approved novelty/stepping-stones instruction, parent evidence, mutation history and the last eight completed trial summaries. Initialization and reseeding failures now enter that history too. The same batch still cannot see its pending outcomes. The new context provides evidence; it does not impose a new selection heuristic or change physics.

Live Jev probabilities can be rounded to two decimal places and total 0.99. The validator accepts only rounding-compatible unit totals, still requires exactly the legal candidates and a highest-probability choice, and preserves the raw reported numbers. Clearly inconsistent totals, out-of-pool choices and malformed replies still stop the run.

Every attempt is written before transport. Request caps count unsuccessful/interrupted attempts as well as successful ones; cached decisions are not new calls. The dollar gate reserves 65,536 input tokens at the pinned model price for each call (about $0.002753). Unknown usage retains that reservation. Limits can be raised on resume without resetting the ledger. This is a bound under the recorded provider price/context contract, not a provider-enforced account spending cap.

`configs/evolution.json` uses 64 evaluations, 128 API attempts, a $1 run-local API cap and a 3,600-second invocation deadline. The deadline stops admitting new requests/batches; in-flight work can finish past it. Replicated seeds have separate caps. Strict mid-batch wall-time termination is not implemented.

## Start a new run

```sh
uv run tendril evolve --config configs/evolution.json --out runs/jev-001
uv run tendril gallery runs/jev-001
```

The private key is already configured on this machine. It is outside the repository and must not be copied into a command, experiment configuration or commit. A scan of source and live-run files found no credential contents.

## Validation and remaining limits

The regression suite passes **140 tests**. Python error/undefined-name checks pass. An offline wheel/source build succeeds and includes the gallery and licensed Three.js assets. Existing broader style findings and upstream vendor whitespace are separate from functional validation.

The low valid fraction in this small run is material: operation is ready, but productive long searches are not established. Improving contact behavior and physical qualification remains research work. Archive admission is based on the primary rollout; automatic repeated-perturbation/timestep qualification, a full archive novelty context, richer tissue remeshing and graphical run controls remain outstanding.

Contract and price references checked September 27: [TypeSafe API](https://docs.typesafe.ai/api), [model limits and pricing](https://docs.typesafe.ai/models).
