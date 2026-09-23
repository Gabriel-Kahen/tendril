# Design

This is a research design, not an implemented specification. **Commitments** describe the accepted direction. **Proposals** are starting hypotheses to test. Specific mechanics, representations, numerical limits, and selection algorithms remain open.

## Purpose and boundaries

The commitment is to evolve interesting physical things in 3D. Novelty and physical capability both matter. A population should discover different ways to grow, move, support itself, respond to contact, and interact with objects, without converging on one predetermined robot or task score.

Biology is the inspiration for inheritance, development, duplication, physical feedback, and the reuse of structures for new purposes. Natural evolution does not literally maximize a novelty score. Our explicit novelty objective is a deliberate way to explore a simulated space.

The initial experiment is not a full ecosystem, a metabolism simulator, or a high-fidelity model of biological tissue. Those additions would need a concrete research reason.

## Proposed physical substrate

Start by investigating a network of structural elements with finite thickness, oriented attachment sites, passive elasticity, and contractile links. This is a simplified mechanical organism, not volumetric flesh merely because it might eventually be rendered that way.

An element or site could carry:

- A 3D position and local orientation, mass, and material properties.
- Local developmental state, age, signals, and measurements such as strain or contact.
- Passive connections with rest geometry, stiffness, damping, and appropriate resistance to bending or twist.
- Contractile fibers between attachment points, with bounded force, shortening, speed, and power.

An actuator changes a desired length or equivalent constitutive parameter. The physics engine computes the resulting motion. It must not teleport endpoints into place.

Developmental rules would operate in a local coordinate frame. Candidate operations include extension, branching, attachment to a nearby site, differentiation, changing material properties, emitting or responding to a signal, and stopping growth. Closed loops and braces should be possible. There should be no built-in instruction meaning “make a leg” or “crawl.”

The exact element type—rods, elastic articulated segments, deformable elements, or a combination—is unresolved. It depends on the engine feasibility test.

## Development and motion

The core proposed loop is:

**growth → shape → contraction → strain/contact → further growth**

Physics should run at the fastest timescale, local control at a slower one, and developmental edits at the slowest. These rates must be measured rather than selected for convenience alone.

During a juvenile phase, growth and actuation happen together. During mature assays, growth pauses. This makes it possible to measure what the developed organism can do without confusing actuation with work supplied by adding material or changing geometry.

Repair or regeneration is an attractive later question, not a requirement for the first version.

## Physical accounting

Evolution will exploit anything the simulator permits. Physical validity therefore needs to be part of the substrate, not an aesthetic judgment after rendering.

- Give organisms explicit material and actuation budgets.
- Account for energy introduced by growth, mass changes, rest-length edits, or stiffness changes. Newly attached connections must not receive unlimited preload for free.
- Initialize or ramp new elements deliberately and preserve state continuity as topology changes. Define how added mass obtains momentum and energy.
- Model contact and self-contact with finite thickness. Members passing through one another must not become an unintended source of capability.
- Reject or quarantine nonfinite states, explosive dynamics, and invalid topology. Log why an organism was rejected.
- Recheck promising behaviors at smaller timesteps and under small perturbations to distinguish mechanisms from numerical artifacts.

These are design requirements, not claims that an available engine already satisfies them in our intended configuration.

## Inheritance and variation

The proposed genotype is an interpretable graph or collection of developmental modules shared across sites. Its execution is local and stateful over time. A module can connect growth decisions, signaling, and muscle control.

Variation should include numerical edits to thresholds, timing, growth angles, stiffness, and activation; structural edits such as duplication, deletion, and rewiring; and compatible module recombination. Duplicating a branch-producing module together with its actuation logic, then changing its phase, is a useful example of a mutation with a meaningful developmental effect.

Ordinary random mutations remain essential. A lineage must be able to pass through neutral changes and passive or immobile precursors. A possible design is to retain a developmental archive alongside a behavior archive so that useful structural stepping stones are not discarded for lacking immediate motion.

An expensive generative model might occasionally invent a new module template. That template would need validation before entering the mutation library. This is optional and distinct from ordinary offspring production.

## Environment and assays

Begin with gravity, a floor, and a few simple movable objects. Proposed assays include undisturbed behavior, a standardized push, contact with a loose object, and a small applied load. They can reveal recoil, recovery, folding, rolling, gripping, support, or mechanical transmission.

Every organism need not succeed at every assay. An organism that provides support can occupy a different niche from one that locomotes. The assays should reveal capabilities and tradeoffs rather than impose one mandatory body plan.

## Selection and discovery

Separate physical validity from novelty and local capability:

1. Check bounded, physically meaningful behavior and resource feasibility.
2. Describe the organism through several views of structure and behavior.
3. Preserve unusual valid outcomes and useful developmental stepping stones.
4. Compare capability, robustness, and efficiency among relevant peers or niches.

Possible descriptors include topology, branching and loops, proportions, material layout, deformation, trajectories, coordination, and response to pushes or loads. Descriptors should come from simulation state rather than camera angle or lighting. Genotype distance or visual difference alone is insufficient.

There should be no single global champion whose descendants overwhelm all niches. Archive sampling and local competition should maintain alternatives and tradeoffs. The exact archive algorithm and descriptors are unresolved; any descriptor imposes a bias. Use multiple views, record descriptor versions, and preserve enough raw data to reinterpret earlier specimens.

Repeatability does not require perfectly periodic or identical motion. Multistable behavior can be interesting. Evaluate distributions across controlled perturbations so that meaningful variability is distinguishable from instability or measurement noise.

An inspectable specimen gallery, developmental playback, behavior clips, and lineage history are intended research outputs. They should make discovery visible, not merely produce aggregate scores.

## Jev's exact proposed role

Jev is a cheap typed-decision model. It returns constrained choices or other typed outputs; it is not the free-form code generator for this design. Its low cost motivates testing more frequent guidance, but does not establish that the guidance will improve evolution.

For a subset of offspring:

1. Code constructs a pool of legal, concrete edits for a selected parent.
2. Jev receives the relevant parent module, computed behavioral summaries, available edit identifiers, and limited lineage or mutation history.
3. Jev selects or shortlists edit identifiers, or possibly a compatible donor module.
4. Code applies and validates the edit; physics evaluates the offspring.

A pool of 32 edits and an initial unguided share of at least half are illustrative starting proposals, not settled hyperparameters. Useful choices might include delayed activation in a duplicated branch, greater compliance at a strained junction, or strain feedback into a growth rule.

Jev should not be the per-frame muscle controller, the novelty or survival judge, a physical oracle, an image critic, or the sole gate through which mutations pass. The candidate generator defines which edits are legal; simulation provides evidence about effects. Limited numerical precision and multi-step reasoning are reasons to keep its decisions narrow and summaries explicit.

Log prompts, typed responses, model versions, costs, and resulting edits. Cache suitable requests and support replay. A low API price may permit many calls, but physics may dominate total cost.

The research comparison is Jev-guided variation against random and simple adaptive selection from matched candidate pools. Compare valid novelty archive expansion, diversity, robustness, and useful capabilities under total cost and time budgets. There is no demonstrated Jev advantage yet.

## EvoForest adaptation

The [EvoForest reimplementation](https://github.com/Gabriel-Kahen/evoforest-reimplementation) offers architectural ideas for graph alternatives, mutation proposals and validation, reusable modules, caching, and experiment records. The reviewed revision was `d79b438213472c218497d4c8ac19658ebb507f79`.

Its existing evaluation and search objectives do not directly implement Tendril. A regression evaluator would be replaced by stateful physical rollouts. Global-best-oriented selection would need diversity archives and local comparisons. A developmental graph is executed across time and across growing sites, rather than only evaluated as a static predictor.

Reuse should follow a concrete interface and experiment need. Do not port the entire system before the physical substrate is proven.
