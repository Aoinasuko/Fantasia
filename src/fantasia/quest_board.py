from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

def available_quest_board_quests(self) -> list[QuestData]:
    if self.state.active_quest:
        return []
    if not self.is_current_location_guild():
        return []
    settlement = self._current_settlement_location()
    settlement_name = settlement.name if settlement else self.state.current_location
    self._refresh_quest_board_for_settlement(settlement_name)
    quests: list[QuestData] = []
    for quest in self.state.world_data.quests:
        if quest.status not in {"available", ""}:
            continue
        if quest.flags.get("wild"):
            continue
        if quest.neighboring_settlement and settlement_name and quest.neighboring_settlement != settlement_name:
            continue
        self._assign_quest_danger(quest, quest.neighboring_settlement or settlement_name)
        self._ensure_quest_reward(quest)
        quests.append(quest)
    return quests

def _quest_board_target_count(self, world: WorldData, settlement_name: str, *, day: int | None = None) -> int:
    day_value = max(1, int(day or 1))
    rng = random.Random(f"quest-board-count|{world.world_name}|{settlement_name}|{day_value}")
    return rng.randint(QUEST_BOARD_REGEN_MIN, QUEST_BOARD_REGEN_MAX)

def _refresh_quest_board_for_settlement(self, settlement_name: str) -> None:
    settlement_name = str(settlement_name or "").strip()
    if not settlement_name:
        return
    world = self.state.world_data
    day = self.current_absolute_day()
    board_state = world.extra.setdefault("quest_board_generation", {})
    if not isinstance(board_state, dict):
        board_state = {}
        world.extra["quest_board_generation"] = board_state
    record = board_state.get(settlement_name)
    if isinstance(record, dict) and _safe_int(record.get("day"), 0) == day:
        return
    world.quests = [
        quest
        for quest in world.quests
        if not (
            quest.status in {"available", ""}
            and not quest.flags.get("wild")
            and str(quest.flags.get("source") or "") == "settlement_quest_generator"
            and (not quest.neighboring_settlement or quest.neighboring_settlement == settlement_name)
        )
    ]
    target_count = self._quest_board_target_count(world, settlement_name, day=day)
    response = self._generate_settlement_quests(self.state.player_name, world, settlement_name, target_count=target_count)
    self._apply_settlement_quests(world, response, settlement_name)
    board_state[settlement_name] = {
        "day": day,
        "count": target_count,
        "source": "quest_board_open",
    }
    world.history.append(
        {
            "manager": "settlement_quest_generator",
            "location": settlement_name,
            "count": target_count,
            "trigger": "quest_board_open",
            "response": _strip_response_metadata(response),
        }
    )

def accept_quest_from_board(self, quest_name: str) -> str:
    if self.state.active_quest:
        self._append_turn(
            QUEST_BOARD_CHOICE_LABEL,
            "進行中の依頼があるため、別の依頼はまだ受けられない。",
            self.state.current_location,
            self._location_default_choices(self.state.current_location),
            input_type="choice",
        )
        self.save_game()
        return self.state.log_text(16)
    if not self.is_current_location_guild():
        self._append_turn(
            QUEST_BOARD_CHOICE_LABEL,
            "依頼掲示板はギルドの中で確認できる。",
            self.state.current_location,
            self._location_default_choices(self.state.current_location),
            input_type="choice",
        )
        self.save_game()
        return self.state.log_text(16)
    quest = self._find_quest_by_name(quest_name)
    if not quest or quest.status not in {"available", ""} or quest.flags.get("wild"):
        self._append_turn(
            QUEST_BOARD_CHOICE_LABEL,
            "その依頼は現在受けられない。",
            self.state.current_location,
            self._location_default_choices(self.state.current_location),
            input_type="choice",
        )
        self.save_game()
        return self.state.log_text(16)
    return self._start_quest(f"依頼を受ける: {quest.name}", "choice", quest)

def _active_quest_can_report_at(self, location_name: str = "") -> bool:
    if not self.state.active_quest:
        return False
    location = str(location_name or self.state.current_location or self.state.world_data.starting_location).strip()
    if location != str(self.state.current_location or "").strip():
        return False
    if not self.is_current_location_guild():
        return False
    quest = self._find_quest_by_name(self.state.active_quest)
    if not quest or quest.status != "active":
        return False
    return self._quest_objectives_returned(quest, location)

def _resolve_dedicated_quest_report(self, action: str, input_type: str, quest: QuestData) -> str:
    location = self.state.current_location or self.state.world_data.starting_location
    if not self.is_current_location_guild():
        narration = "依頼の報告は、受注したギルドの受付で行う必要がある。"
        self._append_turn(action, narration, location, self._location_default_choices(location), input_type=input_type)
        self.save_game()
        return self.state.log_text(16)
    if not self._quest_objectives_returned(quest, location):
        narration = "依頼はまだ報告できない。目的が未達成か、報告先が違っている。"
        self._append_turn(action, narration, location, self._location_default_choices(location), input_type=input_type)
        self.save_game()
        return self.state.log_text(16)
    response = {"narration": f"ギルド受付で依頼「{quest.name}」の達成を報告した。"}
    display_len = len(self.state.display_log)
    event = self._finish_quest(quest, "completed", "quest_report_command", response)
    reward_lines = self.state.display_log[display_len:]
    if reward_lines:
        del self.state.display_log[display_len:]
    choices = self._location_default_choices(location)
    self.state.flags["screen_mode"] = "exploration"
    self._append_turn(action, str(response["narration"]), location, choices, input_type=input_type)
    if reward_lines:
        self.state.display_log.extend(reward_lines)
    self.save_game()
    return self.state.log_text(16)
