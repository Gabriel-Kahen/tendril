# Engine feasibility evaluation

**Status: initial tests run; MuJoCo 3.14.0 is the implemented backend.** SOFA was investigated first. Read [SOFA findings](SOFA_INVESTIGATION.md), [combined branch/mixed-body findings](BRANCH_FINDINGS.md), and [volumetric findings](SOFT_BODY_FINDINGS.md). The requirements below remain the evaluation standard; passing the documented fixtures does not establish validity for all morphologies.

Reuse a physics engine; build Tendril's developmental rules, mutation system, and archives ourselves. The first investigation should test changing topology during active mechanics, because that requirement distinguishes Tendril from ordinary fixed-body simulation.

## Candidate engines

| Engine | Reason to investigate | Key uncertainty |
| --- | --- | --- |
| SOFA | Dynamic-topology facilities and deformable/soft-robotics components | Whether the chosen mechanical, actuator, and collision components support the same runtime edits reliably |
| MuJoCo | Articulated mechanics, tendons/muscles, deformables, and model editing/recompilation | Cost and state fidelity of repeated growth edits with the selected representation |
| Newton | Extensible simulation with GPU execution and several mechanical representations | How to change connectivity and state after model construction; static model storage may complicate growth |

Investigate SOFA first. This is an order of investigation, not a selection decision. Verify current documentation and behavior for each chosen version. References are in [REFERENCES.md](REFERENCES.md).

## Minimal 3D scene

Use a deliberately small scene with gravity and a floor:

1. Begin with a seed structure and a bounded contractile element.
2. Grow an oriented branch while contraction continues.
3. Branch in three dimensions and exercise contact with both the floor and another part of the structure.
4. Connect two previously separate attachment sites to make a loop or brace.
5. Pause development and run a mature actuation assay.
6. Apply a small external perturbation and replay at a smaller timestep.

The test should include genuine out-of-plane geometry and motion. It must not be a planar mechanism merely rendered with a 3D camera. Automated or scripted developmental edits are sufficient here; evolution and Jev are unnecessary until the mechanics work.

## What to measure

| Concern | Evidence to record |
| --- | --- |
| State continuity | Position and velocity before/after edits; changes in momentum attributable to explicitly added material or external impulses |
| Energy accounting | Kinetic, gravitational, and elastic energy where available; actuator work; energy attributable to growth and rest-geometry/material edits |
| Connection creation | New elements' rest state, initial strain, and any activation ramp; no unexplained impulsive motion |
| Collision behavior | Floor contact and self-contact during growth, including around newly inserted members |
| Stability | Finite states, bounded deformation, convergence of the qualitative mechanism under timestep reduction |
| Development cost | Time per topology edit or recompilation and how it changes as the structure grows |
| Rollout cost | Headless throughput, memory, and the cost of reproducing a rollout |
| Inspectability | Saved configurations, deterministic edit logs where possible, and visual playback tied to physical state |

Do not define success solely by a visually plausible animation. Log discontinuities and any engine workarounds. Tolerances must reflect the representation and solver; record and justify them before interpreting the test.

## Decision rule

Prefer the simplest engine and representation that support the developmental loop with credible mechanics and a practical search cost. Record exactly which combination of components and versions passed, rather than generalizing from the engine name.

If a candidate fails, identify the obstacle: unsupported topology, incompatible collision updates, numerical behavior, excessive edit overhead, or our own implementation. Test a targeted fix or another candidate before considering a custom solver. Building a small extension to an existing engine may be enough.

The initial feasibility tests and historical unguided validation are complete. The current project decision requires Jev for every evolutionary selection; future searches must stop on guidance failure rather than fall back to unguided evolution.
