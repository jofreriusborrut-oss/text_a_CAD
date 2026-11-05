"""Linear static stress analysis on a voxel grid (finite element method).

Every solid box of the voxel grid is one 8-node brick element. Boxes of the
same size share the same 24 x 24 stiffness matrix, so only a few different
matrices have to be computed for a whole part.

Plain 8-node bricks are far too stiff in bending ("shear locking"), which is
exactly how brackets and plates are loaded. The element used here adds the
classic incompatible bending modes (Wilson / Taylor) and condenses them out,
which makes even a single layer of boxes bend correctly.

Units: millimetres, newtons, megapascals (1 MPa = 1 N/mm2).

This is a screening tool: it shows where a part is loaded and gives a first
estimate of stress and deflection. Curved and sloped faces are approximated
by steps, so peak stresses at holes and inner corners are only indicative.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import LinearOperator, cg, splu

from .voxel import VoxelGrid

# Local corner order of a brick, as (xi, eta, zeta) signs.
_CORNERS = np.array([
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
], dtype=float)
# Same corners as integer offsets (0 or 1) in the node grid.
_OFFSETS = ((_CORNERS + 1) / 2).astype(int)
_GAUSS = _CORNERS / np.sqrt(3.0)          # 2 x 2 x 2 Gauss points


def elasticity_matrix(E: float, nu: float) -> np.ndarray:
    """6 x 6 matrix linking strains to stresses for an isotropic material.

    Order of components: xx, yy, zz, xy, yz, zx (engineering shear strains).
    """
    if not 0 <= nu < 0.5:
        raise ValueError("Poisson's ratio must be between 0 and 0.5 (not included).")
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[np.arange(3), np.arange(3)] += 2 * mu
    D[np.arange(3, 6), np.arange(3, 6)] = mu
    return D


def _strain_rows(M: np.ndarray, col: int, dx: float, dy: float, dz: float) -> None:
    """Fill the three columns of a strain matrix for one displacement vector."""
    M[0, col] = dx
    M[1, col + 1] = dy
    M[2, col + 2] = dz
    M[3, col], M[3, col + 1] = dy, dx
    M[4, col + 1], M[4, col + 2] = dz, dy
    M[5, col], M[5, col + 2] = dz, dx


def _b_matrices(point: np.ndarray, size: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Strain-displacement matrices at a local point of a box with edges `size`.

    Returns B (6 x 24) for the 8 corner nodes and G (6 x 9) for the three
    incompatible modes (1 - xi^2), (1 - eta^2), (1 - zeta^2).
    """
    xi, eta, zeta = point
    s = _CORNERS
    scale = 2.0 / np.asarray(size, dtype=float)       # d/dx = (2 / hx) d/dxi, etc.
    dn = np.empty((8, 3))
    dn[:, 0] = s[:, 0] * (1 + s[:, 1] * eta) * (1 + s[:, 2] * zeta) / 8 * scale[0]
    dn[:, 1] = s[:, 1] * (1 + s[:, 0] * xi) * (1 + s[:, 2] * zeta) / 8 * scale[1]
    dn[:, 2] = s[:, 2] * (1 + s[:, 0] * xi) * (1 + s[:, 1] * eta) / 8 * scale[2]
    B = np.zeros((6, 24))
    for a in range(8):
        _strain_rows(B, 3 * a, *dn[a])
    dm = np.array([-2 * xi, -2 * eta, -2 * zeta]) * scale
    G = np.zeros((6, 9))
    for m in range(3):
        grad = np.zeros(3)
        grad[m] = dm[m]                               # mode m only varies along local axis m
        _strain_rows(G, 3 * m, *grad)
    return B, G


def element_matrices(size, nu: float) -> tuple[np.ndarray, np.ndarray]:
    """Stiffness of one box for E = 1 (multiply by E), and the matrix that
    recovers the incompatible-mode amplitudes from the corner displacements.

    Boxes with the same proportions share the work: the stiffness simply
    scales with the size, and the recovery matrix does not change.
    """
    size = np.asarray(size, dtype=float)
    scale = float(size[0])
    K, recover = _shape_matrices(round(float(size[1] / scale), 9), round(float(size[2] / scale), 9),
                                 round(float(nu), 9))
    return K * scale, recover


@lru_cache(maxsize=4096)
def _shape_matrices(ry: float, rz: float, nu: float) -> tuple[np.ndarray, np.ndarray]:
    size = np.array([1.0, ry, rz])
    D = elasticity_matrix(1.0, nu)
    Kuu = np.zeros((24, 24))
    Kua = np.zeros((24, 9))
    Kaa = np.zeros((9, 9))
    w = float(np.prod(size)) / 8.0                    # each Gauss point carries 1/8 of the volume
    for gp in _GAUSS:
        B, G = _b_matrices(gp, size)
        Kuu += B.T @ D @ B * w
        Kua += B.T @ D @ G * w
        Kaa += G.T @ D @ G * w
    recover = -np.linalg.solve(Kaa, Kua.T)            # alpha = recover @ u_element
    K = Kuu + Kua @ recover
    return (K + K.T) / 2, recover


@dataclass
class Model:
    """Finite element mesh built from a voxel grid."""
    grid: VoxelGrid
    elements: np.ndarray       # (n_el, 8) node number of each corner
    coords: np.ndarray         # (n_nodes, 3) node positions in mm
    centers: np.ndarray        # (n_el, 3) element centres in mm
    index: np.ndarray          # (n_el, 3) voxel index (i, j, k) of each element
    sizes: np.ndarray          # (n_el, 3) element edge lengths in mm
    kinds: np.ndarray          # (n_el,) index into `kind_sizes`
    kind_sizes: np.ndarray     # (n_kinds, 3) the distinct element sizes

    @property
    def n_nodes(self) -> int:
        return len(self.coords)

    @property
    def n_elements(self) -> int:
        return len(self.elements)

    @property
    def dofs(self) -> np.ndarray:
        """(n_el, 24) degree-of-freedom numbers of each element."""
        return (3 * self.elements[:, :, None] + np.arange(3)[None, None, :]).reshape(len(self.elements), 24)

    @property
    def volumes(self) -> np.ndarray:
        return self.sizes.prod(axis=1)

    def surface_nodes(self) -> np.ndarray:
        """Mask of the nodes that lie on the outer surface of the part."""
        counts = np.bincount(self.elements.ravel(), minlength=self.n_nodes)
        return counts < 8


def build_model(grid: VoxelGrid) -> Model:
    idx = np.argwhere(grid.solid)
    if len(idx) == 0:
        raise ValueError("The voxel grid is empty: nothing to simulate.")
    nx, ny, nz = grid.shape
    corner = idx[:, None, :] + _OFFSETS[None, :, :]                       # (n_el, 8, 3)
    flat = (corner[..., 0] * (ny + 1) + corner[..., 1]) * (nz + 1) + corner[..., 2]
    used, inverse = np.unique(flat, return_inverse=True)
    elements = inverse.reshape(flat.shape)
    k = used % (nz + 1)
    j = (used // (nz + 1)) % (ny + 1)
    i = used // ((nz + 1) * (ny + 1))
    coords = np.stack([grid.edges[0][i], grid.edges[1][j], grid.edges[2][k]], axis=1)
    centers = np.stack([grid.centers_1d(a)[idx[:, a]] for a in range(3)], axis=1)
    sizes = np.stack([grid.sizes(a)[idx[:, a]] for a in range(3)], axis=1)
    kind_sizes, kinds = np.unique(np.round(sizes, 9), axis=0, return_inverse=True)
    return Model(grid=grid, elements=elements, coords=coords, centers=centers, index=idx,
                 sizes=sizes, kinds=np.asarray(kinds).reshape(-1), kind_sizes=kind_sizes)


def assemble(model: Model, E: float, nu: float) -> sparse.csr_matrix:
    """Global stiffness matrix (N/mm)."""
    stack = np.stack([element_matrices(size, nu)[0].ravel() for size in model.kind_sizes]) * E
    dofs = model.dofs
    n = 3 * model.n_nodes
    K = sparse.csr_matrix((n, n))
    block = 15000                                   # elements per block: bounds peak memory
    for start in range(0, len(dofs), block):
        d = dofs[start:start + block]
        rows = np.repeat(d, 24, axis=1).ravel()
        cols = np.tile(d, (1, 24)).ravel()
        data = stack[model.kinds[start:start + block]].ravel()
        K = K + sparse.coo_matrix((data, (rows, cols)), shape=(n, n)).tocsr()
    return K


@dataclass
class Solution:
    displacement: np.ndarray        # (n_nodes, 3) mm
    reactions: np.ndarray           # (n_nodes, 3) N, non-zero only at fixed nodes
    method: str                     # "direct" or "cg"
    iterations: int = 0
    residual: float = 0.0           # relative residual of the linear solve


class SimulationError(ValueError):
    """The simulation could not be set up or solved (message is for the user)."""


def solve(model: Model, E: float, nu: float, fixed: np.ndarray, forces: np.ndarray,
          direct_limit: int = 20000, tol: float = 1e-8, max_iter: int = 30000) -> Solution:
    """Displacements for fully fixed nodes `fixed` (bool mask) and nodal `forces` (N)."""
    fixed = np.asarray(fixed, dtype=bool)
    if fixed.shape != (model.n_nodes,):
        raise SimulationError("`fixed` must be a boolean mask with one entry per node.")
    if not fixed.any():
        raise SimulationError("No point of the part is fixed: it would fly away. Fix a region first.")
    f = np.asarray(forces, dtype=float).reshape(model.n_nodes, 3)
    free_nodes = ~fixed
    if not np.any(f[free_nodes]):
        raise SimulationError("No load is applied on the free part of the model.")
    free = np.repeat(free_nodes, 3)
    K = assemble(model, E, nu)
    Kff = K[free][:, free].tocsc()
    rhs = f.ravel()[free]

    iterations, method = 0, "direct"
    if Kff.shape[0] <= direct_limit:
        try:
            x = splu(Kff).solve(rhs)
        except RuntimeError as exc:                    # singular: part not held properly
            raise SimulationError(
                "The part is not held properly (a piece is loose or the fixed "
                "region is too small). Fix a larger region."
            ) from exc
    else:
        method = "cg"
        diag = Kff.diagonal()
        if np.any(diag <= 0):
            raise SimulationError("The stiffness matrix is not positive: check the fixed region.")
        inv = 1.0 / diag
        count = [0]

        def _count(_):
            count[0] += 1

        x, info = cg(Kff, rhs, rtol=tol, maxiter=max_iter,
                     M=LinearOperator(Kff.shape, matvec=lambda v: inv * v), callback=_count)
        iterations = count[0]
        if info > 0:
            raise SimulationError(
                f"The solver did not converge in {max_iter} iterations. "
                "Use a coarser resolution or check that the part is held firmly."
            )
    if not np.all(np.isfinite(x)):
        raise SimulationError("The solver returned invalid numbers: the part is probably not held.")

    u = np.zeros(3 * model.n_nodes)
    u[free] = x
    full = K @ u
    residual = float(np.linalg.norm(full[free] - rhs) / max(np.linalg.norm(rhs), 1e-30))
    if residual > 1e-4:
        raise SimulationError(
            "The result is not reliable (the part is probably not held firmly, or a "
            "piece of it is loose). Fix a larger region."
        )
    reactions = np.zeros(3 * model.n_nodes)
    reactions[~free] = full[~free] - f.ravel()[~free]
    return Solution(displacement=u.reshape(-1, 3), reactions=reactions.reshape(-1, 3),
                    method=method, iterations=iterations, residual=residual)


def von_mises(stress: np.ndarray) -> np.ndarray:
    """Von Mises equivalent stress from (..., 6) stresses (xx, yy, zz, xy, yz, zx)."""
    sx, sy, sz, txy, tyz, tzx = np.moveaxis(stress, -1, 0)
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                   + 3.0 * (txy ** 2 + tyz ** 2 + tzx ** 2))


@dataclass
class StressField:
    center: np.ndarray      # (n_el,) von Mises at the element centre, MPa
    peak: np.ndarray        # (n_el,) largest von Mises among the 8 Gauss points, MPa
    tensor: np.ndarray      # (n_el, 6) stress tensor at the element centre, MPa


def stresses(model: Model, displacement: np.ndarray, E: float, nu: float) -> StressField:
    """Stresses in every element from the nodal displacements."""
    D = elasticity_matrix(E, nu)
    ue_all = displacement.reshape(-1)[model.dofs]             # (n_el, 24)
    tensor = np.zeros((model.n_elements, 6))
    peak = np.zeros(model.n_elements)
    for kind, size in enumerate(model.kind_sizes):
        sel = np.flatnonzero(model.kinds == kind)
        if len(sel) == 0:
            continue
        ue = ue_all[sel]
        _, recover = element_matrices(size, nu)
        alpha = ue @ recover.T                                # (n, 9)
        B0, _ = _b_matrices(np.zeros(3), size)
        tensor[sel] = ue @ (D @ B0).T                         # incompatible modes vanish at the centre
        best = np.zeros(len(sel))
        for gp in _GAUSS:
            B, G = _b_matrices(gp, size)
            s = ue @ (D @ B).T + alpha @ (D @ G).T
            np.maximum(best, von_mises(s), out=best)
        peak[sel] = best
    return StressField(center=von_mises(tensor), peak=peak, tensor=tensor)


def strain_energy(solution: Solution, forces: np.ndarray) -> float:
    """Work done by the loads (N*mm) = 2 x the elastic energy stored in the part."""
    return float(np.sum(np.asarray(forces, dtype=float).reshape(-1, 3) * solution.displacement))
