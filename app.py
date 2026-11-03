"""Text a CAD - Streamlit interface.

Run with:   streamlit run app.py
"""
from __future__ import annotations

import re
import time

import streamlit as st

from textacad.config import get_settings
from textacad.generator import ClaudeError, generate_part
from textacad.regenerate import regenerate
from textacad.viewer import show_stl

st.set_page_config(page_title="Text a CAD", page_icon="⚙️", layout="wide")

EXAMPLE = (
    "Placa de 60x80x5 mm amb 4 forats de 6,5 mm a 10 mm de les vores "
    "i cantonades arrodonides de radi 4."
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
# st.session_state survives between reruns of the script (every click reruns it).
# "part" is the part currently shown: a plain dict, so it is easy to store in
# the history later.

def _part_from_generation(gen) -> dict:
    part = {
        "id": int(time.time() * 1000),
        "description": gen.description,
        "base_code": gen.code,          # code as written by Claude
        "code": gen.code,               # code with the current slider values
        "params": gen.params,           # PARAMS as written by Claude
        "values": {k: v["value"] for k, v in gen.params.items()},
        "info": gen.run.info,
        "stl": gen.run.stl_path.read_bytes(),
        "step": gen.run.step_path.read_bytes(),
        "attempts": [{"number": a.number, "error": a.error} for a in gen.attempts],
    }
    gen.run.cleanup()
    return part


# Same code + same values -> same result: Streamlit remembers it (no recompute).
@st.cache_data(show_spinner=False, max_entries=200)
def _regenerate_cached(code: str, values: tuple) -> dict:
    return regenerate(code, dict(values))


def _file_name(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", description.lower())[:40].strip("_") or "peca"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def run_generation(description: str) -> None:
    with st.status("Generant la peça…", expanded=True) as status:
        def on_progress(n: int, total: int, msg: str) -> None:
            status.update(label=f"Intent {n} de {total}: {msg}")
            st.write(f"**Intent {n}/{total}** · {msg}")

        try:
            gen = generate_part(description, on_progress=on_progress)
        except ClaudeError as exc:
            status.update(label="No s'ha pogut parlar amb Claude", state="error")
            st.error(str(exc))
            return

        if not gen.ok:
            status.update(label=f"No s'ha aconseguit una peça vàlida en {len(gen.attempts)} intents",
                          state="error")
            st.error("Últim error:")
            st.code(gen.last_error or "", language="text")
            if gen.code:
                with st.expander("Codi de l'últim intent"):
                    st.code(gen.code, language="python")
            return

        label = "Peça generada" + (" a la primera" if len(gen.attempts) == 1
                                   else f" en {len(gen.attempts)} intents")
        status.update(label=label, state="complete", expanded=False)
    st.session_state.part = _part_from_generation(gen)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

def _slider(part: dict, name: str, spec: dict) -> float:
    unit = spec.get("unit", "")
    label = spec.get("label") or name
    key = f"p_{part['id']}_{name}"
    if unit == "count":
        return st.slider(f"{label}", int(spec["min"]), int(spec["max"]),
                         int(part["values"][name]), step=1, key=key)
    lo, hi = float(spec["min"]), float(spec["max"])
    step = 0.1 if hi - lo <= 50 else 0.5
    return st.slider(f"{label} ({unit})", lo, hi, float(part["values"][name]),
                     step=step, key=key, format="%.1f")


def parameter_panel(part: dict) -> None:
    """One slider per PARAMS entry. Moving one rebuilds the part locally."""
    st.subheader("Paràmetres")
    st.caption("Mou un control i la peça es regenera a l'ordinador, sense tornar a cridar Claude.")
    values = {name: _slider(part, name, spec) for name, spec in part["params"].items()}

    if st.button("↺ Valors originals", use_container_width=True):
        for name in part["params"]:
            st.session_state.pop(f"p_{part['id']}_{name}", None)
        values = {k: v["value"] for k, v in part["params"].items()}

    if values == part["values"]:
        return
    with st.spinner("Regenerant la peça…"):
        out = _regenerate_cached(part["base_code"], tuple(sorted(values.items())))
    if out["ok"]:
        part.update(values=values, code=out["code"], info=out["info"],
                    stl=out["stl"], step=out["step"])
        part.pop("regen_error", None)
    else:
        part["regen_error"] = out["error"]
    st.rerun()       # redraw the viewer and the data with the new part


def show_part(part: dict) -> None:
    info = part["info"]
    name = _file_name(part["description"])

    col_view, col_params = st.columns([5, 2], gap="large")
    with col_params:
        parameter_panel(part)
    with col_view:
        if part.get("regen_error"):
            st.warning("Aquesta combinació de valors no genera una peça vàlida; "
                       "es mostra l'última que funcionava.")
            with st.expander("Detall de l'error"):
                st.code(part["regen_error"], language="text")
        show_stl(part["stl"])
        st.caption("Gira amb el botó esquerre, desplaça amb el dret i fes zoom amb la roda.")

        c1, c2, c3 = st.columns(3)
        x, y, z = info["bbox"]["size"]
        c1.markdown(f"**Mida total (X × Y × Z)**  \n{x:.1f} × {y:.1f} × {z:.1f} mm")
        c2.download_button("⬇️ STEP (per a SolidWorks)", part["step"], f"{name}.step",
                           mime="application/step", use_container_width=True)
        c3.download_button("⬇️ STL (per imprimir)", part["stl"], f"{name}.stl",
                           mime="model/stl", use_container_width=True)
        c1.markdown(f"**Volum**  \n{info['volume_mm3'] / 1000:.2f} cm³")

    with st.expander("Codi CadQuery (amb els valors actuals)"):
        st.code(part["code"], language="python")

    failed = [a for a in part["attempts"] if a["error"]]
    if failed:
        with st.expander(f"Errors corregits durant la generació ({len(failed)})"):
            for a in failed:
                st.markdown(f"**Intent {a['number']}**")
                st.code(a["error"], language="text")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def main() -> None:
    settings = get_settings()
    st.title("⚙️ Text a CAD")
    st.write("Descriu una peça mecànica amb mesures en mm i obtindràs el model 3D en STEP i STL.")

    with st.sidebar:
        st.header("Configuració")
        mode = "claude -p (subscripció)" if settings.backend == "cli" else "API d'Anthropic"
        st.write(f"**Connexió:** {mode}")
        st.write(f"**Model:** `{settings.model}`")
        st.caption("Es canvia al fitxer .env")

    with st.form("description_form"):
        description = st.text_area(
            "Descripció de la peça",
            height=120,
            placeholder=EXAMPLE,
            help="Com més detallada, millor: mides totals, gruixos, forats (diàmetre i posició), "
                 "arrodoniments i xamfrans.",
        )
        submitted = st.form_submit_button("Genera la peça", type="primary")

    if submitted:
        if len(description.strip()) < 10:
            st.warning("Escriu una descripció una mica més detallada.")
        else:
            run_generation(description.strip())

    part = st.session_state.get("part")
    if part:
        st.divider()
        st.markdown(f"**Peça:** {part['description']}")
        show_part(part)


main()
