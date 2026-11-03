"""A fake `claude` command for tests: answers from a list, one per call.

make_fake_claude(tmp_path, [answer1, answer2, ...]) returns the path of an
executable that, on call number k, saves its arguments and stdin to
call_k.json and prints answers[k-1] (the last answer is repeated).
"""
import json
import os
import sys
import textwrap


def make_fake_claude(tmp_path, answers) -> str:
    (tmp_path / "answers.json").write_text(json.dumps(list(answers)), encoding="utf-8")
    script = tmp_path / "fake_claude.py"
    script.write_text(textwrap.dedent(f'''
        import json, pathlib, sys
        sys.stdout.reconfigure(encoding="utf-8")
        d = pathlib.Path({str(tmp_path)!r})
        answers = json.loads((d / "answers.json").read_text(encoding="utf-8"))
        k = len(list(d.glob("call_*.json"))) + 1
        stdin = sys.stdin.buffer.read().decode("utf-8")
        (d / f"call_{{k}}.json").write_text(json.dumps({{"argv": sys.argv[1:], "stdin": stdin}}), encoding="utf-8")
        print(answers[min(k, len(answers)) - 1])
    '''), encoding="utf-8")
    if os.name == "nt":
        launcher = tmp_path / "claude.bat"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        launcher = tmp_path / "claude"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    return str(launcher)


def read_call(tmp_path, k: int) -> dict:
    return json.loads((tmp_path / f"call_{k}.json").read_text(encoding="utf-8"))
