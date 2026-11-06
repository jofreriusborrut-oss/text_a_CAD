import math
import cadquery as cq

PARAMS = {
    "plate_width": {"value": 60, "unit": "mm", "min": 30, "max": 150, "label": "Amplada de la placa (Y)"},
    "plate_height": {"value": 40, "unit": "mm", "min": 20, "max": 150, "label": "Alçada de la placa (Z)"},
    "plate_thickness": {"value": 5, "unit": "mm", "min": 3, "max": 15, "label": "Gruix de la placa (X)"},
    "hole_diameter": {"value": 5.5, "unit": "mm", "min": 3, "max": 10, "label": "Forats de la placa (M5 = 5,5)"},
    "hole_spacing": {"value": 44, "unit": "mm", "min": 20, "max": 120, "label": "Distància entre forats"},
    "tube_diameter": {"value": 25, "unit": "mm", "min": 8, "max": 60, "label": "Diàmetre del tub"},
    "tube_clearance": {"value": 0.3, "unit": "mm", "min": 0, "max": 1, "label": "Joc del tub"},
    "sleeve_wall": {"value": 4, "unit": "mm", "min": 2, "max": 10, "label": "Paret del casquet"},
    "sleeve_length": {"value": 40, "unit": "mm", "min": 20, "max": 120, "label": "Llargada del casquet"},
    "angle": {"value": 30, "unit": "deg", "min": 0, "max": 60, "label": "Inclinació respecte a l'horitzontal"},
}

W = PARAMS["plate_width"]["value"]
H = PARAMS["plate_height"]["value"]
T = PARAMS["plate_thickness"]["value"]
HOLE = PARAMS["hole_diameter"]["value"]
HS = PARAMS["hole_spacing"]["value"]
D = PARAMS["tube_diameter"]["value"]
C = PARAMS["tube_clearance"]["value"]
WALL = PARAMS["sleeve_wall"]["value"]
L = PARAMS["sleeve_length"]["value"]
A = PARAMS["angle"]["value"]

ca = math.cos(math.radians(A))
sa = math.sin(math.radians(A))
RB = (D + C) / 2
RO = RB + WALL
HS = max(HS, 2 * RO + HOLE + 4)
W = max(W, HS + HOLE + 6)
H = max(H, 2 * RO / ca + 2)
ZC = H / 2
TS = (T + RB * sa) / ca            # distance along the axis where the bore starts
L = max(L, TS + 10)

d = cq.Vector(ca, 0, sa)

plate = cq.Workplane("XY").box(T, W, H, centered=(False, True, False))
sleeve = cq.Workplane("XY").add(cq.Solid.makeCylinder(RO, L, cq.Vector(0, 0, ZC), d))
body = plate.union(sleeve)
# remove whatever of the sleeve pokes behind the wall
body = body.cut(cq.Workplane("XY").box(2 * L, W + 2 * RO, 3 * H + 2 * L, centered=(False, True, True)).translate((-2 * L, 0, 0)))

p0 = cq.Vector(TS * ca, 0, ZC + TS * sa)
bore = cq.Workplane("XY").add(cq.Solid.makeCylinder(RB, L - TS, p0, d))
body = body.cut(bore)

for sy in (-1, 1):
    h = cq.Workplane("YZ").center(sy * HS / 2, ZC).circle(HOLE / 2).extrude(T)
    body = body.cut(h)

result = body

XE = L * ca
ZE = ZC + L * sa
EXPECTED_BBOX = (XE + RO * sa, max(W, 2 * RO), max(H, ZE + RO * ca))
EXPECTED_HOLES = [(2 * RB, 1), (HOLE, 2)]

REFERENCE = cq.Workplane("XY").add(cq.Solid.makeCylinder(D / 2, L - TS + 10, p0, d))

LOAD_CASE = {
    "description": "Placa fixada per dos cargols M5; 50 N cap avall a l'extrem del casquet",
    "fixed": [
        {"type": "hole", "axis": "x", "center": [T / 2, -HS / 2, ZC], "diameter": HOLE},
        {"type": "hole", "axis": "x", "center": [T / 2, HS / 2, ZC], "diameter": HOLE},
    ],
    "loads": [
        {"region": {"type": "box",
                    "min": [XE - 3, -RO - 1, ZE - RO - 3],
                    "max": [XE + 3, RO + 1, ZE + RO + 3]},
         "force": [0, 0, -50]}
    ],
}
