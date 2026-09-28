"""Elastic energy matching MuJoCo's non-interpolated 3D flex spring force.

MuJoCo 3.14 does not include this term in ``data.energy[0]``.  The packed
edge metric is the same one used by ``mj_flexPassiveStretch``; its energy
is 1/4 e.T K e, where e is the vector of squared edge-length changes.
"""

import numpy as np


def flex_elastic_energy(model, data) -> float:
    """Read current forward-computed flex lengths; reject unsupported flexes.

    Call ``mj_forward`` before this function when state has been edited.
    This does not include contact penalties, damping, or 2D shell bending.
    """
    total = 0.0
    upper_i, upper_j = np.triu_indices(6)
    for f in range(model.nflex):
        stiffness = int(model.flex_stiffnessadr[f])
        if stiffness < 0 or model.flex_rigid[f]:
            continue
        if model.flex_dim[f] != 3 or model.flex_interp[f]:
            raise ValueError(
                "Energy accounting requires non-interpolated 3D tetrahedral flexes"
            )
        n = int(model.flex_elemnum[f])
        metric = np.zeros((n, 6, 6))
        packed = model.flex_stiffness[stiffness : stiffness + 21 * n].reshape(n, 21)
        metric[:, upper_i, upper_j] = packed
        metric[:, upper_j, upper_i] = packed
        address = int(model.flex_elemedgeadr[f])
        edges = model.flex_elemedge[address : address + 6 * n].reshape(n, 6)
        edges = edges + int(model.flex_edgeadr[f])
        elongation = (
            data.flexedge_length[edges] ** 2 - model.flexedge_length0[edges] ** 2
        )
        total += 0.25 * np.einsum("bi,bij,bj->", elongation, metric, elongation)
    return float(total)


def flex_reference_positions(model):
    """World-space flex rest positions, including parent body transforms."""
    import mujoco

    rest = mujoco.MjData(model)
    mujoco.mj_forward(model, rest)
    return rest.flexvert_xpos.copy()


def flex_deformation_metrics(model, data, reference_positions=None) -> dict:
    """Signed volume ratios and principal Green strain of each 3D tissue.

    Cache ``flex_reference_positions`` per compiled model and pass it to avoid
    allocating a reference MjData at every sample. ``model.flex_vert0`` is
    normalized mesh coordinates, so it is not the physical rest geometry.
    """
    if reference_positions is None:
        reference_positions = flex_reference_positions(model)
    tissues = []
    for f in range(model.nflex):
        if model.flex_dim[f] != 3:
            continue
        n = int(model.flex_elemnum[f])
        start = int(model.flex_elemdataadr[f])
        tets = model.flex_elem[start : start + 4 * n].reshape(n, 4)
        tets = tets + int(model.flex_vertadr[f])
        reference = reference_positions[tets]
        actual = data.flexvert_xpos[tets]
        rest_basis = (reference[:, 1:] - reference[:, :1]).transpose(0, 2, 1)
        basis = (actual[:, 1:] - actual[:, :1]).transpose(0, 2, 1)
        deformation = basis @ np.linalg.inv(rest_basis)
        ratios = np.linalg.det(deformation)
        strain = (deformation.transpose(0, 2, 1) @ deformation - np.eye(3)) / 2
        tissues.append(
            dict(
                flex_id=f,
                elements=n,
                min_volume_ratio=float(ratios.min()),
                max_principal_green_strain=float(
                    np.abs(np.linalg.eigvalsh(strain)).max()
                ),
                inverted_elements=int(np.count_nonzero(ratios <= 0)),
            )
        )
    return dict(
        tissues=tissues,
        volumetric_elements=sum(t["elements"] for t in tissues),
        min_volume_ratio=min((t["min_volume_ratio"] for t in tissues), default=1.0),
        max_principal_green_strain=max(
            (t["max_principal_green_strain"] for t in tissues), default=0.0
        ),
        inverted_elements=sum(t["inverted_elements"] for t in tissues),
    )
