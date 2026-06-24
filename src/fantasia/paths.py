from __future__ import annotations

import sys
import os
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def app_root() -> Path:
    override = _env_path("FANTASIA_APP_ROOT")
    if override:
        return override

    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "config.json").exists():
        return exe_dir

    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        if (candidate / "config.json").exists():
            return candidate

    if getattr(sys, "frozen", False):
        return exe_dir
    return module_path.parents[2]


def portable_root() -> Path:
    override = _env_path("FANTASIA_PORTABLE_ROOT")
    if override:
        return override
    return ROOT


ROOT = app_root()
PORTABLE_ROOT = portable_root()
CONFIG_PATH = ROOT / "config.json"
RUNTIME_DIR = ROOT / "runtime"
MODEL_DIR = PORTABLE_ROOT / "model"
MODEL_TEXT_DIR = MODEL_DIR / "text"
MODEL_GRAPHIC_DIR = MODEL_DIR / "graphic"
DATA_DIR = PORTABLE_ROOT / "Data"
TEMPLATE_DIR = DATA_DIR / "Template"
ITEM_TEMPLATE_DIR = TEMPLATE_DIR / "Item"
NPC_TEMPLATE_DIR = TEMPLATE_DIR / "NPC"
SKILL_TEMPLATE_DIR = TEMPLATE_DIR / "Skill"
NAMELIST_TEMPLATE_DIR = DATA_DIR / "NameList"
NAMELIST_TEMPLATE_PATH = NAMELIST_TEMPLATE_DIR / "namelist.json"
LOCATION_WORLD_TEMPLATE_DIR = DATA_DIR / "Location_World"
LOCATION_LOCAL_TEMPLATE_DIR = DATA_DIR / "Location_Local"
LOOT_TABEL_TEMPLATE_DIR = DATA_DIR / "LootTabel"
GENERATED_DIR = RUNTIME_DIR / "generated"
BIN_DIR = ROOT / "bin"
ASSETS_DIR = ROOT / "assets"
LOG_DIR = _env_path("FANTASIA_LOG_ROOT") or (PORTABLE_ROOT / "log")
CRASHLOG_DIR = _env_path("FANTASIA_CRASHLOG_ROOT") or (PORTABLE_ROOT / "crashlog")
OUTPUT_DIR = LOG_DIR / "llm"


def user_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "BlueEggplant" / "Fantasia"
    return ROOT / "user_data"


USER_DATA_DIR = user_data_root()
USER_WORLDS_DIR = USER_DATA_DIR / "worlds"
USER_SAVES_DIR = USER_DATA_DIR / "saves"
USER_EXPORTS_DIR = USER_DATA_DIR / "exports"
USER_LOGS_DIR = LOG_DIR
COMMON_SAVEDATA_PATH = USER_DATA_DIR / "common_savedata.json"


def resolve_model_path(value: object, kind: str | None = None) -> Path:
    raw = str(value or "").strip()
    if not raw:
        return MODEL_TEXT_DIR if (kind or "").strip().lower() == "text" else MODEL_GRAPHIC_DIR if (kind or "").strip().lower() == "graphic" else MODEL_DIR

    path = Path(raw)
    if path.is_absolute():
        return path

    normal = path.as_posix().replace("\\", "/").strip()
    kind_lower = (kind or "").strip().lower()
    if normal.startswith("model/"):
        return PORTABLE_ROOT / normal
    if normal.startswith("publish/model/"):
        candidate = ROOT / normal
        if candidate.exists():
            return candidate
        return ROOT.parent / normal
    if normal.startswith("text/"):
        return MODEL_TEXT_DIR / normal[len("text/") :]
    if normal.startswith("graphic/"):
        return MODEL_GRAPHIC_DIR / normal[len("graphic/") :]

    if normal.startswith("runtime/models/llama_cpp/"):
        return MODEL_TEXT_DIR / normal[len("runtime/models/llama_cpp/") :]
    if normal.startswith("runtime/models/sdxl/"):
        return MODEL_GRAPHIC_DIR / normal[len("runtime/models/sdxl/") :]

    suffix = path.suffix.lower()
    if suffix == ".gguf" and kind_lower != "graphic":
        return MODEL_TEXT_DIR / normal
    if suffix in {".safetensors", ".ckpt", ".pt", ".bin"} and kind_lower != "text":
        return MODEL_GRAPHIC_DIR / normal

    if kind_lower == "text":
        return MODEL_TEXT_DIR / normal
    if kind_lower == "graphic":
        return MODEL_GRAPHIC_DIR / normal
    return MODEL_DIR / normal
