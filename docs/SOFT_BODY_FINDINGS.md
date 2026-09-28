# Volumetric tissue feasibility

Measured locally on September 23, 2026 with MuJoCo **3.14.0**, Python **3.12.13**. These are component tests, not a completed developmental organism or an engine-selection verdict.

Run after installing the project:

```sh
.venv/bin/python scripts/probe_soft.py --out runs/soft-probe
.venv/bin/python -m pytest tests/test_elasticity.py -q
```

The probe uses actual 3D tetrahedral finite elements, not a skin or a network presented as volumetric tissue. An initial 27-node, 48-tetrahedron block receives two appended slabs while a bounded internal contractile force remains active. The resulting 45-node, 96-tetrahedron body settles on the floor. Each new slab shares existing boundary vertices; material mass is lumped from tetrahedral volumes. Existing rest geometry remains intact, so growth does not erase stored elastic energy. New nodes inherit boundary displacement and velocity. Added kinetic, gravitational, elastic-preload energy and momentum are recorded explicitly.

Material settings are 20 kPa Young's modulus, Poisson ratio 0.3, density 300 kg/m³, 4 cm mesh spacing, 2 mm collision radius, and 0.002 s Rayleigh damping coefficient. Muscle-like input is capped at 0.2 N, 0.01 W, and 0.25 m/s shortening; it stops pulling below 5.5 cm endpoint separation. These are probe settings, not calibrated biological parameters or settled organism limits.

## Measured results

One simulated second, including two additions at 0.15 and 0.30 seconds:

| Measurement | 0.5 ms timestep | 0.25 ms timestep |
| --- | ---: | ---: |
| Finite state / engine warnings | yes / none | yes / none |
| Minimum sampled signed volume ratio | 0.97644 | 0.97635 |
| Maximum sampled Green-strain component | 0.04918 | 0.05086 |
| Peak floor contacts | 15 | 15 |
| Peak self-contacts in growing block | 0 | 0 |
| Local measured real-time factor | 0.277× | 0.155× |

These timings include Python diagnostics and recording, and vary with concurrent work. They are not a throughput estimate for full evolutionary evaluations. Initial imposed strain is 0.05156 before stepping; the table reports subsequent samples. Volume ratio is the determinant of the deformation gradient, with inversion below zero.

At the 0.5 ms timestep, both additions preserve every existing node's position and velocity exactly in the tested representation. Momentum accounting residuals are below 6×10⁻²⁰ kg·m/s. Each slab adds 0.0768 kg; added elastic preload is approximately 0.000182 J and 0.000156 J. Compilation takes approximately 2.1–2.2 ms per addition. This does not establish continuity for arbitrary topologies, rotations, attachment policies, or larger edits.

A separate **self-contact fixture** places two disconnected tetrahedral blocks in one flex. Falling onto each other produces 50 simultaneous same-flex contacts, with minimum sampled volume ratio 0.9500 and finite states. This exercises the engine's self-collision pathway. It does **not** demonstrate folding/self-contact of a connected growing organism.

The growth test's minimum reported contact distance is approximately −2.14 mm. MuJoCo uses compliant contact, so nonzero penetration remains; this must be checked against the eventual body's thickness and validity tolerances.

## Implementation findings

- `integrator="discrete"` is required by this version for flex elasticity; `implicit` and `implicitfast` are rejected by the compiler for this combination.
- A newly parsed `MjSpec` followed by `spec.recompile(old_model, old_data)` failed to preserve states and intermittently crashed in the native call. That is not the documented same-spec editing workflow. The probe uses **fresh compilation plus explicit name-based state transfer**. It makes no general claim that correctly retained-spec recompilation fails.
- `data.energy[0]` includes gravitational and 1D flex-edge spring energy, but omits the 3D flex elastic energy in the tested model. `tendril.elasticity.flex_elastic_energy` adds the omitted term using the engine's packed edge stiffness matrix: `0.25 * e.T @ K @ e`, where `e` contains squared edge-length changes. Finite-difference gradients match engine spring forces, including multiple flexes. A textbook continuum formula did not exactly match this engine implementation and is retained only as a separately named reference diagnostic in probe records.
- Do not add the 1D edge spring energy again: that would double-count it. A dedicated test verifies this.
- `model.flex_vert0` contains normalized coordinates; it is not a world-space rest mesh. `flex_reference_positions` obtains the actual reference state, and `flex_deformation_metrics` calculates signed tetrahedron volume ratios, principal Green strains, and inversion counts relative to it.
- Turning on internal tetrahedron collision would alter the constitutive response. This probe leaves `internal="false"` and measures inversions instead.

## Remaining gates

This material formulation is intended for finite rotations and small strains; passing this test does not establish plausible arbitrary squashing or nearly incompressible flesh. The low-stiffness first trial and an invalid state-transfer trial inverted elements; finite values alone are not a valid success criterion.

Subsequent integrated work adds mixed rod/tissue attachment, combined grown-body contact fixtures, mature perturbation assays and budgets/validity gates in search; see BRANCH_FINDINGS.md and VALIDATION.md. Broader strain/timestep stress tests, repeated growth with larger irregular meshes and tissue fusion remain open. Damping, friction and contact losses are not integrated into a closed energy balance here. This component script's actuator-work integral is a sampled diagnostic, not an exact discrete work identity; the production simulator separately charges actual per-step tendon work.

Machine-readable configurations, growth accounting, traces, XML, and sampled trajectories are written under ignored `runs/soft-probe/`. There is no measured evolutionary or Jev advantage in these results.

## Primary references

- [MuJoCo flex elasticity reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html#flex-elasticity)
- [Flex contact behavior](https://mujoco.readthedocs.io/en/stable/XMLreference.html#flex-contact)
- [Model editing lifecycle](https://mujoco.readthedocs.io/en/stable/programming/modeledit.html)
- [Engine passive-force implementation](https://github.com/google-deepmind/mujoco/blob/main/src/engine/engine_passive.c)

The linked documentation/source can change; numerical findings above are tied to the installed version and saved probe configuration.
