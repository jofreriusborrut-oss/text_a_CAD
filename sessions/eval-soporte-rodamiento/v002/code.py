import cadquery as cq

PARAMS = {
    "axis_height": {"value": 25, "unit": "mm", "min": 15, "max": 80, "label": "Alçada de l'eix"},
    "base_length": {"value": 60, "unit": "mm", "min": 40, "max": 120, "label": "Llargada de la base (X)"},
    "base_width": {"value": 36, "unit": "mm", "min": 15, "max": 80, "label": "Amplada de la base (Y)"},
    "base_thickness": {"value": 5, "unit": "mm", "min": 3, "max": 12, "label": "Gruix de la base"},
    "block_thickness": {"value": 10, "unit": "mm", "min": 8, "max": 30, "label": "Gruix del bloc (Y)"},
    "bearing_od": {"value": 22, "unit": "mm", "min": 10, "max": 40, "label": "Diàmetre exterior del rodament"},
    "bearing_width": {"value": 7, "unit": "mm", "min": 3, "max": 15, "label": "Amplada del rodament"},
    "seat_clearance": {"value": 0.1, "unit": "mm", "min": 0, "max": 0.4, "label": "Joc del seient"},
    "seat_wall": {"value": 5, "unit": "mm", "min": 3, "max": 10, "label": "Paret al voltant del seient"},
    "through_bore": {"value": 16, "unit": "mm", "min": 8, "max": 30, "label": "Forat passant (ressalt)"},
    "screw_hole": {"value": 5.5, "unit": "mm", "min": 3, "max": 9, "label": "Forat de la base (M5 = 5,5)"},
    "screw_x": {"value": 22, "unit": "mm", "min": 10, "max": 55, "label": "Posició dels forats (X)"},
    "chamfer": {"value": 1, "unit": "mm", "min": 0, "max": 2, "label": "Xamfrà superior"},
}

AH = PARAMS["axis_height"]["value"]
BL = PARAMS["base_length"]["value"]
BWD = PARAMS["base_width"]["value"]
BT = PARAMS["base_thickness"]["value"]
T = PARAMS["block_thickness"]["value"]
OD = PARAMS["bearing_od"]["value"]
BRW = PARAMS["bearing_width"]["value"]
CL = PARAMS["seat_clearance"]["value"]
SW = PARAMS["seat_wall"]["value"]
BORE = PARAMS["through_bore"]["value"]
SH = PARAMS["screw_hole"]["value"]
SX = PARAMS["screw_x"]["value"]
CH = PARAMS["chamfer"]["value"]

PD = OD + CL                       # pocket diameter
BW = PD + 2 * SW                   # block width
AH = max(AH, BT + PD / 2 + 1)
BL = max(BL, BW + 2 * (SH + 4))
T = max(T, 6)
BWD = max(BWD, T)
DEPTH = min(BRW + 0.2, T - 2)
BORE = min(BORE, PD - 3)
SX = min(max(SX, BW / 2 + SH / 2 + 2), BL / 2 - SH / 2 - 2)
SH = min(SH, BWD - 4)
CH = min(CH, BT / 3, T / 4)

base = cq.Workplane("XY").box(BL, BWD, BT, centered=(True, True, False))
if CH > 0:
    base = base.faces(">Z").edges().chamfer(CH)

post = cq.Workplane("XY").box(BW, T, AH, centered=(True, True, False))
top = cq.Workplane("XZ").center(0, AH).circle(BW / 2).extrude(T / 2, both=True)
upper = post.union(top)
if CH > 0:
    # Chamfer the outline of the front and back faces, except the bottom edges.
    upper = upper.faces(">Y or <Y").edges("not <Z").chamfer(CH)
body = base.union(upper)

# Bearing pocket from the -Y face, and smaller through bore leaving a shoulder.
pocket = (cq.Workplane("XZ").center(0, AH).circle(PD / 2).extrude(DEPTH)
          .translate((0, -T / 2 + DEPTH, 0)))
bore = cq.Workplane("XZ").center(0, AH).circle(BORE / 2).extrude(T, both=True)
body = body.cut(pocket).cut(bore)

# Two M5 holes in the base.
holes = (cq.Workplane("XY").pushPoints([(-SX, 0), (SX, 0)]).circle(SH / 2).extrude(BT))
result = body.cut(holes)

EXPECTED_BBOX = (BL, BWD, AH + BW / 2)
EXPECTED_HOLES = [(PD, 1), (BORE, 1), (SH, 2)]

# Ghost bearing 608 in its seat (bore 8).
REFERENCE = (cq.Workplane("XZ").center(0, AH).circle(OD / 2).circle(4).extrude(BRW)
             .translate((0, -T / 2 + BRW, 0)))

LOAD_CASE = {
    "description": "Base fixed by the two M5 screws, 50 N downwards on the bearing seat",
    "fixed": [
        {"type": "hole", "axis": "z", "center": [-SX, 0, BT / 2], "diameter": SH},
        {"type": "hole", "axis": "z", "center": [SX, 0, BT / 2], "diameter": SH},
    ],
    "loads": [{"region": {"type": "hole", "axis": "y", "center": [0, 0, AH], "diameter": BORE},
               "force": [0, 0, -50]}],
}
