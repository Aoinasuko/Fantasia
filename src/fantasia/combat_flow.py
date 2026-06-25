from __future__ import annotations

import random
from typing import Any

from .character import Character
from .combat_buff import (
    accuracy_modifier,
    damage_taken_multiplier,
    effective_attributes,
    element_resistance_modifier,
    stat_delta,
    status_blocks_attack,
    status_blocks_escape,
    status_blocks_skill,
    status_has_taunt,
    thorns_modifier,
)
from .combat_llm_tool import (
    apply_combat_response_tools,
    combat_enemy_tool_instruction,
    combat_response_tool_calls,
    combat_tool_prompt_instruction,
    compact_combat_payload,
)
from .combat_model import (
    as_list,
    combat_effect_type,
    combat_skill_power,
    combat_skill_sp_cost,
    normalise_combat_buff,
    normalise_combat_skill,
    safe_int,
)
from .combat_resistance import damage_multiplier_for_element
from .combat_roll import ability_roll, opposed_ability_roll
from .items import calculate_equipment_summary


HP_DAMAGE_SKILL_EFFECT_TYPES = {
    "damage_hp_single",
    "damage_hp_party",
    "absorption_single",
    "absorption_party",
}


def resolve_player_attack(engine: Any, action: str, input_type: str, encounter: dict[str, Any]) -> str:
    engine._sync_player_battle_state(encounter)
    player = engine.player_character()
    target = engine._select_encounter_target_from_action(encounter, action)
    if not isinstance(player, Character) or not isinstance(target, Character):
        return _finish_without_enemy_turn(engine, action, input_type, encounter, "攻撃対象を見失った。")
    if status_blocks_attack(player.status_effects):
        response = {
            "narration": "体が動かず、攻撃できなかった。",
            "choices": engine._encounter_choices(encounter),
            "game_combat_result": {"type": "player_attack_blocked"},
        }
        return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_attack")
    response = _resolve_attack(
        engine,
        encounter,
        actor=player,
        target=target,
        action_name=action or "攻撃",
        element=_equipped_weapon_element(engine),
        source="player_attack",
    )
    return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_attack")


def resolve_player_skill(engine: Any, action: str, input_type: str, encounter: dict[str, Any]) -> str:
    engine._sync_player_battle_state(encounter)
    player = engine.player_character()
    skill = normalise_combat_skill(engine._find_player_skill(engine._extract_skill_name_for_combat(action)))
    if not isinstance(player, Character) or not skill:
        return _finish_without_enemy_turn(engine, action, input_type, encounter, f"スキル「{action}」は使用できない。")
    if status_blocks_skill(player.status_effects):
        response = {
            "narration": "体が動かず、スキルを使えなかった。",
            "choices": engine._encounter_choices(encounter),
            "game_combat_result": {"type": "player_skill_blocked"},
        }
        return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_skill")
    cost = combat_skill_sp_cost(skill)
    current_sp = safe_int(encounter.get("player_sp"), 0)
    if cost > current_sp:
        return _finish_without_enemy_turn(engine, action, input_type, encounter, f"SPが足りない。{skill['name']} はSP {cost} 必要。")
    if cost:
        event = engine._apply_player_sp_delta(-cost, source="skill", reason=str(skill.get("name") or ""), encounter=encounter)
        if event.get("line"):
            encounter.setdefault("pending_resource_lines", []).append(str(event["line"]))
    selector = getattr(engine, "_select_player_skill_target_from_action", None)
    if callable(selector):
        target = selector(encounter, action, skill)
    else:
        target = engine._select_encounter_target_from_action(encounter, action)
    response = _resolve_skill(engine, encounter, actor=player, target=target, skill=skill, action=action, source="player_skill")
    return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_skill")


def resolve_player_escape(engine: Any, action: str, input_type: str, encounter: dict[str, Any]) -> str:
    engine._sync_player_battle_state(encounter)
    player = engine.player_character()
    if not isinstance(player, Character):
        return _finish_without_enemy_turn(engine, action, input_type, encounter, "逃走しようとしたが、足がすくんだ。")
    if status_blocks_escape(player.status_effects):
        response = {
            "narration": "体が動かず、逃げ出せなかった。",
            "finished": False,
            "choices": engine._encounter_choices(encounter),
            "game_combat_result": {"type": "player_flee_blocked"},
        }
        return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_escape")
    player_roll = ability_roll(player, "dex")
    enemy_rolls = [ability_roll(opponent, "dex") for opponent in engine._acting_encounter_opponents(encounter)]
    success = all(safe_int(player_roll.get("total"), 0) >= safe_int(enemy.get("total"), 0) for enemy in enemy_rolls)
    if success:
        destination = _move_player_to_escape_destination(engine, encounter)
        encounter["status"] = "ended"
        engine.state.flags.pop("active_encounter", None)
        engine.state.flags["screen_mode"] = "exploration"
        narration = f"あなたは隙を突いて戦闘から離脱した。{destination}"
        response = {
            "narration": narration,
            "finished": True,
            "choices": engine._location_default_choices(engine.state.current_location),
            "game_combat_result": {"type": "player_flee", "success": True, "player_roll": player_roll, "enemy_rolls": enemy_rolls},
        }
        _record_and_append(engine, action, input_type, encounter, response, "combat_player_escape", [], already_finished=True)
        engine.save_game()
        return engine.state.log_text(16)
    response = {
        "narration": "あなたは逃げ道を探したが、相手に先回りされて離脱できなかった。",
        "finished": False,
        "choices": engine._encounter_choices(encounter),
        "game_combat_result": {"type": "player_flee", "success": False, "player_roll": player_roll, "enemy_rolls": enemy_rolls},
    }
    return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_escape")


def resolve_player_free_action(engine: Any, action: str, input_type: str, encounter: dict[str, Any]) -> str:
    engine._sync_player_battle_state(encounter)
    response = _combat_player_action_intent(engine, action, input_type, encounter)
    return finish_combat_round(engine, action, input_type, encounter, response, "combat_player_action")


def finish_combat_round(
    engine: Any,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    player_response: dict[str, Any],
    player_manager: str,
) -> str:
    status_lines = list(encounter.pop("pending_resource_lines", []))
    player_tools = apply_combat_response_tools(
        engine,
        player_response,
        source=player_manager,
        action=action,
        input_type=input_type,
        encounter=encounter,
    )
    status_lines.extend(player_tools.status_lines)
    if player_tools.results:
        player_response["combat_tools"] = player_tools.to_record()
    if player_tools.finished:
        player_response["finished"] = True
    outcome = engine._apply_encounter_outcome(encounter)
    status_lines.extend(engine._apply_quest_encounter_outcome(encounter, outcome))
    narration_parts = [str(player_response.get("narration") or "")]
    if outcome.get("narration"):
        narration_parts.append(str(outcome.get("narration")))
    finished = bool(player_response.get("finished")) or bool(outcome.get("ended")) or engine._is_game_over()
    manager_records = [{"manager": player_manager, "response": engine._strip_response_metadata_for_combat(player_response)}]
    if not finished:
        for companion in list(_acting_party_companions(engine)):
            ally_response, ally_lines = _resolve_ally_turn(engine, action, input_type, encounter, player_response, companion)
            status_lines.extend(ally_lines)
            status_lines.extend(str(line) for line in encounter.pop("pending_resource_lines", []) if str(line).strip())
            manager_records.append(
                {
                    "manager": "combat_ally_action",
                    "companion": companion.name,
                    "response": engine._strip_response_metadata_for_combat(ally_response),
                }
            )
            if ally_response.get("narration"):
                narration_parts.append(str(ally_response.get("narration")))
            outcome = engine._apply_encounter_outcome(encounter)
            status_lines.extend(engine._apply_quest_encounter_outcome(encounter, outcome))
            if outcome.get("narration"):
                narration_parts.append(str(outcome.get("narration")))
            if bool(ally_response.get("finished")) or bool(outcome.get("ended")) or engine._is_game_over():
                finished = True
                break
    if not finished:
        for opponent in list(engine._acting_encounter_opponents(encounter)):
            engine._set_encounter_active_opponent(encounter, opponent)
            enemy_response, enemy_lines = _resolve_enemy_turn(engine, action, input_type, encounter, player_response, opponent)
            status_lines.extend(enemy_lines)
            status_lines.extend(str(line) for line in encounter.pop("pending_resource_lines", []) if str(line).strip())
            manager_records.append(
                {
                    "manager": "combat_enemy_action",
                    "opponent": opponent.name,
                    "response": engine._strip_response_metadata_for_combat(enemy_response),
                }
            )
            if enemy_response.get("narration"):
                narration_parts.append(str(enemy_response.get("narration")))
            outcome = engine._apply_encounter_outcome(encounter)
            status_lines.extend(engine._apply_quest_encounter_outcome(encounter, outcome))
            if outcome.get("narration"):
                narration_parts.append(str(outcome.get("narration")))
            if bool(enemy_response.get("finished")) or bool(outcome.get("ended")) or engine._is_game_over():
                finished = True
                break
    if not engine._is_game_over() and not bool(outcome.get("ended")):
        status_lines.extend(engine._tick_encounter_status_effects(encounter))
        status_lines.extend(engine._apply_equipment_regen_effects("combat_turn", encounter=encounter))
        outcome = engine._apply_encounter_outcome(encounter)
        status_lines.extend(engine._apply_quest_encounter_outcome(encounter, outcome))
        if outcome.get("narration"):
            narration_parts.append(str(outcome.get("narration")))
    game_over = engine._is_game_over() or bool(outcome.get("game_over"))
    living = engine._living_encounter_opponents(encounter)
    if game_over:
        engine.state.flags["screen_mode"] = "game_over"
        engine.state.flags.pop("active_encounter", None)
        choices = engine._game_over_choices_for_combat()
    elif finished or bool(outcome.get("ended")) or not living:
        encounter["status"] = "ended"
        engine._update_encounter_presence(encounter, str(outcome.get("opponent_state") or "gone"))
        engine.state.flags.pop("active_encounter", None)
        engine.state.flags["screen_mode"] = "exploration"
        choices = engine._location_default_choices(str(encounter.get("location") or engine.state.current_location))
    else:
        encounter["status"] = "active"
        acting = engine._acting_encounter_opponents(encounter)
        if acting:
            engine._set_encounter_active_opponent(encounter, acting[0])
        engine._update_encounter_presence(encounter, "present")
        engine.state.flags["active_encounter"] = encounter
        engine.state.flags["screen_mode"] = "battle"
        choices = engine._encounter_choices(encounter)
    narration = "\n".join(part for part in [*narration_parts, "\n".join(status_lines)] if str(part).strip()).strip()
    if not narration:
        narration = "戦闘の状況が変化した。"
    _record_and_append(engine, action, input_type, encounter, player_response, player_manager, manager_records, choices=choices, narration=narration)
    engine.save_game()
    return engine.state.log_text(16)


def _finish_without_enemy_turn(engine: Any, action: str, input_type: str, encounter: dict[str, Any], narration: str) -> str:
    engine.state.flags["screen_mode"] = "battle"
    engine._append_turn(action, narration, str(encounter.get("location") or engine.state.current_location), engine._encounter_choices(encounter), input_type=input_type)
    engine.save_game()
    return engine.state.log_text(16)


def _record_and_append(
    engine: Any,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    player_response: dict[str, Any],
    player_manager: str,
    manager_records: list[dict[str, Any]],
    *,
    choices: list[str] | None = None,
    narration: str | None = None,
    already_finished: bool = False,
) -> None:
    if not manager_records:
        manager_records = [{"manager": player_manager, "response": engine._strip_response_metadata_for_combat(player_response)}]
    engine._record_encounter_turn(action, input_type, encounter, manager_records)
    for record in manager_records:
        engine.state.world_data.history.append(
            {
                "manager": record["manager"],
                "action": action,
                "input_type": input_type,
                "opponent": record.get("opponent"),
                "companion": record.get("companion"),
                "encounter": engine._strip_encounter_log_for_combat(encounter),
                "response": record["response"],
            }
        )
    location = str(encounter.get("location") or engine.state.current_location)
    resolved_choices = choices if choices is not None else engine._encounter_choices(encounter)
    engine._append_turn(action, narration or str(player_response.get("narration") or ""), location, resolved_choices, input_type=input_type)
    if already_finished:
        encounter["status"] = "ended"


def _resolve_attack(
    engine: Any,
    encounter: dict[str, Any],
    *,
    actor: Character,
    target: Character,
    action_name: str,
    element: str,
    source: str,
) -> dict[str, Any]:
    engine._set_encounter_active_opponent(encounter, target)
    weapon = _equipped_weapon_for_attack(engine, actor)
    action_name = _weapon_attack_name(weapon, action_name)
    element = _weapon_attack_element(weapon, element)
    hit_roll = opposed_ability_roll(actor, target, "dex", attacker_modifier=accuracy_modifier(actor.status_effects))
    actor_name = actor.name or "攻撃者"
    target_name = target.name or "相手"
    if not hit_roll.get("success"):
        calc = {"type": source, "hit": False, "element": element, "hit_roll": hit_roll, "damage": 0}
        if weapon:
            calc["weapon"] = _weapon_payload(weapon)
        narration = _narrate_combat_event(
            engine,
            {
                "event": "attack_miss",
                "actor": actor_name,
                "target": target_name,
                "action": action_name,
                "equipped_weapon": _weapon_payload(weapon),
                "description_priority": _weapon_description_priority(weapon),
                "result": calc,
            },
            f"{actor_name}の{action_name}は、{target_name}にかわされた。",
        )
        return {"narration": narration, "choices": engine._encounter_choices(encounter), "game_combat_result": calc}
    attack = _attack_value(engine, actor, encounter)
    defense = _defense_value(engine, target, encounter)
    attrs = effective_attributes(actor)
    strength_factor = max(0.5, attrs.get("str", 10) / 10.0)
    multiplier, multiplier_calc = _element_damage_multiplier(target, element, _equipment_summary_for(engine, target))
    base = max(1, attack - defense)
    damage_before_taken_modifier = 0 if multiplier <= 0 else max(1, int(round(base * strength_factor * multiplier)))
    damage, taken_calc = _apply_damage_taken_modifier(target, damage_before_taken_modifier)
    result = engine._apply_opponent_hp_delta(encounter, -damage, source=source, reason=action_name)
    if result.get("lines"):
        encounter.setdefault("pending_resource_lines", []).extend(str(line) for line in result.get("lines", []))
    reflection = _apply_thorns_reflection(engine, encounter, actor, target, _actual_hp_damage(result, damage), source=source, reason=action_name)
    calc = {
        "type": source,
        "hit": True,
        "element": element,
        "attack": attack,
        "defense": defense,
        "base_damage": base,
        "str": attrs.get("str", 10),
        "strength_factor": round(strength_factor, 3),
        "resistance_multiplier": round(multiplier, 3),
        **multiplier_calc,
        "damage_before_taken_modifier": damage_before_taken_modifier,
        **taken_calc,
        "damage": damage,
        "old_hp": result.get("old_hp"),
        "new_hp": result.get("new_hp"),
        "max_hp": result.get("max_hp"),
        "hit_roll": hit_roll,
    }
    if weapon:
        calc["weapon"] = _weapon_payload(weapon)
    if reflection:
        calc["thorns_reflection"] = reflection
    narration = _narrate_combat_event(
        engine,
        {
            "event": "attack_hit",
            "actor": actor_name,
            "target": target_name,
            "action": action_name,
            "equipped_weapon": _weapon_payload(weapon),
            "description_priority": _weapon_description_priority(weapon),
            "result": calc,
        },
        f"{actor_name}の{action_name}が{target_name}に命中した。",
    )
    calc["narration"] = narration
    engine.state.world_data.extra.setdefault("combat_events", []).append(dict(calc))
    return {"narration": narration, "choices": engine._encounter_choices(encounter), "game_combat_result": calc}


def _resolve_skill(
    engine: Any,
    encounter: dict[str, Any],
    *,
    actor: Character,
    target: Character | None,
    skill: dict[str, Any],
    action: str,
    source: str,
) -> dict[str, Any]:
    skill_name = str(skill.get("name") or action or "スキル")
    effects = as_list(skill.get("type"))
    hp_damage_effect_count = _skill_hp_damage_effect_count(effects)
    targets = [target] if isinstance(target, Character) else []
    if _is_player_side_actor(engine, actor) and _skill_has_enemy_single_offense(effects):
        targets = _constrain_enemy_targets_for_actor(engine, encounter, actor, targets)
    if not targets and _skill_has_enemy_single_offense(effects):
        targets = _enemy_targets_for_actor(engine, encounter, actor)
    narration_bits: list[str] = []
    calc_results: list[dict[str, Any]] = []
    for effect in effects:
        effect_type = combat_effect_type(effect)
        if effect_type in {"damage_hp_single", "absorption_single"}:
            for item in targets[:1]:
                calc_results.append(_apply_skill_hp_damage(engine, encounter, actor, item, skill, effect, source=source, effect_count=hp_damage_effect_count))
        elif effect_type in {"damage_hp_party", "absorption_party"}:
            for item in engine._living_encounter_opponents(encounter):
                calc_results.append(_apply_skill_hp_damage(engine, encounter, actor, item, skill, effect, source=source, effect_count=hp_damage_effect_count))
        elif effect_type == "damage_sp_single":
            for item in targets[:1]:
                calc_results.append(_apply_skill_sp_damage(engine, encounter, actor, item, skill, effect))
        elif effect_type == "damage_sp_party":
            for item in engine._living_encounter_opponents(encounter):
                calc_results.append(_apply_skill_sp_damage(engine, encounter, actor, item, skill, effect))
        elif effect_type == "heal_single":
            heal_targets = targets[:1] if targets else [actor]
            for item in heal_targets:
                calc_results.append(_apply_skill_hp_heal(engine, encounter, actor, item, skill, effect, source=source))
        elif effect_type == "heal_party":
            for item in _same_side_targets(engine, encounter, actor):
                calc_results.append(_apply_skill_hp_heal(engine, encounter, actor, item, skill, effect, source=source))
        elif effect_type in {"effect_enemy_single", "effect_enemy_party"}:
            affected = targets[:1] if effect_type.endswith("_single") else engine._living_encounter_opponents(encounter)
            for item in affected:
                calc_results.append(_apply_skill_buff(item, skill, effect))
        elif effect_type == "effect_self":
            calc_results.append(_apply_skill_buff(actor, skill, effect))
        elif effect_type in {"effect_ally_single", "effect_ally_party"}:
            affected = (targets[:1] if targets else [actor]) if effect_type.endswith("_single") else _same_side_targets(engine, encounter, actor)
            for item in affected:
                calc_results.append(_apply_skill_buff(item, skill, effect))
    for calc in calc_results:
        if calc.get("absorb_heal"):
            heal_event = _apply_character_hp_delta(engine, encounter, actor, calc.get("absorb_heal"), source=source, reason=skill_name)
            for line in heal_event.get("lines", []):
                encounter.setdefault("pending_resource_lines", []).append(str(line))
            if heal_event.get("line"):
                encounter.setdefault("pending_resource_lines", []).append(str(heal_event["line"]))
    fallback = f"{actor.name}は{skill_name}を使った。"
    narration = _narrate_combat_event(
        engine,
        {
            "event": "skill",
            "actor": actor.name,
            "skill": skill,
            "action": action,
            "results": calc_results,
        },
        fallback,
    )
    if narration:
        narration_bits.append(narration)
    engine.state.world_data.extra.setdefault("combat_events", []).append({"type": source, "skill": skill_name, "results": calc_results})
    return {
        "narration": "\n".join(narration_bits) or fallback,
        "choices": engine._encounter_choices(encounter),
        "game_combat_result": {"type": source, "skill": skill_name, "results": calc_results},
    }


def _apply_skill_hp_damage(
    engine: Any,
    encounter: dict[str, Any],
    actor: Character,
    target: Character,
    skill: dict[str, Any],
    effect: Any,
    *,
    source: str,
    effect_count: int = 1,
) -> dict[str, Any]:
    amount, calculation = _skill_hp_damage_amount(engine, encounter, actor, target, skill, effect, effect_count=effect_count)
    engine._set_encounter_active_opponent(encounter, target)
    result = engine._apply_opponent_hp_delta(encounter, -amount, source=source, reason=str(skill.get("name") or "skill"))
    if result.get("lines"):
        encounter.setdefault("pending_resource_lines", []).extend(str(line) for line in result.get("lines", []))
    reflection = _apply_thorns_reflection(engine, encounter, actor, target, _actual_hp_damage(result, amount), source=source, reason=str(skill.get("name") or "skill"))
    calc = {
        "type": combat_effect_type(effect),
        "target": target.name,
        "element": str(skill.get("element") or "physical"),
        "amount": amount,
        "old_hp": result.get("old_hp"),
        "new_hp": result.get("new_hp"),
        "max_hp": result.get("max_hp"),
    }
    calc.update(calculation)
    if reflection:
        calc["thorns_reflection"] = reflection
    if combat_effect_type(effect).startswith("absorption"):
        calc["absorb_heal"] = max(1, amount // 2)
    return calc


def _apply_skill_hp_heal(
    engine: Any,
    encounter: dict[str, Any],
    actor: Character,
    target: Character,
    skill: dict[str, Any],
    effect: Any,
    *,
    source: str,
) -> dict[str, Any]:
    amount = _skill_base_amount(actor, skill)
    event = _apply_character_hp_delta(engine, encounter, target, amount, source=source, reason=str(skill.get("name") or "skill"))
    for line in event.get("lines", []):
        encounter.setdefault("pending_resource_lines", []).append(str(line))
    if event.get("line"):
        encounter.setdefault("pending_resource_lines", []).append(str(event["line"]))
    return {
        "type": combat_effect_type(effect),
        "target": target.name,
        "amount": amount,
        "old_hp": event.get("old_hp"),
        "new_hp": event.get("new_hp"),
        "max_hp": event.get("max_hp"),
    }


def _apply_skill_sp_damage(
    engine: Any,
    encounter: dict[str, Any],
    actor: Character,
    target: Character,
    skill: dict[str, Any],
    effect: Any,
) -> dict[str, Any]:
    amount = _skill_amount(actor, target, skill)
    old_sp = safe_int(target.current_sp, 0)
    target.current_sp = max(0, old_sp - amount)
    target.extra["current_sp"] = target.current_sp
    return {"type": combat_effect_type(effect), "target": target.name, "amount": amount, "old_sp": old_sp, "new_sp": target.current_sp}


def _apply_skill_buff(target: Character, skill: dict[str, Any], effect: Any) -> dict[str, Any]:
    if not isinstance(effect, dict):
        effect = {}
    buff_type = str(effect.get("buff_type") or effect.get("status_type") or "send_llm").strip()
    amount = safe_int(effect.get("amount"), 1)
    buff_effect = {"type": buff_type, "amount": amount}
    for key in ("element", "target_element", "element_type"):
        if effect.get(key) not in (None, "", [], {}):
            buff_effect[key] = effect.get(key)
    buff = normalise_combat_buff(
        {
            "name": str(effect.get("name") or f"{skill.get('name')}の影響"),
            "desc": str(effect.get("desc") or skill.get("desc") or ""),
            "duration": safe_int(effect.get("duration"), 1),
            "condition_cancell": str(effect.get("condition_cancell") or "時間経過、治療、または状況の解消。"),
            "type": [buff_effect],
        }
    )
    if buff:
        target.status_effects.append(buff)
    return {"type": combat_effect_type(effect), "target": target.name, "buff": buff}


def _acting_party_companions(engine: Any) -> list[Character]:
    companions: list[Character] = []
    for companion in engine._party_companions():
        if not isinstance(companion, Character):
            continue
        engine._ensure_character_runtime_data(companion)
        state = str(companion.state or "").strip().casefold()
        if state in {"dead", "defeated"}:
            continue
        if safe_int(companion.current_hp, 0) <= 0:
            continue
        companions.append(companion)
    return companions


def _resolve_ally_turn(
    engine: Any,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    player_response: dict[str, Any],
    companion: Character,
) -> tuple[dict[str, Any], list[str]]:
    engine._ensure_character_runtime_data(companion)
    decision = _combat_ally_action(engine, action, input_type, encounter, player_response, companion)
    action_type = str(decision.get("action_type") or "attack").strip()
    lines: list[str] = []
    if action_type in {"attack", "status_attack"} and status_blocks_attack(companion.status_effects):
        decision["action_type"] = "free_action"
        decision["narration"] = decision.get("narration") or f"{companion.name}は拘束され、攻撃に移れない。"
        return decision, lines
    if action_type == "skill" and status_blocks_skill(companion.status_effects):
        decision["action_type"] = "free_action"
        decision["narration"] = decision.get("narration") or f"{companion.name}は精神を乱され、スキルを使えない。"
        return decision, lines
    if action_type == "skill":
        skill = _ally_skill_from_decision(companion, decision)
        if skill:
            cost = combat_skill_sp_cost(skill)
            old_sp = max(0, safe_int(companion.current_sp, 0))
            if old_sp >= cost:
                companion.current_sp = max(0, old_sp - cost)
                companion.extra["current_sp"] = companion.current_sp
                engine._sync_companion_party_entry(companion)
                lines.append(
                    f"> [SP] {companion.name}: {old_sp}/{max(1, safe_int(companion.max_sp, 1))} "
                    f"-> {companion.current_sp}/{max(1, safe_int(companion.max_sp, 1))} (-{cost})"
                )
                target = _select_ally_skill_target(engine, encounter, companion, skill, decision)
                response = _resolve_skill(engine, encounter, actor=companion, target=target, skill=skill, action=str(skill.get("name") or action), source="ally_skill")
                engine._sync_companion_party_entry(companion)
                return {**decision, **response}, lines
            decision["narration"] = decision.get("narration") or f"{companion.name}は{skill.get('name')}を使おうとしたが、SPが足りない。"
            decision["action_type"] = "free_action"
            return decision, lines
        decision["action_type"] = "attack"
    if action_type == "free_action":
        decision.setdefault("narration", f"{companion.name}は状況を見極めている。")
        return decision, lines
    target = _select_ally_enemy_target(engine, encounter, decision)
    if not isinstance(target, Character):
        decision["finished"] = True
        decision["narration"] = decision.get("narration") or f"{companion.name}は攻撃できる敵を見失った。"
        return decision, lines
    attack_name, element = _enemy_attack_from_decision(companion, decision)
    response = _resolve_attack(
        engine,
        encounter,
        actor=companion,
        target=target,
        action_name=attack_name,
        element=element,
        source="ally_attack",
    )
    engine._sync_companion_party_entry(companion)
    return {**decision, **response}, lines


def _combat_ally_action(
    engine: Any,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    player_response: dict[str, Any],
    companion: Character,
) -> dict[str, Any]:
    payload = {
        "instruction": (
            "Return compact combat JSON for an allied party NPC. Use action_type only: "
            "attack, status_attack, skill, free_action. The game calculates HP/SP locally. "
            "Do not use combat tools and do not set resource deltas. Choose target_name from enemies "
            "for attacks, and from allies for healing or ally buffs."
        ),
        "action": action,
        "input_type": input_type,
        "ally": _combat_character_payload(companion),
        "attacks": companion.extra.get("combat_attacks") or companion.extra.get("attacks") or [],
        "skills": companion.skills,
        "allies": [_combat_character_payload(character) for character in _ally_targets(engine)],
        "enemies": [_combat_character_payload(character) for character in engine._living_encounter_opponents(encounter)],
        "player_result": player_response.get("game_combat_result") or player_response,
        "recent_log": engine.state.log_text(6),
    }
    try:
        response = engine._chat_json(
            "combat_ally_action",
            [
                {
                    "role": "system",
                    "content": (
                        "You decide one autonomous combat action for a party companion NPC. "
                        "Respect the companion's personality, skills, current HP/SP, and visible enemies. "
                        "Return JSON only with action_type, optional attack_name, skill_name, target_name, "
                        "element, narration, and choices."
                    ),
                },
                {"role": "user", "content": compact_combat_payload(payload)},
            ],
            max_tokens=300,
            world_name=engine.state.world_name,
            player_name=engine.state.player_name,
            retries=1,
        )
    except Exception:
        response = {}
    if not isinstance(response, dict):
        response = {}
    response.setdefault("action_type", _fallback_ally_action_type(engine, encounter, companion))
    response.setdefault("choices", engine._encounter_choices(encounter))
    return response


def _fallback_ally_action_type(engine: Any, encounter: dict[str, Any], companion: Character) -> str:
    if status_blocks_attack(companion.status_effects):
        return "free_action"
    for skill in _usable_ally_skills(companion):
        if safe_int(companion.current_sp, 0) < combat_skill_sp_cost(skill):
            continue
        if _skill_has_ally_effect(skill) and _wounded_ally_target(engine):
            return "skill"
    if engine._living_encounter_opponents(encounter):
        return "attack"
    return "free_action"


def _combat_character_payload(character: Character) -> dict[str, Any]:
    max_hp = max(1, safe_int(character.max_hp, 1))
    max_sp = max(1, safe_int(character.max_sp, 1))
    current_hp = max(0, min(max_hp, safe_int(character.current_hp, max_hp)))
    current_sp = max(0, min(max_sp, safe_int(character.current_sp, max_sp)))
    return {
        "name": character.name,
        "uuid": character.uuid,
        "role": character.role,
        "category": character.category,
        "level": character.level,
        "current_hp": current_hp,
        "max_hp": max_hp,
        "hp_ratio": round(current_hp / max_hp, 3),
        "current_sp": current_sp,
        "max_sp": max_sp,
        "sp_ratio": round(current_sp / max_sp, 3),
        "attack": character.attack,
        "defense": character.defense,
        "attributes": dict(character.attributes or {}),
        "status_effects": character.status_effects,
        "personality": character.personality,
        "traits": character.traits,
    }


def _combat_inventory_payload(engine: Any, *, limit: int = 18) -> list[dict[str, Any]]:
    try:
        inventory = engine._player_inventory()
    except Exception:
        inventory = []
    result: list[dict[str, Any]] = []
    for item in inventory:
        if not isinstance(item, dict):
            continue
        data: dict[str, Any] = {
            "name": str(item.get("name") or ""),
            "category": str(item.get("category") or ""),
            "quantity": max(1, safe_int(item.get("quantity"), 1)),
            "item_uuid": str(item.get("item_uuid") or ""),
        }
        effects = item.get("effects")
        if isinstance(effects, list) and effects:
            data["effects"] = effects[:4]
        result.append(data)
        if len(result) >= limit:
            break
    return result


def _ally_skill_from_decision(companion: Character, decision: dict[str, Any]) -> dict[str, Any]:
    wanted = str(decision.get("skill_name") or decision.get("skill") or "").strip()
    skills = _usable_ally_skills(companion)
    if wanted:
        for skill in skills:
            if str(skill.get("name") or "").strip() == wanted:
                return skill
    if str(decision.get("action_type") or "").strip() == "skill":
        if wanted:
            lowered = wanted.casefold()
            for skill in skills:
                name = str(skill.get("name") or "")
                if lowered in name.casefold() or name.casefold() in lowered:
                    return skill
        for skill in skills:
            if _skill_has_ally_effect(skill):
                return skill
        return skills[0] if skills else {}
    return {}


def _usable_ally_skills(companion: Character) -> list[dict[str, Any]]:
    skills = [normalise_combat_skill(item) for item in as_list(companion.skills)]
    return [skill for skill in skills if skill]


def _select_ally_skill_target(
    engine: Any,
    encounter: dict[str, Any],
    companion: Character,
    skill: dict[str, Any],
    decision: dict[str, Any],
) -> Character | None:
    effect_types = {combat_effect_type(effect) for effect in as_list(skill.get("type"))}
    target_name = str(decision.get("target_name") or decision.get("target") or "").strip()
    if any(effect_type in {"heal_party", "effect_ally_party", "effect_self"} for effect_type in effect_types):
        return companion if "effect_self" in effect_types else None
    if any(effect_type in {"heal_single", "effect_ally_single"} for effect_type in effect_types):
        target = _match_character_by_text(_ally_targets(engine), target_name)
        if isinstance(target, Character):
            return target
        if "heal_single" in effect_types:
            wounded = _wounded_ally_target(engine)
            if isinstance(wounded, Character):
                return wounded
        return companion
    taunting = _taunting_enemies(engine, encounter)
    candidates = taunting or engine._living_encounter_opponents(encounter)
    target = _match_character_by_text(candidates, target_name)
    return target if isinstance(target, Character) else _select_ally_enemy_target(engine, encounter, decision)


def _select_ally_enemy_target(engine: Any, encounter: dict[str, Any], decision: dict[str, Any]) -> Character | None:
    target_name = str(decision.get("target_name") or decision.get("target") or decision.get("opponent") or "").strip()
    taunting = _taunting_enemies(engine, encounter)
    candidates = taunting or engine._living_encounter_opponents(encounter)
    target = _match_character_by_text(candidates, target_name)
    if isinstance(target, Character):
        engine._set_encounter_active_opponent(encounter, target)
        return target
    living = candidates
    if not living:
        return None
    engine._set_encounter_active_opponent(encounter, living[0])
    return living[0]


def _match_character_by_text(characters: list[Character], text: str) -> Character | None:
    text = str(text or "").strip()
    if not text:
        return None
    folded = text.casefold()
    for character in characters:
        terms = [character.name, character.uuid, character.role]
        terms.extend(str(item or "") for item in as_list(character.flags.get("aliases")) if str(item or "").strip())
        terms.extend(str(item or "") for item in as_list(character.extra.get("aliases")) if str(item or "").strip())
        for term in terms:
            term = str(term or "").strip()
            if not term:
                continue
            term_folded = term.casefold()
            if text == term or folded == term_folded or folded in term_folded or term_folded in folded:
                return character
    return None


def _ally_targets(engine: Any) -> list[Character]:
    targets = [item for item in [engine.player_character(), *engine._party_companions()] if isinstance(item, Character)]
    return [item for item in targets if safe_int(item.current_hp, 1) > 0]


def _characters_with_taunt(characters: list[Character]) -> list[Character]:
    return [character for character in characters if status_has_taunt(character.status_effects)]


def _taunting_allies(engine: Any) -> list[Character]:
    return _characters_with_taunt(_ally_targets(engine))


def _taunting_enemies(engine: Any, encounter: dict[str, Any]) -> list[Character]:
    return _characters_with_taunt(engine._living_encounter_opponents(encounter))


def _wounded_ally_target(engine: Any) -> Character | None:
    wounded: list[tuple[float, Character]] = []
    for character in _ally_targets(engine):
        max_hp = max(1, safe_int(character.max_hp, 1))
        current_hp = max(0, min(max_hp, safe_int(character.current_hp, max_hp)))
        if current_hp >= max_hp:
            continue
        wounded.append((current_hp / max_hp, character))
    if not wounded:
        return None
    wounded.sort(key=lambda item: item[0])
    return wounded[0][1]


def _skill_has_ally_effect(skill: dict[str, Any]) -> bool:
    return any(
        combat_effect_type(effect) in {"heal_single", "heal_party", "effect_ally_single", "effect_ally_party", "effect_self"}
        for effect in as_list(skill.get("type"))
    )


def _skill_has_enemy_single_offense(effects: Any) -> bool:
    return any(
        combat_effect_type(effect)
        in {
            "damage_hp_single",
            "damage_sp_single",
            "absorption_single",
            "effect_enemy_single",
        }
        for effect in as_list(effects)
    )


def _is_player_side_actor(engine: Any, actor: Character) -> bool:
    if actor.flags.get("is_player") or actor.uuid == engine.state.player_uuid:
        return True
    return any(companion.uuid == actor.uuid for companion in engine._party_companions())


def _enemy_targets_for_actor(engine: Any, encounter: dict[str, Any], actor: Character) -> list[Character]:
    if _is_player_side_actor(engine, actor):
        taunting = _taunting_enemies(engine, encounter)
        if taunting:
            return taunting
    return engine._living_encounter_opponents(encounter)


def _constrain_enemy_targets_for_actor(
    engine: Any,
    encounter: dict[str, Any],
    actor: Character,
    targets: list[Character],
) -> list[Character]:
    if not _is_player_side_actor(engine, actor):
        return targets
    taunting = _taunting_enemies(engine, encounter)
    if not taunting:
        return targets
    filtered = [target for target in targets if any(target.uuid == taunter.uuid for taunter in taunting)]
    return filtered or taunting[:1]


def _random_enemy_single_target(engine: Any) -> Character | None:
    taunting = _taunting_allies(engine)
    targets = taunting or _ally_targets(engine)
    return random.choice(targets) if targets else None


def _enemy_special_target_from_decision(engine: Any, decision: dict[str, Any]) -> Character | None:
    target_name = str(decision.get("target_name") or decision.get("target") or decision.get("player_side_target") or "").strip()
    target = _match_character_by_text(_ally_targets(engine), target_name)
    if isinstance(target, Character):
        return target
    player = engine.player_character()
    return player if isinstance(player, Character) else None


def _enemy_skill_has_hostile_single_effect(effects: Any) -> bool:
    return any(
        combat_effect_type(effect) in {"damage_hp_single", "absorption_single", "damage_sp_single", "effect_enemy_single"}
        for effect in as_list(effects)
    )


def _resolve_enemy_turn(
    engine: Any,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    player_response: dict[str, Any],
    opponent: Character,
) -> tuple[dict[str, Any], list[str]]:
    decision = _combat_enemy_action(engine, action, input_type, encounter, player_response, opponent)
    action_type = str(decision.get("action_type") or "attack").strip()
    lines: list[str] = []
    if _player_surrender_resolution_pending(encounter, player_response) and not _has_surrender_resolution_tool(decision):
        decision["tool_judgements"] = [
            {
                "name": "accept_player_surrender",
                "confidence": 1.0,
                "arguments": {"reason": "fallback_accept_after_player_surrender"},
            }
        ]
        decision["action_type"] = "free_action"
        action_type = "free_action"
        decision["narration"] = f"{opponent.name}はあなたの降伏を受け入れ、敵意を収めた。"
    tool_batch = apply_combat_response_tools(
        engine,
        decision,
        source="combat_enemy_action",
        action=action,
        input_type=input_type,
        encounter=encounter,
        opponent=opponent,
    )
    lines.extend(tool_batch.status_lines)
    if tool_batch.results:
        decision["combat_tools"] = tool_batch.to_record()
    if tool_batch.finished:
        decision["finished"] = True
        decision["narration"] = decision.get("narration") or "\n".join(lines)
        return decision, lines
    if action_type in {"attack", "status_attack"} and status_blocks_attack(opponent.status_effects):
        decision["action_type"] = "free_action"
        decision["narration"] = decision.get("narration") or f"{opponent.name}は拘束され、攻撃に移れない。"
        return decision, lines
    if action_type == "skill" and status_blocks_skill(opponent.status_effects):
        decision["action_type"] = "free_action"
        decision["narration"] = decision.get("narration") or f"{opponent.name}は精神を乱され、スキルを使えない。"
        return decision, lines
    if action_type == "flee" and status_blocks_escape(opponent.status_effects):
        decision["action_type"] = "free_action"
        decision["narration"] = decision.get("narration") or f"{opponent.name}は拘束され、逃走できない。"
        return decision, lines
    if action_type == "flee":
        result = apply_combat_response_tools(
            engine,
            {"tool_judgements": [{"name": "npc_flee", "confidence": 1.0, "arguments": {"reason": "enemy_action_type"}}]},
            source="combat_enemy_action",
            action=action,
            input_type=input_type,
            encounter=encounter,
            opponent=opponent,
        )
        lines.extend(result.status_lines)
        if result.results:
            decision["combat_tools"] = result.to_record()
        decision["finished"] = True
        decision["narration"] = decision.get("narration") or "\n".join(lines)
        return decision, lines
    if action_type == "surrender":
        result = apply_combat_response_tools(
            engine,
            {"tool_judgements": [{"name": "npc_surrender", "confidence": 1.0, "arguments": {"reason": "enemy_action_type"}}]},
            source="combat_enemy_action",
            action=action,
            input_type=input_type,
            encounter=encounter,
            opponent=opponent,
        )
        lines.extend(result.status_lines)
        if result.results:
            decision["combat_tools"] = result.to_record()
        decision["narration"] = decision.get("narration") or "\n".join(lines)
        return decision, lines
    if action_type == "skill":
        skill = _enemy_skill_from_decision(opponent, decision)
        if skill:
            engine._ensure_character_runtime_data(opponent)
            cost = combat_skill_sp_cost(skill)
            old_sp = max(0, safe_int(opponent.current_sp, 0))
            if old_sp < cost:
                decision["action_type"] = "free_action"
                decision["narration"] = decision.get("narration") or f"{opponent.name}は{skill.get('name')}を使おうとしたが、SPが足りなかった。"
                return decision, lines
            opponent.current_sp = max(0, old_sp - cost)
            opponent.extra["current_sp"] = opponent.current_sp
            lines.append(f"> [SP] {opponent.name}: {old_sp}/{max(1, safe_int(opponent.max_sp, 1))} -> {opponent.current_sp}/{max(1, safe_int(opponent.max_sp, 1))} (-{cost})")
            response = _resolve_enemy_skill(engine, encounter, opponent, skill, decision)
            return {**decision, **response}, lines
    if action_type == "status_attack":
        attack_name, element = _enemy_attack_from_decision(opponent, decision)
        target = _enemy_special_target_from_decision(engine, decision)
        response = _resolve_enemy_attack(engine, encounter, opponent, attack_name, element, target=target, prefer_weapon=False)
        buff_type = str(decision.get("buff_type") or decision.get("status_type") or "restraint").strip()
        combat_result = response.get("game_combat_result") if isinstance(response, dict) else {}
        if isinstance(target, Character) and isinstance(combat_result, dict) and bool(combat_result.get("hit")):
            buff = normalise_combat_buff(
                {
                    "name": str(decision.get("status_name") or f"{attack_name}の影響"),
                    "desc": str(decision.get("status_desc") or decision.get("narration") or ""),
                    "duration": safe_int(decision.get("duration"), 1),
                    "condition_cancell": str(decision.get("condition_cancell") or "時間経過、治療、または拘束の解除。"),
                    "type": [{"type": buff_type, "amount": safe_int(decision.get("amount"), 1)}],
                }
            )
            if buff:
                target.status_effects.append(buff)
                _sync_combat_character_state(engine, encounter, target)
                lines.append(f"> [状態] {target.name}: {buff['name']}が付与された。")
        return {**decision, **response}, lines
    if action_type == "free_action":
        decision.setdefault("narration", f"{opponent.name}は様子をうかがっている。")
        return decision, lines
    attack_name, element = _enemy_attack_from_decision(opponent, decision)
    response = _resolve_enemy_attack(engine, encounter, opponent, attack_name, element)
    return {**decision, **response}, lines


def _resolve_enemy_attack(
    engine: Any,
    encounter: dict[str, Any],
    opponent: Character,
    attack_name: str,
    element: str,
    *,
    target: Character | None = None,
    prefer_weapon: bool = True,
) -> dict[str, Any]:
    target = target if isinstance(target, Character) else _random_enemy_single_target(engine)
    if not isinstance(target, Character):
        return {"narration": f"{opponent.name}は攻撃の機を逃した。"}
    weapon = _equipped_weapon_for_attack(engine, opponent) if prefer_weapon else None
    attack_name = _weapon_attack_name(weapon, attack_name)
    element = _weapon_attack_element(weapon, element)
    hit_roll = opposed_ability_roll(opponent, target, "dex", attacker_modifier=accuracy_modifier(opponent.status_effects))
    if not hit_roll.get("success"):
        calc = {"type": "enemy_attack", "hit": False, "target": target.name, "target_uuid": target.uuid, "element": element, "hit_roll": hit_roll, "damage": 0}
        if weapon:
            calc["weapon"] = _weapon_payload(weapon)
        narration = _narrate_combat_event(
            engine,
            {
                "event": "enemy_attack_miss",
                "actor": opponent.name,
                "target": target.name,
                "action": attack_name,
                "equipped_weapon": _weapon_payload(weapon),
                "description_priority": _weapon_description_priority(weapon),
                "result": calc,
            },
            f"{opponent.name}の{attack_name}は、{target.name}に届かなかった。",
        )
        return {"narration": narration, "game_combat_result": calc}
    attack = _attack_value(engine, opponent, encounter)
    defense = _defense_value(engine, target, encounter)
    attrs = effective_attributes(opponent)
    strength_factor = max(0.5, attrs.get("str", 10) / 10.0)
    multiplier, multiplier_calc = _element_damage_multiplier(target, element, _equipment_summary_for(engine, target))
    base = max(1, attack - defense)
    damage_before_taken_modifier = 0 if multiplier <= 0 else max(1, int(round(base * strength_factor * multiplier)))
    damage, taken_calc = _apply_damage_taken_modifier(target, damage_before_taken_modifier)
    event = _apply_character_hp_delta(engine, encounter, target, -damage, source="enemy_attack", reason=opponent.name)
    _append_resource_event_lines(encounter, event)
    reflection = _apply_thorns_reflection(engine, encounter, opponent, target, _actual_hp_damage(event, damage), source="enemy_attack", reason=attack_name)
    calc = {
        "type": "enemy_attack",
        "hit": True,
        "target": target.name,
        "target_uuid": target.uuid,
        "element": element,
        "attack": attack,
        "defense": defense,
        "base_damage": base,
        "str": attrs.get("str", 10),
        "strength_factor": round(strength_factor, 3),
        "resistance_multiplier": round(multiplier, 3),
        **multiplier_calc,
        "damage_before_taken_modifier": damage_before_taken_modifier,
        **taken_calc,
        "damage": damage,
        "old_hp": event.get("old_hp"),
        "new_hp": event.get("new_hp"),
        "max_hp": event.get("max_hp"),
        "hit_roll": hit_roll,
    }
    if weapon:
        calc["weapon"] = _weapon_payload(weapon)
    if reflection:
        calc["thorns_reflection"] = reflection
    narration = _narrate_combat_event(
        engine,
        {
            "event": "enemy_attack_hit",
            "actor": opponent.name,
            "target": target.name,
            "action": attack_name,
            "equipped_weapon": _weapon_payload(weapon),
            "description_priority": _weapon_description_priority(weapon),
            "result": calc,
        },
        f"{opponent.name}の{attack_name}が{target.name}に命中した。",
    )
    return {"narration": narration, "game_combat_result": calc}


def _resolve_enemy_skill(engine: Any, encounter: dict[str, Any], opponent: Character, skill: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    player = engine.player_character()
    if not isinstance(player, Character):
        return {"narration": f"{opponent.name}は{skill.get('name')}を使おうとしたが、狙いを定められなかった。"}
    effects = as_list(skill.get("type"))
    hp_damage_effect_count = _skill_hp_damage_effect_count(effects)
    random_single_target = _random_enemy_single_target(engine) if _enemy_skill_has_hostile_single_effect(effects) else None
    results: list[dict[str, Any]] = []
    for effect in effects:
        effect_type = combat_effect_type(effect)
        if effect_type in {"damage_hp_single", "absorption_single"}:
            target = random_single_target if isinstance(random_single_target, Character) else player
            amount, calculation = _skill_hp_damage_amount(
                engine,
                encounter,
                opponent,
                target,
                skill,
                effect,
                equipment_summary=_equipment_summary_for(engine, target),
                effect_count=hp_damage_effect_count,
            )
            event = _apply_character_hp_delta(engine, encounter, target, -amount, source="enemy_skill", reason=str(skill.get("name") or ""))
            _append_resource_event_lines(encounter, event)
            reflection = _apply_thorns_reflection(engine, encounter, opponent, target, _actual_hp_damage(event, amount), source="enemy_skill", reason=str(skill.get("name") or ""))
            result_item = {"type": effect_type, "target": target.name, "target_uuid": target.uuid, "amount": amount, "old_hp": event.get("old_hp"), "new_hp": event.get("new_hp"), **calculation}
            if reflection:
                result_item["thorns_reflection"] = reflection
            results.append(result_item)
            if effect_type.startswith("absorption"):
                heal_event = _apply_character_hp_delta(engine, encounter, opponent, max(1, amount // 2), source="enemy_skill", reason=str(skill.get("name") or ""))
                _append_resource_event_lines(encounter, heal_event)
                results.append({"type": "absorb_heal", "target": opponent.name, "amount": heal_event.get("actual_delta", 0), "old_hp": heal_event.get("old_hp"), "new_hp": heal_event.get("new_hp")})
        elif effect_type in {"damage_hp_party", "absorption_party"}:
            amount, calculation = _skill_hp_damage_amount(
                engine,
                encounter,
                opponent,
                player,
                skill,
                effect,
                equipment_summary=engine.player_equipment_summary(),
                effect_count=hp_damage_effect_count,
            )
            event = engine._apply_player_hp_delta(-amount, source="enemy_skill", reason=str(skill.get("name") or ""), encounter=encounter)
            _append_resource_event_lines(encounter, event)
            reflection = _apply_thorns_reflection(engine, encounter, opponent, player, _actual_hp_damage(event, amount), source="enemy_skill", reason=str(skill.get("name") or ""))
            result_item = {"type": effect_type, "target": player.name, "amount": amount, "old_hp": event.get("old_hp"), "new_hp": event.get("new_hp"), **calculation}
            if reflection:
                result_item["thorns_reflection"] = reflection
            results.append(result_item)
            if effect_type.startswith("absorption"):
                heal_event = _apply_character_hp_delta(engine, encounter, opponent, max(1, amount // 2), source="enemy_skill", reason=str(skill.get("name") or ""))
                _append_resource_event_lines(encounter, heal_event)
                results.append({"type": "absorb_heal", "target": opponent.name, "amount": heal_event.get("actual_delta", 0), "old_hp": heal_event.get("old_hp"), "new_hp": heal_event.get("new_hp")})
        elif effect_type == "damage_sp_single":
            target = random_single_target if isinstance(random_single_target, Character) else player
            amount = _skill_amount(opponent, target, skill, equipment_summary=_equipment_summary_for(engine, target))
            event = _apply_character_sp_delta(engine, encounter, target, -amount, source="enemy_skill", reason=str(skill.get("name") or ""))
            _append_resource_event_lines(encounter, event)
            results.append({"type": effect_type, "target": target.name, "target_uuid": target.uuid, "amount": abs(safe_int(event.get("actual_delta"), 0)), "old_sp": event.get("old_sp"), "new_sp": event.get("new_sp")})
        elif effect_type == "damage_sp_party":
            event = engine._apply_player_sp_delta(-_skill_amount(opponent, player, skill, equipment_summary=engine.player_equipment_summary()), source="enemy_skill", reason=str(skill.get("name") or ""), encounter=encounter)
            _append_resource_event_lines(encounter, event)
            results.append({"type": effect_type, "target": player.name, "amount": abs(safe_int(event.get("actual_delta"), 0)), "old_sp": event.get("old_sp"), "new_sp": event.get("new_sp")})
        elif effect_type == "heal_single":
            results.append(_apply_skill_hp_heal(engine, encounter, opponent, opponent, skill, effect, source="enemy_skill"))
        elif effect_type == "heal_party":
            for item in _same_side_targets(engine, encounter, opponent):
                results.append(_apply_skill_hp_heal(engine, encounter, opponent, item, skill, effect, source="enemy_skill"))
        elif effect_type in {"effect_enemy_single", "effect_enemy_party"}:
            target = random_single_target if effect_type.endswith("_single") and isinstance(random_single_target, Character) else player
            results.append(_apply_skill_buff(target, skill, effect))
            _sync_combat_character_state(engine, encounter, target)
        elif effect_type == "effect_self":
            results.append(_apply_skill_buff(opponent, skill, effect))
        elif effect_type in {"effect_ally_single", "effect_ally_party"}:
            affected = [opponent] if effect_type.endswith("_single") else _same_side_targets(engine, encounter, opponent)
            for item in affected:
                results.append(_apply_skill_buff(item, skill, effect))
    narration = _narrate_combat_event(
        engine,
        {"event": "enemy_skill", "actor": opponent.name, "target": player.name, "skill": skill, "results": results, "decision": decision},
        f"{opponent.name}は{skill.get('name')}を使った。",
    )
    return {"narration": narration, "game_combat_result": {"type": "enemy_skill", "skill": skill.get("name"), "results": results}}


def _combat_player_action_intent(engine: Any, action: str, input_type: str, encounter: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "action": action,
        "input_type": input_type,
        "encounter": engine._strip_encounter_log_for_combat(encounter),
        "player": engine._encounter_player_payload(encounter),
        "opponent": engine._encounter_opponent_payload(encounter),
        "player_inventory": _combat_inventory_payload(engine, limit=18),
        "recent_log": engine.state.log_text(6),
    }
    try:
        response = engine._chat_json(
            "combat_player_action",
            [
                {
                    "role": "system",
                    "content": (
                        "戦闘中の自由行動intent担当です。HP/SPの変更や通常のitem_removeは決めず、短いnarrationとintentとchoicesを返してください。"
                        "賄賂、餌、食料、供物、説得、なだめる行動で敵が敵意を失って離脱するなら、npc_pacifyを使い、渡す品がある場合はarguments.itemに入れてください。"
                        "\n" + combat_tool_prompt_instruction()
                    ),
                },
                {"role": "user", "content": f"プレイヤー行動: {action}\n{compact_combat_payload(payload)}"},
            ],
            max_tokens=360,
            world_name=engine.state.world_name,
            player_name=engine.state.player_name,
            retries=1,
        )
    except Exception:
        response = {}
    narration = str(response.get("narration") or response.get("text") or f"あなたは「{action}」を試みた。")
    choices = [str(item) for item in as_list(response.get("choices")) if str(item).strip()]
    result = {"intent": str(response.get("intent") or "free_action"), "narration": narration, "choices": choices or engine._encounter_choices(encounter)}
    if isinstance(response.get("tool_judgements"), list):
        result["tool_judgements"] = response["tool_judgements"]
    return result


def _combat_enemy_action(
    engine: Any,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    player_response: dict[str, Any],
    opponent: Character,
) -> dict[str, Any]:
    payload = {
        "instruction": combat_enemy_tool_instruction(),
        "action": action,
        "input_type": input_type,
        "opponent": engine._encounter_opponent_payload(encounter),
        "attacks": opponent.extra.get("combat_attacks") or opponent.extra.get("attacks") or [],
        "skills": opponent.skills,
        "player": engine._encounter_player_payload(encounter),
        "player_side_targets": [_combat_character_payload(character) for character in _ally_targets(engine)],
        "player_result": player_response.get("game_combat_result") or player_response,
        "player_status": encounter.get("player_status"),
        "player_surrender_resolution_required": _player_surrender_resolution_pending(encounter, player_response),
        "recent_log": engine.state.log_text(6),
    }
    try:
        response = engine._chat_json(
            "combat_enemy_action",
            [
                {"role": "system", "content": combat_enemy_tool_instruction() + "\n" + combat_tool_prompt_instruction()},
                {"role": "user", "content": compact_combat_payload(payload)},
            ],
            max_tokens=320,
            world_name=engine.state.world_name,
            player_name=engine.state.player_name,
            retries=1,
        )
    except Exception:
        response = {}
    if not isinstance(response, dict):
        response = {}
    response.setdefault("action_type", "attack")
    response.setdefault("tool_judgements", [])
    response.setdefault("choices", engine._encounter_choices(encounter))
    return response


def _player_surrender_resolution_pending(encounter: dict[str, Any], player_response: dict[str, Any]) -> bool:
    if str(player_response.get("intent") or "").strip().casefold() == "surrender":
        return True
    if bool(encounter.get("surrender_resolution_pending")):
        return True
    return str(encounter.get("player_status") or "").strip().casefold() == "surrendering"


def _has_surrender_resolution_tool(response: dict[str, Any]) -> bool:
    names = {str(item.get("name") or "").strip().casefold().replace("-", "_").replace(" ", "_") for item in combat_response_tool_calls(response, source="combat_enemy_action")}
    return bool(
        names
        & {
            "accept_player_surrender",
            "capture_player",
            "reject_player_surrender",
        }
    )


def _narrate_combat_event(engine: Any, payload: dict[str, Any], fallback: str) -> str:
    try:
        response = engine._chat_json(
            "combat_log_narrator",
            [
                {
                    "role": "system",
                    "content": "ゲーム側で確定した戦闘結果だけを、矛盾なく1〜2文のログにしてください。数値や成否は変更しないでください。",
                },
                {"role": "user", "content": compact_combat_payload(payload, max_chars=1800)},
            ],
            max_tokens=220,
            world_name=engine.state.world_name,
            player_name=engine.state.player_name,
            retries=1,
        )
        narration = str(response.get("narration") or response.get("text") or response.get("message") or "").strip()
        return narration or fallback
    except Exception as exc:
        engine.state.world_data.extra.setdefault("combat_narration_errors", []).append({"manager": "combat_log_narrator", "error": str(exc), "payload": payload})
        return fallback


def _skill_base_amount(actor: Character, skill: dict[str, Any]) -> int:
    attrs = effective_attributes(actor)
    ability = str(skill.get("ability") or "str")
    score = max(1, safe_int(attrs.get(ability), 10))
    power = combat_skill_power(skill)
    return max(1, int(round(2 * score * power * random.uniform(0.5, 1.0))))


def _skill_hp_damage_effect_count(effects: Any) -> int:
    return max(1, sum(1 for effect in as_list(effects) if combat_effect_type(effect) in HP_DAMAGE_SKILL_EFFECT_TYPES))


def _skill_hp_damage_amount(
    engine: Any,
    encounter: dict[str, Any],
    actor: Character,
    target: Character,
    skill: dict[str, Any],
    effect: Any | None = None,
    *,
    equipment_summary: dict[str, Any] | None = None,
    effect_count: int = 1,
) -> tuple[int, dict[str, Any]]:
    base = _skill_base_amount(actor, skill)
    element = str(skill.get("element") or "physical").strip() or "physical"
    multiplier, multiplier_calc = _element_damage_multiplier(target, element, equipment_summary)
    count = max(1, safe_int(effect_count, 1))
    after_resistance = 0 if multiplier <= 0 else int(round(base * multiplier))
    before_mitigation = 0 if multiplier <= 0 else int(round(after_resistance / count))
    mitigation_type, mitigation = _skill_hp_damage_mitigation(engine, encounter, target, element)
    damage_after_mitigation = 0 if multiplier <= 0 else max(1, before_mitigation - mitigation)
    amount, taken_calc = _apply_damage_taken_modifier(target, damage_after_mitigation)
    return amount, {
        "base_amount": base,
        "resistance_multiplier": round(multiplier, 3),
        **multiplier_calc,
        "damage_effect_count": count,
        "effect_multiplier": round(1 / count, 3),
        "damage_before_mitigation": before_mitigation,
        "mitigation_type": mitigation_type,
        "mitigation": mitigation,
        "damage_after_mitigation": damage_after_mitigation,
        **taken_calc,
    }


def _skill_hp_damage_mitigation(engine: Any, encounter: dict[str, Any], target: Character, element: str) -> tuple[str, int]:
    if str(element or "physical").strip().casefold() == "physical":
        return "defense", max(0, _defense_value(engine, target, encounter) * 2)
    attrs = effective_attributes(target)
    intelligence = safe_int(attrs.get("int"), 10)
    equipment_summary = _equipment_summary_for(engine, target)
    equipment_attributes = equipment_summary.get("attributes") if isinstance(equipment_summary, dict) else None
    if isinstance(equipment_attributes, dict):
        intelligence += safe_int(equipment_attributes.get("int"), 0)
    return "int", max(0, intelligence * 2)


def _skill_amount(actor: Character, target: Character, skill: dict[str, Any], effect: Any | None = None, *, equipment_summary: dict[str, Any] | None = None) -> int:
    base = _skill_base_amount(actor, skill)
    multiplier = damage_multiplier_for_element(target, str(skill.get("element") or "physical"), equipment_summary)
    return 0 if multiplier <= 0 else max(1, int(round(base * multiplier)))


def _same_side_targets(engine: Any, encounter: dict[str, Any], actor: Character) -> list[Character]:
    if _is_player_side_actor(engine, actor):
        return _ally_targets(engine)
    return engine._living_encounter_opponents(encounter)


def _apply_character_hp_delta(
    engine: Any,
    encounter: dict[str, Any],
    target: Character,
    delta: int,
    *,
    source: str,
    reason: str = "",
) -> dict[str, Any]:
    if target.flags.get("is_player") or target.uuid == engine.state.player_uuid:
        return engine._apply_player_hp_delta(delta, source=source, reason=reason, encounter=encounter)
    old_hp = max(0, min(max(1, safe_int(target.max_hp, 1)), safe_int(target.current_hp, target.max_hp or 1)))
    max_hp = max(1, safe_int(target.max_hp, old_hp or 1))
    new_hp = max(0, min(max_hp, old_hp + int(delta)))
    actual_delta = new_hp - old_hp
    target.current_hp = new_hp
    target.max_hp = max_hp
    target.extra["current_hp"] = new_hp
    target.extra["max_hp"] = max_hp
    if _is_player_side_actor(engine, target):
        engine._sync_companion_party_entry(target)
    else:
        engine._sync_encounter_opponent_entry(encounter, target)
        engine._sync_companion_party_entry(target)
    sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
    return {
        "changed": actual_delta != 0,
        "old_hp": old_hp,
        "new_hp": new_hp,
        "max_hp": max_hp,
        "actual_delta": actual_delta,
        "lines": [f"> [HP] {target.name}: {old_hp}/{max_hp} -> {new_hp}/{max_hp} ({sign})"],
    }


def _apply_character_sp_delta(
    engine: Any,
    encounter: dict[str, Any],
    target: Character,
    delta: int,
    *,
    source: str,
    reason: str = "",
) -> dict[str, Any]:
    if target.flags.get("is_player") or target.uuid == engine.state.player_uuid:
        return engine._apply_player_sp_delta(delta, source=source, reason=reason, encounter=encounter)
    old_sp = max(0, min(max(1, safe_int(target.max_sp, 1)), safe_int(target.current_sp, target.max_sp or 1)))
    max_sp = max(1, safe_int(target.max_sp, old_sp or 1))
    new_sp = max(0, min(max_sp, old_sp + int(delta)))
    actual_delta = new_sp - old_sp
    target.current_sp = new_sp
    target.max_sp = max_sp
    target.extra["current_sp"] = new_sp
    target.extra["max_sp"] = max_sp
    _sync_combat_character_state(engine, encounter, target)
    sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
    return {
        "changed": actual_delta != 0,
        "old_sp": old_sp,
        "new_sp": new_sp,
        "max_sp": max_sp,
        "actual_delta": actual_delta,
        "lines": [f"> [SP] {target.name}: {old_sp}/{max_sp} -> {new_sp}/{max_sp} ({sign})"],
    }


def _sync_combat_character_state(engine: Any, encounter: dict[str, Any], target: Character) -> None:
    if target.flags.get("is_player") or target.uuid == engine.state.player_uuid:
        engine.state.status_effects = target.status_effects
        return
    if _is_player_side_actor(engine, target):
        engine._sync_companion_party_entry(target)
    else:
        engine._sync_encounter_opponent_entry(encounter, target)
        engine._sync_companion_party_entry(target)


def _append_resource_event_lines(encounter: dict[str, Any], event: dict[str, Any]) -> None:
    for line in event.get("lines", []):
        if str(line).strip():
            encounter.setdefault("pending_resource_lines", []).append(str(line))
    line = event.get("line")
    if str(line or "").strip():
        encounter.setdefault("pending_resource_lines", []).append(str(line))


def _element_damage_multiplier(
    target: Character,
    element: Any,
    equipment_summary: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    base = damage_multiplier_for_element(target, element, equipment_summary)
    modifier = element_resistance_modifier(target.status_effects, element)
    adjusted = max(0.0, base - modifier * 0.1)
    return adjusted, {
        "base_resistance_multiplier": round(base, 3),
        "element_res_mod": modifier,
    }


def _apply_damage_taken_modifier(target: Character, amount: int) -> tuple[int, dict[str, Any]]:
    amount = max(0, safe_int(amount, 0))
    modifier = damage_taken_multiplier(target.status_effects)
    if amount <= 0 or modifier <= 0:
        return 0, {"damage_taken_multiplier": round(modifier, 3)}
    return max(1, int(round(amount * modifier))), {"damage_taken_multiplier": round(modifier, 3)}


def _actual_hp_damage(event: dict[str, Any], fallback: int = 0) -> int:
    actual = event.get("actual_delta", event.get("delta"))
    damage = abs(safe_int(actual, 0))
    if damage <= 0:
        damage = max(0, safe_int(fallback, 0))
    return damage


def _apply_thorns_reflection(
    engine: Any,
    encounter: dict[str, Any],
    attacker: Character,
    defender: Character,
    damage: int,
    *,
    source: str,
    reason: str = "",
) -> dict[str, Any]:
    modifier = thorns_modifier(defender.status_effects)
    damage = max(0, safe_int(damage, 0))
    if modifier <= 0 or damage <= 0:
        return {}
    reflected = max(1, int(round(damage * modifier * 0.1)))
    event = _apply_character_hp_delta(engine, encounter, attacker, -reflected, source=f"{source}:thorns", reason=reason or defender.name)
    _append_resource_event_lines(encounter, event)
    return {
        "source": defender.name,
        "target": attacker.name,
        "thorns_mod": modifier,
        "base_damage": damage,
        "amount": reflected,
        "old_hp": event.get("old_hp"),
        "new_hp": event.get("new_hp"),
    }


def _attack_value(engine: Any, actor: Character, encounter: dict[str, Any]) -> int:
    if actor.flags.get("is_player") or actor.uuid == engine.state.player_uuid:
        return max(1, safe_int(actor.attack, 0) + safe_int(encounter.get("player_attack"), 0) + safe_int(encounter.get("player_attack_bonus"), 0))
    delta = stat_delta(actor.status_effects)
    equipment = _equipment_summary_for(engine, actor) or {}
    return max(1, safe_int(actor.attack, encounter.get("opponent_attack") or 1) + safe_int(equipment.get("attack"), 0) + safe_int(delta.get("attack"), 0))


def _defense_value(engine: Any, actor: Character, encounter: dict[str, Any]) -> int:
    if actor.flags.get("is_player") or actor.uuid == engine.state.player_uuid:
        return max(0, safe_int(actor.defense, 0) + safe_int(encounter.get("player_defense"), 0) + safe_int(encounter.get("player_defense_bonus"), 0))
    delta = stat_delta(actor.status_effects)
    equipment = _equipment_summary_for(engine, actor) or {}
    return max(0, safe_int(actor.defense, encounter.get("opponent_defense") or 0) + safe_int(equipment.get("defense"), 0) + safe_int(delta.get("defense"), 0))


def _equipment_summary_for(engine: Any, character: Character) -> dict[str, Any] | None:
    if character.flags.get("is_player") or character.uuid == engine.state.player_uuid:
        return engine.player_equipment_summary()
    equipment = character.equipment if isinstance(character.equipment, dict) else {}
    return calculate_equipment_summary(equipment)


def _equipped_weapon_for_attack(engine: Any, character: Character) -> dict[str, Any]:
    if character.flags.get("is_player") or character.uuid == engine.state.player_uuid:
        equipment = engine._player_equipment()
    else:
        equipment = character.equipment if isinstance(character.equipment, dict) else {}
    weapon = equipment.get("weapon") if isinstance(equipment, dict) else None
    if not isinstance(weapon, dict) or not weapon:
        return {}
    name = str(weapon.get("name") or weapon.get("item_name") or weapon.get("title") or "").strip()
    return weapon if name else {}


def _weapon_attack_name(weapon: dict[str, Any] | None, fallback: str) -> str:
    name = str((weapon or {}).get("name") or (weapon or {}).get("item_name") or (weapon or {}).get("title") or "").strip()
    if not name:
        return str(fallback or "攻撃")
    return f"{name}での攻撃"


def _weapon_attack_element(weapon: dict[str, Any] | None, fallback: str) -> str:
    element = str((weapon or {}).get("element") or (weapon or {}).get("damage_type") or "").strip()
    return element or str(fallback or "physical")


def _weapon_payload(weapon: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(weapon, dict) or not weapon:
        return {}
    return {
        "name": str(weapon.get("name") or weapon.get("item_name") or weapon.get("title") or "").strip(),
        "category": str(weapon.get("category") or "").strip(),
        "element": str(weapon.get("element") or weapon.get("damage_type") or "").strip(),
        "attack": safe_int(weapon.get("attack"), 0),
        "template_id": str(weapon.get("template_id") or "").strip(),
    }


def _weapon_description_priority(weapon: dict[str, Any] | None) -> str:
    if not isinstance(weapon, dict) or not weapon:
        return ""
    return "Normal attack narration must prioritize the equipped weapon. Describe the attack as using equipped_weapon.name instead of bare hands, claws, or a generic body attack."


def _equipped_weapon_element(engine: Any) -> str:
    equipment = engine._player_equipment()
    weapon = equipment.get("weapon") if isinstance(equipment, dict) else None
    if isinstance(weapon, dict):
        element = str(weapon.get("element") or weapon.get("damage_type") or "").strip()
        if element:
            return element
    return "physical"


def _enemy_attack_from_decision(opponent: Character, decision: dict[str, Any]) -> tuple[str, str]:
    wanted = str(decision.get("attack_name") or decision.get("attack") or "").strip()
    attacks = [item for item in as_list(opponent.extra.get("combat_attacks") or opponent.extra.get("attacks")) if isinstance(item, dict)]
    if wanted:
        for attack in attacks:
            if str(attack.get("name") or "").strip() == wanted:
                return wanted, str(attack.get("type") or "physical")
        return wanted, str(decision.get("element") or "physical")
    if attacks:
        attack = random.choice(attacks)
        return str(attack.get("name") or "攻撃"), str(attack.get("type") or "physical")
    return "攻撃", "physical"


def _enemy_skill_from_decision(opponent: Character, decision: dict[str, Any]) -> dict[str, Any]:
    wanted = str(decision.get("skill_name") or decision.get("skill") or "").strip()
    skills = [normalise_combat_skill(item) for item in as_list(opponent.skills)]
    skills = [skill for skill in skills if skill]
    if wanted:
        for skill in skills:
            if str(skill.get("name") or "").strip() == wanted:
                return skill
    return skills[0] if skills else {}


def _move_player_to_escape_destination(engine: Any, encounter: dict[str, Any]) -> str:
    world = engine.state.world_data
    location = str(encounter.get("location") or engine.state.current_location or world.starting_location)
    graph = engine._ensure_location_subnode_graph(world, location)
    current = engine._current_subnode_id(location)
    adjacent = engine._subnode_adjacent_ids(graph, current) if current else []
    if adjacent:
        target = adjacent[0]
        engine._set_current_subnode(location, target)
        node = graph.get("nodes", {}).get(target, {}) if isinstance(graph, dict) else {}
        return f"{str(node.get('name') or target)}まで退いた。"
    for neighbor in engine._world_neighbors_no_ensure(world, location):
        if neighbor in world.locations:
            previous = engine.state.current_location
            engine.state.current_location = neighbor
            engine.state.flags["previous_location"] = previous
            return f"{neighbor}へ逃げ込んだ。"
    return "少し距離を取った。"
