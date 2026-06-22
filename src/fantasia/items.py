from __future__ import annotations

import hashlib
import json
import random
import re
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from .i18n import ELEMENT_IDS, tr_enum
from .status_effects import (
    STATUS_IMMUNITY_EFFECT_IDS,
    canonical_status_effect_id,
    status_effect_label,
)
from .paths import ITEM_TEMPLATE_DIR, ROOT


RARITY_ORDER = ("common", "uncommon", "rare", "epic", "legendary", "artifact")
RARITY_LABELS = {
    "common": "コモン",
    "uncommon": "アンコモン",
    "rare": "レア",
    "epic": "エピック",
    "legendary": "レジェンダリー",
    "artifact": "アーティファクト",
}
RARITY_COLORS = {
    "common": "white",
    "uncommon": "green",
    "rare": "blue",
    "epic": "purple",
    "legendary": "orange",
    "artifact": "red",
}
RARITY_TEXT_COLORS = {
    "common": "#f2f2f2",
    "uncommon": "#62d96b",
    "rare": "#5aa7ff",
    "epic": "#c17dff",
    "legendary": "#ffa33a",
    "artifact": "#ff5555",
}
RARITY_VALUE_MULTIPLIER = {
    "common": 1.0,
    "uncommon": 1.2,
    "rare": 1.5,
    "epic": 2.0,
    "legendary": 3.0,
    "artifact": 5.0,
}
RARITY_POWER_MULTIPLIER = {
    "common": 1.0,
    "uncommon": 1.2,
    "rare": 1.5,
    "epic": 2.0,
    "legendary": 2.5,
    "artifact": 3.0,
}
ITEM_USE_EFFECTS = {
    "None",
    "HP_Heal",
    "SP_Heal",
    "SP_Damage",
    "HP_Damage",
    "Hunger_Heal",
    "Send_LLM",
}
ITEM_VALUE_VARIANCE_MIN = 0.95
ITEM_VALUE_VARIANCE_MAX = 1.05
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
RARITY_POWER = {
    "common": 1,
    "uncommon": 2,
    "rare": 4,
    "epic": 7,
    "legendary": 11,
    "artifact": 16,
}

# Active item catalog. Old category ids are intentionally not accepted here.
ITEM_CATEGORY_IDS: tuple[str, ...] = (
    "food",
    "drink",
    "medicine",
    "potion",
    "tool",
    "document",
    "scroll",
    "magicrod",
    "material_common",
    "material_liquid",
    "material_plant",
    "material_ore",
    "material_metal",
    "material_gem",
    "material_creature",
    "material_magical",
    "junk",
    "treasure",
    "relic",
    "weapon_small",
    "weapon_medium",
    "weapon_large",
    "weapon_long",
    "weapon_range",
    "armor_shield",
    "armor_head",
    "armor_body",
    "armor_arm",
    "armor_leg",
    "armor_cloth",
    "accessory_ring",
    "accessory_amulet",
)

FANTASIA_ITEM_CATEGORY_COUNTS = {category: 3 for category in ITEM_CATEGORY_IDS}

CATEGORY_LABELS = {
    "food": "食料",
    "drink": "飲料",
    "medicine": "薬",
    "potion": "ポーション",
    "tool": "道具",
    "document": "文書",
    "scroll": "巻物",
    "magicrod": "魔法杖",
    "material_common": "汎用素材",
    "material_liquid": "液体素材",
    "material_plant": "自然素材",
    "material_ore": "鉱石素材",
    "material_metal": "金属素材",
    "material_gem": "宝石素材",
    "material_creature": "生物素材",
    "material_magical": "魔法素材",
    "junk": "ジャンク",
    "treasure": "宝物",
    "relic": "レリック",
    "weapon_small": "小型武器",
    "weapon_medium": "中型武器",
    "weapon_large": "大型武器",
    "weapon_long": "長武器",
    "weapon_range": "遠距離武器",
    "armor_shield": "盾",
    "armor_head": "頭防具",
    "armor_body": "胴防具",
    "armor_arm": "腕防具",
    "armor_leg": "脚防具",
    "armor_cloth": "服",
    "accessory_ring": "指輪",
    "accessory_amulet": "護符",
}

EQUIPMENT_CATEGORIES = {
    "weapon_small",
    "weapon_medium",
    "weapon_large",
    "weapon_long",
    "weapon_range",
    "armor_shield",
    "armor_head",
    "armor_body",
    "armor_arm",
    "armor_leg",
    "armor_cloth",
    "accessory_ring",
    "accessory_amulet",
}

WEAPON_CATEGORIES = {
    "weapon_small",
    "weapon_medium",
    "weapon_large",
    "weapon_long",
    "weapon_range",
}

EQUIPMENT_SLOTS = (
    "weapon",
    "armor_shield",
    "armor_head",
    "armor_body",
    "armor_arm",
    "armor_leg",
    "armor_cloth",
    "accessory_ring",
    "accessory_amulet",
)

EQUIPMENT_SLOT_LABELS = {
    "weapon": "武器",
    "armor_shield": "盾",
    "armor_head": "頭防具",
    "armor_body": "胴防具",
    "armor_arm": "腕防具",
    "armor_leg": "脚防具",
    "armor_cloth": "服",
    "accessory_ring": "指輪",
    "accessory_amulet": "護符",
}

ARMOR_SLOT_BY_CATEGORY = {
    "armor_shield": "armor_shield",
    "armor_head": "armor_head",
    "armor_body": "armor_body",
    "armor_arm": "armor_arm",
    "armor_leg": "armor_leg",
    "armor_cloth": "armor_cloth",
    "accessory_ring": "accessory_ring",
    "accessory_amulet": "accessory_amulet",
}

CATEGORY_BASE_VALUE = {
    "food": 5,
    "drink": 4,
    "medicine": 18,
    "potion": 30,
    "tool": 12,
    "document": 10,
    "scroll": 38,
    "magicrod": 55,
    "material_common": 5,
    "material_liquid": 12,
    "material_plant": 6,
    "material_ore": 10,
    "material_metal": 16,
    "material_gem": 45,
    "material_creature": 10,
    "material_magical": 24,
    "junk": 2,
    "treasure": 45,
    "relic": 90,
    "weapon_small": 30,
    "weapon_medium": 45,
    "weapon_large": 70,
    "weapon_long": 55,
    "weapon_range": 50,
    "armor_shield": 35,
    "armor_head": 25,
    "armor_body": 60,
    "armor_arm": 25,
    "armor_leg": 35,
    "armor_cloth": 18,
    "accessory_ring": 35,
    "accessory_amulet": 35,
}

ITEM_TEMPLATE_LOAD_ERRORS: list[str] = []


def _template_dirs() -> list[Path]:
    candidates = [ITEM_TEMPLATE_DIR, ROOT / "Data" / "Template" / "Item"]
    result: list[Path] = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def _template_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _template_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in ITEM_CATEGORY_IDS else ""


def _template_use_effect(value: Any) -> str:
    text = str(value or "None").strip()
    if not text:
        return "None"
    lowered = text.lower()
    for effect in ITEM_USE_EFFECTS:
        if lowered == effect.lower():
            return effect
    return "None"


def _normalise_item_template(raw: Any, source_path: Path) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    category = _template_category(raw.get("category"))
    name = str(raw.get("name") or "").strip()
    if not category or not name:
        return None
    value = _template_int(raw.get("value"), CATEGORY_BASE_VALUE.get(category, 5))
    level = max(0, _template_int(raw.get("level"), 0))
    power = max(0, _template_int(raw.get("power"), 0))
    desc = str(raw.get("desc") or raw.get("description") or "").strip()
    return {
        "name": name,
        "category": category,
        "level": level,
        "value": max(0, value),
        "desc": desc,
        "description": desc,
        "use_effect": _template_use_effect(raw.get("use_effect")),
        "power": power,
        "send_llm": str(raw.get("send_llm") or "").strip(),
        "element": str(raw.get("element") or "").strip(),
        "source_path": str(source_path),
    }


def _load_item_templates() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = {category: [] for category in ITEM_CATEGORY_IDS}
    ITEM_TEMPLATE_LOAD_ERRORS.clear()
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for template_path in sorted(directory.glob("*.json")):
            try:
                raw_items = json.loads(template_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                ITEM_TEMPLATE_LOAD_ERRORS.append(f"{template_path}: {exc}")
                continue
            if not isinstance(raw_items, list):
                ITEM_TEMPLATE_LOAD_ERRORS.append(f"{template_path}: root must be a JSON array")
                continue
            for raw in raw_items:
                template = _normalise_item_template(raw, template_path)
                if template is None:
                    continue
                loaded.setdefault(str(template["category"]), []).append(template)
    return {category: values for category, values in loaded.items() if values}


ITEM_TEMPLATES = _load_item_templates()

LOOT_PROFILES = {
    "settlement": [("food", 4), ("drink", 2), ("tool", 3), ("junk", 4), ("document", 2), ("treasure", 1)],
    "wilderness": [("material_plant", 5), ("material_creature", 2), ("food", 2), ("drink", 1), ("material_common", 2), ("junk", 1), ("material_ore", 1)],
    "dungeon": [("junk", 4), ("treasure", 2), ("relic", 1), ("potion", 2), ("scroll", 1), ("material_creature", 2), ("material_magical", 1)],
    "battlefield": [("weapon_small", 2), ("weapon_medium", 2), ("armor_shield", 1), ("junk", 3), ("medicine", 1), ("armor_body", 1), ("material_metal", 1)],
    "market": [("food", 3), ("drink", 2), ("tool", 3), ("armor_cloth", 2), ("treasure", 1), ("medicine", 1), ("document", 1)],
    "default": [("food", 2), ("tool", 2), ("junk", 3), ("material_plant", 2), ("treasure", 1), ("medicine", 1), ("material_common", 1)],
}

VENDOR_PROFILES = {
    "healer": [("medicine", 5), ("potion", 4), ("material_plant", 3), ("material_liquid", 2), ("scroll", 1)],
    "apothecary": [("medicine", 5), ("potion", 5), ("material_plant", 4), ("material_liquid", 2)],
    "blacksmith": [
        ("weapon_small", 2),
        ("weapon_medium", 4),
        ("weapon_large", 2),
        ("weapon_long", 3),
        ("weapon_range", 1),
        ("armor_shield", 2),
        ("armor_body", 2),
        ("armor_head", 1),
        ("armor_arm", 1),
        ("armor_leg", 1),
    ],
    "black_market": [
        ("weapon_small", 2),
        ("weapon_medium", 4),
        ("weapon_large", 2),
        ("weapon_long", 3),
        ("weapon_range", 2),
        ("armor_shield", 2),
        ("armor_body", 2),
        ("armor_head", 2),
        ("armor_arm", 1),
        ("armor_leg", 1),
        ("armor_cloth", 1),
        ("accessory_ring", 2),
        ("accessory_amulet", 2),
        ("relic", 1),
    ],
    "food_store": [("food", 6), ("drink", 4), ("material_plant", 1)],
    "material_store": [
        ("material_common", 4),
        ("material_ore", 3),
        ("material_metal", 3),
        ("material_plant", 2),
        ("material_creature", 2),
        ("material_liquid", 2),
        ("material_magical", 1),
        ("material_gem", 1),
        ("junk", 2),
    ],
    "mage": [("scroll", 4), ("magicrod", 2), ("potion", 2), ("material_magical", 4), ("material_gem", 2), ("relic", 1), ("document", 2), ("accessory_amulet", 1)],
    "magic_store": [("scroll", 5), ("magicrod", 2), ("material_magical", 4), ("potion", 2), ("material_gem", 2), ("relic", 1), ("document", 2), ("accessory_ring", 1), ("accessory_amulet", 1)],
    "inn": [("food", 5), ("drink", 4), ("medicine", 1), ("tool", 1)],
    "general_store": [("food", 3), ("drink", 2), ("tool", 4), ("medicine", 2), ("armor_cloth", 2), ("junk", 2), ("material_common", 2), ("document", 1)],
    "general": [("food", 3), ("drink", 2), ("tool", 4), ("medicine", 2), ("armor_cloth", 2), ("junk", 2)],
}

ITEM_CONTAINER_KEYS = {
    "item",
    "items",
    "item_add",
    "item_adds",
    "loot",
    "loot_items",
    "drop",
    "drops",
    "reward",
    "obtained_item",
    "obtained_items",
    "acquired_item",
    "acquired_items",
    "received_item",
    "received_items",
    "inventory_add",
    "inventory_additions",
    "inventory_changes",
    "treasure",
}

GOLD_KEYS = {
    "gold",
    "money",
    "coins",
    "coin",
    "reward_gold",
    "gold_reward",
    "obtained_gold",
    "acquired_gold",
    "received_gold",
}

GOLD_COST_CONTAINER_KEYS = {
    "payment",
    "payments",
    "cost",
    "costs",
    "price",
    "prices",
    "fee",
    "fees",
    "expense",
    "expenses",
    "pay",
    "spend",
    "spent",
}


def starter_items() -> list[dict[str, Any]]:
    return [
        make_item("food", name="黒パン", quantity=2, source="starter"),
        make_item("medicine", name="止血薬", quantity=1, source="starter"),
        make_item("tool", name="ロープ", quantity=1, source="starter"),
    ]


def generate_loot_items(location_name: str, context: str = "", count: int | None = None, danger_level: int = 0) -> list[dict[str, Any]]:
    profile_name = _loot_profile_name(f"{location_name} {context}")
    profile = LOOT_PROFILES[profile_name]
    rng = _rng("loot", location_name, context, profile_name)
    item_count = count if count is not None else rng.randint(2, 4)
    return [
        _random_item(profile, rng, source="loot", context=location_name, danger_level=danger_level)
        for _ in range(max(1, item_count))
    ]


def generate_vendor_items(owner_name: str, context: str = "", count: int | None = None, danger_level: int = 0) -> list[dict[str, Any]]:
    profile_name = _vendor_profile_name(f"{owner_name} {context}")
    profile = VENDOR_PROFILES.get(profile_name, VENDOR_PROFILES["general"])
    rng = _rng("vendor", owner_name, context, profile_name)
    item_count = count if count is not None else rng.randint(5, 8)
    return [
        _random_item(profile, rng, source="vendor", context=owner_name, rarity_profile=profile_name, danger_level=danger_level)
        for _ in range(max(1, item_count))
    ]


def generate_reward_item(category: str, context: str = "", danger_level: int = 0, seed: str = "") -> dict[str, Any]:
    category_id = normalise_category(category)
    rng = _rng("quest_reward", category_id, context, str(danger_level), seed)
    return _random_item([(category_id, 1)], rng, source="quest_reward", context=context, danger_level=danger_level)


def make_item(
    category: str,
    *,
    name: str | None = None,
    description: str | None = None,
    quantity: int = 1,
    value: int | None = None,
    rarity: str = "common",
    source: str = "",
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    category = normalise_category(category)
    rarity = normalise_rarity(rarity)
    cleaned_name = _clean_item_name(name, "")
    template = _template_for(category, cleaned_name or None)
    item_name = cleaned_name or str(template.get("name") or CATEGORY_LABELS.get(category, category))
    template_description = str(template.get("desc") or template.get("description") or "")
    template_value = _safe_int(template.get("value"), CATEGORY_BASE_VALUE.get(category, 5))
    template_power = _template_power(template, rarity)
    explicit_value = value is not None
    item_value = int(value if value is not None else template_value)
    if not explicit_value:
        price_rng = _rng("item_price", category, item_name, rarity, source)
        item_value = _item_value_with_rarity(item_value, rarity, price_rng)
    qty = max(1, int(quantity or 1))
    stackable = category not in EQUIPMENT_CATEGORIES
    item = {
        "name": item_name,
        "category": category,
        "category_label": tr_enum("item_category", category, fallback=CATEGORY_LABELS.get(category, category)),
        "quantity": qty,
        "value": max(0, item_value),
        "rarity": rarity,
        "rarity_label": tr_enum("rarity", rarity, fallback=RARITY_LABELS.get(rarity, rarity)),
        "rarity_color": RARITY_COLORS.get(rarity, "white"),
        "description": str(description or template_description),
        "source": source,
        "template_id": f"{category}:{item_name}",
        "template_source": str(template.get("source_path") or ""),
        "level": max(0, _safe_int(template.get("level"), 0)),
        "use_effect": _template_use_effect(template.get("use_effect")),
        "power": template_power,
        "send_llm": str(template.get("send_llm") or ""),
        "element": str(template.get("element") or ""),
        "stackable": stackable,
        "tradable": True,
        "icon_hint": _icon_hint(category, item_name),
    }
    _ensure_item_uuids(item)
    if category in EQUIPMENT_CATEGORIES:
        item["equipment_slot"] = equipment_slot_for_category(category)
        item["instance_id"] = _new_item_instance_id(category, item_name)
        item["attack"] = template_power if category in WEAPON_CATEGORIES and template_power > 0 else _base_equipment_attack(category, rarity)
        item["defense"] = template_power if category not in WEAPON_CATEGORIES and template_power > 0 else _base_equipment_defense(category, rarity)
        item["effects"] = deepcopy(effects) if effects is not None else _equipment_effects(category, rarity, item_name)
        item["llm_effects"] = _equipment_llm_effects(category, rarity, item_name)
    else:
        item["effects"] = deepcopy(effects) if effects is not None else _template_effects(template, rarity)
        if item["send_llm"] and not any(
            isinstance(effect, dict) and str(effect.get("type") or "").lower() == "send_llm"
            for effect in item["effects"]
        ):
            item["effects"].append({"type": "send_llm", "text": item["send_llm"]})
    return item


def normalise_item(raw: Any, source: str = "", fallback_category: str = "junk") -> dict[str, Any]:
    if isinstance(raw, str):
        return make_item(fallback_category, name=_clean_item_name(raw, ""), source=source)
    if not isinstance(raw, dict):
        return make_item(fallback_category, name=_clean_item_name(raw, ""), source=source)

    data = dict(raw)
    category = normalise_category(
        str(
            data.get("category")
            or data.get("type")
            or data.get("kind")
            or data.get("group")
            or fallback_category
        )
    )
    name = _clean_item_name(data.get("name") or data.get("item_name") or data.get("title") or data.get("label"), "")
    if not name:
        name = CATEGORY_LABELS.get(category, "アイテム")
    quantity = _safe_int(data.get("quantity", data.get("count", data.get("amount", 1))), 1)
    explicit_value = any(key in data for key in ("value", "price", "gold_value"))
    value = _safe_int(data.get("value", data.get("price", data.get("gold_value", CATEGORY_BASE_VALUE.get(category, 5)))), CATEGORY_BASE_VALUE.get(category, 5))
    description = str(data.get("description") or data.get("overview") or data.get("summary") or "")
    rarity = normalise_rarity(data.get("rarity") or "common")
    raw_effects = data.get("effects") if isinstance(data.get("effects"), list) else data.get("equipment_effects")
    effects = raw_effects if isinstance(raw_effects, list) else None
    item = make_item(
        category,
        name=name,
        description=description or None,
        quantity=quantity,
        value=value if explicit_value else None,
        rarity=rarity,
        source=str(data.get("source") or source),
        effects=effects,
    )
    for key, value in data.items():
        if key not in item and not str(key).startswith("_"):
            item[str(key)] = value
    for key in (
        "instance_id",
        "equipped",
        "equipment_slot",
        "attack",
        "defense",
        "effects",
        "llm_effects",
        "item_uuid",
        "item_uuids",
        "level",
        "use_effect",
        "power",
        "send_llm",
        "element",
        "template_source",
        "_craft_source",
        "_craft_source_uuid",
    ):
        if key in data:
            item[key] = deepcopy(data[key])
    if "uuid" in data and not item.get("item_uuid"):
        item["item_uuid"] = str(data.get("uuid") or "")
    item["quantity"] = max(1, _safe_int(item.get("quantity", 1), 1))
    item["value"] = max(0, _safe_int(item.get("value", 0), 0))
    item["stackable"] = bool(item.get("stackable", category not in EQUIPMENT_CATEGORIES))
    item["tradable"] = bool(item.get("tradable", True))
    item["category_label"] = tr_enum("item_category", category, fallback=CATEGORY_LABELS.get(category, category))
    item["rarity"] = normalise_rarity(item.get("rarity") or rarity)
    item["rarity_label"] = tr_enum("rarity", str(item.get("rarity")), fallback=RARITY_LABELS.get(str(item.get("rarity")), str(item.get("rarity"))))
    item["rarity_color"] = RARITY_COLORS.get(str(item.get("rarity")), "white")
    item["use_effect"] = _template_use_effect(item.get("use_effect"))
    item["power"] = max(0, _safe_int(item.get("power"), 0))
    item["send_llm"] = str(item.get("send_llm") or "")
    item["element"] = str(item.get("element") or "")
    if category not in EQUIPMENT_CATEGORIES and effects is None and any(key in data for key in ("use_effect", "power", "send_llm")):
        item["effects"] = _template_effects(item, str(item.get("rarity")))
        if item["send_llm"] and not any(
            isinstance(effect, dict) and str(effect.get("type") or "").lower() == "send_llm"
            for effect in item["effects"]
        ):
            item["effects"].append({"type": "send_llm", "text": item["send_llm"]})
    if category in EQUIPMENT_CATEGORIES:
        item["equipment_slot"] = equipment_slot_for_category(category) or str(item.get("equipment_slot") or "")
        item["instance_id"] = str(item.get("instance_id") or _new_item_instance_id(category, name))
        template_power = max(0, _safe_int(item.get("power"), 0))
        default_attack = template_power if category in WEAPON_CATEGORIES and template_power > 0 else _base_equipment_attack(category, str(item.get("rarity")))
        default_defense = template_power if category not in WEAPON_CATEGORIES and template_power > 0 else _base_equipment_defense(category, str(item.get("rarity")))
        item["attack"] = _safe_int(item.get("attack"), default_attack) if "attack" in data else default_attack
        item["defense"] = _safe_int(item.get("defense"), default_defense) if "defense" in data else default_defense
        if not isinstance(item.get("llm_effects"), list):
            item["llm_effects"] = _equipment_llm_effects(category, str(item.get("rarity")), name)
    _ensure_item_uuids(item)
    return item


def normalise_inventory(inventory: list[dict[str, Any]], source: str = "") -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for raw in list(inventory):
        if isinstance(raw, dict):
            add_item_stack(compacted, raw, source=source)
        elif raw is not None:
            add_item_stack(compacted, normalise_item(raw, source=source), source=source)
    inventory[:] = compacted
    return inventory


def inventory_slot_count(inventory: list[dict[str, Any]]) -> int:
    return len(inventory)


def inventory_free_slots(inventory: list[dict[str, Any]], max_slots: int) -> int:
    return max(0, int(max_slots) - inventory_slot_count(inventory))


def can_add_item_stack(
    inventory: list[dict[str, Any]],
    raw: Any,
    *,
    max_slots: int | None = None,
    source: str = "",
    quantity: int | None = None,
) -> bool:
    if max_slots is None:
        return True
    item = normalise_item(raw, source=source)
    if quantity is not None:
        item["quantity"] = max(1, int(quantity))
        _ensure_item_uuids(item)
    key = _stack_key(item)
    if key:
        for existing in inventory:
            existing_item = normalise_item(existing, source=source)
            if _stack_key(existing_item) == key:
                return True
    return inventory_slot_count(inventory) < max(0, int(max_slots))


def add_item_stack(
    inventory: list[dict[str, Any]],
    raw: Any,
    source: str = "",
    quantity: int | None = None,
    max_slots: int | None = None,
) -> dict[str, Any] | None:
    if not can_add_item_stack(inventory, raw, max_slots=max_slots, source=source, quantity=quantity):
        return None
    item = normalise_item(raw, source=source)
    if quantity is not None:
        item["quantity"] = max(1, int(quantity))
        _ensure_item_uuids(item)
    key = _stack_key(item)
    if key:
        for existing in inventory:
            existing_item = normalise_item(existing, source=source)
            if _stack_key(existing_item) == key:
                existing.clear()
                existing.update(existing_item)
                existing_quantity = _safe_int(existing.get("quantity", 1), 1)
                item_quantity = _safe_int(item.get("quantity", 1), 1)
                existing["quantity"] = existing_quantity + item_quantity
                existing["item_uuids"] = _item_uuid_list(existing_item)[:existing_quantity] + _item_uuid_list(item)[:item_quantity]
                existing["item_uuid"] = existing["item_uuids"][0] if existing["item_uuids"] else _new_item_uuid()
                return deepcopy(item)
    inventory.append(item)
    return deepcopy(item)


def take_item_stack(inventory: list[dict[str, Any]], index: int, quantity: int = 1) -> dict[str, Any] | None:
    if index < 0 or index >= len(inventory):
        return None
    item = normalise_item(inventory[index])
    available = max(1, _safe_int(item.get("quantity", 1), 1))
    take_quantity = min(max(1, int(quantity)), available)
    taken = deepcopy(item)
    taken["quantity"] = take_quantity
    uuids = _item_uuid_list(item)
    taken["item_uuids"] = uuids[:take_quantity]
    taken["item_uuid"] = taken["item_uuids"][0] if taken["item_uuids"] else _new_item_uuid()
    if available > take_quantity:
        item["quantity"] = available - take_quantity
        item["item_uuids"] = uuids[take_quantity:available]
        item["item_uuid"] = item["item_uuids"][0] if item["item_uuids"] else _new_item_uuid()
        inventory[index] = item
    else:
        inventory.pop(index)
    return taken


def transfer_item_stack(
    source_inventory: list[dict[str, Any]],
    target_inventory: list[dict[str, Any]],
    index: int,
    quantity: int = 1,
    source: str = "",
    max_target_slots: int | None = None,
) -> dict[str, Any] | None:
    if index < 0 or index >= len(source_inventory):
        return None
    candidate = normalise_item(source_inventory[index])
    candidate["quantity"] = min(max(1, int(quantity)), max(1, _safe_int(candidate.get("quantity", 1), 1)))
    if not can_add_item_stack(target_inventory, candidate, max_slots=max_target_slots, source=source):
        return None
    taken = take_item_stack(source_inventory, index, quantity)
    if not taken:
        return None
    added = add_item_stack(target_inventory, taken, source=source, max_slots=max_target_slots)
    if not added:
        add_item_stack(source_inventory, taken, source=source)
        return None
    return added


def item_value(item: dict[str, Any]) -> int:
    return max(0, _safe_int(item.get("value", 0), 0))


def item_hp_delta(item: dict[str, Any]) -> int:
    total = 0
    normalised = normalise_item(item)
    effects = normalised.get("effects")
    if isinstance(effects, list):
        for effect in effects:
            total += _effect_hp_delta(effect)
    for key in ("hp_delta", "player_hp_delta", "heal_hp", "restore_hp", "recover_hp", "healing"):
        if key in normalised:
            value = _safe_int(normalised.get(key), 0)
            total += abs(value) if key != "hp_delta" and key != "player_hp_delta" else value
    return total


def item_sp_delta(item: dict[str, Any]) -> int:
    total = 0
    normalised = normalise_item(item)
    effects = normalised.get("effects")
    if isinstance(effects, list):
        for effect in effects:
            total += _effect_sp_delta(effect)
    for key in ("sp_delta", "player_sp_delta", "restore_sp", "recover_sp", "sp_restore", "sp_recovery"):
        if key in normalised:
            value = _safe_int(normalised.get(key), 0)
            total += abs(value) if key not in {"sp_delta", "player_sp_delta"} else value
    return total


def item_hunger_delta(item: dict[str, Any]) -> int:
    total = 0
    normalised = normalise_item(item)
    effects = normalised.get("effects")
    if isinstance(effects, list):
        for effect in effects:
            total += _effect_hunger_delta(effect)
    for key in ("hunger_delta", "player_hunger_delta", "restore_hunger", "recover_hunger", "hunger_restore"):
        if key in normalised:
            value = _safe_int(normalised.get(key), 0)
            total += abs(value) if key not in {"hunger_delta", "player_hunger_delta"} else value
    return total


def sell_value(item: dict[str, Any]) -> int:
    return max(1, item_value(item) // 2)


def item_rarity_color(item: dict[str, Any]) -> str:
    normalised = normalise_item(item)
    return RARITY_TEXT_COLORS.get(str(normalised.get("rarity") or "common"), "#f2f2f2")


def item_label(item: dict[str, Any], price_mode: str = "", language: str = "ja") -> str:
    normalised = normalise_item(item)
    name = str(normalised.get("name") or tr_enum("roster", "unknown", language))
    quantity = max(1, _safe_int(normalised.get("quantity", 1), 1))
    category_id = str(normalised.get("category") or "junk")
    rarity_id = normalise_rarity(normalised.get("rarity"))
    category = tr_enum("item_category", category_id, language, fallback=str(normalised.get("category_label") or category_id))
    rarity = tr_enum("rarity", rarity_id, language, fallback=str(normalised.get("rarity_label") or rarity_id))
    equipped = bool(normalised.get("equipped"))
    prefix = tr_enum("item_marker", "equipped", language) if equipped else ""
    qty = f" x{quantity}" if quantity > 1 else ""
    label = f"{prefix}{name}{qty} [{category}]"
    if rarity and rarity_id != "common":
        label += f" {rarity}"
    return label


def use_inventory_item(inventory: list[dict[str, Any]], index: int, language: str = "ja") -> tuple[dict[str, Any] | None, str]:
    if index < 0 or index >= len(inventory):
        return None, ""
    item = normalise_item(inventory[index])
    unknown = tr_enum("roster", "unknown", language)
    category = str(item.get("category") or "")
    if category in EQUIPMENT_CATEGORIES:
        return None, f"{item.get('name') or unknown} は装備ボタンで装備してください。"
    effects = item.get("effects") if isinstance(item.get("effects"), list) else []
    usable = category in {"food", "drink", "medicine", "potion", "scroll"} or bool(effects)
    if not usable:
        return None, f"{item.get('name') or unknown} は今は使えません。"
    used = take_item_stack(inventory, index, 1)
    if not used:
        return None, ""
    effect_text = _effect_text(used)
    return used, f"{used.get('name') or unknown} を使った。{effect_text}".strip()


def craft_items(
    ingredients: list[dict[str, Any]],
    language: str = "ja",
    craft_roll: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    items = [normalise_item(item) for item in ingredients if isinstance(item, dict)]
    if len(items) < 2:
        return None, "素材を2つ以上選んでください。"
    if isinstance(craft_roll, dict) and craft_roll.get("critical_failure"):
        return None, "クラフトに失敗しました。素材は失われました。"
    equipment = [item for item in items if is_equipment_item(item)]
    total_value = sum(item_value(item) * max(1, _safe_int(item.get("quantity", 1), 1)) for item in items)
    highest_rarity = _highest_rarity(items)
    unknown = tr_enum("roster", "unknown", language)
    ingredient_names = "、".join(str(item.get("name") or unknown) for item in items[:4])
    ingredient_uuids = _collect_item_uuids(items)
    quality_steps = _craft_roll_quality_steps(craft_roll, equipment=bool(equipment))
    stat_bonus = _craft_roll_stat_bonus(craft_roll)
    quality_message = _craft_quality_message(craft_roll)

    if equipment:
        base = equipment[0]
        category = str(base.get("category") or "weapon_medium")
        base_rarity = max(str(base.get("rarity") or "common"), highest_rarity, key=_rarity_rank)
        rarity = _upgrade_rarity(base_rarity, quality_steps)
        base_name = str(base.get("name") or "装備")
        result = make_item(
            category,
            name=f"強化された{base_name}",
            description=f"{ingredient_names}を用いて強化された装備。",
            quantity=1,
            value=max(1, int(total_value * (1.2 + max(0, quality_steps) * 0.15) * RARITY_VALUE_MULTIPLIER.get(rarity, 1.0))),
            rarity=rarity,
            source="craft",
        )
        material_bonus = max(1, len(items) - 1) + stat_bonus
        result["attack"] = max(_safe_int(result.get("attack"), 0), _safe_int(base.get("attack"), 0))
        result["defense"] = max(_safe_int(result.get("defense"), 0), _safe_int(base.get("defense"), 0))
        if category in WEAPON_CATEGORIES:
            result["attack"] = _safe_int(result.get("attack"), 0) + material_bonus
        else:
            result["defense"] = _safe_int(result.get("defense"), 0) + material_bonus
        base_effects = deepcopy(base.get("effects")) if isinstance(base.get("effects"), list) else []
        result_effects = deepcopy(result.get("effects")) if isinstance(result.get("effects"), list) else []
        if isinstance(craft_roll, dict) and craft_roll.get("critical_success"):
            result_effects.extend(_equipment_effects(category, rarity, f"{base_name}:critical"))
        result["effects"] = _dedupe_effects(base_effects + result_effects)[:8]
        base_llm = deepcopy(base.get("llm_effects")) if isinstance(base.get("llm_effects"), list) else []
        result_llm = deepcopy(result.get("llm_effects")) if isinstance(result.get("llm_effects"), list) else []
        if isinstance(craft_roll, dict) and craft_roll.get("critical_success"):
            result_llm.extend(_equipment_llm_effects(category, rarity, f"{base_name}:critical"))
        result["llm_effects"] = _dedupe_effects(base_llm + result_llm)[:4]
        result["craft_ingredients"] = ingredient_uuids
        if isinstance(craft_roll, dict):
            result["craft_roll"] = dict(craft_roll)
        return result, f"{result.get('name')} を作成しました。{quality_message}".strip()

    category = _crafted_consumable_category(items)
    rarity = _upgrade_rarity(highest_rarity, quality_steps)
    result = make_item(
        category,
        name="合成品",
        description=f"{ingredient_names}を組み合わせて作られた品。",
        quantity=1,
        value=max(1, int(total_value * (1.1 + max(0, quality_steps) * 0.12) * RARITY_VALUE_MULTIPLIER.get(rarity, 1.0))),
        rarity=rarity,
        source="craft",
    )
    if stat_bonus and isinstance(result.get("effects"), list):
        for effect in result["effects"]:
            if isinstance(effect, dict) and isinstance(effect.get("value"), int):
                effect["value"] = max(1, int(effect.get("value", 0)) + stat_bonus * 2)
    result["craft_ingredients"] = ingredient_uuids
    if isinstance(craft_roll, dict):
        result["craft_roll"] = dict(craft_roll)
    return result, f"{result.get('name')} を作成しました。{quality_message}".strip()


def extract_response_rewards(payload: Any, source: str = "") -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    gold = 0

    def visit(value: Any, key: str = "", depth: int = 0, in_item_container: bool = False) -> None:
        nonlocal gold
        if depth > 6:
            return
        key_l = key.lower()
        if key_l in GOLD_COST_CONTAINER_KEYS:
            return
        if key_l in GOLD_KEYS:
            gold += _gold_amount(value)
            return

        container = in_item_container or key_l in ITEM_CONTAINER_KEYS
        if isinstance(value, dict):
            if container and _looks_like_item(value):
                items.append(normalise_item(value, source=source, fallback_category=_category_from_key(key_l)))
                return
            for child_key, child_value in value.items():
                child_key_l = str(child_key).lower()
                if child_key_l in GOLD_KEYS:
                    gold += _gold_amount(child_value)
                    continue
                visit(child_value, child_key_l, depth + 1, container or child_key_l in ITEM_CONTAINER_KEYS)
            return

        if isinstance(value, list):
            for child in value:
                if container and _looks_like_item(child):
                    items.append(normalise_item(child, source=source, fallback_category=_category_from_key(key_l)))
                else:
                    visit(child, key_l, depth + 1, container)
            return

        if container and isinstance(value, str):
            amount = _gold_amount(value)
            if amount:
                gold += amount
            elif value.strip():
                items.append(normalise_item(value, source=source, fallback_category=_category_from_key(key_l)))

    visit(payload)
    return items, gold


def reward_log_lines(items: list[dict[str, Any]], gold: int = 0) -> list[str]:
    lines = []
    for item in items:
        lines.append(f"> [入手] {item_label(item)}")
    if gold:
        lines.append(f"> [入手] {gold}G")
    return lines


def normalise_category(category: str) -> str:
    value = str(category or "").strip().lower().replace("-", "_").replace(" ", "_")
    return value if value in FANTASIA_ITEM_CATEGORY_COUNTS else "junk"


def category_label(category: str, language: str = "ja") -> str:
    normalised = normalise_category(category)
    return tr_enum("item_category", normalised, language, fallback=CATEGORY_LABELS.get(normalised, category))


def normalise_rarity(value: Any) -> str:
    text = str(value or "common").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "コモン": "common",
        "白": "common",
        "アンコモン": "uncommon",
        "緑": "uncommon",
        "レア": "rare",
        "青": "rare",
        "エピック": "epic",
        "紫": "epic",
        "レジェンダリー": "legendary",
        "orange": "legendary",
        "オレンジ": "legendary",
        "アーティファクト": "artifact",
        "赤": "artifact",
    }
    text = aliases.get(text, text)
    return text if text in RARITY_ORDER else "common"


def equipment_slot_for_category(category: str) -> str:
    normalised = normalise_category(category)
    if normalised in WEAPON_CATEGORIES:
        return "weapon"
    return ARMOR_SLOT_BY_CATEGORY.get(normalised, "")


def is_equipment_item(item: dict[str, Any]) -> bool:
    return equipment_slot_for_category(str(item.get("category") or "")) in EQUIPMENT_SLOTS


def calculate_equipment_summary(equipment: dict[str, Any] | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "attack": 0,
        "defense": 0,
        "max_hp": 0,
        "max_sp": 0,
        "hp_regen": 0,
        "sp_regen": 0,
        "attributes": {"str": 0, "dex": 0, "con": 0, "int": 0, "wis": 0, "cha": 0},
        "status_immunities": [],
        "resistance": {},
        "element_resistances": {},
        "llm_effects": [],
        "items": [],
    }
    if not isinstance(equipment, dict):
        return summary
    immunities: list[str] = []
    llm_effects: list[Any] = []
    items: list[dict[str, Any]] = []
    for slot in EQUIPMENT_SLOTS:
        raw = equipment.get(slot)
        if not isinstance(raw, dict):
            continue
        item = normalise_item(raw)
        if not is_equipment_item(item):
            continue
        items.append(item)
        summary["attack"] += _safe_int(item.get("attack"), 0)
        summary["defense"] += _safe_int(item.get("defense"), 0)
        for effect in item.get("effects") if isinstance(item.get("effects"), list) else []:
            if not isinstance(effect, dict):
                continue
            effect_type = str(effect.get("type") or effect.get("stat") or effect.get("name") or "").strip().lower()
            value = _safe_int(effect.get("value", effect.get("amount", 0)), 0)
            if effect_type in {"attack", "atk", "attack_power"}:
                summary["attack"] += value
            elif effect_type in {"defense", "def", "defence"}:
                summary["defense"] += value
            elif effect_type in {"max_hp", "hp_max"}:
                summary["max_hp"] += value
            elif effect_type in {"max_sp", "max_mp", "sp_max", "mp_max"}:
                summary["max_sp"] += value
            elif effect_type in {"hp_regen", "auto_hp_regen", "hp_auto_recovery"}:
                summary["hp_regen"] += value
            elif effect_type in {"sp_regen", "mp_regen", "auto_sp_regen", "mp_auto_recovery"}:
                summary["sp_regen"] += value
            elif effect_type in summary["attributes"]:
                summary["attributes"][effect_type] += value
            elif effect_type in {"status_immunity", "immunity", "immune"}:
                immunity = str(effect.get("status") or effect.get("status_id") or effect.get("target") or effect.get("value") or "").strip()
                immunity_id = canonical_status_effect_id(immunity)
                if immunity_id in STATUS_IMMUNITY_EFFECT_IDS:
                    immunities.append(immunity_id)
            elif effect_type in {"element_resistance", "element_damage_reduction", "resist_element"}:
                element = str(effect.get("element") or effect.get("target") or effect.get("attribute") or "").strip()
                if element:
                    amount = max(0.0, min(1.0, _safe_float(effect.get("amount"), 0.0)))
                    resistances = summary["resistance"]
                    resistances[element] = max(_safe_float(resistances.get(element), 0.0), amount)
                    summary["element_resistances"] = dict(resistances)
        if isinstance(item.get("llm_effects"), list):
            llm_effects.extend(item.get("llm_effects") or [])
    summary["status_immunities"] = _dedupe_texts(immunities)
    summary["llm_effects"] = llm_effects[:10]
    summary["items"] = items
    return summary


def item_tooltip_text(item: dict[str, Any], price_mode: str = "", language: str = "ja") -> str:
    normalised = normalise_item(item)
    category_id = str(normalised.get("category") or "junk")
    rarity_id = normalise_rarity(normalised.get("rarity"))
    category = tr_enum("item_category", category_id, language, fallback=str(normalised.get("category_label") or category_id))
    rarity = tr_enum("rarity", rarity_id, language, fallback=str(normalised.get("rarity_label") or rarity_id))
    tip = lambda key: tr_enum("item_tooltip", key, language)
    lines = [
        str(normalised.get("name") or tr_enum("roster", "unknown", language)),
        f"{tip('category')}: {category}",
        f"{tip('rarity')}: {rarity}",
    ]
    value = item_value(normalised)
    if price_mode == "sell":
        lines.append(f"{tip('sell')}: {sell_value(normalised)}G")
    elif price_mode == "buy":
        lines.append(f"{tip('buy')}: {value}G")
    else:
        lines.append(f"{tip('value')}: {value}G")
    slot = equipment_slot_for_category(str(normalised.get("category") or ""))
    if slot:
        lines.append(f"{tip('slot')}: {tr_enum('equipment_slot', slot, language, fallback=EQUIPMENT_SLOT_LABELS.get(slot, slot))}")
        attack = _safe_int(normalised.get("attack"), 0)
        defense = _safe_int(normalised.get("defense"), 0)
        if attack:
            lines.append(f"{tip('attack')} +{attack}")
        if defense:
            lines.append(f"{tip('defense')} +{defense}")
        for effect in normalised.get("effects") if isinstance(normalised.get("effects"), list) else []:
            text = _equipment_effect_label(effect, language)
            if text:
                lines.append(text)
        llm_effects = normalised.get("llm_effects") if isinstance(normalised.get("llm_effects"), list) else []
        for effect in llm_effects:
            if isinstance(effect, dict):
                lines.append(f"{tip('special')}: {effect.get('name') or effect.get('effect')}")
            elif effect:
                lines.append(f"{tip('special')}: {effect}")
    description = str(normalised.get("description") or "").strip()
    if description:
        lines.extend(["", description])
    return "\n".join(str(line) for line in lines if str(line).strip())


def _clean_item_name(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    note_words = (
        "討伐",
        "入手",
        "獲得",
        "報酬",
        "戦利品",
        "ドロップ",
        "drop",
        "loot",
        "reward",
        "obtained",
        "acquired",
    )

    def replace_note(match: re.Match[str]) -> str:
        segment = match.group(0).lower()
        return "" if any(word.lower() in segment for word in note_words) else match.group(0)

    text = re.sub(r"[\(（\[\【][^\)）\]\】]{0,40}[\)）\]\】]", replace_note, text)
    text = re.sub(r"^[\s\"':：,，、。・\-~～|/\\]+|[\s\"':：,，、。・\-~～|/\\]+$", "", text)
    lowered = text.lower()
    invalid = {
        "",
        "none",
        "null",
        "unknown",
        "n/a",
        "討伐時入手",
        "入手",
        "獲得",
        "報酬",
        "戦利品",
        "ドロップ",
        "drop",
        "loot",
        "reward",
    }
    if lowered in invalid:
        return fallback
    if not any(ch.isalnum() for ch in text):
        return fallback
    return text


def _random_item(
    profile: list[tuple[str, int]],
    rng: random.Random,
    source: str,
    context: str,
    rarity_profile: str = "",
    danger_level: int = 0,
) -> dict[str, Any]:
    categories, weights = zip(*profile)
    category = rng.choices(categories, weights=weights, k=1)[0]
    template = rng.choice(_templates_for_category(category, danger_level=danger_level))
    name = str(template.get("name") or CATEGORY_LABELS.get(category, category))
    description = str(template.get("desc") or template.get("description") or "")
    base_value = _safe_int(template.get("value"), CATEGORY_BASE_VALUE.get(category, 5))
    if category in EQUIPMENT_CATEGORIES:
        rarity = _random_equipment_rarity(rng, rarity_profile)
    else:
        rarity = _random_stackable_rarity(rng, rarity_profile)
    item_value = _item_value_with_rarity(base_value, rarity, rng)
    quantity = _random_quantity(category, rng)
    return make_item(
        category,
        name=name,
        description=description,
        quantity=quantity,
        value=item_value,
        rarity=rarity,
        source=source,
    )


def _random_equipment_rarity(rng: random.Random, profile_name: str = "") -> str:
    if profile_name == "black_market":
        return rng.choices(["epic", "legendary", "artifact"], weights=[72, 24, 4], k=1)[0]
    if profile_name == "blacksmith":
        return rng.choices(["common", "uncommon", "rare", "epic", "legendary"], weights=[42, 34, 20, 3.5, 0.5], k=1)[0]
    if profile_name == "magic_store":
        return rng.choices(["uncommon", "rare", "epic", "legendary"], weights=[56, 32, 10, 2], k=1)[0]
    return rng.choices(list(RARITY_ORDER), weights=[65, 22, 8, 3.5, 1.2, 0.3], k=1)[0]


def _random_stackable_rarity(rng: random.Random, profile_name: str = "") -> str:
    if profile_name in {"magic_store", "material_store"}:
        return rng.choices(["common", "uncommon", "rare"], weights=[62, 30, 8], k=1)[0]
    return rng.choices(["common", "uncommon", "rare"], weights=[76, 20, 4], k=1)[0]


def _item_value_with_rarity(base_value: int, rarity: str, rng: random.Random | None = None) -> int:
    base = max(1, int(base_value or 1))
    rarity_key = normalise_rarity(rarity)
    multiplier = RARITY_VALUE_MULTIPLIER.get(rarity_key, 1.0)
    variance_rng = rng or random.Random()
    variance = variance_rng.uniform(ITEM_VALUE_VARIANCE_MIN, ITEM_VALUE_VARIANCE_MAX)
    rarity_floor = base + _rarity_rank(rarity_key)
    return max(1, rarity_floor, int(round(base * multiplier * variance)))


def _loot_profile_name(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("shop", "market", "store", "市", "店", "市場", "商")):
        return "market"
    if any(word in lowered for word in ("dungeon", "ruin", "cave", "地下", "遺跡", "洞窟", "迷宮")):
        return "dungeon"
    if any(word in lowered for word in ("battle", "war", "fort", "戦", "砦", "城壁")):
        return "battlefield"
    if any(word in lowered for word in ("forest", "field", "road", "森", "野", "街道", "山")):
        return "wilderness"
    if any(word in lowered for word in ("town", "inn", "settlement", "村", "町", "宿", "都市")):
        return "settlement"
    return "default"


def _vendor_profile_name(text: str) -> str:
    lowered = text.lower()
    if "facility_type:black_market" in lowered or any(word in lowered for word in ("black market", "black_market", "闇商店", "闇市", "裏市場")):
        return "black_market"
    if "facility_type:blacksmith" in lowered or any(word in lowered for word in ("blacksmith", "鍛冶", "武具", "武器", "防具")):
        return "blacksmith"
    if "facility_type:apothecary" in lowered or any(word in lowered for word in ("potion", "薬品", "薬屋", "薬草", "回復")):
        return "apothecary"
    if "facility_type:food_store" in lowered or any(word in lowered for word in ("food store", "grocery", "食料店", "食料", "食材")):
        return "food_store"
    if "facility_type:material_store" in lowered or any(word in lowered for word in ("material store", "素材店", "素材", "鉱石", "材料")):
        return "material_store"
    if "facility_type:magic_store" in lowered or any(word in lowered for word in ("scroll", "魔術店", "魔法店", "巻物")):
        return "magic_store"
    if "facility_type:general_store" in lowered or any(word in lowered for word in ("general store", "雑貨店", "よろず屋", "道具屋")):
        return "general_store"
    if any(word in lowered for word in ("heal", "doctor", "apothecary", "薬", "医", "治療", "聖職")):
        return "healer"
    if any(word in lowered for word in ("smith", "weapon", "armor", "鍛冶", "武器", "防具", "傭兵")):
        return "blacksmith"
    if any(word in lowered for word in ("mage", "magic", "scholar", "魔", "術", "学者", "書")):
        return "mage"
    if any(word in lowered for word in ("inn", "cook", "tavern", "宿", "酒場", "料理")):
        return "inn"
    return "general"


def _fallback_template(category: str, name: str | None = None) -> dict[str, Any]:
    return {
        "name": name or CATEGORY_LABELS.get(category, category),
        "category": category,
        "level": 0,
        "value": CATEGORY_BASE_VALUE.get(category, 5),
        "desc": "",
        "description": "",
        "use_effect": "None",
        "power": 0,
        "send_llm": "",
        "element": "",
        "source_path": "",
    }


def _templates_for_category(category: str, danger_level: int = 0) -> list[dict[str, Any]]:
    templates = ITEM_TEMPLATES.get(category) or []
    if not templates:
        return [_fallback_template(category)]
    level = max(0, _safe_int(danger_level, 0))
    eligible = [template for template in templates if _safe_int(template.get("level"), 0) <= level]
    return eligible or list(templates)


def _template_for(category: str, name: str | None) -> dict[str, Any]:
    templates = ITEM_TEMPLATES.get(category) or []
    if name:
        for template in templates:
            if str(template.get("name") or "") == name:
                return template
        if templates:
            fallback = dict(templates[0])
            fallback["name"] = name
            return fallback
        return _fallback_template(category, name)
    return templates[0] if templates else _fallback_template(category)


def _template_power(template: dict[str, Any], rarity: str) -> int:
    base_power = max(0, _safe_int(template.get("power"), 0))
    if base_power <= 0:
        return 0
    multiplier = RARITY_POWER_MULTIPLIER.get(normalise_rarity(rarity), 1.0)
    return max(1, int(round(base_power * multiplier)))


def _template_effects(template: dict[str, Any], rarity: str) -> list[dict[str, Any]]:
    use_effect = _template_use_effect(template.get("use_effect"))
    power = _template_power(template, rarity)
    if power <= 0:
        power = max(0, _safe_int(template.get("power"), 0))
    if use_effect == "HP_Heal":
        return [{"type": "heal", "value": power}]
    if use_effect == "SP_Heal":
        return [{"type": "restore_sp", "value": power}]
    if use_effect == "SP_Damage":
        return [{"type": "sp_damage", "value": power}]
    if use_effect == "HP_Damage":
        return [{"type": "hp_damage", "value": power}]
    if use_effect == "Hunger_Heal":
        return [{"type": "hunger", "value": power}]
    if use_effect == "Send_LLM":
        return [{"type": "send_llm", "text": str(template.get("send_llm") or "")}]
    return []


def _new_item_instance_id(category: str, name: str) -> str:
    seed = f"{category}:{name}:{random.getrandbits(64)}"
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _new_item_uuid() -> str:
    return str(uuid.uuid4())


def _ensure_item_uuids(item: dict[str, Any]) -> None:
    quantity = max(1, _safe_int(item.get("quantity", 1), 1))
    raw_uuids = item.get("item_uuids")
    uuids = [str(value) for value in raw_uuids if str(value).strip()] if isinstance(raw_uuids, list) else []
    item_uuid = str(item.get("item_uuid") or "").strip()
    if item_uuid and item_uuid not in uuids:
        uuids.insert(0, item_uuid)
    while len(uuids) < quantity:
        uuids.append(_new_item_uuid())
    if len(uuids) > quantity:
        uuids = uuids[:quantity]
    item["item_uuids"] = uuids
    item["item_uuid"] = uuids[0]


def _item_uuid_list(item: dict[str, Any]) -> list[str]:
    normalised = dict(item)
    _ensure_item_uuids(normalised)
    return [str(value) for value in normalised.get("item_uuids", [])]


def _collect_item_uuids(items: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for item in items:
        result.extend(_item_uuid_list(item))
    return result


def _rarity_rank(rarity: str) -> int:
    rarity = normalise_rarity(rarity)
    return RARITY_ORDER.index(rarity) if rarity in RARITY_ORDER else 0


def _highest_rarity(items: list[dict[str, Any]]) -> str:
    return max((normalise_rarity(item.get("rarity")) for item in items), key=_rarity_rank, default="common")


def _next_rarity(rarity: str) -> str:
    index = min(len(RARITY_ORDER) - 1, _rarity_rank(rarity) + 1)
    return RARITY_ORDER[index]


def _upgrade_rarity(rarity: str, steps: int) -> str:
    index = min(len(RARITY_ORDER) - 1, max(0, _rarity_rank(rarity) + max(0, int(steps or 0))))
    return RARITY_ORDER[index]


def _craft_roll_quality_steps(craft_roll: dict[str, Any] | None, *, equipment: bool) -> int:
    if not isinstance(craft_roll, dict):
        return 1 if equipment else 0
    if craft_roll.get("critical_success"):
        return 2
    target = _safe_int(craft_roll.get("target"), 10)
    total = _safe_int(craft_roll.get("total"), 0)
    success = bool(craft_roll.get("success"))
    margin = total - target
    if margin >= 6:
        return 1
    if success and equipment:
        return 1
    return 0


def _craft_roll_stat_bonus(craft_roll: dict[str, Any] | None) -> int:
    if not isinstance(craft_roll, dict):
        return 0
    if craft_roll.get("critical_success"):
        return 4
    target = _safe_int(craft_roll.get("target"), 10)
    total = _safe_int(craft_roll.get("total"), 0)
    if total >= target + 6:
        return 3
    if total >= target + 3:
        return 2
    if craft_roll.get("success"):
        return 1
    return 0


def _craft_quality_message(craft_roll: dict[str, Any] | None) -> str:
    if not isinstance(craft_roll, dict):
        return ""
    if craft_roll.get("critical_success"):
        return "会心の出来です。"
    target = _safe_int(craft_roll.get("target"), 10)
    total = _safe_int(craft_roll.get("total"), 0)
    if total >= target + 6:
        return "非常に良い出来です。"
    if total >= target + 3:
        return "良い出来です。"
    if craft_roll.get("success"):
        return "安定した出来です。"
    return "粗い出来ですが形になりました。"


def _crafted_consumable_category(items: list[dict[str, Any]]) -> str:
    categories = {normalise_category(str(item.get("category") or "")) for item in items}
    if categories & {"medicine", "potion", "material_plant", "material_liquid"}:
        return "potion"
    if categories & {"food", "drink"}:
        return "food"
    if categories & {"scroll", "magicrod", "material_magical", "material_gem", "relic"}:
        return "material_magical"
    if categories & {"material_ore", "material_metal"}:
        return "material_metal"
    return "material_common"


def _dedupe_effects(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _base_equipment_attack(category: str, rarity: str) -> int:
    if category not in WEAPON_CATEGORIES:
        return 0
    base = {
        "weapon_small": 3,
        "weapon_range": 4,
        "weapon_medium": 5,
        "weapon_long": 6,
        "weapon_large": 8,
    }.get(category, 4)
    return base + RARITY_POWER.get(normalise_rarity(rarity), 1)


def _base_equipment_defense(category: str, rarity: str) -> int:
    if category in WEAPON_CATEGORIES:
        return 0
    base = {
        "armor_head": 2,
        "armor_body": 6,
        "armor_shield": 5,
        "armor_cloth": 1,
        "armor_arm": 2,
        "armor_leg": 3,
        "accessory_ring": 0,
        "accessory_amulet": 0,
    }.get(category, 0)
    return base + max(0, RARITY_POWER.get(normalise_rarity(rarity), 1) // 2)


def _equipment_effects(category: str, rarity: str, name: str) -> list[dict[str, Any]]:
    rarity = normalise_rarity(rarity)
    count = RARITY_EFFECT_COUNT.get(rarity, 0)
    if count <= 0:
        return []
    rng = _rng("equipment_effects", category, rarity, name)
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
        "status_immunity",
    ]
    if category not in WEAPON_CATEGORIES:
        pool.append("element_resistance")
    selected = rng.sample(pool, k=min(count, len(pool)))
    power = RARITY_POWER.get(rarity, 1)
    effects: list[dict[str, Any]] = []
    for effect_type in selected:
        if effect_type == "max_hp":
            effects.append({"type": "max_hp", "value": 5 + power * 3})
        elif effect_type == "max_sp":
            effects.append({"type": "max_sp", "value": 4 + power * 2})
        elif effect_type in {"str", "dex", "con", "int", "wis", "cha"}:
            effects.append({"type": effect_type, "value": max(1, power // 3)})
        elif effect_type == "hp_regen":
            effects.append({"type": "hp_regen", "value": max(1, power // 4)})
        elif effect_type == "sp_regen":
            effects.append({"type": "sp_regen", "value": max(1, power // 5)})
        elif effect_type == "status_immunity":
            status = rng.choice(list(STATUS_IMMUNITY_EFFECT_IDS))
            effects.append({"type": "status_immunity", "status": status, "value": 1})
        elif effect_type == "element_resistance":
            elements = [element_id for element_id in ELEMENT_IDS if element_id != "none"]
            element_id = rng.choice(elements)
            amount = 0.5 if power >= 7 else 0.2
            effects.append({"type": "element_resistance", "element": element_id, "amount": amount})
    return effects


def _equipment_llm_effects(category: str, rarity: str, name: str) -> list[dict[str, Any]]:
    rarity = normalise_rarity(rarity)
    count = RARITY_LLM_EFFECT_COUNT.get(rarity, 0)
    if count <= 0:
        return []
    rng = _rng("equipment_llm_effects", category, rarity, name)
    pool = [
        {"name": "古い誓約", "effect": "持ち主の約束や過去の縁を物語に反映しやすい。"},
        {"name": "精霊の気配", "effect": "自然や精霊に関わる場面で反応や手がかりを増やせる。"},
        {"name": "威圧の意匠", "effect": "交渉や戦闘前の威圧として描写できる。"},
        {"name": "守護の銘", "effect": "危険を察した時に警告や守りの演出を出せる。"},
        {"name": "不吉な残響", "effect": "呪い、亡霊、古戦場に関わる描写で存在感を出せる。"},
        {"name": "幸運の印", "effect": "偶然の発見や小さな幸運を物語に混ぜられる。"},
    ]
    return rng.sample(pool, k=min(count, len(pool)))


def _equipment_effect_label(effect: Any, language: str = "ja") -> str:
    if not isinstance(effect, dict):
        return ""
    effect_type = str(effect.get("type") or effect.get("stat") or effect.get("name") or "").strip().lower()
    value = _safe_int(effect.get("value", effect.get("amount", 0)), 0)
    labels = {
        "max_hp": "最大HP",
        "hp_max": "最大HP",
        "max_sp": "最大SP",
        "max_mp": "最大SP",
        "str": "筋力",
        "dex": "器用",
        "con": "耐久",
        "int": "知力",
        "wis": "判断",
        "cha": "魅力",
        "hp_regen": "HP自動回復",
        "sp_regen": "SP自動回復",
        "mp_regen": "SP自動回復",
    }
    if effect_type in {"status_immunity", "immunity", "immune"}:
        status = effect.get("status") or effect.get("status_id") or effect.get("target") or effect.get("value")
        status_id = canonical_status_effect_id(status)
        label = status_effect_label(status_id or status, language)
        if str(language or "").strip().lower().startswith("en"):
            return f"Status immunity: {label}"
        return f"状態異常無効: {label}"
    if effect_type in {"element_resistance", "element_damage_reduction", "resist_element"}:
        element = str(effect.get("element") or effect.get("target") or effect.get("attribute") or "").strip()
        label = tr_enum("element", element, language, fallback=element)
        percent = int(round(max(0.0, min(1.0, _safe_float(effect.get("amount"), 0.0))) * 100))
        if str(language or "").strip().lower().startswith("en"):
            return f"{label} damage reduction {percent}%"
        return f"{label}ダメージ軽減 {percent}%"
    label = labels.get(effect_type)
    if not label:
        return ""
    sign = f"+{value}" if value >= 0 else str(value)
    return f"{label} {sign}"


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _effect_text(item: dict[str, Any]) -> str:
    effects = item.get("effects")
    if not isinstance(effects, list) or not effects:
        return ""
    parts = []
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        effect_type = str(effect.get("type") or effect.get("name") or "").strip().lower()
        value = effect.get("value")
        if effect_type == "heal":
            parts.append(f"HPが少し回復した(+{value})。")
        elif effect_type in {"stamina", "restore_sp", "recover_sp", "sp_restore"}:
            parts.append(f"SPが少し回復した(+{value})。")
        elif effect_type in {"hp_damage", "damage"}:
            parts.append(f"HPに影響が出た(-{value})。")
        elif effect_type in {"sp_damage", "consume_sp", "fatigue"}:
            parts.append(f"SPに影響が出た(-{value})。")
        elif effect_type in {"hunger", "restore_hunger", "hunger_heal"}:
            parts.append(f"空腹度が回復した(+{value})。")
        elif effect_type == "send_llm":
            text = str(effect.get("text") or "").strip()
            if text:
                parts.append(text)
        elif effect_type:
            parts.append(f"{effect_type} の効果が発生した。")
    return " ".join(parts)


def _effect_hp_delta(effect: Any) -> int:
    if not isinstance(effect, dict):
        return 0
    effect_type = str(effect.get("type") or effect.get("name") or effect.get("kind") or "").strip().lower()
    if "hp_delta" in effect:
        return _safe_int(effect.get("hp_delta"), 0)
    if "player_hp_delta" in effect:
        return _safe_int(effect.get("player_hp_delta"), 0)
    value = _safe_int(
        effect.get("value", effect.get("amount", effect.get("points", effect.get("hp", 0)))),
        0,
    )
    if effect_type in {"heal", "healing", "restore", "restore_hp", "recover", "recover_hp", "hp_restore", "cure", "treatment"}:
        return abs(value)
    if effect_type in {"damage", "hp_damage", "harm", "poison"}:
        return -abs(value)
    return 0


def _effect_sp_delta(effect: Any) -> int:
    if not isinstance(effect, dict):
        return 0
    effect_type = str(effect.get("type") or effect.get("name") or effect.get("kind") or "").strip().lower()
    if "sp_delta" in effect:
        return _safe_int(effect.get("sp_delta"), 0)
    if "player_sp_delta" in effect:
        return _safe_int(effect.get("player_sp_delta"), 0)
    value = _safe_int(
        effect.get("value", effect.get("amount", effect.get("points", effect.get("sp", 0)))),
        0,
    )
    if effect_type in {"restore_sp", "recover_sp", "sp_restore", "sp_recovery", "mana", "mp", "focus", "will"}:
        return abs(value)
    if effect_type in {"consume_sp", "sp_cost", "sp_damage", "drain_sp", "fatigue"}:
        return -abs(value)
    return 0


def _effect_hunger_delta(effect: Any) -> int:
    if not isinstance(effect, dict):
        return 0
    effect_type = str(effect.get("type") or effect.get("name") or effect.get("kind") or "").strip().lower()
    if "hunger_delta" in effect:
        return _safe_int(effect.get("hunger_delta"), 0)
    if "player_hunger_delta" in effect:
        return _safe_int(effect.get("player_hunger_delta"), 0)
    value = _safe_int(
        effect.get("value", effect.get("amount", effect.get("points", effect.get("hunger", 0)))),
        0,
    )
    if effect_type in {"hunger", "hunger_heal", "restore_hunger", "recover_hunger", "hunger_restore", "meal", "food"}:
        return abs(value)
    if effect_type in {"hunger_damage", "starvation", "consume_hunger"}:
        return -abs(value)
    return 0


def _icon_hint(category: str, name: str) -> str:
    count = FANTASIA_ITEM_CATEGORY_COUNTS.get(category, 1)
    rng = _rng("icon", category, name)
    return f"item_candidates/{category}/{rng.randint(1, count)}.png"


def _random_quantity(category: str, rng: random.Random) -> int:
    if category in EQUIPMENT_CATEGORIES or category in {"relic", "scroll", "magicrod", "material_gem", "treasure"}:
        return 1
    if category in {
        "junk",
        "material_common",
        "material_liquid",
        "material_plant",
        "material_ore",
        "material_metal",
        "material_creature",
        "material_magical",
    }:
        return rng.randint(1, 4)
    if category in {"food", "drink", "tool"}:
        return rng.randint(1, 3)
    return rng.randint(1, 2)


def _stack_key(item: dict[str, Any]) -> str:
    if not bool(item.get("stackable", True)):
        return ""
    data = {
        "name": str(item.get("name") or ""),
        "category": normalise_category(str(item.get("category") or "")),
        "value": item_value(item),
        "rarity": str(item.get("rarity") or "common"),
        "effects": item.get("effects") if isinstance(item.get("effects"), list) else [],
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _looks_like_item(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict):
        return False
    keys = {str(key).lower() for key in value}
    return bool(
        keys
        & {
            "name",
            "item_name",
            "title",
            "label",
            "category",
            "type",
            "kind",
            "quantity",
            "count",
            "amount",
            "value",
            "price",
            "description",
        }
    )


def _category_from_key(key: str) -> str:
    if key in {"treasure", "reward", "item_add", "item_adds"}:
        return "treasure"
    if "loot" in key or "drop" in key:
        return "junk"
    return "junk"


def _gold_amount(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, dict):
        total = 0
        for key, child in value.items():
            if str(key).lower() in GOLD_KEYS:
                total += _gold_amount(child)
        return total
    if isinstance(value, list):
        return sum(_gold_amount(item) for item in value)
    text = str(value)
    match = re.search(r"(\d+)\s*(?:g|gp|gold|coins?|G|Ｇ|金貨|所持金)", text)
    return int(match.group(1)) if match else 0


def _rng(*parts: object) -> random.Random:
    seed_text = "|".join(str(part) for part in parts)
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
    return random.Random(seed)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
