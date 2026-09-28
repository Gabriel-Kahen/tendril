# Validation record

Recorded September 23, 2026, with Python 3.12.13, MuJoCo 3.14.0, NumPy 2.5.3 and SciPy 1.18.1. The original implementation validation source fingerprint is `f98959d298368594a60f32aaa7fcf50b87405cc2f44f3bfd474454b3ac16a9c3`.

## Automated checks

The original implementation passed 58 tests. They exercise topology/state continuity and rollback, live connection rest lengths, muscle work/power limits, omitted elastic-energy gradients, volumetric deformation, developmental evaluation/replay, archives and legal mutations, checkpoint compatibility, guidance contracts/cost accounting, and gallery file confinement. The installed console entry point and packaged viewer were checked. Browser playback was visually checked with actual recorded branches, tissue and links.

## End-to-end search

```sh
uv run tendril evolve --config configs/evolution.json --out runs/release/evolution --evaluations 24
uv run tendril verify runs/release/evolution/specimens/000003 --out runs/release/verification
```

Seed 23, four workers, random selection: **24 evaluations, 20 valid, eight structural niches, two behavioral niches**, with 17 structural archive members and three behavioral members. Sixteen evaluations were mutation offspring. Valid evolved tissue bodies occurred among these records; this is not evidence of advanced locomotion or useful manipulation.

The initial invocation took 177.90 seconds while other validation jobs were running. This is an observed run duration, not an isolated throughput benchmark. A subsequent successful no-op resume overwrote summary.json's explicitly named `wall_seconds_this_invocation` field with that invocation's duration.

Specimen 000003 replayed with identical structure descriptors and capabilities. Its half-timestep and changed-perturbation variants remained valid. Half-timestep motion differed by −0.00000547 m and support by −0.00001683 m. The `same_structure: false` refinement field includes small continuous span differences; it does not by itself mean topology changed. These checks cover one specimen, not every archive member.

## Full mixed organism

The curated mixed genome produces seven branches, one 48-tetrahedron tissue patch and one collidable loop. Full three-second development plus four two-second adult assays pass at both timesteps, with the default 50 kPa tissue and unchanged validity gates:

| Physics step | Maximum principal Green strain | Minimum signed volume ratio | Maximum penetration |
| --- | --- | --- | --- |
| 0.5 ms | 0.166732 | 0.885654 | 6.297 mm |
| 0.25 ms | 0.169736 | 0.882789 | 6.166 mm |

Tissue extrema include every physical step. The default all-sites `seed --tissue` genotype fails the strain gate; enabling tissue everywhere is not a guarantee of a mechanically viable organism. The curated genome instead differentiates tissue in its root module while the recursive child module develops branches.

Reproduce using the checked-in mixed genome/configuration; see README.md and BRANCH_FINDINGS.md. Original records are locally under `runs/mixed-validation/root-only-50000-stiff-0.08` and its `-half-step` counterpart.

## Interpretation

Combined branch and mixed-body stress fixtures also exercise growth, contraction, floor/self-contact, loop closure and an adult perturbation at two timesteps. See BRANCH_FINDINGS.md, SOFT_BODY_FINDINGS.md and SOFA_INVESTIGATION.md for their narrower evidence.

No live Jev calls were made for these validations. No guidance advantage, broad numerical robustness, high-fidelity biological material model or open-ended evolutionary result is claimed. Physical and research limitations are documented in IMPLEMENTATION.md.

## Jev-only policy revision

The supported evolutionary path now requires a valid Jev choice for every candidate, including initialization. The historical unguided search measurements above remain evidence for that earlier implementation, not measurements of the new guided policy. Offline tests cover missing-key preflight, rejecting legacy selectors, failed-response checkpoint recovery, cached-decision reuse, retry billing records and malformed/nonfinite replies. No live API requests were made during this revision. Full guided physical search awaits credentials and production run safeguards described in NEXT.md.

## Continuous feedback revision

The full suite passes **82 tests** after separating regulatory dynamics from growth and adding tissue/link contact ownership. Additional real-contact assertions verify that tissue-only contact activates both local muscle feedback and the contact-required growth gate.

Both the original mixed fixture and the authored `configs/feedback-genome.json` complete three seconds of development plus all four independent two-second adult assays. The active-signaling fixture also passes at half the physics timestep:

| Physics step | Maximum principal Green strain | Minimum signed volume ratio | Maximum penetration |
| --- | --- | --- | --- |
| 0.5 ms | 0.166647 | 0.885707 | 6.293 mm |
| 0.25 ms | 0.169576 | 0.882953 | 6.308 mm |

Each develops seven branches, one volumetric patch and one loop. Starting adult signals are cloned independently; their final signal values differ between timesteps by at most `5.64e-13`. Physical trajectories retain timestep sensitivity. The regulatory agreement is expected for unsaturated linear dynamics with matched developmental event times, not evidence that every future evolving body is numerically robust.

Records: `runs/feedback-validation/mixed`, `runs/feedback-validation/signaling` and `runs/feedback-validation/signaling-half-step`. Source fingerprint: `7c0c4781e5360bafabf1ee09d15107c3e480600d49aa4490b92093ade5eab77a`. These are authored physical/controller fixtures, not an unguided evolutionary run or a Jev result.

```sh
uv run tendril run --genome configs/feedback-genome.json --config configs/mixed-organism.json --seed 1 --out runs/feedback-example
```

The model equations, sensor conventions, limitations and proposed qualification scheme are in FEEDBACK_MODEL.md.
# Live Jev integration, September 27, 2026

The full CLI → authenticated Jev → MuJoCo → archive path completed 16 evaluations with checkpoint continuation. One body passed the physical gates; 15 were rejected. Request-cap enforcement and no-op resume made no extra API calls. The regression suite now passes 140 tests. See [LIVE_READINESS.md](LIVE_READINESS.md) for settings, model/version, costs, source fingerprint and limits; earlier measurements below remain historical evidence.
