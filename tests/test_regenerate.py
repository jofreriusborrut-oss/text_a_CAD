"""Phase 4: changing a PARAMS value rebuilds the part locally (no Claude)."""
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from textacad.regenerate import regenerate    # noqa: E402

PLATE = (Path(__file__).parent / "parts" / "a_placa.py").read_text(encoding="utf-8")


def test_new_values_change_the_geometry():
    out = regenerate(PLATE, {"length": 100, "width": 50, "thickness": 8})
    assert out["ok"], out["error"]
    assert out["info"]["bbox"]["size"] == pytest.approx([100, 50, 8], abs=0.1)
    assert out["info"]["expected_bbox"] == pytest.approx([100, 50, 8])
    assert '"value": 100' in out["code"]
    assert len(out["stl"]) > 1000 and len(out["step"]) > 1000


def test_extreme_values_still_valid_thanks_to_clamping():
    # Biggest holes far from the edges on the smallest plate: the code clamps them.
    out = regenerate(PLATE, {"length": 30, "width": 30, "hole_diameter": 15,
                             "hole_edge_distance": 40, "corner_radius": 20})
    assert out["ok"], out["error"]
    assert out["info"]["is_valid"]


def test_unknown_parameter():
    out = regenerate(PLATE, {"does_not_exist": 3})
    assert not out["ok"] and "Unknown parameter" in out["error"]
