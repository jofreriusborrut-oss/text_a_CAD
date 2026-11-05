"""Load cases and the full simulation pipeline on simple parts (no CadQuery needed)."""
import base64

import numpy as np
import pytest

from textacad import mesh as M
from textacad.fea import SimulationError
from textacad.materials import get_material
from textacad.simulate import LoadCase, default_load_case, normalize_region, run_simulation

from . import shapes

BEAM_CASE = {
    "description": "Clamped at x = 0, 10 N down at the free end",
    "fixed": [{"type": "side", "side": "-x"}],
    "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -10]}],
}


def beam_deflection(material, L=100.0, b=10.0, h=5.0, F=10.0):
    I = b * h ** 3 / 12
    G = material.E / (2 * (1 + material.nu))
    return F * L ** 3 / (3 * material.E * I) + F * L / (5 / 6 * G * b * h)


def test_cantilever_end_to_end():
    petg = get_material("petg")
    res = run_simulation(shapes.beam(100, 10, 5), BEAM_CASE, "petg", "draft")
    assert res.max_displacement == pytest.approx(beam_deflection(petg), rel=0.04)
    assert res.applied_force == pytest.approx([0, 0, -10], abs=1e-9)
    assert res.reaction_force == pytest.approx([0, 0, 10], abs=1e-6)
    assert res.equilibrium_error < 1e-6
    assert abs(res.volume_error) < 1e-9
    # Bending stress at the root is M c / I = 24 MPa; away from the clamp it is a bit lower.
    assert 15 < res.max_stress < 26
    assert res.safety_factor == pytest.approx(petg.weak_axis_strength / res.max_stress)
    assert res.safety_factor_in_plane > res.safety_factor
    assert res.stiffness == pytest.approx(10 / res.max_displacement, rel=0.05)


def test_stiffer_material_bends_less_with_same_stress():
    part = shapes.beam(100, 10, 5)
    pla = run_simulation(part, BEAM_CASE, "pla", "draft")
    alu = run_simulation(part, BEAM_CASE, "al6061", "draft")
    assert pla.max_displacement / alu.max_displacement == pytest.approx(68900 / 3300, rel=0.03)
    assert pla.max_stress == pytest.approx(alu.max_stress, rel=0.05)
    assert alu.safety_factor > pla.safety_factor


def test_convergence_check_is_reported():
    res = run_simulation(shapes.beam(100, 10, 5), BEAM_CASE, "petg", "normal")
    assert res.convergence is not None
    assert res.convergence["displacement_change_percent"] < 5
    assert "not_converged_displacement" not in res.warnings
    assert res.n_elements > res.convergence["coarse_elements"]


def test_plate_held_by_a_bolt_hole():
    part = shapes.plate_with_holes(80, 30, 5, [(12, 15, 6.6)])
    case = {
        "fixed": [{"type": "hole", "axis": "z", "center": [12, 15, 0], "diameter": 6.6}],
        "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -20]}],
    }
    res = run_simulation(part, case, "petg", "draft")
    assert res.reaction_force == pytest.approx([0, 0, 20], abs=1e-5)
    assert res.max_displacement_at[0] > 70          # the free end moves most
    assert res.max_stress > 0


def test_own_weight_under_acceleration():
    part = shapes.beam(100, 10, 5)
    steel = get_material("s235")
    case = {"fixed": [{"type": "side", "side": "-x"}], "accel_g": [0, 0, -1]}
    res = run_simulation(part, case, steel, "draft")
    weight = part.volume * steel.density * 1e-6 * 9.80665        # N
    # The clamped layer of nodes carries its share directly, so slightly less than the full weight is applied.
    assert -res.applied_force[2] == pytest.approx(weight, rel=0.03)
    q = weight / 100.0                                           # N/mm, uniformly distributed load
    exact = q * 100 ** 4 / (8 * steel.E * (10 * 5 ** 3 / 12))
    assert res.max_displacement == pytest.approx(exact, rel=0.06)


def test_default_load_case_holds_the_biggest_face():
    part = shapes.l_bracket(40, 30, 4)
    case = default_load_case(part)
    assert case.fixed[0]["side"] in ("-z", "-x")                # base or wall: the two big flat sides
    res = run_simulation(part, case, "petg", "draft")
    assert res.max_displacement > 0


def test_drawing_data_is_the_real_surface_finely_divided():
    part = shapes.beam(100, 10, 5)
    res = run_simulation(part, BEAM_CASE, "petg", "draft")
    data = res.drawing_data()
    points = np.frombuffer(base64.b64decode(data["points"]), dtype="<f4").reshape(-1, 3)
    tris = np.frombuffer(base64.b64decode(data["triangles"]), dtype="<u4").reshape(-1, 3)
    levels = np.frombuffer(base64.b64decode(data["stress_levels"]), dtype=np.uint8)
    disp = np.frombuffer(base64.b64decode(data["displacement"]), dtype="<f4").reshape(-1, 3)
    assert len(levels) == len(points) == len(disp) and tris.max() < len(points)
    assert len(tris) > 20 * len(part)                    # 12 big triangles became hundreds of small ones
    # Still exactly the surface of the bar: closed, same area and volume, normals outwards.
    skin = M.Mesh(points[tris].astype(float))
    assert skin.is_watertight()
    assert skin.area == pytest.approx(part.area, rel=1e-5)
    assert skin.volume == pytest.approx(part.volume, rel=1e-5)
    outward = np.einsum("ij,ij->i", skin.normals, skin.centroids - skin.center_of_mass)
    assert (outward > 0).all()
    edges = np.linalg.norm(skin.triangles - np.roll(skin.triangles, -1, axis=1), axis=2)
    assert edges.max() <= 1.5 * res.pitch + 1e-6
    # The free end moves, the clamped end does not; the stress is highest near the clamp.
    assert np.abs(disp[points[:, 0] > 99, 2]).min() > 0.5 * res.max_displacement
    assert np.abs(disp[points[:, 0] < 1e-6]).max() < 1e-6
    assert data["scale_max_mpa"] == pytest.approx(res.max_stress, rel=1e-3)
    assert levels.max() == 255
    assert levels[points[:, 0] < 15].mean() > 3 * levels[points[:, 0] > 85].mean()


def test_drawing_of_a_part_with_a_hole_follows_the_round_hole():
    part = shapes.plate_with_holes(40, 30, 6, [(20, 15, 12)])
    res = run_simulation(part, {"fixed": [{"type": "side", "side": "-x"}],
                                "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -5]}]},
                         "petg", "draft")
    skin = M.Mesh(res.skin_points[res.skin_triangles])
    assert skin.is_watertight()
    assert skin.volume == pytest.approx(part.volume, rel=1e-6)          # the real part, not the block model
    r = np.hypot(res.skin_points[:, 0] - 20, res.skin_points[:, 1] - 15)
    assert np.isclose(r, 6.0, atol=1e-6).sum() > 100                     # many points on the round wall of the hole
    assert np.isfinite(res.skin_stress).all() and res.skin_stress.min() >= 0


def test_refine_surface_respects_the_triangle_limit():
    from textacad.simulate import refine_surface

    part = shapes.beam(100, 10, 5)
    points, tris = refine_surface(part, max_edge=0.2, limit=3000)
    assert len(tris) <= 3000 and M.Mesh(points[tris]).is_watertight()
    same_points, same_tris = refine_surface(part, max_edge=500)
    assert len(same_tris) == len(part) and len(same_points) == 8


@pytest.mark.parametrize("bad", [
    {},                                                                  # nothing
    {"fixed": [{"type": "side", "side": "-x"}]},                         # no load
    {"loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, 1]}]},   # not held
    {"fixed": [{"type": "side", "side": "left"}], "loads": []},          # bad side
    {"fixed": [{"type": "sausage"}], "loads": []},                       # bad type
])
def test_bad_load_cases_are_rejected(bad):
    with pytest.raises(SimulationError):
        LoadCase.from_dict(bad)


def test_region_that_selects_nothing_is_reported():
    case = {"fixed": [{"type": "box", "min": [500, 500, 500], "max": [600, 600, 600]}],
            "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -1]}]}
    with pytest.raises(SimulationError, match="selects no material"):
        run_simulation(shapes.beam(), case, "petg", "draft")


def test_open_mesh_cannot_be_simulated():
    box = M.box_mesh((10, 10, 10))
    with pytest.raises(SimulationError, match="closed"):
        run_simulation(M.Mesh(box.triangles[:-1]), BEAM_CASE, "petg", "draft")


def test_region_normalisation():
    assert normalize_region({"type": "hole", "axis": "Z", "center": [1, 2, 3], "radius": 3})["diameter"] == 6
    assert normalize_region({"type": "side", "side": " +X "})["side"] == "+x"
    box = normalize_region({"type": "box", "min": [5, 5, 5], "max": [0, 0, 0]})
    assert box["min"] == [0, 0, 0] and box["max"] == [5, 5, 5]


def test_load_at_the_centre_of_a_hole_goes_to_its_rim():
    """Claude often puts the load on the axis of a motor or a bolt: that point is in the air."""
    plate = shapes.plate_with_hole(60, 40, 5, hole_d=22)
    centre = [30.0, 20.0, 2.5]
    case = {"fixed": [{"type": "side", "side": "-x"}],
            "loads": [{"region": {"type": "point", "center": centre, "radius": 6}, "force": [0, 0, -20]}]}
    result = run_simulation(plate, case, "petg", "draft")
    assert "load_moved" in result.warnings
    assert result.applied_force == pytest.approx([0, 0, -20])
    assert result.equilibrium_error < 1e-6 and result.max_displacement > 0
    # A point far away from the part is still an error, not a silent guess.
    far = {"fixed": [{"type": "side", "side": "-x"}],
           "loads": [{"region": {"type": "point", "center": [30, 20, 200], "radius": 6}, "force": [0, 0, -20]}]}
    with pytest.raises(SimulationError, match="selects no free material"):
        run_simulation(plate, far, "petg", "draft")
