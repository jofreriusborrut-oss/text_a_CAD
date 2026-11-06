import cadquery as cq

PARAMS = {
    "width": {"value": 60, "unit": "mm", "min": 45, "max": 120, "label": "Amplada (X)"},
    "height": {"value": 56, "unit": "mm", "min": 45, "max": 120, "label": "Alçada de la placa (Z)"},
    "depth": {"value": 50, "unit": "mm", "min": 30, "max": 120, "label": "Fons de la base (Y)"},
    "plate_t": {"value": 5, "unit": "mm", "min": 3, "max": 12, "label": "Gruix de la placa vertical"},
    "base_t": {"value": 5, "unit": "mm", "min": 3, "max": 12, "label": "Gruix de la base"},
    "motor_center_z": {"value": 31, "unit": "mm", "min": 22, "max": 100, "label": "Alçada del centre del motor"},
    "pilot_diameter": {"value": 22.5, "unit": "mm", "min": 20, "max": 30, "label": "Forat central del motor"},
    "motor_bolt_square": {"value": 31, "unit": "mm", "min": 20, "max": 40, "label": "Quadrat dels forats M3"},
    "motor_bolt_hole": {"value": 3.4, "unit": "mm", "min": 2.5, "max": 4.5, "label": "Forats M3 (3,4)"},
    "base_hole": {"value": 5.5, "unit": "mm", "min": 3, "max": 9, "label": "Forats M5 de la base (5,5)"},
    "base_hole_edge": {"value": 8, "unit": "mm", "min": 5, "max": 20, "label": "Distància dels forats a la vora"},
    "rib_t": {"value": 5, "unit": "mm", "min": 3, "max": 10, "label": "Gruix dels nervis"},
    "rib_length": {"value": 40, "unit": "mm", "min": 10, "max": 100, "label": "Llargada del nervi (sobre la base)"},
    "rib_height": {"value": 35, "unit": "mm", "min": 10, "max": 100, "label": "Alçada del nervi"},
}

W = PARAMS["width"]["value"]
H = PARAMS["height"]["value"]
D = PARAMS["depth"]["value"]
T = PARAMS["plate_t"]["value"]
BT = PARAMS["base_t"]["value"]
HC = PARAMS["motor_center_z"]["value"]
PIL = PARAMS["pilot_diameter"]["value"]
SQ = PARAMS["motor_bolt_square"]["value"]
MH = PARAMS["motor_bolt_hole"]["value"]
BH = PARAMS["base_hole"]["value"]
BE = PARAMS["base_hole_edge"]["value"]
RT = PARAMS["rib_t"]["value"]
RL = PARAMS["rib_length"]["value"]
RH = PARAMS["rib_height"]["value"]

H = max(H, BT + 20)
D = max(D, T + 20)
BT = min(BT, H / 4)
SQ = min(SQ, W - MH - 6)
PIL = min(PIL, SQ - MH - 2)
HC = min(max(HC, SQ / 2 + MH / 2 + 2, BT + SQ / 2 + MH / 2 + 2), H - SQ / 2 - MH / 2 - 2)
BH = min(BH, 8)
BE = max(BE, BH / 2 + 2)
RT = min(RT, W / 4)
RL = min(RL, D - T - 1)
RH = min(RH, H - 2)
YB = -(D - T)   # back edge of the base

plate = cq.Workplane("XY").box(W, T, H, centered=(True, False, False))
base = cq.Workplane("XY").box(W, D, BT, centered=(True, False, False)).translate((0, YB, 0))
body = plate.union(base)

# Triangular ribs at both sides (profile in the YZ plane, extruded along X)
prof = [(T / 2, 0), (-RL, 0), (T / 2, RH)]
for sx in (-1, 1):
    x0 = sx * (W / 2 - RT / 2) - RT / 2
    rib = cq.Workplane("YZ").workplane(offset=x0).polyline(prof).close().extrude(RT)
    body = body.union(rib)

# Motor holes through the plate (along Y)
cutter = cq.Workplane("XZ").center(0, HC).circle(PIL / 2).extrude(T * 2, both=True)
pts = [(sx * SQ / 2, HC + sy * SQ / 2) for sx in (-1, 1) for sy in (-1, 1)]
cutter = cutter.union(cq.Workplane("XZ").pushPoints(pts).circle(MH / 2).extrude(T * 2, both=True))
body = body.cut(cutter)

# M5 holes in the base
hx = W / 2 - BE
hole_pts = [(sx * hx, y) for sx in (-1, 1) for y in (-BE, YB + BE)]
bh = cq.Workplane("XY").pushPoints(hole_pts).circle(BH / 2).extrude(BT)
result = body.cut(bh)

EXPECTED_BBOX = (W, D, H)
EXPECTED_HOLES = [(PIL, 1), (MH, 4), (BH, 4)]

LOAD_CASE = {
    "description": "Base fixed by the M5 bolts, 30 N downwards at the motor",
    "fixed": [{"type": "hole", "axis": "z", "center": [sx * hx, y, BT / 2], "diameter": BH}
              for sx in (-1, 1) for y in (-BE, YB + BE)],
    "loads": [{"region": {"type": "point", "center": [0, T, HC], "radius": 8}, "force": [0, 0, -30]}],
}
