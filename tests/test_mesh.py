"""Mesh toolbox: STL reading/writing and measurements (no CadQuery needed)."""
import numpy as np
import pytest

from textacad import mesh as M

from . import shapes


def test_box_measurements():
    box = M.box_mesh((60, 80, 5))
    assert box.is_watertight()
    assert box.volume == pytest.approx(24000)
    assert box.area == pytest.approx(2 * (60 * 80 + 60 * 5 + 80 * 5))
    assert box.center_of_mass == pytest.approx([30, 40, 2.5])
    assert box.size == pytest.approx([60, 80, 5])


def test_cylinder_volume_close_to_exact():
    cyl = M.cylinder_mesh(10, 30, segments=256)
    assert cyl.is_watertight()
    assert cyl.volume == pytest.approx(np.pi * 100 * 30, rel=1e-3)


def test_hole_reduces_volume():
    part = shapes.plate_with_hole(60, 40, 5, 10, segments=256)
    assert part.is_watertight()
    assert part.volume == pytest.approx(60 * 40 * 5 - np.pi * 25 * 5, rel=1e-3)


def test_open_surface_is_not_watertight():
    box = M.box_mesh((10, 10, 10))
    assert not M.Mesh(box.triangles[:-1]).is_watertight()


def test_stl_binary_roundtrip():
    box = M.box_mesh((10, 20, 30), origin=(1, 2, 3))
    again = M.load_stl(M.dump_stl(box))
    assert np.allclose(again.triangles, box.triangles)


def test_stl_ascii_is_read():
    box = M.box_mesh((10, 20, 30))
    text = "solid part\n"
    for tri in box.triangles:
        text += "facet normal 0 0 0\n outer loop\n"
        text += "".join(f"  vertex {v[0]} {v[1]} {v[2]}\n" for v in tri)
        text += " endloop\nendfacet\n"
    text += "endsolid part\n"
    again = M.load_stl(text.encode("ascii"))
    assert np.allclose(again.triangles, box.triangles)


def test_garbage_is_rejected():
    with pytest.raises(M.MeshError):
        M.load_stl(b"this is not an stl file at all, sorry")


def test_wall_thickness_of_a_hollow_box():
    outer = M.box_mesh((40, 30, 20))
    cavity = M.flipped(M.box_mesh((36, 26, 16), origin=(2, 2, 2)))
    t = M.merge(outer, cavity).wall_thickness(1500)
    assert np.percentile(t, 1) == pytest.approx(2.0, abs=0.01)


def test_thin_wall_is_measured():
    t = shapes.open_box(wall=0.8).wall_thickness(2000)
    assert np.percentile(t, 5) == pytest.approx(0.8, abs=0.01)


def test_overhangs_depend_on_orientation():
    part = shapes.l_bracket(40, 30, 4)
    # Standing on its base (Z up) nothing hangs: the wall rises straight up.
    assert part.overhang_area([0, 0, 1]) == pytest.approx(0, abs=1e-6)
    # Upside down, the base becomes a roof held only by the wall: it needs support.
    assert part.overhang_area([0, 0, -1]) == pytest.approx((40 - 4) * 30, rel=1e-6)
    assert part.bed_contact_area([0, 0, 1]) == pytest.approx(40 * 30)
