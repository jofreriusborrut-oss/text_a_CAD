import cadquery as cq

PARAMS = {
    "tube_diameter": {"value": 43, "unit": "mm", "min": 30, "max": 70, "label": "Diàmetre de la barra"},
    "bore_clearance": {"value": 0.3, "unit": "mm", "min": 0, "max": 1, "label": "Joc de l'anell sobre la barra"},
    "wall": {"value": 5, "unit": "mm", "min": 3, "max": 12, "label": "Gruix de l'anell"},
    "height": {"value": 26, "unit": "mm", "min": 10, "max": 50, "label": "Alçada de l'anell"},
    "slit": {"value": 2, "unit": "mm", "min": 1, "max": 5, "label": "Tall de l'abraçadora"},
    "ear_length": {"value": 14, "unit": "mm", "min": 10, "max": 30, "label": "Llargada de les orelles"},
    "ear_thickness": {"value": 6, "unit": "mm", "min": 4, "max": 12, "label": "Gruix de cada orella"},
    "pinch_bolt_hole": {"value": 5.5, "unit": "mm", "min": 3, "max": 9, "label": "Forat del cargol de tancament (M5 = 5,5)"},
    "bolt_spacing": {"value": 14, "unit": "mm", "min": 8, "max": 40, "label": "Separació entre cargols de tancament"},
    "stud_offset": {"value": 50, "unit": "mm", "min": 25, "max": 90, "label": "Distància de l'eix de la barra a l'extrem del braç"},
    "boss_width": {"value": 16, "unit": "mm", "min": 10, "max": 40, "label": "Amplada del braç del pern"},
    "stud_hole": {"value": 3.3, "unit": "mm", "min": 2, "max": 6, "label": "Forat per roscar el pern (M4 = 3,3)"},
    "stud_depth": {"value": 14, "unit": "mm", "min": 5, "max": 50, "label": "Profunditat del forat roscat vertical"},
}

D = PARAMS["tube_diameter"]["value"]
C = PARAMS["bore_clearance"]["value"]
T = PARAMS["wall"]["value"]
H = PARAMS["height"]["value"]
GAP = PARAMS["slit"]["value"]
EL = PARAMS["ear_length"]["value"]
ET = PARAMS["ear_thickness"]["value"]
BOLT = PARAMS["pinch_bolt_hole"]["value"]
SP = PARAMS["bolt_spacing"]["value"]
OFF = PARAMS["stud_offset"]["value"]
BW = PARAMS["boss_width"]["value"]
STUD = PARAMS["stud_hole"]["value"]
SD = PARAMS["stud_depth"]["value"]

RI = (D + C) / 2
RO = RI + T
BW = min(BW, 2 * RO - 4)
OFF = max(OFF, RO + BW / 2 + 2)
EW = min(2 * ET + GAP, 2 * RO - 4)
BOLT = min(BOLT, EL - 4, (H - 8) / 2)
SP = max(min(SP, H - BOLT - 4), BOLT + 3)
STUD = min(STUD, BW - 6)
SD = min(SD, H - 2)
EAR_X = RO + EL
XS = OFF - BW / 2          # x of the vertical stud hole

ring = cq.Workplane("XY").circle(RO).extrude(H)
boss = cq.Workplane("XY").box(OFF, BW, H, centered=(False, True, False))
ears = cq.Workplane("XY").box(EAR_X, EW, H, centered=(False, True, False)).translate((-EAR_X, 0, 0))
body = ring.union(boss).union(ears)

body = body.cut(cq.Workplane("XY").circle(RI).extrude(H))

slit = cq.Workplane("XY").box(EAR_X + 1, GAP, H, centered=(False, True, False)).translate((-EAR_X - 1, 0, 0))
body = body.cut(slit)

# Two pinch bolts across the ears (along Y), one above the other
pinch = (cq.Workplane("XZ")
         .pushPoints([(-(RO + EL / 2), H / 2 - SP / 2), (-(RO + EL / 2), H / 2 + SP / 2)])
         .circle(BOLT / 2).extrude(EW, both=True))
# Blind vertical threaded hole for the M4 ball stud, from the top face, parallel to the bar
stud = (cq.Workplane("XY").workplane(offset=H - SD)
        .center(XS, 0).circle(STUD / 2).extrude(SD + 1))
result = body.cut(pinch).cut(stud)

EXPECTED_BBOX = (EAR_X + OFF, 2 * RO, H)
EXPECTED_HOLES = [(2 * RI, 1), (BOLT, 2), (STUD, 1)]

REFERENCE = cq.Workplane("XY").workplane(offset=-15).circle(D / 2).extrude(H + 30)

LOAD_CASE = {
    "description": "Abraçadora subjecta a la barra de la forquilla, 30 N al pern vertical en la direcció de la barra",
    "fixed": [{"type": "hole", "axis": "z", "center": [0, 0, 0], "diameter": 2 * RI}],
    "loads": [{"region": {"type": "hole", "axis": "z", "center": [XS, 0, H - SD / 2], "diameter": STUD},
               "force": [0, 0, 30]}],
}
