from __future__ import annotations

import json
import random
import re
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .item_generate_loottabel import generate_loot_table_items
from .namelist import claim_name_from_namelist
from .paths import LOCATION_LOCAL_TEMPLATE_DIR, LOCATION_WORLD_TEMPLATE_DIR, ROOT
from .world_generation import (
    DEFAULT_SUBNODE_ID,
    DUNGEON_DEEPEST_SUBNODE_ID,
    DUNGEON_ENTRY_SUBNODE_ID,
    DUNGEON_SUBNODE_LAYOUT_VERSION,
    SUBNODE_GRAPH_KEY,
    WORLD_FINAL_DANGER_MAX,
    WORLD_FINAL_DANGER_MIN,
    WORLD_MAP_EDGE_HOURS,
    _clamp_world_danger,
    _dungeon_subnode_target_count,
    _ensure_dungeon_graph_connected,
)
from .world_model import LocationData, WorldData

if TYPE_CHECKING:
    from .game import GameEngine


TEMPLATE_WORLD_GENERATION_VERSION = 1
LOCATION_TEMPLATE_CATEGORY_IDS = {"settlement", "highway", "dungeon"}
SETTLEMENT_MANDATORY_TEMPLATE_IDS = (
    "settlement_guild",
    "settlement_townhall",
    "settlement_inn",
    "settlement_blacksmith",
)
SETTLEMENT_EXCLUDED_RANDOM_IDS = {
    "settlement_town_entrance",
    "settlement_village_entrance",
    "settlement_square",
}
FACILITY_TYPE_BY_TEMPLATE_ID = {
    "settlement_guild": "guild",
    "settlement_townhall": "town_hall",
    "settlement_inn": "inn",
    "settlement_blacksmith": "blacksmith",
    "settlement_apothecary": "apothecary",
    "settlement_general_store": "general_store",
    "settlement_food_store": "food_store",
    "settlement_black_market": "black_market",
    "settlement_material_store": "material_store",
    "settlement_magic_store": "magic_store",
    "settlement_junk_store": "junk_store",
    "settlement_church": "temple",
    "settlement_chief_house": "town_hall",
}
FACILITY_DISPLAY_LABEL_BY_TYPE = {
    "guild": "冒険者ギルド",
    "town_hall": "役場",
    "inn": "宿屋",
    "blacksmith": "鍛冶屋",
    "apothecary": "薬品店",
    "general_store": "雑貨店",
    "food_store": "食料品店",
    "black_market": "闇商店",
    "material_store": "素材店",
    "magic_store": "魔法品店",
    "junk_store": "ジャンク店",
    "temple": "教会",
}
FACILITY_NPC_NAMED_TYPES = {
    "inn",
    "blacksmith",
    "apothecary",
    "general_store",
    "food_store",
    "black_market",
    "material_store",
    "magic_store",
    "junk_store",
}
FACILITY_SETTLEMENT_NAMED_TYPES = {"guild", "town_hall", "temple"}
ROUTE_SLOTS = (
    {"category": "settlement", "type": "town", "role": "starting_settlement"},
    {"category": "highway", "type": "highway", "role": "route"},
    {"category": "highway", "type": "highway", "role": "route"},
    {"category": "settlement", "type": "village", "role": "settlement"},
    {"category": "highway", "type": "highway", "role": "route"},
    {"category": "highway", "type": "highway", "role": "route"},
    {"category": "settlement", "type": "town", "role": "settlement"},
    {"category": "highway", "type": "highway", "role": "route"},
    {"category": "highway", "type": "highway", "role": "route"},
    {"category": "dungeon", "type": "", "role": "final_destination"},
)


def generate_template_world(
    engine: GameEngine,
    world: WorldData,
    *,
    player_name: str,
    premise: str,
    theme: dict[str, Any],
    customization: dict[str, str],
    progress_callback: Any = None,
    progress_start: int = 18,
    progress_end: int = 48,
) -> None:
    generator = TemplateWorldGenerator(
        engine,
        world,
        player_name=player_name,
        premise=premise,
        theme=theme,
        customization=customization,
        progress_callback=progress_callback,
        progress_start=progress_start,
        progress_end=progress_end,
    )
    generator.generate()


def install_template_dungeon_subnode_graph(
    engine: GameEngine,
    location: LocationData,
    rng: random.Random | None = None,
    *,
    source: str = "template_dungeon_generation",
) -> bool:
    generator = TemplateWorldGenerator.for_dungeon_install(engine)
    return generator.install_dungeon_subnode_graph(location, rng or random.Random(location.name), source=source)


def refresh_template_subnode_loot(
    engine: GameEngine,
    location: LocationData,
    subnode_id: str,
    node: dict[str, Any],
    slot: dict[str, Any],
) -> bool:
    table = _as_list(node.get("item_tabel") or node.get("item_table"))
    has_template_rule = any(
        key in node
        for key in (
            "item_generate",
            "item_regenerate",
            "item_tabel",
            "item_table",
            "template_item_generate",
            "template_item_regenerate",
        )
    )
    if not has_template_rule:
        return False
    day = _safe_int(getattr(engine.state, "day", 1), 1)
    regenerate = _as_bool(node.get("item_regenerate") or node.get("template_item_regenerate"))
    seeded_day = _safe_int(slot.get("seeded_day"), 0)
    if slot.get("seeded") and not (regenerate and seeded_day != day):
        return True
    slot["inventory"] = []
    if _as_bool(node.get("item_generate") if "item_generate" in node else node.get("template_item_generate")) and table:
        slot["inventory"].extend(
            generate_loot_table_items(
                table,
                context=f"{location.name}:{subnode_id}",
                danger_level=_location_danger(location),
                seed=f"template-loot|{location.name}|{subnode_id}|day:{day}",
                source="template_loot",
            )
        )
    slot["seeded"] = True
    slot["seeded_day"] = day
    slot["item_regenerate"] = regenerate
    slot["source"] = "location_local_template"
    return True


class TemplateWorldGenerator:
    def __init__(
        self,
        engine: GameEngine,
        world: WorldData | None = None,
        *,
        player_name: str = "world_builder",
        premise: str = "",
        theme: dict[str, Any] | None = None,
        customization: dict[str, str] | None = None,
        progress_callback: Any = None,
        progress_start: int = 18,
        progress_end: int = 48,
    ) -> None:
        self.engine = engine
        self.world = world or getattr(engine.state, "world_data", WorldData())
        self.player_name = player_name
        self.premise = premise
        self.theme = theme or {}
        self.customization = customization or {}
        self.progress_callback = progress_callback
        self.progress_start = progress_start
        self.progress_end = progress_end
        self.world_templates = _load_world_templates()
        self.local_templates = _load_local_templates()
        self.rng = random.Random(f"template-world|{self.world.world_name}|{premise}")

    @classmethod
    def for_dungeon_install(cls, engine: GameEngine) -> "TemplateWorldGenerator":
        return cls(engine, getattr(engine.state, "world_data", WorldData()))

    def generate(self) -> None:
        self._emit("location_templates", "ロケーションテンプレートを選択中", self.progress_start)
        specs = self._build_main_route()
        self._emit("location_templates", "ロケーション名と説明を生成中", self._progress(0.45))
        self._describe_template_slots(specs)
        self._emit("location_templates", "ワールド接続を構築中", self._progress(0.82))
        self._connect_route_specs(specs)
        self.engine._set_starting_settlement_gate(self.world)
        self.world.extra["world_generation_mode"] = "template_route"
        self.world.extra["template_world_generation_version"] = TEMPLATE_WORLD_GENERATION_VERSION
        self._emit("location_templates", "テンプレートワールド生成完了", self.progress_end)

    def install_dungeon_subnode_graph(
        self,
        location: LocationData,
        rng: random.Random,
        *,
        source: str = "template_dungeon_generation",
    ) -> bool:
        dungeon_type = str(
            location.extra.get("main_node_subtype")
            or location.extra.get("dungeon_subtype")
            or location.extra.get("quest_dungeon_subtype")
            or "dungeon"
        ).strip()
        if dungeon_type in {"", "dungeon", "final_destination"}:
            dungeon_type = self._choose_dungeon_type(self.premise, rng)
            location.extra["main_node_subtype"] = dungeon_type
            location.extra["dungeon_subtype"] = dungeon_type
        templates = self._local_templates_for_target(dungeon_type, categories=("dungeon", "common"))
        if not templates:
            requested_type = dungeon_type
            dungeon_type = self._choose_dungeon_type(
                " ".join(
                    str(part or "")
                    for part in (
                        requested_type,
                        location.name,
                        location.description,
                    )
                ),
                rng,
            )
            location.extra["main_node_subtype"] = dungeon_type
            location.extra["dungeon_subtype"] = dungeon_type
            location.extra["template_dungeon_subtype"] = dungeon_type
            if requested_type and requested_type != dungeon_type:
                location.extra["requested_dungeon_subtype"] = requested_type
            templates = self._local_templates_for_target(dungeon_type, categories=("dungeon", "common"))
        if not templates and dungeon_type != "ruin":
            requested_type = str(location.extra.get("requested_dungeon_subtype") or dungeon_type)
            dungeon_type = "ruin"
            location.extra["main_node_subtype"] = dungeon_type
            location.extra["dungeon_subtype"] = dungeon_type
            location.extra["template_dungeon_subtype"] = dungeon_type
            if requested_type and requested_type != dungeon_type:
                location.extra["requested_dungeon_subtype"] = requested_type
            templates = self._local_templates_for_target(dungeon_type, categories=("dungeon", "common"))
        if not templates:
            return False
        graph = self._build_dungeon_graph(location, dungeon_type, templates, rng, source=source)
        location.extra[SUBNODE_GRAPH_KEY] = graph
        self._seed_template_subnode_loot(location, graph, source=source)
        if hasattr(self.engine, "_seed_dungeon_deepest_loot"):
            self.engine._seed_dungeon_deepest_loot(location, graph, source=source)
        return True

    def _build_main_route(self) -> list[dict[str, Any]]:
        self.world.locations = {}
        specs: list[dict[str, Any]] = []
        graph = {
            "edge_hours": WORLD_MAP_EDGE_HOURS,
            "target_count": len(ROUTE_SLOTS),
            "generation_mode": "template_route",
            "template_world_generation_version": TEMPLATE_WORLD_GENERATION_VERSION,
            "nodes": {},
            "edges": [],
        }
        self.world.extra["location_graph"] = graph
        self.world.extra["local_world_skeleton"] = {
            "version": TEMPLATE_WORLD_GENERATION_VERSION,
            "generation_mode": "template_route",
            "locations": specs,
            "final_destination_concept": str(self.theme.get("final_destination_concept") or ""),
        }

        for index, route_slot in enumerate(ROUTE_SLOTS):
            slot_id = f"loc_{index:03d}"
            category = str(route_slot["category"])
            role = str(route_slot["role"])
            requested_type = str(route_slot.get("type") or "")
            template_type = requested_type
            if category == "dungeon":
                template_type = self._choose_dungeon_type(
                    " ".join(
                        str(part or "")
                        for part in (
                            self.premise,
                            self.theme.get("final_destination_concept"),
                            self.theme.get("overview"),
                        )
                    ),
                    self.rng,
                )
            template = self._choose_world_template(category, template_type, self.rng)
            template_type = str(template.get("type") or template_type or category)
            danger = self.engine._local_world_danger_for_distance(index, self.rng, seed=f"{self.world.world_name}:{slot_id}")
            if role == "starting_settlement":
                danger = 0
            if role == "final_destination":
                danger = max(danger, self.rng.randint(WORLD_FINAL_DANGER_MIN, WORLD_FINAL_DANGER_MAX))
            location_name = self._unique_location_name(str(template.get("name") or self._fallback_template_name(category, template_type, index)))
            location = self.world.ensure_location(location_name, str(template.get("desc") or ""))
            grid_x, grid_y = index, 0
            location.area = f"route:{index}"
            location.extra.update(
                {
                    "slot_id": slot_id,
                    "main_node_type": category,
                    "main_node_subtype": template_type,
                    "role": role,
                    "location_kind": self._location_kind(category, template_type),
                    "danger_level": _clamp_world_danger(danger),
                    "danger_source": "template_route",
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "grid_distance": index,
                    "world_template": deepcopy(template),
                    "world_template_name": str(template.get("name") or ""),
                    "world_template_desc": str(template.get("desc") or ""),
                    "world_generation_payload": {
                        "slot_id": slot_id,
                        "role": role,
                        "category": category,
                        "subtype": template_type,
                        "danger": _clamp_world_danger(danger),
                        "template": deepcopy(template),
                    },
                }
            )
            location.flags["discovered"] = index == 0
            if category == "settlement":
                location.flags["settlement"] = True
                self._install_settlement_templates(location, template_type, self.rng)
            elif category == "dungeon":
                location.flags["dungeon"] = True
                location.flags["dangerous"] = True
                location.flags["final_destination"] = role == "final_destination"
                location.extra["final_destination"] = role == "final_destination"
                location.extra["boss_required"] = role == "final_destination"
                self.install_dungeon_subnode_graph(location, self.rng, source="template_world_generation")
            else:
                self._install_highway_template(location, template_type, self.rng)
            self.engine._set_location_graph_node(
                self.world,
                location.name,
                kind=self._location_kind(category, template_type),
                danger=_clamp_world_danger(danger),
                location=location,
            )
            if role == "starting_settlement":
                self.world.starting_location = location.name
            specs.append(
                {
                    "slot_id": slot_id,
                    "name": location.name,
                    "category": category,
                    "type": template_type,
                    "kind": self._location_kind(category, template_type),
                    "role": role,
                    "danger": _clamp_world_danger(danger),
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "grid_distance": index,
                    "world_template": deepcopy(template),
                }
            )
        return specs

    def _install_settlement_templates(self, location: LocationData, settlement_type: str, rng: random.Random) -> None:
        location.extra["location_kind"] = "settlement"
        location.extra["main_node_subtype"] = settlement_type
        templates = self._local_templates_for_target(settlement_type, categories=("settlement",))
        entrance = self._choose_entrance_template(templates, settlement_type)
        if entrance:
            location.extra["settlement_entrance_template"] = deepcopy(entrance)
        target_min, target_max = (4, 6) if settlement_type == "village" else (6, 9)
        target_count = rng.randint(target_min, target_max)
        by_id = {str(item.get("id") or ""): item for item in templates if isinstance(item, dict)}
        selected: list[dict[str, Any]] = []
        for template_id in SETTLEMENT_MANDATORY_TEMPLATE_IDS:
            template = by_id.get(template_id)
            if template and self._target_matches(template, settlement_type):
                selected.append(template)
        candidates = [
            item
            for item in templates
            if str(item.get("id") or "") not in SETTLEMENT_EXCLUDED_RANDOM_IDS
            and str(item.get("id") or "") not in {str(selected_item.get("id") or "") for selected_item in selected}
            and self._template_is_settlement_facility(item)
        ]
        rng.shuffle(candidates)
        selected.extend(candidates[: max(0, target_count - len(selected))])
        selected = selected[:target_count]
        facilities = [self._facility_from_template(location, template) for template in selected]
        location.extra["facilities"] = facilities
        location.extra["facility_template_count"] = len(facilities)
        location.extra["location_local_templates"] = [deepcopy(item) for item in selected]
        location.flags["settlement"] = True

    def _install_highway_template(self, location: LocationData, highway_type: str, rng: random.Random) -> None:
        templates = self._local_templates_for_target(highway_type, categories=("highway", "common"))
        template = self._choose_entrance_template(templates, highway_type) or (templates[0] if templates else {})
        graph = {
            "version": 1,
            "nodes": {},
            "edges": [],
            "movement": "adjacent",
            "generated_by": "location_local_template",
            "template_world_generation_version": TEMPLATE_WORLD_GENERATION_VERSION,
            "current": DEFAULT_SUBNODE_ID,
        }
        self.engine._upsert_subnode_node(
            graph,
            DEFAULT_SUBNODE_ID,
            str(template.get("name") or location.name),
            str(template.get("desc") or location.description),
            highway_type or "road",
            120,
            160,
            world_map_exit=True,
            **self._node_template_payload(template),
        )
        location.extra[SUBNODE_GRAPH_KEY] = graph
        self._seed_template_subnode_loot(location, graph, source="template_highway_generation")

    def _build_dungeon_graph(
        self,
        location: LocationData,
        dungeon_type: str,
        templates: list[dict[str, Any]],
        rng: random.Random,
        *,
        source: str,
    ) -> dict[str, Any]:
        target_count = max(5, min(10, _dungeon_subnode_target_count(location)))
        entrance_template = self._choose_entrance_template(templates, dungeon_type) or {}
        deepest_candidates = [item for item in templates if _as_bool(item.get("innermost_part")) and self._target_matches(item, dungeon_type)]
        deepest_template = rng.choice(deepest_candidates) if deepest_candidates else {}
        interior_candidates = [
            item
            for item in templates
            if not _as_bool(item.get("entrance"))
            and not _as_bool(item.get("innermost_part"))
            and self._target_matches(item, dungeon_type)
            and _as_bool(item.get("random_generate", True))
        ]
        rng.shuffle(interior_candidates)
        interior_target = max(3, target_count - 2)
        selected_interiors = interior_candidates[:interior_target]
        nodes: list[tuple[str, dict[str, Any], str, int, int]] = []
        nodes.append((DUNGEON_ENTRY_SUBNODE_ID, entrance_template, "entrance", 80, 240))
        x_step = max(130, min(180, 820 // max(4, len(selected_interiors) + 2)))
        for index, template in enumerate(selected_interiors):
            base_id = str(template.get("id") or f"room_{index + 1:02d}")
            node_id = base_id if not any(existing[0] == base_id for existing in nodes) else f"{base_id}_{index + 1:02d}"
            y = 220 + (index % 2) * 56
            nodes.append((node_id, template, str(template.get("id") or "room"), 220 + index * x_step, y))
        nodes.append((DUNGEON_DEEPEST_SUBNODE_ID, deepest_template, "deepest", 220 + (len(selected_interiors) + 1) * x_step, 240))
        graph: dict[str, Any] = {
            "version": 1,
            "nodes": {},
            "edges": [],
            "movement": "adjacent",
            "dungeon_layout_version": DUNGEON_SUBNODE_LAYOUT_VERSION,
            "dungeon_target_count": len(nodes),
            "generated_by": source,
            "template_world_generation_version": TEMPLATE_WORLD_GENERATION_VERSION,
            "dungeon_type": dungeon_type,
            "current": DUNGEON_ENTRY_SUBNODE_ID,
        }
        for node_id, template, kind, x, y in nodes:
            payload = self._node_template_payload(template)
            if node_id == DUNGEON_ENTRY_SUBNODE_ID:
                payload["world_map_exit"] = True
            if node_id == DUNGEON_DEEPEST_SUBNODE_ID:
                payload["world_map_exit"] = False
                payload["generate_boss"] = bool(
                    payload.get("generate_boss")
                    or location.extra.get("boss_required")
                    or location.extra.get("final_destination")
                )
            self.engine._upsert_subnode_node(
                graph,
                node_id,
                str(template.get("name") or ("入口" if node_id == DUNGEON_ENTRY_SUBNODE_ID else "最奥部" if node_id == DUNGEON_DEEPEST_SUBNODE_ID else node_id)),
                str(template.get("desc") or ""),
                kind,
                x,
                y,
                **payload,
            )
        ordered_ids = [node_id for node_id, *_ in nodes]
        for a, b in zip(ordered_ids, ordered_ids[1:]):
            self.engine._connect_subnodes(graph, a, b)
        for index, node_id in enumerate(ordered_ids[2:-1], start=2):
            if index % 2 == 0:
                self.engine._connect_subnodes(graph, DUNGEON_ENTRY_SUBNODE_ID, node_id, kind="branch")
        graph["external_subnode_candidates"] = [
            node_id
            for node_id in (DUNGEON_ENTRY_SUBNODE_ID, ordered_ids[2] if len(ordered_ids) > 4 else "")
            if node_id
        ]
        _ensure_dungeon_graph_connected(graph)
        return graph

    def _seed_template_subnode_loot(self, location: LocationData, graph: dict[str, Any], *, source: str) -> None:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        loot_store = location.extra.setdefault("subnode_loot", {})
        if not isinstance(loot_store, dict):
            loot_store = {}
            location.extra["subnode_loot"] = loot_store
        day = _safe_int(getattr(self.engine.state, "day", 1), 1)
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            slot = loot_store.setdefault(str(node_id), {})
            if not isinstance(slot, dict):
                slot = {}
                loot_store[str(node_id)] = slot
            table = _as_list(node.get("item_tabel") or node.get("item_table"))
            item_generate = _as_bool(node.get("item_generate") if "item_generate" in node else node.get("template_item_generate"))
            slot["inventory"] = []
            if item_generate and table:
                slot["inventory"].extend(
                    generate_loot_table_items(
                        table,
                        context=f"{location.name}:{node_id}",
                        danger_level=_location_danger(location),
                        seed=f"{source}|{location.name}|{node_id}",
                        source=source,
                    )
                )
            slot["seeded"] = True
            slot["seeded_day"] = day
            slot["source"] = "location_local_template"
            slot["item_regenerate"] = _as_bool(node.get("item_regenerate") or node.get("template_item_regenerate"))

    def _describe_template_slots(self, specs: list[dict[str, Any]]) -> None:
        slots = self._description_slots(specs)
        if not slots:
            return
        prompt = {
            "world": {
                "world_name": self.world.world_name,
                "overview": _short_text(self.world.overview, 900),
                "structure_description": _short_text(self.world.structure_description, 700),
                "final_destination_concept": str(self.theme.get("final_destination_concept") or ""),
            },
            "premise": _short_text(self.premise, 1600),
            "existing_names": [],
            "slots": slots,
            "rules": [
                "Return names and descriptions only for the supplied slot_id values.",
                "Do not change category, type, role, danger, graph, item tables, enemy rates, NPC template candidates, or shop tables.",
                "Use Japanese names and Japanese in-world descriptions.",
                "Avoid internal words such as slot_id, category, target_type, danger rule, template, placeholder, unnamed, or initial point.",
                "For facility slots, describe the facility only. Do not copy the facility description into NPC appearance or personality.",
                "For facility slots, parent_location_name is the settlement name and npc_name is the fixed keeper name.",
                "For facility shop slots, include npc_name in the facility name, such as '<npc_name>の鍛冶屋'.",
                "For guild, town hall, church, or similar public facility slots, include parent_location_name in the facility name.",
                "For the final_destination location, use the final_destination_concept and make it a concrete final dungeon name.",
            ],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You name and describe template-selected Fantasia locations and local subnodes. "
                    "The game has already decided every structure and mechanic. Return compact JSON only."
                ),
            },
            {"role": "user", "content": _ai_json(prompt)},
        ]
        try:
            response = self.engine._chat_json(
                "template_world_location_describer",
                messages,
                max_tokens=max(1800, min(5200, 600 + len(slots) * 115)),
                world_name=self.world.world_name,
                player_name=self.player_name,
                retries=1,
            )
        except Exception as exc:
            self.world.extra.setdefault("template_world_description_errors", []).append({"error": str(exc)})
            self._apply_facility_owner_names(specs)
            return
        self._apply_description_response(specs, response)
        self._apply_facility_owner_names(specs)
        self.world.history.append({"manager": "template_world_location_describer", "response": _strip_response_metadata(response)})

    def _description_slots(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        for spec in specs:
            location = self.world.locations.get(str(spec.get("name") or ""))
            if not location:
                continue
            template = spec.get("world_template") if isinstance(spec.get("world_template"), dict) else {}
            slots.append(
                {
                    "slot_id": spec["slot_id"],
                    "target": "location",
                    "category": spec.get("category"),
                    "type": spec.get("type"),
                    "role": spec.get("role"),
                    "danger": spec.get("danger"),
                    "template_name": template.get("name"),
                    "template_desc": template.get("desc"),
                }
            )
            if spec.get("category") == "settlement":
                for facility in _as_list(location.extra.get("facilities")):
                    if not isinstance(facility, dict):
                        continue
                    slots.append(
                        {
                            "slot_id": f"{spec['slot_id']}:facility:{facility.get('template_id') or facility.get('id') or facility.get('name')}",
                            "target": "facility",
                            "parent_slot_id": spec["slot_id"],
                            "parent_location_name": location.name,
                            "facility_type": facility.get("type"),
                            "template_id": facility.get("template_id"),
                            "template_name": facility.get("template_name") or facility.get("name"),
                            "template_desc": facility.get("template_desc") or facility.get("description"),
                            "npc_name": facility.get("npc_name"),
                            "npc_role": facility.get("npc_role"),
                        }
                    )
            graph = location.extra.get(SUBNODE_GRAPH_KEY)
            nodes = graph.get("nodes", {}) if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict) else {}
            if spec.get("category") == "dungeon":
                for node_id, node in nodes.items():
                    if not isinstance(node, dict):
                        continue
                    slots.append(
                        {
                            "slot_id": f"{spec['slot_id']}:subnode:{node_id}",
                            "target": "subnode",
                            "parent_slot_id": spec["slot_id"],
                            "node_id": node_id,
                            "node_kind": node.get("kind"),
                            "template_id": node.get("template_id"),
                            "template_name": node.get("template_name") or node.get("name"),
                            "template_desc": node.get("template_desc") or node.get("description"),
                        }
                    )
        return slots

    def _apply_description_response(self, specs: list[dict[str, Any]], response: dict[str, Any]) -> None:
        items = _response_items(response)
        by_slot = {str(item.get("slot_id") or item.get("id") or ""): item for item in items if isinstance(item, dict)}
        spec_by_id = {str(spec.get("slot_id") or ""): spec for spec in specs}
        for slot_id, item in by_slot.items():
            if not slot_id:
                continue
            if ":facility:" in slot_id:
                self._apply_facility_description(spec_by_id, slot_id, item)
            elif ":subnode:" in slot_id:
                self._apply_subnode_description(spec_by_id, slot_id, item)
            else:
                self._apply_location_description(spec_by_id, slot_id, item)

    def _apply_location_description(self, spec_by_id: dict[str, dict[str, Any]], slot_id: str, item: dict[str, Any]) -> None:
        spec = spec_by_id.get(slot_id)
        if not spec:
            return
        old_name = str(spec.get("name") or "")
        location = self.world.locations.get(old_name)
        if not location:
            return
        new_name = _clean_llm_name(item.get("name") or item.get("title") or "", fallback=old_name)
        if new_name and new_name != old_name:
            new_name = self.engine._rename_world_location(self.world, old_name, new_name)
            spec["name"] = new_name
            location = self.world.locations.get(new_name) or location
        description = _clean_llm_description(item.get("description") or item.get("desc") or item.get("summary") or "")
        if description:
            location.description = description
        location.extra["llm_location_description"] = _strip_response_metadata(item)
        self.engine._set_location_graph_node(self.world, location.name, kind=str(spec.get("kind") or ""), danger=_safe_int(spec.get("danger"), 0), location=location)

    def _apply_facility_description(self, spec_by_id: dict[str, dict[str, Any]], slot_id: str, item: dict[str, Any]) -> None:
        parent_slot, _, template_part = slot_id.partition(":facility:")
        spec = spec_by_id.get(parent_slot)
        if not spec:
            return
        location = self.world.locations.get(str(spec.get("name") or ""))
        if not location:
            return
        facilities = location.extra.get("facilities")
        if not isinstance(facilities, list):
            return
        for facility in facilities:
            if not isinstance(facility, dict):
                continue
            key_values = {
                str(facility.get("template_id") or ""),
                str(facility.get("id") or ""),
                str(facility.get("name") or ""),
            }
            if template_part not in key_values:
                continue
            llm_name = _clean_llm_name(item.get("name") or item.get("title") or "", fallback=str(facility.get("name") or ""))
            name = _facility_display_name_with_owner(llm_name, facility, location.name)
            description = _clean_llm_description(item.get("description") or item.get("desc") or item.get("summary") or "")
            if name:
                original_name = str(facility.get("name") or "")
                facility["name"] = name
                facility["sub_location"] = name
                aliases = facility.setdefault("aliases", [])
                if isinstance(aliases, list):
                    for alias in (original_name, llm_name):
                        if alias and alias != name and alias not in aliases:
                            aliases.append(alias)
            if description:
                facility["description"] = description
            facility["raw_template_world_facility_description"] = _strip_response_metadata(item)
            return

    def _apply_facility_owner_names(self, specs: list[dict[str, Any]]) -> None:
        for spec in specs:
            if spec.get("category") != "settlement":
                continue
            location = self.world.locations.get(str(spec.get("name") or ""))
            facilities = location.extra.get("facilities") if location else None
            if not isinstance(facilities, list):
                continue
            for facility in facilities:
                if not isinstance(facility, dict):
                    continue
                original_name = str(facility.get("name") or "").strip()
                display_name = _facility_display_name_with_owner(original_name, facility, location.name)
                if not display_name or display_name == original_name:
                    continue
                facility["name"] = display_name
                facility["sub_location"] = display_name
                aliases = facility.setdefault("aliases", [])
                if isinstance(aliases, list) and original_name and original_name not in aliases:
                    aliases.append(original_name)

    def _apply_subnode_description(self, spec_by_id: dict[str, dict[str, Any]], slot_id: str, item: dict[str, Any]) -> None:
        parent_slot, _, node_id = slot_id.partition(":subnode:")
        spec = spec_by_id.get(parent_slot)
        if not spec:
            return
        location = self.world.locations.get(str(spec.get("name") or ""))
        graph = location.extra.get(SUBNODE_GRAPH_KEY) if location else None
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict) else {}
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            return
        name = _clean_llm_name(item.get("name") or item.get("title") or "", fallback=str(node.get("name") or node_id))
        description = _clean_llm_description(item.get("description") or item.get("desc") or item.get("summary") or "")
        if name:
            node["name"] = name
        if description:
            node["description"] = description
        node["raw_template_world_subnode_description"] = _strip_response_metadata(item)

    def _connect_route_specs(self, specs: list[dict[str, Any]]) -> None:
        endpoint_use: dict[str, int] = {}
        for previous, current in zip(specs, specs[1:]):
            self.engine._connect_world_locations_by_subnodes(
                self.world,
                str(previous.get("name") or ""),
                str(current.get("name") or ""),
                self._external_subnode_for_spec(previous, endpoint_use),
                self._external_subnode_for_spec(current, endpoint_use),
                kind="template_route",
            )

    def _external_subnode_for_spec(self, spec: dict[str, Any], endpoint_use: dict[str, int]) -> str:
        name = str(spec.get("name") or "")
        if spec.get("category") == "settlement":
            return "gate"
        if spec.get("category") != "dungeon":
            return DEFAULT_SUBNODE_ID
        location = self.world.locations.get(name)
        graph = location.extra.get(SUBNODE_GRAPH_KEY) if location else None
        candidates = _as_list(graph.get("external_subnode_candidates")) if isinstance(graph, dict) else []
        candidates = [str(item) for item in candidates if str(item)]
        if not candidates:
            candidates = [DUNGEON_ENTRY_SUBNODE_ID]
        index = endpoint_use.get(name, 0)
        endpoint_use[name] = index + 1
        return candidates[index % len(candidates)]

    def _choose_world_template(self, category: str, type_hint: str, rng: random.Random) -> dict[str, Any]:
        candidates = [
            item
            for item in self.world_templates
            if str(item.get("category") or "") == category
            and (not type_hint or str(item.get("type") or "") == type_hint)
        ]
        if not candidates:
            candidates = [item for item in self.world_templates if str(item.get("category") or "") == category]
        if not candidates:
            raise ValueError(f"Missing Location_World template for category={category!r} type={type_hint!r}")
        return deepcopy(rng.choice(candidates))

    def _choose_dungeon_type(self, text: str, rng: random.Random) -> str:
        dungeon_templates = [item for item in self.world_templates if str(item.get("category") or "") == "dungeon"]
        types = sorted({str(item.get("type") or "") for item in dungeon_templates if str(item.get("type") or "")})
        if not types:
            return "dungeon"
        folded = str(text or "").casefold()
        keyword_map = {
            "forest": ("forest", "woods", "grove", "lair", "nest", "den", "森", "樹海", "森林", "巣穴"),
            "mountain": ("mountain", "mine", "peak", "cave", "cavern", "grotto", "quarry", "山", "鉱山", "坑道", "洞窟", "洞穴"),
            "ruin": ("ruin", "ruins", "ancient", "labyrinth", "maze", "crypt", "tomb", "遺跡", "廃墟", "古代", "迷宮", "墓所"),
            "temple": ("temple", "shrine", "sanctuary", "church", "holy", "神殿", "寺院", "聖域", "教会"),
        }
        scored = []
        for dungeon_type in types:
            score = sum(1 for marker in keyword_map.get(dungeon_type, ()) if marker.casefold() in folded)
            scored.append((score, rng.random(), dungeon_type))
        scored.sort(reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][2]
        return rng.choice(types)

    def _local_templates_for_target(self, target_type: str, *, categories: tuple[str, ...]) -> list[dict[str, Any]]:
        target = str(target_type or "").strip()
        result = []
        for item in self.local_templates:
            template_category = _local_template_category(item)
            if template_category not in categories:
                continue
            if self._target_matches(item, target):
                result.append(deepcopy(item))
        return result

    def _target_matches(self, template: dict[str, Any], target_type: str) -> bool:
        targets = [str(item) for item in _as_list(template.get("target_type")) if str(item).strip()]
        return not targets or target_type in targets or "all" in targets or "dungeon" in targets and target_type

    def _choose_entrance_template(self, templates: list[dict[str, Any]], target_type: str) -> dict[str, Any] | None:
        for template in templates:
            if _as_bool(template.get("entrance")) and self._target_matches(template, target_type):
                return deepcopy(template)
        return None

    def _template_is_settlement_facility(self, template: dict[str, Any]) -> bool:
        template_id = str(template.get("id") or "")
        if template_id in SETTLEMENT_EXCLUDED_RANDOM_IDS:
            return False
        return bool(template.get("function_npc") or template.get("shopkeeper") or template.get("shopItem"))

    def _facility_from_template(self, location: LocationData, template: dict[str, Any]) -> dict[str, Any]:
        template_id = str(template.get("id") or "")
        facility_type = FACILITY_TYPE_BY_TEMPLATE_ID.get(template_id) or _facility_type_from_template(template)
        name = str(template.get("name") or template_id or facility_type)
        name_entry = claim_name_from_namelist(
            self.world,
            seed=f"facility-template:{self.world.world_name}:{location.name}:{template_id}",
            reason="facility_npc_candidate",
        )
        npc_name = str((name_entry or {}).get("name_ja") or "")
        record: dict[str, Any] = {
            "name": name,
            "type": facility_type,
            "description": str(template.get("desc") or ""),
            "npc_name": npc_name,
            "npc_role": _default_facility_role(facility_type),
            "location_name": location.name,
            "sub_location": name,
            "source": "location_local_template",
            "template_id": template_id,
            "template_name": name,
            "template_desc": str(template.get("desc") or ""),
            "function_npc": deepcopy(_as_list(template.get("function_npc"))),
            "shopkeeper": deepcopy(_as_list(template.get("shopkeeper"))),
            "shopItem": deepcopy(_as_list(template.get("shopItem"))),
            "local_template": deepcopy(template),
        }
        if name_entry:
            record["npc_namelist_id"] = str(name_entry.get("id") or "")
            record["npc_namelist_english_en"] = str(name_entry.get("english_en") or "")
        return record

    def _node_template_payload(self, template: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "template_id": str(template.get("id") or ""),
            "template_name": str(template.get("name") or ""),
            "template_desc": str(template.get("desc") or ""),
            "target_type": deepcopy(_as_list(template.get("target_type"))),
            "multiple_generating": _as_bool(template.get("multiple_generating")),
            "random_generate": _as_bool(template.get("random_generate", True)),
            "entrance": _as_bool(template.get("entrance")),
            "innermost_part": _as_bool(template.get("innermost_part")),
            "generate_boss": _as_bool(template.get("generate_boss")),
            "item_generate": _as_bool(template.get("item_generate")),
            "item_regenerate": _as_bool(template.get("item_regenerate")),
            "item_tabel": deepcopy(_as_list(template.get("item_tabel") or template.get("item_table"))),
            "function_npc": deepcopy(_as_list(template.get("function_npc"))),
            "shopkeeper": deepcopy(_as_list(template.get("shopkeeper"))),
            "shopItem": deepcopy(_as_list(template.get("shopItem"))),
        }
        if "generate_enemy_rate" in template:
            payload["generate_enemy_rate"] = _safe_float(template.get("generate_enemy_rate"), 0.0)
        return payload

    def _unique_location_name(self, base_name: str) -> str:
        base = str(base_name or "Location").strip() or "Location"
        if base not in self.world.locations:
            return base
        index = 2
        while f"{base}{index}" in self.world.locations:
            index += 1
        return f"{base}{index}"

    def _fallback_template_name(self, category: str, template_type: str, index: int) -> str:
        labels = {
            "settlement": "拠点",
            "highway": "街道",
            "dungeon": "ダンジョン",
        }
        return f"{labels.get(category, category)}{index + 1:02d}"

    def _location_kind(self, category: str, template_type: str) -> str:
        if category == "settlement":
            return "settlement"
        if category == "dungeon":
            return "dungeon"
        if template_type == "coast":
            return "coast"
        return "road"

    def _emit(self, phase: str, message: str, current: int) -> None:
        self.engine._emit_world_generation_progress(self.progress_callback, phase, message, current, 100)

    def _progress(self, ratio: float) -> int:
        return self.progress_start + int((self.progress_end - self.progress_start) * max(0.0, min(1.0, ratio)))


def _load_world_templates() -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for directory in _template_dirs(LOCATION_WORLD_TEMPLATE_DIR, "Location_World"):
        for path in sorted(directory.glob("*.json")):
            for raw in _load_json_array(path):
                if not isinstance(raw, dict):
                    continue
                category = str(raw.get("category") or "").strip()
                if category not in LOCATION_TEMPLATE_CATEGORY_IDS:
                    continue
                name = str(raw.get("name") or "").strip()
                template_type = str(raw.get("type") or "").strip()
                if not name or not template_type:
                    continue
                templates.append({**deepcopy(raw), "source_path": str(path)})
    return templates


def _load_local_templates() -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for directory in _template_dirs(LOCATION_LOCAL_TEMPLATE_DIR, "Location_Local"):
        for path in sorted(directory.glob("*.json")):
            file_category = _local_category_from_filename(path.name)
            for raw in _load_json_array(path):
                if not isinstance(raw, dict):
                    continue
                template_id = str(raw.get("id") or "").strip()
                if not template_id:
                    continue
                templates.append({**deepcopy(raw), "source_path": str(path), "local_category": file_category})
    return templates


def _template_dirs(primary: Path, folder_name: str) -> list[Path]:
    result: list[Path] = []
    for candidate in (primary, ROOT / "Data" / "Template" / folder_name):
        if candidate.exists() and candidate not in result:
            result.append(candidate)
    return result


def _load_json_array(path: Path) -> list[Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("items", "templates", "locations", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def _local_category_from_filename(name: str) -> str:
    lowered = name.lower()
    if "settlement" in lowered:
        return "settlement"
    if "highway" in lowered:
        return "highway"
    if "dungeon" in lowered:
        return "dungeon"
    return "common"


def _local_template_category(template: dict[str, Any]) -> str:
    return str(template.get("local_category") or "common")


def _facility_type_from_template(template: dict[str, Any]) -> str:
    template_id = str(template.get("id") or "").lower()
    for key, value in FACILITY_TYPE_BY_TEMPLATE_ID.items():
        if key in template_id:
            return value
    if template.get("shopkeeper") or template.get("shopItem"):
        return "shop"
    if "inn" in template_id:
        return "inn"
    if "guild" in template_id:
        return "guild"
    if "townhall" in template_id:
        return "town_hall"
    return "facility"


def _facility_display_name_with_owner(name: str, facility: dict[str, Any], settlement_name: str) -> str:
    clean_name = str(name or "").strip()
    facility_type = str(facility.get("type") or _facility_type_from_template(facility)).strip().lower()
    label = FACILITY_DISPLAY_LABEL_BY_TYPE.get(facility_type) or str(facility.get("template_name") or clean_name).strip()
    npc_name = str(facility.get("npc_name") or "").strip()
    settlement = str(settlement_name or facility.get("location_name") or "").strip()
    if facility_type in FACILITY_NPC_NAMED_TYPES and npc_name:
        return clean_name if npc_name in clean_name else f"{npc_name}の{label}"
    if facility_type in FACILITY_SETTLEMENT_NAMED_TYPES and settlement:
        return clean_name if settlement in clean_name else f"{settlement}の{label}"
    return clean_name


def _default_facility_role(facility_type: str) -> str:
    return {
        "guild": "ギルド受付",
        "town_hall": "役場職員",
        "inn": "宿屋の主人",
        "blacksmith": "鍛冶職人",
        "apothecary": "薬師",
        "general_store": "雑貨店主",
        "food_store": "食料品店主",
        "black_market": "闇商人",
        "material_store": "素材商",
        "magic_store": "魔法品商",
        "junk_store": "ジャンク屋",
        "temple": "司祭",
    }.get(str(facility_type or ""), "施設担当者")


def _response_items(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    result: list[dict[str, Any]] = []
    for key in ("items", "slots", "locations", "facilities", "subnodes", "results"):
        value = response.get(key)
        if isinstance(value, list):
            result.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            result.append(value)
    if not result and any(key in response for key in ("slot_id", "name", "description")):
        result.append(response)
    return result


def _strip_response_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_response_metadata(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [_strip_response_metadata(item) for item in value]
    return value


def _clean_llm_name(value: Any, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return fallback
    lowered = text.casefold()
    if any(marker in lowered for marker in ("unnamed", "placeholder", "slot_id", "初期地点", "未命名")):
        return fallback
    return text[:64]


def _clean_llm_description(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if any(marker in text.casefold() for marker in ("slot_id", "target_type", "category", "初期地点", "未命名")):
        return ""
    return text[:260]


def _location_danger(location: LocationData) -> int:
    return _clamp_world_danger(location.extra.get("danger_level", location.extra.get("danger", 0)))


def _ai_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _short_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value in (None, ""):
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "yes", "1", "on"}


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
