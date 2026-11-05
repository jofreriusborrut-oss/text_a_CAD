"""Ask the real Claude for the answers the evaluation is waiting for, and record them.

    python tools/eval_ask.py --first            first message of every case that has no answer yet
    python tools/eval_ask.py --pending DIR      the messages saved by eval_run.py in DIR (<out>/pending)

Answers are appended to eval/cases.json. It uses the same backend as the app
(CLAUDE_BACKEND / CLAUDE_MODEL in .env), so it costs the same as using the app.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textacad.catalog import find_components              # noqa: E402
from textacad.generator import ClaudeError, ask_claude    # noqa: E402
from textacad.prompts import first_request                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", type=Path, default=ROOT / "eval" / "cases.json")
    ap.add_argument("--first", action="store_true")
    ap.add_argument("--pending", type=Path)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in cases}
    jobs = []                                   # (case id, turn index, message)
    if args.first:
        for c in cases:
            turn = c["turns"][0]
            if not turn.get("answers"):
                jobs.append((c["id"], 0, first_request(turn["text"], find_components(turn["text"]))))
    if args.pending and args.pending.is_dir():
        for path in sorted(args.pending.glob("*.json")):
            p = json.loads(path.read_text(encoding="utf-8"))
            turn = by_id[p["case"]]["turns"][p["turn"]]
            if len(turn.setdefault("answers", [])) == p["answer_number"] - 1:      # not answered yet
                jobs.append((p["case"], p["turn"], p["message"]))
    if not jobs:
        print("Nothing to ask.")
        return 0

    def ask(job):
        case_id, turn, message = job
        try:
            return job, ask_claude(message), None
        except ClaudeError as exc:
            return job, None, str(exc)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for (case_id, turn, _), answer, error in pool.map(ask, jobs):
            if error:
                print(f"[{case_id} turn {turn + 1}] ERROR: {error}")
                continue
            by_id[case_id]["turns"][turn].setdefault("answers", []).append(answer)
            print(f"[{case_id} turn {turn + 1}] answer recorded ({len(answer)} characters)")
    args.cases.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
