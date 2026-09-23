# Tendril

**Evolving growing, contractile 3D structures through novelty and physical constraints.**

Tendril is a proposed artificial evolution experiment. Small inherited programs would grow physical structures, equip them with contractile elements, and let their motion feed back into further growth. Search would preserve diverse forms and behaviors while applying enough physical and functional pressure to produce coherent organisms.

The aim is to discover interesting things: a branching structure that braces itself, a loop that rolls, a body that folds around an object, or a lineage that discovers an unexpected mechanism. There is no single target body or universally optimal task.

**Status: design only.** No simulator has been implemented, no physics engine has been selected, and no experiment has been run. These documents capture the starting design and its open questions.

## Starting commitments

- Work in **3D from the outset**, including growth, mechanics, collisions, and evaluation.
- Evolve developmental programs and reusable modules, rather than only optimizing fixed body parameters.
- Couple growth and muscle-like actuation through local physical feedback.
- Combine novelty preservation with physical validity and competition among comparable organisms.
- Reuse an existing physics engine and build our own developmental and evolutionary layers.
- Investigate cheap Jev decisions as guidance for a subset of mutations; let simulation determine what actually happens.

## Read next

- [Design](docs/DESIGN.md): substrate, inheritance, selection, and Jev's proposed role.
- [Handoff](docs/HANDOFF.md): what is agreed, what remains open, and where to resume.
- [Engine evaluation](docs/ENGINE_EVALUATION.md): the first concrete experiment, before selecting a simulator.
- [References](docs/REFERENCES.md): model documentation, related evolution work, and engine sources.

The first milestone is a small physical feasibility test: a 3D branch grows while contracting, contacts the floor and itself, forms a new connection, and then stops growing for an actuation assay. This should reveal whether an engine can support the intended developmental loop without discontinuities or unaccounted energy.

Tendril draws architectural inspiration from [EvoForest's reimplementation](https://github.com/Gabriel-Kahen/evoforest-reimplementation). Adapting its search machinery will require a new rollout evaluator and diversity-preserving selection; this is not a drop-in application.
