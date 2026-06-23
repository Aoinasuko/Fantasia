from __future__ import annotations

import random
from typing import Any, Callable


ACTION_ROLL_ABILITIES = ("str", "con", "dex", "int", "wis", "cha")

ACTION_ROLL_ABILITY_LABELS = {
    "str": "筋力",
    "con": "耐久",
    "dex": "器用",
    "int": "知力",
    "wis": "判断",
    "cha": "魅力",
}

ACTION_ROLL_ABILITY_EXAMPLES = {
    "str": ["扉を力ずくでこじ開ける", "重い岩を押し動かす", "倒れた柱を持ち上げる", "相手を押さえ込む", "鎖を引きちぎる"],
    "con": ["毒や病に耐える", "寒さや暑さを我慢する", "長時間走り続ける", "痛みに耐えて作業を続ける", "息を止めて水中を進む"],
    "dex": ["鍵を開ける", "罠を外す", "物陰に忍び込む", "細かな作業で道具を扱う", "足場を跳び移る"],
    "int": ["古文書を解読する", "仕掛けの構造を分析する", "魔術理論を思い出す", "薬品の成分を見分ける", "複雑な謎を解く"],
    "wis": ["周囲を探索する", "隠れた痕跡を追う", "気配に気づく", "嘘や違和感を見抜く", "危険な兆候を察知する"],
    "cha": ["相手を説得する", "値引き交渉をする", "嘘でごまかす", "威圧して退かせる", "演技や話術で注目を集める"],
}

ACTION_ROLL_DIFFICULTY_GUIDE = {
    0: "技能を持たない素人でも成功する",
    1: "技能があれば成功する、素人には難しい",
    2: "技能があれば五分五分",
    3: "その技能にある程度精通していなければ難しい",
    4: "その技能によほど熟練していなければ難しい",
    5: "高い技能、高い能力に加え、運も必要",
}


def action_roll_judgement_context(action: str, purpose: str, *, current_danger: int = 0) -> dict[str, Any]:
    return {
        "action": str(action or ""),
        "purpose": str(purpose or "action"),
        "current_location_danger": max(0, min(50, _safe_int(current_danger, 0))),
        "ability_examples": {
            ability: {
                "label": ACTION_ROLL_ABILITY_LABELS[ability],
                "examples": list(examples),
            }
            for ability, examples in ACTION_ROLL_ABILITY_EXAMPLES.items()
        },
        "difficulty_guide": dict(ACTION_ROLL_DIFFICULTY_GUIDE),
        "rules": [
            "Return attribute_scores for all six abilities as 0.0 to 1.0 similarity scores.",
            "The roll ability is the ability with the highest score.",
            "Return difficulty as 0 to 5 using the difficulty_guide.",
            "Do not decide success or failure.",
        ],
    }


def action_roll_system_prompt() -> str:
    return (
        "あなたはAI駆動RPGの行動判定分類担当です。"
        "プレイヤー行動を、筋力・耐久・器用・知力・判断・魅力の6能力のどれに近いかで評価します。"
        "各能力の近さを0.0から1.0で返し、行為の難易度を0から5で返してください。"
        "返答はJSONオブジェクトだけにしてください。"
    )


def normalise_action_roll_judgement(response: Any) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    raw_scores = response.get("attribute_scores") or response.get("ability_scores") or response.get("scores")
    if not isinstance(raw_scores, dict):
        return None
    scores: dict[str, float] = {}
    for ability in ACTION_ROLL_ABILITIES:
        value = raw_scores.get(ability)
        if value is None:
            value = raw_scores.get(ACTION_ROLL_ABILITY_LABELS[ability])
        score = _safe_float(value, -1.0)
        if score < 0:
            return None
        scores[ability] = max(0.0, min(1.0, score))
    difficulty = _safe_float(response.get("difficulty"), -1.0)
    if difficulty < 0:
        difficulty = _safe_float(response.get("difficulty_level"), -1.0)
    if difficulty < 0:
        return None
    difficulty = max(0.0, min(5.0, difficulty))
    ability = max(ACTION_ROLL_ABILITIES, key=lambda item: (scores[item], -ACTION_ROLL_ABILITIES.index(item)))
    return {
        "ability": ability,
        "ability_label": ACTION_ROLL_ABILITY_LABELS[ability],
        "attribute_scores": scores,
        "difficulty": difficulty,
        "target": target_for_difficulty(difficulty),
        "reason": str(response.get("reason") or response.get("summary") or "").strip(),
        "source": "llm",
    }


def make_action_roll(
    action: str,
    *,
    purpose: str = "action",
    attributes: dict[str, Any] | None = None,
    current_danger: int = 0,
    forced_ability: str = "",
    forced_target: int | None = None,
    normalise_target: bool = True,
    judgement: dict[str, Any] | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    attrs = attributes if isinstance(attributes, dict) else {}
    if forced_ability:
        ability = normalise_ability(forced_ability, fallback="dex" if purpose == "craft" else "wis")
        difficulty = None
        target = (
            _normalise_roll_target(forced_target)
            if normalise_target
            else max(2, min(30, _safe_int(forced_target, 10)))
        )
        judgement_source = "forced"
        attribute_scores: dict[str, float] = {}
    elif forced_target is not None:
        resolved = judgement if isinstance(judgement, dict) else fallback_action_roll_judgement(action, purpose, current_danger)
        ability = normalise_ability(str(resolved.get("ability") or ""), fallback=fallback_ability_for_action(action, purpose))
        difficulty = resolved.get("difficulty")
        target = (
            _normalise_roll_target(forced_target)
            if normalise_target
            else max(2, min(30, _safe_int(forced_target, 10)))
        )
        judgement_source = str(resolved.get("source") or "fallback")
        attribute_scores = dict(resolved.get("attribute_scores") or {})
    else:
        resolved = judgement if isinstance(judgement, dict) else fallback_action_roll_judgement(action, purpose, current_danger)
        ability = normalise_ability(str(resolved.get("ability") or ""), fallback=fallback_ability_for_action(action, purpose))
        difficulty = _safe_float(resolved.get("difficulty"), fallback_difficulty_for_danger(current_danger))
        target = target_for_difficulty(difficulty)
        judgement_source = str(resolved.get("source") or "fallback")
        attribute_scores = dict(resolved.get("attribute_scores") or {})

    ability_score = _safe_int(attrs.get(ability), 10)
    bonus = ability_score // 3
    dice_source = rng or random
    die_1 = dice_source.randint(1, 6)
    die_2 = dice_source.randint(1, 6)
    natural = die_1 + die_2
    total = natural + bonus
    critical_failure = natural == 2
    critical_success = natural == 12
    success = critical_success or (not critical_failure and total >= target)
    ability_label = _roll_ability_label(ability)
    if critical_success:
        outcome = "強制成功"
    elif critical_failure:
        outcome = "強制失敗"
    else:
        outcome = "成功" if success else "失敗"
    line = f"> [判定] 目標値 {target} / 2d6 {die_1}+{die_2} + {ability_label}ボーナス{bonus} = {total} : {outcome}"
    if difficulty is not None:
        line = f"{line} / 難易度 {round(float(difficulty), 2)}"
    return {
        "enabled": True,
        "rule": "2d6 + floor(relevant_ability / 3) vs target. Natural 2 is forced failure. Natural 12 is forced success. Target is 8 + difficulty * 2.",
        "purpose": purpose,
        "action": action,
        "ability": ability,
        "ability_label": ability_label,
        "ability_score": ability_score,
        "bonus": bonus,
        "dice": [die_1, die_2],
        "roll": natural,
        "target": target,
        "difficulty": difficulty,
        "attribute_scores": attribute_scores,
        "judgement_source": judgement_source,
        "total": total,
        "success": success,
        "failure": not success,
        "critical_success": critical_success,
        "critical_failure": critical_failure,
        "margin": total - target,
        "line": line,
    }


def fallback_action_roll_judgement(action: str, purpose: str, current_danger: int = 0) -> dict[str, Any]:
    ability = fallback_ability_for_action(action, purpose)
    difficulty = fallback_difficulty_for_danger(current_danger)
    scores = {key: 0.0 for key in ACTION_ROLL_ABILITIES}
    scores[ability] = 1.0
    return {
        "ability": ability,
        "ability_label": _roll_ability_label(ability),
        "attribute_scores": scores,
        "difficulty": difficulty,
        "target": target_for_difficulty(difficulty),
        "reason": "LLM judgement unavailable; local keyword fallback was used.",
        "source": "fallback",
    }


def fallback_difficulty_for_danger(current_danger: Any) -> float:
    return max(0.0, min(5.0, _safe_float(current_danger, 0.0) / 10.0))


def target_for_difficulty(difficulty: Any) -> int:
    value = max(0.0, min(5.0, _safe_float(difficulty, 1.0)))
    return max(2, min(30, int(8 + value * 2 + 0.5)))


def should_use_action_roll(
    action: str,
    input_type: str,
    purpose: str,
    *,
    excluded_actions: tuple[str, ...] = (),
    is_quest_abandon: bool = False,
    is_conversation_end: bool = False,
) -> bool:
    text = str(action or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if text in set(excluded_actions):
        return False
    if is_quest_abandon or is_conversation_end:
        return False
    if purpose == "craft":
        return True
    if _contains_any_action_roll_keyword(text, lowered):
        return True
    if _looks_like_simple_auto_action(text, lowered):
        return False
    if purpose in {"quest", "conversation", "exploration"}:
        return input_type == "free_action"
    return input_type == "free_action"


def fallback_ability_for_action(action: str, purpose: str) -> str:
    text = str(action or "")
    lowered = text.lower()
    if purpose == "craft":
        return "dex"
    ability_keywords = (
        ("str", ("force", "break", "lift", "carry", "push", "pull", "bend", "smash", "筋力", "力ずく", "壊す", "破壊", "持ち上げ", "押す", "引く")),
        ("dex", ("dex", "agile", "sneak", "hide", "steal", "lockpick", "pick lock", "disarm", "dodge", "climb", "jump", "throw", "器用", "隠れる", "忍び", "盗む", "鍵", "開錠", "解除", "罠", "避け", "登る", "跳ぶ", "投げ")),
        ("con", ("endure", "resist", "withstand", "swim", "stamina", "poison", "pain", "耐える", "抵抗", "泳ぐ", "毒", "我慢", "痛み")),
        ("int", ("decipher", "study", "analyze", "remember", "research", "solve", "read", "magic", "spell", "ritual", "知識", "解読", "分析", "研究", "調査", "読む", "思い出", "魔法", "呪文", "儀式")),
        ("wis", ("search", "investigate", "track", "notice", "sense", "listen", "find", "will", "focus", "fear", "curse", "探索", "探す", "調べ", "追跡", "気配", "聞き耳", "発見", "観察", "集中", "恐怖", "呪い")),
        ("cha", ("persuade", "convince", "negotiate", "deceive", "lie", "threaten", "perform", "bargain", "説得", "交渉", "騙す", "嘘", "脅す", "演奏", "値切", "魅力")),
    )
    for ability, keywords in ability_keywords:
        if any(keyword in lowered or keyword in text for keyword in keywords):
            return ability
    if purpose == "conversation":
        return "cha"
    if purpose == "exploration":
        return "wis"
    return "wis"


def normalise_ability(ability: str, *, fallback: str = "wis") -> str:
    key = str(ability or "").strip().lower()
    aliases = {
        "strength": "str",
        "筋力": "str",
        "constitution": "con",
        "endurance": "con",
        "耐久": "con",
        "dexterity": "dex",
        "器用": "dex",
        "intelligence": "int",
        "知力": "int",
        "wisdom": "wis",
        "judgement": "wis",
        "judgment": "wis",
        "判断": "wis",
        "charisma": "cha",
        "魅力": "cha",
        "magic": "int",
        "will": "wis",
    }
    resolved = aliases.get(key, key)
    return resolved if resolved in ACTION_ROLL_ABILITIES else fallback


def _normalise_roll_target(value: Any) -> int:
    number = max(6, min(18, _safe_int(value, 10)))
    return min((6, 8, 10, 12, 14, 16, 18), key=lambda target: (abs(target - number), target))


def _roll_ability_label(ability: str) -> str:
    return ACTION_ROLL_ABILITY_LABELS.get(normalise_ability(ability), str(ability or "能力"))


def _contains_any_action_roll_keyword(text: str, lowered: str) -> bool:
    keywords = (
        "search", "investigate", "examine", "lockpick", "pick lock", "force", "break", "climb", "jump",
        "swim", "sneak", "hide", "steal", "persuade", "convince", "threaten", "deceive", "negotiate",
        "bargain", "craft", "combine", "upgrade", "repair", "disarm", "track", "decipher", "cast",
        "ritual", "heal", "treat", "resist", "endure", "dodge", "chase", "trap", "forage", "harvest",
        "mine", "brew", "探索", "調査", "探す", "調べ", "開錠", "鍵", "こじ開け", "破壊", "登る",
        "跳ぶ", "泳ぐ", "忍び", "隠れる", "盗む", "説得", "交渉", "脅す", "騙す", "値切",
        "クラフト", "合成", "強化", "修理", "罠", "解読", "魔法", "儀式", "治療", "手当",
        "抵抗", "耐える", "回避", "追跡", "採取", "採掘", "調合",
    )
    return any(keyword in lowered or keyword in text for keyword in keywords)


def _looks_like_simple_auto_action(text: str, lowered: str) -> bool:
    simple_terms = (
        "周囲を見る", "見る", "確認", "話しかける", "会話", "依頼掲示板", "報告する", "受注する",
        "放棄する", "移動", "休息する", "保存箱を開く", "クラフトを行う", "家から出る",
        "look", "talk", "speak", "report", "accept", "abandon", "move", "rest",
    )
    return any(term in text or term in lowered for term in simple_terms)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, bool):
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback
