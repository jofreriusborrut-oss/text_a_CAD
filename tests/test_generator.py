"""Claude backends without calling Claude: a fake `claude` executable is used."""
import os
import sys
import textwrap
from dataclasses import replace

from textacad.config import get_settings
from textacad.generator import extract_code, generate_code


def test_extract_code_from_fenced_answer():
    answer = "Here you go:\n```python\nPARAMS = {}\nresult = 1\n```\nBye"
    assert extract_code(answer) == "PARAMS = {}\nresult = 1\n"


def test_extract_code_plain():
    assert extract_code("PARAMS = {}\n") == "PARAMS = {}\n"


def make_fake_claude(tmp_path, answer: str) -> str:
    """Create a fake `claude` command that records its arguments and prints `answer`."""
    script = tmp_path / "fake_claude.py"
    script.write_text(textwrap.dedent(f'''
        import sys, json, pathlib
        stdin = sys.stdin.read()
        pathlib.Path({str(tmp_path / "call.json")!r}).write_text(json.dumps({{"argv": sys.argv[1:], "stdin": stdin}}))
        print({answer!r})
    '''), encoding="utf-8")
    if os.name == "nt":
        launcher = tmp_path / "claude.bat"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        launcher = tmp_path / "claude"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    return str(launcher)


def test_cli_backend_calls_claude_p(tmp_path):
    import json

    fake = make_fake_claude(tmp_path, "```python\nPARAMS = {}\nresult = 42\n```")
    settings = replace(get_settings(), backend="cli", cli_path=fake, model="claude-sonnet-5-5")
    code = generate_code("Placa de 10x10x2 mm", settings)
    assert code == "PARAMS = {}\nresult = 42\n"
    call = json.loads((tmp_path / "call.json").read_text())
    assert call["argv"][0] == "-p"
    assert "--model" in call["argv"] and "claude-sonnet-5-5" in call["argv"]
    assert "--system-prompt-file" in call["argv"]
    assert "Placa de 10x10x2 mm" in call["stdin"]
