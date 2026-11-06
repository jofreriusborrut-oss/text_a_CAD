import math
import cadquery as cq

PARAMS = {
    "width": {"value": 100, "unit": "mm", "min": 50, "max": 150, "label": "Width (X)"},
    "base_thickness": {"value": 6, "unit": "mm", "min": 3, "max": 15, "label": "Base thickness"},
    "slot_width": {"value": 12, "unit": "mm", "min": 6, "max": 25, "label": "Phone slot width"},
    "lip_height": {"value": 10, "unit": "mm", "min": 4, "max": 30, "label": "Front lip height"},
    "lip_thickness": {"value": 8, "unit": "mm", "min": 3, "max": 20, "label": "Front lip thickness"},
    "back_height": {"value": 90, "unit": "mm", "min": 40, "max": 160, "label": "Back plate height above base"},
    "back_thickness": {"value": 8, "unit": "mm", "min": 3, "max": 20, "label": "Back plate thickness"},
    "back_angle": {"value": 20, "unit": "deg", "min": 5, "max": 40, "label": "Back lean from vertical"},
    "rear_extension": {"value": 25, "unit": "mm", "min": 0, "max": 60, "label": "Base extension behind the back plate"},
    "cable_width": {"value": 15, "unit": "mm", "min": 5, "max": 40, "label": "Cable cut-out width"},
    "foot_diameter": {"value": 8, "unit": "mm", "min": 4, "max": 20, "label": "Rubber foot pocket diameter"},
    "foot_depth": {"value": 1, "unit": "mm", "min": 0.5, "max": 4, "label": "Rubber foot pocket depth"},
    "foot_inset": {"value": 12, "unit": "mm", "min": 6, "max": 30, "label": "Foot pocket distance from edges"},
}

W = PARAMS["width"]["value"]
T = PARAMS["base_thickness"]["value"]
S = PARAMS["slot_width"]["value"]
LH = PARAMS["lip_height"]["value"]
LT = PARAMS["lip_thickness"]["value"]
BH = PARAMS["back_height"]["value"]
BT = PARAMS["back_thickness"]["value"]
ANG = PARAMS["back_angle"]["value"]
EXT = PARAMS["rear_extension"]["value"]
CW = PARAMS["cable_width"]["value"]
FD = PARAMS["foot_diameter"]["value"]
FDEP = PARAMS["foot_depth"]["value"]
FIN = PARAMS["foot_inset"]["value"]

CW = min(CW, W - 10)
off = BH * math.tan(math.radians(ANG))   # how far the top of the plate leans back
yf = LT + S                              # front face of the back plate at the floor
yb = yf + BT                             # rear face of the back plate at the floor
D = yb + max(EXT, off)                   # total depth

# Keep the foot pockets inside the base and the base solid.
FDEP = min(FDEP, T - 2)
FD = min(FD, W / 2 - 2, D / 2 - 2)
FIN = max(FIN, FD / 2 + 2)
FIN = min(FIN, D / 2 - FD / 2 - 1, W / 2 - FD / 2 - 1)

# Side profile in the YZ plane (local x = Y, local y = Z), extruded along X.
profile = [
    (0, 0), (D, 0), (D, T), (yb, T),
    (yb + off, T + BH), (yf + off, T + BH),
    (yf, T), (LT, T), (LT, T + LH), (0, T + LH),
]
body = cq.Workplane("YZ").polyline(profile).close().extrude(W / 2, both=True)

# Cable cut-out in the middle of the lip, down to the slot floor.
cut = (
    cq.Workplane("XY")
    .box(CW, LT + 2, LH + 1, centered=(True, False, False))
    .translate((0, -1, T))
)
result = body.cut(cut).translate((0, -D / 2, 0))

# Four round pockets under the base for rubber feet.
pts = [(sx * (W / 2 - FIN), sy * (D / 2 - FIN)) for sx in (-1, 1) for sy in (-1, 1)]
feet = cq.Workplane("XY").pushPoints(pts).circle(FD / 2).extrude(FDEP)
result = result.cut(feet)

EXPECTED_BBOX = (W, D, T + BH)
EXPECTED_HOLES = [(FD, 4)]
