from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from .items import RARITY_ORDER, generate_reward_item, normalise_item, normalise_rarity
from .paths import LOOT_TABEL_TEMPLATE_DIR, ROOT


LOOT_TABEL_LOAD_ERRORS: list[str] = []


def generate_loot_table_items(
    loot_table_ref: Any,
    *,
    context: str,
    danger_level: int = 0,
    seed: str = "",
    source: str = "loot_tabel",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, table in enumerate(resolve_loot_tables(loot_table_ref)):
        table_id = str(table.get("id") or f"loot_table_{index}")
        rng = random.Random(f"loot-tabel|{table_id}|{context}|{danger_level}|{seed}|{index}")
        lot_min = max(0, _safe_int(table.get("lot_min"), 1))
        lot_max = max(lot_min, _safe_int(table.get("lot_max"), lot_min))
        lot_count = rng.randint(lot_min, lot_max) if lot_max > 0 else 0
        entries = [entry for entry in _as_list(table.get("item_tabel") or table.get("item_table")) if isinstance(entry, dict)]
        if not entries or lot_count <= 0:
            continue
        weights = [max(0.0, _safe_float(entry.get("generate_rate"), 1.0)) for entry in entries]
        if not any(weight > 0 for weight in weights):
            weights = [1.0 for _ in entries]
        for lot_index in range(lot_count):
            entry = deepcopy(rng.choices(entries, weights=weights, k=1)[0])
            items.append(
                _item_from_loot_entry(
                    entry,
                    context=context,
                    danger_level=danger_level,
                    seed=f"{seed}|{table_id}|{lot_index}",
                    rng=rng,
                    source=source,
                    loot_table_id=table_id,
                )
            )
    return items


def resolve_loot_tables(loot_table_ref: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for ref in _as_list(loot_table_ref):
        if isinstance(ref, dict):
            if isinstance(ref.get("item_tabel") or ref.get("item_table"), list):
                result.append(deepcopy(ref))
                continue
            ref_id = str(ref.get("loot_tabel") or ref.get("loot_tabel_id") or ref.get("loot_table") or ref.get("loot_table_id") or ref.get("id") or "").strip()
        else:
            ref_id = str(ref or "").strip()
        if not ref_id:
            continue
        table = LOOT_TABELS_BY_ID.get(ref_id)
        if table:
            result.append(deepcopy(table))
    return result


def loot_table_ids() -> set[str]:
    return set(LOOT_TABELS_BY_ID)


def _item_from_loot_entry(
    entry: dict[str, Any],
    *,
    context: str,
    danger_level: int,
    seed: str,
    rng: random.Random,
    source: str,
    loot_table_id: str,
) -> dict[str, Any]:
    category = str(entry.get("target_category") or entry.get("category") or "junk").strip()
    amount_min = max(1, _safe_int(entry.get("amount_min"), 1))
    amount_max = max(amount_min, _safe_int(entry.get("amount_max"), amount_min))
    amount = rng.randint(amount_min, amount_max)
    item = generate_reward_item(
        category,
        context=context,
        danger_level=danger_level,
        seed=seed,
    )
    bounded_rarity = _bounded_rarity(
        item.get("rarity"),
        entry.get("rarity_min"),
        entry.get("rarity_max"),
        rng,
    )
    if bounded_rarity and bounded_rarity != normalise_rarity(item.get("rarity")):
        item["rarity"] = bounded_rarity
        item.pop("value", None)
    item["quantity"] = amount
    item["source"] = source
    item["loot_tabel_id"] = loot_table_id
    item["loot_tabel_context"] = context
    return normalise_item(item, source=source, fallback_category=category)


def _bounded_rarity(value: Any, rarity_min: Any, rarity_max: Any, rng: random.Random) -> str:
    current = normalise_rarity(value)
    has_min = rarity_min not in (None, "")
    has_max = rarity_max not in (None, "")
    if not has_min and not has_max:
        return current
    low = RARITY_ORDER.index(normalise_rarity(rarity_min)) if has_min else 0
    high = RARITY_ORDER.index(normalise_rarity(rarity_max)) if has_max else len(RARITY_ORDER) - 1
    if high < low:
        high = low
    current_index = RARITY_ORDER.index(current)
    if low <= current_index <= high:
        return current
    return RARITY_ORDER[rng.randint(low, high)]


def _load_loot_tabels() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    LOOT_TABEL_LOAD_ERRORS.clear()
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            for raw in _load_json_array(path):
                if not isinstance(raw, dict):
                    continue
                table_id = str(raw.get("id") or "").strip()
                entries = raw.get("item_tabel") or raw.get("item_table")
                if not table_id or not isinstance(entries, list):
                    LOOT_TABEL_LOAD_ERRORS.append(f"{path}: loot table must have id and item_tabel")
                    continue
                loaded[table_id] = {
                    **deepcopy(raw),
                    "source_path": str(path),
                    "lot_min": max(0, _safe_int(raw.get("lot_min"), 1)),
                    "lot_max": max(0, _safe_int(raw.get("lot_max"), _safe_int(raw.get("lot_min"), 1))),
                }
    return loaded


def _template_dirs() -> list[Path]:
    result: list[Path] = []
    for candidate in (LOOT_TABEL_TEMPLATE_DIR, ROOT / "Data" / "Template" / "LootTabel"):
        if candidate.exists() and candidate not in result:
            result.append(candidate)
    return result


def _load_json_array(path: Path) -> list[Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        LOOT_TABEL_LOAD_ERRORS.append(f"{path}: {exc}")
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("items", "tables", "loot_tabels", "loot_tables", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    LOOT_TABEL_LOAD_ERRORS.append(f"{path}: root must be a JSON array or known wrapper")
    return []


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value in (None, ""):
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


LOOT_TABELS_BY_ID = _load_loot_tabels()
