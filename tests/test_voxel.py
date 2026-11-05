"""Voxel grid: which boxes are inside the part (no CadQuery needed)."""
import numpy as np
import pytest

from textacad import mesh as M
from textacad.voxel import VoxelGrid, grid_lines, pitch_for_count, voxelize

from . import shapes


@pytest.mark.parametrize("pitch", [2.0, 1.3, 0.7])
def test_box_volume_is_exact_for_any_pitch(pitch):
    box = M.box_mesh((60, 80, 5))
    grid = voxelize(box, pitch)
    assert grid.volume == pytest.approx(box.volume, rel=1e-9)
    assert grid.solid.all()


def test_cylinder_volume():
    cyl = M.cylinder_mesh(25, 10, segments=360)
    grid = voxelize(cyl, 0.5)
    assert grid.volume == pytest.approx(cyl.volume, rel=0.01)


def test_hole_is_empty_and_plate_is_solid():
    part = shapes.plate_with_hole(60, 40, 5, 10)
    grid = voxelize(part, 1.0)
    centers = grid.centers()
    r = np.hypot(centers[:, 0] - 30, centers[:, 1] - 20)
    assert r.min() > 4.0                       # nothing left inside the hole
    assert grid.volume == pytest.approx(part.volume, rel=0.02)


def test_grid_follows_the_walls_of_an_l_bracket():
    part = shapes.l_bracket(40, 30, 4)
    grid = voxelize(part, 1.7)                 # 1.7 does not divide 4: a plain cube grid would be off
    assert 4.0 in np.round(grid.edges[0], 9)   # a grid line sits on the inner face of the wall
    assert 4.0 in np.round(grid.edges[2], 9)   # ... and on the top face of the base
    assert grid.volume == pytest.approx(part.volume, rel=1e-9)


def test_closed_cavity_stays_empty():
    outer = M.box_mesh((40, 30, 20))
    cavity = M.flipped(M.box_mesh((36, 26, 16), origin=(2, 2, 2)))
    grid = voxelize(M.merge(outer, cavity), 1.0)
    assert grid.volume == pytest.approx(40 * 30 * 20 - 36 * 26 * 16, rel=1e-9)


def test_grid_lines_include_planes_and_skip_slivers():
    lines = grid_lines(0, 40, 2.0, planes=np.array([4.0, 4.2, 20.0]), areas=np.array([500.0, 3.0, 100.0]))
    assert lines[0] == 0 and lines[-1] == 40
    assert 4.0 in lines and 20.0 in lines
    assert 4.2 not in lines                    # 0.2 mm from a bigger face: dropped
    assert np.diff(lines).min() > 0.6


def test_pitch_for_count():
    box = M.box_mesh((60, 80, 5))
    pitch = pitch_for_count(box, 12000)
    assert voxelize(box, pitch).count == pytest.approx(12000, rel=0.35)


def test_uniform_grid_helper():
    grid = VoxelGrid.uniform(np.ones((4, 2, 1), bool), (1, 2, 3), 0.5)
    assert grid.volume == pytest.approx(8 * 0.125)
    assert grid.centers()[0] == pytest.approx([1.25, 2.25, 3.25])
    assert grid.pitch == pytest.approx(0.5)
