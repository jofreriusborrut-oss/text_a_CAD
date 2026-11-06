"""The conversation: Claude gets the current part on every turn and edits it.

No real Claude calls: tests/fake_claude.py plays Claude's role.
"""
from dataclasses import replace
from pathlib import Path

from textacad.config import get_settings
from textacad.generator import chat_turn, split_answer
from textacad.prompts import chat_request

from .fake_claude import make_fake_claude, read_call

GOOD = (Path(__file__).parent / "parts" / "c_casquet.py").read_text(encoding="utf-8")
TALLER = GOOD.replace('"height": {"value": 15', '"height": {"value": 25')
BROKEN = TALLER.replace("result = result.edges().chamfer(C)", "result = result.edges().fillet(50)")
INFO = {"bbox": {"size": [20.0, 20.0, 15.0]}, "volume_mm3": 3958.4, "n_solids": 1, "is_valid": True}


def answer(text: str, code: str) -> str:
    return f"{text}\n\n```python\n{code}```\n"


def settings_for(fake: str):
    return replace(get_settings(), backend="cli", cli_path=fake, model="claude-sonnet-5-5", exec_timeout=30)


def test_split_answer_text_and_code():
    text, code = split_answer("He fet l'alçada de 25 mm.\n```python\nPARAMS = {}\nresult = 1\n```")
    assert text == "He fet l'alçada de 25 mm."
    assert code == "PARAMS = {}\nresult = 1\n"


def test_split_answer_only_text():
    assert split_answer("Et recomano PETG.") == ("Et recomano PETG.", None)


def test_split_answer_code_without_fences():
    text, code = split_answer(GOOD)
    assert text == "" and code == GOOD.strip() + "\n"


def test_request_carries_history_part_and_message():
    req = chat_request("Fes-lo de 25 mm d'alçada", GOOD, INFO,
                       [("user", "Casquet de 20x8x15"), ("assistant", "Aquí tens la peça.")])
    assert "User: Casquet de 20x8x15" in req
    assert "Assistant: Aquí tens la peça." in req
    assert '"outer_diameter": {"value": 20' in req          # the current script
    assert "20.00 x 20.00 x 15.00 mm" in req                # what was measured
    assert req.rstrip().endswith("Fes-lo de 25 mm d'alçada")


def test_request_without_part_says_so():
    assert "no current part" in chat_request("Una placa de 10x10x2")


def test_change_edits_the_current_part(tmp_path):
    fake = make_fake_claude(tmp_path, [answer("Alçada de 15 a 25 mm.", TALLER)])
    turn = chat_turn("Fes-lo de 25 mm d'alçada", current_code=GOOD, current_info=INFO,
                     history=[("user", "Casquet de 20x8x15")], settings=settings_for(fake))
    assert turn.reply == "Alçada de 15 a 25 mm."
    assert turn.generation.ok and len(turn.generation.attempts) == 1
    assert turn.generation.params["height"]["value"] == 25
    assert turn.generation.run.info["bbox"]["size"][2] == 25
    sent = read_call(tmp_path, 1)["stdin"]
    assert '"height": {"value": 15' in sent                 # Claude saw the part it must edit
    assert "Casquet de 20x8x15" in sent                     # ...and the conversation
    turn.generation.run.cleanup()


def test_question_gives_text_and_no_new_part(tmp_path):
    fake = make_fake_claude(tmp_path, ["Per imprimir-lo, PETG. Pesaria uns 5 g."])
    turn = chat_turn("Quin material em recomanes?", current_code=GOOD, current_info=INFO,
                     settings=settings_for(fake))
    assert turn.generation is None
    assert "PETG" in turn.reply
    assert not (tmp_path / "call_2.json").exists()          # one call, no retries


def test_failed_change_is_sent_back_and_fixed(tmp_path):
    fake = make_fake_claude(tmp_path, [answer("Fet.", BROKEN), answer("Alçada a 25 mm.", TALLER)])
    turn = chat_turn("Fes-lo de 25 mm d'alçada", current_code=GOOD, current_info=INFO,
                     settings=settings_for(fake))
    assert turn.generation.ok
    assert [a.error is None for a in turn.generation.attempts] == [False, True]
    assert turn.reply == "Alçada a 25 mm."
    second = read_call(tmp_path, 2)["stdin"]
    assert "fillet(50)" in second                           # the failed script
    assert "Fes-lo de 25 mm d'alçada" in second             # the original request
    assert '"height": {"value": 15' in second               # and the part to edit
    turn.generation.run.cleanup()


def test_gives_up_and_reports_the_error(tmp_path):
    fake = make_fake_claude(tmp_path, [answer("Fet.", BROKEN)])
    turn = chat_turn("Fes-lo de 25 mm", current_code=GOOD, settings=settings_for(fake))
    assert not turn.generation.ok
    assert len(turn.generation.attempts) == 3 and turn.generation.last_error
