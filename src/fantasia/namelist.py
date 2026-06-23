from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from .paths import NAMELIST_TEMPLATE_PATH


NAMELIST_LOAD_ERRORS: list[str] = []


def namelist_entries() -> list[dict[str, str]]:
    return deepcopy(NAMELIST_ENTRIES)


def claim_name_from_namelist(
    world: Any,
    *,
    seed: str = "",
    reason: str = "",
    language: str = "ja",
    reserved_names: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, str] | None:
    entries = NAMELIST_ENTRIES
    if not entries or world is None:
        return None
    extra = getattr(world, "extra", None)
    if not isinstance(extra, dict):
        return None
    used_ids = _string_list(extra.setdefault("used_namelist_ids", []))
    used_names = set(_string_list(extra.setdefault("used_namelist_names", [])))
    reserved = {str(value).strip() for value in (reserved_names or ()) if str(value).strip()}
    for character in getattr(world, "characters", {}).values() if isinstance(getattr(world, "characters", None), dict) else []:
        name = str(getattr(character, "name", "") or "").strip()
        if name:
            reserved.add(name)
    candidates = [
        entry
        for entry in entries
        if str(entry.get("id") or "") not in used_ids
        and str(entry.get("name_ja") or "") not in used_names
        and str(entry.get("english_en") or "") not in used_names
        and str(entry.get("name_ja") or "") not in reserved
        and str(entry.get("english_en") or "") not in reserved
    ]
    if not candidates:
        return None
    rng = random.Random(seed or f"namelist:{getattr(world, 'world_name', '')}:{len(used_ids)}")
    entry = deepcopy(rng.choice(candidates))
    name = str(entry.get("name_ja") if str(language or "").lower().startswith("ja") else entry.get("english_en") or entry.get("name_ja"))
    used_ids.append(str(entry["id"]))
    used_names.add(str(entry.get("name_ja") or ""))
    used_names.add(str(entry.get("english_en") or ""))
    extra["used_namelist_ids"] = used_ids
    extra["used_namelist_names"] = sorted(name for name in used_names if name)
    claims = extra.setdefault("namelist_claims", [])
    if isinstance(claims, list):
        claims.append(
            {
                "id": entry["id"],
                "name_ja": entry["name_ja"],
                "english_en": entry["english_en"],
                "used_name": name,
                "reason": reason,
            }
        )
    return entry


def apply_namelist_metadata(target: dict[str, Any], entry: dict[str, str], *, reason: str) -> None:
    extra = target.setdefault("extra", {})
    if isinstance(extra, dict):
        extra["namelist_id"] = str(entry.get("id") or "")
        extra["namelist_name_ja"] = str(entry.get("name_ja") or "")
        extra["namelist_english_en"] = str(entry.get("english_en") or "")
        extra["namelist_reason"] = reason
    flags = target.setdefault("flags", {})
    if isinstance(flags, dict):
        flags["namelist_id"] = str(entry.get("id") or "")


def _load_namelist_entries() -> list[dict[str, str]]:
    loaded: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    NAMELIST_LOAD_ERRORS.clear()
    for path in _candidate_paths():
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            NAMELIST_LOAD_ERRORS.append(f"{path}: {exc}")
            continue
        rows = raw if isinstance(raw, list) else raw.get("names") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            NAMELIST_LOAD_ERRORS.append(f"{path}: root must be a JSON array or a names wrapper")
            continue
        for row in rows:
            entry = _normalise_entry(row, path)
            if entry is None:
                continue
            if entry["id"] in seen_ids:
                NAMELIST_LOAD_ERRORS.append(f"{path}: duplicate id {entry['id']}")
                continue
            seen_ids.add(entry["id"])
            loaded.append(entry)
        if loaded:
            break
    return loaded


def _candidate_paths() -> list[Path]:
    return [NAMELIST_TEMPLATE_PATH]


def _normalise_entry(raw: Any, source_path: Path) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    entry_id = str(raw.get("id") or "").strip()
    name_ja = str(raw.get("name_ja") or "").strip()
    english_en = str(raw.get("english_en") or "").strip()
    if not entry_id or not name_ja or not english_en:
        NAMELIST_LOAD_ERRORS.append(f"{source_path}: name entry must have id, name_ja, and english_en")
        return None
    return {"id": entry_id, "name_ja": name_ja, "english_en": english_en}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


NAMELIST_ENTRIES = _load_namelist_entries()
