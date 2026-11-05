"""Turn a closed triangle mesh into a grid of small boxes (voxels).

The simulation (fea.py) works on this grid: every box that lies inside the
part becomes one finite element. Only numpy is needed.

Two ideas keep the grid faithful to the part:

1. The grid lines are placed ON the flat faces of the part that are parallel
   to the X, Y and Z planes (the usual case for plates, brackets and
   housings). A 4 mm wall is then exactly 4 mm in the simulation instead of
   being rounded to a whole number of cubes. The boxes are therefore not all
   the same size ("rectilinear grid").
2. A box is solid when its centre is inside the part. For every (x, y) column
   of centres a vertical line is intersected with the mesh; going up along
   the line each crossing switches between outside and inside.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mesh import Mesh


@dataclass
class VoxelGrid:
    solid: np.ndarray                                   # (nx, ny, nz) bool: True where there is material
    edges: tuple[np.ndarray, np.ndarray, np.ndarray]    # grid line positions along x, y, z (mm)

    @classmethod
    def uniform(cls, solid: np.ndarray, origin, pitch: float) -> "VoxelGrid":
        """Grid of equal cubes of side `pitch` starting at `origin`."""
        origin = np.asarray(origin, dtype=float)
        edges = tuple(origin[a] + np.arange(solid.shape[a] + 1) * float(pitch) for a in range(3))
        return cls(np.asarray(solid, dtype=bool), edges)

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.solid.shape

    @property
    def count(self) -> int:
        return int(self.solid.sum())

    def sizes(self, axis: int) -> np.ndarray:
        """Box sizes (mm) along one axis."""
        return np.diff(self.edges[axis])

    def centers_1d(self, axis: int) -> np.ndarray:
        e = self.edges[axis]
        return (e[:-1] + e[1:]) / 2

    @property
    def pitch(self) -> float:
        """Typical box size (mm): geometric mean of the average size along each axis."""
        return float(np.prod([self.sizes(a).mean() for a in range(3)]) ** (1 / 3))

    @property
    def cell_volumes(self) -> np.ndarray:
        hx, hy, hz = (self.sizes(a) for a in range(3))
        return hx[:, None, None] * hy[None, :, None] * hz[None, None, :]

    @property
    def volume(self) -> float:
        return float(self.cell_volumes[self.solid].sum())

    def centers(self) -> np.ndarray:
        """Centre (mm) of every solid box, shape (count, 3)."""
        idx = np.argwhere(self.solid)
        return np.stack([self.centers_1d(a)[idx[:, a]] for a in range(3)], axis=1)


# ---------------------------------------------------------------------------
# Where to put the grid lines
# ---------------------------------------------------------------------------

def flat_face_planes(mesh: Mesh, axis: int, min_area: float) -> tuple[np.ndarray, np.ndarray]:
    """Positions along `axis` of the flat faces perpendicular to it, with their areas."""
    aligned = np.abs(mesh.normals[:, axis]) > 0.99999
    if not aligned.any():
        return np.empty(0), np.empty(0)
    pos = mesh.triangles[aligned][:, :, axis].mean(axis=1)
    key = np.round(pos, 4)
    uniq, inv = np.unique(key, return_inverse=True)
    area = np.bincount(inv, weights=mesh.areas[aligned])
    keep = area >= min_area
    return uniq[keep], area[keep]


def grid_lines(lo: float, hi: float, pitch: float, planes: np.ndarray = (), areas: np.ndarray = ()) -> np.ndarray:
    """Grid line positions between lo and hi: they include `planes` and are about `pitch` apart."""
    marks = {float(lo): np.inf, float(hi): np.inf}
    for p, a in zip(planes, areas):
        if lo < p < hi:
            marks[float(p)] = max(float(a), marks.get(float(p), 0.0))
    pts = sorted(marks)
    # Drop planes that are much closer than the pitch to a more important one:
    # they would create needle-thin boxes (typically chamfers and small steps).
    min_gap = 0.3 * pitch
    changed = True
    while changed and len(pts) > 2:
        changed = False
        gaps = np.diff(pts)
        i = int(np.argmin(gaps))
        if gaps[i] < min_gap:
            a, b = pts[i], pts[i + 1]
            drop = a if marks[a] < marks[b] else b
            if np.isinf(marks[drop]):                 # never drop the two ends
                drop = b if drop == a else a
            if not np.isinf(marks[drop]):
                pts.remove(drop)
                changed = True
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(round((b - a) / pitch)))
        out.extend(a + (b - a) * (k + 1) / n for k in range(n))
    return np.array(out)


# ---------------------------------------------------------------------------
# Inside / outside test
# ---------------------------------------------------------------------------

def _edge(ax, ay, bx, by, px, py):
    """Twice the signed area of triangle (a, b, p): > 0 when p is left of a->b."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def fill(mesh: Mesh, edges: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    """Boolean array telling which boxes of the grid have their centre inside the mesh."""
    ex, ey, ez = (np.asarray(e, dtype=float) for e in edges)
    nx, ny, nz = len(ex) - 1, len(ey) - 1, len(ez) - 1
    # Tiny irrational shift: keeps sample lines away from mesh edges and
    # vertices, which often sit exactly on round coordinates in CAD parts.
    span = max(ex[-1] - ex[0], ey[-1] - ey[0], 1e-9)
    cx = (ex[:-1] + ex[1:]) / 2 + span * 1.0e-7 * np.sqrt(2.0)
    cy = (ey[:-1] + ey[1:]) / 2 + span * 1.0e-7 * np.sqrt(3.0)
    cz = (ez[:-1] + ez[1:]) / 2

    tri = mesh.triangles
    x, y, z = tri[:, :, 0], tri[:, :, 1], tri[:, :, 2]
    area2 = _edge(x[:, 0], y[:, 0], x[:, 1], y[:, 1], x[:, 2], y[:, 2])
    keep = np.abs(area2) > 1e-12                      # vertical triangles are never crossed
    x, y, z, area2 = x[keep], y[keep], z[keep], area2[keep]

    # Columns whose centre falls inside the bounding box of each triangle.
    i0 = np.searchsorted(cx, x.min(axis=1), side="left")
    i1 = np.searchsorted(cx, x.max(axis=1), side="right")
    j0 = np.searchsorted(cy, y.min(axis=1), side="left")
    j1 = np.searchsorted(cy, y.max(axis=1), side="right")
    wi = np.maximum(i1 - i0, 0)
    wj = np.maximum(j1 - j0, 0)
    cells = wi * wj

    crossings = np.zeros((nx, ny, nz + 1), dtype=np.int32)
    order = np.argsort(cells, kind="stable")
    cells_sorted = cells[order]
    start = int(np.searchsorted(cells_sorted, 1))     # triangles covering no column are skipped
    budget = 4_000_000                                # (triangle, column) pairs handled per block
    while start < len(order):
        total = np.cumsum(cells_sorted[start:])
        stop = start + max(1, int(np.searchsorted(total, budget, side="right")))
        t = order[start:stop]
        start = stop
        c = cells[t]
        tid = np.repeat(np.arange(len(t)), c)         # which triangle each candidate belongs to
        local = np.arange(int(c.sum())) - np.repeat(np.cumsum(c) - c, c)
        wj_t = wj[t][tid]
        ii = i0[t][tid] + local // wj_t
        jj = j0[t][tid] + local % wj_t
        px, py = cx[ii], cy[jj]
        tt = t[tid]
        w0 = _edge(x[tt, 1], y[tt, 1], x[tt, 2], y[tt, 2], px, py)
        w1 = _edge(x[tt, 2], y[tt, 2], x[tt, 0], y[tt, 0], px, py)
        w2 = _edge(x[tt, 0], y[tt, 0], x[tt, 1], y[tt, 1], px, py)
        a = area2[tt]
        sign = np.sign(a)
        inside = (w0 * sign >= 0) & (w1 * sign >= 0) & (w2 * sign >= 0)
        if not inside.any():
            continue
        ii, jj, tt, a = ii[inside], jj[inside], tt[inside], a[inside]
        zc = (w0[inside] * z[tt, 0] + w1[inside] * z[tt, 1] + w2[inside] * z[tt, 2]) / a
        k = np.searchsorted(cz, zc, side="left")      # first box (along z) whose centre is above the crossing
        np.add.at(crossings, (ii, jj, k), 1)

    below = np.cumsum(crossings[:, :, :nz], axis=2)
    return (below % 2) == 1


def voxelize(mesh: Mesh, pitch: float, conform: bool = True) -> VoxelGrid:
    """Voxel grid of the solid enclosed by `mesh`, with boxes of about `pitch` mm.

    With conform=True (default) the grid lines sit on the flat faces of the
    part, so walls parallel to the axes keep their exact thickness.
    """
    if pitch <= 0:
        raise ValueError("pitch must be positive")
    lo, hi = mesh.bounds
    edges = []
    for axis in range(3):
        if conform:
            planes, areas = flat_face_planes(mesh, axis, min_area=0.25 * pitch * pitch)
        else:
            planes, areas = (), ()
        if hi[axis] - lo[axis] < 1e-9:
            edges.append(np.array([lo[axis] - pitch / 2, lo[axis] + pitch / 2]))
        else:
            edges.append(grid_lines(lo[axis], hi[axis], pitch, planes, areas))
    edges = tuple(edges)
    return VoxelGrid(solid=fill(mesh, edges), edges=edges)


def pitch_for_count(mesh: Mesh, target: int, min_pitch: float = 0.05) -> float:
    """Box size that gives roughly `target` solid boxes for this mesh."""
    volume = mesh.volume
    if volume <= 0:
        lo, hi = mesh.bounds
        volume = float(np.prod(np.maximum(hi - lo, 1e-6)))
    return max(float((volume / max(target, 1)) ** (1.0 / 3.0)), min_pitch)
