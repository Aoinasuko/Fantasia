from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

def _quest_investigation_point_name(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    for key in ("investigation_point_name", "survey_point_name", "objective_subnode_name", "target_name", "objective"):
        value = str(response.get(key) or "").strip()
        if value:
            return _clean_generated_name(value, "\u8abf\u67fb\u5730\u70b9", kind="actor")
    text = _quest_destination_source_text(quest, response)
    if "\u6700\u6df1\u90e8" in text:
        return "\u6700\u6df1\u90e8\u306e\u8abf\u67fb\u5730\u70b9"
    if "\u907a\u8de1" in text:
        return "\u907a\u8de1\u306e\u8abf\u67fb\u5730\u70b9"
    return f"{quest.name}\u306e\u8abf\u67fb\u5730\u70b9"

def _quest_procurement_requirement_name(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    for key in ("procurement_item_name", "requested_item_name", "required_item_name", "target_item_name", "item_name"):
        value = str(response.get(key) or "").strip()
        if value:
            return _strip_generated_name_notes(value) or "\u8abf\u9054\u54c1"
    text = _quest_destination_source_text(quest, response)
    if "\u30dd\u30fc\u30b7\u30e7\u30f3" in text or "potion" in text.casefold():
        return "\u6761\u4ef6\u306b\u5408\u3046\u30dd\u30fc\u30b7\u30e7\u30f3"
    if "\u85ac" in text:
        return "\u6761\u4ef6\u306b\u5408\u3046\u85ac"
    if "\u98df" in text:
        return "\u6761\u4ef6\u306b\u5408\u3046\u98df\u6599"
    return f"{quest.name}\u306e\u8abf\u9054\u54c1"

def _quest_procurement_requirement_text(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    for key in ("procurement_requirement", "required_item_description", "objective", "description"):
        value = str(response.get(key) or "").strip()
        if value:
            return value
    return _quest_destination_source_text(quest, response) or quest.overview

def _quest_procurement_category_words(category: str) -> tuple[str, ...]:
    category = str(category or "").strip().lower()
    return {
        "potion": ("\u30dd\u30fc\u30b7\u30e7\u30f3", "potion"),
        "medicine": ("\u85ac", "\u85ac\u54c1", "\u6cbb\u7642", "medicine"),
        "food": ("\u98df\u6599", "\u98df\u3079\u7269", "food"),
        "drink": ("\u98f2\u6599", "\u98f2\u307f\u7269", "drink"),
        "tool": ("\u9053\u5177", "tool"),
        "document": ("\u6587\u66f8", "\u624b\u7d19", "document", "letter"),
        "scroll": ("\u5dfb\u7269", "scroll"),
        "magicrod": ("\u6756", "\u9b54\u6cd5\u6756", "rod"),
        "material_plant": ("\u85ac\u8349", "\u690d\u7269", "\u8349", "herb", "plant"),
        "material_gem": ("\u5b9d\u77f3", "\u5b9d\u73e0", "gem", "jewel"),
        "relic": ("\u907a\u7269", "\u30ec\u30ea\u30c3\u30af", "relic"),
        "treasure": ("\u5b9d", "\u5b9d\u7269", "treasure"),
    }.get(category, ())

def _quest_objective_kind(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    explicit = str(
        response.get("objective_kind")
        or response.get("objective_type")
        or response.get("target_kind")
        or extra.get("objective_kind")
        or extra.get("objective_type")
        or ""
    ).strip().lower()
    if explicit in {"npc", "person", "character", "rescue", "escort", "hostage"}:
        return "npc"
    if explicit in {"item", "quest_item", "object", "artifact", "retrieve", "collect"}:
        return "item"
    text = _quest_destination_source_text(quest, response)
    lowered = text.casefold()
    if any(
        word in text
        for word in (
            "\u6551\u51fa",
            "\u6551\u52a9",
            "\u4fdd\u8b77",
            "\u8b77\u9001",
            "\u4eba\u8cea",
            "\u6500",
            "\u652b",
            "\u3055\u3089\u308f",
            "\u9023\u308c\u53bb",
            "\u5a18",
            "\u884c\u65b9\u4e0d\u660e\u8005",
        )
    ):
        return "npc"
    if any(
        word in text
        for word in (
            "\u56de\u53ce",
            "\u53ce\u96c6",
            "\u63a1\u53d6",
            "\u6301\u3061\u5e30",
            "\u5c4a\u3051",
            "\u7d0d\u54c1",
            "\u4f9d\u983c\u54c1",
            "\u8a3c\u62e0",
            "\u6587\u66f8",
            "\u5b9d\u73e0",
            "\u907a\u7269",
            "\u85ac\u8349",
        )
    ):
        return "item"
    if any(word in lowered for word in ("rescue", "save", "escort", "hostage", "kidnap", "kidnapped")):
        return "npc"
    if any(word in text for word in ("救出", "救助", "保護", "護送", "人質", "攫", "さらわ", "連れ去", "娘", "行方不明者")):
        return "npc"
    if any(word in lowered for word in ("retrieve", "collect", "bring back", "deliver", "quest item", "artifact", "document")):
        return "item"
    if any(word in text for word in ("回収", "収集", "採取", "持ち帰", "届け", "納品", "依頼品", "証拠", "文書", "宝珠", "遺物", "薬草")):
        return "item"
    return ""

def _quest_objective_npc_name(
    quest: QuestData,
    response: dict[str, Any] | None = None,
    *,
    objective_role: str = "rescue_target",
) -> str:
    response = response or {}
    role_keys = {
        "rescue_target": ("objective_npc_name", "target_npc_name", "rescue_target_name", "target_name"),
        "defeat_target": ("defeat_target_name", "target_npc_name", "monster_name", "target_name"),
        "delivery_target": ("delivery_target_name", "recipient_name", "target_npc_name", "target_name"),
        "blocker": ("captor_name", "blocker_name", "enemy_name", "target_name"),
    }.get(objective_role, ("objective_npc_name", "target_npc_name", "target_name"))
    for key in role_keys:
        value = str(response.get(key) or "").strip()
        if value:
            fallback = {
                "defeat_target": "\u8a0e\u4f10\u5bfe\u8c61",
                "delivery_target": "\u914d\u9054\u5148",
                "blocker": "\u62d8\u675f\u8005",
            }.get(objective_role, "\u6551\u51fa\u5bfe\u8c61")
            return _clean_generated_name(value, fallback, kind="character")
    if objective_role == "defeat_target":
        return f"{quest.name}\u306e\u8a0e\u4f10\u5bfe\u8c61"
    if objective_role == "delivery_target":
        return _quest_delivery_target_name(quest, response)
    if objective_role == "blocker":
        return "\u62d8\u675f\u8005"
    for key in ("objective_npc_name", "target_npc_name", "rescue_target_name", "target_name"):
        value = str(response.get(key) or "").strip()
        if value:
            return _clean_generated_name(value, "救出対象", kind="character")
    return f"{quest.name}の救出対象"

def _quest_objective_npc_fallback_design(
    quest: QuestData,
    response: dict[str, Any] | None = None,
    *,
    objective_role: str = "rescue_target",
) -> dict[str, Any]:
    response = response or {}
    base_name = _quest_objective_npc_name(quest, response, objective_role=objective_role)
    role_label = INTERNAL_QUEST_TOKEN_LABELS.get(objective_role, "依頼対象")
    design: dict[str, Any] = {
        "name": base_name,
        "display_alias": base_name,
        "role_label": role_label,
        "description": str(response.get("objective_npc_description") or response.get("objective") or quest.overview),
        "personality": str(response.get("objective_npc_personality") or ""),
        "look": "",
        "species": "",
        "category": "quest_objective",
        "hostile": objective_role in {"defeat_target", "blocker"},
        "image_prompt": "",
        "aliases": [role_label],
    }
    if objective_role == "rescue_target":
        return design
    if objective_role == "blocker":
        design.update(
            {
                "display_alias": "妨害者",
                "description": "依頼対象の救出を妨げる存在。具体的な正体や特徴はLLMの生成結果に委ねる。",
                "personality": "侵入者を警戒し、救出対象を逃がさない。",
                "look": "目的地で救出対象を妨げる存在",
                "hostile": True,
                "image_prompt": "fantasy quest blocker, hostile obstacle, quest objective",
                "aliases": ["拘束者", "妨害者"],
            }
        )
        return design
    if objective_role == "defeat_target":
        design.update({"display_alias": "討伐対象", "hostile": True, "aliases": ["討伐対象"]})
    elif objective_role == "delivery_target":
        design.update({"display_alias": "配達先", "hostile": False, "aliases": ["配達先"]})
    return design

def _quest_objective_item_name(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    if not any(str(response.get(key) or "").strip() for key in ("objective_item_name", "target_item_name", "quest_item_name", "item_name", "target_name")):
        text = _quest_destination_source_text(quest, response)
        for word, name in (
            ("\u5b9d\u73e0", "\u4f9d\u983c\u306e\u5b9d\u73e0"),
            ("\u907a\u7269", "\u4f9d\u983c\u306e\u907a\u7269"),
            ("\u6587\u66f8", "\u4f9d\u983c\u306e\u6587\u66f8"),
            ("\u85ac\u8349", "\u4f9d\u983c\u306e\u85ac\u8349"),
            ("\u8a3c\u62e0", "\u4f9d\u983c\u306e\u8a3c\u62e0\u54c1"),
        ):
            if word in text:
                return name
    for key in ("objective_item_name", "target_item_name", "quest_item_name", "item_name", "target_name"):
        value = str(response.get(key) or "").strip()
        if value:
            return _strip_generated_name_notes(value) or "依頼品"
    text = _quest_destination_source_text(quest, response)
    for word, name in (
        ("宝珠", "依頼の宝珠"),
        ("遺物", "依頼の遺物"),
        ("文書", "依頼の文書"),
        ("薬草", "依頼の薬草"),
        ("証拠", "依頼の証拠品"),
    ):
        if word in text:
            return name
    return f"{quest.name}の依頼品"

def _quest_delivery_target_name(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    for key in ("delivery_target_name", "recipient_name", "target_npc_name", "target_name"):
        value = str(response.get(key) or "").strip()
        if value:
            return _clean_generated_name(value, "\u914d\u9054\u5148", kind="character")
    text = _quest_destination_source_text(quest, response)
    for word, name in (
        ("\u935b\u51b6", "\u935b\u51b6\u5c4b"),
        ("\u5bbf\u5c4b", "\u5bbf\u5c4b\u306e\u4e3b"),
        ("\u85ac", "\u85ac\u5e2b"),
        ("\u30ae\u30eb\u30c9", "\u30ae\u30eb\u30c9\u4fc2\u54e1"),
        ("\u6751\u9577", "\u6751\u9577"),
    ):
        if word in text:
            return name
    return f"{quest.name}\u306e\u914d\u9054\u5148"

def _quest_delivery_item_name(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    for key in ("delivery_item_name", "objective_item_name", "quest_item_name", "item_name"):
        value = str(response.get(key) or "").strip()
        if value:
            return _strip_generated_name_notes(value) or "\u914d\u9054\u54c1"
    text = _quest_destination_source_text(quest, response)
    for word, name in (
        ("\u624b\u7d19", "\u4f9d\u983c\u306e\u624b\u7d19"),
        ("\u5305\u307f", "\u4f9d\u983c\u306e\u5305\u307f"),
        ("\u8377\u7269", "\u4f9d\u983c\u306e\u8377\u7269"),
        ("\u6587\u66f8", "\u4f9d\u983c\u306e\u6587\u66f8"),
    ):
        if word in text:
            return name
    return f"{quest.name}\u306e\u914d\u9054\u54c1"

def _quest_objective_item_category(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    explicit = str(response.get("objective_item_category") or response.get("item_category") or "").strip()
    if explicit:
        return explicit
    text = _quest_destination_source_text(quest, response)
    if any(word in text for word in ("\u6587\u66f8", "\u624b\u7d19", "\u66f8\u985e", "document", "letter")):
        return "document"
    if any(word in text for word in ("\u5dfb\u7269", "scroll")):
        return "scroll"
    if any(word in text for word in ("\u85ac\u8349", "\u82b1", "\u8349", "plant", "herb")):
        return "material_plant"
    if any(word in text for word in ("\u5b9d\u77f3", "\u5b9d\u73e0", "gem", "jewel")):
        return "material_gem"
    if any(word in text for word in ("\u907a\u7269", "\u8056\u907a\u7269", "relic", "artifact")):
        return "relic"
    if any(word in text for word in ("文書", "手紙", "書類", "document", "letter")):
        return "document"
    if any(word in text for word in ("巻物", "scroll")):
        return "scroll"
    if any(word in text for word in ("薬草", "花", "草", "plant", "herb")):
        return "material_plant"
    if any(word in text for word in ("宝石", "宝珠", "gem", "jewel")):
        return "material_gem"
    if any(word in text for word in ("遺物", "聖遺物", "relic", "artifact")):
        return "relic"
    return "treasure"

def _quest_objective_npc_action(action: str) -> bool:
    text = str(action or "").casefold()
    if any(
        word in str(action or "")
        for word in (
            "\u6551\u51fa",
            "\u6551\u52a9",
            "\u52a9\u3051",
            "\u4fdd\u8b77",
            "\u89e3\u653e",
            "\u9023\u308c\u3066",
            "\u9023\u308c\u5e30",
            "\u8b77\u9001",
            "\u8a71\u3057\u304b\u3051",
            "\u7121\u4e8b",
        )
    ):
        return True
    return any(word in text for word in ("rescue", "save", "escort", "free", "protect", "help")) or any(
        word in str(action or "")
        for word in ("救出", "救助", "助け", "保護", "解放", "連れて", "連れ帰", "護送", "話しかけ", "無事")
    )

def _quest_objective_item_action(action: str) -> bool:
    text = str(action or "").casefold()
    if any(
        word in str(action or "")
        for word in (
            "\u62fe",
            "\u53d6",
            "\u56de\u53ce",
            "\u63a1\u53d6",
            "\u53ce\u96c6",
            "\u63a2",
            "\u8abf\u3079",
            "\u6301\u3061\u5e30",
            "\u5165\u624b",
            "\u78ba\u4fdd",
        )
    ):
        return True
    return any(word in text for word in ("take", "pick", "collect", "retrieve", "search", "obtain", "bring back")) or any(
        word in str(action or "")
        for word in ("拾", "取", "回収", "採取", "収集", "探", "調べ", "持ち帰", "入手", "確保")
    )

def _quest_delivery_action(action: str) -> bool:
    text = str(action or "").casefold()
    return any(word in text for word in ("deliver", "hand over", "give", "pass to", "bring to")) or any(
        word in str(action or "")
        for word in ("\u6e21", "\u5c4a\u3051", "\u624b\u6e21", "\u914d\u9054", "\u7d0d\u54c1", "\u9810\u3051")
    )

def _quest_investigation_action(action: str) -> bool:
    text = str(action or "").casefold()
    return any(word in text for word in ("investigate", "inspect", "survey", "examine", "research", "search")) or any(
        word in str(action or "")
        for word in (
            "\u8abf\u67fb",
            "\u8abf\u3079",
            "\u63a2\u308b",
            "\u63a2\u7d22",
            "\u78ba\u8a8d",
            "\u8e0f\u67fb",
            "\u89b3\u5bdf",
            "\u8a18\u9332",
            "\u63a1\u5bf8",
        )
    )

def _quest_procurement_action(action: str) -> bool:
    text = str(action or "").casefold()
    return any(word in text for word in ("submit", "turn in", "hand over", "deliver", "give", "procure")) or any(
        word in str(action or "")
        for word in (
            "\u6e21",
            "\u624b\u6e21",
            "\u7d0d\u54c1",
            "\u63d0\u51fa",
            "\u8abf\u9054",
            "\u5c4a\u3051",
            "\u6301\u3063\u3066\u304d",
            "\u6301\u3061\u8fbc",
            "\u7528\u610f",
            "\u5831\u544a",
        )
    )

def _quest_captor_resolution_action(action: str) -> bool:
    text = str(action or "").casefold()
    return any(word in text for word in ("negotiate", "persuade", "convince", "defeat", "drive away", "neutralize")) or any(
        word in str(action or "")
        for word in ("\u4ea4\u6e09", "\u8aac\u5f97", "\u8a71\u3057\u5408", "\u89e3\u6c7a", "\u7121\u529b\u5316", "\u8ffd\u3044\u6255", "\u8a0e\u4f10", "\u5012")
    )

def _quest_completion_report_action(action: str) -> bool:
    original = str(action or "").strip()
    if original == QUEST_REPORT_CHOICE_LABEL:
        return True
    text = original.casefold()
    if any(
        phrase in original
        for phrase in (
            "依頼を報告",
            "依頼の報告",
            "依頼完了",
            "クエスト報告",
            "ギルドに報告",
            "受付に報告",
            "報告する",
            "達成報告",
            "完了報告",
            "報酬をもら",
            "報酬を受け取",
            "報酬を請求",
        )
    ):
        return True
    return any(word in text for word in ("report quest", "turn in quest", "claim reward"))

def _apply_quest_encounter_outcome(self, encounter: dict[str, Any], outcome: dict[str, Any]) -> list[str]:
    if not self.state.active_quest or not (_as_bool(outcome.get("ended")) or _as_bool(outcome.get("opponent_defeated"))):
        return []
    quest = self._find_quest_by_name(self.state.active_quest)
    if not quest or quest.status != "active":
        return []
    opponent_uuid = str(outcome.get("defeated_opponent_uuid") or encounter.get("opponent_uuid") or "").strip()
    if not opponent_uuid:
        opponent_name = str(outcome.get("defeated_opponent_name") or encounter.get("opponent_name") or "")
        opponent = self.state.world_data.character(opponent_name)
        opponent_uuid = str(opponent.uuid if opponent else "")
    if not opponent_uuid:
        return []
    opponent_state = str(outcome.get("opponent_state") or "").strip().lower()
    opponent_dead = _as_bool(outcome.get("opponent_defeated")) or opponent_state in {"dead", "corpse", "killed"} or int(encounter.get("opponent_hp") or 0) <= 0
    opponent_gone = opponent_state in {"gone", "fled", "retreated", "neutralized"}
    if not opponent_dead and not opponent_gone:
        return []
    lines: list[str] = []
    pack = self._quest_objective_pack(quest)
    for entry in pack.get("npcs", []):
        if not isinstance(entry, dict) or str(entry.get("uuid") or "") != opponent_uuid:
            continue
        role = str(entry.get("role") or "")
        if role == "defeat_target":
            if not opponent_dead:
                continue
            entry["status"] = "defeated"
            pack["status"] = QUEST_REPORT_STAGE
            quest.extra["quest_stage"] = QUEST_REPORT_STAGE
            self._set_quest_flag(quest, "objective_defeated", True)
            self._set_quest_flag(quest, "ready_to_report", True)
            lines.append(f"> [Quest] 討伐対象を倒しました: {entry.get('name')}")
        elif role == "blocker":
            entry["status"] = "defeated" if opponent_dead else "neutralized"
            self._set_quest_flag(quest, "blocker_resolved", True)
            lines.append(f"> [Quest] 妨害者を排除しました: {entry.get('name')}")
    return lines

def _initialize_quest_state(
    self,
    quest: QuestData,
    destination: dict[str, Any],
    response: dict[str, Any] | None = None,
) -> list[str]:
    quest_type = _quest_type(quest, response)
    if quest_type not in QUEST_TYPES:
        quest_type = "retrieve"
    quest.status = "active"
    origin = self._quest_origin_location(quest)
    origin_subnode = self._quest_origin_subnode_id(origin)
    start_hours = self._world_time_total_hours()
    quest.extra["quest_type"] = quest_type
    quest.extra["quest_stage"] = "accepted"
    quest.extra["quest_flags"] = {
        "objective_found": False,
        "objective_retrieved": False,
        "objective_rescued": False,
        "objective_defeated": False,
        "objective_investigated": False,
        "delivery_completed": False,
        "procurement_completed": False,
        "ready_to_report": False,
        "reported": False,
    }
    quest.extra["origin_location"] = origin
    quest.extra["report_location"] = origin
    quest.extra["origin_subnode_id"] = origin_subnode
    quest.extra["report_subnode_id"] = origin_subnode
    quest.extra["start_hours"] = start_hours
    quest.extra["deadline_hours"] = start_hours + QUEST_DEADLINE_HOURS
    quest.extra["deadline_label"] = self._world_time_label(start_hours + QUEST_DEADLINE_HOURS)
    quest.extra["destination"] = destination
    quest_type_label = INTERNAL_QUEST_TOKEN_LABELS.get(quest_type, quest_type)
    return [
        f"> [Quest] 依頼を受注しました: {quest_type_label} / 報告先: {origin} / 期限: {QUEST_DEADLINE_HOURS}時間"
    ]

def _quest_objective_pack(self, quest: QuestData) -> dict[str, Any]:
    raw = quest.extra.get("objective_entities")
    if not isinstance(raw, dict):
        raw = {"version": 3, "npcs": [], "items": [], "markers": [], "requirements": [], "flags": {}}
        quest.extra["objective_entities"] = raw
    raw.setdefault("version", 3)
    if not isinstance(raw.get("npcs"), list):
        raw["npcs"] = []
    if not isinstance(raw.get("items"), list):
        raw["items"] = []
    if not isinstance(raw.get("markers"), list):
        raw["markers"] = []
    if not isinstance(raw.get("requirements"), list):
        raw["requirements"] = []
    if not isinstance(raw.get("flags"), dict):
        raw["flags"] = {}
    return raw

def _ensure_quest_objective_entities(
    self,
    quest: QuestData,
    destination: dict[str, Any],
    response: dict[str, Any] | None = None,
) -> list[str]:
    pack = self._quest_objective_pack(quest)
    if pack.get("npcs") or pack.get("items") or pack.get("markers") or pack.get("requirements"):
        return []
    quest_type = str(quest.extra.get("quest_type") or _quest_type(quest, response)).strip().lower()
    if quest_type not in QUEST_TYPES:
        quest_type = "retrieve"
    location_name = str(destination.get("location") or quest.extra.get("objective_location") or "").strip()
    if not location_name:
        return []
    location = self.state.world_data.ensure_location(location_name)
    subnode_id = str(destination.get("objective_subnode_id") or quest.extra.get("objective_subnode_id") or "").strip()
    if subnode_id:
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        if subnode_id not in graph.get("nodes", {}):
            subnode_id = ""
    if not subnode_id:
        subnode_id = self._default_subnode_for_location(location)
    pack["location"] = location_name
    pack["subnode_id"] = subnode_id
    pack["status"] = "waiting"
    pack["quest_type"] = quest_type
    pack["flags"] = dict(quest.extra.get("quest_flags") if isinstance(quest.extra.get("quest_flags"), dict) else {})
    if quest_type == "rescue":
        entry = self._create_quest_objective_npc(quest, location_name, subnode_id, response, objective_role="rescue_target")
        pack["npcs"].append(entry)
        lines = [f"> [Quest] 救出対象を配置しました: {entry.get('name')}"]
        if _quest_requires_captor(quest, response):
            blocker = self._create_quest_objective_npc(quest, location_name, subnode_id, response, objective_role="blocker")
            pack["npcs"].append(blocker)
            pack["flags"]["blocker_required"] = True
            lines.append(f"> [Quest] 妨害者を配置しました: {blocker.get('name')}")
        return lines
    if quest_type == "defeat":
        entry = self._create_quest_objective_npc(quest, location_name, subnode_id, response, objective_role="defeat_target")
        pack["npcs"].append(entry)
        return [f"> [Quest] 討伐対象を配置しました: {entry.get('name')}"]
    if quest_type == "delivery":
        target = self._create_quest_objective_npc(quest, location_name, subnode_id, response, objective_role="delivery_target")
        pack["npcs"].append(target)
        item = self._create_quest_delivery_item(quest, response)
        pack["items"].append(item)
        return [
            f"> [Quest] 配達先を配置しました: {target.get('name')}",
            f"> [Quest] 配達品を受け取りました: {item.get('name')}",
        ]
    if quest_type == "investigate":
        marker = self._create_quest_investigation_marker(quest, location_name, subnode_id, response)
        pack["markers"].append(marker)
        return [f"> [Quest] 調査地点を設定しました: {marker.get('name')}"]
    if quest_type == "procure":
        requirement = self._create_quest_procurement_requirement(quest, response)
        pack["requirements"].append(requirement)
        return [f"> [Quest] 調達条件を設定しました: {requirement.get('name')}"]
    entry = self._create_quest_objective_item(quest, location_name, subnode_id, response, objective_role="retrieve_item")
    pack["items"].append(entry)
    return [f"> [Quest] 回収品を配置しました: {entry.get('name')}"]

def _quest_objective_npc_design(
    self,
    quest: QuestData,
    location_name: str,
    subnode_id: str,
    response: dict[str, Any],
    *,
    objective_role: str,
) -> dict[str, Any]:
    return npc_generate.quest_objective_npc_design(
        self,
        quest,
        location_name,
        subnode_id,
        response,
        objective_role=objective_role,
    )

def _create_quest_objective_npc(
    self,
    quest: QuestData,
    location_name: str,
    subnode_id: str,
    response: dict[str, Any] | None = None,
    *,
    objective_role: str = "rescue_target",
) -> dict[str, Any]:
    return npc_generate.create_quest_objective_npc(
        self,
        quest,
        location_name,
        subnode_id,
        response,
        objective_role=objective_role,
    )

def _create_quest_objective_item(
    self,
    quest: QuestData,
    location_name: str,
    subnode_id: str,
    response: dict[str, Any] | None = None,
    *,
    objective_role: str = "retrieve_item",
) -> dict[str, Any]:
    response = response or {}
    item = normalise_item(
        {
            "name": _quest_objective_item_name(quest, response),
            "category": _quest_objective_item_category(quest, response),
            "description": str(response.get("objective_item_description") or response.get("objective") or quest.overview),
            "quantity": 1,
            "rarity": str(response.get("objective_item_rarity") or "common"),
            "tradable": False,
            "stackable": False,
            "source": "quest_objective",
        },
        source="quest_objective",
        fallback_category="relic",
    )
    item["quantity"] = 1
    item["stackable"] = False
    item["tradable"] = False
    item["quest_objective"] = True
    item["quest_name"] = quest.name
    item["quest_objective_kind"] = "item"
    item["quest_objective_role"] = objective_role
    item["quest_location"] = location_name
    item["quest_subnode_id"] = subnode_id
    inventory = self._location_inventory(location_name)
    inventory.append(item)
    return {
        "kind": "item",
        "item_uuid": str(item.get("item_uuid") or ""),
        "name": str(item.get("name") or ""),
        "location": location_name,
        "subnode_id": subnode_id,
        "role": objective_role,
        "status": "waiting",
    }

def _create_quest_delivery_item(self, quest: QuestData, response: dict[str, Any] | None = None) -> dict[str, Any]:
    response = response or {}
    item = normalise_item(
        {
            "name": _quest_delivery_item_name(quest, response),
            "category": _quest_objective_item_category(quest, response),
            "description": str(response.get("delivery_item_description") or response.get("objective") or quest.overview),
            "quantity": 1,
            "rarity": str(response.get("delivery_item_rarity") or "common"),
            "tradable": False,
            "stackable": False,
            "source": "quest_delivery",
        },
        source="quest_delivery",
        fallback_category="document",
    )
    item["quantity"] = 1
    item["stackable"] = False
    item["tradable"] = False
    item["quest_objective"] = True
    item["quest_name"] = quest.name
    item["quest_objective_kind"] = "item"
    item["quest_objective_role"] = "delivery_item"
    added = add_item_stack(self._player_inventory(), item, source="quest_delivery")
    if added:
        self._sync_player_inventory()
    item_uuid = str((added or item).get("item_uuid") or "")
    return {
        "kind": "item",
        "item_uuid": item_uuid,
        "name": str(item.get("name") or ""),
        "location": quest.extra.get("origin_location") or self._quest_origin_location(quest),
        "subnode_id": quest.extra.get("origin_subnode_id") or "",
        "role": "delivery_item",
        "status": "carrying",
    }

def _create_quest_investigation_marker(
    self,
    quest: QuestData,
    location_name: str,
    subnode_id: str,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = response or {}
    return {
        "kind": "marker",
        "uuid": uuid4().hex,
        "name": _quest_investigation_point_name(quest, response),
        "description": str(response.get("investigation_description") or response.get("objective") or quest.overview),
        "location": location_name,
        "subnode_id": subnode_id,
        "role": "investigation_point",
        "status": "waiting",
    }

def _create_quest_procurement_requirement(
    self,
    quest: QuestData,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = response or {}
    return {
        "kind": "requirement",
        "uuid": uuid4().hex,
        "name": _quest_procurement_requirement_name(quest, response),
        "description": _quest_procurement_requirement_text(quest, response),
        "role": "procurement_requirement",
        "status": "waiting",
        "accepted_item_uuid": "",
        "accepted_item_name": "",
        "checker_reason": "",
    }

def _quest_objective_character(self, entry: dict[str, Any]) -> Character | None:
    target_uuid = str(entry.get("uuid") or "").strip()
    if not target_uuid:
        return None
    for character in self.state.world_data.characters.values():
        if str(character.uuid) == target_uuid:
            return character
    return None

def _quest_objective_item_in_player_inventory(self, item_uuid: str) -> dict[str, Any] | None:
    item_uuid = str(item_uuid or "").strip()
    if not item_uuid:
        return None
    for raw in self._player_inventory():
        item = normalise_item(raw, source="player")
        if item_uuid in [str(value) for value in _as_list(item.get("item_uuids"))]:
            return item
    return None

def _quest_objective_item_in_location_inventory(self, location_name: str, item_uuid: str) -> dict[str, Any] | None:
    item_uuid = str(item_uuid or "").strip()
    if not item_uuid:
        return None
    for raw in self._location_inventory(location_name):
        item = normalise_item(raw, source="location")
        if item_uuid in [str(value) for value in _as_list(item.get("item_uuids"))]:
            return item
    return None

def _quest_procurement_candidates(self, action: str) -> list[dict[str, Any]]:
    action_text = str(action or "")
    candidates: list[dict[str, Any]] = []
    for index, raw in enumerate(list(self._player_inventory())):
        if not isinstance(raw, dict):
            continue
        item = normalise_item(raw, source="procurement")
        self._player_inventory()[index] = item
        quantity = max(1, _safe_int(item.get("quantity"), 1))
        uuids = [str(value) for value in _as_list(item.get("item_uuids"))] or [str(item.get("item_uuid") or "")]
        for offset in range(quantity):
            item_uuid = uuids[offset] if offset < len(uuids) else str(item.get("item_uuid") or "")
            if not item_uuid:
                continue
            single = dict(item)
            single["quantity"] = 1
            single["item_uuid"] = item_uuid
            single["item_uuids"] = [item_uuid]
            name = str(single.get("name") or "")
            category = str(single.get("category") or "")
            description = str(single.get("description") or "")
            score = 0
            if name and name in action_text:
                score += 100 + len(name)
            if category and category in action_text:
                score += 20
            if any(word and word in action_text for word in _quest_procurement_category_words(category)):
                score += 15
            candidates.append(
                {
                    "item_uuid": item_uuid,
                    "name": name,
                    "category": category,
                    "description": _short_text(description, 240),
                    "rarity": str(single.get("rarity") or ""),
                    "value": single.get("value"),
                    "_score": score,
                }
            )
    candidates.sort(key=lambda entry: (int(entry.get("_score") or 0), len(str(entry.get("name") or ""))), reverse=True)
    return [{key: value for key, value in entry.items() if key != "_score"} for entry in candidates[:18]]

def _quest_procurement_checker(
    self,
    quest: QuestData,
    action: str,
    requirement: dict[str, Any],
) -> dict[str, Any]:
    candidates = self._quest_procurement_candidates(action)
    if not candidates:
        return {"accepted": False, "item_uuid": "", "reason": "no player inventory candidate"}
    messages = [
        {
            "role": "system",
            "content": (
                "You judge only whether one player inventory item satisfies a procurement quest request. "
                "Return JSON only. Do not decide quest completion or failure. "
                "If an item is acceptable, return accepted=true and the exact item_uuid from candidates. "
                "If none fits, return accepted=false and item_uuid=\"\"."
            ),
        },
        {
            "role": "user",
            "content": (
                f"quest: {_ai_json(_quest_ai_context(quest, include_log=False, include_extra=True))}\n"
                f"procurement_requirement: {_ai_json(requirement)}\n"
                f"player_action: {action}\n"
                f"player_inventory_candidates: {_ai_json(candidates)}\n"
                "Judge whether the player is intentionally submitting a suitable item for this procurement request. "
                "Use semantic fit, not exact name matching only. For example, a healing potion can satisfy a request "
                "for a potion effective on wounds. Return accepted, item_uuid, item_name, reason."
            ),
        },
    ]
    try:
        response = self._chat_json(
            "quest_procurement_checker",
            messages,
            max_tokens=400,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )
    except Exception as exc:
        return {"accepted": False, "item_uuid": "", "reason": f"procurement check failed: {exc}"}
    accepted = _as_bool(
        response.get("accepted")
        or response.get("acceptable")
        or response.get("is_acceptable")
        or response.get("matched")
    )
    item_uuid = str(response.get("item_uuid") or response.get("accepted_item_uuid") or response.get("uuid") or "").strip()
    valid_uuids = {str(item.get("item_uuid") or "") for item in candidates}
    if accepted and item_uuid in valid_uuids:
        response["accepted"] = True
        response["item_uuid"] = item_uuid
        return response
    response["accepted"] = False
    if item_uuid and item_uuid not in valid_uuids:
        response["reason"] = str(response.get("reason") or "returned item_uuid is not in player inventory candidates")
    return response

def _at_quest_objective_place(self, quest: QuestData, location: str) -> bool:
    pack = self._quest_objective_pack(quest)
    target_location = str(pack.get("location") or quest.extra.get("objective_location") or "").strip()
    if not target_location or target_location != str(location or "").strip():
        return False
    target_subnode = str(pack.get("subnode_id") or quest.extra.get("objective_subnode_id") or "").strip()
    if not target_subnode:
        return True
    try:
        return self._current_subnode_id(target_location) == target_subnode
    except Exception:
        return True

def _quest_flags(self, quest: QuestData) -> dict[str, Any]:
    flags = quest.extra.get("quest_flags")
    if not isinstance(flags, dict):
        flags = {}
        quest.extra["quest_flags"] = flags
    pack = self._quest_objective_pack(quest)
    pack_flags = pack.get("flags")
    if isinstance(pack_flags, dict):
        flags.update({key: value for key, value in pack_flags.items() if key not in flags})
    pack["flags"] = flags
    return flags

def _set_quest_flag(self, quest: QuestData, key: str, value: Any = True) -> None:
    flags = self._quest_flags(quest)
    flags[str(key)] = value
    self._quest_objective_pack(quest)["flags"] = flags

def _quest_entries_by_role(self, quest: QuestData, role: str, group: str = "npcs") -> list[dict[str, Any]]:
    pack = self._quest_objective_pack(quest)
    entries = pack.get(group, [])
    return [
        entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("role") or "").strip() == role
    ]

def _quest_blockers_resolved(self, quest: QuestData) -> bool:
    blockers = self._quest_entries_by_role(quest, "blocker", "npcs")
    if not blockers:
        return True
    return all(str(entry.get("status") or "") in {"neutralized", "defeated", "dead", "delivered"} for entry in blockers)

def _refresh_quest_objective_state(self, quest: QuestData) -> None:
    pack = self._quest_objective_pack(quest)
    quest_type = str(quest.extra.get("quest_type") or pack.get("quest_type") or "").strip().lower()
    if quest_type == "retrieve":
        for entry in self._quest_entries_by_role(quest, "retrieve_item", "items"):
            item_uuid = str(entry.get("item_uuid") or "")
            if self._quest_objective_item_in_player_inventory(item_uuid):
                entry["status"] = "retrieved"
                pack["status"] = "retrieved"
                quest.extra["quest_stage"] = "return_to_guild"
                self._set_quest_flag(quest, "objective_retrieved", True)
    elif quest_type == "defeat":
        for entry in self._quest_entries_by_role(quest, "defeat_target", "npcs"):
            character = self._quest_objective_character(entry)
            if character and _character_state_is_dead(character):
                entry["status"] = "defeated"
                pack["status"] = QUEST_REPORT_STAGE
                quest.extra["quest_stage"] = QUEST_REPORT_STAGE
                self._set_quest_flag(quest, "objective_defeated", True)
                self._set_quest_flag(quest, "ready_to_report", True)
    elif quest_type == "rescue":
        if self._quest_blockers_resolved(quest):
            self._set_quest_flag(quest, "blocker_resolved", True)
    elif quest_type == "investigate":
        for entry in self._quest_entries_by_role(quest, "investigation_point", "markers"):
            if str(entry.get("status") or "") in {"investigated", "reported", "delivered"}:
                self._set_quest_flag(quest, "objective_investigated", True)
                quest.extra["quest_stage"] = "return_to_guild"
    elif quest_type == "procure":
        for entry in self._quest_entries_by_role(quest, "procurement_requirement", "requirements"):
            if str(entry.get("status") or "") in {"submitted", "delivered"}:
                self._set_quest_flag(quest, "procurement_completed", True)
                self._set_quest_flag(quest, "ready_to_report", True)
                quest.extra["quest_stage"] = QUEST_REPORT_STAGE

def _apply_quest_objective_action(self, quest: QuestData, action: str, location: str) -> list[str]:
    pack = self._quest_objective_pack(quest)
    lines: list[str] = []
    quest_type = str(quest.extra.get("quest_type") or pack.get("quest_type") or "retrieve").strip().lower()
    if quest_type == "procure":
        if self._quest_report_location_matches(quest, location) and _quest_procurement_action(action):
            for requirement in self._quest_entries_by_role(quest, "procurement_requirement", "requirements"):
                if str(requirement.get("status") or "") in {"submitted", "delivered"}:
                    continue
                decision = self._quest_procurement_checker(quest, action, requirement)
                if not _as_bool(decision.get("accepted")):
                    reason = str(decision.get("reason") or "submitted item did not satisfy the procurement request")
                    requirement["checker_reason"] = reason
                    lines.append(f"> [Quest] Procurement rejected: {reason}")
                    continue
                item_uuid = str(decision.get("item_uuid") or "").strip()
                removed = self._remove_player_item_by_uuid(item_uuid, source="quest_procurement", reason="submitted")
                if not removed:
                    lines.append("> [Quest] 調達品が手元に見つかりません。")
                    continue
                requirement["status"] = "submitted"
                requirement["accepted_item_uuid"] = item_uuid
                requirement["accepted_item_name"] = str(removed.get("name") or decision.get("item_name") or "")
                requirement["checker_reason"] = str(decision.get("reason") or "")
                pack["status"] = QUEST_REPORT_STAGE
                quest.extra["quest_stage"] = QUEST_REPORT_STAGE
                self._set_quest_flag(quest, "procurement_completed", True)
                self._set_quest_flag(quest, "ready_to_report", True)
                self._sync_player_inventory()
                lines.append(f"> [Quest] 調達品を提出しました: {requirement.get('accepted_item_name')}")
        return lines
    if not self._at_quest_objective_place(quest, location):
        return lines
    if quest_type == "rescue":
        if _quest_captor_resolution_action(action):
            for entry in self._quest_entries_by_role(quest, "blocker", "npcs"):
                if str(entry.get("status") or "") not in {"neutralized", "defeated", "dead"}:
                    entry["status"] = "neutralized"
                    self._set_quest_flag(quest, "blocker_resolved", True)
                    lines.append(f"> [Quest] 妨害者を無力化しました: {entry.get('name')}")
        if _quest_objective_npc_action(action):
            if not self._quest_blockers_resolved(quest):
                lines.append("> [Quest] まだ救出できません: 妨害者への対処が必要です。")
                return lines
            for entry in self._quest_entries_by_role(quest, "rescue_target", "npcs"):
                if str(entry.get("status") or "") not in {"waiting", "found"}:
                    continue
                character = self._quest_objective_character(entry)
                if not character or _character_state_is_dead(character):
                    entry["status"] = "lost"
                    continue
                entry["status"] = "escorting"
                pack["status"] = "escorting"
                quest.extra["quest_stage"] = "return_to_guild"
                self._set_quest_flag(quest, "objective_found", True)
                self._set_quest_flag(quest, "objective_rescued", True)
                character.flags["quest_escort"] = True
                character.extra["quest_escort"] = {"quest": quest.name, "origin_location": quest.extra.get("origin_location") or self._quest_origin_location(quest)}
                self._set_character_presence(character, location, "escorted", subnode_id=self._current_subnode_id(location))
                lines.append(f"> [Quest] 救出対象を保護しました: {character.name}")
    elif quest_type == "delivery":
        if _quest_delivery_action(action):
            target_entries = self._quest_entries_by_role(quest, "delivery_target", "npcs")
            item_entries = self._quest_entries_by_role(quest, "delivery_item", "items")
            target_ok = all(self._quest_objective_character(entry) is not None for entry in target_entries)
            delivered_any = False
            if target_ok:
                for entry in item_entries:
                    if str(entry.get("status") or "") == "delivered":
                        delivered_any = True
                        continue
                    item_uuid = str(entry.get("item_uuid") or "")
                    removed = self._remove_player_item_by_uuid(item_uuid, source="quest_delivery", reason="delivered")
                    if removed:
                        entry["status"] = "delivered"
                        delivered_any = True
                        lines.append(f"> [Quest] 配達品を渡しました: {entry.get('name')}")
                if delivered_any:
                    for target in target_entries:
                        target["status"] = "received"
                    pack["status"] = QUEST_REPORT_STAGE
                    quest.extra["quest_stage"] = QUEST_REPORT_STAGE
                    self._set_quest_flag(quest, "delivery_completed", True)
                    self._set_quest_flag(quest, "ready_to_report", True)
            else:
                lines.append("> [Quest] Delivery target is not present.")
    elif quest_type == "retrieve":
        if _quest_objective_item_action(action):
            for entry in self._quest_entries_by_role(quest, "retrieve_item", "items"):
                if str(entry.get("status") or "") not in {"waiting", "found"}:
                    continue
                item_uuid = str(entry.get("item_uuid") or "")
                if self._quest_objective_item_in_player_inventory(item_uuid):
                    entry["status"] = "retrieved"
                    pack["status"] = "retrieved"
                    quest.extra["quest_stage"] = "return_to_guild"
                    self._set_quest_flag(quest, "objective_retrieved", True)
                    continue
                location_item = self._quest_objective_item_in_location_inventory(location, item_uuid)
                if not location_item:
                    continue
                if not self.can_add_player_item(location_item, source="quest_objective"):
                    lines.append(self._inventory_full_line(location_item))
                    continue
                removed = self._remove_item_uuid_from_inventory(self._location_inventory(location), item_uuid, source="quest_objective", reason="retrieve")
                if not removed:
                    continue
                added = self._add_player_item_stack(removed, source="quest_objective")
                if added:
                    entry["status"] = "retrieved"
                    pack["status"] = "retrieved"
                    quest.extra["quest_stage"] = "return_to_guild"
                    self._set_quest_flag(quest, "objective_retrieved", True)
                    lines.append(f"> [Quest] 依頼品を回収しました: {entry.get('name')}")
                else:
                    self._location_inventory(location).append(removed)
                    lines.append(self._inventory_full_line(removed))
    elif quest_type == "investigate":
        if _quest_investigation_action(action):
            for entry in self._quest_entries_by_role(quest, "investigation_point", "markers"):
                if str(entry.get("status") or "") not in {"waiting", "found"}:
                    continue
                entry["status"] = "investigated"
                pack["status"] = "investigated"
                quest.extra["quest_stage"] = "return_to_guild"
                self._set_quest_flag(quest, "objective_found", True)
                self._set_quest_flag(quest, "objective_investigated", True)
                lines.append(f"> [Quest] 調査を完了しました: {entry.get('name')}")
    return lines

def _sync_quest_objective_escorts(self, location: str, *, subnode_id: str = "") -> None:
    quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
    if not quest:
        return
    pack = self._quest_objective_pack(quest)
    if str(pack.get("status") or "") not in {"escorting", "retrieved"}:
        return
    subnode_id = subnode_id or self._runtime_subnode_for_presence(location)
    delivered_any = False
    at_report_location = self.is_current_location_guild() and self._quest_report_location_matches(quest, location)
    for entry in pack.get("npcs", []):
        if not isinstance(entry, dict) or str(entry.get("status") or "") != "escorting":
            continue
        character = self._quest_objective_character(entry)
        if character and not _character_state_is_dead(character):
            if at_report_location:
                entry["status"] = "delivered"
                character.flags.pop("quest_escort", None)
                character.extra.pop("quest_escort", None)
                self._set_character_presence(character, location, "present", subnode_id=subnode_id)
                delivered_any = True
            else:
                self._set_character_presence(character, location, "escorted", subnode_id=subnode_id)
    if delivered_any:
        pack["status"] = QUEST_REPORT_STAGE
        quest.extra["quest_stage"] = QUEST_REPORT_STAGE
        self._set_quest_flag(quest, "objective_rescued", True)
        self._set_quest_flag(quest, "ready_to_report", True)

def _quest_objective_completion_allowed(
    self,
    quest: QuestData,
    action: str,
    location: str,
    response: dict[str, Any] | None = None,
) -> bool:
    pack = self._quest_objective_pack(quest)
    has_objectives = bool(pack.get("npcs") or pack.get("items") or pack.get("markers") or pack.get("requirements"))
    if not has_objectives:
        return False
    if not self._quest_objectives_returned(quest, location):
        return False
    if _quest_completion_report_action(action):
        return True
    return False

def _quest_objectives_returned(self, quest: QuestData, location: str) -> bool:
    self._refresh_quest_objective_state(quest)
    if not self._quest_report_location_matches(quest, location):
        return False
    pack = self._quest_objective_pack(quest)
    quest_type = str(quest.extra.get("quest_type") or pack.get("quest_type") or "").strip().lower()
    flags = self._quest_flags(quest)
    if quest_type == "rescue":
        if not self._quest_blockers_resolved(quest):
            return False
        rescue_entries = self._quest_entries_by_role(quest, "rescue_target", "npcs")
        if not rescue_entries:
            return False
        for entry in rescue_entries:
            character = self._quest_objective_character(entry)
            if not character or _character_state_is_dead(character):
                return False
            if str(entry.get("status") or "") not in {"escorting", "delivered"}:
                return False
        return bool(flags.get("objective_rescued"))
    if quest_type == "retrieve":
        item_entries = self._quest_entries_by_role(quest, "retrieve_item", "items")
        if not item_entries:
            return False
        for entry in item_entries:
            item_uuid = str(entry.get("item_uuid") or "")
            if str(entry.get("status") or "") == "delivered":
                continue
            if not self._quest_objective_item_in_player_inventory(item_uuid):
                return False
        return bool(flags.get("objective_retrieved"))
    if quest_type == "defeat":
        target_entries = self._quest_entries_by_role(quest, "defeat_target", "npcs")
        if not target_entries:
            return False
        return all(str(entry.get("status") or "") in {"defeated", "dead"} for entry in target_entries) and bool(flags.get("objective_defeated"))
    if quest_type == "delivery":
        item_entries = self._quest_entries_by_role(quest, "delivery_item", "items")
        target_entries = self._quest_entries_by_role(quest, "delivery_target", "npcs")
        if not item_entries or not target_entries:
            return False
        return (
            all(str(entry.get("status") or "") == "delivered" for entry in item_entries)
            and all(str(entry.get("status") or "") in {"received", "delivered"} for entry in target_entries)
            and bool(flags.get("delivery_completed"))
        )
    if quest_type == "investigate":
        marker_entries = self._quest_entries_by_role(quest, "investigation_point", "markers")
        if not marker_entries:
            return False
        return (
            all(str(entry.get("status") or "") in {"investigated", "reported", "delivered"} for entry in marker_entries)
            and bool(flags.get("objective_investigated"))
        )
    if quest_type == "procure":
        requirements = self._quest_entries_by_role(quest, "procurement_requirement", "requirements")
        if not requirements:
            return False
        return (
            all(str(entry.get("status") or "") in {"submitted", "delivered"} for entry in requirements)
            and bool(flags.get("procurement_completed"))
        )
    return False

def _quest_report_location_matches(self, quest: QuestData, location: str) -> bool:
    location = str(location or "").strip()
    origin = str(quest.extra.get("report_location") or quest.extra.get("origin_location") or quest.neighboring_settlement or "").strip()
    if not origin:
        origin = self._quest_origin_location(quest)
    settlement = self._current_settlement_location()
    if not (location and origin and (location == origin or (settlement and settlement.name == origin))):
        return False
    report_subnode = str(quest.extra.get("report_subnode_id") or quest.extra.get("origin_subnode_id") or "").strip()
    if self.is_current_location_guild():
        return True
    if not report_subnode:
        return True
    try:
        return self._current_subnode_id(origin) == report_subnode
    except Exception:
        return False

def _settle_rescued_quest_character(
    self,
    quest: QuestData,
    entry: dict[str, Any],
    character: Character,
    origin: str,
    *,
    source: str,
) -> dict[str, Any]:
    world = self.state.world_data
    settlement_name = str(origin or "").strip()
    settlement = world.locations.get(settlement_name) if settlement_name else None
    if settlement is None or not _is_settlement_location(settlement):
        current_settlement = self._current_settlement_location()
        if current_settlement:
            settlement = current_settlement
            settlement_name = current_settlement.name
    if not settlement_name:
        settlement_name = self.state.current_location or world.starting_location
        settlement = world.locations.get(settlement_name)
    if settlement_name and settlement_name not in world.locations:
        world.ensure_location(settlement_name)
    home_subnode_id = self._random_settlement_home_subnode(settlement_name, character.uuid or character.name)
    character.flags.pop("quest_escort", None)
    character.extra.pop("quest_escort", None)
    character.flags["quest_rescue_settled"] = True
    character.flags["hostile"] = False
    character.extra["home_location"] = settlement_name
    character.extra["origin_location"] = settlement_name
    character.extra["spawn_location"] = settlement_name
    if home_subnode_id:
        character.extra["home_subnode_id"] = home_subnode_id
        character.extra["origin_subnode_id"] = home_subnode_id
        character.extra["spawn_subnode_id"] = home_subnode_id
    self._set_character_presence(character, settlement_name or self.state.current_location, "present", subnode_id=home_subnode_id)
    entry["status"] = "delivered"
    entry["home_location"] = settlement_name
    entry["home_subnode_id"] = home_subnode_id
    entry["settled_source"] = source
    return {
        "uuid": character.uuid,
        "name": character.name,
        "status": "delivered",
        "home_location": settlement_name,
        "home_subnode_id": home_subnode_id,
    }

def _complete_quest_objectives(self, quest: QuestData, *, source: str) -> dict[str, Any]:
    pack = self._quest_objective_pack(quest)
    result: dict[str, Any] = {"npcs": [], "items": []}
    origin = str(quest.extra.get("origin_location") or self._quest_origin_location(quest))
    current_subnode = self._runtime_subnode_for_presence(origin) if origin == self.state.current_location else ""
    for entry in pack.get("npcs", []):
        if not isinstance(entry, dict):
            continue
        character = self._quest_objective_character(entry)
        if character and not _character_state_is_dead(character):
            if (
                str(quest.extra.get("quest_type") or pack.get("quest_type") or "").strip().lower() == "rescue"
                and str(entry.get("role") or "").strip() == "rescue_target"
            ):
                result["npcs"].append(self._settle_rescued_quest_character(quest, entry, character, origin, source=source))
                continue
            character.flags.pop("quest_escort", None)
            character.extra.pop("quest_escort", None)
            self._set_character_presence(character, origin or self.state.current_location, "present", subnode_id=current_subnode)
            entry["status"] = "delivered"
            result["npcs"].append({"uuid": character.uuid, "name": character.name, "status": "delivered"})
    for entry in pack.get("items", []):
        if not isinstance(entry, dict):
            continue
        item_uuid = str(entry.get("item_uuid") or "")
        if str(entry.get("status") or "") == "submitted":
            entry["status"] = "delivered"
            result["items"].append({"item_uuid": item_uuid, "name": entry.get("name"), "delivered": True})
            continue
        removed = self._remove_player_item_by_uuid(item_uuid, source=source, reason="quest_delivered")
        entry["status"] = "delivered" if removed else str(entry.get("status") or "")
        result["items"].append({"item_uuid": item_uuid, "name": entry.get("name"), "delivered": bool(removed)})
    for entry in pack.get("markers", []):
        if not isinstance(entry, dict):
            continue
        entry["status"] = "delivered" if str(entry.get("status") or "") in {"investigated", "reported", "delivered"} else str(entry.get("status") or "")
    for entry in pack.get("requirements", []):
        if not isinstance(entry, dict):
            continue
        entry["status"] = "delivered" if str(entry.get("status") or "") in {"submitted", "delivered"} else str(entry.get("status") or "")
    pack["status"] = "delivered"
    self._sync_player_inventory()
    return result

def _close_quest_objectives(self, quest: QuestData, status: str, *, source: str) -> dict[str, Any]:
    pack = self._quest_objective_pack(quest)
    pack["status"] = status
    for group in ("npcs", "items", "markers", "requirements"):
        for entry in pack.get(group, []):
            if isinstance(entry, dict) and str(entry.get("status") or "") not in {"delivered", "lost"}:
                entry["status"] = status
    return {"status": status, "source": source}

