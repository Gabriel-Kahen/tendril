# References

Sources collected during design on September 23, 2026. Living documentation can change; pin versions and recheck claims when implementing. These references motivate investigation and do not establish that Tendril's proposed combination works.

## Jev / TypeSafe

- [Models](https://docs.typesafe.ai/models): supported models, limits, and current pricing. Jev's inexpensive constrained decisions motivate frequent variation guidance; do not assume prices or limits remain fixed.
- [Jev 1.13 model jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13): strengths and limitations that matter when defining narrow decisions.
- [Choice primitive](https://docs.typesafe.ai/primitives/choice): choosing from a supplied set of alternatives.
- [Confidence](https://docs.typesafe.ai/confidence): interpreting model confidence rather than treating it as a physical verdict.
- [Fan-out pattern](https://docs.typesafe.ai/patterns/fan-out): background for many constrained decisions.

## EvoForest

- [EvoForest reimplementation](https://github.com/Gabriel-Kahen/evoforest-reimplementation), reviewed at revision [`d79b438213472c218497d4c8ac19658ebb507f79`](https://github.com/Gabriel-Kahen/evoforest-reimplementation/tree/d79b438213472c218497d4c8ac19658ebb507f79): architectural inspiration for alternatives, mutation proposals, validation, caching, and experiment records. Its evaluator and selection need substantive adaptation.

## Evolution and development

- [Joel Lehman's dissertation](https://www.joellehman.com/lehman-dissertation.pdf): novelty search, minimal criteria, and local competition.
- [Growing Neural Cellular Automata](https://distill.pub/2020/growing-ca/): local rules as a developmental mechanism. Tendril does not inherit the objective of reproducing a target image.
- [Developmental soft-robot evolution research, arXiv:1706.07296](https://arxiv.org/abs/1706.07296): background on development and evolvability.
- [Regeneration in soft-robot research, arXiv:2206.06674](https://arxiv.org/abs/2206.06674): related developmental questions; regeneration is not a first-version requirement.
- [Karl Sims: Evolved Virtual Creatures](https://www.karlsims.com/evolved-virtual-creatures.html) and [SIGGRAPH 1994 paper](https://www.karlsims.com/papers/siggraph94.pdf): foundational context for jointly evolving morphology and behavior. Tendril should not claim this general idea is new.

## Physics engines

- [SOFA](https://www.sofa-framework.org/) and [topology documentation](https://sofa-framework.github.io/doc/simulation-principles/topology/): investigate dynamic topology and component-specific support.
- [SOFA SoftRobots cable constraint](https://sofa-framework.github.io/doc/plugins/usual-plugins/softrobots/cableconstraint/) and [SoftRobots documentation](https://softrobots.readthedocs.io/en/latest/): candidate actuation mechanisms, subject to compatibility testing.
- [MuJoCo model editing](https://mujoco.readthedocs.io/en/latest/programming/modeledit.html): model specifications, editing, and recompilation. Runtime growth feasibility and cost need measurement.
- [MuJoCo modeling](https://mujoco.readthedocs.io/en/stable/modeling.html): mechanical representations and actuation.
- [Newton repository](https://github.com/newton-physics/newton), [ModelBuilder](https://newton-physics.github.io/newton/latest/api/_generated/newton.ModelBuilder.html), and [Model documentation](https://newton-physics.github.io/newton/1.4.0/api/_generated/newton.Model.html): examine construction, model storage, supported mechanics, and options for repeated topology edits.
