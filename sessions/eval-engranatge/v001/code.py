import math
import cadquery as cq

PARAMS = {
    "module": {"value": 2, "unit": "mm", "min": 0.5, "max": 8, "label": "Mòdul"},
    "teeth": {"value": 20, "unit": "count", "min": 12, "max": 60, "label": "Nombre de dents"},
    "pressure_angle": {"value": 20, "unit": "deg", "min": 14.5, "max": 25, "label": "Angle de pressió"},
    "thickness": {"value": 10, "unit": "mm", "min": 2, "max": 50, "label": "Gruix"},
    "bore_diameter": {"value": 8, "unit": "mm", "min": 3, "max": 40, "label": "Diàmetre del forat"},
    "keyway_width": {"value": 3, "unit": "mm", "min": 1, "max": 10, "label": "Ample del xaveter"},
    "keyway_depth": {"value": 1.4, "unit": "mm", "min": 0.5, "max": 5, "label": "Fondària del xaveter (sobre el forat)"},
}

M = PARAMS["module"]["value"]
Z = int(PARAMS["teeth"]["value"])
PA = math.radians(PARAMS["pressure_angle"]["value"])
T = PARAMS["thickness"]["value"]
BORE = PARAMS["bore_diameter"]["value"]
KW = PARAMS["keyway_width"]["value"]
KD = PARAMS["keyway_depth"]["value"]

rp = M * Z / 2
ra = rp + M
rr = rp - 1.25 * M
rb = rp * math.cos(PA)
BORE = min(BORE, 2 * rr - 6)
KW = min(KW, BORE * 0.6)
KD = min(KD, rr - BORE / 2 - 1.5)


def inv(a):
    return math.tan(a) - a


def half(r):
    # half angular thickness of the tooth at radius r
    a = math.acos(min(rb / r, 1.0))
    return math.pi / (2 * Z) + inv(PA) - inv(a)


rs = max(rb, rr)
steps = 8
radii = [rs + (ra - rs) * i / steps for i in range(steps + 1)]
pts = []
for k in range(Z):
    c = 2 * math.pi * k / Z
    h0 = half(rs)
    pts.append((rr * math.cos(c - h0), rr * math.sin(c - h0)))
    for r in radii:
        h = max(half(r), 0.005)
        pts.append((r * math.cos(c - h), r * math.sin(c - h)))
    for r in reversed(radii):
        h = max(half(r), 0.005)
        pts.append((r * math.cos(c + h), r * math.sin(c + h)))
    pts.append((rr * math.cos(c + h0), rr * math.sin(c + h0)))

gear = cq.Workplane("XY").polyline(pts).close().extrude(T)

bore = cq.Workplane("XY").circle(BORE / 2).extrude(T)
key = cq.Workplane("XY").box(BORE / 2 + KD, KW, T, centered=(False, True, False))
result = gear.cut(bore).cut(key)

EXPECTED_BBOX = (2 * ra, 2 * ra, T)
EXPECTED_HOLES = [(BORE, 1)]
