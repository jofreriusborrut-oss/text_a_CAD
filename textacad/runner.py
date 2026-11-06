"""Executes a CadQuery script in its OWN process and exports the result.

This file is never imported by the app. sandbox.py launches it as:

    python runner.py <job_dir>

<job_dir> must contain "code.py". The runner writes into the same folder:
    part.step, part.stl  -> the exported solid
    result.json          -> {"ok": true, ...measurements...}
                            or {"ok": false, "error": "...traceback..."}

If `result` is a dictionary {"name": solid, ...} the script describes an
ASSEMBLY of separate parts. Then part.step is an assembly STEP (SolidWorks
opens it with one component per part), part.stl is all the parts together
(for the viewer) and parts/<name>.step + parts/<name>.stl are each part alone.

Running the code in a separate process means that if the generated code
crashes, loops forever or eats all the memory, the app keeps working:
sandbox.py simply kills this process after the time limit.
"""
from __future__ import annotations

import itertools
import json
import re
import sys
import traceback
from pathlib import Path

# One colour per component (r, g, b from 0 to 1), so they are easy to tell apart.
COLOURS = [
    (0.30, 0.52, 0.80), (0.90, 0.56, 0.22), (0.38, 0.70, 0.42), (0.80, 0.35, 0.35),
    (0.58, 0.45, 0.75), (0.55, 0.55, 0.58), (0.85, 0.75, 0.30), (0.35, 0.70, 0.72),
]
MAX_PARTS = 20
OVERLAP_MIN_MM3 = 0.5       # smaller overlaps are numerical noise between touching faces


def _to_shape(result):
    """Accept a Workplane, a Shape or a list of shapes and return one Shape."""
    import cadquery as cq

    if isinstance(result, cq.Workplane):
        objs = [o for o in result.vals() if isinstance(o, cq.Shape)]
        if not objs:
            raise ValueError("`result` is a Workplane with no solids in it.")
        return objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)
    if isinstance(result, cq.Shape):
        return result
    if isinstance(result, (list, tuple)) and all(isinstance(o, cq.Shape) for o in result):
        return cq.Compound.makeCompound(list(result))
    raise TypeError(
        f"`result` must be a cadquery Workplane or Shape, got {type(result).__name__}."
    )


def _bbox(shape) -> dict:
    bb = shape.BoundingBox()
    return {
        "xmin": bb.xmin, "ymin": bb.ymin, "zmin": bb.zmin,
        "xmax": bb.xmax, "ymax": bb.ymax, "zmax": bb.zmax,
        "size": [bb.xlen, bb.ylen, bb.zlen],
    }


def _boxes_overlap(a: dict, b: dict) -> bool:
    return all(a[f"{ax}min"] < b[f"{ax}max"] and b[f"{ax}min"] < a[f"{ax}max"] for ax in "xyz")


def _export_assembly_step(cq, shapes: dict, path: Path) -> str:
    """Write a STEP where every part is a named component. Returns the kind written."""
    try:
        assy = cq.Assembly(name="conjunt")
        for i, (name, shape) in enumerate(shapes.items()):
            try:
                colour = cq.Color(*COLOURS[i % len(COLOURS)])
            except Exception:  # noqa: BLE001 - colours are only cosmetic
                colour = None
            assy.add(shape, name=name, color=colour)
        save = getattr(assy, "export", None) or assy.save      # export() is the newer name
        save(str(path))
        if path.stat().st_size > 0:
            return "assembly"
    except Exception:  # noqa: BLE001
        pass
    # Fallback: one STEP with several bodies (SolidWorks opens it as a multibody part).
    cq.exporters.export(cq.Compound.makeCompound(list(shapes.values())), str(path))
    return "multibody"


def run_assembly(cq, job_dir: Path, result: dict, expected) -> dict:
    if not result:
        raise ValueError("`result` is an empty dictionary: an assembly needs at least one part.")
    if len(result) > MAX_PARTS:
        raise ValueError(f"The assembly has {len(result)} parts; the limit is {MAX_PARTS}.")
    shapes: dict = {}
    for name, obj in result.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError(
                f"Part name {name!r} is not valid: use only letters without accents, "
                "digits and underscores (for example \"tapa_superior\")."
            )
        if name.lower() in {n.lower() for n in shapes}:
            raise ValueError(f"Two parts are called {name!r} (names must differ, ignoring case).")
        shape = _to_shape(obj)
        if not shape.Solids():
            raise ValueError(f"Part {name!r} contains no solid (only faces, wires or edges).")
        shapes[name] = shape

    parts_dir = job_dir / "parts"
    parts_dir.mkdir(exist_ok=True)
    parts = []
    for name, shape in shapes.items():
        cq.exporters.export(shape, str(parts_dir / f"{name}.step"))
        cq.exporters.export(shape, str(parts_dir / f"{name}.stl"), tolerance=0.02, angularTolerance=0.1)
        parts.append({
            "name": name,
            "is_valid": bool(shape.isValid()),
            "n_solids": len(shape.Solids()),
            "volume_mm3": float(shape.Volume()),
            "bbox": _bbox(shape),
        })

    # Parts that occupy the same space (touching faces are fine).
    overlaps = []
    for (a, sa), (b, sb) in itertools.combinations(zip(parts, shapes.values()), 2):
        if not _boxes_overlap(a["bbox"], b["bbox"]):
            continue
        try:
            common = float(sa.intersect(sb).Volume())
        except Exception:  # noqa: BLE001 - a failed boolean must not hide a good assembly
            continue
        if common > OVERLAP_MIN_MM3:
            overlaps.append({"a": a["name"], "b": b["name"], "volume_mm3": common})

    whole = cq.Compound.makeCompound(list(shapes.values()))
    step_kind = _export_assembly_step(cq, shapes, job_dir / "part.step")
    cq.exporters.export(whole, str(job_dir / "part.stl"), tolerance=0.02, angularTolerance=0.1)

    return {
        "ok": True,
        "assembly": True,
        "step_kind": step_kind,
        "parts": parts,
        "overlaps": overlaps,
        "is_valid": all(p["is_valid"] for p in parts),
        "n_solids": sum(p["n_solids"] for p in parts),
        "volume_mm3": sum(p["volume_mm3"] for p in parts),
        "area_mm2": float(whole.Area()),
        "bbox": _bbox(whole),
        "expected_bbox": [float(v) for v in expected] if expected is not None else None,
    }


def run(job_dir: Path) -> dict:
    import cadquery as cq

    code = (job_dir / "code.py").read_text(encoding="utf-8")
    namespace: dict = {"__name__": "__textacad__"}
    exec(compile(code, "generated_part.py", "exec"), namespace)

    if "result" not in namespace:
        raise NameError("The code must define a final variable called `result`.")
    if isinstance(namespace["result"], dict):
        return run_assembly(cq, job_dir, namespace["result"], namespace.get("EXPECTED_BBOX"))
    shape = _to_shape(namespace["result"])

    solids = shape.Solids()
    if not solids:
        raise ValueError("`result` contains no solid (only faces, wires or edges).")

    cq.exporters.export(shape, str(job_dir / "part.step"))
    cq.exporters.export(
        shape, str(job_dir / "part.stl"), tolerance=0.02, angularTolerance=0.1
    )

    bb = shape.BoundingBox()
    expected = namespace.get("EXPECTED_BBOX")
    return {
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
    }


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
