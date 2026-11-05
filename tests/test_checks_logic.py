"""Checks computed from the runner's measurements (no CadQuery needed)."""
import pytest

from textacad import checks
from textacad.mesh import dump_stl

from . import shapes


def info(size=(60, 40, 5), expected=(60, 40, 5), holes=(), expected_holes=None, **extra):
    data = {"is_valid": True, "n_solids": 1, "volume_mm3": size[0] * size[1] * size[2],
            "bbox": {"size": list(size)}, "expected_bbox": list(expected) if expected else None,
            "holes": [{"diameter": d, "axis": "z", "count": n} for d, n in holes],
            "expected_holes": [list(h) for h in expected_holes] if expected_holes is not None else None}
    data.update(extra)
    return data


def test_size_ok_rotated_and_wrong():
    assert checks.check_bbox(info()).code == "size_ok"
    assert checks.check_bbox(info(expected=(40, 60, 5))).level == "info"
    wrong = checks.check_bbox(info(expected=(60, 50, 5)))
    assert wrong.code == "size_mismatch" and wrong.level == "warning"
    assert wrong.values["axes"] == [("Y", 40.0, 50.0)]
    assert checks.check_bbox(info(expected=None)).code == "size_unchecked"


def test_holes_match():
    assert checks.check_holes(info(holes=[(6.6, 4)], expected_holes=[(6.6, 4)])).code == "holes_ok"
    assert checks.check_holes(info(holes=[(6.62, 4)], expected_holes=[(6.6, 4)])).code == "holes_ok"   # tolerance
    assert checks.check_holes(info(holes=[], expected_holes=[])).code == "holes_none"
    # Two entries with the same diameter add up.
    assert checks.check_holes(info(holes=[(5.5, 4)], expected_holes=[(5.5, 2), (5.5, 2)])).code == "holes_ok"
    # Extra holes that were not declared are only listed.
    assert checks.check_holes(info(holes=[(6.6, 4), (30, 1)], expected_holes=[(6.6, 4)])).code == "holes_ok"


def test_holes_mismatch():
    c = checks.check_holes(info(holes=[(6.6, 3)], expected_holes=[(6.6, 4), (30, 1)]))
    assert c.code == "holes_mismatch" and c.level == "warning"
    assert {(p["diameter"], p["want"], p["got"]) for p in c.values["hole_problems"]} == {(6.6, 4, 3), (30.0, 1, 0)}


def test_holes_without_declaration_are_listed():
    assert checks.check_holes(info(holes=[(6.6, 4)])).code == "holes_listed"
    assert checks.check_holes(info()).code == "holes_none"
    assert checks.check_holes({**info(), "holes": None}) is None            # measurement unavailable


def test_fit_with_reference():
    assert checks.check_fit(info()) is None
    assert checks.check_fit(info(reference={"interference_mm3": 0.2})).code == "fit_ok"
    assert checks.check_fit(info(reference={"interference_mm3": 85.0})).code == "fit_collision"


def test_full_run_on_a_good_part():
    part = shapes.plate_with_holes(60, 40, 5, [(10, 10, 6.6), (50, 10, 6.6), (10, 30, 6.6), (50, 30, 6.6)])
    data = info(holes=[(6.6, 4)], expected_holes=[(6.6, 4)])
    data["volume_mm3"] = part.volume
    result = checks.run_checks(data, dump_stl(part), "petg")
    assert [c.code for c in result] == ["solid_ok", "size_ok", "holes_ok", "walls_ok", "mass"]
    assert all(c.level in ("ok", "info") for c in result)


def test_thin_walls_and_open_mesh():
    tray = shapes.open_box(40, 30, 20, wall=0.8)
    data = info(size=(40, 30, 20), expected=(40, 30, 20))
    codes = {c.code: c for c in checks.run_checks(data, dump_stl(tray))}
    assert codes["walls_thin"].level == "warning"
    assert codes["walls_thin"].values["thinnest"] == pytest.approx(0.8, abs=0.02)

    broken = dump_stl(type(tray)(tray.triangles[:-2]))
    codes = {c.code: c for c in checks.run_checks(data, broken)}
    assert codes["solid_invalid"].level == "error"
    assert "walls_unmeasured" in codes


def test_weight_uses_the_material():
    c = checks.check_weight(info(), "pla")
    assert c.values["grams"] == pytest.approx(12.0 * 1.24)
    title, _ = c.text("ca")
    assert "14,9 g" in title and "PLA" in title and "12,00 cm³" in title


def test_texts_in_three_languages():
    wrong = checks.check_bbox(info(expected=(60, 50, 5)))
    assert "does NOT match" in wrong.text("en")[0] and "Y = 40.0 (50.0)" in wrong.text("en")[1]
    assert "NO coincideix" in wrong.text("ca")[0] and "Y = 40,0 (50,0)" in wrong.text("ca")[1]
    assert "NO coincide" in wrong.text("es")[0]
    holes = checks.check_holes(info(holes=[(6.6, 3)], expected_holes=[(6.6, 4)]))
    assert "4 × Ø6.6" in holes.text("en")[1] and "3 × Ø6.6 (Z)" in holes.text("en")[1]
    assert "4 × Ø6,6" in holes.text("ca")[1]
    d = checks.Check("error", "solid_invalid", {"solid_problems": ["n_solids"], "n_solids": 2}).as_dict("es")
    assert d["detail"].startswith("Hay 2 sólidos")


def test_feedback_for_claude():
    assert checks.problems_for_claude(info(holes=[(6.6, 4)], expected_holes=[(6.6, 4)])) is None
    text = checks.problems_for_claude(info(expected=(60, 50, 5), holes=[(6.6, 3)], expected_holes=[(6.6, 4)]))
    assert "60.00 x 40.00 x 5.00" in text and "60.00 x 50.00 x 5.00" in text
    assert "4 round hole(s) of diameter 6.6" in text and "has 3" in text
    assert "EXPECTED_BBOX" in checks.problems_for_claude(info(expected=None))
    assert "ONE solid" in checks.problems_for_claude({**info(), "n_solids": 2})
    assert "overlaps the REFERENCE" in checks.problems_for_claude(info(reference={"interference_mm3": 50.0}))
    # A rotated but otherwise right part is not sent back.
    assert checks.problems_for_claude(info(expected=(40, 60, 5))) is None
