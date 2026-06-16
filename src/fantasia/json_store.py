from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import OUTPUT_DIR


def _safe_segment(value: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in value.strip())
    return cleaned or "unknown"


class JsonStore:
    def __init__(self, output_dir: Path = OUTPUT_DIR) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_llm_exchange(
        self,
        world_name: str,
        player_name: str,
        manager_name: str,
        messages: list[dict[str, str]],
        response: Any,
    ) -> Path:
        folder = (
            self.output_dir
            / _safe_segment(world_name)
            / _safe_segment(player_name)
            / _safe_segment(manager_name)
        )
        folder.mkdir(parents=True, exist_ok=True)
        next_id = 1
        existing = [path for path in folder.glob("*.json") if path.stem.isdigit()]
        if existing:
            next_id = max(int(path.stem) for path in existing) + 1

        path = folder / f"{next_id}.json"
        payload = {"messages": messages, "response": response}
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path
