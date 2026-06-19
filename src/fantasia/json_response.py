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
        if any(field.name in {"player_hunger_delta", "hunger_delta", "restore_hunger", "recover_hunger", "player_hunger", "hunger", "hunger_effect", "hunger_effects"} for field in self.fields):
            lines.append(
                "- Hunger changes: use player_hunger_delta/hunger_delta for signed changes, restore_hunger/recover_hunger for meals or food, or player_hunger/hunger for an absolute hunger value. The game clamps hunger to 0-50."
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
                "- Equipment changes: use equip_item/equip_items to equip a named item or item object, unequip_item/remove_equipment to remove equipment, or equipment_changes with action=equip/unequip and slot/item. Slots are weapon/armor_shield/armor_head/armor_body/armor_arm/armor_leg/armor_cloth/accessory_ring/accessory_amulet."
            )
        if any(field.name == "display_cg" for field in self.fields):
            lines.append(
                "- 重要な場面、発見、戦闘の山場、会話の決定的瞬間など一枚絵CGが必要な場合だけ display_cg=true と cg_prompt/cg_description を返してください。"
            )
        if any(field.name in {"status_effects", "player_status_effects", "character_status_effects", "long_term_statuses"} for field in self.fields):
            lines.append(
                "- 状態付与が必要な場合は status_effects/player_status_effects/character_status_effects に、"
                "name, description, remove_condition, power, duration, effect_id, llm_effect を持つオブジェクトを返してください。"
                "duration は残り時間、-1 は永続です。effect_id は HP_Damage/SP_Damage/Paralysis/Silence/Psychosis/Inoperable/SendLLM/Atk_Mod/Def_Mod のいずれかです。"
                "効果IDで決められない描写や補助効果は llm_effect に書いてください。行動不能系は effect_id=Inoperable にし、表示名は攻撃手段に合う具体名と説明にしてください。"
            )
        if any(field.name == "npc_action" for field in self.fields):
            lines.append(
                "- NPC action tools: return npc_action='flee' when the NPC escapes to an adjacent node/location, "
                "npc_action='surrender' when the NPC yields and stops acting. Surrender does not remove the NPC from combat; "
                "the player decides whether to accept the surrender or keep fighting. For flee/surrender, set combat_judgement.offensive=false "
                "and do not include HP damage."
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
                "target, name, effect_id, reason, treatment を持つオブジェクトを返してください。永続状態も解除対象にできます。"
            )
        if any(field.name in {"item_rewards", "items", "rewards", "gold", "lost_items", "stolen_items", "given_items"} for field in self.fields):
            lines.append(
                "- アイテム報酬は可能な限り {name, category, quantity, description, value} のオブジェクトで返してください。"
                "name には (討伐時入手)、(報酬)、drop、loot などの入手条件を書かず、入手条件は description/source/reason に分けてください。"
            )
            lines.append(
                "- 装備品は category に weapon_small/weapon_medium/weapon_large/weapon_long/weapon_range/armor_shield/armor_head/armor_body/armor_arm/armor_leg/armor_cloth/accessory_ring/accessory_amulet 等を使い、rarity は common/uncommon/rare/epic/legendary/artifact から選べます。拾った物を即装備する場合は equip_item も返してください。"
            )
        if any(field.name in {"item_rewards", "items", "rewards", "gold", "lost_items", "stolen_items", "given_items"} for field in self.fields):
            lines.append(
                "- Item loss: when the player gives, loses, spends, is robbed of, or has items confiscated, return lost_items/stolen_items/given_items/remove_items as item references. Use item_uuid or item_uuids when available so the same item can be recovered later."
            )
        if any(field.name in {"enemies", "opponents", "npcs", "new_npc_requests"} for field in self.fields):
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
        if any(field.name in {"map_reveal", "map_reveals", "world_map_reveal", "world_map_reveals", "unlock_world_map_route"} for field in self.fields):
            lines.append(
                "- ワールドマップの経路を開放する場合は map_reveal を返してください。"
                "例: {target_location: \"目的地名\", reason: \"目的地への地図を受け取った\"}。"
                "現在受注中のクエスト目的地なら {target: \"quest_destination\"} でも構いません。"
                "既知の経路を指定する場合は route/path にロケーション名配列を入れてください。"
            )
        if any(field.name in {"time_passed_hours", "advance_time_hours", "long_time_passage_hours", "time_skip_hours", "spend_time_hours", "long_time_passage"} for field in self.fields):
            lines.append(
                "- 休憩、睡眠、待機、数日間の滞在などで長い時間が経つ場合は、"
                "long_time_passage_hours/time_skip_hours/spend_time_hours などに1時間単位の経過時間を返してください。"
                "数日間なら days ではなく hours に換算しても構いません。単純な短い移動では返さないでください。"
            )
        if any(field.name in {"game_over", "force_game_over", "fatal_outcome", "bad_end"} for field in self.fields):
            lines.append(
                "- プレイヤーの行動結果が確実に冒険終了・死亡・脱出不能・破滅などのゲームオーバーだと判断できる場合だけ "
                "game_over=true と game_over_reason/game_over_narration を返してください。"
                "ゲームオーバー時に「リスタート」「再開」など存在しない選択肢を作らないでください。"
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
    FieldRule("map_reveal", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("map_reveals", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("reveal_map", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("reveal_maps", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("world_map_reveal", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("world_map_reveals", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("reveal_world_map", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("unlock_world_map_route", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("unlock_world_map_routes", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("map_route_reveal", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("map_route_reveals", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("subnode_map_reveal", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("subnode_map_reveals", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("reveal_subnode_map", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("reveal_subnode_maps", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("unlock_subnode_route", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("unlock_subnode_routes", (dict, list, str, bool), required=False, non_empty=False, string_items=False),
    FieldRule("home_construction", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("player_home_construction", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("home_building", (dict, list, str), required=False, non_empty=False, string_items=False),
    FieldRule("player_home_building", (dict, list, str), required=False, non_empty=False, string_items=False),
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
    FieldRule("player_hunger_delta", (int, str), required=False, non_empty=False),
    FieldRule("hunger_delta", (int, str), required=False, non_empty=False),
    FieldRule("restore_hunger", (int, str), required=False, non_empty=False),
    FieldRule("recover_hunger", (int, str), required=False, non_empty=False),
    FieldRule("consume_hunger", (int, str), required=False, non_empty=False),
    FieldRule("player_hunger", (int, str), required=False, non_empty=False),
    FieldRule("hunger", (int, str), required=False, non_empty=False),
    FieldRule("hunger_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("hunger_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("hunger_reason", (str,), required=False, non_empty=False),
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
    FieldRule("long_time_passage_hours", (int, str), required=False, non_empty=False),
    FieldRule("time_skip_hours", (int, str), required=False, non_empty=False),
    FieldRule("spend_time_hours", (int, str), required=False, non_empty=False),
    FieldRule("wait_hours", (int, str), required=False, non_empty=False),
    FieldRule("rest_hours", (int, str), required=False, non_empty=False),
    FieldRule("sleep_hours", (int, str), required=False, non_empty=False),
    FieldRule("long_time_passage_days", (int, str), required=False, non_empty=False),
    FieldRule("time_skip_days", (int, str), required=False, non_empty=False),
    FieldRule("spend_time_days", (int, str), required=False, non_empty=False),
    FieldRule("time_effect", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("time_effects", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("long_time_passage", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("time_skip", (dict, list), required=False, non_empty=False, string_items=False),
    FieldRule("time_reason", (str,), required=False, non_empty=False),
    FieldRule("game_over", (bool, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("force_game_over", (bool, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("fatal_outcome", (bool, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("bad_end", (bool, dict, str), required=False, non_empty=False, string_items=False),
    FieldRule("game_over_reason", (str,), required=False, non_empty=False),
    FieldRule("game_over_narration", (str,), required=False, non_empty=False),
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
    "create_world_location_batch": ManagerSchema(
        manager_name="create_world_location_batch",
        fields=(
            FieldRule("locations", (list, dict), string_items=False),
            FieldRule("connections", (list, dict), non_empty=False, string_items=False),
            FieldRule("batch_summary", (str,), required=False, non_empty=False),
        ),
        example={
            "batch_summary": "The next road segment adds nearby terrain without duplicating one-off important locations.",
            "locations": [
                {"name": "月影の森", "kind": "wilderness", "danger": 1, "description": "開始地点の外れに広がる静かな森。"},
                {"name": "古い祠", "kind": "landmark", "danger": 2, "description": "森の奥に残る小さな祠。"},
                {"name": "湿った洞穴", "kind": "dungeon", "danger": 3, "description": "祠の裏手に開いた浅い洞穴。"},
            ],
            "connections": [
                {"from": "開始地点", "to": "月影の森", "hours": 2},
                {"from": "月影の森", "to": "古い祠", "hours": 2},
                {"from": "古い祠", "to": "湿った洞穴", "hours": 2},
            ],
        },
    ),
    "dungeon_subnode_generator": ManagerSchema(
        manager_name="dungeon_subnode_generator",
        fields=(
            FieldRule("nodes", (list, dict), aliases=("subnodes", "rooms"), string_items=False),
            FieldRule("edges", (list, dict), aliases=("connections", "paths"), non_empty=False, string_items=False),
            FieldRule("summary", (str,), required=False, non_empty=False),
        ),
        example={
            "summary": "入口から複数の枝道が伸び、鉱脈、薬草群生地、宝箱の間を経て最奥部へ至る。",
            "nodes": [
                {"id": "entrance", "name": "入口", "kind": "entrance", "description": "外と内部をつなぐ出入口。"},
                {"id": "ore_vein", "name": "青鉄鉱の広間", "kind": "ore_vein", "description": "壁に青い鉱石が走る採掘跡。"},
                {"id": "herb_grove", "name": "光苔の薬草群生地", "kind": "herb_grove", "description": "湿った床に薬草と光苔が広がる。"},
                {"id": "treasure_room", "name": "古い宝箱の間", "kind": "treasure_room", "description": "罠の気配がある宝箱の部屋。"},
                {"id": "deepest", "name": "最奥部", "kind": "deepest", "description": "ダンジョンの中核に近い場所。"},
            ],
            "edges": [
                {"from": "entrance", "to": "ore_vein"},
                {"from": "ore_vein", "to": "herb_grove"},
                {"from": "herb_grove", "to": "deepest"},
                {"from": "ore_vein", "to": "treasure_room"},
                {"from": "treasure_room", "to": "deepest"},
            ],
        },
    ),
    "craft_item_generator": ManagerSchema(
        manager_name="craft_item_generator",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "message")),
            FieldRule("item", (dict,), aliases=("crafted_item", "result"), string_items=False),
        ),
        example={
            "narration": "素材を削り、磨き、旅で使える小さな道具に仕上げた。",
            "item": {
                "name": "旅人の補修具",
                "category": "tool",
                "description": "壊れた装備や道具を応急修理するための小さな工具。",
                "quantity": 1,
                "value": 20,
                "rarity": "common",
            },
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
    "input_gatekeeper": ManagerSchema(
        manager_name="input_gatekeeper",
        fields=(
            FieldRule("content_violation", (bool,)),
            FieldRule("action_possible", (bool,), aliases=("possible", "allowed", "feasible")),
            FieldRule("reason", (str,)),
            FieldRule("message", (str,)),
            FieldRule("suggested_action", (str,), required=False, non_empty=False),
        ),
        example={
            "content_violation": False,
            "action_possible": True,
            "reason": "The action can be passed to the normal game managers in the current scene.",
            "message": "The action can proceed.",
            "suggested_action": "",
        },
    ),
    "check_action_feasibility": ManagerSchema(
        manager_name="check_action_feasibility",
        fields=(
            FieldRule("action_possible", (bool,), aliases=("possible", "allowed", "feasible")),
            FieldRule("reason", (str,)),
            FieldRule("message", (str,)),
            FieldRule("suggested_action", (str,), required=False, non_empty=False),
        ),
        example={
            "action_possible": False,
            "reason": "所持品や周囲の状況に存在しない大量のGoldを突然得る行動で、世界内の因果がない。",
            "message": "そのようなことはできない。金貨を得るには、探索、取引、報酬などの手段が必要だ。",
            "suggested_action": "周囲を探して価値のあるものがないか調べる",
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
                    "npc_gender": "female",
                    "npc_age": "late 20s",
                    "npc_look": "short brown hair, practical guild uniform, calm eyes",
                    "npc_personality": "calm, organized, helpful to adventurers",
                }
            ],
            "residents": [
                {
                    "name": "ミラ",
                    "role": "宿の主人",
                    "gender": "female",
                    "age": "middle-aged",
                    "look": "warm smile, apron over a plain dress, tidy tied hair",
                    "personality": "kind but careful with strangers",
                    "description": "古い道の噂を知る寡黙な主人。",
                }
            ],
            "adventurers": [
                {
                    "name": "セオ",
                    "role": "斥候",
                    "gender": "male",
                    "age": "early 30s",
                    "look": "lean scout, hooded cloak, light leather armor",
                    "personality": "observant and dryly humorous",
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
                    "quest_type": "investigate",
                    "overview": "最後に灯守りの宿を出た隊商の足取りを追う。",
                    "neighboring_settlement": "灯守りの宿",
                    "destination_hint": {
                        "location_kind": "wilderness",
                        "anchor_kind": "road",
                        "objective_subnode_name": "隊商の痕跡",
                        "objective_description": "街道近くの森に残された車輪跡と破れた荷布。",
                    },
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
    "home_construction_evaluator": ManagerSchema(
        manager_name="home_construction_evaluator",
        fields=(
            FieldRule("usable", (bool,)),
            FieldRule("reason", (str,), required=False, non_empty=False),
            FieldRule("narration", (str,), required=False, non_empty=False, aliases=("text", "message")),
            FieldRule("furniture_level_gain", (int, str), required=False, non_empty=False),
            FieldRule("consume_item", (bool,), required=False, non_empty=False),
        ),
        example={
            "usable": True,
            "reason": "乾いた木材は壁材や棚に使える。",
            "narration": "あなたは木材を切りそろえ、家の骨組みと作業棚を少しずつ組み上げた。",
            "furniture_level_gain": 2,
            "consume_item": True,
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
            FieldRule("destination_location", (str,), required=False),
            FieldRule("objective_subnode_name", (str,), required=False),
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
    "quest_objective_npc_designer": ManagerSchema(
        manager_name="quest_objective_npc_designer",
        fields=(
            FieldRule("name", (str,)),
            FieldRule("display_alias", (str,), required=False, non_empty=False),
            FieldRule("role_label", (str,), required=False, non_empty=False),
            FieldRule("description", (str,)),
            FieldRule("personality", (str,), required=False, non_empty=False),
            FieldRule("gender", (str,), required=False, non_empty=False),
            FieldRule("age", (str,), required=False, non_empty=False),
            FieldRule("look", (str,), required=False, non_empty=False),
            FieldRule("species", (str,), required=False, non_empty=False),
            FieldRule("category", (str,), required=False, non_empty=False),
            FieldRule("hostile", (bool,), required=False, non_empty=False),
            FieldRule("image_prompt", (str, list), required=False, non_empty=False, string_items=False),
            FieldRule("aliases", (list,), required=False, non_empty=False),
        ),
        example={
            "name": "森蔦の拘束者",
            "display_alias": "町娘をさらった者",
            "role_label": "妨害者",
            "description": "依頼の舞台と噂に合う、救出対象を妨げる存在。",
            "personality": "警戒心が強く、獲物を逃がさない。",
            "gender": "none",
            "age": "adult",
            "look": "暗い森に溶け込む影と絡みつく蔦のような腕を持つ。",
            "species": "魔物",
            "category": "quest_objective",
            "hostile": True,
            "image_prompt": "fantasy monster, dark forest captor, vine-like limbs",
            "aliases": ["拘束者", "さらった者"],
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
    "quest_procurement_checker": ManagerSchema(
        manager_name="quest_procurement_checker",
        fields=(
            FieldRule("accepted", (bool,), aliases=("acceptable", "is_acceptable", "matched")),
            FieldRule("item_uuid", (str,), aliases=("accepted_item_uuid", "uuid"), non_empty=False),
            FieldRule("item_name", (str,), required=False, non_empty=False),
            FieldRule("reason", (str,), non_empty=False),
        ),
        example={
            "accepted": True,
            "item_uuid": "item-uuid-from-candidates",
            "item_name": "治癒のポーション",
            "reason": "傷に効くポーションという依頼条件に合うため。",
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
            FieldRule("enemies", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("opponents", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("boss_npc", (dict, list), required=False, non_empty=False, string_items=False),
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
                "kind": "dungeon",
                "description": "硝子森の斜面に隠れていた古い地下入口。",
                "area": "硝子森",
            },
            "boss_npc": {
                "name": "霧底の守護者",
                "role": "地下門のボス",
                "description": "地下門の最奥で声の主を守るように待ち構える魔物。",
                "personality": "侵入者を試すように威圧する。",
                "gender": "none",
                "age": "ancient",
                "look": "霧をまとった巨大な影。",
                "image_generation_prompt": ["fantasy dungeon boss", "mist guardian"],
                "hostile": True,
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
                    "gender": "female",
                    "age": "late 20s",
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
            FieldRule("gender", (str,), required=False, non_empty=False),
            FieldRule("age", (str,), required=False, non_empty=False),
            FieldRule("personality", (str,), required=False, non_empty=False),
            FieldRule("look", (str,), required=False, non_empty=False, aliases=("appearance",)),
            FieldRule("image_generation_prompt", (list, str), required=False, non_empty=False, string_items=False),
            FieldRule("skills", (list,), string_items=False),
            FieldRule("behavior_policy", (str,), required=False, non_empty=False),
            FieldRule("conversation_topics", (list,), required=False, non_empty=False),
            FieldRule("memory_updates", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("relationship", (dict, list, str), required=False, non_empty=False, string_items=False),
            *STATUS_EFFECT_FIELDS,
        ),
        example={
            "name": "レナ",
            "gender": "female",
            "age": "late 20s",
            "personality": "警戒心が強いが、困っている相手には助言を惜しまない。",
            "look": "濡れた旅外套、薬草袋、小さな銀の鈴を身につけている。",
            "image_generation_prompt": ["female traveling herbalist", "rain cloak", "herb pouch"],
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
    "encounter_target_resolver": ManagerSchema(
        manager_name="encounter_target_resolver",
        fields=(
            FieldRule("target_name", (str,), aliases=("name", "monster_name", "enemy_name")),
            FieldRule("opponent_type", (str,), required=False),
            FieldRule("category", (str,), required=False),
            FieldRule("description", (str,), required=False),
            FieldRule("gender", (str,), required=False, non_empty=False),
            FieldRule("age", (str,), required=False, non_empty=False),
            FieldRule("look", (str,), required=False, non_empty=False, aliases=("appearance",)),
            FieldRule("personality", (str,), required=False, non_empty=False),
            FieldRule("traits", (list,), required=False, non_empty=False, string_items=False),
            FieldRule("image_generation_prompt", (list, str), required=False, non_empty=False),
            FieldRule("confidence", (int, str), required=False, non_empty=False),
            FieldRule("reason", (str,), required=False, non_empty=False),
        ),
        example={
            "target_name": "触手",
            "opponent_type": "character",
            "category": "tentacle_monster",
            "description": "水辺に潜む粘液をまとった触手状の魔物。",
            "gender": "none",
            "age": "adult",
            "look": "dark wet tendrils, many flexible limbs, non-human silhouette",
            "personality": "predatory, cautious, reacts to weak prey",
            "traits": [{"name": "絡みつく触手", "description": "多数の触手で相手の動きを封じる。"}],
            "image_generation_prompt": ["tentacle monster", "slimy tendrils", "fantasy RPG monster"],
            "confidence": 90,
            "reason": "プレイヤー行動と直近ログの両方で触手が戦闘対象として示されているため。",
        },
    ),
    "hostile_npc_encounter_evaluator": ManagerSchema(
        manager_name="hostile_npc_encounter_evaluator",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "message")),
            FieldRule("combat_started", (bool,), aliases=("start_combat", "battle_started")),
            FieldRule("opponent_name", (str,), required=False, non_empty=False, aliases=("target_name", "enemy_name")),
            FieldRule("stance", (str,), required=False, non_empty=False),
            FieldRule("choices", (list,), required=False, non_empty=False),
            FieldRule("reason", (str,), required=False, non_empty=False),
        ),
        example={
            "narration": "洞窟の奥に潜んでいた黒角の獣があなたに気づき、低く唸りながら身構えた。",
            "combat_started": False,
            "opponent_name": "黒角の獣",
            "stance": "watching",
            "choices": ["距離を取る", "武器を構える", "声をかける"],
            "reason": "敵対的だが、まだ即座には襲いかかっていないため。",
        },
    ),
    "combat_transition_detector": ManagerSchema(
        manager_name="combat_transition_detector",
        fields=(
            FieldRule("combat_started", (bool,), aliases=("start_combat", "battle_started")),
            FieldRule("opponent_name", (str,), required=False, non_empty=False, aliases=("target_name", "enemy_name")),
            FieldRule("narration", (str,), required=False, non_empty=False, aliases=("text", "message")),
            FieldRule("reason", (str,), required=False, non_empty=False),
        ),
        example={
            "combat_started": True,
            "opponent_name": "街道を塞ぐ蟲",
            "narration": "蟲が牙を鳴らして飛びかかり、戦闘が始まった。",
            "reason": "応答文で敵が明確に攻撃を開始しているため。",
        },
    ),
    "context_reference_resolver": ManagerSchema(
        manager_name="context_reference_resolver",
        fields=(
            FieldRule("target_type", (str,), aliases=("type", "kind")),
            FieldRule("target_name", (str,), aliases=("name", "target", "character_name", "quest_name"), non_empty=False),
            FieldRule("resolved_action", (str,), required=False, non_empty=False),
            FieldRule("confidence", (int, str), required=False, non_empty=False),
            FieldRule("reason", (str,)),
        ),
        example={
            "target_type": "character",
            "target_name": "ミラ",
            "resolved_action": "ミラにさっきの依頼について尋ねる",
            "confidence": 80,
            "reason": "直近ログで会話していた宿の主人がミラで、入力の「あの人」がその人物を指すため。",
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
                        "description": "霧の傷が残り、行動ごとにHPが少し削られる。",
                        "remove_condition": "止血する、霧の魔力を払う、または時間経過で治まる。",
                        "power": 1,
                        "duration": 3,
                        "effect_id": "HP_Damage",
                        "llm_effect": "傷口に幻霧がまとわりつき、痛みと視界の揺らぎを描写に反映する。",
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
                        "description": "武器を下ろしているため、再武装するまで攻撃行動が不利になる。",
                        "remove_condition": "武器を拾い直す、または敵が降伏を受け入れる。",
                        "power": -2,
                        "duration": -1,
                        "effect_id": "Atk_Mod",
                        "llm_effect": "武器を構えていないため、攻撃するには一手遅れる。",
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
            FieldRule("combat_judgement", (dict,), required=False, non_empty=False, string_items=False),
            FieldRule("finished", (bool,), required=False, non_empty=False),
            FieldRule("should_end_encounter", (bool,), required=False, non_empty=False),
            *STATUS_EFFECT_FIELDS,
            *REWARD_FIELDS,
            *VISUAL_FIELDS,
        ),
        example={
            "npc_action": "restrain",
            "intent": "capture",
            "target": "Player",
            "narration": "影は踏み込まず、足元の闇を糸のように伸ばしてあなたの脚を縫い止めた。",
            "encounter_update": {
                "opponent_status": "guarded",
                "player_status": "disarmed",
                "player_status_effects": [
                    {
                        "name": "影縛り",
                        "description": "影の糸に足元を縫い止められ、攻撃・逃走・移動ができない。",
                        "remove_condition": "影の糸を切る、術者を説得する、または拘束を解く。",
                        "power": 0,
                        "duration": 2,
                        "effect_id": "Inoperable",
                        "llm_effect": "影による拘束。攻撃・逃走・移動を妨げる。",
                    }
                ],
            },
            "combat_judgement": {"offensive": False, "weakness_multiplier": 0.0, "reason": "拘束のみでHPダメージなし。"},
            "effects": [{"name": "拘束姿勢", "duration": 1}],
            "finished": False,
            "should_end_encounter": False,
            "choices": ["拘束を解こうともがく", "事情を説明する"],
        },
    ),
    "referee_npc_rewrite": ManagerSchema(
        manager_name="referee_npc_rewrite",
        fields=(
            FieldRule("narration", (str,), aliases=("text",)),
            FieldRule("choices", (list,)),
            FieldRule("npc_action", (str,), required=False),
            FieldRule("encounter_update", (dict, list), required=False, non_empty=False, string_items=False),
            FieldRule("combat_judgement", (dict,), required=False, non_empty=False, string_items=False),
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
                            "description": "敵に見張られている。急な攻撃や逃走は疑われやすい。",
                            "remove_condition": "会話で安全を得る、またはその場を離れる。",
                            "power": 0,
                            "duration": -1,
                            "effect_id": "SendLLM",
                            "llm_effect": "監視による行動圧力。会話や慎重な移動は可能。",
                        }
                    ]
                },
            },
            "combat_judgement": {"offensive": False, "weakness_multiplier": 0.0, "reason": "監視と武装解除のみでHPダメージなし。"},
            "finished": True,
            "rewrite_reason": "相手の慎重な性格と降伏の意思を反映した。",
            "choices": ["事情を説明する", "ゆっくり離れる"],
        },
    ),
    "combat_damage_narrator": ManagerSchema(
        manager_name="combat_damage_narrator",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "message")),
        ),
        example={
            "narration": "ナナはゴブリンへ素早い一閃を繰り出した。刃は的確に急所を捉え、ゴブリンはその場で力尽きた。",
        },
    ),
    "combat_heal_narrator": ManagerSchema(
        manager_name="combat_heal_narrator",
        fields=(
            FieldRule("narration", (str,), aliases=("text", "message")),
        ),
        example={
            "narration": "ナナは癒しの魔法を唱えた。淡い光が傷を少しふさぎ、呼吸がいくらか楽になった。",
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
    "create_initial_character_profile": ManagerSchema(
        manager_name="create_initial_character_profile",
        fields=(
            FieldRule("name", (str,)),
            FieldRule("gender", (str,)),
            FieldRule("age", (str,)),
            FieldRule("backstory", (str,)),
            FieldRule("personality", (str,)),
            FieldRule("look", (str,)),
            FieldRule("image_generation_prompt", (list, str), aliases=("image_prompt", "prompt")),
            FieldRule("traits", (list,), non_empty=False, string_items=False),
            FieldRule("skills", (list,), non_empty=False, string_items=False),
            FieldRule("ability", (dict, list, str), required=False, non_empty=False, string_items=False),
            FieldRule("role", (str,), required=False),
            FieldRule("category", (str,), required=False),
            FieldRule("negative_prompt", (str,), required=False, non_empty=False),
        ),
        example={
            "name": "Mira",
            "gender": "female",
            "age": "late 30s",
            "role": "innkeeper",
            "category": "resident",
            "backstory": "A former road guide who now keeps the village inn.",
            "personality": "Calm, observant, and protective toward travelers.",
            "ability": {"name": "Old Road Memory", "description": "Remembers safe routes and hidden dangers."},
            "look": "A practical innkeeper with a navy apron, lantern charm, and weathered travel boots.",
            "image_generation_prompt": ["fantasy innkeeper woman", "navy apron", "lantern charm", "anime illustration"],
            "traits": [
                {
                    "name": "Watchful Host",
                    "description": "Quickly notices danger near guests.",
                    "severity": 2,
                    "power": 2,
                    "strength_level": 2,
                    "effect": "Better at warning allies before ambushes.",
                }
            ],
            "skills": [
                {
                    "name": "Lantern Signal",
                    "description": "Uses a lantern flash to guide or distract.",
                    "element": "light",
                    "skill_type": "support",
                    "effects": "Improves ally positioning and weakens surprise attacks.",
                    "sp_cost": 3,
                    "power": 2,
                    "strength_level": 2,
                    "usefulness": "Supportive utility in travel and combat.",
                }
            ],
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
            "choices": ["移動する", "宿の主人に話しかける", "外へ出る"],
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
                "isolated cutout",
                "pure white background",
                "no scenery",
                "no background objects",
            ],
            "negative_prompt": "low quality, blurry, text, watermark, extra fingers, bad hands, background objects, wall, pillar",
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
                "isolated cutout",
                "pure white background",
                "no scenery",
                "no background objects",
            ],
            "negative_prompt": "low quality, blurry, text, watermark, cropped, extra limbs, background objects, wall, pillar",
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
    if manager_name == "check_action_feasibility":
        instruction += (
            "\ncheck_action_feasibility rules:\n"
            "- This is not a content-safety check. Judge only whether the player's input can be attempted inside the current world, location, inventory, NPC state, and recent context.\n"
            "- Return action_possible=true for risky, foolish, dangerous, hostile, exploratory, bargaining, surrendering, fleeing, hiding, or uncertain attempts when the player can plausibly try them. Success or failure is decided later.\n"
            "- Return action_possible=false when the input directly creates causeless money/items/victory/death/teleportation/new concepts/NPC personality changes/world-setting changes without an in-world method.\n"
            "- message must be a short natural refusal addressed to the player when action_possible=false.\n"
            "- Return compact JSON only. Do not add Markdown or commentary.\n"
        )
    if manager_name == "create_world_overview":
        instruction += (
            "\ncreate_world_overview専用ルール:\n"
            "- トップレベルの world_name, overview, structure_description, structure, locations, connections を必ず返してください。\n"
            "- locations はロケーション配列、connections は {from, to, hours} の配列にしてください。\n"
            "- locations の各要素は name, kind, danger, description を持たせてください。\n"
            "- kind は settlement/wilderness/dungeon/landmark/road/crossroad/coast/mountain/river/plain のいずれかを優先してください。街の施設は location にせず、settlement の facilities として扱います。\n"
            "- danger は0〜50で表し、開始地点は0付近、旅の最終地点・最終神殿・ラスボス地点は40〜45にしてください。\n"
            "- 宿屋、鍛冶屋、ギルド、店、寺院などの街施設を独立したロケーションにしないでください。\n"
            "- ただし、ユーザーが明示した神殿・寺院がダンジョン、最終地点、ボスが待つ場所である場合は facility ではなく kind=dungeon にしてください。\n"
            "- 洞窟やダンジョンの入口、内部、奥、深部などは同じ dungeon ロケーション内のサブ地点として扱い、別ロケーションにしないでください。\n"
            "- ロケーション名は世界観、地形、文化、危険度、役割から新しく命名してください。白石街道、緑瓦の宿場、アルテミスなどの固定プリセットや同じモチーフの反復は避けてください。\n"
            "- structure には世界全体の地理ルール、危険度ルール、文化圏、主要テーマなどを入れてください。\n"
        )
    if manager_name == "create_world_overview":
        instruction += (
            "\nAdditional create_world_overview rule:\n"
            "- Do not generate the full world map here. Return only the starting location and 1-3 essential anchor locations; detailed surrounding locations are generated later in small batches.\n"
        )
    if manager_name == "create_world_location_batch":
        instruction += (
            "\ncreate_world_location_batch NPC template rules:\n"
            "- If enemy_npc_templates are supplied and a dungeon boss matches one, include boss_npc.npc_template_id with that template id.\n"
        )
        instruction += (
            "\ncreate_world_location_batch rules:\n"
            "- Generate only the requested 3 to 5 new locations, or fewer when remaining_count is smaller.\n"
            "- All human-readable names and descriptions must be Japanese.\n"
            "- Do not duplicate existing location names, roles, capitals, final temples, unique shrines, unique ruins, or other one-off important places from the provided summary.\n"
            "- Each location must include name, kind, danger, and description. kind should be one of settlement, wilderness, dungeon, landmark, road, crossroad, coast, mountain, river, or plain.\n"
            "- Do not create town facilities as world-map locations. Inns, guilds, blacksmiths, shops, temples, and similar places belong inside a settlement's facilities data.\n"
            "- Do not split a dungeon/cave into separate entrance/interior/depth locations. Keep those as subareas of one dungeon location.\n"
            "- Invent location names from the world tone, terrain, local culture, role, and danger. Do not use fixed preset-like names such as 白石街道, 緑瓦の宿場, or repeated motifs such as アルテミス unless explicitly specified.\n"
            "- danger is 0-50 and should generally rise with distance from the starting location, while allowing occasional world-appropriate exceptions.\n"
            "- Locations that can be the final destination, final temple, or final boss area should use danger 40-45.\n"
            "- connections must connect each new location to an existing location or another location from this same batch. Use hours=2 unless the prompt explicitly asks otherwise.\n"
            "- Return compact JSON only. Do not add Markdown or commentary.\n"
        )
    if manager_name == "dungeon_subnode_generator":
        instruction += (
            "\ndungeon_subnode_generator rules:\n"
            "- Return 5 to 20 nodes total, including entrance and deepest.\n"
            "- Include an entrance node with id=\"entrance\" and a deepest/goal node with id=\"deepest\".\n"
            "- Make the graph branch like a small maze. Do not return a single straight line.\n"
            "- Use varied node kinds and descriptions, such as ore_vein, herb_grove, treasure_room, monster_nest, underground_stream, ancient_altar, hidden_chamber, trap_hall, collapsed_passage, or crystal_cavity.\n"
            "- edges must reference existing node ids only.\n"
            "- Do not create separate world locations. These are subnodes inside the current dungeon.\n"
            "- Only nodes that explicitly contain a teleporter, portal, return gate, or similar device may include remote_travel_targets. Each remote_travel_targets item must be {location, subnode}. Omit it for normal rooms.\n"
        )
    if manager_name in {"master_ai_facilitator", "field_event_evaluator", "quest_referee_with_free_action", "quest_referee_event_resolve"}:
        instruction += (
            "\nDangerous-area movement rules:\n"
            "- In dungeons or dangerous areas, movement is limited to current_subnode.adjacent_subnodes unless current_subnode.remote_travel_targets explicitly allows remote movement.\n"
            "- Do not narrate jumping from a dungeon entrance to the objective, from the deepest area back to town, or to a non-adjacent subnode unless the response uses an allowed remote target.\n"
            "- If the player receives a map, route note, or clue for a dungeon interior, reveal it with subnode_map_reveal/unlock_subnode_route instead of marking the nodes visited.\n"
            "- To reveal nearby dungeon rooms after looking around, use subnode_map_reveal={\"scope\":\"surroundings\"}. To reveal a route to the active quest objective, use subnode_map_reveal={\"quest\":\"active\"}.\n"
        )
    if manager_name == "field_event_evaluator":
        instruction += (
            "\nfield_event_evaluator NPC template rules:\n"
            "- If NPC template candidates are supplied and a generated npc/enemy/boss matches one, include npc_template_id with that template id.\n"
        )
        instruction += (
            "\nfield_event_evaluator rules:\n"
            "- If the player explicitly asks to discover, create, or move to a dungeon, discovered_location.kind must be dungeon.\n"
            "- Do not split a dungeon, temple, cave, entrance, interior, depth, or boss room into separate world locations. Put them into one dungeon location and let the game generate subnodes.\n"
            "- If the dungeon premise says a boss, guardian, god, goddess, ruler, lord, or named entity waits there, return boss_npc.\n"
            "- boss_npc must be an NPC object with name, role, description, personality, look, image_generation_prompt, and hostile.\n"
            "- Return compact JSON only. Do not add Markdown or commentary.\n"
        )
    if manager_name == "settlement_quest_generator":
        instruction += (
            "\nsettlement_quest_generator NPC template rules:\n"
            "- If NPC template candidates are supplied and fit the objective, include target_npc_template_id. "
            "Use enemy template ids for defeat targets and rescue blockers; use friendly template ids for rescue targets and delivery targets.\n"
        )
        instruction += (
            "\nsettlement_quest_generator rules:\n"
            "- Generate only the requested 2 to 3 quests per response. Do not fill the whole board at once.\n"
            "- Each quest object must include quest_type, one of rescue, retrieve, defeat, delivery, investigate, or procure.\n"
            "- Defeating, hunting, clearing, or driving away monsters/enemies that block a road or place is always quest_type=\"defeat\".\n"
            "- Only requests to obtain a suitable item from somewhere are quest_type=\"procure\".\n"
            "- Include destination_hint with location_kind, anchor_kind, objective_subnode_name, and objective_description whenever possible.\n"
        )
    if manager_name == "create_initial_character_profile":
        instruction += (
            "\ncreate_initial_character_profile rules:\n"
            "- Return one character object only, not separate create_character/create_look/create_trait/create_skill payloads.\n"
            "- image_generation_prompt should be a compact array of English SDXL tags.\n"
            "- traits and skills may be empty arrays only when the character truly has no notable trait or skill.\n"
            "- Use the supplied element ids for skill.element.\n"
        )
    if manager_name == "master_ai_facilitator":
        instruction += (
            "\nmaster_ai_facilitator home construction rules:\n"
            "- If the player is outside a settlement and clearly tries to build or improve their own house using a specified material item, return home_construction.\n"
            "- home_construction should include usable, material_name, furniture_level_gain, narration, and reason. furniture_level_gain must be 0 to 3.\n"
            "- If the material is not suitable as building material, set usable=false and explain the refusal in narration/reason.\n"
            "- Do not create a player home only by narration. The game side creates the home when construction progress reaches 100%.\n"
        )
    if manager_name == "home_construction_evaluator":
        instruction += (
            "\nhome_construction_evaluator rules:\n"
            "- Judge whether the specified item can reasonably be used as building material or furniture/workshop material for a player home in this world.\n"
            "- Return usable=false for unsuitable items, missing items, obviously fragile/irrelevant items, or materials that cannot help build a home.\n"
            "- furniture_level_gain is 0 to 3. Use 1 for basic material, 2 for good material, 3 for excellent/rare workshop material. Never exceed 3.\n"
            "- Return JSON only.\n"
        )
    if manager_name == "create_settlement_detail":
        instruction += (
            "\ncreate_settlement_detail専用ルール:\n"
            "- トップレベルには必ず settlement_structure_description, atmosphere, settlement_structure, facilities, residents, adventurers を置いてください。\n"
            "- core/spots/districts/landmarks などは settlement_structure の中にだけ入れてください。トップレベルに core/spots だけを返す形式は禁止です。\n"
            "- residents と adventurers に該当者がいない場合も [] を返してください。facilities も不明なら [] を返してください。\n"
            "- 次の外枠を崩さず、値だけを拠点に合わせて埋めてください。\n"
            "{\n"
            '  "settlement_structure_description": "拠点構造の文章",\n'
            '  "atmosphere": "拠点の雰囲気",\n'
            '  "settlement_structure": {"core": "中心施設", "spots": ["施設や広場"]},\n'
            '  "facilities": [{"name": "施設名", "type": "guild", "description": "説明", "npc_name": "担当者名", "npc_role": "役割"}],\n'
            '  "residents": [],\n'
            '  "adventurers": []\n'
            "}\n"
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
    previous = previous_response if isinstance(previous_response, dict) else {}
    previous_keys = {str(key) for key in previous.keys()} if isinstance(previous, dict) else set()
    if manager_name == "create_settlement_detail":
        missing_outer_keys = any(str(error).startswith("missing required key:") for error in errors)
        if not missing_outer_keys:
            return ""
        note = (
            "create_settlement_detailの修正注意:\n"
            "- 前回の応答が core/spots だけの場合、それらはトップレベルではなく settlement_structure の中に入れてください。\n"
            "- トップレベルには必ず settlement_structure_description, atmosphere, settlement_structure, facilities, residents, adventurers を置いてください。\n"
            "- residents/adventurers/facilities が空でも、キー自体は必ず [] として返してください。\n"
            "- 次の外枠を崩さず、値だけを拠点設定に合わせて埋めてください。\n"
            "{\n"
            '  "settlement_structure_description": "拠点構造の文章",\n'
            '  "atmosphere": "拠点の雰囲気",\n'
            '  "settlement_structure": {"core": "中心施設", "spots": ["施設や広場"]},\n'
            '  "facilities": [],\n'
            '  "residents": [],\n'
            '  "adventurers": []\n'
            "}\n"
        )
        if previous_keys & {"core", "spots", "districts", "landmarks", "places", "buildings"}:
            note += "- 前回のトップレベルキー " + ", ".join(sorted(previous_keys & {"core", "spots", "districts", "landmarks", "places", "buildings"})) + " は settlement_structure 内へ移動してください。\n"
        return note
    if manager_name != "create_world_overview":
        return ""
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
    if manager_name == "create_settlement_detail":
        return _repair_settlement_detail_response(value)
    if manager_name == "create_initial_character_profile":
        if isinstance(value, dict):
            for key in ("character", "profile", "npc"):
                nested = value.get(key)
                if isinstance(nested, dict):
                    response = dict(nested)
                    for outer_key, outer_value in value.items():
                        if outer_key != key and outer_key not in response:
                            response[outer_key] = outer_value
                    return response
        return value
    if manager_name == "settlement_quest_generator":
        return _wrap_collection_response(
            value,
            "quests",
            aliases=("quest", "generated_quest", "settlement_quest", "quest_list"),
            item_keys=("name", "overview", "quest_type", "neighboring_settlement", "choices", "reward", "status", "objective"),
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
    if manager_name == "craft_item_generator":
        return _wrap_item_response(
            value,
            "item",
            aliases=("crafted_item", "result", "generated_item"),
            item_keys=("name", "category", "description", "quantity", "value", "rarity", "effects", "llm_effects"),
        )
    return value


def _repair_settlement_detail_response(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    response = dict(value)
    structure_keys = (
        "core",
        "spots",
        "districts",
        "landmarks",
        "places",
        "buildings",
        "shops",
        "gates",
    )
    has_structure_piece = any(key in response for key in structure_keys)
    has_settlement_piece = any(
        key in response
        for key in (
            "settlement_structure",
            "settlement_structure_description",
            "atmosphere",
            "facilities",
            "residents",
            "adventurers",
        )
    )
    if not has_structure_piece and not has_settlement_piece:
        return value

    if "settlement_structure" not in response:
        structure = {key: response[key] for key in structure_keys if key in response}
        if structure:
            response["settlement_structure"] = structure

    if not response.get("settlement_structure_description"):
        response["settlement_structure_description"] = _settlement_structure_summary(response.get("settlement_structure"))
    if not response.get("atmosphere"):
        response["atmosphere"] = "人々の生活音と旅人の気配が混ざる、物語の始まりにふさわしい拠点。"
    if "facilities" not in response or not isinstance(response.get("facilities"), list):
        response["facilities"] = _settlement_facilities_from_structure(response.get("settlement_structure"))
    if "residents" not in response or not isinstance(response.get("residents"), list):
        response["residents"] = []
    if "adventurers" not in response or not isinstance(response.get("adventurers"), list):
        response["adventurers"] = []
    return response


def _settlement_structure_summary(structure: Any) -> str:
    if isinstance(structure, dict):
        core = str(structure.get("core") or "").strip()
        spots = [str(item).strip() for item in _list_from_any(structure.get("spots")) if str(item).strip()]
        if core and spots:
            return f"{core}を中心に、{', '.join(spots[:6])} が並ぶ拠点。"
        if core:
            return f"{core}を中心に人と施設が集まる拠点。"
        for key in ("districts", "landmarks", "places", "buildings", "shops", "gates"):
            values = [str(item).strip() for item in _list_from_any(structure.get(key)) if str(item).strip()]
            if values:
                return f"{', '.join(values[:6])} が配置された拠点。"
    if isinstance(structure, list):
        values = [str(item).strip() for item in structure if str(item).strip()]
        if values:
            return f"{', '.join(values[:6])} が配置された拠点。"
    return "中心施設と生活区、旅人向けの施設がまとまった拠点。"


def _settlement_facilities_from_structure(structure: Any) -> list[dict[str, Any]]:
    names: list[str] = []
    if isinstance(structure, dict):
        for key in ("spots", "shops", "buildings", "places", "districts", "landmarks"):
            names.extend(str(item).strip() for item in _list_from_any(structure.get(key)) if str(item).strip())
        core = str(structure.get("core") or "").strip()
        if core:
            names.append(core)
    elif isinstance(structure, list):
        names.extend(str(item).strip() for item in structure if str(item).strip())

    facilities: list[dict[str, Any]] = []
    for name in names:
        facility_type = _settlement_facility_type(name)
        if not facility_type:
            continue
        if any(_normalise_text(item.get("name")) == _normalise_text(name) for item in facilities):
            continue
        facilities.append(
            {
                "name": name,
                "type": facility_type,
                "description": f"{name}はこの拠点の内部施設。",
                "npc_name": "",
                "npc_role": _settlement_facility_role(facility_type),
            }
        )
    return facilities


def _settlement_facility_type(name: str) -> str:
    text = str(name or "").casefold()
    mapping = (
        ("guild", ("guild", "adventurer", "quest board", "ギルド", "冒険者", "依頼掲示板", "掲示板")),
        ("town_hall", ("town hall", "city hall", "municipal", "役場", "市庁舎", "役所", "行政庁")),
        ("black_market", ("black market", "闇商店", "闇市")),
        ("blacksmith", ("blacksmith", "smith", "鍛冶", "武器", "防具", "武具")),
        ("apothecary", ("apothecary", "potion", "medicine", "薬", "薬品", "治療")),
        ("food_store", ("food", "grocery", "食料", "食品")),
        ("material_store", ("material", "素材", "鉱石", "採集")),
        ("magic_store", ("magic", "scroll", "魔術", "魔法", "巻物")),
        ("inn", ("inn", "宿", "旅籠")),
        ("temple", ("temple", "church", "shrine", "神殿", "教会", "寺院", "大聖堂")),
        ("market", ("market", "shop", "store", "市場", "商店", "通り")),
    )
    for facility_type, needles in mapping:
        if any(needle in text for needle in needles):
            return facility_type
    return ""


def _settlement_facility_role(facility_type: str) -> str:
    return {
        "guild": "ギルド受付",
        "town_hall": "役場職員",
        "black_market": "闇商人",
        "blacksmith": "鍛冶職人",
        "apothecary": "薬師",
        "food_store": "食料店主",
        "material_store": "素材商",
        "magic_store": "魔術商",
        "inn": "宿の主人",
        "temple": "神官",
        "market": "商人",
    }.get(facility_type, "施設の担当者")


def _list_from_any(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _normalise_text(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


def _wrap_item_response(
    value: Any,
    item_key: str,
    *,
    aliases: tuple[str, ...],
    item_keys: tuple[str, ...],
) -> Any:
    if not isinstance(value, dict):
        return value
    response = dict(value)
    if item_key in response:
        return response
    for alias in aliases:
        if alias in response:
            response[item_key] = response[alias]
            return response
    if any(key in response for key in item_keys):
        item = {key: item_value for key, item_value in response.items() if key in item_keys}
        response = {key: item_value for key, item_value in response.items() if key not in item_keys}
        response[item_key] = item
        response.setdefault("narration", str(response.get("text") or response.get("message") or ""))
    return response


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
