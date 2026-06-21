from __future__ import annotations

from typing import Any


COMBAT_ABILITY_IDS = ("str", "dex", "con", "int", "wis", "cha", "magic", "will")
COMBAT_DEFAULT_ATTRIBUTES = {
    "str": 10,
    "dex": 10,
    "con": 10,
    "int": 10,
    "wis": 10,
    "cha": 10,
    "magic": 10,
    "will": 10,
}
COMBAT_SKILL_EFFECT_TYPES = {
    "heal_single",
    "heal_party",
    "damage_hp_single",
    "damage_hp_party",
    "damage_sp_single",
    "damage_sp_party",
    "absorption_single",
    "absorption_party",
    "effect_enemy_single",
    "effect_enemy_party",
    "effect_self",
    "effect_ally_single",
    "effect_ally_party",
}
COMBAT_BUFF_TYPES = {
    "delta_atk",
    "delta_def",
    "regen_hp",
    "regen_sp",
    "decrease_hp",
    "decrease_sp",
    "send_llm",
    "paralysis",
    "psychosis",
    "restraint",
}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def clamp_int(value: Any, low: int, high: int, default: int) -> int:
    return max(low, min(high, safe_int(value, default)))


def normalise_combat_ability(value: Any, default: str = "str") -> str:
    text = str(value or "").strip().lower()
    return text if text in COMBAT_ABILITY_IDS else default


def character_attributes(character: Any) -> dict[str, int]:
    raw = getattr(character, "attributes", None)
    source = raw if isinstance(raw, dict) else {}
    resolved = {
        key: max(1, safe_int(source.get(key), default))
        for key, default in COMBAT_DEFAULT_ATTRIBUTES.items()
    }
    resolved["magic"] = max(1, safe_int(source.get("magic"), resolved["int"]))
    resolved["will"] = max(1, safe_int(source.get("will"), resolved["wis"]))
    return resolved


def normalise_effect_items(value: Any, *, allowed: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in as_list(value):
        if isinstance(item, str):
            effect_type = item.strip()
            data: dict[str, Any] = {"type": effect_type}
        elif isinstance(item, dict):
            data = {str(key): entry for key, entry in item.items() if entry not in (None, "", [], {})}
            effect_type = str(data.get("type") or "").strip()
        else:
            continue
        if effect_type not in allowed:
            continue
        data["type"] = effect_type
        result.append(data)
    return result


def normalise_combat_skill(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    name = str(value.get("name") or "").strip()
    if not name:
        return {}
    effects = normalise_effect_items(value.get("type"), allowed=COMBAT_SKILL_EFFECT_TYPES)
    if not effects:
        effects = [{"type": "damage_hp_single"}]
    return {
        "name": name,
        "desc": str(value.get("desc") or "").strip(),
        "usesp": clamp_int(value.get("usesp"), 1, 12, 1),
        "power": clamp_int(value.get("power"), 1, 5, 1),
        "ability": normalise_combat_ability(value.get("ability"), "str"),
        "element": str(value.get("element") or "physical").strip() or "physical",
        "type": effects,
    }


def normalise_combat_buff(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    name = str(value.get("name") or "").strip()
    if not name:
        return {}
    effects = normalise_effect_items(value.get("type"), allowed=COMBAT_BUFF_TYPES)
    if not effects:
        return {}
    amount = value.get("amount")
    if amount not in (None, ""):
        for effect in effects:
            effect.setdefault("amount", safe_int(amount, 0))
    return {
        "name": name,
        "desc": str(value.get("desc") or "").strip(),
        "duration": max(-1, safe_int(value.get("duration"), 1)),
        "condition_cancell": str(value.get("condition_cancell") or "").strip(),
        "type": effects,
    }


def combat_skill_sp_cost(skill: dict[str, Any]) -> int:
    return clamp_int(skill.get("usesp"), 1, 12, 1)


def combat_skill_power(skill: dict[str, Any]) -> int:
    return clamp_int(skill.get("power"), 1, 5, 1)


def combat_effect_type(effect: Any) -> str:
    if isinstance(effect, dict):
        return str(effect.get("type") or "").strip()
    return str(effect or "").strip()
