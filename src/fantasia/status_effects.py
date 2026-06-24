from __future__ import annotations

import json
import re
from typing import Any


INCAPACITATED_STATUS_ID = "Inoperable"
INCAPACITATED_STATUS_NAME = "行動不能"
SURRENDERED_STATUS_ID = "surrendered"
FLED_STATUS_ID = "fled"
ATTRIBUTE_STATUS_EFFECT_IDS = (
    "str_mod",
    "dex_mod",
    "con_mod",
    "int_mod",
    "wis_mod",
    "cha_mod",
)

STATUS_EFFECT_IDS = (
    "HP_Damage",
    "SP_Damage",
    "Paralysis",
    "Silence",
    "Psychosis",
    "Inoperable",
    "SendLLM",
    "Atk_Mod",
    "Def_Mod",
    "Taunt",
    "accuracy_mod",
    "damage_taken_mod",
    "element_res_mod",
    "stun",
    "thorns",
    *ATTRIBUTE_STATUS_EFFECT_IDS,
)

STATUS_IMMUNITY_EFFECT_IDS = (
    "HP_Damage",
    "SP_Damage",
    "Paralysis",
    "Silence",
    "Psychosis",
    "Inoperable",
    "stun",
)

STATUS_EFFECT_LABELS_JA = {
    "HP_Damage": "HPダメージ",
    "SP_Damage": "SPダメージ",
    "Paralysis": "麻痺",
    "Silence": "沈黙",
    "Psychosis": "精神異常",
    "Inoperable": "行動不能",
    "SendLLM": "特殊効果",
    "Atk_Mod": "攻撃力変化",
    "Def_Mod": "防御力変化",
    "Taunt": "挑発",
    "accuracy_mod": "命中変化",
    "damage_taken_mod": "被ダメージ変化",
    "element_res_mod": "属性耐性変化",
    "stun": "スタン",
    "thorns": "反射",
    "str_mod": "筋力変化",
    "dex_mod": "器用変化",
    "con_mod": "耐久変化",
    "int_mod": "知力変化",
    "wis_mod": "判断変化",
    "cha_mod": "魅力変化",
}

STATUS_EFFECT_LABELS_EN = {
    "HP_Damage": "HP damage",
    "SP_Damage": "SP damage",
    "Paralysis": "Paralysis",
    "Silence": "Silence",
    "Psychosis": "Psychosis",
    "Inoperable": "Inoperable",
    "SendLLM": "LLM effect",
    "Atk_Mod": "Attack modifier",
    "Def_Mod": "Defense modifier",
    "Taunt": "Taunt",
    "accuracy_mod": "Accuracy modifier",
    "damage_taken_mod": "Damage taken modifier",
    "element_res_mod": "Element resistance modifier",
    "stun": "Stun",
    "thorns": "Thorns",
    "str_mod": "Strength modifier",
    "dex_mod": "Dexterity modifier",
    "con_mod": "Constitution modifier",
    "int_mod": "Intelligence modifier",
    "wis_mod": "Wisdom modifier",
    "cha_mod": "Charisma modifier",
}

STATUS_EFFECT_DESCRIPTIONS_JA = {
    "HP_Damage": "HPが自動的に減少する。",
    "SP_Damage": "SPが自動的に減少する。",
    "Paralysis": "肉体的な麻痺によって、敵に与えるダメージや行動に不利益が出る。",
    "Silence": "口がふさがれたり魔法で封じられたときに、口を使う行動が使えない。",
    "Psychosis": "スキルが使えなくなる。",
    "Inoperable": "四肢を拘束されたり眠ったりして、攻撃や移動や逃走が行えない。",
    "SendLLM": "LLMに渡す効果文のみを持つ。",
    "Atk_Mod": "攻撃力が上昇または減少する。",
    "Def_Mod": "防御力が上昇または減少する。",
    "Taunt": "攻撃対象を引きつける。",
    "accuracy_mod": "命中判定に補正を加える。",
    "damage_taken_mod": "受けるHPダメージが上昇または減少する。",
    "element_res_mod": "指定属性、または全属性への耐性が上昇または減少する。",
    "stun": "攻撃、スキル、逃走ができなくなる。",
    "thorns": "受けたHPダメージの一部を攻撃者へ反射する。",
    "str_mod": "筋力が上昇または減少する。",
    "dex_mod": "器用が上昇または減少する。",
    "con_mod": "耐久が上昇または減少する。",
    "int_mod": "知力が上昇または減少する。",
    "wis_mod": "判断が上昇または減少する。",
    "cha_mod": "魅力が上昇または減少する。",
}

STATUS_EFFECT_ALIASES = {
    "hp_damage": "HP_Damage",
    "hp damage": "HP_Damage",
    "poison": "HP_Damage",
    "venom": "HP_Damage",
    "bleed": "HP_Damage",
    "bleeding": "HP_Damage",
    "burn": "HP_Damage",
    "burning": "HP_Damage",
    "dot": "HP_Damage",
    "sp_damage": "SP_Damage",
    "sp damage": "SP_Damage",
    "mp_damage": "SP_Damage",
    "mp damage": "SP_Damage",
    "mana_damage": "SP_Damage",
    "paralysis": "Paralysis",
    "paralyzed": "Paralysis",
    "paralysed": "Paralysis",
    "stun": "stun",
    "stunned": "stun",
    "silence": "Silence",
    "silent": "Silence",
    "mute": "Silence",
    "muted": "Silence",
    "psychosis": "Psychosis",
    "confusion": "Psychosis",
    "madness": "Psychosis",
    "fear": "Psychosis",
    "panic": "Psychosis",
    "inoperable": "Inoperable",
    "incapacitated": "Inoperable",
    "immobilized": "Inoperable",
    "immobilised": "Inoperable",
    "restrained": "Inoperable",
    "bound": "Inoperable",
    "sleep": "Inoperable",
    "asleep": "Inoperable",
    "sendllm": "SendLLM",
    "send_llm": "SendLLM",
    "llm": "SendLLM",
    "atk_mod": "Atk_Mod",
    "attack_mod": "Atk_Mod",
    "attack_modifier": "Atk_Mod",
    "attack_up": "Atk_Mod",
    "attack_down": "Atk_Mod",
    "def_mod": "Def_Mod",
    "defense_mod": "Def_Mod",
    "defence_mod": "Def_Mod",
    "defense_modifier": "Def_Mod",
    "defense_up": "Def_Mod",
    "defense_down": "Def_Mod",
    "taunt": "Taunt",
    "provoke": "Taunt",
    "provocation": "Taunt",
    "aggro": "Taunt",
    "accuracy_mod": "accuracy_mod",
    "accuracy_up": "accuracy_mod",
    "accuracy_down": "accuracy_mod",
    "hit_mod": "accuracy_mod",
    "hit_rate_mod": "accuracy_mod",
    "damage_taken_mod": "damage_taken_mod",
    "vulnerability": "damage_taken_mod",
    "damage_reduction": "damage_taken_mod",
    "element_res_mod": "element_res_mod",
    "element_resistance_mod": "element_res_mod",
    "resistance_mod": "element_res_mod",
    "thorns": "thorns",
    "thorn": "thorns",
    "reflect_damage": "thorns",
    "strength_mod": "str_mod",
    "strength_up": "str_mod",
    "strength_down": "str_mod",
    "str_up": "str_mod",
    "str_down": "str_mod",
    "dexterity_mod": "dex_mod",
    "dexterity_up": "dex_mod",
    "dexterity_down": "dex_mod",
    "dex_up": "dex_mod",
    "dex_down": "dex_mod",
    "constitution_mod": "con_mod",
    "constitution_up": "con_mod",
    "constitution_down": "con_mod",
    "con_up": "con_mod",
    "con_down": "con_mod",
    "intelligence_mod": "int_mod",
    "intelligence_up": "int_mod",
    "intelligence_down": "int_mod",
    "int_up": "int_mod",
    "int_down": "int_mod",
    "wisdom_mod": "wis_mod",
    "wisdom_up": "wis_mod",
    "wisdom_down": "wis_mod",
    "wis_up": "wis_mod",
    "wis_down": "wis_mod",
    "charisma_mod": "cha_mod",
    "charisma_up": "cha_mod",
    "charisma_down": "cha_mod",
    "cha_up": "cha_mod",
    "cha_down": "cha_mod",
    "hpダメージ": "HP_Damage",
    "毒": "HP_Damage",
    "出血": "HP_Damage",
    "炎上": "HP_Damage",
    "火傷": "HP_Damage",
    "spダメージ": "SP_Damage",
    "mpダメージ": "SP_Damage",
    "麻痺": "Paralysis",
    "しびれ": "Paralysis",
    "スタン": "stun",
    "沈黙": "Silence",
    "精神異常": "Psychosis",
    "混乱": "Psychosis",
    "恐怖": "Psychosis",
    "狂乱": "Psychosis",
    "行動不能": "Inoperable",
    "拘束": "Inoperable",
    "睡眠": "Inoperable",
    "眠り": "Inoperable",
    "特殊効果": "SendLLM",
    "攻撃力変化": "Atk_Mod",
    "攻撃力上昇": "Atk_Mod",
    "攻撃力低下": "Atk_Mod",
    "防御力変化": "Def_Mod",
    "防御力上昇": "Def_Mod",
    "防御力低下": "Def_Mod",
    "挑発": "Taunt",
    "命中変化": "accuracy_mod",
    "命中上昇": "accuracy_mod",
    "命中低下": "accuracy_mod",
    "被ダメージ変化": "damage_taken_mod",
    "被ダメージ上昇": "damage_taken_mod",
    "被ダメージ低下": "damage_taken_mod",
    "属性耐性変化": "element_res_mod",
    "属性耐性上昇": "element_res_mod",
    "属性耐性低下": "element_res_mod",
    "反射": "thorns",
    "筋力変化": "str_mod",
    "筋力上昇": "str_mod",
    "筋力低下": "str_mod",
    "器用変化": "dex_mod",
    "器用上昇": "dex_mod",
    "器用低下": "dex_mod",
    "耐久変化": "con_mod",
    "耐久上昇": "con_mod",
    "耐久低下": "con_mod",
    "知力変化": "int_mod",
    "知力上昇": "int_mod",
    "知力低下": "int_mod",
    "判断変化": "wis_mod",
    "判断上昇": "wis_mod",
    "判断低下": "wis_mod",
    "魅力変化": "cha_mod",
    "魅力上昇": "cha_mod",
    "魅力低下": "cha_mod",
}


def canonical_status_effect_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text in STATUS_EFFECT_IDS:
        return text
    lowered = text.casefold()
    if lowered in STATUS_EFFECT_ALIASES:
        return STATUS_EFFECT_ALIASES[lowered]
    for effect_id in STATUS_EFFECT_IDS:
        if effect_id.casefold() == lowered:
            return effect_id
    for alias, effect_id in STATUS_EFFECT_ALIASES.items():
        if alias and alias in lowered:
            return effect_id
    return ""


def status_effect_label(effect_id: Any, language: str = "ja") -> str:
    canonical = canonical_status_effect_id(effect_id) or str(effect_id or "").strip()
    if str(language or "").strip().lower().startswith("en"):
        return STATUS_EFFECT_LABELS_EN.get(canonical, canonical)
    return STATUS_EFFECT_LABELS_JA.get(canonical, canonical)


def status_effect_description(effect_id: Any) -> str:
    canonical = canonical_status_effect_id(effect_id)
    return STATUS_EFFECT_DESCRIPTIONS_JA.get(canonical, "")


def status_effect_is_equipment_immune_allowed(effect_id: Any) -> bool:
    return canonical_status_effect_id(effect_id) in STATUS_IMMUNITY_EFFECT_IDS


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "enabled", "有効", "はい"}


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def _status_effect_target(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    text = str(value.get("target") or value.get("actor") or value.get("recipient") or "").strip().lower()
    if text in {"player", "pc", "hero", "self", "you", "あなた", "プレイヤー"}:
        return "player"
    if text in {"opponent", "enemy", "monster", "npc", "target", "foe", "相手", "敵", "対象"}:
        return "opponent"
    return ""


def _global_status_target(value: Any, default_target: str, context_target: str) -> str:
    if not isinstance(value, dict):
        return default_target
    text = str(
        value.get("target")
        or value.get("actor")
        or value.get("recipient")
        or value.get("character")
        or value.get("character_name")
        or value.get("npc")
        or value.get("npc_name")
        or ""
    ).strip()
    lowered = text.lower()
    if lowered in {"", "default"}:
        return default_target
    if lowered in {"player", "pc", "hero", "protagonist", "you", "あなた", "プレイヤー"}:
        return "player"
    if lowered in {"self"}:
        return default_target
    if lowered in {"speaker", "npc", "character", "target"}:
        return context_target or default_target
    if lowered in {"monster", "enemy", "opponent"}:
        return "monster"
    return text


def _status_effect_applied_line(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("target") or "対象")
    effect = item.get("effect") if isinstance(item.get("effect"), dict) else {}
    name = str(effect.get("name") or "状態")
    marker = "長期状態" if _safe_int(effect.get("duration"), 0) == -1 else "状態"
    stage = str(effect.get("stage") or "")
    suffix = f" ({stage})" if stage else ""
    return f"[{marker}] {label}に{name}{suffix}が付与された。"


def _status_effect_removed_line(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("target") or "target")
    effect = item.get("effect") if isinstance(item.get("effect"), dict) else {}
    name = str(effect.get("name") or "status")
    marker = "long-term status removed" if _safe_int(effect.get("duration"), 0) == -1 else "status removed"
    treatment = str(item.get("treatment") or "")
    suffix = f" ({treatment})" if treatment else ""
    return f"[{marker}] {label}: {name}{suffix}"


def _status_effect_items(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        if any(
            key in value
            for key in (
                "name",
                "title",
                "label",
                "id",
                "effect_id",
                "status",
                "condition",
                "effect",
                "effect_text",
                "llm_effect",
                "description",
                "mechanics",
                "power",
                "duration",
                "remove_condition",
            )
        ):
            return [value]
        result: list[Any] = []
        for item in value.values():
            result.extend(_status_effect_items(item))
        return result
    return [value]


def _normalise_status_effect(value: Any, *, source: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        raw_name = str(
            value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("id")
            or value.get("status")
            or value.get("condition")
            or ""
        ).strip()
        data = {str(key): item for key, item in value.items()}
    else:
        raw_name = str(value).strip()
        data = {"name": raw_name}
    raw_effect_text = _first_status_text(
        data,
        "effect",
        "effect_text",
        "mechanics",
        "mechanical_effect",
        "rule",
        "rules",
    )
    effect_text_is_id = bool(canonical_status_effect_id(raw_effect_text))
    description = _first_status_text(data, "description", "summary", "detail")
    llm_effect = _first_status_text(data, "llm_effect", "send_llm", "send_llm_text", "llm_text")
    if not llm_effect and raw_effect_text and not effect_text_is_id:
        llm_effect = raw_effect_text
    raw_name = raw_name or _status_name_from_text(llm_effect or description)
    combined = " ".join(part for part in (raw_name, raw_effect_text, description, llm_effect) if part)
    preset = _status_effect_preset(combined)
    raw_id = str(
        data.get("effect_id")
        or data.get("effect_type")
        or data.get("status_id")
        or data.get("id")
        or (raw_effect_text if effect_text_is_id else "")
        or preset.get("effect_id")
        or preset.get("id")
        or ""
    ).strip()
    system_id = raw_id if raw_id in {"dead", "defeated", SURRENDERED_STATUS_ID, FLED_STATUS_ID} else ""
    effect_id = canonical_status_effect_id(raw_id) or canonical_status_effect_id(combined) or system_id
    if not effect_id:
        effect_id = "SendLLM" if (llm_effect or description or raw_name) else ""
    if not effect_id:
        return {}
    name = str(data.get("name") or preset.get("name") or raw_name or status_effect_label(effect_id)).strip()
    if name == effect_id:
        name = status_effect_label(effect_id)
    description = description or str(preset.get("description") or status_effect_description(effect_id) or "")
    remove_condition = str(data.get("remove_condition") or data.get("cure_condition") or preset.get("remove_condition") or "").strip()
    inferred_duration = _infer_status_duration(llm_effect or description or raw_name)
    duration_value = (
        data.get("duration")
        if "duration" in data
        else data.get("time", data.get("turns", preset.get("duration", inferred_duration)))
    )
    permanent = _is_permanent_status_duration(duration_value) or _as_bool(data.get("permanent") or data.get("persistent") or preset.get("persistent"))
    duration = -1 if permanent else _safe_int(duration_value, _safe_int(preset.get("duration", inferred_duration), 0))
    if duration <= 0 and inferred_duration > 0:
        duration = inferred_duration
    power = _safe_int(
        data.get(
            "power",
            data.get(
                "value",
                data.get("amount", data.get("effect_amount", preset.get("power", 0))),
            ),
        ),
        _safe_int(preset.get("power"), 0),
    )
    if effect_id in {"HP_Damage", "SP_Damage", "Paralysis"}:
        power = abs(power)
    result = {
        "name": name,
        "description": description,
        "remove_condition": remove_condition,
        "power": power,
        "duration": duration,
        "effect_id": effect_id,
        "llm_effect": llm_effect,
        "source": source or str(data.get("source") or ""),
    }
    for key in (
        "severity",
        "category",
        "scope",
        "stage",
        "progress",
        "visual",
        "tick_text",
        "expire_text",
        "apply_text",
        "started_day",
        "started_location",
        "expected_day",
        "due_day",
        "expires_day",
        "notes",
        "combat_state",
        "element",
        "target_element",
        "element_type",
    ):
        item = data.get(key) if key in data else preset.get(key)
        if item not in (None, "", [], {}):
            result[key] = item
    return _drop_empty(result)


def _first_status_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()
    return ""


def _status_name_from_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    for separator in ("。", ".", "、", ",", ":", "：", "\n"):
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
            break
    return cleaned[:28] + ("..." if len(cleaned) > 28 else "")


def _infer_status_duration(text: str) -> int:
    source = str(text or "")
    patterns = (
        r"(\d+)\s*(?:ターン|turns?)",
        r"(?:for|next)\s+(\d+)\s+turns?",
    )
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if match:
            return max(0, _safe_int(match.group(1), 0))
    return 0


def _is_permanent_status_duration(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {
        "permanent",
        "persistent",
        "indefinite",
        "until_removed",
        "until removed",
        "long_term",
        "long term",
        "永続",
        "恒久",
        "長期",
        "解除まで",
    }


def _format_status_template(template: Any, actor_label: str, name: str, hp_delta: int) -> str:
    text = str(template or "").strip()
    if not text:
        return ""
    values = {
        "actor": actor_label,
        "name": name,
        "damage": abs(hp_delta) if hp_delta < 0 else 0,
        "heal": hp_delta if hp_delta > 0 else 0,
        "hp_delta": hp_delta,
    }
    try:
        return text.format(**values)
    except (KeyError, ValueError):
        return text


def _status_effect_preset(text: str) -> dict[str, Any]:
    source = str(text or "")
    lowered = source.casefold()
    effect_id = canonical_status_effect_id(source)
    if effect_id:
        power = 1 if effect_id in {"HP_Damage", "SP_Damage", "Paralysis"} else 0
        return {
            "effect_id": effect_id,
            "name": status_effect_label(effect_id),
            "description": status_effect_description(effect_id),
            "duration": 3 if effect_id in {"HP_Damage", "SP_Damage", "Paralysis", "Silence", "Psychosis", "Inoperable"} else 0,
            "power": power,
        }
    if any(word in lowered for word in ("dead", "death")) or "死亡" in source:
        return {"effect_id": "dead", "name": "死亡", "duration": -1, "power": 0}
    if any(word in lowered for word in ("defeated", "unconscious")) or "戦闘不能" in source:
        return {"effect_id": "defeated", "name": "戦闘不能", "duration": -1, "power": 0}
    if "surrender" in lowered or "降伏" in source:
        return {"effect_id": SURRENDERED_STATUS_ID, "name": "降伏", "duration": -1, "power": 0}
    if any(word in lowered for word in ("fled", "escaped")) or "逃走" in source:
        return {"effect_id": FLED_STATUS_ID, "name": "逃走", "duration": -1, "power": 0}
    if "pregnan" in lowered or "妊娠" in source:
        return {
            "effect_id": "SendLLM",
            "name": "妊娠",
            "description": "長期的に保持される身体状態。",
            "duration": -1,
            "power": 0,
            "llm_effect": "妊娠している。行動や描写で必要に応じて考慮する。",
            "scope": "character",
        }
    if any(word in lowered for word in ("wounded", "injured")) or "負傷" in source or "重傷" in source:
        return {
            "effect_id": "SendLLM",
            "name": "負傷",
            "description": "傷を負っており、行動や描写に影響する。",
            "duration": 0,
            "power": 0,
            "llm_effect": "負傷している。痛みや動作の鈍りを描写に反映する。",
        }
    return {}


def _status_effect_from_status_text(text: str) -> dict[str, Any]:
    preset = _status_effect_preset(text)
    return _normalise_status_effect(preset, source="status_text") if preset else {}


def _status_effect_blocks_action(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) == "Inoperable"


def _status_effect_blocks_movement(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) == "Inoperable"


def _status_effect_blocks_attack(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) == "Inoperable"


def _status_effect_blocks_escape(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) == "Inoperable"


def _status_effect_blocks_skill(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) == "Psychosis"


def _status_effect_action_uses_mouth(action: str) -> bool:
    text = str(action or "").casefold()
    if not text:
        return False
    return any(
        keyword in text
        for keyword in (
            "詠唱",
            "唱える",
            "唱え",
            "話す",
            "話しかけ",
            "説得",
            "交渉",
            "叫ぶ",
            "歌う",
            "speech",
            "speak",
            "talk",
            "negotiate",
            "persuade",
            "chant",
            "cast",
            "sing",
            "shout",
        )
    )


def _status_effect_is_surrendered_or_fled(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) in {SURRENDERED_STATUS_ID, FLED_STATUS_ID}


def _status_response_context_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, dict):
        parts = [
            str(value.get(key) or "")
            for key in (
                "narration",
                "text",
                "message",
                "npc_action",
                "intent",
                "reason",
                "description",
            )
        ]
        judgement = value.get("combat_judgement")
        if isinstance(judgement, dict):
            parts.extend(str(judgement.get(key) or "") for key in ("reason", "description"))
        return "\n".join(part for part in parts if part)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _status_effect_is_incapacitating(effect: dict[str, Any]) -> bool:
    if not isinstance(effect, dict):
        return False
    return _status_effect_id(effect) == "Inoperable"


def _status_effect_has_generic_incapacitated_text(effect: dict[str, Any]) -> bool:
    return _status_effect_has_generic_incapacitated_name(effect) or _status_effect_has_generic_incapacitated_description(effect)


def _status_effect_has_generic_incapacitated_name(effect: dict[str, Any]) -> bool:
    name = str(effect.get("name") or "").strip()
    lowered = name.casefold()
    return lowered in {
        "",
        INCAPACITATED_STATUS_ID,
        "immobilized",
        "immobilised",
        "restrained",
        "bound",
        "unable to act",
        "cannot act",
        "status",
        "condition",
        "状態",
        INCAPACITATED_STATUS_NAME,
        "拘束",
        "拘束状態",
        "捕縛",
        "身動き不能",
        "動けない",
    }


def _status_effect_has_generic_incapacitated_description(effect: dict[str, Any]) -> bool:
    description = str(effect.get("description") or "").strip()
    effect_text = str(effect.get("llm_effect") or effect.get("effect") or "").strip()
    if not description and not effect_text:
        return True
    generic_parts = (
        "拘束や麻痺などにより",
        "攻撃・逃走・移動ができない",
        "unable to act",
        "cannot act",
        "prevents action",
    )
    combined = f"{description}\n{effect_text}".casefold()
    return any(part.casefold() in combined for part in generic_parts)


def _contextual_incapacitated_status_details(actor_name: str, context_text: str) -> dict[str, str]:
    actor = str(actor_name or "").strip()
    source = f"{actor}\n{context_text}".casefold()

    def has_any(*words: str) -> bool:
        return any(word.casefold() in source for word in words)

    if has_any("触手", "tentacle"):
        return {
            "name": "触手拘束",
            "description": "絡みつく触手に手足を押さえ込まれ、攻撃・逃走・移動ができない。",
            "effect": "触手による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("糸", "蜘蛛", "粘糸", "web", "spider"):
        return {
            "name": "粘糸拘束",
            "description": "粘つく糸が体に絡み、攻撃・逃走・移動ができない。",
            "effect": "粘糸による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("粘液", "スライム", "slime", "mucus"):
        return {
            "name": "粘液拘束",
            "description": "まとわりつく粘液で体の自由を奪われ、攻撃・逃走・移動ができない。",
            "effect": "粘液による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("蔓", "つる", "根", "植物", "vine", "root"):
        return {
            "name": "蔓絡み",
            "description": "蔓や根が足元から絡みつき、攻撃・逃走・移動ができない。",
            "effect": "植物による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("氷", "凍", "ice", "frost", "freeze"):
        return {
            "name": "氷縛",
            "description": "凍りついた冷気が体を固め、攻撃・逃走・移動ができない。",
            "effect": "氷結による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("雷", "電", "痺", "しびれ", "麻痺", "lightning", "shock", "paraly"):
        return {
            "name": "電撃麻痺",
            "description": "走るしびれで体が硬直し、攻撃・逃走・移動ができない。",
            "effect": "電撃による麻痺。攻撃・逃走・移動を妨げる。",
        }
    if has_any("影", "闇", "shadow", "dark"):
        return {
            "name": "影縛り",
            "description": "足元の影に縫い止められ、攻撃・逃走・移動ができない。",
            "effect": "影による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("鎖", "縄", "ロープ", "chain", "rope"):
        return {
            "name": "鎖縄拘束",
            "description": "鎖や縄で体を取られ、攻撃・逃走・移動ができない。",
            "effect": "鎖縄による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("網", "罠", "net", "trap"):
        return {
            "name": "罠絡み",
            "description": "罠に体を絡め取られ、攻撃・逃走・移動ができない。",
            "effect": "罠による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("呪", "魔法", "spell", "curse", "magic"):
        return {
            "name": "呪縛",
            "description": "敵の術が体の自由を奪い、攻撃・逃走・移動ができない。",
            "effect": "呪いまたは魔法による拘束。攻撃・逃走・移動を妨げる。",
        }
    if has_any("押さえ", "組み伏せ", "掴", "grab", "pin", "grapple"):
        return {
            "name": "組み伏せ",
            "description": "体勢を崩されて押さえ込まれ、攻撃・逃走・移動ができない。",
            "effect": "組み伏せによる拘束。攻撃・逃走・移動を妨げる。",
        }
    label = f"{actor}の拘束" if actor else "拘束"
    return {
        "name": label,
        "description": "敵の攻撃で体の自由を奪われ、攻撃・逃走・移動ができない。",
        "effect": "攻撃に伴う拘束。攻撃・逃走・移動を妨げる。",
    }


def _combat_status_effects_payload(value: Any) -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _status_effect_items(value):
        effect = _normalise_status_effect(raw) if not isinstance(raw, dict) else _normalise_status_effect(raw, source=str(raw.get("source") or ""))
        if not effect:
            continue
        name = str(effect.get("name") or "").strip()
        if not name:
            continue
        key = f"{_status_effect_id(effect)}|{name}"
        if key in seen:
            continue
        seen.add(key)
        item = {
            "effect_id": _status_effect_id(effect),
            "name": name,
            "description": str(effect.get("description") or ""),
            "remove_condition": str(effect.get("remove_condition") or ""),
            "power": effect.get("power"),
            "duration": effect.get("duration"),
            "llm_effect": str(effect.get("llm_effect") or ""),
        }
        effects.append({key: value for key, value in item.items() if value not in (None, "", [], {})})
    return effects[:3]


def _combat_status_effects_fallback_note(value: Any, target_name: str) -> str:
    effects = _combat_status_effects_payload(value)
    if not effects:
        return ""
    target = str(target_name or "対象")
    parts: list[str] = []
    for effect in effects[:2]:
        name = str(effect.get("name") or "状態異常")
        description = str(effect.get("description") or effect.get("llm_effect") or "")
        parts.append(f"{target}は「{name}」を受けた。{description}".strip())
    return " " + " ".join(parts)


def _combat_status_effects_mentioned(text: str, value: Any) -> bool:
    source = str(text or "")
    if not source:
        return False
    for effect in _combat_status_effects_payload(value):
        name = str(effect.get("name") or "").strip()
        description = str(effect.get("description") or effect.get("llm_effect") or "").strip()
        if name and name in source:
            return True
        if description:
            fragment = description[: min(10, len(description))]
            if fragment and fragment in source:
                return True
    return False


def _status_effect_merge_key(effect: dict[str, Any]) -> str:
    return f"{_status_effect_id(effect)}|{str(effect.get('name') or '').casefold()}"


def _merge_status_power(existing_power: Any, new_power: Any) -> int:
    existing = _safe_int(existing_power, 0)
    new = _safe_int(new_power, 0)
    if existing < 0 and new < 0:
        return min(existing, new)
    if existing > 0 and new > 0:
        return max(existing, new)
    return new if new != 0 else existing


def _merge_status_effect(status_list: list[dict[str, Any]], effect: dict[str, Any]) -> None:
    effect_key = _status_effect_merge_key(effect)
    for existing in status_list:
        if _status_effect_merge_key(existing) != effect_key:
            continue
        existing.update({key: value for key, value in effect.items() if value not in (None, "", [])})
        existing_duration = _safe_int(existing.get("duration"), 0)
        effect_duration = _safe_int(effect.get("duration"), 0)
        existing["duration"] = -1 if -1 in {existing_duration, effect_duration} else max(existing_duration, effect_duration)
        existing["power"] = _merge_status_power(existing.get("power"), effect.get("power"))
        return
    status_list.append(effect)


def _tick_status_effects(status_list: list[dict[str, Any]], actor_label: str) -> tuple[list[dict[str, Any]], int, int, list[str]]:
    updated: list[dict[str, Any]] = []
    total_hp_delta = 0
    total_sp_delta = 0
    lines: list[str] = []
    for raw in status_list:
        effect = _normalise_status_effect(raw, source=str(raw.get("source") or "") if isinstance(raw, dict) else "")
        if not effect:
            continue
        name = str(effect.get("name") or "状態異常")
        effect_id = _status_effect_id(effect)
        power = max(0, _safe_int(effect.get("power"), 0))
        hp_delta = -power if effect_id == "HP_Damage" and power else 0
        sp_delta = -power if effect_id == "SP_Damage" and power else 0
        if hp_delta:
            total_hp_delta += hp_delta
            tick_text = _format_status_template(effect.get("tick_text"), actor_label, name, hp_delta)
            if tick_text:
                lines.append(tick_text)
            elif hp_delta < 0:
                lines.append(f"[状態] {actor_label}は{name}により{abs(hp_delta)}ダメージを受けた。")
            else:
                lines.append(f"[状態] {actor_label}は{name}により{hp_delta}回復した。")
        if sp_delta:
            total_sp_delta += sp_delta
            lines.append(f"[状態] {actor_label}は{name}によりSPを{abs(sp_delta)}失った。")
        elif effect.get("tick_text"):
            lines.append(_format_status_template(effect.get("tick_text"), actor_label, name, hp_delta))
        elif effect.get("llm_effect") and _safe_int(effect.get("duration"), 0) > 0:
            lines.append(f"[状態] {actor_label}は{name}の影響を受けている: {effect.get('llm_effect')}")
        duration = _safe_int(effect.get("duration"), 0)
        if duration > 0:
            duration -= 1
            if duration <= 0:
                expire_text = _format_status_template(effect.get("expire_text"), actor_label, name, hp_delta)
                lines.append(expire_text or f"[状態] {actor_label}の{name}は治まった。")
                continue
            effect["duration"] = duration
        updated.append(effect)
    return updated, total_hp_delta, total_sp_delta, lines


def _status_effect_id(value: Any) -> str:
    if isinstance(value, dict):
        direct = str(value.get("effect_id") or value.get("effect_type") or value.get("status_id") or "").strip()
        canonical = canonical_status_effect_id(direct)
        if canonical:
            return canonical
        raw_id = str(value.get("id") or "").strip()
        if raw_id in {"dead", "defeated", SURRENDERED_STATUS_ID, FLED_STATUS_ID}:
            return raw_id
        text = str(value.get("name") or value.get("title") or value.get("label") or value.get("status") or value.get("condition") or value.get("effect") or value.get("description") or "")
    else:
        text = str(value)
    preset = _status_effect_preset(text)
    preset_id = str(preset.get("effect_id") or preset.get("id") or "").strip()
    canonical = canonical_status_effect_id(preset_id) or canonical_status_effect_id(text)
    if canonical:
        return canonical
    if preset_id in {"dead", "defeated", SURRENDERED_STATUS_ID, FLED_STATUS_ID}:
        return preset_id
    return _slug_status(text)


def _slug_status(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text).strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "status"
