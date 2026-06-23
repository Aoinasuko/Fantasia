from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .status_effects import canonical_status_effect_id

class LlmToolName(str, Enum):
    STATUS_EFFECTS = "status_effects"
    HP_EFFECTS = "hp_effects"
    SP_EFFECTS = "sp_effects"
    GOLD_DELTA = "gold_delta"
    HUNGER_DELTA = "hunger_delta"
    EXP_DELTA = "exp_delta"
    TIME_PASSAGE = "time_passage"
    GAME_OVER = "game_over"
    NPC_CHANGE_RELATIONSHIP = "npc_change_relationship"
    NPC_MOVE = "npc_move"
    NPC_JOIN_PARTY = "npc_join_party"
    NPC_REMOVE_PARTY = "npc_remove_party"
    NPC_DEAD = "npc_dead"
    NPC_CAPTURE_PLAYER = "npc_capture_player"
    NPC_UPDATE_MEMORY = "npc_update_memory"
    NPC_UPDATE_DESCRIPTION = "npc_update_description"
    WORLD_HOME_CONSTRUCTION = "world_home_construction"
    WORLD_MAINNODE_REVEAL = "world_mainnode_reveal"
    WORLD_SUBNODE_REVEAL = "world_subnode_reveal"
    CRIME_RISK = "crime_risk"
    ITEM_ADD = "item_add"
    ITEM_REMOVE = "item_remove"
    ITEM_EQUIP = "item_equip"
    ITEM_UNEQUIP = "item_unequip"
    CRAFT = "craft"
    VISUAL_INTENT = "visual_intent"
    MOVEMENT_STATUS = "movement_status"
    MOVE_PLAYER = "move_player"
    START_COMBAT = "start_combat"
    QUEST_REPORT = "quest_report"
    QUEST_ACCEPT = "quest_accept"
    QUEST_ABANDON = "quest_abandon"
    FACILITY_VISIT = "facility_visit"
    FACILITY_REQUEST = "facility_request"
    CONVERSATION_START = "conversation_start"
    CONVERSATION_END = "conversation_end"
    TRADE_NEGOTIATION = "trade_negotiation"
    HOME_PURCHASE = "home_purchase"
    PLAYER_REST = "player_rest"
    DISCOVER_LOCATION = "discover_location"
    GENERATE_DUNGEON = "generate_dungeon"
    GENERATE_QUEST = "generate_quest"
    SPAWN_NPC = "spawn_npc"
    SPAWN_ENEMY = "spawn_enemy"
    SPAWN_BOSS = "spawn_boss"
    REQUEST_NPC_GENERATION = "request_npc_generation"
    QUEST_EVENT = "quest_event"
    QUEST_PROGRESS = "quest_progress"
    QUEST_UPDATE = "quest_update"
    NPC_ACTION = "npc_action"


@dataclass(frozen=True)
class LlmToolCall:
    name: LlmToolName
    source: str
    response: Any = None
    action: str = ""
    input_type: str = ""
    location: str = ""
    previous_location: str = ""
    default_target: str = "player"
    default_character: Any = None
    encounter: dict[str, Any] | None = None
    movement_result: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "tool": self.name.value,
            "source": self.source,
        }
        if self.action:
            record["action"] = self.action
        if self.input_type:
            record["input_type"] = self.input_type
        if self.location:
            record["location"] = self.location
        if self.payload:
            record["payload"] = self.payload
        return record


@dataclass
class LlmToolResult:
    name: LlmToolName
    lines: list[str] = field(default_factory=list)
    event: dict[str, Any] = field(default_factory=dict)
    acted: bool = False

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"tool": self.name.value}
        if self.lines:
            record["lines"] = list(self.lines)
        if self.event:
            record["event"] = self.event
        if self.acted:
            record["acted"] = True
        return record


@dataclass
class LlmToolBatchResult:
    results: list[LlmToolResult] = field(default_factory=list)
    status_lines: list[str] = field(default_factory=list)
    item_event: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "tools": [result.to_record() for result in self.results],
            "status_lines": list(self.status_lines),
            "item_event": self.item_event,
        }


def run_llm_tool(engine: Any, call: LlmToolCall) -> LlmToolResult:
    name = call.name
    response = tool_response_for_call(call)
    source = call.source
    if name == LlmToolName.STATUS_EFFECTS:
        return LlmToolResult(
            name,
            lines=engine._apply_response_status_effects(
                response,
                source,
                default_target=call.default_target,
                context_character=call.default_character,
            ),
        )
    if name == LlmToolName.HP_EFFECTS:
        return LlmToolResult(name, lines=engine._apply_response_hp_effects(response, source))
    if name == LlmToolName.SP_EFFECTS:
        return LlmToolResult(name, lines=engine._apply_response_sp_effects(response, source))
    if name == LlmToolName.GOLD_DELTA:
        return LlmToolResult(name, lines=engine._apply_response_gold_effects(response, source))
    if name == LlmToolName.HUNGER_DELTA:
        return LlmToolResult(name, lines=engine._apply_response_hunger_effects(response, source))
    if name == LlmToolName.EXP_DELTA:
        return LlmToolResult(
            name,
            lines=engine._apply_response_exp_effects(
                response,
                source,
                default_character=call.default_character,
                encounter=call.encounter,
            ),
        )
    if name == LlmToolName.TIME_PASSAGE:
        return LlmToolResult(name, lines=engine._apply_response_time_effects(response, source))
    if name == LlmToolName.GAME_OVER:
        return LlmToolResult(
            name,
            lines=engine._apply_response_game_over_effects(response, source, encounter=call.encounter),
        )
    if name == LlmToolName.NPC_CHANGE_RELATIONSHIP:
        return LlmToolResult(
            name,
            lines=engine._apply_response_relationship_effects(response, source, default_character=call.default_character),
        )
    if name == LlmToolName.NPC_MOVE:
        return LlmToolResult(
            name,
            lines=engine._apply_response_npc_move_effects(
                response,
                source,
                default_character=call.default_character,
                default_location=call.location,
            ),
        )
    if name == LlmToolName.NPC_JOIN_PARTY:
        return LlmToolResult(
            name,
            lines=engine._apply_response_npc_join_party_effects(response, source, default_character=call.default_character),
        )
    if name == LlmToolName.NPC_REMOVE_PARTY:
        return LlmToolResult(
            name,
            lines=engine._apply_response_npc_remove_party_effects(
                response,
                source,
                default_character=call.default_character,
                default_location=call.location,
            ),
        )
    if name == LlmToolName.NPC_DEAD:
        return LlmToolResult(
            name,
            lines=engine._apply_response_npc_dead_effects(response, source, default_character=call.default_character),
        )
    if name == LlmToolName.NPC_CAPTURE_PLAYER:
        return LlmToolResult(
            name,
            lines=engine._apply_response_capture_relocation_effects(
                response,
                source,
                default_character=call.default_character,
                default_location=call.location,
                encounter=call.encounter,
            ),
        )
    if name == LlmToolName.NPC_UPDATE_MEMORY:
        return LlmToolResult(
            name,
            lines=engine._apply_response_npc_memory_effects(response, source, default_character=call.default_character),
        )
    if name == LlmToolName.NPC_UPDATE_DESCRIPTION:
        return LlmToolResult(
            name,
            lines=engine._apply_response_npc_description_effects(response, source, default_character=call.default_character),
        )
    if name == LlmToolName.WORLD_HOME_CONSTRUCTION:
        return LlmToolResult(name, lines=engine._apply_response_home_construction_effects(response, source))
    if name == LlmToolName.WORLD_MAINNODE_REVEAL:
        return LlmToolResult(
            name,
            lines=engine._apply_response_world_mainnode_reveals(response, source, default_location=call.location),
        )
    if name == LlmToolName.WORLD_SUBNODE_REVEAL:
        return LlmToolResult(
            name,
            lines=engine._apply_response_subnode_map_reveals(response, source, default_location=call.location),
        )
    if name == LlmToolName.CRIME_RISK:
        return LlmToolResult(
            name,
            lines=engine._apply_crime_risk(call.action, response, source, location=call.location),
        )
    if name == LlmToolName.ITEM_ADD:
        event = engine._apply_response_item_add_effects(response, source)
        return LlmToolResult(name, event=event, acted=_item_event_has_changes(event))
    if name == LlmToolName.ITEM_REMOVE:
        event = engine._apply_response_item_remove_effects(response, source)
        return LlmToolResult(name, event=event, acted=_item_event_has_changes(event))
    if name == LlmToolName.ITEM_EQUIP:
        event = engine._apply_response_item_equip_effects(response, source)
        return LlmToolResult(name, event=event, acted=_item_event_has_changes(event))
    if name == LlmToolName.ITEM_UNEQUIP:
        event = engine._apply_response_item_unequip_effects(response, source)
        return LlmToolResult(name, event=event, acted=_item_event_has_changes(event))
    if name == LlmToolName.CRAFT:
        event = engine._apply_response_craft_tool(
            response,
            source,
            default_action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(
            name,
            lines=[str(line) for line in event.get("lines", []) if str(line).strip()],
            event=event,
            acted=bool(event.get("crafted") or event.get("failed") or event.get("consumed")),
        )
    if name == LlmToolName.VISUAL_INTENT:
        engine._apply_visual_intent(response, source, call.location, call.previous_location)
        return LlmToolResult(name, acted=True)
    if name == LlmToolName.MOVEMENT_STATUS:
        movement = call.movement_result or {}
        lines = [str(line) for line in movement.get("status_lines", []) if str(line).strip()]
        return LlmToolResult(name, lines=lines, acted=bool(lines))
    if name == LlmToolName.MOVE_PLAYER:
        event = engine._apply_response_move_player_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
            location=call.location,
        )
        return LlmToolResult(
            name,
            lines=[str(line) for line in event.get("lines", []) if str(line).strip()],
            event=event,
            acted=bool(event.get("handled")),
        )
    if name == LlmToolName.START_COMBAT:
        event = engine._apply_response_start_combat_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
            location=call.location,
        )
        return LlmToolResult(
            name,
            lines=[str(line) for line in event.get("lines", []) if str(line).strip()],
            event=event,
            acted=bool(event.get("started")),
        )
    if name == LlmToolName.QUEST_REPORT:
        event = engine._apply_response_quest_report_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.QUEST_ACCEPT:
        event = engine._apply_response_quest_accept_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.QUEST_ABANDON:
        event = engine._apply_response_quest_abandon_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.FACILITY_VISIT:
        event = engine._apply_response_facility_visit_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.FACILITY_REQUEST:
        event = engine._apply_response_facility_request_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.CONVERSATION_START:
        event = engine._apply_response_conversation_start_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.CONVERSATION_END:
        event = engine._apply_response_conversation_end_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.TRADE_NEGOTIATION:
        event = engine._apply_response_trade_negotiation_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.HOME_PURCHASE:
        event = engine._apply_response_home_purchase_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.PLAYER_REST:
        event = engine._apply_response_player_rest_tool(
            response,
            source,
            action=call.action,
            input_type=call.input_type,
        )
        return LlmToolResult(name, event=event, acted=bool(event.get("handled")))
    if name == LlmToolName.NPC_ACTION:
        result = apply_npc_action_tool(
            engine,
            call.encounter or {},
            response if isinstance(response, dict) else {},
            call.payload.get("rewrite_response") if isinstance(call.payload.get("rewrite_response"), dict) else {},
        )
        return LlmToolResult(
            name,
            lines=[str(line) for line in result.get("lines", []) if str(line).strip()],
            event=dict(result),
            acted=bool(result.get("acted")),
        )
    if name == LlmToolName.GENERATE_DUNGEON:
        event = engine._apply_response_generate_dungeon_tool(response, source, default_location=call.location)
        return LlmToolResult(
            name,
            lines=[str(line) for line in event.get("lines", []) if str(line).strip()],
            event=event,
            acted=bool(event.get("created") or event.get("revealed")),
        )
    return LlmToolResult(name)


def response_tool_calls(response: Any, *, source: str = "") -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    calls: list[dict[str, Any]] = []
    raw_tools = response.get("tool_judgements")
    if not isinstance(raw_tools, list):
        return []
    for raw in raw_tools:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if _confidence_value(raw.get("confidence")) != 1.0:
            continue
        canonical = _canonical_tool_name(name)
        if not canonical:
            continue
        args = raw.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            continue
        calls.append(
            {
                "name": canonical.value,
                "arguments": dict(args),
                "source": source,
            }
        )
    return calls


def tool_effect_payload(response: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for item in response_tool_calls(response):
        try:
            tool_name = LlmToolName(item["name"])
        except ValueError:
            continue
        args = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        _merge_tool_payload(payload, tool_name, args)
    return payload


def requested_location_from_tools(response: Any, fallback: str = "") -> str:
    payload = tool_effect_payload(response)
    return str(payload.get("location") or payload.get("destination_location") or fallback or "").strip()


def tool_prompt_instruction() -> str:
    return (
        "Tool judgement JSON rule: put all game-state side-effect candidates in a top-level tool_judgements array. "
        "Do not use top-level side-effect keys such as location, hp_delta, sp_delta, item_add, item_remove, item_equip, item_unequip, craft, status_effects, "
        "relationship_change, npc_movements, npc_move, npc_join_party, npc_remove_party, npc_dead, "
        "npc_capture_player, npc_update_memory, npc_update_description, map_reveal, world_home_construction, "
        "world_mainnode_reveal, world_subnode_reveal, discovered_location, quest_update, or combat_started. "
        "Top-level fields are only content_violation, intent, narration, process, finished, speaker, topic, mood, "
        "quest_name, objective, choices, and tool_judgements. "
        "Each tool judgement item must be {\"name\":\"tool_name\",\"confidence\":0.0-1.0,\"arguments\":{...},\"reason\":\"...\"}. "
        "The game executes only tool judgements whose confidence is exactly 1.0; 0.99 or missing confidence is not executed. "
        "Set confidence to 1.0 only when the state change is definitely intended by the action and current context. "
        "Use start_combat only when combat actually begins now. Mentioning danger, an enemy, traces of an attack, a threat, "
        "or an option to fight is not enough. For player-initiated attacks or ambushes, include opponent_name or target_name; "
        "set surprise_attack=true only when the player takes the first strike immediately. "
        "For the status_effects tool, arguments must be {\"status_effects\":[{\"effect_id\":\"HP_Damage/SP_Damage/Paralysis/Silence/Psychosis/Inoperable/SendLLM/Atk_Mod/Def_Mod\",...}]}; "
        "status effects without explicit effect_id are ignored. "
        "Supported tools: move_player, status_effects, hp_effects, sp_effects, gold_delta, hunger_delta, "
        "exp_delta, time_passage, game_over, npc_change_relationship, npc_move, npc_join_party, "
        "npc_remove_party, npc_dead, npc_capture_player, npc_update_memory, npc_update_description, "
        "world_home_construction, world_mainnode_reveal, world_subnode_reveal, "
        "crime_risk, item_add, item_remove, item_equip, item_unequip, craft, visual_intent, start_combat, "
        "quest_report, quest_accept, quest_abandon, facility_visit, facility_request, conversation_start, "
        "conversation_end, trade_negotiation, home_purchase, player_rest, discover_location, generate_dungeon, generate_quest, spawn_npc, spawn_enemy, "
        "spawn_boss, request_npc_generation, quest_event, quest_progress, quest_update. "
        "Use craft when the player explicitly tries crafting, cooking, smithing, alchemy, combining, or processing items; "
        "arguments must include consume_items as an array of item names or item_uuid values from current craft candidates, "
        "craft_type as auto|mix|synthesis|smithing|alchemy|cooking, and content as the intended result or request. "
        "Do not also emit item_add or item_remove for the same craft; the craft tool consumes materials and creates the result. "
        "Use home_purchase only when the player explicitly buys a home through a town hall plan. "
        "Use player_rest only when the player explicitly rests at an inn, their home, or the current area. "
        "Use generate_dungeon only when a definite clue, diary, map, document, rumor, or magical effect reveals an unknown dungeon near the current or adjacent main node; "
        "arguments may include {\"name\":\"dungeon name\",\"description\":\"short description\",\"dungeon_subtype\":\"forest|mountain|ruin|cave|mine|labyrinth|crypt|lair\",\"anchor_location\":\"current or adjacent location\",\"reason\":\"why it is revealed\"}. "
        "Use an empty tool_judgements array when no state changes are needed."
    )


def tool_response_for_call(call: LlmToolCall) -> dict[str, Any]:
    if call.payload:
        payload: dict[str, Any] = {}
        _merge_tool_payload(payload, call.name, dict(call.payload))
        return payload or dict(call.payload)
    if isinstance(call.response, dict):
        payload = tool_effect_payload(call.response)
        if payload:
            return payload
        return {}
    return {}


def apply_npc_action_tool(
    engine: Any,
    encounter: dict[str, Any],
    npc_response: dict[str, Any],
    rewrite_response: dict[str, Any],
) -> dict[str, Any]:
    action = _npc_action_tool_kind(npc_response, rewrite_response)
    if action == "surrender":
        return engine._npc_surrender_from_encounter(encounter)
    if action == "flee":
        return engine._npc_flee_from_encounter(encounter)
    return {"acted": False, "lines": []}


def _npc_action_tool_kind(*responses: Any) -> str:
    surrender_values = {"surrender", "yield", "give_up", "giveup", "降伏", "降参"}
    flee_values = {"flee", "escape", "run_away", "runaway", "retreat", "withdraw", "逃亡", "逃走", "退却"}
    for response in responses:
        if not isinstance(response, dict):
            continue
        if _as_bool(response.get("npc_surrender") or response.get("surrender")):
            return "surrender"
        if _as_bool(response.get("npc_flee") or response.get("flee")):
            return "flee"
        for key in ("npc_action", "action", "kind", "intent"):
            value = response.get(key)
            value_text = str(value or "").strip()
            if not value_text:
                continue
            normalized = value_text.casefold().replace("-", "_").replace(" ", "_")
            if normalized in surrender_values or value_text in surrender_values:
                return "surrender"
            if normalized in flee_values or value_text in flee_values:
                return "flee"
    return ""


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "はい"}
    return bool(value)


def apply_common_response_tools(
    engine: Any,
    response: dict[str, Any],
    *,
    source: str,
    action: str,
    input_type: str,
    location: str,
    previous_location: str = "",
    movement_result: dict[str, Any] | None = None,
    default_target: str = "player",
    default_character: Any = None,
    encounter: dict[str, Any] | None = None,
    content_violation: bool = False,
    include_items: bool = True,
    include_visual: bool = True,
    include_crime: bool = True,
    append_display: bool = True,
) -> LlmToolBatchResult:
    batch = LlmToolBatchResult()
    common = {
        "source": source,
        "response": response,
        "action": action,
        "input_type": input_type,
        "location": location,
        "previous_location": previous_location,
        "default_target": default_target,
        "default_character": default_character,
        "encounter": encounter,
        "movement_result": movement_result,
    }

    if not content_violation:
        movement_result_record = run_llm_tool(engine, LlmToolCall(LlmToolName.MOVEMENT_STATUS, **common))
        batch.results.append(movement_result_record)
        batch.status_lines.extend(movement_result_record.lines)

        requested_tools = response_tool_calls(response, source=source)
        for tool in requested_tools:
            try:
                tool_name = LlmToolName(tool["name"])
            except ValueError:
                continue
            if tool_name == LlmToolName.CRIME_RISK and not include_crime:
                continue
            if tool_name in {LlmToolName.ITEM_ADD, LlmToolName.ITEM_REMOVE, LlmToolName.ITEM_EQUIP, LlmToolName.ITEM_UNEQUIP} and not include_items:
                continue
            if tool_name == LlmToolName.VISUAL_INTENT and not include_visual:
                continue
            if tool_name in {
                LlmToolName.MOVE_PLAYER,
                LlmToolName.START_COMBAT,
                LlmToolName.QUEST_REPORT,
                LlmToolName.QUEST_ACCEPT,
                LlmToolName.QUEST_ABANDON,
                LlmToolName.FACILITY_VISIT,
                LlmToolName.FACILITY_REQUEST,
                LlmToolName.CONVERSATION_START,
                LlmToolName.CONVERSATION_END,
                LlmToolName.TRADE_NEGOTIATION,
                LlmToolName.HOME_PURCHASE,
                LlmToolName.PLAYER_REST,
                LlmToolName.DISCOVER_LOCATION,
                LlmToolName.GENERATE_QUEST,
                LlmToolName.SPAWN_NPC,
                LlmToolName.SPAWN_ENEMY,
                LlmToolName.SPAWN_BOSS,
                LlmToolName.REQUEST_NPC_GENERATION,
                LlmToolName.QUEST_EVENT,
                LlmToolName.QUEST_PROGRESS,
                LlmToolName.QUEST_UPDATE,
            }:
                continue
            result = run_llm_tool(engine, LlmToolCall(tool_name, **common, payload=tool.get("arguments") or {}))
            batch.results.append(result)
            batch.status_lines.extend(result.lines)
            if tool_name in {LlmToolName.ITEM_ADD, LlmToolName.ITEM_REMOVE, LlmToolName.ITEM_EQUIP, LlmToolName.ITEM_UNEQUIP}:
                _merge_item_event(batch.item_event, result.event)

    if batch.status_lines and append_display:
        engine.state.display_log.extend(batch.status_lines)

    return batch


def _item_event_has_changes(event: dict[str, Any]) -> bool:
    return bool(
        event.get("items")
        or event.get("skipped_items")
        or event.get("lost_items")
        or event.get("equipment")
    )


def _merge_item_event(target: dict[str, Any], event: dict[str, Any]) -> None:
    if not event:
        return
    if event.get("source") and not target.get("source"):
        target["source"] = event.get("source")
    for key in ("items", "skipped_items", "lost_items", "equipment"):
        values = event.get(key)
        if isinstance(values, list):
            target.setdefault(key, []).extend(values)
        elif values not in (None, "", [], {}):
            target.setdefault(key, []).append(values)


def _canonical_tool_name(name: str) -> LlmToolName | None:
    key = str(name or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    try:
        return LlmToolName(key)
    except ValueError:
        return None


def _confidence_value(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def _merge_tool_payload(payload: dict[str, Any], tool_name: LlmToolName, args: dict[str, Any]) -> None:
    if tool_name == LlmToolName.MOVE_PLAYER:
        location = str(args.get("location") or args.get("destination") or args.get("to") or args.get("target_location") or "").strip()
        if location:
            payload["location"] = location
            payload["destination_location"] = location
        _merge_keys(payload, args, ("subnode", "subnode_id", "target_subnode", "reason"))
        return
    if tool_name == LlmToolName.START_COMBAT:
        payload["combat_started"] = True
        _merge_keys(
            payload,
            args,
            (
                "opponent_name",
                "target_name",
                "enemy_name",
                "narration",
                "reason",
                "surprise",
                "surprise_attack",
                "first_strike",
                "preemptive",
                "player_initiated",
            ),
        )
        return
    if tool_name in {
        LlmToolName.QUEST_REPORT,
        LlmToolName.QUEST_ACCEPT,
        LlmToolName.QUEST_ABANDON,
        LlmToolName.FACILITY_VISIT,
        LlmToolName.FACILITY_REQUEST,
        LlmToolName.CONVERSATION_START,
        LlmToolName.CONVERSATION_END,
        LlmToolName.TRADE_NEGOTIATION,
        LlmToolName.HOME_PURCHASE,
        LlmToolName.PLAYER_REST,
    }:
        payload.update(args)
        return
    if tool_name == LlmToolName.DISCOVER_LOCATION:
        payload["discovered_location"] = _single_or_value(args, "location", "discovered_location", "value")
        return
    if tool_name == LlmToolName.GENERATE_DUNGEON:
        value = args.get("generate_dungeon") if args.get("generate_dungeon") not in (None, "", [], {}) else args
        payload["generate_dungeon"] = value or True
        return
    if tool_name == LlmToolName.CRAFT:
        value = args.get("craft") if args.get("craft") not in (None, "", [], {}) else args
        payload["craft"] = value or True
        return
    if tool_name == LlmToolName.GENERATE_QUEST:
        _append_payload_list(payload, "quests", _single_or_value(args, "quest", "quests", "value"))
        return
    if tool_name == LlmToolName.SPAWN_NPC:
        _append_payload_list(payload, "npcs", _single_or_value(args, "npc", "npcs", "characters", "value"))
        return
    if tool_name == LlmToolName.SPAWN_ENEMY:
        _append_payload_list(payload, "enemies", _single_or_value(args, "enemy", "enemies", "opponents", "value"))
        return
    if tool_name == LlmToolName.SPAWN_BOSS:
        payload["boss_npc"] = _single_or_value(args, "boss_npc", "boss", "enemy", "value")
        return
    if tool_name == LlmToolName.REQUEST_NPC_GENERATION:
        _append_payload_list(payload, "new_npc_requests", _single_or_value(args, "requests", "request", "new_npc_requests", "value"))
        return
    if tool_name == LlmToolName.QUEST_EVENT:
        payload["event"] = _single_or_value(args, "event", "value")
        return
    if tool_name == LlmToolName.QUEST_PROGRESS:
        value = args.get("progress", args.get("quest_progress", args.get("value", "")))
        if value:
            payload["quest_progress"] = str(value)
        return
    if tool_name == LlmToolName.QUEST_UPDATE:
        payload["quest_update"] = _single_or_value(args, "quest_update", "update", "value")
        return
    if tool_name == LlmToolName.STATUS_EFFECTS:
        effects = _explicit_status_effects(args.get("status_effects"))
        if effects:
            payload["status_effects"] = effects
        return
    if tool_name == LlmToolName.HP_EFFECTS:
        _merge_or_wrap(payload, args, "hp_effects", ("effects",))
        if "delta" in args and "hp_delta" not in payload:
            payload["hp_delta"] = args["delta"]
        return
    if tool_name == LlmToolName.SP_EFFECTS:
        _merge_or_wrap(payload, args, "sp_effects", ("effects",))
        if "delta" in args and "sp_delta" not in payload:
            payload["sp_delta"] = args["delta"]
        return
    if tool_name == LlmToolName.GOLD_DELTA:
        payload.update(args)
        value = _single_or_value(args, "gold_delta", "delta", "amount", "value", "gold", "money", "coins")
        if value is not args:
            payload["gold_delta"] = value
        return
    if tool_name == LlmToolName.HUNGER_DELTA:
        payload.update(args)
        value = _single_or_value(args, "hunger_delta", "player_hunger_delta", "delta", "amount", "value", "hunger")
        if value is not args:
            payload["hunger_delta"] = value
        return
    if tool_name == LlmToolName.EXP_DELTA:
        payload.update(args)
        value = _single_or_value(args, "exp_delta", "player_exp_delta", "delta", "amount", "value", "exp", "xp")
        if value is not args:
            payload["exp_delta"] = value
        _merge_keys(payload, args, ("target", "target_name", "character", "character_name", "npc", "npc_name", "target_uuid", "uuid", "reason"))
        return
    if tool_name == LlmToolName.TIME_PASSAGE:
        payload.update(args)
        if "hours" in args and "time_passed_hours" not in payload:
            payload["time_passed_hours"] = args["hours"]
        if "days" in args and "time_passed_days" not in payload:
            payload["time_passed_days"] = args["days"]
        if "delta" in args and "time_passed_hours" not in payload and "time_passed_days" not in payload:
            payload["time_passed_hours"] = args["delta"]
        if "amount" in args and "unit" not in args and "time_passed_hours" not in payload and "time_passed_days" not in payload:
            payload["time_passed_hours"] = args["amount"]
        return
    if tool_name == LlmToolName.GAME_OVER:
        payload.update(args)
        payload["game_over"] = args.get("game_over", args.get("value", True))
        _merge_keys(payload, args, ("reason", "game_over_reason", "narration", "game_over_narration"))
        return
    if tool_name == LlmToolName.NPC_CHANGE_RELATIONSHIP:
        _append_payload_list(payload, "relationship_change", _single_or_value(args, "relationship_change", "change", "value"))
        return
    if tool_name == LlmToolName.NPC_MOVE:
        _append_payload_list(payload, "npc_move", _single_or_value(args, "npc_move", "movement", "move", "value"))
        return
    if tool_name == LlmToolName.NPC_JOIN_PARTY:
        value = _target_payload(args, "npc_join_party", "character", "npc", "target", "value")
        _append_payload_list(payload, "npc_join_party", value)
        return
    if tool_name == LlmToolName.NPC_REMOVE_PARTY:
        value = _target_payload(args, "npc_remove_party", "character", "npc", "target", "value")
        _append_payload_list(payload, "npc_remove_party", value)
        return
    if tool_name == LlmToolName.NPC_DEAD:
        value = _target_payload(args, "npc_dead", "character", "npc", "target", "value")
        _append_payload_list(payload, "npc_dead", value)
        return
    if tool_name == LlmToolName.NPC_CAPTURE_PLAYER:
        payload["npc_capture_player"] = _single_or_value(args, "npc_capture_player", "capture", "value")
        return
    if tool_name == LlmToolName.NPC_UPDATE_MEMORY:
        value = _target_payload(args, "memory_updates", "memory", "memories", "value", value_key="memory")
        _append_payload_list(payload, "memory_updates", value)
        return
    if tool_name == LlmToolName.NPC_UPDATE_DESCRIPTION:
        value = _target_payload(args, "npc_description_updates", "description", "update", "value", value_key="description")
        _append_payload_list(payload, "npc_description_updates", value)
        return
    if tool_name == LlmToolName.WORLD_HOME_CONSTRUCTION:
        _append_payload_list(payload, "home_construction", _single_or_value(args, "home_construction", "construction", "value"))
        return
    if tool_name == LlmToolName.WORLD_MAINNODE_REVEAL:
        value = args.get("world_mainnode_reveal") if args.get("world_mainnode_reveal") not in (None, "", [], {}) else args
        _append_payload_list(payload, "world_mainnode_reveal", value)
        return
    if tool_name == LlmToolName.WORLD_SUBNODE_REVEAL:
        value = args
        for key in ("world_subnode_reveal", "subnode_map_reveal"):
            if args.get(key) not in (None, "", [], {}):
                value = args[key]
                break
        _append_payload_list(payload, "subnode_map_reveal", value)
        return
    if tool_name == LlmToolName.CRIME_RISK:
        payload["crime_risk"] = args or True
        payload.update(args)
        return
    if tool_name == LlmToolName.ITEM_ADD:
        _append_payload_list(payload, "item_add", _item_tool_payload(args, "item_add", "item", "items", "value"))
        return
    if tool_name == LlmToolName.ITEM_REMOVE:
        _append_payload_list(payload, "item_remove", _item_tool_payload(args, "item_remove", "item", "items", "target", "value"))
        return
    if tool_name == LlmToolName.ITEM_EQUIP:
        _append_payload_list(payload, "item_equip", _item_tool_payload(args, "item_equip", "item", "target", "value"))
        return
    if tool_name == LlmToolName.ITEM_UNEQUIP:
        _append_payload_list(payload, "item_unequip", _item_tool_payload(args, "item_unequip", "item", "slot", "target", "value"))
        return
    if tool_name == LlmToolName.VISUAL_INTENT:
        payload["visual_intent"] = args or True
        payload.update(args)
        return
    if tool_name == LlmToolName.NPC_ACTION:
        payload["npc_action"] = args.get("action") or args.get("npc_action") or args.get("value") or ""
        payload.update(args)


def _merge_keys(target: dict[str, Any], source: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            target[key] = value


def _single_or_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] not in (None, "", [], {}):
            return source[key]
    return source


def _target_payload(source: dict[str, Any], *keys: str, value_key: str = "target") -> Any:
    value = _single_or_value(source, *keys)
    if value is source or not any(key in source for key in ("target", "character", "character_name", "npc", "npc_name", "name")):
        return value
    significant = {key: item for key, item in source.items() if item not in (None, "", [], {})}
    if len(significant) <= 1:
        return value
    entry = dict(source)
    entry.setdefault(value_key, value)
    return entry


def _item_tool_payload(source: dict[str, Any], *keys: str) -> Any:
    value = _single_or_value(source, *keys)
    if value is source:
        return source
    significant = {key: item for key, item in source.items() if item not in (None, "", [], {})}
    if len(significant) <= 1:
        return value
    entry = dict(source)
    entry.setdefault("item", value)
    return entry


def _explicit_status_effects(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else [value]
    effects: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        effect_id = canonical_status_effect_id(item.get("effect_id"))
        if not effect_id:
            continue
        effect = dict(item)
        effect["effect_id"] = effect_id
        effects.append(effect)
    return effects


def _append_payload_list(payload: dict[str, Any], key: str, value: Any) -> None:
    if value in (None, "", [], {}):
        return
    items = value if isinstance(value, list) else [value]
    payload.setdefault(key, []).extend(items)


def _merge_or_wrap(payload: dict[str, Any], args: dict[str, Any], default_key: str, aliases: tuple[str, ...]) -> None:
    known = any(key in args for key in (default_key, *aliases))
    if known:
        payload.update(args)
        for alias in aliases:
            if alias in args and default_key not in payload:
                payload[default_key] = args[alias]
        return
    if args:
        payload[default_key] = args
