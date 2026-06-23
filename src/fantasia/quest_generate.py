from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

from .items import ITEM_CATEGORY_IDS, choose_item_template

QUEST_PLAN_DUNGEON_SUBTYPES = ("forest", "mountain", "ruin", "temple")

QUEST_PLAN_TYPES = ("rescue", "retrieve", "defeat", "delivery", "investigate", "procure")

QUEST_DELIVERY_ITEM_CATEGORIES = ("document", "medicine", "potion", "food", "tool", "material_common", "material_magical")
QUEST_HARVEST_ITEM_CATEGORIES = ("material_plant",)
QUEST_PROCUREMENT_ITEM_CATEGORIES = tuple(
    category
    for category in ITEM_CATEGORY_IDS
    if not category.startswith("weapon_")
    and not category.startswith("armor_")
    and not category.startswith("accessory_")
)


def _quest_plan_item_categories(quest_type: str) -> tuple[str, ...]:
    if quest_type == "delivery":
        return QUEST_DELIVERY_ITEM_CATEGORIES
    if quest_type == "procure":
        return QUEST_PROCUREMENT_ITEM_CATEGORIES
    if quest_type == "retrieve":
        return QUEST_HARVEST_ITEM_CATEGORIES
    return ()


def _quest_generation_item_template(
    world: WorldData,
    settlement_name: str,
    plan_index: int,
    quest_type: str,
    danger: int,
) -> dict[str, Any]:
    categories = _quest_plan_item_categories(quest_type)
    if not categories:
        return {}
    return choose_item_template(
        categories,
        max_level=danger,
        seed=f"quest-objective-item|{world.world_name}|{settlement_name}|{plan_index}|{quest_type}|{danger}",
        context=settlement_name,
    ) or {}


def _quest_generation_plan(
    self,
    world: WorldData,
    settlement_name: str,
    plan_index: int,
) -> dict[str, Any]:
    settlement_danger = self._current_location_danger(settlement_name)
    low = max(1, _clamp_world_danger(settlement_danger))
    high = max(low, _clamp_world_danger(settlement_danger + 5))
    rng = random.Random(f"quest-plan|{world.world_name}|{settlement_name}|{plan_index}|{len(world.quests)}")
    quest_type = rng.choice(QUEST_PLAN_TYPES)
    dungeon_subtype = rng.choice(QUEST_PLAN_DUNGEON_SUBTYPES)
    danger = rng.randint(low, high)
    reward_table = choose_loot_table_by_tag(
        "reward",
        seed=f"quest-reward-plan|{world.world_name}|{settlement_name}|{plan_index}|{quest_type}",
        context=settlement_name,
        danger_level=danger,
    ) or {}
    item_template = _quest_generation_item_template(world, settlement_name, plan_index, quest_type, danger)
    rescue_template = {}
    if quest_type == "rescue":
        rescue_template = choose_npc_template(
            FRIENDLY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger,
            used_ids=used_npc_template_ids(world),
            seed=f"quest-rescue-template|{world.world_name}|{settlement_name}|{plan_index}|{danger}",
            rescued=True,
        ) or {}
    return {
        "quest_plan_id": f"quest_plan_{plan_index + 1:03d}",
        "quest_type": quest_type,
        "danger_level": danger,
        "dungeon_subtype": dungeon_subtype,
        "reward_loot_table_id": str(reward_table.get("id") or ""),
        "reward_loot_table_name_jp": str(reward_table.get("name_jp") or ""),
        "reward_loot_table_name_en": str(reward_table.get("name_en") or ""),
        "objective_item_template_id": str(item_template.get("id") or ""),
        "objective_item_template_name": str(item_template.get("name") or ""),
        "objective_item_template_category": str(item_template.get("category") or ""),
        "objective_item_template_desc": str(item_template.get("desc") or item_template.get("description") or ""),
        "objective_item_template_level": _safe_int(item_template.get("level"), 0) if item_template else 0,
        "rescue_target_template_id": str(rescue_template.get("id") or ""),
        "rescue_target_template_name": str(rescue_template.get("name") or ""),
        "rescue_target_template_role": str(rescue_template.get("role") or ""),
    }


def _apply_quest_generation_plan(item: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    planned = dict(item)
    destination_hint = planned.get("destination_hint") if isinstance(planned.get("destination_hint"), dict) else {}
    destination_hint = dict(destination_hint)
    destination_hint["location_kind"] = str(plan.get("dungeon_subtype") or "dungeon")
    destination_hint.setdefault("anchor_kind", "")
    planned["destination_hint"] = destination_hint
    planned["quest_plan_id"] = str(plan.get("quest_plan_id") or "")
    planned["quest_type"] = str(plan.get("quest_type") or "retrieve")
    planned["objective_type"] = planned["quest_type"]
    planned["danger_level"] = _safe_int(plan.get("danger_level"), 1)
    planned["planned_danger_level"] = planned["danger_level"]
    planned["danger_source"] = "local_quest_plan"
    planned["dungeon_subtype"] = str(plan.get("dungeon_subtype") or "")
    planned["reward_loot_table_id"] = str(plan.get("reward_loot_table_id") or "")
    planned["reward_loot_table_name_jp"] = str(plan.get("reward_loot_table_name_jp") or "")
    planned["reward_loot_table_name_en"] = str(plan.get("reward_loot_table_name_en") or "")
    planned["objective_item_template_id"] = str(plan.get("objective_item_template_id") or "")
    planned["objective_item_template_name"] = str(plan.get("objective_item_template_name") or "")
    planned["objective_item_template_category"] = str(plan.get("objective_item_template_category") or "")
    planned["objective_item_template_desc"] = str(plan.get("objective_item_template_desc") or "")
    planned["objective_item_template_level"] = _safe_int(plan.get("objective_item_template_level"), 0)
    if planned["quest_type"] == "rescue" and str(plan.get("rescue_target_template_id") or "").strip():
        planned["target_npc_template_id"] = str(plan.get("rescue_target_template_id") or "")
        planned["rescue_target_template_id"] = str(plan.get("rescue_target_template_id") or "")
        planned["rescue_target_template_name"] = str(plan.get("rescue_target_template_name") or "")
    planned.pop("reward", None)
    return planned

def _generate_settlement_quests(
    self,
    player_name: str,
    world: WorldData,
    settlement_name: str,
    target_count: int | None = None,
) -> dict[str, Any]:
    settlement_danger = self._current_location_danger(settlement_name)
    quest_danger_cap = _clamp_world_danger(settlement_danger + 5)
    world_payload = _ai_json(
        _world_ai_context(world, include_characters=True, include_monsters=False, include_quests=True)
    )
    used_template_ids = used_npc_template_ids(world)
    npc_template_payload = json.dumps(
        {
            "enemy_templates": npc_template_prompt_summaries(
                ENEMY_NPC_TEMPLATE_CATEGORIES,
                danger_level=self._current_location_danger(settlement_name),
                used_ids=used_template_ids,
                limit=12,
            ),
            "friendly_templates": npc_template_prompt_summaries(
                FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                danger_level=self._current_location_danger(settlement_name),
                used_ids=used_template_ids,
                limit=12,
            ),
        },
        ensure_ascii=False,
    )
    collected: list[dict[str, Any]] = []
    seen_names = {quest.name for quest in world.quests}
    batch_records: list[dict[str, Any]] = []
    batch_index = 1
    quest_limit = max(1, min(SETTLEMENT_QUEST_MAX_PER_SETTLEMENT, int(target_count or SETTLEMENT_QUEST_MAX_PER_SETTLEMENT)))
    while len(collected) < quest_limit:
        remaining = quest_limit - len(collected)
        requested_count = min(SETTLEMENT_QUEST_BATCH_MAX, remaining)
        request_min = min(SETTLEMENT_QUEST_BATCH_MIN, requested_count)
        if requested_count < SETTLEMENT_QUEST_BATCH_MIN and collected and len(collected) >= QUEST_BOARD_REGEN_MIN:
            break
        plans = [
            _quest_generation_plan(self, world, settlement_name, len(collected) + index)
            for index in range(requested_count)
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの拠点クエスト生成担当です。"
                    "Fantasiaのsettlement_quest_generator相当として、"
                    "quests を持つJSONだけを返してください。"
                    "quests はクエスト候補オブジェクトの配列にしてください。"
                    f"このバッチでは {request_min}〜{requested_count} 件だけ生成してください。"
                    f"1つの拠点に登録する依頼は最大 {quest_limit} 件です。"
                    "各クエストには quest_type を必ず含め、rescue/retrieve/defeat/delivery/investigate/procure のいずれかにしてください。"
                    "街道をふさぐ魔物や危険生物の排除、討伐、退治、狩猟は必ず quest_type=\"defeat\" です。"
                    "薬や食料など指定品をどこかから調達する依頼だけ quest_type=\"procure\" にしてください。"
                    "報酬金、経験値、報酬アイテム、危険度、ダンジョン種別、目的アイテムテンプレート、救出対象NPCテンプレートはゲーム側で決定済みです。"
                    "reward は返さないでください。"
                    "quest_plans の quest_plan_id ごとに1件ずつ、名称、概要、objective_subnode_name、objective_description、"
                    "救出対象NPC名または討伐対象NPC名だけを世界観に合わせて生成してください。"
                    "delivery/procure/retrieve では objective_item_template_name と objective_item_template_desc を必ず依頼名と概要に反映してください。"
                    "retrieve は必ず植物採取依頼として扱い、指定された plant 素材を採取する内容にしてください。"
                    "quest_type, danger_level, dungeon_subtype, reward_loot_table_id, objective_item_template_id, target_npc_template_id は変更しないでください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"対象拠点: {settlement_name}\n"
                    f"拠点危険度: {settlement_danger}\n"
                    f"依頼危険度上限: {quest_danger_cap}\n"
                    f"バッチ番号: {batch_index}\n"
                    f"今回の生成件数: {request_min}〜{requested_count}\n"
                    f"quest_plans: {json.dumps(plans, ensure_ascii=False)}\n"
                    f"既存依頼名: {json.dumps(sorted(seen_names), ensure_ascii=False)}\n"
                    f"世界データ: {world_payload}\n"
                    "この拠点で自然に発生するクエスト候補を、quest_plansの固定値に従い、既存依頼と重複しないように作ってください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    f"NPC template candidates: {npc_template_payload}\n"
                    "When a quest_plan already has rescue_target_template_id, copy it exactly as target_npc_template_id. "
                    "Use enemy_templates for defeat targets and rescue blockers. "
                    "Use friendly_templates only for non-rescue friendly targets. "
                    "For destination_hint.location_kind, copy the quest_plan dungeon_subtype exactly. "
                    "Do not use road, plain, coast, river, settlement, or wilderness as the quest objective location kind. "
                    "The game will instantiate that template and let a later LLM pass fill only missing flavor details."
                ),
            }
        )
        response = self._chat_json(
            "settlement_quest_generator",
            messages,
            max_tokens=850,
            world_name=world.world_name,
            player_name=player_name,
        )
        batch_records.append(_strip_response_metadata(response))
        added = 0
        raw_items = _as_list(response.get("quests") or response.get("settlement_quests") or response.get("story_quests"))
        plans_by_id = {str(plan.get("quest_plan_id") or ""): plan for plan in plans}
        for item_index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                continue
            plan = plans_by_id.get(str(item.get("quest_plan_id") or "")) or (plans[item_index] if item_index < len(plans) else {})
            if plan:
                item = _apply_quest_generation_plan(item, plan)
            name = str(item.get("name") or item.get("quest_name") or item.get("title") or "").strip()
            if not name or name in seen_names:
                continue
            item = dict(item)
            item["quest_type"] = _normalise_quest_type_id(item.get("quest_type") or item.get("objective_type") or item.get("type") or item.get("kind")) or _quest_type(
                QuestData(name=name, overview=str(item.get("overview") or item.get("description") or item.get("summary") or ""), extra=dict(item)),
                item,
            )
            collected.append(item)
            seen_names.add(name)
            added += 1
            if len(collected) >= quest_limit:
                break
        if added <= 0:
            break
        batch_index += 1
    return {"quests": collected, "batches": batch_records, "settlement": settlement_name}

def _apply_settlement_quests(self, world: WorldData, response: dict[str, Any], settlement_name: str = "") -> None:
    generated = response.get("quests") or response.get("settlement_quests") or response.get("story_quests")
    existing = {quest.name for quest in world.quests}
    for index, item in enumerate(_as_list(generated)):
        quest = _quest_from_raw(item, len(world.quests) + index)
        if quest.name in existing:
            continue
        quest.flags.setdefault("source", "settlement_quest_generator")
        if not quest.neighboring_settlement:
            quest.neighboring_settlement = settlement_name or str(response.get("settlement") or response.get("location") or "")
        self._assign_quest_danger(quest, quest.neighboring_settlement or settlement_name)
        self._ensure_quest_reward(quest)
        world.quests.append(quest)
        existing.add(quest.name)
    world.extra["raw_settlement_quest_generator"] = _strip_response_metadata(response)

def _apply_field_event_quests(self, response: dict[str, Any], location: str) -> list[QuestData]:
    raw_quests = _as_list(response.get("quests"))
    raw_quest = response.get("quest")
    if raw_quest:
        raw_quests.extend(_as_list(raw_quest))

    existing = {quest.name for quest in self.state.world_data.quests}
    generated: list[QuestData] = []
    for item in raw_quests:
        quest = _quest_from_raw(item, len(self.state.world_data.quests) + len(generated))
        if quest.name in existing:
            continue
        if not quest.neighboring_settlement:
            quest.neighboring_settlement = location
        quest.flags.setdefault("source", "field_event_evaluator")
        quest.flags["wild"] = True
        self._assign_quest_danger(quest, quest.neighboring_settlement or location)
        self._ensure_quest_reward(quest)
        quest.log.append(
            {
                "manager": "field_event_evaluator",
                "event": response.get("event"),
                "response": _strip_response_metadata(response),
            }
        )
        self.state.world_data.quests.append(quest)
        generated.append(quest)
        existing.add(quest.name)
    return generated
