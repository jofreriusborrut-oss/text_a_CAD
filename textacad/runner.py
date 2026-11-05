"""Executes a CadQuery script in its OWN process and exports the result.

This file is never imported by the app. sandbox.py launches it as:

    python runner.py <job_dir>

<job_dir> must contain "code.py". The runner writes into the same folder:
    part.step, part.stl  -> the exported solid (STEP for CAD, STL for printing)
    part.3mf             -> the same for slicers that prefer 3MF (when available)
    reference.stl        -> the mating components declared in REFERENCE, if any
    result.json          -> {"ok": true, ...measurements...}
                            or {"ok": false, "error": "...traceback..."}

Running the code in a separate process means that if the generated code
crashes, loops forever or eats all the memory, the app keeps working:
sandbox.py simply kills this process after the time limit.

Besides exporting, the runner MEASURES the solid (size, volume, centre of
mass, round holes, collisions with the reference components). The app
compares these measurements with what the script says it built.
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from pathlib import Path

HOLE_MIN_SPAN = math.radians(270)      # a "hole" wraps at least 3/4 of a turn (clamp bores are slit)


def _flatten(obj) -> list:
    """Shapes inside a Workplane, a Shape or a (nested) list of them."""
    import cadquery as cq

    if isinstance(obj, cq.Workplane):
        return [o for o in obj.vals() if isinstance(o, cq.Shape)]
    if isinstance(obj, cq.Shape):
        return [obj]
    if isinstance(obj, (list, tuple)):
        out = []
        for item in obj:
            out.extend(_flatten(item))
        return out
    raise TypeError(f"expected a cadquery Workplane or Shape, got {type(obj).__name__}")


def _to_shape(result, what: str = "result"):
    """Accept a Workplane, a Shape or a list of shapes and return one Shape."""
    import cadquery as cq

    try:
        objs = _flatten(result)
    except TypeError as exc:
        raise TypeError(f"`{what}` must be a cadquery Workplane or Shape ({exc}).") from None
    if not objs:
        raise ValueError(f"`{what}` contains no solids.")
    return objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

def _axis_name(direction) -> str:
    for name, value in zip("xyz", direction):
        if abs(abs(value) - 1.0) < 1e-3:
            return name
    return "oblique"


def find_holes(shape) -> tuple[list[dict], list[dict]]:
    """Round holes of the solid.

    Every cylindrical face is read from the exact geometry (not the mesh):
    its radius, its axis and whether the material is outside it (a hole) or
    inside it (a pin or an outer surface). Faces on the same axis with the
    same radius are one feature, so a hole through two walls counts once.

    Returns (holes, summary): one entry per hole, and the holes grouped by
    diameter and direction.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec

    groups: dict[tuple, dict] = {}
    for face in shape.Faces():
        if face.geomType() != "CYLINDER":
            continue
        surface = BRepAdaptor_Surface(face.wrapped)
        cyl = surface.Cylinder()
        radius = float(cyl.Radius())
        axis = cyl.Axis()
        d = axis.Direction()
        direction = [d.X(), d.Y(), d.Z()]
        # Same axis written in the opposite direction must give the same key.
        lead = next((v for v in direction if abs(v) > 1e-6), 1.0)
        if lead < 0:
            direction = [-v for v in direction]
        loc = axis.Location()
        p0 = [loc.X(), loc.Y(), loc.Z()]
        along0 = sum(p * v for p, v in zip(p0, direction))
        foot = [p - along0 * v for p, v in zip(p0, direction)]      # axis point closest to the origin

        u0, u1 = surface.FirstUParameter(), surface.LastUParameter()
        v0, v1 = surface.FirstVParameter(), surface.LastVParameter()
        point, normal = gp_Pnt(), gp_Vec()
        BRepGProp_Face(face.wrapped).Normal((u0 + u1) / 2, (v0 + v1) / 2, point, normal)
        p = [point.X(), point.Y(), point.Z()]
        rel = [a - b for a, b in zip(p, foot)]
        along = sum(a * v for a, v in zip(rel, direction))
        radial = [a - along * v for a, v in zip(rel, direction)]
        outward = sum(a * b for a, b in zip([normal.X(), normal.Y(), normal.Z()], radial))
        concave = outward < 0                                       # the surface normal points to the axis

        # Extent of the face along the axis, from the corners of its parameter box.
        ends = []
        for v in (v0, v1):
            q = surface.Value((u0 + u1) / 2, v)
            ends.append(sum((c - f) * w for c, f, w in zip([q.X(), q.Y(), q.Z()], foot, direction)))

        key = (tuple(round(v, 4) for v in direction), tuple(round(v, 3) for v in foot), round(radius, 3))
        g = groups.setdefault(key, {"span": 0.0, "lo": min(ends), "hi": max(ends), "concave": 0, "convex": 0,
                                    "direction": direction, "foot": foot, "radius": radius})
        g["span"] += abs(u1 - u0)
        g["lo"], g["hi"] = min(g["lo"], *ends), max(g["hi"], *ends)
        g["concave" if concave else "convex"] += 1

    holes = []
    for g in groups.values():
        if g["concave"] <= g["convex"] or g["span"] < HOLE_MIN_SPAN:
            continue
        mid = (g["lo"] + g["hi"]) / 2
        holes.append({
            "diameter": round(2 * g["radius"], 4),
            "axis": _axis_name(g["direction"]),
            "direction": [round(v, 5) for v in g["direction"]],
            "center": [round(f + mid * v, 4) for f, v in zip(g["foot"], g["direction"])],
            "length": round(g["hi"] - g["lo"], 4),
        })
    holes.sort(key=lambda h: (h["diameter"], h["axis"], h["center"]))

    summary: dict[tuple, dict] = {}
    for h in holes:
        key = (round(h["diameter"], 2), h["axis"])
        entry = summary.setdefault(key, {"diameter": round(h["diameter"], 3), "axis": h["axis"], "count": 0})
        entry["count"] += 1
    return holes, sorted(summary.values(), key=lambda e: (e["diameter"], e["axis"]))


def _jsonable(value, depth: int = 0):
    """Turn a LOAD_CASE written with Python/numpy numbers into plain JSON data."""
    if depth > 8:
        raise ValueError("too deeply nested")
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, depth + 1) for v in value]
    if isinstance(value, (str, bool)) or value is None:
        return value
    return float(value)


def _expected_holes(value) -> list[list[float]]:
    out = []
    for item in value:
        diameter, count = item
        if float(diameter) > 0 and int(count) > 0:
            out.append([float(diameter), int(count)])
    return out


def run(job_dir: Path) -> dict:
    import cadquery as cq

    code = (job_dir / "code.py").read_text(encoding="utf-8")
    namespace: dict = {"__name__": "__textacad__"}
    exec(compile(code, "generated_part.py", "exec"), namespace)

    if "result" not in namespace:
        raise NameError("The code must define a final variable called `result`.")
    shape = _to_shape(namespace["result"])

    solids = shape.Solids()
    if not solids:
        raise ValueError("`result` contains no solid (only faces, wires or edges).")

    # Measured on the exact geometry, BEFORE the solid is meshed for the STL
    # (afterwards OpenCascade would measure the triangles, slightly bigger).
    bb = shape.BoundingBox()

    cq.exporters.export(shape, str(job_dir / "part.step"))
    cq.exporters.export(
        shape, str(job_dir / "part.stl"), tolerance=0.02, angularTolerance=0.1
    )
    expected = namespace.get("EXPECTED_BBOX")
    out = {
        "ok": True,
        "is_valid": bool(shape.isValid()),
        "n_solids": len(solids),
        "volume_mm3": float(shape.Volume()),
        "area_mm2": float(shape.Area()),
        "bbox": {
            "xmin": bb.xmin, "ymin": bb.ymin, "zmin": bb.zmin,
            "xmax": bb.xmax, "ymax": bb.ymax, "zmax": bb.zmax,
            "size": [bb.xlen, bb.ylen, bb.zlen],
        },
        "expected_bbox": [float(v) for v in expected] if expected is not None else None,
        "n_faces": len(shape.Faces()),
        "notes": [],
    }

    # Everything below is extra information: a failure here must never lose
    # the part that was just built, so each step reports its own problem.
    try:
        c = shape.Center()
        out["center_of_mass"] = [float(c.x), float(c.y), float(c.z)]
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"center_of_mass: {exc}")

    try:
        out["hole_list"], out["holes"] = find_holes(shape)
    except Exception as exc:  # noqa: BLE001
        out["holes"] = None
        out["notes"].append(f"holes: {type(exc).__name__}: {exc}")

    out["expected_holes"] = None
    if namespace.get("EXPECTED_HOLES") is not None:
        try:
            out["expected_holes"] = _expected_holes(namespace["EXPECTED_HOLES"])
        except Exception as exc:  # noqa: BLE001
            out["notes"].append(f"EXPECTED_HOLES is not a list of (diameter, count): {exc}")

    out["reference"] = None
    if namespace.get("REFERENCE") is not None:
        try:
            ref = _to_shape(namespace["REFERENCE"], "REFERENCE")
            cq.exporters.export(ref, str(job_dir / "reference.stl"), tolerance=0.05, angularTolerance=0.2)
            info = {"volume_mm3": float(ref.Volume()), "interference_mm3": None}
            try:
                info["interference_mm3"] = max(float(shape.intersect(ref).Volume()), 0.0)
            except Exception as exc:  # noqa: BLE001
                out["notes"].append(f"reference interference: {exc}")
            out["reference"] = info
        except Exception as exc:  # noqa: BLE001
            out["notes"].append(f"REFERENCE: {type(exc).__name__}: {exc}")

    out["load_case"] = None
    if namespace.get("LOAD_CASE") is not None:
        try:
            out["load_case"] = _jsonable(namespace["LOAD_CASE"])
        except Exception as exc:  # noqa: BLE001
            out["notes"].append(f"LOAD_CASE: {type(exc).__name__}: {exc}")

    try:
        cq.exporters.export(shape, str(job_dir / "part.3mf"), tolerance=0.02, angularTolerance=0.1)
        out["has_3mf"] = (job_dir / "part.3mf").stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        out["has_3mf"] = False
        out["notes"].append(f"3mf: {type(exc).__name__}: {exc}")
    return out


def main() -> None:
    job_dir = Path(sys.argv[1])
    # Loading CadQuery/OpenCascade can be slow the first time (DLLs, antivirus).
    # We tell sandbox.py when it is loaded, so the time limit only counts the
    # generated code, not this start-up.
    import cadquery  # noqa: F401

    (job_dir / "ready").touch()
    try:
        out = run(job_dir)
    except BaseException:  # noqa: BLE001 - we want to report *everything* to Claude
        tb = traceback.format_exc()
        # Keep only the part of the traceback that concerns the generated code.
        marker = 'File "generated_part.py"'
        if marker in tb:
            tb = "Traceback (most recent call last):\n  " + tb[tb.index(marker):]
        out = {"ok": False, "error": tb.strip()}
    (job_dir / "result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
