from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .item_enchant import apply_equipment_level_caps
from .items import (
    EQUIPMENT_CATEGORIES,
    ITEM_CATEGORY_IDS,
    RARITY_ORDER,
    RARITY_POWER,
    WEAPON_CATEGORIES,
    equipment_slot_for_category,
    is_equipment_item,
    item_value,
    make_item,
    normalise_category,
    normalise_item_effects,
    normalise_item,
    normalise_rarity,
)


CRAFT_INTENT_DEFINITIONS = {
    "auto": {
        "label_ja": "おまかせ",
        "label_en": "Auto",
        "instruction": "Let the materials and craft roll decide the most natural result.",
    },
    "mix": {
        "label_ja": "混合",
        "label_en": "Mix",
        "instruction": "Prioritize mixing materials or item properties into a combined practical result.",
    },
    "synthesis": {
        "label_ja": "合成",
        "label_en": "Synthesis",
        "instruction": "Prioritize fusing multiple ingredients into a new item with a coherent identity.",
    },
    "smithing": {
        "label_ja": "鍛冶",
        "label_en": "Smithing",
        "instruction": "Prioritize metalwork, weapon improvement, armor improvement, or durable tools.",
    },
    "alchemy": {
        "label_ja": "錬金術",
        "label_en": "Alchemy",
        "instruction": "Prioritize potions, medicine, reagents, magical materials, or transmutation results.",
    },
    "cooking": {
        "label_ja": "料理",
        "label_en": "Cooking",
        "instruction": "Prioritize food, drink, meals, preserved food, or edible restorative results.",
    },
}

CRAFT_KIND_LABELS = {
    "equipment_upgrade": "武具強化",
    "equipment_create": "武具制作",
    "consumable": "消耗品",
    "cooking": "料理",
}

CONSUMABLE_CATEGORIES = {"medicine", "potion", "scroll", "magicrod", "food", "drink"}
COOKING_CATEGORIES = {"food", "drink", "material_plant"}
ALCHEMY_HINT_CATEGORIES = {"medicine", "potion", "material_liquid", "material_plant", "material_magical", "material_gem"}
SMITHING_HINT_CATEGORIES = {"material_ore", "material_metal"}
RARITY_UPGRADE_TARGETS = {
    "common": 8,
    "uncommon": 10,
    "rare": 12,
    "epic": 14,
    "legendary": 16,
    "artifact": 16,
}


@dataclass(frozen=True)
class CraftPlan:
    kind: str
    intent: str
    label: str
    base_target: int
    target: int
    base_rarity: str = "common"
    target_item_index: int = -1
    target_item_name: str = ""
    home_level: int = 0
    home_reduction: int = 0
    dangerous_area: bool = False
    danger_adjustment: int = 0
    material_rarity_steps: int = 0
    material_rarity_reduction: int = 0
    item_count_adjustment: int = 0
    non_food_penalty: int = 0
    result_category_hint: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "intent": craft_intent_payload(self.intent),
            "base_target": self.base_target,
            "target": self.target,
            "base_rarity": self.base_rarity,
            "target_item_index": self.target_item_index,
            "target_item_name": self.target_item_name,
            "home_level": self.home_level,
            "home_reduction": self.home_reduction,
            "dangerous_area": self.dangerous_area,
            "danger_adjustment": self.danger_adjustment,
            "material_rarity_steps": self.material_rarity_steps,
            "material_rarity_reduction": self.material_rarity_reduction,
            "item_count_adjustment": self.item_count_adjustment,
            "non_food_penalty": self.non_food_penalty,
            "result_category_hint": self.result_category_hint,
            "notes": list(self.notes),
        }


def normalise_craft_intent(value: Any) -> str:
    text = str(value or "auto").strip().casefold()
    aliases = {
        "": "auto",
        "automatic": "auto",
        "おまかせ": "auto",
        "任せる": "auto",
        "mixing": "mix",
        "混合": "mix",
        "synth": "synthesis",
        "combine": "synthesis",
        "合成": "synthesis",
        "鍛冶": "smithing",
        "smith": "smithing",
        "blacksmith": "smithing",
        "錬金": "alchemy",
        "錬金術": "alchemy",
        "brew": "alchemy",
        "調合": "alchemy",
        "料理": "cooking",
        "調理": "cooking",
        "cook": "cooking",
    }
    resolved = aliases.get(text, text)
    return resolved if resolved in CRAFT_INTENT_DEFINITIONS else "auto"


def craft_intent_payload(value: Any) -> dict[str, str]:
    intent = normalise_craft_intent(value)
    payload = dict(CRAFT_INTENT_DEFINITIONS[intent])
    payload["id"] = intent
    return payload


def craft_intent_from_action(action: str) -> str:
    text = str(action or "")
    lowered = text.casefold()
    if any(word in lowered or word in text for word in ("鍛冶", "鍛える", "強化", "武器", "防具", "装飾", "smith", "forge", "weapon", "armor")):
        return "smithing"
    if any(word in lowered or word in text for word in ("錬金", "調合", "薬", "ポーション", "alchemy", "brew", "potion", "medicine")):
        return "alchemy"
    if any(word in lowered or word in text for word in ("料理", "調理", "焼く", "煮る", "cook", "meal", "food", "drink")):
        return "cooking"
    if any(word in lowered or word in text for word in ("合成", "combine", "synthesis")):
        return "synthesis"
    if any(word in lowered or word in text for word in ("混ぜ", "混合", "mix")):
        return "mix"
    return "auto"


def is_craft_action_text(action: str) -> bool:
    text = str(action or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    craft_words = (
        "craft",
        "make",
        "create",
        "combine",
        "synthesize",
        "forge",
        "cook",
        "brew",
        "mix",
        "クラフト",
        "作る",
        "作成",
        "制作",
        "製作",
        "合成",
        "加工",
        "鍛冶",
        "料理",
        "調理",
        "調合",
        "錬金",
    )
    if not any(word in lowered or word in text for word in craft_words):
        return False
    return True


def craft_material_phrases(action: str) -> list[str]:
    text = str(action or "").strip()
    if not text:
        return []
    for result_marker in ("を作る", "を作成", "を製作", "をクラフト", "を作"):
        if result_marker in text:
            text = text.split(result_marker, 1)[0]
            for separator in ("で", "から"):
                if separator in text:
                    text = text.rsplit(separator, 1)[0]
                    break
            break
    separators = ["と", "、", ",", "，", "+", "＋", " / ", "/", " and ", " with "]
    for marker in ("を加工", "を合成", "をクラフト", "を強化", "を使", "から", "で作", "でクラフト", "to make", "into"):
        text = text.replace(marker, " ")
    pattern = "|".join(re.escape(separator) for separator in separators)
    parts = [part.strip(" 　[]()（）「」『』") for part in re.split(pattern, text) if part.strip(" 　[]()（）「」『』")]
    noise = {"クラフト", "合成", "料理", "調理", "鍛冶", "加工", "作成", "制作", "製作", "作る"}
    return [part for part in parts if part not in noise and len(part) <= 40]


def match_craft_candidate(
    phrase: str,
    candidates: list[dict[str, Any]],
    used_uuids: set[str],
) -> dict[str, Any] | None:
    target = str(phrase or "").strip()
    if not target:
        return None
    for candidate in candidates:
        item = candidate.get("item") if isinstance(candidate, dict) else {}
        item = item if isinstance(item, dict) else {}
        item_uuid = str(item.get("item_uuid") or "")
        if item_uuid in used_uuids:
            continue
        name = str(item.get("name") or "")
        if name and (name == target or target in name or name in target):
            return candidate
    return None


def craft_fallback_category(ingredients: list[dict[str, Any]], plan: CraftPlan | None = None) -> str:
    if plan is not None:
        if plan.kind == "equipment_upgrade" and 0 <= plan.target_item_index < len(ingredients):
            return str(normalise_item(ingredients[plan.target_item_index]).get("category") or "weapon_medium")
        if plan.kind == "equipment_create":
            return plan.result_category_hint or "weapon_medium"
        if plan.kind == "cooking":
            return "food"
        if plan.kind == "consumable":
            return plan.result_category_hint or "potion"
    for item in ingredients:
        category = str(item.get("category") or "")
        if category.startswith("weapon_") or category.startswith("armor_") or category.startswith("accessory_"):
            return category
    if any(str(item.get("category") or "") in COOKING_CATEGORIES for item in ingredients):
        return "food"
    return "potion"


def determine_craft_plan(
    ingredients: list[dict[str, Any]],
    craft_intent: str = "auto",
    *,
    home_level: int = 0,
    dangerous_area: bool = False,
) -> CraftPlan:
    items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
    intent = normalise_craft_intent(craft_intent)
    kind = _classify_craft_kind(items, intent)
    base_rarity = _base_rarity_for_kind(items, kind)
    base_target = 10 if kind == "equipment_create" else RARITY_UPGRADE_TARGETS.get(base_rarity, 8)
    home_level = max(0, _safe_int(home_level, 0))
    home_reduction = home_level // 2
    danger_adjustment = 2 if dangerous_area else 0
    material_steps = _material_rarity_steps(items, kind)
    material_reduction = material_steps // 2
    item_count_adjustment = 0
    if len(items) >= 3 and kind == "equipment_create":
        item_count_adjustment = -2
    elif len(items) >= 3 and kind in {"cooking", "consumable"}:
        item_count_adjustment = 2
    non_food_penalty = 0
    if kind == "cooking":
        non_food_penalty = sum(1 for item in items if str(item.get("category") or "") not in COOKING_CATEGORIES) * 8
    target = max(
        2,
        base_target - home_reduction - material_reduction + danger_adjustment + item_count_adjustment + non_food_penalty,
    )
    target_index = 0 if kind == "equipment_upgrade" and items else -1
    target_name = str(items[target_index].get("name") or "") if target_index >= 0 else ""
    return CraftPlan(
        kind=kind,
        intent=intent,
        label=CRAFT_KIND_LABELS.get(kind, kind),
        base_target=base_target,
        target=target,
        base_rarity=base_rarity,
        target_item_index=target_index,
        target_item_name=target_name,
        home_level=home_level,
        home_reduction=home_reduction,
        dangerous_area=bool(dangerous_area),
        danger_adjustment=danger_adjustment,
        material_rarity_steps=material_steps,
        material_rarity_reduction=material_reduction,
        item_count_adjustment=item_count_adjustment,
        non_food_penalty=non_food_penalty,
        result_category_hint=_result_category_hint(items, kind, intent),
    )


def craft_preview_text(plan: CraftPlan) -> str:
    return f"種別:{plan.label} / 予想目標値:{plan.target}"


def build_craft_result(
    response: dict[str, Any],
    ingredients: list[dict[str, Any]],
    craft_roll: dict[str, Any],
    plan: CraftPlan,
    *,
    player_level: int = 1,
) -> dict[str, Any] | None:
    if bool(craft_roll.get("critical_failure")):
        return None
    items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
    if plan.kind == "equipment_upgrade":
        return _build_equipment_upgrade_result(response, items, craft_roll, plan, player_level=player_level)
    if plan.kind == "equipment_create":
        return _build_equipment_create_result(response, items, craft_roll, plan, player_level=player_level)
    if plan.kind == "cooking":
        return _build_cooking_result(response, items, craft_roll, plan)
    return _build_consumable_result(response, items, craft_roll, plan)


def craft_items(
    ingredients: list[dict[str, Any]],
    language: str = "ja",
    craft_roll: dict[str, Any] | None = None,
    craft_intent: str = "auto",
    *,
    home_level: int = 0,
    dangerous_area: bool = False,
    player_level: int = 1,
) -> tuple[dict[str, Any] | None, str]:
    items = [normalise_item(item) for item in ingredients if isinstance(item, dict)]
    if len(items) < 2:
        return None, "素材を2つ以上選んでください。"
    plan = determine_craft_plan(items, craft_intent, home_level=home_level, dangerous_area=dangerous_area)
    roll = dict(craft_roll or {"success": True, "target": plan.target, "total": plan.target})
    if roll.get("critical_failure"):
        return None, "クラフトに強制失敗しました。素材はすべて失われました。"
    result = build_craft_result({}, items, roll, plan, player_level=player_level)
    if not result:
        return None, "クラフトに失敗しました。素材は失われました。"
    return result, f"{result.get('name') or item_label(result, language=language)} を作成しました。{craft_quality_message(roll)}".strip()


def craft_quality_message(craft_roll: dict[str, Any] | None) -> str:
    if not isinstance(craft_roll, dict):
        return ""
    if craft_roll.get("critical_success"):
        return "会心の出来です。"
    target = _safe_int(craft_roll.get("target"), 10)
    total = _safe_int(craft_roll.get("total"), 0)
    if total >= target + 8:
        return "極めて良い出来です。"
    if total >= target + 4:
        return "非常に良い出来です。"
    if total >= target + 2:
        return "良い出来です。"
    if craft_roll.get("success"):
        return "安定した出来です。"
    return "粗い出来ですが形になりました。"


def _classify_craft_kind(items: list[dict[str, Any]], intent: str) -> str:
    if items and is_equipment_item(items[0]):
        return "equipment_upgrade"
    categories = {str(item.get("category") or "") for item in items}
    if intent == "cooking" or (intent == "auto" and categories & COOKING_CATEGORIES):
        return "cooking"
    if intent == "smithing" or categories & SMITHING_HINT_CATEGORIES:
        return "equipment_create"
    if intent == "alchemy" or categories & ALCHEMY_HINT_CATEGORIES or categories & CONSUMABLE_CATEGORIES:
        return "consumable"
    return "consumable"


def _base_rarity_for_kind(items: list[dict[str, Any]], kind: str) -> str:
    if not items:
        return "common"
    if kind in {"equipment_upgrade", "consumable", "cooking"}:
        return normalise_rarity(items[0].get("rarity"))
    return "common"


def _result_category_hint(items: list[dict[str, Any]], kind: str, intent: str) -> str:
    if kind == "equipment_upgrade" and items:
        return str(items[0].get("category") or "weapon_medium")
    if kind == "equipment_create":
        for item in items:
            category = str(item.get("category") or "")
            if category in EQUIPMENT_CATEGORIES:
                return category
        return "weapon_medium"
    if kind == "cooking":
        return "food"
    if intent == "alchemy":
        return "potion"
    return "potion"


def _material_rarity_steps(items: list[dict[str, Any]], kind: str) -> int:
    if kind == "equipment_upgrade":
        materials = items[1:]
    elif kind == "cooking":
        materials = items[1:]
    elif kind == "equipment_create":
        materials = items
    else:
        materials = []
    return sum(_rarity_rank(str(item.get("rarity") or "common")) for item in materials)


def _build_equipment_upgrade_result(
    response: dict[str, Any],
    items: list[dict[str, Any]],
    craft_roll: dict[str, Any],
    plan: CraftPlan,
    *,
    player_level: int,
) -> dict[str, Any] | None:
    if not items:
        return None
    base = normalise_item(items[0], source="craft")
    if not bool(craft_roll.get("success")):
        returned = deepcopy(base)
        returned["craft_result_kind"] = plan.kind
        returned["craft_failed_returned_target"] = True
        returned["craft_roll"] = dict(craft_roll)
        return returned
    old_rarity = normalise_rarity(base.get("rarity"))
    old_attack = _safe_int(base.get("attack"), 0)
    old_defense = _safe_int(base.get("defense"), 0)
    if old_rarity == "artifact":
        new_rarity = "artifact"
        stat_delta = 6 if bool(craft_roll.get("critical_success")) else 3
    else:
        steps = 2 if bool(craft_roll.get("critical_success")) else 1
        new_rarity = _shift_rarity(old_rarity, steps)
        stat_delta = max(1, RARITY_POWER.get(new_rarity, 1) - RARITY_POWER.get(old_rarity, 1))
    raw = _response_item(response)
    name = _safe_name(raw, str(base.get("name") or "装備"))
    description = str(raw.get("description") or raw.get("desc") or base.get("description") or "")
    category = str(base.get("category") or "weapon_medium")
    result = make_item(category, name=name, description=description, rarity=new_rarity, quantity=1, source="craft")
    if category in WEAPON_CATEGORIES:
        result["attack"] = max(_safe_int(result.get("attack"), 0), old_attack + stat_delta)
        if old_defense:
            result["defense"] = max(_safe_int(result.get("defense"), 0), old_defense)
    else:
        result["defense"] = max(_safe_int(result.get("defense"), 0), old_defense + stat_delta)
        if old_attack:
            result["attack"] = max(_safe_int(result.get("attack"), 0), old_attack)
    result["effects"] = _dedupe_effects(_as_list(base.get("effects")) + _as_list(result.get("effects")))[:8]
    result["llm_effects"] = _dedupe_effects(_as_list(base.get("llm_effects")) + _as_list(result.get("llm_effects")))[:4]
    apply_equipment_level_caps(result, player_level, seed=_craft_enchant_seed(plan, craft_roll, items))
    result["craft_result_kind"] = plan.kind
    result["upgraded_from"] = str(base.get("name") or "")
    result["craft_ingredients"] = _collect_item_uuids(items)
    result["craft_roll"] = dict(craft_roll)
    return normalise_item(result, source="craft", fallback_category=category)


def _build_equipment_create_result(
    response: dict[str, Any],
    items: list[dict[str, Any]],
    craft_roll: dict[str, Any],
    plan: CraftPlan,
    *,
    player_level: int,
) -> dict[str, Any]:
    raw = _response_item(response)
    category = normalise_category(str(raw.get("category") or plan.result_category_hint or "weapon_medium"))
    if category not in EQUIPMENT_CATEGORIES:
        category = plan.result_category_hint if plan.result_category_hint in EQUIPMENT_CATEGORIES else "weapon_medium"
    rarity = "common" if not bool(craft_roll.get("success")) else _equipment_creation_rarity(craft_roll)
    name = _safe_name(raw, "クラフト装備")
    description = str(raw.get("description") or raw.get("desc") or "素材から制作された装備。")
    value = _scaled_price(_ingredient_value_total(items), craft_roll)
    result = make_item(category, name=name, description=description, value=value, rarity=rarity, quantity=1, source="craft")
    apply_equipment_level_caps(result, player_level, seed=_craft_enchant_seed(plan, craft_roll, items))
    result["craft_result_kind"] = plan.kind
    result["craft_ingredients"] = _collect_item_uuids(items)
    result["craft_roll"] = dict(craft_roll)
    return normalise_item(result, source="craft", fallback_category=category)


def _build_consumable_result(
    response: dict[str, Any],
    items: list[dict[str, Any]],
    craft_roll: dict[str, Any],
    plan: CraftPlan,
) -> dict[str, Any]:
    raw = _response_item(response)
    category = normalise_category(str(raw.get("category") or plan.result_category_hint or "potion"))
    if category not in CONSUMABLE_CATEGORIES or category in COOKING_CATEGORIES:
        category = "potion"
    rarity = _upgrade_result_rarity(plan.base_rarity, craft_roll)
    effects = _combined_consumable_effects(items, craft_roll)
    name = _safe_name(raw, "合成消耗品")
    description = str(raw.get("description") or raw.get("desc") or "素材を調合して作られた消耗品。")
    value = _scaled_price(_ingredient_value_total(items), craft_roll)
    result = make_item(
        category,
        name=name,
        description=description,
        value=value,
        rarity=rarity,
        quantity=1,
        source="craft",
        effects=effects,
    )
    result["craft_effect_multiplier"] = _consumable_effect_multiplier(craft_roll)
    result["craft_result_kind"] = plan.kind
    result["craft_ingredients"] = _collect_item_uuids(items)
    result["craft_roll"] = dict(craft_roll)
    return normalise_item(result, source="craft", fallback_category=category)


def _build_cooking_result(
    response: dict[str, Any],
    items: list[dict[str, Any]],
    craft_roll: dict[str, Any],
    plan: CraftPlan,
) -> dict[str, Any]:
    raw = _response_item(response)
    category = normalise_category(str(raw.get("category") or "food"))
    if category not in COOKING_CATEGORIES:
        category = "food"
    rarity = _upgrade_result_rarity(plan.base_rarity, craft_roll)
    effects = _combined_consumable_effects(items, craft_roll)
    name = _safe_name(raw, "料理")
    description = str(raw.get("description") or raw.get("desc") or "素材を調理して作られた料理。")
    value = _scaled_price(_ingredient_value_total(items), craft_roll)
    result = make_item(
        category,
        name=name,
        description=description,
        value=value,
        rarity=rarity,
        quantity=1,
        source="craft",
        effects=effects,
    )
    result["craft_effect_multiplier"] = _consumable_effect_multiplier(craft_roll)
    result["craft_result_kind"] = plan.kind
    result["craft_ingredients"] = _collect_item_uuids(items)
    result["craft_roll"] = dict(craft_roll)
    return normalise_item(result, source="craft", fallback_category=category)


def _response_item(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    raw = response.get("item") or response.get("crafted_item") or response.get("result")
    if isinstance(raw, dict):
        return dict(raw)
    return {
        "name": str(response.get("name") or ""),
        "category": str(response.get("category") or ""),
        "description": str(response.get("description") or response.get("narration") or ""),
        "rarity": str(response.get("rarity") or ""),
    }


def _equipment_creation_rarity(craft_roll: dict[str, Any]) -> str:
    target = _safe_int(craft_roll.get("target"), 10)
    total = _safe_int(craft_roll.get("total"), target)
    if total >= target + 8:
        return "epic"
    if total >= target + 4:
        return "rare"
    if total >= target + 2:
        return "uncommon"
    return "common"


def _upgrade_result_rarity(base_rarity: str, craft_roll: dict[str, Any]) -> str:
    base = normalise_rarity(base_rarity)
    if not bool(craft_roll.get("success")):
        return base
    return _shift_rarity(base, 2 if bool(craft_roll.get("critical_success")) else 1)


def _shift_rarity(rarity: str, steps: int) -> str:
    index = min(len(RARITY_ORDER) - 1, max(0, _rarity_rank(rarity) + max(0, int(steps or 0))))
    return RARITY_ORDER[index]


def _scaled_price(base_value: int, craft_roll: dict[str, Any]) -> int:
    base_value = max(0, int(base_value or 0))
    if bool(craft_roll.get("critical_success")):
        factor = 2.0
    elif bool(craft_roll.get("success")):
        factor = 1.2
    else:
        factor = 0.5
    return max(1, int(base_value * factor + 0.5))


def _ingredient_value_total(items: list[dict[str, Any]]) -> int:
    return sum(item_value(item) * max(1, _safe_int(item.get("quantity"), 1)) for item in items)


def _consumable_effect_multiplier(craft_roll: dict[str, Any]) -> int:
    if bool(craft_roll.get("critical_success")):
        return 3
    if bool(craft_roll.get("success")):
        return 2
    return 1


def _combined_consumable_effects(items: list[dict[str, Any]], craft_roll: dict[str, Any]) -> list[dict[str, Any]]:
    multiplier = _consumable_effect_multiplier(craft_roll)
    heal_totals: dict[str, int] = {}
    damage_effects: dict[str, dict[str, Any]] = {}
    add_status: dict[str, dict[str, Any]] = {}
    remove_status_types: list[str] = []
    spawn_effects: list[dict[str, Any]] = []
    for item in items:
        quantity = max(1, _safe_int(item.get("quantity"), 1))
        for effect in normalise_item_effects(item.get("effects")):
            effect_type = str(effect.get("type") or "")
            if effect_type in {"heal_hp", "heal_sp", "heal_hunger"}:
                heal_totals[effect_type] = heal_totals.get(effect_type, 0) + max(0, _safe_int(effect.get("power"), 0)) * quantity
                continue
            if effect_type == "damage_hp":
                extra = effect.get("extra") if isinstance(effect.get("extra"), dict) else {}
                key = f"{extra.get('damage_type') or 'physical'}|{extra.get('dependency_status') or ''}"
                current = damage_effects.setdefault(
                    key,
                    {"type": "damage_hp", "power": 0, "extra": dict(extra)},
                )
                current["power"] = _safe_int(current.get("power"), 0) + max(0, _safe_int(effect.get("power"), 0)) * quantity
                continue
            if effect_type == "spawn_item":
                spawn_effects.append(deepcopy(effect))
                continue
            if effect_type == "add_status":
                extra = effect.get("extra") if isinstance(effect.get("extra"), dict) else {}
                status_type = str(extra.get("status_type") or "").strip()
                if not status_type:
                    continue
                current = add_status.setdefault(
                    status_type,
                    {
                        "type": "add_status",
                        "power": 0,
                        "extra": dict(extra),
                    },
                )
                current["power"] = _safe_int(current.get("power"), 0) + _safe_int(effect.get("power"), 0) * quantity
                current_extra = current.get("extra") if isinstance(current.get("extra"), dict) else {}
                current_extra["status_duration"] = max(
                    _safe_int(current_extra.get("status_duration"), 0),
                    _safe_int(extra.get("status_duration"), 0),
                )
                current_extra["gain_rate"] = max(
                    _safe_float(current_extra.get("gain_rate"), 1.0),
                    _safe_float(extra.get("gain_rate"), 1.0),
                )
                current["extra"] = current_extra
                continue
            if effect_type == "remove_status":
                extra = effect.get("extra") if isinstance(effect.get("extra"), dict) else {}
                status_types = extra.get("status_type")
                if isinstance(status_types, list):
                    remove_status_types.extend(str(value) for value in status_types if str(value).strip())
    combined: list[dict[str, Any]] = []
    for effect_type, power in heal_totals.items():
        if power > 0:
            combined.append({"type": effect_type, "power": max(1, power * multiplier)})
    for effect in damage_effects.values():
        power = max(0, _safe_int(effect.get("power"), 0))
        if power > 0:
            effect["power"] = max(1, power * multiplier)
            combined.append(effect)
    for effect in add_status.values():
        power = _safe_int(effect.get("power"), 0)
        if power:
            effect["power"] = power * multiplier
        combined.append(effect)
    unique_removals = _dedupe_texts(remove_status_types)
    if unique_removals:
        combined.append({"type": "remove_status", "extra": {"status_type": unique_removals}})
    combined.extend(_dedupe_effects(spawn_effects))
    return normalise_item_effects(combined)


def _safe_name(raw: dict[str, Any], fallback: str) -> str:
    text = str(raw.get("name") or raw.get("item_name") or raw.get("title") or "").strip()
    return text or fallback


def _rarity_rank(rarity: str) -> int:
    value = normalise_rarity(rarity)
    return RARITY_ORDER.index(value) if value in RARITY_ORDER else 0


def _collect_item_uuids(items: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for item in items:
        raw = item.get("item_uuids")
        if isinstance(raw, list):
            result.extend(str(value) for value in raw if str(value).strip())
            continue
        value = str(item.get("item_uuid") or "").strip()
        if value:
            result.append(value)
    return result


def _craft_enchant_seed(plan: CraftPlan, craft_roll: dict[str, Any], items: list[dict[str, Any]]) -> str:
    ingredient_keys = [
        str(item.get("item_uuid") or item.get("name") or item.get("template_id") or "")
        for item in items
    ]
    return "|".join(
        [
            plan.kind,
            str(plan.target),
            str(plan.result_category_hint),
            str(craft_roll.get("total", "")),
            str(craft_roll.get("critical_success", "")),
            *ingredient_keys,
        ]
    )


def _dedupe_effects(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = repr(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(deepcopy(value))
    return result


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
