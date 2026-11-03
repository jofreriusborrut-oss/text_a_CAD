"""Executes a CadQuery script in its OWN process and exports the result.

This file is never imported by the app. sandbox.py launches it as:

    python runner.py <job_dir>

<job_dir> must contain "code.py". The runner writes into the same folder:
    part.step, part.stl  -> the exported solid
    result.json          -> {"ok": true, ...measurements...}
                            or {"ok": false, "error": "...traceback..."}

Running the code in a separate process means that if the generated code
crashes, loops forever or eats all the memory, the app keeps working:
sandbox.py simply kills this process after the time limit.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


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
