"""The web server end to end, with a fake `claude` and a fake CadQuery runner."""
import base64
import time

import numpy as np
import pytest

import server
from textacad import assistant

from . import fake_runner
from .fake_claude import make_fake_claude
from .fake_runner import PLATE, answer

THICK = PLATE.replace('"thickness": {"value": 5', '"thickness": {"value": 8')


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(assistant, "run_code", fake_runner.run_code)
    monkeypatch.setattr(server, "run_code", fake_runner.run_code)
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("CLAUDE_BACKEND", "cli")
    monkeypatch.setattr(server.catalog, "USER_FILE", tmp_path / "catalog_user.json")
    server._sessions.clear()
    server._jobs.clear()
    server._cache.clear()

    def use(answers):
        monkeypatch.setenv("CLAUDE_CLI_PATH", make_fake_claude(tmp_path, answers))

    c = server.app.test_client()
    c.use_answers = use
    return c


def send(client, sid, text, **extra):
    r = client.post(f"/api/sessions/{sid}/messages", json={"text": text, **extra})
    assert r.status_code == 200, r.get_json()
    job = r.get_json()["job"]
    for _ in range(200):
        state = client.get(f"/api/jobs/{job}").get_json()
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def start(client, answers=(answer(PLATE),), text="Placa de 60x40x5 amb 4 forats M6"):
    client.use_answers(list(answers))
    sid = client.post("/api/sessions").get_json()["id"]
    state = send(client, sid, text)
    return sid, state


def test_index_and_static_files(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Text a CAD" in r.data
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/three/three.module.min.js").status_code == 200


def test_config_lists_materials(client):
    data = client.get("/api/config?lang=ca").get_json()
    assert data["backend"] == "cli" and data["default_material"] == "petg"
    petg = next(m for m in data["materials"] if m["id"] == "petg")
    assert petg["E"] == 2000 and "tot terreny" in petg["note"]
    assert "normal" in data["resolutions"]


def test_create_then_change(client):
    sid, state = start(client, [answer(PLATE), answer(THICK, changes=["Gruix: de 5 a 8 mm."])])
    assert state["status"] == "done" and state["outcome"] == {"kind": "version", "version": 1}
    assert [e["stage"] for e in state["events"]] == ["asking", "running", "checking", "done"]

    s = client.get(f"/api/sessions/{sid}?lang=ca").get_json()
    v1 = s["versions"][0]
    assert s["current"] == 1 and s["title"] == "placa" and not s["busy"]
    assert v1["note"]["summary"].startswith("Placa de 60") and v1["file_stem"] == "placa-v1"
    assert v1["files"] == ["part.step", "part.stl"]
    assert v1["components"][0]["id"] == "metric-m6"
    assert [c["code"] for c in v1["checks"]] == ["solid_ok", "size_ok", "holes_ok", "walls_ok", "mass"]
    assert v1["checks"][1]["title"] == "La mida total coincideix amb la descripció"

    state = send(client, sid, "Fes-la de 8 mm de gruix")
    assert state["outcome"] == {"kind": "version", "version": 2}
    s = client.get(f"/api/sessions/{sid}").get_json()
    assert [v["number"] for v in s["versions"]] == [1, 2] and s["current"] == 2
    assert s["versions"][1]["note"]["changes"] == ["Gruix: de 5 a 8 mm."]
    assert [m["role"] for m in s["messages"]] == ["user", "assistant", "user", "assistant"]
    assert client.get("/api/sessions").get_json()["sessions"][0]["versions"] == 2


def test_sliders_rebuild_without_claude(client):
    sid, _ = start(client)
    r = client.post(f"/api/sessions/{sid}/versions/1/params", json={"values": {"length": 100, "hole_count": 6}})
    data = r.get_json()
    assert data["ok"], data
    v = data["version"]
    assert v["values"] == {"length": 100, "width": 40, "thickness": 5, "hole_count": 6}
    assert v["info"]["bbox"]["size"] == [100, 40, 5]
    assert '"hole_count": {"value": 6' in v["code"] and '"hole_count": {"value": 4' in v["base_code"]
    bad = client.post(f"/api/sessions/{sid}/versions/1/params", json={"values": {"nope": 1}})
    assert bad.status_code == 400 and "Unknown parameter" in bad.get_json()["error"]


def test_files_are_served_with_good_names(client):
    sid, _ = start(client)
    r = client.get(f"/api/sessions/{sid}/versions/1/files/part.step?download=1")
    assert r.status_code == 200 and "placa-v1.step" in r.headers["Content-Disposition"]
    assert client.get(f"/api/sessions/{sid}/versions/1/files/part.stl").data[:80].strip() != b""
    assert client.get(f"/api/sessions/{sid}/versions/1/files/part.3mf").status_code == 404
    assert client.get(f"/api/sessions/{sid}/versions/1/files/session.json").status_code == 404
    assert client.get(f"/api/sessions/{sid}/versions/9/files/part.stl").status_code == 404


def test_simulation_materials_print_and_report(client):
    sid, _ = start(client)
    case = client.get(f"/api/sessions/{sid}/versions/1/loadcase").get_json()
    assert case["source"] == "script" and case["load_case"]["loads"][0]["force"] == [0, 0, -20]

    r = client.post(f"/api/sessions/{sid}/versions/1/simulate",
                    json={"material": "petg", "resolution": "draft", "lang": "ca"}).get_json()
    assert r["ok"], r
    summary = r["summary"]
    # Cantilever 60 x 40 x 5 mm in PETG with 20 N at the end: F L^3 / (3 E I) = 0.86 mm
    assert summary["max_displacement_mm"] == pytest.approx(20 * 60 ** 3 / (3 * 2000 * 40 * 5 ** 3 / 12), rel=0.12)
    assert summary["reaction_force_n"] == pytest.approx([0, 0, 20], abs=1e-3)
    assert summary["required_safety_factor"] == 3.0 and summary["safety_factor"] > 1
    levels = np.frombuffer(base64.b64decode(r["drawing"]["stress_levels"]), dtype=np.uint8)
    points = np.frombuffer(base64.b64decode(r["drawing"]["points"]), dtype="<f4")
    assert len(levels) > 100 and len(points) == 3 * len(levels)

    mats = client.post(f"/api/sessions/{sid}/versions/1/materials",
                       json={"lang": "ca", "use": {"max_temp_c": 90, "vibration": True}}).get_json()
    assert mats["use"]["stress_mpa"] == pytest.approx(summary["max_stress_mpa"], rel=1e-3)
    best = mats["materials"][0]
    assert best["suitable"] and best["id"] not in ("pla", "petg")       # too soft at 90 C
    pla = next(m for m in mats["materials"] if m["id"] == "pla")
    assert not pla["suitable"] and "s'estova per sota de la temperatura de treball" in pla["warnings"]

    pr = client.get(f"/api/sessions/{sid}/versions/1/print?material=petg&lang=en").get_json()
    assert pr["best"]["up"] in ("+z", "-z") and pr["best"]["support_area_mm2"] == 0
    assert pr["estimate"]["mass_g"] > 0 and "Prints without supports" in pr["notes"][0]

    rep = client.post(f"/api/sessions/{sid}/versions/1/report", json={"lang": "ca", "material": "petg"}).get_json()
    assert rep["name"] == "placa-v1-report.html"
    assert "Fitxa tècnica" in rep["html"] and "Simulació de tensions" in rep["html"] and "Llargada" in rep["html"]


def test_simulation_error_is_reported_not_raised(client):
    sid, _ = start(client)
    case = {"fixed": [{"type": "box", "min": [900, 900, 900], "max": [901, 901, 901]}],
            "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -1]}]}
    r = client.post(f"/api/sessions/{sid}/versions/1/simulate", json={"load_case": case, "resolution": "draft"}).get_json()
    assert not r["ok"] and "selects no material" in r["error"]


def test_catalog_endpoints(client):
    found = client.post("/api/detect", json={"text": "suport per a motor NEMA 17 amb cargols M3"}).get_json()
    assert {c["id"] for c in found["components"]} == {"nema17", "metric-m3"}
    assert client.get("/api/catalog?q=bearing").get_json()["components"][0]["category"] == "bearing"
    r = client.post("/api/catalog", json={"name": "Sensor Gefran PZ12", "dims": {"body_diameter": 12.7},
                                          "keywords": ["gefran pz12"]}).get_json()
    assert r["component"]["id"] == "user-sensor-gefran-pz12"
    found = client.post("/api/detect", json={"text": "abraçadora per al Gefran PZ12"}).get_json()
    assert found["components"][0]["id"] == "user-sensor-gefran-pz12"
    assert client.post("/api/catalog", json={"name": "x", "dims": {}}).status_code == 400
    assert client.delete("/api/catalog/metric-m3").status_code == 404
    assert client.delete("/api/catalog/user-sensor-gefran-pz12").get_json() == {"ok": True}


def test_errors(client):
    client.use_answers([answer(PLATE)])
    assert client.get("/api/sessions/20260101-000000-abcdef").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404
    sid = client.post("/api/sessions").get_json()["id"]
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": "a"}).status_code == 400
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": "x" * 7000}).status_code == 400
    assert client.get(f"/api/sessions/{sid}/versions/1").status_code == 404


def test_claude_missing_shows_an_error_message(client, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(tmp_path / "no-claude-here"))
    sid = client.post("/api/sessions").get_json()["id"]
    state = send(client, sid, "Placa de 60x40x5")
    assert state["status"] == "error" and "Could not start Claude Code" in state["error"]
    s = client.get(f"/api/sessions/{sid}").get_json()
    assert s["messages"][-1]["kind"] == "error" and s["versions"] == []


def test_switch_version_and_delete_session(client):
    sid, _ = start(client, [answer(PLATE), answer(THICK)])
    send(client, sid, "Més gruixuda")
    assert client.post(f"/api/sessions/{sid}/current", json={"version": 1}).get_json() == {"current": 1}
    assert client.post(f"/api/sessions/{sid}/current", json={"version": 5}).status_code == 404
    state = send(client, sid, "Una altra variant", base=1)            # branch from version 1
    v3 = client.get(f"/api/sessions/{sid}").get_json()["versions"][2]
    assert state["outcome"]["version"] == 3 and v3["parent"] == 1
    assert client.delete(f"/api/sessions/{sid}").get_json() == {"ok": True}
    assert client.get(f"/api/sessions/{sid}").status_code == 404
