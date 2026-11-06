import cadquery as cq

PARAMS = {
    "length": {"value": 80, "unit": "mm", "min": 40, "max": 200, "label": "Llargada (X)"},
    "width": {"value": 30, "unit": "mm", "min": 15, "max": 100, "label": "Amplada (Y)"},
    "thickness": {"value": 3, "unit": "mm", "min": 2, "max": 10, "label": "Gruix de la placa"},
    "hole_diameter": {"value": 3, "unit": "mm", "min": 1.5, "max": 8, "label": "Diàmetre dels forats"},
    "hole_edge": {"value": 6, "unit": "mm", "min": 3, "max": 20, "label": "Distància del forat a la vora"},
    "text_depth": {"value": 1, "unit": "mm", "min": 0.6, "max": 3, "label": "Profunditat del gravat"},
    "text_size": {"value": 6, "unit": "mm", "min": 4, "max": 15, "label": "Mida del text"},
}

L = PARAMS["length"]["value"]
W = PARAMS["width"]["value"]
T = PARAMS["thickness"]["value"]
HD = PARAMS["hole_diameter"]["value"]
HE = PARAMS["hole_edge"]["value"]
TD = PARAMS["text_depth"]["value"]
TS = PARAMS["text_size"]["value"]

HD = min(HD, W / 3)
HE = min(max(HE, HD / 2 + 1.5), L / 4)
TD = min(TD, T - 1)
avail = L - 2 * HE - HD - 4
TS = max(min(TS, W - 8, avail / 9.1), 1)

plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))

# Holes at both ends
plate = plate.cut(
    cq.Workplane("XY").pushPoints([(-(L / 2 - HE), 0), (L / 2 - HE, 0)]).circle(HD / 2).extrude(T)
)

# Engraved text, built apart and cut letter by letter
letters = (
    cq.Workplane("XY").workplane(offset=T - TD)
    .text("EPSEVG RACING", TS, TD + 0.5, combine=False, halign="center", valign="center")
)
for s in letters.val().Solids():
    plate = plate.cut(cq.Workplane("XY").add(s))

result = plate

EXPECTED_BBOX = (L, W, T)
EXPECTED_HOLES = [(HD, 2)]
