"""Technical sheet of a part as a self-contained HTML page (print it to get a PDF)."""
from __future__ import annotations

import html
import time

from . import i18n

T = {
    "sheet": {"en": "Technical sheet", "ca": "Fitxa tècnica", "es": "Ficha técnica"},
    "version": {"en": "Version", "ca": "Versió", "es": "Versión"},
    "request": {"en": "What was asked", "ca": "Què es va demanar", "es": "Qué se pidió"},
    "design": {"en": "What was built", "ca": "Què s'ha construït", "es": "Qué se ha construido"},
    "assumptions": {"en": "Assumptions to confirm", "ca": "Suposicions per confirmar", "es": "Suposiciones por confirmar"},
    "parameters": {"en": "Parameters", "ca": "Paràmetres", "es": "Parámetros"},
    "measured": {"en": "Measured on the model", "ca": "Mesurat sobre el model", "es": "Medido sobre el modelo"},
    "size": {"en": "Overall size (X × Y × Z)", "ca": "Mida total (X × Y × Z)", "es": "Tamaño total (X × Y × Z)"},
    "volume": {"en": "Volume", "ca": "Volum", "es": "Volumen"},
    "com": {"en": "Centre of mass", "ca": "Centre de masses", "es": "Centro de masas"},
    "holes": {"en": "Round holes", "ca": "Forats rodons", "es": "Agujeros redondos"},
    "checks": {"en": "Automatic checks", "ca": "Comprovacions automàtiques", "es": "Comprobaciones automáticas"},
    "material": {"en": "Material", "ca": "Material", "es": "Material"},
    "stiffness": {"en": "Stiffness E", "ca": "Rigidesa E", "es": "Rigidez E"},
    "strength": {"en": "Yield strength", "ca": "Límit elàstic", "es": "Límite elástico"},
    "across": {"en": "Strength across layers", "ca": "Resistència entre capes", "es": "Resistencia entre capas"},
    "density": {"en": "Density", "ca": "Densitat", "es": "Densidad"},
    "max_temp": {"en": "Maximum service temperature", "ca": "Temperatura màxima de servei", "es": "Temperatura máxima de servicio"},
    "mass": {"en": "Mass (solid)", "ca": "Massa (massissa)", "es": "Masa (maciza)"},
    "simulation": {"en": "Stress simulation", "ca": "Simulació de tensions", "es": "Simulación de tensiones"},
    "load": {"en": "Load case", "ca": "Cas de càrrega", "es": "Caso de carga"},
    "max_stress": {"en": "Highest stress (von Mises)", "ca": "Tensió màxima (von Mises)", "es": "Tensión máxima (von Mises)"},
    "max_disp": {"en": "Largest deflection", "ca": "Deformació màxima", "es": "Deformación máxima"},
    "sf": {"en": "Safety factor (across layers / along layers)", "ca": "Factor de seguretat (entre capes / al llarg)",
           "es": "Factor de seguridad (entre capas / a lo largo)"},
    "mesh": {"en": "Simulation mesh", "ca": "Malla de simulació", "es": "Malla de simulación"},
    "elements": {"en": "elements", "ca": "elements", "es": "elementos"},
    "convergence": {"en": "Change versus a coarser mesh", "ca": "Canvi respecte a una malla més grollera",
                    "es": "Cambio respecto a una malla más gruesa"},
    "printing": {"en": "3D printing", "ca": "Impressió 3D", "es": "Impresión 3D"},
    "orientation": {"en": "Recommended orientation (axis pointing up)", "ca": "Orientació recomanada (eix cap amunt)",
                    "es": "Orientación recomendada (eje hacia arriba)"},
    "support": {"en": "Area needing support", "ca": "Àrea que necessita suport", "es": "Área que necesita soporte"},
    "estimate": {"en": "Estimate (20 % infill)", "ca": "Estimació (20 % de farciment)", "es": "Estimación (20 % de relleno)"},
    "files": {"en": "Files", "ca": "Fitxers", "es": "Archivos"},
    "files_text": {
        "en": "STEP for SolidWorks and other CAD (File → Open, type STEP). STL and 3MF for the slicer.",
        "ca": "STEP per a SolidWorks i altres CAD (Fitxer → Obre, tipus STEP). STL i 3MF per al laminador.",
        "es": "STEP para SolidWorks y otros CAD (Archivo → Abrir, tipo STEP). STL y 3MF para el laminador."},
    "disclaimer": {
        "en": "Generated automatically by Text a CAD. Material data are typical values and the simulation is a "
              "first estimate on a simplified model: check critical parts with the supplier's datasheet and a "
              "validated analysis before relying on them.",
        "ca": "Generat automàticament per Text a CAD. Les dades de material són valors típics i la simulació és "
              "una primera estimació sobre un model simplificat: comprova les peces crítiques amb la fitxa del "
              "fabricant i una anàlisi validada abans de confiar-hi.",
        "es": "Generado automáticamente por Text a CAD. Los datos de material son valores típicos y la simulación "
              "es una primera estimación sobre un modelo simplificado: comprueba las piezas críticas con la ficha "
              "del fabricante y un análisis validado antes de confiar en ellas."},
}

ICON = {"ok": "✓", "info": "i", "warning": "!", "error": "✕"}


def _t(key: str, lang: str) -> str:
    return T[key].get(lang) or T[key]["en"]


def _e(value) -> str:
    return html.escape(str(value))


def _rows(pairs) -> str:
    return "".join(f"<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>" for k, v in pairs if v not in (None, ""))


def build(title: str, version, history: list[str], checks: list[dict], material, simulation: dict | None,
          print_data: dict | None, image: str | None, lang: str = "en") -> str:
    lang = i18n.lang_of(lang)
    n = lambda x, d=1: i18n.num(float(x), d, lang)        # noqa: E731
    info = version.info
    note = version.note or {}
    parts: list[str] = []

    parts.append(f"<header><div class='kicker'>{_t('sheet', lang)} · Text a CAD</div>"
                 f"<h1>{_e(title or 'Part')}</h1>"
                 f"<div class='meta'>{_t('version', lang)} {version.number} · "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(version.created))}</div></header>")
    if image and image.startswith("data:image/"):
        parts.append(f"<img class='shot' src='{_e(image)}' alt=''>")

    if history:
        items = "".join(f"<li>{_e(h)}</li>" for h in history)
        parts.append(f"<section><h2>{_t('request', lang)}</h2><ol>{items}</ol></section>")
    if note.get("summary"):
        parts.append(f"<section><h2>{_t('design', lang)}</h2><p>{_e(note['summary'])}</p></section>")
    if note.get("assumptions"):
        items = "".join(f"<li>{_e(a)}</li>" for a in note["assumptions"])
        parts.append(f"<section><h2>{_t('assumptions', lang)}</h2><ul>{items}</ul></section>")

    rows = "".join(
        f"<tr><th>{_e(spec.get('label') or name)}</th><td>{_e(n(version.values.get(name, spec['value']), 2).rstrip('0').rstrip(',.'))}"
        f" {_e('' if spec.get('unit') == 'count' else spec.get('unit', ''))}</td></tr>"
        for name, spec in version.params.items())
    parts.append(f"<section><h2>{_t('parameters', lang)}</h2><table>{rows}</table></section>")

    holes = info.get("holes")
    holes_text = ", ".join(f"{h['count']} × Ø{n(h['diameter'], 2).rstrip('0').rstrip(',.')} ({h['axis'].upper()})"
                           for h in holes) if holes else ("—" if holes is not None else None)
    com = info.get("center_of_mass")
    measured = [
        (_t("size", lang), i18n.size_text(info["bbox"]["size"], lang, 2) + " mm"),
        (_t("volume", lang), n(info["volume_mm3"] / 1000, 2) + " cm³"),
        (_t("mass", lang) + f" · {material.name}", n(info["volume_mm3"] / 1000 * material.density, 1) + " g"),
        (_t("com", lang), ("(" + "; ".join(n(v, 2) for v in com) + ") mm") if com else None),
        (_t("holes", lang), holes_text),
    ]
    parts.append(f"<section><h2>{_t('measured', lang)}</h2><table>{_rows(measured)}</table></section>")

    items = "".join(
        f"<li class='{_e(c['level'])}'><span class='ic'>{ICON.get(c['level'], '')}</span>"
        f"<div><b>{_e(c['title'])}</b><br>{_e(c['detail'])}</div></li>" for c in checks)
    parts.append(f"<section><h2>{_t('checks', lang)}</h2><ul class='checks'>{items}</ul></section>")

    mat_rows = [
        (_t("stiffness", lang), f"{material.E:g} MPa"),
        (_t("strength", lang), f"{material.yield_strength:g} MPa"),
        (_t("across", lang), f"{material.weak_axis_strength:.0f} MPa" if material.z_factor < 1 else None),
        (_t("density", lang), n(material.density, 2) + " g/cm³"),
        (_t("max_temp", lang), f"{material.max_service_temp:g} °C"),
    ]
    mat_note = material.notes.get(lang) or material.notes.get("en", "")
    parts.append(f"<section><h2>{_t('material', lang)}: {_e(material.name)}</h2><p>{_e(mat_note)}</p>"
                 f"<table>{_rows(mat_rows)}</table></section>")

    if simulation:
        s = simulation
        conv = s.get("convergence")
        sim_rows = [
            (_t("load", lang), s["load_case"].get("description") or "—"),
            (_t("max_stress", lang), f"{n(s['max_stress_mpa'], 2)} MPa"),
            (_t("max_disp", lang), f"{n(s['max_displacement_mm'], 3)} mm"),
            (_t("sf", lang), f"{n(s['safety_factor'], 1)} / {n(s['safety_factor_in_plane'], 1)}"),
            (_t("mesh", lang), f"{s['n_elements']} {_t('elements', lang)} · {n(s['pitch_mm'], 2)} mm · {s['material']['name']}"),
            (_t("convergence", lang),
             f"{n(conv['displacement_change_percent'], 1)} % · {n(conv['stress_change_percent'], 1)} %" if conv else None),
        ]
        warn = "".join(f"<li>{_e(i18n.pick(i18n.SIM_WARNINGS, w, lang))}</li>" for w in s.get("warnings", []))
        parts.append(f"<section><h2>{_t('simulation', lang)}</h2><table>{_rows(sim_rows)}</table>"
                     + (f"<ul>{warn}</ul>" if warn else "") + "</section>")

    if print_data:
        best = print_data["best"]
        est = print_data.get("estimate")
        pr_rows = [
            (_t("orientation", lang), best["up"].upper()),
            (_t("support", lang), f"{n(best['support_area_mm2'] / 100, 1)} cm²"),
            (_t("estimate", lang),
             f"{n(est['mass_g'], 0)} g · {est['time_minutes'] // 60} h {est['time_minutes'] % 60:02d} min · "
             f"{n(est['material_cost_eur'], 2)} €" if est else None),
        ]
        notes = "".join(f"<li>{_e(x)}</li>" for x in print_data.get("notes", []))
        parts.append(f"<section><h2>{_t('printing', lang)}</h2><table>{_rows(pr_rows)}</table><ul>{notes}</ul></section>")

    parts.append(f"<section><h2>{_t('files', lang)}</h2><p>{_t('files_text', lang)}</p></section>")
    parts.append(f"<footer>{_t('disclaimer', lang)}</footer>")

    css = """
    :root{--ink:#16202b;--soft:#5b6875;--line:#d6dde4;--accent:#1f5fbf;--ok:#1d7a4c;--warn:#a86200;--err:#b3261e}
    *{box-sizing:border-box}body{font:15px/1.5 "Segoe UI",system-ui,sans-serif;color:var(--ink);margin:0;background:#fff}
    main{max-width:820px;margin:0 auto;padding:32px 28px}
    .kicker{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}
    h1{font-size:30px;margin:4px 0 2px;line-height:1.15}.meta{color:var(--soft);font-size:13px}
    h2{font-size:16px;margin:26px 0 8px;padding-bottom:4px;border-bottom:2px solid var(--ink)}
    .shot{display:block;max-width:100%;margin:18px 0 0;border:1px solid var(--line);border-radius:6px}
    table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
    th{font-weight:500;color:var(--soft);width:46%}td{font-variant-numeric:tabular-nums}
    ul,ol{margin:6px 0;padding-left:20px}.checks{list-style:none;padding:0}
    .checks li{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--line)}
    .ic{flex:none;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff;background:var(--soft)}
    .ok .ic{background:var(--ok)}.warning .ic{background:var(--warn)}.error .ic{background:var(--err)}
    footer{margin-top:28px;padding-top:10px;border-top:1px solid var(--line);font-size:12px;color:var(--soft)}
    section{break-inside:avoid}@media print{main{padding:0}}
    """
    return (f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{_e(title or 'Part')} · v{version.number}</title><style>{css}</style></head>"
            f"<body><main>{''.join(parts)}</main></body></html>")
