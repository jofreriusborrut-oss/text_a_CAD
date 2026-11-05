"""Stand-in for the CadQuery runner.

It lets the assistant, the sessions and the web server be tested on a
machine without CadQuery. It understands a tiny subset of CadQuery:

    cq.Workplane("XY").box(x, y, z, centered=(True, True, False)).hole(d, count)

and returns the same kind of measurements as textacad/runner.py.
"""
import sys
import tempfile
import traceback
import types
from pathlib import Path

from textacad import mesh as M
from textacad import safety
from textacad.sandbox import RunResult


class Workplane:
    def __init__(self, plane="XY"):
        self.dims = None
        self.holes = []

    def box(self, x, y, z, centered=(True, True, False)):
        if min(x, y, z) <= 0:
            raise ValueError("box dimensions must be positive")
        self.dims = (float(x), float(y), float(z))
        return self

    def hole(self, diameter, count=1):
        if count:
            self.holes.append((float(diameter), int(count)))
        return self

    def fillet(self, radius):
        if radius > min(self.dims) / 2:
            raise ValueError("BRep_API: command not done (fillet too big)")
        return self


def _fake_cadquery():
    module = types.ModuleType("cadquery")
    module.Workplane = Workplane
    return module


def run_code(code, timeout=None, job_dir=None, trusted=False):
    if not trusted:
        try:
            problems = safety.find_problems(code)
        except SyntaxError as exc:
            return RunResult(ok=False, error=f"SyntaxError: {exc.msg} (line {exc.lineno})")
        if problems:
            return RunResult(ok=False, error="This script is not allowed to run:\n" + "\n".join(problems))
    job_dir = Path(job_dir or tempfile.mkdtemp(prefix="textacad_fake_"))
    job_dir.mkdir(parents=True, exist_ok=True)

    saved = sys.modules.get("cadquery")
    sys.modules["cadquery"] = _fake_cadquery()
    namespace = {"__name__": "__textacad__"}
    try:
        exec(compile(code, "generated_part.py", "exec"), namespace)
    except BaseException:  # noqa: BLE001
        tb = traceback.format_exc()
        marker = 'File "generated_part.py"'
        if marker in tb:
            tb = "Traceback (most recent call last):\n  " + tb[tb.index(marker):]
        return RunResult(ok=False, job_dir=job_dir, error=tb.strip())
    finally:
        if saved is None:
            sys.modules.pop("cadquery", None)
        else:
            sys.modules["cadquery"] = saved

    result = namespace.get("result")
    if not isinstance(result, Workplane) or result.dims is None:
        return RunResult(ok=False, job_dir=job_dir, error="NameError: The code must define a final variable called `result`.")
    x, y, z = result.dims
    mesh = M.box_mesh((x, y, z), origin=(-x / 2, -y / 2, 0))
    (job_dir / "part.stl").write_bytes(M.dump_stl(mesh))
    (job_dir / "part.step").write_text("ISO-10303-21; (fake STEP file for tests)\n" + "0" * 1200, encoding="ascii")

    holes = {}
    for d, n in result.holes:
        holes[d] = holes.get(d, 0) + n
    expected = namespace.get("EXPECTED_BBOX")
    expected_holes = namespace.get("EXPECTED_HOLES")
    info = {
        "ok": True, "is_valid": True, "n_solids": 1,
        "volume_mm3": x * y * z, "area_mm2": 2 * (x * y + y * z + x * z),
        "bbox": {"xmin": -x / 2, "ymin": -y / 2, "zmin": 0.0, "xmax": x / 2, "ymax": y / 2, "zmax": z,
                 "size": [x, y, z]},
        "expected_bbox": [float(v) for v in expected] if expected is not None else None,
        "n_faces": 6, "notes": [], "center_of_mass": [0.0, 0.0, z / 2],
        "hole_list": [],
        "holes": [{"diameter": d, "axis": "z", "count": n} for d, n in sorted(holes.items())],
        "expected_holes": [[float(d), int(n)] for d, n in expected_holes if d > 0 and n > 0]
        if expected_holes is not None else None,
        "reference": None, "load_case": namespace.get("LOAD_CASE"), "has_3mf": False,
    }
    ref = namespace.get("REFERENCE")
    if isinstance(ref, Workplane) and ref.dims:
        (job_dir / "reference.stl").write_bytes(M.dump_stl(M.box_mesh(ref.dims)))
        info["reference"] = {"volume_mm3": ref.dims[0] * ref.dims[1] * ref.dims[2],
                             "interference_mm3": float(namespace.get("FAKE_INTERFERENCE", 0.0))}
    return RunResult(ok=True, job_dir=job_dir, info=info)


PLATE = '''import cadquery as cq

PARAMS = {
    "length": {"value": 60, "unit": "mm", "min": 20, "max": 200, "label": "Llargada"},
    "width": {"value": 40, "unit": "mm", "min": 10, "max": 200, "label": "Amplada"},
    "thickness": {"value": 5, "unit": "mm", "min": 1, "max": 30, "label": "Gruix"},
    "hole_count": {"value": 4, "unit": "count", "min": 0, "max": 8, "label": "Forats"},
}

L = PARAMS["length"]["value"]
W = PARAMS["width"]["value"]
T = PARAMS["thickness"]["value"]
N = int(PARAMS["hole_count"]["value"])

result = cq.Workplane("XY").box(L, W, T, centered=(True, True, False)).hole(6.6, N)

EXPECTED_BBOX = (L, W, T)
EXPECTED_HOLES = [(6.6, N)]
LOAD_CASE = {
    "description": "Held on the left side, 20 N down on the right side",
    "fixed": [{"type": "side", "side": "-x"}],
    "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -20]}],
}
'''


def answer(code, title="placa", summary="Placa de 60 × 40 × 5 mm amb 4 forats M6.", changes=(),
           assumptions=("Forats M6 amb joc mitjà: 6,6 mm.",), questions=(), use="process=fdm, vibration=no"):
    """A complete answer in the format Claude is asked to use."""
    def bullets(items):
        return "".join(f"- {i}\n" for i in items)

    note = (f"<title>{title}</title>\n<summary>{summary}</summary>\n"
            f"<changes>\n{bullets(changes)}</changes>\n<assumptions>\n{bullets(assumptions)}</assumptions>\n"
            f"<questions>\n{bullets(questions)}</questions>\n<use>{use}</use>\n")
    return note + (f"```python\n{code}```\n" if code else "")
