from __future__ import annotations

from typing import Any


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
)

STATUS_IMMUNITY_EFFECT_IDS = (
    "HP_Damage",
    "SP_Damage",
    "Paralysis",
    "Silence",
    "Psychosis",
    "Inoperable",
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
    "stun": "Paralysis",
    "stunned": "Paralysis",
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
    "hpダメージ": "HP_Damage",
    "毒": "HP_Damage",
    "出血": "HP_Damage",
    "炎上": "HP_Damage",
    "火傷": "HP_Damage",
    "spダメージ": "SP_Damage",
    "mpダメージ": "SP_Damage",
    "麻痺": "Paralysis",
    "しびれ": "Paralysis",
    "スタン": "Paralysis",
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
