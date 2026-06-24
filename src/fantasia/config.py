from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import CONFIG_PATH


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]

    @property
    def llm_backend(self) -> str:
        return self.raw["ai_setting"]["local_model_setting"].get("llm_backend", "llama_cpp_completion_cuda")

    @property
    def image_backend_name(self) -> str:
        return self.raw["ai_setting"]["local_model_setting"].get("image_backend", {}).get("name", "mock_sdxl")

    @property
    def local_llm(self) -> dict[str, Any]:
        return self.raw["ai_setting"]["local_model_setting"].get("local_llm", {})

    @property
    def llm_context_size(self) -> int:
        local_llm = self.local_llm
        for key in ("context_size", "ctx_size", "n_ctx"):
            if local_llm.get(key) is None:
                continue
            try:
                return max(1024, int(local_llm[key]))
            except (TypeError, ValueError):
                continue
        return 16384

    @property
    def cloud_llm(self) -> dict[str, Any]:
        return self.raw["ai_setting"]["local_model_setting"].get("cloud_llm", {})

    @property
    def image_backend(self) -> dict[str, Any]:
        return self.raw["ai_setting"]["local_model_setting"].get("image_backend", {})

    @property
    def sdxl(self) -> dict[str, Any]:
        return self.raw["ai_setting"]["local_model_setting"].get("sdxl", {})

    @property
    def server_parameters(self) -> dict[str, str]:
        return self.raw["ai_setting"].get("server_parameters", {})

    @property
    def environment_setting(self) -> dict[str, str]:
        return self.raw["ai_setting"].get("environment_setting", {})

    @property
    def completion_parameters(self) -> dict[str, Any]:
        return self.raw["ai_setting"].get("completion_parameters", {})

    @property
    def prompt_template_path(self) -> str:
        return str(self.raw["ai_setting"].get("prompt_template_path", "assets/prompt_templates"))

    @property
    def ui_setting(self) -> dict[str, Any]:
        return self.raw.get("ui_setting", {})

    @property
    def window_size(self) -> tuple[int, int]:
        size = self.ui_setting.get("window_size", {})
        return int(size.get("width", 1152)), int(size.get("height", 768))

    @property
    def font_path(self) -> str:
        return str(self.ui_setting.get("font_path", "assets/fonts/JF-Dot-MPlus10.ttf"))

    @property
    def font_family(self) -> str:
        return str(self.ui_setting.get("font_family", "")).strip()

    @property
    def font_size(self) -> int:
        return int(self.ui_setting.get("font_size", 14))

    @property
    def language(self) -> str:
        language = str(self.ui_setting.get("language", "ja")).strip().lower()
        if language in {"en", "english"}:
            return "en"
        return "ja"

    @property
    def allow_any_action_concept(self) -> bool:
        return bool(self.ui_setting.get("allow_any_action_concept", False))

    @property
    def reveal_world_map_on_generation(self) -> bool:
        return bool(self.ui_setting.get("reveal_world_map_on_generation", False))

    @property
    def debug_free_location_travel(self) -> bool:
        return bool(self.ui_setting.get("debug_free_location_travel", False))

    @property
    def debug_disable_movement_time_passage(self) -> bool:
        return bool(self.ui_setting.get("debug_disable_movement_time_passage", False))

    @property
    def debug_disable_dungeon_random_encounters(self) -> bool:
        return bool(self.ui_setting.get("debug_disable_dungeon_random_encounters", False))


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    with path.open("r", encoding="utf-8") as handle:
        return AppConfig(json.load(handle))
