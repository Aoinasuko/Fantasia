from __future__ import annotations

from typing import Any

from .combat_model import as_list, safe_float


def character_resistance_map(character: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    for entry in as_list(getattr(character, "resistance", [])):
        if not isinstance(entry, dict):
            continue
        element = str(entry.get("type") or "").strip()
        if not element:
            continue
        amount = max(0.0, min(1.0, safe_float(entry.get("amount"), 0.0)))
        result[element] = max(result.get(element, 0.0), amount)
    return result


def equipment_resistance_map(equipment_summary: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(equipment_summary, dict):
        return {}
    raw = equipment_summary.get("resistance")
    if not isinstance(raw, dict):
        raw = equipment_summary.get("element_resistances")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in raw.items():
        element = str(key or "").strip()
        if not element:
            continue
        result[element] = max(0.0, min(1.0, safe_float(value, 0.0)))
    return result


def combined_resistance_map(character: Any, equipment_summary: dict[str, Any] | None = None) -> dict[str, float]:
    result = character_resistance_map(character)
    for element, amount in equipment_resistance_map(equipment_summary).items():
        result[element] = max(result.get(element, 0.0), amount)
    return result


def damage_multiplier_for_element(
    character: Any,
    element: Any,
    equipment_summary: dict[str, Any] | None = None,
) -> float:
    element_id = str(element or "physical").strip() or "physical"
    resistance = combined_resistance_map(character, equipment_summary)
    amount = max(resistance.get(element_id, 0.0), resistance.get("all", 0.0))
    return max(0.0, 1.0 - max(0.0, min(1.0, amount)))
