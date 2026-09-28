"""Small installation/component probe; not Tendril's engine acceptance test.

Run with SOFA_ROOT/PYTHONPATH configured for an official SOFA release and its
matching Python interpreter. Reports JSON after SOFA's own diagnostic output.
"""

import json
import platform
import time

import numpy as np
import Sofa.Core
import Sofa.Simulation
import SofaRuntime

PLUGINS = (
    "AnimationLoop",
    "StateContainer",
    "Topology.Container.Dynamic",
    "ODESolver.Backward",
    "LinearSolver.Iterative",
    "Mass",
    "SolidMechanics.FEM.Elastic",
)


def probe(kind):
    root = Sofa.Core.Node("probe_" + kind)
    root.dt = 0.001
    root.gravity = [0, -9.81, 0]
    root.addObject("DefaultAnimationLoop")
    root.addObject("EulerImplicitSolver")
    root.addObject("CGLinearSolver", iterations=30, tolerance=1e-10, threshold=1e-12)
    if kind == "beam":
        positions = [[0, 1, 0, 0, 0, 0, 1], [0.1, 1, 0, 0, 0, 0, 1]]
        dofs = root.addObject(
            "MechanicalObject", template="Rigid3d", position=positions
        )
        root.addObject("EdgeSetTopologyContainer", edges=[[0, 1]])
        modifier = root.addObject("EdgeSetTopologyModifier")
        field = root.addObject(
            "BeamFEMForceField", youngModulus=1e5, poissonRatio=0.3, radius=0.01
        )
        edit_method = "addEdges"
    else:
        positions = [[0, 1, 0], [0.1, 1, 0], [0, 1.1, 0], [0, 1, 0.1]]
        dofs = root.addObject("MechanicalObject", template="Vec3d", position=positions)
        root.addObject("TetrahedronSetTopologyContainer", tetrahedra=[[0, 1, 2, 3]])
        modifier = root.addObject("TetrahedronSetTopologyModifier")
        field = root.addObject(
            "TetrahedralCorotationalFEMForceField", youngModulus=1e5, poissonRatio=0.3
        )
        edit_method = "addTetrahedra"
    root.addObject("UniformMass", totalMass=0.1)
    Sofa.Simulation.init(root)
    start = time.perf_counter()
    for _ in range(100):
        Sofa.Simulation.animate(root, root.dt.value)
    elapsed = time.perf_counter() - start
    result = dict(
        kind=kind,
        steps=100,
        simulated_seconds=root.time.value,
        elapsed_seconds=elapsed,
        finite=bool(np.isfinite(dofs.position.value).all()),
        field_state=str(field.componentState.value),
        modifier_type=type(modifier).__name__,
        point_addition_exposed=hasattr(modifier, "addPoints"),
        element_addition_exposed=hasattr(modifier, edit_method),
        positions=np.asarray(dofs.position.value).tolist(),
    )
    Sofa.Simulation.unload(root)
    return result


if __name__ == "__main__":
    for plugin in PLUGINS:
        SofaRuntime.importPlugin("Sofa.Component." + plugin)
    print(
        json.dumps(
            dict(
                python=platform.python_version(),
                numpy=np.__version__,
                probes=[probe("beam"), probe("tetrahedron")],
            ),
            indent=2,
        )
    )
