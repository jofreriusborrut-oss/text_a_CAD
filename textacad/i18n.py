"""Texts shown to the user, in English, Catalan and Spanish.

The checks, the simulation and the material recommender produce short codes
(for example "walls_thin") plus numbers. This module turns them into
sentences in the language the user chose in the interface.
"""
from __future__ import annotations

LANGS = ("en", "ca", "es")
DEFAULT_LANG = "en"


def lang_of(value: str | None) -> str:
    value = (value or "").lower()[:2]
    return value if value in LANGS else DEFAULT_LANG


def num(x: float, decimals: int = 1, lang: str = "en") -> str:
    """Number with the decimal mark of the language: 1.2 (en) or 1,2 (ca, es)."""
    text = f"{x:.{decimals}f}"
    return text if lang == "en" else text.replace(".", ",")


def size_text(size, lang: str, decimals: int = 1) -> str:
    return " × ".join(num(v, decimals, lang) for v in size)


# code -> {lang: (title, detail)}.  {placeholders} are filled from the check's numbers.
CHECKS = {
    "solid_ok": {
        "en": ("Valid, closed solid", "One single solid with no gaps in its surface."),
        "ca": ("Sòlid vàlid i tancat", "Un únic sòlid, sense forats a la superfície."),
        "es": ("Sólido válido y cerrado", "Un único sólido, sin huecos en la superficie."),
    },
    "solid_invalid": {
        "en": ("The solid is not valid", "{problems}."),
        "ca": ("Sòlid no vàlid", "{problems}."),
        "es": ("Sólido no válido", "{problems}."),
    },
    "size_ok": {
        "en": ("Overall size matches the description", "{got} mm"),
        "ca": ("La mida total coincideix amb la descripció", "{got} mm"),
        "es": ("El tamaño total coincide con la descripción", "{got} mm"),
    },
    "size_rotated": {
        "en": ("Right size, different orientation",
               "Expected (X × Y × Z): {want} mm · Actual: {got} mm. Same dimensions on other axes."),
        "ca": ("Mida correcta però orientació diferent",
               "Esperada (X × Y × Z): {want} mm · Real: {got} mm. Les mides coincideixen però en un altre ordre d'eixos."),
        "es": ("Tamaño correcto pero orientación distinta",
               "Esperado (X × Y × Z): {want} mm · Real: {got} mm. Las medidas coinciden pero en otro orden de ejes."),
    },
    "size_mismatch": {
        "en": ("Overall size does NOT match the description", "Expected: {want} mm · Actual: {got} mm ({axes})."),
        "ca": ("La mida total NO coincideix amb la descripció", "Esperada: {want} mm · Real: {got} mm ({axes})."),
        "es": ("El tamaño total NO coincide con la descripción", "Esperado: {want} mm · Real: {got} mm ({axes})."),
    },
    "size_unchecked": {
        "en": ("Overall size not checked", "The script does not state the expected size. Actual size: {got} mm."),
        "ca": ("Mida total no comprovada", "El codi no indica la mida esperada. Mida real: {got} mm."),
        "es": ("Tamaño total no comprobado", "El código no indica el tamaño esperado. Tamaño real: {got} mm."),
    },
    "holes_ok": {
        "en": ("Holes match the description", "Found: {found}."),
        "ca": ("Els forats coincideixen amb la descripció", "Trobats: {found}."),
        "es": ("Los agujeros coinciden con la descripción", "Encontrados: {found}."),
    },
    "holes_mismatch": {
        "en": ("Holes do NOT match the description", "{problems}. Found on the part: {found}."),
        "ca": ("Els forats NO coincideixen amb la descripció", "{problems}. Trobats a la peça: {found}."),
        "es": ("Los agujeros NO coinciden con la descripción", "{problems}. Encontrados en la pieza: {found}."),
    },
    "holes_listed": {
        "en": ("Round holes found on the part", "{found}."),
        "ca": ("Forats rodons trobats a la peça", "{found}."),
        "es": ("Agujeros redondos encontrados en la pieza", "{found}."),
    },
    "holes_none": {
        "en": ("No round holes", "The part has no cylindrical holes."),
        "ca": ("Sense forats rodons", "La peça no té forats cilíndrics."),
        "es": ("Sin agujeros redondos", "La pieza no tiene agujeros cilíndricos."),
    },
    "walls_ok": {
        "en": ("No wall thinner than {limit} mm", "Thinnest wall found: about {thinnest} mm."),
        "ca": ("Cap paret més prima que {limit} mm", "Gruix mínim aproximat: {thinnest} mm."),
        "es": ("Ninguna pared más fina que {limit} mm", "Grosor mínimo aproximado: {thinnest} mm."),
    },
    "walls_thin": {
        "en": ("Thin walls (< {limit} mm): risky for 3D printing",
               "{share} % of the surface is thinner than {limit} mm (thinnest: about {thinnest} mm). It may print badly or be fragile."),
        "ca": ("Parets primes (< {limit} mm): risc en impressió 3D",
               "Un {share} % de la superfície té un gruix inferior a {limit} mm (mínim aproximat: {thinnest} mm). Pot no imprimir-se bé o ser fràgil."),
        "es": ("Paredes finas (< {limit} mm): riesgo en impresión 3D",
               "Un {share} % de la superficie tiene un grosor inferior a {limit} mm (mínimo aproximado: {thinnest} mm). Puede imprimirse mal o ser frágil."),
    },
    "walls_unmeasured": {
        "en": ("Wall thickness not measured", "It needs a closed mesh."),
        "ca": ("Gruix de paret no mesurat", "Cal una malla tancada."),
        "es": ("Grosor de pared no medido", "Hace falta una malla cerrada."),
    },
    "fit_ok": {
        "en": ("No collision with the mating component", "The part and the reference component do not overlap."),
        "ca": ("Sense col·lisió amb el component de referència", "La peça i el component de referència no se solapen."),
        "es": ("Sin colisión con el componente de referencia", "La pieza y el componente de referencia no se solapan."),
    },
    "fit_collision": {
        "en": ("The part collides with the mating component",
               "They overlap by {volume} mm³. The part would not fit: check the clearance."),
        "ca": ("La peça xoca amb el component de referència",
               "Se solapen {volume} mm³. La peça no encaixaria: revisa el joc."),
        "es": ("La pieza choca con el componente de referencia",
               "Se solapan {volume} mm³. La pieza no encajaría: revisa la holgura."),
    },
    "mass": {
        "en": ("Volume: {volume} cm³ · weight in {material}: about {grams} g",
               "Solid part (100 % infill), density {density} g/cm³. With partial infill it weighs less."),
        "ca": ("Volum: {volume} cm³ · pes aproximat en {material}: {grams} g",
               "Peça massissa (100 % de farciment), densitat {density} g/cm³. Amb farciment parcial pesarà menys."),
        "es": ("Volumen: {volume} cm³ · peso aproximado en {material}: {grams} g",
               "Pieza maciza (100 % de relleno), densidad {density} g/cm³. Con relleno parcial pesará menos."),
    },
}

SOLID_PROBLEMS = {
    "brep_invalid": {"en": "the CAD kernel reports invalid geometry",
                     "ca": "el nucli CAD diu que la geometria no és vàlida",
                     "es": "el núcleo CAD dice que la geometría no es válida"},
    "n_solids": {"en": "there are {n} separate solids instead of one",
                 "ca": "hi ha {n} sòlids separats en lloc d'un",
                 "es": "hay {n} sólidos separados en lugar de uno"},
    "not_watertight": {"en": "the STL mesh is not closed (it has holes or open edges)",
                       "ca": "la malla STL no és tancada (té forats o arestes obertes)",
                       "es": "la malla STL no está cerrada (tiene huecos o aristas abiertas)"},
}

HOLE_PROBLEMS = {
    "missing": {"en": "expected {want} × Ø{d} but found {got}",
                "ca": "s'esperaven {want} × Ø{d} però n'hi ha {got}",
                "es": "se esperaban {want} × Ø{d} pero hay {got}"},
}

SIM_WARNINGS = {
    "not_converged_displacement": {
        "en": "The deflection changed more than 10 % between the coarse and the normal mesh: use the fine resolution.",
        "ca": "La deformació canvia més d'un 10 % entre la malla grollera i la normal: fes servir la resolució fina.",
        "es": "La deformación cambia más de un 10 % entre la malla gruesa y la normal: usa la resolución fina."},
    "not_converged_stress": {
        "en": "The peak stress changed more than 25 % between meshes: it sits at a sharp corner or a small feature. Treat it as indicative.",
        "ca": "La tensió màxima canvia més d'un 25 % entre malles: és en una cantonada viva o un detall petit. Pren-la com a orientativa.",
        "es": "La tensión máxima cambia más de un 25 % entre mallas: está en una esquina viva o un detalle pequeño. Tómala como orientativa."},
    "coarse_geometry": {
        "en": "The simulated model differs from the real part by more than 8 % in volume: use a finer resolution.",
        "ca": "El model simulat difereix de la peça real en més d'un 8 % de volum: fes servir una resolució més fina.",
        "es": "El modelo simulado difiere de la pieza real en más de un 8 % de volumen: usa una resolución más fina."},
    "load_moved": {
        "en": "A load point was not on the part (for example the centre of a hole): the force was applied to the nearest material.",
        "ca": "Un punt de càrrega no tocava la peça (per exemple, el centre d'un forat): la força s'ha aplicat al material més proper.",
        "es": "Un punto de carga no tocaba la pieza (por ejemplo, el centro de un agujero): la fuerza se ha aplicado al material más cercano."},
    "yields": {
        "en": "The stress is above the strength of the material: the part would deform permanently or break.",
        "ca": "La tensió supera la resistència del material: la peça es deformaria permanentment o es trencaria.",
        "es": "La tensión supera la resistencia del material: la pieza se deformaría permanentemente o se rompería."},
    "large_deformation": {
        "en": "The part moves more than 10 % of its size: this linear analysis is not accurate for such large deflections.",
        "ca": "La peça es mou més d'un 10 % de la seva mida: aquesta anàlisi lineal no és precisa per a deformacions tan grans.",
        "es": "La pieza se mueve más de un 10 % de su tamaño: este análisis lineal no es preciso para deformaciones tan grandes."},
    "large_deformation_material": {
        "en": "Flexible materials do not behave linearly: the numbers are only a rough guide.",
        "ca": "Els materials flexibles no es comporten linealment: els números són només orientatius.",
        "es": "Los materiales flexibles no se comportan linealmente: los números son solo orientativos."},
}

MATERIAL_REASONS = {
    "temp_ok": {"en": "handles the temperature", "ca": "aguanta la temperatura", "es": "aguanta la temperatura"},
    "uv_good": {"en": "weatherproof", "ca": "resisteix la intempèrie", "es": "resiste la intemperie"},
    "chemical_good": {"en": "resists fuel and oil", "ca": "resisteix combustible i oli", "es": "resiste combustible y aceite"},
    "tough": {"en": "takes vibration and impacts", "ca": "aguanta vibracions i cops", "es": "aguanta vibraciones y golpes"},
    "strong_enough": {"en": "strong enough with margin", "ca": "prou resistent amb marge", "es": "suficientemente resistente con margen"},
    "easy": {"en": "easy to make", "ca": "fàcil de fabricar", "es": "fácil de fabricar"},
}

MATERIAL_WARNINGS = {
    "process_unavailable": {"en": "needs a process you did not select", "ca": "necessita un procés que no has seleccionat",
                            "es": "necesita un proceso que no has seleccionado"},
    "not_flexible": {"en": "it is rigid and you need a flexible part", "ca": "és rígid i necessites una peça flexible",
                     "es": "es rígido y necesitas una pieza flexible"},
    "too_flexible": {"en": "too flexible for a rigid part", "ca": "massa flexible per a una peça rígida",
                     "es": "demasiado flexible para una pieza rígida"},
    "too_hot": {"en": "softens below the working temperature", "ca": "s'estova per sota de la temperatura de treball",
                "es": "se ablanda por debajo de la temperatura de trabajo"},
    "temp_margin_small": {"en": "little margin on temperature", "ca": "poc marge de temperatura", "es": "poco margen de temperatura"},
    "uv_poor": {"en": "degrades outdoors", "ca": "es degrada a l'exterior", "es": "se degrada en exterior"},
    "chemical_poor": {"en": "attacked by fuel or oil", "ca": "l'ataquen el combustible o l'oli", "es": "lo atacan el combustible o el aceite"},
    "brittle": {"en": "brittle under vibration", "ca": "fràgil amb vibracions", "es": "frágil con vibraciones"},
    "breaks": {"en": "would break under the simulated load", "ca": "es trencaria amb la càrrega simulada",
               "es": "se rompería con la carga simulada"},
    "low_safety_factor": {"en": "safety factor below the recommended one", "ca": "factor de seguretat per sota del recomanat",
                          "es": "factor de seguridad por debajo del recomendado"},
}

PRINT_NOTES = {
    "no_support": {"en": "Prints without supports in the recommended orientation.",
                   "ca": "S'imprimeix sense suports en l'orientació recomanada.",
                   "es": "Se imprime sin soportes en la orientación recomendada."},
    "small_overhangs": {"en": "Only small overhangs (cross holes, chamfers): they usually bridge without supports.",
                        "ca": "Només hi ha voladissos petits (forats transversals, xamfrans): normalment s'imprimeixen en pont, sense suports.",
                        "es": "Solo hay voladizos pequeños (agujeros transversales, chaflanes): normalmente se imprimen en puente, sin soportes."},
    "needs_support": {"en": "Needs supports even in the best orientation.",
                      "ca": "Necessita suports fins i tot en la millor orientació.",
                      "es": "Necesita soportes incluso en la mejor orientación."},
    "small_bed_contact": {"en": "Little contact with the bed: add a brim so it does not come loose.",
                          "ca": "Poc contacte amb el llit: afegeix una vora (brim) perquè no es desenganxi.",
                          "es": "Poco contacto con la cama: añade un borde (brim) para que no se despegue."},
    "tall_and_thin": {"en": "Tall and narrow: print slowly or lay it down to avoid wobble.",
                      "ca": "Alta i estreta: imprimeix a poc a poc o tomba-la per evitar que tremoli.",
                      "es": "Alta y estrecha: imprime despacio o túmbala para evitar que tiemble."},
    "weak_between_layers": {"en": "This material is weak between layers: orient the part so the main load runs along the layers.",
                            "ca": "Aquest material és feble entre capes: orienta la peça perquè la càrrega principal vagi al llarg de les capes.",
                            "es": "Este material es débil entre capas: orienta la pieza para que la carga principal vaya a lo largo de las capas."},
    "too_big": {"en": "Too big for the common desktop printers listed: split it or use a print service.",
                "ca": "Massa gran per a les impressores d'escriptori habituals: divideix-la o fes servir un servei d'impressió.",
                "es": "Demasiado grande para las impresoras de escritorio habituales: divídela o usa un servicio de impresión."},
}


def pick(table: dict, code: str, lang: str, **values) -> str:
    """Text of `code` in `lang` (English when a translation is missing)."""
    entry = table.get(code)
    if entry is None:
        return code
    text = entry.get(lang) or entry["en"]
    return text.format(**values) if values else text
