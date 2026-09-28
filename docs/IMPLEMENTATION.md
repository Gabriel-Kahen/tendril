# Implementation and physical conventions

Implemented September 23, 2026. Tendril is now executable research software, not a design-only repository. This document distinguishes implemented choices from verified fixtures and open scientific questions.

## Scope

The actual system includes 3D growth during contraction, finite-thickness collision geometry, local inherited development, bounded muscle actuation, structural and behavioral archives, legal variation, CPU process workers, independent mature assays, required Jev selection, reproducible experiment records, and an offline 3D gallery. Soft tissue consists of volumetric tetrahedral finite elements, not a cosmetic surface. There is no 2D fallback, fabricated rollout evaluator, or single global fitness objective.

This does not make the scientific program complete: rich evolving behaviors, descriptor quality, robust physical accounting across all legal morphologies, and guidance benefits require experiments. An implementation passing a fixture is evidence about that fixture.

## Engine decision

SOFA was investigated first. Its official release runs on this machine and passed beam/tetrahedron smoke tests, but the tested Python bindings lack edge/tetrahedron insertion. Its C++ components have relevant topology callbacks; SOFA remains viable with a binding extension or measured scene-rebuild path. See SOFA_INVESTIGATION.md.

MuJoCo **3.14.0** is the implemented backend because the combined branch feasibility scene works with explicit compilation/state transfer, contractile actuation, floor contact, nonadjacent self-contact, and new collidable connections. Mixed tissue passes for particular tested material/body combinations. Newton was not installed or benchmarked; no relative performance claim is made.

The selected representation is an experimental substrate, not a claim of high-fidelity biological tissue. All units are SI.

## Body, growth, and mechanics

Each structural segment is a finite-radius capsule in a tree. The root has a free joint; child ball joints provide elastic bending/twisting with damping and a bounded angular range. Three off-axis tension-only tendons span each parent/child joint. MuJoCo integrates the motion and collision response. Direct parent/child capsule collision is excluded at the shared joint; nonadjacent segments collide. Capsule geometry starts slightly beyond a child's joint to avoid overlapping branching junctions.

Attachment creates a **1D flex with finite radius**, elastic extension and damping. It collides, unlike a rendering-only line or ordinary spatial tendon. Its initial rest length equals the current tip separation. Cable mass is lumped equally at the endpoints. It does not model bending stiffness of a thick beam.

Tissue differentiation creates a 3×3×3 grid with 48 tetrahedra beside a segment, pinning one face. Pinned-node mass is explicitly returned to the supporting body; moving nodes retain their own masses. The mixed body therefore includes stiff supports, elastic joints, contractile fibers, collidable flexible links, and deformable volume. The current developmental operation adds complete patches; arbitrary remeshing and fusion of existing patches are not implemented. Separate component tests demonstrate contiguous tetrahedral slab addition.

The discrete integrator is required for volumetric elasticity in this engine version. Rod-only worlds use implicit-fast integration. Default configurations use a 0.5 ms physics step, 20 ms control interval, and 100 ms developmental interval. These are configurable research settings, not universal stability guarantees.

A local module stores segment geometry/material properties, muscle timing and feedback, signal emission, growth age/depth bounds, strain/contact gates, an attachment radius, tissue differentiation, and references to child modules with local 3D directions. Recursive module references permit repeated motifs; depth, material, energy and element caps bound execution. Neighbor signals propagate through tree and loop connections at every physics step, including adult assays, and affect contraction. Signal source/decay/diffusion uses cached exact linear propagation followed by saturation. Solver-active contacts on capsules, tissue and flexible links feed their local owners. Strain and contact can alter contraction and gate development. See FEEDBACK_MODEL.md for equations and sensor limitations. There are no built-in legs, gaits, grips or target body plans.

## Topology changes and supply accounting

An edit is transactional:

1. Record mechanical energy, mass, momentum and existing contacts.
2. Compile the proposed graph using the existing engine.
3. Copy named generalized positions, velocities, controls and warm-start accelerations. Compiler-generated tissue joints receive stable body-derived names. New joints begin with zero relative velocity, inheriting attachment motion.
4. Set new link rest lengths from the live connection geometry. Retain old links' rest lengths.
5. Verify existing world positions remain continuous, reject new deep overlap and budget violations, then accept or roll back the entire edit.
6. Log signed energy change, mass added, momentum supplied, material/energy charge and edit time.

New material comes from an explicit **external reservoir comoving with the attachment**. This is an open mass system: total organism momentum is not claimed to remain constant when adding material. New mass can bring kinetic and gravitational energy; those changes are logged and positive mechanical-energy changes are charged, along with a configurable fabrication cost per kilogram. Negative edit energy never refunds the budget. There is no metabolism/ecosystem model.

MuJoCo's reported energy includes gravity, joint springs and 1D flex springs but omits the tested 3D flex elastic term. The implementation adds the engine-consistent packed-metric energy `0.25 * eᵀ K e`. Its finite-difference gradient is tested against engine forces. It does not add the already-accounted 1D term twice.

Muscle force, mechanical power, shortening speed and shortening range are bounded. Each constant-force timestep records work from force times actual tendon-length change, including acceleration from rest. Positive work is charged per muscle so absorption cannot cancel supply elsewhere. A holding cost is also charged. Trial steps exceeding the power or remaining-energy limit are rolled back and retried with reduced force; only one physical step is accepted. External perturbation work is recorded separately. Motor energy conversion efficiency is conventionally 1 in this initial accounting model, not measured physiology.

Damping, friction and compliant-contact losses are not integrated into a closed discrete energy balance. Reported mechanical work and growth terms do not prove exact conservation or eliminate every possible numerical exploit. Smaller-timestep checks and passive controls remain essential.

## Validity and assays

Validity rejects engine warnings, nonfinite states, excessive speed, excessive contact penetration, escape from the bounded domain, over-budget mass/energy, inverted or over-compressed tissue, and excessive tissue strain. Volume/strain extrema are monitored at every physical step for tissue and retained, so a transient failure cannot disappear between saved frames. The current tissue limits are minimum signed volume ratio 0.5 and maximum principal Green strain 0.25. They reflect the intended small-strain material regime, not a universal failure criterion for living tissue.

Contact is compliant. The current absolute penetration gate is 8 mm; branch fixtures reach approximately 5–7 mm with 12 mm capsule radius. That is a material limitation requiring tighter contact studies, not invisible perfect collision prevention.

Development ends before adult assays. Each assay clones the same adult physical state, including actual link rest geometry and deformed tissue:

- Undisturbed baseline.
- Seeded horizontal push.
- Downward load at a high attachment site.
- A standardized loose object positioned beside an extremity.

Object placement is an external assay intervention and its energy change is logged. All tissue mass participates in the organism center of mass. Shape deformation removes best-fit rigid translation/rotation. Separate reported capabilities cover motion, support, recovery, object displacement and energy expenditure. These metrics are initial operational definitions, not validated measures of interestingness.

## Evolution and guidance

`genome.py` validates bounded modules and generates explicit legal numerical, direction, duplication, deletion, rewiring, branching, pruning, passive, differentiation and recombination edits. Every proposal pool is saved.

`search.py` maintains two archives. The structural archive protects a pioneer and uses descriptor diversity within a niche, allowing passive developmental precursors. The behavioral archive uses local Pareto capability competition. Parents are sampled across niches and archive views; there is no global scalar champion. Descriptor schemas and experiment settings are versioned.

Jev selects every evolutionary candidate, including initialization, from the legal candidate interface. Random/adaptive selectors and random error fallback are removed. Candidate generation and parent sampling remain seeded and stochastic; no candidate reaches the evolutionary evaluator without a valid Jev choice. Errors/invalid choices stop the run and preserve a checkpoint. Requests, failed attempts, responses, resolved versions and token usage support replay. The transport reads credentials from the environment; the CLI can load an owner-only local key file before starting. Credentials and key-file paths never enter experiment records. The pinned model is `jev-1.13.0`; authenticated selection has been validated.

`experiments.py` runs replicated Jev searches across seeds and reports diversity, capabilities, wall time and API costs. The API ledger includes completed requests from interrupted batches and preserves failed-attempt accounting; unknown usage/pricing stays unknown. Run-local API attempt/dollar gates reserve the full pinned-model context before dispatch and charge uncertain attempts conservatively. The invocation wall deadline is an admission limit checked before candidate work and batches; it does not terminate in-flight work. Limits can be raised on resume; request/cost accounting is retained. Replicated seeds have separate limits. See LIVE_READINESS.md. There is no unguided comparison path.

Promising specimens can be rerun with `tendril verify`, including a half timestep and another perturbation direction. Archive membership currently uses the primary evaluation; it does **not** automatically mean the specimen passed all refinement runs. Large-scale scientific claims must use those verification results.

## Files, replay, and operation

- `config.py`: explicit physical settings and validation.
- `physics.py`, `elasticity.py`: engine construction, state transfer, accounting and tissue diagnostics.
- `simulation.py`, `signals.py`: development, continuous local regulation, assays, descriptors and records.
- `genome.py`, `guidance.py`, `search.py`, `experiments.py`: inheritance, selection and comparison.
- `gallery.py`, `viewer.html`: offline playback of recorded three-dimensional states.
- `cli.py`: run/evolve/replicate/verify/gallery/native inspection commands.

A specimen contains `genome.json`, `config.json`, `result.json`, `events.jsonl`, `frames.jsonl`, `adult.xml`, `adult.mjb`, and `adult_state.npz`. Search adds `proposal.json` with legal alternatives and lineage. The XML is inspectable construction input; it alone does **not** retain runtime flex rest-length overrides. The binary and state preserve the adult engine model. Replay from genome/config/seed is tested deterministically on the same version/environment; cross-platform bitwise identity is not promised.

Experiments record source fingerprints and Python/engine/library versions. Resume refuses incompatible versions/settings before modifying the checkpoint. Checkpoints are atomic; workers only evaluate bodies, while the parent consumes results in deterministic submission order. Generated bulk output is ignored by git.

The gallery serves read-only local files with path/symlink confinement, plays actual saved frames, and distinguishes independent assay time resets. It does not run a replacement browser physics engine. The native MuJoCo viewer is also available for inspecting saved adult mechanics.

## Remaining research work

- Tighten contact behavior relative to body thickness and test more morphologies/materials.
- Establish broader conservation/error budgets and independent physical references.
- Compare body representations and tissue resolutions at matched compute cost.
- Improve descriptors and assays if archives preserve trivial stationary variants or miss useful precursors.
- Run replicated, longer searches and recheck discoveries before interpreting behavior.
- Measure Jev-guided diversity/capability and total physics/API cost across replicated runs; no baseline advantage can be inferred.
- Extend tissue growth/remeshing only with explicit state, mass, energy and collision tests.

The implemented system enables these investigations. It does not predetermine their outcome.
