# Behavior-preserving efficiency pass

September 23, 2026. Scope: eliminate redundant work without reducing physical accuracy, checks, recorded information, model context, replay guarantees or interface features. Timing gains are workload-specific, not a universal speed guarantee.

## Retained changes

- **Warning checks:** test MuJoCo's existing warning-count array directly instead of constructing and iterating Python warning views twice per step. Every warning category still rejects invalid dynamics. A 100,000-check microbenchmark measured 69.46 to 2.12 microseconds per check.
- **Frame construction:** compute each segment's endpoints once and use both values, instead of performing the same computation twice.
- **Signal graph construction:** canonicalize each two-endpoint edge with a comparison instead of allocating and sorting a two-item list. The existing bounded cache keys and matrix arithmetic are unchanged. Seven alternating 30,000-step samples measured median 0.41144 to 0.38060 seconds, with exactly equal resulting states.
- **Playback UI:** do not rebuild DOM for an unchanged recorded frame. Physical/event details update when visible and are refreshed immediately on opening. Playback timing, saved frames and refresh cadence are unchanged.
- **Tissue rendering:** reuse the current mesh, material and position/normal buffers when their sizes match. Update all coordinates and recompute normals and bounds. No frames or past meshes are retained in a new cache.

## Equivalence evidence

The original source was copied before edits. Before/after evaluator subprocesses run the same authored genome, configuration and seed. Equality covers all saved frames, genome/configuration, adult XML, numeric adult-state arrays, event records and result fields. Only measured runtime/edit timings and the deliberately changed source fingerprint are excluded. Equality is exact, not tolerance-based.

Renderer checks compare 573 forward, backward and empty saved frames against the original code: identical coordinates, normals, bounds, capsule transforms/colors and wireframe behavior. Across two tissue lifetimes, each tissue resource allocation count falls from 564 to 2. One hundred unchanged-frame UI updates allocate zero DOM nodes instead of 1,500. Opening Details, phase transitions and scrubbing retain the same content. Browser inspection checks playback and mesh mode with no JavaScript errors.

The complete regression suite passes: 83 tests, including every MuJoCo warning category. The broader Ruff check reports 29 existing style findings in unchanged code; they are outside this pass.

## Rejected changes

- Preparing immutable tetrahedral rest inverses reduced metric CPU time and allocation peak, but retained another 4,224 bytes per patch. It was removed to honor the strict no-tradeoff request.
- Streaming JSONL reduced full-request peak allocations by about 30%, but regressed tiny-record latency and allocation peak. Original loading is retained.
- Changing timestep, numerical precision, tissue resolution, solver settings, check frequency, model input, worker/batch policy or checkpoint/audit durability would trade away behavior, evidence or guarantees. None were changed.
- Search/guidance I/O did not reveal a compelling free gain in this pass. Successful-call caching already avoids repeated requests; removing durable attempt records or changing checkpoint frequency was rejected. No live Jev calls were made.

## Measured rollout times

Local CPU wall time around evaluation, including saved output, using `configs/feedback-genome.json`, `configs/mixed-organism.json` and seed 1:

| Fixture | Before | After | Less wall time |
| --- | ---: | ---: | ---: |
| Branches/loop, tissue disabled, 2 simulated seconds | 1.983 s | 1.356 s | 31.6% |
| Mixed body, 2 simulated seconds | 5.001 s | 4.303 s | 14.0% |
| Mixed body, full 11 simulated seconds | 29.230 s | 25.582 s | 12.5% |

Short cases use median times from three interleaved before/after pairs, with 0.8 seconds of development and four independent 0.3-second assays. The full case uses one pair with the original three-second development and four two-second assays. All seven pairs are valid and match exactly under the comparison above. These are local fixture measurements, not isolated machine-wide throughput claims; browser inspection overlapped the full pair.

The raw comparison scripts and evidence for this pass are in the local temporary directory `/tmp/tendril-efficiency-ay33ias2/`; full run artifacts remain outside version control.

## Second pass: smaller allocation and dispatch costs

The second pass compares against the already optimized first-pass code. It retains three small changes:

- `World.positions()` lets the enclosing NumPy array make the independent snapshot, removing redundant copies of each site's coordinates. The returned array still cannot mutate MuJoCo state.
- Adult shape measurement reads final positions once and centers that private array in place. Arithmetic and rigid-alignment calculation remain unchanged.
- Signal saturation calls the array's `clip` method directly. This avoids the generic NumPy function wrapper while keeping the same array operation, bounds and output allocation.

Position snapshots, median of seven alternating 10,000-call samples:

| Sites | Before | After | Traced peak allocation, before → after |
| --- | ---: | ---: | ---: |
| 1 | 2.174 μs | 1.853 μs | 424 → 304 bytes |
| 7 | 12.158 μs | 9.111 μs | 1,432 → 576 bytes |
| 32 | 56.251 μs | 39.167 μs | 6,424 → 2,168 bytes |

Exact values and independence from engine arrays were checked at all three sizes. Signal stepping, median of seven alternating 20,000-step samples, fell from 0.18341 to 0.16323 seconds at one site, 0.26172 to 0.24974 seconds at seven sites, and 0.54383 to 0.52275 seconds at 32 sites. Resulting signals match exactly; traced peak allocation fell by 56 bytes in each case. These microbenchmarks describe individual operations, not overall rollout speed.

Additional rejected experiments: in-place tissue strain arithmetic saved allocation but ran slightly slower; using an uninitialized energy-metric buffer gave inconsistent timing gains; in-place signal clipping increased allocation peak for the smallest network. None were retained. No new persistent cache, physics changes, omitted checks or guidance-context reductions were introduced.

Second-pass evidence is local to `/tmp/tendril-efficiency2-vytcj5my/` and `/tmp/tendril-efficiency2-physics/`; generated runs stay outside version control.

Nine paired rollout comparisons (three per fixture, alternating execution order) remain valid with exactly equal saved results under the same comparison as the first pass. Median evaluation wall times including saved output:

| Fixture | Before second pass | After second pass |
| --- | ---: | ---: |
| Branches/loop, 2 simulated seconds | 1.342 s | 1.313 s |
| Mixed body, 2 simulated seconds | 4.427 s | 4.483 s |
| Mixed body, 11 simulated seconds | 25.786 s | 25.955 s |

The mixed-body measurements do not demonstrate an overall speedup: the medians are slightly slower (1.3% short, 0.7% full), with overlapping before/after sample ranges. The retained changes reduce measured component work and temporary allocations; a total mixed-body throughput benefit is unproven. These small timings cannot establish a universal absence of performance regressions. Physical settings, output information and checks are unchanged.
