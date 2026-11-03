"""The 5 reference descriptions every version of the app must handle."""

DESCRIPCIONS = {
    "a_placa": (
        "Placa de 60x80x5 mm amb 4 forats de 6,5 mm a 10 mm de les vores "
        "i cantonades arrodonides de radi 4."
    ),
    "b_escaire": (
        "Escaire en L de 40x40 mm, 30 mm d'amplada i 4 mm de gruix, "
        "amb 2 forats de 5 mm a cada ala."
    ),
    "c_casquet": (
        "Casquet cilíndric de diàmetre exterior 20 mm, interior 8 mm i alçada 15 mm, "
        "amb xamfrà d'1 mm."
    ),
    "d_caixa": "Caixa de 100x60x40 mm, parets de 2 mm, oberta per dalt.",
    "e_suport_bici": (
        "Suport de paret per a bicicleta: placa de 120x60x6 mm amb 3 forats M6 "
        "i un ganxo de 80 mm de llarg."
    ),
}

# Overall size (sorted, mm) each part must have, used by the real tests.
MIDES_ESPERADES = {
    "a_placa": (5, 60, 80),
    "b_escaire": (30, 40, 40),
    "c_casquet": (15, 20, 20),
    "d_caixa": (40, 60, 100),
    # e: the hook adds depth; only the plate dimensions are known for sure.
    "e_suport_bici": None,
}
