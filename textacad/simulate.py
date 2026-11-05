"""Set up and run a stress simulation of a part from its STL.

A "load case" says where the part is held and where it is pushed:

    LOAD_CASE = {
        "description": "Bolted to the wall, 50 N pulling down at the tip",
        "fixed": [{"type": "hole", "axis": "z", "center": [0, 20, 0], "diameter": 6.6}],
        "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -50]}],
        "accel_g": [0, 0, 0],      # optional: acceleration in g acting on the part's own mass
    }

Regions (all coordinates in mm, in the coordinates of the part):
    {"type": "side", "side": "-x"}                         the outer face on that side of the part
    {"type": "box", "min": [x, y, z], "max": [x, y, z]}    everything inside a box
    {"type": "hole", "axis": "z", "center": [x, y, z], "diameter": d}
                                                           the wall of a hole (or a pin) around an axis
    {"type": "point", "center": [x, y, z], "radius": r}    everything within r of a point

Forces are in newtons and are spread evenly over the selected region.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field

import numpy as np

from . import fea
from .fea import SimulationError
from .materials import Material, get_material
from .mesh import Mesh
from .voxel import pitch_for_count, voxelize

RESOLUTIONS = {"draft": 3000, "normal": 12000, "fine": 30000}
G = 9.80665                                   # m/s2
_AXES = {"x": 0, "y": 1, "z": 2}


# ---------------------------------------------------------------------------
# Load case
# ---------------------------------------------------------------------------

def _vec3(value, what: str) -> np.ndarray:
    try:
        v = np.array([float(x) for x in value], dtype=float)
    except (TypeError, ValueError):
        raise SimulationError(f"{what} must be a list of three numbers.") from None
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise SimulationError(f"{what} must be a list of three numbers.")
    return v


def normalize_region(region: dict) -> dict:
    """Check a region description and return it in a clean, JSON-friendly form."""
    if not isinstance(region, dict) or "type" not in region:
        raise SimulationError('A region must be a dictionary with a "type" (side, box, hole or point).')
    kind = str(region["type"]).lower()
    if kind == "side":
        side = str(region.get("side", "")).lower().replace(" ", "")
        if len(side) != 2 or side[0] not in "+-" or side[1] not in _AXES:
            raise SimulationError('A "side" region needs "side": one of -x, +x, -y, +y, -z, +z.')
        return {"type": "side", "side": side, "depth": max(float(region.get("depth", 0.0)), 0.0)}
    if kind == "box":
        lo, hi = _vec3(region.get("min"), "box min"), _vec3(region.get("max"), "box max")
        return {"type": "box", "min": np.minimum(lo, hi).tolist(), "max": np.maximum(lo, hi).tolist()}
    if kind in ("hole", "cylinder", "pin"):
        axis = str(region.get("axis", "z")).lower()
        if axis not in _AXES:
            raise SimulationError('A "hole" region needs "axis": x, y or z.')
        diameter = float(region.get("diameter", 2 * float(region.get("radius", 0))))
        if diameter <= 0:
            raise SimulationError('A "hole" region needs a positive "diameter".')
        return {"type": "hole", "axis": axis, "center": _vec3(region.get("center"), "hole center").tolist(),
                "diameter": diameter}
    if kind in ("point", "sphere"):
        radius = float(region.get("radius", 0))
        if radius <= 0:
            raise SimulationError('A "point" region needs a positive "radius".')
        return {"type": "point", "center": _vec3(region.get("center"), "point center").tolist(), "radius": radius}
    raise SimulationError(f"Unknown region type {kind!r} (use side, box, hole or point).")


@dataclass
class LoadCase:
    fixed: list[dict]
    loads: list[dict]                         # each: {"region": {...}, "force": [fx, fy, fz]}
    accel_g: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "LoadCase":
        if not isinstance(data, dict):
            raise SimulationError("The load case must be a dictionary.")
        fixed = data.get("fixed") or []
        if isinstance(fixed, dict):
            fixed = [fixed]
        loads = data.get("loads") or []
        if isinstance(loads, dict):
            loads = [loads]
        fixed = [normalize_region(r) for r in fixed]
        clean_loads = []
        for load in loads:
            if not isinstance(load, dict) or "region" not in load or "force" not in load:
                raise SimulationError('Each load needs a "region" and a "force" [fx, fy, fz] in newtons.')
            clean_loads.append({"region": normalize_region(load["region"]),
                                "force": _vec3(load["force"], "force").tolist()})
        accel = _vec3(data.get("accel_g") or [0, 0, 0], "accel_g").tolist()
        if not fixed:
            raise SimulationError("The load case does not say where the part is held (\"fixed\").")
        if not clean_loads and not any(accel):
            raise SimulationError("The load case has no load (\"loads\" or \"accel_g\").")
        return cls(fixed=fixed, loads=clean_loads, accel_g=accel,
                   description=str(data.get("description", ""))[:300])

    def as_dict(self) -> dict:
        return {"description": self.description, "fixed": self.fixed, "loads": self.loads,
                "accel_g": self.accel_g}


def default_load_case(mesh: Mesh, force_n: float = 50.0) -> LoadCase:
    """A generic first test: hold the part by its largest flat side and push the far end.

    The part is held on the side with the most area at its extreme (usually
    the base) and the load pushes sideways on the opposite end, which bends
    the part. It is only a starting point for the user to edit.
    """
    lo, hi = mesh.bounds
    best = None
    for axis, name in enumerate("xyz"):
        for sign, bound in (("-", lo[axis]), ("+", hi[axis])):
            on = np.all(np.abs(mesh.triangles[:, :, axis] - bound) < 1e-6 * max(hi[axis] - lo[axis], 1), axis=1)
            area = float(mesh.areas[on].sum())
            if best is None or area > best[0]:
                best = (area, sign, name, axis)
    _, sign, name, axis = best
    opposite = ("+" if sign == "-" else "-") + name
    size = hi - lo
    others = [a for a in range(3) if a != axis]
    push_axis = others[int(np.argmin(size[others]))]          # push along the thinner direction: worst case
    force = [0.0, 0.0, 0.0]
    force[push_axis] = -force_n
    return LoadCase(fixed=[{"type": "side", "side": sign + name, "depth": 0.0}],
                    loads=[{"region": {"type": "side", "side": opposite, "depth": 0.0}, "force": force}],
                    description="auto")


def select_nodes(model: fea.Model, region: dict) -> np.ndarray:
    """Boolean mask of the nodes of the model that belong to a region."""
    xyz = model.coords
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    span = float(np.max(hi - lo))
    tol = 1e-6 * max(span, 1.0)
    kind = region["type"]
    if kind == "side":
        axis = _AXES[region["side"][1]]
        depth = region.get("depth", 0.0) + tol
        if region["side"][0] == "-":
            return xyz[:, axis] <= lo[axis] + depth
        return xyz[:, axis] >= hi[axis] - depth
    if kind == "box":
        a, b = np.array(region["min"]) - tol, np.array(region["max"]) + tol
        return np.all((xyz >= a) & (xyz <= b), axis=1)
    if kind == "hole":
        axis = _AXES[region["axis"]]
        others = [a for a in range(3) if a != axis]
        c = np.array(region["center"])
        r = np.hypot(xyz[:, others[0]] - c[others[0]], xyz[:, others[1]] - c[others[1]])
        pitch = float(np.mean([model.grid.sizes(a).mean() for a in others]))
        return r <= region["diameter"] / 2 + 0.75 * pitch
    if kind == "point":
        d = np.linalg.norm(xyz - np.array(region["center"]), axis=1)
        return d <= region["radius"] + 0.5 * model.grid.pitch
    raise SimulationError(f"Unknown region type {kind!r}.")


# Corner numbers of the six faces of a brick (see fea._CORNERS), listed so that
# the face normal points out of the element.
_FACES = {
    (0, -1): (0, 4, 7, 3), (0, 1): (1, 2, 6, 5),
    (1, -1): (0, 1, 5, 4), (1, 1): (3, 7, 6, 2),
    (2, -1): (0, 3, 2, 1), (2, 1): (4, 5, 6, 7),
}


def surface_mesh(model: fea.Model) -> tuple[np.ndarray, np.ndarray]:
    """Outer skin of the finite element model.

    Returns (nodes, triangles): the numbers of the nodes on the surface and
    the triangles as indices into that list. A face of an element belongs to
    the skin when there is no element on its other side.
    """
    solid = np.pad(model.grid.solid, 1)
    idx = model.index + 1                                  # position of each element in the padded grid
    quads = []
    for (axis, sign), corners in _FACES.items():
        neighbour = idx.copy()
        neighbour[:, axis] += sign
        free = ~solid[neighbour[:, 0], neighbour[:, 1], neighbour[:, 2]]
        quads.append(model.elements[free][:, corners])
    quads = np.concatenate(quads)
    nodes, inverse = np.unique(quads, return_inverse=True)
    q = inverse.reshape(quads.shape)
    triangles = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
    return nodes, triangles


def describe_region(region: dict) -> str:
    kind = region["type"]
    if kind == "side":
        return f"side {region['side']}"
    if kind == "box":
        return f"box {region['min']} .. {region['max']}"
    if kind == "hole":
        return f"hole d={region['diameter']:g} along {region['axis']} at {region['center']}"
    return f"point {region['center']} r={region['radius']:g}"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    material: Material
    load_case: LoadCase
    resolution: str
    pitch: float                         # typical element size, mm
    n_elements: int
    n_nodes: int
    seconds: float
    method: str
    max_displacement: float              # mm
    max_displacement_at: list[float]
    max_stress: float                    # MPa, away from the held and loaded regions
    max_stress_at: list[float]
    max_stress_at_supports: float        # MPa, including the held/loaded regions (often exaggerated)
    applied_force: list[float]           # N, sum of all loads
    reaction_force: list[float]          # N, sum of reactions at the held region
    equilibrium_error: float             # |applied + reaction| / |applied|
    voxel_volume: float                  # mm3 of the simulated model
    mesh_volume: float                   # mm3 of the real part (from the STL)
    safety_factor: float                 # weak-axis yield / max_stress
    safety_factor_in_plane: float        # full yield / max_stress
    stiffness: float | None              # N/mm at the loaded region (force / deflection along the force)
    convergence: dict | None = None      # {"coarse_displacement", "change_percent", ...}
    warnings: list[str] = field(default_factory=list)
    # Fields for drawing (not part of the summary): the skin of the simulated model.
    skin_points: np.ndarray | None = None            # (n, 3) mm
    skin_triangles: np.ndarray | None = None         # (m, 3) indices into skin_points
    skin_stress: np.ndarray | None = None            # (n,) MPa (von Mises)
    skin_displacement: np.ndarray | None = None      # (n, 3) mm

    @property
    def volume_error(self) -> float:
        return self.voxel_volume / self.mesh_volume - 1 if self.mesh_volume > 0 else 0.0

    def summary(self) -> dict:
        """Plain numbers for the interface and the report (no big arrays)."""
        m = self.material
        return {
            "material": {"id": m.id, "name": m.name, "E": m.E, "yield": m.yield_strength,
                         "weak_axis_strength": round(m.weak_axis_strength, 1), "process": m.process},
            "load_case": self.load_case.as_dict(),
            "resolution": self.resolution,
            "pitch_mm": round(self.pitch, 3),
            "n_elements": self.n_elements,
            "n_nodes": self.n_nodes,
            "seconds": round(self.seconds, 2),
            "method": self.method,
            "max_displacement_mm": float(f"{self.max_displacement:.4g}"),
            "max_displacement_at": [round(v, 2) for v in self.max_displacement_at],
            "max_stress_mpa": float(f"{self.max_stress:.4g}"),
            "max_stress_at": [round(v, 2) for v in self.max_stress_at],
            "max_stress_at_supports_mpa": float(f"{self.max_stress_at_supports:.4g}"),
            "applied_force_n": [round(v, 4) for v in self.applied_force],
            "reaction_force_n": [round(v, 4) for v in self.reaction_force],
            "equilibrium_error": float(f"{self.equilibrium_error:.2g}"),
            "volume_error": round(self.volume_error, 4),
            "safety_factor": float(f"{self.safety_factor:.3g}"),
            "safety_factor_in_plane": float(f"{self.safety_factor_in_plane:.3g}"),
            "stiffness_n_per_mm": None if self.stiffness is None else float(f"{self.stiffness:.4g}"),
            "convergence": self.convergence,
            "warnings": self.warnings,
        }

    def drawing_data(self, scale_max: float | None = None) -> dict:
        """The simulated model with its stresses and displacements, for the 3D viewer.

        Arrays are packed as base64: points and displacement as float32
        (x, y, z per node), triangles as uint32, stress level as one byte
        per node (0 = no stress, 255 = scale_max or more).
        """
        if self.skin_points is None:
            return {}
        top = max(float(scale_max or self.max_stress or self.skin_stress.max() or 1.0), 1e-12)
        level = np.clip(self.skin_stress / top, 0, 1)

        def pack(array, dtype) -> str:
            return base64.b64encode(np.ascontiguousarray(array, dtype=dtype).tobytes()).decode("ascii")

        return {
            "points": pack(self.skin_points, "<f4"),
            "triangles": pack(self.skin_triangles, "<u4"),
            "stress_levels": pack((level * 255).round(), np.uint8),
            "displacement": pack(self.skin_displacement, "<f4"),
            "scale_max_mpa": float(f"{top:.4g}"),
            "max_displacement_mm": float(f"{self.max_displacement:.4g}"),
        }


def _solve_once(mesh: Mesh, case: LoadCase, material: Material, target: int):
    pitch = pitch_for_count(mesh, target)
    grid = voxelize(mesh, pitch)
    if grid.count == 0:
        raise SimulationError("The part is too thin for this resolution. Try a finer resolution.")
    model = fea.build_model(grid)

    fixed = np.zeros(model.n_nodes, dtype=bool)
    for region in case.fixed:
        sel = select_nodes(model, region)
        if not sel.any():
            raise SimulationError(f"The held region selects no material: {describe_region(region)}.")
        fixed |= sel
    if fixed.all():
        raise SimulationError("The whole part is held: nothing can deform. Hold a smaller region.")

    forces = np.zeros((model.n_nodes, 3))
    loaded = np.zeros(model.n_nodes, dtype=bool)
    for load in case.loads:
        sel = select_nodes(model, load["region"]) & ~fixed
        if not sel.any():
            raise SimulationError(
                f"The loaded region selects no free material: {describe_region(load['region'])}."
            )
        forces[sel] += np.array(load["force"]) / sel.sum()
        loaded |= sel
    accel = np.array(case.accel_g, dtype=float)
    if np.any(accel):
        # Weight of every element times the acceleration, shared by its 8 corners.
        mass_kg = model.volumes * material.density * 1e-6          # mm3 * g/cm3 -> kg
        per_corner = (mass_kg[:, None] * accel[None, :] * G) / 8.0
        for c in range(8):
            np.add.at(forces, model.elements[:, c], per_corner)
        forces[fixed] = 0.0

    solution = fea.solve(model, material.E, material.nu, fixed, forces)
    field_ = fea.stresses(model, solution.displacement, material.E, material.nu)
    return model, fixed, loaded, forces, solution, field_


def run_simulation(mesh: Mesh, load_case: LoadCase | dict, material: Material | str = "petg",
                   resolution: str = "normal", check_convergence: bool = True) -> SimResult:
    """Run the simulation and return the results."""
    start = time.monotonic()
    if isinstance(load_case, dict):
        load_case = LoadCase.from_dict(load_case)
    if isinstance(material, str):
        material = get_material(material)
    if resolution not in RESOLUTIONS:
        raise SimulationError(f"Unknown resolution {resolution!r} (use draft, normal or fine).")
    if not mesh.is_watertight():
        raise SimulationError("The part is not a closed solid, so it cannot be simulated.")

    target = RESOLUTIONS[resolution]
    model, fixed, loaded, forces, sol, st = _solve_once(mesh, load_case, material, target)

    disp = np.linalg.norm(sol.displacement, axis=1)
    i_disp = int(np.argmax(disp))

    # Stress peaks right at the supports and load points are artefacts of the
    # idealised supports, so they are reported separately.
    touched = fixed | loaded
    near = touched[model.elements].any(axis=1)
    peak = st.peak
    if (~near).any():
        candidates = np.where(near, -1.0, peak)
        i_stress = int(np.argmax(candidates))
        max_stress = float(peak[i_stress])
    else:
        i_stress = int(np.argmax(peak))
        max_stress = float(peak[i_stress])

    applied = forces.sum(axis=0)
    reaction = sol.reactions.sum(axis=0)
    eq_err = float(np.linalg.norm(applied + reaction) / max(np.linalg.norm(applied), 1e-30))

    stiffness = None
    if load_case.loads and loaded.any():
        f_total = forces[loaded].sum(axis=0)
        norm = np.linalg.norm(f_total)
        if norm > 0:
            along = float(np.mean(sol.displacement[loaded] @ (f_total / norm)))
            if along > 1e-12:
                stiffness = float(norm / along)

    warnings: list[str] = []
    convergence = None
    if check_convergence and resolution != "draft":
        try:
            m2, fx2, ld2, _, sol2, st2 = _solve_once(mesh, load_case, material, max(target // 4, 800))
            d2 = float(np.linalg.norm(sol2.displacement, axis=1).max())
            near2 = (fx2 | ld2)[m2.elements].any(axis=1)
            s2 = float(st2.peak[~near2].max()) if (~near2).any() else float(st2.peak.max())
            change_d = abs(disp[i_disp] - d2) / max(disp[i_disp], 1e-30) * 100
            change_s = abs(max_stress - s2) / max(max_stress, 1e-30) * 100
            convergence = {"coarse_elements": m2.n_elements, "coarse_displacement_mm": float(f"{d2:.4g}"),
                           "coarse_stress_mpa": float(f"{s2:.4g}"),
                           "displacement_change_percent": round(change_d, 1),
                           "stress_change_percent": round(change_s, 1)}
            if change_d > 10:
                warnings.append("not_converged_displacement")
            if change_s > 25:
                warnings.append("not_converged_stress")
        except SimulationError:
            convergence = None

    voxel_volume = float(model.volumes.sum())
    if abs(voxel_volume / mesh.volume - 1) > 0.08:
        warnings.append("coarse_geometry")
    weak = material.weak_axis_strength
    sf = weak / max_stress if max_stress > 0 else float("inf")
    sf_plane = material.yield_strength / max_stress if max_stress > 0 else float("inf")
    if sf < 1:
        warnings.append("yields")
    if material.flexible:
        warnings.append("large_deformation_material")
    if disp[i_disp] > 0.1 * float(np.max(mesh.size)):
        warnings.append("large_deformation")

    # For drawing: stress at every node (average of the elements around it) on the skin of the model.
    node_stress = np.zeros(model.n_nodes)
    counts = np.zeros(model.n_nodes)
    for c in range(8):
        np.add.at(node_stress, model.elements[:, c], peak)
        np.add.at(counts, model.elements[:, c], 1)
    node_stress /= np.maximum(counts, 1)
    skin_nodes, skin_triangles = surface_mesh(model)

    return SimResult(
        material=material, load_case=load_case, resolution=resolution, pitch=model.grid.pitch,
        n_elements=model.n_elements, n_nodes=model.n_nodes, seconds=time.monotonic() - start,
        method=sol.method, max_displacement=float(disp[i_disp]),
        max_displacement_at=model.coords[i_disp].tolist(), max_stress=max_stress,
        max_stress_at=model.centers[i_stress].tolist(), max_stress_at_supports=float(peak.max()),
        applied_force=applied.tolist(), reaction_force=reaction.tolist(), equilibrium_error=eq_err,
        voxel_volume=voxel_volume, mesh_volume=mesh.volume, safety_factor=float(sf),
        safety_factor_in_plane=float(sf_plane), stiffness=stiffness, convergence=convergence,
        warnings=warnings, skin_points=model.coords[skin_nodes], skin_triangles=skin_triangles,
        skin_stress=node_stress[skin_nodes], skin_displacement=sol.displacement[skin_nodes],
    )
