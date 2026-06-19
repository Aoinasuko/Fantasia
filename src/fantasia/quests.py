from __future__ import annotations

import json
import re
from typing import Any

from .world_model import QuestData


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "??"}
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _short_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in ("", None, [], {})}


def _is_ai_metadata_key(key: str) -> bool:
    return (
        key.startswith("_")
        or key.startswith("raw_")
        or key
        in {
            "history",
            "prompts",
            "image_paths",
            "image_pipeline",
            "generation_metadata",
            "postprocess",
            "source_response",
            "request",
            "request_params",
            "response_info",
            "prompt_debug",
        }
    )


def _compact_value(value: Any, *, max_chars: int = 1000, list_limit: int = 12, dict_limit: int = 16) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _short_text(value, max_chars)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [
            _compact_value(item, max_chars=max(160, max_chars // 2), list_limit=list_limit, dict_limit=dict_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= dict_limit:
                break
            key_text = str(key)
            if _is_ai_metadata_key(key_text):
                continue
            result[key_text] = _compact_value(
                item,
                max_chars=max(160, max_chars // 2),
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
        return _drop_empty(result)
    return _short_text(str(value), max_chars)


def _strip_response_metadata(response: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in response.items() if not key.startswith("_")}


def _clamp_world_danger(value: Any, default: int = 0) -> int:
    return max(0, min(50, _safe_int(value, default)))


INTERNAL_QUEST_NPC_ROLES = {
    "rescue_target",
    "blocker",
    "defeat_target",
    "delivery_target",
}

INTERNAL_QUEST_TOKEN_LABELS = {
    "rescue_target": "救出対象",
    "blocker": "妨害者",
    "defeat_target": "討伐対象",
    "delivery_target": "配達先",
    "retrieve_item": "回収品",
    "delivery_item": "配達品",
    "investigation_point": "調査地点",
    "procurement_requirement": "調達条件",
}

QUEST_BOARD_NAME = "依頼掲示板"

QUEST_BOARD_CHOICE_LABEL = "依頼掲示板を見る"

QUEST_DEADLINE_HOURS = 48

QUEST_TYPES = {"rescue", "retrieve", "defeat", "delivery", "investigate", "procure"}

QUEST_REPORT_STAGE = "report_ready"

SETTLEMENT_QUEST_MAX_PER_SETTLEMENT = 9

SETTLEMENT_QUEST_BATCH_MIN = 2

SETTLEMENT_QUEST_BATCH_MAX = 3

def _quest_destination_hint(quest: QuestData, response: dict[str, Any] | None = None) -> dict[str, Any]:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    destination_raw = extra.get("destination") if isinstance(extra.get("destination"), dict) else {}
    hint_raw = extra.get("destination_hint") if isinstance(extra.get("destination_hint"), dict) else {}
    text = _quest_destination_source_text(quest, response)
    location_name = str(
        response.get("destination_location")
        or response.get("target_location")
        or hint_raw.get("location")
        or hint_raw.get("destination_location")
        or destination_raw.get("location")
        or extra.get("destination_location")
        or extra.get("target_location")
        or ""
    ).strip()
    kind = str(
        response.get("destination_kind")
        or response.get("location_kind")
        or hint_raw.get("kind")
        or hint_raw.get("location_kind")
        or destination_raw.get("location_kind")
        or ""
    ).strip().lower()
    if not kind:
        kind = _quest_location_kind_from_text(text)
    anchor_kind = str(hint_raw.get("anchor_kind") or "").strip().lower()
    if not anchor_kind:
        anchor_kind = _quest_anchor_kind_from_text(text, kind)
    objective_name = str(
        response.get("objective_subnode_name")
        or response.get("objective_name")
        or hint_raw.get("objective_subnode_name")
        or hint_raw.get("objective_name")
        or destination_raw.get("objective_subnode_name")
        or ""
    ).strip()
    objective_description = str(
        response.get("objective_subnode_description")
        or response.get("objective_description")
        or hint_raw.get("objective_subnode_description")
        or hint_raw.get("objective_description")
        or destination_raw.get("objective_subnode_description")
        or quest.overview
        or ""
    ).strip()
    return {
        "source_text": text,
        "location": location_name,
        "location_kind": kind,
        "anchor_kind": anchor_kind,
        "anchor_location": str(hint_raw.get("anchor_location") or destination_raw.get("anchor_location") or "").strip(),
        "description": str(hint_raw.get("description") or destination_raw.get("description") or "").strip(),
        "objective_subnode_id": str(destination_raw.get("objective_subnode_id") or "").strip(),
        "objective_subnode_name": objective_name or _quest_objective_name_from_text(text),
        "objective_subnode_description": objective_description,
    }

def _quest_destination_source_text(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    parts: list[str] = [
        quest.name,
        quest.overview,
        quest.neighboring_settlement,
        json.dumps(quest.choices, ensure_ascii=False, default=str),
        json.dumps(extra, ensure_ascii=False, default=str),
    ]
    if response:
        parts.append(json.dumps(_strip_response_metadata(response), ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if str(part or "").strip())

def _quest_location_kind_from_text(text: str) -> str:
    lowered = str(text or "").casefold()
    if any(word in lowered for word in ("dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair", "洞窟", "迷宮", "遺跡", "鉱山", "巣穴", "巣")):
        return "dungeon"
    if any(word in lowered for word in ("forest", "woods", "swamp", "wild", "森", "樹海", "沼", "荒野")):
        return "wilderness"
    if any(word in lowered for word in ("coast", "beach", "shore", "seaside", "海岸", "浜辺", "岬")):
        return "coast"
    if any(word in lowered for word in ("mountain", "peak", "ridge", "山", "峠", "尾根")):
        return "mountain"
    if any(word in lowered for word in ("river", "stream", "brook", "川", "河", "沢", "渡し")):
        return "river"
    if any(word in lowered for word in ("plain", "field", "grassland", "meadow", "平原", "草原", "牧野")):
        return "plain"
    if any(word in lowered for word in ("crossroad", "junction", "fork", "分岐路", "分かれ道", "辻")):
        return "crossroad"
    if any(word in lowered for word in ("road", "trail", "route", "街道", "古道", "小道")):
        return "road"
    if any(word in lowered for word in ("rescue", "save", "討伐", "救出", "救助", "行方不明", "連れ去", "魔物", "モンスター")):
        return "wilderness"
    return "wilderness"

def _quest_anchor_kind_from_text(text: str, destination_kind: str) -> str:
    lowered = str(text or "").casefold()
    near_words = ("near", "nearby", "around", "近く", "周辺", "付近", "そば")
    if not any(word in lowered for word in near_words):
        return ""
    if any(word in lowered for word in ("road", "trail", "route", "街道", "古道", "小道")) and destination_kind != "road":
        return "road"
    if any(word in lowered for word in ("crossroad", "junction", "分岐路", "分かれ道", "辻")) and destination_kind != "crossroad":
        return "crossroad"
    if any(word in lowered for word in ("river", "stream", "川", "河", "沢")) and destination_kind != "river":
        return "river"
    return ""

def _quest_location_kind_label(kind: str) -> str:
    return {
        "dungeon": "ダンジョン",
        "wilderness": "森",
        "road": "街道",
        "crossroad": "分岐路",
        "coast": "海岸",
        "mountain": "山",
        "river": "川辺",
        "plain": "平原",
        "landmark": "目標地点",
    }.get(str(kind or "").strip().lower(), "探索地")

def _quest_destination_name(quest: QuestData, hint: dict[str, Any], origin: str, anchor: str) -> str:
    kind = str(hint.get("location_kind") or "wilderness").strip().lower()
    anchor_kind = str(hint.get("anchor_kind") or "").strip().lower()
    label = _quest_location_kind_label(kind)
    text = str(hint.get("source_text") or "")
    anchor_name = str(anchor or origin or "").strip()
    if kind == "wilderness" and any(word in text for word in ("森", "forest", "woods")):
        label = "森"
    elif kind == "dungeon" and any(word in text for word in ("洞窟", "cave", "cavern")):
        label = "洞窟"
    if anchor_kind == "road" and anchor_name:
        return f"{str(origin or anchor_name).strip()}近郊の街道沿いの{label}"
    if anchor_kind == "crossroad" and anchor_name:
        return f"{str(origin or anchor_name).strip()}近郊の分岐路そばの{label}"
    if anchor_name:
        return f"{anchor_name}近くの{label}"
    return f"{quest.name}の{label}"

def _quest_objective_name_from_text(text: str) -> str:
    lowered = str(text or "").casefold()
    if any(word in lowered for word in ("rescue", "save", "救出", "救助", "娘", "行方不明")):
        return "救出対象のいる地点"
    if any(word in lowered for word in ("defeat", "討伐", "退治", "倒")):
        return "討伐目標のいる地点"
    if any(word in lowered for word in ("collect", "採取", "収集", "回収", "入手")):
        return "回収目標のある地点"
    if any(word in lowered for word in ("investigate", "調査", "確認", "探索")):
        return "調査目標地点"
    return "依頼目標地点"

def _quest_destination_danger(hint: dict[str, Any], kind: str, base_danger: int) -> int:
    text = str(hint.get("source_text") or "").casefold()
    danger = max(1, int(base_danger) + 5)
    if kind in {"dungeon", "wilderness", "mountain"}:
        danger = max(10, danger)
    if any(word in text for word in ("危険", "討伐", "魔物", "モンスター", "monster", "defeat", "rescue", "救出")):
        danger += 5
    return _clamp_world_danger(danger)

def _quest_text_requests_new_site(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(word in lowered for word in ("未知", "新しい", "隠れ", "未踏", "hidden", "unknown", "undiscovered"))

def _map_reveal_value_means_active_quest(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text in {
        "active_quest",
        "quest",
        "quest_destination",
        "objective_location",
        "target_location",
        "current_quest",
        "依頼目的地",
        "クエスト目的地",
        "目的地",
    }

def _map_reveal_reason(entry: Any) -> str:
    if isinstance(entry, dict):
        for key in ("reason", "source", "item", "map_name", "description"):
            value = str(entry.get(key) or "").strip()
            if value:
                return _short_text(value, 80)
    if entry is True:
        return "map reveal"
    return _short_text(str(entry or ""), 80)

def _normalise_quest_type_id(value: Any) -> str:
    explicit = str(value or "").strip().lower()
    aliases = {
        "rescue": "rescue",
        "search": "rescue",
        "find_person": "rescue",
        "escort": "rescue",
        "retrieve": "retrieve",
        "collect": "retrieve",
        "gather": "retrieve",
        "lost_item": "retrieve",
        "defeat": "defeat",
        "hunt": "defeat",
        "slay": "defeat",
        "subjugation": "defeat",
        "delivery": "delivery",
        "deliver": "delivery",
        "errand": "delivery",
        "investigate": "investigate",
        "investigation": "investigate",
        "survey": "investigate",
        "inspect": "investigate",
        "procure": "procure",
        "procurement": "procure",
        "supply": "procure",
        "acquire": "procure",
    }
    return aliases.get(explicit, "")

def _quest_type(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    explicit = _normalise_quest_type_id(
        response.get("quest_type")
        or response.get("objective_type")
        or extra.get("quest_type")
        or extra.get("objective_type")
        or extra.get("type")
        or extra.get("kind")
        or ""
    )
    if explicit:
        return explicit
    text = _quest_destination_source_text(quest, response)
    lowered = text.casefold()
    if any(word in lowered for word in ("deliver", "delivery", "errand", "courier")) or any(
        word in text for word in ("\u914d\u9054", "\u5c4a\u3051", "\u304a\u4f7f\u3044", "\u904b\u642c", "\u5c4a\u3051\u7269")
    ):
        return "delivery"
    if any(word in lowered for word in ("defeat", "slay", "hunt", "subjugate", "kill")) or any(
        word in text for word in ("\u8a0e\u4f10", "\u9000\u6cbb", "\u5012", "\u72e9", "\u6226")
    ):
        return "defeat"
    if any(word in lowered for word in ("rescue", "save", "escort", "hostage", "kidnap", "missing person")) or any(
        word in text for word in ("\u6551\u51fa", "\u6551\u52a9", "\u4fdd\u8b77", "\u8b77\u9001", "\u4eba\u8cea", "\u652b", "\u5a18", "\u884c\u65b9\u4e0d\u660e")
    ):
        return "rescue"
    if any(word in lowered for word in ("investigate", "investigation", "survey", "inspect", "research")) or any(
        word in text for word in ("\u8abf\u67fb", "\u8abf\u3079", "\u63a2\u308b", "\u63a2\u7d22", "\u78ba\u8a8d", "\u8e0f\u67fb", "\u5075\u5bdf", "\u6700\u6df1\u90e8")
    ):
        return "investigate"
    if any(word in lowered for word in ("procure", "procurement", "acquire", "obtain", "supply", "bring me")) or any(
        word in text for word in ("\u8abf\u9054", "\u7528\u610f", "\u624b\u306b\u5165\u308c\u3066", "\u5165\u624b\u3057\u3066", "\u8cb7\u3063\u3066", "\u4ed5\u5165\u308c")
    ):
        return "procure"
    return "retrieve"

def _quest_requires_captor(quest: QuestData, response: dict[str, Any] | None = None) -> bool:
    response = response or {}
    explicit = response.get("requires_captor") or response.get("captor_required") or quest.extra.get("requires_captor")
    if explicit not in (None, "", [], {}):
        return _as_bool(explicit)
    return False

def _quest_start_choices(quests: list[QuestData]) -> list[str]:
    return []

def _quest_response_narration(response: dict[str, Any] | None) -> str:
    if not isinstance(response, dict):
        return ""
    return str(response.get("narration") or response.get("text") or response.get("narr") or "").strip()

def _quest_event_needs_resolve(event: Any) -> bool:
    if not event:
        return False
    if isinstance(event, list):
        return any(_quest_event_needs_resolve(item) for item in event)
    if not isinstance(event, dict):
        text = str(event).strip()
        lowered = text.lower()
        return any(word in lowered or word in text for word in ("unresolved", "pending", "needs_resolution", "未解決", "保留", "判定待ち"))

    explicit_keys = (
        "requires_resolution",
        "needs_resolution",
        "unresolved",
        "pending",
        "choice_required",
        "combat_required",
    )
    for key in explicit_keys:
        if key in event:
            return _as_bool(event.get(key))

    status = str(event.get("status") or event.get("state") or "").strip().lower()
    if status in {"unresolved", "pending", "open", "needs_resolution", "active", "未解決", "保留", "継続中"}:
        return True
    if status in {"resolved", "complete", "completed", "done", "解決", "完了"}:
        return False

    if any(key in event for key in ("result", "outcome", "resolved_result", "summary")):
        return False
    return True

def _quest_payload_has_reward(payload: Any) -> bool:
    if isinstance(payload, list):
        return any(_quest_payload_has_reward(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    reward_keys = {
        "reward",
        "rewards",
        "item_rewards",
        "items",
        "receive_items",
        "gain_items",
        "gold_delta",
        "player_gold_delta",
        "receive_gold",
        "gain_gold",
        "reward_gold",
        "exp",
        "xp",
        "reward_exp",
        "player_exp_delta",
        "experience_delta",
    }
    for key in reward_keys:
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        if key in {"gold_delta", "player_gold_delta", "receive_gold", "gain_gold", "reward_gold", "exp", "xp", "reward_exp", "player_exp_delta", "experience_delta"}:
            if _safe_int(value, 0) <= 0:
                continue
        return True
    for value in payload.values():
        if isinstance(value, (dict, list)) and _quest_payload_has_reward(value):
            return True
    return False

def _quest_explicit_finish_status(referee: dict[str, Any] | None, event_resolution: dict[str, Any] | None) -> str:
    return ""
    for payload in (event_resolution or {}, referee or {}):
        status = str(
            payload.get("quest_status")
            or payload.get("quest_outcome")
            or ""
        ).strip().lower()
        if status in {"completed", "complete", "success", "succeeded", "cleared", "達成", "成功", "完了", "解決"}:
            return "completed"
        if status in {"failed", "failure", "fail", "失敗"}:
            return "failed"
        if status in {"abandoned", "withdrawn", "retreated", "cancelled", "canceled", "撤退", "放棄", "中止"}:
            return "abandoned"
        if _as_bool(payload.get("quest_finished") or payload.get("quest_completed") or payload.get("complete_quest") or payload.get("completed_quest")):
            return "completed"
        if _as_bool(payload.get("quest_failed")):
            return "failed"
        if _as_bool(payload.get("quest_abandoned")):
            return "abandoned"
    return ""

def _quest_completion_text(
    quest: QuestData,
    action: str,
    referee: dict[str, Any],
    event_resolution: dict[str, Any] | None,
    narration: str,
    location: str,
) -> str:
    parts: list[str] = [
        str(quest.extra.get("objective") or ""),
        str(quest.extra.get("quest_progress") or ""),
        action,
        narration,
        location,
    ]
    for payload in (referee, event_resolution or {}):
        if not isinstance(payload, dict):
            continue
        for key in ("quest_progress", "quest_update", "event", "reward", "rewards"):
            value = payload.get(key)
            if value not in (None, "", [], {}):
                if isinstance(value, (dict, list)):
                    parts.append(json.dumps(value, ensure_ascii=False, default=str))
                else:
                    parts.append(str(value))
    return "\n".join(part for part in parts if part)

def _infer_quest_finish_status(
    quest: QuestData,
    action: str,
    referee: dict[str, Any],
    event_resolution: dict[str, Any] | None,
    narration: str,
    location: str,
) -> str:
    return ""
    explicit = _quest_explicit_finish_status(referee, event_resolution)
    if explicit:
        return explicit
    if _is_quest_abandon_action(action):
        return "abandoned"

    text = _quest_completion_text(quest, action, referee, event_resolution, narration, location)
    lowered = text.lower()
    quest_text = f"{quest.name}\n{quest.overview}\n{quest.extra.get('objective') or ''}"
    quest_lowered = quest_text.lower()

    rescue_quest = any(word in quest_lowered or word in quest_text for word in ("rescue", "save", "救出", "救助", "助け", "娘", "行方不明", "連れ去"))
    rescued = any(word in lowered or word in text for word in ("rescued", "saved", "救出した", "救助した", "保護した", "無事に保護", "解放した", "拘束を解除した"))
    returned = any(word in lowered or word in text for word in ("returned", "brought back", "帰還した", "連れて帰った", "連れ帰った", "連れ帰り", "連れ戻した", "戻った"))
    reported = any(word in lowered or word in text for word in ("reported", "reported to", "quest giver", "client", "報告した", "報告を終え", "依頼主へ報告", "依頼人へ報告", "ギルドへ報告"))
    completed = any(word in lowered or word in text for word in ("quest completed", "quest complete", "cleared quest", "依頼を達成", "依頼達成", "クエスト達成", "達成した", "完了した", "完遂した", "解決した"))
    reward_claimed = any(word in lowered or word in text for word in ("reward received", "received reward", "報酬を受け取", "報酬を受領", "報酬が支払"))
    reward_seen = _quest_payload_has_reward(referee) or _quest_payload_has_reward(event_resolution)

    if reward_seen and (completed or reward_claimed):
        return "completed"
    if rescue_quest and rescued and returned and (reported or completed or reward_claimed):
        return "completed"
    if completed and (reported or reward_claimed):
        return "completed"
    return ""

def _quest_finish_status(action: str, referee: dict[str, Any], event_resolution: dict[str, Any] | None) -> str:
    return ""
    for payload in (event_resolution or {}, referee or {}):
        status = str(payload.get("quest_status") or payload.get("quest_outcome") or "").strip().lower()
        if status in {"completed", "complete", "success", "succeeded", "達成", "成功"}:
            return "completed"
        if status in {"failed", "failure", "fail", "失敗"}:
            return "failed"
        if status in {"abandoned", "withdrawn", "retreated", "cancelled", "canceled", "撤退", "放棄", "中止"}:
            return "abandoned"
        if _as_bool(payload.get("quest_completed") or payload.get("complete_quest") or payload.get("completed_quest")):
            return "completed"
        if _as_bool(payload.get("quest_failed")):
            return "failed"
        if _as_bool(payload.get("quest_abandoned")):
            return "abandoned"
    action_text = str(action or "").lower()
    if any(word in action_text for word in ("撤退", "放棄", "諦め", "やめる", "retreat", "abandon", "withdraw", "give up")):
        return "abandoned"
    return ""

def _is_quest_abandon_action(action: str) -> bool:
    text = str(action or "").lower()
    return any(word in text for word in ("撤退", "放棄", "諦め", "やめる", "retreat", "abandon", "withdraw", "give up"))

def _quest_ai_context(
    quest: QuestData,
    *,
    include_log: bool = True,
    include_extra: bool = True,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": quest.name,
        "overview": _short_text(quest.overview, 900),
        "status": quest.status,
        "quest_type": quest.extra.get("quest_type"),
        "quest_stage": quest.extra.get("quest_stage"),
        "deadline_hours": quest.extra.get("deadline_hours"),
        "neighboring_settlement": quest.neighboring_settlement,
        "choices": [str(item) for item in quest.choices[:6]],
        "reward": _compact_value(quest.extra.get("reward", {}), max_chars=600),
    }
    if include_log and quest.log:
        data["recent_log"] = _compact_value(_quest_ai_public_value(quest.log[-6:]), max_chars=1400)
    if include_extra and quest.extra:
        data["details"] = _compact_value(_quest_ai_public_value(quest.extra), max_chars=2400)
    return _drop_empty(data)

def _quest_ai_public_value(value: Any, *, key: str = "") -> Any:
    key_text = str(key or "")
    if key_text in {"uuid", "item_uuid", "item_uuids", "accepted_item_uuid"} or key_text.endswith("_uuid"):
        return None
    if isinstance(value, str):
        return _hide_internal_quest_tokens(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        result = [
            _quest_ai_public_value(item)
            for item in value
        ]
        return [item for item in result if item is not None]
    if isinstance(value, dict):
        if key_text == "objective_entities":
            return _quest_objective_entities_ai_view(value)
        result: dict[str, Any] = {}
        for child_key, child_value in value.items():
            child_key_text = str(child_key)
            if child_key_text in {"uuid", "item_uuid", "item_uuids", "accepted_item_uuid"} or child_key_text.endswith("_uuid"):
                continue
            public_value = _quest_ai_public_value(child_value, key=child_key_text)
            if public_value is not None:
                result[child_key_text] = public_value
        return result
    return _hide_internal_quest_tokens(str(value))

def _quest_objective_entities_ai_view(pack: dict[str, Any]) -> dict[str, Any]:
    def public_entries(group: str, prefix: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for index, entry in enumerate(_as_list(pack.get(group)), start=1):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").strip()
            label = str(entry.get("role_label") or entry.get("display_alias") or INTERNAL_QUEST_TOKEN_LABELS.get(role, role) or prefix)
            entries.append(
                _drop_empty(
                    {
                        "ref": f"{prefix}_{index}",
                        "name": _hide_internal_quest_tokens(entry.get("name")),
                        "display_alias": _hide_internal_quest_tokens(entry.get("display_alias") or label),
                        "role_label": _hide_internal_quest_tokens(label),
                        "role": INTERNAL_QUEST_TOKEN_LABELS.get(role, role),
                        "status": str(entry.get("status") or ""),
                        "location": str(entry.get("location") or ""),
                        "subnode_id": str(entry.get("subnode_id") or ""),
                    }
                )
            )
        return entries

    return _drop_empty(
        {
            "version": pack.get("version"),
            "quest_type": pack.get("quest_type"),
            "location": pack.get("location"),
            "subnode_id": pack.get("subnode_id"),
            "status": pack.get("status"),
            "npcs": public_entries("npcs", "objective_npc"),
            "items": public_entries("items", "objective_item"),
            "markers": public_entries("markers", "objective_marker"),
            "requirements": public_entries("requirements", "objective_requirement"),
            "flags": _quest_ai_public_value(pack.get("flags", {})),
        }
    )

def _hide_internal_quest_tokens(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?i)\s*\bUUID\s*[:=]\s*[0-9a-f-]{8,}\b", "", text)
    text = re.sub(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "対象",
        text,
    )
    text = re.sub(r"(?i)\b[0-9a-f]{24,36}\b", "対象", text)
    text = re.sub(r"(?i)\s*\bUUID\s*[:=]\s*対象\b", "", text)
    text = re.sub(r"\s*[\(（]\s*対象\s*[\)）]", "", text)
    for token, label in INTERNAL_QUEST_TOKEN_LABELS.items():
        text = re.sub(rf"\b{re.escape(token)}\b", label, text)
    return text

def _quest_from_raw(item: Any, index: int) -> QuestData:
    if isinstance(item, dict):
        data = dict(item)
        data["name"] = str(data.get("name") or data.get("quest_name") or data.get("title") or f"Quest {index + 1}")
        data["overview"] = str(data.get("overview") or data.get("description") or data.get("summary") or "")
        quest = QuestData.from_dict(data, default_name=f"Quest {index + 1}")
        known_keys = {"name", "overview", "status", "neighboring_settlement", "choices", "log", "flags", "extra"}
        if isinstance(data.get("extra"), dict):
            quest.extra.update(data.get("extra") or {})
        for key, value in data.items():
            if key not in known_keys and value not in (None, "", [], {}):
                quest.extra.setdefault(key, value)
        quest_type = _normalise_quest_type_id(
            data.get("quest_type")
            or data.get("objective_type")
            or data.get("type")
            or data.get("kind")
            or quest.extra.get("quest_type")
            or quest.extra.get("objective_type")
        )
        if not quest_type:
            quest_type = _quest_type(quest, data)
        quest.extra["quest_type"] = quest_type
        quest.extra["objective_type"] = quest_type
        return quest
    return QuestData(name=f"Quest {index + 1}", overview=str(item))
