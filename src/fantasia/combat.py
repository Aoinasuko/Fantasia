from __future__ import annotations

import json
from typing import Any


def _short_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


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
            if key_text.startswith("_") or key_text.startswith("raw_"):
                continue
            result[key_text] = _compact_value(
                item,
                max_chars=max(160, max_chars // 2),
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
        return {key: item for key, item in result.items() if item not in ("", None, [], {})}
    return _short_text(str(value), max_chars)


def _combat_action_text(*responses: Any) -> str:
    parts: list[str] = []
    for response in responses:
        if not isinstance(response, dict):
            continue
        for key in ("npc_action", "action", "intent", "narration", "text", "message"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=400)
            if value:
                parts.append(str(value))
        update = response.get("encounter_update")
        if isinstance(update, (dict, list)):
            parts.append(json.dumps(_compact_value(update, max_chars=500), ensure_ascii=False))
    return " ".join(parts)


def _response_implies_capture_relocation(response: dict[str, Any]) -> bool:
    if not isinstance(response, dict):
        return False
    text = _combat_action_text(response).casefold()
    if not text:
        return False
    capture_terms = (
        "capture",
        "captured",
        "captivity",
        "kidnap",
        "abduct",
        "carried away",
        "dragged away",
        "taken away",
        "nest",
        "lair",
        "den",
        "base",
        "hideout",
        "post_capture",
        "broodmother",
        "連れ去",
        "連行",
        "攫",
        "さらわ",
        "捕獲",
        "拘束",
        "巣",
        "巣穴",
        "拠点",
        "根城",
        "苗床",
    )
    if not any(term.casefold() in text for term in capture_terms):
        return False
    movement_terms = (
        "moved",
        "relocated",
        "transported",
        "dragged",
        "carried",
        "taken",
        "連れ",
        "運ば",
        "引きず",
        "移動",
        "連行",
        "運搬",
    )
    status_terms = (
        "post_capture",
        "captivity",
        "captured_to",
        "broodmother",
        "nest",
        "lair",
        "base",
        "hideout",
        "巣",
        "巣穴",
        "拠点",
        "根城",
        "苗床",
    )
    return any(term.casefold() in text for term in movement_terms) or any(term.casefold() in text for term in status_terms)


def _capture_subnode_name(response: dict[str, Any], opponent_name: str = "") -> str:
    text = _combat_action_text(response)
    lowered = text.casefold()
    base = str(opponent_name or "").strip()
    if "巣" in text or "nest" in lowered or "den" in lowered:
        return _short_text(f"{base}の巣" if base else "敵の巣", 48)
    if "拠点" in text or "base" in lowered or "hideout" in lowered or "lair" in lowered:
        return _short_text(f"{base}の拠点" if base else "敵の拠点", 48)
    return _short_text(f"{base}の捕獲場所" if base else "捕獲場所", 48)


def _capture_subnode_description(response: dict[str, Any], opponent_name: str = "") -> str:
    narration = str(response.get("narration") or response.get("text") or response.get("message") or "").strip()
    if narration:
        return _short_text(narration, 180)
    base = str(opponent_name or "敵").strip()
    return f"{base}に連れ込まれた場所。出口までの道を探す必要がある。"
