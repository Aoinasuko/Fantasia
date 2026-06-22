from __future__ import annotations

import random
from typing import Any

from .quest_rules import (
    _as_list,
    _clamp_world_danger,
    _quest_destination_danger,
    _quest_destination_hint,
    _quest_type,
    _safe_int,
    _strip_response_metadata,
)
from .world_model import QuestData

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

QUEST_REWARD_TABLE = (
    (1, (60, 80), (30, 60)),
    (10, (250, 300), (90, 150)),
    (20, (450, 600), (200, 400)),
    (30, (800, 1000), (600, 800)),
    (40, (1300, 1700), (1200, 1500)),
    (50, (2000, 2500), (2000, 3000)),
)

QUEST_REWARD_ITEM_POOLS_BY_TYPE = {
    "rescue": ("medicine", "potion", "accessory_amulet", "armor_cloth", "treasure"),
    "retrieve": ("treasure", "relic", "material_gem", "material_magical", "tool"),
    "defeat": ("weapon_small", "weapon_medium", "armor_body", "armor_shield", "material_creature", "treasure"),
    "delivery": ("tool", "document", "scroll", "medicine", "accessory_ring"),
    "investigate": ("document", "scroll", "magicrod", "relic", "material_magical"),
    "procure": ("material_common", "material_plant", "material_ore", "material_metal", "material_magical"),
}

QUEST_REWARD_ITEM_POOLS_BY_DANGER = (
    (1, ("food", "drink", "medicine", "tool", "document", "material_common", "material_plant")),
    (10, ("medicine", "potion", "tool", "scroll", "material_ore", "material_metal", "material_creature")),
    (20, ("potion", "scroll", "material_metal", "material_gem", "weapon_small", "weapon_medium", "armor_body")),
    (30, ("treasure", "relic", "magicrod", "material_magical", "weapon_large", "weapon_long", "armor_body", "accessory_ring")),
    (40, ("treasure", "relic", "magicrod", "material_gem", "material_magical", "weapon_range", "armor_shield", "accessory_amulet")),
    (50, ("relic", "treasure", "magicrod", "material_magical", "material_gem", "accessory_ring", "accessory_amulet")),
)


def _assign_quest_danger(self, quest: QuestData, origin_location: str = "") -> int:
    hint = _quest_destination_hint(quest)
    kind = str(hint.get("location_kind") or "").strip().lower()
    origin = str(origin_location or quest.neighboring_settlement or self.state.current_location or self.state.world_data.starting_location)
    base_danger = self._current_location_danger(origin)
    raw_danger = _quest_destination_danger(hint, kind, base_danger)
    danger_cap = _clamp_world_danger(base_danger + 5)
    quest.extra["danger_level"] = max(1, min(_clamp_world_danger(raw_danger), danger_cap))
    quest.extra["origin_danger_level"] = base_danger
    quest.extra["danger_cap"] = danger_cap
    quest.extra["danger_source"] = "local_quest_generation"
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
    item_category = _quest_reward_item_category(quest, danger, rng)
    item = _quest_reward_item(quest, danger, item_category)
    return {
        "gold": rng.randint(gold_range[0], gold_range[1]),
        "exp": rng.randint(exp_range[0], exp_range[1]),
        "items": [item],
        "item_category": item_category,
        "danger_level": danger,
        "source": "local_quest_reward",
    }


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


def _quest_reward_item_category(quest: QuestData, danger: int, rng: random.Random) -> str:
    quest_type = _quest_type(quest)
    type_pool = QUEST_REWARD_ITEM_POOLS_BY_TYPE.get(quest_type, ())
    danger_pool = QUEST_REWARD_ITEM_POOLS_BY_DANGER[0][1]
    for threshold, pool in QUEST_REWARD_ITEM_POOLS_BY_DANGER:
        if danger >= threshold:
            danger_pool = pool
    if danger >= 40:
        high_type_pool = {
            "rescue": ("relic", "treasure", "accessory_amulet", "material_magical"),
            "retrieve": ("relic", "treasure", "material_gem", "material_magical"),
            "defeat": ("weapon_large", "weapon_long", "weapon_range", "armor_body", "armor_shield", "relic", "treasure"),
            "delivery": ("relic", "treasure", "accessory_ring", "accessory_amulet", "scroll"),
            "investigate": ("relic", "magicrod", "material_magical", "scroll"),
            "procure": ("material_gem", "material_magical", "relic", "treasure"),
        }.get(quest_type, ())
        pool = list(high_type_pool) + list(danger_pool)
    else:
        pool = list(type_pool) + list(danger_pool)
    return rng.choice(pool or ["treasure"])


def _quest_reward_item(quest: QuestData, danger: int, category: str) -> dict[str, Any]:
    from .items import generate_reward_item

    item = generate_reward_item(
        category,
        context=quest.name,
        danger_level=danger,
        seed=f"{quest.name}:{quest.extra.get('quest_type') or ''}:{danger}",
    )
    item["reward_category"] = category
    return item

def _grant_quest_reward(self, quest: QuestData) -> dict[str, Any]:
    if quest.flags.get("reward_granted"):
        return {"items": [], "lost_items": [], "gold": 0, "exp": 0, "lines": []}
    self._ensure_quest_reward(quest)
    reward = quest.extra.get("reward")
    payload: dict[str, Any] = {}
    if isinstance(reward, dict):
        payload.update(reward)
        if reward.get("items") and not payload.get("item_add"):
            payload["item_add"] = reward.get("items")
        if reward.get("gold") is not None and not any(key in payload for key in ("receive_gold", "gain_gold", "gold_delta")):
            payload["receive_gold"] = reward.get("gold")
        if reward.get("exp") is not None and not any(key in payload for key in ("reward_exp", "exp", "player_exp_delta")):
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
