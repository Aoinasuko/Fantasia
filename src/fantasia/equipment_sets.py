from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from .items import (
    EQUIPMENT_CATEGORIES,
    WEAPON_CATEGORIES,
    equipment_slot_for_category,
    item_template_by_id,
    make_item_from_template_id,
)
from .paths import DATA_DIR, ROOT


EQUIPMENT_SET_LOAD_ERRORS: list[str] = []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _template_dirs() -> list[Path]:
    candidates = [DATA_DIR / "EquipmentSet", ROOT / "Data" / "EquipmentSet"]
    result: list[Path] = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def _normalise_equipment_set(raw: Any, source_path: Path) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    set_id = str(raw.get("id") or "").strip()
    if not set_id:
        return None
    categories: dict[str, list[str]] = {}
    for category in sorted(EQUIPMENT_CATEGORIES):
        ids = [str(item).strip() for item in _as_list(raw.get(category)) if str(item).strip()]
        if ids:
            categories[category] = ids
    return {"id": set_id, "categories": categories, "source_path": str(source_path), "raw": deepcopy(raw)}


def _load_equipment_sets() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    EQUIPMENT_SET_LOAD_ERRORS.clear()
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for template_path in sorted(directory.glob("*.json")):
            try:
                raw_items = json.loads(template_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                EQUIPMENT_SET_LOAD_ERRORS.append(f"{template_path}: {exc}")
                continue
            if not isinstance(raw_items, list):
                EQUIPMENT_SET_LOAD_ERRORS.append(f"{template_path}: root must be a JSON array")
                continue
            for raw in raw_items:
                equipment_set = _normalise_equipment_set(raw, template_path)
                if equipment_set is not None:
                    loaded[str(equipment_set["id"])] = equipment_set
    return loaded


EQUIPMENT_SETS = _load_equipment_sets()


def equipment_set_by_id(set_id: Any) -> dict[str, Any] | None:
    equipment_set = EQUIPMENT_SETS.get(str(set_id or "").strip())
    return deepcopy(equipment_set) if equipment_set else None


def build_equipment_from_set(
    set_id: Any,
    *,
    level: int = 0,
    seed: str = "",
    rarity: str = "common",
    source: str = "npc_equipment",
) -> dict[str, dict[str, Any]]:
    equipment_set = equipment_set_by_id(set_id)
    if not equipment_set:
        return {}
    rng = random.Random(seed or f"equipment-set:{set_id}:{level}")
    categories = equipment_set.get("categories") if isinstance(equipment_set.get("categories"), dict) else {}
    equipment: dict[str, dict[str, Any]] = {}

    weapon_ids: list[str] = []
    for category in sorted(WEAPON_CATEGORIES):
        weapon_ids.extend(_eligible_template_ids(categories.get(category), category, level))
    weapon = _make_equipped_item(rng.choice(weapon_ids), rarity=rarity, source=source) if weapon_ids else None
    if weapon:
        equipment["weapon"] = weapon

    for category in sorted(set(EQUIPMENT_CATEGORIES) - set(WEAPON_CATEGORIES)):
        item_ids = _eligible_template_ids(categories.get(category), category, level)
        if not item_ids:
            continue
        item = _make_equipped_item(rng.choice(item_ids), rarity=rarity, source=source)
        if not item:
            continue
        slot = equipment_slot_for_category(str(item.get("category") or ""))
        if slot:
            equipment[slot] = item
    return equipment


def _eligible_template_ids(value: Any, expected_category: str, level: int) -> list[str]:
    result: list[str] = []
    max_level = max(0, _safe_int(level, 0))
    for template_id in [str(item).strip() for item in _as_list(value) if str(item).strip()]:
        template = item_template_by_id(template_id)
        if not template:
            continue
        if str(template.get("category") or "").strip() != expected_category:
            continue
        if _safe_int(template.get("level"), 0) > max_level:
            continue
        result.append(template_id)
    return result


def _make_equipped_item(template_id: str, *, rarity: str, source: str) -> dict[str, Any] | None:
    template = item_template_by_id(template_id)
    if not template:
        return None
    item = make_item_from_template_id(template_id, quantity=1, rarity=rarity, source=source)
    slot = equipment_slot_for_category(str(item.get("category") or ""))
    if not slot:
        return None
    item["equipped"] = True
    item["equipment_slot"] = slot
    return item
