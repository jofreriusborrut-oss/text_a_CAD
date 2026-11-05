"""A small triangle-mesh toolbox that only needs numpy.

The app works with the STL that CadQuery exports. This module reads and
writes STL files (binary and ASCII) and measures the mesh: size, volume,
whether it is closed, local wall thickness and overhangs for 3D printing.

A mesh is stored as an array `triangles` with shape (n, 3, 3):
n triangles x 3 corners x (x, y, z), in millimetres.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import cached_property

import numpy as np


class MeshError(ValueError):
    """The STL data could not be understood."""


@dataclass
class Mesh:
    triangles: np.ndarray           # (n, 3, 3) float64

    def __post_init__(self) -> None:
        self.triangles = np.ascontiguousarray(self.triangles, dtype=np.float64)
        if self.triangles.ndim != 3 or self.triangles.shape[1:] != (3, 3):
            raise MeshError("triangles must have shape (n, 3, 3)")

    def __len__(self) -> int:
        return len(self.triangles)

    # -- basic geometry -----------------------------------------------------

    @cached_property
    def _cross(self) -> np.ndarray:
        t = self.triangles
        return np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])

    @cached_property
    def areas(self) -> np.ndarray:
        return 0.5 * np.linalg.norm(self._cross, axis=1)

    @cached_property
    def normals(self) -> np.ndarray:
        """Unit normal of every triangle (zero for degenerate triangles)."""
        length = np.linalg.norm(self._cross, axis=1, keepdims=True)
        return np.divide(self._cross, length, out=np.zeros_like(self._cross), where=length > 0)

    @cached_property
    def centroids(self) -> np.ndarray:
        return self.triangles.mean(axis=1)

    @cached_property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        pts = self.triangles.reshape(-1, 3)
        return pts.min(axis=0), pts.max(axis=0)

    @property
    def size(self) -> np.ndarray:
        lo, hi = self.bounds
        return hi - lo

    @cached_property
    def area(self) -> float:
        return float(self.areas.sum())

    @cached_property
    def volume(self) -> float:
        """Enclosed volume (mm3). Only meaningful for a closed mesh."""
        t = self.triangles
        return float(abs(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()) / 6.0)

    @cached_property
    def center_of_mass(self) -> np.ndarray:
        """Centre of mass of the enclosed solid, assuming uniform density."""
        t = self.triangles
        signed = np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])) / 6.0
        total = signed.sum()
        if abs(total) < 1e-12:
            return self.centroids.mean(axis=0)
        # Each tetrahedron (origin + triangle) has its centroid at the mean of its 4 corners.
        return (signed[:, None] * t.sum(axis=1) / 4.0).sum(axis=0) / total

    # -- topology -----------------------------------------------------------

    def is_watertight(self, tol: float = 1e-5) -> bool:
        """True when every edge is shared by exactly two triangles (closed surface)."""
        if len(self) == 0:
            return False
        keys = np.round(self.triangles.reshape(-1, 3) / tol).astype(np.int64)
        _, idx = np.unique(keys, axis=0, return_inverse=True)
        faces = idx.reshape(-1, 3)
        keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
        faces = faces[keep]                      # ignore triangles squashed to a line
        if len(faces) == 0:
            return False
        edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        edges.sort(axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        return bool(np.all(counts == 2))

    # -- sampling and ray casting ------------------------------------------

    def sample_surface(self, n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
        """n random points spread evenly over the surface, and the triangle of each."""
        rng = np.random.default_rng(seed)
        areas = self.areas
        total = areas.sum()
        if total <= 0:
            raise MeshError("The mesh has no area.")
        face = rng.choice(len(areas), size=n, p=areas / total)
        r1 = np.sqrt(rng.random(n))
        r2 = rng.random(n)
        t = self.triangles[face]
        pts = (1 - r1)[:, None] * t[:, 0] + (r1 * (1 - r2))[:, None] * t[:, 1] + (r1 * r2)[:, None] * t[:, 2]
        return pts, face

    def first_hit(self, origins: np.ndarray, directions: np.ndarray, eps: float = 1e-6,
                  chunk_cells: int = 2_000_000) -> np.ndarray:
        """Distance from each ray origin to the first triangle it hits (inf if none).

        Moller-Trumbore intersection, done for blocks of rays against all the
        triangles at once so that memory use stays bounded.
        """
        tri = self.triangles
        v0 = tri[:, 0]
        e1 = tri[:, 1] - v0
        e2 = tri[:, 2] - v0
        n_rays = len(origins)
        out = np.full(n_rays, np.inf)
        step = max(1, chunk_cells // max(len(tri), 1))
        for start in range(0, n_rays, step):
            o = origins[start:start + step][:, None, :]          # (r, 1, 3)
            d = directions[start:start + step][:, None, :]
            p = np.cross(d, e2[None])                            # (r, t, 3)
            det = np.einsum("rtk,tk->rt", p, e1)
            ok = np.abs(det) > 1e-12
            inv = np.divide(1.0, det, out=np.zeros_like(det), where=ok)
            s = o - v0[None]
            u = np.einsum("rtk,rtk->rt", s, p) * inv
            q = np.cross(s, e1[None])
            v = np.einsum("rtk,rtk->rt", np.broadcast_to(d, q.shape), q) * inv
            dist = np.einsum("rtk,tk->rt", q, e2) * inv
            hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (dist > eps)
            dist = np.where(hit, dist, np.inf)
            out[start:start + step] = dist.min(axis=1)
        return out

    def wall_thickness(self, n_samples: int = 2000, seed: int = 0,
                       max_work: float = 3.0e7) -> np.ndarray:
        """Local thickness (mm) at points spread over the surface.

        From each point a ray is shot INTO the material (against the surface
        normal). The distance to where it leaves the part is the thickness
        there. The number of rays is reduced for very dense meshes so that the
        check always takes a few seconds at most.
        """
        n = int(min(n_samples, max(300, max_work // max(len(self), 1))))
        pts, face = self.sample_surface(n, seed)
        normals = self.normals[face]
        eps = 1e-3
        dist = self.first_hit(pts - normals * eps, -normals, eps=eps)
        dist = dist[np.isfinite(dist)]
        return dist + eps

    # -- 3D printing --------------------------------------------------------

    def overhang_area(self, up: np.ndarray, angle_deg: float = 45.0, bed_tol: float = 0.05) -> float:
        """Area (mm2) of faces that would need support when printing with `up` as vertical.

        A face needs support when it looks downwards more steeply than
        `angle_deg` from the vertical, unless it rests on the print bed.
        """
        up = np.asarray(up, dtype=float)
        up = up / np.linalg.norm(up)
        down_component = -(self.normals @ up)                    # 1 = facing straight down
        heights = self.triangles @ up                            # (n, 3)
        bed = heights.min()
        on_bed = heights.max(axis=1) <= bed + bed_tol
        needs = (down_component > np.cos(np.radians(angle_deg)) + 1e-9) & ~on_bed
        return float(self.areas[needs].sum())

    def bed_contact_area(self, up: np.ndarray, bed_tol: float = 0.05) -> float:
        up = np.asarray(up, dtype=float)
        up = up / np.linalg.norm(up)
        heights = self.triangles @ up
        on_bed = heights.max(axis=1) <= heights.min() + bed_tol
        return float(self.areas[on_bed].sum())


# ---------------------------------------------------------------------------
# STL reading and writing
# ---------------------------------------------------------------------------

def _looks_binary(data: bytes) -> bool:
    if len(data) < 84:
        return False
    (count,) = struct.unpack_from("<I", data, 80)
    return len(data) == 84 + 50 * count


def load_stl(data: bytes) -> Mesh:
    """Read an STL file given as bytes (binary or ASCII)."""
    if _looks_binary(data):
        (count,) = struct.unpack_from("<I", data, 80)
        if count == 0:
            raise MeshError("The STL file has no triangles.")
        raw = np.frombuffer(data, dtype=np.uint8, count=50 * count, offset=84).reshape(count, 50)
        floats = raw[:, :48].copy().view("<f4").reshape(count, 4, 3)
        return Mesh(floats[:, 1:4].astype(np.float64))
    text = data.decode("ascii", errors="ignore")
    if "vertex" not in text:
        raise MeshError("Not an STL file (neither a valid binary nor an ASCII STL).")
    values = [line.split()[1:4] for line in text.splitlines() if line.lstrip().startswith("vertex")]
    arr = np.array(values, dtype=np.float64)
    if len(arr) == 0 or len(arr) % 3:
        raise MeshError("The ASCII STL file is damaged (vertices are not in groups of three).")
    return Mesh(arr.reshape(-1, 3, 3))


def dump_stl(mesh: Mesh, name: str = "textacad") -> bytes:
    """Write the mesh as a binary STL."""
    count = len(mesh)
    out = np.zeros(count, dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    out["n"] = mesh.normals
    out["v"] = mesh.triangles
    header = name.encode("ascii", errors="ignore")[:80].ljust(80, b" ")
    return header + struct.pack("<I", count) + out.tobytes()


# ---------------------------------------------------------------------------
# Simple shapes (used by the tests and the demo mode, no CadQuery needed)
# ---------------------------------------------------------------------------

def box_mesh(size: tuple[float, float, float], origin: tuple[float, float, float] = (0, 0, 0)) -> Mesh:
    """Axis-aligned box with outward normals, from `origin` to `origin + size`."""
    x0, y0, z0 = origin
    x1, y1, z1 = x0 + size[0], y0 + size[1], z0 + size[2]
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], dtype=float)
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return Mesh(v[np.array(faces)])


def merge(*meshes: Mesh) -> Mesh:
    return Mesh(np.concatenate([m.triangles for m in meshes]))


def flipped(mesh: Mesh) -> Mesh:
    """Same surface with the normals pointing the other way (used for cavities)."""
    return Mesh(mesh.triangles[:, ::-1])


def cylinder_mesh(radius: float, height: float, center: tuple[float, float] = (0, 0),
                  z0: float = 0.0, segments: int = 48) -> Mesh:
    """Closed cylinder along Z with outward normals."""
    ang = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring = np.stack([center[0] + radius * np.cos(ang), center[1] + radius * np.sin(ang)], axis=1)
    nxt = np.roll(ring, -1, axis=0)
    z1 = z0 + height
    tris = []
    c0 = (center[0], center[1], z0)
    c1 = (center[0], center[1], z1)
    for a, b in zip(ring, nxt):
        a0, b0, a1, b1 = (*a, z0), (*b, z0), (*a, z1), (*b, z1)
        tris += [(a0, b0, b1), (a0, b1, a1), (c0, b0, a0), (c1, a1, b1)]
    return Mesh(np.array(tris, dtype=float))
