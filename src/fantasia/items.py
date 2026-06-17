from __future__ import annotations

import hashlib
import json
import random
import re
import uuid
from copy import deepcopy
from typing import Any

from .i18n import ELEMENT_IDS, tr_enum


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

ITEM_TEMPLATES = {
    "food": [
        ("干し肉", "旅で食べやすい保存食。", 5),
        ("黒パン", "腹持ちのよい素朴なパン。", 10),
        ("焼き菓子", "甘く焼き固めた携帯食。", 15),
    ],
    "drink": [
        ("水袋", "きれいな水を入れた革袋。", 5),
        ("薬草茶", "体を温める香りのよい茶。", 10),
        ("小瓶のエール", "短い休憩に向いた軽い酒。", 15),
    ],
    "medicine": [
        ("止血薬", "浅い傷の出血を止める薬。", 15),
        ("解毒薬", "毒やしびれを和らげる薬。", 20),
        ("鎮痛軟膏", "痛みと腫れを抑える軟膏。", 20),
    ],
    "potion": [
        ("治癒のポーション", "HPを回復する赤いポーション。", 30),
        ("活力のポーション", "SPを回復する青いポーション。", 30),
        ("精神集中のポーション", "集中力を整える澄んだポーション。", 30),
    ],
    "tool": [
        ("ロープ", "登攀や固定に使える丈夫な縄。", 10),
        ("ランタン", "暗所を照らす携帯灯。", 20),
        ("探索用ナイフ", "採取や簡単な作業に使える小刀。", 15),
    ],
    "document": [
        ("古い地図", "周辺の地形が大まかに描かれた地図。", 20),
        ("依頼書の写し", "依頼の要点がまとめられた紙。", 10),
        ("旅人の日誌", "道中の噂と記録が書かれた日誌。", 15),
        ("宝の地図", "恐らく宝のありかが書かれた地図。", 100),
    ],
    "scroll": [
        ("汎用の巻物", "弱いながらもある程度任意の魔法を引き出せる巻物。", 20),
        ("火花の巻物", "小さな炎を呼ぶ使い捨ての巻物。", 30),
        ("解錠の巻物", "単純な鍵や封印に働きかける巻物。", 30),
        ("防護の巻物", "一時的な守りを与える巻物。", 50),
    ],
    "magicrod": [
        ("火球の魔法杖", "相手に向かって火球を発射できる短い杖。", 50),
        ("癒しの魔法杖", "使用者を癒すことが出来る杖。", 70),
        ("鑑定の魔法杖", "よくわからない物を鑑定することが出来る杖。", 30),
    ],
    "material_common": [
        ("丈夫な糸", "修理や裁縫に使える汎用素材。", 5),
        ("獣骨片", "加工しやすい小さな骨片。", 10),
        ("加工木材", "乾燥させて整えた木材。", 15),
    ],
    "material_liquid": [
        ("澄んだ油", "灯りや調合に使える油。", 10),
        ("薬草エキス", "薬効成分を抽出した液体。", 15),
        ("魔力インク", "巻物や術式に使う淡く光るインク。", 20),
    ],
    "material_plant": [
        ("薬草", "薬の材料になる野草。", 10),
        ("香草", "食事や薬に香りを加える草。", 15),
        ("月光花", "夜に淡く光る希少な花。", 20),
    ],
    "material_ore": [
        ("銅鉱石", "加工しやすい赤みのある鉱石。", 5),
        ("鉄鉱石", "武具の材料になる鉱石。", 10),
        ("金鉱石", "装飾品にも使われる鉱石。", 15),
        ("銀鉱石", "装飾品にも使われる鉱石。", 15),
        ("黒曜石片", "鋭く割れる黒い石片。", 20),
        ("金剛石片", "非常に丈夫な石片。", 30),
    ],
    "material_metal": [
        ("銅インゴット", "鍛冶に使う精錬済みの金属。", 10),
        ("鉄インゴット", "鍛冶に使う精錬済みの金属。", 20),
        ("金インゴット", "魔術品にも使われる銀の塊。", 30),
        ("銀インゴット", "魔術品にも使われる銀の塊。", 30),
        ("強化金属片", "武具を強化できる金属片。", 50),
    ],
    "material_gem": [
        ("水晶片", "魔力を通しやすい透明な欠片。", 35),
        ("サファイア原石", "青く輝く未加工の宝石。", 60),
        ("ルビー原石", "赤く輝く未加工の宝石。", 60),
    ],
    "material_creature": [
        ("魔物の爪", "武具や薬の材料になる鋭い爪。", 10),
        ("獣皮", "防具や服の素材になる皮。", 10),
        ("透明な翅", "薄く魔力を帯びた生物素材。", 20),
    ],
    "material_magical": [
        ("魔力粉", "術式の触媒になる細かな粉。", 20),
        ("精霊の雫", "自然魔力を宿した液状の結晶。", 40),
    ],
    "junk": [
        ("錆びた釘", "売るか素材にする程度の古い釘。", 2),
        ("割れた陶片", "何かの器だった陶器の破片。", 2),
        ("壊れた歯車", "修理すれば使えるかもしれない部品。", 4),
    ],
    "treasure": [
        ("古貨幣", "今では使われていない古い貨幣。", 40),
        ("銀の杯", "細工の入った価値ある杯。", 60),
        ("宝石細工の箱", "小粒の宝石で飾られた箱。", 80),
    ],
    "relic": [
        ("祈りの小像", "古い信仰に使われた小さな像。", 100),
        ("古代の腕輪", "失われた意匠の腕輪。", 150),
        ("失われた紋章", "由来の分からない紋章片。", 200),
    ],
    "weapon_small": [
        ("短剣", "取り回しのよい小型武器。", 30),
        ("小型斧", "片手で扱える小さな斧。", 40),
    ],
    "weapon_medium": [
        ("鉄の剣", "標準的な片手剣。", 45),
        ("戦槌", "鎧越しに衝撃を通す鈍器。", 50),
        ("曲刀", "斬りつけに向いた湾曲した剣。", 60),
    ],
    "weapon_large": [
        ("大剣", "両手で振るう重い剣。", 70),
        ("戦斧", "破壊力のある大型斧。", 75),
        ("重槌", "強烈な打撃を与える大槌。", 75),
    ],
    "weapon_long": [
        ("槍", "間合いを取って突く長武器。", 55),
        ("薙刀", "斬撃にも突きにも使える長柄武器。", 60),
        ("長柄斧", "遠い間合いから振るう斧。", 60),
    ],
    "weapon_range": [
        ("投石袋", "投げるのにちょうどいい石が詰まった袋。", 10),
        ("弓", "離れた相手を狙える遠距離武器。", 50),
        ("クロスボウ", "強い弦で矢を撃ち出す武器。", 60),
        ("投げナイフ束", "複数本を束ねた投擲武器。", 40),
    ],
    "armor_shield": [
        ("丸盾", "扱いやすい標準的な盾。", 35),
        ("鉄盾", "重いが頼れる金属盾。", 50),
        ("祈祷盾", "簡単な護符を刻んだ盾。", 80),
    ],
    "armor_head": [
        ("革帽子", "軽く頭を守る帽子。", 20),
        ("鉄兜", "頑丈な金属製の兜。", 30),
        ("魔除けの頭巾", "不吉な力を避ける刺繍入りの頭巾。", 40),
    ],
    "armor_body": [
        ("革鎧", "動きやすい胴防具。", 55),
        ("鎖帷子", "刃を受け流す金属鎧。", 65),
        ("鉄胸甲", "胴をしっかり守る胸当て。", 75),
    ],
    "armor_arm": [
        ("革手袋", "手を守る厚手の手袋。", 20),
        ("鉄籠手", "前腕まで覆う金属防具。", 35),
        ("祈りの籠手", "守りの祈りが刻まれた腕防具。", 45),
    ],
    "armor_leg": [
        ("革ブーツ", "旅に向いた丈夫なブーツ。", 20),
        ("鉄脚甲", "脚を守る金属防具。", 40),
        ("旅人の脚絆", "長旅で足を支える布防具。", 50),
    ],
    "armor_cloth": [
        ("旅人の服", "動きやすく丈夫な服。", 15),
        ("厚手の外套", "寒さと小傷を防ぐ外套。", 30),
        ("魔術師のローブ", "術式の集中を助ける衣。", 45),
    ],
    "accessory_ring": [
        ("銀の指輪", "簡素な銀製の指輪。", 35),
        ("守りの指輪", "小さな守護紋を刻んだ指輪。", 55),
        ("火除けの指輪", "熱を遠ざける赤石付きの指輪。", 70),
    ],
    "accessory_amulet": [
        ("旅人の護符", "旅の安全を願った護符。", 35),
        ("聖印の首飾り", "祈りの印を下げた首飾り。", 55),
        ("黒曜石の護符", "闇や呪いを避けるとされる護符。", 70),
    ],
}

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
        make_item("food", name="黒パン", quantity=2, source="starter"),
        make_item("medicine", name="止血薬", quantity=1, source="starter"),
        make_item("tool", name="ロープ", quantity=1, source="starter"),
    ]


def generate_loot_items(location_name: str, context: str = "", count: int | None = None) -> list[dict[str, Any]]:
    profile_name = _loot_profile_name(f"{location_name} {context}")
    profile = LOOT_PROFILES[profile_name]
    rng = _rng("loot", location_name, context, profile_name)
    item_count = count if count is not None else rng.randint(2, 4)
    return [_random_item(profile, rng, source="loot", context=location_name) for _ in range(max(1, item_count))]


def generate_vendor_items(owner_name: str, context: str = "", count: int | None = None) -> list[dict[str, Any]]:
    profile_name = _vendor_profile_name(f"{owner_name} {context}")
    profile = VENDOR_PROFILES.get(profile_name, VENDOR_PROFILES["general"])
    rng = _rng("vendor", owner_name, context, profile_name)
    item_count = count if count is not None else rng.randint(5, 8)
    return [
        _random_item(profile, rng, source="vendor", context=owner_name, rarity_profile=profile_name)
        for _ in range(max(1, item_count))
    ]


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
    if category in EQUIPMENT_CATEGORIES:
        item["equipment_slot"] = equipment_slot_for_category(category) or str(item.get("equipment_slot") or "")
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
                if immunity:
                    immunities.append(immunity)
            elif effect_type in {"element_resistance", "element_damage_reduction", "resist_element"}:
                element = str(effect.get("element") or effect.get("target") or effect.get("attribute") or "").strip()
                if element:
                    resistances = summary["element_resistances"]
                    resistances[element] = max(_safe_int(resistances.get(element), 0), value)
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
) -> dict[str, Any]:
    categories, weights = zip(*profile)
    category = rng.choices(categories, weights=weights, k=1)[0]
    name, description, base_value = rng.choice(
        ITEM_TEMPLATES.get(category, [(CATEGORY_LABELS.get(category, "アイテム"), "", CATEGORY_BASE_VALUE.get(category, 5))])
    )
    if category in EQUIPMENT_CATEGORIES:
        rarity = _random_equipment_rarity(rng, rarity_profile)
    else:
        rarity = _random_stackable_rarity(rng, rarity_profile)
    item_value = _item_value_with_rarity(base_value, rarity, rng)
    quantity = _random_quantity(category, rng)
    loot_description = f"{context}で見つかる品。{description}" if source == "loot" and context else description
    return make_item(
        category,
        name=name,
        description=loot_description,
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
    if category in {"scroll", "magicrod"}:
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
            status = rng.choice(["poison", "bleed", "burn", "freeze", "sleep", "paralysis", "fear", "curse"])
            effects.append({"type": "status_immunity", "status": status, "value": 1})
        elif effect_type == "element_resistance":
            elements = [element_id for element_id in ELEMENT_IDS if element_id != "none"]
            element_id = rng.choice(elements)
            value = max(10, min(50, 10 + power * 2 + rng.randrange(0, 11)))
            effects.append({"type": "element_resistance", "element": element_id, "value": value})
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
        return f"状態異常無効: {status}"
    if effect_type in {"element_resistance", "element_damage_reduction", "resist_element"}:
        element = str(effect.get("element") or effect.get("target") or effect.get("attribute") or "").strip()
        label = tr_enum("element", element, language, fallback=element)
        if str(language or "").strip().lower().startswith("en"):
            return f"{label} damage reduction {value}%"
        return f"{label}ダメージ軽減 {value}%"
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
    if key in {"treasure", "reward", "rewards"}:
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
