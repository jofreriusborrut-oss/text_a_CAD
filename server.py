"""Text a CAD - web interface.

Run with:   python server.py          (then open http://localhost:8765)

The page (textacad/static) talks to this small server:
  - a message from the user starts a background job that asks Claude for the
    script, runs it and checks it (assistant.py); the page polls the job;
  - moving a slider rebuilds the part locally, without Claude;
  - checks, material advice, 3D-printing analysis and the stress simulation
    are computed here on request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from textacad import catalog, checks, i18n, printability, report
from textacad.assistant import handle_message
from textacad.config import get_settings
from textacad.fea import SimulationError
from textacad.generator import ClaudeError
from textacad.materials import DEFAULT_MATERIAL, MATERIALS, UseCase, get_material, recommend
from textacad.mesh import MeshError, load_stl
from textacad.params import ParamsError, apply_values, extract_params
from textacad.sandbox import run_code
from textacad.session import DesignSession, SessionError, delete_session, list_sessions
from textacad.simulate import RESOLUTIONS, LoadCase, default_load_case, run_simulation

STATIC = Path(__file__).resolve().parent / "textacad" / "static"
VERSION = "2.0"

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False

_lock = threading.RLock()
_sessions: dict[str, DesignSession] = {}
_jobs: dict[str, dict] = {}
_cache: dict[tuple, object] = {}          # checks, simulations, print analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lang() -> str:
    return i18n.lang_of(request.args.get("lang") or (request.get_json(silent=True) or {}).get("lang"))


def _session(session_id: str) -> DesignSession:
    with _lock:
        if session_id not in _sessions:
            try:
                _sessions[session_id] = DesignSession.load(session_id)
            except SessionError:
                abort(404, description="Session not found.")
        return _sessions[session_id]


def _version(session: DesignSession, number: int):
    try:
        return session.get(number)
    except SessionError:
        abort(404, description="Version not found.")


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _code_key(version) -> str:
    return hashlib.sha1(version.code.encode("utf-8")).hexdigest()[:16]


def _stl(session: DesignSession, number: int) -> bytes:
    path = session.file_path(number, "part.stl")
    if not path.exists():
        abort(404, description="This version has no STL file.")
    return path.read_bytes()


def _mesh(session: DesignSession, version):
    key = ("mesh", session.id, version.number, _code_key(version))
    if key not in _cache:
        _cache[key] = load_stl(_stl(session, version.number))
    return _cache[key]


def _material(name: str | None):
    try:
        return get_material(name or DEFAULT_MATERIAL)
    except KeyError:
        abort(400, description="Unknown material.")


def _checks(session: DesignSession, version, material, lang: str) -> list[dict]:
    key = ("checks", session.id, version.number, _code_key(version), material.id)
    if key not in _cache:
        _cache[key] = checks.run_checks(version.info, _stl(session, version.number), material)
    return [c.as_dict(lang) for c in _cache[key]]


def _suggest_material(version) -> str:
    """Material to start with: the one the user named, else the best match for the stated use."""
    use = dict(version.note.get("use") or {})
    named = str(use.get("material", "")).lower().replace(" ", "")
    if named in MATERIALS:
        return named
    process = use.get("process")
    use["processes"] = [process] if process in ("fdm", "sls", "cnc") else ["fdm"]
    for rec in recommend(UseCase.from_dict(use)):
        if rec.suitable:
            return rec.material.id
    return DEFAULT_MATERIAL


def _version_payload(session: DesignSession, version, lang: str, material=None) -> dict:
    suggested = _suggest_material(version)
    material = material or get_material(suggested)
    folder = session.version_dir(version.number)
    by_id = {c["id"]: c for c in catalog.all_components()}
    data = version.public()
    data["files"] = [n for n in ("part.step", "part.stl", "part.3mf", "reference.stl") if (folder / n).exists()]
    data["file_stem"] = session.file_stem(version.number)
    data["components"] = [catalog.public(by_id[c]) for c in version.components if c in by_id]
    data["checks"] = _checks(session, version, material, lang)
    data["material"] = material.id                    # the material the weight check was computed for
    data["suggested_material"] = suggested
    data["stamp"] = _code_key(version)
    return data


def _session_payload(session: DesignSession, lang: str) -> dict:
    return {
        "id": session.id, "title": session.title, "current": session.current,
        "messages": session.messages,
        "versions": [_version_payload(session, v, lang) for v in session.versions],
        "busy": any(j["session"] == session.id and j["status"] == "running" for j in _jobs.values()),
    }


# ---------------------------------------------------------------------------
# Pages and static files
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_files(name: str):
    return send_from_directory(STATIC, name)


@app.errorhandler(404)
@app.errorhandler(400)
def http_error(exc):
    if request.path.startswith("/api/"):
        return jsonify({"error": exc.description}), exc.code
    return exc


# ---------------------------------------------------------------------------
# Configuration and catalogue
# ---------------------------------------------------------------------------

@app.get("/api/config")
def api_config():
    settings = get_settings()
    lang = _lang()
    return jsonify({
        "version": VERSION,
        "backend": settings.backend,
        "model": settings.model,
        "max_attempts": settings.max_attempts,
        "default_material": DEFAULT_MATERIAL,
        "resolutions": list(RESOLUTIONS),
        "materials": [{**m.as_dict(), "note": m.notes.get(lang) or m.notes.get("en", "")}
                      for m in MATERIALS.values()],
    })


@app.get("/api/catalog")
def api_catalog():
    return jsonify({"components": [catalog.public(c) for c in catalog.search(request.args.get("q", ""))]})


@app.post("/api/catalog")
def api_catalog_add():
    data = request.get_json(silent=True) or {}
    try:
        entry = catalog.save_user_component(
            data.get("name", ""), data.get("dims") or {}, data.get("notes", ""),
            data.get("keywords") or [], data.get("source", ""))
    except catalog.CatalogError as exc:
        return _error(str(exc))
    return jsonify({"component": catalog.public(entry)})


@app.delete("/api/catalog/<component_id>")
def api_catalog_delete(component_id: str):
    if not component_id.startswith("user-") or not catalog.delete_user_component(component_id):
        return _error("Only your own components can be removed.", 404)
    return jsonify({"ok": True})


@app.post("/api/detect")
def api_detect():
    """Reference components mentioned in a text (shown as chips while typing)."""
    text = (request.get_json(silent=True) or {}).get("text", "")
    return jsonify({"components": [catalog.public(c) for c in catalog.find_components(text)]})


# ---------------------------------------------------------------------------
# Sessions and the conversation
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
def api_sessions():
    return jsonify({"sessions": list_sessions()})


@app.post("/api/sessions")
def api_session_new():
    session = DesignSession()
    with _lock:
        _sessions[session.id] = session
    return jsonify(_session_payload(session, _lang()))


@app.get("/api/sessions/<session_id>")
def api_session(session_id: str):
    return jsonify(_session_payload(_session(session_id), _lang()))


@app.delete("/api/sessions/<session_id>")
def api_session_delete(session_id: str):
    with _lock:
        _sessions.pop(session_id, None)
    try:
        return jsonify({"ok": delete_session(session_id)})
    except SessionError as exc:
        return _error(str(exc))


@app.post("/api/sessions/<session_id>/current")
def api_set_current(session_id: str):
    session = _session(session_id)
    number = (request.get_json(silent=True) or {}).get("version")
    _version(session, number)
    session.current = number
    session.save()
    return jsonify({"current": number})


def _run_job(job: dict, session: DesignSession, text: str, base: int | None) -> None:
    def progress(event: dict) -> None:
        job["events"].append({**event, "time": time.time()})

    try:
        outcome = handle_message(session, text, progress, base=base)
        job["outcome"] = {"kind": outcome.kind,
                          "version": outcome.version.number if outcome.version else None}
        job["status"] = "done"
    except ClaudeError as exc:
        session.add_message("assistant", kind="error", error=str(exc))
        session.save()
        job["status"], job["error"] = "error", str(exc)
    except Exception as exc:  # noqa: BLE001 - never leave the page waiting for ever
        session.add_message("assistant", kind="error", error=f"{type(exc).__name__}: {exc}")
        session.save()
        job["status"], job["error"] = "error", f"{type(exc).__name__}: {exc}"
    finally:
        job["finished"] = time.time()


@app.post("/api/sessions/<session_id>/messages")
def api_message(session_id: str):
    session = _session(session_id)
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if len(text) < 3:
        return _error("Write what you want to build or change.")
    if len(text) > 6000:
        return _error("The message is too long (6000 characters at most).")
    base = data.get("base")
    if session.versions and base is not None:
        _version(session, base)
    with _lock:
        if any(j["session"] == session.id and j["status"] == "running" for j in _jobs.values()):
            return _error("The assistant is still working on the previous message.", 409)
        job = {"id": uuid.uuid4().hex[:12], "session": session.id, "status": "running", "events": [],
               "outcome": None, "error": None, "started": time.time(), "finished": None}
        _jobs[job["id"]] = job
        for old in [k for k, j in _jobs.items() if j["finished"] and time.time() - j["finished"] > 3600]:
            _jobs.pop(old, None)
    threading.Thread(target=_run_job, args=(job, session, text, base), daemon=True).start()
    return jsonify({"job": job["id"]})


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        abort(404, description="Job not found.")
    return jsonify({k: job[k] for k in ("id", "status", "events", "outcome", "error", "started", "finished")})


# ---------------------------------------------------------------------------
# One version: sliders, files, checks
# ---------------------------------------------------------------------------

@app.post("/api/sessions/<session_id>/versions/<int:number>/params")
def api_params(session_id: str, number: int):
    """New slider values: rebuild the part locally (Claude is not called)."""
    session = _session(session_id)
    version = _version(session, number)
    values = (request.get_json(silent=True) or {}).get("values") or {}
    try:
        clean = {k: float(v) for k, v in values.items()}
        code = apply_values(version.base_code, clean)
    except (ParamsError, TypeError, ValueError) as exc:
        return _error(str(exc))
    run = run_code(code)
    try:
        if not run.ok:
            return jsonify({"ok": False, "error": run.error})
        from textacad.assistant import _clean_load_case

        _clean_load_case(run.info)
        values = {k: v["value"] for k, v in extract_params(code).items()}
        with _lock:
            session.update_version(number, code, values, run.info, run.files())
    finally:
        run.cleanup()
    return jsonify({"ok": True, "version": _version_payload(session, version, _lang())})


@app.get("/api/sessions/<session_id>/versions/<int:number>/files/<name>")
def api_file(session_id: str, number: int, name: str):
    session = _session(session_id)
    _version(session, number)
    try:
        path = session.file_path(number, name)
    except SessionError:
        abort(404, description="Unknown file.")
    if not path.exists():
        abort(404, description="This version does not have that file.")
    download = request.args.get("download")
    ext = name.rsplit(".", 1)[-1]
    stem = session.file_stem(number) + ("-reference" if name.startswith("reference") else "")
    response = send_file(path, as_attachment=bool(download), download_name=f"{stem}.{ext}", max_age=0)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/sessions/<session_id>/versions/<int:number>")
def api_version(session_id: str, number: int):
    session = _session(session_id)
    version = _version(session, number)
    return jsonify(_version_payload(session, version, _lang(), _material(request.args.get("material"))))


# ---------------------------------------------------------------------------
# Materials, printing, simulation
# ---------------------------------------------------------------------------

def _last_stress(session: DesignSession, version) -> float | None:
    key = ("stress", session.id, version.number, _code_key(version))
    return _cache.get(key)


@app.post("/api/sessions/<session_id>/versions/<int:number>/materials")
def api_materials(session_id: str, number: int):
    """Material ranking for this part. The body may override the use case."""
    session = _session(session_id)
    version = _version(session, number)
    lang = _lang()
    data = request.get_json(silent=True) or {}
    use_data = {**(version.note.get("use") or {}), **(data.get("use") or {})}
    if "processes" not in use_data:
        proc = use_data.get("process")
        use_data["processes"] = [proc] if proc in ("fdm", "sls", "cnc") else ["fdm", "sls", "cnc"]
    use = UseCase.from_dict(use_data)
    use.stress_mpa = _last_stress(session, version)
    ranked = []
    for rec in recommend(use):
        d = rec.as_dict()
        d["reasons"] = [i18n.pick(i18n.MATERIAL_REASONS, r, lang) for r in rec.reasons]
        d["warnings"] = [i18n.pick(i18n.MATERIAL_WARNINGS, w, lang) for w in rec.warnings]
        d["note"] = rec.material.notes.get(lang) or rec.material.notes.get("en", "")
        d["properties"] = rec.material.as_dict()
        d["mass_g"] = round(version.info["volume_mm3"] / 1000 * rec.material.density, 1)
        ranked.append(d)
    return jsonify({
        "use": {"processes": list(use.processes), "max_temp_c": use.max_temp_c, "outdoor": use.outdoor,
                "fluids": use.fluids, "vibration": use.vibration, "flexible": use.flexible,
                "stress_mpa": use.stress_mpa},
        "materials": ranked,
    })


@app.get("/api/sessions/<session_id>/versions/<int:number>/print")
def api_print(session_id: str, number: int):
    session = _session(session_id)
    version = _version(session, number)
    material = _material(request.args.get("material"))
    lang = _lang()
    key = ("print", session.id, number, _code_key(version), material.id)
    if key not in _cache:
        try:
            _cache[key] = printability.analyse(_mesh(session, version), material)
        except MeshError as exc:
            return _error(str(exc))
    data = dict(_cache[key])
    data["notes"] = [i18n.pick(i18n.PRINT_NOTES, n, lang) for n in data["notes"]]
    return jsonify(data)


@app.get("/api/sessions/<session_id>/versions/<int:number>/loadcase")
def api_loadcase(session_id: str, number: int):
    """The load case to start from: the one in the script, or a generic one."""
    session = _session(session_id)
    version = _version(session, number)
    if version.info.get("load_case"):
        return jsonify({"load_case": version.info["load_case"], "source": "script"})
    case = default_load_case(_mesh(session, version))
    return jsonify({"load_case": case.as_dict(), "source": "auto"})


@app.post("/api/sessions/<session_id>/versions/<int:number>/simulate")
def api_simulate(session_id: str, number: int):
    session = _session(session_id)
    version = _version(session, number)
    lang = _lang()
    data = request.get_json(silent=True) or {}
    material = _material(data.get("material"))
    resolution = data.get("resolution", "normal")
    mesh = _mesh(session, version)
    try:
        if data.get("load_case"):
            case = LoadCase.from_dict(data["load_case"])
        elif version.info.get("load_case"):
            case = LoadCase.from_dict(version.info["load_case"])
        else:
            case = default_load_case(mesh)
        key = ("sim", session.id, number, _code_key(version), material.id, resolution,
               json.dumps(case.as_dict(), sort_keys=True))
        if key not in _cache:
            _cache[key] = run_simulation(mesh, case, material, resolution)
        result = _cache[key]
    except SimulationError as exc:
        return jsonify({"ok": False, "error": str(exc)})
    _cache[("stress", session.id, number, _code_key(version))] = result.max_stress
    _cache[("simsummary", session.id, number, _code_key(version))] = result.summary()
    summary = result.summary()
    summary["warning_texts"] = [i18n.pick(i18n.SIM_WARNINGS, w, lang) for w in result.warnings]
    use = UseCase.from_dict(version.note.get("use") or {})
    from textacad.materials import required_safety_factor

    summary["required_safety_factor"] = required_safety_factor(material, use)
    return jsonify({"ok": True, "summary": summary, "drawing": result.drawing_data()})


@app.post("/api/sessions/<session_id>/versions/<int:number>/report")
def api_report(session_id: str, number: int):
    """Technical sheet of the version as a self-contained HTML page."""
    session = _session(session_id)
    version = _version(session, number)
    lang = _lang()
    data = request.get_json(silent=True) or {}
    material = _material(data.get("material"))
    try:
        print_data = printability.analyse(_mesh(session, version), material)
        print_data["notes"] = [i18n.pick(i18n.PRINT_NOTES, n, lang) for n in print_data["notes"]]
    except MeshError:
        print_data = None
    html = report.build(
        title=version.note.get("title") or session.title,
        version=version,
        history=session.history(number),
        checks=_checks(session, version, material, lang),
        material=material,
        simulation=_cache.get(("simsummary", session.id, number, _code_key(version))),
        print_data=print_data,
        image=data.get("image"),
        lang=lang,
    )
    return jsonify({"html": html, "name": session.file_stem(number) + "-report.html"})


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Text a CAD web interface")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    args = ap.parse_args()
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print(f"Text a CAD {VERSION}  ->  {url}   (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
