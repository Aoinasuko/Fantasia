from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

def _active_quest_destination_location(self) -> str:
    quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
    if not quest or not isinstance(quest.extra, dict):
        return ""
    destination = quest.extra.get("destination")
    if isinstance(destination, dict):
        return str(destination.get("location") or "").strip()
    return str(quest.extra.get("objective_location") or "").strip()

def _active_quest_destination_subnode(self) -> str:
    quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
    if not quest or not isinstance(quest.extra, dict):
        return ""
    destination = quest.extra.get("destination")
    if isinstance(destination, dict):
        return str(destination.get("objective_subnode_id") or "").strip()
    return str(quest.extra.get("objective_subnode_id") or "").strip()

def _ensure_quest_destination(self, quest: QuestData, response: dict[str, Any] | None = None) -> dict[str, Any]:
    world = self.state.world_data
    existing = quest.extra.get("destination")
    if isinstance(existing, dict):
        location_name = str(existing.get("location") or existing.get("destination_location") or "").strip()
        if location_name and location_name in world.locations:
            subnode = self._ensure_quest_objective_subnode(world.locations[location_name], quest, existing)
            existing["location"] = location_name
            existing["objective_subnode_id"] = subnode.get("id") or existing.get("objective_subnode_id") or ""
            existing["objective_subnode_name"] = subnode.get("name") or existing.get("objective_subnode_name") or ""
            quest.extra["destination"] = existing
            quest.extra["objective_location"] = location_name
            quest.extra["objective_subnode_id"] = str(existing.get("objective_subnode_id") or "")
            quest.extra["objective_subnode_name"] = str(existing.get("objective_subnode_name") or "")
            return existing

    hint = _quest_destination_hint(quest, response)
    origin = self._quest_origin_location(quest)
    anchor = self._quest_anchor_location(origin, hint)
    location = self._quest_destination_location(quest, hint, origin, anchor)
    subnode = self._ensure_quest_objective_subnode(location, quest, hint)
    destination = {
        "location": location.name,
        "location_kind": str(location.extra.get("location_kind") or ""),
        "danger_level": _safe_int(location.extra.get("danger_level"), 0),
        "anchor_location": anchor,
        "objective_subnode_id": str(subnode.get("id") or ""),
        "objective_subnode_name": str(subnode.get("name") or ""),
        "objective_subnode_description": str(subnode.get("description") or ""),
        "source": "quest_destination_resolver",
    }
    quest.extra["destination"] = destination
    quest.extra["objective_location"] = location.name
    quest.extra["objective_subnode_id"] = destination["objective_subnode_id"]
    quest.extra["objective_subnode_name"] = destination["objective_subnode_name"]
    return destination

def _quest_origin_subnode_id(self, origin: str) -> str:
    origin = str(origin or "").strip()
    if not origin:
        return ""
    if origin == self.state.current_location:
        current = self._current_subnode_id(origin)
        if current:
            return current
    location = self.state.world_data.locations.get(origin)
    if not location or not _is_settlement_location(location):
        return ""
    graph = self._ensure_location_subnode_graph(self.state.world_data, origin)
    nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
    for facility in self._ensure_settlement_facilities(location):
        if str(facility.get("type") or "").strip().lower() == "guild" or _looks_like_guild_name(str(facility.get("name") or "")):
            node_id = self._facility_subnode_id(facility)
            if node_id in nodes:
                return node_id
    return DEFAULT_SUBNODE_ID if DEFAULT_SUBNODE_ID in nodes else ""

def _quest_origin_location(self, quest: QuestData) -> str:
    world = self.state.world_data
    for value in (
        quest.extra.get("origin_location"),
        quest.neighboring_settlement,
        (self._current_settlement_location().name if self._current_settlement_location() else ""),
        self.state.current_location,
        world.starting_location,
    ):
        name = str(value or "").strip()
        if name and name in world.locations:
            return name
    return self.state.current_location or world.starting_location

def _quest_anchor_location(self, origin: str, hint: dict[str, Any]) -> str:
    world = self.state.world_data
    origin = origin if origin in world.locations else (world.starting_location or origin)
    anchor_kind = str(hint.get("anchor_kind") or "").strip()
    destination_kind = str(hint.get("location_kind") or "").strip()
    explicit_anchor = str(hint.get("anchor_location") or "").strip()
    if explicit_anchor:
        resolved = self._find_world_location_by_name(explicit_anchor)
        if resolved:
            return resolved
    if anchor_kind and anchor_kind != destination_kind:
        found = self._find_nearby_location_by_kind(origin, anchor_kind)
        if found:
            return found
        if anchor_kind in {"road", "crossroad"}:
            anchor_name = _unique_world_location_name(
                world,
                f"{world.locations.get(origin, LocationData(name=origin)).name}近くの{_quest_location_kind_label(anchor_kind)}",
            )
            anchor_location = world.ensure_location(anchor_name, f"{origin}から目的地へ向かう途中にある{_quest_location_kind_label(anchor_kind)}。")
            anchor_location.extra["location_kind"] = anchor_kind
            anchor_location.extra["danger_level"] = 0
            anchor_location.flags["discovered"] = True
            self._set_location_graph_node(world, anchor_name, kind=anchor_kind, danger=0, location=anchor_location)
            self._connect_world_locations(world, origin, anchor_name)
            return anchor_name
    return origin

def _quest_hint_requests_dungeon(self, quest: QuestData, hint: dict[str, Any]) -> bool:
    kind = str(hint.get("location_kind") or "").strip().lower()
    if kind in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair", "forest", "mountain"}:
        return True
    text = " ".join(
        str(part or "")
        for part in (
            quest.name,
            quest.overview,
            hint.get("source_text"),
            hint.get("description"),
            hint.get("objective_description"),
            hint.get("objective_subnode_description"),
            hint.get("objective_subnode_name"),
        )
    ).lower()
    return any(word in text for word in ("dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair", "洞窟", "遺跡", "鉱山", "迷宮", "巣穴", "森", "山"))

def _quest_dungeon_branch_anchor(self, origin: str, fallback: str = "") -> str:
    world = self.state.world_data
    specs = self._route_skeleton_specs(world)
    origin = str(origin or "").strip()
    fallback = str(fallback or "").strip()
    origin_index = next((index for index, spec in enumerate(specs) if str(spec.get("name") or "") == origin), -1)
    if origin_index >= 0:
        for spec in specs[origin_index + 1 :]:
            category = str(spec.get("category") or "")
            role = str(spec.get("role") or "")
            if category == "settlement" or role == "final_destination":
                break
            if category == "single":
                name = str(spec.get("name") or "")
                if name in world.locations:
                    return name
        for spec in reversed(specs[:origin_index]):
            category = str(spec.get("category") or "")
            role = str(spec.get("role") or "")
            if category == "settlement" or role == "final_destination":
                break
            if category == "single":
                name = str(spec.get("name") or "")
                if name in world.locations:
                    return name
    fallback_location = world.locations.get(fallback)
    if fallback_location and str(fallback_location.extra.get("main_node_type") or "") == "single":
        return fallback
    return origin if origin in world.locations else fallback

def _create_quest_dungeon_location(self, quest: QuestData, hint: dict[str, Any], origin: str, anchor: str) -> LocationData:
    world = self.state.world_data
    branch_anchor = self._quest_dungeon_branch_anchor(origin, anchor)
    kind = "dungeon"
    explicit_name = str(hint.get("location") or hint.get("destination_location") or "").strip()
    base_name = explicit_name or _quest_destination_name(quest, {**hint, "location_kind": "dungeon"}, origin, branch_anchor)
    location_name = _unique_world_location_name(world, base_name)
    anchor_node = self._location_graph_for_update(world).get("nodes", {}).get(branch_anchor, {})
    anchor_danger = _safe_int(anchor_node.get("danger") if isinstance(anchor_node, dict) else 0, self._current_location_danger(branch_anchor))
    danger = max(anchor_danger + 1, _quest_destination_danger(hint, kind, anchor_danger))
    description = str(hint.get("description") or hint.get("objective_subnode_description") or "").strip()
    if not description:
        description = f"依頼「{quest.name}」の目的地となる探索地。"
    location = world.ensure_location(location_name, description)
    location.extra.update(
        {
            "location_kind": kind,
            "main_node_type": "dungeon",
            "main_node_subtype": str(hint.get("location_kind") or "dungeon"),
            "role": "quest_dungeon",
            "danger_level": _clamp_world_danger(danger),
            "danger_source": "quest_dungeon",
            "quest_destination_for": quest.name,
            "generated_for_quest": quest.name,
            "branch_anchor_location": branch_anchor,
        }
    )
    location.flags["dungeon"] = True
    location.flags["dangerous"] = True
    location.flags["discovered"] = True
    anchor_location = world.locations.get(branch_anchor)
    if anchor_location:
        anchor_location.flags["discovered"] = True
        anchor_node = self._set_location_graph_node(world, branch_anchor, location=anchor_location)
        anchor_node["discovered"] = True
    self._install_local_dungeon_subnode_graph(location, random.Random(f"quest-dungeon|{world.world_name}|{quest.name}|{branch_anchor}"))
    self._set_location_graph_node(world, location_name, kind=kind, danger=location.extra["danger_level"], location=location)
    if branch_anchor and branch_anchor != location_name:
        self._connect_world_locations_by_subnodes(
            world,
            branch_anchor,
            location_name,
            DEFAULT_SUBNODE_ID,
            DUNGEON_ENTRY_SUBNODE_ID,
            kind="quest_dungeon_branch",
        )
    world.history.append(
        {
            "manager": "quest_dungeon_generator",
            "quest": quest.name,
            "location": location_name,
            "branch_anchor": branch_anchor,
        }
    )
    return location

def _quest_destination_location(self, quest: QuestData, hint: dict[str, Any], origin: str, anchor: str) -> LocationData:
    world = self.state.world_data
    explicit_name = str(hint.get("location") or hint.get("destination_location") or "").strip()
    if explicit_name:
        resolved = self._find_world_location_by_name(explicit_name)
        if resolved:
            location = world.locations[resolved]
            if not self._world_neighbors_no_ensure(world, resolved) and anchor and anchor != resolved:
                self._connect_world_locations(world, anchor, resolved)
            return location

    kind = str(hint.get("location_kind") or "wilderness").strip() or "wilderness"
    if self._quest_hint_requests_dungeon(quest, hint):
        return self._create_quest_dungeon_location(quest, hint, origin, anchor)
    nearby_existing = self._find_nearby_location_by_kind(anchor or origin, kind)
    if nearby_existing and not _quest_text_requests_new_site(str(hint.get("source_text") or "")):
        return world.locations[nearby_existing]

    base_name = explicit_name or _quest_destination_name(quest, hint, origin, anchor)
    location_name = _unique_world_location_name(world, base_name)
    origin_node = self._location_graph_for_update(world).get("nodes", {}).get(origin, {})
    base_danger = _safe_int(origin_node.get("danger") if isinstance(origin_node, dict) else 0, 0)
    danger = _quest_destination_danger(hint, kind, base_danger)
    description = str(hint.get("description") or "").strip()
    if not description:
        description = f"依頼「{quest.name}」の目標が存在する{_quest_location_kind_label(kind)}。"
    location = world.ensure_location(location_name, description)
    location.extra["location_kind"] = kind
    location.extra["danger_level"] = danger
    location.extra["quest_destination_for"] = quest.name
    location.flags["discovered"] = True
    if _world_kind_is_settlement(kind):
        location.flags["settlement"] = True
    if _world_location_blocks_world_map_departure(location):
        location.flags["dangerous"] = True
    self._set_location_graph_node(world, location_name, kind=kind, danger=danger, location=location)
    if anchor and anchor != location_name:
        self._connect_world_locations(world, anchor, location_name)
    elif origin and origin != location_name:
        self._connect_world_locations(world, origin, location_name)
    return location

def _find_world_location_by_name(self, name: str) -> str:
    key = _world_location_name_key(name)
    if not key:
        return ""
    for location_name in self.state.world_data.locations:
        if _world_location_name_key(location_name) == key:
            return location_name
    for location_name in self.state.world_data.locations:
        location_key = _world_location_name_key(location_name)
        if key in location_key or location_key in key:
            return location_name
    return ""

def _find_nearby_location_by_kind(self, origin: str, kind: str) -> str:
    world = self.state.world_data
    target_kind = str(kind or "").strip().lower()
    if not target_kind:
        return ""
    candidates = [origin, *self._world_neighbors_no_ensure(world, origin)]
    for neighbor in self._world_neighbors_no_ensure(world, origin):
        candidates.extend(self._world_neighbors_no_ensure(world, neighbor))
    for name in _dedupe_strs(candidates):
        location = world.locations.get(name)
        if not location:
            continue
        current_kind = str(location.extra.get("location_kind") or "").strip().lower()
        if current_kind == target_kind:
            return name
    return ""

def _ensure_quest_objective_subnode(self, location: LocationData, quest: QuestData, hint: dict[str, Any]) -> dict[str, Any]:
    location.extra.setdefault(SUBNODE_GRAPH_KEY, {"nodes": {}, "edges": []})
    graph = self._ensure_location_subnode_graph(self.state.world_data, location.name)
    nodes = graph.setdefault("nodes", {})
    node_id = str(hint.get("objective_subnode_id") or "").strip()
    if not node_id:
        node_id = f"quest:{_world_location_name_key(quest.name) or 'objective'}"
    node_name, description = self._quest_objective_subnode_display(quest, hint)
    existing = nodes.get(node_id)
    if isinstance(existing, dict):
        existing["quest_name"] = quest.name
        existing["quest_objective"] = True
        if _subnode_display_needs_fill(existing.get("name")):
            existing["name"] = node_name
        if _subnode_display_needs_fill(existing.get("description")):
            existing["description"] = description
        if _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location):
            self._ensure_quest_branch_connection(location, graph, quest, node_id)
        else:
            self._ensure_subnode_connected_to_anchor(graph, node_id, kind="quest_path", prefer_deep=True)
        return existing
    x = 560
    y = 360 + (len(nodes) % 3) * 90
    if _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location):
        parent = self._ensure_quest_branch_node(location, graph, quest)
        parent_node = nodes.get(parent, {}) if isinstance(nodes.get(parent), dict) else {}
        x = _safe_int(parent_node.get("x"), 560) + 140
        y = _safe_int(parent_node.get("y"), 260) + 70
    elif "depths" in nodes:
        parent = "depths"
        x = _safe_int(nodes[parent].get("x"), 560) + 170
        y = _safe_int(nodes[parent].get("y"), 180)
    elif "fork" in nodes:
        parent = "fork"
    else:
        parent = self._subnode_anchor(graph, prefer_deep=True, exclude=node_id)
    node = self._upsert_subnode_node(
        graph,
        node_id,
        node_name,
        description,
        "quest_objective",
        x,
        y,
        quest_name=quest.name,
        quest_objective=True,
    )
    if parent:
        self._connect_subnodes(graph, str(parent), node_id, kind="quest_path")
    if _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location):
        self._ensure_quest_branch_connection(location, graph, quest, node_id)
    else:
        self._ensure_subnode_connected_to_anchor(graph, node_id, kind="quest_path", prefer_deep=True)
    return node

def _ensure_quest_branch_node(self, location: LocationData, graph: dict[str, Any], quest: QuestData) -> str:
    nodes = graph.setdefault("nodes", {})
    branch_id = f"quest_branch:{_world_location_name_key(quest.name) or 'objective'}"
    if branch_id in nodes:
        return branch_id
    parent = self._quest_branch_parent(graph)
    parent_node = nodes.get(parent, {}) if isinstance(nodes.get(parent), dict) else {}
    x = _safe_int(parent_node.get("x"), 360) + 80
    y = _safe_int(parent_node.get("y"), 220) + 110
    self._upsert_subnode_node(
        graph,
        branch_id,
        f"{quest.name}への分岐",
        "本道から外れた、依頼の目的地へ続く分岐点。",
        "quest_branch",
        x,
        y,
        quest_name=quest.name,
        revealed=False,
        world_map_exit=False,
    )
    if parent:
        self._connect_subnodes(graph, parent, branch_id, kind="quest_branch")
    self._ensure_subnode_connected_to_anchor(graph, branch_id, kind="quest_branch", prefer_deep=False)
    return branch_id

def _quest_branch_parent(self, graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
    if not nodes:
        return ""
    start = DUNGEON_ENTRY_SUBNODE_ID if DUNGEON_ENTRY_SUBNODE_ID in nodes else self._subnode_anchor(graph, prefer_deep=False)
    deepest = DUNGEON_DEEPEST_SUBNODE_ID if DUNGEON_DEEPEST_SUBNODE_ID in nodes else ""
    path = self._subnode_path(graph, start, deepest) if start and deepest else []
    candidates = [node_id for node_id in path[1:-1] if node_id in nodes]
    if candidates:
        return candidates[max(0, len(candidates) // 2)]
    for node_id in self._subnode_adjacent_ids(graph, start):
        if node_id != deepest:
            return node_id
    return start

def _ensure_quest_branch_connection(
    self,
    location: LocationData,
    graph: dict[str, Any],
    quest: QuestData,
    objective_node_id: str,
) -> None:
    nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
    objective_node_id = str(objective_node_id or "").strip()
    if objective_node_id not in nodes:
        return
    branch_id = self._ensure_quest_branch_node(location, graph, quest)
    if branch_id:
        self._connect_subnodes(graph, branch_id, objective_node_id, kind="quest_path")
    _ensure_dungeon_graph_connected(graph)

def _quest_objective_subnode_display(self, quest: QuestData, hint: dict[str, Any]) -> tuple[str, str]:
    text_parts = [
        hint.get("objective_subnode_name"),
        hint.get("objective_name"),
        hint.get("target_name"),
        hint.get("objective"),
        hint.get("objective_description"),
        hint.get("objective_subnode_description"),
        quest.name,
        quest.overview,
        getattr(quest, "description", ""),
        quest.extra.get("description") if isinstance(quest.extra, dict) else "",
    ]
    source_text = "\n".join(str(part) for part in text_parts if str(part or "").strip())
    raw_name = str(hint.get("objective_subnode_name") or hint.get("objective_name") or "").strip()
    if _subnode_display_needs_fill(raw_name):
        raw_name = _quest_objective_name_from_text(source_text)
    if _subnode_display_needs_fill(raw_name):
        raw_name = f"{quest.name} objective"
    raw_description = str(
        hint.get("objective_subnode_description")
        or hint.get("objective_description")
        or hint.get("target_description")
        or quest.overview
        or getattr(quest, "description", "")
        or (quest.extra.get("description") if isinstance(quest.extra, dict) else "")
        or ""
    ).strip()
    if _subnode_display_needs_fill(raw_description):
        raw_description = f"Objective site for quest: {quest.name}."
    return _short_text(raw_name, 48), _short_text(raw_description, 180)

def _quest_destination_choices(self, destination: dict[str, Any], current_location: str) -> list[str]:
    location_name = str(destination.get("location") or "").strip()
    if not location_name or location_name == current_location:
        return []
    return [f"{location_name}へ向かう"]

def _quest_destination_for_action(
    self,
    quest: QuestData,
    action: str,
    referee: dict[str, Any] | None,
    event_resolution: dict[str, Any] | None,
    *,
    explicit_movement: bool = False,
) -> dict[str, Any]:
    if not explicit_movement:
        return {}
    destination = quest.extra.get("destination")
    if not isinstance(destination, dict):
        return {}
    location_name = str(destination.get("location") or "").strip()
    if not location_name or location_name not in self.state.world_data.locations:
        return {}
    return destination

