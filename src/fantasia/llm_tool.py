from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .combat import _npc_action_tool_kind


class LlmToolName(str, Enum):
    STATUS_EFFECTS = "status_effects"
    HP_EFFECTS = "hp_effects"
    SP_EFFECTS = "sp_effects"
    GOLD_DELTA = "gold_delta"
    HUNGER_DELTA = "hunger_delta"
    EXP_DELTA = "exp_delta"
    TIME_PASSAGE = "time_passage"
    GAME_OVER = "game_over"
    WORLD_STATE_EFFECTS = "world_state_effects"
    CRIME_RISK = "crime_risk"
    REWARDS = "rewards"
    VISUAL_INTENT = "visual_intent"
    MOVEMENT_STATUS = "movement_status"
    MOVE_PLAYER = "move_player"
    START_COMBAT = "start_combat"
    DISCOVER_LOCATION = "discover_location"
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
    reward_event: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "tools": [result.to_record() for result in self.results],
            "status_lines": list(self.status_lines),
            "reward_event": self.reward_event,
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
    if name == LlmToolName.WORLD_STATE_EFFECTS:
        return LlmToolResult(
            name,
            lines=engine._apply_response_world_state_effects(
                response,
                source,
                default_character=call.default_character,
                default_location=call.location,
                encounter=call.encounter,
            ),
        )
    if name == LlmToolName.CRIME_RISK:
        return LlmToolResult(
            name,
            lines=engine._apply_crime_risk(call.action, response, source, location=call.location),
        )
    if name == LlmToolName.REWARDS:
        event = engine._apply_response_rewards(response, source)
        return LlmToolResult(name, event=event, acted=_reward_event_has_changes(event))
    if name == LlmToolName.VISUAL_INTENT:
        engine._apply_visual_intent(response, source, call.location, call.previous_location)
        return LlmToolResult(name, acted=True)
    if name == LlmToolName.MOVEMENT_STATUS:
        movement = call.movement_result or {}
        lines = [str(line) for line in movement.get("status_lines", []) if str(line).strip()]
        return LlmToolResult(name, lines=lines, acted=bool(lines))
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
    return LlmToolResult(name)


def response_tool_calls(response: Any, *, source: str = "") -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    raw_tools = response.get("tools")
    if not isinstance(raw_tools, list):
        return []
    calls: list[dict[str, Any]] = []
    for raw in raw_tools:
        if isinstance(raw, str):
            name = raw.strip()
            args: Any = {}
        elif isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("tool") or raw.get("type") or "").strip()
            args = raw.get("arguments")
            if args is None:
                args = raw.get("args")
            if args is None:
                args = raw.get("payload")
            if args is None:
                args = {
                    key: value
                    for key, value in raw.items()
                    if key not in {"name", "tool", "type", "arguments", "args", "payload"}
                }
        else:
            continue
        canonical = _canonical_tool_name(name)
        if not canonical:
            continue
        calls.append(
            {
                "name": canonical.value,
                "arguments": _tool_arguments(args),
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
        args = _tool_arguments(item.get("arguments"))
        _merge_tool_payload(payload, tool_name, args)
    return payload


def requested_location_from_tools(response: Any, fallback: str = "") -> str:
    payload = tool_effect_payload(response)
    return str(payload.get("location") or payload.get("destination_location") or fallback or "").strip()


def tool_prompt_instruction() -> str:
    return (
        "Tool JSON rule: put all game-state side effects in a top-level tools array. "
        "Do not use top-level side-effect keys such as location, hp_delta, sp_delta, rewards, status_effects, "
        "relationship_change, npc_movements, map_reveal, discovered_location, quest_update, or combat_started. "
        "Top-level fields are only content_violation, intent, narration, process, finished, speaker, topic, mood, "
        "quest_name, objective, choices, and tools. "
        "Each tool item must be {\"name\":\"tool_name\",\"arguments\":{...}}. "
        "Supported tools: move_player, status_effects, hp_effects, sp_effects, gold_delta, hunger_delta, "
        "exp_delta, time_passage, game_over, world_state_effects, "
        "crime_risk, rewards, visual_intent, start_combat, discover_location, generate_quest, spawn_npc, spawn_enemy, "
        "spawn_boss, request_npc_generation, quest_event, quest_progress, quest_update. "
        "Use an empty tools array when no state changes are needed."
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
    include_rewards: bool = True,
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
            if tool_name == LlmToolName.REWARDS and not include_rewards:
                continue
            if tool_name == LlmToolName.VISUAL_INTENT and not include_visual:
                continue
            if tool_name in {
                LlmToolName.MOVE_PLAYER,
                LlmToolName.START_COMBAT,
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
            if tool_name == LlmToolName.REWARDS:
                batch.reward_event = result.event

    if batch.status_lines and append_display:
        engine.state.display_log.extend(batch.status_lines)

    return batch


def _reward_event_has_changes(event: dict[str, Any]) -> bool:
    return bool(
        event.get("items")
        or event.get("skipped_items")
        or event.get("lost_items")
        or event.get("gold")
        or event.get("equipment")
    )


_TOOL_ALIASES = {
    "status": LlmToolName.STATUS_EFFECTS,
    "status_effect": LlmToolName.STATUS_EFFECTS,
    "status_effects": LlmToolName.STATUS_EFFECTS,
    "hp": LlmToolName.HP_EFFECTS,
    "hp_effect": LlmToolName.HP_EFFECTS,
    "hp_effects": LlmToolName.HP_EFFECTS,
    "sp": LlmToolName.SP_EFFECTS,
    "sp_effect": LlmToolName.SP_EFFECTS,
    "sp_effects": LlmToolName.SP_EFFECTS,
    "gold": LlmToolName.GOLD_DELTA,
    "gold_delta": LlmToolName.GOLD_DELTA,
    "money_delta": LlmToolName.GOLD_DELTA,
    "hunger": LlmToolName.HUNGER_DELTA,
    "hunger_delta": LlmToolName.HUNGER_DELTA,
    "exp": LlmToolName.EXP_DELTA,
    "xp": LlmToolName.EXP_DELTA,
    "exp_delta": LlmToolName.EXP_DELTA,
    "experience_delta": LlmToolName.EXP_DELTA,
    "time": LlmToolName.TIME_PASSAGE,
    "time_passage": LlmToolName.TIME_PASSAGE,
    "advance_time": LlmToolName.TIME_PASSAGE,
    "time_passed": LlmToolName.TIME_PASSAGE,
    "game_over": LlmToolName.GAME_OVER,
    "bad_end": LlmToolName.GAME_OVER,
    "world_state": LlmToolName.WORLD_STATE_EFFECTS,
    "world_state_effect": LlmToolName.WORLD_STATE_EFFECTS,
    "world_state_effects": LlmToolName.WORLD_STATE_EFFECTS,
    "crime": LlmToolName.CRIME_RISK,
    "crime_risk": LlmToolName.CRIME_RISK,
    "reward": LlmToolName.REWARDS,
    "rewards": LlmToolName.REWARDS,
    "visual": LlmToolName.VISUAL_INTENT,
    "visual_intent": LlmToolName.VISUAL_INTENT,
    "move": LlmToolName.MOVE_PLAYER,
    "movement": LlmToolName.MOVE_PLAYER,
    "move_player": LlmToolName.MOVE_PLAYER,
    "start_combat": LlmToolName.START_COMBAT,
    "combat": LlmToolName.START_COMBAT,
    "discover_location": LlmToolName.DISCOVER_LOCATION,
    "discovered_location": LlmToolName.DISCOVER_LOCATION,
    "generate_quest": LlmToolName.GENERATE_QUEST,
    "generated_quest": LlmToolName.GENERATE_QUEST,
    "quest": LlmToolName.GENERATE_QUEST,
    "spawn_npc": LlmToolName.SPAWN_NPC,
    "npcs": LlmToolName.SPAWN_NPC,
    "spawn_enemy": LlmToolName.SPAWN_ENEMY,
    "enemies": LlmToolName.SPAWN_ENEMY,
    "spawn_boss": LlmToolName.SPAWN_BOSS,
    "boss_npc": LlmToolName.SPAWN_BOSS,
    "request_npc_generation": LlmToolName.REQUEST_NPC_GENERATION,
    "new_npc_request": LlmToolName.REQUEST_NPC_GENERATION,
    "new_npc_requests": LlmToolName.REQUEST_NPC_GENERATION,
    "quest_event": LlmToolName.QUEST_EVENT,
    "event": LlmToolName.QUEST_EVENT,
    "quest_progress": LlmToolName.QUEST_PROGRESS,
    "quest_update": LlmToolName.QUEST_UPDATE,
    "npc_action": LlmToolName.NPC_ACTION,
}


def _canonical_tool_name(name: str) -> LlmToolName | None:
    key = str(name or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    if key in _TOOL_ALIASES:
        return _TOOL_ALIASES[key]
    try:
        return LlmToolName(key)
    except ValueError:
        return None


def _tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    return {"value": value}


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
        _merge_keys(payload, args, ("opponent_name", "target_name", "enemy_name", "narration", "reason"))
        return
    if tool_name == LlmToolName.DISCOVER_LOCATION:
        payload["discovered_location"] = _single_or_value(args, "location", "discovered_location", "value")
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
        _merge_or_wrap(payload, args, "status_effects", ("effects", "add", "apply"))
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
    if tool_name == LlmToolName.WORLD_STATE_EFFECTS:
        payload.update(args)
        return
    if tool_name == LlmToolName.CRIME_RISK:
        payload["crime_risk"] = args or True
        payload.update(args)
        return
    if tool_name == LlmToolName.REWARDS:
        payload.update(args)
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
