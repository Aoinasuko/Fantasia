from __future__ import annotations

from typing import Any

from .combat_model import (
    as_list,
    character_attributes,
    combat_effect_type,
    normalise_combat_buff,
    safe_int,
)


def combat_buffs(value: Any) -> list[dict[str, Any]]:
    return [buff for buff in (normalise_combat_buff(item) for item in as_list(value)) if buff]


def buff_effects(buff: dict[str, Any], effect_type: str = "") -> list[dict[str, Any]]:
    effects: list[dict[str, Any]] = []
    for entry in as_list(buff.get("type")):
        if not isinstance(entry, dict):
            continue
        current = combat_effect_type(entry)
        if current and (not effect_type or current == effect_type):
            effects.append(entry)
    return effects


def has_buff_type(statuses: Any, effect_type: str) -> bool:
    return any(buff_effects(buff, effect_type) for buff in combat_buffs(statuses))


def status_blocks_attack(statuses: Any) -> bool:
    return has_buff_type(statuses, "restraint")


def status_blocks_escape(statuses: Any) -> bool:
    return has_buff_type(statuses, "restraint")


def status_blocks_skill(statuses: Any) -> bool:
    return has_buff_type(statuses, "psychosis")


def effective_attributes(character: Any) -> dict[str, int]:
    attrs = character_attributes(character)
    statuses = getattr(character, "status_effects", [])
    if has_buff_type(statuses, "paralysis"):
        attrs["str"] = max(1, attrs["str"] // 2)
        attrs["dex"] = max(1, attrs["dex"] // 2)
    return attrs


def stat_delta(statuses: Any) -> dict[str, int]:
    result = {"attack": 0, "defense": 0}
    for buff in combat_buffs(statuses):
        for effect in buff_effects(buff):
            effect_type = combat_effect_type(effect)
            amount = safe_int(effect.get("amount"), 0)
            if effect_type == "delta_atk":
                result["attack"] += amount
            elif effect_type == "delta_def":
                result["defense"] += amount
    return result


def tick_buffs(
    statuses: Any,
    actor_name: str,
    *,
    hours: int = 0,
    combat_turn: bool = False,
) -> tuple[list[dict[str, Any]], int, int, list[str]]:
    hp_delta = 0
    sp_delta = 0
    lines: list[str] = []
    updated: list[dict[str, Any]] = []
    for buff in combat_buffs(statuses):
        name = str(buff.get("name") or "状態")
        local_hp = 0
        local_sp = 0
        tick_count = 1 if combat_turn else max(0, hours)
        if tick_count > 0:
            for effect in buff_effects(buff):
                amount = abs(safe_int(effect.get("amount"), 0)) * tick_count
                effect_type = combat_effect_type(effect)
                if effect_type == "regen_hp":
                    local_hp += amount
                elif effect_type == "regen_sp":
                    local_sp += amount
                elif effect_type == "decrease_hp":
                    local_hp -= amount
                elif effect_type == "decrease_sp":
                    local_sp -= amount
        duration = safe_int(buff.get("duration"), 0)
        if hours > 0 and duration > 0:
            duration = max(0, duration - hours)
            buff["duration"] = duration
        if duration != 0:
            updated.append(buff)
        hp_delta += local_hp
        sp_delta += local_sp
        if local_hp:
            sign = f"+{local_hp}" if local_hp > 0 else str(local_hp)
            lines.append(f"> [状態] {actor_name}: {name} HP {sign}")
        if local_sp:
            sign = f"+{local_sp}" if local_sp > 0 else str(local_sp)
            lines.append(f"> [状態] {actor_name}: {name} SP {sign}")
    return updated, hp_delta, sp_delta, lines
