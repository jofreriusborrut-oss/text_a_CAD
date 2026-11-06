import cadquery as cq

PARAMS = {
    "base_length": {"value": 60, "unit": "mm", "min": 40, "max": 200, "label": "Llargada de la base (X)"},
    "base_width": {"value": 25, "unit": "mm", "min": 15, "max": 100, "label": "Amplada (Y)"},
    "thickness": {"value": 5, "unit": "mm", "min": 3, "max": 15, "label": "Gruix de base i ala"},
    "wing_height": {"value": 35, "unit": "mm", "min": 15, "max": 120, "label": "Alçada total de l'ala (Z)"},
    "inner_radius": {"value": 3, "unit": "mm", "min": 1.5, "max": 10, "label": "Radi interior"},
    "base_hole": {"value": 6.6, "unit": "mm", "min": 3, "max": 12, "label": "Forats de la base (M6 = 6,6)"},
    "base_hole_spacing": {"value": 40, "unit": "mm", "min": 15, "max": 150, "label": "Separació dels forats"},
    "wing_hole": {"value": 3.3, "unit": "mm", "min": 2, "max": 8, "label": "Forat roscat ala (M4 = 3,3)"},
    "wing_hole_height": {"value": 25, "unit": "mm", "min": 10, "max": 110, "label": "Alçada del forat de l'ala"},
    "rib_thickness": {"value": 4, "unit": "mm", "min": 2, "max": 10, "label": "Gruix dels nervis"},
    "rib_length": {"value": 20, "unit": "mm", "min": 5, "max": 100, "label": "Llargada del nervi sobre la base"},
    "rib_height": {"value": 20, "unit": "mm", "min": 5, "max": 100, "label": "Alçada del nervi sobre l'ala"},
}

L = PARAMS["base_length"]["value"]
W = PARAMS["base_width"]["value"]
T = PARAMS["thickness"]["value"]
H = PARAMS["wing_height"]["value"]
R = PARAMS["inner_radius"]["value"]
BH = PARAMS["base_hole"]["value"]
SP = PARAMS["base_hole_spacing"]["value"]
WH = PARAMS["wing_hole"]["value"]
HZ = PARAMS["wing_hole_height"]["value"]
RT = PARAMS["rib_thickness"]["value"]
RL = PARAMS["rib_length"]["value"]
RH = PARAMS["rib_height"]["value"]

H = max(H, T + R + 8)
R = min(R, H - T - 2, L / 4)
BH = min(BH, W - 4)
WH = min(WH, W - 4, T * 2)
free_len = L - T                      # base length not occupied by the wing
SP = min(SP, free_len - BH - 4)
HZ = min(max(HZ, T + R + WH / 2 + 1), H - WH / 2 - 2)
cx = -L / 2 + free_len / 2            # centre of the free part of the base
RT = min(RT, W / 4)
RL = min(RL, free_len - 2)
RH = min(RH, H - T - 2)

# L profile in XZ with an inner fillet, extruded symmetrically along Y.
k = 0.70710678 * R
xi = L / 2 - T
profile = (
    cq.Workplane("XZ")
    .moveTo(-L / 2, 0)
    .lineTo(L / 2, 0)
    .lineTo(L / 2, H)
    .lineTo(xi, H)
    .lineTo(xi, T + R)
    .threePointArc((xi - R + k, T + R - k), (xi - R, T))
    .lineTo(-L / 2, T)
    .close()
)
body = profile.extrude(W / 2, both=True)

# Triangular gussets, one on each side, flush with the base edges.
# The profile overlaps the wing and the base by 1 mm so the union is solid.
rib_pts = [(xi - RL, T), (xi, T + RH), (xi + 1, T + RH), (xi + 1, T - 1), (xi - RL, T - 1)]
rib = cq.Workplane("XZ").polyline(rib_pts).close().extrude(RT)   # spans y = 0 .. -RT
rib_neg = rib.translate((0, -(W / 2 - RT), 0))
rib_pos = rib.translate((0, W / 2, 0))
body = body.union(rib_neg).union(rib_pos)

# Two M6 clearance holes through the base.
pts = [(cx - SP / 2, 0), (cx + SP / 2, 0)]
bolts = cq.Workplane("XY").pushPoints(pts).circle(BH / 2).extrude(T)
body = body.cut(bolts)

# Tapped M4 hole (tap drill) through the wing, along X.
stud = cq.Workplane("YZ").workplane(offset=xi - 1).center(0, HZ).circle(WH / 2).extrude(T + 2)
result = body.cut(stud)

EXPECTED_BBOX = (L, W, H)
EXPECTED_HOLES = [(BH, 2), (WH, 1)]

LOAD_CASE = {
    "description": "Fixat pels dos forats M6 de la base, 30 N a la ròtula en direcció X",
    "fixed": [
        {"type": "hole", "axis": "z", "center": [cx - SP / 2, 0, T / 2], "diameter": BH},
        {"type": "hole", "axis": "z", "center": [cx + SP / 2, 0, T / 2], "diameter": BH},
    ],
    "loads": [{"region": {"type": "hole", "axis": "x", "center": [L / 2 - T / 2, 0, HZ], "diameter": WH}, "force": [30, 0, 0]}],
}
