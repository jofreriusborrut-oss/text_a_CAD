import math
import cadquery as cq

PARAMS = {
    "diameter": {"value": 50, "unit": "mm", "min": 25, "max": 100, "label": "Diàmetre total"},
    "height": {"value": 15, "unit": "mm", "min": 8, "max": 50, "label": "Alçada"},
    "lobe_count": {"value": 7, "unit": "count", "min": 3, "max": 8, "label": "Nombre de lòbuls"},
    "lobe_radius": {"value": 8.75, "unit": "mm", "min": 3, "max": 20, "label": "Radi dels lòbuls"},
    "core_radius": {"value": 13.75, "unit": "mm", "min": 8, "max": 30, "label": "Radi del nucli central"},
    "bolt_hole": {"value": 6.6, "unit": "mm", "min": 4, "max": 9, "label": "Forat del cargol (M6 = 6,6)"},
    "nut_flats": {"value": 10.3, "unit": "mm", "min": 8, "max": 14, "label": "Femella: cares (10 + 0,3)"},
    "nut_depth": {"value": 5.5, "unit": "mm", "min": 3, "max": 12, "label": "Fondària de l'allotjament"},
}

D = PARAMS["diameter"]["value"]
H = PARAMS["height"]["value"]
N = int(PARAMS["lobe_count"]["value"])
LR = PARAMS["lobe_radius"]["value"]
CR = PARAMS["core_radius"]["value"]
BH = PARAMS["bolt_hole"]["value"]
NF = PARAMS["nut_flats"]["value"]
ND = PARAMS["nut_depth"]["value"]

NC = NF / 0.866                       # across corners
LR = min(LR, D / 2 - 6)
CR = max(CR, NC / 2 + 2)
CR = min(CR, D / 2 - 1)
C = D / 2 - LR                        # lobe centre distance
LR = max(LR, 1)
BH = min(BH, NF - 2)
ND = min(ND, H - 3)

result = cq.Workplane("XY").circle(CR).extrude(H)
for i in range(N):
    a = 2 * math.pi * i / N
    lobe = cq.Workplane("XY").center(C * math.cos(a), C * math.sin(a)).circle(LR).extrude(H)
    result = result.union(lobe)

# Through hole and hex nut pocket from below
result = result.cut(cq.Workplane("XY").circle(BH / 2).extrude(H))
result = result.cut(cq.Workplane("XY").polygon(6, NC).extrude(ND))

xs = [C * math.cos(2 * math.pi * i / N) for i in range(N)]
ys = [C * math.sin(2 * math.pi * i / N) for i in range(N)]
EXPECTED_BBOX = (max(xs) - min(xs) + 2 * LR, max(ys) - min(ys) + 2 * LR, H)
EXPECTED_HOLES = [(BH, 1)]
