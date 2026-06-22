from __future__ import annotations

# Installed onto GameEngine by game._install_quest_modules().
# Shared helpers are supplied from game.py at install time to avoid import cycles.

def _generate_settlement_quests(
    self,
    player_name: str,
    world: WorldData,
    settlement_name: str,
    target_count: int | None = None,
) -> dict[str, Any]:
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
                    "報酬金、経験値、報酬アイテムはゲーム側で決定するため、reward は返さないでください。"
                    "各クエストには destination_hint を含めてください。"
                    "destination_hint は location_kind, anchor_kind, objective_subnode_name, objective_description を持つ短いヒントです。"
                    "destination_hint は目的地そのものではなく、ゲーム側がロケーションとサブノードを確定するための材料です。"
                    "街道近くの森、洞窟の奥、川辺の遺跡など、目標が存在する地形とサブ地点を具体的にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"対象拠点: {settlement_name}\n"
                    f"バッチ番号: {batch_index}\n"
                    f"今回の生成件数: {request_min}〜{requested_count}\n"
                    f"既存依頼名: {json.dumps(sorted(seen_names), ensure_ascii=False)}\n"
                    f"世界データ: {world_payload}\n"
                    "この拠点で自然に発生するクエスト候補を、既存依頼と重複しないように作ってください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    f"NPC template candidates: {npc_template_payload}\n"
                    "When a template fits a quest objective, include target_npc_template_id in the quest object. "
                    "Use enemy_templates for defeat targets and rescue blockers. "
                    "Use friendly_templates for rescue targets and delivery targets. "
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
        for item in _as_list(response.get("quests") or response.get("settlement_quests") or response.get("story_quests")):
            if not isinstance(item, dict):
                continue
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
