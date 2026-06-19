from __future__ import annotations

import json
import re
from typing import Any

from .status_effects import _combat_status_effects_payload


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "はい"}
    return bool(value)


def _short_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def _compact_value(value: Any, *, max_chars: int = 1000, list_limit: int = 12, dict_limit: int = 16) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _short_text(value, max_chars)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [
            _compact_value(item, max_chars=max(160, max_chars // 2), list_limit=list_limit, dict_limit=dict_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= dict_limit:
                break
            key_text = str(key)
            if _is_ai_metadata_key(key_text):
                continue
            result[key_text] = _compact_value(
                item,
                max_chars=max(160, max_chars // 2),
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
        return _drop_empty(result)
    return _short_text(str(value), max_chars)


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in ("", None, [], {})}


def _is_ai_metadata_key(key: str) -> bool:
    return (
        key.startswith("_")
        or key.startswith("raw_")
        or key
        in {
            "history",
            "prompts",
            "image_paths",
            "image_pipeline",
            "generation_metadata",
            "postprocess",
            "source_response",
            "request",
            "request_params",
            "response_info",
            "prompt_debug",
        }
    )


def _game_controlled_hp_keys(target: str, *, top_level: bool = False) -> set[str]:
    if target == "opponent":
        return {
            "opponent_hp",
            "enemy_hp",
            "target_hp",
            "opponent_current_hp",
            "opponent_hp_delta",
            "enemy_hp_delta",
            "target_hp_delta",
            "opponent_damage_hp",
            "enemy_damage_hp",
            "target_damage_hp",
            "opponent_heal_hp",
            "enemy_heal_hp",
            "target_heal_hp",
        }
    keys = {
        "player_hp",
        "player_current_hp",
        "player_hp_delta",
        "hp_delta",
        "health_delta",
        "damage_hp",
        "hp_damage",
        "player_damage_hp",
        "harm_hp",
        "heal_hp",
        "healing",
        "restore_hp",
        "recover_hp",
        "hp_restore",
        "player_heal_hp",
        "player_recover_hp",
        "hp_effect",
        "hp_effects",
        "player_hp_effect",
        "player_hp_effects",
        "health_effect",
        "health_effects",
        "recovery_effect",
        "recovery_effects",
    }
    if top_level:
        keys.add("current_hp")
    return keys


def _strip_hp_update_value(value: Any, target: str) -> Any:
    if isinstance(value, list):
        return [_strip_hp_update_value(item, target) for item in value]
    if not isinstance(value, dict):
        return value
    blocked = _game_controlled_hp_keys(target)
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if str(key).strip().lower() in blocked:
            continue
        cleaned[key] = _strip_hp_update_value(item, target)
    return cleaned


def _combat_response_candidates(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    candidates = [response]
    for key in (
        "combat_judgement",
        "combat_judgment",
        "combat_result",
        "damage_judgement",
        "damage_judgment",
        "damage_calculation",
        "skill_judgement",
        "skill_judgment",
        "skill_calculation",
        "attack_result",
        "game_combat_result",
    ):
        value = response.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    return candidates


def _response_has_status_effect_update(value: Any, *, _depth: int = 0) -> bool:
    if _depth > 4 or value in (None, "", [], {}):
        return False
    status_keys = {
        "status_effect",
        "status_effects",
        "player_status",
        "player_status_effect",
        "player_status_effects",
        "add_player_status_effect",
        "add_player_status_effects",
        "opponent_status",
        "opponent_status_effect",
        "opponent_status_effects",
        "add_opponent_status_effect",
        "add_opponent_status_effects",
        "npc_status_effects",
        "character_status_effects",
        "long_term_statuses",
        "persistent_statuses",
    }
    if isinstance(value, list):
        return any(_response_has_status_effect_update(item, _depth=_depth + 1) for item in value)
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        key_text = str(key).strip().lower()
        if key_text in status_keys and item not in (None, "", [], {}):
            return True
        if key_text in {"encounter_update", "updates", "effects", "result"} and _response_has_status_effect_update(item, _depth=_depth + 1):
            return True
    return False


def _combat_value_from_response(response: Any, keys: tuple[str, ...]) -> Any:
    for candidate in _combat_response_candidates(response):
        for key in keys:
            if key in candidate and candidate.get(key) not in (None, ""):
                return candidate.get(key)
    return None


def _combat_weakness_multiplier(response: Any, default: float = 1.0) -> float:
    value = _combat_value_from_response(
        response,
        (
            "weakness_multiplier",
            "weakness_modifier",
            "weakness",
            "damage_multiplier",
            "effectiveness",
            "element_multiplier",
            "element_modifier",
            "multiplier",
        ),
    )
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        number_match = re.search(r"-?\d+(?:\.\d+)?", text)
        if number_match:
            value = number_match.group(0)
        elif any(word in text for word in ("immune", "無効", "効かない", "通らない")):
            return 0.0
        elif any(word in text for word in ("resist", "耐性", "軽減", "半減")):
            return 0.5
        elif any(word in text for word in ("very weak", "大弱点", "致命的", "critical")):
            return 2.0
        elif any(word in text for word in ("weak", "弱点", "有効")):
            return 1.5
        else:
            return default
    multiplier = _safe_float(value, default)
    if multiplier > 3 and multiplier <= 300:
        multiplier /= 100.0
    return max(0.0, min(3.0, multiplier))


def _combat_apply_defense(response: Any, *, default: bool) -> bool:
    ignore_value = _combat_value_from_response(response, ("ignore_defense", "pierce_defense", "defense_ignored"))
    if ignore_value not in (None, "") and _as_bool(ignore_value):
        return False
    value = _combat_value_from_response(
        response,
        ("apply_defense", "uses_defense", "use_defense", "defense_applies", "subtract_defense"),
    )
    if value in (None, ""):
        return default
    return _as_bool(value)


def _combat_ability_from_response(response: Any, *, skill: dict[str, Any], healing: bool) -> str:
    value = _combat_value_from_response(
        response,
        ("ability", "attribute", "ability_id", "attribute_id", "damage_ability", "scaling_attribute"),
    )
    ability = _normalise_combat_ability(value)
    if ability:
        return ability
    return _skill_default_ability(skill, healing=healing)


def _normalise_combat_ability(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    aliases = {
        "str": "str",
        "strength": "str",
        "power": "str",
        "筋力": "str",
        "力": "str",
        "dex": "dex",
        "dexterity": "dex",
        "agi": "dex",
        "agility": "dex",
        "器用": "dex",
        "敏捷": "dex",
        "con": "con",
        "constitution": "con",
        "endurance": "con",
        "耐久": "con",
        "int": "int",
        "intelligence": "int",
        "knowledge": "int",
        "知力": "int",
        "wis": "wis",
        "will": "will",
        "wisdom": "wis",
        "spirit": "will",
        "意志": "will",
        "精神": "wis",
        "cha": "cha",
        "charisma": "cha",
        "charm": "cha",
        "魅力": "cha",
        "交渉": "cha",
        "magic": "magic",
        "mag": "magic",
        "魔力": "magic",
    }
    return aliases.get(text, "")


def _skill_is_healing(skill: dict[str, Any], response: Any) -> bool:
    value = _combat_value_from_response(response, ("effect_type", "skill_effect", "intent", "result_type", "type"))
    text = " ".join(
        str(item or "")
        for item in (
            value,
            skill.get("name"),
            skill.get("skill_type"),
            skill.get("element"),
            skill.get("description"),
            skill.get("effect"),
            skill.get("effects"),
        )
    ).lower()
    return any(word in text for word in ("heal", "healing", "recover", "recovery", "restore", "cure", "treat", "回復", "治療", "癒", "応急"))


def _skill_default_uses_defense(skill: dict[str, Any]) -> bool:
    text = " ".join(str(skill.get(key) or "") for key in ("skill_type", "element", "category", "description", "effect")).lower()
    if any(word in text for word in ("magic", "spell", "arcane", "mental", "poison", "light", "dark", "fire", "water", "ice", "lightning")):
        return False
    if any(word in text for word in ("support", "heal", "healing", "recover", "回復", "治療", "補助")):
        return False
    return True


def _skill_default_ability(skill: dict[str, Any], *, healing: bool) -> str:
    text = " ".join(str(skill.get(key) or "") for key in ("skill_type", "element", "category", "description", "effect")).lower()
    if healing:
        return "wis"
    if any(word in text for word in ("physical", "weapon", "slash", "strike", "none", "物理")):
        return "str"
    if any(word in text for word in ("support", "mental", "spirit", "精神")):
        return "wis"
    if any(word in text for word in ("magic", "spell", "arcane", "fire", "water", "ice", "lightning", "earth", "wind", "light", "dark", "魔法", "魔力")):
        return "magic"
    if any(word in text for word in ("poison", "grass", "tool", "道具", "毒", "草")):
        return "dex"
    return "str"


def _combat_damage_message(damage: int, max_hp: int, *, action_name: str) -> str:
    hp = max(1, int(max_hp or 1))
    ratio = max(0.0, damage / hp)
    if damage <= 0:
        return f"{action_name}は通らず、相手に有効な傷を与えられなかった。"
    if damage <= 2 or ratio <= 0.05:
        return f"勢いよく{action_name}したが、かすり傷しか与えられなかった。"
    if ratio <= 0.15:
        return f"{action_name}が浅く入り、相手に小さな傷を負わせた。"
    if ratio <= 0.35:
        return f"{action_name}がしっかり命中し、確かなダメージを与えた。"
    if ratio <= 0.60:
        return f"重い{action_name}が入り、相手の体勢を大きく崩した。"
    return f"{action_name}が急所を捉え、致命的な傷を与えた。"


def _combat_heal_message(amount: int, skill_name: str) -> str:
    if amount <= 0:
        return f"> [戦闘] {skill_name}を使ったが、HPは回復しなかった。"
    if amount <= 5:
        return f"> [戦闘] {skill_name}で少し体勢を立て直した。"
    if amount <= 20:
        return f"> [戦闘] {skill_name}が傷を癒やし、HPを回復した。"
    return f"> [戦闘] {skill_name}が大きく傷を癒やし、HPを大幅に回復した。"


def _combat_narration_payload(combat_result: dict[str, Any]) -> dict[str, Any]:
    old_hp = _first_int(combat_result, ("old_hp", "player_old_hp"), 0)
    new_hp = _first_int(combat_result, ("new_hp", "player_new_hp"), old_hp)
    max_hp = max(1, _first_int(combat_result, ("max_hp", "player_max_hp"), max(old_hp, new_hp, 1)))
    damage = _first_int(combat_result, ("damage",), max(0, old_hp - new_hp))
    actual_damage = max(0, old_hp - new_hp)
    healing = _first_int(combat_result, ("actual_healing", "healing"), max(0, new_hp - old_hp))
    payload = {
        "type": combat_result.get("type"),
        "damage": damage,
        "actual_damage": actual_damage,
        "healing": healing,
        "old_hp": old_hp,
        "new_hp": new_hp,
        "max_hp": max_hp,
        "lethal": new_hp <= 0 and damage > 0,
        "weakness_multiplier": combat_result.get("weakness_multiplier"),
        "base_damage": combat_result.get("base_damage"),
        "attack": combat_result.get("attack"),
        "defense": combat_result.get("defense"),
        "ability": combat_result.get("ability"),
        "ability_score": combat_result.get("ability_score"),
        "power": combat_result.get("power"),
    }
    status_effects = _combat_status_effects_payload(combat_result.get("applied_status_effects"))
    if status_effects:
        payload["applied_status_effects"] = status_effects
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _first_int(data: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    for key in keys:
        if key in data:
            return _safe_int(data.get(key), default)
    return default


def _npc_response_is_offensive(*responses: Any) -> bool:
    texts: list[str] = []
    explicit: bool | None = None
    for response in responses:
        if not isinstance(response, dict):
            continue
        for candidate in _combat_response_candidates(response):
            for key in ("offensive", "attack", "attacks", "damage_intent", "hostile_action"):
                if key in candidate and candidate.get(key) not in (None, ""):
                    explicit = _as_bool(candidate.get(key))
        for key in ("npc_action", "action", "intent", "narration", "text", "message"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=400)
            texts.append(str(value or ""))
    if explicit is not None:
        return explicit
    joined = " ".join(texts).lower()
    if not joined.strip():
        return False
    if any(word in joined for word in ("降伏", "逃走", "退却", "交渉", "防御", "様子", "hesitate", "surrender", "flee", "defend", "negotiate")):
        return False
    return any(
        word in joined
        for word in (
            "攻撃",
            "襲",
            "斬",
            "刺",
            "殴",
            "噛",
            "爪",
            "撃つ",
            "矢",
            "魔法を放",
            "ダメージ",
            "attack",
            "strike",
            "slash",
            "stab",
            "bite",
            "claw",
            "shoot",
            "cast",
            "damage",
        )
    )


def _surrender_control_prevents_npc_damage(encounter: dict[str, Any], *responses: Any) -> bool:
    if not _encounter_player_surrendered(encounter):
        return False
    joined = _combat_action_text(*responses).lower()
    if not joined.strip():
        return False
    control_terms = (
        "accept_surrender",
        "surrender_accepted",
        "approach_and_entangle",
        "entangle",
        "restrain",
        "restrained",
        "capture",
        "bind",
        "grapple",
        "disarm",
        "watch",
        "guard",
        "拘束",
        "絡め",
        "絡み",
        "包み込",
        "包囲",
        "捕獲",
        "確保",
        "監視",
        "見張",
        "武装解除",
        "降伏を受け入",
        "屈服",
        "身を委ね",
        "警戒",
    )
    if not any(term in joined for term in control_terms):
        return False
    damaging_terms = (
        "damage",
        "hp",
        "kill",
        "strike",
        "slash",
        "stab",
        "bite",
        "claw",
        "shoot",
        "cast",
        "ダメージ",
        "殺",
        "致命",
        "襲",
        "斬",
        "刺",
        "殴",
        "噛",
        "爪",
        "裂",
        "貫",
        "焼",
        "燃",
        "締め付け",
        "締め上げ",
    )
    return not any(term in joined for term in damaging_terms)


def _player_surrender_response_ends_encounter(encounter: dict[str, Any], *responses: Any) -> bool:
    if not isinstance(encounter, dict):
        return False
    if _as_bool(encounter.get("capture_relocated")):
        return True
    if not _encounter_player_surrendered(encounter):
        return False
    joined = _combat_action_text(*responses).casefold()
    if not joined.strip():
        return False
    if _npc_response_is_offensive(*responses) and not _surrender_control_prevents_npc_damage(encounter, *responses):
        return False
    accept_terms = (
        "accept_surrender",
        "surrender_accepted",
        "player_surrendered",
        "capture",
        "captured",
        "restrain",
        "restrained",
        "watch",
        "guard",
        "disarm",
        "post_capture",
        "降伏を受け入",
        "降参を受け入",
        "屈服",
        "捕獲",
        "拘束",
        "監視",
        "見張",
        "武装解除",
        "連れ去",
    )
    if any(term.casefold() in joined for term in accept_terms):
        return True
    return any(isinstance(response, dict) and _as_bool(response.get("finished") or response.get("should_end_encounter")) for response in responses)


def _encounter_player_surrendered(encounter: dict[str, Any]) -> bool:
    if _as_bool(encounter.get("player_surrendered")):
        return True
    status_text = " ".join(
        str(encounter.get(key) or "")
        for key in ("player_status", "intent", "last_player_intent")
    ).lower()
    return any(term in status_text for term in ("surrender", "surrendering", "surrender_accepted", "降伏", "屈服"))


def _combat_action_text(*responses: Any) -> str:
    parts: list[str] = []
    for response in responses:
        if not isinstance(response, dict):
            continue
        for key in ("npc_action", "action", "intent", "narration", "text", "message"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=400)
            if value:
                parts.append(str(value))
        update = response.get("encounter_update")
        if isinstance(update, (dict, list)):
            parts.append(json.dumps(_compact_value(update, max_chars=500), ensure_ascii=False))
    return " ".join(parts)


def _response_implies_capture_relocation(response: dict[str, Any]) -> bool:
    if not isinstance(response, dict):
        return False
    text = _combat_action_text(response).casefold()
    if not text:
        return False
    capture_terms = (
        "capture",
        "captured",
        "captivity",
        "kidnap",
        "abduct",
        "carried away",
        "dragged away",
        "taken away",
        "nest",
        "lair",
        "den",
        "base",
        "hideout",
        "post_capture",
        "broodmother",
        "連れ去",
        "連行",
        "攫",
        "さらわ",
        "捕獲",
        "拘束",
        "巣",
        "巣穴",
        "拠点",
        "根城",
        "苗床",
    )
    if not any(term.casefold() in text for term in capture_terms):
        return False
    movement_terms = (
        "moved",
        "relocated",
        "transported",
        "dragged",
        "carried",
        "taken",
        "連れ",
        "運ば",
        "引きず",
        "移動",
        "連行",
        "運搬",
    )
    status_terms = (
        "post_capture",
        "captivity",
        "captured_to",
        "broodmother",
        "nest",
        "lair",
        "base",
        "hideout",
        "巣",
        "巣穴",
        "拠点",
        "根城",
        "苗床",
    )
    return any(term.casefold() in text for term in movement_terms) or any(term.casefold() in text for term in status_terms)


def _capture_subnode_name(response: dict[str, Any], opponent_name: str = "") -> str:
    text = _combat_action_text(response)
    lowered = text.casefold()
    base = str(opponent_name or "").strip()
    if "巣" in text or "nest" in lowered or "den" in lowered:
        return _short_text(f"{base}の巣" if base else "敵の巣", 48)
    if "拠点" in text or "base" in lowered or "hideout" in lowered or "lair" in lowered:
        return _short_text(f"{base}の拠点" if base else "敵の拠点", 48)
    return _short_text(f"{base}の捕獲場所" if base else "捕獲場所", 48)


def _capture_subnode_description(response: dict[str, Any], opponent_name: str = "") -> str:
    narration = str(response.get("narration") or response.get("text") or response.get("message") or "").strip()
    if narration:
        return _short_text(narration, 180)
    base = str(opponent_name or "敵").strip()
    return f"{base}に連れ込まれた場所。出口までの道を探す必要がある。"


def _npc_action_tool_kind(*responses: Any) -> str:
    surrender_values = {"surrender", "yield", "give_up", "giveup", "降伏", "降伏する", "降参", "降参する"}
    flee_values = {"flee", "escape", "run_away", "runaway", "retreat", "withdraw", "逃亡", "逃走", "逃げる", "退却", "離脱"}
    for response in responses:
        if not isinstance(response, dict):
            continue
        if _as_bool(response.get("npc_surrender") or response.get("surrender")):
            return "surrender"
        if _as_bool(response.get("npc_flee") or response.get("flee")):
            return "flee"
        values: list[str] = []
        for key in ("npc_action", "npc_tool", "tool", "intent"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=120)
            value_text = str(value or "").strip()
            if value_text:
                values.append(value_text)
        update = response.get("encounter_update")
        if isinstance(update, dict):
            for key in ("opponent_status", "npc_action", "npc_tool", "intent"):
                value_text = str(update.get(key) or "").strip()
                if value_text:
                    values.append(value_text)
        for value in values:
            normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized in surrender_values or value.strip() in surrender_values:
                return "surrender"
            if normalized in flee_values or value.strip() in flee_values:
                return "flee"
    return ""
