from __future__ import annotations

import hashlib
import json
import random
import re
import uuid
from copy import deepcopy
from typing import Any

from .i18n import tr_enum


FANTASIA_ITEM_CATEGORY_COUNTS: dict[str, int] = {
    "accessory": 161,
    "body_armor": 63,
    "clothing": 89,
    "creature": 128,
    "creature_part": 342,
    "document": 214,
    "drink": 53,
    "food": 309,
    "gauntlets": 53,
    "gem": 97,
    "headgear": 180,
    "large_weapon": 155,
    "legwear": 151,
    "leg_armor": 151,
    "liquid_material": 65,
    "long_weapon": 76,
    "magical_material": 89,
    "medicine": 4,
    "medium_weapon": 163,
    "metal": 20,
    "mushroom": 91,
    "ore": 63,
    "other_material": 116,
    "plant": 237,
    "potion": 61,
    "relic": 129,
    "scrap": 261,
    "scroll": 60,
    "shield": 114,
    "small_weapon": 267,
    "throwable_weapon": 12,
    "tool": 214,
    "treasure": 170,
}

CATEGORY_LABELS: dict[str, str] = {
    "accessory": "装飾品",
    "body_armor": "胴防具",
    "clothing": "衣服",
    "creature": "生物",
    "creature_part": "素材",
    "document": "文書",
    "drink": "飲料",
    "food": "食料",
    "gauntlets": "腕防具",
    "gem": "宝石",
    "headgear": "頭防具",
    "large_weapon": "大型武器",
    "legwear": "脚衣",
    "leg_armor": "脚防具",
    "liquid_material": "液体素材",
    "long_weapon": "長柄武器",
    "magical_material": "魔法素材",
    "medicine": "薬",
    "medium_weapon": "武器",
    "metal": "金属",
    "mushroom": "茸",
    "ore": "鉱石",
    "other_material": "素材",
    "plant": "植物",
    "potion": "ポーション",
    "relic": "遺物",
    "scrap": "ガラクタ",
    "scroll": "巻物",
    "shield": "盾",
    "small_weapon": "小型武器",
    "throwable_weapon": "投擲武器",
    "tool": "道具",
    "treasure": "財宝",
}

EQUIPMENT_CATEGORIES = {
    "accessory",
    "body_armor",
    "clothing",
    "gauntlets",
    "headgear",
    "large_weapon",
    "legwear",
    "leg_armor",
    "long_weapon",
    "medium_weapon",
    "shield",
    "small_weapon",
    "throwable_weapon",
}

WEAPON_CATEGORIES = {
    "small_weapon",
    "medium_weapon",
    "large_weapon",
    "long_weapon",
    "throwable_weapon",
}

EQUIPMENT_SLOTS = ("weapon", "head", "body", "feet", "accessory")

EQUIPMENT_SLOT_LABELS = {
    "weapon": "武器",
    "head": "頭",
    "body": "胴体",
    "feet": "足",
    "accessory": "アクセサリー",
}

ARMOR_SLOT_BY_CATEGORY = {
    "headgear": "head",
    "body_armor": "body",
    "clothing": "body",
    "gauntlets": "body",
    "shield": "body",
    "leg_armor": "feet",
    "legwear": "feet",
    "accessory": "accessory",
}

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
    "uncommon": 1.7,
    "rare": 3.0,
    "epic": 5.5,
    "legendary": 9.0,
    "artifact": 15.0,
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
RARITY_POWER = {
    "common": 1,
    "uncommon": 2,
    "rare": 4,
    "epic": 7,
    "legendary": 11,
    "artifact": 16,
}

CATEGORY_ALIASES = {
    "armor": "body_armor",
    "armour": "body_armor",
    "consumable": "potion",
    "material": "other_material",
    "weapon": "medium_weapon",
    "sword": "medium_weapon",
    "blade": "medium_weapon",
    "helmet": "headgear",
    "helm": "headgear",
    "boots": "leg_armor",
    "shoes": "legwear",
    "money": "treasure",
    "valuable": "treasure",
    "book": "document",
    "note": "document",
}

CATEGORY_BASE_VALUE = {
    "food": 5,
    "drink": 4,
    "medicine": 18,
    "potion": 28,
    "tool": 12,
    "scrap": 2,
    "other_material": 5,
    "plant": 4,
    "mushroom": 6,
    "ore": 10,
    "metal": 14,
    "gem": 45,
    "treasure": 35,
    "document": 10,
    "scroll": 38,
    "magical_material": 24,
    "relic": 80,
    "small_weapon": 30,
    "medium_weapon": 45,
    "large_weapon": 70,
    "long_weapon": 55,
    "throwable_weapon": 12,
    "shield": 35,
    "body_armor": 60,
    "headgear": 25,
    "gauntlets": 22,
    "leg_armor": 35,
    "clothing": 14,
    "legwear": 12,
    "accessory": 35,
    "creature_part": 8,
    "liquid_material": 12,
    "creature": 20,
}

ITEM_TEMPLATES: dict[str, list[tuple[str, str, int]]] = {
    "food": [
        ("旅糧パン", "硬く焼いた携帯食。長旅でも腹を満たせる。", 5),
        ("干し果物", "小袋に詰められた甘い保存食。", 7),
        ("燻製肉", "煙の香りが残る肉片。", 10),
    ],
    "drink": [
        ("水袋", "澄んだ水を入れた革袋。", 4),
        ("薄いエール", "喉を湿らせる軽い酒。", 6),
        ("薬草茶", "体を温める苦い茶。", 8),
    ],
    "medicine": [
        ("止血薬", "浅い傷に効く基礎的な薬。", 18),
        ("解毒薬", "毒やしびれを抑える薬。", 24),
        ("癒やしの軟膏", "傷口に塗る軟膏。", 20),
        ("気付け薬", "意識をはっきりさせる刺激薬。", 16),
    ],
    "potion": [
        ("小瓶の治癒薬", "淡く光る赤い薬液。", 30),
        ("澄んだ魔力薬", "魔力を帯びた青い薬液。", 34),
        ("耐毒の霊薬", "毒気に抗うための霊薬。", 42),
    ],
    "tool": [
        ("松明", "暗所を照らすための松明。", 8),
        ("古いロープ", "まだ使える丈夫なロープ。", 12),
        ("火打ち石", "火を起こすための小道具。", 10),
        ("携帯ランタン", "油を入れて使う小さなランタン。", 20),
    ],
    "scrap": [
        ("錆びた釘束", "修理や罠作りに使えそうな釘。", 2),
        ("壊れた歯車", "古い機械から外れた部品。", 3),
        ("裂けた布切れ", "包帯や詰め物にできる布。", 2),
        ("曲がった金具", "鍛冶屋なら再利用できそうな金具。", 4),
    ],
    "other_material": [
        ("丈夫な紐", "荷造りや簡単な修理に使える。", 4),
        ("獣脂の塊", "灯火や薬の材料になる。", 5),
        ("骨片", "小さな加工素材。", 4),
    ],
    "plant": [
        ("薬草", "薬の材料になる青い草。", 5),
        ("香草の束", "食事や薬に香りを加える草。", 6),
        ("夜露草", "夜明けにだけ採れる湿った草。", 9),
    ],
    "mushroom": [
        ("白まだら茸", "食用か薬用か判別が必要な茸。", 6),
        ("月影茸", "薄く光る珍しい茸。", 14),
    ],
    "ore": [
        ("鉄鉱石", "精錬すれば武具の材料になる。", 10),
        ("銅鉱石", "扱いやすい赤みがかった鉱石。", 8),
        ("黒曜石片", "鋭く割れる黒い石。", 12),
    ],
    "metal": [
        ("鉄の延べ棒", "鍛冶に使う精錬済みの金属。", 18),
        ("銀片", "魔除けにも使われる金属片。", 24),
    ],
    "gem": [
        ("曇った水晶", "内側に淡い光を含む水晶。", 35),
        ("小さな紅玉", "傷はあるが価値のある宝石。", 55),
        ("青い輝石", "魔法触媒として扱われる石。", 48),
    ],
    "treasure": [
        ("古い硬貨", "今も交換価値が残る硬貨。", 12),
        ("銀の小杯", "細工の入った小さな杯。", 38),
        ("細工箱", "鍵の壊れた装飾箱。", 45),
    ],
    "document": [
        ("濡れた手紙", "差出人の名がにじんだ手紙。", 8),
        ("古い地図片", "周辺の道筋が描かれた紙片。", 18),
        ("店の覚書", "取引の記録が残る帳面。", 12),
    ],
    "scroll": [
        ("封じた巻物", "簡単な術式が記された巻物。", 36),
        ("護符の紙片", "災い避けの印が書かれている。", 22),
    ],
    "magical_material": [
        ("魔力の粉", "術式に混ぜるきらめく粉。", 24),
        ("星硝子", "夜空のように光る硝子片。", 34),
    ],
    "relic": [
        ("欠けた聖印", "古い祈りの痕跡が残る遺物。", 70),
        ("記憶石", "触れると微かな声が響く石。", 95),
    ],
    "small_weapon": [
        ("短剣", "扱いやすい小型の刃物。", 28),
        ("狩猟ナイフ", "野外で役立つ刃物。", 24),
    ],
    "medium_weapon": [
        ("鉄の剣", "標準的な片手剣。", 45),
        ("片手斧", "木を割るにも戦うにも使える斧。", 42),
    ],
    "large_weapon": [
        ("大剣", "両手で扱う重い剣。", 72),
        ("戦槌", "鎧ごと叩き潰す重い槌。", 68),
    ],
    "long_weapon": [
        ("槍", "間合いを取れる長柄武器。", 50),
        ("古い薙刀", "刃こぼれした長柄武器。", 44),
    ],
    "throwable_weapon": [
        ("投げナイフ", "軽く投げやすい短い刃。", 12),
        ("投石袋", "丸石を入れた簡易武器。", 6),
    ],
    "shield": [
        ("木の盾", "軽く扱いやすい盾。", 28),
        ("丸盾", "金属縁の小型盾。", 38),
    ],
    "body_armor": [
        ("革鎧", "動きやすい軽装の鎧。", 55),
        ("鎖帷子", "刃を受け流す鎖の鎧。", 75),
    ],
    "headgear": [
        ("旅人の帽子", "雨風をしのぐ帽子。", 12),
        ("革の兜", "頭を守る簡素な兜。", 26),
    ],
    "gauntlets": [
        ("革手袋", "手を守る厚手の手袋。", 16),
        ("鉄の篭手", "前腕まで覆う金属防具。", 32),
    ],
    "leg_armor": [
        ("革の脛当て", "足元を守る軽い防具。", 24),
        ("鉄の脚甲", "重いが頼れる脚防具。", 38),
    ],
    "clothing": [
        ("旅装束", "埃に強い外套つきの服。", 16),
        ("町人の服", "目立たない日常着。", 12),
    ],
    "legwear": [
        ("丈夫な靴下", "長歩きで足を守る布。", 5),
        ("旅靴", "道歩きに向いた靴。", 18),
    ],
    "accessory": [
        ("銅の指輪", "簡素な銅製の指輪。", 24),
        ("旅のお守り", "小さな祈り札を束ねた飾り。", 28),
    ],
    "creature_part": [
        ("獣の牙", "加工すれば矢じりにもなる牙。", 8),
        ("硬い鱗", "防具素材になりそうな鱗。", 10),
        ("魔物の爪", "微かな魔力を帯びた爪。", 12),
    ],
    "liquid_material": [
        ("澄んだ油", "ランタンや調合に使える油。", 10),
        ("粘つく樹液", "接着や薬の材料になる樹液。", 12),
    ],
    "creature": [
        ("小さな使い魔", "籠の中で眠る奇妙な生き物。", 45),
        ("荷運び虫", "小荷物を運べる大きな虫。", 30),
    ],
}

LOOT_PROFILES: dict[str, list[tuple[str, int]]] = {
    "settlement": [("food", 4), ("drink", 2), ("tool", 3), ("scrap", 4), ("document", 2), ("treasure", 1)],
    "wilderness": [("plant", 5), ("mushroom", 2), ("creature_part", 2), ("food", 2), ("scrap", 1), ("ore", 1)],
    "dungeon": [("scrap", 4), ("treasure", 2), ("relic", 1), ("potion", 2), ("scroll", 1), ("creature_part", 2)],
    "battlefield": [("small_weapon", 2), ("medium_weapon", 2), ("shield", 1), ("scrap", 3), ("medicine", 1), ("body_armor", 1)],
    "market": [("food", 3), ("drink", 2), ("tool", 3), ("clothing", 2), ("treasure", 1), ("medicine", 1)],
    "default": [("food", 2), ("tool", 2), ("scrap", 3), ("plant", 2), ("treasure", 1), ("medicine", 1)],
}

VENDOR_PROFILES: dict[str, list[tuple[str, int]]] = {
    "healer": [("medicine", 5), ("potion", 4), ("plant", 3), ("liquid_material", 2), ("scroll", 1)],
    "blacksmith": [("small_weapon", 2), ("medium_weapon", 4), ("large_weapon", 1), ("long_weapon", 2), ("shield", 2), ("body_armor", 2), ("metal", 3)],
    "mage": [("scroll", 4), ("potion", 2), ("magical_material", 4), ("gem", 2), ("relic", 1), ("document", 2)],
    "inn": [("food", 5), ("drink", 4), ("medicine", 1), ("tool", 1)],
    "general": [("food", 3), ("drink", 2), ("tool", 4), ("medicine", 2), ("clothing", 2), ("scrap", 2)],
}

ITEM_CONTAINER_KEYS = {
    "item",
    "items",
    "item_reward",
    "item_rewards",
    "loot",
    "loot_items",
    "drop",
    "drops",
    "reward",
    "rewards",
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
        make_item("food", name="旅糧パン", quantity=2, source="starter"),
        make_item("medicine", name="止血薬", quantity=1, source="starter"),
        make_item("tool", name="古いロープ", quantity=1, source="starter"),
    ]


def generate_loot_items(location_name: str, context: str = "", count: int | None = None) -> list[dict[str, Any]]:
    profile_name = _loot_profile_name(f"{location_name} {context}")
    profile = LOOT_PROFILES[profile_name]
    rng = _rng("loot", location_name, context, profile_name)
    item_count = count if count is not None else rng.randint(2, 4)
    return [_random_item(profile, rng, source="loot", context=location_name) for _ in range(max(1, item_count))]


def generate_vendor_items(owner_name: str, context: str = "", count: int | None = None) -> list[dict[str, Any]]:
    profile_name = _vendor_profile_name(f"{owner_name} {context}")
    profile = VENDOR_PROFILES[profile_name]
    rng = _rng("vendor", owner_name, context, profile_name)
    item_count = count if count is not None else rng.randint(5, 8)
    return [_random_item(profile, rng, source="vendor", context=owner_name) for _ in range(max(1, item_count))]


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
    template_name, template_description, template_value = _template_for(category, cleaned_name or None)
    item_name = cleaned_name or str(template_name)
    explicit_value = value is not None
    item_value = int(value if value is not None else template_value)
    if category in EQUIPMENT_CATEGORIES and not explicit_value:
        item_value = max(1, int(item_value * RARITY_VALUE_MULTIPLIER.get(rarity, 1.0)))
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
        "stackable": stackable,
        "tradable": True,
        "icon_hint": _icon_hint(category, item_name),
    }
    _ensure_item_uuids(item)
    if category in EQUIPMENT_CATEGORIES:
        item["equipment_slot"] = equipment_slot_for_category(category)
        item["instance_id"] = _new_item_instance_id(category, item_name)
        item["attack"] = _base_equipment_attack(category, rarity)
        item["defense"] = _base_equipment_defense(category, rarity)
        item["effects"] = deepcopy(effects) if effects is not None else _equipment_effects(category, rarity, item_name)
        item["llm_effects"] = _equipment_llm_effects(category, rarity, item_name)
    else:
        item["effects"] = deepcopy(effects) if effects is not None else _default_effects(category)
    return item


def normalise_item(raw: Any, source: str = "", fallback_category: str = "scrap") -> dict[str, Any]:
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
        value=value,
        rarity=rarity,
        source=str(data.get("source") or source),
        effects=effects,
    )
    for key, value in data.items():
        if key not in item and not str(key).startswith("_"):
            item[str(key)] = value
    for key in ("instance_id", "equipped", "equipment_slot", "attack", "defense", "effects", "llm_effects", "item_uuid", "item_uuids"):
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
    if category in EQUIPMENT_CATEGORIES:
        item["equipment_slot"] = str(item.get("equipment_slot") or equipment_slot_for_category(category))
        item["instance_id"] = str(item.get("instance_id") or _new_item_instance_id(category, name))
        item["attack"] = _safe_int(item.get("attack"), _base_equipment_attack(category, str(item.get("rarity"))))
        item["defense"] = _safe_int(item.get("defense"), _base_equipment_defense(category, str(item.get("rarity"))))
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


def add_item_stack(inventory: list[dict[str, Any]], raw: Any, source: str = "", quantity: int | None = None) -> dict[str, Any]:
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
) -> dict[str, Any] | None:
    taken = take_item_stack(source_inventory, index, quantity)
    if not taken:
        return None
    return add_item_stack(target_inventory, taken, source=source)


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


def sell_value(item: dict[str, Any]) -> int:
    return max(1, item_value(item) // 2)


def item_rarity_color(item: dict[str, Any]) -> str:
    normalised = normalise_item(item)
    return RARITY_TEXT_COLORS.get(str(normalised.get("rarity") or "common"), "#f2f2f2")


def item_label(item: dict[str, Any], price_mode: str = "", language: str = "ja") -> str:
    normalised = normalise_item(item)
    name = str(normalised.get("name") or tr_enum("roster", "unknown", language))
    quantity = max(1, _safe_int(normalised.get("quantity", 1), 1))
    category_id = str(normalised.get("category") or "scrap")
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
        category = str(base.get("category") or "medium_weapon")
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
    value = CATEGORY_ALIASES.get(value, value)
    return value if value in FANTASIA_ITEM_CATEGORY_COUNTS else "scrap"


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
                if immunity:
                    immunities.append(immunity)
        if isinstance(item.get("llm_effects"), list):
            llm_effects.extend(item.get("llm_effects") or [])
    summary["status_immunities"] = _dedupe_texts(immunities)
    summary["llm_effects"] = llm_effects[:10]
    summary["items"] = items
    return summary


def item_tooltip_text(item: dict[str, Any], price_mode: str = "", language: str = "ja") -> str:
    normalised = normalise_item(item)
    category_id = str(normalised.get("category") or "scrap")
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
            text = _equipment_effect_label(effect)
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


def _random_item(profile: list[tuple[str, int]], rng: random.Random, source: str, context: str) -> dict[str, Any]:
    categories, weights = zip(*profile)
    category = rng.choices(categories, weights=weights, k=1)[0]
    name, description, base_value = rng.choice(ITEM_TEMPLATES.get(category, [(CATEGORY_LABELS.get(category, "アイテム"), "", CATEGORY_BASE_VALUE.get(category, 5))]))
    if category in EQUIPMENT_CATEGORIES:
        rarity = rng.choices(list(RARITY_ORDER), weights=[65, 22, 8, 3.5, 1.2, 0.3], k=1)[0]
        multiplier = 1.0
    else:
        rarity = rng.choices(["common", "uncommon", "rare"], weights=[76, 20, 4], k=1)[0]
        multiplier = {"common": 1.0, "uncommon": 1.5, "rare": 2.3}[rarity]
    quantity = _random_quantity(category, rng)
    return make_item(
        category,
        name=name,
        description=f"{context}で見つかる品。{description}" if source == "loot" else description,
        quantity=quantity,
        value=max(1, int(base_value * multiplier)),
        rarity=rarity,
        source=source,
    )


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
    if any(word in lowered for word in ("heal", "doctor", "apothecary", "薬", "医", "治療", "聖職")):
        return "healer"
    if any(word in lowered for word in ("smith", "weapon", "armor", "鍛冶", "武器", "防具", "傭兵")):
        return "blacksmith"
    if any(word in lowered for word in ("mage", "magic", "scholar", "魔", "術", "学者", "書")):
        return "mage"
    if any(word in lowered for word in ("inn", "cook", "tavern", "宿", "酒場", "料理")):
        return "inn"
    return "general"


def _template_for(category: str, name: str | None) -> tuple[str, str, int]:
    templates = ITEM_TEMPLATES.get(category)
    if not templates:
        return (name or CATEGORY_LABELS.get(category, "アイテム"), "", CATEGORY_BASE_VALUE.get(category, 5))
    if name:
        for template_name, description, value in templates:
            if template_name == name:
                return template_name, description, value
        return name, "", CATEGORY_BASE_VALUE.get(category, templates[0][2])
    return templates[0]


def _default_effects(category: str) -> list[dict[str, Any]]:
    if category == "medicine":
        return [{"type": "heal", "value": 8}]
    if category == "potion":
        return [{"type": "heal", "value": 14}]
    if category in {"food", "drink"}:
        return [{"type": "stamina", "value": 4}]
    if category == "scroll":
        return [{"type": "magic", "value": 1}]
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
    if categories & {"medicine", "potion", "plant", "mushroom"}:
        return "potion"
    if categories & {"food", "drink"}:
        return "food"
    if categories & {"scroll", "magical_material", "gem", "relic"}:
        return "magical_material"
    if categories & {"ore", "metal"}:
        return "metal"
    return "other_material"


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
        "small_weapon": 3,
        "throwable_weapon": 2,
        "medium_weapon": 5,
        "long_weapon": 6,
        "large_weapon": 8,
    }.get(category, 4)
    return base + RARITY_POWER.get(normalise_rarity(rarity), 1)


def _base_equipment_defense(category: str, rarity: str) -> int:
    if category in WEAPON_CATEGORIES:
        return 0
    base = {
        "headgear": 2,
        "body_armor": 6,
        "shield": 5,
        "clothing": 1,
        "gauntlets": 2,
        "leg_armor": 3,
        "legwear": 1,
        "accessory": 0,
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
            status = rng.choice(["poison", "bleed", "burn", "freeze", "sleep", "paralysis", "fear", "curse"])
            effects.append({"type": "status_immunity", "status": status, "value": 1})
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


def _equipment_effect_label(effect: Any) -> str:
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
        return f"状態異常無効: {status}"
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
        effect_type = str(effect.get("type") or effect.get("name") or "")
        value = effect.get("value")
        if effect_type == "heal":
            parts.append(f"HPが少し回復した(+{value})。")
        elif effect_type == "stamina":
            parts.append(f"体力が少し戻った(+{value})。")
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


def _icon_hint(category: str, name: str) -> str:
    count = FANTASIA_ITEM_CATEGORY_COUNTS.get(category, 1)
    rng = _rng("icon", category, name)
    return f"item_candidates/{category}/{rng.randint(1, count)}.png"


def _random_quantity(category: str, rng: random.Random) -> int:
    if category in EQUIPMENT_CATEGORIES or category in {"relic", "scroll", "gem", "treasure"}:
        return 1
    if category in {"scrap", "plant", "mushroom", "ore", "creature_part"}:
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
    if key in {"treasure", "reward", "rewards"}:
        return "treasure"
    if "loot" in key or "drop" in key:
        return "scrap"
    return "scrap"


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
