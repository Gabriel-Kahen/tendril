# SOFA investigation

Investigated September 23, 2026. **SOFA is runnable on this PC; Tendril's complete growing, actuated, self-colliding organism test has not passed.** This investigation does not select an engine. The runnable component probe is [`scripts/probe_sofa.py`](../scripts/probe_sofa.py).

## Installation actually tested

The host reports CachyOS Linux and system Python 3.14.6. No `runSofa` was initially on `PATH`. The official **SOFA v26.06.00 Linux/Python 3.12** archive was downloaded and extracted under `/tmp/tendril-sofa-probe`, with a separate uv environment at `/tmp/tendril-sofa-probe-venv`. No system packages were changed.

Archive: `SOFA_v26.06.00_Linux_Python3.12.zip` (231,348,351 bytes).

Verified SHA256:

```text
2a5c80dd012a433c36bae11ed06df701eb447387b6d2657410b2ef76ff2e32be
```

The [official download page](https://www.sofa-framework.org/download/) supplies that checksum and lists the bundled plugins. The [release](https://github.com/sofa-framework/sofa/releases/tag/v26.06.00) also offers Python 3.10 binaries; its checksum section retains old version labels, so the correctly labeled download page was used for comparison. The [SofaPython3 installation instructions](https://sofapython3.readthedocs.io/en/latest/content/Installation.html) require a matching Python version and explicit package paths.

Measured environment: CPython 3.12.13, NumPy 2.5.3, SciPy 1.18.1, pybind11 2.12.0. Only Python/NumPy are exercised directly by the probe. Set `SOFA_ROOT` to the extracted release, add its `plugins/SofaPython3/lib/python3/site-packages` to `PYTHONPATH`, and put the matching Python runtime's `lib` directory in `LD_LIBRARY_PATH` if needed. Then run:

```sh
/tmp/tendril-sofa-probe-venv/bin/python scripts/probe_sofa.py
```

These temporary locations are investigation artifacts, not a permanent dependency installation. A reproducible production setup would pin and verify the same archive in an explicit external dependency directory. Import individual `Sofa.Component.*` libraries: this archive did not provide the attempted `Sofa.Component.All` umbrella plugin.

## What ran

Both headless scenes used `DefaultAnimationLoop`, `EulerImplicitSolver`, `CGLinearSolver` (30 iterations, tolerance 1e-10, threshold 1e-12), `UniformMass` (0.1 total), gravity `[0, -9.81, 0]`, and 100 steps of 0.001 seconds.

| Scene | Components | Observed result |
| --- | --- | --- |
| One 0.1-unit beam | `Rigid3d` mechanical state, `EdgeSetTopologyContainer`, `BeamFEMForceField`, Young's modulus 100,000, Poisson ratio 0.3, radius 0.01 | Force field reports `Valid`; finite states; falls 0.0495405 units in 0.1 seconds |
| One tetrahedron with 0.1-unit perpendicular edges | `Vec3d`, `TetrahedronSetTopologyContainer`, `TetrahedralCorotationalFEMForceField`, same modulus and Poisson ratio | Force field reports `Valid`; finite states; same free-fall displacement |

The runs took approximately 0.0066 and 0.0065 seconds respectively, excluding setup. **These are installation smoke checks, not Tendril throughput estimates.** Uniform free fall does not test bending, deformation, self-contact, actuation, new material, solver convergence, or energy conservation. The script prints the actual state and elapsed time on every run.

## Component support and integration gaps

SOFA's [topology documentation](https://sofa-framework.github.io/doc/simulation-principles/topology/) describes addition and removal through topology containers, modifiers, and algorithms, while explicitly limiting compatibility to some components. Directly replacing topology arrays is therefore not an acceptable substitute for propagating topology events.

| Requirement | Evidence | Current status |
| --- | --- | --- |
| Oriented elastic branches | [BeamFEMForceField](https://sofa-framework.github.io/doc/components/solidmechanics/fem/elastic/beamfemforcefield/) uses rigid frames. The shipped v26.06.00 `BeamFEMForceField.inl` registers an edge creation callback and derives new beam properties from rest positions. | Static component ran. Dynamic mechanical/state compatibility untested. |
| Deformable volumes | The shipped `TetrahedralCorotationalFEMForceField.inl` registers tetrahedron creation callbacks. This is a distinct class from `TetrahedronFEMForceField`. | One static tetrahedron ran. Growing volumetric contact untested. |
| Python adaptive topology edits | Both the instantiated edge and tetrahedron modifiers downcast to `Sofa.Core.PointSetTopologyModifier`. Runtime inspection exposes `addPoints`, but no `addEdges` or `addTetrahedra`; shipped `Sofa/Core/__init__.pyi` agrees. | Missing from the tested Python binding, **not proven unsupported by SOFA's C++ engine**. |
| Bounded contraction | [SoftRobots](https://github.com/SofaDefrost/SoftRobots) supplies cable and pressure actuators. Its shipped `CableConstraint.inl` supports force/displacement modes and force, displacement, and displacement-change limits. | Source inspected only. Growth-compatible mappings and explicit actuator-work accounting untested. |
| Surface collisions and self-contact | [TriangleCollisionModel](https://sofa-framework.github.io/doc/components/collision/geometry/trianglecollisionmodel/) and [TetrahedronFEMForceField examples](https://sofa-framework.github.io/doc/components/solidmechanics/fem/elastic/tetrahedronfemforcefield/) provide collision and tetrahedron-to-surface machinery. | Availability is not evidence that insertion updates contact mappings correctly. Full combination untested. |
| Finite-radius beam contact | Beam mechanical radius does not itself establish collision geometry. A compatible collision model/mapping is required. | Untested. |
| Material and energy accounting | Tendril must explicitly initialize new material, rest states, velocity, inertia, actuator limits, and edit-energy charges. | No complete accounting test performed here. |

The source evidence above comes from headers included in the checksum-verified archive, not from an unspecified development branch. Relevant files live below `include/Sofa.Component.SolidMechanics.FEM.Elastic/` and `plugins/SoftRobots/include/`. The probe does not load or test the optional plugins.

## Recommendation

Keep SOFA as a viable candidate. The immediate obstacle is the missing element-edit Python bindings, not installation failure. A small C++/pybind bridge to official topology modifier methods is a plausible route; alternatively, controlled scene reconstruction could be tested for state preservation and edit cost. Neither route has been implemented or validated here. Scheduled `TopologicalChangeProcessor` edits can help exercise engine mechanics, but would not by themselves provide adaptive local growth.

Next, validate a single runtime edge insertion, preserving all old positions and velocities, deliberately initializing the new rest state and material momentum, and checking force-field/collision state before and after the edit. Repeat for tetrahedral growth. Then run the combined contraction, floor contact, self-contact, attachment, mature assay, and timestep checks from [ENGINE_EVALUATION.md](ENGINE_EVALUATION.md). Do not promote the component smoke checks into a feasibility pass, select SOFA solely from its component inventory, or reject it solely because the Python bridge needs work.
