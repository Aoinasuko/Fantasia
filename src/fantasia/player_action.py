from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .quest_rules import QUEST_REPORT_CHOICE_LABEL


class PlayerInputType(str, Enum):
    CHOICE = "choice"
    FREE_ACTION = "free_action"


class ActionCommandType(str, Enum):
    INPUT_REJECTED = "input_rejected"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    GUARD_ENCOUNTER = "guard_encounter"
    ENCOUNTER = "encounter"
    HOME = "home"
    ATTACK = "attack"
    SKILL = "skill"
    CRAFT = "craft"
    TRADE_NEGOTIATION = "trade_negotiation"
    FACILITY = "facility"
    QUEST_START = "quest_start"
    QUEST_REPORT = "quest_report"
    QUEST_GO_TO_DESTINATION = "quest_go_to_destination"
    QUEST_OBJECTIVE_ACTION = "quest_objective_action"
    QUEST_ABANDON = "quest_abandon"
    CONVERSATION_CONTINUE = "conversation_continue"
    CONVERSATION_START = "conversation_start"
    FIELD_EVENT = "field_event"
    MASTER_AI = "master_ai"


@dataclass(frozen=True)
class PlayerActionRequest:
    text: str
    input_type: str
    generated_choice: bool = False
    before_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, engine: Any, action: str, input_type: str) -> "PlayerActionRequest":
        text = normalise_action_text(action)
        return cls(
            text=text,
            input_type=str(input_type or PlayerInputType.FREE_ACTION.value),
            generated_choice=is_generated_choice(engine, text, input_type),
            before_context=engine._input_dedupe_context(),
        )


@dataclass(frozen=True)
class ActionCommand:
    type: ActionCommandType
    text: str
    input_type: str
    source: str = "player"
    target: str = ""
    generated_choice: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "manager": "player_action",
            "command_type": self.type.value,
            "action": self.text,
            "input_type": self.input_type,
            "source": self.source,
            "generated_choice": self.generated_choice,
        }
        if self.target:
            record["target"] = self.target
        if self.payload:
            record["payload"] = self.payload
        return record


def normalise_action_text(action: str) -> str:
    text = str(action or "").strip()
    return text or "周囲を見る"


def is_generated_choice(engine: Any, action_text: str, input_type: str) -> bool:
    if input_type != PlayerInputType.CHOICE.value:
        return False
    normalized = str(action_text or "").strip()
    if not normalized:
        return False
    return any(normalized == str(choice).strip() for choice in engine.state.choices if str(choice).strip())


def record_action_command(engine: Any, command: ActionCommand) -> None:
    try:
        engine.state.world_data.history.append(command.to_record())
    except Exception:
        return


def player_action_type_for_text(
    action: str,
    *,
    is_skill_action: Callable[[str], bool],
) -> ActionCommandType | None:
    if is_skill_action(action):
        return ActionCommandType.SKILL
    return None


def quest_action_command_type(
    engine: Any,
    quest: Any,
    action: str,
    *,
    is_quest_abandon_action: Callable[[str], bool],
    is_quest_report_action: Callable[[str], bool],
) -> ActionCommandType:
    if is_quest_abandon_action(action):
        return ActionCommandType.QUEST_ABANDON
    destination_requested = _quest_destination_action_requested(engine, quest, action)
    if _explicit_quest_report_action(action):
        return ActionCommandType.QUEST_REPORT
    if destination_requested:
        return ActionCommandType.QUEST_GO_TO_DESTINATION
    if is_quest_report_action(action):
        return ActionCommandType.QUEST_REPORT
    return ActionCommandType.QUEST_OBJECTIVE_ACTION


def _explicit_quest_report_action(action: str) -> bool:
    text = str(action or "").strip()
    if text == QUEST_REPORT_CHOICE_LABEL:
        return True
    lowered = text.casefold()
    if any(
        phrase in text
        for phrase in (
            "依頼を報告",
            "依頼の報告",
            "依頼完了",
            "クエスト報告",
            "ギルドに報告",
            "受付に報告",
            "報告する",
            "達成報告",
            "完了報告",
            "報酬をもら",
            "報酬を受け取",
            "報酬を請求",
        )
    ):
        return True
    return any(word in lowered for word in ("report quest", "turn in quest", "claim reward"))


def _quest_destination_action_requested(engine: Any, quest: Any, action: str) -> bool:
    destination = getattr(quest, "extra", {}).get("destination") if isinstance(getattr(quest, "extra", None), dict) else {}
    if not isinstance(destination, dict):
        return False
    location_name = str(destination.get("location") or destination.get("destination_location") or "").strip()
    objective_name = str(destination.get("objective_subnode_name") or "").strip()
    objective_id = str(destination.get("objective_subnode_id") or "").strip()
    if location_name and location_name not in getattr(engine.state.world_data, "locations", {}):
        return False
    text = str(action or "")
    lowered = text.casefold()
    movement_requested = any(word in text for word in ("向か", "行く", "移動", "出発", "進む", "入る", "戻")) or any(
        word in lowered for word in ("go", "travel", "move", "head", "depart", "enter", "return")
    )
    if not movement_requested:
        return False
    named_target = any(value and value in text for value in (location_name, objective_name, objective_id))
    generic_target = any(word in text for word in ("目的地", "現地", "目標地点")) or any(
        word in lowered for word in ("destination", "target site", "objective site")
    )
    return named_target or generic_target


def resolve_player_input(
    engine: Any,
    action: str,
    input_type: str,
    *,
    as_bool: Callable[[Any], bool],
    is_attack_action: Callable[[str], bool],
    is_surprise_attack_action: Callable[[str], bool],
    is_exploration_action: Callable[[str], bool],
    is_skill_action: Callable[[str], bool],
    is_quest_abandon_action: Callable[[str], bool],
    is_quest_report_action: Callable[[str], bool],
    strip_response_metadata: Callable[[Any], Any] | None = None,
) -> str:
    request = PlayerActionRequest.from_raw(engine, action, input_type)
    action_text = request.text
    before_context = request.before_context
    if engine._is_repeated_player_input(action_text, input_type, before_context):
        return engine.state.log_text(16)

    def command(command_type: ActionCommandType, *, target: str = "", payload: dict[str, Any] | None = None) -> ActionCommand:
        return ActionCommand(
            type=command_type,
            text=action_text,
            input_type=input_type,
            target=target,
            generated_choice=request.generated_choice,
            payload=payload or {},
        )

    def finish(action_command: ActionCommand, result: str) -> str:
        record_action_command(engine, action_command)
        engine._remember_resolved_input(action_text, input_type, before_context)
        engine.save_game()
        return result

    timeout_event = engine._fail_expired_active_quest(source="quest_deadline", append_log=True)
    if timeout_event:
        engine.save_game()
        return finish(command(ActionCommandType.TIMEOUT), engine.state.log_text(16))

    if request.generated_choice:
        input_gate = {
            "content_violation": False,
            "action_possible": True,
            "reason": "generated_choice",
            "message": "",
        }
        engine.state.world_data.history.append(
            {
                "manager": "input_gatekeeper",
                "action": action_text,
                "input_type": input_type,
                "skipped": True,
                "reason": "generated_choice",
            }
        )
    else:
        input_gate = engine._input_gatekeeper(
            action_text,
            input_type,
            check_feasibility=not engine.allow_any_action_concept,
        )
    illegal_check = input_gate
    if as_bool(illegal_check.get("content_violation")):
        message = str(illegal_check.get("message") or illegal_check.get("reason") or "その行動は処理されませんでした。")
        engine._append_turn(
            action_text,
            message,
            engine.state.current_location,
            engine.state.choices,
            input_type=input_type,
        )
        engine.state.world_data.history.append(
            {
                "manager": "input_gatekeeper",
                "action": action_text,
                "input_type": input_type,
                "response": strip_response_metadata(illegal_check),
            }
            if strip_response_metadata is not None
            else {
                "manager": "input_gatekeeper",
                "action": action_text,
                "input_type": input_type,
                "response": illegal_check,
            }
        )
        engine.save_game()
        return finish(command(ActionCommandType.INPUT_REJECTED, payload={"content_violation": True}), engine.state.log_text(16))

    if not engine.allow_any_action_concept:
        feasibility_check = input_gate
        if not as_bool(feasibility_check.get("action_possible")):
            message = str(
                feasibility_check.get("message")
                or feasibility_check.get("reason")
                or "その行動は、現在の状況では実現できない。"
            )
            engine._append_turn(
                action_text,
                message,
                engine.state.current_location,
                engine.state.choices,
                input_type=input_type,
            )
            engine.state.world_data.history.append(
                {
                    "manager": "input_gatekeeper",
                    "action": action_text,
                    "input_type": input_type,
                    "allowed": False,
                    "response": strip_response_metadata(feasibility_check),
                }
                if strip_response_metadata is not None
                else {
                    "manager": "input_gatekeeper",
                    "action": action_text,
                    "input_type": input_type,
                    "allowed": False,
                    "response": feasibility_check,
                }
            )
            engine.save_game()
            return finish(command(ActionCommandType.INPUT_REJECTED, payload={"action_possible": False}), engine.state.log_text(16))

    block_reason = engine._player_incapacitated_action_block(action_text)
    if block_reason:
        return finish(
            command(ActionCommandType.BLOCKED, target=str(block_reason)),
            engine._resolve_blocked_player_action(action_text, input_type, block_reason),
        )

    guard_result = engine._maybe_start_guard_encounter(action_text, input_type)
    if guard_result:
        return finish(command(ActionCommandType.GUARD_ENCOUNTER), guard_result)

    active_encounter = engine._active_encounter()
    if active_encounter:
        command_type = ActionCommandType.SKILL if is_skill_action(action_text) else ActionCommandType.ENCOUNTER
        return finish(
            command(command_type, target=str(active_encounter.get("opponent_name") or "")),
            engine._resolve_encounter_input(action_text, input_type, active_encounter),
        )

    home_result = engine._resolve_home_action(action_text, input_type)
    if home_result is not None:
        return finish(command(ActionCommandType.HOME), home_result)

    if is_attack_action(action_text):
        if is_surprise_attack_action(action_text):
            return finish(command(ActionCommandType.ATTACK, payload={"surprise": True}), engine._resolve_player_attack(action_text, input_type))
        return finish(command(ActionCommandType.ATTACK), engine._start_encounter_from_attack(action_text, input_type))

    if input_type != PlayerInputType.FREE_ACTION.value:
        craft_result = engine._resolve_craft_action(action_text, input_type)
        if craft_result is not None:
            return finish(command(ActionCommandType.CRAFT), craft_result)

    trade_negotiation_target = engine._trade_negotiation_target(action_text)
    if trade_negotiation_target:
        return finish(
            command(ActionCommandType.TRADE_NEGOTIATION, target=str(trade_negotiation_target.name)),
            engine._resolve_trade_negotiation_action(action_text, input_type, trade_negotiation_target),
        )

    facility_result = engine._create_facility_from_action(action_text, input_type)
    if facility_result is not None:
        return finish(command(ActionCommandType.FACILITY), facility_result)

    quest_to_start = engine._find_quest_to_start(action_text)
    if quest_to_start:
        return finish(
            command(ActionCommandType.QUEST_START, target=str(quest_to_start.name)),
            engine._start_quest(action_text, input_type, quest_to_start),
        )

    if engine.state.active_quest:
        active_quest = engine._find_quest_by_name(engine.state.active_quest)
        if active_quest:
            quest_command_type = quest_action_command_type(
                engine,
                active_quest,
                action_text,
                is_quest_abandon_action=is_quest_abandon_action,
                is_quest_report_action=is_quest_report_action,
            )
            if quest_command_type != ActionCommandType.QUEST_REPORT and engine._active_quest_can_report_at(engine.state.current_location):
                conversation_target = engine._find_conversation_target(action_text)
                if conversation_target:
                    return finish(
                        command(ActionCommandType.CONVERSATION_START, target=str(conversation_target.name)),
                        engine._start_conversation(action_text, input_type, conversation_target),
                    )
            action_roll = None
            if quest_command_type != ActionCommandType.QUEST_REPORT:
                action_roll = engine._action_roll_for_input(action_text, input_type, "quest")
            action_kind = player_action_type_for_text(
                action_text,
                is_skill_action=is_skill_action,
            )
            payload = {"action_roll": action_roll or {}}
            if action_kind is not None:
                payload["player_action_type"] = action_kind.value
            return finish(
                command(quest_command_type, target=str(active_quest.name), payload=payload),
                engine._resolve_active_quest_action(
                    action_text,
                    input_type,
                    active_quest,
                    action_roll=action_roll,
                    action_command_type=quest_command_type.value,
                    player_action_type=action_kind.value if action_kind is not None else "",
                ),
            )
        engine.state.active_quest = ""

    active_conversation = engine._active_conversation_character()
    if active_conversation:
        action_roll = engine._action_roll_for_input(action_text, input_type, "conversation")
        return finish(
            command(ActionCommandType.CONVERSATION_CONTINUE, target=str(active_conversation.name), payload={"action_roll": action_roll or {}}),
            engine._continue_conversation(action_text, input_type, active_conversation, action_roll=action_roll),
        )

    conversation_target = engine._find_conversation_target(action_text)
    if conversation_target:
        return finish(
            command(ActionCommandType.CONVERSATION_START, target=str(conversation_target.name)),
            engine._start_conversation(action_text, input_type, conversation_target),
        )

    action_roll: dict[str, Any] | None = None
    action_kind = player_action_type_for_text(
        action_text,
        is_skill_action=is_skill_action,
    )
    exploration_action = is_exploration_action(action_text)
    if exploration_action:
        action_roll = engine._action_roll_for_input(action_text, input_type, "exploration")
    if exploration_action and engine._should_run_field_event_evaluator(action_text, input_type):
        field_event_trigger = engine._roll_field_event_trigger(action_text, input_type, action_roll)
        if not as_bool(field_event_trigger.get("triggered")):
            engine.state.world_data.history.append(
                {
                    "manager": "field_event_local_roll",
                    "action": action_text,
                    "input_type": input_type,
                    "action_roll": action_roll,
                    "field_event_trigger": field_event_trigger,
                    "event_occurred": False,
                    "called_llm": False,
                }
            )
        else:
            field_event = engine._field_event_evaluator(
                action_text,
                input_type,
                action_roll=action_roll,
                field_event_trigger=field_event_trigger,
            )
            if as_bool(field_event.get("event_occurred")):
                return finish(
                    command(
                        ActionCommandType.FIELD_EVENT,
                        payload={"field_event_trigger": field_event_trigger, "routed_to": ActionCommandType.FIELD_EVENT.value},
                    ),
                    engine._apply_field_event(
                        action_text,
                        input_type,
                        field_event,
                        action_roll=action_roll,
                        field_event_trigger=field_event_trigger,
                    ),
                )
            engine.state.world_data.history.append(
                {
                    "manager": "field_event_evaluator",
                    "action": action_text,
                    "input_type": input_type,
                    "action_roll": action_roll,
                    "field_event_trigger": field_event_trigger,
                    "event_occurred": False,
                    "response": strip_response_metadata(field_event)
                    if strip_response_metadata is not None
                    else field_event,
                }
            )

    if action_roll is None:
        action_roll = engine._action_roll_for_input(action_text, input_type, "action")
    return finish(
        command(
            action_kind or ActionCommandType.MASTER_AI,
            payload={"action_roll": action_roll or {}, "routed_to": ActionCommandType.MASTER_AI.value},
        ),
        engine._resolve_master_ai_turn(action_text, input_type, action_roll=action_roll),
    )
