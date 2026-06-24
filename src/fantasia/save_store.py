from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from .paths import COMMON_SAVEDATA_PATH, USER_DATA_DIR, USER_EXPORTS_DIR, USER_SAVES_DIR, USER_WORLDS_DIR
from .save_projection import (
    BOSS_INITIAL_CACHE_KEY,
    ENEMY_TEMPLATE_INITIAL_CACHE_KEY,
    NPC_INITIAL_CACHE_KEY,
    PLAYER_WORLD_STATE_KEY,
    game_state_payload_for_save,
    runtime_world_from_save,
    world_cache_for_save,
)
from .world_model import CommonSaveData, GameStateData, WorldData


WORLD_EXPORT_FORMAT = "fantasia_world_export"
WORLD_EXPORT_VERSION = 1
CURRENT_SAVE_VERSION = 3


@dataclass(frozen=True)
class SaveSlot:
    world_name: str
    player_name: str
    path: Path
    updated_at: float

    @property
    def label(self) -> str:
        updated = datetime.fromtimestamp(self.updated_at).strftime("%Y-%m-%d %H:%M:%S")
        return f"{self.world_name} / {self.player_name} ({updated})"


@dataclass(frozen=True)
class WorldSlot:
    world_name: str
    path: Path
    updated_at: float

    @property
    def label(self) -> str:
        updated = datetime.fromtimestamp(self.updated_at).strftime("%Y-%m-%d %H:%M:%S")
        return f"{self.world_name} ({updated})"


@dataclass(frozen=True)
class WorldImportResult:
    world: WorldData
    path: Path
    source: Path
    renamed_from: str = ""


class SaveStore:
    def __init__(
        self,
        data_dir: Path = USER_DATA_DIR,
        worlds_dir: Path = USER_WORLDS_DIR,
        saves_dir: Path = USER_SAVES_DIR,
        exports_dir: Path = USER_EXPORTS_DIR,
        common_path: Path = COMMON_SAVEDATA_PATH,
    ) -> None:
        self.data_dir = data_dir
        self.worlds_dir = worlds_dir
        self.saves_dir = saves_dir
        self.exports_dir = exports_dir
        self.common_path = common_path
        self.ensure_layout()

    def ensure_layout(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.worlds_dir.mkdir(parents=True, exist_ok=True)
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        if not self.common_path.exists():
            self.save_common(CommonSaveData())

    def load_common(self) -> CommonSaveData:
        if not self.common_path.exists():
            return CommonSaveData()
        data = _read_json(self.common_path)
        return CommonSaveData.from_dict(data if isinstance(data, dict) else {})

    def save_common(self, data: CommonSaveData) -> Path:
        _write_json(self.common_path, data.to_dict())
        return self.common_path

    def world_dir(self, world_name: str) -> Path:
        return self.worlds_dir / _safe_segment(world_name)

    def save_dir(self, world_name: str, player_name: str) -> Path:
        return self.saves_dir / _safe_segment(world_name) / _safe_segment(player_name)

    def save_world(self, world: WorldData) -> Path:
        world_folder = self.world_dir(world.world_name)
        (world_folder / "backgrounds").mkdir(parents=True, exist_ok=True)
        (world_folder / "characters").mkdir(parents=True, exist_ok=True)
        (world_folder / "cgs").mkdir(parents=True, exist_ok=True)
        path = world_folder / "world_data.json"
        _write_json(path, world.to_dict())
        return path

    def load_world(self, world_name: str) -> WorldData:
        path = self.world_dir(world_name) / "world_data.json"
        data = _read_json(path)
        return WorldData.from_dict(data if isinstance(data, dict) else {})

    def list_worlds(self) -> list[WorldSlot]:
        slots: list[WorldSlot] = []
        if not self.worlds_dir.exists():
            return slots
        for path in self.worlds_dir.glob("*/world_data.json"):
            world_name = path.parent.name
            try:
                data = _read_json(path)
            except Exception:
                data = {}
            if isinstance(data, dict):
                world_name = str(data.get("world_name") or world_name)
            slots.append(WorldSlot(world_name=world_name, path=path, updated_at=path.stat().st_mtime))
        slots.sort(key=lambda slot: slot.updated_at, reverse=True)
        return slots

    def export_world(
        self,
        world_name: str,
        target_path: Path | None = None,
        include_assets: bool = True,
    ) -> Path:
        world_folder = self.world_dir(world_name)
        world_path = world_folder / "world_data.json"
        if not world_path.exists():
            raise FileNotFoundError(f"World data not found: {world_path}")

        world = self.load_world(world_name)
        target = self._resolve_export_path(world.world_name, target_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.suffix.lower() == ".json":
            _write_json(target, world.to_dict())
            return target

        manifest = {
            "format": WORLD_EXPORT_FORMAT,
            "version": WORLD_EXPORT_VERSION,
            "world_name": world.world_name,
            "exported_at": _now_iso(),
            "include_assets": include_assets,
        }
        target_resolved = target.resolve()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json_bytes(manifest))
            if include_assets:
                for file_path in world_folder.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if file_path.resolve() == target_resolved:
                        continue
                    archive.write(file_path, f"world/{file_path.relative_to(world_folder).as_posix()}")
            else:
                archive.writestr(
                    "world/world_data.json",
                    _json_bytes(world.to_dict()),
                )
        return target

    def import_world(
        self,
        source_path: Path,
        overwrite: bool = False,
    ) -> WorldImportResult:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"World import source not found: {source}")

        if source.is_dir():
            world, asset_source = _load_world_from_directory(source)
            result = self._prepare_import_target(world, source, overwrite)
            _copy_world_assets_from_directory(asset_source, result.path.parent)
        elif _is_zip_path(source):
            world, world_member = _load_world_from_zip(source)
            result = self._prepare_import_target(world, source, overwrite)
            _copy_world_assets_from_zip(source, world_member, result.path.parent)
        else:
            world = _load_world_from_json_file(source)
            result = self._prepare_import_target(world, source, overwrite)

        _rebase_world_asset_paths(result.world, result.path.parent)
        self.save_world(result.world)
        return result

    def save_game(self, state: GameStateData) -> Path:
        state.version = CURRENT_SAVE_VERSION
        state.world_name = state.world_data.world_name or state.world_name
        state.world_data.world_name = state.world_name
        state.last_saved_at = _now_iso()
        self.save_world(world_cache_for_save(state))

        slot_dir = self.save_dir(state.world_name, state.player_name)
        slot_dir.mkdir(parents=True, exist_ok=True)
        path = slot_dir / "save_data.json"
        _write_json(path, game_state_payload_for_save(state))
        return path

    def load_game(self, world_name: str, player_name: str) -> GameStateData:
        path = self.save_dir(world_name, player_name) / "save_data.json"
        data = _read_json(path)
        return _game_state_from_current_save(data, path, self.load_world(world_name))

    def delete_game(self, world_name: str, player_name: str) -> None:
        slot_dir = self.save_dir(world_name, player_name)
        if not slot_dir.exists():
            return
        _remove_directory_inside(slot_dir, self.saves_dir)

    def load_latest(self) -> GameStateData:
        slots = self.list_saves()
        if not slots:
            raise FileNotFoundError(f"No Fantasia save files found in {self.saves_dir}")
        slot = slots[0]
        data = _read_json(slot.path)
        world_name = str(data.get("world_name") or slot.world_name) if isinstance(data, dict) else slot.world_name
        return _game_state_from_current_save(data, slot.path, self.load_world(world_name))

    def list_saves(self) -> list[SaveSlot]:
        slots: list[SaveSlot] = []
        if not self.saves_dir.exists():
            return slots
        for path in self.saves_dir.rglob("save_data.json"):
            world_name = path.parent.parent.name
            player_name = path.parent.name
            try:
                data = _read_json(path)
            except Exception:
                data = {}
            if isinstance(data, dict):
                world_name = str(data.get("world_name") or world_name)
                player_name = str(data.get("player_name") or player_name)
            slots.append(
                SaveSlot(
                    world_name=world_name,
                    player_name=player_name,
                    path=path,
                    updated_at=path.stat().st_mtime,
                )
            )
        slots.sort(key=lambda slot: slot.updated_at, reverse=True)
        return slots

    def save_background_asset(
        self,
        world_name: str,
        location_name: str,
        image_path: Path,
        prompts: dict[str, Any],
    ) -> Path:
        source = Path(image_path)
        if not source.exists():
            raise FileNotFoundError(f"Generated image not found: {source}")

        folder = self.world_dir(world_name) / "backgrounds" / _safe_segment(location_name)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "image.png"
        _copy_if_needed(source, target)
        _write_json(folder / "prompts.json", prompts)
        _write_generation_metadata(folder, prompts)
        return target

    def save_character_asset(
        self,
        world_name: str,
        character_name: str,
        image_path: Path,
        image_name: str,
        prompts: dict[str, Any],
    ) -> Path:
        folder = self.world_dir(world_name) / "characters" / _safe_segment(character_name)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / image_name
        _copy_if_needed(Path(image_path), target)
        _write_json(folder / "prompts.json", prompts)
        _write_generation_metadata(folder, prompts)
        return target

    def save_cg_asset(
        self,
        world_name: str,
        image_path: Path,
        prompts: dict[str, Any],
        scene_name: str = "",
    ) -> Path:
        source = Path(image_path)
        if not source.exists():
            raise FileNotFoundError(f"Generated image not found: {source}")
        existing = len(list((self.world_dir(world_name) / "cgs").glob("cg_*")))
        folder_name = f"cg_{existing + 1:04d}"
        if scene_name:
            folder_name += "_" + _safe_segment(scene_name)[:36]
        folder = self.world_dir(world_name) / "cgs" / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "image.png"
        _copy_if_needed(source, target)
        _write_json(folder / "prompts.json", prompts)
        _write_generation_metadata(folder, prompts)
        return target

    def _resolve_export_path(self, world_name: str, target_path: Path | None) -> Path:
        if target_path is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            return self.exports_dir / f"{_safe_segment(world_name)}-{stamp}.fantasia-world.zip"
        target = Path(target_path)
        if target.exists() and target.is_dir():
            return target / f"{_safe_segment(world_name)}.fantasia-world.zip"
        if target.suffix:
            return target
        return target.with_suffix(".fantasia-world.zip")

    def _prepare_import_target(
        self,
        world: WorldData,
        source: Path,
        overwrite: bool,
    ) -> WorldImportResult:
        original_name = world.world_name.strip() or source.stem or "Imported World"
        target_name = self._unique_world_name(original_name, overwrite)
        renamed_from = "" if target_name == original_name else original_name
        world.world_name = target_name
        target_folder = self.world_dir(target_name)
        if overwrite and target_folder.exists():
            _remove_directory_inside(target_folder, self.worlds_dir)
        target_folder.mkdir(parents=True, exist_ok=True)
        (target_folder / "backgrounds").mkdir(exist_ok=True)
        (target_folder / "characters").mkdir(exist_ok=True)
        (target_folder / "cgs").mkdir(exist_ok=True)
        return WorldImportResult(
            world=world,
            path=target_folder / "world_data.json",
            source=source,
            renamed_from=renamed_from,
        )

    def _unique_world_name(self, world_name: str, overwrite: bool) -> str:
        base = world_name.strip() or "Imported World"
        if overwrite or not self.world_dir(base).exists():
            return base
        suffix = 2
        while self.world_dir(f"{base} {suffix}").exists():
            suffix += 1
        return f"{base} {suffix}"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_generation_metadata(folder: Path, prompts: dict[str, Any]) -> None:
    metadata = prompts.get("generation_metadata")
    if isinstance(metadata, dict):
        _write_json(folder / "generation_metadata.json", metadata)


def _game_state_from_current_save(data: Any, path: Path, base_world: WorldData) -> GameStateData:
    if not isinstance(data, dict):
        raise ValueError(f"Invalid save data: {path}")
    version = int(data.get("version") or 0)
    if version != CURRENT_SAVE_VERSION:
        raise ValueError(
            f"Unsupported save version {version} in {path}. "
            f"Fantasia now expects save version {CURRENT_SAVE_VERSION}; start a new game or create a new save."
        )
    payload = dict(data)
    payload["world_data"] = runtime_world_from_save(base_world, payload.get(PLAYER_WORLD_STATE_KEY))
    return GameStateData.from_dict(payload)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_world_from_json_file(path: Path) -> WorldData:
    data = _read_json(path)
    return _world_from_json_payload(data if isinstance(data, dict) else {}, path)


def _load_world_from_directory(path: Path) -> tuple[WorldData, Path]:
    if (path / "world_data.json").is_file():
        world_path = path / "world_data.json"
        asset_source = path
    elif (path / "world" / "world_data.json").is_file():
        world_path = path / "world" / "world_data.json"
        asset_source = path / "world"
    else:
        raise FileNotFoundError(f"world_data.json not found in directory: {path}")
    return _load_world_from_json_file(world_path), asset_source


def _load_world_from_zip(path: Path) -> tuple[WorldData, str]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        world_member = "world/world_data.json" if "world/world_data.json" in names else ""
        if not world_member and "world_data.json" in names:
            world_member = "world_data.json"
        if not world_member:
            matches = [name for name in names if name.endswith("/world_data.json")]
            if matches:
                world_member = sorted(matches, key=len)[0]
        if not world_member:
            raise FileNotFoundError(f"world_data.json not found in export package: {path}")
        with archive.open(world_member) as handle:
            data = json.loads(handle.read().decode("utf-8"))
    return _world_from_json_payload(data if isinstance(data, dict) else {}, path), world_member


def _world_from_json_payload(data: dict[str, Any], source: Path) -> WorldData:
    world = WorldData.from_dict(data)
    if not world.world_name or world.world_name == "unknown":
        world.world_name = source.parent.name if source.name == "world_data.json" else source.stem
    return world


def _copy_world_assets_from_directory(source: Path, target: Path) -> None:
    for item_name in ("backgrounds", "characters", "cgs"):
        source_item = source / item_name
        if not source_item.exists():
            continue
        target_item = target / item_name
        if source_item.resolve() == target_item.resolve():
            continue
        if target_item.exists():
            shutil.rmtree(target_item)
        if source_item.is_dir():
            shutil.copytree(source_item, target_item)
        elif source_item.is_file():
            _copy_if_needed(source_item, target_item)


def _copy_world_assets_from_zip(path: Path, world_member: str, target: Path) -> None:
    world_prefix = _zip_world_prefix(world_member)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            rel = _zip_world_relative_path(info.filename, world_prefix)
            if rel is None or rel.as_posix() == "world_data.json":
                continue
            if rel.parts[0] not in {"backgrounds", "characters", "cgs"}:
                continue
            target_path = _safe_join(target, rel.parts)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source_handle, target_path.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)


def _zip_world_prefix(world_member: str) -> tuple[str, ...]:
    parts = PurePosixPath(world_member).parts
    if len(parts) <= 1:
        return ()
    return parts[:-1]


def _zip_world_relative_path(filename: str, world_prefix: tuple[str, ...]) -> PurePosixPath | None:
    parts = PurePosixPath(filename).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe path in world export package: {filename}")
    if world_prefix:
        if tuple(parts[: len(world_prefix)]) != world_prefix:
            return None
        parts = parts[len(world_prefix) :]
    elif parts[0] == "manifest.json":
        return None
    if not parts:
        return None
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe path in world export package: {filename}")
    return PurePosixPath(*parts)


def _safe_join(root: Path, parts: tuple[str, ...]) -> Path:
    target = root.joinpath(*parts)
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
        raise ValueError(f"Unsafe path escapes target directory: {target}")
    return target


def _remove_directory_inside(path: Path, root: Path) -> None:
    path_resolved = path.resolve()
    root_resolved = root.resolve()
    if path_resolved == root_resolved or root_resolved not in path_resolved.parents:
        raise ValueError(f"Refusing to remove path outside worlds directory: {path}")
    shutil.rmtree(path)


def _rebase_world_asset_paths(world: WorldData, world_folder: Path) -> None:
    for location in world.locations.values():
        image_path = world_folder / "backgrounds" / _safe_segment(location.name) / "image.png"
        if image_path.is_file():
            location.image_path = str(image_path)
        facilities = location.extra.get("facilities")
        if not isinstance(facilities, list):
            facilities = []
        for facility in facilities:
            if not isinstance(facility, dict):
                continue
            facility_name = str(facility.get("name") or "").strip()
            if not facility_name:
                continue
            facility_path = world_folder / "backgrounds" / _safe_segment(f"{location.name}__facility__{facility_name}") / "image.png"
            if facility_path.is_file():
                facility["image_path"] = str(facility_path)
        graph = location.extra.get("subnode_graph")
        nodes = graph.get("nodes") if isinstance(graph, dict) else None
        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                subnode_path = world_folder / "backgrounds" / _safe_segment(f"{location.name}__subnode__{node_id}") / "image.png"
                if subnode_path.is_file():
                    node["image_path"] = str(subnode_path)

    for character in world.characters.values():
        folder = world_folder / "characters" / _safe_segment(character.name)
        _rebase_image_map(character.image_paths, folder)
    _rebase_cached_character_asset_paths(world, world_folder)


def _rebase_cached_character_asset_paths(world: WorldData, world_folder: Path) -> None:
    for cache_key in (NPC_INITIAL_CACHE_KEY, BOSS_INITIAL_CACHE_KEY, ENEMY_TEMPLATE_INITIAL_CACHE_KEY):
        cache = world.extra.get(cache_key)
        if not isinstance(cache, dict):
            continue
        for payload in cache.values():
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name") or "").strip()
            image_paths = payload.get("image_paths")
            if not name or not isinstance(image_paths, dict):
                continue
            folder = world_folder / "characters" / _safe_segment(name)
            _rebase_image_map(image_paths, folder)

def _rebase_image_map(image_paths: dict[str, str], folder: Path) -> None:
    for key, value in list(image_paths.items()):
        filename = Path(value).name if value else _default_asset_filename(key)
        if not filename:
            continue
        target = folder / filename
        if target.is_file():
            image_paths[key] = str(target)


def _default_asset_filename(key: str) -> str:
    defaults = {
        "generated_image": "generated_image.png",
        "base_image": "base_image.png",
        "no_bg_image": "no_bg_image.png",
        "face_image": "face_image.png",
        "add_border_image": "add_border_image.png",
        "image": "image.png",
    }
    return defaults.get(key, "")


def _is_zip_path(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".zip") or name.endswith(".fantasia-world")


def _copy_if_needed(source: Path, target: Path) -> None:
    if source.resolve() == target.resolve():
        return
    shutil.copy2(source, target)


def _safe_segment(value: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in str(value).strip())
    return cleaned or "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
