from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

def _quest_starter_location(self, action: str, response: dict[str, Any]) -> str:
    current = self.state.current_location or self.state.world_data.starting_location
    proposed = str(response.get("location") or current).strip() or current
    facility_result = self._normalize_facility_response_location(action, response, current, proposed)
    if facility_result is not None:
        return str(facility_result.get("location") or current)
    settlement = self._current_settlement_location()
    if settlement is not None and proposed != settlement.name and _looks_like_facility_location_name(proposed):
        facility_name = _facility_name_from_sub_location(settlement, proposed)
        if facility_name:
            facility = self._find_or_create_facility_record(settlement, facility_name)
            if facility:
                self._set_active_facility(settlement, facility)
        return settlement.name
    return current


def _start_quest(self, action: str, input_type: str, quest: QuestData) -> str:
    previous_location = self.state.current_location
    quest_destination = self._ensure_quest_destination(quest)
    response = self._quest_starter(quest)
    tool_payload = tool_effect_payload(response)
    quest_destination = self._ensure_quest_destination(quest, response)
    quest.status = "active"
    self.state.active_quest = quest.name
    state_lines = self._initialize_quest_state(quest, quest_destination, response)
    objective = str(response.get("objective") or "")
    if objective:
        quest.extra["objective"] = objective
    objective_lines = self._ensure_quest_objective_entities(quest, quest_destination, response)

    narration = str(response.get("narration") or response.get("text") or f"クエスト「{quest.name}」を開始した。")
    location = self._quest_starter_location(action, tool_payload)
    choices = self._augment_location_choices(_as_str_list(response.get("choices")), location)
    quest.log.append(
        {
            "manager": "quest_starter",
            "action": action,
            "response": _strip_response_metadata(response),
        }
    )
    self.state.world_data.history.append(
        {
            "manager": "quest_starter",
            "quest": quest.name,
            "action": action,
            "response": _strip_response_metadata(response),
        }
    )
    self.state.flags["screen_mode"] = "exploration"
    self._append_turn(action, narration, location, choices, input_type=input_type)
    tool_result = apply_common_response_tools(
        self,
        response,
        source="quest_starter",
        action=action,
        input_type=input_type,
        location=location,
        previous_location=previous_location,
        default_target="player",
        append_display=False,
    )
    status_lines = list(tool_result.status_lines)
    status_lines.extend(state_lines)
    status_lines.extend(objective_lines)
    if status_lines:
        status_lines = [_hide_internal_quest_tokens(line) for line in status_lines if str(line).strip()]
        self.state.display_log.extend(status_lines)
    if tool_result.results:
        quest.log[-1]["llm_tools"] = tool_result.to_record()
    self.save_game()
    return self.state.log_text(16)

def _quest_starter(self, quest: QuestData) -> dict[str, Any]:
    world_payload = _ai_json(self._focused_world_ai_context(include_recent_log=False))
    quest_payload = _ai_json(_quest_ai_context(quest))
    destination_payload = _ai_json(quest.extra.get("destination") if isinstance(quest.extra.get("destination"), dict) else {})
    messages = [
        {
            "role": "system",
            "content": (
                "あなたはAI駆動RPGのクエスト開始担当です。"
                "Fantasiaのquest_starter相当として、"
                "narration, choices を持つJSONだけを返してください。"
                "必要なら quest_name, objective, location も含めてください。"
                "この担当は依頼を受けた瞬間の導入だけを作ります。"
                "プレイヤーを目的地へ移動させたり、依頼達成扱いにしたり、報酬を渡したりしないでください。"
                "location は現在いる街または街の中の施設だけにしてください。"
                "quest_destination が渡された場合、その場所と objective_subnode がゲーム側で確定した目的地です。"
                "目的地名や目標地点名を別名へ言い換えたり、新しい目的地を作ったりしないでください。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界データ: {world_payload}\n"
                f"クエスト名: {quest.name}\n"
                f"クエストデータ: {quest_payload}\n"
                f"quest_destination: {destination_payload}\n"
                "このクエストの導入文、最初の目標、選択肢を作ってください。"
                "まだ目的地へは移動せず、まだ依頼は完了していません。"
                "選択肢には、準備や聞き込みを入れてください。目的地へ向かう選択肢はゲーム側の移動UIが追加します。"
            ),
        },
    ]
    messages.append(
        {
            "role": "user",
            "content": (
                "Quest objective entity rule: the game will create concrete objective NPCs, objective items, "
                "investigation markers, or procurement requirements at quest start. Do not invent a second "
                "different target. The game tracks objectives internally and will only complete the quest after "
                "the exact NPC/item/marker/requirement state is satisfied and reported at the quest origin. "
                "Never write internal ids or UUID-like identifiers in narration or choices. "
                "Do not decide quest completion or failure. The game controls quest flags, deadline, completion, and failure."
            ),
        }
    )
    messages.append({"role": "system", "content": tool_prompt_instruction()})
    messages.append({"role": "system", "content": self._movement_choice_rule_prompt()})
    return self._chat_json(
        "quest_starter",
        messages,
        max_tokens=700,
        world_name=self.state.world_name,
        player_name=self.state.player_name,
    )

def _resolve_active_quest_action(
    self,
    action: str,
    input_type: str,
    quest: QuestData,
    action_roll: dict[str, Any] | None = None,
    action_command_type: str = "",
    player_action_type: str = "",
) -> str:
    previous_location = self.state.current_location
    current_location = self.state.current_location or self.state.world_data.starting_location
    quest_movement_explicit = False
    timeout_event = self._fail_quest_if_deadline_expired(quest, source="quest_deadline", append_log=True)
    if timeout_event:
        self.save_game()
        return self.state.log_text(16)
    if _is_quest_abandon_action(action):
        narration = f"依頼「{quest.name}」から撤退した。"
        location = self.state.current_location or self.state.world_data.starting_location
        choices = self._location_default_choices(location)
        self.state.flags["screen_mode"] = "exploration"
        narration = _hide_internal_quest_tokens(narration)
        choices = [_hide_internal_quest_tokens(choice) for choice in choices]
        self._append_turn(action, narration, location, choices, input_type=input_type)
        self._finish_quest(quest, "abandoned", "player_abandoned", {"narration": narration})
        self._apply_visual_intent({}, "quest_abandoned", location, previous_location)
        self.save_game()
        return self.state.log_text(16)
    if action_command_type == ActionCommandType.QUEST_REPORT.value:
        return self._resolve_dedicated_quest_report(action, input_type, quest)
    referee = self._quest_referee_with_free_action(
        action,
        input_type,
        quest,
        action_roll=action_roll,
        action_command_type=action_command_type,
    )
    if action_roll:
        referee.setdefault("game_side_action_roll", action_roll)
    event_resolution: dict[str, Any] | None = None
    referee_tools = tool_effect_payload(referee)
    event_payload = referee_tools.get("event")
    if _quest_event_needs_resolve(event_payload):
        event_resolution = self._quest_referee_event_resolve(action, quest, referee)
    event_tools = tool_effect_payload(event_resolution) if event_resolution else {}

    narration_parts = [_quest_response_narration(referee)]
    if event_resolution:
        narration_parts.append(_quest_response_narration(event_resolution))
    narration = "\n".join(part for part in narration_parts if part).strip() or "クエストは静かに進行した。"

    quest_destination = self._quest_destination_for_action(
        quest,
        action,
        referee,
        event_resolution,
        explicit_movement=quest_movement_explicit,
    )
    if quest_movement_explicit:
        raw_location = str(
            event_tools.get("location")
            or referee_tools.get("location")
            or self.state.current_location
        )
        if quest_destination:
            raw_location = str(quest_destination.get("location") or raw_location)
        movement_response = dict(event_tools or referee_tools)
        if quest_destination:
            movement_response["location"] = raw_location
            movement_response.setdefault("destination_location", raw_location)
        movement_result = self._normalize_world_response_location(action, input_type, movement_response, raw_location)
    else:
        raw_location = current_location
        movement_response = {}
        movement_result = {
            "location": raw_location,
            "moved": False,
            "denied": False,
            "narration_lines": [],
            "status_lines": [],
        }
    location = str(movement_result.get("location") or raw_location)
    if quest.status == "failed":
        self.state.flags["screen_mode"] = "exploration"
        self.save_game()
        return self.state.log_text(16)
    if quest_destination and location == str(quest_destination.get("location") or ""):
        objective_subnode_id = str(quest_destination.get("objective_subnode_id") or "").strip()
        if objective_subnode_id:
            location_data = self.state.world_data.locations.get(location)
            if location_data:
                self._ensure_quest_objective_subnode(location_data, quest, quest_destination)
    self._set_player_presence(location)
    objective_lines = self._apply_quest_objective_action(quest, action, location)
    movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
    if movement_narration:
        narration = "\n".join([narration, *movement_narration]).strip()
    choices = _exploration_choices(_as_str_list((event_resolution or {}).get("choices") or referee.get("choices")))
    if not choices:
        choices = self._location_default_choices(location)
    finished = False
    finish_status = ""
    objective_pack = self._quest_objective_pack(quest)
    has_objective_entities = bool(objective_pack.get("entries"))
    objective_response = event_tools or referee_tools
    if has_objective_entities and not finished and self._quest_objective_completion_allowed(quest, action, location, objective_response):
        if _quest_completion_report_action(action):
            finished = True
            finish_status = "completed"
    completion_blocked_line = ""
    if _quest_completion_report_action(action) and has_objective_entities and not finished:
        completion_blocked_line = "> [Quest] 依頼はまだ報告できません: 目的が未達成、または報告先に戻っていません。"

    quest.log.append(
        {
            "manager": "quest_referee_with_free_action",
            "action": action,
            "input_type": input_type,
            "action_command_type": action_command_type,
            "player_action_type": player_action_type,
            "action_roll": action_roll,
            "response": _strip_response_metadata(referee),
        }
    )
    if event_resolution:
        quest.log.append(
            {
                "manager": "quest_referee_event_resolve",
                "action": action,
                "action_command_type": action_command_type,
                "response": _strip_response_metadata(event_resolution),
            }
        )
        quest.extra["last_event_resolution"] = _strip_response_metadata(event_resolution)
    elif event_payload:
        quest.extra["last_event"] = _strip_response_metadata(event_payload) if isinstance(event_payload, dict) else event_payload
    if referee_tools.get("quest_progress"):
        quest.extra["quest_progress"] = str(referee_tools.get("quest_progress"))
    if event_tools.get("quest_update"):
        quest.extra["quest_update"] = event_tools.get("quest_update")
    if finished:
        if not choices:
            choices = self._location_default_choices(location)

    self.state.world_data.history.append(
        {
            "manager": "quest_referee_with_free_action",
            "quest": quest.name,
            "action": action,
            "input_type": input_type,
            "action_command_type": action_command_type,
            "player_action_type": player_action_type,
            "action_roll": action_roll,
            "response": _strip_response_metadata(referee),
        }
    )
    if event_resolution:
        self.state.world_data.history.append(
            {
                "manager": "quest_referee_event_resolve",
                "quest": quest.name,
                "action": action,
                "action_command_type": action_command_type,
                "response": _strip_response_metadata(event_resolution),
            }
        )

    visual_response = event_tools or referee_tools
    combat_source = "quest_referee_event_resolve" if event_resolution else "quest_referee_with_free_action"
    narration, choices, transition_response = self._maybe_start_combat_from_response(
        action,
        input_type,
        combat_source,
        visual_response,
        location,
        narration,
        choices,
    )
    if transition_response:
        quest.extra["last_combat_transition"] = _strip_response_metadata(transition_response)
    if not self._active_encounter() and movement_result.get("moved"):
        narration, choices, arrival_response = self._evaluate_hostile_arrival(
            action,
            input_type,
            "quest_arrival",
            location,
            narration,
            choices,
        )
        if arrival_response:
            quest.extra["last_hostile_arrival"] = _strip_response_metadata(arrival_response)
    if not self._active_encounter():
        self.state.flags["screen_mode"] = "exploration"
    narration = _hide_internal_quest_tokens(narration)
    choices = [_hide_internal_quest_tokens(choice) for choice in choices]
    self._append_turn(action, narration, location, choices, input_type=input_type)
    self._append_action_roll_log(action_roll)
    tool_result = apply_common_response_tools(
        self,
        referee,
        source="quest_referee_with_free_action",
        action=action,
        input_type=input_type,
        location=location,
        previous_location=previous_location,
        movement_result=movement_result,
        default_target="player",
        append_display=False,
    )
    status_lines = list(tool_result.status_lines)
    status_lines.extend(objective_lines)
    if completion_blocked_line:
        status_lines.append(completion_blocked_line)
    if tool_result.results:
        quest.extra["last_referee_tools"] = tool_result.to_record()
    if event_resolution:
        event_tool_result = apply_common_response_tools(
            self,
            event_resolution,
            source="quest_referee_event_resolve",
            action=action,
            input_type=input_type,
            location=location,
            previous_location=previous_location,
            default_target="player",
            append_display=False,
        )
        status_lines.extend(event_tool_result.status_lines)
        if event_tool_result.results:
            quest.extra["last_event_tools"] = event_tool_result.to_record()
    if status_lines:
        status_lines = [_hide_internal_quest_tokens(line) for line in status_lines if str(line).strip()]
        self.state.display_log.extend(status_lines)
    if finished:
        self._finish_quest(quest, finish_status, "quest_referee_event_resolve" if event_resolution else "quest_referee_with_free_action", event_resolution or referee)
    self.save_game()
    return self.state.log_text(16)

def _quest_referee_with_free_action(
    self,
    action: str,
    input_type: str,
    quest: QuestData,
    action_roll: dict[str, Any] | None = None,
    action_command_type: str = "",
) -> dict[str, Any]:
    world_payload = _ai_json(self._focused_world_ai_context(include_recent_log=False))
    quest_payload = _ai_json(_quest_ai_context(quest))
    destination_payload = _ai_json(quest.extra.get("destination") if isinstance(quest.extra.get("destination"), dict) else {})
    action_roll_payload = json.dumps(action_roll or {}, ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "あなたはAI駆動RPGのクエスト進行判定担当です。"
                "Fantasiaのquest_referee_with_free_action相当として、"
                "プレイヤーの自由行動をクエスト進行へ変換してください。"
                "narration, choices を持つJSONだけを返してください。"
                "必要なら location, quest_progress, event, finished も含めてください。"
                "game_side_action_roll が enabled=true の場合、クエスト行動の成否はゲーム側の確定判定として必ず尊重してください。"
                "event は未解決で追加判定が必要な突発事象だけに使い、単なる進捗や結果済みの出来事は quest_progress に書いてください。"
                "quest_destination がある場合、目的地と objective_subnode はゲーム側で確定済みです。"
                "目的地へ向かう行動では location に quest_destination.location を返し、別名の新規ロケーションを作らないでください。"
                "クエスト目標は objective_subnode に存在するものとして扱い、同じ目標を別の場所へ移動させないでください。"
                "救出対象を保護して依頼主へ報告し、クエスト完了として確定できる段階まで到達したら finished=true と quest_status=\"completed\" を必ず返してください。"
                "報酬金、経験値、報酬アイテムはゲーム側で決定して付与するため、gold, exp, reward, item_add は返さないでください。"
                "依頼の説明を聞いた、目的地や報酬内容を確認した、準備を始めた、だけの段階では finished や quest_status=\"completed\" を返さないでください。"
                "完了後に新しい探索フックを提示する場合も、このクエスト自体は完了として扱ってください。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界データ: {world_payload}\n"
                f"クエスト名: {quest.name}\n"
                f"クエストデータ: {quest_payload}\n"
                f"quest_destination: {destination_payload}\n"
                f"入力種別: {input_type}\n"
                f"action_command_type: {action_command_type}\n"
                f"プレイヤー行動: {action}\n"
                f"game_side_action_roll: {action_roll_payload}\n"
                "この行動がクエストをどう進めるか判定してください。"
            ),
        },
    ]
    messages.append(
        {
            "role": "system",
            "content": (
                "Action command rule: choices are display-only labels for the player and must never be used "
                "as evidence for movement, quest reporting, reward grants, combat start, or quest completion. "
                "Quest destination movement is not handled by this referee. Keep location at the current "
                "player location even if the narration mentions another place."
            ),
        }
    )
    messages.append(
        {
            "role": "system",
            "content": (
                "Override quest completion behavior: never decide quest completion or failure in this response. "
                "Do not output finished=true, quest_status, quest_completed, quest_failed, completed_quest, or complete_quest. "
                "The game-side quest state machine owns all quest flags, deadlines, completion, and failure."
            ),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "Important game-side objective rule: if quest_data.details.objective_entities exists, those listed objective entries "
                "are the only valid quest targets. Do not replace them with similarly named NPCs, items, places, or requirements. "
                "Narrate rescue, retrieval, defeat, delivery, investigation, procurement, escort, and reporting around those game-side tracked entities. The game "
                "will block completion until the exact objective entry state has been satisfied and reported. "
                "Never write internal ids or UUID-like identifiers in narration or choices. "
                "Do not set finished, quest_status, quest_completed, quest_failed, or completed_quest. "
                "Describe the scene and offer helpful choices; the game-side quest pipeline updates flags."
            ),
        }
    )
    messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
    messages.append({"role": "system", "content": tool_prompt_instruction()})
    messages.append({"role": "system", "content": self._movement_choice_rule_prompt()})
    return self._chat_json(
        "quest_referee_with_free_action",
        messages,
        max_tokens=800,
        world_name=self.state.world_name,
        player_name=self.state.player_name,
    )

def _quest_referee_event_resolve(
    self,
    action: str,
    quest: QuestData,
    referee_response: dict[str, Any],
) -> dict[str, Any]:
    world_payload = _ai_json(self._focused_world_ai_context(include_recent_log=False))
    quest_payload = _ai_json(_quest_ai_context(quest))
    referee_payload = json.dumps(_strip_response_metadata(referee_response), ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "あなたはAI駆動RPGのクエストイベント解決担当です。"
                "Fantasiaのquest_referee_event_resolve相当として、"
                "発生したイベントの結果を確定してください。"
                "narration, choices を持つJSONだけを返してください。"
                "必要なら location, quest_update, finished も含めてください。"
                "イベント解決後に元の目的が達成、失敗、撤退のいずれかに到達した場合は finished=true と quest_status を必ず返してください。"
                "結果済みの進捗をもう一度描写し直さず、必要な差分だけを短く返してください。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"世界データ: {world_payload}\n"
                f"クエスト名: {quest.name}\n"
                f"クエストデータ: {quest_payload}\n"
                f"プレイヤー行動: {action}\n"
                f"直前の判定: {referee_payload}\n"
                "イベント解決後の描写、クエスト更新、次の選択肢を確定してください。"
            ),
        },
    ]
    messages.append(
        {
            "role": "system",
            "content": (
                "Override quest completion behavior: never decide quest completion or failure in this response. "
                "Do not output finished=true, quest_status, quest_completed, quest_failed, completed_quest, or complete_quest. "
                "The game-side quest state machine owns all quest flags, deadlines, completion, and failure."
            ),
        }
    )
    messages.append(
        {
            "role": "user",
            "content": (
                "Use quest_data.details.objective_entities when present. The game validates completion with internal objective entries, "
                "so event resolution must not complete a quest unless the exact objective NPC, item, marker, or "
                "procurement requirement has reached the game-side report-ready state. Do not write internal ids or UUID-like identifiers. "
                "Do not decide completion or failure; the game-side flags do that."
            ),
        }
    )
    messages.append({"role": "system", "content": tool_prompt_instruction()})
    messages.append({"role": "system", "content": self._movement_choice_rule_prompt()})
    return self._chat_json(
        "quest_referee_event_resolve",
        messages,
        max_tokens=800,
        world_name=self.state.world_name,
        player_name=self.state.player_name,
    )

def _find_quest_to_start(self, action: str) -> QuestData | None:
    if not self.state.flags.get("allow_direct_quest_start"):
        return None
    if self.state.active_quest:
        return None
    text = action.strip()
    if not text:
        return None
    for quest in self.state.world_data.quests:
        if quest.status not in {"available", ""}:
            continue
        if quest.name and quest.name in text:
            return quest
    available_quests = [quest for quest in self.state.world_data.quests if quest.status in {"available", ""}]
    if available_quests and _text_may_need_context_reference(text):
        resolved = self._resolve_context_reference(text, "quest_start_target", allowed_target_types=["quest"])
        target_name = str(resolved.get("target_name") or "").strip()
        if target_name:
            for quest in available_quests:
                if quest.name == target_name or target_name in quest.name or quest.name in target_name:
                    return quest
    if "クエスト" in text or "依頼" in text:
        if len(available_quests) == 1:
            return available_quests[0]
        return available_quests[0] if available_quests else None
    return None

def _find_quest_by_name(self, name: str) -> QuestData | None:
    for quest in self.state.world_data.quests:
        if quest.name == name:
            return quest
    return None
