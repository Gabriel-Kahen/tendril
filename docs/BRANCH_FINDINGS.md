# Growing branch feasibility

Measured September 23, 2026 with MuJoCo 3.14.0. This exercises the implemented `World` mechanics using a prescribed legal edit schedule. The schedule was selected through fixture exploration; it is not an evolved organism or evidence for guided search.

```sh
.venv/bin/python scripts/probe_branch.py --out runs/branch-probe
.venv/bin/python scripts/probe_branch.py --mixed --timestep .0005 --tissue-young 20000 --out runs/branch-strict-20000
.venv/bin/python scripts/probe_branch.py --mixed --timestep .0005 --tissue-young 50000 --out runs/branch-strict-50000
.venv/bin/python scripts/probe_branch.py --mixed --timestep .0005 --tissue-young 100000 --out runs/branch-strict-100000
.venv/bin/python -m pytest tests/test_physics.py tests/test_simulation.py tests/test_elasticity.py -q
```

The fixture grows six oriented finite-thickness branches from a seed at 20 ms intervals while muscle control and gravity run. It attaches tips 5 and 6 with a finite-radius elastic connection at 0.12 s, pauses growth at 0.16 s, and applies a small three-axis impulse during the adult phase at 0.6 s. All motion, collisions, growth directions and recording are 3D. The final seven-segment body has spatial rank three.

## Branch result

| Measurement | 1 ms timestep | 0.5 ms timestep |
| --- | ---: | ---: |
| Simulated duration | 1.3 s | 1.3 s |
| Accepted extensions / connections | 6 / 1 | 6 / 1 |
| Existing joint position/velocity edit error | 0 / 0 | 0 / 0 |
| Floor contact records, accumulated over steps | 10,452 | 20,428 |
| Nonadjacent rod self-contact records | 1,076 | 1,971 |
| Maximum contact penetration | 5.29 mm | 5.52 mm |
| Signed actuator work | 0.00967 J | 0.01039 J |
| Growth energy delta | 0.43197 J | 0.43220 J |
| Total charged energy | 1.67960 J | 1.68039 J |
| Measured real-time factor | 1.88× | 0.98× |
| Current validity gates | pass | pass |

Contact totals count solver records across timesteps, not independent impacts; doubling the step count should increase them. Direct parent-child rod collision is excluded at their shared joint, so reported rod self-contacts involve nonadjacent segments. The final tip positions differ by 1.93 mm RMS and 4.05 mm maximum between timesteps. This is encouraging for this fixture, not broad convergence proof.

The test verifies that developmental additions, continuing actuation, floor contact, actual nonadjacent self-contact, a collidable loop connection, frozen adult topology and a perturbation coexist. A separate connection test checks zero initial elastic extension against the measured live rest length. Connection mass is explicitly added at its endpoints.

The 5.3–5.5 mm contact penetration is below the current configured 8 mm rejection threshold but appreciable relative to 12 mm rod radius. Passing the current threshold does not establish that the contact parameters are final. More stringent collision tolerances, alternative contact settings and varied body scales need evaluation.

Timings include Python validity checks, frame generation and accounting; concurrent local work affects them. They do not establish evolutionary evaluations/hour or GPU performance.

## Mixed tissue result: material-dependent acceptance

The mixed variant adds a genuine 27-node, 48-tetrahedron patch to the moving root at 0.14 s, using the implemented pinned-face attachment. Existing branch growth/closure operations succeed and joint transfer is continuous for each tested material. The same strain limit (0.25) and minimum volume ratio (0.5) apply to all trials. The final table uses extrema tracked at every physics step, replacing earlier frame-sampled measurements; all six cases were rerun with the final accounting code.

| Young's modulus | Timestep | Minimum all-step volume ratio | Maximum principal Green strain | Current gates |
| --- | ---: | ---: | ---: | --- |
| 20 kPa | 0.5 ms | 0.1100 | 0.4964 | reject: strain and volume |
| 20 kPa | 0.25 ms | 0.1063 | 0.4966 | reject: strain and volume |
| 50 kPa | 0.5 ms | 0.6672 | 0.3443 | reject: strain |
| 50 kPa | 0.25 ms | 0.6575 | 0.3495 | reject: strain |
| 100 kPa | 0.5 ms | 0.8561 | 0.2060 | pass |
| 100 kPa | 0.25 ms | 0.8549 | 0.2072 | pass |

At 20 kPa the first sampled strain failure occurs around 0.220 s, after creation. State remains finite, but tissue substantially compresses during this active body's interactions. At 50 kPa the volume gate passes while strain remains excessive. Halving the timestep does not rescue either rejected combination. These fixtures demonstrate physical rejection, not a reason to prohibit volumetric tissue categorically.

At 100 kPa the complete mixed fixture passes the unchanged gates at both timesteps: genuine tissue is added to a growing, contracting, colliding, nonplanar branch with a loop closure, then tested with frozen topology and an adult push. Maximum contact penetration is approximately 6.92 mm, close enough to the configured 8 mm bound to warrant tighter contact studies. Measured real-time factors are approximately 0.36× and 0.20×, including diagnostics and concurrent local work.

Acceptance depends on material, morphology, attachment and loading together. A 50 kPa patch failing this stress fixture does not establish that other 50 kPa organisms fail. Conversely, the 100 kPa fixture passing current gates does not establish calibrated biological tissue or validity under arbitrary squashing. The constitutive model and chosen strain cutoff remain research assumptions.

## Full development and adult assays: accepted mixed specimen

The checked-in `configs/mixed-genome.json` expresses two developmental modules: the root differentiates a volumetric patch and produces branches; the recursively reused child module keeps growing and contracting without automatically adding tissue at every site. Root maturation is 0.05 s, while child maturation remains 0.25 s. This is selective tissue expression through the genome, with normal branch depth and 32-segment capacity preserved.

`configs/mixed-organism.json` is the exact validated configuration. It retains the default 50 kPa tissue, 3 s development, four independent 2 s adult assays, 20 J budget, strain limit 0.25, minimum volume ratio 0.5, and penetration limit 8 mm. The authored specimen develops seven branches, one genuine tetrahedral tissue patch and one loop connection. It passes baseline, push, load and object assays at both timesteps.

| All-step extrema across development and assays | 0.5 ms | 0.25 ms |
| --- | ---: | ---: |
| Maximum principal Green strain | 0.166732 | 0.169736 |
| Minimum tissue volume ratio | 0.885654 | 0.882789 |
| Maximum contact penetration | 6.297 mm | 6.166 mm |
| Completed simulated duration | 11 s | 11 s |
| All four adult assays | pass | pass |

These extrema are accumulated at **every physics step**, including between playback frames. An earlier all-sites tissue variant was rejected after this stricter tracking exposed transient strain above the configured limit; selected patch placement and developmental timing resolve that failure for this specimen without relaxing the gates. This establishes a usable mixed example, not universal material validity or an evolved discovery.

Reproduce the normal run, then request replay, timestep refinement and another perturbation direction:

```sh
.venv/bin/tendril run --genome configs/mixed-genome.json --config configs/mixed-organism.json --seed 1 --out runs/mixed-example
.venv/bin/tendril verify runs/mixed-example --out runs/mixed-example-verified
```

The recorded base and half-timestep evidence is under `runs/mixed-validation/root-only-50000-stiff-0.08/` and `runs/mixed-validation/root-only-50000-stiff-0.08-half-step/`. Genome/configuration files in `configs/` are copied exactly from the validated base run. The measured source fingerprint was `f98959d298368594a60f32aaa7fcf50b87405cc2f44f3bfd474454b3ac16a9c3`; each result records its own version information. The additional perturbation-direction command above is available for further checking; the table reports the measured base and half-timestep runs.

## Reproducibility and tests

The scripts write exact genome/configuration, edit accounting, playback frames, final XML and results under ignored `runs/`. Physics/evaluation tests cover moving joint state transfer, stress-free finite-thickness connection creation, nonplanar growth, real tissue compilation, energy exhaustion and near-exhaust active control, transactional rollback, byte-identical replay frames, independent adult starting states, paused adult growth, and evaluable passive precursors. Separate elasticity tests check engine force/energy agreement and inversion detection.

These results do not close the full physical accounting problem: damping/contact losses, robust material supply/momentum rules for arbitrary additions, and stricter checks across diverse morphologies remain necessary. No evolutionary or Jev advantage is measured here.
