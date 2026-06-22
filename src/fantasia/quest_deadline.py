from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

def active_quest_remaining_hours(self) -> int | None:
    quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
    if not quest or quest.status != "active":
        return None
    deadline = _safe_int(quest.extra.get("deadline_hours"), -1)
    if deadline < 0:
        return None
    return max(0, deadline - self._world_time_total_hours())

def active_quest_remaining_time_label(self) -> str:
    remaining = self.active_quest_remaining_hours()
    if remaining is None:
        return "-"
    days, hours = divmod(int(remaining), HOURS_PER_DAY)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h"

def _quest_remaining_hours(self, quest: QuestData) -> int | None:
    deadline = _safe_int(quest.extra.get("deadline_hours"), -1)
    if deadline < 0:
        return None
    return max(0, deadline - self._world_time_total_hours())

def _fail_expired_active_quest(self, *, source: str, append_log: bool = False) -> dict[str, Any] | None:
    quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
    if not quest:
        return None
    return self._fail_quest_if_deadline_expired(quest, source=source, append_log=append_log)

def _fail_quest_if_deadline_expired(self, quest: QuestData, *, source: str, append_log: bool = False) -> dict[str, Any] | None:
    if quest.status != "active":
        return None
    deadline = _safe_int(quest.extra.get("deadline_hours"), -1)
    if deadline < 0 or self._world_time_total_hours() < deadline:
        return None
    event = self._finish_quest(quest, "failed", source, {"reason": "deadline_expired"})
    quest.extra["quest_stage"] = "failed"
    quest.extra["failure_reason"] = "deadline_expired"
    line = f"> [Quest] {quest.name} failed: time limit expired."
    if append_log:
        self.state.display_log.append(line)
    event["line"] = line
    return event

