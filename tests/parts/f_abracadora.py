import cadquery as cq

PARAMS = {
    "tube_diameter": {"value": 52, "unit": "mm", "min": 30, "max": 70, "label": "Diàmetre del tub de la forquilla"},
    "bore_clearance": {"value": 0.3, "unit": "mm", "min": 0, "max": 1, "label": "Joc de l'anell sobre el tub"},
    "wall": {"value": 5, "unit": "mm", "min": 3, "max": 12, "label": "Gruix de l'anell"},
    "height": {"value": 26, "unit": "mm", "min": 10, "max": 50, "label": "Alçada de l'anell"},
    "slit": {"value": 2, "unit": "mm", "min": 1, "max": 5, "label": "Tall de l'abraçadora"},
    "ear_length": {"value": 14, "unit": "mm", "min": 10, "max": 30, "label": "Llargada de les orelles"},
    "ear_thickness": {"value": 6, "unit": "mm", "min": 4, "max": 12, "label": "Gruix de cada orella"},
    "pinch_bolt_hole": {"value": 5.5, "unit": "mm", "min": 3, "max": 9, "label": "Forat dels cargols de tancament (M5 = 5,5)"},
    "pinch_bolt_count": {"value": 2, "unit": "count", "min": 1, "max": 3, "label": "Nombre de cargols de tancament"},
    "stud_offset": {"value": 40, "unit": "mm", "min": 25, "max": 80, "label": "Distància de l'eix del tub a la cara del pern"},
    "boss_width": {"value": 16, "unit": "mm", "min": 10, "max": 40, "label": "Amplada del suport del pern"},
    "stud_hole": {"value": 3.3, "unit": "mm", "min": 2, "max": 6, "label": "Forat per roscar el pern (M4 = 3,3)"},
    "bore_chamfer": {"value": 1, "unit": "mm", "min": 0, "max": 2, "label": "Xamfrà d'entrada del forat"},
}

D = PARAMS["tube_diameter"]["value"]
C = PARAMS["bore_clearance"]["value"]
T = PARAMS["wall"]["value"]
H = PARAMS["height"]["value"]
GAP = PARAMS["slit"]["value"]
EL = PARAMS["ear_length"]["value"]
ET = PARAMS["ear_thickness"]["value"]
BOLT = PARAMS["pinch_bolt_hole"]["value"]
NB = int(PARAMS["pinch_bolt_count"]["value"])
OFF = PARAMS["stud_offset"]["value"]
BW = PARAMS["boss_width"]["value"]
STUD = PARAMS["stud_hole"]["value"]
CH = PARAMS["bore_chamfer"]["value"]

RI = (D + C) / 2                      # bore radius
RO = RI + T                           # outer radius of the ring
OFF = max(OFF, RO + 3)                # the stud face must stick out of the ring
BW = min(BW, 2 * RO - 4)
EW = min(2 * ET + GAP, 2 * RO - 4)    # two ears plus the slit between them
BOLT = min(BOLT, EL - 4, H / NB - 4)
STUD = min(STUD, BW - 6, H - 6)
CH = min(CH, T / 3)
EAR_X = RO + EL                       # how far the ears reach from the tube axis

# The tube axis is Z. Ring, a flat boss towards +X for the ball stud and a
# block towards -X that becomes the two clamping ears.
ring = cq.Workplane("XY").circle(RO).extrude(H)
boss = cq.Workplane("XY").box(OFF, BW, H, centered=(False, True, False))
ears = cq.Workplane("XY").box(EAR_X, EW, H, centered=(False, True, False)).translate((-EAR_X, 0, 0))
body = ring.union(boss).union(ears)

# Bore for the tube, cut AFTER the unions so nothing is left inside it.
body = body.cut(cq.Workplane("XY").circle(RI).extrude(H))

# Lead-in chamfer at both ends of the bore: a cone is more robust than selecting the split edges.
if CH > 0:
    body = body.cut(cq.Solid.makeCone(RI + CH, RI, CH))
    body = body.cut(cq.Solid.makeCone(RI, RI + CH, CH, pnt=cq.Vector(0, 0, H - CH)))

# Slit through the ears and the ring wall on the -X side only.
slit = cq.Workplane("XY").box(EAR_X + 1, GAP, H, centered=(False, True, False)).translate((-EAR_X - 1, 0, 0))
body = body.cut(slit)

# Pinch bolts across both ears (along Y), spread over the height, and the
# threaded hole for the ball stud (along X).
zs = [H * (i + 0.5) / NB for i in range(NB)]
pinch = cq.Workplane("XZ").pushPoints([(-(RO + EL / 2), z) for z in zs]).circle(BOLT / 2).extrude(EW, both=True)
stud = cq.Workplane("YZ").center(0, H / 2).circle(STUD / 2).extrude(OFF + 1)
result = body.cut(pinch).cut(stud)

EXPECTED_BBOX = (EAR_X + OFF, 2 * RO, H)
EXPECTED_HOLES = [(2 * RI, 1), (BOLT, NB), (STUD, 1)]

# The fork tube, to check the fit (it is not part of the result).
REFERENCE = cq.Workplane("XY").workplane(offset=-15).circle(D / 2).extrude(H + 30)

LOAD_CASE = {
    "description": "Clamp gripping the fork tube, 30 N along the fork at the ball stud",
    "fixed": [{"type": "hole", "axis": "z", "center": [0, 0, 0], "diameter": 2 * RI}],
    "loads": [{"region": {"type": "point", "center": [OFF, 0, H / 2], "radius": 6}, "force": [0, 0, 30]}],
}
