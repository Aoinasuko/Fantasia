from __future__ import annotations

import hashlib
import random
from copy import deepcopy
from typing import Any

from .i18n import ELEMENT_IDS
from .status_effects import STATUS_IMMUNITY_EFFECT_IDS


RARITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary", "artifact")
RARITY_POWER = {
    "common": 1,
    "uncommon": 2,
    "rare": 4,
    "epic": 7,
    "legendary": 11,
    "artifact": 16,
}
RARITY_POWER_MULTIPLIER = {
    "common": 1.0,
    "uncommon": 1.2,
    "rare": 1.5,
    "epic": 2.0,
    "legendary": 2.5,
    "artifact": 3.0,
}
RARITY_EFFECT_COUNT = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "artifact": 5,
}
RARITY_LLM_EFFECT_COUNT = {
    "common": 0,
    "uncommon": 0,
    "rare": 1,
    "epic": 1,
    "legendary": 2,
    "artifact": 2,
}

WEAPON_CATEGORIES = {
    "weapon_small",
    "weapon_medium",
    "weapon_large",
    "weapon_long",
    "weapon_range",
}
ARMOR_CATEGORIES = {
    "armor_shield",
    "armor_head",
    "armor_body",
    "armor_arm",
    "armor_leg",
    "armor_cloth",
}
ACCESSORY_CATEGORIES = {"accessory_ring", "accessory_amulet"}
EQUIPMENT_CATEGORIES = WEAPON_CATEGORIES | ARMOR_CATEGORIES | ACCESSORY_CATEGORIES

ATTACK_CAP_TABLE = (
    (1, 3, 6),
    (10, 9, 12),
    (20, 15, 18),
    (30, 21, 24),
    (40, 27, 30),
    (50, 33, 36),
)
DEFENSE_CAP_TABLE = (
    (1, 0, 3),
    (10, 3, 6),
    (20, 6, 9),
    (30, 9, 12),
    (40, 12, 15),
    (50, 15, 18),
)
MAX_RESOURCE_CAP_TABLE = (
    (1, 1, 5),
    (10, 5, 10),
    (20, 10, 20),
    (30, 20, 30),
    (40, 30, 40),
    (50, 40, 50),
)
ATTRIBUTE_CAP_TABLE = (
    (1, 1, 3),
    (10, 3, 5),
    (20, 5, 7),
    (30, 7, 9),
    (40, 9, 11),
    (50, 11, 15),
)
REGEN_CAP_TABLE = (
    (1, 1, 2),
    (10, 2, 4),
    (20, 3, 6),
    (30, 4, 8),
    (40, 5, 10),
    (50, 6, 12),
)
DAMAGE_REDUCTION_CAP_TABLE = (
    (1, 1, 5),
    (10, 2, 10),
    (20, 3, 15),
    (30, 4, 20),
    (40, 5, 25),
    (50, 6, 30),
)

RESOURCE_EFFECT_TYPES = {"max_hp", "hp_max", "max_sp", "max_mp", "sp_max", "mp_max"}
ATTRIBUTE_EFFECT_TYPES = {"str", "dex", "con", "int", "wis", "cha"}
REGEN_EFFECT_TYPES = {"hp_regen", "auto_hp_regen", "hp_auto_recovery", "sp_regen", "mp_regen", "auto_sp_regen", "mp_auto_recovery"}
DAMAGE_REDUCTION_EFFECT_TYPES = {
    "damage_reduction",
    "damage_reduce",
    "all_damage_reduction",
    "element_resistance",
    "element_damage_reduction",
    "resist_element",
}


def equipment_effects(
    category: str,
    rarity: str,
    name: str,
    *,
    player_level: int | None = None,
    seed: str = "",
) -> list[dict[str, Any]]:
    rarity = normalise_rarity(rarity)
    count = RARITY_EFFECT_COUNT.get(rarity, 0)
    if count <= 0:
        return []
    category = str(category or "").strip()
    rng = _rng("equipment_effects", category, rarity, name, seed, player_level or "")
    pool = [
        "max_hp",
        "max_sp",
        "str",
        "dex",
        "con",
        "int",
        "wis",
        "cha",
        "hp_regen",
        "sp_regen",
        "damage_reduction",
        "status_immunity",
    ]
    if category not in WEAPON_CATEGORIES:
        pool.append("element_resistance")
    selected = rng.sample(pool, k=min(count, len(pool)))
    return [
        _build_effect(effect_type, category, rarity, rng, player_level=player_level)
        for effect_type in selected
    ]


def equipment_llm_effects(category: str, rarity: str, name: str, *, seed: str = "") -> list[dict[str, Any]]:
    rarity = normalise_rarity(rarity)
    count = RARITY_LLM_EFFECT_COUNT.get(rarity, 0)
    if count <= 0:
        return []
    rng = _rng("equipment_llm_effects", category, rarity, name, seed)
    pool = [
        {"name": "古い誓約", "effect": "持ち主の約束や過去の縁を物語に反映しやすい。"},
        {"name": "精霊の気配", "effect": "自然や精霊に関わる場面で反応や手がかりを増やせる。"},
        {"name": "威圧の意匠", "effect": "交渉や戦闘前の威圧として描写できる。"},
        {"name": "守護の銘", "effect": "危険を察した時に警告や守りの演出を出せる。"},
        {"name": "不吉な残響", "effect": "呪い、亡霊、古戦場に関わる描写で存在感を出せる。"},
        {"name": "幸運の印", "effect": "偶然の発見や小さな幸運を物語に混ぜられる。"},
    ]
    return rng.sample(pool, k=min(count, len(pool)))


def ensure_equipment_enchants(
    item: dict[str, Any],
    *,
    player_level: int | None = None,
    seed: str = "",
    cap_existing: bool = False,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        return item
    category = str(item.get("category") or "").strip()
    if category not in EQUIPMENT_CATEGORIES:
        return item
    rarity = normalise_rarity(item.get("rarity"))
    name = str(item.get("name") or "")
    effects = item.get("effects")
    if not isinstance(effects, list) or not effects:
        item["effects"] = equipment_effects(category, rarity, name, player_level=player_level, seed=seed)
    elif cap_existing and player_level is not None:
        item["effects"] = cap_equipment_effects(effects, player_level, rarity=rarity, seed=seed)
    llm_effects = item.get("llm_effects")
    if not isinstance(llm_effects, list) or not llm_effects:
        item["llm_effects"] = equipment_llm_effects(category, rarity, name, seed=seed)
    return item


def apply_equipment_level_caps(
    item: dict[str, Any],
    player_level: int,
    *,
    seed: str = "",
) -> dict[str, Any]:
    if not isinstance(item, dict):
        return item
    category = str(item.get("category") or "").strip()
    if category not in EQUIPMENT_CATEGORIES:
        return item
    rarity = normalise_rarity(item.get("rarity"))
    name = str(item.get("name") or "")
    rng = _rng("equipment_level_cap", category, rarity, name, seed, player_level)
    if category in WEAPON_CATEGORIES or _safe_int(item.get("attack"), 0) > 0:
        item["attack"] = _cap_integer_value(
            item.get("attack"),
            ATTACK_CAP_TABLE,
            player_level,
            rarity=rarity,
            rng=rng,
            minimum_final=1,
        )
    if category in ARMOR_CATEGORIES or _safe_int(item.get("defense"), 0) > 0:
        item["defense"] = _cap_integer_value(
            item.get("defense"),
            DEFENSE_CAP_TABLE,
            player_level,
            rarity=rarity,
            rng=rng,
            minimum_final=0,
        )
    ensure_equipment_enchants(item, player_level=player_level, seed=seed, cap_existing=True)
    return item


def cap_equipment_effects(
    effects: list[Any],
    player_level: int,
    *,
    rarity: str = "common",
    seed: str = "",
) -> list[dict[str, Any]]:
    rng = _rng("equipment_effect_caps", rarity, seed, player_level)
    result: list[dict[str, Any]] = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        result.append(_cap_effect(effect, player_level, normalise_rarity(rarity), rng))
    return result


def normalise_rarity(value: Any) -> str:
    rarity = str(value or "common").strip().lower()
    return rarity if rarity in RARITY_ORDER else "common"


def _build_effect(
    effect_type: str,
    category: str,
    rarity: str,
    rng: random.Random,
    *,
    player_level: int | None,
) -> dict[str, Any]:
    if player_level is None:
        return _legacy_scaled_effect(effect_type, category, rarity, rng)
    if effect_type == "max_hp":
        return {"type": "max_hp", "value": _rolled_scaled_value(MAX_RESOURCE_CAP_TABLE, player_level, rarity, rng)}
    if effect_type == "max_sp":
        return {"type": "max_sp", "value": _rolled_scaled_value(MAX_RESOURCE_CAP_TABLE, player_level, rarity, rng)}
    if effect_type in ATTRIBUTE_EFFECT_TYPES:
        return {"type": effect_type, "value": _rolled_scaled_value(ATTRIBUTE_CAP_TABLE, player_level, rarity, rng)}
    if effect_type == "hp_regen":
        return {"type": "hp_regen", "value": _rolled_scaled_value(REGEN_CAP_TABLE, player_level, rarity, rng)}
    if effect_type == "sp_regen":
        return {"type": "sp_regen", "value": _rolled_scaled_value(REGEN_CAP_TABLE, player_level, rarity, rng)}
    if effect_type == "status_immunity":
        status = rng.choice(list(STATUS_IMMUNITY_EFFECT_IDS))
        return {"type": "status_immunity", "status": status, "value": 1}
    if effect_type == "element_resistance":
        element_id = rng.choice([element_id for element_id in ELEMENT_IDS if element_id != "none"] or ["physical"])
        percent = _rolled_scaled_value(DAMAGE_REDUCTION_CAP_TABLE, player_level, rarity, rng)
        return {"type": "element_resistance", "element": element_id, "amount": round(percent / 100.0, 3), "value": percent}
    percent = _rolled_scaled_value(DAMAGE_REDUCTION_CAP_TABLE, player_level, rarity, rng)
    return {"type": "damage_reduction", "amount": round(percent / 100.0, 3), "value": percent}


def _legacy_scaled_effect(effect_type: str, category: str, rarity: str, rng: random.Random) -> dict[str, Any]:
    power = RARITY_POWER.get(rarity, 1)
    if effect_type == "max_hp":
        return {"type": "max_hp", "value": 5 + power * 3}
    if effect_type == "max_sp":
        return {"type": "max_sp", "value": 4 + power * 2}
    if effect_type in ATTRIBUTE_EFFECT_TYPES:
        return {"type": effect_type, "value": max(1, power // 3)}
    if effect_type == "hp_regen":
        return {"type": "hp_regen", "value": max(1, power // 4)}
    if effect_type == "sp_regen":
        return {"type": "sp_regen", "value": max(1, power // 5)}
    if effect_type == "status_immunity":
        status = rng.choice(list(STATUS_IMMUNITY_EFFECT_IDS))
        return {"type": "status_immunity", "status": status, "value": 1}
    if effect_type == "element_resistance":
        element_id = rng.choice([element_id for element_id in ELEMENT_IDS if element_id != "none"] or ["physical"])
        amount = 0.5 if power >= 7 else 0.2
        return {"type": "element_resistance", "element": element_id, "amount": amount, "value": int(round(amount * 100))}
    percent = min(30, max(1, 1 + power * 2))
    return {"type": "damage_reduction", "amount": round(percent / 100.0, 3), "value": percent}


def _cap_effect(effect: dict[str, Any], player_level: int, rarity: str, rng: random.Random) -> dict[str, Any]:
    capped = deepcopy(effect)
    effect_type = str(capped.get("type") or capped.get("stat") or capped.get("name") or "").strip().lower()
    if effect_type in RESOURCE_EFFECT_TYPES:
        capped["value"] = _cap_integer_value(capped.get("value", capped.get("amount")), MAX_RESOURCE_CAP_TABLE, player_level, rarity=rarity, rng=rng)
    elif effect_type in ATTRIBUTE_EFFECT_TYPES:
        capped["value"] = _cap_integer_value(capped.get("value", capped.get("amount")), ATTRIBUTE_CAP_TABLE, player_level, rarity=rarity, rng=rng)
    elif effect_type in REGEN_EFFECT_TYPES:
        capped["value"] = _cap_integer_value(capped.get("value", capped.get("amount")), REGEN_CAP_TABLE, player_level, rarity=rarity, rng=rng)
    elif effect_type in DAMAGE_REDUCTION_EFFECT_TYPES:
        current_percent = _effect_percent(capped)
        percent = _cap_integer_value(current_percent, DAMAGE_REDUCTION_CAP_TABLE, player_level, rarity=rarity, rng=rng, minimum_final=1)
        capped["amount"] = round(max(0, min(95, percent)) / 100.0, 3)
        capped["value"] = int(round(max(0, min(95, percent))))
    return capped


def _cap_integer_value(
    current: Any,
    table: tuple[tuple[int, int, int], ...],
    player_level: int,
    *,
    rarity: str,
    rng: random.Random,
    minimum_final: int = 1,
) -> int:
    low, high = _range_for_level(table, player_level)
    multiplier = RARITY_POWER_MULTIPLIER.get(normalise_rarity(rarity), 1.0)
    current_value = _safe_int(current, 0)
    if current_value <= 0:
        base_value = rng.randint(low, high)
    else:
        base_value = int(round(current_value / max(0.01, multiplier)))
        if base_value < low:
            base_value = rng.randint(low, high)
        elif base_value > high:
            base_value = high
    return max(minimum_final, int(round(base_value * multiplier)))


def _rolled_scaled_value(
    table: tuple[tuple[int, int, int], ...],
    player_level: int,
    rarity: str,
    rng: random.Random,
) -> int:
    low, high = _range_for_level(table, player_level)
    base_value = rng.randint(low, high)
    multiplier = RARITY_POWER_MULTIPLIER.get(normalise_rarity(rarity), 1.0)
    return max(1, int(round(base_value * multiplier)))


def _range_for_level(table: tuple[tuple[int, int, int], ...], player_level: int) -> tuple[int, int]:
    level = max(1, min(50, _safe_int(player_level, 1)))
    first_level, first_low, first_high = table[0]
    if level <= first_level:
        return first_low, first_high
    for left, right in zip(table, table[1:]):
        left_level, left_low, left_high = left
        right_level, right_low, right_high = right
        if level <= right_level:
            span = max(1, right_level - left_level)
            ratio = (level - left_level) / span
            low = int(round(left_low + (right_low - left_low) * ratio))
            high = int(round(left_high + (right_high - left_high) * ratio))
            return min(low, high), max(low, high)
    _, last_low, last_high = table[-1]
    return last_low, last_high


def _effect_percent(effect: dict[str, Any]) -> int:
    if "value" in effect:
        value = _safe_int(effect.get("value"), 0)
        if value:
            return value
    amount = effect.get("amount")
    if isinstance(amount, (int, float)):
        if amount <= 1:
            return int(round(float(amount) * 100))
        return int(round(float(amount)))
    try:
        text = str(amount or "").strip().replace("%", "")
        if not text:
            return 0
        number = float(text)
        return int(round(number * 100 if number <= 1 else number))
    except Exception:
        return 0


def _safe_int(value: Any, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except Exception:
        return fallback


def _rng(*parts: Any) -> random.Random:
    seed = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    return random.Random(int(digest[:16], 16))
