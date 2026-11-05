"""Automatic checks on a generated part.

1. The solid is valid and closed (watertight).
2. The overall size matches EXPECTED_BBOX (the size Claude read in the description).
3. The round holes match EXPECTED_HOLES (diameters and how many of each).
4. The part does not collide with the mating component (REFERENCE), if any.
5. Wall thickness: thin areas (< 1.2 mm) are risky for FDM 3D printing.
6. Volume and approximate weight.

Each check is a short code plus numbers; i18n.py turns it into a sentence in
the user's language, and `problems_for_claude` turns the failed ones into an
English message so that Claude can correct the script.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import i18n
from .materials import Material, get_material
from .mesh import Mesh, MeshError, load_stl

MIN_WALL = 1.2              # mm
BBOX_TOL_ABS = 0.2          # mm
BBOX_TOL_REL = 0.01         # 1 %
HOLE_TOL = 0.06             # mm on the diameter
COLLISION_TOL = 1.0         # mm3 of overlap that is ignored (touching faces, rounding)

LEVELS = ("ok", "info", "warning", "error")


@dataclass
class Check:
    level: str              # "ok", "info", "warning" or "error"
    code: str               # key of the text in i18n.CHECKS
    values: dict = field(default_factory=dict)

    def text(self, lang: str = "en") -> tuple[str, str]:
        """(title, detail) in the given language."""
        lang = i18n.lang_of(lang)
        v = dict(self.values)
        fmt: dict = {}
        if "size" in v:
            fmt["got"] = i18n.size_text(v["size"], lang)
        if "expected" in v:
            fmt["want"] = i18n.size_text(v["expected"], lang)
        if "axes" in v:
            fmt["axes"] = "; ".join(
                f"{a} = {i18n.num(got, 1, lang)} ({i18n.num(want, 1, lang)})" for a, got, want in v["axes"])
        if "found" in v:
            fmt["found"] = _holes_text(v["found"], lang)
        if "hole_problems" in v:
            fmt["problems"] = "; ".join(
                i18n.pick(i18n.HOLE_PROBLEMS, "missing", lang, want=p["want"], got=p["got"],
                          d=i18n.num(p["diameter"], 2, lang).rstrip("0").rstrip(",."))
                for p in v["hole_problems"])
        if "solid_problems" in v:
            text = "; ".join(i18n.pick(i18n.SOLID_PROBLEMS, p, lang, n=v.get("n_solids", 0))
                             for p in v["solid_problems"])
            fmt["problems"] = text[:1].upper() + text[1:]
        for key, decimals in (("limit", 1), ("thinnest", 2), ("volume", 2), ("grams", 1), ("density", 2)):
            if key in v:
                fmt[key] = i18n.num(v[key], decimals, lang)
        if "share" in v:
            fmt["share"] = f"{v['share']:.0f}"
        if "material" in v:
            fmt["material"] = v["material"]
        title, detail = (i18n.CHECKS[self.code].get(lang) or i18n.CHECKS[self.code]["en"])
        return title.format(**fmt), detail.format(**fmt)

    def as_dict(self, lang: str = "en") -> dict:
        title, detail = self.text(lang)
        return {"level": self.level, "code": self.code, "title": title, "detail": detail}


def _holes_text(found: list[dict], lang: str) -> str:
    if not found:
        return "-"
    parts = []
    for h in found:
        d = i18n.num(h["diameter"], 2, lang).rstrip("0").rstrip(",.")
        axis = "" if h.get("axis") in (None, "oblique") else f" ({h['axis'].upper()})"
        parts.append(f"{h['count']} × Ø{d}{axis}")
    return ", ".join(parts)


def load_mesh(stl_bytes: bytes) -> Mesh:
    return load_stl(stl_bytes)


# ---------------------------------------------------------------------------
# 1. Valid and closed
# ---------------------------------------------------------------------------

def check_solid(info: dict, mesh: Mesh | None) -> Check:
    problems = []
    if not info.get("is_valid", True):
        problems.append("brep_invalid")
    if info.get("n_solids", 1) != 1:
        problems.append("n_solids")
    if mesh is None or not mesh.is_watertight():
        problems.append("not_watertight")
    if problems:
        return Check("error", "solid_invalid", {"solid_problems": problems, "n_solids": info.get("n_solids", 1)})
    return Check("ok", "solid_ok")


# ---------------------------------------------------------------------------
# 2. Overall size
# ---------------------------------------------------------------------------

def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(BBOX_TOL_ABS, BBOX_TOL_REL * abs(b))


def check_bbox(info: dict) -> Check:
    size = [float(v) for v in info["bbox"]["size"]]
    expected = info.get("expected_bbox")
    if not expected:
        return Check("warning", "size_unchecked", {"size": size})
    expected = [float(v) for v in expected]
    if all(_close(a, b) for a, b in zip(size, expected)):
        return Check("ok", "size_ok", {"size": size})
    if all(_close(a, b) for a, b in zip(sorted(size), sorted(expected))):
        return Check("info", "size_rotated", {"size": size, "expected": expected})
    axes = [(n, a, b) for n, a, b in zip("XYZ", size, expected) if not _close(a, b)]
    return Check("warning", "size_mismatch", {"size": size, "expected": expected, "axes": axes})


# ---------------------------------------------------------------------------
# 3. Round holes
# ---------------------------------------------------------------------------

def count_holes(found: list[dict], diameter: float, tol: float = HOLE_TOL) -> int:
    return sum(h["count"] for h in found if abs(h["diameter"] - diameter) <= tol)


def check_holes(info: dict) -> Check | None:
    """Compare the holes measured on the solid with EXPECTED_HOLES."""
    found = info.get("holes")
    if found is None:
        return None                          # measurement not available
    expected = info.get("expected_holes")
    if expected is None:
        return Check("info", "holes_listed" if found else "holes_none", {"found": found})
    merged: dict[float, int] = {}
    for diameter, count in expected:         # the same diameter listed twice adds up
        key = next((k for k in merged if abs(k - diameter) <= HOLE_TOL), float(diameter))
        merged[key] = merged.get(key, 0) + int(count)
    problems = [{"diameter": d, "want": n, "got": count_holes(found, d)}
                for d, n in merged.items() if count_holes(found, d) != n]
    if problems:
        return Check("warning", "holes_mismatch", {"hole_problems": problems, "found": found})
    if not found:
        return Check("ok", "holes_none", {"found": found})
    return Check("ok", "holes_ok", {"found": found})


# ---------------------------------------------------------------------------
# 4. Fit with the mating component
# ---------------------------------------------------------------------------

def check_fit(info: dict) -> Check | None:
    ref = info.get("reference")
    if not ref or ref.get("interference_mm3") is None:
        return None
    overlap = float(ref["interference_mm3"])
    limit = max(COLLISION_TOL, 1e-4 * float(info.get("volume_mm3", 0.0)))
    if overlap > limit:
        return Check("warning", "fit_collision", {"volume": overlap})
    return Check("ok", "fit_ok")


# ---------------------------------------------------------------------------
# 5. Wall thickness (ray casting)
# ---------------------------------------------------------------------------

def check_walls(mesh: Mesh, min_wall: float = MIN_WALL) -> Check:
    t = mesh.wall_thickness()
    if len(t) == 0:
        return Check("info", "walls_unmeasured")
    share = float((t < min_wall).mean() * 100)
    thinnest = float(np.percentile(t, 0.5))      # ignore a few rays grazing sharp edges
    values = {"limit": min_wall, "thinnest": thinnest, "share": share}
    if share < 0.5:
        return Check("ok", "walls_ok", values)
    return Check("warning", "walls_thin", values)


# ---------------------------------------------------------------------------
# 6. Volume and weight
# ---------------------------------------------------------------------------

def check_weight(info: dict, material: Material | str = "petg") -> Check:
    if isinstance(material, str):
        material = get_material(material)
    cm3 = info["volume_mm3"] / 1000
    return Check("info", "mass", {"volume": cm3, "grams": cm3 * material.density,
                                  "density": material.density, "material": material.name})


def run_checks(info: dict, stl_bytes: bytes, material: Material | str = "petg") -> list[Check]:
    try:
        mesh = load_mesh(stl_bytes)
    except MeshError:
        mesh = None
    solid = check_solid(info, mesh)
    checks = [solid, check_bbox(info)]
    for extra in (check_holes(info), check_fit(info)):
        if extra is not None:
            checks.append(extra)
    checks.append(check_walls(mesh) if solid.level == "ok" else Check("info", "walls_unmeasured"))
    checks.append(check_weight(info, material))
    return checks


# ---------------------------------------------------------------------------
# Feedback for Claude
# ---------------------------------------------------------------------------

def problems_for_claude(info: dict) -> str | None:
    """English description of what does not match, or None if the part is acceptable.

    Only uses the measurements made by the runner (no mesh needed), so it is
    cheap enough to run after every attempt.
    """
    msgs = []
    if info.get("expected_bbox") is None:
        msgs.append("The variable EXPECTED_BBOX = (size_x, size_y, size_z) is missing.")
    if info.get("n_solids", 1) != 1:
        msgs.append(
            f"`result` contains {info['n_solids']} separate solids; it must be ONE solid. "
            "Make sure all pieces touch/overlap and are joined with union()."
        )
    if not info.get("is_valid", True):
        msgs.append(
            "The resulting solid is not valid (OpenCascade BRepCheck failed). "
            "Avoid fillets/chamfers on tiny or tangent edges and coincident faces."
        )
    bbox = check_bbox(info)
    if bbox.code == "size_mismatch":
        got = " x ".join(f"{v:.2f}" for v in bbox.values["size"])
        want = " x ".join(f"{v:.2f}" for v in bbox.values["expected"])
        msgs.append(
            f"The solid measures {got} mm (X x Y x Z) but EXPECTED_BBOX says {want} mm. "
            "Either the geometry or EXPECTED_BBOX does not follow the request."
        )
    holes = check_holes(info)
    if holes is not None and holes.code == "holes_mismatch":
        found = ", ".join(f"{h['count']} x d{h['diameter']:g} (axis {h['axis']})"
                          for h in holes.values["found"]) or "none"
        for p in holes.values["hole_problems"]:
            msgs.append(
                f"EXPECTED_HOLES says {p['want']} round hole(s) of diameter {p['diameter']:g} mm "
                f"but the solid has {p['got']}."
            )
        msgs.append(f"Round holes actually found on the solid: {found}.")
    fit = check_fit(info)
    if fit is not None and fit.code == "fit_collision":
        msgs.append(
            f"The part overlaps the REFERENCE component by {fit.values['volume']:.1f} mm3: it would "
            "not fit. Give the part clearance around the component (REFERENCE must keep the "
            "component's real size)."
        )
    return "\n".join(msgs) or None
