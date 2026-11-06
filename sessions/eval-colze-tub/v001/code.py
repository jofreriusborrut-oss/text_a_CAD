import cadquery as cq

PARAMS = {
    "tube_diameter": {"value": 20, "unit": "mm", "min": 6, "max": 60, "label": "Diàmetre exterior del tub"},
    "wall": {"value": 2, "unit": "mm", "min": 1, "max": 6, "label": "Gruix de paret"},
    "bend_radius": {"value": 30, "unit": "mm", "min": 15, "max": 120, "label": "Radi de curvatura (a l'eix)"},
    "socket_depth": {"value": 12, "unit": "mm", "min": 5, "max": 40, "label": "Fondària de la boca femella"},
    "clearance": {"value": 0.3, "unit": "mm", "min": 0, "max": 1, "label": "Joc de la boca sobre el tub"},
}

D = PARAMS["tube_diameter"]["value"]
W = PARAMS["wall"]["value"]
R = PARAMS["bend_radius"]["value"]
S = PARAMS["socket_depth"]["value"]
C = PARAMS["clearance"]["value"]

W = min(W, D / 4)
BORE = D + C                      # socket bore
RS = BORE / 2 + W                 # outer radius of the whole elbow
RI = D / 2 - W                    # inner radius of the bent part
R = max(R, RS + 1)                # bend must be possible

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

# Inner passage of the bent part, cut to the same quadrant.
inner_torus = (cq.Workplane("XZ").pushPoints([(R, RS)]).circle(RI)
               .revolve(360, (0, 0, 0), (0, 1, 0)))
inner_bend = inner_torus.intersect(quad)
body = body.cut(inner_bend)

# Female sockets.
sock_a = cq.Workplane("XZ").pushPoints([(R, RS)]).circle(BORE / 2).extrude(S)
sock_b = (cq.Workplane("YZ").workplane(offset=-S)
          .pushPoints([(R, RS)]).circle(BORE / 2).extrude(S))
result = body.cut(sock_a).cut(sock_b)

EXPECTED_BBOX = (R + RS + S, R + RS + S, 2 * RS)
EXPECTED_HOLES = [(BORE, 2)]

# Tube stubs in the sockets (not part of the result).
REFERENCE = [
    cq.Workplane("XZ").pushPoints([(R, RS)]).circle(D / 2).extrude(S * 0.99),
    cq.Workplane("YZ").workplane(offset=-S * 0.99).pushPoints([(R, RS)]).circle(D / 2).extrude(S * 0.99),
]
