from __future__ import annotations

import re
from typing import Any

from .quest_rules import (
    INTERNAL_QUEST_TOKEN_LABELS,
    _as_list,
    _drop_empty,
    _short_text,
)
from .world_model import QuestData


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

