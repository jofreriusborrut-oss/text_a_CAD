import cadquery as cq

PARAMS = {
    "base_length": {"value": 40, "unit": "mm", "min": 20, "max": 100, "label": "Base length (X)"},
    "base_width": {"value": 30, "unit": "mm", "min": 20, "max": 100, "label": "Base width (Y)"},
    "base_thickness": {"value": 4, "unit": "mm", "min": 2, "max": 10, "label": "Base thickness"},
    "corner_radius": {"value": 4, "unit": "mm", "min": 0, "max": 12, "label": "Base corner radius"},
    "base_hole": {"value": 3.4, "unit": "mm", "min": 2, "max": 6, "label": "Base hole diameter"},
    "base_hole_inset": {"value": 4, "unit": "mm", "min": 3, "max": 10, "label": "Base hole distance from edges"},
    "prong_thickness": {"value": 3, "unit": "mm", "min": 2, "max": 8, "label": "Prong thickness"},
    "prong_gap": {"value": 3.2, "unit": "mm", "min": 2, "max": 10, "label": "Gap between prongs"},
    "prong_width": {"value": 15, "unit": "mm", "min": 8, "max": 30, "label": "Prong width (X)"},
    "prong_height": {"value": 15, "unit": "mm", "min": 8, "max": 40, "label": "Prong height above base"},
    "cross_hole": {"value": 5, "unit": "mm", "min": 2, "max": 8, "label": "Cross hole diameter"},
    "cross_hole_height": {"value": 9, "unit": "mm", "min": 4, "max": 35, "label": "Cross hole height above base"},
}

L = PARAMS["base_length"]["value"]
W = PARAMS["base_width"]["value"]
TB = PARAMS["base_thickness"]["value"]
R = PARAMS["corner_radius"]["value"]
BH = PARAMS["base_hole"]["value"]
INS = PARAMS["base_hole_inset"]["value"]
TP = PARAMS["prong_thickness"]["value"]
GAP = PARAMS["prong_gap"]["value"]
PW = PARAMS["prong_width"]["value"]
PH = PARAMS["prong_height"]["value"]
CH = PARAMS["cross_hole"]["value"]
CZ = PARAMS["cross_hole_height"]["value"]

# Keep the geometry valid.
R = min(R, L / 2 - 0.5, W / 2 - 0.5)
INS = max(INS, BH / 2 + 1.5)
INS = min(INS, L / 2 - BH / 2 - 0.5, W / 2 - BH / 2 - 0.5)
TP = min(TP, (W - 2) / 5)
GAP = min(GAP, (W - 3 * TP - 2) / 2)
GAP = max(GAP, 0.5)
PW = min(PW, L - 2)
CH = min(CH, PW - 3)
PH = max(PH, CH / 2 + 2)
CZ = min(max(CZ, CH / 2 + 1), PH - CH / 2 - 1)
TOTAL_Y = 3 * TP + 2 * GAP

# Base
base = cq.Workplane("XY").box(L, W, TB, centered=(True, True, False))
if R > 0:
    base = base.edges("|Z").fillet(R)
pts = [(sx * (L / 2 - INS), sy * (W / 2 - INS)) for sx in (-1, 1) for sy in (-1, 1)]
base = base.cut(cq.Workplane("XY").pushPoints(pts).circle(BH / 2).extrude(TB))

# Three prongs, side by side along Y.
def prong(y_center):
    return (cq.Workplane("XY").workplane(offset=TB - 0.01)
            .center(0, y_center).rect(PW, TP).extrude(PH + 0.01))

pitch = GAP + TP
prongs = prong(-pitch).union(prong(0)).union(prong(pitch))

# Round the prong tops.
zc = TB + CZ
rr = min(PW / 2, TB + PH - zc)
if rr > 0.5:
    top_keep = cq.Workplane("XZ").center(0, zc).circle(PW / 2).extrude(TOTAL_Y, both=True)
    lower_box = (cq.Workplane("XY").box(PW, TOTAL_Y, zc - TB + 0.01, centered=(True, True, False))
                 .translate((0, 0, TB - 0.01)))
    prongs = prongs.intersect(top_keep.union(lower_box))

body = base.union(prongs)

# Cross hole along Y through all three prongs.
cross = cq.Workplane("XZ").center(0, zc).circle(CH / 2).extrude(TOTAL_Y, both=True)
result = body.cut(cross)

top = min(TB + PH, zc + PW / 2)
EXPECTED_BBOX = (L, W, max(top, zc + CH / 2))
EXPECTED_HOLES = [(BH, 4), (CH, 1)]

LOAD_CASE = {
    "description": "Base screwed down by four bolts; 30 N pull on the cross screw (camera load)",
    "fixed": [{"type": "hole", "axis": "z", "center": [p[0], p[1], 0], "diameter": BH} for p in pts],
    "loads": [{"region": {"type": "hole", "axis": "y", "center": [0, 0, zc], "diameter": CH},
               "force": [0, 0, 30]}],
}
