"""Design sessions: versions, history and saving to disk."""
import pytest

from textacad.params import extract_params
from textacad.session import DesignSession, SessionError, delete_session, list_sessions

from . import fake_runner


def add(session, text, code=fake_runner.PLATE, parent=None, title="placa"):
    run = fake_runner.run_code(code)
    assert run.ok, run.error
    try:
        return session.add_version(text, code, extract_params(code), run.info,
                                   {"title": title, "summary": "s"}, run.files(), parent=parent)
    finally:
        run.cleanup()


def test_versions_and_files(tmp_path):
    s = DesignSession(tmp_path)
    v1 = add(s, "Placa de 60x40x5 amb 4 forats M6")
    assert v1.number == 1 and v1.label == "v1" and s.current == 1 and s.title == "placa"
    assert v1.values == {"length": 60, "width": 40, "thickness": 5, "hole_count": 4}
    assert s.file_path(1, "part.stl").stat().st_size > 500
    assert s.file_path(1, "code.py").read_text(encoding="utf-8") == fake_runner.PLATE
    v2 = add(s, "Fes-la de 8 mm", fake_runner.PLATE.replace('"value": 5', '"value": 8'), parent=1)
    assert v2.number == 2 and v2.parent == 1 and s.current == 2
    assert s.file_stem() == "placa-v2" and s.file_stem(1) == "placa-v1"
    with pytest.raises(SessionError):
        s.get(7)
    with pytest.raises(SessionError):
        s.file_path(1, "../../secret.txt")


def test_history_follows_the_parent_chain(tmp_path):
    s = DesignSession(tmp_path)
    add(s, "A")
    add(s, "B", parent=1)
    add(s, "C (branch from A)", parent=1)
    add(s, "D", parent=3)
    assert s.history(4) == ["A", "C (branch from A)", "D"]
    assert s.history(2) == ["A", "B"]


def test_save_and_load_roundtrip(tmp_path):
    s = DesignSession(tmp_path)
    s.add_message("user", "Placa")
    add(s, "Placa")
    s.add_message("assistant", kind="design", version=1)
    s.save()
    again = DesignSession.load(s.id, tmp_path)
    assert again.title == s.title and again.current == 1
    assert [m["role"] for m in again.messages] == ["user", "assistant"]
    assert again.get(1).params == s.get(1).params
    assert again.get(1).code == fake_runner.PLATE


def test_slider_update_keeps_the_version(tmp_path):
    s = DesignSession(tmp_path)
    add(s, "Placa")
    code = fake_runner.PLATE.replace('"value": 60', '"value": 90')
    run = fake_runner.run_code(code)
    s.update_version(1, code, {"length": 90, "width": 40, "thickness": 5, "hole_count": 4}, run.info, run.files())
    run.cleanup()
    v = DesignSession.load(s.id, tmp_path).get(1)
    assert v.values["length"] == 90 and v.info["bbox"]["size"][0] == 90
    assert v.base_code == fake_runner.PLATE and '"value": 90' in v.code
    assert len(s.versions) == 1


def test_list_and_delete(tmp_path):
    a = DesignSession(tmp_path)
    add(a, "Placa A", title="a")
    DesignSession(tmp_path).save()                       # empty sessions are not listed
    b = DesignSession(tmp_path)
    add(b, "Placa B", title="b")
    listed = list_sessions(tmp_path)
    assert {x["title"] for x in listed} == {"a", "b"} and all(x["versions"] == 1 for x in listed)
    assert delete_session(a.id, tmp_path)
    assert [x["title"] for x in list_sessions(tmp_path)] == ["b"]
    with pytest.raises(SessionError):
        DesignSession.load(a.id, tmp_path)
    with pytest.raises(SessionError):
        delete_session("../etc", tmp_path)
