from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4


T = TypeVar("T")


@dataclass
class CommonSaveData:
    talent_point: int = 12

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommonSaveData":
        return cls(talent_point=int(data.get("talent_point", 12)))

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass
class LocationData:
    name: str = "unknown"
    description: str = ""
    area: str = ""
    image_path: str = ""
    prompts: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_name: str = "unknown") -> "LocationData":
        kwargs = _known_kwargs(cls, data)
        kwargs["name"] = str(kwargs.get("name") or default_name)
        kwargs["prompts"] = _as_dict(kwargs.get("prompts"))
        kwargs["flags"] = _as_dict(kwargs.get("flags"))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass
class CharacterData:
    uuid: str = field(default_factory=lambda: uuid4().hex)
    name: str = "unknown"
    role: str = ""
    category: str = ""
    location: str = ""
    state: str = "present"
    level: int = 1
    current_hp: int = 0
    max_hp: int = 0
    current_sp: int = 0
    max_sp: int = 0
    attack: int = 0
    defense: int = 0
    attributes: dict[str, int] = field(default_factory=dict)
    gender: str = ""
    age: str = ""
    backstory: str = ""
    personality: str = ""
    look: str = ""
    image_generation_prompt: list[str] = field(default_factory=list)
    traits: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    status_effects: list[dict[str, Any]] = field(default_factory=list)
    inventory: list[dict[str, Any]] = field(default_factory=list)
    gold: int = 0
    image_paths: dict[str, str] = field(default_factory=dict)
    prompts: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_name: str = "unknown") -> "CharacterData":
        kwargs = _known_kwargs(cls, data)
        kwargs["uuid"] = str(kwargs.get("uuid") or uuid4().hex)
        kwargs["name"] = str(kwargs.get("name") or default_name)
        kwargs["level"] = max(1, _as_int(kwargs.get("level"), 1))
        kwargs["current_hp"] = max(0, _as_int(kwargs.get("current_hp"), 0))
        kwargs["max_hp"] = max(0, _as_int(kwargs.get("max_hp"), 0))
        kwargs["current_sp"] = max(0, _as_int(kwargs.get("current_sp"), 0))
        kwargs["max_sp"] = max(0, _as_int(kwargs.get("max_sp"), 0))
        kwargs["attack"] = max(0, _as_int(kwargs.get("attack"), 0))
        kwargs["defense"] = max(0, _as_int(kwargs.get("defense"), 0))
        kwargs["attributes"] = _int_dict(kwargs.get("attributes"))
        kwargs["image_generation_prompt"] = _as_list(kwargs.get("image_generation_prompt"))
        kwargs["traits"] = _as_list(kwargs.get("traits"))
        kwargs["skills"] = _as_list(kwargs.get("skills"))
        kwargs["status_effects"] = _as_list(kwargs.get("status_effects"))
        kwargs["inventory"] = _as_list(kwargs.get("inventory"))
        kwargs["image_paths"] = _as_dict(kwargs.get("image_paths"))
        kwargs["prompts"] = _as_dict(kwargs.get("prompts"))
        kwargs["flags"] = _as_dict(kwargs.get("flags"))
        kwargs["extra"] = _as_dict(kwargs.get("extra"))
        kwargs["gold"] = int(kwargs.get("gold") or 0)
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass
class QuestData:
    name: str = "unknown"
    overview: str = ""
    status: str = "available"
    neighboring_settlement: str = ""
    choices: list[str] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_name: str = "unknown") -> "QuestData":
        kwargs = _known_kwargs(cls, data)
        kwargs["name"] = str(kwargs.get("name") or default_name)
        kwargs["choices"] = [str(item) for item in _as_list(kwargs.get("choices"))]
        kwargs["log"] = _as_list(kwargs.get("log"))
        kwargs["flags"] = _as_dict(kwargs.get("flags"))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass
class WorldData:
    version: int = 1
    world_name: str = "unknown"
    overview: str = ""
    structure_description: str = ""
    structure: Any = field(default_factory=dict)
    current_rumor: str = ""
    world_situation: str = ""
    flow: Any = field(default_factory=list)
    starting_location: str = "unknown"
    locations: dict[str, LocationData] = field(default_factory=dict)
    characters: dict[str, CharacterData] = field(default_factory=dict)
    quests: list[QuestData] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_overview(cls, response: dict[str, Any]) -> "WorldData":
        world_name = str(response.get("world_name") or "unknown")
        structure = response.get("structure", {})
        starting_location = str(
            response.get("starting_location")
            or _guess_starting_location(structure)
            or "unknown"
        )
        opening = str(response.get("opening") or response.get("overview") or "")
        quests = [
            QuestData.from_dict(item, default_name=f"Quest {index + 1}")
            for index, item in enumerate(_as_list(response.get("story_quests")))
            if isinstance(item, dict)
        ]
        locations: dict[str, LocationData] = {}
        if starting_location and starting_location != "unknown":
            locations[starting_location] = LocationData(
                name=starting_location,
                description=opening,
                area="starting",
            )

        return cls(
            world_name=world_name,
            overview=str(response.get("overview") or opening),
            structure_description=str(response.get("structure_description") or ""),
            structure=structure,
            current_rumor=str(response.get("current_rumor") or ""),
            world_situation=str(response.get("world_situation") or ""),
            flow=response.get("flow", []),
            starting_location=starting_location,
            locations=locations,
            quests=quests,
            extra={"raw_create_world_overview": response},
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorldData":
        data = {key: value for key, value in data.items() if key != "monsters"}
        kwargs = _known_kwargs(cls, data)
        kwargs["locations"] = _location_map(kwargs.get("locations"))
        kwargs["characters"] = _character_map(kwargs.get("characters"))
        kwargs["quests"] = _quest_list(kwargs.get("quests"))
        kwargs["flags"] = _as_dict(kwargs.get("flags"))
        kwargs["history"] = _as_list(kwargs.get("history"))
        return cls(**kwargs)

    def ensure_location(self, name: str, description: str = "") -> LocationData:
        key = name or "unknown"
        if key not in self.locations:
            self.locations[key] = LocationData(name=key, description=description)
        elif description and not self.locations[key].description:
            self.locations[key].description = description
        return self.locations[key]

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass
class GameStateData:
    version: int = 2
    world_name: str = "unknown"
    player_name: str = "Player"
    current_area: str = ""
    current_location: str = "unknown"
    day: int = 1
    gold: int = 0
    party: list[dict[str, Any]] = field(default_factory=list)
    inventory: list[dict[str, Any]] = field(default_factory=list)
    status_effects: list[dict[str, Any]] = field(default_factory=list)
    active_quest: str = ""
    completed_quests: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    narration_log: list[dict[str, Any]] = field(default_factory=list)
    action_log: list[dict[str, Any]] = field(default_factory=list)
    display_log: list[str] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    last_image_path: str = ""
    last_saved_at: str = ""
    world_data: WorldData = field(default_factory=WorldData)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new_game(
        cls,
        player_name: str,
        world_data: WorldData,
        opening: str,
        choices: list[str] | None = None,
    ) -> "GameStateData":
        display_log = [f"世界: {world_data.world_name}"]
        if opening:
            display_log.append(opening)
        return cls(
            world_name=world_data.world_name,
            player_name=player_name,
            current_location=world_data.starting_location,
            choices=choices or [],
            display_log=display_log,
            narration_log=[
                {
                    "type": "opening",
                    "location": world_data.starting_location,
                    "text": opening,
                    "choices": choices or [],
                }
            ],
            world_data=world_data,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameStateData":
        kwargs = _known_kwargs(cls, data)
        world_raw = kwargs.get("world_data") or {}
        kwargs["world_data"] = (
            world_raw
            if isinstance(world_raw, WorldData)
            else WorldData.from_dict(world_raw if isinstance(world_raw, dict) else {})
        )
        kwargs["party"] = _as_list(kwargs.get("party"))
        kwargs["inventory"] = _as_list(kwargs.get("inventory"))
        kwargs["status_effects"] = _as_list(kwargs.get("status_effects"))
        kwargs["completed_quests"] = [str(item) for item in _as_list(kwargs.get("completed_quests"))]
        kwargs["choices"] = [str(item) for item in _as_list(kwargs.get("choices"))]
        kwargs["narration_log"] = _as_list(kwargs.get("narration_log"))
        kwargs["action_log"] = _as_list(kwargs.get("action_log"))
        kwargs["display_log"] = [str(item) for item in _as_list(kwargs.get("display_log"))]
        kwargs["flags"] = _as_dict(kwargs.get("flags"))
        kwargs["gold"] = int(kwargs.get("gold") or 0)
        kwargs["day"] = int(kwargs.get("day") or 1)
        return cls(**kwargs)

    def append_turn(
        self,
        action: str,
        narration: str,
        location: str,
        choices: list[str],
        input_type: str = "free_action",
    ) -> None:
        self.action_log.append({"action": action, "location": location, "input_type": input_type})
        self.narration_log.append(
            {
                "type": "turn",
                "action": action,
                "input_type": input_type,
                "location": location,
                "text": narration,
                "choices": choices,
            }
        )
        marker = "> [選択肢]" if input_type == "choice" else ">"
        self.display_log.append(f"{marker} {action}")
        self.display_log.append(narration)
        self.current_location = location
        self.choices = choices
        self.world_data.ensure_location(location)

    def log_text(self, max_lines: int | None = None) -> str:
        lines = self.display_log[-max_lines:] if max_lines else self.display_log
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


def dataclass_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: dataclass_to_dict(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): dataclass_to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _known_kwargs(cls: type[T], data: dict[str, Any]) -> dict[str, Any]:
    known = {item.name for item in fields(cls)}
    kwargs = {key: value for key, value in data.items() if key in known and key != "extra"}
    if "extra" in known:
        extra: dict[str, Any] = {}
        existing_extra = data.get("extra")
        if isinstance(existing_extra, dict):
            extra.update(existing_extra)
        extra.update({key: value for key, value in data.items() if key not in known})
        kwargs["extra"] = extra
    return kwargs


def _location_map(value: Any) -> dict[str, LocationData]:
    if isinstance(value, dict):
        return {
            str(key): item if isinstance(item, LocationData) else LocationData.from_dict(item, str(key))
            for key, item in value.items()
            if isinstance(item, (dict, LocationData))
        }
    if isinstance(value, list):
        result: dict[str, LocationData] = {}
        for index, item in enumerate(value):
            if isinstance(item, dict):
                location = LocationData.from_dict(item, f"Location {index + 1}")
                result[location.name] = location
        return result
    return {}


def _character_map(value: Any) -> dict[str, CharacterData]:
    if isinstance(value, dict):
        return {
            str(key): item if isinstance(item, CharacterData) else CharacterData.from_dict(item, str(key))
            for key, item in value.items()
            if isinstance(item, (dict, CharacterData))
        }
    if isinstance(value, list):
        result: dict[str, CharacterData] = {}
        for index, item in enumerate(value):
            if isinstance(item, dict):
                character = CharacterData.from_dict(item, f"Character {index + 1}")
                result[character.name] = character
        return result
    return {}


def _quest_list(value: Any) -> list[QuestData]:
    return [
        item if isinstance(item, QuestData) else QuestData.from_dict(item, f"Quest {index + 1}")
        for index, item in enumerate(_as_list(value))
        if isinstance(item, (dict, QuestData))
    ]


def _guess_starting_location(structure: Any) -> str:
    if isinstance(structure, dict):
        for key in ("starting_location", "location", "name", "settlement_name"):
            if structure.get(key):
                return str(structure[key])
        settlements = structure.get("settlements") or structure.get("towns") or structure.get("locations")
        if isinstance(settlements, list) and settlements:
            first = settlements[0]
            if isinstance(first, dict):
                for key in ("name", "settlement_name", "location"):
                    if first.get(key):
                        return str(first[key])
            return str(first)
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _as_int(item, 0) for key, item in value.items()}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
