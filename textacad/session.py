"""A design session: the conversation with the assistant and every version of the part.

Each change the user asks for creates a new VERSION of the part. Versions
are kept, so the user can go back, compare two of them, or continue from an
older one. Everything is saved under sortida/sessions/<id>/ :

    session.json          the conversation and the data of every version
    v001/part.step ...    the files of version 1 (STEP, STL, 3MF, reference, code)
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import get_settings
from .protocol import slug

FILE_NAMES = ("part.step", "part.stl", "part.3mf", "reference.stl")
_ID = re.compile(r"^[a-z0-9-]{6,80}$")


class SessionError(ValueError):
    """Unknown session or version."""


@dataclass
class Version:
    number: int                     # 1, 2, 3...
    instruction: str                # what the user asked for
    parent: int | None              # version it was derived from (None for the first one)
    base_code: str                  # script exactly as Claude wrote it
    code: str                       # script with the current slider values
    params: dict                    # PARAMS as Claude wrote them
    values: dict                    # current slider values
    info: dict                      # measurements from the runner
    note: dict                      # what the assistant said (summary, changes, assumptions...)
    attempts: list[dict] = field(default_factory=list)
    components: list[str] = field(default_factory=list)   # reference components used
    created: float = field(default_factory=time.time)

    @property
    def label(self) -> str:
        return f"v{self.number}"

    def public(self) -> dict:
        """Data sent to the interface (everything except nothing: versions are small)."""
        return asdict(self)


class DesignSession:
    def __init__(self, root: Path | None = None, session_id: str | None = None, title: str = ""):
        root = Path(root or get_settings().sessions_dir)
        self.id = session_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        if not _ID.match(self.id):
            raise SessionError("Bad session id.")
        self.dir = root / self.id
        self.title = title
        self.created = time.time()
        self.messages: list[dict] = []
        self.versions: list[Version] = []
        self.current: int | None = None

    # -- conversation -------------------------------------------------------

    def add_message(self, role: str, text: str = "", **extra) -> dict:
        msg = {"role": role, "text": text, "time": time.time(), **extra}
        self.messages.append(msg)
        return msg

    # -- versions -----------------------------------------------------------

    def get(self, number: int | None = None) -> Version:
        number = self.current if number is None else number
        for v in self.versions:
            if v.number == number:
                return v
        raise SessionError(f"Version {number} does not exist in this session.")

    def version_dir(self, number: int) -> Path:
        return self.dir / f"v{number:03d}"

    def file_path(self, number: int, name: str) -> Path:
        if name not in FILE_NAMES + ("code.py",):
            raise SessionError(f"Unknown file {name!r}.")
        return self.version_dir(number) / name

    def _store_files(self, number: int, files: dict[str, Path], code: str) -> None:
        folder = self.version_dir(number)
        folder.mkdir(parents=True, exist_ok=True)
        for name in FILE_NAMES:
            target = folder / name
            if name in files:
                shutil.copyfile(files[name], target)
            else:
                target.unlink(missing_ok=True)
        (folder / "code.py").write_text(code, encoding="utf-8")

    def add_version(self, instruction: str, code: str, params: dict, info: dict, note: dict,
                    files: dict[str, Path], attempts: list[dict] | None = None,
                    components: list[str] | None = None, parent: int | None = None) -> Version:
        number = max((v.number for v in self.versions), default=0) + 1
        version = Version(
            number=number, instruction=instruction, parent=parent, base_code=code, code=code,
            params=params, values={k: v["value"] for k, v in params.items()}, info=info, note=note,
            attempts=attempts or [], components=components or [],
        )
        self._store_files(number, files, code)
        self.versions.append(version)
        self.current = number
        if not self.title:
            self.title = note.get("title") or instruction[:60]
        self.save()
        return version

    def update_version(self, number: int, code: str, values: dict, info: dict, files: dict[str, Path]) -> Version:
        """New slider values for an existing version (no new version is created)."""
        version = self.get(number)
        version.code, version.values, version.info = code, dict(values), info
        self._store_files(number, files, code)
        self.save()
        return version

    def history(self, number: int | None = None) -> list[str]:
        """What the user asked, from the first version up to version `number`."""
        chain: list[str] = []
        seen: set[int] = set()
        version = self.get(number) if self.versions else None
        while version is not None and version.number not in seen:
            seen.add(version.number)
            chain.append(version.instruction)
            version = self.get(version.parent) if version.parent else None
        return chain[::-1]

    def file_stem(self, number: int | None = None) -> str:
        version = self.get(number)
        return f"{slug(version.note.get('title') or self.title or 'part')}-v{version.number}"

    # -- saving -------------------------------------------------------------

    def as_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "created": self.created, "current": self.current,
            "messages": self.messages, "versions": [v.public() for v in self.versions],
        }

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / "session.json.tmp"
        tmp.write_text(json.dumps(self.as_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.dir / "session.json")

    @classmethod
    def load(cls, session_id: str, root: Path | None = None) -> "DesignSession":
        root = Path(root or get_settings().sessions_dir)
        if not _ID.match(session_id or ""):
            raise SessionError("Bad session id.")
        path = root / session_id / "session.json"
        if not path.exists():
            raise SessionError(f"Session {session_id} not found.")
        data = json.loads(path.read_text(encoding="utf-8"))
        session = cls(root, session_id=data["id"], title=data.get("title", ""))
        session.created = data.get("created", 0.0)
        session.messages = data.get("messages", [])
        session.versions = [Version(**v) for v in data.get("versions", [])]
        session.current = data.get("current")
        return session


def list_sessions(root: Path | None = None, limit: int = 50) -> list[dict]:
    """Saved sessions, newest first: id, title, date and number of versions."""
    root = Path(root or get_settings().sessions_dir)
    out = []
    if not root.exists():
        return out
    for path in root.glob("*/session.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not data.get("versions"):
            continue
        out.append({"id": data["id"], "title": data.get("title") or data["id"],
                    "created": data.get("created", 0.0), "versions": len(data["versions"])})
    out.sort(key=lambda s: s["created"], reverse=True)
    return out[:limit]


def delete_session(session_id: str, root: Path | None = None) -> bool:
    root = Path(root or get_settings().sessions_dir)
    if not _ID.match(session_id or ""):
        raise SessionError("Bad session id.")
    folder = root / session_id
    if not (folder / "session.json").exists():
        return False
    shutil.rmtree(folder, ignore_errors=True)
    return True
