from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .character import Character
from .status_effects import FLED_STATUS_ID, SURRENDERED_STATUS_ID, _merge_status_effect, _normalise_status_effect


class CombatToolName(str, Enum):
    COMBAT_END = "combat_end"
    PLAYER_SURRENDER = "player_surrender"
    ACCEPT_PLAYER_SURRENDER = "accept_player_surrender"
    REJECT_PLAYER_SURRENDER = "reject_player_surrender"
    CAPTURE_PLAYER = "capture_player"
    NPC_SURRENDER = "npc_surrender"
    NPC_FLEE = "npc_flee"
    APPLY_COMBAT_STATUS = "apply_combat_status"


@dataclass(frozen=True)
class CombatToolCall:
    name: CombatToolName
    source: str
    action: str = ""
    input_type: str = ""
    encounter: dict[str, Any] | None = None
    opponent: Character | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"tool": self.name.value, "source": self.source}
        if self.action:
            record["action"] = self.action
        if self.input_type:
            record["input_type"] = self.input_type
        if self.payload:
            record["payload"] = dict(self.payload)
        return record


@dataclass
class CombatToolResult:
    name: CombatToolName
    lines: list[str] = field(default_factory=list)
    event: dict[str, Any] = field(default_factory=dict)
    acted: bool = False
    finished: bool = False

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"tool": self.name.value}
        if self.lines:
            record["lines"] = list(self.lines)
        if self.event:
            record["event"] = dict(self.event)
        if self.acted:
            record["acted"] = True
        if self.finished:
            record["finished"] = True
        return record


@dataclass
class CombatToolBatchResult:
    results: list[CombatToolResult] = field(default_factory=list)
    status_lines: list[str] = field(default_factory=list)
    finished: bool = False

    def to_record(self) -> dict[str, Any]:
        return {
            "tools": [result.to_record() for result in self.results],
            "status_lines": list(self.status_lines),
            "finished": self.finished,
        }


def combat_enemy_tool_instruction() -> str:
    return (
        "Return compact combat JSON. Use action_type only for local combat calculation: "
        "attack, status_attack, skill, free_action. Put every combat state side effect in tool_judgements. "
        "Supported combat tools: combat_end, player_surrender, accept_player_surrender, "
        "reject_player_surrender, capture_player, npc_surrender, npc_flee, apply_combat_status. "
        "For each possible combat tool, return confidence from 0.0 to 1.0. The game executes only "
        "tools with confidence exactly 1.0. When the player is surrendering, set exactly one of "
        "accept_player_surrender, capture_player, or reject_player_surrender to confidence 1.0 "
        "before any attack. Do not set HP/SP/resource deltas; the game calculates them locally."
    )


def combat_tool_prompt_instruction() -> str:
    return (
        "Combat tool JSON rule: top-level fields may include intent, narration, action_type, "
        "attack_name, skill_name, element, choices, reason, finished, and tool_judgements. "
        "tool_judgements must be an array of {\"name\":\"tool_name\",\"confidence\":0.0-1.0,"
        "\"arguments\":{...},\"reason\":\"...\"}. The game executes only judgements whose "
        "confidence is exactly 1.0; 0.99 or missing confidence is not executed. "
        "Use player_surrender with confidence 1.0 when the player's intent is yielding, "
        "submitting, maintaining nonresistance, keeping weapons down, showing no hostility, "
        "or waiting helplessly for the enemy's decision. Do not rely on exact wording. "
        "Use accept_player_surrender or capture_player to end combat after accepting surrender. "
        "Use reject_player_surrender only when combat continues. Use npc_surrender when the "
        "opponent yields, npc_flee when the opponent escapes, apply_combat_status for combat-only "
        "conditions, and combat_end for a final truce, capture, or other non-damage end."
    )


def compact_combat_payload(value: Any, *, max_chars: int = 1600) -> str:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def combat_response_tool_calls(response: Any, *, source: str = "") -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    calls: list[dict[str, Any]] = []
    raw_tools: list[Any] = []
    for key in ("tool_judgements", "tool_judgments", "tool_confidences", "combat_tool_judgements", "tools"):
        value = response.get(key)
        if isinstance(value, list):
            raw_tools.extend(value)
    for raw in raw_tools:
        confidence = 0.0
        if isinstance(raw, str):
            name = raw
            args: Any = {}
        elif isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("tool_name") or raw.get("tool") or raw.get("type") or "")
            confidence = _confidence_value(raw.get("confidence") or raw.get("score") or raw.get("probability") or raw.get("judgement"))
            args = raw.get("arguments")
            if args is None:
                args = raw.get("args")
            if args is None:
                args = raw.get("parameters")
            if args is None:
                args = raw.get("payload")
            if args is None:
                args = {
                    key: value
                    for key, value in raw.items()
                    if key
                    not in {
                        "name",
                        "tool_name",
                        "tool",
                        "type",
                        "confidence",
                        "score",
                        "probability",
                        "judgement",
                        "arguments",
                        "args",
                        "parameters",
                        "payload",
                    }
                }
        else:
            continue
        if confidence < 1.0:
            continue
        canonical = _canonical_combat_tool_name(name)
        if canonical is None:
            continue
        calls.append({"name": canonical.value, "arguments": _tool_arguments(args), "source": source})
    return calls


def apply_combat_response_tools(
    engine: Any,
    response: dict[str, Any],
    *,
    source: str,
    action: str,
    input_type: str,
    encounter: dict[str, Any],
    opponent: Character | None = None,
) -> CombatToolBatchResult:
    batch = CombatToolBatchResult()
    for raw in combat_response_tool_calls(response, source=source):
        try:
            name = CombatToolName(raw["name"])
        except ValueError:
            continue
        result = run_combat_tool(
            engine,
            CombatToolCall(
                name,
                source=source,
                action=action,
                input_type=input_type,
                encounter=encounter,
                opponent=opponent,
                payload=raw.get("arguments") or {},
            ),
        )
        batch.results.append(result)
        batch.status_lines.extend(result.lines)
        if result.finished:
            batch.finished = True
    return batch


def run_combat_tool(engine: Any, call: CombatToolCall) -> CombatToolResult:
    encounter = call.encounter or {}
    if call.name == CombatToolName.PLAYER_SURRENDER:
        return _tool_player_surrender(engine, encounter, call.payload)
    if call.name == CombatToolName.ACCEPT_PLAYER_SURRENDER:
        return _tool_accept_player_surrender(engine, encounter, call.payload)
    if call.name == CombatToolName.REJECT_PLAYER_SURRENDER:
        return _tool_reject_player_surrender(engine, encounter, call.payload)
    if call.name == CombatToolName.CAPTURE_PLAYER:
        return _tool_capture_player(engine, encounter, call.payload, call.opponent, call.source)
    if call.name == CombatToolName.NPC_SURRENDER:
        return _tool_npc_surrender(engine, encounter, call.opponent)
    if call.name == CombatToolName.NPC_FLEE:
        return _tool_npc_flee(engine, encounter, call.opponent)
    if call.name == CombatToolName.APPLY_COMBAT_STATUS:
        return _tool_apply_combat_status(engine, encounter, call.payload, call.opponent, call.source, call.action)
    if call.name == CombatToolName.COMBAT_END:
        return _tool_combat_end(engine, encounter, call.payload)
    return CombatToolResult(call.name)


def _tool_player_surrender(engine: Any, encounter: dict[str, Any], payload: dict[str, Any]) -> CombatToolResult:
    encounter["player_surrendered"] = True
    encounter["player_status"] = "surrendering"
    encounter["surrender_resolution_pending"] = True
    reason = str(payload.get("reason") or "player_surrender").strip()
    line = str(payload.get("line") or "> [戦闘] あなたは降伏の意思を示し、相手の反応を待った。")
    event = {"kind": "player_surrender", "reason": reason}
    return CombatToolResult(CombatToolName.PLAYER_SURRENDER, lines=[line], event=event, acted=True)


def _tool_accept_player_surrender(engine: Any, encounter: dict[str, Any], payload: dict[str, Any]) -> CombatToolResult:
    encounter["player_surrendered"] = True
    encounter["player_status"] = "surrender_accepted"
    encounter["surrender_resolution_pending"] = False
    encounter["status"] = "ended"
    encounter["combat_end_reason"] = "player_surrender_accepted"
    for opponent in _encounter_opponents(engine, encounter):
        opponent.flags["hostile"] = False
        opponent.extra["hostile"] = False
    line = str(payload.get("line") or "> [戦闘] 相手はあなたの降伏を受け入れた。戦闘は終了した。")
    event = {"kind": "accept_player_surrender", "reason": str(payload.get("reason") or "")}
    return CombatToolResult(CombatToolName.ACCEPT_PLAYER_SURRENDER, lines=[line], event=event, acted=True, finished=True)


def _tool_reject_player_surrender(engine: Any, encounter: dict[str, Any], payload: dict[str, Any]) -> CombatToolResult:
    encounter["player_surrendered"] = True
    encounter["player_status"] = "surrender_rejected"
    encounter["surrender_resolution_pending"] = False
    line = str(payload.get("line") or "> [戦闘] 相手はあなたの降伏を拒み、戦闘を続ける。")
    event = {"kind": "reject_player_surrender", "reason": str(payload.get("reason") or "")}
    return CombatToolResult(CombatToolName.REJECT_PLAYER_SURRENDER, lines=[line], event=event, acted=True)


def _tool_capture_player(
    engine: Any,
    encounter: dict[str, Any],
    payload: dict[str, Any],
    opponent: Character | None,
    source: str,
) -> CombatToolResult:
    capture_payload = dict(payload)
    capture_payload.setdefault("npc_capture_player", True)
    lines = engine._apply_response_capture_relocation_effects(
        capture_payload,
        source,
        default_character=opponent or engine._encounter_opponent(encounter),
        default_location=str(encounter.get("location") or engine.state.current_location),
        encounter=encounter,
    )
    encounter["player_surrendered"] = bool(encounter.get("player_surrendered"))
    encounter["player_status"] = "captured"
    encounter["surrender_resolution_pending"] = False
    encounter["status"] = "ended"
    encounter["combat_end_reason"] = "player_captured"
    if not lines:
        lines = ["> [戦闘] あなたは捕えられた。戦闘は終了した。"]
    event = {
        "kind": "capture_player",
        "location": str(encounter.get("location") or engine.state.current_location),
        "subnode_id": str(encounter.get("capture_subnode_id") or ""),
        "subnode_name": str(encounter.get("capture_subnode_name") or ""),
    }
    return CombatToolResult(CombatToolName.CAPTURE_PLAYER, lines=[str(line) for line in lines if str(line).strip()], event=event, acted=True, finished=True)


def _tool_npc_surrender(engine: Any, encounter: dict[str, Any], opponent: Character | None = None) -> CombatToolResult:
    target = opponent if isinstance(opponent, Character) else engine._encounter_opponent(encounter)
    if not isinstance(target, Character):
        encounter["opponent_status"] = SURRENDERED_STATUS_ID
        return CombatToolResult(
            CombatToolName.NPC_SURRENDER,
            lines=["> [戦闘] 相手は降伏し、行動を止めた。"],
            event={"kind": "npc_surrender"},
            acted=True,
        )
    effect = _normalise_status_effect(
        {
            "id": SURRENDERED_STATUS_ID,
            "name": "降伏",
            "description": "戦闘で降伏し、敵対行動を止めている。",
            "duration": 0,
            "combat_state": SURRENDERED_STATUS_ID,
        },
        source="npc_surrender",
    )
    if effect:
        _merge_status_effect(target.status_effects, effect)
    target.flags["surrendered"] = True
    target.flags["hostile"] = False
    target.extra["surrendered"] = True
    target.extra["hostile"] = False
    engine._set_encounter_opponent_combat_status(encounter, target, SURRENDERED_STATUS_ID)
    return CombatToolResult(
        CombatToolName.NPC_SURRENDER,
        lines=[f"> [戦闘] {target.name}は降伏し、行動を止めた。"],
        event={"kind": "npc_surrender", "opponent": target.name},
        acted=True,
    )


def _tool_npc_flee(engine: Any, encounter: dict[str, Any], opponent: Character | None = None) -> CombatToolResult:
    target = opponent if isinstance(opponent, Character) else engine._encounter_opponent(encounter)
    if not isinstance(target, Character):
        encounter["opponent_status"] = FLED_STATUS_ID
        encounter["status"] = "ended"
        return CombatToolResult(
            CombatToolName.NPC_FLEE,
            lines=["> [戦闘] 相手は逃亡し、戦闘から外れた。"],
            event={"kind": "npc_flee"},
            acted=True,
            finished=True,
        )
    location = str(encounter.get("location") or target.location or engine.state.current_location)
    destination = engine._npc_flee_destination(target, location)
    target.flags["fled_from_combat"] = True
    target.extra["fled_from_combat"] = True
    engine._set_encounter_opponent_combat_status(encounter, target, FLED_STATUS_ID)
    if destination.get("location"):
        engine._set_character_presence(
            target,
            str(destination["location"]),
            "present",
            subnode_id=str(destination.get("subnode") or ""),
        )
        label = str(destination.get("label") or destination.get("location") or "")
        line = f"> [戦闘] {target.name}は{label}へ逃亡し、戦闘から外れた。"
    else:
        target.state = FLED_STATUS_ID
        target.flags["state"] = FLED_STATUS_ID
        target.extra["state"] = FLED_STATUS_ID
        line = f"> [戦闘] {target.name}はその場から逃げ去り、戦闘から外れた。"
    return CombatToolResult(
        CombatToolName.NPC_FLEE,
        lines=[line],
        event={"kind": "npc_flee", "opponent": target.name, "destination": destination},
        acted=True,
        finished=True,
    )


def _tool_apply_combat_status(
    engine: Any,
    encounter: dict[str, Any],
    payload: dict[str, Any],
    opponent: Character | None,
    source: str,
    action: str,
) -> CombatToolResult:
    target = str(payload.get("target") or payload.get("side") or "player").strip().casefold()
    target_key = "opponent" if target in {"opponent", "enemy", "npc", "monster"} else "player"
    if target_key == "opponent" and isinstance(opponent, Character):
        engine._set_encounter_active_opponent(encounter, opponent)
    status_value = (
        payload.get("status")
        or payload.get("status_effect")
        or payload.get("status_effects")
        or payload.get("condition")
        or payload.get("conditions")
        or payload
    )
    context_actor = opponent if target_key == "player" else engine.player_character()
    applied = engine._add_actor_status_effects(
        target_key,
        status_value,
        encounter=encounter,
        source=source,
        context_actor=context_actor,
        action_context=action,
        response_context=payload,
    )
    lines = [f"> [状態] {target_key}: {str(effect.get('name') or effect.get('id') or 'status')} が付与された。" for effect in applied]
    return CombatToolResult(
        CombatToolName.APPLY_COMBAT_STATUS,
        lines=lines,
        event={"kind": "apply_combat_status", "target": target_key, "count": len(applied)},
        acted=bool(applied),
    )


def _tool_combat_end(engine: Any, encounter: dict[str, Any], payload: dict[str, Any]) -> CombatToolResult:
    reason = str(payload.get("reason") or payload.get("outcome") or "ended").strip()
    encounter["status"] = "ended"
    encounter["combat_end_reason"] = reason
    if reason:
        encounter["opponent_status"] = reason if reason in {"fled", "escaped", "retreated", "surrender_accepted"} else str(encounter.get("opponent_status") or "ended")
    line = str(payload.get("line") or payload.get("narration") or f"> [戦闘] 戦闘は終了した: {reason}。")
    return CombatToolResult(CombatToolName.COMBAT_END, lines=[line], event={"kind": "combat_end", "reason": reason}, acted=True, finished=True)


def _encounter_opponents(engine: Any, encounter: dict[str, Any]) -> list[Character]:
    try:
        return [item for item in engine._encounter_opponents(encounter) if isinstance(item, Character)]
    except Exception:
        opponent = engine._encounter_opponent(encounter)
        return [opponent] if isinstance(opponent, Character) else []


_COMBAT_TOOL_ALIASES = {
    "combat_end": CombatToolName.COMBAT_END,
    "end_combat": CombatToolName.COMBAT_END,
    "finish_combat": CombatToolName.COMBAT_END,
    "player_surrender": CombatToolName.PLAYER_SURRENDER,
    "surrender_player": CombatToolName.PLAYER_SURRENDER,
    "accept_player_surrender": CombatToolName.ACCEPT_PLAYER_SURRENDER,
    "surrender_accept": CombatToolName.ACCEPT_PLAYER_SURRENDER,
    "accept_surrender": CombatToolName.ACCEPT_PLAYER_SURRENDER,
    "enemy_accept_player_surrender": CombatToolName.ACCEPT_PLAYER_SURRENDER,
    "reject_player_surrender": CombatToolName.REJECT_PLAYER_SURRENDER,
    "surrender_reject": CombatToolName.REJECT_PLAYER_SURRENDER,
    "reject_surrender": CombatToolName.REJECT_PLAYER_SURRENDER,
    "enemy_reject_player_surrender": CombatToolName.REJECT_PLAYER_SURRENDER,
    "capture_player": CombatToolName.CAPTURE_PLAYER,
    "npc_capture_player": CombatToolName.CAPTURE_PLAYER,
    "player_capture": CombatToolName.CAPTURE_PLAYER,
    "npc_surrender": CombatToolName.NPC_SURRENDER,
    "enemy_surrender": CombatToolName.NPC_SURRENDER,
    "opponent_surrender": CombatToolName.NPC_SURRENDER,
    "npc_flee": CombatToolName.NPC_FLEE,
    "enemy_flee": CombatToolName.NPC_FLEE,
    "opponent_flee": CombatToolName.NPC_FLEE,
    "apply_combat_status": CombatToolName.APPLY_COMBAT_STATUS,
    "combat_status": CombatToolName.APPLY_COMBAT_STATUS,
    "status": CombatToolName.APPLY_COMBAT_STATUS,
}


def _canonical_combat_tool_name(name: str) -> CombatToolName | None:
    key = str(name or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if not key:
        return None
    if key in _COMBAT_TOOL_ALIASES:
        return _COMBAT_TOOL_ALIASES[key]
    try:
        return CombatToolName(key)
    except ValueError:
        return None


def _tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    return {"value": value}


def _confidence_value(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            try:
                return max(0.0, min(1.0, float(text[:-1].strip()) / 100.0))
            except ValueError:
                return 0.0
        try:
            return max(0.0, min(1.0, float(text)))
        except ValueError:
            return 0.0
    return 0.0
