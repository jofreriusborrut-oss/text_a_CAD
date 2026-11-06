"""Text a CAD - Streamlit interface.

Run with:   streamlit run app.py
"""
from __future__ import annotations

import re
import time

import streamlit as st

from textacad.checks import num, run_checks
from textacad.config import get_settings
from textacad.generator import ClaudeError, chat_turn
from textacad.regenerate import regenerate
from textacad.viewer import show_stl

st.set_page_config(page_title="Text a CAD", page_icon="⚙️", layout="wide")

MAX_HISTORY = 30
LEVEL_ICON = {"ok": "✅", "info": "ℹ️", "warning": "⚠️", "error": "❌"}

EXAMPLE = (
    "Placa de 60x80x5 mm amb 4 forats de 6,5 mm a 10 mm de les vores "
    "i cantonades arrodonides de radi 4."
)
EXAMPLE_CHANGES = "«fes-la de 8 mm de gruix», «afegeix un forat central de 20 mm», «quin material em recomanes?»"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
# st.session_state survives between reruns of the script (every click reruns it).
# "part" is the part currently shown: a plain dict, so it is easy to store in
# the history later.
# "messages" is the conversation: a list of {"role": "user" | "assistant",
# "content": text}. Every change asked in the chat creates a NEW part (a new
# version) in the history, so going back to an older version is one click.

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


def current_part() -> dict | None:
    for part in st.session_state.get("history", []):
        if part["id"] == st.session_state.get("current_id"):
            return part
    return None


def add_to_history(part: dict) -> None:
    history = st.session_state.setdefault("history", [])
    history.append(part)
    del history[:-MAX_HISTORY]          # keep only the most recent parts (memory)
    st.session_state.current_id = part["id"]


# Same code + same values -> same result: Streamlit remembers it (no recompute).
@st.cache_data(show_spinner=False, max_entries=200)
def _regenerate_cached(code: str, values: tuple) -> dict:
    return regenerate(code, dict(values))


@st.cache_data(show_spinner=False, max_entries=200)
def _checks_cached(stl: bytes, info_items: str) -> list[dict]:
    import json

    return [c.__dict__ for c in run_checks(json.loads(info_items), stl)]


def show_checks(part: dict) -> None:
    import json

    st.subheader("Comprovacions")
    checks = _checks_cached(part["stl"], json.dumps(part["info"], sort_keys=True))
    for c in checks:
        text = f"**{c['title']}**" + (f"  \n{c['detail']}" if c["detail"] else "")
        box = {"ok": st.success, "info": st.info, "warning": st.warning, "error": st.error}[c["level"]]
        box(text, icon=LEVEL_ICON[c["level"]])


def _file_name(description: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", description.lower())[:40].strip("_") or "peca"


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

def _say(text: str, **extra) -> None:
    st.session_state.setdefault("messages", []).append(
        {"role": "assistant", "content": text, **extra})


def run_turn(prompt: str) -> None:
    """Send the user's message to Claude together with the current part.

    Claude has no memory of its own: we give it the previous messages and the
    script of the part on screen, and it answers with text, with a modified
    script, or with both.
    """
    messages = st.session_state.setdefault("messages", [])
    history = [(m["role"], m["content"]) for m in messages]
    messages.append({"role": "user", "content": prompt})
    parent = current_part()

    with st.status("Pensant…", expanded=True) as status:
        def on_progress(n: int, total: int, msg: str) -> None:
            status.update(label=f"Intent {n} de {total}: {msg}")
            st.write(f"**Intent {n}/{total}** · {msg}")

        try:
            turn = chat_turn(
                prompt,
                current_code=parent["code"] if parent else None,   # with the slider values
                current_info=parent["info"] if parent else None,
                history=history,
                on_progress=on_progress,
            )
        except ClaudeError as exc:
            status.update(label="No s'ha pogut parlar amb Claude", state="error")
            _say(f"No he pogut parlar amb Claude:\n\n```text\n{exc}\n```")
            return
        status.update(label="Fet", state="complete", expanded=False)

    gen = turn.generation
    if gen is None:                         # Claude only talked (a question, advice...)
        _say(turn.reply or "…")
        return

    if not gen.ok:
        kept = " La peça que tenies no s'ha tocat." if parent else ""
        _say(
            f"No he aconseguit una peça vàlida en {len(gen.attempts)} intents.{kept} "
            f"Prova de dir-ho d'una altra manera o amb més detall.\n\n"
            f"Últim error:\n```text\n{(gen.last_error or '').strip()[-1500:]}\n```"
        )
        return

    part = _part_from_generation(gen)
    part["time"] = time.strftime("%H:%M")
    part["version"] = parent.get("version", 1) + 1 if parent else 1
    part["name"] = (parent.get("name") or _file_name(parent["description"])) if parent else _file_name(prompt)
    add_to_history(part)
    default = "He aplicat el canvi." if parent else "Aquí tens la peça."
    _say(turn.reply or default, part_id=part["id"])


def new_conversation() -> None:
    """Forget the conversation and the current part (the history is kept)."""
    st.session_state.messages = []
    st.session_state.current_id = None


def show_chat() -> None:
    st.subheader("Conversa")
    messages = st.session_state.setdefault("messages", [])
    part = current_part()

    box = st.container(height=560)
    with box:
        if not messages:
            st.caption(
                "Descriu una peça amb mides en mm. Quan la tinguis, demana canvis "
                f"amb frases curtes ({EXAMPLE_CHANGES}): recordo la peça i només "
                "toco el que em dius."
            )
            st.caption(f"Exemple: {EXAMPLE}")
        for m in messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    placeholder = "Demana un canvi o fes una pregunta…" if part else "Descriu la peça…"
    prompt = st.chat_input(placeholder)
    if prompt and prompt.strip():
        with box:
            with st.chat_message("user"):
                st.markdown(prompt)
            run_turn(prompt.strip())
        st.rerun()          # redraw everything with the new message and the new part


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


def show_part(part: dict, col_view, col_params) -> None:
    info = part["info"]
    name = part.get("name") or _file_name(part["description"])
    if part.get("version", 1) > 1:
        name = f"{name}_v{part['version']}"

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
        c1.markdown(f"**Mida total (X × Y × Z)**  \n{num(x)} × {num(y)} × {num(z)} mm")
        c2.download_button("⬇️ STEP (per a SolidWorks)", part["step"], f"{name}.step",
                           mime="application/step", use_container_width=True)
        c3.download_button("⬇️ STL (per imprimir)", part["stl"], f"{name}.stl",
                           mime="model/stl", use_container_width=True)
        c1.markdown(f"**Volum**  \n{num(info['volume_mm3'] / 1000, 2)} cm³")
        show_checks(part)

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

def show_history() -> None:
    history = st.session_state.get("history", [])
    st.header("Historial")
    if not history:
        st.caption("Encara no has generat cap peça en aquesta sessió.")
        return
    st.caption("Cada canvi desa una versió. Clica'n una per tornar-hi i seguir des d'allà.")
    for part in reversed(history):
        text = part["description"]
        label = f"{part['time']} · v{part.get('version', 1)} · {text[:40]}{'…' if len(text) > 40 else ''}"
        selected = part["id"] == st.session_state.get("current_id")
        if st.button(label, key=f"h_{part['id']}", use_container_width=True,
                     type="primary" if selected else "secondary"):
            st.session_state.current_id = part["id"]
            st.rerun()
    if st.button("🗑️ Esborra l'historial", use_container_width=True):
        st.session_state.history = []
        new_conversation()
        st.rerun()


def main() -> None:
    settings = get_settings()
    st.title("⚙️ Text a CAD")
    st.write("Descriu una peça mecànica amb mesures en mm i ves-la afinant parlant: "
             "obtindràs el model 3D en STEP i STL.")

    with st.sidebar:
        if st.button("➕ Peça nova", use_container_width=True, type="primary",
                     help="Comença una conversa nova. Les peces fetes queden a l'historial."):
            new_conversation()
            st.rerun()
        st.header("Configuració")
        mode = "claude -p (subscripció)" if settings.backend == "cli" else "API d'Anthropic"
        st.write(f"**Connexió:** {mode}")
        st.write(f"**Model:** `{settings.model}`")
        st.caption("Es canvia al fitxer .env")

    col_chat, col_view, col_params = st.columns([3, 5, 2], gap="large")
    with col_chat:
        show_chat()             # may create a new part and rerun the script

    part = current_part()
    if part:
        with col_view:
            st.markdown(f"**Peça (versió {part.get('version', 1)}):** {part['description']}")
        show_part(part, col_view, col_params)
    else:
        with col_view:
            st.info("La peça apareixerà aquí quan la descriguis al xat.", icon="🧩")

    # Drawn last, so a part generated in this run already appears in the list.
    with st.sidebar:
        st.divider()
        show_history()


main()
