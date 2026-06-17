from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class JsonResponseError(RuntimeError):
    def __init__(self, manager_name: str, errors: list[str], response: Any) -> None:
        self.manager_name = manager_name
        self.errors = errors
        self.response = response
        message = f"{manager_name} returned invalid JSON response: " + "; ".join(errors)
        super().__init__(message)


@dataclass(frozen=True)
class FieldRule:
    name: str
    expected: tuple[type, ...]
    required: bool = True
    non_empty: bool = True
    aliases: tuple[str, ...] = ()
    string_items: bool = True

    @property
    def type_label(self) -> str:
        labels = []
        for item in self.expected:
            if item is str:
                labels.append("string")
            elif item is bool:
                labels.append("boolean")
            elif item is list:
                labels.append("array")
            elif item is dict:
                labels.append("object")
            else:
                labels.append(item.__name__)
        return " | ".join(labels)


@dataclass(frozen=True)
class ManagerSchema:
    manager_name: str
    fields: tuple[FieldRule, ...]
    example: dict[str, Any]

    def instruction(self) -> str:
        required = [field for field in self.fields if field.required]
        optional = [field for field in self.fields if not field.required]
        lines = [
            "応答形式の厳守:",
            "- Markdownや説明文を付けず、JSONオブジェクトだけを返してください。",
            "- 文字列は空にしないでください。",
            "- choices と prompt の配列の中身は文字列にしてください。",
            "必須キー:",
        ]
        lines.extend(f"- {field.name}: {field.type_label}" for field in required)
        if optional:
            lines.append("任意キー:")
            lines.extend(f"- {field.name}: {field.type_label}" for field in optional)
        if any(field.name in {"player_hp_delta", "hp_delta", "heal_hp", "restore_hp", "recover_hp", "damage_hp", "player_hp", "hp_effect", "hp_effects"} for field in self.fields):
            lines.append(
                "- HP changes: use player_hp_delta/hp_delta for signed changes, heal_hp/restore_hp/recover_hp for healing, damage_hp for damage, or player_hp for an absolute current HP value. The game clamps HP to the valid range."
            )
        if any(field.name in {"player_sp_delta", "sp_delta", "restore_sp", "recover_sp", "consume_sp", "player_sp", "sp_effect", "sp_effects"} for field in self.fields):
            lines.append(
                "- SP changes: use player_sp_delta/sp_delta for signed changes, restore_sp/recover_sp for recovery, consume_sp for spent SP, or player_sp for an absolute current SP value. Skills should use sp_cost instead of max_uses."
            )
        if any(field.name in {"gold_delta", "player_gold_delta", "pay_gold", "spend_gold", "receive_gold", "gold_effect", "gold_effects"} for field in self.fields):
            lines.append(
                "- Gold changes: use gold_delta/player_gold_delta for signed changes, receive_gold/gain_gold for rewards, and pay_gold/spend_gold/cost_gold for payments. The game clamps gold at 0."
            )
        if any(field.name in {"time_passed_hours", "time_passed_days", "advance_time_hours", "time_effect", "time_effects"} for field in self.fields):
            lines.append(
                "- Time passage: when the action should consume world time, return time_passed_hours or time_passed_days. The game calendar uses 60 days each for 春/夏/秋/冬."
            )
        if any(field.name in {"player_exp_delta", "exp", "experience", "reward_exp", "xp", "exp_effect", "exp_effects"} for field in self.fields):
            lines.append(
                "- Experience: return exp/reward_exp/xp or player_exp_delta when the player learned, survived, completed a quest, defeated an enemy, or otherwise earned growth. Level-up is controlled by the game."
            )
        if any(field.name in {"equip_item", "unequip_item", "equipment_changes"} for field in self.fields):
            lines.append(
                "- Equipment changes: use equip_item/equip_items to equip a named item or item object, unequip_item/remove_equipment to remove equipment, or equipment_changes with action=equip/unequip and slot/item. Slots are weapon/shield/body_armor/headgear/gauntlets/leg_armor/clothing/legwear/accessory."
            )
        if any(field.name == "display_cg" for field in self.fields):
            lines.append(
                "- 重要な場面、発見、戦闘の山場、会話の決定的瞬間など一枚絵CGが必要な場合だけ display_cg=true と cg_prompt/cg_description を返してください。"
            )
        if any(field.name in {"status_effects", "player_status_effects", "character_status_effects", "long_term_statuses"} for field in self.fields):
            lines.append(
                "- 状態付与が必要な場合は status_effects/player_status_effects/character_status_effects に、"
                "name, target, effect, duration, permanent, long_term, stage, remove_condition を持つオブジェクトを返してください。"
                "長期・永続状態は permanent=true または long_term=true にしてください。"
            )
        lines.append("例:")
        if any(field.name == "display_cg" for field in self.fields):
            lines.append(
                "- CGを表示する場合、cg_description/cg_prompt は直前の narration と同じ出来事だけを描写してください。"
                "現在地、行動結果、登場中のNPC/敵、重要な小物を具体化し、文章にない人物や別の場所を追加しないでください。"
            )
        if any(field.name in {"status_effects", "player_status_effects", "character_status_effects", "long_term_statuses"} for field in self.fields):
            lines.append(
                "- 治療、解呪、休息、交渉などで状態が解除される場合は remove_status_effects/cure_status_effects/treated_status_effects に、"
                "target, name, id, reason, treatment を持つオブジェクトを返してください。長期・永続状態も解除対象にできます。"
            )
        if any(field.name in {"item_rewards", "items", "rewards", "gold", "lost_items", "stolen_items", "given_items"} for field in self.fields):
            lines.append(
                "- アイテム報酬は可能な限り {name, category, quantity, description, value} のオブジェクトで返してください。"
                "name には (討伐時入手)、(報酬)、drop、loot などの入手条件を書かず、入手条件は description/source/reason に分けてください。"
            )
            lines.append(
                "- 装備品は category に small_weapon/medium_weapon/large_weapon/long_weapon/throwable_weapon/shield/body_armor/headgear/gauntlets/leg_armor/clothing/legwear/accessory 等を使い、rarity は common/uncommon/rare/epic/legendary/artifact から選べます。拾った物を即装備する場合は equip_item も返してください。"
            )
        if any(field.name in {"item_rewards", "items", "rewards", "gold", "lost_items", "stolen_items", "given_items"} for field in self.fields):
            lines.append(
                "- Item loss: when the player gives, loses, spends, is robbed of, or has items confiscated, return lost_items/stolen_items/given_items/remove_items as item references. Use item_uuid or item_uuids when available so the same item can be recovered later."
            )
        if any(field.name in {"monsters", "npcs", "new_npc_requests"} for field in self.fields):
            lines.append(
                "- NPC名や敵名は固有名詞だけにしてください。name に (討伐時入手)、(出現時)、報酬、ドロップ、説明文を混ぜないでください。"
                "説明や出現条件は description/reason/location に分けてください。"
            )
            lines.append(
                "- プレイヤー、主人公、あなた、自分、PC はNPCとして生成しないでください。"
                "現在地にいる既存NPCの名前、役割、別名を指す場合は new_npc_requests に入れないでください。"
            )
        if any(field.name in {"relationship_change", "relationship_changes", "npc_relationship_change", "affinity_change", "affinity_changes"} for field in self.fields):
            lines.append(
                "- NPC好感度が変化する場合は relationship_change または affinity_changes に "
                "{target/name/npc_name, delta, reason} を返してください。delta は差分で、0が中立、-10が完全敵対、10が完全信頼です。"
            )
        if any(field.name in {"relationship_change", "relationship_changes", "npc_relationship_change", "affinity_change", "affinity_changes"} for field in self.fields):
            lines.append(
                "- NPC affinity scale is -100 to 100. Return only the change as delta, normally clamped from -10 to +10 per event."
            )
        if any(field.name in {"npc_movement", "npc_movements", "character_movement", "character_movements", "move_npc", "move_npcs"} for field in self.fields):
            lines.append(
                "- NPCが同行・離脱・別地点へ移動した場合は npc_movements に "
                "{target/name/npc_name, location/to/destination, state, reason} を返してください。文章だけで同行させず、必ず実データ更新用に返してください。"
            )
        if any(field.name in {"npc_movement", "npc_movements", "character_movement", "character_movements", "move_npc", "move_npcs"} for field in self.fields):
            lines.append(
                "- Party movement must also be explicit: use state='party' or join_party=true when an NPC joins, "
                "leave_party=true when an NPC leaves, wait=true or state='waiting' when an NPC waits on the current map, "
                "and state='dead' when an NPC dies."
            )
        lines.append(json.dumps(self.example, ensure_ascii=False, indent=2))
        return "\n".join(lines)


REWARD_FIELDS = (
    FieldRule("item_rewards", (list,), required=False, non_empty=False, string_items=False),
    FieldRule("items", (list,), required=False, non_empty=False, string_items=False),
    FieldRule("rewards", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("gold", (int, str), required=False, non_empty=False),
    FieldRule("lost_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("lose_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("remove_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("removed_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("consume_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("consumed_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("stolen_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("taken_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("give_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("given_items", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("confiscated_items", (list, dict, str), required=False, non_empty=False, string_items=False),
)


VISUAL_FIELDS = (
    FieldRule("display_cg", (bool,), required=False, non_empty=False),
    FieldRule("cg_prompt", (list, str), required=False, non_empty=False, string_items=False),
    FieldRule("cg_description", (str,), required=False, non_empty=False),
)


STATUS_EFFECT_FIELDS = (
    FieldRule("status_effects", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("player_status_effects", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("character_status_effects", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("npc_status_effects", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("opponent_status_effects", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("long_term_statuses", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("persistent_statuses", (list, dict), required=False, non_empty=False, string_items=False),
    FieldRule("remove_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("remove_player_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("remove_character_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("remove_npc_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("cure_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("cure_player_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("cure_character_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("cure_npc_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("treated_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("treated_player_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("treated_character_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("treated_npc_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("resolved_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("resolved_player_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("resolved_character_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("resolved_npc_status_effects", (list, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("relationship_change", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("relationship_changes", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("npc_relationship_change", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("npc_relationship_changes", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("affinity_change", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("affinity_changes", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("npc_affinity_change", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("npc_affinity_changes", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("npc_movement", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("npc_movements", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("character_movement", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("character_movements", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("actor_movement", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("actor_movements", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("move_npc", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("move_npcs", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("moved_npcs", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("followers", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("escorted_npcs", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("player_hp_delta", (int, str), required=False, non_empty=False),
    FieldRule("hp_delta", (int, str), required=False, non_empty=False),
    FieldRule("heal_hp", (int, str), required=False, non_empty=False),
    FieldRule("restore_hp", (int, str), required=False, non_empty=False),
    FieldRule("recover_hp", (int, str), required=False, non_empty=False),
    FieldRule("damage_hp", (int, str), required=False, non_empty=False),
    FieldRule("player_hp", (int, str), required=False, non_empty=False),
    FieldRule("hp_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("hp_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("hp_reason", (str,), required=False, non_empty=False),
    FieldRule("player_sp_delta", (int, str), required=False, non_empty=False),
    FieldRule("sp_delta", (int, str), required=False, non_empty=False),
    FieldRule("restore_sp", (int, str), required=False, non_empty=False),
    FieldRule("recover_sp", (int, str), required=False, non_empty=False),
    FieldRule("consume_sp", (int, str), required=False, non_empty=False),
    FieldRule("player_sp", (int, str), required=False, non_empty=False),
    FieldRule("sp_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("sp_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("sp_reason", (str,), required=False, non_empty=False),
    FieldRule("gold_delta", (int, str), required=False, non_empty=False),
    FieldRule("player_gold_delta", (int, str), required=False, non_empty=False),
    FieldRule("receive_gold", (int, str, dict), required=False, non_empty=False, string_items=False),
    FieldRule("gain_gold", (int, str, dict), required=False, non_empty=False, string_items=False),
    FieldRule("pay_gold", (int, str, dict), required=False, non_empty=False, string_items=False),
    FieldRule("spend_gold", (int, str, dict), required=False, non_empty=False, string_items=False),
    FieldRule("cost_gold", (int, str, dict), required=False, non_empty=False, string_items=False),
    FieldRule("gold_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("gold_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("gold_reason", (str,), required=False, non_empty=False),
    FieldRule("time_passed_hours", (int, str), required=False, non_empty=False),
    FieldRule("time_passed_days", (int, str), required=False, non_empty=False),
    FieldRule("advance_time_hours", (int, str), required=False, non_empty=False),
    FieldRule("time_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("time_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("time_reason", (str,), required=False, non_empty=False),
    FieldRule("player_exp_delta", (int, str), required=False, non_empty=False),
    FieldRule("exp", (int, str), required=False, non_empty=False),
    FieldRule("experience", (int, str), required=False, non_empty=False),
    FieldRule("reward_exp", (int, str), required=False, non_empty=False),
    FieldRule("xp", (int, str), required=False, non_empty=False),
    FieldRule("exp_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("exp_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("exp_reason", (str,), required=False, non_empty=False),
    FieldRule("equip_item", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("equip_items", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("unequip_item", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("unequip_items", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("remove_equipment", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("equipment_changes", (dict, list), required=False, non_empty=False, string_items=False),
)


SCHEMAS: dict[str, ManagerSchema] = {
    "create_world_overview": ManagerSchema(
        manager_name="create_world_overview",
        fields=(
            FieldRule("world_name", (str,)),
            FieldRule("overview", (str,)),
            FieldRule("structure_description", (str,)),
            FieldRule("structure", (dict, list), non_empty=False, string_items=False),
            FieldRule("starting_location", (str,), required=False),
            FieldRule("locations", (list, dict), string_items=False),
            FieldRule("connections", (list, dict), non_empty=False, string_items=False),
        ),
        example={
            "world_name": "硝子森の辺境",
            "overview": "古い森と鉱山跡に囲まれた辺境。",
            "structure_description": "宿場町、森、鉱山跡が接続している。",
            "structure": {
                "map_rule": "地点同士は2時間単位の道で結ばれている。",
                "danger_rule": "開始地点から離れるほど危険度が上がる。",
                "themes": ["古い森", "錆びた鉱山跡"],
            },
            "starting_location": "灯守りの宿",
            "locations": [
                {"name": "灯守りの宿", "kind": "settlement", "danger": 0, "description": "旅人が集まる宿場町。"},
                {"name": "硝子森", "kind": "wilderness", "danger": 1, "description": "透明な葉が鳴る森。"},
            ],
            "connections": [{"from": "灯守りの宿", "to": "硝子森", "hours": 2}],
        },
    ),
    "check_world_content_violation": ManagerSchema(
        manager_name="check_world_content_violation",
        fields=(
            FieldRule("content_violation", (bool,)),
            FieldRule("reason", (str,)),
            FieldRule("message", (str,)),
            FieldRule("suggested_revision", (str,), required=False, non_empty=False),
        ),
        example={
            "content_violation": False,
            "reason": "世界設定として処理可能です。",
            "message": "この内容で世界生成を続行できます。",
            "suggested_revision": "",
        },
    ),
    "check_illegal_content": ManagerSchema(
        manager_name="check_illegal_content",
        fields=(
            FieldRule("content_violation", (bool,)),
            FieldRule("reason", (str,)),
            FieldRule("message", (str,)),
            FieldRule("suggested_action", (str,), required=False, non_empty=False),
        ),
        example={
            "content_violation": False,
            "reason": "プレイヤー入力として処理可能です。",
            "message": "この行動を通常のナレーションへ渡せます。",
            "suggested_action": "",
        },
    ),
    "create_story": ManagerSchema(
        manager_name="create_story",
        fields=(
            FieldRule("world_situation", (str,)),
            FieldRule("flow", (list, dict), non_empty=False, string_items=False),
            FieldRule("current_rumor", (str,)),
            FieldRule("story_quests", (list,), non_empty=False, string_items=False),
        ),
        example={
            "world_situation": "辺境では雨の夜だけ古い道が開き、行方不明者が増えている。",
            "flow": [
                {"phase": "導入", "goal": "宿場町で噂を集める"},
                {"phase": "探索", "goal": "硝子森の赤い印を追う"},
            ],
            "current_rumor": "錆びた鉱山跡から夜ごとに鐘の音が聞こえる。",
            "story_quests": [
                {
                    "name": "雨夜の赤い印",
                    "overview": "地図の赤い印が示す場所を調べる。",
                    "neighboring_settlement": "灯守りの宿",
                }
            ],
        },
    ),
    "create_settlement_detail": ManagerSchema(
        manager_name="create_settlement_detail",
        fields=(
            FieldRule("settlement_structure_description", (str,)),
            FieldRule("atmosphere", (str,), aliases=("atomosphere",)),
            FieldRule("settlement_structure", (dict, list), non_empty=False, string_items=False),
            FieldRule("facilities", (list,), non_empty=False, string_items=False),
            FieldRule("residents", (list,), non_empty=False, string_items=False),
            FieldRule("adventurers", (list,), non_empty=False, string_items=False),
        ),
        example={
            "settlement_structure_description": "宿、馬小屋、掲示板、小さな礼拝所が中庭を囲んでいる。",
            "atmosphere": "雨音とランタンの温かさが混ざった、警戒心の強い宿場。",
            "settlement_structure": {
                "core": "灯守りの宿",
                "spots": ["掲示板", "馬小屋", "古井戸", "礼拝所"],
            },
            "facilities": [
                {
                    "name": "冒険者ギルド",
                    "type": "guild",
                    "description": "依頼掲示板と受付がある小さなギルド。",
                    "npc_name": "ミラ",
                    "npc_role": "ギルド受付",
                }
            ],
            "residents": [
                {
                    "name": "ミラ",
                    "role": "宿の主人",
                    "description": "古い道の噂を知る寡黙な主人。",
                }
            ],
            "adventurers": [
                {
                    "name": "セオ",
                    "role": "斥候",
                    "description": "硝子森から戻ったばかりの旅人。",
                }
            ],
        },
    ),
    "settlement_quest_generator": ManagerSchema(
        manager_name="settlement_quest_generator",
        fields=(
            FieldRule("quests", (list,), aliases=("settlement_quests", "story_quests"), non_empty=False, string_items=False),
        ),
        example={
            "quests": [
                {
                    "name": "消えた隊商",
                    "overview": "最後に灯守りの宿を出た隊商の足取りを追う。",
                    "neighboring_settlement": "灯守りの宿",
                    "choices": ["掲示板を確認する", "馬丁に話を聞く"],
                }
            ]
        },
    ),
    "facility_request_evaluator": ManagerSchema(
        manager_name="facility_request_evaluator",
        fields=(
            FieldRule("allowed", (bool,), aliases=("can_create",)),
            FieldRule("narration", (str,), aliases=("text", "reason")),
            FieldRule("facility", (dict,), required=False, non_empty=False, string_items=False),
            FieldRule("npc", (dict,), required=False, non_empty=False, string_items=False),
            FieldRule("choices", (list,), required=False, non_empty=False),
        ),
        example={
            "allowed": True,
            "narration": "街の通りを抜けると、炉の熱が漏れる鍛冶屋が見つかった。",
            "facility": {
                "name": "鍛冶屋",
                "type": "blacksmith",
                "description": "武具の修理と売買を行う小さな鍛冶場。",
            },
            "npc": {
                "name": "炉番のレナ",
                "role": "鍛冶職人",
                "personality": "口数は少ないが、仕事には誠実。",
            },
            "choices": ["炉番のレナに話しかける", "品物を見る"],
        },
    ),
    "quest_starter": ManagerSchema(
        manager_name="quest_starter",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "narr")),
            FieldRule("choices", (list,)),
            FieldRule("quest_name", (str,), required=False),
            FieldRule("objective", (str,), required=False),
            FieldRule("location", (str,), required=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "quest_name": "消えた隊商",
            "objective": "隊商が最後に通った道を調べる。",
            "location": "灯守りの宿",
            "narration": "掲示板の古い依頼札が雨で滲んでいる。",
            "choices": ["掲示板を読む", "馬丁に話を聞く", "宿の外へ出る"],
        },
    ),
    "quest_referee_with_free_action": ManagerSchema(
        manager_name="quest_referee_with_free_action",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "narr")),
            FieldRule("choices", (list,)),
            FieldRule("location", (str,), required=False),
            FieldRule("quest_progress", (str,), required=False),
            FieldRule("event", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            FieldRule("quest_status", (str,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "narration": "馬丁は隊商の馬車が森の方へ曲がったと証言した。",
            "location": "灯守りの宿",
            "quest_progress": "隊商は硝子森へ向かった。",
            "event": {"name": "森へ向かう手がかり", "result": "新しい調査地点が見つかった。"},
            "finished": False,
            "choices": ["硝子森へ向かう", "さらに聞き込みをする"],
        },
    ),
    "quest_referee_event_resolve": ManagerSchema(
        manager_name="quest_referee_event_resolve",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "narr")),
            FieldRule("choices", (list,)),
            FieldRule("location", (str,), required=False),
            FieldRule("quest_update", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            FieldRule("quest_status", (str,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "narration": "手がかりは地図の赤い印と一致した。",
            "location": "灯守りの宿",
            "quest_update": {"progress": "赤い印の場所へ向かう理由ができた。"},
            "finished": False,
            "choices": ["赤い印へ向かう", "宿で準備する"],
        },
    ),
    "field_event_evaluator": ManagerSchema(
        manager_name="field_event_evaluator",
        fields=(
            FieldRule("event_occurred", (bool,)),
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("location", (str,)),
            FieldRule("choices", (list,)),
            FieldRule("event", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("discovered_location", (dict, str), required=False, non_empty=False, string_items=False),
            FieldRule("quest", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("quests", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("npcs", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("monsters", (list,), required=False, non_empty=False, string_items=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "event_occurred": True,
            "narration": "霧の向こうから助けを求める声が聞こえ、苔むした地下門が姿を現した。",
            "location": "灯守りの宿の外れ",
            "event": {
                "name": "霧中の救難声",
                "kind": "wild_quest",
                "summary": "ゲーム側に事前登録されていない突発クエストの種。",
            },
            "discovered_location": {
                "name": "雨裂きの地下門",
                "description": "硝子森の斜面に隠れていた古い地下入口。",
                "area": "硝子森",
            },
            "quest": {
                "name": "霧中の救難声",
                "overview": "地下門の奥から聞こえる声の主を探す。",
                "neighboring_settlement": "灯守りの宿",
                "choices": ["地下門へ入る", "宿へ戻って助けを呼ぶ"],
            },
            "choices": ["地下門へ近づく", "声に返事をする", "宿へ戻る"],
        },
    ),
    "master_ai_facilitator": ManagerSchema(
        manager_name="master_ai_facilitator",
        fields=(
            FieldRule("content_violation", (bool,)),
            FieldRule("think", (str,)),
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("process", (list, dict, str), non_empty=False, string_items=False),
            FieldRule("finished", (bool,)),
            FieldRule("location", (str,), required=False),
            FieldRule("choices", (list,), required=False),
            FieldRule("recipients", (list,), required=False, non_empty=False),
            FieldRule("new_npc_requests", (list, dict), required=False, non_empty=False, string_items=False),
            FieldRule("reason", (str,), required=False, non_empty=False),
            FieldRule("message", (str,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "content_violation": False,
            "think": "現在地と直近ログから、会話と探索のどちらへ進むか整理する。",
            "narration": "宿の主人は雨に濡れた地図を広げ、赤い印の意味を慎重に語り始めた。",
            "process": [
                {"step": "入力解釈", "result": "宿の主人への相談として処理する"},
                {"step": "状態更新", "result": "赤い印の噂を補強する"},
            ],
            "finished": False,
            "location": "灯守りの宿",
            "recipients": ["ミラ"],
            "choices": ["赤い印について聞く", "掲示板を見る", "周辺を探索する"],
        },
    ),
    "master_ai_process_summarizer": ManagerSchema(
        manager_name="master_ai_process_summarizer",
        fields=(
            FieldRule("summary", (str,)),
            FieldRule("recipients", (list,)),
            FieldRule("process_summary", (dict, list, str), required=False, non_empty=False, string_items=False),
            FieldRule("memory_updates", (list,), required=False, non_empty=False, string_items=False),
        ),
        example={
            "summary": "ミラは赤い印が硝子森の古道を示すと示唆した。",
            "recipients": ["ミラ"],
            "process_summary": {"topic": "赤い印", "state": "噂が強化された"},
            "memory_updates": [
                {"target": "ミラ", "memory": "プレイヤーに赤い印の噂を伝えた"}
            ],
        },
    ),
    "master_ai_process_summarizer_with_no_recipients": ManagerSchema(
        manager_name="master_ai_process_summarizer_with_no_recipients",
        fields=(
            FieldRule("summary", (str,)),
            FieldRule("process_summary", (dict, list, str), required=False, non_empty=False, string_items=False),
            FieldRule("memory_updates", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("no_recipients_reason", (str,), required=False, non_empty=False),
        ),
        example={
            "summary": "プレイヤーは状況を整理し、次に追うべき手がかりを絞った。",
            "process_summary": {"topic": "自己整理", "state": "次の行動候補が明確になった"},
            "memory_updates": [],
            "no_recipients_reason": "NPCや外部対象へ渡す情報がないため。",
        },
    ),
    "master_ai_npc_generater": ManagerSchema(
        manager_name="master_ai_npc_generater",
        fields=(
            FieldRule("npcs", (list,), string_items=False),
            FieldRule("reason", (str,), required=False, non_empty=False),
        ),
        example={
            "reason": "探索の進行で新しい手がかりを持つNPCが必要になったため。",
            "npcs": [
                {
                    "name": "レナ",
                    "category": "traveler",
                    "description": "雨の中で宿場に立ち寄った巡回薬師。",
                    "personality": "警戒心が強いが、困っている相手には助言を惜しまない。",
                    "look": "濡れた旅外套、薬草袋、小さな銀の鈴を身につけている。",
                    "occupation": "巡回薬師",
                    "archetype": "cautious_helper",
                    "skills": [
                        {
                            "name": "薬草鑑定",
                            "description": "周辺の薬草や毒草を見分ける。",
                            "skill_type": "support",
                            "effects": [{"name": "治療手がかり", "value": 1}],
                            "sp_cost": 3,
                            "power": 2,
                            "strength_level": 2,
                            "usefulness": "探索と会話で追加情報を出せる。",
                        }
                    ],
                    "traits": [{"name": "慎重", "description": "危険な相手には距離を取る。", "power": 1, "strength_level": 1}],
                }
            ],
        },
    ),
    "npc_detail_generater": ManagerSchema(
        manager_name="npc_detail_generater",
        fields=(
            FieldRule("name", (str,)),
            FieldRule("talk_style", (str,)),
            FieldRule("archetype", (str,)),
            FieldRule("skills", (list,), string_items=False),
            FieldRule("behavior_policy", (str,), required=False, non_empty=False),
            FieldRule("conversation_topics", (list,), required=False, non_empty=False),
            FieldRule("memory_updates", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("relationship", (dict, list, str), required=False, non_empty=False, string_items=False),
            *STATUS_EFFECT_FIELDS,
        ),
        example={
            "name": "レナ",
            "talk_style": "短く慎重に話し、危険を感じると質問で相手を試す。",
            "archetype": "cautious_helper",
            "behavior_policy": "困っている相手には助言するが、無謀な戦闘には加担しない。",
            "conversation_topics": ["薬草", "雨夜の道", "行方不明の旅人"],
            "skills": [
                {
                    "name": "雨避けの処方",
                    "description": "雨で悪化する状態異常を一時的に和らげる。",
                    "skill_type": "support",
                    "effects": [{"name": "状態異常緩和", "value": 1}],
                    "sp_cost": 2,
                    "power": 1,
                    "strength_level": 1,
                    "usefulness": "探索前の準備や会話イベントに使える。",
                }
            ],
            "memory_updates": [{"target": "レナ", "memory": "プレイヤーと初対面。まだ警戒している。"}],
            "relationship": {"trust": 0, "stance": "watchful"},
        },
    ),
    "conversation_starter": ManagerSchema(
        manager_name="conversation_starter",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("speaker", (str,)),
            FieldRule("choices", (list,)),
            FieldRule("location", (str,), required=False),
            FieldRule("topic", (str,), required=False),
            FieldRule("mood", (str,), required=False),
            FieldRule("content_violation", (bool,), required=False, non_empty=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "speaker": "ミラ",
            "topic": "赤い印",
            "mood": "警戒しつつ協力的",
            "location": "灯守りの宿",
            "narration": "ミラは声を落とし、赤い印について知っていることを話し始めた。",
            "finished": False,
            "choices": ["赤い印について聞く", "失踪者について聞く", "会話を終える"],
        },
    ),
    "conversation_facilitator": ManagerSchema(
        manager_name="conversation_facilitator",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("speaker", (str,)),
            FieldRule("choices", (list,)),
            FieldRule("location", (str,), required=False),
            FieldRule("topic", (str,), required=False),
            FieldRule("relationship_change", (dict, str), required=False, non_empty=False, string_items=False),
            FieldRule("content_violation", (bool,), required=False, non_empty=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "speaker": "ミラ",
            "topic": "赤い印",
            "location": "灯守りの宿",
            "narration": "ミラは、赤い印が雨夜の古道を示す合図だと打ち明けた。",
            "relationship_change": {"trust": 1, "reason": "落ち着いて質問した"},
            "finished": False,
            "choices": ["古道について聞く", "協力を頼む", "会話を終える"],
        },
    ),
    "conversation_resolver": ManagerSchema(
        manager_name="conversation_resolver",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("summary", (str,)),
            FieldRule("choices", (list,)),
            FieldRule("speaker", (str,), required=False),
            FieldRule("location", (str,), required=False),
            FieldRule("relationship_change", (dict, str), required=False, non_empty=False, string_items=False),
            FieldRule("memory_updates", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "speaker": "ミラ",
            "summary": "ミラから赤い印と雨夜の古道の関係を聞いた。",
            "location": "灯守りの宿",
            "narration": "ミラは地図を畳み、雨が強まる前に動くなら今だと告げた。",
            "relationship_change": {"trust": 1},
            "memory_updates": [
                {"target": "ミラ", "memory": "プレイヤーに赤い印の秘密を共有した"}
            ],
            "finished": True,
            "choices": ["掲示板を見る", "周辺を探索する"],
        },
    ),
    "referee_player_attack_new_new": ManagerSchema(
        manager_name="referee_player_attack_new_new",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("choices", (list,)),
            FieldRule("target", (str,), required=False),
            FieldRule("hit", (bool,), required=False, non_empty=False),
            FieldRule("damage", (int, str), required=False, non_empty=False),
            FieldRule("encounter_update", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("effects", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "target": "硝子森の影",
            "hit": True,
            "damage": 3,
            "narration": "刃は霧を裂き、影の輪郭をわずかに揺らした。",
            "encounter_update": {
                "opponent_hp_delta": -3,
                "opponent_status": "wounded",
                "opponent_status_effects": [
                    {
                        "name": "幻霧の裂傷",
                        "effect": "霧の傷が残り、次の3ターンは毎ターン1ダメージを受ける。",
                        "duration": 3,
                        "damage_per_turn": 1,
                    }
                ],
            },
            "effects": [{"name": "牽制", "duration": 1}],
            "finished": False,
            "choices": ["距離を取る", "追撃する", "降伏する"],
        },
    ),
    "referee_player_any_input_new_new": ManagerSchema(
        manager_name="referee_player_any_input_new_new",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("choices", (list,)),
            FieldRule("intent", (str,)),
            FieldRule("encounter_update", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("effects", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            FieldRule("content_violation", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "intent": "surrender",
            "narration": "あなたは武器を下ろし、敵意がないことを示した。",
            "encounter_update": {
                "player_status": "surrendering",
                "player_surrendered": True,
                "player_status_effects": [
                    {
                        "name": "武装解除",
                        "effect": "武器を下ろしているため、再武装するまで攻撃行動が不利になる。",
                        "remove_condition": "武器を拾い直す、または敵が降伏を受け入れる。",
                    }
                ],
            },
            "effects": [],
            "finished": False,
            "choices": ["両手を上げる", "事情を説明する", "相手の反応を待つ"],
        },
    ),
    "referee_npc": ManagerSchema(
        manager_name="referee_npc",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("choices", (list,)),
            FieldRule("npc_action", (str,)),
            FieldRule("target", (str,), required=False),
            FieldRule("intent", (str,), required=False),
            FieldRule("encounter_update", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("effects", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            FieldRule("should_end_encounter", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "npc_action": "accept_surrender",
            "intent": "mercy",
            "target": "Player",
            "narration": "影は攻撃の構えを解き、あなたが武器を捨てるのを待った。",
            "encounter_update": {
                "opponent_status": "guarded",
                "player_status": "disarmed",
                "player_status_effects": [
                    {
                        "name": "威圧に呑まれた",
                        "effect": "敵の威圧で足が止まり、次の2ターンは逃走や回避の判断が遅れる。",
                        "duration": 2,
                    }
                ],
            },
            "effects": [{"name": "戦闘停止", "duration": 1}],
            "finished": True,
            "should_end_encounter": True,
            "choices": ["事情を説明する", "その場を離れる"],
        },
    ),
    "referee_npc_rewrite": ManagerSchema(
        manager_name="referee_npc_rewrite",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("choices", (list,)),
            FieldRule("npc_action", (str,), required=False),
            FieldRule("encounter_update", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            FieldRule("rewrite_reason", (str,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "npc_action": "accept_surrender",
            "narration": "硝子森の影は踏み込まず、雨音の中で武器を下ろせと短く告げた。",
            "encounter_update": {
                "opponent_status": "watching",
                "player_status": "surrender_accepted",
                "status_effects": {
                    "player": [
                        {
                            "name": "監視下",
                            "effect": "敵に見張られている。急な攻撃や逃走は疑われやすい。",
                            "remove_condition": "会話で安全を得る、またはその場を離れる。",
                        }
                    ]
                },
            },
            "finished": True,
            "rewrite_reason": "相手の慎重な性格と降伏の意思を反映した。",
            "choices": ["事情を説明する", "ゆっくり離れる"],
        },
    ),
    "create_character": ManagerSchema(
        manager_name="create_character",
        fields=(
            FieldRule("name", (str,)),
            FieldRule("gender", (str,)),
            FieldRule("age", (str,)),
            FieldRule("backstory", (str,)),
            FieldRule("personality", (str,)),
            FieldRule("ability", (dict, list, str), non_empty=False, string_items=False),
            FieldRule("role", (str,), required=False),
            FieldRule("category", (str,), required=False),
        ),
        example={
            "name": "ミラ",
            "gender": "女性",
            "age": "30代後半",
            "role": "宿の主人",
            "category": "resident",
            "backstory": "雨夜の古道を知るが、旅人をむやみに危険へ送らないよう慎重に振る舞う。",
            "personality": "寡黙で観察眼が鋭く、困っている者には不器用に親切。",
            "ability": {
                "name": "古道の記憶",
                "description": "雨の夜だけ現れる道と古い噂を結びつけられる。",
            },
        },
    ),
    "create_look": ManagerSchema(
        manager_name="create_look",
        fields=(
            FieldRule("category", (str,)),
            FieldRule("look", (str,)),
            FieldRule("image_generation_prompt", (list,)),
            FieldRule("negative_prompt", (str,), required=False, non_empty=False),
        ),
        example={
            "category": "human",
            "look": "濃紺のエプロンとランタン型の首飾りを身につけた宿の主人。",
            "image_generation_prompt": [
                "fantasy innkeeper woman",
                "navy apron",
                "lantern pendant",
                "warm lantern light",
                "anime illustration",
            ],
            "negative_prompt": "low quality, blurry, extra fingers, text, watermark",
        },
    ),
    "create_trait": ManagerSchema(
        manager_name="create_trait",
        fields=(
            FieldRule("traits", (list,), string_items=False),
        ),
        example={
            "traits": [
                {
                    "name": "慎重",
                    "description": "危険な依頼を安易に勧めない。",
                    "severity": 2,
                    "power": 2,
                    "strength_level": 2,
                    "effect": "降伏や交渉を選んだ相手にはまず事情を聞く。",
                },
                {
                    "name": "古道の知識",
                    "description": "雨夜の古道にまつわる噂を知っている。",
                    "severity": 3,
                    "power": 3,
                    "strength_level": 3,
                    "effect": "探索や会話で赤い印の情報を出せる。",
                },
            ]
        },
    ),
    "create_skill": ManagerSchema(
        manager_name="create_skill",
        fields=(
            FieldRule("skills", (list,), string_items=False),
        ),
        example={
            "skills": [
                {
                    "name": "噂の照合",
                    "description": "旅人の証言と古い地図を照らし合わせる。",
                    "element": "light",
                    "skill_type": "support",
                    "effects": [{"name": "手がかり発見", "value": 1}],
                    "sp_cost": 3,
                    "power": 2,
                    "strength_level": 2,
                    "usefulness": "探索前の情報収集に役立つ。",
                }
            ]
        },
    ),
    "narrator_initial": ManagerSchema(
        manager_name="narrator_initial",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("location", (str,)),
            FieldRule("choices", (list,)),
            *VISUAL_FIELDS,
        ),
        example={
            "narration": "宿の主人が古びた地図を差し出した。",
            "location": "灯守りの宿",
            "choices": ["地図を見る", "宿の主人に話しかける", "外へ出る"],
        },
    ),
    "narrator": ManagerSchema(
        manager_name="narrator",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("location", (str,)),
            FieldRule("choices", (list,)),
            *VISUAL_FIELDS,
        ),
        example={
            "narration": "あなたの行動に応じて状況が変化した。",
            "location": "灯守りの宿",
            "choices": ["さらに調べる", "別の場所へ向かう"],
        },
    ),
    "character_image_creator": ManagerSchema(
        manager_name="character_image_creator",
        fields=(
            FieldRule("prompt", (list, str)),
            FieldRule("negative_prompt", (str,), required=False, non_empty=False),
        ),
        example={
            "prompt": [
                "masterpiece",
                "best quality",
                "single fantasy RPG character",
                "full body",
                "standing pose",
                "plain light background",
            ],
            "negative_prompt": "low quality, blurry, text, watermark, extra fingers, bad hands",
        },
    ),
    "monster_image_creator": ManagerSchema(
        manager_name="monster_image_creator",
        fields=(
            FieldRule("prompt", (list, str)),
            FieldRule("negative_prompt", (str,), required=False, non_empty=False),
        ),
        example={
            "prompt": [
                "masterpiece",
                "best quality",
                "single fantasy RPG monster",
                "full body creature",
                "plain light background",
            ],
            "negative_prompt": "low quality, blurry, text, watermark, cropped, extra limbs",
        },
    ),
    "background_image_creator": ManagerSchema(
        manager_name="background_image_creator",
        fields=(
            FieldRule("prompt", (list, str)),
            FieldRule("negative_prompt", (str,), required=False, non_empty=False),
        ),
        example={
            "prompt": ["fantasy RPG background", "misty frontier inn", "warm lantern light"],
            "negative_prompt": "low quality, blurry, text, watermark",
        },
    ),
    "cg_image_creator": ManagerSchema(
        manager_name="cg_image_creator",
        fields=(
            FieldRule("prompt", (list, str)),
            FieldRule("negative_prompt", (str,), required=False, non_empty=False),
        ),
        example={
            "prompt": [
                "fantasy RPG event CG",
                "dramatic cinematic composition",
                "misty gate discovery",
                "single scene illustration",
            ],
            "negative_prompt": "low quality, blurry, text, watermark, UI, speech bubble",
        },
    ),
}


def schema_instruction(manager_name: str) -> str:
    schema = SCHEMAS.get(manager_name)
    if not schema:
        return "応答はJSONオブジェクトだけにしてください。"
    instruction = schema.instruction()
    if manager_name == "create_world_overview":
        instruction += (
            "\ncreate_world_overview専用ルール:\n"
            "- トップレベルの world_name, overview, structure_description, structure, locations, connections を必ず返してください。\n"
            "- locations はロケーション配列、connections は {from, to, hours} の配列にしてください。\n"
            "- locations の各要素は name, kind, danger, description を持たせてください。\n"
            "- kind は settlement/wilderness/dungeon/landmark/facility のいずれかを優先してください。\n"
            "- structure には世界全体の地理ルール、危険度ルール、文化圏、主要テーマなどを入れてください。\n"
        )
    return instruction


def validate_manager_response(manager_name: str, value: Any) -> tuple[dict[str, Any], list[str]]:
    schema = SCHEMAS.get(manager_name)
    value = _canonicalize_manager_response(manager_name, value)
    if not isinstance(value, dict):
        return {}, [f"response must be a JSON object, got {type(value).__name__}"]
    if not schema:
        return dict(value), []

    response = dict(value)
    errors: list[str] = []
    for field in schema.fields:
        _apply_alias(response, field)
        if field.name not in response or response[field.name] is None:
            if field.required:
                errors.append(f"missing required key: {field.name}")
            continue

        item = response[field.name]
        item = _normalize_value(field, item)
        response[field.name] = item
        if not isinstance(item, field.expected):
            errors.append(f"{field.name} must be {field.type_label}, got {type(item).__name__}")
            continue
        if field.non_empty and _is_empty(item):
            errors.append(f"{field.name} must not be empty")
        if field.string_items and (field.expected == (list,) or list in field.expected):
            if isinstance(item, list):
                response[field.name] = [str(part) for part in item if str(part).strip()]
                if field.non_empty and not response[field.name]:
                    errors.append(f"{field.name} must contain at least one non-empty item")

    return response, errors


def retry_prompt(manager_name: str, errors: list[str], previous_response: Any) -> str:
    previous = json.dumps(sanitize_retry_response(previous_response), ensure_ascii=False, indent=2)
    if len(previous) > 2400:
        previous = previous[:2400] + "\n... [truncated]"
    manager_guidance = _manager_retry_guidance(manager_name, errors, previous_response)
    return (
        "前回の応答はJSON形式または必須キー/型の検証に失敗しました。\n"
        f"manager: {manager_name}\n"
        "検証エラー:\n"
        + "\n".join(f"- {error}" for error in errors)
        + "\n\n"
        "前回の応答:\n"
        f"{previous}\n\n"
        "上記を修正し、次の条件を満たすJSONオブジェクトだけを返してください。\n"
        f"{manager_guidance}"
        f"{schema_instruction(manager_name)}"
    )


def _manager_retry_guidance(manager_name: str, errors: list[str], previous_response: Any) -> str:
    if manager_name != "create_world_overview":
        return ""
    previous = previous_response if isinstance(previous_response, dict) else {}
    previous_keys = {str(key) for key in previous.keys()} if isinstance(previous, dict) else set()
    structure_like_keys = {"map_rule", "danger_rule", "themes", "regions", "settlements", "breeding_mechanics", "combat_priority"}
    missing_outer_keys = any(str(error).startswith("missing required key:") for error in errors)
    if not missing_outer_keys:
        return ""
    note = (
        "create_world_overviewの修正注意:\n"
        "- 前回の応答が map_rule/danger_rule/themes 等だけの場合、それらはトップレベルではなく structure の中に入れてください。\n"
        "- トップレベルには必ず world_name, overview, structure_description, structure, locations, connections を置いてください。\n"
        "- locations は最低2件以上、connections は最低1件以上を返してください。\n"
        "- 次の外枠を崩さず、値だけを世界設定に合わせて埋めてください。\n"
        "{\n"
        '  "world_name": "世界名",\n'
        '  "overview": "世界全体の概要",\n'
        '  "structure_description": "地理構造と移動ルールの説明",\n'
        '  "structure": {"map_rule": "地点同士は2時間単位で接続", "danger_rule": "開始地点から遠いほど危険"},\n'
        '  "starting_location": "初期地点名",\n'
        '  "locations": [{"name": "初期地点名", "kind": "settlement", "danger": 0, "description": "説明"}],\n'
        '  "connections": [{"from": "初期地点名", "to": "隣接地点名", "hours": 2}]\n'
        "}\n"
    )
    if previous_keys & structure_like_keys:
        note += "- 前回のトップレベルキー " + ", ".join(sorted(previous_keys & structure_like_keys)) + " は structure 内へ移動してください。\n"
    return note


def sanitize_retry_response(value: Any, string_limit: int = 1200) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_retry_response(item, string_limit)
            for key, item in value.items()
            if not str(key).startswith("_") and str(key) not in _RETRY_METADATA_KEYS
        }
    if isinstance(value, list):
        return [sanitize_retry_response(item, string_limit) for item in value[:20]]
    if isinstance(value, str) and len(value) > string_limit:
        return value[:string_limit] + "... [truncated]"
    return value


_RETRY_METADATA_KEYS = {
    "generation_metadata",
    "metadata",
    "request",
    "request_params",
    "response_info",
    "prompt_debug",
}


def _apply_alias(response: dict[str, Any], field: FieldRule) -> None:
    if field.name in response:
        return
    for alias in field.aliases:
        if alias in response:
            response[field.name] = response[alias]
            return


def _canonicalize_manager_response(manager_name: str, value: Any) -> Any:
    if manager_name == "settlement_quest_generator":
        return _wrap_collection_response(
            value,
            "quests",
            aliases=("quest", "generated_quest", "settlement_quest", "quest_list"),
            item_keys=("name", "overview", "neighboring_settlement", "choices", "reward", "status", "objective"),
        )
    if manager_name == "create_skill":
        return _wrap_collection_response(
            value,
            "skills",
            aliases=("skill", "generated_skill", "skill_list"),
            item_keys=("name", "description", "element", "skill_type", "effects", "sp_cost", "power", "strength_level", "usefulness"),
        )
    if manager_name == "create_trait":
        return _wrap_collection_response(
            value,
            "traits",
            aliases=("trait", "generated_trait", "trait_list"),
            item_keys=("name", "description", "severity", "effect"),
        )
    return value


def _wrap_collection_response(
    value: Any,
    collection_key: str,
    *,
    aliases: tuple[str, ...],
    item_keys: tuple[str, ...],
) -> Any:
    if isinstance(value, list):
        return {collection_key: value}
    if not isinstance(value, dict):
        return value

    response = dict(value)
    if collection_key in response:
        if isinstance(response[collection_key], dict):
            response[collection_key] = [response[collection_key]]
        return response

    for alias in aliases:
        if alias in response:
            item = response[alias]
            response[collection_key] = item if isinstance(item, list) else [item]
            return response

    if any(key in response for key in item_keys):
        item = {key: item_value for key, item_value in response.items() if not str(key).startswith("_")}
        response = {key: item_value for key, item_value in response.items() if str(key).startswith("_")}
        response[collection_key] = [item]
    return response


def _normalize_value(field: FieldRule, item: Any) -> Any:
    if bool in field.expected and isinstance(item, str):
        lowered = item.strip().lower()
        if lowered in {"true", "yes", "1", "はい"}:
            return True
        if lowered in {"false", "no", "0", "いいえ"}:
            return False
    if list in field.expected and isinstance(item, str):
        return [item]
    if str in field.expected and not isinstance(item, (str, list, dict)):
        return str(item)
    return item


def _is_empty(item: Any) -> bool:
    if isinstance(item, str):
        return not item.strip()
    if isinstance(item, (list, dict)):
        return len(item) == 0
    return False
