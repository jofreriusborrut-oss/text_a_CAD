"""Read Claude's answer: the note for the user and the CadQuery script.

The answer format is described in prompts.py:

    <title>...</title>
    <summary>...</summary>
    <changes> - ... </changes>
    <assumptions> - ... </assumptions>
    <questions> - ... </questions>
    <use>process=fdm, max_temp_c=80, outdoor=no, ...</use>
    ```python
    ...script...
    ```

Parsing is forgiving: a missing block is simply empty, and an answer that is
only code (as in the first version of the app) still works.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")
_TAGS = ("title", "summary", "changes", "assumptions", "questions", "use")


class AnswerError(ValueError):
    """Claude's answer contains nothing usable."""


@dataclass
class Note:
    title: str = ""
    summary: str = ""
    changes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    use: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "Note":
        data = data or {}
        return cls(
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            changes=[str(x) for x in data.get("changes", [])],
            assumptions=[str(x) for x in data.get("assumptions", [])],
            questions=[str(x) for x in data.get("questions", [])],
            use=dict(data.get("use", {})),
        )


@dataclass
class Answer:
    note: Note
    code: str | None          # None when Claude only asked questions


def _tag(text: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _bullets(block: str) -> list[str]:
    """Split a block into its bullet points (lines that continue a bullet are joined)."""
    items: list[str] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        if _BULLET.match(line) or not items:
            items.append(_BULLET.sub("", line).strip())
        else:
            items[-1] += " " + line.strip()
    return [i for i in items if i]


def parse_use(text: str) -> dict:
    """ "process=fdm, max_temp_c=80, outdoor=yes" -> {"process": "fdm", "max_temp_c": 80.0, "outdoor": True}"""
    out: dict = {}
    for part in re.split(r"[,;\n]", text):
        if "=" not in part:
            continue
        key, value = (s.strip().lower() for s in part.split("=", 1))
        key = re.sub(r"[^a-z_]", "", key)
        if not key:
            continue
        if value in ("yes", "true", "si", "sí", "y"):
            out[key] = True
        elif value in ("no", "false", "n"):
            out[key] = False
        elif value in ("", "unknown", "none", "null", "?", "n/a"):
            continue
        else:
            try:
                out[key] = float(value.replace("c", "").replace("°", "").strip())
            except ValueError:
                out[key] = value
    return out


def slug(text: str, default: str = "part") -> str:
    """Safe file name from a title: "Suport en L" -> "suport-en-l"."""
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48] or default


def extract_code(answer: str) -> str | None:
    """The Python script inside the answer, or None if there is none."""
    blocks = _FENCE.findall(answer)
    if blocks:
        with_params = [b for b in blocks if "PARAMS" in b]
        code = max(with_params or blocks, key=len)
    else:
        # No ``` fence: accept the text as code only if it looks like a script.
        stripped = answer
        for name in _TAGS:
            stripped = re.sub(rf"<{name}>.*?</{name}>", "", stripped, flags=re.DOTALL | re.IGNORECASE)
        code = stripped if re.search(r"PARAMS\s*=|import cadquery|result\s*=", stripped) else ""
    code = code.strip()
    return code + "\n" if code else None


def parse_answer(answer: str) -> Answer:
    """Split Claude's answer into the note and the script."""
    note = Note(
        title=_tag(answer, "title")[:80],
        summary=" ".join(_tag(answer, "summary").split()),
        changes=_bullets(_tag(answer, "changes")),
        assumptions=_bullets(_tag(answer, "assumptions")),
        questions=_bullets(_tag(answer, "questions")),
        use=parse_use(_tag(answer, "use")),
    )
    code = extract_code(answer)
    if code is None and not (note.summary or note.questions):
        raise AnswerError("Claude returned an empty answer.")
    return Answer(note=note, code=code)
