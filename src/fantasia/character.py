from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any
from uuid import uuid4


@dataclass
class Character:
    uuid: str = field(default_factory=lambda: uuid4().hex)
    name: str = "unknown"
    role: str = ""
    category: str = ""
    location: str = ""
    state: str = "present"
    level: int = 1
    exp: int = 0
    current_hp: int = 0
    max_hp: int = 0
    current_sp: int = 0
    max_sp: int = 0
    hunger: int = 50
    max_hunger: int = 50
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
    equipment: dict[str, dict[str, Any]] = field(default_factory=dict)
    gold: int = 0
    image_paths: dict[str, str] = field(default_factory=dict)
    prompts: dict[str, Any] = field(default_factory=dict)
    flags: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], default_name: str = "unknown") -> "Character":
        kwargs = _known_kwargs(cls, data if isinstance(data, dict) else {})
        kwargs["uuid"] = str(kwargs.get("uuid") or uuid4().hex)
        kwargs["name"] = str(kwargs.get("name") or default_name)
        kwargs["level"] = max(1, _as_int(kwargs.get("level"), 1))
        kwargs["exp"] = max(0, _as_int(kwargs.get("exp"), 0))
        kwargs["current_hp"] = max(0, _as_int(kwargs.get("current_hp"), 0))
        kwargs["max_hp"] = max(0, _as_int(kwargs.get("max_hp"), 0))
        kwargs["current_sp"] = max(0, _as_int(kwargs.get("current_sp"), 0))
        kwargs["max_sp"] = max(0, _as_int(kwargs.get("max_sp"), 0))
        kwargs["hunger"] = max(0, _as_int(kwargs.get("hunger"), 50))
        kwargs["max_hunger"] = max(1, _as_int(kwargs.get("max_hunger"), 50))
        kwargs["attack"] = max(0, _as_int(kwargs.get("attack"), 0))
        kwargs["defense"] = max(0, _as_int(kwargs.get("defense"), 0))
        kwargs["attributes"] = _int_dict(kwargs.get("attributes"))
        kwargs["image_generation_prompt"] = _as_list(kwargs.get("image_generation_prompt"))
        kwargs["traits"] = _as_list(kwargs.get("traits"))
        kwargs["skills"] = _as_list(kwargs.get("skills"))
        kwargs["status_effects"] = _as_list(kwargs.get("status_effects"))
        kwargs["inventory"] = _as_list(kwargs.get("inventory"))
        kwargs["equipment"] = _as_dict(kwargs.get("equipment"))
        kwargs["image_paths"] = _as_dict(kwargs.get("image_paths"))
        kwargs["prompts"] = _as_dict(kwargs.get("prompts"))
        kwargs["flags"] = _as_dict(kwargs.get("flags"))
        kwargs["extra"] = _as_dict(kwargs.get("extra"))
        kwargs["gold"] = max(0, _as_int(kwargs.get("gold"), 0))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)

    @property
    def is_player(self) -> bool:
        return bool(self.flags.get("is_player") or self.category == "player" or self.role == "Player")


def dataclass_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: dataclass_to_dict(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): dataclass_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    return value


def _known_kwargs(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {item.name for item in fields(cls)}
    return {key: value for key, value in data.items() if key in allowed}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        result[str(key)] = _as_int(item)
    return result
