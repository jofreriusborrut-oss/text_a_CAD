"""Reading Claude's answer: note + script."""
import pytest

from textacad.protocol import AnswerError, extract_code, parse_answer, parse_use, slug

from .fake_runner import PLATE, answer


def test_full_answer():
    a = parse_answer(answer(PLATE, changes=["Gruix: de 5 a 8 mm."], questions=["De quin material?"]))
    assert a.code.startswith("import cadquery as cq") and a.code.endswith("\n")
    assert a.note.title == "placa"
    assert a.note.summary.startswith("Placa de 60")
    assert a.note.changes == ["Gruix: de 5 a 8 mm."]
    assert a.note.assumptions == ["Forats M6 amb joc mitjà: 6,6 mm."]
    assert a.note.questions == ["De quin material?"]
    assert a.note.use == {"process": "fdm", "vibration": False}


def test_code_only_answer_still_works():
    a = parse_answer("Here you go:\n```python\nPARAMS = {}\nresult = 1\n```\nBye")
    assert a.code == "PARAMS = {}\nresult = 1\n"
    assert a.note.summary == "" and a.note.changes == []
    assert extract_code("PARAMS = {}\n") == "PARAMS = {}\n"


def test_questions_only_answer():
    a = parse_answer(answer(None, summary="Em falta saber què vols.", questions=["Quines mides té?", "On va muntat?"]))
    assert a.code is None
    assert a.note.questions == ["Quines mides té?", "On va muntat?"]


def test_empty_answer_is_an_error():
    with pytest.raises(AnswerError):
        parse_answer("   \n")


def test_bullets_with_wrapped_lines_and_numbers():
    text = "<assumptions>\n1. Primera cosa\n   que continua.\n* Segona\n</assumptions>\n```python\nresult = 1\n```"
    assert parse_answer(text).note.assumptions == ["Primera cosa que continua.", "Segona"]


def test_use_block():
    use = parse_use("process=FDM, max_temp_c=90, outdoor=yes; fluids=no, vibration=sí, flexible=unknown")
    assert use == {"process": "fdm", "max_temp_c": 90.0, "outdoor": True, "fluids": False, "vibration": True}


def test_picks_the_script_among_several_blocks():
    text = "```python\nx = 1\n```\ntext\n```python\nPARAMS = {'a': 1}\nresult = 2\n```"
    assert "PARAMS" in parse_answer(text).code


def test_slug():
    assert slug("Abraçadora sensor forquilla Ø52") == "abracadora-sensor-forquilla-52"
    assert slug("???") == "part"


def test_language_of_a_request():
    from textacad.prompts import change_request, detect_language, first_request

    assert detect_language("Placa de 60x40x5 mm amb 4 forats per a M6") == "Catalan"
    assert detect_language("Fes-la més gruixuda i afegeix dos forats") == "Catalan"
    assert detect_language("Soporte con dos agujeros para tornillos M5") == "Spanish"
    assert detect_language("Make it 100 mm wide and add four holes") == "English"
    assert detect_language("Entretoise de 30 mm de diamètre extérieur, alésage de 12 mm") is None     # French: no hint
    assert detect_language("60x40x5") is None
    assert "is written in Catalan: write the note in Catalan." in first_request("Placa amb 4 forats de 6 mm")
    request = change_request("Make it 100 mm wide and add two holes", "PARAMS = {}", ["Placa amb forats"])
    assert "is written in English: write the note in English." in request
    assert "must be in the language of the description above" in first_request("Entretoise de 30 mm")
