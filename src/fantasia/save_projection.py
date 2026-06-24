from __future__ import annotations

from copy import deepcopy
from typing import Any

from .character import Character
from .world_generation import SUBNODE_GRAPH_KEY
from .world_model import GameStateData, LocationData, QuestData, WorldData


PLAYER_WORLD_STATE_KEY = "player_world_state"
PLAYER_WORLD_STATE_VERSION = 1
WORLD_CACHE_VERSION = 2

WORLD_GRAPH_KEY = "location_graph"
INITIAL_SUBNODE_LOOT_KEY = "initial_subnode_loot"
CURRENT_SUBNODE_LOOT_KEY = "subnode_loot"

PLAYER_WORLD_EXTRA_KEYS = {
    "active_encounter",
    "bone_file_drop_events",
    "bone_file_spawn_events",
    "bone_file_spawned_ids",
    "completed_quest_events",
    "craft_events",
    "crime_events",
    "current_subnodes",
    "dead_npcs",
    "encounters",
    "exp_events",
    "field_event_quests",
    "npc_affinity_events",
    "npc_capture_events",
    "npc_memory_events",
    "npc_movement_events",
    "player_home_construction",
    "player_home_events",
    "player_homes",
    "quest_board_generation",
    "quest_finish_events",
    "quest_objective_events",
    "quest_progress_events",
    "trade_events",
    "vendor_inventory_events",
    "visited_locations",
}

WORLD_CACHE_EXTRA_DROP_KEYS = PLAYER_WORLD_EXTRA_KEYS | {
    "active_facility",
    "last_active_facility",
}

LOCATION_PLAYER_EXTRA_KEYS = {
    "inventory",
    "subnode_loot",
}

LOCATION_WORLD_EXTRA_DROP_KEYS = {
    "inventory",
    "subnode_loot",
}

LOCATION_DYNAMIC_FLAG_KEYS = {
    "discovered",
    "inventory_seeded",
    "visited",
}

SUBNODE_WORLD_DYNAMIC_KEYS = {
    "discovered",
    "revealed",
    "visited",
}

SUBNODE_PLAYER_TEMP_KEYS = {
    "player_home",
    "quest_temporary_objective",
    "temporary",
}

CHARACTER_DYNAMIC_EXTRA_KEYS = {
    "affinity",
    "current_hp",
    "current_sp",
    "description_updates",
    "exp",
    "experience",
    "memory_updates",
    "next_exp",
    "player_memories",
    "previous_description",
    "relationship_changes",
    "trust",
}

CHARACTER_DYNAMIC_FLAG_KEYS = {
    "alive",
    "current_location",
    "state",
}


def world_cache_for_save(state: GameStateData) -> WorldData:
    world = WorldData.from_dict(state.world_data.to_dict())
    world.version = WORLD_CACHE_VERSION
    world.quests = []
    world.locations = {
        name: _location_cache_for_save(location)
        for name, location in world.locations.items()
    }
    world.extra = _world_extra_cache_for_save(world.extra)
    world.characters = {}

    npc_cache: dict[str, dict[str, Any]] = {}
    boss_cache: dict[str, dict[str, Any]] = {}
    enemy_template_cache = deepcopy(world.extra.get("enemy_template_initial_cache") or {})
    if not isinstance(enemy_template_cache, dict):
        enemy_template_cache = {}

    for character in state.world_data.characters.values():
        cached = _character_cache_for_save(character)
        if cached is None:
            continue
        payload = cached.to_dict()
        if _is_boss_character(cached):
            world.characters[str(cached.uuid)] = cached
            boss_cache[str(cached.uuid)] = payload
        elif _is_enemy_character(cached):
            template_id = _character_template_id(cached)
            if template_id:
                enemy_template_cache.setdefault(template_id, payload)
        else:
            world.characters[str(cached.uuid)] = cached
            npc_cache[str(cached.uuid)] = payload

    if npc_cache:
        world.extra["npc_initial_cache"] = npc_cache
    if boss_cache:
        world.extra["boss_initial_cache"] = boss_cache
    if enemy_template_cache:
        world.extra["enemy_template_initial_cache"] = enemy_template_cache
    return world


def game_state_payload_for_save(state: GameStateData) -> dict[str, Any]:
    payload = state.to_dict()
    payload.pop("world_data", None)
    payload.pop("inventory", None)
    extra = payload.get("extra")
    if isinstance(extra, dict):
        extra.pop(PLAYER_WORLD_STATE_KEY, None)
        extra.pop("equipment", None)
    payload[PLAYER_WORLD_STATE_KEY] = player_world_state_for_save(state)
    return payload


def player_world_state_for_save(state: GameStateData) -> dict[str, Any]:
    world = state.world_data
    return {
        "version": PLAYER_WORLD_STATE_VERSION,
        "world_name": world.world_name,
        "characters": {
            str(character.uuid): character.to_dict()
            for character in world.characters.values()
        },
        "quests": [quest.to_dict() for quest in world.quests],
        "locations": {
            name: _location_player_state_for_save(location)
            for name, location in world.locations.items()
        },
        "world_extra": _player_world_extra_for_save(world.extra),
    }


def runtime_world_from_save(base_world: WorldData, player_world_state: Any) -> WorldData:
    world = WorldData.from_dict(base_world.to_dict())
    _install_initial_loot(world)
    player_state = player_world_state if isinstance(player_world_state, dict) else {}

    world.extra.update(_dict(player_state.get("world_extra")))
    for name, location_state in _dict(player_state.get("locations")).items():
        location = world.locations.get(str(name))
        if location is None:
            location = LocationData(name=str(name))
            world.locations[location.name] = location
        _apply_location_player_state(location, location_state)

    characters = _dict(player_state.get("characters"))
    if characters:
        world.characters = {}
        for key, raw in characters.items():
            if isinstance(raw, dict):
                character = Character.from_dict(raw, str(key))
                world.characters[str(character.uuid)] = character
    else:
        world.characters = {
            str(character.uuid): Character.from_dict(character.to_dict(), character.name)
            for character in world.characters.values()
        }

    quests = player_state.get("quests")
    if isinstance(quests, list):
        world.quests = [
            QuestData.from_dict(item, f"Quest {index + 1}")
            for index, item in enumerate(quests)
            if isinstance(item, dict)
        ]
    else:
        world.quests = []
    _sync_world_graph_visibility_from_locations(world)
    return world


def _location_cache_for_save(location: LocationData) -> LocationData:
    cached = LocationData.from_dict(location.to_dict(), location.name)
    cached.flags = {
        key: deepcopy(value)
        for key, value in cached.flags.items()
        if key not in LOCATION_DYNAMIC_FLAG_KEYS
    }
    extra = {
        key: deepcopy(value)
        for key, value in cached.extra.items()
        if key not in LOCATION_WORLD_EXTRA_DROP_KEYS
    }
    graph = extra.get(SUBNODE_GRAPH_KEY)
    if isinstance(graph, dict):
        extra[SUBNODE_GRAPH_KEY] = _subnode_graph_cache_for_save(graph)
    initial_loot = cached.extra.get(INITIAL_SUBNODE_LOOT_KEY)
    if isinstance(initial_loot, dict):
        extra[INITIAL_SUBNODE_LOOT_KEY] = deepcopy(initial_loot)
        extra[CURRENT_SUBNODE_LOOT_KEY] = deepcopy(initial_loot)
    cached.extra = extra
    return cached


def _location_player_state_for_save(location: LocationData) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key in LOCATION_PLAYER_EXTRA_KEYS:
        if key in location.extra:
            extra[key] = deepcopy(location.extra.get(key))
    graph = location.extra.get(SUBNODE_GRAPH_KEY)
    if isinstance(graph, dict):
        extra[SUBNODE_GRAPH_KEY] = deepcopy(graph)
    return {
        "flags": deepcopy(location.flags),
        "extra": extra,
    }


def _apply_location_player_state(location: LocationData, raw: Any) -> None:
    state = raw if isinstance(raw, dict) else {}
    flags = state.get("flags")
    if isinstance(flags, dict):
        location.flags.update(deepcopy(flags))
    extra = state.get("extra")
    if isinstance(extra, dict):
        location.extra.update(deepcopy(extra))


def _world_extra_cache_for_save(extra: dict[str, Any]) -> dict[str, Any]:
    cached = {
        key: deepcopy(value)
        for key, value in _dict(extra).items()
        if key not in WORLD_CACHE_EXTRA_DROP_KEYS
    }
    graph = cached.get(WORLD_GRAPH_KEY)
    if isinstance(graph, dict):
        cached[WORLD_GRAPH_KEY] = _world_location_graph_cache_for_save(graph)
    return cached


def _player_world_extra_for_save(extra: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in PLAYER_WORLD_EXTRA_KEYS:
        if key in extra:
            result[key] = deepcopy(extra.get(key))
    return result


def _world_location_graph_cache_for_save(graph: dict[str, Any]) -> dict[str, Any]:
    cached = deepcopy(graph)
    nodes = cached.get("nodes")
    if isinstance(nodes, dict):
        for node in nodes.values():
            if isinstance(node, dict):
                node.pop("visited", None)
                node.pop("discovered", None)
    return cached


def _sync_world_graph_visibility_from_locations(world: WorldData) -> None:
    graph = world.extra.get(WORLD_GRAPH_KEY)
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, dict):
        return
    visited_locations = set()
    raw_visited = world.extra.get("visited_locations")
    if isinstance(raw_visited, list):
        visited_locations = {str(item) for item in raw_visited if str(item).strip()}
    for name, location in world.locations.items():
        node = nodes.get(name)
        if not isinstance(node, dict):
            continue
        if location.flags.get("visited") or name in visited_locations:
            node["visited"] = True
            node["discovered"] = True
        elif location.flags.get("discovered"):
            node["discovered"] = True


def _subnode_graph_cache_for_save(graph: dict[str, Any]) -> dict[str, Any]:
    cached = deepcopy(graph)
    cached.pop("current", None)
    nodes = cached.get("nodes")
    if not isinstance(nodes, dict):
        return cached
    remove_ids: set[str] = set()
    for node_id, node in list(nodes.items()):
        if not isinstance(node, dict):
            continue
        if any(node.get(key) for key in SUBNODE_PLAYER_TEMP_KEYS):
            remove_ids.add(str(node_id))
            continue
        for key in SUBNODE_WORLD_DYNAMIC_KEYS:
            node.pop(key, None)
    for node_id in remove_ids:
        nodes.pop(node_id, None)
    edges = cached.get("edges")
    if isinstance(edges, list) and remove_ids:
        cached["edges"] = [
            edge
            for edge in edges
            if not (
                isinstance(edge, dict)
                and (str(edge.get("from") or "") in remove_ids or str(edge.get("to") or "") in remove_ids)
            )
        ]
    return cached


def _install_initial_loot(world: WorldData) -> None:
    for location in world.locations.values():
        initial = location.extra.get(INITIAL_SUBNODE_LOOT_KEY)
        if isinstance(initial, dict) and CURRENT_SUBNODE_LOOT_KEY not in location.extra:
            location.extra[CURRENT_SUBNODE_LOOT_KEY] = deepcopy(initial)


def _character_cache_for_save(character: Character) -> Character | None:
    if character.flags.get("is_player") or character.is_player:
        return None
    if _is_quest_objective_character(character) and not _is_boss_character(character):
        return None
    cached = Character.from_dict(character.to_dict(), character.name)
    cached.location = _initial_character_location(cached)
    cached.state = "present"
    _apply_level_one_cache(cached)
    cached.status_effects = []
    cached.inventory = []
    cached.equipment = {}
    cached.vender_inventory = []
    cached.gold = 0
    for key in CHARACTER_DYNAMIC_EXTRA_KEYS:
        cached.extra.pop(key, None)
    for key in CHARACTER_DYNAMIC_FLAG_KEYS:
        cached.flags.pop(key, None)
    cached.extra["cached_initial_state"] = True
    cached.extra["cached_initial_level"] = 1
    cached.flags["cached_initial_state"] = True
    return cached


def _apply_level_one_cache(character: Character) -> None:
    level_one = character.extra.get("level_one_cache") if isinstance(character.extra, dict) else None
    if isinstance(level_one, dict):
        character.level = 1
        character.exp = 0
        character.attributes = _int_dict(level_one.get("attributes")) or character.attributes
        character.max_hp = max(1, _int(level_one.get("max_hp"), character.max_hp or 1))
        character.current_hp = max(1, min(character.max_hp, _int(level_one.get("current_hp"), character.max_hp)))
        character.max_sp = max(1, _int(level_one.get("max_sp"), character.max_sp or 1))
        character.current_sp = max(1, min(character.max_sp, _int(level_one.get("current_sp"), character.max_sp)))
        character.attack = max(0, _int(level_one.get("attack"), character.attack))
        character.defense = max(0, _int(level_one.get("defense"), character.defense))
    else:
        character.level = 1
        character.exp = 0
        attrs = _character_attributes(character)
        character.attributes = attrs
        character.max_hp = _calculated_max_hp(attrs, 1)
        character.current_hp = character.max_hp
        character.max_sp = _calculated_max_sp(attrs, 1, character.max_hp)
        character.current_sp = character.max_sp
        character.attack = max(1, 1 + attrs["str"] // 3 + attrs["dex"] // 5)
        character.defense = max(0, attrs["con"] // 4 + attrs["wis"] // 6)
    character.extra["level"] = 1
    character.extra["exp"] = 0
    character.extra["experience"] = 0
    character.extra["current_hp"] = character.current_hp
    character.extra["max_hp"] = character.max_hp
    character.extra["current_sp"] = character.current_sp
    character.extra["max_sp"] = character.max_sp
    character.extra["attack"] = character.attack
    character.extra["defense"] = character.defense
    character.extra["attributes"] = dict(character.attributes)


def _initial_character_location(character: Character) -> str:
    for source in (character.extra, character.flags):
        if not isinstance(source, dict):
            continue
        for key in ("origin_location", "home_location", "spawn_location", "first_seen_location"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return str(character.location or "").strip()


def _is_quest_objective_character(character: Character) -> bool:
    return bool(
        character.category == "quest_objective"
        or character.flags.get("quest_objective")
        or character.extra.get("quest_objective")
    )


def _is_boss_character(character: Character) -> bool:
    return bool(
        character.flags.get("generated_dungeon_boss")
        or character.flags.get("boss_npc")
        or character.extra.get("generated_dungeon_boss")
        or character.extra.get("boss_npc")
    )


def _is_enemy_character(character: Character) -> bool:
    return bool(
        character.category in {"enemy_npc", "wild_encounter", "hostile", "monster"}
        or character.flags.get("enemy_npc")
        or character.flags.get("hostile")
        or character.extra.get("enemy_npc")
        or character.extra.get("hostile")
    )


def _character_template_id(character: Character) -> str:
    return str(
        character.extra.get("npc_template_id")
        or character.flags.get("npc_template_id")
        or character.extra.get("template_id")
        or character.flags.get("template_id")
        or ""
    ).strip()


def _character_attributes(character: Character) -> dict[str, int]:
    attrs: dict[str, Any] = {}
    if isinstance(character.attributes, dict):
        attrs.update(character.attributes)
    extra_attrs = character.extra.get("attributes") if isinstance(character.extra, dict) else None
    if isinstance(extra_attrs, dict):
        attrs.update(extra_attrs)
    ability = character.extra.get("ability") if isinstance(character.extra, dict) else None
    if isinstance(ability, dict) and isinstance(ability.get("attributes"), dict):
        attrs.update(ability["attributes"])
    resolved = {
        "str": max(1, _int(attrs.get("str"), 10)),
        "dex": max(1, _int(attrs.get("dex"), 10)),
        "con": max(1, _int(attrs.get("con"), 10)),
        "int": max(1, _int(attrs.get("int"), 10)),
        "wis": max(1, _int(attrs.get("wis"), 10)),
        "cha": max(1, _int(attrs.get("cha"), 10)),
    }
    resolved["magic"] = max(1, _int(attrs.get("magic", attrs.get("mag", resolved["int"])), resolved["int"]))
    resolved["will"] = max(1, _int(attrs.get("will", resolved["wis"]), resolved["wis"]))
    return resolved


def _calculated_max_hp(attrs: dict[str, int], level: int) -> int:
    return max(10, 8 + level * 3 + attrs["con"] * 2 + attrs["str"] // 2 + attrs["will"] // 3)


def _calculated_max_sp(attrs: dict[str, int], level: int, max_hp: int) -> int:
    return max(6, int(max_hp * 0.45) + attrs["magic"] + attrs["will"] + level * 2)


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(item, 0) for key, item in value.items()}


def _int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
