import cadquery as cq

PARAMS = {
    "length": {"value": 80, "unit": "mm", "min": 40, "max": 200, "label": "Llargada (X)"},
    "width": {"value": 30, "unit": "mm", "min": 15, "max": 100, "label": "Amplada (Y)"},
    "thickness": {"value": 3, "unit": "mm", "min": 2, "max": 10, "label": "Gruix de la placa"},
    "hole_diameter": {"value": 3, "unit": "mm", "min": 1.5, "max": 8, "label": "Diàmetre dels forats"},
    "hole_edge": {"value": 6, "unit": "mm", "min": 3, "max": 20, "label": "Distància del forat a la vora"},
    "text_height": {"value": 1, "unit": "mm", "min": 0.6, "max": 3, "label": "Alçada del relleu"},
    "text_size": {"value": 6, "unit": "mm", "min": 4, "max": 15, "label": "Mida del text"},
}

L = PARAMS["length"]["value"]
W = PARAMS["width"]["value"]
T = PARAMS["thickness"]["value"]
HD = PARAMS["hole_diameter"]["value"]
HE = PARAMS["hole_edge"]["value"]
TH = PARAMS["text_height"]["value"]
TS = PARAMS["text_size"]["value"]

HD = min(HD, W / 3)
HE = min(max(HE, HD / 2 + 1.5), L / 4)
TS = min(TS, W - 8)

plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))

# Holes at both ends
plate = plate.cut(
    cq.Workplane("XY").pushPoints([(-(L / 2 - HE), 0), (L / 2 - HE, 0)]).circle(HD / 2).extrude(T)
)

# Raised text, built apart and added letter by letter (starts 0.2 mm inside the plate)
letters = (
    cq.Workplane("XY").workplane(offset=T - 0.2)
    .text("MOTOSTUDENT", TS, TH + 0.2, combine=False, halign="center", valign="center")
)
for s in letters.val().Solids():
    plate = plate.union(cq.Workplane("XY").add(s))

result = plate

EXPECTED_BBOX = (L, W, T + TH)
EXPECTED_HOLES = [(HD, 2)]
