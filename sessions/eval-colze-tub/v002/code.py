import cadquery as cq
import math

PARAMS = {
    "tube_diameter": {"value": 20, "unit": "mm", "min": 6, "max": 60, "label": "Diàmetre exterior del tub"},
    "wall": {"value": 2, "unit": "mm", "min": 1, "max": 6, "label": "Gruix de paret"},
    "bend_radius": {"value": 30, "unit": "mm", "min": 15, "max": 120, "label": "Radi de curvatura (a l'eix)"},
    "socket_depth": {"value": 12, "unit": "mm", "min": 5, "max": 40, "label": "Fondària de la boca femella"},
    "clearance": {"value": 0.3, "unit": "mm", "min": 0, "max": 1, "label": "Joc de la boca sobre el tub"},
    "ear_thickness": {"value": 4, "unit": "mm", "min": 2, "max": 10, "label": "Gruix de l'orella"},
    "ear_width": {"value": 16, "unit": "mm", "min": 10, "max": 40, "label": "Amplada de l'orella"},
    "ear_reach": {"value": 12, "unit": "mm", "min": 8, "max": 40, "label": "Distància del tub al centre del forat"},
    "ear_hole": {"value": 5, "unit": "mm", "min": 2, "max": 12, "label": "Forat de l'orella"},
}

D = PARAMS["tube_diameter"]["value"]
W = PARAMS["wall"]["value"]
R = PARAMS["bend_radius"]["value"]
S = PARAMS["socket_depth"]["value"]
C = PARAMS["clearance"]["value"]
ET = PARAMS["ear_thickness"]["value"]
EW = PARAMS["ear_width"]["value"]
ER = PARAMS["ear_reach"]["value"]
HD = PARAMS["ear_hole"]["value"]

W = min(W, D / 4)
BORE = D + C                      # socket bore
RS = BORE / 2 + W                 # outer radius of the whole elbow
RI = D / 2 - W                    # inner radius of the bent part
R = max(R, RS + 1)                # bend must be possible
ET = min(ET, RS)
EW = min(EW, 2 * RS)
HD = min(HD, EW - 6)
ER = max(ER, HD / 2 + 3)
RH = R + RS + ER                  # radius of the ear hole centre

# Outer torus (axis Z through origin), cut to the first quadrant -> 90 deg bend.
torus = (cq.Workplane("XZ").pushPoints([(R, RS)]).circle(RS)
         .revolve(360, (0, 0, 0), (0, 1, 0)))
size = R + RS + 1
quad = cq.Workplane("XY").box(size, size, 2 * RS + 2, centered=(False, False, False)).translate((0, 0, -1))
bend = torus.intersect(quad)

# Outer sleeves at both ends.
sleeve_a = cq.Workplane("XZ").pushPoints([(R, RS)]).circle(RS).extrude(S)
sleeve_b = (cq.Workplane("YZ").workplane(offset=-S)
            .pushPoints([(R, RS)]).circle(RS).extrude(S))
body = bend.union(sleeve_a).union(sleeve_b)

# Mounting ear on the outside of the bend (45 deg), flat on z = 0.
ear = (cq.Workplane("XY").box(RH - R, EW, ET, centered=(False, True, False)).translate((R, 0, 0))
       .union(cq.Workplane("XY").center(RH, 0).circle(EW / 2).extrude(ET)))
ear = ear.rotate((0, 0, 0), (0, 0, 1), 45)
body = body.union(ear)

# Inner passage of the bent part, cut to the same quadrant.
inner_torus = (cq.Workplane("XZ").pushPoints([(R, RS)]).circle(RI)
               .revolve(360, (0, 0, 0), (0, 1, 0)))
inner_bend = inner_torus.intersect(quad)
body = body.cut(inner_bend)

# Female sockets.
sock_a = cq.Workplane("XZ").pushPoints([(R, RS)]).circle(BORE / 2).extrude(S)
sock_b = (cq.Workplane("YZ").workplane(offset=-S)
          .pushPoints([(R, RS)]).circle(BORE / 2).extrude(S))
body = body.cut(sock_a).cut(sock_b)

# Ear hole along Z.
ear_hole = (cq.Workplane("XY").center(RH, 0).circle(HD / 2).extrude(ET)
            .rotate((0, 0, 0), (0, 0, 1), 45))
result = body.cut(ear_hole)

HX = RH * math.cos(math.radians(45))
EXT = max(R + RS, HX + EW / 2)
EXPECTED_BBOX = (EXT + S, EXT + S, 2 * RS)
EXPECTED_HOLES = [(BORE, 2), (HD, 1)]

# Tube stubs in the sockets (not part of the result).
REFERENCE = [
    cq.Workplane("XZ").pushPoints([(R, RS)]).circle(D / 2).extrude(S * 0.99),
    cq.Workplane("YZ").workplane(offset=-S * 0.99).pushPoints([(R, RS)]).circle(D / 2).extrude(S * 0.99),
]

LOAD_CASE = {
    "description": "Colze cargolat a la paret per l'orella; 20 N de tracció al tub d'una boca",
    "fixed": [{"type": "hole", "axis": "z", "center": [HX, HX, ET / 2], "diameter": HD}],
    "loads": [{"region": {"type": "box", "min": [R - RS, -S, 0], "max": [R + RS, -S + 1, 2 * RS]},
               "force": [0, -20, 0]}],
}
