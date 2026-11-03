"""Automatic checks on a generated part, shown to the user as warnings.

1. The solid is valid and closed (watertight).
2. The overall size matches EXPECTED_BBOX (the size Claude read in the description).
3. Wall thickness: thin areas (< 1.2 mm) are risky for FDM 3D printing.
4. Volume and approximate weight in PLA.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import trimesh

PLA_DENSITY = 1.24          # g/cm3
MIN_WALL = 1.2              # mm
BBOX_TOL_ABS = 0.2          # mm
BBOX_TOL_REL = 0.01         # 1 %


def num(x: float, decimals: int = 1) -> str:
    """1.2 -> "1,2" (Catalan decimal comma)."""
    return f"{x:.{decimals}f}".replace(".", ",")



@dataclass
class Check:
    level: str              # "ok", "info", "warning" or "error"
    title: str
    detail: str = ""


def load_mesh(stl_bytes: bytes) -> trimesh.Trimesh:
    return trimesh.load(io.BytesIO(stl_bytes), file_type="stl", force="mesh")


# ---------------------------------------------------------------------------
# 1. Valid and closed
# ---------------------------------------------------------------------------

def check_solid(info: dict, mesh: trimesh.Trimesh) -> Check:
    problems = []
    if not info.get("is_valid"):
        problems.append("OpenCascade diu que el sòlid no és vàlid (BRepCheck)")
    if info.get("n_solids", 1) != 1:
        problems.append(f"hi ha {info['n_solids']} sòlids separats en lloc d'un")
    if not mesh.is_watertight:
        problems.append("la malla STL no és tancada (té forats o arestes obertes)")
    if problems:
        return Check("error", "Sòlid no vàlid", "; ".join(problems).capitalize() + ".")
    return Check("ok", "Sòlid vàlid i tancat", "Un únic sòlid, sense forats a la superfície.")


# ---------------------------------------------------------------------------
# 2. Overall size
# ---------------------------------------------------------------------------

def check_bbox(info: dict) -> Check:
    size = info["bbox"]["size"]
    expected = info.get("expected_bbox")
    got = " × ".join(num(v) for v in size)
    if not expected:
        return Check("warning", "Mida total no comprovada",
                     f"El codi no indica la mida esperada (EXPECTED_BBOX). Mida real: {got} mm.")
    want = " × ".join(num(v) for v in expected)

    def close(a, b):
        return abs(a - b) <= max(BBOX_TOL_ABS, BBOX_TOL_REL * abs(b))

    if all(close(a, b) for a, b in zip(size, expected)):
        return Check("ok", "La mida total coincideix amb la descripció", f"{got} mm")
    if all(close(a, b) for a, b in zip(sorted(size), sorted(expected))):
        return Check("info", "Mida correcta però orientació diferent",
                     f"Esperada (X × Y × Z): {want} mm · Real: {got} mm. "
                     "Les mides coincideixen però en un altre ordre d'eixos.")
    axes = [f"{n} = {num(a)} (esperat {num(b)})"
            for n, a, b in zip("XYZ", size, expected) if not close(a, b)]
    return Check("warning", "La mida total NO coincideix amb la descripció",
                 f"Esperada: {want} mm · Real: {got} mm ({'; '.join(axes)} mm).")


# ---------------------------------------------------------------------------
# 3. Wall thickness (ray casting)
# ---------------------------------------------------------------------------

def wall_thickness(mesh: trimesh.Trimesh, n_samples: int = 4000, seed: int = 0) -> np.ndarray:
    """Local thickness (mm) at points spread evenly over the surface.

    From each point we shoot a ray INTO the material (opposite to the face
    normal). The distance to where the ray leaves the part is the local
    thickness there.
    """
    # Random points, more of them on bigger faces (uniform over the area).
    points, face_idx = trimesh.sample.sample_surface(mesh, n_samples, seed=seed)
    normals = mesh.face_normals[face_idx]
    eps = 1e-3
    origins = points - normals * eps
    directions = -normals
    locations, ray_idx, _ = mesh.ray.intersects_location(origins, directions, multiple_hits=True)

    thickness = np.full(len(points), np.inf)
    if len(ray_idx):
        dist = np.linalg.norm(locations - origins[ray_idx], axis=1)
        valid = dist > eps
        np.minimum.at(thickness, ray_idx[valid], dist[valid] + eps)
    return thickness[np.isfinite(thickness)]


def check_walls(mesh: trimesh.Trimesh, min_wall: float = MIN_WALL) -> Check:
    t = wall_thickness(mesh)
    if len(t) == 0:
        return Check("info", "No s'ha pogut mesurar el gruix de paret")
    thin = t < min_wall
    share = thin.mean() * 100
    t_min = float(np.percentile(t, 0.5))   # ignore a few rays grazing sharp edges
    if share < 0.5:
        return Check("ok", f"Cap paret més prima que {num(min_wall)} mm",
                     f"Gruix mínim aproximat: {num(t_min)} mm.")
    return Check("warning", f"Parets primes (< {num(min_wall)} mm): risc en impressió 3D",
                 f"Un {share:.0f} % de la superfície té un gruix inferior a {num(min_wall)} mm "
                 f"(mínim aproximat: {num(t_min, 2)} mm). Pot no imprimir-se bé o ser fràgil.")


# ---------------------------------------------------------------------------
# 4. Volume and weight
# ---------------------------------------------------------------------------

def check_weight(info: dict) -> Check:
    cm3 = info["volume_mm3"] / 1000
    grams = cm3 * PLA_DENSITY
    return Check("info", f"Volum: {num(cm3, 2)} cm³ · pes aproximat en PLA: {num(grams)} g",
                 f"Peça massissa (100 % de farciment), densitat del PLA: {num(PLA_DENSITY, 2)} g/cm³. "
                 "Amb farciment parcial pesarà menys.")


def run_checks(info: dict, stl_bytes: bytes) -> list[Check]:
    mesh = load_mesh(stl_bytes)
    checks = [check_solid(info, mesh), check_bbox(info)]
    checks.append(check_walls(mesh) if mesh.is_watertight
                  else Check("info", "Gruix de paret no mesurat", "Cal una malla tancada."))
    checks.append(check_weight(info))
    return checks
