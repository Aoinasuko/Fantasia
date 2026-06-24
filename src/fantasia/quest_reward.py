from __future__ import annotations

import random
from typing import Any

from .item_generate_loottabel import choose_loot_table_by_tag, generate_loot_table_items, loot_table_by_id
from .quest_rules import (
    _as_list,
    _clamp_world_danger,
    _quest_type,
    _safe_int,
    _strip_response_metadata,
)
from .world_model import QuestData

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

QUEST_REWARD_TABLE = (
    (1, (60, 80), (30, 60)),
    (10, (250, 300), (60, 90)),
    (20, (450, 600), (90, 180)),
    (30, (800, 1000), (180, 360)),
    (40, (1300, 1700), (500, 1000)),
    (50, (2000, 2500), (1500, 2000)),
)

def _assign_quest_danger(self, quest: QuestData, origin_location: str = "") -> int:
    origin = str(origin_location or quest.neighboring_settlement or self.state.current_location or self.state.world_data.starting_location)
    base_danger = self._current_location_danger(origin)
    planned_danger = _safe_int(quest.extra.get("planned_danger_level"), 0)
    danger_cap = _clamp_world_danger(base_danger + 5)
    if planned_danger > 0:
        danger = max(1, min(_clamp_world_danger(planned_danger), danger_cap))
        source = str(quest.extra.get("danger_source") or "local_quest_plan")
    else:
        low = max(1, _clamp_world_danger(base_danger))
        high = max(low, danger_cap)
        rng = random.Random(f"quest-danger:{self.state.world_name}:{quest.name}:{origin}:{base_danger}")
        danger = rng.randint(low, high)
        source = "local_quest_generation"
    quest.extra["danger_level"] = danger
    quest.extra["planned_danger_level"] = danger
    quest.extra["origin_danger_level"] = base_danger
    quest.extra["danger_cap"] = danger_cap
    quest.extra["danger_source"] = source
    return int(quest.extra["danger_level"])


def _ensure_quest_reward(self, quest: QuestData) -> None:
    danger = max(1, _clamp_world_danger(_safe_int(quest.extra.get("danger_level"), 0)))
    if danger <= 1 and quest.extra.get("danger_source") != "local_quest_generation":
        danger = self._assign_quest_danger(quest)
    reward = quest.extra.get("reward")
    if (
        isinstance(reward, dict)
        and str(reward.get("source") or "") == "local_quest_reward"
        and _safe_int(reward.get("danger_level"), 0) == danger
    ):
        return
    quest.extra["reward"] = _local_quest_reward(self, quest, danger)


def _local_quest_reward(self, quest: QuestData, danger: int) -> dict[str, Any]:
    rng = random.Random(
        f"quest-reward:{self.state.world_name}:{self.state.world_data.world_name}:{quest.name}:{danger}:{_quest_type(quest)}"
    )
    gold_range, exp_range = _quest_reward_ranges_for_danger(danger)
    loot_table = _quest_reward_loot_table(self, quest, danger)
    loot_table_id = str((loot_table or {}).get("id") or "")
    items = generate_loot_table_items(
        loot_table_id,
        context=quest.name,
        danger_level=danger,
        seed=f"{quest.name}:{quest.extra.get('quest_type') or ''}:{danger}:{loot_table_id}",
        source="quest_reward",
    )
    return {
        "gold": rng.randint(gold_range[0], gold_range[1]),
        "exp": rng.randint(exp_range[0], exp_range[1]),
        "items": items,
        "item_category": loot_table_id,
        "loot_tabel_id": loot_table_id,
        "loot_tabel_name_jp": str((loot_table or {}).get("name_jp") or ""),
        "loot_tabel_name_en": str((loot_table or {}).get("name_en") or ""),
        "danger_level": danger,
        "source": "local_quest_reward",
    }


def _quest_reward_loot_table(self, quest: QuestData, danger: int) -> dict[str, Any]:
    table_id = str(quest.extra.get("reward_loot_table_id") or "").strip()
    table = loot_table_by_id(table_id) if table_id else None
    if table is None:
        table = choose_loot_table_by_tag(
            "reward",
            seed=f"quest-reward-table:{self.state.world_name}:{quest.name}:{danger}",
            context=quest.name,
            danger_level=danger,
        )
        table_id = str((table or {}).get("id") or "")
    quest.extra["reward_loot_table_id"] = table_id
    quest.extra["reward_loot_table_name_jp"] = str((table or {}).get("name_jp") or "")
    quest.extra["reward_loot_table_name_en"] = str((table or {}).get("name_en") or "")
    return table or {}


def _quest_reward_ranges_for_danger(danger: int) -> tuple[tuple[int, int], tuple[int, int]]:
    level = max(1, min(50, int(danger or 1)))
    previous = QUEST_REWARD_TABLE[0]
    for current in QUEST_REWARD_TABLE[1:]:
        if level <= current[0]:
            ratio = (level - previous[0]) / max(1, current[0] - previous[0])
            return (
                (
                    _interpolate_int(previous[1][0], current[1][0], ratio),
                    _interpolate_int(previous[1][1], current[1][1], ratio),
                ),
                (
                    _interpolate_int(previous[2][0], current[2][0], ratio),
                    _interpolate_int(previous[2][1], current[2][1], ratio),
                ),
            )
        previous = current
    return QUEST_REWARD_TABLE[-1][1], QUEST_REWARD_TABLE[-1][2]


def _interpolate_int(start: int, end: int, ratio: float) -> int:
    return int(round(start + (end - start) * max(0.0, min(1.0, ratio))))


def _grant_quest_reward(self, quest: QuestData) -> dict[str, Any]:
    if quest.flags.get("reward_granted"):
        return {"items": [], "lost_items": [], "gold": 0, "exp": 0, "lines": []}
    self._ensure_quest_reward(quest)
    reward = quest.extra.get("reward")
    payload: dict[str, Any] = {}
    if isinstance(reward, dict):
        payload.update({key: value for key, value in reward.items() if key not in {"items", "gold", "exp"}})
        if reward.get("items"):
            payload["item_add"] = reward.get("items")
        if reward.get("gold") is not None:
            payload["receive_gold"] = reward.get("gold")
        if reward.get("exp") is not None:
            payload["reward_exp"] = reward.get("exp")
    elif reward:
        payload["item_add"] = _as_list(reward)
    item_event = self._apply_response_item_effects(payload, "quest_reward")
    lines: list[str] = []
    lines.extend(self._apply_response_gold_effects(payload, "quest_reward"))
    lines.extend(self._apply_response_hunger_effects(payload, "quest_reward"))
    lines.extend(self._apply_response_exp_effects(payload, "quest_reward"))
    lines.extend(self._apply_response_time_effects(payload, "quest_reward"))
    lines.extend(self._apply_response_game_over_effects(payload, "quest_reward"))
    if lines:
        self.state.display_log.extend(lines)
    quest.flags["reward_granted"] = True
    quest.log.append({"manager": "quest_reward", "reward": reward, "lines": lines})
    return {
        **item_event,
        "exp": _safe_int(payload.get("reward_exp") or payload.get("exp") or payload.get("player_exp_delta"), 0),
        "lines": lines,
    }

def _finish_quest(self, quest: QuestData, status: str, source: str, response: dict[str, Any] | None = None) -> dict[str, Any]:
    final_status = status if status in {"completed", "failed", "abandoned", "cancelled"} else "completed"
    quest.status = final_status
    self.state.active_quest = ""
    event: dict[str, Any] = {
        "quest": quest.name,
        "status": final_status,
        "source": source,
        "location": self.state.current_location,
        "response": _strip_response_metadata(response or {}),
    }
    if final_status == "completed":
        event["objectives"] = self._complete_quest_objectives(quest, source=source)
        quest.extra["quest_stage"] = "completed"
        self._set_quest_flag(quest, "reported", True)
        if quest.name not in self.state.completed_quests:
            self.state.completed_quests.append(quest.name)
        event["reward"] = self._grant_quest_reward(quest)
    elif final_status in {"failed", "abandoned", "cancelled"}:
        event["objectives"] = self._close_quest_objectives(quest, final_status, source=source)
    quest.flags["finished"] = True
    quest.flags["finish_source"] = source
    quest.log.append(event)
    self.state.world_data.extra.setdefault("quest_finish_events", []).append(event)
    return event

def _maybe_finish_active_quest_from_response(self, response: dict[str, Any], source: str, action: str) -> dict[str, Any] | None:
    return None
