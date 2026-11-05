"""Finite element solver checked against textbook solutions (no CadQuery needed)."""
import numpy as np
import pytest

from textacad import fea
from textacad import mesh as M
from textacad.voxel import VoxelGrid, voxelize

E, NU = 2000.0, 0.35


def cantilever(grid, length, force=10.0, nu=NU):
    model = fea.build_model(grid)
    fixed = model.coords[:, 0] < 1e-9
    tip = model.coords[:, 0] > length - 1e-9
    f = np.zeros((model.n_nodes, 3))
    f[tip, 2] = -force / tip.sum()
    sol = fea.solve(model, E, nu, fixed, f)
    return model, sol, tip, f


def beam_theory(length, b, h, force=10.0, nu=NU):
    inertia = b * h ** 3 / 12
    shear_modulus = E / (2 * (1 + nu))
    return force * length ** 3 / (3 * E * inertia) + force * length / (5 / 6 * shear_modulus * b * h)


def test_element_matrix_has_six_rigid_body_modes():
    K, _ = fea.element_matrices((1.0, 2.0, 0.5), NU)
    assert np.allclose(K, K.T)
    eig = np.linalg.eigvalsh(K)
    assert np.sum(np.abs(eig) < 1e-9 * eig.max()) == 6      # 3 translations + 3 rotations cost no energy
    assert eig.min() > -1e-9 * eig.max()


def test_element_stiffness_scales_with_size():
    K1, _ = fea.element_matrices((1.0, 2.0, 0.5), NU)
    K3, _ = fea.element_matrices((3.0, 6.0, 1.5), NU)
    assert np.allclose(K3, 3 * K1)


def test_bar_in_tension_is_exact():
    # With Poisson's ratio 0 the clamped end does not disturb the stress:
    # elongation = F L / (E A), stress = F / A everywhere.
    L, b, h, F = 50.0, 10.0, 10.0, 400.0
    grid = VoxelGrid.uniform(np.ones((10, 2, 2), bool), (0, 0, 0), 5.0)
    model = fea.build_model(grid)
    fixed = model.coords[:, 0] < 1e-9
    end = model.coords[:, 0] > L - 1e-9
    f = np.zeros((model.n_nodes, 3))
    # Consistent nodal forces for a uniform pull: corner 1/4, edge 1/2, inner 1 share.
    yz = model.coords[end][:, 1:]
    share = np.where((yz[:, 0] == 0) | (yz[:, 0] == b), 0.5, 1.0) * np.where((yz[:, 1] == 0) | (yz[:, 1] == h), 0.5, 1.0)
    f[end, 0] = F * share / share.sum()
    sol = fea.solve(model, E, 0.0, fixed, f)
    assert sol.displacement[end, 0] == pytest.approx(F * L / (E * b * h), rel=1e-8)
    st = fea.stresses(model, sol.displacement, E, 0.0)
    assert st.tensor[:, 0] == pytest.approx(F / (b * h), rel=1e-8)
    assert st.center == pytest.approx(F / (b * h), rel=1e-8)
    assert st.peak == pytest.approx(F / (b * h), rel=1e-8)


@pytest.mark.parametrize("pitch", [10.0, 5.0, 2.5])
def test_cantilever_deflection_matches_beam_theory(pitch):
    L, b, h = 100.0, 10.0, 10.0
    n = (round(L / pitch), round(b / pitch), round(h / pitch))
    model, sol, tip, _ = cantilever(VoxelGrid.uniform(np.ones(n, bool), (0, 0, 0), pitch), L)
    deflection = -sol.displacement[tip, 2].mean()
    # Even ONE element through the thickness is within 3 % (plain bricks would be ~50 % too stiff).
    assert deflection == pytest.approx(beam_theory(L, b, h), rel=0.03)


def test_cantilever_bending_stress():
    L, b, h, F, pitch = 100.0, 10.0, 10.0, 10.0, 2.5
    model, sol, _, _ = cantilever(VoxelGrid.uniform(np.ones((40, 4, 4), bool), (0, 0, 0), pitch), L, F)
    st = fea.stresses(model, sol.displacement, E, NU)
    mid_top = (np.abs(model.centers[:, 0] - 51.25) < 0.1) & (model.centers[:, 2] > h - pitch)
    x = model.centers[mid_top, 0].mean()
    z = h / 2 - pitch / 2                                    # element centre, measured from the neutral axis
    expected = F * (L - x) * z / (b * h ** 3 / 12)
    assert st.tensor[mid_top, 0].mean() == pytest.approx(expected, rel=0.02)


def test_reactions_balance_the_load():
    model, sol, _, f = cantilever(VoxelGrid.uniform(np.ones((20, 2, 2), bool), (0, 0, 0), 5.0), 100.0)
    assert sol.reactions.sum(axis=0) == pytest.approx(-f.sum(axis=0), abs=1e-8)
    assert sol.residual < 1e-8


def test_direct_and_iterative_solvers_agree():
    grid = VoxelGrid.uniform(np.ones((24, 4, 4), bool), (0, 0, 0), 2.5)
    model = fea.build_model(grid)
    fixed = model.coords[:, 0] < 1e-9
    tip = model.coords[:, 0] > 60 - 1e-9
    f = np.zeros((model.n_nodes, 3))
    f[tip, 2] = -1.0
    direct = fea.solve(model, E, NU, fixed, f, direct_limit=10 ** 9)
    iterative = fea.solve(model, E, NU, fixed, f, direct_limit=0)
    assert direct.method == "direct" and iterative.method == "cg"
    scale = np.abs(direct.displacement).max()
    assert np.allclose(direct.displacement, iterative.displacement, atol=1e-5 * scale)


def test_grid_that_follows_the_faces_gives_the_same_beam():
    # 100 x 10 x 5 bar meshed with a pitch that does not divide its size.
    L, b, h = 100.0, 10.0, 5.0
    grid = voxelize(M.box_mesh((L, b, h)), 1.3)
    assert grid.volume == pytest.approx(L * b * h)
    model, sol, tip, _ = cantilever(grid, L)
    assert -sol.displacement[tip, 2].mean() == pytest.approx(beam_theory(L, b, h), rel=0.03)


def test_unheld_part_is_rejected():
    model = fea.build_model(VoxelGrid.uniform(np.ones((4, 2, 2), bool), (0, 0, 0), 1.0))
    f = np.zeros((model.n_nodes, 3))
    f[-1, 2] = 1
    with pytest.raises(fea.SimulationError):
        fea.solve(model, E, NU, np.zeros(model.n_nodes, bool), f)


def test_loose_piece_is_rejected():
    # Two separate blocks: only the first is held, the load is on the second.
    solid = np.ones((5, 2, 2), bool)
    solid[2] = False
    model = fea.build_model(VoxelGrid.uniform(solid, (0, 0, 0), 1.0))
    fixed = model.coords[:, 0] < 1e-9
    f = np.zeros((model.n_nodes, 3))
    f[model.coords[:, 0] > 5 - 1e-9, 2] = -1
    with pytest.raises(fea.SimulationError):
        fea.solve(model, E, NU, fixed, f)


def test_von_mises_of_simple_states():
    assert fea.von_mises(np.array([100.0, 0, 0, 0, 0, 0])) == pytest.approx(100)
    assert fea.von_mises(np.array([50.0, 50, 50, 0, 0, 0])) == pytest.approx(0)          # pure pressure
    assert fea.von_mises(np.array([0.0, 0, 0, 10, 0, 0])) == pytest.approx(10 * np.sqrt(3))  # pure shear
