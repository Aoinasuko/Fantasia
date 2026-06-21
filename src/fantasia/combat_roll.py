from __future__ import annotations

import random
from typing import Any

from .combat_buff import effective_attributes
from .combat_model import normalise_combat_ability, safe_int


def ability_bonus(score: Any) -> int:
    return safe_int(score, 0) // 3


def roll_2d6(rng: random.Random | None = None) -> int:
    dice = rng or random
    return dice.randint(1, 6) + dice.randint(1, 6)


def ability_roll(character: Any, ability: str = "dex", rng: random.Random | None = None) -> dict[str, int | str]:
    ability_id = normalise_combat_ability(ability, "dex")
    attrs = effective_attributes(character)
    score = attrs.get(ability_id, 10)
    dice = roll_2d6(rng)
    bonus = ability_bonus(score)
    return {
        "ability": ability_id,
        "score": score,
        "dice": dice,
        "bonus": bonus,
        "total": dice + bonus,
    }


def opposed_ability_roll(
    attacker: Any,
    defender: Any,
    ability: str = "dex",
    rng: random.Random | None = None,
) -> dict[str, Any]:
    attack_roll = ability_roll(attacker, ability, rng)
    defense_roll = ability_roll(defender, ability, rng)
    return {
        "attacker": attack_roll,
        "defender": defense_roll,
        "success": safe_int(attack_roll.get("total"), 0) > safe_int(defense_roll.get("total"), 0),
    }
