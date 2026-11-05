"""Replay recorded Claude answers through the REAL pipeline and report what happened.

    python tools/eval_run.py [--cases eval/cases.json] [--out ci-out] [--only CASE_ID]

Why: the automatic tests replace Claude by hand-written answers. This tool
measures how the app behaves with answers that Claude really gave (recorded
with tools/eval_ask.py), on real CadQuery: does the script run, does the part
match what the script says it built, how many corrections were needed.

For every case it creates a design session under <out>/sessions and plays
the user's messages in order. When the pipeline needs an answer that has not
been recorded yet (a correction after a failed attempt, or the next change),
the exact message it wanted to send is saved to <out>/pending/<case>.json so
that eval_ask.py can ask Claude and record it. Repeat until nothing is pending.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textacad import assistant, checks, printability      # noqa: E402
from textacad.config import get_settings                  # noqa: E402
from textacad.materials import UseCase, recommend          # noqa: E402
from textacad.mesh import load_stl                         # noqa: E402
from textacad.session import DesignSession                 # noqa: E402
from textacad.simulate import LoadCase, default_load_case, run_simulation   # noqa: E402


class NeedAnswer(Exception):
    """The pipeline asked for an answer that is not recorded yet."""

    def __init__(self, message: str):
        super().__init__("no recorded answer")
        self.message = message


def _measure(session: DesignSession, version) -> dict:
    """Checks, a draft simulation and the print analysis of one version."""
    out: dict = {}
    stl = session.file_path(version.number, "part.stl").read_bytes()
    out["checks"] = [{"level": c.level, "code": c.code, "detail": c.text("en")[1]}
                     for c in checks.run_checks(version.info, stl, "petg")]
    try:
        mesh = load_stl(stl)
        own = bool(version.info.get("load_case"))
        case = LoadCase.from_dict(version.info["load_case"]) if own else default_load_case(mesh)
        s = run_simulation(mesh, case, "petg", "draft").summary()
        out["simulation"] = {"own_load_case": own, "description": case.description,
                             **{k: s[k] for k in ("max_stress_mpa", "max_displacement_mm", "safety_factor",
                                                  "n_elements", "volume_error", "equilibrium_error", "warnings",
                                                  "seconds")}}
        use = UseCase.from_dict(version.note.get("use") or {})
        use.stress_mpa = s["max_stress_mpa"]
        out["material"] = [r.material.id for r in recommend(use) if r.suitable][:3]
        p = printability.analyse(mesh, "petg")
        out["print"] = {"up": p["best"]["up"], "support_mm2": p["best"]["support_area_mm2"], "notes": p["notes"],
                        "mass_g": p["estimate"]["mass_g"], "minutes": p["estimate"]["time_minutes"]}
    except Exception as exc:  # noqa: BLE001 - the report must say what went wrong
        out["simulation"] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def run_case(args: tuple[dict, str]) -> dict:
    case, out_dir = args
    out = Path(out_dir)
    settings = replace(get_settings(), max_attempts=4, exec_timeout=60, sessions_dir=out / "sessions")
    session = DesignSession(out / "sessions", session_id="eval-" + case["id"])
    report = {"id": case["id"], "turns": [], "pending": False}

    for k, turn in enumerate(case["turns"]):
        answers = list(turn.get("answers", []))
        used = 0

        def replay(message: str, _settings=None) -> str:
            nonlocal used
            if used >= len(answers):
                raise NeedAnswer(message)
            used += 1
            return answers[used - 1]

        assistant.ask_claude = replay
        events: list[dict] = []
        start = time.monotonic()
        entry: dict = {"text": turn["text"]}
        try:
            outcome = assistant.handle_message(session, turn["text"], events.append, settings)
        except NeedAnswer as need:
            (out / "pending").mkdir(parents=True, exist_ok=True)
            (out / "pending" / f"{case['id']}.json").write_text(json.dumps(
                {"case": case["id"], "turn": k, "answer_number": used + 1, "message": need.message},
                ensure_ascii=False, indent=1), encoding="utf-8")
            entry.update(status="pending", answers_used=used,
                         problems=[e.get("detail", "") for e in events if e["stage"] == "error"])
            report["turns"].append(entry)
            report["pending"] = True
            break

        entry["seconds"] = round(time.monotonic() - start, 1)
        entry["status"] = outcome.kind
        entry["attempts"] = [{"number": a.number, "error": (a.error or "")[-1200:] or None} for a in outcome.attempts]
        if outcome.note:
            entry["note"] = outcome.note.as_dict()
        if outcome.kind == "version":
            v = outcome.version
            entry.update(
                version=v.number, components=v.components, n_params=len(v.params),
                code_lines=len(v.code.splitlines()), size=[round(x, 3) for x in v.info["bbox"]["size"]],
                expected_bbox=v.info.get("expected_bbox"), volume_cm3=round(v.info["volume_mm3"] / 1000, 2),
                holes=v.info.get("holes"), expected_holes=v.info.get("expected_holes"),
                reference=v.info.get("reference"), runner_notes=v.info.get("notes"),
            )
            entry.update(_measure(session, v))
        report["turns"].append(entry)
        if outcome.kind != "version":
            break
    return report


def _markdown(reports: list[dict]) -> str:
    lines = ["| case | turn | result | attempts | warnings | size (mm) | holes | stress MPa / SF |",
             "|---|---|---|---|---|---|---|---|"]
    for r in reports:
        for k, t in enumerate(r["turns"], start=1):
            if t["status"] == "version":
                warn = ", ".join(c["code"] for c in t["checks"] if c["level"] in ("warning", "error")) or "-"
                size = " x ".join(f"{v:g}" for v in t["size"])
                holes = ", ".join(f"{h['count']}xd{h['diameter']:g}{h['axis']}" for h in (t.get("holes") or [])) or "-"
                sim = t.get("simulation", {})
                stress = (f"{sim['max_stress_mpa']:g} / {sim['safety_factor']:g}" + ("" if sim.get("own_load_case") else " (auto)")
                          if "max_stress_mpa" in sim else "error: " + sim.get("error", "?")[:60])
                attempts = len(t["attempts"])
            else:
                warn = size = holes = stress = "-"
                attempts = len(t.get("attempts", [])) or t.get("answers_used", 0)
            lines.append(f"| {r['id']} | {k} | {t['status']} | {attempts} | {warn} | {size} | {holes} | {stress} |")
    return "\n".join(lines) + "\n"


def summarize(reports: list[dict]) -> dict:
    turns = [t for r in reports for t in r["turns"] if t["status"] != "pending"]
    built = [t for t in turns if t["status"] == "version"]
    clean = [t for t in built if not any(c["level"] in ("warning", "error") for c in t["checks"])]
    return {
        "cases": len(reports), "turns_played": len(turns), "parts_built": len(built),
        "first_attempt": sum(1 for t in built if len(t["attempts"]) == 1),
        "needed_corrections": sum(1 for t in built if len(t["attempts"]) > 1),
        "built_without_warnings": len(clean),
        "failed": sum(1 for t in turns if t["status"] == "failed"),
        "questions_only": sum(1 for t in turns if t["status"] == "questions"),
        "pending_cases": [r["id"] for r in reports if r["pending"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", type=Path, default=ROOT / "eval" / "cases.json")
    ap.add_argument("--out", type=Path, default=ROOT / "ci-out")
    ap.add_argument("--only", help="Run a single case")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    cases = [c for c in cases if c["turns"] and c["turns"][0].get("answers")]
    for name in ("sessions", "pending"):
        shutil.rmtree(args.out / name, ignore_errors=True)
    args.out.mkdir(parents=True, exist_ok=True)

    jobs = [(c, str(args.out)) for c in cases]
    if args.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            reports = list(pool.map(run_case, jobs))
    else:
        reports = [run_case(j) for j in jobs]

    summary = summarize(reports)
    (args.out / "eval.json").write_text(json.dumps({"summary": summary, "cases": reports}, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    table = _markdown(reports)
    (args.out / "eval.md").write_text(json.dumps(summary, indent=1) + "\n\n" + table, encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
