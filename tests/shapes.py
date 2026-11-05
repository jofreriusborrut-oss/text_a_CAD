"""Simple test parts built without CadQuery (see textacad/mesh.py).

All of them are proper closed surfaces without internal faces, like the STL
that CadQuery exports.
"""
import numpy as np

from textacad import mesh as M


def beam(length=100.0, width=10.0, height=5.0):
    """Rectangular bar along X, from the origin."""
    return M.box_mesh((length, width, height))


def plate_with_hole(length=60.0, width=40.0, thickness=5.0, hole_d=10.0, segments=96):
    """Plate on the XY plane with a through hole in the middle."""
    return plate_with_holes(length, width, thickness, [(length / 2, width / 2, hole_d)], segments)


def plate_with_holes(length, width, thickness, holes, segments=64):
    """Plate with through holes given as (x, y, diameter).

    The top and bottom faces are not re-triangulated around the holes: the
    hole is a separate inward-facing cylinder. That is enough for volume,
    voxelisation and simulation tests.
    """
    parts = [M.box_mesh((length, width, thickness))]
    for x, y, d in holes:
        parts.append(M.flipped(M.cylinder_mesh(d / 2, thickness, center=(x, y), segments=segments)))
    return M.merge(*parts)


def _prism_xz(profile, width):
    """Extrude a polygon drawn in the XZ plane along +Y.

    `profile` lists the (x, z) corners counter-clockwise when looking along
    +Y... the triangles are oriented so that normals point outwards. The
    polygon must be visible from its first corner (true for L and U shapes
    listed from an outer corner).
    """
    p = np.asarray(profile, dtype=float)
    n = len(p)
    front = np.column_stack([p[:, 0], np.zeros(n), p[:, 1]])          # y = 0
    back = np.column_stack([p[:, 0], np.full(n, width), p[:, 1]])     # y = width
    tris = []
    for i in range(1, n - 1):                                         # caps: fan from corner 0
        tris.append((front[0], front[i], front[i + 1]))
        tris.append((back[0], back[i + 1], back[i]))
    for i in range(n):                                                # side walls
        j = (i + 1) % n
        tris.append((front[i], back[i], back[j]))
        tris.append((front[i], back[j], front[j]))
    mesh = M.Mesh(np.array(tris))
    # Make sure the normals point outwards (positive signed volume).
    t = mesh.triangles
    signed = np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum()
    return mesh if signed > 0 else M.flipped(mesh)


def l_bracket(leg=40.0, width=30.0, thickness=4.0):
    """L bracket: a base along X (on z = 0) and a wall along Z at x = 0."""
    t = thickness
    profile = [(0, 0), (leg, 0), (leg, t), (t, t), (t, leg), (0, leg)]
    return _prism_xz(profile, width)


def open_box(length=40.0, width=30.0, height=20.0, wall=2.0):
    """Box open at the top (a tray), with the given wall and floor thickness."""
    L, W, H, t = length, width, height, wall
    o = np.array([[0, 0], [L, 0], [L, W], [0, W]], dtype=float)                 # outer corners
    i = np.array([[t, t], [L - t, t], [L - t, W - t], [t, W - t]], dtype=float)  # inner corners

    def pt(xy, z):
        return (xy[0], xy[1], z)

    tris = [(pt(o[0], 0), pt(o[2], 0), pt(o[1], 0)), (pt(o[0], 0), pt(o[3], 0), pt(o[2], 0)),   # underside
            (pt(i[0], t), pt(i[1], t), pt(i[2], t)), (pt(i[0], t), pt(i[2], t), pt(i[3], t))]   # floor
    for a in range(4):
        b = (a + 1) % 4
        tris += [(pt(o[a], 0), pt(o[b], 0), pt(o[b], H)), (pt(o[a], 0), pt(o[b], H), pt(o[a], H))]   # outer wall
        tris += [(pt(i[a], t), pt(i[b], H), pt(i[b], t)), (pt(i[a], t), pt(i[a], H), pt(i[b], H))]   # inner wall
        tris += [(pt(o[a], H), pt(o[b], H), pt(i[b], H)), (pt(o[a], H), pt(i[b], H), pt(i[a], H))]   # top rim
    return M.Mesh(np.array(tris))


def stl_bytes(mesh):
    return M.dump_stl(mesh)
