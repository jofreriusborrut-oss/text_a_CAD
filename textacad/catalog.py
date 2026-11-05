"""Find the reference components mentioned in a text.

    find_components("suport per a un motor NEMA 17 amb cargols M3")
    -> [NEMA 17 entry, M3 fastener entry]

Matching is done on whole words (after removing accents), so "625" inside
"625 mm" is not mistaken for a bearing unless a word like "bearing" or
"rodament" is also there.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .catalog_data import COMPONENTS
from .config import PROJECT_DIR

USER_FILE = PROJECT_DIR / "catalog_user.json"
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?(?:/[0-9]+)?")
_METRIC_WITH_LENGTH = re.compile(r"^(m\d+(?:\.\d+)?)x\d")


class CatalogError(ValueError):
    """A user component is badly formed."""


def tokens(text: str) -> set[str]:
    """Lower-case words and numbers of a text, without accents."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)            # decimal comma -> point
    found = set(_TOKEN.findall(text))
    for tok in list(found):
        m = _METRIC_WITH_LENGTH.match(tok)                 # "m5x20" also counts as "m5"
        if m:
            found.add(m.group(1))
        if tok.endswith("mm") and tok[:-2].replace(".", "").isdigit():
            found.add(tok[:-2])                            # "75mm" also counts as "75"
    return found


def load_user_components(path: Path | None = None) -> list[dict]:
    path = path or USER_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [c for c in data if isinstance(c, dict) and c.get("id") and c.get("name")]


def all_components(path: Path | None = None) -> list[dict]:
    """Built-in components plus the user's own (which win when ids clash)."""
    user = load_user_components(path)
    user_ids = {c["id"] for c in user}
    return user + [c for c in COMPONENTS if c["id"] not in user_ids]


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60]


def save_user_component(name: str, dims: dict, notes: str = "", keywords: list[str] | None = None,
                        source: str = "", path: Path | None = None) -> dict:
    """Add (or replace) a component of the user's own and return the stored entry."""
    name = (name or "").strip()
    if len(name) < 3:
        raise CatalogError("Give the component a name of at least 3 characters.")
    if not isinstance(dims, dict) or not dims:
        raise CatalogError("Give at least one dimension, for example {\"diameter\": 12.5}.")
    clean = {}
    for key, value in dims.items():
        key = re.sub(r"[^a-z0-9_]+", "_", str(key).strip().lower()).strip("_")
        if not key:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise CatalogError(f"The value of {key!r} must be a number or a short text.")
        clean[key] = value if not isinstance(value, str) else value.strip()[:120]
    if not clean:
        raise CatalogError("No valid dimension names were given.")
    words = [w for w in (keywords or []) if tokens(w)]
    match = [sorted(tokens(w)) for w in words] or [sorted(tokens(name))]
    entry = {
        "id": "user-" + _slug(name),
        "name": name,
        "category": "user",
        "match": match,
        "dims": clean,
        "notes": notes.strip()[:800],
        "confidence": "user",
        "source": source.strip()[:300] or "Added by the user",
    }
    path = path or USER_FILE
    items = [c for c in load_user_components(path) if c["id"] != entry["id"]]
    items.append(entry)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def delete_user_component(component_id: str, path: Path | None = None) -> bool:
    path = path or USER_FILE
    items = load_user_components(path)
    kept = [c for c in items if c["id"] != component_id]
    if len(kept) == len(items):
        return False
    path.write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def find_components(text: str, limit: int = 8, path: Path | None = None) -> list[dict]:
    """Components mentioned in `text`, most specific match first."""
    toks = tokens(text)
    hits: list[tuple[int, int, dict]] = []
    for order, comp in enumerate(all_components(path)):
        if any(x in toks for x in comp.get("exclude", ())):
            continue
        best = 0
        for phrase in comp.get("match", ()):
            if phrase and all(w in toks for w in phrase):
                best = max(best, len(phrase))
        if best:
            hits.append((best, -order, comp))
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
    found = [h[2] for h in hits]
    # A specific model hides the generic entry of its family.
    families = {c["family"] for c in found if c.get("family")}
    found = [c for c in found if c.get("family_of") not in families]
    return found[:limit]


def search(query: str, path: Path | None = None) -> list[dict]:
    """Free-text search for the catalogue browser (any word of the query may match)."""
    q = tokens(query)
    comps = all_components(path)
    if not q:
        return comps
    scored = []
    for comp in comps:
        hay = tokens(" ".join([comp["name"], comp.get("category", ""), comp["id"].replace("-", " ")]))
        for phrase in comp.get("match", ()):
            hay.update(phrase)
        score = sum(1 for w in q if w in hay or any(h.startswith(w) for h in hay))
        if score:
            scored.append((score, comp))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [c for _, c in scored]


def describe(comp: dict) -> str:
    """Compact text block for the prompt sent to Claude."""
    lines = [f"- {comp['name']}  [id: {comp['id']}, data: {comp.get('confidence', 'typical')}]"]
    if comp.get("dims"):
        dims = "; ".join(f"{k} = {v}" for k, v in comp["dims"].items())
        lines.append(f"  Dimensions (mm): {dims}")
    if comp.get("notes"):
        lines.append(f"  Notes: {comp['notes']}")
    return "\n".join(lines)


def public(comp: dict) -> dict:
    """Entry as sent to the interface."""
    return {k: comp.get(k) for k in ("id", "name", "category", "dims", "notes", "confidence", "source")}
