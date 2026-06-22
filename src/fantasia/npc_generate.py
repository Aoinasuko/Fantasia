from __future__ import annotations

import json
import random
import re
from typing import TYPE_CHECKING, Any

from .character import Character
from .npc_templates import (
    ENEMY_NPC_TEMPLATE_CATEGORIES,
    FRIENDLY_NPC_TEMPLATE_CATEGORIES,
    choose_npc_template,
    merge_npc_template_payload,
    npc_template_ai_context,
    npc_template_ids_from_payloads,
    npc_template_prompt_summaries,
    npc_templates_for_categories,
    npc_template_to_character_payload,
    used_npc_template_ids,
)
from .quests import (
    INTERNAL_QUEST_TOKEN_LABELS,
    _quest_ai_context,
    _quest_destination_source_text,
)
from .world_generation import _clamp_world_danger
from .world_model import LocationData, QuestData, WorldData

if TYPE_CHECKING:
    from .game import GameEngine


NPC_DEFAULT_POWER_BUDGET = 8
NPC_ATTRIBUTE_GENERATED_FLAG = "npc_attributes_generated"
NPC_ATTRIBUTE_PROFILE_KEY = "npc_attribute_profile"
NPC_MAX_LEVEL = 50
CHARACTER_DEFAULT_ATTRIBUTES = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}


def _game_helpers():
    from . import game

    return game


def _safe_int(value: Any, fallback: int = 0) -> int:
    return _game_helpers()._safe_int(value, fallback)


def _as_bool(value: Any) -> bool:
    return _game_helpers()._as_bool(value)


def _as_list(value: Any) -> list[Any]:
    return _game_helpers()._as_list(value)


def _as_str_list(value: Any) -> list[str]:
    return _game_helpers()._as_str_list(value)


def _dedupe_strs(values: list[str]) -> list[str]:
    return _game_helpers()._dedupe_strs(values)


def _clean_generated_name(value: Any, fallback: str, *, kind: str = "actor") -> str:
    return _game_helpers()._clean_generated_name(value, fallback, kind=kind)


def _unique_character_name(world: WorldData, name: str) -> str:
    return _game_helpers()._unique_character_name(world, name)


def _world_has_dead_npc_identity(world: WorldData, *, name: str = "", uuid: str = "") -> bool:
    return world_has_dead_npc_identity(world, name=name, uuid=uuid)


def _normalise_skill(value: Any) -> dict[str, Any]:
    return _game_helpers()._normalise_skill(value)


def _trait_entry(value: Any) -> dict[str, Any]:
    return _game_helpers()._trait_entry(value)


def _normalise_actor_power_loadout(character: Character) -> None:
    _game_helpers()._normalise_actor_power_loadout(character)


def _character_runtime_attributes(character: Character) -> dict[str, int]:
    attrs: dict[str, Any] = {}
    if isinstance(character.attributes, dict):
        attrs.update(character.attributes)
    if isinstance(character.extra, dict):
        direct = character.extra.get("attributes")
        if isinstance(direct, dict):
            attrs.update(direct)
        ability = character.extra.get("ability")
        if isinstance(ability, dict) and isinstance(ability.get("attributes"), dict):
            attrs.update(ability["attributes"])
    resolved = {
        key: max(1, _safe_int(attrs.get(key), default))
        for key, default in CHARACTER_DEFAULT_ATTRIBUTES.items()
    }
    resolved["magic"] = max(1, _safe_int(attrs.get("magic", attrs.get("mag", resolved["int"])), resolved["int"]))
    resolved["will"] = max(1, _safe_int(attrs.get("will", resolved["wis"]), resolved["wis"]))
    return resolved


def _npc_attribute_base_for_level(level: Any) -> int:
    resolved = max(1, min(NPC_MAX_LEVEL, _safe_int(level, 1)))
    return 10 + int(round((resolved - 1) * 5 / 9))


def _npc_attribute_seed(character: Character) -> str:
    return f"{character.uuid}:{character.name}:{character.role}:{character.category}"


def _npc_tendency_text(character: Character) -> str:
    parts: list[Any] = [
        character.name,
        character.role,
        character.category,
        character.backstory,
        character.personality,
        character.look,
        character.image_generation_prompt,
        character.skills,
        character.traits,
    ]
    if isinstance(character.extra, dict):
        for key in (
            "archetype",
            "occupation",
            "role_label",
            "title",
            "display_alias",
            "description",
            "ability",
            "raw_create_settlement_detail_entry",
            "raw_field_event_enemy",
        ):
            if key in character.extra:
                parts.append(_npc_tendency_part(character.extra.get(key)))
    if isinstance(character.flags, dict):
        for key in ("source", "enemy_npc", "hostile", "guard", "generated_dungeon_boss"):
            if key in character.flags:
                parts.append(character.flags.get(key))
    return json.dumps(parts, ensure_ascii=False, default=str).casefold()


def _npc_tendency_part(value: Any, *, max_chars: int = 600, _depth: int = 0, _seen: set[int] | None = None) -> Any:
    if value in (None, ""):
        return ""
    if isinstance(value, (str, int, float, bool)):
        text = str(value)
        return text[:max_chars]
    if _seen is None:
        _seen = set()
    ident = id(value)
    if ident in _seen:
        return ""
    _seen.add(ident)
    if _depth >= 2:
        return str(value)[:max_chars]
    if isinstance(value, list):
        return [_npc_tendency_part(item, max_chars=max(120, max_chars // 2), _depth=_depth + 1, _seen=_seen) for item in value[:8]]
    if isinstance(value, dict):
        allowed = (
            "name",
            "role",
            "category",
            "description",
            "overview",
            "summary",
            "type",
            "kind",
            "element",
            "npc_template_id",
            "npc_template_source",
            "generated_dungeon_boss",
            "boss_npc",
        )
        return {
            key: _npc_tendency_part(value.get(key), max_chars=max(120, max_chars // 2), _depth=_depth + 1, _seen=_seen)
            for key in allowed
            if key in value
        }
    return str(value)[:max_chars]


def _npc_is_boss_like(character: Character) -> bool:
    text = _npc_tendency_text(character)
    return bool(
        character.flags.get("generated_dungeon_boss")
        or character.flags.get("boss_npc")
        or character.extra.get("generated_dungeon_boss")
        or character.extra.get("boss_npc")
        or str(character.role or "").casefold() in {"boss", "ボス", "ダンジョンボス"}
        or "boss" in str(character.category or "").casefold()
        or any(word in text for word in ("boss", "ボス", "首領", "支配者"))
    )


def _npc_attribute_weights(character: Character) -> dict[str, int]:
    text = _npc_tendency_text(character)
    weights = {key: 0 for key in CHARACTER_DEFAULT_ATTRIBUTES}
    keyword_map = {
        "str": (
            "warrior", "fighter", "knight", "soldier", "guard", "mercenary", "brute", "berserker", "blacksmith",
            "beast", "monster", "giant", "orc", "ogre", "dragon", "weapon", "sword", "axe", "hammer",
            "戦士", "騎士", "兵士", "衛兵", "傭兵", "山賊", "鍛冶", "力", "腕力", "怪力", "剛腕", "獣", "巨人", "竜", "鬼",
        ),
        "dex": (
            "thief", "rogue", "ranger", "archer", "hunter", "assassin", "scout", "ninja", "dancer", "artisan",
            "craft", "quick", "agile", "bow", "knife", "trap", "sneak",
            "盗賊", "斥候", "狩人", "弓", "暗殺", "忍者", "踊り", "器用", "素早", "細工", "罠", "短剣",
        ),
        "con": (
            "defender", "guardian", "tank", "miner", "laborer", "veteran", "golem", "undead", "shield",
            "sturdy", "tough", "hardy", "armor", "heavy",
            "守護", "防衛", "盾", "重装", "頑丈", "屈強", "鉱夫", "労働", "不死", "ゴーレム", "耐久", "体力",
        ),
        "int": (
            "mage", "wizard", "witch", "sorcerer", "scholar", "alchemist", "researcher", "sage", "engineer",
            "magic", "spell", "book", "scroll", "tactician", "strategist",
            "魔術", "魔法", "魔女", "魔導", "学者", "錬金", "研究", "賢者", "知識", "書", "巻物", "策士", "軍師",
        ),
        "wis": (
            "priest", "cleric", "healer", "monk", "druid", "elder", "shaman", "oracle", "saint", "spirit",
            "calm", "wise", "judge", "will", "faith",
            "司祭", "僧侶", "治療", "白魔", "修道", "長老", "巫女", "神官", "聖者", "精霊", "冷静", "判断", "意志", "信仰",
        ),
        "cha": (
            "merchant", "shopkeeper", "innkeeper", "bard", "noble", "leader", "mayor", "guild master", "princess",
            "negotiator", "diplomat", "idol", "performer", "charming",
            "商人", "店主", "女将", "宿屋", "吟遊", "貴族", "村長", "ギルドマスター", "姫", "交渉", "外交", "魅力", "芸人",
        ),
    }
    for key, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword and keyword.casefold() in text:
                weights[key] += 2
    if any(word in text for word in ("boss", "ボス", "首領", "長", "王", "支配者")):
        weights["str"] += 1
        weights["con"] += 2
        weights["wis"] += 1
    if any(word in text for word in ("hostile", "enemy", "enemy_npc", "敵", "魔物", "怪物")):
        weights["str"] += 1
        weights["con"] += 1
    if any(word in text for word in ("tentacle", "slime", "触手", "スライム", "粘液")):
        weights["dex"] += 1
        weights["con"] += 2
    if not any(weights.values()):
        rng = random.Random(f"npc-attribute-profile:{_npc_attribute_seed(character)}")
        keys = tuple(CHARACTER_DEFAULT_ATTRIBUTES)
        weights[keys[rng.randrange(len(keys))]] += 2
        weights[keys[rng.randrange(len(keys))]] += 1
    return weights


def _npc_profile_order(character: Character, weights: dict[str, int]) -> list[str]:
    rng = random.Random(f"npc-attribute-order:{_npc_attribute_seed(character)}")
    tie_breaker = {key: rng.random() for key in CHARACTER_DEFAULT_ATTRIBUTES}
    return sorted(CHARACTER_DEFAULT_ATTRIBUTES, key=lambda key: (-weights.get(key, 0), tie_breaker[key]))


def _npc_profile_attributes(character: Character, base: int, *, boss: bool = False) -> dict[str, int]:
    weights = _npc_attribute_weights(character)
    order = _npc_profile_order(character, weights)
    level = max(1, min(NPC_MAX_LEVEL, _safe_int(character.level, 1)))
    primary_bonus = max(2, min(7, 1 + (level + 4) // 5))
    secondary_bonus = max(1, primary_bonus // 2)
    tertiary_bonus = 1 if level >= 10 else 0
    attrs = {key: base for key in CHARACTER_DEFAULT_ATTRIBUTES}
    if order:
        attrs[order[0]] += primary_bonus
    if len(order) > 1:
        attrs[order[1]] += secondary_bonus
    if tertiary_bonus and len(order) > 2 and weights.get(order[2], 0) > 0:
        attrs[order[2]] += tertiary_bonus
    if boss:
        attrs["con"] += 2
        attrs[order[0] if order else "str"] += 1
    character.extra[NPC_ATTRIBUTE_PROFILE_KEY] = ",".join(order[:2])
    return attrs


def _npc_attributes_need_generation(character: Character, attrs: dict[str, int]) -> bool:
    if character.extra.get(NPC_ATTRIBUTE_GENERATED_FLAG) or character.flags.get(NPC_ATTRIBUTE_GENERATED_FLAG):
        return True
    values = [_safe_int(attrs.get(key), CHARACTER_DEFAULT_ATTRIBUTES[key]) for key in CHARACTER_DEFAULT_ATTRIBUTES]
    return len(set(values)) <= 1


def _npc_level_tendency_attributes(
    character: Character,
    attrs: dict[str, int],
    *,
    boss: bool = False,
    force: bool = False,
) -> dict[str, int]:
    if not isinstance(character, Character) or character.flags.get("is_player"):
        return attrs
    boss = boss or _npc_is_boss_like(character)
    if (character.extra.get("npc_template_id") or character.flags.get("npc_template_id")) and not force:
        resolved = {
            key: max(1, _safe_int(attrs.get(key), CHARACTER_DEFAULT_ATTRIBUTES[key]))
            for key in CHARACTER_DEFAULT_ATTRIBUTES
        }
        resolved["magic"] = max(1, _safe_int(attrs.get("magic", attrs.get("mag", resolved["int"])), resolved["int"]))
        resolved["will"] = max(1, _safe_int(attrs.get("will", resolved["wis"]), resolved["wis"]))
        return resolved
    base = _npc_attribute_base_for_level(character.level)
    if force or _npc_attributes_need_generation(character, attrs):
        resolved = _npc_profile_attributes(character, base, boss=boss)
        character.extra[NPC_ATTRIBUTE_GENERATED_FLAG] = True
        character.flags[NPC_ATTRIBUTE_GENERATED_FLAG] = True
    else:
        resolved = {
            key: max(base + max(0, _safe_int(attrs.get(key), CHARACTER_DEFAULT_ATTRIBUTES[key]) - CHARACTER_DEFAULT_ATTRIBUTES[key]), base)
            for key in CHARACTER_DEFAULT_ATTRIBUTES
        }
    resolved["magic"] = max(_safe_int(attrs.get("magic", attrs.get("mag", resolved["int"])), resolved["int"]), resolved["int"])
    resolved["will"] = max(_safe_int(attrs.get("will", resolved["wis"]), resolved["wis"]), resolved["wis"])
    return resolved


def _character_calculated_max_hp(character: Character) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    return max(10, 8 + level * 3 + attrs["con"] * 2 + attrs["str"] // 2 + attrs["will"] // 3)


def _character_calculated_max_sp(character: Character, *, max_hp: int | None = None) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    resolved_max_hp = max_hp if max_hp is not None else _character_calculated_max_hp(character)
    return max(6, int(resolved_max_hp * 0.45) + attrs["magic"] + attrs["will"] + level * 2)


def _character_calculated_attack(character: Character) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    return max(1, level + attrs["str"] // 3 + attrs["dex"] // 5)


def _character_calculated_defense(character: Character) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    return max(0, level // 2 + attrs["con"] // 4 + attrs["wis"] // 6)


def _danger_scaled_level_floor(danger: Any, *, boss: bool = False) -> int:
    resolved = _clamp_world_danger(danger)
    base = 1 + int(round(resolved * 0.72))
    if boss:
        base += 8
    return max(1, min(NPC_MAX_LEVEL, base))


def _scale_character_for_danger(character: Character, danger: Any, *, boss: bool = False) -> None:
    if not isinstance(character, Character) or character.flags.get("is_player"):
        return
    resolved_danger = _clamp_world_danger(danger)
    boss = bool(boss or _npc_is_boss_like(character))
    if boss:
        character.flags["boss_npc"] = True
        character.extra["boss_npc"] = True
    level_floor = _danger_scaled_level_floor(resolved_danger, boss=boss)
    if _safe_int(character.level, 1) < level_floor:
        character.level = level_floor

    attrs = _character_runtime_attributes(character)
    attrs = _npc_level_tendency_attributes(character, attrs, boss=boss)
    character.attributes = attrs
    character.extra["attributes"] = dict(attrs)
    ability = character.extra.setdefault("ability", {})
    if isinstance(ability, dict):
        ability["attributes"] = dict(attrs)
    character.flags["danger_level"] = resolved_danger
    character.extra["danger_level"] = resolved_danger

    old_max_hp = max(0, _safe_int(character.max_hp, 0))
    old_current_hp = max(0, _safe_int(character.current_hp, 0))
    calculated_hp = _character_calculated_max_hp(character)
    if old_max_hp <= 0 or old_max_hp < calculated_hp:
        character.max_hp = calculated_hp
        if old_current_hp <= 0 or old_current_hp >= old_max_hp:
            character.current_hp = calculated_hp
        else:
            character.current_hp = min(calculated_hp, old_current_hp)
    calculated_sp = _character_calculated_max_sp(character, max_hp=character.max_hp)
    if _safe_int(character.max_sp, 0) < calculated_sp:
        character.max_sp = calculated_sp
        if _safe_int(character.current_sp, 0) <= 0:
            character.current_sp = calculated_sp
    calculated_attack = _character_calculated_attack(character)
    calculated_defense = _character_calculated_defense(character)
    template_controlled = bool(character.extra.get("npc_template_id") or character.flags.get("npc_template_id"))
    if template_controlled:
        if _safe_int(character.attack, 0) <= 0:
            character.attack = calculated_attack
        if _safe_int(character.defense, 0) <= 0:
            character.defense = calculated_defense
    else:
        character.attack = max(_safe_int(character.attack, 0), calculated_attack)
        character.defense = max(_safe_int(character.defense, 0), calculated_defense)


def _danger_scaled_placeholder_enemy(name: str, danger: Any) -> Character:
    character = Character(name=str(name or "Enemy"), role="敵対者", category="enemy_npc")
    _scale_character_for_danger(character, danger)
    return character


def _character_state_is_dead(character: Character) -> bool:
    state = str(character.state or character.flags.get("state") or "").strip().lower()
    if state in {"dead", "corpse", "killed"}:
        return True
    if character.flags.get("dead") is True or character.flags.get("alive") is False:
        return True
    return False


def _npc_from_raw(item: Any, index: int) -> Character:
    if isinstance(item, dict):
        data = dict(item)
        name = _clean_generated_name(
            data.get("name") or data.get("character_name") or data.get("npc_name"),
            f"NPC {index + 1}",
            kind="character",
        )
        category = str(data.get("category") or data.get("npc_category") or "npc")
        role = str(data.get("role") or data.get("occupation") or data.get("job") or category)
        character = Character.from_dict(data, default_name=name)
        character.name = name
        character.category = category
        character.role = role
        description = str(data.get("description") or data.get("backstory") or data.get("summary") or "")
        if description and not character.backstory:
            character.backstory = description
        if data.get("personality") and not character.personality:
            character.personality = str(data.get("personality"))
        if data.get("look") and not character.look:
            character.look = str(data.get("look"))
        if data.get("appearance") and not character.look:
            character.look = str(data.get("appearance"))
        if description and not character.look:
            character.look = description
        if data.get("image_generation_prompt") and not character.image_generation_prompt:
            character.image_generation_prompt = _as_str_list(data.get("image_generation_prompt"))
        if data.get("skills"):
            character.skills = [skill for skill in (_normalise_skill(item) for item in _as_list(data.get("skills"))) if skill.get("name")]
        if data.get("traits"):
            character.traits = [trait for trait in (_trait_entry(item) for item in _as_list(data.get("traits"))) if trait.get("name")]
        _normalise_actor_power_loadout(character)
        if data.get("aliases"):
            character.extra["aliases"] = _as_str_list(data.get("aliases"))
        if data.get("description"):
            character.extra["description"] = str(data.get("description"))
        if data.get("occupation"):
            character.extra["occupation"] = str(data.get("occupation"))
        if data.get("archetype"):
            character.extra["archetype"] = str(data.get("archetype"))
        return character
    return Character(
        name=f"NPC {index + 1}",
        role="npc",
        category="npc",
        backstory=str(item),
    )


def _enemy_npc_from_raw(item: Any, index: int) -> Character:
    if isinstance(item, dict):
        data = dict(item)
        name = _clean_generated_name(
            data.get("name") or data.get("monster_name") or data.get("enemy_name"),
            f"Enemy {index + 1}",
            kind="monster",
        )
        category = str(data.get("category") or data.get("monster_category") or data.get("type") or "wild_encounter")
        description = str(data.get("description") or data.get("summary") or data.get("overview") or "")
        character = Character.from_dict(data, default_name=name)
        character.name = name
        character.role = str(data.get("role") or data.get("role_label") or category or "敵対者")
        character.category = "enemy_npc"
        if description and not character.backstory:
            character.backstory = description
        if not character.gender:
            character.gender = str(data.get("gender") or "none")
        if not character.age:
            character.age = str(data.get("age") or "unknown")
        if data.get("personality") and not character.personality:
            character.personality = str(data.get("personality"))
        if description and not character.look:
            character.look = description
        if data.get("image_generation_prompt"):
            character.image_generation_prompt = _as_str_list(data.get("image_generation_prompt"))
            character.prompts["image_generation_prompt"] = _as_str_list(data.get("image_generation_prompt"))
        if data.get("skills"):
            character.skills = [skill for skill in (_normalise_skill(item) for item in _as_list(data.get("skills"))) if skill.get("name")]
        if data.get("traits"):
            character.traits = [trait for trait in (_trait_entry(item) for item in _as_list(data.get("traits"))) if trait.get("name")]
        character.flags["enemy_npc"] = True
        character.flags["hostile"] = _as_bool(data.get("hostile", True))
        character.extra["aliases"] = _dedupe_strs([name, category, "敵", "魔物", *[str(value) for value in _as_list(data.get("aliases"))]])
        character.extra["description"] = description
        character.extra.setdefault("raw_field_event_enemy", data)
        _normalise_actor_power_loadout(character)
        return character
    return Character(
        name=f"Enemy {index + 1}",
        role="敵対者",
        category="enemy_npc",
        backstory=str(item),
        look=str(item),
        flags={"enemy_npc": True, "hostile": True},
    )


def npc_generation_requests(response: dict[str, Any]) -> list[Any]:
    for key in (
        "new_npc_requests",
        "new_npc_request",
        "npc_requests",
        "npc_request",
        "new_npcs",
        "needed_npcs",
        "required_npcs",
        "npc_to_generate",
        "npcs_to_generate",
    ):
        if key not in response:
            continue
        value = response.get(key)
        if value is True:
            return [{"reason": key}]
        if value:
            return _as_list(value)
    return []


def infer_npc_generation_requests(response: dict[str, Any], action: str, location: str, world: WorldData) -> list[Any]:
    gh = _game_helpers()
    inferred: list[Any] = []
    for item in _as_list(response.get("recipients")):
        name = _clean_generated_name(item, "", kind="character")
        if should_generate_npc_name(world, name, location=location):
            inferred.append(
                {
                    "name": name,
                    "role": "npc",
                    "reason": "master_ai_facilitator named this recipient, but the character is not registered yet.",
                    "location": location,
                }
            )

    for item in _collect_nested_npc_requests(response):
        inferred.append(item)

    text_blob = json.dumps(gh._strip_response_metadata(response), ensure_ascii=False)
    for name in _extract_npc_candidate_names(action + "\n" + text_blob):
        if should_generate_npc_name(world, name, location=location):
            inferred.append(
                {
                    "name": name,
                    "role": "npc",
                    "reason": "The recent narration or choices refer to this unregistered NPC.",
                    "location": location,
                }
            )
    return inferred


def dedupe_npc_requests(requests: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in requests:
        if isinstance(item, dict):
            data = dict(item)
            name = _clean_generated_name(
                data.get("name") or data.get("character_name") or data.get("npc_name") or "",
                "",
                kind="character",
            )
            if name:
                data["name"] = name
            key = json.dumps(
                {
                    "name": name,
                    "role": data.get("role") or data.get("occupation") or data.get("job") or data.get("category") or "",
                    "reason": data.get("reason") or data.get("description") or data.get("summary") or "",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            value: Any = data
        else:
            name = _clean_generated_name(item, "", kind="character")
            key = name or str(item)
            value = {"name": name, "reason": str(item)} if name else item
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def filter_npc_generation_requests(
    requests: list[Any],
    world: WorldData,
    location: str,
    player_name: str,
) -> list[Any]:
    result: list[Any] = []
    for item in requests:
        name = npc_request_name(item)
        if name and not should_generate_npc_name(world, name, location=location, player_name=player_name):
            continue
        if _npc_request_matches_existing_scene_character(item, world, location, player_name):
            continue
        if _npc_request_is_player(item, world, player_name):
            continue
        result.append(item)
    return result


def npc_request_name(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_generated_name(
            value.get("name") or value.get("character_name") or value.get("npc_name") or value.get("target") or value.get("recipient"),
            "",
            kind="character",
        )
    return _clean_generated_name(value, "", kind="character")


def _npc_request_terms(value: Any) -> list[str]:
    if isinstance(value, dict):
        terms: list[str] = []
        for key in (
            "name",
            "character_name",
            "npc_name",
            "target",
            "recipient",
            "role",
            "occupation",
            "job",
            "title",
            "alias",
        ):
            cleaned = _clean_generated_name(value.get(key), "", kind="character")
            if cleaned:
                terms.append(cleaned)
        for key in ("aliases", "tags"):
            for item in _as_list(value.get(key)):
                cleaned = _clean_generated_name(item, "", kind="character")
                if cleaned:
                    terms.append(cleaned)
        return _dedupe_strs(terms)
    name = _clean_generated_name(value, "", kind="character")
    return [name] if name else []


def _npc_request_matches_existing_scene_character(value: Any, world: WorldData, location: str, player_name: str) -> bool:
    terms = _npc_request_terms(value)
    if not terms:
        return False
    gh = _game_helpers()
    for term in terms:
        if gh._existing_scene_character_matches(world, term, location, player_name):
            return True
    return False


def _npc_request_is_player(value: Any, world: WorldData, player_name: str) -> bool:
    gh = _game_helpers()
    return any(gh._is_player_reference(term, world, player_name) for term in _npc_request_terms(value))


def _collect_nested_npc_requests(value: Any, depth: int = 0) -> list[Any]:
    if depth > 5:
        return []
    if isinstance(value, dict):
        result: list[Any] = []
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in {
                "new_npc_request",
                "new_npc_requests",
                "npc_request",
                "npc_requests",
                "needed_npc",
                "needed_npcs",
                "required_npc",
                "required_npcs",
                "npc_to_generate",
                "npcs_to_generate",
            }:
                result.extend(_as_list(item))
                continue
            result.extend(_collect_nested_npc_requests(item, depth + 1))
        return result
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            result.extend(_collect_nested_npc_requests(item, depth + 1))
        return result
    return []


def _extract_npc_candidate_names(text: str) -> list[str]:
    source = str(text or "")
    names: list[str] = []
    patterns = (
        r"([^\s、。.「」『』（）\[\]{}:：]{2,20})(?:に話しかける|と話す|に会う)",
        r"(?:talk to|speak to|ask|meet)\s+([A-Za-z][A-Za-z0-9 _'\-]{1,32})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source, flags=re.IGNORECASE):
            cleaned = _clean_generated_name(match.group(1), "", kind="character")
            if cleaned:
                names.append(cleaned)
    return _dedupe_strs(names)


def should_generate_npc_name(
    world: WorldData,
    name: str,
    *,
    location: str = "",
    player_name: str = "",
) -> bool:
    if not name:
        return False
    if name == world.world_name or world.has_character_name(name):
        return False
    if world_has_dead_npc_identity(world, name=name):
        return False
    lowered = name.lower()
    if lowered in {"player", "pc", "npc", "character", "unknown", "monster", "enemy", "hero", "protagonist", "you"}:
        return False
    gh = _game_helpers()
    if gh._is_player_reference(name, world, player_name):
        return False
    if gh._existing_scene_character_matches(world, name, location, player_name):
        return False
    return True


def world_has_dead_npc_identity(world: WorldData, *, name: str = "", uuid: str = "") -> bool:
    extra = world.extra if isinstance(world.extra, dict) else {}
    dead_names = extra.get("dead_npc_names")
    if name and isinstance(dead_names, list):
        if any(str(item) == name for item in dead_names):
            return True
    dead_uuids = extra.get("dead_npc_uuids")
    if uuid and isinstance(dead_uuids, list):
        if any(str(item) == uuid for item in dead_uuids):
            return True
    return False


def npc_template_used_ids(engine: GameEngine, world: WorldData | None = None) -> set[str]:
    return used_npc_template_ids(world or engine.state.world_data)


def npc_template_categories_for_objective(objective_role: str) -> tuple[str, ...]:
    role = str(objective_role or "").strip()
    if role in {"defeat_target", "blocker", "boss", "enemy", "opponent"}:
        return ENEMY_NPC_TEMPLATE_CATEGORIES
    return FRIENDLY_NPC_TEMPLATE_CATEGORIES


def npc_template_danger_for_location(engine: GameEngine, location_name: str) -> int:
    return engine._current_location_danger(location_name)


def select_npc_template(
    engine: GameEngine,
    *,
    categories: tuple[str, ...],
    danger_level: int,
    seed: str,
    payloads: tuple[Any, ...] = (),
) -> dict[str, Any] | None:
    preferred_ids = npc_template_ids_from_payloads(*payloads)
    return choose_npc_template(
        categories,
        danger_level=danger_level,
        preferred_ids=preferred_ids,
        used_ids=npc_template_used_ids(engine),
        seed=seed,
    )


def npc_template_character_payload(
    engine: GameEngine,
    template: dict[str, Any] | None,
    *,
    danger_level: int,
    seed: str,
    hostile: bool | None = None,
    boss: bool = False,
) -> dict[str, Any]:
    return npc_template_to_character_payload(
        template,
        danger_level=danger_level,
        enemy_strength=engine._enemy_strength_setting(),
        seed=seed,
        hostile=hostile,
        boss=boss,
    )


def npc_template_selection_text(raw: Any) -> tuple[str, str, str, str]:
    if isinstance(raw, dict):
        text_parts = [
            raw.get("name"),
            raw.get("role"),
            raw.get("category"),
            raw.get("npc_category"),
            raw.get("job"),
            raw.get("occupation"),
            raw.get("description"),
            raw.get("personality"),
            raw.get("look"),
            raw.get("appearance"),
        ]
        extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        flags = raw.get("flags") if isinstance(raw.get("flags"), dict) else {}
        text_parts.extend([extra.get("role_label"), extra.get("internal_role"), flags.get("source")])
        text = " ".join(str(part or "") for part in text_parts).casefold()
        gender = str(raw.get("gender") or "").strip().casefold()
        age = str(raw.get("age") or "").strip().casefold()
        role = " ".join(str(part or "") for part in (raw.get("role"), raw.get("category"), raw.get("job"), raw.get("occupation"))).casefold()
        return text, gender, age, role
    text = str(raw or "").casefold()
    return text, "", "", text


def score_npc_template_for_raw(template: dict[str, Any], raw: Any) -> int:
    text, gender, age, role = npc_template_selection_text(raw)
    template_id = str(template.get("id") or "").casefold()
    template_text = " ".join(
        str(part or "")
        for part in (
            template.get("id"),
            template.get("name"),
            template.get("role"),
            template.get("gender"),
            template.get("age"),
            template.get("category"),
        )
    ).casefold()
    score = 0
    template_gender = str(template.get("gender") or "").strip().casefold()
    binary_genders = {"male", "female"}
    if gender and template_gender:
        if gender == template_gender:
            score += 8
        elif gender in binary_genders and template_gender in binary_genders:
            score -= 10
    raw_child = any(term in f"{age} {role} {text}" for term in ("child", "kid", "boy", "girl", "teen", "young", "子供", "少年", "少女"))
    raw_adult = any(term in f"{age} {role} {text}" for term in ("adult", "grown", "elder", "old", "20", "30", "40", "50", "60", "大人", "成人", "老人"))
    template_child = "child" in template_id or any(term in template_text for term in ("child", "kid", "子供", "少年", "少女"))
    if raw_child:
        score += 7 if template_child else -2
    if raw_adult and template_child:
        score -= 9
    if any(term in role or term in text for term in ("merchant", "shop", "keeper", "store", "vendor", "facility")):
        score += 6 if "merchant" in template_id or "merchant" in template_text else 0
    if any(term in role or term in text for term in ("resident", "villager", "civilian")):
        score += 5 if "resident" in template_id or "residents" in template_id else 0
    if any(term in role or term in text for term in ("adventurer", "guard", "soldier", "hunter", "mercenary")):
        if not template_child:
            score += 3
    raw_elf = "elf" in text or "エルフ" in text
    template_elf = "elf" in template_id or "elf" in template_text or "エルフ" in template_text
    if raw_elf:
        score += 6 if template_elf else 0
    elif template_elf:
        score -= 2
    for term in re.split(r"[^a-z0-9_]+", role):
        if len(term) >= 4 and term in template_text:
            score += 2
    return score


def choose_npc_template_for_raw(
    engine: GameEngine,
    raw: Any,
    *,
    categories: tuple[str, ...],
    danger_level: int,
    seed: str,
    preferred_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    if preferred_ids:
        return choose_npc_template(
            categories,
            danger_level=danger_level,
            preferred_ids=preferred_ids,
            used_ids=npc_template_used_ids(engine),
            seed=seed,
        )
    candidates = npc_templates_for_categories(
        categories,
        danger_level=danger_level,
        used_ids=npc_template_used_ids(engine),
    )
    if not candidates:
        return None
    rng = random.Random(seed or f"npc-template:{danger_level}:{','.join(categories)}")
    scored = [(score_npc_template_for_raw(template, raw), rng.random(), template) for template in candidates]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]


def template_augmented_npc_raw(
    engine: GameEngine,
    raw: Any,
    *,
    categories: tuple[str, ...],
    danger_level: int,
    seed: str,
    hostile: bool | None = None,
    boss: bool = False,
    select_without_id: bool = True,
) -> dict[str, Any]:
    payloads = (raw,) if isinstance(raw, dict) else ()
    preferred_ids = npc_template_ids_from_payloads(*payloads)
    if not preferred_ids and not select_without_id:
        return dict(raw) if isinstance(raw, dict) else {"name": str(raw or "")}
    template = choose_npc_template_for_raw(
        engine,
        raw,
        categories=categories,
        danger_level=danger_level,
        preferred_ids=preferred_ids,
        seed=seed,
    )
    template_payload = npc_template_character_payload(
        engine,
        template,
        danger_level=danger_level,
        seed=seed,
        hostile=hostile,
        boss=boss,
    )
    return merge_npc_template_payload(template_payload, raw)


def generated_npc_level(
    engine: GameEngine,
    character: Character,
    *,
    location_name: str = "",
    danger_level: int | None = None,
    role_hint: str = "",
    boss: bool = False,
) -> int:
    danger = _clamp_world_danger(
        danger_level if danger_level is not None else npc_template_danger_for_location(engine, location_name)
    )
    role_text = " ".join(
        str(part or "")
        for part in (
            role_hint,
            character.category,
            character.role,
            character.flags.get("source"),
            character.flags.get("quest_objective_role"),
            character.extra.get("role_label"),
            character.extra.get("internal_role"),
            character.extra.get("npc_template_category"),
        )
    ).casefold()
    boss = bool(boss or _npc_is_boss_like(character) or "boss" in role_text)
    if boss:
        target_level = _danger_scaled_level_floor(danger, boss=True)
    else:
        target_level = _danger_scaled_level_floor(danger)
        hostile = bool(
            character.flags.get("hostile")
            or character.extra.get("hostile")
            or character.flags.get("enemy_npc")
            or character.category == "enemy_npc"
        )
        combat_terms = (
            "adventurer",
            "blocker",
            "captain",
            "defeat_target",
            "enemy",
            "fighter",
            "guard",
            "guardian",
            "hunter",
            "mercenary",
            "monster",
            "opponent",
            "soldier",
            "warrior",
        )
        civilian_terms = (
            "child",
            "delivery_target",
            "facility",
            "keeper",
            "merchant",
            "resident",
            "rescue_target",
            "shop",
            "villager",
        )
        if hostile:
            target_level += max(1, danger // 5)
        elif any(term in role_text for term in combat_terms):
            target_level += 1
        elif any(term in role_text for term in civilian_terms):
            target_level = max(1, target_level - 2)

    base_level = max(
        _safe_int(character.level, 1),
        _safe_int(character.extra.get("base_level"), 1) if isinstance(character.extra, dict) else 1,
        _safe_int(character.extra.get("level"), 1) if isinstance(character.extra, dict) else 1,
    )
    return max(1, min(NPC_MAX_LEVEL, max(base_level, target_level)))


def finalize_generated_npc(
    engine: GameEngine,
    character: Character,
    *,
    location_name: str = "",
    danger_level: int | None = None,
    role_hint: str = "",
    boss: bool = False,
    sync_vitals_to_formula: bool = True,
) -> None:
    danger = _clamp_world_danger(
        danger_level if danger_level is not None else npc_template_danger_for_location(engine, location_name)
    )
    boss = bool(boss or _npc_is_boss_like(character))
    character.level = generated_npc_level(
        engine,
        character,
        location_name=location_name,
        danger_level=danger,
        role_hint=role_hint,
        boss=boss,
    )
    _scale_character_for_danger(character, danger, boss=boss)
    engine._ensure_character_runtime_data(
        character,
        level=character.level,
        sync_vitals_to_formula=sync_vitals_to_formula,
    )
    character.flags["danger_level"] = danger
    character.extra["danger_level"] = danger


def ensure_facility_npc(engine: GameEngine, settlement: LocationData, facility: dict[str, Any], location_name: str) -> Character | None:
    gh = _game_helpers()
    npc_name = str(facility.get("npc_name") or "").strip()
    if not npc_name:
        npc_name = gh._default_facility_npc_name(str(facility.get("name") or ""), str(facility.get("type") or ""))
        facility["npc_name"] = npc_name
    npc_payload = facility.get("npc") if isinstance(facility.get("npc"), dict) else {}
    npc_gender = str(facility.get("npc_gender") or npc_payload.get("gender") or "").strip()
    npc_age = str(facility.get("npc_age") or npc_payload.get("age") or "").strip()
    npc_look = str(
        facility.get("npc_look")
        or facility.get("npc_appearance")
        or npc_payload.get("look")
        or npc_payload.get("appearance")
        or ""
    ).strip()
    npc_personality = str(facility.get("npc_personality") or npc_payload.get("personality") or "").strip()
    if _world_has_dead_npc_identity(engine.state.world_data, name=npc_name):
        return None
    character = engine.state.world_data.character(npc_name)
    if character is None:
        danger_level = npc_template_danger_for_location(engine, settlement.name or location_name)
        npc_raw = template_augmented_npc_raw(
            engine,
            {
                "name": npc_name,
                "role": str(facility.get("npc_role") or gh._default_facility_role(str(facility.get("type") or ""))),
                "category": "facility_npc",
                "gender": npc_gender,
                "age": npc_age,
                "description": str(facility.get("description") or ""),
                "personality": npc_personality,
                "look": npc_look,
                "facility": str(facility.get("name") or ""),
                "facility_type": str(facility.get("type") or gh._facility_type_from_name(str(facility.get("name") or ""))),
            },
            categories=FRIENDLY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger_level,
            seed=f"facility-npc:{engine.state.world_name}:{settlement.name}:{npc_name}",
            hostile=False,
        )
        character = _npc_from_raw(npc_raw, len(engine.state.world_data.characters))
        character.name = _unique_character_name(engine.state.world_data, character.name)
        character.category = "facility_npc"
        facility["npc_name"] = character.name
        character.flags["source"] = "facility"
        character.flags["facility_name"] = str(facility.get("name") or "")
        character.flags["facility_type"] = str(facility.get("type") or gh._facility_type_from_name(str(facility.get("name") or "")))
        character.extra["facility"] = str(facility.get("name") or "")
        character.extra["facility_type"] = str(facility.get("type") or gh._facility_type_from_name(str(facility.get("name") or "")))
        character.extra["parent_settlement"] = settlement.name
        finalize_generated_npc(
            engine,
            character,
            location_name=settlement.name or location_name,
            danger_level=danger_level,
            role_hint="facility_npc",
        )
        engine.state.world_data.add_character(character)
    else:
        character.flags["facility_name"] = str(facility.get("name") or character.flags.get("facility_name") or "")
        character.flags["facility_type"] = str(facility.get("type") or character.flags.get("facility_type") or gh._facility_type_from_name(str(facility.get("name") or "")))
        character.extra["facility"] = str(facility.get("name") or character.extra.get("facility") or "")
        character.extra["facility_type"] = str(facility.get("type") or character.extra.get("facility_type") or gh._facility_type_from_name(str(facility.get("name") or "")))
        character.extra["parent_settlement"] = settlement.name
        if npc_gender and not character.gender:
            character.gender = npc_gender
        if npc_age and not character.age:
            character.age = npc_age
        if npc_look and not character.look:
            character.look = npc_look
        if npc_personality and not character.personality:
            character.personality = npc_personality
    subnode_id = engine._stamp_character_facility_subnode(character, settlement, facility)
    engine._set_character_presence(character, location_name, subnode_id=subnode_id)
    return character


def ensure_guard_character(engine: GameEngine, settlement: LocationData) -> Character:
    base_name = f"{settlement.name}の衛兵"
    character = engine.state.world_data.character(base_name)
    if character is None or _character_state_is_dead(character):
        name = base_name if character is None else _unique_character_name(engine.state.world_data, base_name)
        danger_level = npc_template_danger_for_location(engine, settlement.name)
        npc_raw = template_augmented_npc_raw(
            engine,
            {
                "name": name,
                "role": "衛兵",
                "category": "guard",
                "description": f"{settlement.name}の治安を守る衛兵。",
                "personality": "職務に忠実で、街中の犯罪者を見逃さない。",
                "flags": {"source": "crime_guard", "guard": True},
            },
            categories=FRIENDLY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger_level,
            seed=f"crime-guard:{engine.state.world_name}:{settlement.name}:{name}",
            hostile=False,
        )
        character = _npc_from_raw(npc_raw, len(engine.state.world_data.characters))
        character.name = name
        character.category = "guard"
        character.flags["source"] = "crime_guard"
        character.flags["guard"] = True
        finalize_generated_npc(
            engine,
            character,
            location_name=settlement.name,
            danger_level=danger_level,
            role_hint="guard",
        )
        engine.state.world_data.add_character(character)
    engine._set_character_presence(character, engine.state.current_location or settlement.name)
    return character


def quest_objective_npc_design(
    engine: GameEngine,
    quest: QuestData,
    location_name: str,
    subnode_id: str,
    response: dict[str, Any],
    *,
    objective_role: str,
) -> dict[str, Any]:
    gh = _game_helpers()
    fallback = gh._quest_objective_npc_fallback_design(quest, response, objective_role=objective_role)
    danger_level = npc_template_danger_for_location(engine, location_name)
    template = choose_npc_template_for_raw(
        engine,
        {
            "role": objective_role,
            "category": fallback.get("category") or objective_role,
            "name": fallback.get("name"),
            "description": fallback.get("description") or quest.overview,
            "gender": fallback.get("gender"),
            "age": fallback.get("age"),
            "extra": {
                "role_label": fallback.get("role_label"),
                "internal_role": objective_role,
            },
        },
        categories=npc_template_categories_for_objective(objective_role),
        danger_level=danger_level,
        seed=f"quest-objective:{engine.state.world_name}:{quest.name}:{objective_role}:{location_name}:{subnode_id}",
        preferred_ids=npc_template_ids_from_payloads(quest.extra, response),
    )
    template_payload = npc_template_character_payload(
        engine,
        template,
        danger_level=danger_level,
        seed=f"quest-objective-payload:{engine.state.world_name}:{quest.name}:{objective_role}:{location_name}:{subnode_id}",
        hostile=objective_role in {"defeat_target", "blocker"},
    )
    if template_payload:
        template_extra = template_payload.get("extra") if isinstance(template_payload.get("extra"), dict) else {}
        fallback.update(
            {
                "name": template_payload.get("name") or fallback.get("name"),
                "display_alias": template_payload.get("name") or fallback.get("display_alias"),
                "role_label": template_payload.get("role") or fallback.get("role_label"),
                "description": template_payload.get("description") or fallback.get("description"),
                "personality": template_payload.get("personality") or fallback.get("personality"),
                "gender": template_payload.get("gender") or fallback.get("gender"),
                "age": template_payload.get("age") or fallback.get("age"),
                "look": template_payload.get("look") or fallback.get("look"),
                "category": template_payload.get("category") or fallback.get("category"),
                "image_prompt": ", ".join(_as_str_list(template_payload.get("image_generation_prompt"))),
                "attack": template_payload.get("attack"),
                "defense": template_payload.get("defense"),
                "attributes": template_payload.get("attributes"),
                "skills": template_payload.get("skills") if "skills" in template_payload else fallback.get("skills"),
                "traits": template_payload.get("traits") if "traits" in template_payload else fallback.get("traits"),
                "attacks": template_extra.get("attacks") if isinstance(template_extra, dict) else [],
                "npc_template_id": template_extra.get("npc_template_id") if isinstance(template_extra, dict) else "",
                "npc_template_category": template_extra.get("npc_template_category") if isinstance(template_extra, dict) else "",
                "npc_template_payload": template_payload,
            }
        )
    location = engine.state.world_data.locations.get(location_name)
    subnode_context: dict[str, Any] = {}
    if location:
        try:
            graph = engine._ensure_location_subnode_graph(engine.state.world_data, location_name)
            node = graph.get("nodes", {}).get(subnode_id) if isinstance(graph, dict) else None
            if isinstance(node, dict):
                subnode_context = {
                    "id": subnode_id,
                    "name": str(node.get("name") or subnode_id),
                    "kind": str(node.get("kind") or ""),
                    "description": str(node.get("description") or ""),
                }
        except Exception:
            subnode_context = {"id": subnode_id}
    messages = [
        {
            "role": "system",
            "content": (
                "You design one concrete quest objective NPC for Fantasia. Return JSON only. "
                "Use the world tone, quest request, destination, and objective role to decide a player-facing name, "
                "epithet, role label, description, personality, age, gender, appearance, and whether the NPC is hostile. "
                "For a rescue blocker/captor/obstacle, make it match the request: if the quest implies tentacles, beasts, "
                "spirits, bandits, curses, or another non-human threat, do not default to a generic human. "
                "Do not output UUIDs or internal ids such as rescue_target, blocker, defeat_target, or delivery_target. "
                "Always include gender and age. Use gender=none and age=adult/ancient/unknown for non-human entities "
                "when a human age or binary gender is not meaningful. "
                "If npc_template is supplied, keep the same creature/person type and use it as the base; fill only "
                "missing flavor such as a concrete name variant, look details, personality details, skills, or traits. "
                "When traits are returned, each trait must contain only name and desc."
            ),
        },
        {
            "role": "user",
            "content": gh._ai_json(
                {
                    "objective_role": objective_role,
                    "fallback": fallback,
                    "quest": _quest_ai_context(quest, include_log=False, include_extra=True),
                    "destination": {
                        "location": location_name,
                        "location_kind": str((location.extra if location else {}).get("location_kind") or ""),
                        "danger_level": _safe_int((location.extra if location else {}).get("danger_level"), 0),
                        "description": str(location.description if location else ""),
                        "subnode": subnode_context,
                    },
                    "quest_response_hints": gh._compact_value(response, max_chars=1200),
                    "source_text": _quest_destination_source_text(quest, response),
                    "npc_template": npc_template_ai_context(template),
                }
            ),
        },
    ]
    try:
        generated = engine._chat_json(
            "quest_objective_npc_designer",
            messages,
            max_tokens=600,
            world_name=engine.state.world_name,
            player_name=engine.state.player_name,
        )
    except Exception as exc:
        fallback["designer_error"] = str(exc)
        return fallback

    design = dict(fallback)
    for key in ("name", "display_alias", "role_label", "description", "personality", "gender", "age", "look", "species", "category"):
        value = str(generated.get(key) or "").strip()
        if value:
            design[key] = value
    for key in ("skills", "traits", "attacks"):
        if key in generated and isinstance(generated.get(key), list):
            design[key] = generated.get(key)
    image_prompt = generated.get("image_prompt")
    if isinstance(image_prompt, list):
        image_prompt = ", ".join(str(item).strip() for item in image_prompt if str(item).strip())
    if str(image_prompt or "").strip():
        design["image_prompt"] = str(image_prompt).strip()
    aliases = [str(item).strip() for item in _as_list(generated.get("aliases")) if str(item).strip()]
    if aliases:
        design["aliases"] = aliases
    if "hostile" in generated:
        design["hostile"] = _as_bool(generated.get("hostile"))
    design["name"] = _clean_generated_name(design.get("name"), fallback.get("name") or "依頼対象", kind="character")
    if not str(design.get("display_alias") or "").strip():
        design["display_alias"] = design["name"]
    if not str(design.get("role_label") or "").strip():
        design["role_label"] = INTERNAL_QUEST_TOKEN_LABELS.get(objective_role, "依頼対象")
    return design


def create_quest_objective_npc(
    engine: GameEngine,
    quest: QuestData,
    location_name: str,
    subnode_id: str,
    response: dict[str, Any] | None = None,
    *,
    objective_role: str = "rescue_target",
) -> dict[str, Any]:
    gh = _game_helpers()
    response = response or {}
    design = quest_objective_npc_design(engine, quest, location_name, subnode_id, response, objective_role=objective_role)
    base_name = str(design.get("name") or gh._quest_objective_npc_name(quest, response, objective_role=objective_role))
    name = _unique_character_name(engine.state.world_data, base_name)
    role_label = str(design.get("role_label") or INTERNAL_QUEST_TOKEN_LABELS.get(objective_role, "依頼対象"))
    display_alias = str(design.get("display_alias") or name)
    aliases = _dedupe_strs([display_alias, role_label, *[str(item) for item in _as_list(design.get("aliases"))]])
    hostile = bool(design.get("hostile")) if "hostile" in design else objective_role in {"defeat_target", "blocker"}
    description = str(design.get("description") or response.get("objective_npc_description") or response.get("objective") or quest.overview)
    personality = str(design.get("personality") or response.get("objective_npc_personality") or "")
    look = str(design.get("look") or design.get("image_prompt") or "")
    image_prompts = _as_str_list(design.get("image_prompt") or design.get("image_generation_prompt"))
    if not image_prompts and look:
        image_prompts = [look]
    attributes = {
        key: max(1, _safe_int(value, CHARACTER_DEFAULT_ATTRIBUTES.get(key, 10)))
        for key, value in (design.get("attributes") if isinstance(design.get("attributes"), dict) else {}).items()
        if key in CHARACTER_DEFAULT_ATTRIBUTES
    }
    skills = [skill for skill in (_normalise_skill(item) for item in _as_list(design.get("skills"))) if skill.get("name")]
    traits = [trait for trait in (_trait_entry(item) for item in _as_list(design.get("traits"))) if trait.get("name")]
    attacks = [dict(item) for item in _as_list(design.get("attacks")) if isinstance(item, dict)]
    resistance = [dict(item) for item in _as_list(design.get("resistance")) if isinstance(item, dict)]
    npc_template_payload = design.get("npc_template_payload") if isinstance(design.get("npc_template_payload"), dict) else {}
    npc_template_extra = npc_template_payload.get("extra") if isinstance(npc_template_payload.get("extra"), dict) else {}
    npc_template_flags = npc_template_payload.get("flags") if isinstance(npc_template_payload.get("flags"), dict) else {}
    npc_template_id = str(design.get("npc_template_id") or npc_template_extra.get("npc_template_id") or "").strip()
    character = Character(
        name=name,
        role=role_label,
        category=str(design.get("category") or "quest_objective"),
        attack=max(0, _safe_int(design.get("attack"), 0)),
        defense=max(0, _safe_int(design.get("defense"), 0)),
        attributes=attributes,
        gender=str(design.get("gender") or ""),
        age=str(design.get("age") or ""),
        backstory=description,
        personality=personality,
        look=look,
        image_generation_prompt=[part for part in [*image_prompts, description] if part],
        skills=skills,
        traits=traits,
        resistance=resistance or _as_list(npc_template_payload.get("resistance")),
        flags={
            "source": "quest_objective",
            "quest_objective": True,
            "quest_name": quest.name,
            "quest_objective_kind": "npc",
            "quest_objective_role": objective_role,
            "hostile": hostile,
            "display_alias": display_alias,
            "role_label": role_label,
            **npc_template_flags,
        },
        extra={
            "quest_name": quest.name,
            "quest_objective": True,
            "quest_objective_role": objective_role,
            "internal_role": objective_role,
            "display_alias": display_alias,
            "role_label": role_label,
            "aliases": aliases,
            "species": str(design.get("species") or ""),
            "appearance_prompt": str(design.get("image_prompt") or look),
            "attacks": attacks or npc_template_extra.get("attacks") or [],
            "combat_attacks": attacks or npc_template_extra.get("combat_attacks") or [],
            "npc_template_id": npc_template_id,
            "npc_template_category": str(design.get("npc_template_category") or npc_template_extra.get("npc_template_category") or ""),
            "npc_template_source": str(npc_template_extra.get("npc_template_source") or ""),
            "objective_location": location_name,
            "objective_subnode_id": subnode_id,
            "origin_location": quest.extra.get("origin_location") or engine._quest_origin_location(quest),
            **npc_template_extra,
        },
        prompts={
            "character": str(design.get("image_prompt") or look),
            "quest_objective": description,
        },
    )
    finalize_generated_npc(
        engine,
        character,
        location_name=location_name,
        danger_level=npc_template_danger_for_location(engine, location_name),
        role_hint=objective_role,
        boss=objective_role == "boss",
    )
    engine._set_character_presence(character, location_name, "quest_objective", subnode_id=subnode_id)
    engine.state.world_data.add_character(character)
    return {
        "kind": "npc",
        "uuid": character.uuid,
        "name": character.name,
        "display_alias": display_alias,
        "role_label": role_label,
        "location": location_name,
        "subnode_id": subnode_id,
        "role": objective_role,
        "status": "waiting",
    }


def master_ai_npc_generater(
    engine: GameEngine,
    action: str,
    input_type: str,
    facilitator_response: dict[str, Any],
    requests: list[Any],
    location: str,
) -> dict[str, Any]:
    gh = _game_helpers()
    world_payload = gh._ai_json(engine._focused_world_ai_context(include_recent_log=False))
    facilitator_payload = json.dumps(gh._strip_response_metadata(facilitator_response), ensure_ascii=False)
    request_payload = json.dumps(requests, ensure_ascii=False)
    npc_template_payload = json.dumps(
        {
            "friendly_templates": npc_template_prompt_summaries(
                FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                danger_level=engine._current_location_danger(location),
                used_ids=npc_template_used_ids(engine),
                limit=12,
            )
        },
        ensure_ascii=False,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "あなたはAI駆動RPGのNPC生成担当です。"
                "Fantasiaのmaster_ai_npc_generater相当として、"
                "master_ai_facilitatorが必要とした未登録NPCを生成してください。"
                "NPCカテゴリ、説明、性格、外見、職業、archetype、skills、traitsを持つJSONだけを返してください。"
                "skillsは必ず name, desc, usesp(1-12), power(1-5), ability, element, type を持つ新形式にしてください。"
                "typeは heal_single, damage_hp_single, effect_enemy_single 等の戦闘効果ID配列です。"
                "traitsを返す場合は各traitを name と desc だけにしてください。"
                "resistanceを返す場合は [{type, amount}] とし、弱い耐性は0.2、強い耐性は0.5だけを使ってください。"
                "店主・一般NPCは合計8、通常NPCは8-12、終盤・精鋭・ボス級は16-25を目安にしてください。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界データ: {world_payload}\n"
                f"現在地: {location}\n"
                f"入力種別: {input_type}\n"
                f"プレイヤー行動: {action}\n"
                f"master_ai_facilitator応答: {facilitator_payload}\n"
                f"NPC生成要求: {request_payload}\n"
                "既存NPCと重複せず、現在の場面で自然に登場できるNPCを生成してください。"
            ),
        },
        {
            "role": "system",
            "content": (
                "NPC completeness rule: every generated NPC in npcs must include gender, age, look, and personality. "
                "Do not leave these blank. gender must be female, male, none, or a localized equivalent. age must be "
                "a visible age or age range; for monsters/non-humans use adult, young, ancient, or unknown if exact "
                "age is not meaningful. look must be concrete enough for character image generation."
            ),
        },
        {
            "role": "system",
            "content": (
                f"NPC template candidates: {npc_template_payload}\n"
                "Generate NPCs as world- and role-specific variations of these templates. "
                "If a generated NPC matches a template, include npc_template_id on that NPC object. "
                "The game will select a template locally if the id is absent. Keep the same character type "
                "and use the template as the base."
            ),
        },
    ]
    return engine._chat_json(
        "master_ai_npc_generater",
        messages,
        max_tokens=900,
        world_name=engine.state.world_name,
        player_name=engine.state.player_name,
    )


def npc_detail_generater(
    engine: GameEngine,
    action: str,
    input_type: str,
    facilitator_response: dict[str, Any],
    character: Character,
) -> dict[str, Any]:
    gh = _game_helpers()
    world_payload = gh._ai_json(engine._focused_world_ai_context(include_recent_log=False))
    character_payload = gh._ai_json(gh._character_ai_context(character))
    facilitator_payload = json.dumps(gh._strip_response_metadata(facilitator_response), ensure_ascii=False)
    power_instruction = gh._skill_power_instruction(character)
    messages = [
        {
            "role": "system",
            "content": (
                "あなたはAI駆動RPGのNPC詳細補完担当です。"
                "Fantasiaのnpc_detail_generater相当として、"
                "話し方、archetype、skills、会話トピック、行動方針を補完してください。"
                "必ずname, talk_style, archetype, skillsを持つJSONだけを返してください。"
                "skillsは必ず name, desc, usesp(1-12), power(1-5), ability, element, type を持つ新形式にしてください。"
                "typeは heal_single, damage_hp_single, effect_enemy_single 等の戦闘効果ID配列です。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界データ: {world_payload}\n"
                f"入力種別: {input_type}\n"
                f"プレイヤー行動: {action}\n"
                f"master_ai_facilitator応答: {facilitator_payload}\n"
                f"対象キャラクター: {character.name}\n"
                f"キャラクターデータ: {character_payload}\n"
                f"{power_instruction}\n"
                "このNPCを会話、探索、戦闘判定で使えるように詳細化してください。"
            ),
        },
        {
            "role": "user",
            "content": (
                "Base profile repair rule: if the target character is missing gender, age, look, personality, or "
                "image_generation_prompt, fill those fields in this response. Preserve already established facts. "
                "look must describe visible appearance and clothing/species traits; image_generation_prompt should "
                "be usable by a character image generator."
            ),
        },
    ]
    return engine._chat_json(
        "npc_detail_generater",
        messages,
        max_tokens=750,
        world_name=engine.state.world_name,
        player_name=engine.state.player_name,
    )


def apply_master_ai_npcs(engine: GameEngine, response: dict[str, Any], location: str) -> list[Character]:
    gh = _game_helpers()
    raw_npcs = _as_list(response.get("npcs") or response.get("characters") or response.get("npc"))
    generated: list[Character] = []
    danger_level = engine._current_location_danger(location)
    for item in raw_npcs:
        item = template_augmented_npc_raw(
            engine,
            item,
            categories=FRIENDLY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger_level,
            seed=f"master-ai-npc:{engine.state.world_name}:{location}:{len(generated)}",
            hostile=False,
        )
        character = _npc_from_raw(item, len(engine.state.world_data.characters) + len(generated))
        if world_has_dead_npc_identity(engine.state.world_data, name=character.name, uuid=character.uuid):
            continue
        character.name = _unique_character_name(engine.state.world_data, character.name)
        character.flags.setdefault("source", "master_ai_npc_generater")
        character.flags.setdefault("generated", True)
        if location:
            character.flags.setdefault("first_seen_location", location)
            engine._set_character_presence(character, location)
        finalize_generated_npc(
            engine,
            character,
            location_name=location,
            danger_level=danger_level,
            role_hint="master_ai_npc",
        )
        character.extra["raw_master_ai_npc_generater"] = gh._strip_response_metadata(response)
        engine.state.world_data.add_character(character)
        generated.append(character)

        engine.state.world_data.extra.setdefault("generated_npcs", []).append(
            {
                "manager": "master_ai_npc_generater",
                "name": character.name,
                "location": location,
                "response": gh._strip_response_metadata(response),
            }
        )
    return generated


def apply_npc_detail(engine: GameEngine, character: Character, response: dict[str, Any]) -> None:
    gh = _game_helpers()
    generated_name = str(response.get("name") or "").strip()
    if generated_name and generated_name != character.name:
        character.extra["detail_generated_name"] = generated_name
    if response.get("talk_style") is not None:
        character.extra["talk_style"] = str(response.get("talk_style") or "")
    if response.get("archetype") is not None:
        character.extra["archetype"] = str(response.get("archetype") or "")
    if response.get("gender") is not None and not character.gender:
        character.gender = str(response.get("gender") or "").strip()
    if response.get("age") is not None and not character.age:
        character.age = str(response.get("age") or "").strip()
    if response.get("personality") is not None and not character.personality:
        character.personality = str(response.get("personality") or "").strip()
    detail_look = str(response.get("look") or response.get("appearance") or "").strip()
    if detail_look and not character.look:
        character.look = detail_look
    if response.get("image_generation_prompt") is not None:
        prompt_parts = _as_str_list(response.get("image_generation_prompt"))
        if prompt_parts and not character.image_generation_prompt:
            character.image_generation_prompt = prompt_parts
            character.prompts["image_generation_prompt"] = prompt_parts
    if response.get("behavior_policy") is not None:
        character.extra["behavior_policy"] = str(response.get("behavior_policy") or "")
    if response.get("conversation_topics") is not None:
        character.extra["conversation_topics"] = _as_str_list(response.get("conversation_topics"))
    if response.get("memory_updates") is not None:
        character.extra["memory_updates"] = _as_list(response.get("memory_updates"))
    if response.get("relationship") is not None:
        character.extra["relationship"] = response.get("relationship")
    if response.get("resistance") is not None:
        character.resistance = [dict(item) for item in _as_list(response.get("resistance")) if isinstance(item, dict)]
    response_location = str(response.get("location") or response.get("current_location") or "").strip()
    if response_location:
        engine._set_character_presence(character, response_location, str(response.get("state") or character.state or "present"))
    elif character.location:
        engine._set_character_presence(character, character.location, character.state or "present")

    detail_skills = [_normalise_skill(item) for item in _as_list(response.get("skills"))]
    detail_skills = [skill for skill in detail_skills if skill.get("name")]
    if detail_skills:
        merged_skills = gh._merge_named_dicts(character.skills, detail_skills)
        character.skills = gh._limit_power_entries_for_actor(
            character,
            merged_skills,
            used_power=0,
        )
    engine._apply_response_status_effects(response, "npc_detail_generater", default_target=character.name, context_character=character)
    character.extra["raw_npc_detail_generater"] = gh._strip_response_metadata(response)
