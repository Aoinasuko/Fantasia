from __future__ import annotations

import json
import random
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from . import npc_generate
from . import combat_flow
from .action_roll import (
    _normalise_roll_target,
    action_roll_judgement_context,
    action_roll_system_prompt,
    make_action_roll as _make_game_action_roll,
    normalise_action_roll_judgement,
    should_use_action_roll as _should_use_action_roll,
)
from .image_pipeline import process_subject_image
from .imagegen import BaseImageBackend, ImageResult
from .i18n import ELEMENT_IDS, tr_enum
from .combat import (
    _capture_subnode_description,
    _capture_subnode_name,
    _response_implies_capture_relocation,
)
from .combat_llm_tool import CombatToolCall, CombatToolName, run_combat_tool
from .combat_buff import (
    effective_attributes as _combat_effective_attributes,
    has_buff_type as _combat_has_buff_type,
    stat_delta as _combat_stat_delta,
    status_blocks_attack as _combat_status_blocks_attack,
    status_blocks_escape as _combat_status_blocks_escape,
    status_blocks_skill as _combat_status_blocks_skill,
    tick_buffs as _combat_tick_buffs,
)
from .combat_model import combat_effect_type, combat_skill_sp_cost, normalise_combat_skill
from .craft import (
    CraftPlan,
    build_craft_result,
    craft_intent_payload as _craft_intent_payload,
    craft_material_phrases as _craft_material_phrases,
    craft_preview_text,
    determine_craft_plan,
    match_craft_candidate as _match_craft_candidate,
    normalise_craft_intent as _normalise_craft_intent,
)
from .items import (
    EQUIPMENT_SLOT_LABELS,
    EQUIPMENT_SLOTS,
    ITEM_CATEGORY_IDS,
    add_item_stack,
    calculate_equipment_summary,
    can_add_item_stack,
    equipment_slot_for_category,
    extract_response_rewards,
    generate_reward_item,
    inventory_slot_count,
    is_equipment_item,
    choose_item_template,
    item_template_by_id,
    item_label,
    make_item,
    make_item_from_template_id,
    normalise_item,
    reward_log_lines,
    take_item_stack,
)
from .json_response import JsonResponseError, retry_prompt, sanitize_retry_response, schema_instruction, validate_manager_response
from .json_store import JsonStore
from .llm import BaseLlmBackend
from .llm_tool import (
    LlmToolCall,
    LlmToolName,
    apply_common_response_tools,
    apply_npc_action_tool as apply_llm_npc_action_tool,
    requested_location_from_tools,
    response_tool_calls,
    run_llm_tool,
    tool_effect_payload,
    tool_prompt_instruction,
)
from .npc_templates import (
    ENEMY_NPC_TEMPLATE_CATEGORIES,
    FRIENDLY_NPC_TEMPLATE_CATEGORIES,
    choose_npc_template,
    npc_template_prompt_summaries,
    used_npc_template_ids,
)
from .paths import GENERATED_DIR
from .player_action import ActionCommandType, resolve_player_input as resolve_player_action_input
from .prompt_templates import PromptTemplateStore
from .quest_context import (
    _hide_internal_quest_tokens,
    _quest_ai_context,
)
from .quest_rules import (
    INTERNAL_QUEST_TOKEN_LABELS,
    QUEST_ABANDON_CHOICE_LABEL,
    QUEST_BOARD_CHOICE_LABEL,
    QUEST_BOARD_NAME,
    QUEST_DEADLINE_HOURS,
    QUEST_REPORT_CHOICE_LABEL,
    QUEST_REPORT_STAGE,
    QUEST_TYPES,
    SETTLEMENT_QUEST_BATCH_MAX,
    SETTLEMENT_QUEST_BATCH_MIN,
    SETTLEMENT_QUEST_MAX_PER_SETTLEMENT,
    _infer_quest_finish_status,
    _is_quest_abandon_action,
    _map_reveal_reason,
    _map_reveal_value_means_active_quest,
    _normalise_quest_type_id,
    _quest_anchor_kind_from_text,
    _quest_destination_danger,
    _quest_destination_hint,
    _quest_destination_name,
    _quest_destination_source_text,
    _quest_event_needs_resolve,
    _quest_finish_status,
    _quest_from_raw,
    _quest_location_kind_from_text,
    _quest_location_kind_label,
    _quest_objective_name_from_text,
    _quest_payload_has_reward,
    _quest_requires_captor,
    _quest_response_narration,
    _quest_start_choices,
    _quest_text_requests_new_site,
    _quest_type,
)
from .save_store import SaveSlot, SaveStore
from .status_effects import (
    FLED_STATUS_ID,
    INCAPACITATED_STATUS_ID,
    INCAPACITATED_STATUS_NAME,
    SURRENDERED_STATUS_ID,
    STATUS_IMMUNITY_EFFECT_IDS,
    canonical_status_effect_id,
    _contextual_incapacitated_status_details,
    _global_status_target,
    _merge_status_effect,
    _normalise_status_effect,
    _status_effect_action_uses_mouth,
    _status_effect_applied_line,
    _status_effect_blocks_action,
    _status_effect_blocks_attack,
    _status_effect_blocks_escape,
    _status_effect_blocks_movement,
    _status_effect_blocks_skill,
    _status_effect_from_status_text,
    _status_effect_has_generic_incapacitated_description,
    _status_effect_has_generic_incapacitated_name,
    _status_effect_has_generic_incapacitated_text,
    _status_effect_id,
    _status_effect_is_incapacitating,
    _status_effect_is_surrendered_or_fled,
    _status_effect_items,
    _status_effect_merge_key,
    _status_effect_removed_line,
    _status_effect_target,
    _status_response_context_text,
    _tick_status_effects,
)
from .world_generation import (
    ACTOR_SUBNODE_ID_FLAG,
    ACTOR_SUBNODE_LOCATION_FLAG,
    CURRENT_SUBNODE_FLAG,
    DEFAULT_SUBNODE_ID,
    DEFAULT_WORLD_CRIME_RISK,
    DEFAULT_WORLD_ENEMY_STRENGTH,
    DEFAULT_WORLD_LOCATION_COUNT,
    DUNGEON_DEEPEST_SUBNODE_ID,
    DUNGEON_ENTRY_SUBNODE_ID,
    DUNGEON_SUBNODE_LAYOUT_VERSION,
    FANTASY_LOCATION_PREFIXES,
    FANTASY_LOCATION_STEMS,
    SUBNODE_EXTERNAL_PREFIX,
    SUBNODE_GRAPH_KEY,
    WORLD_CRIME_RISK_OPTIONS,
    WORLD_DANGER_MAX,
    WORLD_ENEMY_STRENGTH_OPTIONS,
    WORLD_FINAL_DANGER_MAX,
    WORLD_FINAL_DANGER_MIN,
    WORLD_LOCATION_BATCH_MAX,
    WORLD_LOCATION_BATCH_MIN,
    WORLD_LOCATION_COUNT_OPTIONS,
    WORLD_LOCATION_KIND_LABELS,
    WORLD_LOCATION_KIND_OPTIONS,
    WORLD_MAP_EDGE_HOURS,
    WORLD_MAP_MAX_DYNAMIC_DEGREE,
    _clamp_world_danger,
    _dungeon_branch_parent,
    _dungeon_scale_label,
    _dungeon_subnode_target_count,
    _ensure_dungeon_graph_connected,
    _explicit_dungeon_location_request,
    _explicit_generated_dungeon_location_request,
    _fallback_dungeon_subnode_layout,
    _fallback_world_location_description,
    _fallback_world_location_kind,
    _fallback_world_location_name,
    _generated_dungeon_boss_payload,
    _generated_dungeon_boss_required,
    _generated_dungeon_boss_text_implies_boss,
    _infer_world_location_kind,
    _infer_world_location_kind_for_request,
    _infer_world_location_kind_for_world_generation,
    _looks_like_facility_location_name,
    _merge_dungeon_subnode_layout,
    _protected_dungeon_subnodes,
    _safe_subnode_kind,
    _world_connection_payloads,
    _world_customization_settings,
    _world_default_danger_for_index,
    _world_generation_dungeon_has_boss,
    _world_generation_location_danger,
    _world_generation_named_location_requested_as_dungeon,
    _world_generation_premise_refers_to_location,
    _world_kind_is_settlement,
    _world_location_allows_world_map_departure,
    _world_location_batch_max_tokens,
    _world_location_batch_size,
    _world_location_blocks_world_map_departure,
    _world_location_danger_from_payload,
    _world_location_description_from_payload,
    _world_location_is_final_endpoint_candidate,
    _world_location_is_world_map_exit,
    _world_location_kind_guidance,
    _world_location_name_from_payload,
    _world_location_name_key,
    _world_location_payloads,
    _world_location_target_count,
    _world_overview_max_tokens,
)
from .item_generate_loottabel import choose_loot_table_by_tag, generate_loot_table_items, loot_table_by_id
from .world_generate import (
    generate_template_world,
    install_template_dungeon_subnode_graph,
    refresh_template_subnode_loot,
)
from .character import Character
from .world_model import GameStateData, LocationData, QuestData, WorldData


SEASONS = ("春", "夏", "秋", "冬")
DAYS_PER_SEASON = 60
HOURS_PER_DAY = 24
WORLD_DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
INITIAL_WORLD_TIME_HOURS = 8
PLAYER_MAX_HUNGER = 50
PLAYER_HUNGER_PER_HOUR = 1
PLAYER_STARVATION_HP_SP_DAMAGE = 3
PLAYER_MAX_LEVEL = 50
PLAYER_BASE_EXP_TO_NEXT = 5
PLAYER_MAX_EXP_TO_NEXT = 100_000_000
MAX_EXPLORATION_CHOICES = 5
TEMP_LLM_CONTEXT_MAX_CHARS = 16_000
TEMP_LLM_CONTEXT_EVENT_LIMIT = 8
TEMP_CONTEXT_AWARE_MANAGERS = {
    "master_ai_facilitator",
    "field_event_evaluator",
    "conversation_starter",
    "conversation_facilitator",
    "conversation_resolver",
    "quest_referee_with_free_action",
    "quest_referee_event_resolve",
    "quest_procurement_checker",
    "facility_request_evaluator",
    "home_construction_evaluator",
    "input_gatekeeper",
    "check_action_feasibility",
    "craft_item_generator",
    "combat_player_action",
    "combat_enemy_action",
}
COMBAT_MAX_OPPONENTS = 3
REPEATED_INPUT_DEDUPE_SECONDS = 4.0
DEFAULT_GUILD_NAME = "冒険者ギルド"
MOVE_CHOICE_LABEL = "移動する"
PLAYER_HOMES_KEY = "player_homes"
PLAYER_HOME_CONSTRUCTION_KEY = "player_home_construction"
PLAYER_HOME_SUBNODE_ID = "player_home"
PLAYER_HOME_KIND = "player_home"
PLAYER_HOME_NAME = "プレイヤーの家"
PLAYER_HOME_MAX_LEVEL = 10
PLAYER_HOME_BUILD_PROGRESS_STEP = 25
PLAYER_HOME_REST_HOURS = 8
PLAYER_REST_INN_COST = 50
PLAYER_HOME_TOWN_HALL_PLANS = {500: 3, 1000: 5, 10000: 7}
PLAYER_HOME_CHOICES = ("保存箱を開く", "クラフトを行う", "休息する", "家から出る")
COMBAT_CHOICE_ATTACK_MENU = "攻撃対象選択"
COMBAT_CHOICE_SKILL_MENU = "スキル一覧"
COMBAT_CHOICE_ESCAPE = "逃走する"
COMBAT_CHOICE_ACCEPT_SURRENDER = "降伏を受け入れる"
COMBAT_CHOICE_BACK = "戻る"
COMBAT_CHOICE_ATTACK_PREFIX = "攻撃: "
COMBAT_CHOICE_SKILL_PREFIX = "スキル: "
COMBAT_CHOICE_TARGET_PREFIX = "対象: "
COMBAT_CHOICE_MENU_FLAG = "combat_choice_menu"
SKILL_POWER_MIN = 1
SKILL_POWER_MAX = 5
NPC_DEFAULT_POWER_BUDGET = npc_generate.NPC_DEFAULT_POWER_BUDGET
PLAYER_UNLIMITED_POWER_BUDGET = 999
CHARACTER_DEFAULT_ATTRIBUTES = npc_generate.CHARACTER_DEFAULT_ATTRIBUTES
NPC_ATTRIBUTE_GENERATED_FLAG = npc_generate.NPC_ATTRIBUTE_GENERATED_FLAG
NPC_ATTRIBUTE_PROFILE_KEY = npc_generate.NPC_ATTRIBUTE_PROFILE_KEY
NPC_MAX_LEVEL = npc_generate.NPC_MAX_LEVEL
NPC_AFFINITY_MIN = -100
NPC_AFFINITY_MAX = 100
NPC_AFFINITY_DELTA_MIN = -10
NPC_AFFINITY_DELTA_MAX = 10
_character_runtime_attributes = npc_generate._character_runtime_attributes
_npc_level_tendency_attributes = npc_generate._npc_level_tendency_attributes
_character_calculated_max_hp = npc_generate._character_calculated_max_hp
_character_calculated_max_sp = npc_generate._character_calculated_max_sp
_character_calculated_attack = npc_generate._character_calculated_attack
_character_calculated_defense = npc_generate._character_calculated_defense
_danger_scaled_placeholder_enemy = npc_generate._danger_scaled_placeholder_enemy
_scale_character_for_danger = npc_generate._scale_character_for_danger
_character_state_is_dead = npc_generate._character_state_is_dead
_npc_from_raw = npc_generate._npc_from_raw
_enemy_npc_from_raw = npc_generate._enemy_npc_from_raw
_npc_generation_requests = npc_generate.npc_generation_requests
_infer_npc_generation_requests = npc_generate.infer_npc_generation_requests
_dedupe_npc_requests = npc_generate.dedupe_npc_requests
_filter_npc_generation_requests = npc_generate.filter_npc_generation_requests
_npc_request_name = npc_generate.npc_request_name
_should_generate_npc_name = npc_generate.should_generate_npc_name
_world_has_dead_npc_identity = npc_generate.world_has_dead_npc_identity
COMPANION_WAIT_RETURN_DAYS = 3
PLAYER_INVENTORY_MAX_SLOTS = 27

FACILITY_KEYWORDS = (
    "guild",
    "adventurer",
    "quest board",
    "board",
    "blacksmith",
    "black market",
    "apothecary",
    "food store",
    "material store",
    "general store",
    "magic store",
    "town hall",
    "city hall",
    "municipal office",
    "役場",
    "市庁舎",
    "闇商店",
    "闇市",
    "薬品店",
    "薬屋",
    "食料店",
    "素材店",
    "雑貨店",
    "魔術店",
    "魔法店",
    "smith",
    "weapon shop",
    "armor shop",
    "shop",
    "store",
    "market",
    "inn",
    "tavern",
    "bar",
    "temple",
    "church",
    "clinic",
    "hospital",
    "apothecary",
    "library",
    "stable",
    "bath",
    "鍛冶",
    "武器屋",
    "防具屋",
    "道具屋",
    "雑貨屋",
    "市場",
    "店",
    "宿",
    "酒場",
    "ギルド",
    "依頼掲示板",
    "掲示板",
    "教会",
    "神殿",
    "寺院",
    "診療所",
    "病院",
    "薬屋",
    "図書館",
    "厩舎",
    "馬小屋",
    "浴場",
)

SHOP_FACILITY_TYPES = {
    "blacksmith",
    "black_market",
    "apothecary",
    "food_store",
    "material_store",
    "general_store",
    "magic_store",
    "junk_store",
    "shop",
    "market",
}

SETTLEMENT_REQUIRED_SHOP_TYPES = (
    "blacksmith",
    "apothecary",
    "general_store",
)

SETTLEMENT_OPTIONAL_SHOP_TYPES = (
    "food_store",
    "material_store",
    "magic_store",
    "junk_store",
)

DANGER_SUBNODE_RANDOM_ENCOUNTER_CHANCE = 0.20
PARTY_COMPANION_LIMIT = 2
INITIAL_ROUTE_WORLD_LOCATION_COUNT = 10
QUEST_BOARD_REGEN_MIN = 3
QUEST_BOARD_REGEN_MAX = 5

SHOP_FACILITY_PRICE_MULTIPLIERS = {
    "black_market": 3.0,
}

DEFAULT_VENDOR_LOOT_TABEL_ID = "shop_general_store"
SHOP_LOOT_TABEL_BY_FACILITY_TYPE = {
    "blacksmith": "shop_blacksmith",
    "black_market": "shop_black_market",
    "apothecary": "shop_apothecary",
    "clinic": "shop_apothecary",
    "food_store": "shop_food_store",
    "inn": "shop_food_store",
    "tavern": "shop_food_store",
    "material_store": "shop_material_store",
    "magic_store": "shop_magic_store",
    "junk_store": "shop_junk_store",
    "general_store": "shop_general_store",
    "shop": "shop_general_store",
    "market": "shop_general_store",
    "facility": "shop_general_store",
}

SHOP_FACILITY_NAME_BANK = {
    "blacksmith": ("鋼火鍛冶", "赤炉工房", "槌音鍛冶店", "黒鉄武具店"),
    "black_market": ("影市", "月裏商会", "黒帳武具店", "夜鴉商店"),
    "apothecary": ("若葉薬品店", "月露薬房", "白瓶堂", "癒し草の薬屋"),
    "food_store": ("麦籠食料店", "香草食料店", "旅腹亭", "朝市食材店"),
    "material_store": ("素材蔵", "石と根の素材店", "採集者の棚", "原石商会"),
    "general_store": ("よろず屋", "旅支度雑貨店", "何でも棚", "道具箱商店"),
    "magic_store": ("星灯魔術店", "巻物堂", "青燐魔法店", "古文書の塔"),
    "junk_store": ("がらくた市", "壊れ物横丁", "拾い物倉庫", "錆び棚商店"),
    "shop": ("よろず屋", "旅支度雑貨店", "何でも棚", "道具箱商店"),
    "market": ("広場市場", "朝市", "旅人市場", "屋台通り"),
}

GENERIC_SHOP_FACILITY_NAMES = {
    "blacksmith",
    "black market",
    "apothecary",
    "food store",
    "material store",
    "general store",
    "magic store",
    "shop",
    "store",
    "market",
    "鍛冶屋",
    "武器屋",
    "防具屋",
    "武具屋",
    "闇商店",
    "闇市",
    "薬品店",
    "薬屋",
    "食料店",
    "素材店",
    "雑貨店",
    "魔術店",
    "魔法店",
    "道具屋",
    "商店",
    "市場",
}

MOVEMENT_KEYWORDS = (
    "go to",
    "visit",
    "enter",
    "move to",
    "head to",
    "行く",
    "向かう",
    "入る",
    "訪ねる",
    "寄る",
    "探す",
    "開く",
    "見る",
)


class GameEngine:
    def __init__(
        self,
        llm: BaseLlmBackend,
        image_backend: BaseImageBackend,
        store: JsonStore,
        save_store: SaveStore | None = None,
        prompt_templates: PromptTemplateStore | None = None,
        allow_any_action_concept: bool = False,
        reveal_world_map_on_generation: bool = False,
    ) -> None:
        self.llm = llm
        self.image_backend = image_backend
        self.store = store
        self.save_store = save_store or SaveStore()
        self.prompt_templates = prompt_templates or PromptTemplateStore()
        self.allow_any_action_concept = bool(allow_any_action_concept)
        self.reveal_world_map_on_generation = bool(reveal_world_map_on_generation)
        self.state = GameStateData()
        self._last_resolved_input: dict[str, Any] = {}
        self._temp_llm_context_events: list[dict[str, Any]] = []

    def _create_world_legacy(
        self,
        world_name: str,
        premise: str,
        player_character: Character | None = None,
        save_game: bool = True,
        crime_risk: str = DEFAULT_WORLD_CRIME_RISK,
        enemy_strength: str = DEFAULT_WORLD_ENEMY_STRENGTH,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> str:
        requested_world_name = world_name.strip()
        player = (player_character.name if player_character else "").strip() or "Player"
        premise_text = premise.strip() or "霧深い辺境、古い魔法、探索"
        target_location_count = _world_location_target_count(location_count)
        customization = _world_customization_settings(crime_risk, enemy_strength)
        self._emit_world_generation_progress(progress_callback, "content_check", "内容確認中", 0, 100)
        world_check = self._check_world_content_violation(requested_world_name or "unknown", premise_text)
        premise_context = _short_text(premise_text, 5000)
        if _as_bool(world_check.get("content_violation")):
            message = str(world_check.get("message") or world_check.get("reason") or "世界生成を開始できませんでした。")
            self.state = GameStateData(
                player_name=player,
                display_log=[message],
                flags={
                    "premise": premise_text,
                    "world_content_check": _strip_response_metadata(world_check),
                    "screen_mode": "exploration",
                },
            )
            return self.state.log_text()

        self._emit_world_generation_progress(progress_callback, "world_overview", "世界概要を生成中", 8, 100)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのワールドビルダーです。"
                    "必ず日本語で、Fantasiaのcreate_world_overview相当として、"
                    "world_name, overview, structure_description, structure, locations, connections を持つJSONだけを返してください。"
                    "locationsは世界地図の地点一覧、connectionsは地点間を2時間で結ぶ線です。"
                    "開始地点が自然に決まる場合は starting_location も追加してください。"
                    "危険度 danger は0〜50で表し、基本的に開始地点から遠いほど高くしてください。ただし物語上の例外は許可します。"
                    "旅の最終地点・最終神殿・ラスボス地点になりえる場所は danger=40〜45 にしてください。"
                    "街の施設（宿屋、鍛冶屋、ギルド、店など）はロケーションにせず、街の内部施設として扱ってください。"
                    "ただし、ユーザーが明示した神殿・寺院がダンジョン、最終地点、ボスが待つ場所なら kind=dungeon として扱ってください。"
                    "洞窟やダンジョンの入口・内部・奥は同じダンジョンロケーション内のサブ地点として扱い、別ロケーションにしないでください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"希望世界名: {requested_world_name or 'AIに任せる'}\n"
                    f"初期ロケーション数: {target_location_count}\n"
                    f"ゲーム設定: {json.dumps(customization, ensure_ascii=False)}\n"
                    f"使用可能なロケーション種別: {json.dumps(_world_location_kind_guidance(), ensure_ascii=False)}\n"
                    "地名命名ルール: 固定の候補リストは使わず、世界観、文化、地形、危険度、役割から新しい地名を考えてください。"
                    "特に指定がない場合はファンタジーRPGらしい固有名に寄せ、白石街道、緑瓦の宿場、アルテミスのような反復しやすい既存モチーフは避けてください。\n"
                    f"次の雰囲気で、新しいRPG世界の初期状態を作ってください: {premise_context}"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "World map generation is split into small batches. In create_world_overview, do not create all "
                    f"{target_location_count} locations at once. Return only the starting location and 1-3 essential "
                    "anchor locations that define the world. Later managers will generate surrounding locations in "
                    "3-5 location batches using the overview, existing map summary, neighboring terrain, danger, and world tone. "
                    "Invent location names from the world's culture, terrain, role, and danger. Do not rely on fixed sample names; avoid repeating motifs such as アルテミス."
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Important location rule: starting_location must be the starting settlement/town/village itself, "
                    "not an inn, plaza, guild, shop, room, gate, or other sub-place inside the town. Put those sub-places "
                    "inside the settlement's facilities or subnodes instead of making them world-map locations."
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Game customization must affect generated world data. If crime_risk is normal or strict, "
                    "settlement locations should describe public order and may set extra.crime_risk_multiplier from 0.0 to 2.0. "
                    "0.0 means crime is effectively ignored there, 1.0 is ordinary, and 2.0 is severe enforcement. "
                    "Enemy strength is handled by the game rules, but danger_level should still represent how threatening "
                    "each location is on a 0-50 scale."
                ),
            }
        )
        response = self._chat_json(
            "create_world_overview",
            messages,
            max_tokens=_world_overview_max_tokens(target_location_count),
            world_name="unknown",
            player_name=requested_world_name or player,
        )

        self._emit_world_generation_progress(progress_callback, "location_graph", f"ロケーションを生成中（0/{target_location_count}）", 20, 100)
        world = WorldData.from_overview(_strip_response_metadata(response))
        _normalise_world_starting_location(world, response)
        world.extra["customization"] = dict(customization)
        world.extra["crime_risk"] = customization["crime_risk"]
        world.extra["enemy_strength"] = customization["enemy_strength"]
        if requested_world_name:
            world.world_name = requested_world_name
        if world.world_name == "unknown":
            world.world_name = "硝子森の辺境"
        if world.starting_location == "unknown":
            world.starting_location = "灯守りの町"
            world.ensure_location(world.starting_location)
        self._ensure_world_location_graph(
            world,
            response,
            premise_text,
            target_location_count,
            progress_callback=progress_callback,
            progress_start=20,
            progress_end=45,
        )
        self._emit_world_generation_progress(progress_callback, "story", "ストーリー生成準備中", 46, 100)
        self._mark_location_visited(world, world.starting_location)
        world.history.append(
            {
                "manager": "create_world_overview",
                "premise": premise_text,
                "customization": dict(customization),
                "response": _strip_response_metadata(response),
            }
        )

        self._emit_world_generation_progress(progress_callback, "story", "ストーリーを生成中", 48, 100)
        story = self._create_story(player, premise_text, world)
        self._apply_story(world, story)
        world.history.append(
            {
                "manager": "create_story",
                "response": _strip_response_metadata(story),
            }
        )

        settlement_location = world.starting_location
        self._emit_world_generation_progress(progress_callback, "settlement", "初期拠点を生成中", 60, 100)
        settlement = self._create_settlement_detail(player, world, settlement_location)
        self._apply_settlement_detail(world, settlement_location, settlement)
        world.history.append(
            {
                "manager": "create_settlement_detail",
                "location": settlement_location,
                "response": _strip_response_metadata(settlement),
            }
        )

        self._emit_world_generation_progress(progress_callback, "characters", "NPCを生成中", 70, 100)
        self._enrich_initial_characters(player, premise_text, world, progress_callback=progress_callback, progress_start=70, progress_end=82)
        self._emit_world_generation_progress(progress_callback, "quests", "クエストと報酬を生成中", 82, 100)
        settlement_quests = self._generate_settlement_quests(player, world, settlement_location)
        self._apply_settlement_quests(world, settlement_quests, settlement_location)
        world.history.append(
            {
                "manager": "settlement_quest_generator",
                "location": settlement_location,
                "response": _strip_response_metadata(settlement_quests),
            }
        )

        self._emit_world_generation_progress(progress_callback, "initial_narration", "初期場面を生成中", 92, 100)
        initial = self._create_initial_narration(player, premise_text, world)
        opening = str(
            initial.get("narration")
            or initial.get("text")
            or response.get("opening")
            or response.get("overview")
            or "物語が始まった。"
        )
        initial_location = str(initial.get("location") or world.starting_location)
        initial_facility_name = ""
        current_location = settlement_location
        settlement_for_initial = world.locations.get(settlement_location)
        if settlement_for_initial:
            initial_facility_name = _facility_name_from_sub_location(settlement_for_initial, initial_location)
            if initial_facility_name:
                current_location = settlement_location
            elif (
                initial_location
                and initial_location != settlement_location
                and _looks_like_facility_location_name(initial_location)
                and not _is_reserved_settlement_facility_name(initial_location)
            ):
                initial_facility_name = initial_location
                facilities = settlement_for_initial.extra.get("facilities")
                if not isinstance(facilities, list):
                    facilities = []
                    settlement_for_initial.extra["facilities"] = facilities
                if not _facility_exists([item for item in facilities if isinstance(item, dict)], initial_facility_name):
                    facilities.append(
                        _facility_record(
                            initial_facility_name,
                            settlement_for_initial.name,
                            _facility_type_from_name(initial_facility_name),
                        )
                    )
                current_location = settlement_location
            elif initial_location and initial_location != settlement_location:
                settlement_for_initial.extra["initial_sub_location"] = initial_location
        dungeon_parent = _existing_dungeon_location_for_subarea(world, initial_location)
        if dungeon_parent:
            _record_location_subarea(world, dungeon_parent, initial_location)
            current_location = dungeon_parent
        self._mark_location_visited(world, current_location)
        world.history.append(
            {
                "manager": "narrator_initial",
                "location": current_location,
                "reported_location": initial_location,
                "response": _strip_response_metadata(initial),
            }
        )
        choices = _augment_location_choices_for_world(
            world,
            current_location,
            _filter_llm_display_choices(_as_str_list(initial.get("choices") or response.get("choices"))),
            active_quest=False,
        )
        if self.reveal_world_map_on_generation:
            self._reveal_all_world_map_locations(world)
        self.state = GameStateData.new_game(player, world, opening, choices)
        self._set_world_time_total_hours(INITIAL_WORLD_TIME_HOURS)
        self.state.flags["premise"] = premise_text
        self.state.flags["world_customization"] = dict(customization)
        self.state.flags["world_content_check"] = _strip_response_metadata(world_check)
        self.state.flags["llm_backend"] = str(response.get("_backend") or "")
        self.state.flags["initial_llm_backend"] = str(initial.get("_backend") or response.get("_backend") or "")
        self.state.flags["screen_mode"] = "exploration"
        initial_graph = self._ensure_location_subnode_graph(world, self.state.current_location)
        if initial_graph:
            self._set_current_subnode(self.state.current_location, self._default_subnode_for_location(world.locations.get(self.state.current_location)))
        self._apply_visual_intent(initial, "narrator_initial", self.state.current_location)
        if player_character:
            self._install_player_character(player_character)
        if initial_facility_name and settlement_for_initial:
            facility = self._find_or_create_facility_record(settlement_for_initial, initial_facility_name)
            if facility:
                self._set_active_facility(settlement_for_initial, facility)
                self._ensure_facility_npc(settlement_for_initial, facility, settlement_for_initial.name)
        if save_game:
            self.save_game()
        self._emit_world_generation_progress(progress_callback, "completed", "ワールド生成完了", 100, 100)
        return self.state.log_text()

    def create_world(
        self,
        world_name: str,
        premise: str,
        player_character: Character | None = None,
        save_game: bool = True,
        location_count: int = DEFAULT_WORLD_LOCATION_COUNT,
        crime_risk: str = DEFAULT_WORLD_CRIME_RISK,
        enemy_strength: str = DEFAULT_WORLD_ENEMY_STRENGTH,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> str:
        requested_world_name = world_name.strip()
        player = (player_character.name if player_character else "").strip() or "Player"
        premise_text = premise.strip() or "霧深い辺境と忘れられた遺跡を巡る幻想RPG"
        target_location_count = INITIAL_ROUTE_WORLD_LOCATION_COUNT
        customization = _world_customization_settings(crime_risk, enemy_strength)

        self._emit_world_generation_progress(progress_callback, "content_check", "内容確認中", 0, 100)
        world_check = self._check_world_content_violation(requested_world_name or "unknown", premise_text)
        if _as_bool(world_check.get("content_violation")):
            message = str(world_check.get("message") or world_check.get("reason") or "世界生成を開始できませんでした。")
            self.state = GameStateData(
                player_name=player,
                display_log=[message],
                flags={
                    "premise": premise_text,
                    "world_content_check": _strip_response_metadata(world_check),
                    "screen_mode": "exploration",
                },
            )
            return self.state.log_text()

        self._emit_world_generation_progress(progress_callback, "world_theme", "世界設定を生成中", 8, 100)
        theme = self._create_world_theme(
            player,
            requested_world_name,
            premise_text,
            target_location_count,
            customization,
        )
        world = self._world_from_local_theme(theme, requested_world_name, premise_text, customization)

        self._emit_world_generation_progress(progress_callback, "location_templates", "ロケーションテンプレートからワールドを生成中", 18, 100)
        generate_template_world(
            self,
            world,
            player_name=player,
            premise=premise_text,
            theme=theme,
            customization=customization,
            progress_callback=progress_callback,
            progress_start=18,
            progress_end=48,
        )

        self._emit_world_generation_progress(progress_callback, "location_templates", "テンプレートロケーションを配置済み", 48, 100)
        self._recalculate_world_graph_layout(world)

        self._emit_world_generation_progress(progress_callback, "story", "ストーリーを生成中", 50, 100)
        self._mark_location_visited(world, world.starting_location)
        world.history.append(
            {
                "manager": "create_world_theme",
                "premise": premise_text,
                "customization": dict(customization),
                "response": _strip_response_metadata(theme),
            }
        )
        story = self._create_story(player, premise_text, world)
        self._apply_story(world, story)
        world.history.append(
            {
                "manager": "create_story",
                "response": _strip_response_metadata(story),
            }
        )

        settlement_location = world.starting_location
        self._emit_world_generation_progress(progress_callback, "settlement", "初期拠点のテンプレート施設を確定中", 62, 100)
        if world.locations.get(settlement_location):
            self._ensure_settlement_facilities(world.locations[settlement_location])
        self._set_starting_settlement_gate(world)

        self._emit_world_generation_progress(progress_callback, "characters", "NPCを生成中", 72, 100)
        self._enrich_initial_characters(player, premise_text, world, progress_callback=progress_callback, progress_start=72, progress_end=84)
        self._emit_world_generation_progress(progress_callback, "quests", "クエストと報酬を生成中", 84, 100)
        initial_quest_count = self._quest_board_target_count(world, settlement_location, day=1)
        settlement_quests = self._generate_settlement_quests(player, world, settlement_location, target_count=initial_quest_count)
        self._apply_settlement_quests(world, settlement_quests, settlement_location)
        world.extra.setdefault("quest_board_generation", {})[settlement_location] = {
            "day": 1,
            "count": initial_quest_count,
            "source": "world_generation_initial",
        }
        world.history.append(
            {
                "manager": "settlement_quest_generator",
                "location": settlement_location,
                "count": initial_quest_count,
                "response": _strip_response_metadata(settlement_quests),
            }
        )
        if self.reveal_world_map_on_generation:
            self._reveal_all_world_map_locations(world)

        opening = self._local_world_opening(theme, story, world)
        choices = _augment_location_choices_for_world(
            world,
            settlement_location,
            self._location_default_choices(settlement_location),
            active_quest=False,
        )
        self.state = GameStateData.new_game(player, world, opening, choices)
        self._set_world_time_total_hours(INITIAL_WORLD_TIME_HOURS)
        self.state.flags["premise"] = premise_text
        self.state.flags["world_customization"] = dict(customization)
        self.state.flags["world_content_check"] = _strip_response_metadata(world_check)
        self.state.flags["llm_backend"] = str(theme.get("_backend") or "")
        self.state.flags["initial_llm_backend"] = str(theme.get("_backend") or "")
        self.state.flags["screen_mode"] = "exploration"
        self._set_starting_settlement_gate(world)
        self._set_current_subnode(settlement_location, "gate")
        if player_character:
            self._install_player_character(player_character)
        self._emit_world_generation_progress(progress_callback, "final_boss", "Generating final dungeon boss", 96, 100)
        final_boss_event = self._ensure_final_destination_boss(world, premise_text)
        if final_boss_event:
            world.history.append(
                {
                    "manager": "world_generation_final_dungeon_boss",
                    "location": final_boss_event.get("location"),
                    "boss": final_boss_event,
                }
            )
        if save_game:
            self.save_game()
        self._emit_world_generation_progress(progress_callback, "completed", "ワールド生成完了", 100, 100)
        return self.state.log_text()

    def _create_world_theme(
        self,
        player_name: str,
        requested_world_name: str,
        premise: str,
        target_location_count: int,
        customization: dict[str, str],
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You create only the high-level theme for Fantasia world generation. "
                    "The game will locally decide the map graph, node types, subnode structures, connections, and danger. "
                    "Do not return a location list or connection list. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": _ai_json(
                    {
                        "requested_world_name": requested_world_name,
                        "player_name": player_name,
                        "premise": _short_text(premise, 5000),
                        "target_location_count": target_location_count,
                        "game_customization": customization,
                        "needed": [
                            "world_name",
                            "overview",
                            "structure_description",
                            "structure",
                            "final_destination_concept",
                            "opening",
                        ],
                        "rule": "Only decide world tone, culture, conflict, geography, and the final-destination concept. The game side builds the map skeleton.",
                    }
                ),
            },
        ]
        response = self._chat_json(
            "create_world_theme",
            messages,
            max_tokens=900,
            world_name=requested_world_name or "unknown",
            player_name=player_name,
        )
        if requested_world_name:
            response["world_name"] = requested_world_name
        return response

    def _world_from_local_theme(
        self,
        theme: dict[str, Any],
        requested_world_name: str,
        premise: str,
        customization: dict[str, str],
    ) -> WorldData:
        structure = theme.get("structure")
        if not isinstance(structure, (dict, list)):
            structure = {
                "theme": _short_text(premise, 900),
                "generation_mode": "local_skeleton_llm_descriptions",
            }
        world = WorldData(
            world_name=str(theme.get("world_name") or requested_world_name or "幻想の辺境"),
            overview=str(theme.get("overview") or premise or "未知の世界。"),
            structure_description=str(theme.get("structure_description") or ""),
            structure=structure,
            starting_location="未命名の街00",
            extra={
                "raw_create_world_theme": _strip_response_metadata(theme),
                "customization": dict(customization),
                "crime_risk": customization["crime_risk"],
                "enemy_strength": customization["enemy_strength"],
                "world_generation_mode": "local_skeleton_llm_descriptions",
            },
        )
        return world

    def _build_local_world_skeleton(
        self,
        world: WorldData,
        premise: str,
        target_count: int,
        customization: dict[str, str],
    ) -> None:
        target_count = INITIAL_ROUTE_WORLD_LOCATION_COUNT
        rng = random.Random(f"route-world-skeleton|{world.world_name}|{premise}")
        route_slots = [
            ("settlement", "settlement", "starting_town", "starting_settlement", "未命名の街00"),
            ("single", "road", "road", "route", "未命名の街道01"),
            ("single", "road", "crossroad", "route", "未命名の分かれ道02"),
            ("settlement", "settlement", "village", "settlement", "未命名の村03"),
            ("single", "road", "road", "route", "未命名の街道04"),
            ("single", "plain", "plain", "route", "未命名の平原05"),
            ("settlement", "settlement", "town", "settlement", "未命名の街06"),
            ("single", "road", "road", "route", "未命名の街道07"),
            ("single", "landmark", "landmark", "route", "未命名の目印08"),
            ("dungeon", "dungeon", "final_destination", "final_destination", "未命名の最終ダンジョン09"),
        ]
        coords = [(index, 0) for index in range(len(route_slots))]
        max_distance = len(route_slots) - 1
        specs: list[dict[str, Any]] = []
        graph = {
            "edge_hours": WORLD_MAP_EDGE_HOURS,
            "target_count": target_count,
            "generation_mode": "route_skeleton",
            "grid_origin": [0, 0],
            "danger_rule": "danger is rolled from route distance from the starting town",
            "nodes": {},
            "edges": [],
        }
        world.extra["location_graph"] = graph
        world.extra["local_world_skeleton"] = {
            "version": 2,
            "target_count": target_count,
            "max_grid_distance": max_distance,
            "final_destination_concept": str((world.extra.get("raw_create_world_theme") or {}).get("final_destination_concept") or ""),
            "locations": specs,
        }

        for index, slot in enumerate(route_slots):
            category, kind, subtype, role, placeholder = slot
            grid_x, grid_y = coords[index]
            distance = index
            slot_id = f"loc_{index:03d}"
            danger = self._local_world_danger_for_distance(distance, rng, seed=f"{world.world_name}:{slot_id}")
            if role == "final_destination":
                danger = max(danger, rng.randint(WORLD_FINAL_DANGER_MIN, WORLD_FINAL_DANGER_MAX))
            if role == "starting_settlement":
                danger = 0
            location = world.ensure_location(placeholder, self._local_world_placeholder_description(category, subtype, danger))
            location.area = f"grid:{grid_x},{grid_y}"
            location.extra.update(
                {
                    "slot_id": slot_id,
                    "main_node_type": category,
                    "main_node_subtype": subtype,
                    "role": role,
                    "location_kind": kind,
                    "danger_level": danger,
                    "danger_source": "local_world_skeleton",
                    "boss_required": role == "final_destination",
                    "final_destination": role == "final_destination",
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                    "grid_distance": distance,
                    "world_generation_payload": {
                        "slot_id": slot_id,
                        "role": role,
                        "kind": kind,
                        "subtype": subtype,
                        "danger": danger,
                        "grid_x": grid_x,
                        "grid_y": grid_y,
                        "grid_distance": distance,
                        "boss_required": role == "final_destination",
                    },
                }
            )
            location.flags["discovered"] = index == 0
            if category == "settlement":
                location.flags["settlement"] = True
            if category == "dungeon":
                location.flags["dungeon"] = True
                location.flags["dangerous"] = True
                self._install_local_dungeon_subnode_graph(location, rng)
            else:
                self._ensure_location_subnode_graph(world, location.name)
            if role == "final_destination":
                location.flags["final_destination"] = True
            self._set_location_graph_node(world, location.name, kind=kind, danger=danger, location=location)
            spec = {
                "slot_id": slot_id,
                "name": location.name,
                "placeholder_name": placeholder,
                "category": category,
                "kind": kind,
                "subtype": subtype,
                "role": role,
                "danger": danger,
                "grid_x": grid_x,
                "grid_y": grid_y,
                "grid_distance": distance,
                "coord_index": index,
            }
            specs.append(spec)
            if role == "starting_settlement":
                world.starting_location = location.name

        endpoint_use: dict[str, int] = {}
        for previous, current in zip(specs, specs[1:]):
            self._connect_world_locations_by_subnodes(
                world,
                previous["name"],
                current["name"],
                self._local_external_subnode_for_spec(world, previous, endpoint_use),
                self._local_external_subnode_for_spec(world, current, endpoint_use),
                kind="main_route",
            )
        self._set_starting_settlement_gate(world)

    def _local_world_grid_coordinates(self, target_count: int, rng: random.Random) -> list[tuple[int, int]]:
        target_count = max(1, int(target_count or 1))
        coords: list[tuple[int, int]] = [(0, 0)]
        seen = {(0, 0)}
        frontier = {(1, 0), (-1, 0), (0, 1), (0, -1)}
        while len(coords) < target_count and frontier:
            candidates = list(frontier)
            candidates.sort(key=lambda item: (max(abs(item[0]), abs(item[1])), rng.random()))
            coord = candidates[0]
            frontier.remove(coord)
            if coord in seen:
                continue
            x, y = coord
            if not any((x + dx, y + dy) in seen for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                frontier.add(coord)
                continue
            coords.append(coord)
            seen.add(coord)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbor = (x + dx, y + dy)
                if neighbor not in seen:
                    frontier.add(neighbor)
        radius = 1
        while len(coords) < target_count:
            ring = [
                (x, y)
                for x in range(-radius, radius + 1)
                for y in range(-radius, radius + 1)
                if max(abs(x), abs(y)) == radius and (x, y) not in seen
            ]
            rng.shuffle(ring)
            for coord in ring:
                coords.append(coord)
                seen.add(coord)
                if len(coords) >= target_count:
                    break
            radius += 1
        return coords

    def _choose_final_destination_coord(self, coords: list[tuple[int, int]], rng: random.Random) -> tuple[int, int]:
        if not coords:
            return (0, 0)
        max_distance = max(max(abs(x), abs(y)) for x, y in coords)
        candidates = [coord for coord in coords if max(abs(coord[0]), abs(coord[1])) == max_distance and coord != (0, 0)]
        if not candidates:
            return coords[-1]
        return rng.choice(candidates)

    def _choose_settlement_coords(
        self,
        coords: list[tuple[int, int]],
        final_coord: tuple[int, int],
        target_count: int,
        rng: random.Random,
    ) -> set[tuple[int, int]]:
        desired = max(1, min(5, target_count // 18))
        candidates = [
            coord
            for coord in coords
            if coord not in {(0, 0), final_coord} and 2 <= max(abs(coord[0]), abs(coord[1])) <= 4
        ]
        rng.shuffle(candidates)
        return set(candidates[:desired])

    def _local_world_node_category(self, distance: int, rng: random.Random) -> tuple[str, str, str]:
        single_subtypes = ("road", "crossroad", "coast", "river", "plain", "landmark")
        dungeon_subtypes = ("forest", "mountain", "ruin", "cave", "mine")
        dungeon_chance = 0.18 if distance <= 1 else 0.28 if distance == 2 else 0.42
        if rng.random() < dungeon_chance:
            return "dungeon", "dungeon", rng.choice(dungeon_subtypes)
        subtype = rng.choice(single_subtypes)
        kind = subtype if subtype in {"road", "crossroad", "coast", "river", "plain"} else "landmark"
        return "single", kind, subtype

    def _local_world_placeholder_name(self, category: str, subtype: str, index: int) -> str:
        if category == "settlement":
            return f"未命名の村{index:02d}"
        if category == "dungeon":
            labels = {
                "forest": "森",
                "mountain": "山",
                "ruin": "遺跡",
                "cave": "洞窟",
                "mine": "鉱山",
                "final_destination": "最終領域",
            }
            return f"未命名の{labels.get(subtype, '迷宮')}{index:02d}"
        labels = {
            "road": "道",
            "crossroad": "分かれ道",
            "coast": "海岸",
            "river": "川辺",
            "plain": "平原",
            "landmark": "目印",
            "wilderness": "野外",
        }
        return f"未命名の{labels.get(subtype, '場所')}{index:02d}"

    def _local_world_placeholder_description(self, category: str, subtype: str, danger: int) -> str:
        if category == "settlement":
            return f"ローカル生成された拠点。危険度 {danger}。"
        if category == "dungeon":
            return f"複数のサブノードに分かれる探索地。種別: {subtype}。危険度 {danger}。"
        return f"単体サブノードのロケーション。種別: {subtype}。危険度 {danger}。"

    def _local_world_danger_for_distance(
        self,
        distance: int,
        rng: random.Random | None = None,
        *,
        seed: str = "",
    ) -> int:
        distance = max(0, int(distance or 0))
        if distance <= 0:
            return 0
        local_rng = rng if seed == "" else random.Random(f"world-grid-danger|{seed}|{distance}")
        if distance == 1:
            return 1
        if distance == 2:
            return local_rng.randint(1, 3)
        if distance == 3:
            return local_rng.randint(3, 6)
        if distance == 4:
            return local_rng.randint(6, 12)
        low = min(WORLD_DANGER_MAX, 6 * (2 ** (distance - 4)))
        high = min(WORLD_DANGER_MAX, 12 * (2 ** (distance - 4)))
        if high < low:
            high = low
        return _clamp_world_danger(local_rng.randint(low, high))

    def _local_world_node_is_final_destination(
        self,
        location: LocationData | None,
        node: dict[str, Any] | None = None,
    ) -> bool:
        extra = location.extra if location and isinstance(location.extra, dict) else {}
        payload = extra.get("world_generation_payload") if isinstance(extra.get("world_generation_payload"), dict) else {}
        node = node if isinstance(node, dict) else {}
        values = {
            str(extra.get("role") or "").strip(),
            str(extra.get("main_node_subtype") or "").strip(),
            str(payload.get("role") or "").strip(),
            str(payload.get("subtype") or "").strip(),
            str(node.get("role") or "").strip(),
            str(node.get("subtype") or "").strip(),
        }
        return (
            "final_destination" in values
            or bool(extra.get("final_destination"))
            or bool(payload.get("boss_required"))
            or bool(node.get("boss_required"))
            or bool(location and location.flags.get("final_destination"))
        )

    def _local_world_final_danger_for_node(
        self,
        world: WorldData,
        name: str,
        grid_x: Any = "",
        grid_y: Any = "",
    ) -> int:
        rng = random.Random(f"world-final-danger|{world.world_name}|{name}|{grid_x}|{grid_y}")
        return rng.randint(WORLD_FINAL_DANGER_MIN, WORLD_FINAL_DANGER_MAX)

    def _install_local_dungeon_subnode_graph(self, location: LocationData, rng: random.Random) -> None:
        if install_template_dungeon_subnode_graph(self, location, rng):
            return
        target_count = _dungeon_subnode_target_count(location)
        layout = _fallback_dungeon_subnode_layout(location, target_count)
        graph: dict[str, Any] = {
            "version": 1,
            "nodes": {},
            "edges": [],
            "movement": "adjacent",
            "dungeon_layout_version": DUNGEON_SUBNODE_LAYOUT_VERSION,
            "dungeon_target_count": target_count,
            "generated_by": "local_world_skeleton",
        }
        self._replace_dungeon_subnode_layout(graph, layout, {})
        nodes = graph.setdefault("nodes", {})
        self._upsert_subnode_node(
            graph,
            "entrance_b",
            "別入口",
            "別のエリアへ抜けることができるもう一つの入口。",
            "entrance",
            90,
            420,
            world_map_exit=True,
        )
        anchor = "main_02" if "main_02" in nodes else "main_01" if "main_01" in nodes else DUNGEON_ENTRY_SUBNODE_ID
        self._connect_subnodes(graph, "entrance_b", anchor, "side_entrance")
        middle_exit = "main_02" if "main_02" in nodes else "side_01" if "side_01" in nodes else ""
        if middle_exit and isinstance(nodes.get(middle_exit), dict):
            nodes[middle_exit]["world_map_exit"] = True
            nodes[middle_exit]["external_exit_hint"] = "この中腹から別エリアへ出られる。"
        if DUNGEON_ENTRY_SUBNODE_ID in nodes:
            nodes[DUNGEON_ENTRY_SUBNODE_ID]["world_map_exit"] = True
        if DUNGEON_DEEPEST_SUBNODE_ID in nodes:
            nodes[DUNGEON_DEEPEST_SUBNODE_ID]["world_map_exit"] = False
        graph["external_subnode_candidates"] = [
            node_id
            for node_id in (DUNGEON_ENTRY_SUBNODE_ID, "entrance_b", middle_exit, "side_01")
            if node_id and node_id in nodes
        ]
        graph["current"] = DUNGEON_ENTRY_SUBNODE_ID
        _ensure_dungeon_graph_connected(graph)
        location.extra[SUBNODE_GRAPH_KEY] = graph
        self._seed_dungeon_deepest_loot(location, graph, source="local_dungeon_generation")

    def _seed_dungeon_deepest_loot(
        self,
        location: LocationData,
        graph: dict[str, Any],
        *,
        source: str = "dungeon_generation",
    ) -> dict[str, Any]:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if DUNGEON_DEEPEST_SUBNODE_ID not in nodes:
            return {"seeded": False, "reason": "missing_deepest"}
        loot_store = location.extra.setdefault("subnode_loot", {})
        if not isinstance(loot_store, dict):
            loot_store = {}
            location.extra["subnode_loot"] = loot_store
        slot = loot_store.setdefault(DUNGEON_DEEPEST_SUBNODE_ID, {})
        if not isinstance(slot, dict):
            slot = {}
            loot_store[DUNGEON_DEEPEST_SUBNODE_ID] = slot
        if slot.get("guaranteed_deepest_reward_seeded"):
            return {
                "seeded": False,
                "reason": "already_seeded",
                "reward_kind": str(slot.get("guaranteed_reward_kind") or ""),
            }
        inventory = slot.setdefault("inventory", [])
        if not isinstance(inventory, list):
            inventory = []
            slot["inventory"] = inventory
        rng = random.Random(
            "|".join(
                (
                    "dungeon-deepest-loot",
                    self.state.world_name or self.state.world_data.world_name or "world",
                    location.name,
                    str(location.extra.get("danger_level") or ""),
                )
            )
        )
        reward_kind, items = self._dungeon_deepest_reward_items(location, rng, source=source)
        inventory.extend(items)
        slot["seeded"] = True
        slot["guaranteed_deepest_reward_seeded"] = True
        slot["guaranteed_reward_kind"] = reward_kind
        slot["source"] = source
        return {
            "seeded": True,
            "reward_kind": reward_kind,
            "items": items,
        }

    def _dungeon_deepest_reward_items(
        self,
        location: LocationData,
        rng: random.Random,
        *,
        source: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        table = choose_loot_table_by_tag(
            "dungeon_innermost",
            seed=f"{source}|{location.name}|deepest|{rng.random()}",
            context=location.name,
            danger_level=_clamp_world_danger(location.extra.get("danger_level", location.extra.get("danger", 0))),
        )
        loot_table_id = str((table or {}).get("id") or "dungeon_innermost_treasure")
        return loot_table_id, generate_loot_table_items(
            loot_table_id,
            context=location.name,
            danger_level=_clamp_world_danger(location.extra.get("danger_level", location.extra.get("danger", 0))),
            seed=f"{source}|{location.name}|deepest",
            source=source,
        )

    def _connect_local_world_skeleton_edges(
        self,
        world: WorldData,
        specs: list[dict[str, Any]],
        coords: list[tuple[int, int]],
        rng: random.Random,
    ) -> None:
        by_coord = {(spec["grid_x"], spec["grid_y"]): spec for spec in specs}
        connected = {(0, 0)}
        endpoint_use: dict[str, int] = {}
        for spec in specs[1:]:
            coord = (spec["grid_x"], spec["grid_y"])
            neighbors = [
                (coord[0] + dx, coord[1] + dy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (coord[0] + dx, coord[1] + dy) in connected
            ]
            if not neighbors:
                neighbors = [(0, 0)]
            parent_coord = min(neighbors, key=lambda item: (max(abs(item[0]), abs(item[1])), rng.random()))
            parent = by_coord[parent_coord]
            self._connect_world_locations_by_subnodes(
                world,
                parent["name"],
                spec["name"],
                self._local_external_subnode_for_spec(world, parent, endpoint_use),
                self._local_external_subnode_for_spec(world, spec, endpoint_use),
                kind="map_route",
            )
            connected.add(coord)

        coords_set = set(coords)
        for coord in coords:
            spec = by_coord.get(coord)
            if not spec:
                continue
            for dx, dy in ((1, 0), (0, 1)):
                other_coord = (coord[0] + dx, coord[1] + dy)
                if other_coord not in coords_set or other_coord not in by_coord:
                    continue
                if rng.random() > 0.23:
                    continue
                other = by_coord[other_coord]
                if self._world_edge_between(world, spec["name"], other["name"]):
                    continue
                self._connect_world_locations_by_subnodes(
                    world,
                    spec["name"],
                    other["name"],
                    self._local_external_subnode_for_spec(world, spec, endpoint_use),
                    self._local_external_subnode_for_spec(world, other, endpoint_use),
                    kind="map_route",
                )

    def _local_external_subnode_for_spec(
        self,
        world: WorldData,
        spec: dict[str, Any],
        endpoint_use: dict[str, int],
    ) -> str:
        name = str(spec.get("name") or "")
        location = world.locations.get(name)
        category = str(spec.get("category") or "")
        if category == "settlement":
            return "gate"
        if category != "dungeon" or not location:
            return DEFAULT_SUBNODE_ID
        graph = location.extra.get(SUBNODE_GRAPH_KEY)
        candidates = []
        if isinstance(graph, dict):
            candidates = [str(item) for item in _as_list(graph.get("external_subnode_candidates")) if str(item)]
        if not candidates:
            candidates = [DUNGEON_ENTRY_SUBNODE_ID]
        index = endpoint_use.get(name, 0)
        endpoint_use[name] = index + 1
        return candidates[index % len(candidates)]

    def _connect_world_locations_by_subnodes(
        self,
        world: WorldData,
        a: str,
        b: str,
        from_subnode: str,
        to_subnode: str,
        *,
        hours: int = WORLD_MAP_EDGE_HOURS,
        kind: str = "road",
    ) -> None:
        a = str(a or "").strip()
        b = str(b or "").strip()
        if not a or not b or a == b:
            return
        graph = self._location_graph_for_update(world)
        self._set_location_graph_node(world, a)
        self._set_location_graph_node(world, b)
        edge_key = {a, b}
        for edge in graph.setdefault("edges", []):
            if not isinstance(edge, dict):
                continue
            if {str(edge.get("from") or ""), str(edge.get("to") or "")} != edge_key:
                continue
            edge["hours"] = int(hours or WORLD_MAP_EDGE_HOURS)
            edge["kind"] = str(edge.get("kind") or kind)
            if str(edge.get("from") or "") == a:
                edge["from_subnode"] = from_subnode
                edge["to_subnode"] = to_subnode
                edge.setdefault("subnodes", {})[a] = from_subnode
                edge.setdefault("subnodes", {})[b] = to_subnode
            else:
                edge["from_subnode"] = to_subnode
                edge["to_subnode"] = from_subnode
                edge.setdefault("subnodes", {})[a] = from_subnode
                edge.setdefault("subnodes", {})[b] = to_subnode
            self._ensure_world_edge_subnodes(world, edge)
            return
        edge = {
            "from": a,
            "to": b,
            "hours": int(hours or WORLD_MAP_EDGE_HOURS),
            "kind": kind,
            "from_subnode": from_subnode,
            "to_subnode": to_subnode,
            "subnodes": {a: from_subnode, b: to_subnode},
        }
        self._ensure_world_edge_subnodes(world, edge)
        graph.setdefault("edges", []).append(edge)

    def _describe_local_world_skeleton(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        theme: dict[str, Any],
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_start: int = 0,
        progress_end: int = 100,
    ) -> None:
        skeleton = world.extra.get("local_world_skeleton") if isinstance(world.extra, dict) else {}
        specs = skeleton.get("locations") if isinstance(skeleton, dict) else []
        if not isinstance(specs, list):
            return
        settlement_specs = [spec for spec in specs if isinstance(spec, dict) and spec.get("category") == "settlement"]
        single_specs = [spec for spec in specs if isinstance(spec, dict) and spec.get("category") == "single"]
        dungeon_specs = [spec for spec in specs if isinstance(spec, dict) and spec.get("category") == "dungeon"]
        total_steps = (1 if settlement_specs else 0) + ((len(single_specs) + 2) // 3 if single_specs else 0) + len(dungeon_specs)
        total_steps = max(1, total_steps)
        step = 0

        self._describe_local_world_settlements(player_name, premise, world, theme, settlement_specs)
        step += 1
        self._emit_world_generation_progress(
            progress_callback,
            "location_descriptions",
            f"街/村の名称生成 {len(settlement_specs)}件",
            progress_start + int((progress_end - progress_start) * step / max(1, total_steps)),
            100,
            item_current=step,
            item_total=total_steps,
        )

        for batch in self._chunks(single_specs, 3):
            self._describe_local_world_single_batch(player_name, premise, world, theme, batch)
            step += 1
            self._emit_world_generation_progress(
                progress_callback,
                "location_descriptions",
                f"単体ロケーション名称生成 {min(step, total_steps)}/{total_steps}",
                progress_start + int((progress_end - progress_start) * step / max(1, total_steps)),
                100,
                item_current=step,
                item_total=total_steps,
            )

        for spec in dungeon_specs:
            self._describe_local_world_dungeon(player_name, premise, world, theme, spec)
            step += 1
            self._emit_world_generation_progress(
                progress_callback,
                "location_descriptions",
                f"複数ノードロケーション名称生成 {min(step, total_steps)}/{total_steps}",
                progress_start + int((progress_end - progress_start) * step / max(1, total_steps)),
                100,
                item_current=step,
                item_total=total_steps,
            )

        self._repair_local_world_placeholder_descriptions(
            player_name,
            premise,
            world,
            theme,
            specs,
            progress_callback=progress_callback,
            progress_value=progress_end,
        )

    def _describe_local_world_settlements(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        theme: dict[str, Any],
        specs: list[dict[str, Any]],
    ) -> None:
        if not specs:
            return
        prompt = self._local_world_description_prompt(world, premise, theme, specs, "settlement")
        messages = [
            {
                "role": "system",
                "content": (
                    "Name and describe only the supplied settlement slots. "
                    "Do not change map structure, danger, coordinates, or connections. Return Japanese names and summaries."
                ),
            },
            {"role": "user", "content": _ai_json(prompt)},
        ]
        response = self._chat_json(
            "local_world_settlement_describer",
            messages,
            max_tokens=max(
                900,
                min(
                    2400,
                    360
                    + len(specs) * 230
                    + sum(len(_as_list(slot.get("required_shop_facilities"))) for slot in prompt.get("slots", [])) * 120,
                ),
            ),
            world_name=world.world_name,
            player_name=player_name,
        )
        for index, item in enumerate(self._local_world_description_items(response, "settlement")):
            if isinstance(item, dict):
                item = self._local_world_item_with_slot_fallback(item, specs, index)
                self._apply_local_world_location_description(world, specs, item)
        world.history.append({"manager": "local_world_settlement_describer", "response": _strip_response_metadata(response)})

    def _describe_local_world_single_batch(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        theme: dict[str, Any],
        specs: list[dict[str, Any]],
    ) -> None:
        if not specs:
            return
        prompt = self._local_world_description_prompt(world, premise, theme, specs, "single")
        messages = [
            {
                "role": "system",
                "content": (
                    "Name and describe exactly the supplied single-subnode location slots. "
                    "Do not add connections or subnodes. Return Japanese names and summaries."
                ),
            },
            {"role": "user", "content": _ai_json(prompt)},
        ]
        response = self._chat_json(
            "local_world_single_location_describer",
            messages,
            max_tokens=max(650, min(1100, 280 + len(specs) * 220)),
            world_name=world.world_name,
            player_name=player_name,
        )
        for index, item in enumerate(self._local_world_description_items(response, "single")):
            if isinstance(item, dict):
                item = self._local_world_item_with_slot_fallback(item, specs, index)
                self._apply_local_world_location_description(world, specs, item)
        world.history.append({"manager": "local_world_single_location_describer", "response": _strip_response_metadata(response)})

    def _describe_local_world_dungeon(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        theme: dict[str, Any],
        spec: dict[str, Any],
    ) -> None:
        prompt = self._local_world_description_prompt(world, premise, theme, [spec], "dungeon")
        prompt["subnodes_to_name"] = self._dungeon_subnodes_for_llm_description(world, spec)
        messages = [
            {
                "role": "system",
                "content": (
                    "Name and describe one multi-node location and its listed internal subnodes. "
                    "The game already fixed entrance/deepest nodes, graph shape, danger, and external links. "
                    "Do not change structure. Return Japanese names and summaries."
                ),
            },
            {"role": "user", "content": _ai_json(prompt)},
        ]
        response = self._chat_json(
            "local_world_dungeon_location_describer",
            messages,
            max_tokens=max(900, min(1800, 520 + len(prompt.get("subnodes_to_name") or []) * 95)),
            world_name=world.world_name,
            player_name=player_name,
        )
        response_items = self._local_world_description_items(response, "dungeon")
        location_item = response_items[0] if response_items else (response.get("location") if isinstance(response.get("location"), dict) else response)
        if isinstance(location_item, dict):
            location_item = self._local_world_item_with_slot_fallback(location_item, [spec], 0)
            if isinstance(response.get("subnodes"), list) and "subnodes" not in location_item:
                location_item = {**location_item, "subnodes": response.get("subnodes")}
            self._apply_local_world_location_description(world, [spec], location_item)
            self._apply_local_world_subnode_descriptions(world, spec, location_item)
        world.history.append({"manager": "local_world_dungeon_location_describer", "slot_id": spec.get("slot_id"), "response": _strip_response_metadata(response)})

    def _local_world_description_items(self, response: dict[str, Any], mode: str) -> list[dict[str, Any]]:
        if not isinstance(response, dict):
            return []
        keys_by_mode = {
            "settlement": ("settlements", "locations", "items", "results", "slots"),
            "single": ("locations", "single_locations", "single_subnode_locations", "items", "results", "slots"),
            "dungeon": ("location", "dungeon", "dungeon_location", "locations", "items", "results", "slots"),
        }
        items: list[dict[str, Any]] = []
        for key in keys_by_mode.get(mode, ("locations", "items", "results")):
            value = response.get(key)
            if isinstance(value, dict):
                items.append(dict(value))
            elif isinstance(value, list):
                items.extend(dict(item) for item in value if isinstance(item, dict))
        if not items and any(key in response for key in ("slot_id", "id", "name", "title", "description", "summary")):
            items.append(dict(response))
        return items

    def _local_world_item_with_slot_fallback(
        self,
        item: dict[str, Any],
        specs: list[dict[str, Any]],
        index: int,
    ) -> dict[str, Any]:
        if str(item.get("slot_id") or item.get("id") or "").strip():
            return item
        if index < len(specs):
            return {**item, "slot_id": specs[index].get("slot_id")}
        return item

    def _repair_local_world_placeholder_descriptions(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        theme: dict[str, Any],
        specs: list[dict[str, Any]],
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_value: int = 48,
    ) -> None:
        unresolved = self._local_world_specs_needing_description(world, specs)
        if not unresolved:
            return
        self._emit_world_generation_progress(
            progress_callback,
            "location_descriptions",
            f"未補完ロケーションを再生成中 {len(unresolved)}件",
            progress_value,
            100,
            item_current=0,
            item_total=len(unresolved),
        )
        settlement_specs = [spec for spec in unresolved if str(spec.get("category") or "") == "settlement"]
        single_specs = [spec for spec in unresolved if str(spec.get("category") or "") == "single"]
        dungeon_specs = [spec for spec in unresolved if str(spec.get("category") or "") == "dungeon"]
        if settlement_specs:
            self._describe_local_world_settlements(player_name, premise, world, theme, settlement_specs)
        for batch in self._chunks(single_specs, 3):
            self._describe_local_world_single_batch(player_name, premise, world, theme, batch)
        for spec in dungeon_specs:
            self._describe_local_world_dungeon(player_name, premise, world, theme, spec)
        remaining = self._local_world_specs_needing_description(world, specs)
        if remaining:
            applied = self._apply_local_world_placeholder_fallbacks(world, theme, remaining)
            if applied:
                world.history.append(
                    {
                        "manager": "local_world_description_fallback",
                        "slot_ids": applied,
                    }
                )
            remaining = self._local_world_specs_needing_description(world, specs)
        if remaining:
            errors = world.extra.setdefault("location_generation_errors", [])
            if isinstance(errors, list):
                errors.append(
                    {
                        "stage": "local_world_description_repair",
                        "remaining_slot_ids": [str(spec.get("slot_id") or "") for spec in remaining],
                    }
                )

    def _local_world_specs_needing_description(
        self,
        world: WorldData,
        specs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            location = world.locations.get(str(spec.get("name") or "").strip())
            if location and _local_world_location_needs_llm_description(location, spec):
                result.append(spec)
        return result

    def _apply_local_world_placeholder_fallbacks(
        self,
        world: WorldData,
        theme: dict[str, Any],
        specs: list[dict[str, Any]],
    ) -> list[str]:
        applied: list[str] = []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            old_name = str(spec.get("name") or "").strip()
            location = world.locations.get(old_name)
            if not location:
                continue
            fallback_name = self._local_world_fallback_location_name(world, theme, spec)
            if _local_world_placeholder_location_name(fallback_name):
                continue
            if fallback_name != old_name:
                new_name = self._rename_world_location(world, old_name, fallback_name)
                spec["name"] = new_name
                location = world.locations.get(new_name)
                if not location:
                    continue
            description = self._local_world_fallback_location_description(world, theme, spec, location.name)
            if not _local_world_placeholder_location_description(description):
                location.description = description
            danger = _safe_int(spec.get("danger"), _safe_int(location.extra.get("danger_level"), 0))
            if str(spec.get("role") or "") == "final_destination":
                danger = max(danger, self._local_world_final_danger_for_node(world, location.name, spec.get("grid_x"), spec.get("grid_y")))
                location.flags["final_destination"] = True
                location.extra["role"] = "final_destination"
                location.extra["final_destination"] = True
                location.extra["boss_required"] = True
            location.extra["danger_level"] = _clamp_world_danger(danger)
            location.extra["llm_location_description"] = {
                "slot_id": spec.get("slot_id"),
                "name": location.name,
                "description": location.description,
                "source": "local_world_placeholder_fallback",
            }
            self._set_location_graph_node(
                world,
                location.name,
                kind=str(spec.get("kind") or ""),
                danger=location.extra["danger_level"],
                location=location,
            )
            applied.append(str(spec.get("slot_id") or ""))
        return applied

    def _local_world_fallback_location_name(
        self,
        world: WorldData,
        theme: dict[str, Any],
        spec: dict[str, Any],
    ) -> str:
        role = str(spec.get("role") or "").strip()
        subtype = str(spec.get("subtype") or "").strip()
        if role == "final_destination":
            extracted = self._local_world_final_destination_name_from_theme(world, theme)
            if extracted:
                return extracted
        labels = {
            "forest": "\u68ee",
            "mountain": "\u5c71",
            "ruin": "\u907a\u8de1",
            "cave": "\u6d1e\u7a9f",
            "mine": "\u9271\u5c71",
            "road": "\u8857\u9053",
            "crossroad": "\u8fbb",
            "coast": "\u6d77\u5cb8",
            "river": "\u5ddd\u8fba",
            "plain": "\u5e73\u539f",
            "landmark": "\u77f3\u7891",
            "wilderness": "\u91ce",
            "final_destination": "\u795e\u6bbf",
        }
        prefixes = (
            "\u9727\u6df1\u304d",
            "\u6708\u5f71\u306e",
            "\u661f\u7720\u308b",
            "\u9280\u706f\u306e",
            "\u8d64\u9306\u306e",
            "\u767d\u9418\u306e",
            "\u98a8\u54ed\u304d\u306e",
            "\u96e8\u5f85\u3061\u306e",
            "\u7070\u51a0\u306e",
            "\u9752\u785d\u5b50\u306e",
        )
        label = labels.get(subtype) or labels.get(str(spec.get("category") or "")) or "\u5730"
        rng = random.Random(f"local-world-fallback-name|{world.world_name}|{spec.get('slot_id')}|{subtype}|{world.overview}")
        return f"{rng.choice(prefixes)}{label}"

    def _local_world_final_destination_name_from_theme(
        self,
        world: WorldData,
        theme: dict[str, Any],
    ) -> str:
        raw_theme = world.extra.get("raw_create_world_theme") if isinstance(world.extra, dict) else {}
        concept = str(theme.get("final_destination_concept") or (raw_theme or {}).get("final_destination_concept") or "").strip()
        if not concept:
            return ""
        for opener, closer in (("\u300c", "\u300d"), ("\u300e", "\u300f"), ("\"", "\""), ("'", "'")):
            start = concept.find(opener)
            end = concept.find(closer, start + 1) if start >= 0 else -1
            if start >= 0 and end > start:
                candidate = concept[start + len(opener) : end].strip()
                if 2 <= len(candidate) <= 28 and not _local_world_placeholder_location_name(candidate):
                    return candidate
        keywords = (
            "\u795e\u6bbf",
            "\u5bfa\u9662",
            "\u8056\u5802",
            "\u907a\u8de1",
            "\u8ff7\u5bae",
            "\u5bae\u6bbf",
            "\u57ce",
            "\u5854",
            "\u8981\u585e",
            "\u6d1e\u7a9f",
            "\u9271\u5c71",
            "\u68ee",
            "\u5c71",
        )
        for keyword in keywords:
            match = re.search(r"([\u3041-\u309f\u30a1-\u30ff\u3400-\u9fff\u3005\u30fcA-Za-z0-9]{2,28}" + re.escape(keyword) + r")", concept)
            if match:
                candidate = match.group(1).strip()
                if not _local_world_placeholder_location_name(candidate):
                    return candidate
        return "\u6700\u679c\u3066\u306e\u795e\u6bbf"

    def _local_world_fallback_location_description(
        self,
        world: WorldData,
        theme: dict[str, Any],
        spec: dict[str, Any],
        name: str,
    ) -> str:
        role = str(spec.get("role") or "").strip()
        subtype = str(spec.get("subtype") or "").strip()
        raw_theme = world.extra.get("raw_create_world_theme") if isinstance(world.extra, dict) else {}
        concept = str(theme.get("final_destination_concept") or (raw_theme or {}).get("final_destination_concept") or "").strip()
        if role == "final_destination":
            base = concept or f"{world.overview}\u306e\u7d50\u672b\u306b\u7acb\u3061\u306f\u3060\u304b\u308b\u7981\u57df"
            return f"{base}\u3002\u4e16\u754c\u306e\u5916\u7e01\u306b\u5c01\u3058\u3089\u308c\u305f\u7981\u57df\u3067\u3001\u6700\u5965\u3067\u306f\u65c5\u306e\u7d50\u672b\u3092\u5de6\u53f3\u3059\u308b\u5f37\u5927\u306a\u5b58\u5728\u304c\u5f85\u3061\u53d7\u3051\u308b\u3002"
        descriptions = {
            "forest": f"{name}\u306f\u3001\u53e4\u3044\u6728\u3005\u3068\u6e7f\u3063\u305f\u571f\u306e\u9999\u308a\u304c\u6e80\u3061\u308b\u68ee\u3002\u6728\u3005\u306e\u5965\u3078\u9032\u3080\u307b\u3069\u3001\u7570\u5e38\u306a\u6c17\u914d\u304c\u6fc3\u304f\u306a\u308b\u3002",
            "mountain": f"{name}\u306f\u3001\u9669\u3057\u3044\u5c3e\u6839\u3068\u5ca9\u9670\u306e\u5165\u53e3\u304c\u7d9a\u304f\u5c71\u3002\u98a8\u306e\u97f3\u306b\u307e\u3058\u3063\u3066\u3001\u5965\u5730\u304b\u3089\u91d1\u5c5e\u306e\u8ef8\u3080\u97f3\u304c\u97ff\u304f\u3002",
            "ruin": f"{name}\u306f\u3001\u5d29\u308c\u305f\u77f3\u58c1\u3068\u53e4\u3044\u796d\u58c7\u304c\u6b8b\u308b\u907a\u8de1\u3002\u3044\u304f\u3064\u3082\u306e\u901a\u8def\u304c\u5730\u4e0b\u3078\u6298\u308c\u3001\u5fd8\u308c\u3089\u308c\u305f\u6c17\u914d\u3092\u6f02\u308f\u305b\u3066\u3044\u308b\u3002",
            "cave": f"{name}\u306f\u3001\u51b7\u305f\u3044\u98a8\u304c\u5439\u304d\u51fa\u3059\u6d1e\u7a9f\u3002\u6fe1\u308c\u305f\u5ca9\u808c\u3068\u5206\u5c90\u3059\u308b\u5965\u9053\u304c\u3001\u8db3\u97f3\u3092\u9060\u304f\u307e\u3067\u53cd\u97ff\u3055\u305b\u308b\u3002",
            "mine": f"{name}\u306f\u3001\u9306\u3073\u305f\u652f\u67f1\u3068\u53e4\u3044\u8ecc\u9053\u304c\u6b8b\u308b\u9271\u5c71\u3002\u6398\u308a\u629c\u304b\u308c\u305f\u5751\u9053\u306e\u5965\u306b\u3001\u307e\u3060\u8ab0\u304b\u306e\u6c17\u914d\u304c\u6f5c\u3093\u3067\u3044\u308b\u3002",
        }
        return descriptions.get(
            subtype,
            f"{name}\u306f\u3001{world.overview}\u306e\u8fba\u5883\u306b\u5e83\u304c\u308b\u63a2\u7d22\u5730\u3002\u9053\u306f\u66f2\u304c\u308a\u304f\u306d\u308a\u3001\u5965\u3078\u5411\u304b\u3046\u307b\u3069\u9759\u3051\u3055\u3068\u7dca\u5f35\u304c\u5897\u3057\u3066\u3044\u304f\u3002",
        )

    def _local_world_description_prompt(
        self,
        world: WorldData,
        premise: str,
        theme: dict[str, Any],
        specs: list[dict[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        existing_names = [name for name in world.locations if not str(name).startswith("未命名")]
        existing_names = [name for name in existing_names if not _local_world_placeholder_location_name(name)]
        slots = []
        graph = world.extra.get("location_graph") if isinstance(world.extra, dict) else {}
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        for spec in specs:
            name = str(spec.get("name") or "")
            node = nodes.get(name, {}) if isinstance(nodes, dict) else {}
            neighbors = self._world_neighbors_no_ensure(world, name)
            slot = {
                "slot_id": spec.get("slot_id"),
                "placeholder_name": name,
                "category": spec.get("category"),
                "kind": spec.get("kind"),
                "subtype": spec.get("subtype"),
                "role": spec.get("role"),
                "danger": spec.get("danger"),
                "grid": [spec.get("grid_x"), spec.get("grid_y")],
                "grid_distance": spec.get("grid_distance"),
                "neighbor_placeholders": neighbors,
                "node": {key: node.get(key) for key in ("kind", "danger", "grid_x", "grid_y", "grid_distance") if isinstance(node, dict)},
                "final_destination_concept": str(theme.get("final_destination_concept") or "") if str(spec.get("role") or "") == "final_destination" else "",
            }
            if mode == "settlement" and str(spec.get("role") or "") != "starting_settlement":
                required_shop_facilities = self._settlement_required_shop_slots(world, name)
                spec["required_shop_facilities"] = required_shop_facilities
                slot["required_shop_facilities"] = required_shop_facilities
            slots.append(slot)
        rules = [
            "Return one item per supplied slot_id.",
            "Do not change category, danger, coordinates, or connections.",
            "Names must fit the world and avoid duplicate existing names.",
            "Never return placeholder names such as 未命名, unnamed, final destination, or generic location labels.",
            "Descriptions must be in-world prose. Never mention internal labels such as 単体サブノード, 複数ノード, slot_id, category, subtype, grid, or danger rule.",
            "Use danger and grid distance to make farther locations feel more threatening.",
        ]
        if mode == "single":
            rules.append("For single-subnode locations, invent a concrete road, coast, riverbank, landmark, or plain identity and a real setting description.")
        if mode == "settlement":
            rules.append("For non-starting settlement slots with required_shop_facilities, include facilities matching every listed type.")
            rules.append("Each facility must have name, type, description, npc_name, npc_role, npc_gender, npc_age, npc_look, and npc_personality.")
            rules.append("npc_look and npc_personality describe the facility keeper, not the facility. Never copy the facility description into those fields.")
            rules.append("Do not include gates, entrances, central plazas, or plazas as facilities.")
        if mode == "dungeon":
            rules.append("For final_destination slots, use final_destination_concept and the world premise to create a proper named endgame location.")
        return {
            "mode": mode,
            "world": {
                "world_name": world.world_name,
                "overview": _short_text(world.overview, 1200),
                "structure_description": _short_text(world.structure_description, 900),
                "structure": _compact_value(world.structure, max_chars=1600),
                "final_destination_concept": str(theme.get("final_destination_concept") or ""),
            },
            "premise": _short_text(premise, 2000),
            "existing_location_names": existing_names,
            "slots": slots,
            "rules": rules,
        }

    def _dungeon_subnodes_for_llm_description(self, world: WorldData, spec: dict[str, Any]) -> list[dict[str, Any]]:
        location = world.locations.get(str(spec.get("name") or ""))
        if not location:
            return []
        graph = location.extra.get(SUBNODE_GRAPH_KEY)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict) else {}
        result: list[dict[str, Any]] = []
        excluded = {DUNGEON_ENTRY_SUBNODE_ID, DUNGEON_DEEPEST_SUBNODE_ID, "entrance_b"}
        for node_id, node in nodes.items():
            node_id = str(node_id)
            if node_id in excluded or not isinstance(node, dict):
                continue
            result.append(
                {
                    "id": node_id,
                    "kind": node.get("kind"),
                    "current_name": node.get("name"),
                    "danger": spec.get("danger"),
                }
            )
        return result

    def _apply_local_world_location_description(
        self,
        world: WorldData,
        specs: list[dict[str, Any]],
        item: dict[str, Any],
    ) -> None:
        slot_id = str(item.get("slot_id") or item.get("id") or "").strip()
        spec = next((candidate for candidate in specs if str(candidate.get("slot_id") or "") == slot_id), None)
        if spec is None and len(specs) == 1:
            spec = specs[0]
        if spec is None:
            return
        old_name = str(spec.get("name") or "")
        new_name = str(item.get("name") or item.get("title") or old_name).strip() or old_name
        if not old_name:
            return
        if _local_world_placeholder_location_name(new_name):
            new_name = old_name
        if new_name != old_name:
            new_name = self._rename_world_location(world, old_name, new_name)
            spec["name"] = new_name
        location = world.locations.get(str(spec.get("name") or old_name))
        if not location:
            return
        description = str(item.get("description") or item.get("overview") or item.get("summary") or "").strip()
        if _local_world_placeholder_location_description(description):
            description = ""
        if description:
            if _is_settlement_location(location):
                description = _clean_settlement_generated_text(description, location.name)
            location.description = description
        area = str(item.get("area") or item.get("region") or "").strip()
        if area:
            location.area = area
        if str(spec.get("category") or "") == "settlement":
            self._apply_local_world_settlement_facilities(world, location.name, spec, item)
        location.extra["llm_location_description"] = _strip_response_metadata(item)
        self._set_location_graph_node(world, location.name, kind=str(spec.get("kind") or ""), danger=_safe_int(spec.get("danger"), 0), location=location)

    def _apply_local_world_settlement_facilities(
        self,
        world: WorldData,
        settlement_name: str,
        spec: dict[str, Any],
        item: dict[str, Any],
    ) -> None:
        if str(spec.get("role") or "") == "starting_settlement":
            return
        location = world.locations.get(settlement_name)
        if not location:
            return
        required_shop_slots = [
            dict(slot)
            for slot in _as_list(item.get("required_shop_facilities") or spec.get("required_shop_facilities"))
            if isinstance(slot, dict)
        ]
        if not required_shop_slots:
            required_shop_slots = self._settlement_required_shop_slots(world, settlement_name)
        facilities: list[dict[str, Any]] = []
        for raw in _as_list(item.get("facilities") or item.get("shops")):
            if isinstance(raw, dict):
                name = _clean_settlement_generated_text(raw.get("name") or raw.get("facility_name") or raw.get("title") or "", settlement_name)
                if not name or _is_reserved_settlement_facility_name(name):
                    continue
                description = _facility_description_from_payload(
                    raw.get("description") or raw.get("overview") or raw.get("summary") or "",
                    settlement_name,
                    name,
                )
                facilities.append(
                    {
                        "name": name,
                        "type": str(raw.get("type") or raw.get("facility_type") or _facility_type_from_name(name)).strip(),
                        "description": description,
                        "npc_name": _clean_settlement_generated_text(raw.get("npc_name") or raw.get("keeper") or raw.get("owner") or "", settlement_name),
                        "npc_role": _clean_settlement_generated_text(raw.get("npc_role") or raw.get("role") or "", settlement_name),
                        **_facility_keeper_fields(raw, settlement_name, name, description),
                        "location_name": settlement_name,
                        "sub_location": name,
                        "source": str(raw.get("source") or "local_world_settlement_describer"),
                    }
                )
            else:
                name = _clean_settlement_generated_text(raw or "", settlement_name)
                if name and not _is_reserved_settlement_facility_name(name):
                    facilities.append(_facility_record(name, settlement_name))
        self._append_missing_required_shop_facilities(settlement_name, facilities, required_shop_slots)
        location.extra["required_shop_facilities"] = required_shop_slots
        location.extra["facilities"] = facilities
        location.extra["raw_local_world_settlement_facilities"] = _strip_response_metadata(item)
        location.flags["settlement"] = True
        location.extra["location_kind"] = "settlement"
        self._ensure_settlement_facilities(location)

    def _apply_local_world_subnode_descriptions(
        self,
        world: WorldData,
        spec: dict[str, Any],
        item: dict[str, Any],
    ) -> None:
        location = world.locations.get(str(spec.get("name") or ""))
        if not location:
            return
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        excluded = {DUNGEON_ENTRY_SUBNODE_ID, DUNGEON_DEEPEST_SUBNODE_ID, "entrance_b"}
        for raw in _as_list(item.get("subnodes") or item.get("rooms") or item.get("internal_subnodes")):
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or raw.get("node_id") or "").strip()
            if not node_id or node_id in excluded or node_id not in nodes:
                continue
            node = nodes.get(node_id)
            if not isinstance(node, dict):
                continue
            name = str(raw.get("name") or raw.get("title") or "").strip()
            description = str(raw.get("description") or raw.get("overview") or raw.get("summary") or "").strip()
            kind = str(raw.get("kind") or raw.get("type") or "").strip()
            if name:
                node["name"] = _short_text(name, 64)
            if description:
                node["description"] = _short_text(description, 220)
            if kind:
                node["kind"] = _safe_subnode_kind(kind)

    def _rename_world_location(self, world: WorldData, old_name: str, new_name: str) -> str:
        old_name = str(old_name or "").strip()
        new_name = str(new_name or "").strip()
        if not old_name or not new_name or old_name == new_name:
            return old_name
        if new_name in world.locations and new_name != old_name:
            new_name = _unique_world_location_name(world, new_name)
        location = world.locations.pop(old_name, None)
        if location is None:
            return new_name
        location.name = new_name
        world.locations[new_name] = location
        if world.starting_location == old_name:
            world.starting_location = new_name
        graph = world.extra.get("location_graph") if isinstance(world.extra, dict) else None
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            if isinstance(nodes, dict) and old_name in nodes:
                node = nodes.pop(old_name)
                if isinstance(node, dict):
                    node["name"] = new_name
                nodes[new_name] = node
            for edge in graph.get("edges", []):
                if not isinstance(edge, dict):
                    continue
                if str(edge.get("from") or "") == old_name:
                    edge["from"] = new_name
                if str(edge.get("to") or "") == old_name:
                    edge["to"] = new_name
                subnodes = edge.get("subnodes")
                if isinstance(subnodes, dict) and old_name in subnodes:
                    subnodes[new_name] = subnodes.pop(old_name)
        visited = world.extra.get("visited_locations") if isinstance(world.extra, dict) else None
        if isinstance(visited, list):
            for index, value in enumerate(list(visited)):
                if value == old_name:
                    visited[index] = new_name
        skeleton = world.extra.get("local_world_skeleton") if isinstance(world.extra, dict) else None
        specs = skeleton.get("locations") if isinstance(skeleton, dict) else None
        if isinstance(specs, list):
            for spec in specs:
                if isinstance(spec, dict) and spec.get("name") == old_name:
                    spec["name"] = new_name
        return new_name

    def _set_starting_settlement_gate(self, world: WorldData) -> None:
        location = world.locations.get(world.starting_location)
        if not location:
            return
        gate_name = self._settlement_gate_name(location)
        gate_description = self._settlement_gate_description(location)
        location.extra["starting_gate_name"] = gate_name
        location.extra["starting_gate_description"] = gate_description
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        gate = nodes.get("gate")
        if isinstance(gate, dict):
            gate["name"] = gate_name
            gate["description"] = gate_description
            gate["world_map_exit"] = True
            gate["visited"] = True
        graph["current"] = "gate"

    def _settlement_gate_name(self, location: LocationData) -> str:
        subtype = str(location.extra.get("main_node_subtype") or "").strip().lower()
        if subtype == "village":
            return "\u6751\u306e\u5165\u308a\u53e3"
        name = str(location.name or "").strip()
        if name:
            return f"{name}\u306e\u5165\u308a\u53e3"
        return "\u6751\u306e\u5165\u308a\u53e3"

    def _settlement_gate_description(self, location: LocationData) -> str:
        subtype = str(location.extra.get("main_node_subtype") or "").strip().lower()
        if subtype == "village":
            return "\u6751\u306e\u5916\u3078\u7d9a\u304f\u5165\u308a\u53e3\u3002\u4eba\u3084\u8377\u99ac\u8eca\u304c\u884c\u304d\u4ea4\u3063\u3066\u3044\u308b\u3002"
        name = str(location.name or "").strip()
        if name:
            return f"{name}\u306e\u5916\u3078\u7d9a\u304f\u5165\u308a\u53e3\u3002\u4eba\u3084\u8377\u99ac\u8eca\u304c\u884c\u304d\u4ea4\u3063\u3066\u3044\u308b\u3002"
        return "\u6751\u306e\u5916\u3078\u7d9a\u304f\u5165\u308a\u53e3\u3002\u4eba\u3084\u8377\u99ac\u8eca\u304c\u884c\u304d\u4ea4\u3063\u3066\u3044\u308b\u3002"

    def _local_world_opening(self, theme: dict[str, Any], story: dict[str, Any], world: WorldData) -> str:
        opening = str(theme.get("opening") or story.get("opening") or "").strip()
        if opening:
            return _clean_settlement_generated_text(opening, world.starting_location)
        return f"{world.starting_location}\u306e\u5165\u308a\u53e3\u306b\u7acb\u3063\u3066\u3044\u308b\u3002\u3053\u3053\u304b\u3089{world.world_name}\u306e\u65c5\u304c\u59cb\u307e\u308b\u3002\n{world.overview}"

    def _chunks(self, values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        size = max(1, int(size or 1))
        return [values[index : index + size] for index in range(0, len(values), size)]

    def apply_player_character(self, character: Character) -> str:
        if not self.state.world_data or self.state.world_data.world_name == "unknown":
            raise RuntimeError("No generated world is waiting for character setup.")
        self._install_player_character(character)
        self.save_game()
        return self.state.log_text()

    def player_character(self) -> Character | None:
        player_uuid = str(self.state.player_uuid or "").strip()
        if player_uuid:
            player = self.state.world_data.character(player_uuid)
            if player:
                return player
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                return character
        return None

    def _emit_world_generation_progress(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None,
        phase: str,
        message: str,
        current: int,
        total: int,
        *,
        item_current: int | None = None,
        item_total: int | None = None,
    ) -> None:
        if progress_callback is None:
            return
        safe_total = max(1, int(total or 1))
        safe_current = max(0, min(safe_total, int(current or 0)))
        payload: dict[str, Any] = {
            "phase": phase,
            "message": message,
            "current": safe_current,
            "total": safe_total,
            "percent": int(safe_current * 100 / safe_total),
        }
        if item_current is not None:
            payload["item_current"] = max(0, int(item_current))
        if item_total is not None:
            payload["item_total"] = max(0, int(item_total))
        try:
            progress_callback(payload)
        except Exception:
            return

    def generate_character_setup_traits(
        self,
        character: Character,
        seed_name: str = "",
        seed_description: str = "",
    ) -> list[dict[str, Any]]:
        if str(seed_name or "").strip():
            character.traits = [_trait_entry({"name": seed_name, "desc": seed_description})]
        else:
            character.traits = [trait for trait in (_trait_entry(item) for item in _as_list(character.traits)) if trait.get("name")]
        return character.traits

    def generate_character_setup_skills(
        self,
        character: Character,
        desired_element: str = "",
        seed_name: str = "",
        seed_description: str = "",
    ) -> list[dict[str, Any]]:
        response = self._create_skill(
            character.name or self.state.player_name,
            self.state.world_data,
            character,
            desired_element=desired_element,
            seed_name=seed_name,
            seed_description=seed_description,
        )
        self._apply_character_skills(character, response)
        return character.skills

    def _install_player_character(self, character: Character) -> None:
        name = character.name.strip() or "Player"
        character.name = name
        character.role = character.role or "Player"
        character.category = character.category or "player"
        character.flags["is_player"] = True
        character.flags.setdefault("source", "character_setup")
        for existing_uuid, existing in list(self.state.world_data.characters.items()):
            if str(existing.uuid or "") == str(character.uuid or ""):
                continue
            if existing.name != name:
                continue
            if not (existing.flags.get("is_player") or existing.flags.get("source") in {"character_setup", "character_setup_preview"}):
                continue
            if not character.image_paths:
                character.image_paths.update(existing.image_paths)
            if not character.prompts:
                character.prompts.update(existing.prompts)
            if existing.extra.get("image_pipeline") and not character.extra.get("image_pipeline"):
                character.extra["image_pipeline"] = existing.extra.get("image_pipeline")
            self.state.world_data.characters.pop(existing_uuid, None)
        _normalise_actor_power_loadout(character)
        self.state.player_name = name
        self.state.player_uuid = character.uuid
        self.state.gold = int(character.gold or 0)
        self.state.inventory = list(character.inventory)
        character.inventory = self.state.inventory
        character.location = self.state.current_location or self.state.world_data.starting_location
        character.state = "present"
        self._ensure_character_runtime_data(character)
        self._ensure_player_progress(character)
        self.state.party_uuids = [character.uuid]
        self.state.party = [character.to_dict()]
        self.state.world_data.add_character(character)
        self.state.flags["player_character"] = character.to_dict()
        max_hp = self._player_max_hp(character)
        current_hp = self._player_current_hp(max_hp)
        self._set_player_hp(current_hp, max_hp=max_hp)
        max_sp = self._player_max_sp(character)
        current_sp = self._player_current_sp(max_sp)
        self._set_player_sp(current_sp, max_sp=max_sp)
        self._set_player_hunger(self._player_hunger())
        self.state.flags["player_character"] = character.to_dict()
        self.state.world_data.history.append(
            {
                "manager": "character_setup",
                "character": name,
                "response": _character_ai_context(character),
            }
        )

    def _append_turn(
        self,
        action: str,
        narration: str,
        location: str,
        choices: list[str],
        input_type: str = "free_action",
    ) -> None:
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self.state.display_log.extend(self._apply_starvation_turn_penalty())

    def _player_inventory(self) -> list[dict[str, Any]]:
        character = self.player_character()
        if character:
            inventory = character.inventory if isinstance(character.inventory, list) else []
            character.inventory = inventory
            self.state.inventory = inventory
            return inventory
        inventory = self.state.inventory
        if not isinstance(inventory, list):
            inventory = []
            self.state.inventory = inventory
        return inventory

    def _sync_player_inventory(self) -> None:
        inventory = self._player_inventory()
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["inventory"] = inventory
            self.state.party[0]["gold"] = self.state.gold
        character = self.player_character()
        if character:
            character.inventory = inventory
            character.gold = self.state.gold

    def player_inventory_slots_used(self) -> int:
        return inventory_slot_count(self._player_inventory())

    def player_inventory_slots_max(self) -> int:
        return PLAYER_INVENTORY_MAX_SLOTS

    def can_add_player_item(self, item: Any, *, source: str = "", quantity: int | None = None) -> bool:
        return can_add_item_stack(
            self._player_inventory(),
            item,
            max_slots=PLAYER_INVENTORY_MAX_SLOTS,
            source=source,
            quantity=quantity,
        )

    def _inventory_full_line(self, item: Any | None = None) -> str:
        name = ""
        if item is not None:
            try:
                name = str(normalise_item(item).get("name") or "")
            except Exception:
                name = str(item or "")
        suffix = f": {name}" if name else ""
        return f"> [所持品] 所持品がいっぱいです ({self.player_inventory_slots_used()}/{PLAYER_INVENTORY_MAX_SLOTS}){suffix}"

    def _add_player_item_stack(self, item: Any, *, source: str, quantity: int | None = None) -> dict[str, Any] | None:
        added = add_item_stack(
            self._player_inventory(),
            item,
            source=source,
            quantity=quantity,
            max_slots=PLAYER_INVENTORY_MAX_SLOTS,
        )
        if added:
            self._sync_player_inventory()
        return added

    def _player_homes(self) -> dict[str, dict[str, Any]]:
        homes = self.state.world_data.extra.setdefault(PLAYER_HOMES_KEY, {})
        if not isinstance(homes, dict):
            homes = {}
            self.state.world_data.extra[PLAYER_HOMES_KEY] = homes
        return homes

    def _player_home_construction(self) -> dict[str, dict[str, Any]]:
        construction = self.state.world_data.extra.setdefault(PLAYER_HOME_CONSTRUCTION_KEY, {})
        if not isinstance(construction, dict):
            construction = {}
            self.state.world_data.extra[PLAYER_HOME_CONSTRUCTION_KEY] = construction
        return construction

    def _player_home_for_location(self, location_name: str) -> dict[str, Any] | None:
        location_name = str(location_name or "").strip()
        if not location_name:
            return None
        home = self._player_homes().get(location_name)
        if not isinstance(home, dict):
            return None
        storage = home.setdefault("storage", [])
        if not isinstance(storage, list):
            storage = []
            home["storage"] = storage
        home["level"] = max(1, min(PLAYER_HOME_MAX_LEVEL, _safe_int(home.get("level"), 1)))
        home.setdefault("name", PLAYER_HOME_NAME)
        home.setdefault("subnode_id", PLAYER_HOME_SUBNODE_ID)
        return home

    def _current_player_home(self) -> dict[str, Any] | None:
        location_name = self.state.current_location or self.state.world_data.starting_location
        home = self._player_home_for_location(location_name)
        if not home:
            return None
        current_subnode = self._current_subnode_id(location_name)
        if current_subnode and current_subnode == str(home.get("subnode_id") or ""):
            return home
        return None

    def is_current_player_home(self) -> bool:
        return self._current_player_home() is not None

    def current_home_storage_inventory(self) -> list[dict[str, Any]]:
        home = self._current_player_home()
        if not home:
            return []
        storage = home.setdefault("storage", [])
        if not isinstance(storage, list):
            storage = []
            home["storage"] = storage
        for index, raw in enumerate(list(storage)):
            if isinstance(raw, dict):
                storage[index] = normalise_item(raw, source="home_storage")
        return storage

    def _home_choices(self) -> list[str]:
        return _exploration_choices(list(PLAYER_HOME_CHOICES))

    def _current_home_furniture_level(self) -> int:
        home = self._current_player_home()
        if not home:
            return 0
        return max(1, min(PLAYER_HOME_MAX_LEVEL, _safe_int(home.get("level"), 1)))

    def _home_craft_target(self, base_target: int) -> tuple[int, int, int]:
        level = self._current_home_furniture_level()
        reduction = min(5, level // 2) if level else 0
        target = _normalise_roll_target(max(6, int(base_target) - reduction))
        return target, level, reduction

    def _create_player_home(
        self,
        location_name: str,
        level: int,
        *,
        source: str,
        parent_subnode_id: str = "",
        cost: int = 0,
    ) -> dict[str, Any]:
        location_name = str(location_name or self.state.current_location or self.state.world_data.starting_location).strip()
        location = self.state.world_data.ensure_location(location_name)
        level = max(1, min(PLAYER_HOME_MAX_LEVEL, _safe_int(level, 1)))
        existing = self._player_home_for_location(location_name)
        if existing:
            return existing
        if not isinstance(location.extra.get(SUBNODE_GRAPH_KEY), dict):
            location.extra[SUBNODE_GRAPH_KEY] = {}
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        nodes = graph.setdefault("nodes", {})
        parent = str(parent_subnode_id or self._current_subnode_id(location_name) or self._default_subnode_for_location(location)).strip()
        if parent not in nodes:
            parent = self._default_subnode_for_location(location)
        if parent not in nodes:
            self._ensure_basic_subnodes(location, graph)
            parent = DEFAULT_SUBNODE_ID if DEFAULT_SUBNODE_ID in nodes else next(iter(nodes), DEFAULT_SUBNODE_ID)
        parent_node = nodes.get(parent, {}) if isinstance(nodes.get(parent), dict) else {}
        x = _safe_int(parent_node.get("x"), 120) + 160
        y = _safe_int(parent_node.get("y"), 160) + 90
        node = self._upsert_subnode_node(
            graph,
            PLAYER_HOME_SUBNODE_ID,
            PLAYER_HOME_NAME,
            f"あなたの家。鍛冶、料理、調合、クラフトに使える家具が一通りそろっている。家具Lv{level}。",
            PLAYER_HOME_KIND,
            x,
            y,
            player_home=True,
            home_level=level,
            world_map_exit=bool(parent_node.get("world_map_exit")),
        )
        self._connect_subnodes(graph, parent, PLAYER_HOME_SUBNODE_ID, kind="home_path")
        node["visited"] = True
        home = {
            "location": location_name,
            "subnode_id": PLAYER_HOME_SUBNODE_ID,
            "parent_subnode_id": parent,
            "name": PLAYER_HOME_NAME,
            "level": level,
            "storage": [],
            "source": source,
            "cost": max(0, int(cost or 0)),
            "created_day": self.state.day,
        }
        self._player_homes()[location_name] = home
        self.state.world_data.extra.setdefault("player_home_events", []).append(
            {"type": "created", "location": location_name, "level": level, "source": source, "cost": cost}
        )
        return home

    def _resolve_home_rest(self, action: str, input_type: str) -> str:
        return self._resolve_player_rest_tool_action(action, input_type) or self.state.log_text(16)

    def _resolve_home_exit(self, action: str, input_type: str) -> str:
        home = self._current_player_home()
        if not home:
            return self.state.log_text(16)
        parent = str(home.get("parent_subnode_id") or DEFAULT_SUBNODE_ID)
        return self._run_llm_action_tool(
            LlmToolName.MOVE_PLAYER,
            "player_choice",
            action,
            input_type,
            {"target_subnode": parent, "reason": "home_exit", "narration": "家を出て、外の空気を吸い込んだ。"},
        ) or self.state.log_text(16)

    def _apply_response_move_player_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "choice",
        location: str = "",
    ) -> dict[str, Any]:
        response = response if isinstance(response, dict) else {}
        previous_location = self.state.current_location or self.state.world_data.starting_location
        proposed = requested_location_from_tools(response, location or previous_location)
        movement_result = self._normalize_world_response_location(action, input_type, response, proposed)
        new_location = str(movement_result.get("location") or proposed or previous_location)
        narration = str(response.get("narration") or "").strip()
        movement_lines = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
        if not narration:
            if movement_result.get("moved"):
                narration = "移動した。"
            elif movement_result.get("denied"):
                narration = movement_lines[0] if movement_lines else "その場所へは移動できない。"
            else:
                narration = "現在地を確認した。"
        if movement_lines and movement_lines[0] not in narration:
            narration = "\n".join([narration, *movement_lines]).strip()
        choices = self._location_default_choices(new_location)
        encounter = self._active_encounter()
        if encounter:
            choices = self._encounter_choices(encounter)
        elif not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self._append_turn(action or "移動する", narration, new_location, choices, input_type=input_type)
        self._set_player_presence(new_location)
        status_lines = [str(line) for line in movement_result.get("status_lines", []) if str(line).strip()]
        if status_lines:
            self.state.display_log.extend(status_lines)
        event = {
            "handled": True,
            "source": source,
            "action": action,
            "input_type": input_type,
            "previous_location": previous_location,
            "location": new_location,
            "moved": bool(movement_result.get("moved")),
            "denied": bool(movement_result.get("denied")),
            "movement_result": movement_result,
            "lines": status_lines,
            "log_text": self.state.log_text(16),
        }
        self.state.world_data.extra.setdefault("move_player_tool_events", []).append(
            {key: value for key, value in event.items() if key != "log_text"}
        )
        self.save_game()
        return event

    def _resolve_player_rest_tool_action(self, action: str, input_type: str) -> str | None:
        return self._run_llm_action_tool(LlmToolName.PLAYER_REST, "player_choice", action, input_type, {})

    def _apply_response_player_rest_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "choice",
    ) -> dict[str, Any]:
        location_name = self.state.current_location or self.state.world_data.starting_location
        rest_kind = self._player_rest_kind()
        if rest_kind == "inn" and self.state.gold < PLAYER_REST_INN_COST:
            narration = f"宿屋で休むには{PLAYER_REST_INN_COST}Goldが必要だ。所持金が足りない。"
            self._append_turn(action or "休息する", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            self.save_game()
            return {
                "handled": True,
                "rested": False,
                "reason": "not_enough_gold",
                "required_gold": PLAYER_REST_INN_COST,
                "current_gold": self.state.gold,
                "log_text": self.state.log_text(16),
            }

        gold_event: dict[str, Any] = {}
        if rest_kind == "inn":
            gold_event = self._apply_gold_delta(
                -PLAYER_REST_INN_COST,
                source=source,
                reason="宿泊",
                append_log=False,
            )

        time_event = self._advance_world_time(
            PLAYER_HOME_REST_HOURS,
            source=source or "player_rest",
            reason=self._player_rest_reason(rest_kind),
            append_log=False,
        )
        full_recovery = rest_kind in {"inn", "home"}
        recovery_lines = self._recover_player_and_party_for_rest(full=full_recovery)
        ambush_event: dict[str, Any] = {}
        narration = self._player_rest_narration(rest_kind)
        choices = self._location_default_choices(location_name)
        if rest_kind == "dangerous" and not self._rest_location_has_npc(location_name):
            ambush_event = self._maybe_start_rest_ambush(action or "休息する")
            if ambush_event.get("started"):
                narration = "\n".join(part for part in (narration, str(ambush_event.get("narration") or "")) if part.strip())
                encounter = self._active_encounter()
                if encounter:
                    choices = self._encounter_choices(encounter)

        self._append_turn(action or "休息する", narration, location_name, choices, input_type=input_type)
        display_lines: list[str] = []
        if gold_event.get("line"):
            display_lines.append(str(gold_event["line"]))
        if time_event.get("line"):
            display_lines.append(str(time_event["line"]))
        display_lines.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        display_lines.extend(recovery_lines)
        self.state.display_log.extend(display_lines)
        event = {
            "handled": True,
            "rested": True,
            "source": source,
            "rest_kind": rest_kind,
            "hours": PLAYER_HOME_REST_HOURS,
            "full_recovery": full_recovery,
            "location": location_name,
            "gold_event": gold_event,
            "time_event": time_event,
            "recovery_lines": recovery_lines,
            "ambush": ambush_event,
            "log_text": self.state.log_text(16),
        }
        self.state.world_data.extra.setdefault("player_rest_events", []).append(
            {key: value for key, value in event.items() if key != "log_text"}
        )
        self.save_game()
        return event

    def _player_rest_kind(self) -> str:
        active = self._active_facility_record()
        if active:
            facility_id = str(active.get("id") or active.get("facility_id") or "").strip().lower()
            facility_type = str(active.get("type") or active.get("kind") or "").strip().lower()
            if facility_id == "inn" or facility_type == "inn":
                return "inn"
        if self._current_player_home():
            return "home"
        return "dangerous" if self._current_area_is_dangerous_for_rest() else "safe"

    def _player_rest_reason(self, rest_kind: str) -> str:
        if rest_kind == "inn":
            return "inn rest"
        if rest_kind == "home":
            return "home rest"
        if rest_kind == "dangerous":
            return "dangerous area rest"
        return "safe area rest"

    def _player_rest_narration(self, rest_kind: str) -> str:
        if rest_kind == "inn":
            return "宿屋で部屋を取り、身体を休めた。"
        if rest_kind == "home":
            return "自分の家で身体を休めた。家具の整った静かな空間で、疲労がゆっくりと抜けていく。"
        if rest_kind == "dangerous":
            return "危険地帯で周囲を警戒しながら休息した。十分とは言えないが、少しだけ体力を取り戻した。"
        return "安全な場所で休息し、少しだけ体力を取り戻した。"

    def _current_area_is_dangerous_for_rest(self) -> bool:
        location = self.state.world_data.locations.get(self.state.current_location)
        if not location:
            return False
        if location.flags.get("dangerous") or _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location):
            return True
        return self._current_location_danger(location.name) > 0 and not _is_settlement_location(location)

    def _recover_player_and_party_for_rest(self, *, full: bool) -> list[str]:
        lines: list[str] = []
        max_hp = self._player_max_hp()
        max_sp = self._player_max_sp()
        old_hp = self._player_current_hp(max_hp)
        old_sp = self._player_current_sp(max_sp)
        new_hp = max_hp if full else min(max_hp, old_hp + max(1, (max_hp + 3) // 4))
        new_sp = max_sp if full else min(max_sp, old_sp + max(1, (max_sp + 3) // 4))
        self._set_player_hp(new_hp, max_hp=max_hp)
        self._set_player_sp(new_sp, max_sp=max_sp)
        lines.append(f"> [休息] {self.state.player_name}: HP {old_hp}/{max_hp} -> {new_hp}/{max_hp} / SP {old_sp}/{max_sp} -> {new_sp}/{max_sp}")
        for companion in self._party_companions():
            self._ensure_character_runtime_data(companion)
            comp_max_hp = max(1, _safe_int(companion.max_hp, _character_calculated_max_hp(companion)))
            comp_max_sp = max(1, _safe_int(companion.max_sp, _character_calculated_max_sp(companion, max_hp=comp_max_hp)))
            comp_old_hp = max(0, min(comp_max_hp, _safe_int(companion.current_hp, comp_max_hp)))
            comp_old_sp = max(0, min(comp_max_sp, _safe_int(companion.current_sp, comp_max_sp)))
            comp_new_hp = comp_max_hp if full else min(comp_max_hp, comp_old_hp + max(1, (comp_max_hp + 3) // 4))
            comp_new_sp = comp_max_sp if full else min(comp_max_sp, comp_old_sp + max(1, (comp_max_sp + 3) // 4))
            companion.max_hp = comp_max_hp
            companion.max_sp = comp_max_sp
            companion.current_hp = comp_new_hp
            companion.current_sp = comp_new_sp
            companion.extra["current_hp"] = comp_new_hp
            companion.extra["max_hp"] = comp_max_hp
            companion.extra["current_sp"] = comp_new_sp
            companion.extra["max_sp"] = comp_max_sp
            self._sync_companion_party_entry(companion)
            lines.append(f"> [休息] {companion.name}: HP {comp_old_hp}/{comp_max_hp} -> {comp_new_hp}/{comp_max_hp} / SP {comp_old_sp}/{comp_max_sp} -> {comp_new_sp}/{comp_max_sp}")
        return lines

    def _rest_location_has_npc(self, location_name: str) -> bool:
        location_name = str(location_name or self.state.current_location or self.state.world_data.starting_location or "").strip()
        if not location_name:
            return False
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_current_subnode(character, location_name):
                continue
            if location_name == (self.state.current_location or self.state.world_data.starting_location) and not self._character_matches_active_facility(character):
                continue
            return True
        return False

    def _maybe_start_rest_ambush(self, action: str) -> dict[str, Any]:
        roll = random.random()
        event: dict[str, Any] = {"roll": round(roll, 6), "chance": 0.5, "started": False}
        if roll >= 0.5 or self._active_encounter():
            return event
        location_name = self.state.current_location or self.state.world_data.starting_location
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        subnode_id = self._current_subnode_id(location_name)
        node = graph.get("nodes", {}).get(subnode_id, {}) if isinstance(graph, dict) else {}
        monster = self._generate_random_danger_subnode_monster(
            location_name,
            subnode_id,
            node if isinstance(node, dict) else {},
            source="player_rest_ambush",
            action=action,
        )
        if monster is None:
            event["error"] = "monster_generation_failed"
            return event
        encounter = self._start_encounter_with_character(monster, source="player_rest_ambush", action=action, location=location_name)
        subnode_name = str((node or {}).get("name") or subnode_id or location_name)
        narration = f"{subnode_name}で休んでいる最中、{monster.name}が襲いかかってきた。"
        event.update(
            {
                "started": True,
                "location": location_name,
                "subnode_id": subnode_id,
                "monster_uuid": monster.uuid,
                "monster_name": monster.name,
                "narration": narration,
                "encounter": _strip_encounter_log(encounter),
            }
        )
        self.state.world_data.extra.setdefault("player_rest_ambushes", []).append(event)
        return event

    def is_current_location_settlement(self) -> bool:
        return self._current_settlement_location() is not None

    def is_current_location_guild(self) -> bool:
        active_facility = self._active_facility_record()
        if active_facility and str(active_facility.get("type") or "").lower() == "guild":
            return True
        location = self.state.world_data.locations.get(self.state.current_location)
        if not location:
            return False
        if str(location.extra.get("facility_type") or "").lower() == "guild":
            return True
        settlement = self._current_settlement_location()
        if settlement:
            facility = _facility_for_location(settlement, self.state.current_location)
            if facility and str(facility.get("type") or "").lower() == "guild":
                return True
        return _looks_like_guild_name(location.name)

    def current_location_facilities(self) -> list[dict[str, Any]]:
        settlement = self._current_settlement_location()
        if not settlement:
            return []
        return self._ensure_settlement_facilities(settlement)

    def _active_facility_record(self) -> dict[str, Any] | None:
        active = self.state.flags.get("current_facility")
        if not isinstance(active, dict):
            return None
        settlement = self._current_settlement_location()
        if settlement is None:
            return None
        active_settlement = str(active.get("settlement") or "").strip()
        if active_settlement and active_settlement != settlement.name:
            return None
        active_name = str(active.get("name") or "").strip()
        for facility in self._ensure_settlement_facilities(settlement):
            if active_name and _facility_name_matches(str(facility.get("name") or ""), active_name):
                return facility
        return dict(active)

    def _set_active_facility(self, settlement: LocationData, facility: dict[str, Any]) -> None:
        name = str(facility.get("name") or "").strip()
        facility_type = str(facility.get("type") or _facility_type_from_name(name)).strip()
        self.state.flags.pop("active_conversation", None)
        self.state.flags["current_facility"] = {
            "settlement": settlement.name,
            "name": name,
            "type": facility_type,
            "npc_name": str(facility.get("npc_name") or ""),
            "description": str(facility.get("description") or ""),
        }
        graph = self._ensure_location_subnode_graph(self.state.world_data, settlement.name)
        node_id = self._facility_subnode_id(facility)
        if graph and node_id in graph.get("nodes", {}):
            self._set_current_subnode(settlement.name, node_id)

    def _clear_active_facility(self, *, reset_subnode: bool = True) -> None:
        self.state.flags.pop("current_facility", None)
        self.state.flags.pop("active_conversation", None)
        if reset_subnode:
            location_name = self.state.current_location or self.state.world_data.starting_location
            location = self.state.world_data.locations.get(location_name)
            if location and _is_settlement_location(location):
                self._set_current_subnode(location_name, DEFAULT_SUBNODE_ID)

    def _set_character_subnode_fields(self, character: Character, location_name: str, subnode_id: str) -> None:
        location_name = str(location_name or "").strip()
        subnode_id = str(subnode_id or "").strip()
        if not location_name or not subnode_id:
            return
        character.flags[ACTOR_SUBNODE_ID_FLAG] = subnode_id
        character.flags[ACTOR_SUBNODE_LOCATION_FLAG] = location_name
        character.extra[ACTOR_SUBNODE_ID_FLAG] = subnode_id
        character.extra[ACTOR_SUBNODE_LOCATION_FLAG] = location_name

    def _clear_character_subnode_fields(self, character: Character) -> None:
        for mapping in (character.flags, character.extra):
            if isinstance(mapping, dict):
                mapping.pop(ACTOR_SUBNODE_ID_FLAG, None)
                mapping.pop(ACTOR_SUBNODE_LOCATION_FLAG, None)

    def _character_subnode_assignment(self, character: Character) -> tuple[str, str]:
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        subnode_id = str(extra.get(ACTOR_SUBNODE_ID_FLAG) or flags.get(ACTOR_SUBNODE_ID_FLAG) or "").strip()
        location_name = str(extra.get(ACTOR_SUBNODE_LOCATION_FLAG) or flags.get(ACTOR_SUBNODE_LOCATION_FLAG) or "").strip()
        return location_name, subnode_id

    def _ensure_character_subnode_assignment_for_location(self, character: Character, location_name: str) -> str:
        location_name = str(location_name or "").strip()
        if not location_name or character.flags.get("is_player"):
            return ""
        location = self.state.world_data.locations.get(location_name)
        if not location or not _is_settlement_location(location):
            return ""
        return self._assign_settlement_character_subnode(self.state.world_data, location, character)

    def _runtime_subnode_for_presence(self, location_name: str) -> str:
        location_name = str(location_name or "").strip()
        if not location_name or location_name != (self.state.current_location or self.state.world_data.starting_location):
            return ""
        if location_name not in self.state.world_data.locations:
            return ""
        try:
            return self._current_subnode_id(location_name)
        except Exception:
            return ""

    def _character_matches_current_subnode(self, character: Character, location_name: str | None = None) -> bool:
        location_name = str(location_name or self.state.current_location or self.state.world_data.starting_location or "").strip()
        assigned_location, assigned_subnode = self._character_subnode_assignment(character)
        if not assigned_subnode:
            assigned_subnode = self._ensure_character_subnode_assignment_for_location(character, location_name)
            if not assigned_subnode:
                return True
            assigned_location = location_name
        if assigned_location and location_name and assigned_location != location_name:
            return True
        current_subnode = self._current_subnode_id(location_name) if location_name else ""
        if not current_subnode:
            return True
        return assigned_subnode == current_subnode

    def _character_matches_active_facility(self, character: Character) -> bool:
        if not self._character_matches_current_subnode(character):
            return False
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        facility_name = str(extra.get("facility") or flags.get("facility_name") or "").strip()
        facility_type = str(extra.get("facility_type") or flags.get("facility_type") or "").strip().lower()
        if not facility_name and not facility_type:
            return True
        active = self._active_facility_record()
        if not active:
            return False
        active_name = str(active.get("name") or "").strip()
        active_type = str(active.get("type") or "").strip().lower()
        if facility_name and active_name and _facility_name_matches(facility_name, active_name):
            return True
        return bool(facility_type and active_type and facility_type == active_type and not facility_name)

    def _npc_visibility_rule_prompt(self) -> str:
        return (
            "NPC visibility rule: world_data.nearby_npcs / context.nearby_npcs contains NPCs in the "
            "current location and current subnode. Treat every listed NPC as present and directly visible "
            "to the player. Do not describe listed NPCs as absent, too far away, unseen, or not nearby "
            "unless an explicit state/tool result has moved or hidden them."
        )

    def _visible_npc_context_fields(self, character: Character, location_name: str) -> dict[str, Any]:
        location_name = str(location_name or "").strip()
        assigned_location, assigned_subnode = self._character_subnode_assignment(character)
        current_subnode = ""
        if location_name:
            try:
                current_subnode = self._current_subnode_id(location_name)
            except Exception:
                current_subnode = ""
        subnode_id = assigned_subnode
        if not subnode_id:
            subnode_id = self._ensure_character_subnode_assignment_for_location(character, location_name)
            if subnode_id:
                assigned_location = location_name
        if assigned_location and location_name and assigned_location != location_name:
            subnode_id = current_subnode
        if not subnode_id:
            subnode_id = current_subnode
        subnode_name = ""
        if location_name and subnode_id:
            graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
            nodes = graph.get("nodes", {}) if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict) else {}
            node = nodes.get(subnode_id, {}) if isinstance(nodes, dict) else {}
            if isinstance(node, dict):
                subnode_name = str(node.get("name") or subnode_id)
        same_subnode = bool(current_subnode and subnode_id and current_subnode == subnode_id)
        return _drop_empty(
            {
                "location": location_name,
                "subnode_id": subnode_id,
                "subnode_name": subnode_name,
                "same_location": bool(location_name),
                "same_subnode": same_subnode or None,
                "visibility": "visible_current_subnode" if same_subnode else "visible_current_location",
            }
        )

    def travel_to_facility(self, facility_name: str) -> str:
        self.dismiss_active_cg()
        settlement = self._current_settlement_location()
        if settlement is None:
            narration = "ここは街や村ではないため、施設の地図は使えない。"
            self._append_turn(MOVE_CHOICE_LABEL, narration, self.state.current_location, self.state.choices, input_type="choice")
            self.save_game()
            return self.state.log_text(16)

        facility = self._find_or_create_facility_record(settlement, facility_name)
        if not facility:
            narration = f"{settlement.name}には「{facility_name}」という施設は見当たらない。"
            self._append_turn(MOVE_CHOICE_LABEL, narration, self.state.current_location, self._location_default_choices(settlement.name), input_type="choice")
            self.save_game()
            return self.state.log_text(16)

        return self._move_to_facility(settlement, facility, action=f"{facility.get('name') or facility_name}へ移動", input_type="choice")

    def _player_equipment(self) -> dict[str, dict[str, Any]]:
        raw = self.state.extra.get("equipment")
        if not isinstance(raw, dict):
            raw = {}
            self.state.extra["equipment"] = raw
        equipment: dict[str, dict[str, Any]] = {}
        for slot in EQUIPMENT_SLOTS:
            item = raw.get(slot)
            if isinstance(item, dict) and item:
                normalised = normalise_item(item)
                normalised["equipped"] = True
                normalised["equipment_slot"] = slot
                equipment[slot] = normalised
            else:
                equipment[slot] = {}
        self.state.extra["equipment"] = equipment
        return equipment

    def _equipment_slot_for_item(self, item: dict[str, Any]) -> str:
        slot = equipment_slot_for_category(str(item.get("category") or ""))
        if slot in EQUIPMENT_SLOTS:
            return slot
        slot = str(item.get("equipment_slot") or "").strip()
        if slot in EQUIPMENT_SLOTS:
            return slot
        return ""

    def _sync_player_equipment(self) -> None:
        equipment = self._player_equipment()
        inventory = self._player_inventory()
        equipped_ids = {
            str(item.get("instance_id") or "")
            for item in equipment.values()
            if isinstance(item, dict) and item.get("instance_id")
        }
        for item in inventory:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("instance_id") or "")
            item["equipped"] = bool(item_id and item_id in equipped_ids)
            if item["equipped"]:
                item["equipment_slot"] = equipment_slot_for_category(str(item.get("category") or ""))
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["equipment"] = equipment
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra["equipment"] = equipment
        character = self.player_character()
        if character:
            character.extra["equipment"] = equipment

    def player_equipment_summary(self) -> dict[str, Any]:
        return calculate_equipment_summary(self._player_equipment())

    def player_combat_stats(self) -> dict[str, int]:
        equipment = self.player_equipment_summary()
        temporary = self._temporary_combat_bonuses()
        return {
            "attack": int(equipment.get("attack") or 0),
            "defense": int(equipment.get("defense") or 0),
            "attack_bonus": int(temporary.get("attack") or 0),
            "defense_bonus": int(temporary.get("defense") or 0),
        }

    def _temporary_combat_bonuses(self) -> dict[str, int]:
        effects: list[Any] = []
        active = self._active_encounter()
        effects.extend(self.state.status_effects)
        player = self.player_character()
        if player:
            effects.extend(player.status_effects)
        if isinstance(active, dict):
            effects.extend(_as_list(active.get("player_status_effects")))
        return _combat_stat_delta(effects)

    def _player_status_immunity_ids(self) -> set[str]:
        summary = self.player_equipment_summary()
        result: set[str] = set()
        for value in summary.get("status_immunities", []):
            effect_id = canonical_status_effect_id(value)
            if effect_id in STATUS_IMMUNITY_EFFECT_IDS:
                result.add(effect_id)
        return result

    def _player_is_immune_to_status(self, effect: dict[str, Any]) -> bool:
        effect_id = _status_effect_id(effect)
        if not effect_id:
            return False
        if effect_id not in STATUS_IMMUNITY_EFFECT_IDS:
            return False
        return effect_id in self._player_status_immunity_ids()

    def toggle_player_equipment(self, inventory_index: int, *, save_game: bool = True) -> dict[str, Any]:
        inventory = self._player_inventory()
        if inventory_index < 0 or inventory_index >= len(inventory):
            return {"changed": False, "line": ""}
        item = normalise_item(inventory[inventory_index])
        inventory[inventory_index] = item
        if not is_equipment_item(item):
            return {"changed": False, "line": f"> [装備] {item.get('name') or 'Unknown'} は装備できない。"}
        if item.get("equipped"):
            event = self._unequip_player_slot(self._equipment_slot_for_item(item), source="inventory")
        else:
            event = self._equip_player_inventory_index(inventory_index, source="inventory")
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _equip_player_inventory_index(self, inventory_index: int, *, source: str, reason: str = "") -> dict[str, Any]:
        inventory = self._player_inventory()
        if inventory_index < 0 or inventory_index >= len(inventory):
            return {"changed": False, "line": ""}
        item = normalise_item(inventory[inventory_index], source=source)
        slot = equipment_slot_for_category(str(item.get("category") or ""))
        if slot not in EQUIPMENT_SLOTS:
            return {"changed": False, "line": ""}
        equipment = self._player_equipment()
        previous = equipment.get(slot) if isinstance(equipment.get(slot), dict) else {}
        if previous:
            self._mark_inventory_equipped(str(previous.get("instance_id") or ""), False)
        item["equipped"] = True
        item["equipment_slot"] = slot
        inventory[inventory_index] = item
        equipment[slot] = dict(item)
        self.state.extra["equipment"] = equipment
        self._sync_player_equipment()
        self._refresh_player_resource_caps_after_equipment_change()
        previous_name = str(previous.get("name") or "")
        suffix = f"（{previous_name}を外した）" if previous_name else ""
        line = f"> [装備] {EQUIPMENT_SLOT_LABELS.get(slot, slot)}: {item.get('name')}{suffix}"
        event = {"changed": True, "action": "equip", "slot": slot, "item": dict(item), "previous": previous, "source": source, "reason": reason, "line": line}
        self.state.world_data.extra.setdefault("equipment_events", []).append(_strip_response_metadata(event))
        return event

    def _unequip_player_slot(self, slot: str, *, source: str, reason: str = "") -> dict[str, Any]:
        slot = str(slot or "").strip()
        if slot not in EQUIPMENT_SLOTS:
            return {"changed": False, "line": ""}
        equipment = self._player_equipment()
        item = equipment.get(slot) if isinstance(equipment.get(slot), dict) else {}
        if not item:
            return {"changed": False, "line": ""}
        equipment[slot] = {}
        self.state.extra["equipment"] = equipment
        self._mark_inventory_equipped(str(item.get("instance_id") or ""), False)
        self._sync_player_equipment()
        self._refresh_player_resource_caps_after_equipment_change()
        line = f"> [装備解除] {EQUIPMENT_SLOT_LABELS.get(slot, slot)}: {item.get('name')}"
        event = {"changed": True, "action": "unequip", "slot": slot, "item": dict(item), "source": source, "reason": reason, "line": line}
        self.state.world_data.extra.setdefault("equipment_events", []).append(_strip_response_metadata(event))
        return event

    def _mark_inventory_equipped(self, instance_id: str, equipped: bool) -> None:
        if not instance_id:
            return
        for item in self._player_inventory():
            if isinstance(item, dict) and str(item.get("instance_id") or "") == instance_id:
                item["equipped"] = equipped

    def _refresh_player_resource_caps_after_equipment_change(self) -> None:
        max_hp = self._player_max_hp()
        current_hp = self._player_current_hp(max_hp)
        self._set_player_hp(current_hp, max_hp=max_hp)
        max_sp = self._player_max_sp()
        current_sp = self._player_current_sp(max_sp)
        self._set_player_sp(current_sp, max_sp=max_sp)

    def _apply_response_item_add_effects(self, response: Any, source: str) -> dict[str, Any]:
        items = self._response_item_add_entries(response, source)
        added_items: list[dict[str, Any]] = []
        skipped_items: list[dict[str, Any]] = []
        for item in items:
            added = self._add_player_item_stack(item, source=source)
            if added:
                added_items.append(added)
            else:
                skipped_items.append(normalise_item(item, source=source))
        event = {"source": source, "items": added_items, "skipped_items": skipped_items}
        if not added_items and not skipped_items:
            return event
        self._sync_player_inventory()
        self.state.world_data.extra.setdefault("inventory_events", []).append(event)
        self.state.display_log.extend(reward_log_lines(added_items, 0))
        self.state.display_log.extend(self._inventory_full_line(item) for item in skipped_items)
        return event

    def _response_item_add_entries(self, response: Any, source: str) -> list[dict[str, Any]]:
        if not isinstance(response, dict):
            return []
        items: list[dict[str, Any]] = []
        for key in ("item_add", "item_adds", "item", "items"):
            if response.get(key) in (None, "", [], {}):
                continue
            extracted, _gold = extract_response_rewards({"items": response.get(key)}, source=source)
            items.extend(extracted)
        return items

    def _apply_response_item_remove_effects(self, response: Any, source: str) -> dict[str, Any]:
        removed = self._apply_response_item_losses(response, source)
        event = {"source": source, "lost_items": removed}
        if removed:
            self.state.display_log.extend(f"> [喪失] {item_label(item)}" for item in removed)
        return event

    def _apply_response_item_equip_effects(self, response: Any, source: str) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {"source": source, "equipment": []}
        events: list[dict[str, Any]] = []
        for key in ("item_equip", "item_equips"):
            for value in _as_list(response.get(key)):
                reason = _item_effect_reason(value)
                event = self._equip_player_item_reference(_item_effect_reference(value), source=source, reason=reason)
                if event.get("changed"):
                    events.append(event)
        if events:
            self.state.display_log.extend(str(item.get("line")) for item in events if item.get("line"))
        return {"source": source, "equipment": events}

    def _apply_response_item_unequip_effects(self, response: Any, source: str) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {"source": source, "equipment": []}
        events: list[dict[str, Any]] = []
        for key in ("item_unequip", "item_unequips"):
            for value in _as_list(response.get(key)):
                reason = _item_effect_reason(value)
                event = self._unequip_player_reference(_item_effect_reference(value), source=source, reason=reason)
                if event.get("changed"):
                    events.append(event)
        if events:
            self.state.display_log.extend(str(item.get("line")) for item in events if item.get("line"))
        return {"source": source, "equipment": events}

    def _apply_response_item_effects(self, response: Any, source: str) -> dict[str, Any]:
        payload = tool_effect_payload(response) if isinstance(response, dict) else {}
        if not payload:
            payload = response
        event: dict[str, Any] = {"source": source, "items": [], "skipped_items": [], "lost_items": [], "equipment": []}
        for partial in (
            self._apply_response_item_add_effects(payload, source),
            self._apply_response_item_remove_effects(payload, source),
            self._apply_response_item_equip_effects(payload, source),
            self._apply_response_item_unequip_effects(payload, source),
        ):
            for key in ("items", "skipped_items", "lost_items", "equipment"):
                values = partial.get(key) if isinstance(partial, dict) else None
                if isinstance(values, list):
                    event[key].extend(values)
                elif values not in (None, "", [], {}):
                    event[key].append(values)
        return event

    def resolve_craft_from_selected_items(
        self,
        ingredients: list[dict[str, Any]],
        intent: str = "",
        craft_category: str = "auto",
    ) -> str:
        craft_intent = _normalise_craft_intent(craft_category)
        intent_info = _craft_intent_payload(craft_intent)
        action = intent.strip() or f"craft selected materials as {intent_info['label_en']}"
        items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
        return self._resolve_craft_with_ingredients(
            action,
            "free_action",
            items,
            source="craft_menu",
            craft_intent=craft_intent,
        )

    def craft_preview_for_selected_items(
        self,
        ingredients: list[dict[str, Any]],
        craft_category: str = "auto",
    ) -> dict[str, Any]:
        items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
        if len(items) < 2:
            return {"text": "種別:- / 予想目標値:-", "kind": "", "target": 0}
        plan = self._craft_plan_for_items(items, craft_category)
        payload = plan.to_dict()
        payload["text"] = craft_preview_text(plan)
        return payload

    def _craft_plan_for_items(self, ingredients: list[dict[str, Any]], craft_intent: str = "auto") -> CraftPlan:
        return determine_craft_plan(
            ingredients,
            craft_intent,
            home_level=self._current_home_furniture_level(),
            dangerous_area=self._craft_dangerous_area(),
        )

    def _craft_dangerous_area(self) -> bool:
        location = self.state.world_data.locations.get(self.state.current_location)
        if not location:
            return False
        return bool(
            location.flags.get("dangerous")
            or _is_dungeon_location(location)
            or _world_location_blocks_world_map_departure(location)
        )

    def _resolve_home_action(self, action: str, input_type: str) -> str | None:
        text = str(action or "").strip()
        if not text:
            return None
        if self._current_player_home():
            if text == "保存箱を開く":
                self.state.flags["pending_home_menu"] = "storage"
                self._append_turn(action, "家の保存箱を開いた。", self.state.current_location, self._home_choices(), input_type=input_type)
                self.save_game()
                return self.state.log_text(16)
            if text == "クラフトを行う":
                self.state.flags["pending_home_menu"] = "craft"
                self._append_turn(action, "家の作業台を使う準備をした。", self.state.current_location, self._home_choices(), input_type=input_type)
                self.save_game()
                return self.state.log_text(16)
            if text == "休息する":
                return self._resolve_player_rest_tool_action(action, input_type)
            if text == "家から出る":
                return self._resolve_home_exit(action, input_type)

        home_travel = self._resolve_player_home_travel(action, input_type)
        if home_travel is not None:
            return home_travel

        town_hall_result = self._resolve_home_purchase_tool_action(action, input_type)
        if town_hall_result is not None:
            return town_hall_result
        return None

    def _resolve_player_home_travel(self, action: str, input_type: str) -> str | None:
        text = str(action or "")
        lowered = text.lower()
        if not any(word in lowered or word in text for word in ("プレイヤーの家", "自宅", "家", "home", "house")):
            return None
        if not any(word in lowered or word in text for word in ("移動", "行く", "向かう", "入る", "帰る", "go", "enter", "home")):
            return None
        location_name = self.state.current_location or self.state.world_data.starting_location
        home = self._player_home_for_location(location_name)
        if not home:
            return None
        self._clear_active_facility(reset_subnode=False)
        self._set_current_subnode(location_name, str(home.get("subnode_id") or PLAYER_HOME_SUBNODE_ID))
        narration = "あなたは自分の家へ戻った。鍛冶、料理、調合、クラフトに使える家具が静かに並んでいる。"
        self._append_turn(action, narration, location_name, self._home_choices(), input_type=input_type)
        self.save_game()
        return self.state.log_text(16)

    def _resolve_town_hall_home_purchase(self, action: str, input_type: str) -> str | None:
        return self._resolve_home_purchase_tool_action(action, input_type)

    def _resolve_home_purchase_tool_action(self, action: str, input_type: str) -> str | None:
        active = self._active_facility_record()
        if not active or str(active.get("type") or "").lower() != "town_hall":
            return None
        text = str(action or "")
        plan = _town_hall_home_plan_from_action(action)
        if not plan and not any(word in text for word in ("家", "自宅", "住居", "home", "house")):
            return None
        payload: dict[str, Any] = {}
        if plan:
            payload["cost"] = plan[0]
            payload["level"] = plan[1]
        return self._run_llm_action_tool(LlmToolName.HOME_PURCHASE, "player_choice", action, input_type, payload)

    def _apply_response_home_purchase_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "choice",
    ) -> dict[str, Any]:
        response = response if isinstance(response, dict) else {}
        active = self._active_facility_record()
        if not active or str(active.get("type") or "").lower() != "town_hall":
            return {"handled": False, "reason": "not_town_hall"}
        settlement = self._current_settlement_location()
        if settlement is None:
            return {"handled": False, "reason": "not_settlement"}
        if self._player_home_for_location(settlement.name):
            narration = f"{settlement.name}には、すでにあなたの家がある。"
            self._append_turn(action, narration, settlement.name, self._location_default_choices(settlement.name), input_type=input_type)
            self.save_game()
            return {"handled": True, "purchased": False, "reason": "already_has_home", "log_text": self.state.log_text(16)}
        cost = _safe_int((response or {}).get("cost") or (response or {}).get("price") or (response or {}).get("gold"), 0)
        level = _safe_int((response or {}).get("level") or (response or {}).get("home_level"), 0)
        plan = (cost, level) if cost in PLAYER_HOME_TOWN_HALL_PLANS and level > 0 else _town_hall_home_plan_from_action(action)
        if plan and plan[0] in PLAYER_HOME_TOWN_HALL_PLANS:
            plan = (plan[0], PLAYER_HOME_TOWN_HALL_PLANS[plan[0]])
        if not plan:
            choices = [f"{cost}Goldで家を建てる" for cost in sorted(PLAYER_HOME_TOWN_HALL_PLANS)]
            narration = "役場では、土地と小さな家の手続きを行える。500Gold、1000Gold、10000Goldの三つのプランが提示された。"
            self._append_turn(action, narration, settlement.name, _exploration_choices(choices), input_type=input_type)
            self.save_game()
            return {"handled": True, "purchased": False, "reason": "plan_selection", "log_text": self.state.log_text(16)}
        cost, level = plan
        if self.state.gold < cost:
            narration = f"役場職員は首を横に振った。{cost}Goldの支払いには所持金が足りない。"
            self._append_turn(action, narration, settlement.name, self._location_default_choices(settlement.name), input_type=input_type)
            self.save_game()
            return {
                "handled": True,
                "purchased": False,
                "reason": "not_enough_gold",
                "required_gold": cost,
                "current_gold": self.state.gold,
                "log_text": self.state.log_text(16),
            }
        gold_event = self._apply_gold_delta(-cost, source=source or "home_purchase", reason="家の購入", append_log=False)
        self._create_player_home(settlement.name, level, source="town_hall", parent_subnode_id=DEFAULT_SUBNODE_ID, cost=cost)
        narration = f"役場で{cost}Goldを支払い、{settlement.name}にあなたの家を用意した。家具レベルは{level}。"
        choices = [MOVE_CHOICE_LABEL, f"{PLAYER_HOME_NAME}へ移動", "周囲を見る"]
        self._append_turn(action, narration, settlement.name, _exploration_choices(choices), input_type=input_type)
        if gold_event.get("line"):
            self.state.display_log.append(str(gold_event["line"]))
        self.save_game()
        return {
            "handled": True,
            "purchased": True,
            "cost": cost,
            "level": level,
            "location": settlement.name,
            "gold_event": gold_event,
            "log_text": self.state.log_text(16),
        }

    def _apply_home_construction_entry(
        self,
        entry: Any,
        *,
        source: str,
        action: str = "",
        input_type: str = "free_action",
        preselected_item: dict[str, Any] | None = None,
        append_turn: bool = True,
    ) -> list[str]:
        if not isinstance(entry, dict):
            return []
        location_name = self.state.current_location or self.state.world_data.starting_location
        subnode_id = self._current_subnode_id(location_name) or DEFAULT_SUBNODE_ID
        item = dict(preselected_item or {})
        material_name = str(entry.get("material_name") or entry.get("item_name") or entry.get("material") or "").strip()
        if not item and material_name:
            for candidate in self._craft_item_candidates():
                candidate_item = dict(candidate["item"])
                if _loose_name_match(str(candidate_item.get("name") or ""), material_name):
                    candidate_item["_craft_source"] = candidate["source"]
                    candidate_item["_craft_source_uuid"] = str(candidate_item.get("item_uuid") or "")
                    item = candidate_item
                    break
        usable = _as_bool(entry.get("usable") or entry.get("allowed") or entry.get("can_use"))
        narration = str(entry.get("narration") or entry.get("message") or entry.get("reason") or "").strip()
        if not usable:
            if not narration:
                narration = "その素材は家の建築には向いていない。"
            if append_turn:
                self._append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            return []
        if not item:
            narration = "建築に使う素材が見つからない。"
            if append_turn:
                self._append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            return []
        if self._player_home_for_location(location_name):
            narration = "このロケーションには、すでにあなたの家がある。"
            if append_turn:
                self._append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            return []
        consume = entry.get("consume_item")
        if consume is None:
            consume = True
        removed: dict[str, Any] | None = None
        if _as_bool(consume):
            item_uuid = str(item.get("_craft_source_uuid") or item.get("item_uuid") or "").strip()
            item_source = str(item.get("_craft_source") or "player").strip()
            if item_source == "location":
                removed = self._remove_item_uuid_from_inventory(self._current_location_inventory(), item_uuid, source=source, reason="home_construction")
            else:
                removed = self._remove_player_item_by_uuid(item_uuid, source=source, reason="home_construction")
            if not removed:
                removed = self._remove_craft_ingredient_by_name(item, source=source)
            if not removed:
                narration = "建築に使う素材を消費できなかった。"
                if append_turn:
                    self._append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
                return []

        progress_key = f"{location_name}::{subnode_id}"
        construction = self._player_home_construction()
        record = construction.setdefault(
            progress_key,
            {
                "location": location_name,
                "subnode_id": subnode_id,
                "progress": 0,
                "furniture_level": 0,
                "materials": [],
            },
        )
        gain = max(0, min(3, _safe_int(entry.get("furniture_level_gain"), 0)))
        old_progress = max(0, min(100, _safe_int(record.get("progress"), 0)))
        new_progress = min(100, old_progress + PLAYER_HOME_BUILD_PROGRESS_STEP)
        old_level = max(0, min(PLAYER_HOME_MAX_LEVEL, _safe_int(record.get("furniture_level"), 0)))
        new_level = min(PLAYER_HOME_MAX_LEVEL, old_level + gain)
        record["progress"] = new_progress
        record["furniture_level"] = new_level
        material_label = item_label(removed or item)
        record.setdefault("materials", []).append(
            {"name": material_label, "gain": gain, "source": source, "day": self.state.day}
        )
        if not narration:
            narration = f"{material_label}を使って、家の建築を少し進めた。"
        lines = [f"> [建築] {location_name}/{subnode_id}: {old_progress}% -> {new_progress}% / 家具Lv {old_level} -> {new_level}"]
        if removed:
            lines.append(f"> [消費] {material_label}")
            self._sync_player_inventory()
        if new_progress >= 100:
            final_level = max(1, new_level)
            self._create_player_home(location_name, final_level, source="field_construction", parent_subnode_id=subnode_id)
            construction.pop(progress_key, None)
            narration = "\n".join([narration, f"建築進捗が100%に達し、隣接地点にあなたの家が完成した。家具レベルは{final_level}。"])
            choices = _exploration_choices([f"{PLAYER_HOME_NAME}へ移動", "周囲を見る"])
        else:
            narration = "\n".join([narration, f"建築進捗は{new_progress}%になった。"])
            choices = self._location_default_choices(location_name)
        if append_turn:
            self._append_turn(action or "家を建てる", narration, location_name, choices, input_type=input_type)
        self.state.world_data.extra.setdefault("player_home_events", []).append(
            {
                "type": "construction",
                "location": location_name,
                "subnode_id": subnode_id,
                "progress": new_progress,
                "furniture_level": new_level,
                "material": material_label,
                "source": source,
            }
        )
        return lines

    def _apply_response_craft_tool(
        self,
        response: Any,
        source: str,
        *,
        default_action: str = "",
        input_type: str = "free_action",
    ) -> dict[str, Any]:
        payload = self._response_craft_tool_payload(response)
        event: dict[str, Any] = {"source": source, "lines": []}
        if not payload:
            event["skipped_reason"] = "empty_craft_payload"
            return event

        refs = self._craft_tool_item_refs(payload)
        items, missing = self._craft_ingredients_from_tool_refs(refs)
        event["requested_items"] = [self._craft_tool_ref_label(ref) for ref in refs]
        if missing:
            line = f"> [クラフト] 指定素材が見つかりません: {', '.join(missing)}"
            event.update({"failed": True, "missing_items": missing, "lines": [line]})
            self.save_game()
            return event

        craft_intent = _normalise_craft_intent(
            payload.get("craft_type")
            or payload.get("craft_intent")
            or payload.get("category")
            or payload.get("kind")
            or payload.get("type")
            or "auto"
        )
        content = str(
            payload.get("content")
            or payload.get("request")
            or payload.get("result")
            or payload.get("target")
            or payload.get("make")
            or ""
        ).strip()
        action = content or str(default_action or "").strip() or "craft"
        event.update(
            self._execute_craft_tool_action(
                action,
                input_type,
                items,
                source=source,
                craft_intent=craft_intent,
            )
        )
        event["tool_arguments"] = _drop_empty(
            {
                "craft_type": craft_intent,
                "content": content,
                "consume_items": event.get("requested_items"),
            }
        )
        self.save_game()
        return event

    def _response_craft_tool_payload(self, response: Any) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {}
        for key in ("craft", "crafting", "craft_item"):
            value = response.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        return dict(item)
                continue
            if isinstance(value, dict):
                return dict(value)
        if any(
            key in response
            for key in (
                "consume_items",
                "consumed_items",
                "ingredients",
                "items",
                "materials",
                "craft_type",
                "craft_intent",
                "content",
                "request",
            )
        ):
            return dict(response)
        return {}

    def _craft_tool_item_refs(self, payload: dict[str, Any]) -> list[Any]:
        refs: list[Any] = []
        for key in ("consume_items", "consumed_items", "ingredients", "items", "materials", "item_names", "consume_item"):
            value = payload.get(key)
            if value in (None, "", [], {}):
                continue
            raw_items = _as_list(value)
            if isinstance(value, str) and ("," in value or "、" in value):
                raw_items = [part.strip() for part in re.split(r"[,、]", value) if part.strip()]
            for raw in raw_items:
                quantity = 1
                if isinstance(raw, dict):
                    quantity = max(1, min(20, _safe_int(raw.get("quantity"), 1)))
                for _ in range(quantity):
                    refs.append(raw)
        return refs

    def _craft_ingredients_from_tool_refs(self, refs: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
        candidates = self._craft_item_candidates()
        used_uuids: set[str] = set()
        items: list[dict[str, Any]] = []
        missing: list[str] = []
        for ref in refs:
            label = self._craft_tool_ref_label(ref)
            match = self._match_craft_tool_candidate(ref, candidates, used_uuids)
            if not match:
                if label:
                    missing.append(label)
                continue
            item = dict(match["item"])
            item["_craft_source"] = match["source"]
            item["_craft_source_uuid"] = str(item.get("item_uuid") or "")
            item_uuid = str(item.get("item_uuid") or "")
            if item_uuid:
                used_uuids.add(item_uuid)
            items.append(item)
        return items, missing

    def _match_craft_tool_candidate(
        self,
        ref: Any,
        candidates: list[dict[str, Any]],
        used_uuids: set[str],
    ) -> dict[str, Any] | None:
        ref_uuid = ""
        ref_source = ""
        if isinstance(ref, dict):
            ref_uuid = str(ref.get("item_uuid") or ref.get("uuid") or ref.get("id") or "").strip()
            ref_source = str(ref.get("source") or ref.get("inventory") or "").strip()
        if ref_uuid:
            for candidate in candidates:
                item = candidate.get("item") if isinstance(candidate, dict) else {}
                item = item if isinstance(item, dict) else {}
                item_uuid = str(item.get("item_uuid") or "")
                if item_uuid in used_uuids:
                    continue
                if item_uuid == ref_uuid and (not ref_source or str(candidate.get("source") or "") == ref_source):
                    return candidate

        label = self._craft_tool_ref_label(ref)
        if not label:
            return None
        return _match_craft_candidate(label, candidates, used_uuids)

    def _craft_tool_ref_label(self, ref: Any) -> str:
        if isinstance(ref, dict):
            for key in ("name", "item_name", "label", "item_uuid", "uuid", "id"):
                value = str(ref.get(key) or "").strip()
                if value:
                    return value
            return ""
        return str(ref or "").strip()

    def _execute_craft_tool_action(
        self,
        action: str,
        input_type: str,
        ingredients: list[dict[str, Any]],
        *,
        source: str,
        craft_intent: str = "auto",
    ) -> dict[str, Any]:
        items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
        event: dict[str, Any] = {"source": source, "lines": []}
        if len(items) < 2:
            line = "> [クラフト] クラフトには素材が2つ以上必要です。"
            event.update({"failed": True, "lines": [line]})
            return event
        if not self._craft_ingredients_available(items):
            line = "> [クラフト] 指定された素材は、所持品や現在地のアイテムから見つかりません。"
            event.update({"failed": True, "lines": [line]})
            return event
        if not self._craft_result_can_fit_after_consumption(items):
            line = self._inventory_full_line()
            event.update({"failed": True, "lines": [line]})
            return event

        craft_intent = _normalise_craft_intent(craft_intent)
        craft_plan = self._craft_plan_for_items(items, craft_intent)
        craft_roll = self._roll_craft_check_for_plan(craft_plan)
        ingredient_labels = [item_label(item) for item in items]
        event.update(
            {
                "ingredients": ingredient_labels,
                "roll": craft_roll,
                "craft_intent": _craft_intent_payload(craft_intent),
                "craft_plan": craft_plan.to_dict(),
            }
        )

        if craft_roll.get("critical_failure"):
            removed = self._consume_craft_ingredients(items, source=source)
            self._append_action_roll_log(craft_roll)
            line = "> [クラフト] 強制失敗: 使用した素材はすべて失われました。"
            event.update(
                {
                    "removed": removed,
                    "failed": True,
                    "critical_failure": True,
                    "consumed": bool(removed),
                    "lines": [line],
                }
            )
            self.state.world_data.extra.setdefault("craft_events", []).append(dict(event))
            self._sync_player_inventory()
            return event

        response: dict[str, Any] = {}
        if craft_plan.kind != "equipment_upgrade" or craft_roll.get("success"):
            response = self._craft_item_generator(action, items, craft_roll, craft_plan)
        result = build_craft_result(response, items, craft_roll, craft_plan, player_level=self._player_level())
        if not result:
            removed = self._consume_craft_ingredients(items, source=source)
            self._append_action_roll_log(craft_roll)
            line = "> [クラフト] クラフトは失敗し、素材は失われました。"
            event.update(
                {
                    "removed": removed,
                    "failed": True,
                    "consumed": bool(removed),
                    "response": _strip_response_metadata(response),
                    "lines": [line],
                }
            )
            self.state.world_data.extra.setdefault("craft_events", []).append(dict(event))
            self._sync_player_inventory()
            return event

        removed = self._consume_craft_ingredients(items, source=source)
        added = self._add_player_item_stack(result, source="craft")
        added_to_location: dict[str, Any] | None = None
        lines: list[str] = []
        if added:
            lines.append(f"> [クラフト] {item_label(added)}")
        else:
            location_inventory = self._current_location_inventory()
            added_to_location = add_item_stack(location_inventory, result, source="craft_overflow")
            if added_to_location:
                lines.append(f"> [クラフト] {item_label(added_to_location)}")
                lines.append("> [所持品] 所持品に空きがないため、完成品は現在地に置かれました。")
            else:
                lines.append(self._inventory_full_line(result))

        self._append_action_roll_log(craft_roll)
        event.update(
            {
                "removed": removed,
                "result": normalise_item(added or added_to_location or result, source="craft"),
                "response": _strip_response_metadata(response),
                "crafted": bool(added or added_to_location),
                "consumed": bool(removed),
                "lines": lines,
            }
        )
        self.state.world_data.extra.setdefault("craft_events", []).append(dict(event))
        self._sync_player_inventory()
        return event

    def _resolve_craft_with_ingredients(
        self,
        action: str,
        input_type: str,
        ingredients: list[dict[str, Any]],
        *,
        source: str,
        craft_intent: str = "auto",
    ) -> str:
        items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
        if len(items) < 2:
            message = "クラフトには素材が2つ以上必要です。"
            self._append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if not self._craft_ingredients_available(items):
            message = "指定された素材は、すでに所持品や周囲から見つかりません。"
            self._append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if not self._craft_result_can_fit_after_consumption(items):
            message = self._inventory_full_line()
            self._append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)

        craft_intent = _normalise_craft_intent(craft_intent)
        craft_plan = self._craft_plan_for_items(items, craft_intent)
        craft_roll = self._roll_craft_check_for_plan(craft_plan)
        ingredient_labels = [item_label(item) for item in items]
        if craft_roll.get("critical_failure"):
            removed = self._consume_craft_ingredients(items, source=source)
            narration = "クラフトは強制失敗し、使用した素材はすべて失われました。"
            self._append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
            self._append_action_roll_log(craft_roll)
            self.state.world_data.extra.setdefault("craft_events", []).append(
                {
                    "source": source,
                    "ingredients": ingredient_labels,
                    "removed": removed,
                    "roll": craft_roll,
                    "craft_plan": craft_plan.to_dict(),
                    "failed": True,
                    "critical_failure": True,
                }
            )
            self._sync_player_inventory()
            self.save_game()
            return self.state.log_text(16)

        response: dict[str, Any] = {}
        if craft_plan.kind != "equipment_upgrade" or craft_roll.get("success"):
            response = self._craft_item_generator(action, items, craft_roll, craft_plan)
        result = build_craft_result(response, items, craft_roll, craft_plan, player_level=self._player_level())
        if not result:
            removed = self._consume_craft_ingredients(items, source=source)
            narration = "クラフトは失敗し、素材は失われました。"
            self._append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
            self._append_action_roll_log(craft_roll)
            self.state.world_data.extra.setdefault("craft_events", []).append(
                {
                    "source": source,
                    "ingredients": ingredient_labels,
                    "removed": removed,
                    "roll": craft_roll,
                    "craft_plan": craft_plan.to_dict(),
                    "failed": True,
                }
            )
            self._sync_player_inventory()
            self.save_game()
            return self.state.log_text(16)
        removed = self._consume_craft_ingredients(items, source=source)
        added = self._add_player_item_stack(result, source="craft")
        narration = str(response.get("narration") or response.get("text") or "").strip()
        if not narration:
            if craft_plan.kind == "equipment_upgrade" and not craft_roll.get("success"):
                narration = f"{craft_plan.target_item_name or '強化対象'}の強化は失敗した。強化対象はそのまま戻り、素材は失われた。"
            else:
                narration = "素材を組み合わせ、新しいアイテムを作り上げました。"
        if not added:
            location_inventory = self._current_location_inventory()
            added_to_location = add_item_stack(location_inventory, result, source="craft_overflow")
            if added_to_location:
                narration = "\n".join([narration, "所持品に空きがないため、完成品はその場に置かれました。"])
        self._append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
        self._append_action_roll_log(craft_roll)
        if added:
            self.state.display_log.append(f"> [クラフト] {item_label(added)}")
        else:
            self.state.display_log.append(self._inventory_full_line(result))
        event = {
            "source": source,
            "ingredients": ingredient_labels,
            "removed": removed,
            "roll": craft_roll,
            "craft_intent": _craft_intent_payload(craft_intent),
            "craft_plan": craft_plan.to_dict(),
            "result": normalise_item(added or result, source="craft"),
            "response": _strip_response_metadata(response),
        }
        self.state.world_data.extra.setdefault("craft_events", []).append(event)
        self._sync_player_inventory()
        self.save_game()
        return self.state.log_text(16)

    def _craft_item_generator(
        self,
        action: str,
        ingredients: list[dict[str, Any]],
        craft_roll: dict[str, Any],
        craft_plan: CraftPlan,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False, include_monsters=False, include_quests=True))
        location = self.state.world_data.locations.get(self.state.current_location)
        location_payload = _ai_json(_location_ai_context(location)) if location else "{}"
        ingredients_payload = _ai_json([_compact_item_for_ai(item) for item in ingredients])
        roll_payload = json.dumps(craft_roll, ensure_ascii=False)
        craft_plan_payload = _ai_json(craft_plan.to_dict())
        categories = ", ".join(ITEM_CATEGORY_IDS)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのクラフト結果生成AIです。"
                    "素材、プレイヤーの意図、世界観、ゲーム側のクラフト計画を尊重し、JSONだけを返してください。"
                    "戻り値は narration と item を中心にします。item は name, category, description を返してください。"
                    "category は次のIDから選んでください: "
                    f"{categories}。"
                    "レアリティ、価格、攻撃力、防御力、効果量、空腹回復量、power はゲーム側が決定します。"
                    "武具強化では item に name と description だけを返し、元装備のカテゴリや能力値を変更しないでください。"
                    "消耗品と料理では、必要であれば use_effect または effects で効果種別だけを示してください。効果量は書かないでください。"
                    "存在しない素材を勝手に足さず、素材から自然に作れる物にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"現在地データ: {location_payload}\n"
                    f"プレイヤーのクラフト意図: {action}\n"
                    f"craft_plan: {craft_plan_payload}\n"
                    f"素材: {ingredients_payload}\n"
                    f"game_side_craft_roll: {roll_payload}\n"
                    "このクラフトで完成するアイテムを1つ生成してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "The opening scene may happen inside an inn, plaza, guild, or another facility, but location should "
                    "remain the settlement/town name when possible. If you mention a sub-place, treat it as a facility "
                    "or subnode inside the starting settlement, not as a separate world-map location."
                ),
            }
        )
        return self._chat_json(
            "craft_item_generator",
            messages,
            max_tokens=650,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _current_location_inventory(self) -> list[dict[str, Any]]:
        return self._location_inventory(self.state.current_location)

    def _location_inventory(self, location_name: str) -> list[dict[str, Any]]:
        location = self.state.world_data.ensure_location(location_name or self.state.current_location)
        inventory = location.extra.setdefault("inventory", [])
        if not isinstance(inventory, list):
            inventory = []
            location.extra["inventory"] = inventory
        for index, raw in enumerate(list(inventory)):
            if isinstance(raw, dict):
                inventory[index] = normalise_item(raw, source="location")
        return inventory

    def _craft_ingredients_from_action(self, action: str) -> tuple[list[dict[str, Any]], list[str]]:
        phrases = _craft_material_phrases(action)
        candidates = self._craft_item_candidates()
        used_uuids: set[str] = set()
        items: list[dict[str, Any]] = []
        missing: list[str] = []
        for phrase in phrases:
            match = _match_craft_candidate(phrase, candidates, used_uuids)
            if not match:
                missing.append(phrase)
                continue
            item = dict(match["item"])
            item["_craft_source"] = match["source"]
            item["_craft_source_uuid"] = str(item.get("item_uuid") or "")
            used_uuids.add(str(item.get("item_uuid") or ""))
            items.append(item)
        if not phrases:
            for candidate in candidates:
                name = str(candidate["item"].get("name") or "")
                uuid = str(candidate["item"].get("item_uuid") or "")
                if name and uuid not in used_uuids and name in action:
                    item = dict(candidate["item"])
                    item["_craft_source"] = candidate["source"]
                    item["_craft_source_uuid"] = uuid
                    used_uuids.add(uuid)
                    items.append(item)
        return items, missing

    def _craft_item_candidates(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for source, inventory in (("player", self._player_inventory()), ("location", self._current_location_inventory())):
            for index, raw in enumerate(list(inventory)):
                if not isinstance(raw, dict):
                    continue
                item = normalise_item(raw, source=source)
                inventory[index] = item
                quantity = max(1, _safe_int(item.get("quantity"), 1))
                uuids = [str(value) for value in _as_list(item.get("item_uuids"))] or [str(item.get("item_uuid") or "")]
                for offset in range(quantity):
                    single = dict(item)
                    item_uuid = uuids[offset] if offset < len(uuids) else str(item.get("item_uuid") or "")
                    single["quantity"] = 1
                    single["item_uuids"] = [item_uuid] if item_uuid else []
                    single["item_uuid"] = item_uuid
                    candidates.append({"source": source, "index": index, "item": single})
        candidates.sort(key=lambda entry: len(str(entry["item"].get("name") or "")), reverse=True)
        return candidates

    def _craft_tool_ai_candidates(self, limit: int = 24) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for candidate in self._craft_item_candidates()[: max(0, limit)]:
            item = candidate.get("item") if isinstance(candidate, dict) else {}
            if not isinstance(item, dict):
                continue
            data = _compact_item_for_ai(item)
            data["item_uuid"] = str(item.get("item_uuid") or "")
            data["source"] = str(candidate.get("source") or "")
            result.append(_drop_empty(data))
        return result

    def _craft_ingredients_available(self, ingredients: list[dict[str, Any]]) -> bool:
        candidates = self._craft_item_candidates()
        used: set[str] = set()
        for ingredient in ingredients:
            uuid = str(ingredient.get("_craft_source_uuid") or ingredient.get("item_uuid") or "").strip()
            source = str(ingredient.get("_craft_source") or "").strip()
            found = False
            for candidate in candidates:
                item = candidate["item"]
                item_uuid = str(item.get("item_uuid") or "")
                if item_uuid in used:
                    continue
                if uuid and item_uuid == uuid and (not source or candidate["source"] == source):
                    used.add(item_uuid)
                    found = True
                    break
                if not uuid and str(item.get("name") or "") == str(ingredient.get("name") or ""):
                    used.add(item_uuid)
                    found = True
                    break
            if not found:
                return False
        return True

    def _craft_result_can_fit_after_consumption(self, ingredients: list[dict[str, Any]]) -> bool:
        if self.can_add_player_item({"name": "craft probe", "category": "junk", "quantity": 1}, source="craft_probe"):
            return True
        inventory = self._player_inventory()
        selected_by_index: dict[int, int] = {}
        for ingredient in ingredients:
            if str(ingredient.get("_craft_source") or "player") != "player":
                continue
            uuid = str(ingredient.get("_craft_source_uuid") or ingredient.get("item_uuid") or "")
            for index, raw in enumerate(inventory):
                item = normalise_item(raw, source="player")
                if uuid and uuid in [str(value) for value in _as_list(item.get("item_uuids"))]:
                    selected_by_index[index] = selected_by_index.get(index, 0) + 1
                    break
        for index, count in selected_by_index.items():
            if index < len(inventory):
                item = normalise_item(inventory[index], source="player")
                if count >= max(1, _safe_int(item.get("quantity"), 1)):
                    return True
        return False

    def _consume_craft_ingredients(self, ingredients: list[dict[str, Any]], *, source: str) -> list[dict[str, Any]]:
        removed: list[dict[str, Any]] = []
        for ingredient in ingredients:
            item_uuid = str(ingredient.get("_craft_source_uuid") or ingredient.get("item_uuid") or "").strip()
            item_source = str(ingredient.get("_craft_source") or "player")
            if item_source == "location":
                item = self._remove_item_uuid_from_inventory(self._current_location_inventory(), item_uuid, source=source, reason="craft")
            else:
                item = self._remove_player_item_by_uuid(item_uuid, source=source, reason="craft")
            if not item:
                item = self._remove_craft_ingredient_by_name(ingredient, source=source)
            if item:
                removed.append(item)
        return removed

    def _remove_craft_ingredient_by_name(self, ingredient: dict[str, Any], *, source: str) -> dict[str, Any] | None:
        target_name = str(ingredient.get("name") or "").strip()
        item_source = str(ingredient.get("_craft_source") or "player")
        inventory = self._current_location_inventory() if item_source == "location" else self._player_inventory()
        for index, raw in enumerate(list(inventory)):
            item = normalise_item(raw, source=item_source)
            if str(item.get("name") or "") != target_name:
                continue
            if item_source == "player" and item.get("equipped"):
                self._unequip_player_slot(self._equipment_slot_for_item(item), source=source, reason="craft")
            removed = take_item_stack(inventory, index, 1)
            if removed:
                removed["loss_reason"] = "craft"
                removed["source"] = source
            return removed
        return None

    def _remove_item_uuid_from_inventory(
        self,
        inventory: list[dict[str, Any]],
        item_uuid: str,
        *,
        source: str,
        reason: str = "",
    ) -> dict[str, Any] | None:
        if not item_uuid:
            return None
        for index, raw in enumerate(list(inventory)):
            item = normalise_item(raw, source=source)
            uuids = [str(value) for value in _as_list(item.get("item_uuids"))]
            if item_uuid not in uuids:
                continue
            removed = dict(item)
            removed["quantity"] = 1
            removed["item_uuids"] = [item_uuid]
            removed["item_uuid"] = item_uuid
            remaining = [value for value in uuids if value != item_uuid]
            if remaining:
                item["quantity"] = len(remaining)
                item["item_uuids"] = remaining
                item["item_uuid"] = remaining[0]
                inventory[index] = item
            else:
                inventory.pop(index)
            removed["source"] = source
            removed["loss_reason"] = reason
            return removed
        return None

    def _apply_response_item_losses(self, response: Any, source: str) -> list[dict[str, Any]]:
        if not isinstance(response, dict):
            return []
        removed: list[dict[str, Any]] = []
        loss_keys = (
            "item_remove",
            "item_removes",
            "remove_item",
            "remove_items",
            "removed_items",
            "lost_items",
            "lose_items",
            "consume_items",
            "consumed_items",
            "stolen_items",
            "taken_items",
            "give_items",
            "given_items",
            "confiscated_items",
        )
        for key in loss_keys:
            for value in _as_list(response.get(key)):
                item = self._remove_player_item_reference(value, source=source, reason=key)
                if item:
                    item["loss_reason"] = key
                    removed.append(item)
        if removed:
            self._sync_player_inventory()
            self.state.world_data.extra.setdefault("lost_items", []).append(
                {
                    "source": source,
                    "items": removed,
                }
            )
        return removed

    def _remove_player_item_reference(self, value: Any, *, source: str, reason: str = "") -> dict[str, Any] | None:
        value = _item_effect_reference(value)
        inventory = self._player_inventory()
        references = _as_list(value.get("item_uuids")) if isinstance(value, dict) else []
        if references:
            removed_items: list[dict[str, Any]] = []
            for item_uuid in references:
                removed = self._remove_player_item_by_uuid(str(item_uuid), source=source, reason=reason)
                if removed:
                    removed_items.append(removed)
            if removed_items:
                first = dict(removed_items[0])
                first["quantity"] = len(removed_items)
                first["item_uuids"] = [uuid for item in removed_items for uuid in _as_list(item.get("item_uuids"))]
                first["item_uuid"] = first["item_uuids"][0]
                return first
        index = self._find_inventory_item_index(value)
        if index is None or index >= len(inventory):
            return None
        item = normalise_item(inventory[index])
        if item.get("equipped"):
            self._unequip_player_slot(self._equipment_slot_for_item(item), source=source, reason=reason)
        quantity = 1
        if isinstance(value, dict):
            quantity = _safe_int(value.get("quantity", value.get("count", value.get("amount", 1))), 1)
            item_uuid = str(value.get("item_uuid") or value.get("uuid") or "").strip()
            if item_uuid:
                return self._remove_player_item_by_uuid(item_uuid, source=source, reason=reason)
        removed = take_item_stack(inventory, index, quantity)
        if removed:
            removed["source"] = source
            removed["loss_reason"] = reason
        return removed

    def _remove_player_item_by_uuid(self, item_uuid: str, *, source: str, reason: str = "") -> dict[str, Any] | None:
        if not item_uuid:
            return None
        inventory = self._player_inventory()
        for index, raw in enumerate(list(inventory)):
            item = normalise_item(raw)
            uuids = [str(value) for value in item.get("item_uuids", [])]
            if item_uuid not in uuids:
                continue
            if item.get("equipped"):
                self._unequip_player_slot(self._equipment_slot_for_item(item), source=source, reason=reason)
            removed = dict(item)
            removed["quantity"] = 1
            removed["item_uuids"] = [item_uuid]
            removed["item_uuid"] = item_uuid
            remaining = [value for value in uuids if value != item_uuid]
            if remaining:
                item["quantity"] = len(remaining)
                item["item_uuids"] = remaining
                item["item_uuid"] = remaining[0]
                inventory[index] = item
            else:
                inventory.pop(index)
            removed["source"] = source
            removed["loss_reason"] = reason
            return removed
        return None

    def _equip_player_item_reference(self, value: Any, *, source: str, reason: str = "") -> dict[str, Any]:
        index = self._find_inventory_item_index(value)
        if index is None and isinstance(value, dict):
            added = self._add_player_item_stack(value, source=source)
            if not added:
                self.state.display_log.append(self._inventory_full_line(value))
                return {"changed": False, "line": ""}
            index = self._find_inventory_item_index(added)
        if index is None:
            return {"changed": False, "line": ""}
        return self._equip_player_inventory_index(index, source=source, reason=reason)

    def _unequip_player_reference(self, value: Any, *, source: str, reason: str = "") -> dict[str, Any]:
        if isinstance(value, dict):
            slot = str(value.get("slot") or value.get("equipment_slot") or "").strip()
            category_slot = equipment_slot_for_category(str(value.get("category") or value.get("type") or value.get("kind") or ""))
            if category_slot:
                slot = category_slot
            if slot in EQUIPMENT_SLOT_LABELS.values():
                slot = next((key for key, label in EQUIPMENT_SLOT_LABELS.items() if label == slot), slot)
            if slot:
                return self._unequip_player_slot(slot, source=source, reason=reason)
            value = value.get("item") or value.get("name") or value.get("item_name") or value.get("target") or value
        text = str(value or "").strip()
        if text in EQUIPMENT_SLOTS:
            return self._unequip_player_slot(text, source=source, reason=reason)
        for slot, item in self._player_equipment().items():
            if isinstance(item, dict) and text and text in str(item.get("name") or ""):
                return self._unequip_player_slot(slot, source=source, reason=reason)
        return {"changed": False, "line": ""}

    def _find_inventory_item_index(self, value: Any) -> int | None:
        inventory = self._player_inventory()
        if isinstance(value, dict):
            instance_id = str(value.get("instance_id") or "")
            item_uuid = str(value.get("item_uuid") or value.get("uuid") or "").strip()
            name = str(value.get("name") or value.get("item_name") or value.get("title") or "").strip()
            category = str(value.get("category") or value.get("type") or value.get("kind") or "").strip()
        else:
            instance_id = ""
            item_uuid = ""
            name = str(value or "").strip()
            category = ""
        for index, item in enumerate(inventory):
            if not isinstance(item, dict):
                continue
            if instance_id and str(item.get("instance_id") or "") == instance_id:
                return index
            if item_uuid and item_uuid in [str(uuid) for uuid in _as_list(item.get("item_uuids"))]:
                return index
            item_name = str(item.get("name") or "")
            if name and (name == item_name or name in item_name or item_name in name):
                if not category or equipment_slot_for_category(category) == equipment_slot_for_category(str(item.get("category") or "")):
                    return index
        return None

    def apply_gold_delta(
        self,
        delta: Any,
        *,
        source: str = "event",
        reason: str = "",
        save_game: bool = True,
    ) -> dict[str, Any]:
        event = self._apply_gold_delta(delta, source=source, reason=reason, append_log=True)
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _apply_response_game_over_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        payload = self._response_game_over_payload(response)
        if not payload or self._is_game_over():
            return []
        reason = str(
            payload.get("reason")
            or payload.get("game_over_reason")
            or (response.get("game_over_reason") if isinstance(response, dict) else "")
            or payload.get("description")
            or "LLM judged the outcome as game over."
        ).strip()
        narration = str(
            payload.get("narration")
            or payload.get("game_over_narration")
            or (response.get("game_over_narration") if isinstance(response, dict) else "")
            or (response.get("narration") if isinstance(response, dict) else "")
            or ""
        ).strip()
        event = self._set_game_over(source=source, reason=reason, narration=narration, encounter=encounter)
        return [str(event["line"])] if event.get("line") else []

    def _response_game_over_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            for item in payload:
                result = self._response_game_over_payload(item)
                if result:
                    return result
            return {}
        if not isinstance(payload, dict):
            return {}
        trigger_keys = {
            "game_over",
            "force_game_over",
            "fatal_outcome",
            "bad_end",
            "bad_ending",
            "player_dead",
            "player_death",
        }
        for key in trigger_keys:
            if key not in payload:
                continue
            value = payload.get(key)
            if isinstance(value, dict):
                enabled = value.get("enabled", value.get("value", value.get("game_over", True)))
                if _as_bool(enabled):
                    result = dict(value)
                    result.setdefault("reason", payload.get("game_over_reason") or payload.get("reason") or key)
                    result.setdefault("narration", payload.get("game_over_narration") or payload.get("narration") or "")
                    return result
            elif _as_bool(value):
                return {
                    "reason": payload.get("game_over_reason") or payload.get("reason") or key,
                    "narration": payload.get("game_over_narration") or payload.get("narration") or "",
                }
        for key in ("outcome", "result", "ending", "state_update", "world_state", "player_state"):
            child = payload.get(key)
            if isinstance(child, (dict, list)):
                result = self._response_game_over_payload(child)
                if result:
                    return result
        return {}

    def _apply_equipment_regen_effects(
        self,
        source: str,
        *,
        hours: int = 1,
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        summary = self.player_equipment_summary()
        lines: list[str] = []
        multiplier = max(1, int(hours or 1))
        hp_regen = _safe_int(summary.get("hp_regen"), 0)
        sp_regen = _safe_int(summary.get("sp_regen"), 0)
        if hp_regen:
            event = self._apply_player_hp_delta(
                hp_regen * multiplier,
                source=f"{source}:equipment",
                reason="equipment regen",
                encounter=encounter,
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        if sp_regen:
            event = self._apply_player_sp_delta(
                sp_regen * multiplier,
                source=f"{source}:equipment",
                reason="equipment regen",
                encounter=encounter,
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        return lines

    def _apply_response_gold_effects(self, response: dict[str, Any], source: str) -> list[str]:
        if not isinstance(response, dict):
            return []
        delta = self._response_gold_delta(response)
        if not delta:
            return []
        event = self._apply_gold_delta(delta, source=source, reason=self._response_gold_reason(response), append_log=False)
        return [str(event["line"])] if event.get("line") else []

    def _apply_gold_delta(
        self,
        delta: Any,
        *,
        source: str,
        reason: str = "",
        append_log: bool = False,
    ) -> dict[str, Any]:
        requested_delta = self._hp_number(delta, 0)
        if requested_delta == 0:
            return {"changed": False, "requested_delta": 0}
        old_gold = max(0, int(self.state.gold or 0))
        new_gold = max(0, old_gold + requested_delta)
        actual_delta = new_gold - old_gold
        if actual_delta == 0:
            return {
                "changed": False,
                "requested_delta": requested_delta,
                "old_gold": old_gold,
                "new_gold": new_gold,
            }
        self.state.gold = new_gold
        self._sync_player_inventory()
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        reason_text = f" {reason}" if reason else ""
        line = f"> [Gold] {old_gold}G -> {new_gold}G ({sign}G){reason_text}"
        event = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "day": self.state.day,
            "requested_delta": requested_delta,
            "actual_delta": actual_delta,
            "old_gold": old_gold,
            "new_gold": new_gold,
            "line": line,
            "changed": True,
        }
        self.state.world_data.extra.setdefault("gold_events", []).append(dict(event))
        if append_log:
            self.state.display_log.append(line)
        return event

    def _response_gold_delta(self, payload: Any) -> int:
        if isinstance(payload, list):
            return sum(self._response_gold_delta(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        total = 0
        effect_type = str(payload.get("type") or payload.get("kind") or payload.get("name") or "").strip().lower()
        value = self._gold_number(
            payload.get("value", payload.get("amount", payload.get("gold", payload.get("money", payload.get("coins", 0))))),
        )
        if effect_type in {"gain_gold", "receive_gold", "reward_gold", "earn_gold", "payment_received", "income"}:
            total += abs(value)
        elif effect_type in {"pay_gold", "spend_gold", "lose_gold", "cost_gold", "fee", "payment", "expense"}:
            total -= abs(value)

        signed_keys = {"gold_delta", "player_gold_delta", "money_delta", "coin_delta", "coins_delta"}
        positive_keys = {"receive_gold", "received_gold", "gain_gold", "gained_gold", "earn_gold", "earned_gold", "income_gold"}
        negative_keys = {
            "pay_gold",
            "paid_gold",
            "spend_gold",
            "spent_gold",
            "cost_gold",
            "price_gold",
            "fee_gold",
            "lose_gold",
            "lost_gold",
            "remove_gold",
        }
        negative_object_keys = {"payment", "cost", "price", "fee"}
        nested_keys = {"gold_effect", "gold_effects", "money_effect", "money_effects", "economy_effects"}
        for key, child_value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in signed_keys:
                total += self._gold_number(child_value)
            elif key_text in positive_keys:
                total += abs(self._gold_number(child_value))
            elif key_text in negative_keys:
                total -= abs(self._gold_number(child_value))
            elif key_text in negative_object_keys:
                nested = self._response_gold_delta(child_value)
                total += nested if nested else -abs(self._gold_number(child_value))
            elif key_text in nested_keys:
                total += self._response_gold_delta(child_value)
        return total

    def _gold_number(self, value: Any) -> int:
        if isinstance(value, list):
            return sum(self._gold_number(item) for item in value)
        if isinstance(value, dict):
            for key in ("amount", "value", "gold", "money", "coins", "price", "cost", "fee"):
                if key in value:
                    return self._gold_number(value.get(key))
            return sum(self._gold_number(item) for item in value.values())
        return self._hp_number(value, 0)

    def _response_gold_reason(self, response: dict[str, Any]) -> str:
        reason = response.get("gold_reason") or response.get("payment_reason") or response.get("reason") or response.get("event")
        if isinstance(reason, (dict, list)):
            return ""
        return _short_text(str(reason or "").strip(), 40)

    def current_time_label(self) -> str:
        return self._world_time_label(self._world_time_total_hours())

    def advance_time(
        self,
        hours: Any,
        *,
        source: str = "event",
        reason: str = "",
        save_game: bool = True,
    ) -> dict[str, Any]:
        event = self._advance_world_time(hours, source=source, reason=reason, append_log=True)
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _apply_response_time_effects(self, response: dict[str, Any], source: str) -> list[str]:
        if not isinstance(response, dict):
            return []
        hours = self._response_time_delta_hours(response)
        if not hours:
            return []
        event = self._advance_world_time(hours, source=source, reason=self._response_time_reason(response), append_log=False)
        lines = [str(event["line"])] if event.get("line") else []
        lines.extend(str(item) for item in event.get("companion_lines", []) if item)
        return lines

    def _advance_world_time(
        self,
        hours: Any,
        *,
        source: str,
        reason: str = "",
        append_log: bool = False,
    ) -> dict[str, Any]:
        requested_hours = max(0, self._hp_number(hours, 0))
        if requested_hours <= 0:
            return {"changed": False, "requested_hours": 0}
        old_hours = self._world_time_total_hours()
        old_label = self._world_time_label(old_hours)
        new_hours = old_hours + requested_hours
        self._set_world_time_total_hours(new_hours)
        new_label = self._world_time_label(new_hours)
        companion_lines = self._resolve_pending_companion_returns(source=source)
        hunger_event = self._apply_player_hunger_delta(
            -requested_hours * PLAYER_HUNGER_PER_HOUR,
            source="time",
            reason=reason or source,
        )
        if hunger_event.get("line"):
            companion_lines.append(str(hunger_event["line"]))
        companion_lines.extend(
            self._apply_equipment_regen_effects(
                f"{source}:time_passage",
                hours=requested_hours,
            )
        )
        companion_lines.extend(self._apply_time_passage_combat_buffs(requested_hours, source=source))
        reason_text = f" {reason}" if reason else ""
        line = f"> [時間] {old_label} -> {new_label} (+{requested_hours}時間){reason_text}"
        event = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "old_hours": old_hours,
            "new_hours": new_hours,
            "hours": requested_hours,
            "old_label": old_label,
            "new_label": new_label,
            "line": line,
            "companion_lines": companion_lines,
            "changed": True,
        }
        deadline_event = self._fail_expired_active_quest(source="quest_deadline", append_log=append_log)
        if deadline_event:
            line_extra = f"> [Quest] Time limit expired: {deadline_event.get('quest')}"
            event["quest_deadline"] = deadline_event
            event.setdefault("companion_lines", []).append(line_extra)
        self.state.world_data.extra.setdefault("time_events", []).append(dict(event))
        if append_log:
            self.state.display_log.append(line)
            self.state.display_log.extend(companion_lines)
        return event

    def _apply_time_passage_combat_buffs(self, hours: int, *, source: str = "time") -> list[str]:
        if hours <= 0:
            return []
        lines: list[str] = []
        player = self.player_character()
        if player:
            updated, hp_delta, sp_delta, tick_lines = _combat_tick_buffs(player.status_effects, player.name or self.state.player_name or "Player", hours=hours)
            player.status_effects = updated
            self.state.status_effects = list(updated)
            lines.extend(tick_lines)
            if hp_delta:
                event = self._apply_player_hp_delta(hp_delta, source=f"{source}:status_tick", reason="status")
                if event.get("line"):
                    lines.append(str(event["line"]))
            if sp_delta:
                event = self._apply_player_sp_delta(sp_delta, source=f"{source}:status_tick", reason="status")
                if event.get("line"):
                    lines.append(str(event["line"]))
        for character in self.state.world_data.characters.values():
            if not isinstance(character, Character) or character.flags.get("is_player"):
                continue
            if not character.status_effects:
                continue
            updated, hp_delta, sp_delta, tick_lines = _combat_tick_buffs(character.status_effects, character.name, hours=hours)
            character.status_effects = updated
            lines.extend(tick_lines)
            if hp_delta:
                max_hp = max(1, _safe_int(character.max_hp, _character_calculated_max_hp(character)))
                old_hp = max(0, _safe_int(character.current_hp, max_hp))
                character.max_hp = max_hp
                character.current_hp = max(0, min(max_hp, old_hp + hp_delta))
                character.extra["current_hp"] = character.current_hp
                character.extra["max_hp"] = max_hp
                sign = f"+{character.current_hp - old_hp}" if character.current_hp >= old_hp else str(character.current_hp - old_hp)
                lines.append(f"> [HP] {character.name}: {old_hp}/{max_hp} -> {character.current_hp}/{max_hp} ({sign})")
            if sp_delta:
                max_sp = max(1, _safe_int(character.max_sp, _character_calculated_max_sp(character)))
                old_sp = max(0, _safe_int(character.current_sp, max_sp))
                character.max_sp = max_sp
                character.current_sp = max(0, min(max_sp, old_sp + sp_delta))
                character.extra["current_sp"] = character.current_sp
                character.extra["max_sp"] = max_sp
                sign = f"+{character.current_sp - old_sp}" if character.current_sp >= old_sp else str(character.current_sp - old_sp)
                lines.append(f"> [SP] {character.name}: {old_sp}/{max_sp} -> {character.current_sp}/{max_sp} ({sign})")
        return lines

    def _world_time_total_hours(self) -> int:
        value = self.state.extra.get("world_time_hours")
        if value is not None:
            return max(0, _safe_int(value, 0))
        day = max(1, _safe_int(self.state.day, 1))
        hour = max(0, min(23, _safe_int(self.state.extra.get("hour") or self.state.extra.get("current_hour"), 0)))
        total_hours = (day - 1) * HOURS_PER_DAY + hour
        self._set_world_time_total_hours(total_hours)
        return total_hours

    def _set_world_time_total_hours(self, total_hours: int) -> None:
        total = max(0, int(total_hours))
        day_index = total // HOURS_PER_DAY
        hour = total % HOURS_PER_DAY
        year = day_index // WORLD_DAYS_PER_YEAR + 1
        day_of_year = day_index % WORLD_DAYS_PER_YEAR
        season_index = min(len(SEASONS) - 1, day_of_year // DAYS_PER_SEASON)
        season = SEASONS[season_index]
        day_in_season = day_of_year % DAYS_PER_SEASON + 1
        self.state.day = day_index + 1
        time_payload = {
            "total_hours": total,
            "year": year,
            "season": season,
            "season_index": season_index,
            "day": day_in_season,
            "hour": hour,
            "absolute_day": self.state.day,
            "label": self._world_time_label(total),
        }
        self.state.extra["world_time_hours"] = total
        self.state.extra["world_time"] = time_payload
        self.state.world_data.extra["world_time"] = dict(time_payload)

    def _world_time_label(self, total_hours: int) -> str:
        total = max(0, int(total_hours))
        day_index = total // HOURS_PER_DAY
        hour = total % HOURS_PER_DAY
        year = day_index // WORLD_DAYS_PER_YEAR + 1
        day_of_year = day_index % WORLD_DAYS_PER_YEAR
        season = SEASONS[min(len(SEASONS) - 1, day_of_year // DAYS_PER_SEASON)]
        day_in_season = day_of_year % DAYS_PER_SEASON + 1
        return f"{year}年目 {season} {day_in_season}日 {hour}時"

    def current_absolute_day(self) -> int:
        self._set_world_time_total_hours(self._world_time_total_hours())
        return max(1, _safe_int(self.state.day, 1))

    def _response_time_delta_hours(self, payload: Any) -> int:
        if isinstance(payload, list):
            return sum(self._response_time_delta_hours(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        total = 0
        hour_keys = {
            "time_passed_hours",
            "passed_hours",
            "elapsed_hours",
            "advance_hours",
            "advance_time_hours",
            "time_delta_hours",
            "hours_passed",
            "long_time_passage_hours",
            "time_skip_hours",
            "skip_time_hours",
            "spend_time_hours",
            "spent_hours",
            "wait_hours",
            "rest_hours",
            "sleep_hours",
            "stay_hours",
        }
        day_keys = {
            "time_passed_days",
            "passed_days",
            "elapsed_days",
            "advance_days",
            "advance_time_days",
            "days_passed",
            "long_time_passage_days",
            "time_skip_days",
            "skip_time_days",
            "spend_time_days",
            "spent_days",
            "wait_days",
            "rest_days",
            "sleep_days",
            "stay_days",
        }
        nested_keys = {
            "time_effect",
            "time_effects",
            "time_passage",
            "elapsed_time",
            "long_time_passage",
            "time_skip",
            "skip_time",
            "spend_time",
            "wait_time",
            "rest_time",
            "sleep_time",
            "stay_time",
        }
        effect_type = str(payload.get("type") or payload.get("kind") or payload.get("name") or "").strip().lower()
        unit = str(payload.get("unit") or payload.get("time_unit") or "").strip().lower()
        if not effect_type and "amount" in payload and unit in {"day", "days", "日", "日間", "hour", "hours", "h", "時間"}:
            amount = self._hp_number(payload.get("amount", 0), 0)
            total += amount * HOURS_PER_DAY if unit in {"day", "days", "日", "日間"} else amount
        if effect_type in {"time_passes", "advance_time", "elapsed_time", "long_time_passage", "time_skip", "spend_time", "wait", "rest", "sleep", "stay"}:
            amount = self._hp_number(payload.get("amount", 0), 0)
            if amount and unit in {"day", "days", "日", "日間"}:
                total += amount * HOURS_PER_DAY
            elif amount and (not unit or unit in {"hour", "hours", "h", "時間"}):
                total += amount
            total += self._hp_number(payload.get("hours", 0), 0)
            total += self._hp_number(payload.get("days", 0), 0) * HOURS_PER_DAY
        for key, child_value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in hour_keys:
                total += self._hp_number(child_value, 0)
            elif key_text in day_keys:
                total += self._hp_number(child_value, 0) * HOURS_PER_DAY
            elif key_text in nested_keys:
                total += self._response_time_delta_hours(child_value)
        return max(0, total)

    def _response_time_reason(self, response: dict[str, Any]) -> str:
        reason = response.get("time_reason") or response.get("elapsed_reason") or response.get("reason") or response.get("event")
        if isinstance(reason, (dict, list)):
            return ""
        return _short_text(str(reason or "").strip(), 40)

    def player_progress(self) -> dict[str, int]:
        level = self._player_level()
        exp = self._player_exp()
        return {"level": level, "exp": exp, "next_exp": self._exp_to_next(level)}

    def apply_player_exp(
        self,
        amount: Any,
        *,
        source: str = "event",
        reason: str = "",
        save_game: bool = True,
    ) -> dict[str, Any]:
        event = self._apply_player_exp(amount, source=source, reason=reason)
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _apply_response_exp_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        amount = self._response_player_exp_delta(response)
        if not amount:
            return []
        target = self._response_exp_target(response, default_character=default_character, encounter=encounter)
        reason = self._response_exp_reason(response)
        if target is not None and not target.flags.get("is_player") and target.name != self.state.player_name:
            event = self._apply_character_exp(target, amount, source=source, reason=reason, encounter=encounter)
        else:
            event = self._apply_player_exp(amount, source=source, reason=reason, encounter=encounter)
        return [str(line) for line in event.get("lines", [])]

    def _apply_player_exp(
        self,
        amount: Any,
        *,
        source: str,
        reason: str = "",
        encounter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gained = max(0, self._hp_number(amount, 0))
        if gained <= 0:
            return {"changed": False, "amount": 0}
        original_level = self._player_level()
        old_exp = self._player_exp()
        level = original_level
        max_exp_bar = self._exp_to_next(PLAYER_MAX_LEVEL)
        if level >= PLAYER_MAX_LEVEL and old_exp >= max_exp_bar:
            return {"changed": False, "amount": gained, "level": level, "exp": old_exp, "reason": "max_level"}
        exp = min(max_exp_bar, old_exp + gained) if level >= PLAYER_MAX_LEVEL else old_exp + gained
        old_max_hp = self._player_max_hp()
        old_current_hp = self._player_current_hp(old_max_hp)
        old_max_sp = self._player_max_sp()
        old_current_sp = self._player_current_sp(old_max_sp)
        level_ups: list[dict[str, Any]] = []
        while level < PLAYER_MAX_LEVEL and exp >= self._exp_to_next(level):
            exp -= self._exp_to_next(level)
            level += 1
            level_ups.append({"level": level, "attribute_gains": self._raise_random_player_attributes()})
        if level >= PLAYER_MAX_LEVEL:
            level = PLAYER_MAX_LEVEL
            exp = min(exp, max_exp_bar)
        self._set_player_progress(level, exp)
        new_max_hp = old_max_hp
        new_max_sp = old_max_sp
        if level_ups:
            new_max_hp = max(old_max_hp + 1, self._calculated_player_max_hp(level=level))
            new_max_sp = max(old_max_sp + 1, self._calculated_player_max_sp(level=level, max_hp=new_max_hp))
            self._set_player_hp(old_current_hp + max(0, new_max_hp - old_max_hp), max_hp=new_max_hp, encounter=encounter)
            self._set_player_sp(old_current_sp + max(0, new_max_sp - old_max_sp), max_sp=new_max_sp, encounter=encounter)
        else:
            self._sync_player_progress_to_character()

        lines = [f"> [EXP] {self.state.player_name}: +{gained} ({old_exp}/{self._exp_to_next(original_level)} -> {exp}/{self._exp_to_next(level)})"]
        display_level = original_level
        for item in level_ups:
            gains = item.get("attribute_gains") or {}
            gain_text = ", ".join(f"{key.upper()}+{value}" for key, value in gains.items()) or "能力上昇なし"
            lines.append(f"> [Level Up] {self.state.player_name}: Lv {display_level} -> {item.get('level')} / {gain_text}")
            display_level = int(item.get("level") or display_level)
        if level_ups:
            lines.append(f"> [成長] HP {old_max_hp}->{new_max_hp} / SP {old_max_sp}->{new_max_sp}")
        event = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "day": self.state.day,
            "amount": gained,
            "old_level": original_level,
            "new_level": level,
            "old_exp": old_exp,
            "new_exp": exp,
            "level_ups": level_ups,
            "lines": lines,
            "changed": True,
        }
        self.state.world_data.extra.setdefault("exp_events", []).append(_strip_response_metadata(event))
        return event

    def _apply_character_exp(
        self,
        character: Character,
        amount: Any,
        *,
        source: str,
        reason: str = "",
        encounter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gained = max(0, self._hp_number(amount, 0))
        if gained <= 0:
            return {"changed": False, "amount": 0}
        self._ensure_character_runtime_data(character)
        original_level = max(1, min(PLAYER_MAX_LEVEL, _safe_int(character.level, 1)))
        old_exp = max(0, _safe_int(character.extra.get("exp") or character.extra.get("experience"), 0))
        level = original_level
        max_exp_bar = self._exp_to_next(PLAYER_MAX_LEVEL)
        if level >= PLAYER_MAX_LEVEL and old_exp >= max_exp_bar:
            return {"changed": False, "amount": gained, "level": level, "exp": old_exp, "reason": "max_level"}
        exp = min(max_exp_bar, old_exp + gained) if level >= PLAYER_MAX_LEVEL else old_exp + gained
        old_max_hp = max(1, _safe_int(character.max_hp, _character_calculated_max_hp(character)))
        old_current_hp = max(0, min(old_max_hp, _safe_int(character.current_hp, old_max_hp)))
        old_max_sp = max(1, _safe_int(character.max_sp, _character_calculated_max_sp(character, max_hp=old_max_hp)))
        old_current_sp = max(0, min(old_max_sp, _safe_int(character.current_sp, old_max_sp)))
        level_ups: list[dict[str, Any]] = []
        while level < PLAYER_MAX_LEVEL and exp >= self._exp_to_next(level):
            exp -= self._exp_to_next(level)
            level += 1
            level_ups.append({"level": level, "attribute_gains": self._raise_random_character_attributes(character)})
        if level >= PLAYER_MAX_LEVEL:
            level = PLAYER_MAX_LEVEL
            exp = min(exp, max_exp_bar)
        character.level = level
        character.extra["level"] = level
        character.extra["exp"] = exp
        character.extra["experience"] = exp
        character.extra["next_exp"] = self._exp_to_next(level)
        new_max_hp = old_max_hp
        new_max_sp = old_max_sp
        if level_ups:
            attrs = _character_runtime_attributes(character)
            new_max_hp = max(old_max_hp + 1, 8 + level * 3 + attrs["con"] * 2 + attrs["str"] // 2 + attrs["will"] // 3)
            new_max_hp = max(10, new_max_hp)
            new_max_sp = max(old_max_sp + 1, int(new_max_hp * 0.45) + attrs["magic"] + attrs["will"] + level * 2)
            new_max_sp = max(6, new_max_sp)
            character.max_hp = new_max_hp
            character.max_sp = new_max_sp
            character.current_hp = max(0, min(new_max_hp, old_current_hp + max(0, new_max_hp - old_max_hp)))
            character.current_sp = max(0, min(new_max_sp, old_current_sp + max(0, new_max_sp - old_max_sp)))
        character.extra["current_hp"] = character.current_hp
        character.extra["max_hp"] = character.max_hp
        character.extra["current_sp"] = character.current_sp
        character.extra["max_sp"] = character.max_sp
        self._sync_companion_party_entry(character)
        if encounter is not None:
            self._sync_encounter_character_after_exp(encounter, character)

        lines = [f"> [EXP] {character.name}: +{gained} ({old_exp}/{self._exp_to_next(original_level)} -> {exp}/{self._exp_to_next(level)})"]
        display_level = original_level
        for item in level_ups:
            gains = item.get("attribute_gains") or {}
            gain_text = ", ".join(f"{key.upper()}+{value}" for key, value in gains.items()) or "ability unchanged"
            lines.append(f"> [Level Up] {character.name}: Lv {display_level} -> {item.get('level')} / {gain_text}")
            display_level = int(item.get("level") or display_level)
        if level_ups:
            lines.append(f"> [Stats] {character.name}: HP {old_max_hp}->{new_max_hp} / SP {old_max_sp}->{new_max_sp}")
        event = {
            "source": source,
            "reason": reason,
            "location": character.location or self.state.current_location,
            "day": self.state.day,
            "target": character.name,
            "target_uuid": character.uuid,
            "amount": gained,
            "old_level": original_level,
            "new_level": level,
            "old_exp": old_exp,
            "new_exp": exp,
            "level_ups": level_ups,
            "lines": lines,
            "changed": True,
        }
        self.state.world_data.extra.setdefault("exp_events", []).append(_strip_response_metadata(event))
        return event

    def _response_exp_target(
        self,
        response: dict[str, Any],
        *,
        default_character: Character | None = None,
        encounter: dict[str, Any] | None = None,
    ) -> Character | None:
        target_uuid = str(response.get("target_uuid") or response.get("uuid") or response.get("character_uuid") or "").strip()
        target_name = str(
            response.get("target")
            or response.get("target_name")
            or response.get("character")
            or response.get("character_name")
            or response.get("npc")
            or response.get("npc_name")
            or ""
        ).strip()
        if not target_name and not target_uuid:
            return None
        if target_name.casefold() in {"player", "pc", "self", "主人公", "プレイヤー", self.state.player_name.casefold()}:
            return self.player_character()
        character = self._character_from_reference(target_name, target_uuid)
        if character:
            return character
        if (
            default_character is not None
            and (
                (target_name and target_name in {default_character.name, str(default_character.uuid or "")})
                or (target_uuid and target_uuid == str(default_character.uuid or ""))
            )
        ):
            return default_character
        if encounter is not None:
            opponent = self._encounter_opponent(encounter)
            if isinstance(opponent, Character) and target_name and target_name == opponent.name:
                return opponent
        return None

    def _raise_random_character_attributes(self, character: Character) -> dict[str, int]:
        attrs = _character_runtime_attributes(character)
        keys = ["str", "dex", "con", "int", "wis", "cha"]
        count = random.randint(1, 3)
        selected = random.sample(keys, k=min(count, len(keys)))
        gains: dict[str, int] = {}
        for key in selected:
            attrs[key] = _safe_int(attrs.get(key), 10) + 1
            gains[key] = gains.get(key, 0) + 1
        attrs["magic"] = max(_safe_int(attrs.get("magic"), attrs.get("int", 10)), attrs.get("int", 10))
        attrs["will"] = max(_safe_int(attrs.get("will"), attrs.get("wis", 10)), attrs.get("wis", 10))
        character.attributes.update(attrs)
        character.extra["attributes"] = dict(attrs)
        ability = character.extra.setdefault("ability", {})
        if isinstance(ability, dict):
            ability["attributes"] = dict(attrs)
        return gains

    def _sync_encounter_character_after_exp(self, encounter: dict[str, Any], character: Character) -> None:
        active_uuid = str(encounter.get("active_opponent_uuid") or encounter.get("opponent_uuid") or "")
        active_name = str(encounter.get("active_opponent_name") or encounter.get("opponent_name") or "")
        opponents = encounter.get("opponents") if isinstance(encounter.get("opponents"), list) else []
        in_encounter = bool(
            (active_uuid and active_uuid == str(character.uuid or ""))
            or (active_name and active_name == character.name)
            or any(
                isinstance(item, dict)
                and (
                    str(item.get("uuid") or "") == str(character.uuid or "")
                    or str(item.get("name") or "") == character.name
                )
                for item in opponents
            )
        )
        if not in_encounter:
            return
        self._sync_encounter_opponent_entry(encounter, character)
        if (active_uuid and active_uuid == str(character.uuid or "")) or (active_name and active_name == character.name):
            encounter["opponent_hp"] = character.current_hp
            encounter["opponent_max_hp"] = character.max_hp
            encounter["opponent_sp"] = character.current_sp
            encounter["opponent_max_sp"] = character.max_sp
            encounter["opponent_level"] = character.level

    def _response_player_exp_delta(self, payload: Any) -> int:
        if isinstance(payload, list):
            return sum(self._response_player_exp_delta(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        total = 0
        effect_type = str(payload.get("type") or payload.get("kind") or payload.get("name") or "").strip().lower()
        value = self._hp_number(
            payload.get("value", payload.get("amount", payload.get("exp", payload.get("xp", 0)))),
            0,
        )
        if effect_type in {"exp", "experience", "xp", "gain_exp", "reward_exp"}:
            total += abs(value)
        signed_keys = {"player_exp_delta", "exp_delta", "experience_delta", "xp_delta"}
        positive_keys = {
            "exp",
            "experience",
            "xp",
            "player_exp",
            "reward_exp",
            "exp_reward",
            "experience_points",
            "gain_exp",
            "gained_exp",
        }
        nested_keys = {"exp_effect", "exp_effects", "experience_effect", "experience_effects", "reward"}
        for key, child_value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in signed_keys:
                total += max(0, self._hp_number(child_value, 0))
            elif key_text in positive_keys:
                total += abs(self._hp_number(child_value, 0))
            elif key_text in nested_keys:
                total += self._response_player_exp_delta(child_value)
        return max(0, total)

    def _response_exp_reason(self, response: dict[str, Any]) -> str:
        reason = response.get("exp_reason") or response.get("experience_reason") or response.get("reason") or response.get("event")
        if isinstance(reason, (dict, list)):
            return ""
        return _short_text(str(reason or "").strip(), 40)

    def _apply_visual_intent(
        self,
        response: dict[str, Any],
        source: str,
        location: str,
        previous_location: str = "",
    ) -> None:
        location_name = location or self.state.current_location or self.state.world_data.starting_location
        self.state.flags.pop("pending_cg_request", None)
        self._request_background_if_needed(location_name)

    def dismiss_active_cg(self) -> bool:
        removed = False
        for key in ("active_cg_image_path", "active_cg_request"):
            if key in self.state.flags:
                self.state.flags.pop(key, None)
                removed = True
        return removed

    def _request_background_if_needed(self, location: str) -> None:
        if not location:
            return
        target = self._current_background_target(location)
        self.state.flags["active_background_context"] = _strip_response_metadata(target)
        image_path = str(target.get("image_path") or "")
        image_exists = bool(image_path and Path(image_path).is_file())
        if image_exists:
            if target.get("kind") == "location":
                self.state.flags.pop("active_background_image_path", None)
            else:
                self.state.flags["active_background_image_path"] = image_path
            self.state.flags.pop("pending_background_location", None)
            self.state.flags.pop("pending_background_context", None)
            return

        if target.get("kind") == "location":
            self.state.flags.pop("active_background_image_path", None)
        else:
            self.state.flags.pop("active_background_image_path", None)
        if not image_exists:
            self.state.flags["pending_background_location"] = location
            self.state.flags["pending_background_context"] = _strip_response_metadata(target)

    def _current_background_target(self, location: str) -> dict[str, Any]:
        world = self.state.world_data
        location_name = str(location or self.state.current_location or world.starting_location or "unknown").strip()
        location_data = world.ensure_location(location_name)

        active_facility = self._active_facility_record()
        if active_facility and _is_settlement_location(location_data):
            facility_name = str(active_facility.get("name") or "").strip()
            if facility_name:
                return {
                    "kind": "facility",
                    "location": location_name,
                    "name": facility_name,
                    "display_name": f"{location_name} / {facility_name}",
                    "description": str(active_facility.get("description") or location_data.description or ""),
                    "facility_type": str(active_facility.get("type") or ""),
                    "image_path": str(active_facility.get("image_path") or ""),
                    "storage_key": f"{location_name}__facility__{facility_name}",
                }

        graph = self._ensure_location_subnode_graph(world, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        subnode_id = self._current_subnode_id(location_name) if nodes else ""
        subnode = nodes.get(subnode_id) if subnode_id else None
        if isinstance(subnode, dict):
            subnode_name = str(subnode.get("name") or subnode_id).strip()
            specific_subnode = (
                bool(subnode_id and subnode_id != DEFAULT_SUBNODE_ID)
                or _is_dungeon_location(location_data)
                or _world_location_blocks_world_map_departure(location_data)
            )
            if subnode_name and specific_subnode:
                return {
                    "kind": "subnode",
                    "location": location_name,
                    "subnode_id": subnode_id,
                    "name": subnode_name,
                    "display_name": f"{location_name} / {subnode_name}",
                    "description": str(subnode.get("description") or location_data.description or ""),
                    "subnode_kind": str(subnode.get("kind") or ""),
                    "image_path": str(subnode.get("image_path") or ""),
                    "storage_key": f"{location_name}__subnode__{subnode_id}",
                }

        return {
            "kind": "location",
            "location": location_name,
            "name": location_name,
            "display_name": location_name,
            "description": str(location_data.description or location_data.area or ""),
            "image_path": str(location_data.image_path or ""),
            "storage_key": location_name,
        }

    def _apply_background_image_to_target(
        self,
        target: dict[str, Any],
        image_path: Path,
        prompt_record: dict[str, Any],
    ) -> None:
        world = self.state.world_data
        kind = str(target.get("kind") or "location")
        location_name = str(target.get("location") or self.state.current_location or world.starting_location or "unknown")
        saved_path = str(image_path)
        if kind == "facility":
            settlement = world.locations.get(location_name)
            if settlement:
                facility_name = str(target.get("name") or "")
                for facility in self._ensure_settlement_facilities(settlement):
                    if _facility_name_matches(str(facility.get("name") or ""), facility_name):
                        facility["image_path"] = saved_path
                        facility["prompts"] = prompt_record
                        break
            self.state.flags["active_background_image_path"] = saved_path
        elif kind == "subnode":
            graph = self._ensure_location_subnode_graph(world, location_name)
            nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
            node = nodes.get(str(target.get("subnode_id") or ""))
            if isinstance(node, dict):
                node["image_path"] = saved_path
                node["prompts"] = prompt_record
            self.state.flags["active_background_image_path"] = saved_path
        else:
            location_data = world.ensure_location(location_name)
            location_data.image_path = saved_path
            location_data.prompts = prompt_record
            self.state.flags.pop("active_background_image_path", None)
        self.state.flags["active_background_context"] = _strip_response_metadata({**target, "image_path": saved_path})

    def _current_settlement_location(self) -> LocationData | None:
        current_name = self.state.current_location or self.state.world_data.starting_location
        current = self.state.world_data.locations.get(current_name)
        if _is_non_settlement_submap(self.state.world_data, current_name):
            return None
        if current and _is_settlement_location(current):
            return current
        parent_name = str((current.extra.get("parent_location") if current else "") or "")
        if not parent_name:
            parent_name = _infer_settlement_parent_name(self.state.world_data, current_name)
            if parent_name and current:
                current.extra["parent_location"] = parent_name
                current.area = current.area or parent_name
        if parent_name:
            parent = self.state.world_data.locations.get(parent_name)
            if parent and _is_settlement_location(parent):
                return parent
        return None

    def _world_customization(self) -> dict[str, str]:
        raw = self.state.world_data.extra.get("customization") if isinstance(self.state.world_data.extra, dict) else None
        if not isinstance(raw, dict):
            raw = self.state.flags.get("world_customization")
        raw = raw if isinstance(raw, dict) else {}
        return _world_customization_settings(
            raw.get("crime_risk") or self.state.world_data.extra.get("crime_risk"),
            raw.get("enemy_strength") or self.state.world_data.extra.get("enemy_strength"),
        )

    def _crime_risk_setting(self) -> str:
        return self._world_customization().get("crime_risk", DEFAULT_WORLD_CRIME_RISK)

    def _enemy_strength_setting(self) -> str:
        return self._world_customization().get("enemy_strength", DEFAULT_WORLD_ENEMY_STRENGTH)

    def _npc_template_used_ids(self, world: WorldData | None = None) -> set[str]:
        return npc_generate.npc_template_used_ids(self, world)

    def _npc_template_categories_for_objective(self, objective_role: str) -> tuple[str, ...]:
        return npc_generate.npc_template_categories_for_objective(objective_role)

    def _npc_template_danger_for_location(self, location_name: str) -> int:
        return npc_generate.npc_template_danger_for_location(self, location_name)

    def _select_npc_template(
        self,
        *,
        categories: tuple[str, ...],
        danger_level: int,
        seed: str,
        payloads: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        return npc_generate.select_npc_template(
            self,
            categories=categories,
            danger_level=danger_level,
            seed=seed,
            payloads=payloads,
        )

    def _npc_template_character_payload(
        self,
        template: dict[str, Any] | None,
        *,
        danger_level: int,
        seed: str,
        hostile: bool | None = None,
        boss: bool = False,
    ) -> dict[str, Any]:
        return npc_generate.npc_template_character_payload(
            self,
            template,
            danger_level=danger_level,
            seed=seed,
            hostile=hostile,
            boss=boss,
        )

    def _npc_template_selection_text(self, raw: Any) -> tuple[str, str, str, str]:
        return npc_generate.npc_template_selection_text(raw)

    def _score_npc_template_for_raw(self, template: dict[str, Any], raw: Any) -> int:
        return npc_generate.score_npc_template_for_raw(template, raw)

    def _choose_npc_template_for_raw(
        self,
        raw: Any,
        *,
        categories: tuple[str, ...],
        danger_level: int,
        seed: str,
        preferred_ids: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        return npc_generate.choose_npc_template_for_raw(
            self,
            raw,
            categories=categories,
            danger_level=danger_level,
            seed=seed,
            preferred_ids=preferred_ids,
        )

    def _template_augmented_npc_raw(
        self,
        raw: Any,
        *,
        categories: tuple[str, ...],
        danger_level: int,
        seed: str,
        hostile: bool | None = None,
        boss: bool = False,
        select_without_id: bool = True,
    ) -> dict[str, Any]:
        return npc_generate.template_augmented_npc_raw(
            self,
            raw,
            categories=categories,
            danger_level=danger_level,
            seed=seed,
            hostile=hostile,
            boss=boss,
            select_without_id=select_without_id,
        )

    def _generated_npc_level(
        self,
        character: Character,
        *,
        location_name: str = "",
        danger_level: int | None = None,
        role_hint: str = "",
        boss: bool = False,
    ) -> int:
        return npc_generate.generated_npc_level(
            self,
            character,
            location_name=location_name,
            danger_level=danger_level,
            role_hint=role_hint,
            boss=boss,
        )

    def _finalize_generated_npc(
        self,
        character: Character,
        *,
        location_name: str = "",
        danger_level: int | None = None,
        role_hint: str = "",
        boss: bool = False,
        sync_vitals_to_formula: bool = True,
    ) -> None:
        npc_generate.finalize_generated_npc(
            self,
            character,
            location_name=location_name,
            danger_level=danger_level,
            role_hint=role_hint,
            boss=boss,
            sync_vitals_to_formula=sync_vitals_to_formula,
        )
    def _ensure_settlement_crime_profile(self, settlement: LocationData) -> dict[str, Any]:
        profile = settlement.extra.setdefault("crime", {})
        if not isinstance(profile, dict):
            profile = {}
            settlement.extra["crime"] = profile
        profile.setdefault("player_score", 0)
        profile.setdefault("wanted", False)
        profile.setdefault("risk_multiplier", _settlement_crime_risk_multiplier(settlement))
        profile["player_score"] = max(0, min(100, _safe_int(profile.get("player_score"), 0)))
        profile["wanted"] = bool(profile.get("wanted")) or profile["player_score"] >= 100
        return profile

    def _apply_crime_risk(self, action: str, response: Any, source: str, *, location: str = "") -> list[str]:
        mode = self._crime_risk_setting()
        if mode == "none":
            return []
        settlement = _settlement_location_for_name(self.state.world_data, location or self.state.current_location)
        if settlement is None:
            return []
        severity = _crime_severity(action, response)
        if severity <= 0:
            return []
        profile = self._ensure_settlement_crime_profile(settlement)
        multiplier = max(0.0, min(2.0, _safe_float(profile.get("risk_multiplier"), 1.0)))
        if multiplier <= 0:
            return []
        mode_multiplier = 1.0 if mode == "normal" else 2.0
        delta = max(1, int(round(severity * multiplier * mode_multiplier)))
        old_score = max(0, min(100, _safe_int(profile.get("player_score"), 0)))
        new_score = max(0, min(100, old_score + delta))
        profile["player_score"] = new_score
        became_wanted = new_score >= 100 and not bool(profile.get("wanted"))
        if new_score >= 100:
            profile["wanted"] = True
        event = {
            "source": source,
            "action": action,
            "location": settlement.name,
            "risk_setting": mode,
            "risk_multiplier": multiplier,
            "severity": severity,
            "delta": delta,
            "old_score": old_score,
            "new_score": new_score,
            "wanted": bool(profile.get("wanted")),
        }
        self.state.world_data.extra.setdefault("crime_events", []).append(event)
        wanted = self.state.flags.setdefault("wanted_settlements", {})
        if isinstance(wanted, dict):
            wanted[settlement.name] = bool(profile.get("wanted"))
        lines = [f"> [犯罪度] {settlement.name}: {old_score} -> {new_score} (+{delta})"]
        if became_wanted:
            lines.append(f"> [犯罪度] {settlement.name}でお尋ね者になった。")
        return lines

    def _maybe_start_guard_encounter(self, action: str, input_type: str) -> str | None:
        if self._crime_risk_setting() == "none":
            return None
        if self._active_encounter():
            return None
        settlement = self._current_settlement_location()
        if settlement is None:
            return None
        profile = self._ensure_settlement_crime_profile(settlement)
        if not bool(profile.get("wanted")):
            return None
        multiplier = max(0.0, min(2.0, _safe_float(profile.get("risk_multiplier"), 1.0)))
        if multiplier <= 0:
            return None
        base_chance = 0.18 if self._crime_risk_setting() == "normal" else 0.34
        chance = max(0.05, min(0.70, base_chance * max(0.5, multiplier)))
        rng = random.Random(f"guard-encounter:{self.state.world_name}:{settlement.name}:{self.state.day}:{len(self.state.action_log)}:{action}")
        if rng.random() > chance:
            return None
        guard = self._ensure_guard_character(settlement)
        encounter = self._build_encounter("character", guard.name, location=self.state.current_location)
        encounter["guard_encounter"] = True
        self.state.flags["active_encounter"] = encounter
        self.state.flags["screen_mode"] = "battle"
        narration = f"{settlement.name}の衛兵があなたを見つけ、武器を構えた。"
        self._append_turn(action, narration, self.state.current_location, self._encounter_choices(encounter), input_type=input_type)
        self.state.display_log.append(f"> [警備] お尋ね者として衛兵に見つかった。")
        self.save_game()
        return self.state.log_text(16)

    def _ensure_guard_character(self, settlement: LocationData) -> Character:
        return npc_generate.ensure_guard_character(self, settlement)

    def _current_location_danger(self, location_name: str = "") -> int:
        name = location_name or self.state.current_location or self.state.world_data.starting_location
        location = self.state.world_data.locations.get(name)
        danger = _safe_int((location.extra.get("danger_level") if location else 0), 0)
        if not location:
            danger = max(danger, self._danger_for_subnode_display_location(name))
        graph = self.state.world_data.extra.get("location_graph") if isinstance(self.state.world_data.extra, dict) else None
        nodes = graph.get("nodes") if isinstance(graph, dict) else None
        node = nodes.get(name) if isinstance(nodes, dict) else None
        if isinstance(node, dict):
            danger = max(danger, _safe_int(node.get("danger"), danger))
        return _clamp_world_danger(danger)

    def _danger_for_subnode_display_location(self, display_name: str) -> int:
        display_name = str(display_name or "").strip()
        if not display_name:
            return 0
        graph = self.state.world_data.extra.get("location_graph") if isinstance(self.state.world_data.extra, dict) else None
        nodes = graph.get("nodes") if isinstance(graph, dict) else {}
        best = 0
        for location_name, location in self.state.world_data.locations.items():
            subnode_graph = location.extra.get(SUBNODE_GRAPH_KEY) if isinstance(location.extra, dict) else None
            subnodes = subnode_graph.get("nodes") if isinstance(subnode_graph, dict) else None
            if not isinstance(subnodes, dict):
                continue
            for subnode in subnodes.values():
                if not isinstance(subnode, dict):
                    continue
                subnode_name = str(subnode.get("name") or "").strip()
                if not subnode_name:
                    continue
                if display_name not in {subnode_name, f"{location_name}\u30fb{subnode_name}", f"{location_name} / {subnode_name}"}:
                    continue
                danger = _safe_int(location.extra.get("danger_level"), 0)
                node = nodes.get(location_name) if isinstance(nodes, dict) else None
                if isinstance(node, dict):
                    danger = max(danger, _safe_int(node.get("danger"), danger))
                best = max(best, danger)
        return _clamp_world_danger(best)

    def _opponent_combat_profile(self, opponent_type: str, opponent_name: str, *, location: str = "") -> dict[str, Any]:
        danger = self._current_location_danger(location)
        combat_stats = self.player_combat_stats()
        player_attack = max(0, int(combat_stats.get("attack") or 0) + int(combat_stats.get("attack_bonus") or 0))
        player_defense = max(0, int(combat_stats.get("defense") or 0) + int(combat_stats.get("defense_bonus") or 0))
        setting = self._enemy_strength_setting()
        base_attack = max(0, 1 + danger * 2)
        base_defense = max(0, danger)
        base_hp = 1
        hp = base_hp
        if setting == "weak":
            attack = max(0, min(base_attack, max(0, player_defense - 1)))
            defense = max(0, min(base_defense, max(0, player_attack // 2 - 1)))
        elif setting == "strong":
            attack = max(base_attack, player_defense + 2 + danger // 2)
            defense = max(base_defense, max(1, player_attack // 2 + 1 + danger // 2))
        else:
            attack = base_attack
            defense = base_defense
        opponent = self.state.world_data.character(opponent_name)
        if isinstance(opponent, Character):
            has_normal_hp = _safe_int(opponent.max_hp, 0) > 0
            if not has_normal_hp:
                _scale_character_for_danger(opponent, danger)
                self._ensure_character_runtime_data(opponent)
            elif _safe_int(opponent.current_hp, 0) > 0:
                self._ensure_character_runtime_data(opponent)
            if opponent.attack <= 0:
                opponent.attack = max(attack, _character_calculated_attack(opponent))
            if opponent.defense <= 0:
                opponent.defense = max(defense, _character_calculated_defense(opponent))
            opponent.extra["attack"] = opponent.attack
            opponent.extra["defense"] = opponent.defense
            hp = max(1, _safe_int(opponent.max_hp, hp))
            attack = max(0, _safe_int(opponent.attack, attack))
            defense = max(0, _safe_int(opponent.defense, defense))
        else:
            hp = _character_calculated_max_hp(_danger_scaled_placeholder_enemy(opponent_name, danger))
        return {
            "enemy_strength": setting,
            "danger_level": danger,
            "opponent_attack": max(0, int(attack)),
            "opponent_defense": max(0, int(defense)),
            "opponent_hp": max(1, int(hp)),
            "opponent_max_hp": max(1, int(hp)),
        }

    def _encounter_opponent_names_for_start(self, primary: Character | None, location: str) -> list[str]:
        names: list[str] = []
        if isinstance(primary, Character) and primary.name:
            names.append(primary.name)
        if isinstance(primary, Character) and not _character_is_hostile_actor(primary):
            return names[:1]
        for character in self._hostile_characters_at(location, limit=COMBAT_MAX_OPPONENTS + 2):
            if len(names) >= COMBAT_MAX_OPPONENTS:
                break
            if not character.name or character.name in names:
                continue
            if not _character_is_hostile_actor(character):
                continue
            names.append(character.name)
        return names[:COMBAT_MAX_OPPONENTS]

    def _encounter_opponent_entry(self, character: Character, *, location: str) -> dict[str, Any]:
        profile = self._opponent_combat_profile("character", character.name, location=location)
        if _safe_int(character.max_hp, 0) <= 0 or _safe_int(character.current_hp, 0) > 0:
            self._ensure_character_runtime_data(character)
        current_hp = max(0, min(character.max_hp, _safe_int(character.current_hp, character.max_hp)))
        character.current_hp = current_hp
        character.extra["current_hp"] = current_hp
        return {
            "opponent_type": "character",
            "name": character.name,
            "uuid": str(character.uuid or ""),
            "status": "active" if current_hp > 0 and not _character_state_is_dead(character) else "defeated",
            "opponent_status": str(character.extra.get("combat_status") or character.state or "hostile"),
            "opponent_attack": max(0, _safe_int(profile.get("opponent_attack"), character.attack)),
            "opponent_defense": max(0, _safe_int(profile.get("opponent_defense"), character.defense)),
            "opponent_hp": current_hp,
            "opponent_max_hp": max(1, _safe_int(character.max_hp, 1)),
            "danger_level": profile.get("danger_level"),
            "enemy_strength": profile.get("enemy_strength"),
        }

    def _sync_encounter_opponent_entry(self, encounter: dict[str, Any], character: Character) -> dict[str, Any]:
        opponents = encounter.setdefault("opponents", [])
        if not isinstance(opponents, list):
            opponents = []
            encounter["opponents"] = opponents
        entry: dict[str, Any] | None = None
        for item in opponents:
            if not isinstance(item, dict):
                continue
            if str(item.get("uuid") or "") == str(character.uuid or "") or str(item.get("name") or "") == character.name:
                entry = item
                break
        if entry is None:
            entry = {"opponent_type": "character", "name": character.name, "uuid": str(character.uuid or "")}
            opponents.append(entry)
        keep_zero_hp = _safe_int(character.max_hp, 0) > 0 and _safe_int(character.current_hp, 0) <= 0
        if not keep_zero_hp:
            self._ensure_character_runtime_data(character)
        entry["name"] = character.name
        entry["uuid"] = str(character.uuid or "")
        entry["opponent_hp"] = max(0, min(character.max_hp, _safe_int(character.current_hp, character.max_hp)))
        entry["opponent_max_hp"] = max(1, _safe_int(character.max_hp, 1))
        entry["opponent_attack"] = max(0, _safe_int(character.attack, entry.get("opponent_attack") or 0))
        entry["opponent_defense"] = max(0, _safe_int(character.defense, entry.get("opponent_defense") or 0))
        if entry["opponent_hp"] <= 0 or _character_state_is_dead(character):
            entry["status"] = "defeated"
        else:
            entry["status"] = str(entry.get("status") or "active")
        return entry

    def _set_encounter_active_opponent(self, encounter: dict[str, Any], character: Character | None) -> None:
        if not isinstance(character, Character):
            return
        entry = self._sync_encounter_opponent_entry(encounter, character)
        encounter["opponent_type"] = "character"
        encounter["opponent_name"] = character.name
        encounter["opponent_uuid"] = str(character.uuid or "")
        encounter["opponent_status"] = str(entry.get("opponent_status") or encounter.get("opponent_status") or "hostile")
        encounter["opponent_attack"] = max(0, _safe_int(entry.get("opponent_attack"), character.attack))
        encounter["opponent_defense"] = max(0, _safe_int(entry.get("opponent_defense"), character.defense))
        encounter["opponent_hp"] = max(0, _safe_int(entry.get("opponent_hp"), character.current_hp))
        encounter["opponent_max_hp"] = max(1, _safe_int(entry.get("opponent_max_hp"), character.max_hp or 1))
        encounter["active_opponent_uuid"] = str(character.uuid or "")
        encounter["active_opponent_name"] = character.name

    def _encounter_opponents(self, encounter: dict[str, Any]) -> list[Character]:
        opponents: list[Character] = []
        raw = encounter.get("opponents")
        entries = raw if isinstance(raw, list) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            character = self._character_from_reference(str(entry.get("name") or ""), str(entry.get("uuid") or ""))
            if character and character not in opponents:
                opponents.append(character)
        primary = self._character_from_reference(str(encounter.get("opponent_name") or ""), str(encounter.get("opponent_uuid") or ""))
        if primary and primary not in opponents:
            opponents.insert(0, primary)
        return opponents[:COMBAT_MAX_OPPONENTS]

    def _living_encounter_opponents(self, encounter: dict[str, Any]) -> list[Character]:
        living: list[Character] = []
        for character in self._encounter_opponents(encounter):
            entry = self._sync_encounter_opponent_entry(encounter, character)
            combat_status = str(entry.get("status") or entry.get("opponent_status") or character.extra.get("combat_status") or "").strip().lower()
            if combat_status in {FLED_STATUS_ID, "escaped", "retreated", "surrender_accepted"}:
                continue
            if any(_status_effect_id(_normalise_status_effect(effect)) == FLED_STATUS_ID for effect in character.status_effects):
                continue
            if _character_state_is_dead(character):
                continue
            if max(0, _safe_int(character.current_hp, 0)) <= 0:
                continue
            living.append(character)
        return living

    def _acting_encounter_opponents(self, encounter: dict[str, Any]) -> list[Character]:
        return [character for character in self._living_encounter_opponents(encounter) if not self._character_has_surrendered(character, encounter)]

    def _character_has_surrendered(self, character: Character, encounter: dict[str, Any] | None = None) -> bool:
        if not isinstance(character, Character):
            return False
        flags = character.flags if isinstance(character.flags, dict) else {}
        extra = character.extra if isinstance(character.extra, dict) else {}
        if _as_bool(flags.get("surrendered")) or _as_bool(extra.get("surrendered")):
            return True
        status = str(extra.get("combat_status") or flags.get("combat_status") or "").strip().lower()
        if status == SURRENDERED_STATUS_ID:
            return True
        if encounter is not None:
            for item in encounter.get("opponents", []):
                if not isinstance(item, dict):
                    continue
                if str(item.get("uuid") or "") != str(character.uuid or "") and str(item.get("name") or "") != character.name:
                    continue
                entry_status = str(item.get("status") or item.get("opponent_status") or "").strip().lower()
                if entry_status == SURRENDERED_STATUS_ID:
                    return True
        return any(_status_effect_id(_normalise_status_effect(effect)) == SURRENDERED_STATUS_ID for effect in character.status_effects)

    def _encounter_has_surrendered_opponents(self, encounter: dict[str, Any]) -> bool:
        return any(self._character_has_surrendered(character, encounter) for character in self._living_encounter_opponents(encounter))

    def _select_encounter_target_from_action(self, encounter: dict[str, Any], action: str) -> Character | None:
        living = self._living_encounter_opponents(encounter)
        if not living:
            return None
        target = _clean_generated_name(_extract_attack_target(action), "", kind="monster")
        if not target:
            target = str(action or "").strip()
        folded = target.casefold()
        if folded:
            for character in living:
                terms = _character_reference_terms(character)
                terms.extend(_as_str_list(character.flags.get("aliases")))
                terms.extend(_as_str_list(character.extra.get("aliases")))
                for term in _dedupe_strs([str(item or "").strip() for item in terms]):
                    if not term:
                        continue
                    term_folded = term.casefold()
                    if term == target or target in term or term in target or folded in term_folded or term_folded in folded:
                        self._set_encounter_active_opponent(encounter, character)
                        return character
        active_uuid = str(encounter.get("active_opponent_uuid") or encounter.get("opponent_uuid") or "")
        active_name = str(encounter.get("active_opponent_name") or encounter.get("opponent_name") or "")
        for character in living:
            if (active_uuid and str(character.uuid) == active_uuid) or (active_name and character.name == active_name):
                self._set_encounter_active_opponent(encounter, character)
                return character
        self._set_encounter_active_opponent(encounter, living[0])
        return living[0]

    def _character_from_reference(self, name: str = "", uuid: str = "") -> Character | None:
        uuid = str(uuid or "").strip()
        if uuid:
            for character in self.state.world_data.characters.values():
                if str(character.uuid or "") == uuid:
                    return character
        name = str(name or "").strip()
        if name:
            return self.state.world_data.character(name)
        return None

    def _build_encounter(self, opponent_type: str, opponent_name: str, *, location: str = "") -> dict[str, Any]:
        location_name = location or self.state.current_location
        player_max_hp = self._player_max_hp()
        player_hp = self._player_current_hp(player_max_hp)
        player_max_sp = self._player_max_sp()
        player_sp = self._player_current_sp(player_max_sp)
        combat_stats = self.player_combat_stats()
        equipment_summary = self.player_equipment_summary()
        opponent_profile = self._opponent_combat_profile(opponent_type, opponent_name, location=location_name)
        opponent = self.state.world_data.character(opponent_name)
        opponent_names = self._encounter_opponent_names_for_start(opponent if isinstance(opponent, Character) else None, location_name)
        opponent_entries: list[dict[str, Any]] = []
        for name in opponent_names:
            character = self.state.world_data.character(name)
            if isinstance(character, Character):
                opponent_entries.append(self._encounter_opponent_entry(character, location=location_name))
        encounter = {
            "status": "active",
            "turn": 0,
            "opponent_type": "character",
            "opponent_name": opponent_name,
            "opponent_uuid": str(getattr(opponent, "uuid", "") or ""),
            "player_status": "armed",
            "opponent_status": "hostile",
            "player_hp": player_hp,
            "player_max_hp": player_max_hp,
            "player_sp": player_sp,
            "player_max_sp": player_max_sp,
            "player_hunger": self._player_hunger(),
            "player_max_hunger": PLAYER_MAX_HUNGER,
            "player_attack": combat_stats["attack"],
            "player_attack_bonus": combat_stats["attack_bonus"],
            "player_defense": combat_stats["defense"],
            "player_defense_bonus": combat_stats["defense_bonus"],
            "player_equipment": _compact_value(equipment_summary, max_chars=900),
            "location": location_name,
            "opponents": opponent_entries,
            "turn_order": ["player"] + [entry.get("uuid") or entry.get("name") for entry in opponent_entries],
            "log": [],
        }
        encounter.update(opponent_profile)
        if isinstance(opponent, Character):
            self._set_encounter_active_opponent(encounter, opponent)
        self._sync_encounter_status_effects(encounter)
        self._update_encounter_presence(encounter, "present")
        return encounter

    def _ensure_settlement_facilities(self, settlement: LocationData) -> list[dict[str, Any]]:
        raw = settlement.extra.get("facilities")
        facilities = [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if not any(_looks_like_guild_name(str(item.get("name") or "")) for item in facilities):
            facilities.insert(0, _facility_record(DEFAULT_GUILD_NAME, settlement.name, facility_type="guild"))
        if not _facility_exists([item for item in facilities if isinstance(item, dict)], "役場"):
            facilities.append(_facility_record("役場", settlement.name, facility_type="town_hall"))
        normalized: list[dict[str, Any]] = []
        for item in facilities:
            name = _clean_settlement_generated_text(
                item.get("name") or item.get("facility_name") or item.get("title") or "",
                settlement.name,
            )
            if not name:
                continue
            if _is_reserved_settlement_facility_name(name):
                continue
            facility_type = str(item.get("type") or item.get("facility_type") or _facility_type_from_name(name)).strip()
            original_name = name
            name = _shop_facility_display_name(name, facility_type, settlement.name, len(normalized))
            if _is_reserved_settlement_facility_name(name):
                continue
            description = _facility_description_from_payload(
                item.get("description") or item.get("overview") or "",
                settlement.name,
                name,
            )
            record = {
                "name": name,
                "type": facility_type,
                "description": description,
                "npc_name": _clean_settlement_generated_text(item.get("npc_name") or item.get("keeper") or item.get("owner") or "", settlement.name),
                "npc_role": _clean_settlement_generated_text(item.get("npc_role") or item.get("role") or "", settlement.name),
                **_facility_keeper_fields(item, settlement.name, name, description),
                "location_name": settlement.name,
                "sub_location": name,
                "source": str(item.get("source") or "settlement"),
                "aliases": _facility_aliases(original_name, name, facility_type),
            }
            for template_key in (
                "template_id",
                "template_name",
                "template_desc",
                "function_npc",
                "shopkeeper",
                "shopItem",
                "shop_item_table",
                "local_template",
                "raw_template_world_facility_description",
                "npc_namelist_id",
                "npc_namelist_english_en",
            ):
                if template_key in item:
                    record[template_key] = item[template_key]
            if _looks_like_guild_name(name):
                record["type"] = "guild"
                record.setdefault("npc_role", "ギルド受付")
            if not _facility_exists(normalized, name):
                normalized.append(record)
        settlement.extra["facilities"] = normalized
        settlement.flags["settlement"] = True
        return normalized

    def _find_or_create_facility_record(self, settlement: LocationData, facility_name: str) -> dict[str, Any] | None:
        requested = str(facility_name or "").strip()
        if not requested:
            return None
        facilities = self._ensure_settlement_facilities(settlement)
        for facility in facilities:
            if _facility_record_matches_requested(facility, requested):
                return facility
        requested_type = _facility_type_from_name(requested)
        if requested_type == "guild":
            for facility in facilities:
                if str(facility.get("type") or "").lower() == "guild" or _looks_like_guild_name(str(facility.get("name") or "")):
                    return facility
        if requested_type in SHOP_FACILITY_TYPES:
            for facility in facilities:
                if str(facility.get("type") or "").lower() == requested_type:
                    return facility
        return None

    def _create_facility_from_action(self, action: str, input_type: str) -> str | None:
        settlement = self._current_settlement_location()
        facilities = self.current_location_facilities()
        requested = _facility_request_from_action(action, facilities) or _facility_request_from_creation_action(action, facilities)
        if not requested:
            return None
        if _is_reserved_settlement_facility_name(requested):
            return None
        if settlement is None:
            narration = f"この場所には「{requested}」のような街の施設は存在しない。"
            self._append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        existing = self._find_or_create_facility_record(settlement, requested)
        if existing:
            return self._move_to_facility(settlement, existing, action=action, input_type=input_type)

        response = self._facility_request_evaluator(action, requested, settlement)
        allowed = _as_bool(response.get("allowed") or response.get("can_create"))
        if not allowed:
            narration = str(response.get("narration") or response.get("reason") or f"{settlement.name}には「{requested}」はない。")
            self.state.world_data.history.append(
                {
                    "manager": "facility_request_evaluator",
                    "action": action,
                    "requested_facility": requested,
                    "allowed": False,
                    "response": _strip_response_metadata(response),
                }
            )
            self._append_turn(action, narration, settlement.name, self._location_default_choices(settlement.name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)

        facility = self._facility_from_response(response, requested, settlement)
        if _is_reserved_settlement_facility_name(str(facility.get("name") or "")):
            return None
        facilities = self._ensure_settlement_facilities(settlement)
        facilities.append(facility)
        settlement.extra["facilities"] = facilities
        self.state.world_data.history.append(
            {
                "manager": "facility_request_evaluator",
                "action": action,
                "requested_facility": requested,
                "allowed": True,
                "facility": facility,
                "response": _strip_response_metadata(response),
            }
        )
        return self._move_to_facility(settlement, facility, action=action, input_type=input_type, response=response)

    def _move_to_facility(
        self,
        settlement: LocationData,
        facility: dict[str, Any],
        *,
        action: str,
        input_type: str,
        response: dict[str, Any] | None = None,
    ) -> str:
        previous_location = self.state.current_location
        facility_name = str(facility.get("name") or "facility")
        location_name = settlement.name
        block_reason = self._player_incapacitated_action_block(action, for_movement=True)
        if block_reason:
            narration = self._player_incapacitated_message(block_reason)
            self._append_turn(action, narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        narrator_response = self._direct_travel_narrator(
            action=action,
            input_type=input_type,
            travel_kind="facility",
            source_name=previous_location,
            destination_location=settlement.name,
            destination_name=facility_name,
            destination_description=str(facility.get("description") or settlement.description or ""),
            route_text=f"{settlement.name}の中にある{facility_name}へ向かう。",
        )
        facility["location_name"] = settlement.name
        facility["sub_location"] = facility_name
        settlement.flags["settlement"] = True
        settlement.flags["discovered"] = True
        settlement.extra["location_kind"] = "settlement"
        self._mark_location_visited(self.state.world_data, settlement.name)
        self._set_active_facility(settlement, facility)
        npc = self._ensure_facility_npc(settlement, facility, settlement.name)
        choices = (
            self._location_default_choices(settlement.name)
            + self._filter_llm_choices_for_display(_as_str_list((response or {}).get("choices")))
            + self._filter_llm_choices_for_display(_as_str_list(narrator_response.get("choices")))
        )
        if npc:
            choices.append(f"{npc.name}に話しかける")
        narration = str(narrator_response.get("narration") or (response or {}).get("narration") or f"{facility_name}へ移動した。")
        self._set_player_presence(settlement.name)
        choices = _exploration_choices(choices)
        narration, choices, _ = self._evaluate_hostile_arrival(action, input_type, "facility_travel", settlement.name, narration, choices)
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self._append_turn(action, narration, settlement.name, choices, input_type=input_type)
        visual_response = self._merge_visual_response(response or {}, narrator_response)
        self._apply_visual_intent(visual_response, "facility_travel", settlement.name, previous_location)
        self.save_game()
        return self.state.log_text(16)

    def _direct_travel_narrator(
        self,
        *,
        action: str,
        input_type: str,
        travel_kind: str,
        source_name: str,
        destination_location: str,
        destination_name: str,
        destination_description: str = "",
        route_text: str = "",
        elapsed_hours: int = 0,
    ) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの移動描写担当です。"
                    "ゲーム側で移動可否、移動先、経過時間はすでに確定しています。"
                    "それらを変更せず、移動後の場面が自然に分かる短い描写と次の選択肢だけを返してください。"
                    "location は必ず destination_location と同じ文字列にしてください。"
                    "施設名やサブノード名を location にしないでください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界: {self.state.world_name}\n"
                    f"移動種別: {travel_kind}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"移動元: {source_name}\n"
                    f"destination_location: {destination_location}\n"
                    f"移動先表示名: {destination_name}\n"
                    f"移動先概要: {destination_description}\n"
                    f"経過時間: {elapsed_hours}時間\n"
                    f"経路: {route_text}\n"
                    f"直近ログ:\n{self.state.log_text(6)}\n"
                    "この直接移動を、現在の物語に合うように描写してください。"
                ),
            },
        ]
        response = self._chat_json(
            "narrator",
            messages,
            max_tokens=500,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )
        response["location"] = destination_location
        self.state.world_data.history.append(
            {
                "manager": "narrator",
                "source": "direct_travel",
                "travel_kind": travel_kind,
                "action": action,
                "input_type": input_type,
                "from": source_name,
                "to": destination_location,
                "destination_name": destination_name,
                "response": _strip_response_metadata(response),
            }
        )
        return response

    def _merge_visual_response(self, base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base or {})
        for key in ("narration", "choices"):
            if key in overlay:
                merged[key] = overlay[key]
        return merged

    def _match_settlement_facility_for_character(
        self,
        settlement: LocationData,
        character: Character,
    ) -> dict[str, Any] | None:
        facilities = self._ensure_settlement_facilities(settlement)
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        raw = extra.get("raw_create_settlement_detail_entry")
        raw = raw if isinstance(raw, dict) else {}
        explicit_facility = str(
            raw.get("facility")
            or raw.get("facility_name")
            or raw.get("workplace")
            or raw.get("shop")
            or extra.get("facility")
            or flags.get("facility_name")
            or ""
        ).strip()
        if explicit_facility:
            for facility in facilities:
                if _facility_record_matches_requested(facility, explicit_facility):
                    return facility
        explicit_type = str(
            raw.get("facility_type")
            or raw.get("workplace_type")
            or extra.get("facility_type")
            or flags.get("facility_type")
            or ""
        ).strip().lower()
        if explicit_type:
            for facility in facilities:
                if str(facility.get("type") or "").strip().lower() == explicit_type:
                    return facility

        name = str(character.name or "").strip()
        role = str(character.role or "").strip()
        text_blob = "\n".join(
            str(value or "")
            for value in (
                name,
                role,
                character.backstory,
                character.personality,
                character.look,
                raw.get("description"),
                raw.get("summary"),
                raw.get("job"),
                raw.get("occupation"),
            )
        )
        folded_blob = text_blob.casefold()
        inferred_type = _facility_type_from_name(text_blob)
        for facility in facilities:
            npc_name = str(facility.get("npc_name") or "").strip()
            if npc_name and name and _clean_generated_name(npc_name, "", kind="character") == _clean_generated_name(name, "", kind="character"):
                return facility
            npc_role = str(facility.get("npc_role") or "").strip()
            if npc_role and role and (npc_role in role or role in npc_role):
                return facility
            facility_name = str(facility.get("name") or "").strip()
            if facility_name and _facility_name_matches(facility_name, text_blob):
                return facility
            aliases = _as_str_list(facility.get("aliases"))
            if any(alias and alias.casefold() in folded_blob for alias in aliases):
                return facility
            facility_type = str(facility.get("type") or "").strip().lower()
            if inferred_type not in {"facility", "guild"} and facility_type == inferred_type:
                return facility
        return None

    def _stamp_character_facility_subnode(
        self,
        character: Character,
        settlement: LocationData,
        facility: dict[str, Any],
    ) -> str:
        facility_name = str(facility.get("name") or "")
        facility_type = str(facility.get("type") or _facility_type_from_name(facility_name))
        character.flags["facility_name"] = facility_name
        character.flags["facility_type"] = facility_type
        character.extra["facility"] = facility_name
        character.extra["facility_type"] = facility_type
        character.extra["parent_settlement"] = settlement.name
        subnode_id = self._facility_subnode_id(facility)
        self._set_character_subnode_fields(character, settlement.name, subnode_id)
        return subnode_id

    def _assign_settlement_character_subnode(
        self,
        world: WorldData,
        settlement: LocationData,
        character: Character,
    ) -> str:
        facility = self._match_settlement_facility_for_character(settlement, character)
        if facility:
            return self._stamp_character_facility_subnode(character, settlement, facility)
        graph = self._ensure_location_subnode_graph(world, settlement.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        subnode_id = DEFAULT_SUBNODE_ID if DEFAULT_SUBNODE_ID in nodes else next(iter(nodes), DEFAULT_SUBNODE_ID)
        self._set_character_subnode_fields(character, settlement.name, subnode_id)
        return subnode_id

    def _ensure_facility_npc(self, settlement: LocationData, facility: dict[str, Any], location_name: str) -> Character | None:
        return npc_generate.ensure_facility_npc(self, settlement, facility, location_name)

    def _set_player_presence(self, location: str) -> None:
        player = self.player_character()
        subnode_id = self._runtime_subnode_for_presence(location)
        if player:
            self._set_character_presence(player, location, subnode_id=subnode_id)
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["location"] = location
            flags = self.state.party[0].setdefault("flags", {})
            if isinstance(flags, dict):
                flags["current_location"] = location
                if subnode_id:
                    flags[ACTOR_SUBNODE_ID_FLAG] = subnode_id
                    flags[ACTOR_SUBNODE_LOCATION_FLAG] = location
        for companion in self._party_companions():
            self._set_character_presence(companion, location, "party", subnode_id=subnode_id)
        self._sync_quest_objective_escorts(location, subnode_id=subnode_id)

    def _ensure_world_location_graph(
        self,
        world: WorldData,
        response: dict[str, Any] | None = None,
        premise: str = "",
        target_count: int = DEFAULT_WORLD_LOCATION_COUNT,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_start: int = 0,
        progress_end: int = 100,
    ) -> dict[str, Any]:
        target_count = _world_location_target_count(target_count)
        graph = world.extra.get("location_graph")
        if (
            isinstance(graph, dict)
            and graph.get("generation_mode") == "route_skeleton"
            and isinstance(graph.get("nodes"), dict)
            and isinstance(graph.get("edges"), list)
        ):
            for name, location in world.locations.items():
                self._set_location_graph_node(world, name, location=location)
            self._recalculate_world_graph_layout(world)
            return graph
        if (
            isinstance(graph, dict)
            and isinstance(graph.get("nodes"), dict)
            and isinstance(graph.get("edges"), list)
            and (response is None or len(graph.get("nodes", {})) >= target_count)
        ):
            for name, location in world.locations.items():
                self._set_location_graph_node(world, name, location=location)
            self._recalculate_world_graph_layout(world)
            return graph

        rng = random.Random(f"{world.world_name}|{premise}|{target_count}")
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        world.extra["location_graph"] = {
            "edge_hours": WORLD_MAP_EDGE_HOURS,
            "target_count": target_count,
            "nodes": nodes,
            "edges": edges,
        }

        raw_locations = _world_location_payloads(response or {})
        self._emit_world_generation_progress(
            progress_callback,
            "location_graph",
            f"ロケーションを生成中（0/{target_count}）",
            progress_start,
            100,
            item_current=0,
            item_total=target_count,
        )
        pending_facilities: list[tuple[str, str, str]] = []
        for payload in raw_locations:
            name = _world_location_name_from_payload(payload)
            if not name:
                continue
            description = _world_location_description_from_payload(payload)
            kind = _infer_world_location_kind_for_world_generation(premise, payload, name, description)
            danger = _world_generation_location_danger(payload, name, description, premise, len(nodes), target_count, rng)
            if kind == "facility" and _add_facility_payload_to_settlement(world, name, description, str(payload.get("type") or payload.get("facility_type") or "")):
                continue
            if kind == "facility":
                pending_facilities.append((name, description, str(payload.get("type") or payload.get("facility_type") or "")))
                continue
            dungeon_parent = _existing_dungeon_location_for_subarea(world, name)
            if dungeon_parent:
                _record_location_subarea(world, dungeon_parent, name, description)
                continue
            location = world.ensure_location(name, description)
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = danger
            location.extra["world_generation_payload"] = dict(payload)
            location.flags["discovered"] = bool(name == world.starting_location)
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
            if kind == "dungeon":
                location.flags["dungeon"] = True
            self._set_location_graph_node(world, name, kind=kind, danger=danger, location=location)
            completed = min(len(nodes), target_count)
            percent = progress_start + int((progress_end - progress_start) * completed / max(1, target_count))
            self._emit_world_generation_progress(
                progress_callback,
                "location_graph",
                f"ロケーションを生成中（{completed}/{target_count}）",
                percent,
                100,
                item_current=completed,
                item_total=target_count,
            )

        for name, location in list(world.locations.items()):
            self._set_location_graph_node(world, name, location=location)

        if world.starting_location and world.starting_location != "unknown":
            world.ensure_location(world.starting_location)
            self._set_location_graph_node(world, world.starting_location, kind="settlement", danger=0)

        for name, description, facility_type in pending_facilities:
            _add_facility_payload_to_settlement(world, name, description, facility_type)

        for payload in _world_connection_payloads(response or {}):
            a = str(payload.get("from") or payload.get("source") or payload.get("a") or "").strip()
            b = str(payload.get("to") or payload.get("target") or payload.get("b") or "").strip()
            if a and b and a in nodes and b in nodes:
                self._connect_world_locations(world, a, b, hours=WORLD_MAP_EDGE_HOURS)

        if len(nodes) < target_count:
            self._generate_world_location_batches(
                world,
                premise,
                target_count,
                progress_callback=progress_callback,
                progress_start=progress_start,
                progress_end=progress_end,
                rng=rng,
            )

        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes")
        if not isinstance(nodes, dict):
            nodes = {}
            graph["nodes"] = nodes

        fallback_index = 1
        fallback_guard = max(target_count * 2, 10)
        while len(nodes) < target_count and fallback_index <= fallback_guard:
            kind = _fallback_world_location_kind(rng, len(nodes))
            name = _unique_world_location_name(world, _fallback_world_location_name(kind, fallback_index))
            fallback_index += 1
            danger = _world_default_danger_for_index(len(nodes), target_count, rng)
            description = _fallback_world_location_description(kind, danger)
            location = world.ensure_location(name, description)
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = danger
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
            if kind == "dungeon":
                location.flags["dungeon"] = True
            self._set_location_graph_node(world, name, kind=kind, danger=danger, location=location)
            graph = self._location_graph_for_update(world)
            nodes = graph.get("nodes")
            if not isinstance(nodes, dict):
                nodes = {}
                graph["nodes"] = nodes
            completed = min(len(nodes), target_count)
            percent = progress_start + int((progress_end - progress_start) * completed / max(1, target_count))
            self._emit_world_generation_progress(
                progress_callback,
                "location_graph",
                f"ロケーションを生成中（{completed}/{target_count}）",
                percent,
                100,
                item_current=completed,
                item_total=target_count,
            )

        if len(nodes) < target_count:
            errors = world.extra.setdefault("location_generation_errors", [])
            if isinstance(errors, list):
                errors.append(
                    {
                        "stage": "fallback",
                        "error": f"location graph stopped at {len(nodes)}/{target_count}",
                    }
                )

        for payload in _world_connection_payloads(response or {}):
            a = str(payload.get("from") or payload.get("source") or payload.get("a") or "").strip()
            b = str(payload.get("to") or payload.get("target") or payload.get("b") or "").strip()
            if a and b and a in nodes and b in nodes:
                self._connect_world_locations(world, a, b, hours=WORLD_MAP_EDGE_HOURS)

        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes")
        if not isinstance(nodes, dict):
            nodes = {}
            graph["nodes"] = nodes
        ordered_names = list(nodes)
        start = world.starting_location if world.starting_location in nodes else (ordered_names[0] if ordered_names else "")
        connected = {start} if start else set()
        for name in ordered_names:
            if not name or name in connected:
                continue
            candidates = [item for item in ordered_names if item in connected] or ordered_names[:1]
            parent = min(candidates, key=lambda item: (len(self._world_neighbors(world, item)), rng.random()))
            self._connect_world_locations(world, parent, name, hours=WORLD_MAP_EDGE_HOURS)
            connected.add(name)
        self._ensure_world_generation_dungeon_content(world, premise, progress_callback=progress_callback, progress_value=progress_end)
        self._recalculate_world_graph_layout(world)
        return world.extra["location_graph"]

    def _ensure_world_generation_dungeon_content(
        self,
        world: WorldData,
        premise: str,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_value: int = 45,
    ) -> None:
        dungeon_names: list[str] = []
        for name, location in list(world.locations.items()):
            payload = location.extra.get("world_generation_payload") if isinstance(location.extra, dict) else {}
            payload_dict = payload if isinstance(payload, dict) else {}
            kind = _infer_world_location_kind_for_world_generation(premise, payload_dict, name, location.description)
            if kind == "dungeon":
                location.extra["location_kind"] = "dungeon"
                location.flags["dungeon"] = True
                self._set_location_graph_node(world, name, kind="dungeon", location=location)
            if _is_dungeon_location(location):
                dungeon_names.append(name)
        for index, name in enumerate(dungeon_names, start=1):
            location = world.locations.get(name)
            if not location:
                continue
            self._emit_world_generation_progress(
                progress_callback,
                "dungeon_subnodes",
                f"ダンジョン仕上げ中({index}/{len(dungeon_names)})",
                progress_value,
                100,
                item_current=index,
                item_total=len(dungeon_names),
            )
            graph = self._ensure_location_subnode_graph(world, name)
            if graph:
                graph.setdefault("created_for_world_generation", True)
            boss_event = self._ensure_world_generation_dungeon_boss(world, name, premise)
            if boss_event:
                world.history.append(
                    {
                        "manager": "world_generation_dungeon_boss",
                        "location": name,
                        "boss": boss_event,
                    }
                )

    def _world_generation_dungeon_boss_response(
        self,
        world: WorldData,
        location: LocationData,
        premise: str,
    ) -> dict[str, Any]:
        if self.llm is None:
            return {}
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        subnodes = [
            {
                "id": str(node_id),
                "name": str(node.get("name") or ""),
                "kind": str(node.get("kind") or ""),
                "description": _short_text(str(node.get("description") or ""), 180),
            }
            for node_id, node in nodes.items()
            if isinstance(node, dict)
        ]
        raw_theme = world.extra.get("raw_create_world_theme") if isinstance(world.extra, dict) else {}
        danger = max(5, _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0))
        npc_template_payload = json.dumps(
            {
                "enemy_templates": npc_template_prompt_summaries(
                    ENEMY_NPC_TEMPLATE_CATEGORIES,
                    danger_level=danger,
                    used_ids=used_npc_template_ids(world),
                    limit=12,
                )
            },
            ensure_ascii=False,
        )
        prompt = {
            "world": _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True, location_limit=10),
            "premise": _short_text(premise, 2000),
            "final_destination_concept": str((raw_theme or {}).get("final_destination_concept") or ""),
            "final_dungeon": {
                "name": location.name,
                "description": _short_text(location.description, 900),
                "danger_level": danger,
                "subnodes": subnodes,
                "boss_subnode_id": DUNGEON_DEEPEST_SUBNODE_ID,
            },
            "requirements": {
                "return_key": "boss_npc",
                "language": "Japanese",
                "hostile": True,
                "boss_should_reflect": ["world premise", "final_destination_concept", "final dungeon name", "final dungeon description"],
                "required_boss_fields": [
                    "name",
                    "role",
                    "description",
                    "gender",
                    "age",
                    "look",
                    "personality",
                    "image_generation_prompt",
                    "hostile",
                    "npc_template_id",
                ],
            },
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Generate exactly one final dungeon boss for Fantasia world generation. "
                    "Return compact JSON only with a boss_npc object. "
                    "The boss must fit the world setting and the final destination concept. "
                    "Do not create locations, quests, rewards, or map changes."
                ),
            },
            {"role": "user", "content": _ai_json(prompt)},
            {
                "role": "system",
                "content": (
                    f"NPC template candidates: {npc_template_payload}\n"
                    "Prefer a matching enemy template when possible and include npc_template_id. "
                    "If no template matches, still generate a complete boss_npc."
                ),
            },
        ]
        return self._chat_json(
            "world_generation_dungeon_boss",
            messages,
            max_tokens=900,
            world_name=world.world_name,
            player_name=self.state.player_name,
        )

    def _ensure_world_generation_dungeon_boss(
        self,
        world: WorldData,
        location_name: str,
        premise: str,
    ) -> dict[str, str] | None:
        location = world.locations.get(str(location_name or "").strip())
        if not location or not _is_dungeon_location(location):
            return None
        if _world_generation_dungeon_has_boss(world, location.name):
            return None
        raw_payload = location.extra.get("world_generation_payload") if isinstance(location.extra, dict) else {}
        response = dict(raw_payload) if isinstance(raw_payload, dict) else {}
        response.setdefault("narration", location.description)
        response.setdefault("location", location.name)
        is_final_destination = self._local_world_node_is_final_destination(location)
        premise_context = premise if is_final_destination or _world_generation_premise_refers_to_location(premise, location.name) else ""
        boss_required = is_final_destination or _generated_dungeon_boss_required(premise_context, response, location)
        boss_payload = _generated_dungeon_boss_payload(response)
        if not boss_payload and boss_required:
            boss_response = self._world_generation_dungeon_boss_response(world, location, premise_context or premise)
            if boss_response:
                response["world_generation_boss_response"] = _strip_response_metadata(boss_response)
                boss_payload = _generated_dungeon_boss_payload(boss_response)
        if not boss_payload and not boss_required:
            return None
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        target_subnode = DUNGEON_DEEPEST_SUBNODE_ID if DUNGEON_DEEPEST_SUBNODE_ID in nodes else self._default_subnode_for_location(location)
        if not target_subnode:
            return None
        boss_payload = boss_payload or _fallback_generated_dungeon_boss_payload(location, premise_context, response)
        danger = max(1, _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0))
        boss_payload = self._template_augmented_npc_raw(
            boss_payload,
            categories=ENEMY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger,
            seed=f"world-generation-boss:{world.world_name}:{location.name}",
            hostile=True,
            boss=True,
        )
        character = _enemy_npc_from_raw(boss_payload, len(world.characters))
        character.name = _unique_character_name(world, character.name)
        character.role = str(character.role or "ダンジョンボス")
        character.category = "enemy_npc"
        character.flags["enemy_npc"] = True
        character.flags["hostile"] = _as_bool(character.flags.get("hostile") if "hostile" in character.flags else True)
        character.flags["generated_dungeon_boss"] = True
        character.flags["world_generation_boss"] = True
        character.flags["danger_level"] = danger
        character.extra["generated_dungeon_boss"] = True
        character.extra["world_generation_boss"] = True
        character.extra["boss_location"] = location.name
        character.extra["danger_level"] = danger
        character.extra["spawn_subnode_id"] = target_subnode
        character.extra["origin_subnode_id"] = target_subnode
        character.extra["display_alias"] = str(character.extra.get("display_alias") or "ボス")
        character.extra["aliases"] = _dedupe_strs([character.name, "ボス", "守護者", *[str(value) for value in _as_list(character.extra.get("aliases"))]])
        character.level = max(_safe_int(character.level, 1), _generated_dungeon_boss_level(location))
        self._finalize_generated_npc(
            character,
            location_name=location.name,
            danger_level=danger,
            role_hint="world_generation_boss",
            boss=True,
        )
        character.location = location.name
        character.state = "present"
        character.flags["state"] = character.state
        character.flags["alive"] = True
        character.flags["current_location"] = location.name
        character.flags.setdefault("first_seen_location", location.name)
        character.extra.setdefault("origin_location", location.name)
        self._set_character_subnode_fields(character, location.name, target_subnode)
        world.add_character(character)
        generated_bosses = location.extra.get("generated_bosses")
        if not isinstance(generated_bosses, list):
            generated_bosses = []
            location.extra["generated_bosses"] = generated_bosses
        generated_bosses.append(
            {
                "uuid": character.uuid,
                "name": character.name,
                "subnode_id": target_subnode,
                "source": "world_generation_dungeon_boss",
            }
        )
        return {"type": "character", "name": character.name, "role": "boss", "location": location.name, "subnode": target_subnode}

    def _ensure_final_destination_boss(self, world: WorldData, premise: str) -> dict[str, str] | None:
        location_name = ""
        for spec in self._route_skeleton_specs(world):
            if str(spec.get("role") or "") == "final_destination":
                location_name = str(spec.get("name") or "").strip()
                break
        if not location_name:
            for name, location in world.locations.items():
                if self._local_world_node_is_final_destination(location):
                    location_name = name
                    break
        if not location_name:
            return None
        location = world.locations.get(location_name)
        if not location:
            return None
        location.extra["location_kind"] = "dungeon"
        location.extra["boss_required"] = True
        location.extra["final_destination"] = True
        location.flags["dungeon"] = True
        location.flags["dangerous"] = True
        location.flags["final_destination"] = True
        if SUBNODE_GRAPH_KEY not in location.extra:
            self._install_local_dungeon_subnode_graph(location, random.Random(f"final-dungeon:{world.world_name}:{location.name}"))
        return self._ensure_world_generation_dungeon_boss(world, location.name, premise)

    def _generate_world_location_batches(
        self,
        world: WorldData,
        premise: str,
        target_count: int,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_start: int = 0,
        progress_end: int = 100,
        rng: random.Random | None = None,
    ) -> None:
        if self.llm is None:
            return
        rng = rng or random.Random(f"{world.world_name}|location_batches|{target_count}")
        graph = self._location_graph_for_update(world)
        nodes = graph.setdefault("nodes", {})
        batch_history: list[dict[str, Any]] = []
        failures = 0
        batch_index = 1
        max_batches = max(1, ((target_count - len(nodes)) + WORLD_LOCATION_BATCH_MIN - 1) // WORLD_LOCATION_BATCH_MIN + 4)
        while len(nodes) < target_count and batch_index <= max_batches:
            remaining = max(0, target_count - len(nodes))
            batch_size = _world_location_batch_size(remaining)
            if batch_size <= 0:
                break
            context = self._world_location_batch_context(
                world,
                premise,
                target_count=target_count,
                batch_size=batch_size,
                batch_index=batch_index,
            )
            completed = min(len(nodes), target_count)
            percent = progress_start + int((progress_end - progress_start) * completed / max(1, target_count))
            self._emit_world_generation_progress(
                progress_callback,
                "location_graph",
                f"AI location batch {batch_index}: {completed}/{target_count}",
                percent,
                100,
                item_current=completed,
                item_total=target_count,
            )
            messages = [
                {
                    "role": "system",
                "content": (
                    "You expand Fantasia's world map in small batches. Generate only the requested nearby "
                    "locations and connections. Preserve the existing world tone, terrain, danger curve, and "
                    "unique important locations. Town facilities are not world locations; keep inns, guilds, "
                    "shops, and blacksmiths inside settlement facility data. Dungeon entrances/interiors/depths "
                    "are subareas of one dungeon location. Use danger 0-50; final destinations/final temples/final "
                    "boss areas should be danger 40-45. If an explicit temple/shrine is a dungeon or boss location, "
                    "return kind=dungeon, not facility. Return JSON only."
                ),
            },
                {
                    "role": "user",
                    "content": _ai_json(context),
                },
            ]
            try:
                response = self._chat_json(
                    "create_world_location_batch",
                    messages,
                    max_tokens=_world_location_batch_max_tokens(batch_size),
                    world_name=world.world_name,
                    player_name="world_builder",
                    retries=1,
                )
            except Exception as exc:
                failures += 1
                errors = world.extra.setdefault("location_generation_errors", [])
                if isinstance(errors, list):
                    errors.append({"batch": batch_index, "error": str(exc)})
                if failures >= 2:
                    break
                batch_index += 1
                continue
            added_names = self._apply_world_location_batch(
                world,
                response,
                premise=premise,
                target_count=target_count,
                anchor_names=[str(item) for item in context.get("anchor_names", [])],
            )
            if not added_names:
                failures += 1
                if failures >= 2:
                    break
            else:
                failures = 0
                batch_history.append(
                    {
                        "batch": batch_index,
                        "added_locations": added_names,
                        "response": _strip_response_metadata(response),
                    }
                )
                completed = min(len(nodes), target_count)
                percent = progress_start + int((progress_end - progress_start) * completed / max(1, target_count))
                self._emit_world_generation_progress(
                    progress_callback,
                    "location_graph",
                    f"AI location batch {batch_index}: {completed}/{target_count}",
                    percent,
                    100,
                    item_current=completed,
                    item_total=target_count,
                )
            batch_index += 1
        if batch_history:
            world.extra["location_generation_batches"] = batch_history

    def _world_location_batch_context(
        self,
        world: WorldData,
        premise: str,
        *,
        target_count: int,
        batch_size: int,
        batch_index: int,
    ) -> dict[str, Any]:
        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        anchor_names = self._world_location_batch_anchors(world, limit=6)
        existing_names = list(nodes.keys())
        important_names = [
            name
            for name, node in nodes.items()
            if isinstance(node, dict)
            and (
                name == world.starting_location
                or _safe_int(node.get("danger"), 0) >= 30
                or str(node.get("kind") or "").strip().lower() in {"settlement", "dungeon", "landmark"}
            )
        ][:18]
        return {
            "world_name": world.world_name,
            "world_overview": _short_text(world.overview, 900),
            "structure_description": _short_text(world.structure_description, 900),
            "world_structure": _compact_value(world.structure, max_chars=1400),
            "premise": _short_text(premise, 1200),
            "customization": _world_customization_settings(
                world.extra.get("crime_risk") if isinstance(world.extra, dict) else DEFAULT_WORLD_CRIME_RISK,
                world.extra.get("enemy_strength") if isinstance(world.extra, dict) else DEFAULT_WORLD_ENEMY_STRENGTH,
            ),
            "starting_location": world.starting_location,
            "target_count": target_count,
            "generated_count": len(nodes),
            "remaining_count": max(0, target_count - len(nodes)),
            "requested_batch_size": batch_size,
            "batch_index": batch_index,
            "generated_summary": self._world_location_generation_summary(world),
            "anchor_names": anchor_names,
            "nearby_locations": [self._world_location_node_context(world, name) for name in anchor_names],
            "kind_options": _world_location_kind_guidance(),
            "naming_rule": (
                "Use the world tone, nearby terrain, local culture, role, and danger to invent new fantasy location names. "
                "Do not use a preset candidate list or repeat names/motifs such as 白石街道, 緑瓦の宿場, or アルテミス unless the user explicitly specified them."
            ),
            "important_existing_locations": [self._world_location_node_context(world, name) for name in important_names],
            "recent_existing_locations": [
                self._world_location_node_context(world, name)
                for name in existing_names[-24:]
                if name not in important_names
            ],
            "existing_location_names": existing_names[-80:],
            "enemy_npc_templates": npc_template_prompt_summaries(
                ENEMY_NPC_TEMPLATE_CATEGORIES,
                danger_level=50,
                used_ids=self._npc_template_used_ids(world),
                limit=16,
            ),
            "rules": [
                "Generate only new locations. Never reuse existing_location_names.",
                "Avoid creating multiple versions of unique one-off locations such as the capital, final temple, main shrine, or central dungeon.",
                "Use nearby_locations as the local terrain and route context.",
                "Danger is 0-50 and should usually increase as generated_count grows, with occasional world-appropriate exceptions.",
                "Locations that can be the final destination, final temple, or final boss area should use danger 40-45.",
                "Every generated location must be connected by a 2-hour edge to an existing or same-batch location.",
                "Do not generate town facilities as world-map locations.",
                "Do not split dungeon entrances, interiors, or depths into separate locations.",
                "Use kind_options. Roads, crossroads, coasts, mountains, rivers, and plains are valid world-map location kinds.",
                "Invent names from naming_rule. Avoid fixed preset-like names and repeated mythic motifs such as アルテミス.",
                "If game customization enables crime risk, settlement nodes should include public order cues and may include extra.crime_risk_multiplier between 0.0 and 2.0.",
            ],
        }

    def _world_location_generation_summary(self, world: WorldData) -> str:
        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        kind_counts: dict[str, int] = {}
        high_danger: list[str] = []
        for name, node in nodes.items():
            if not isinstance(node, dict):
                continue
            kind = str(node.get("kind") or "unknown")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            if _safe_int(node.get("danger"), 0) >= 30:
                high_danger.append(str(name))
        parts = [
            f"generated={len(nodes)}",
            f"starting_location={world.starting_location}",
            "kinds=" + ", ".join(f"{kind}:{count}" for kind, count in sorted(kind_counts.items())),
        ]
        if high_danger:
            parts.append("high_danger=" + ", ".join(high_danger[:12]))
        return "; ".join(parts)

    def _world_location_node_context(self, world: WorldData, name: str) -> dict[str, Any]:
        graph = self._location_graph_for_update(world)
        node = graph.get("nodes", {}).get(name, {}) if isinstance(graph.get("nodes"), dict) else {}
        location = world.locations.get(name)
        return {
            "name": name,
            "kind": node.get("kind") if isinstance(node, dict) else "",
            "danger": node.get("danger") if isinstance(node, dict) else 0,
            "description": _short_text((location.description if location else "") or (node.get("description") if isinstance(node, dict) else ""), 220),
            "neighbors": self._world_neighbors_no_ensure(world, name)[:8],
        }

    def _world_location_batch_anchors(self, world: WorldData, *, limit: int = 6) -> list[str]:
        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if not nodes:
            return [world.starting_location] if world.starting_location else []

        def score(name: str) -> tuple[int, int, int, str]:
            node = nodes.get(name, {}) if isinstance(nodes, dict) else {}
            degree = len(self._world_neighbors_no_ensure(world, name))
            danger = _safe_int(node.get("danger"), 0) if isinstance(node, dict) else 0
            start_bonus = 0 if name == world.starting_location else 1
            return (degree, start_bonus, danger, name)

        return sorted([str(name) for name in nodes.keys()], key=score)[:limit]

    def _apply_world_location_batch(
        self,
        world: WorldData,
        response: dict[str, Any],
        *,
        premise: str = "",
        target_count: int,
        anchor_names: list[str],
    ) -> list[str]:
        graph = self._location_graph_for_update(world)
        nodes = graph.setdefault("nodes", {})
        existing_keys = {_world_location_name_key(name) for name in world.locations.keys()}
        added_names: list[str] = []
        payloads = _world_location_payloads({"locations": response.get("locations")})
        for payload in payloads:
            if len(nodes) >= target_count:
                break
            name = _world_location_name_from_payload(payload)
            if not name:
                continue
            name_key = _world_location_name_key(name)
            if not name_key or name_key in existing_keys:
                continue
            description = _world_location_description_from_payload(payload)
            kind = _infer_world_location_kind_for_world_generation(premise, payload, name, description)
            danger = _world_generation_location_danger(payload, name, description, premise, len(nodes), target_count)
            if kind == "facility" and _add_facility_payload_to_settlement(world, name, description, str(payload.get("type") or payload.get("facility_type") or "")):
                continue
            dungeon_parent = _existing_dungeon_location_for_subarea(world, name)
            if dungeon_parent:
                _record_location_subarea(world, dungeon_parent, name, description)
                continue
            if not any(key in payload for key in ("danger", "danger_level", "threat", "threat_level", "difficulty", "rank")):
                danger = _world_default_danger_for_index(len(nodes), target_count)
            location = world.ensure_location(name, description)
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = danger
            location.extra["world_generation_payload"] = dict(payload)
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
            if kind == "dungeon":
                location.flags["dungeon"] = True
            self._set_location_graph_node(world, name, kind=kind, danger=danger, location=location)
            existing_keys.add(name_key)
            added_names.append(name)

        for payload in _world_connection_payloads(response):
            a = str(payload.get("from") or payload.get("source") or payload.get("a") or "").strip()
            b = str(payload.get("to") or payload.get("target") or payload.get("b") or "").strip()
            if a and b and a in nodes and b in nodes:
                self._connect_world_locations(world, a, b, hours=WORLD_MAP_EDGE_HOURS)

        anchors = [name for name in anchor_names if name in nodes]
        if not anchors and world.starting_location in nodes:
            anchors = [world.starting_location]
        for index, name in enumerate(added_names):
            if self._world_neighbors_no_ensure(world, name):
                continue
            parent = anchors[index % len(anchors)] if anchors else ""
            if parent and parent != name:
                self._connect_world_locations(world, parent, name, hours=WORLD_MAP_EDGE_HOURS)
        return added_names

    def _set_location_graph_node(
        self,
        world: WorldData,
        name: str,
        *,
        kind: str = "",
        danger: int | None = None,
        location: LocationData | None = None,
    ) -> dict[str, Any]:
        graph = world.extra.setdefault("location_graph", {"edge_hours": WORLD_MAP_EDGE_HOURS, "nodes": {}, "edges": []})
        nodes = graph.setdefault("nodes", {})
        key = str(name or "").strip()
        if not key:
            key = "unknown"
        location = location or world.ensure_location(key)
        extra = location.extra if isinstance(location.extra, dict) else {}
        resolved_kind = kind or str(extra.get("location_kind") or extra.get("kind") or extra.get("type") or "").strip()
        if not resolved_kind:
            resolved_kind = _infer_world_location_kind({}, key, location.description)
        node = nodes.setdefault(key, {})
        grid_x = extra.get("grid_x", node.get("grid_x"))
        grid_y = extra.get("grid_y", node.get("grid_y"))
        has_grid = grid_x not in (None, "") and grid_y not in (None, "")
        grid_distance = _safe_int(extra.get("grid_distance", node.get("grid_distance")), -1)
        if has_grid and grid_distance < 0:
            grid_distance = max(abs(_safe_int(grid_x, 0)), abs(_safe_int(grid_y, 0)))
        resolved_danger = _safe_int(extra.get("danger_level"), 0) if danger is None else int(danger)
        danger_source = str(extra.get("danger_source") or node.get("danger_source") or "")
        has_explicit_danger = (
            danger is not None
            or extra.get("danger_level") not in (None, "")
            or node.get("danger") not in (None, "")
        )
        if danger is None and has_grid and not has_explicit_danger and danger_source in {"world_grid", "local_world_skeleton", "dynamic_world_grid"}:
            resolved_danger = self._local_world_danger_for_distance(grid_distance, seed=f"{world.world_name}:{key}:{grid_x}:{grid_y}")
        is_final_destination = self._local_world_node_is_final_destination(location, node)
        if is_final_destination:
            resolved_danger = max(
                _clamp_world_danger(resolved_danger),
                self._local_world_final_danger_for_node(world, key, grid_x, grid_y),
            )
        node.update(
            {
                "name": key,
                "description": _short_text(location.description or str(node.get("description") or ""), 220),
                "kind": resolved_kind,
                "danger": _clamp_world_danger(resolved_danger),
                "visited": bool(location.flags.get("visited") or node.get("visited")),
                "discovered": bool(location.flags.get("discovered") or node.get("discovered")),
            }
        )
        if has_grid:
            node["grid_x"] = _safe_int(grid_x, 0)
            node["grid_y"] = _safe_int(grid_y, 0)
            node["grid_distance"] = grid_distance
            node["danger_source"] = str(extra.get("danger_source") or node.get("danger_source") or "world_grid")
            location.extra["grid_x"] = node["grid_x"]
            location.extra["grid_y"] = node["grid_y"]
            location.extra["grid_distance"] = grid_distance
            location.extra["danger_source"] = node["danger_source"]
        payload = extra.get("world_generation_payload") if isinstance(extra.get("world_generation_payload"), dict) else {}
        role = str(extra.get("role") or payload.get("role") or node.get("role") or "").strip()
        subtype = str(extra.get("main_node_subtype") or payload.get("subtype") or node.get("subtype") or "").strip()
        if role:
            node["role"] = role
            location.extra["role"] = role
        if subtype:
            node["subtype"] = subtype
        if is_final_destination:
            node["role"] = "final_destination"
            node["subtype"] = "final_destination"
            node["boss_required"] = True
            location.extra["role"] = "final_destination"
            location.extra["final_destination"] = True
            location.extra["boss_required"] = True
            location.flags["final_destination"] = True
        if _world_kind_is_settlement(resolved_kind):
            location.flags["settlement"] = True
        location.extra["location_kind"] = resolved_kind
        location.extra["danger_level"] = node["danger"]
        return node

    def _location_graph_for_update(self, world: WorldData) -> dict[str, Any]:
        graph = world.extra.get("location_graph")
        if isinstance(graph, dict) and isinstance(graph.get("nodes"), dict) and isinstance(graph.get("edges"), list):
            return graph
        graph = {
            "edge_hours": WORLD_MAP_EDGE_HOURS,
            "target_count": max(len(world.locations), 1),
            "nodes": {},
            "edges": [],
        }
        world.extra["location_graph"] = graph
        for name, location in world.locations.items():
            self._set_location_graph_node(world, name, location=location)
        return graph

    def _connect_world_locations(
        self,
        world: WorldData,
        a: str,
        b: str,
        *,
        hours: int = WORLD_MAP_EDGE_HOURS,
        kind: str = "road",
    ) -> None:
        a = str(a or "").strip()
        b = str(b or "").strip()
        if not a or not b or a == b:
            return
        graph = self._location_graph_for_update(world)
        self._set_location_graph_node(world, a)
        self._set_location_graph_node(world, b)
        self._assign_world_grid_position_if_missing(world, a, parent=b)
        self._assign_world_grid_position_if_missing(world, b, parent=a)
        self._sync_world_grid_danger(world, a)
        self._sync_world_grid_danger(world, b)
        edge_key = {a, b}
        for edge in graph.setdefault("edges", []):
            if {str(edge.get("from") or ""), str(edge.get("to") or "")} == edge_key:
                edge["hours"] = int(hours or WORLD_MAP_EDGE_HOURS)
                edge.setdefault("kind", kind)
                self._ensure_world_edge_subnodes(world, edge)
                return
        edge = {"from": a, "to": b, "hours": int(hours or WORLD_MAP_EDGE_HOURS), "kind": kind}
        self._ensure_world_edge_subnodes(world, edge)
        graph.setdefault("edges", []).append(edge)

    def _assign_world_grid_position_if_missing(self, world: WorldData, name: str, *, parent: str = "") -> None:
        name = str(name or "").strip()
        if not name:
            return
        graph = self._location_graph_for_update(world)
        nodes = graph.setdefault("nodes", {})
        node = nodes.get(name)
        if not isinstance(node, dict):
            node = self._set_location_graph_node(world, name)
        if node.get("grid_x") not in (None, "") and node.get("grid_y") not in (None, ""):
            return
        location = world.locations.get(name)
        if name == world.starting_location:
            grid_x = 0
            grid_y = 0
        else:
            parent_node = nodes.get(parent) if parent else None
            if not isinstance(parent_node, dict) or parent_node.get("grid_x") in (None, "") or parent_node.get("grid_y") in (None, ""):
                return
            grid_x, grid_y = self._choose_free_world_grid_neighbor(world, _safe_int(parent_node.get("grid_x"), 0), _safe_int(parent_node.get("grid_y"), 0))
        grid_distance = max(abs(grid_x), abs(grid_y))
        danger = self._local_world_danger_for_distance(grid_distance, seed=f"{world.world_name}:{name}:{grid_x}:{grid_y}")
        node.update(
            {
                "grid_x": grid_x,
                "grid_y": grid_y,
                "grid_distance": grid_distance,
                "danger": danger,
                "danger_source": "dynamic_world_grid",
            }
        )
        if location:
            location.extra["grid_x"] = grid_x
            location.extra["grid_y"] = grid_y
            location.extra["grid_distance"] = grid_distance
            location.extra["danger_level"] = danger
            location.extra["danger_source"] = "dynamic_world_grid"

    def _choose_free_world_grid_neighbor(self, world: WorldData, x: int, y: int) -> tuple[int, int]:
        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        occupied = {
            (_safe_int(node.get("grid_x"), 0), _safe_int(node.get("grid_y"), 0))
            for node in nodes.values()
            if isinstance(node, dict) and node.get("grid_x") not in (None, "") and node.get("grid_y") not in (None, "")
        }
        candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        candidates.sort(key=lambda coord: (coord in occupied, max(abs(coord[0]), abs(coord[1])), coord[0], coord[1]))
        for coord in candidates:
            if coord not in occupied:
                return coord
        radius = 2
        while radius < 20:
            ring = [
                (x + dx, y + dy)
                for dx in range(-radius, radius + 1)
                for dy in range(-radius, radius + 1)
                if abs(dx) + abs(dy) == radius
            ]
            ring.sort(key=lambda coord: (max(abs(coord[0]), abs(coord[1])), coord[0], coord[1]))
            for coord in ring:
                if coord not in occupied:
                    return coord
            radius += 1
        return (x + 1, y)

    def _sync_world_grid_danger(self, world: WorldData, name: str) -> None:
        name = str(name or "").strip()
        if not name:
            return
        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        node = nodes.get(name)
        location = world.locations.get(name)
        if not isinstance(node, dict):
            return
        if node.get("grid_x") in (None, "") or node.get("grid_y") in (None, ""):
            return
        grid_x = _safe_int(node.get("grid_x"), 0)
        grid_y = _safe_int(node.get("grid_y"), 0)
        grid_distance = max(abs(grid_x), abs(grid_y))
        danger = self._local_world_danger_for_distance(grid_distance, seed=f"{world.world_name}:{name}:{grid_x}:{grid_y}")
        if self._local_world_node_is_final_destination(location, node):
            danger = max(danger, self._local_world_final_danger_for_node(world, name, grid_x, grid_y))
        node["grid_distance"] = grid_distance
        node["danger"] = danger
        node["danger_source"] = str(node.get("danger_source") or "world_grid")
        if self._local_world_node_is_final_destination(location, node):
            node["role"] = "final_destination"
            node["subtype"] = "final_destination"
            node["boss_required"] = True
        if location:
            location.extra["grid_x"] = grid_x
            location.extra["grid_y"] = grid_y
            location.extra["grid_distance"] = grid_distance
            location.extra["danger_level"] = danger
            location.extra["danger_source"] = str(location.extra.get("danger_source") or node.get("danger_source") or "world_grid")
            if self._local_world_node_is_final_destination(location, node):
                location.extra["role"] = "final_destination"
                location.extra["final_destination"] = True
                location.extra["boss_required"] = True
                location.flags["final_destination"] = True

    def _world_edge_between(self, world: WorldData, a: str, b: str) -> dict[str, Any] | None:
        a = str(a or "").strip()
        b = str(b or "").strip()
        if not a or not b or a == b:
            return None
        graph = self._location_graph_for_update(world)
        edge_key = {a, b}
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if {str(edge.get("from") or ""), str(edge.get("to") or "")} == edge_key:
                self._ensure_world_edge_subnodes(world, edge)
                return edge
        return None

    def _ensure_world_edge_subnodes(self, world: WorldData, edge: dict[str, Any]) -> None:
        a = str(edge.get("from") or "").strip()
        b = str(edge.get("to") or "").strip()
        if not a or not b:
            return
        self._ensure_location_subnode_graph(world, a)
        self._ensure_location_subnode_graph(world, b)
        a_location = world.locations.get(a)
        b_location = world.locations.get(b)
        from_subnode = (
            "gate"
            if _is_settlement_location(a_location)
            else self._declared_world_edge_subnode(edge, "from", a) or self._default_external_source_subnode(world, a, b)
        )
        to_subnode = (
            "gate"
            if _is_settlement_location(b_location)
            else self._declared_world_edge_subnode(edge, "to", b) or self._default_external_target_subnode(world, b, a)
        )
        if from_subnode:
            edge["from_subnode"] = from_subnode
            edge.setdefault("subnodes", {})[a] = from_subnode
        if to_subnode:
            edge["to_subnode"] = to_subnode
            edge.setdefault("subnodes", {})[b] = to_subnode

    def _world_edge_subnode_for_location(self, world: WorldData, edge: dict[str, Any], location_name: str) -> str:
        location_name = str(location_name or "").strip()
        a = str(edge.get("from") or "").strip()
        b = str(edge.get("to") or "").strip()
        self._ensure_world_edge_subnodes(world, edge)
        if location_name == a:
            return self._declared_world_edge_subnode(edge, "from", location_name)
        if location_name == b:
            return self._declared_world_edge_subnode(edge, "to", location_name)
        return ""

    def _current_subnode_can_reach_world_edge(self, world: WorldData, location_name: str, edge: dict[str, Any]) -> bool:
        graph = self._ensure_location_subnode_graph(world, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        source = self._world_edge_subnode_for_location(world, edge, location_name)
        if not source or source not in nodes:
            return False
        current = self._current_subnode_id(location_name)
        if current == source:
            return True
        movement = str(graph.get("movement") or "adjacent")
        if movement == "free":
            return self._subnode_reachable(graph, current, source)
        return False

    def _world_path_subnode_route(self, world: WorldData, path: list[str]) -> list[dict[str, Any]] | None:
        if len(path) < 2:
            return []
        route: list[dict[str, Any]] = []
        current_subnodes: dict[str, str] = {path[0]: self._current_subnode_id(path[0])}
        for current, target in zip(path, path[1:]):
            edge = self._world_edge_between(world, current, target)
            if not edge:
                return None
            source_subnode = self._world_edge_subnode_for_location(world, edge, current)
            target_subnode = self._world_edge_subnode_for_location(world, edge, target)
            if not source_subnode or not target_subnode:
                return None
            graph = self._ensure_location_subnode_graph(world, current)
            movement = str(graph.get("movement") or "adjacent")
            current_subnode = current_subnodes.get(current) or self._current_subnode_id(current)
            if current_subnode != source_subnode:
                if movement != "free" or not self._subnode_reachable(graph, current_subnode, source_subnode):
                    return None
            route.append(
                {
                    "from": current,
                    "to": target,
                    "from_subnode": source_subnode,
                    "to_subnode": target_subnode,
                    "edge": edge,
                }
            )
            current_subnodes[target] = target_subnode
        return route

    def _world_neighbors(self, world: WorldData, location: str) -> list[str]:
        graph = self._location_graph_for_update(world)
        name = str(location or "").strip()
        neighbors: list[str] = []
        for edge in graph.get("edges", []):
            a = str(edge.get("from") or "").strip()
            b = str(edge.get("to") or "").strip()
            if a == name and b:
                neighbors.append(b)
            elif b == name and a:
                neighbors.append(a)
        return _dedupe_strs(neighbors)

    def _mark_location_visited(self, world: WorldData, location: str) -> None:
        name = str(location or "").strip()
        if not name:
            return
        location_data = world.ensure_location(name)
        location_data.flags["visited"] = True
        location_data.flags["discovered"] = True
        node = self._set_location_graph_node(world, name, location=location_data)
        node["visited"] = True
        visited = world.extra.setdefault("visited_locations", [])
        if isinstance(visited, list) and name not in visited:
            visited.append(name)

    def _reveal_all_world_map_locations(self, world: WorldData) -> None:
        graph = self._location_graph_for_update(world)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        for name, node in nodes.items():
            if not isinstance(node, dict) or _world_graph_node_is_facility(world, node):
                continue
            location = world.locations.get(str(name))
            if location:
                location.flags["discovered"] = True
            node["discovered"] = True
        world.extra["world_map_revealed_on_generation"] = True

    def _recalculate_world_graph_layout(self, world: WorldData) -> None:
        graph = world.extra.get("location_graph")
        if not isinstance(graph, dict):
            return
        nodes = graph.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            return
        start = world.starting_location if world.starting_location in nodes else next(iter(nodes))
        depths: dict[str, int] = {start: 0}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for neighbor in self._world_neighbors_no_ensure(world, current):
                if neighbor in depths:
                    continue
                depths[neighbor] = depths[current] + 1
                queue.append(neighbor)
        levels: dict[int, list[str]] = {}
        for name in nodes:
            depth = depths.get(name, max(depths.values(), default=0) + 1)
            nodes[name]["depth"] = depth
            levels.setdefault(depth, []).append(name)
        for depth, names in levels.items():
            names.sort()
            for index, name in enumerate(names):
                nodes[name]["x"] = 80 + depth * 170
                nodes[name]["y"] = 80 + index * 130 + (depth % 2) * 48

    def _world_neighbors_no_ensure(self, world: WorldData, location: str) -> list[str]:
        graph = world.extra.get("location_graph")
        if not isinstance(graph, dict):
            return []
        name = str(location or "").strip()
        result: list[str] = []
        for edge in graph.get("edges", []):
            a = str(edge.get("from") or "").strip()
            b = str(edge.get("to") or "").strip()
            if a == name and b:
                result.append(b)
            elif b == name and a:
                result.append(a)
        return _dedupe_strs(result)

    def _location_uses_subnodes(self, location: LocationData | None) -> bool:
        # World edges are resolved at subnode endpoints, so every location owns
        # at least one hidden center node. Single-node locations still hide the
        # subnode map in the UI.
        return location is not None

    def _ensure_location_subnode_graph(self, world: WorldData, location_name: str) -> dict[str, Any]:
        name = str(location_name or "").strip()
        location = world.locations.get(name) if name else None
        if not self._location_uses_subnodes(location):
            return {}
        assert location is not None
        raw_graph = location.extra.get(SUBNODE_GRAPH_KEY)
        graph = raw_graph if isinstance(raw_graph, dict) else {}
        nodes = graph.get("nodes")
        if not isinstance(nodes, dict):
            nodes = {}
        edges = graph.get("edges")
        if not isinstance(edges, list):
            edges = []
        graph["version"] = 1
        graph["nodes"] = nodes
        graph["edges"] = edges
        graph["movement"] = "free" if self._location_subnodes_are_free(location) else "adjacent"
        if _is_settlement_location(location):
            self._ensure_settlement_subnodes(location, graph)
        elif _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location):
            self._ensure_dungeon_subnodes(location, graph)
        else:
            self._ensure_basic_subnodes(location, graph)
        default_id = self._default_subnode_for_location(location)
        if str(graph.get("current") or "") not in nodes:
            graph["current"] = default_id if default_id in nodes else next(iter(nodes), DEFAULT_SUBNODE_ID)
        location.extra[SUBNODE_GRAPH_KEY] = graph
        return graph

    def _location_subnodes_are_free(self, location: LocationData) -> bool:
        if _is_settlement_location(location) and not _world_location_blocks_world_map_departure(location):
            return True
        kind = str(location.extra.get("location_kind") or "").strip().lower()
        return kind in {"facility", "shop", "inn", "guild", "temple", "clinic", "market"}

    def _ensure_basic_subnodes(self, location: LocationData, graph: dict[str, Any]) -> None:
        self._upsert_subnode_node(
            graph,
            DEFAULT_SUBNODE_ID,
            location.name,
            location.description,
            "center",
            80,
            120,
            world_map_exit=True,
        )

    def _ensure_settlement_subnodes(self, location: LocationData, graph: dict[str, Any]) -> None:
        self._upsert_subnode_node(
            graph,
            DEFAULT_SUBNODE_ID,
            "\u4e2d\u592e\u5e83\u5834",
            "\u753a\u3084\u62e0\u70b9\u306e\u4e2d\u5fc3\u90e8\u3002",
            "settlement_center",
            120,
            180,
            world_map_exit=True,
        )
        gate_name = str(location.extra.get("starting_gate_name") or self._settlement_gate_name(location))
        gate_description = str(location.extra.get("starting_gate_description") or self._settlement_gate_description(location))
        self._upsert_subnode_node(graph, "gate", gate_name, gate_description, "gate", 120, 40, world_map_exit=True)
        self._connect_subnodes(graph, DEFAULT_SUBNODE_ID, "gate")
        facilities = self._ensure_settlement_facilities(location)
        for index, facility in enumerate(facilities):
            node_id = self._facility_subnode_id(facility)
            x = 320 + (index % 3) * 170
            y = 70 + (index // 3) * 130
            name = str(facility.get("name") or node_id)
            self._upsert_subnode_node(
                graph,
                node_id,
                name,
                str(facility.get("description") or ""),
                str(facility.get("type") or "facility"),
                x,
                y,
                facility_name=name,
                facility_type=str(facility.get("type") or ""),
            )
            self._connect_subnodes(graph, DEFAULT_SUBNODE_ID, node_id)

    def _ensure_dungeon_subnodes(self, location: LocationData, graph: dict[str, Any]) -> None:
        if _safe_int(graph.get("dungeon_layout_version"), 0) != DUNGEON_SUBNODE_LAYOUT_VERSION:
            target_count = _dungeon_subnode_target_count(location)
            protected_nodes = _protected_dungeon_subnodes(graph)
            layout = self._dungeon_subnode_layout(location, target_count)
            self._replace_dungeon_subnode_layout(graph, layout, protected_nodes)
            graph["dungeon_layout_version"] = DUNGEON_SUBNODE_LAYOUT_VERSION
            graph["dungeon_target_count"] = target_count
            graph["generated_by"] = "dungeon_subnode_generator"
        self._ensure_dungeon_subarea_nodes(location, graph)
        self._seed_dungeon_deepest_loot(location, graph, source="dungeon_subnode_generation")

    def _dungeon_subnode_layout(self, location: LocationData, target_count: int) -> dict[str, Any]:
        fallback = _fallback_dungeon_subnode_layout(location, target_count)
        llm_layout = self._dungeon_subnode_layout_from_llm(location, target_count)
        return _merge_dungeon_subnode_layout(fallback, llm_layout, target_count)

    def _dungeon_subnode_layout_from_llm(self, location: LocationData, target_count: int) -> dict[str, Any]:
        if self.llm is None:
            return {}
        prompt = {
            "location": {
                "name": location.name,
                "description": _short_text(location.description, 900),
                "area": location.area,
                "kind": location.extra.get("location_kind") if isinstance(location.extra, dict) else "",
                "danger": _safe_int((location.extra if isinstance(location.extra, dict) else {}).get("danger"), 0),
                "scale": _dungeon_scale_label(location),
            },
            "target_node_count": target_count,
            "required_nodes": [
                {"id": DUNGEON_ENTRY_SUBNODE_ID, "role": "entrance"},
                {"id": DUNGEON_DEEPEST_SUBNODE_ID, "role": "deepest_or_goal"},
            ],
            "rules": [
                "Return 5 to 20 subnodes total, including entrance and deepest.",
                "Make the dungeon graph branch like a small maze, not a single straight road.",
                "Give varied room kinds such as ore vein, herb grove, treasure room, monster nest, altar, stream, collapsed path, or hidden chamber.",
                "Do not create separate world locations for entrance/interior/depth. They are subnodes of this one dungeon.",
                "Only when a node explicitly has a teleporter, portal, return gate, or similar device, include remote_travel_targets on that node. "
                "Each remote target must be {location, subnode}. Otherwise omit remote_travel_targets.",
            ],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You design Fantasia dungeon subnodes. Return JSON only. "
                    "Each node needs id, name, kind, description. Edges connect node ids. "
                    "The game will validate and may adjust coordinates/edges, but use diverse fantasy dungeon features."
                ),
            },
            {"role": "user", "content": _ai_json(prompt)},
        ]
        try:
            return self._chat_json(
                "dungeon_subnode_generator",
                messages,
                max_tokens=900,
                world_name=self.state.world_name or self.state.world_data.world_name or location.name,
                player_name=self.state.player_name or "world_builder",
                retries=1,
            )
        except Exception as exc:
            errors = location.extra.setdefault("dungeon_subnode_generation_errors", [])
            if isinstance(errors, list):
                errors.append({"error": str(exc), "target_node_count": target_count})
            return {}

    def _replace_dungeon_subnode_layout(
        self,
        graph: dict[str, Any],
        layout: dict[str, Any],
        protected_nodes: dict[str, dict[str, Any]],
    ) -> None:
        nodes = graph.setdefault("nodes", {})
        edges = graph.setdefault("edges", [])
        nodes.clear()
        edges[:] = [edge for edge in edges if isinstance(edge, dict) and edge.get("external")]
        for raw in layout.get("nodes", []):
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("id") or "").strip()
            if not node_id:
                continue
            self._upsert_subnode_node(
                graph,
                node_id,
                str(raw.get("name") or node_id),
                str(raw.get("description") or ""),
                str(raw.get("kind") or "room"),
                _safe_int(raw.get("x"), 80),
                _safe_int(raw.get("y"), 180),
                world_map_exit=bool(raw.get("world_map_exit")) if node_id == DUNGEON_ENTRY_SUBNODE_ID else bool(raw.get("world_map_exit")),
                resource_hint=str(raw.get("resource_hint") or ""),
                encounter_hint=str(raw.get("encounter_hint") or ""),
                loot_hint=str(raw.get("loot_hint") or ""),
                remote_travel_targets=_as_list(raw.get("remote_travel_targets")),
            )
        for raw in layout.get("edges", []):
            if not isinstance(raw, dict):
                continue
            self._connect_subnodes(
                graph,
                str(raw.get("from") or raw.get("source") or ""),
                str(raw.get("to") or raw.get("target") or ""),
                kind=str(raw.get("kind") or "path"),
            )
        if DUNGEON_ENTRY_SUBNODE_ID in nodes:
            nodes[DUNGEON_ENTRY_SUBNODE_ID]["world_map_exit"] = True
        if DUNGEON_DEEPEST_SUBNODE_ID in nodes:
            nodes[DUNGEON_DEEPEST_SUBNODE_ID]["world_map_exit"] = False
        for node_id, node in protected_nodes.items():
            if node_id in nodes:
                continue
            nodes[node_id] = node
            parent = DUNGEON_DEEPEST_SUBNODE_ID if DUNGEON_DEEPEST_SUBNODE_ID in nodes else DUNGEON_ENTRY_SUBNODE_ID
            if parent in nodes:
                self._connect_subnodes(graph, parent, node_id, kind="quest_path")
        _ensure_dungeon_graph_connected(graph)

    def _ensure_dungeon_subarea_nodes(self, location: LocationData, graph: dict[str, Any]) -> None:
        raw_subareas = location.extra.get("subareas")
        if not isinstance(raw_subareas, list):
            raw_subareas = []
        for index, raw in enumerate(raw_subareas):
            if isinstance(raw, dict):
                subarea_name = str(raw.get("name") or raw.get("title") or "").strip()
                description = str(raw.get("description") or "")
            else:
                subarea_name = str(raw or "").strip()
                description = ""
            if not subarea_name:
                continue
            lowered = subarea_name.casefold()
            if any(word in lowered for word in ("entrance", "inside", "interior", "depth", "deep")):
                continue
            node_id = f"subarea:{_world_location_name_key(subarea_name) or index}"
            x = 320 + (index % 3) * 160
            y = 340 + (index // 3) * 120
            self._upsert_subnode_node(graph, node_id, subarea_name, description, "subarea", x, y)
            parent = _dungeon_branch_parent(graph, index)
            self._connect_subnodes(graph, parent, node_id)

    def _upsert_subnode_node(
        self,
        graph: dict[str, Any],
        node_id: str,
        name: str,
        description: str,
        kind: str,
        x: int,
        y: int,
        **extra: Any,
    ) -> dict[str, Any]:
        nodes = graph.setdefault("nodes", {})
        node = nodes.setdefault(str(node_id), {})
        node.update({"id": str(node_id), "name": str(name or node_id), "kind": str(kind or "place"), "x": int(x), "y": int(y)})
        if description and not node.get("description"):
            node["description"] = str(description)
        elif "description" not in node:
            node["description"] = ""
        for key, value in extra.items():
            if value is not None and value != "":
                node[key] = value
        return node

    def _connect_subnodes(self, graph: dict[str, Any], a: str, b: str, kind: str = "path") -> None:
        a = str(a or "").strip()
        b = str(b or "").strip()
        if not a or not b or a == b:
            return
        edges = graph.setdefault("edges", [])
        edge_key = {a, b}
        for edge in edges:
            if not isinstance(edge, dict) or edge.get("external"):
                continue
            if {str(edge.get("from") or ""), str(edge.get("to") or "")} == edge_key:
                return
        edges.append({"from": a, "to": b, "kind": kind})

    def _subnode_reachable(self, graph: dict[str, Any], start: str, goal: str) -> bool:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        start = str(start or "").strip()
        goal = str(goal or "").strip()
        if not start or not goal or start not in nodes or goal not in nodes:
            return False
        if start == goal:
            return True
        seen = {start}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for edge in graph.get("edges", []):
                if not isinstance(edge, dict) or edge.get("external"):
                    continue
                a = str(edge.get("from") or "")
                b = str(edge.get("to") or "")
                if a == current and b in nodes and b not in seen:
                    if b == goal:
                        return True
                    seen.add(b)
                    queue.append(b)
                elif b == current and a in nodes and a not in seen:
                    if a == goal:
                        return True
                    seen.add(a)
                    queue.append(a)
        return False

    def _subnode_path(self, graph: dict[str, Any], start: str, goal: str) -> list[str]:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        start = str(start or "").strip()
        goal = str(goal or "").strip()
        if not start or not goal or start not in nodes or goal not in nodes:
            return []
        queue: list[list[str]] = [[start]]
        seen = {start}
        while queue:
            path = queue.pop(0)
            current = path[-1]
            if current == goal:
                return path
            for edge in graph.get("edges", []):
                if not isinstance(edge, dict) or edge.get("external"):
                    continue
                a = str(edge.get("from") or "")
                b = str(edge.get("to") or "")
                neighbor = b if a == current else a if b == current else ""
                if neighbor and neighbor in nodes and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append([*path, neighbor])
        return []

    def _subnode_adjacent_ids(self, graph: dict[str, Any], node_id: str) -> list[str]:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        current = str(node_id or "").strip()
        result: list[str] = []
        if not current or current not in nodes:
            return result
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict) or edge.get("external"):
                continue
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            if source == current and target in nodes:
                result.append(target)
            elif target == current and source in nodes:
                result.append(source)
        return _dedupe_strs(result)

    def _remote_travel_targets_for_subnode(self, node: dict[str, Any]) -> list[dict[str, str]]:
        raw_targets = node.get("remote_travel_targets")
        targets: list[dict[str, str]] = []
        for raw in _as_list(raw_targets):
            if isinstance(raw, dict):
                location = str(raw.get("location") or raw.get("target_location") or raw.get("destination") or "").strip()
                subnode = str(raw.get("subnode") or raw.get("subnode_id") or raw.get("target_subnode") or "").strip()
            else:
                location = str(raw or "").strip()
                subnode = ""
            if location or subnode:
                targets.append({"location": location, "subnode": subnode})
        return targets

    def _remote_subnode_travel_allowed(
        self,
        graph: dict[str, Any],
        current_id: str,
        target_location: str,
        target_subnode: str,
    ) -> bool:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        current = nodes.get(str(current_id or ""))
        if not isinstance(current, dict):
            return False
        target_location = str(target_location or "").strip()
        target_subnode = str(target_subnode or "").strip()
        for target in self._remote_travel_targets_for_subnode(current):
            allowed_location = str(target.get("location") or "").strip()
            allowed_subnode = str(target.get("subnode") or "").strip()
            if allowed_location and target_location and allowed_location != target_location:
                continue
            if target_subnode and not allowed_subnode:
                continue
            if allowed_subnode and target_subnode and allowed_subnode != target_subnode:
                continue
            if allowed_location or allowed_subnode:
                return True
        return False

    def _subnode_anchor(self, graph: dict[str, Any], *, prefer_deep: bool = False, exclude: str = "") -> str:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        exclude = str(exclude or "").strip()
        candidates: list[str] = []
        if prefer_deep:
            candidates.extend([DUNGEON_DEEPEST_SUBNODE_ID, "depths", "main_03", "main_02", "main_01"])
        current = str(graph.get("current") or "").strip()
        if current:
            candidates.append(current)
        candidates.extend([DUNGEON_ENTRY_SUBNODE_ID, DEFAULT_SUBNODE_ID, "fork"])
        for candidate in candidates:
            if candidate and candidate in nodes and candidate != exclude:
                return candidate
        for node_id in nodes:
            node_key = str(node_id)
            if node_key != exclude:
                return node_key
        return ""

    def _ensure_subnode_connected_to_anchor(
        self,
        graph: dict[str, Any],
        node_id: str,
        *,
        kind: str = "path",
        prefer_deep: bool = False,
    ) -> None:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        node_id = str(node_id or "").strip()
        if not node_id or node_id not in nodes:
            return
        root = DUNGEON_ENTRY_SUBNODE_ID if DUNGEON_ENTRY_SUBNODE_ID in nodes else DEFAULT_SUBNODE_ID if DEFAULT_SUBNODE_ID in nodes else self._subnode_anchor(graph, exclude=node_id)
        if root and self._subnode_reachable(graph, root, node_id):
            return
        parent = self._subnode_anchor(graph, prefer_deep=prefer_deep, exclude=node_id)
        if parent:
            self._connect_subnodes(graph, parent, node_id, kind=kind)
        if DUNGEON_ENTRY_SUBNODE_ID in nodes:
            _ensure_dungeon_graph_connected(graph)

    def _mark_subnode_route_visited(self, graph: dict[str, Any], start: str, goal: str) -> None:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        path = self._subnode_path(graph, start, goal)
        if not path and goal in nodes:
            path = [goal]
        for node_id in path:
            if node_id in nodes and isinstance(nodes[node_id], dict):
                nodes[node_id]["visited"] = True

    def _facility_subnode_id(self, facility: dict[str, Any]) -> str:
        name = str(facility.get("name") or facility.get("facility_name") or facility.get("title") or "facility")
        return f"facility:{_world_location_name_key(name) or 'facility'}"

    def _default_subnode_for_location(self, location: LocationData | None) -> str:
        if _is_dungeon_location(location):
            return DUNGEON_ENTRY_SUBNODE_ID
        return DEFAULT_SUBNODE_ID

    def _current_subnode_id(self, location_name: str) -> str:
        world = self.state.world_data
        graph = self._ensure_location_subnode_graph(world, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        if not nodes:
            return ""
        location = world.locations.get(location_name)
        if location and _is_settlement_location(location):
            active = self._active_facility_record()
            if active:
                node_id = self._facility_subnode_id(active)
                if node_id in nodes:
                    return node_id
        raw = self.state.flags.get(CURRENT_SUBNODE_FLAG)
        if isinstance(raw, dict) and str(raw.get("location") or "") == location_name:
            node_id = str(raw.get("id") or "")
            if node_id in nodes:
                return node_id
        node_id = str(graph.get("current") or "")
        if node_id in nodes:
            return node_id
        default_id = self._default_subnode_for_location(location)
        return default_id if default_id in nodes else next(iter(nodes), "")

    def _set_current_subnode(self, location_name: str, node_id: str) -> None:
        location_name = str(location_name or "").strip()
        node_id = str(node_id or "").strip()
        if not location_name or not node_id:
            return
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        if node_id not in nodes:
            return
        graph["current"] = node_id
        nodes[node_id]["visited"] = True
        self.state.flags[CURRENT_SUBNODE_FLAG] = {"location": location_name, "id": node_id}

    def _subnode_has_edge(self, graph: dict[str, Any], a: str, b: str) -> bool:
        edge_key = {str(a or ""), str(b or "")}
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict) or edge.get("external"):
                continue
            if {str(edge.get("from") or ""), str(edge.get("to") or "")} == edge_key:
                return True
        return False

    def _current_subnode_allows_world_map_departure(self, world: WorldData, location_name: str) -> bool:
        location = world.locations.get(str(location_name or "").strip())
        if location is None:
            return False
        if not _world_location_blocks_world_map_departure(location):
            return True
        graph = self._ensure_location_subnode_graph(world, location.name)
        current_id = self._current_subnode_id(location.name)
        node = graph.get("nodes", {}).get(current_id, {}) if isinstance(graph, dict) else {}
        return bool(current_id == DUNGEON_ENTRY_SUBNODE_ID or node.get("world_map_exit"))

    def _dangerous_fast_travel_message(self) -> str:
        return "ここは危険地帯なので、一気に移動することはできない。隣接する場所へ順番に進んでください。"

    def world_map_travel_precheck_message(self, destination: str) -> str:
        world = self.state.world_data
        current = self.state.current_location or world.starting_location
        target = str(destination or "").strip()
        graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), DEFAULT_WORLD_LOCATION_COUNT))
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if not target or target not in nodes or _world_graph_node_is_facility(world, nodes.get(target, {})):
            return "その場所はまだ地図に記録されていません。"
        if target == current:
            return ""
        block_reason = self._player_incapacitated_action_block(f"world map travel {target}", for_movement=True)
        if block_reason:
            return self._player_incapacitated_message(block_reason)
        if not self._current_subnode_allows_world_map_departure(world, current):
            return self._dangerous_fast_travel_message()
        if target in self._world_neighbors(world, current):
            route = self._world_path_subnode_route(world, [current, target])
            return "" if route is not None else self._dangerous_fast_travel_message()
        if not bool(nodes.get(target, {}).get("visited")):
            return "その場所はまだ地図に記録されていません。"
        path = self._shortest_world_path(world, current, target, visited_only=True)
        route = self._world_path_subnode_route(world, path)
        if route is None:
            return self._dangerous_fast_travel_message()
        if not path:
            return "現在地からその場所までの道が見つかりません。"
        return ""

    def subnode_travel_precheck_message(self, node_id: str) -> str:
        data = self.subnode_map_data()
        target_id = str(node_id or "").strip()
        node_lookup = {str(node.get("id") or ""): node for node in data.get("nodes", []) if isinstance(node, dict)}
        target = node_lookup.get(target_id)
        graph = self._ensure_location_subnode_graph(self.state.world_data, str(data.get("current_location") or ""))
        if not target:
            nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
            node = nodes.get(target_id)
            if isinstance(node, dict):
                target = {**node, "id": target_id, "external": False}
        if not target:
            return "その場所は現在の内部マップにありません。"
        current_id = str(data.get("current_subnode") or "")
        if target_id == current_id:
            return ""
        block_reason = self._player_incapacitated_action_block(f"subnode travel {target_id}", for_movement=True)
        if block_reason:
            return self._player_incapacitated_message(block_reason)
        movement = str(data.get("movement") or "adjacent")
        if target.get("external"):
            source_id = str(target.get("source_subnode") or "")
            if movement != "free" and current_id != source_id:
                return self._dangerous_fast_travel_message()
            return ""
        if movement != "free" and not self._subnode_has_edge(graph, current_id, target_id):
            return self._dangerous_fast_travel_message()
        return ""

    def has_current_subnode_map(self) -> bool:
        nodes = [
            node
            for node in self.subnode_map_data().get("nodes", [])
            if isinstance(node, dict) and not node.get("external")
        ]
        return len(nodes) > 1

    def has_movement_options(self) -> bool:
        return bool(self.available_movement_options())

    def available_movement_options(self) -> list[dict[str, Any]]:
        return self._movement_options_for_location(self.state.current_location or self.state.world_data.starting_location)

    def _location_has_movement_options(self, location_name: str) -> bool:
        return bool(self._movement_options_for_location(location_name))

    def _movement_options_for_location(self, location_name: str) -> list[dict[str, Any]]:
        block_reason = self._player_incapacitated_action_block("move", for_movement=True)
        if block_reason:
            return []
        world = self.state.world_data
        location_name = str(location_name or self.state.current_location or world.starting_location).strip()
        if not location_name:
            return []
        location = world.locations.get(location_name)
        options: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        graph = self._ensure_location_subnode_graph(world, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        current_subnode = self._current_subnode_id(location_name) if nodes else ""
        movement = str(graph.get("movement") or "adjacent")
        external_targets: set[str] = set()
        if nodes and current_subnode in nodes:
            if movement == "free":
                local_targets = [str(node_id) for node_id in nodes if str(node_id) != current_subnode]
            else:
                local_targets = self._subnode_adjacent_ids(graph, current_subnode)
            for node_id in local_targets:
                node = nodes.get(node_id)
                if not isinstance(node, dict):
                    continue
                key = ("subnode", node_id)
                if key in seen:
                    continue
                seen.add(key)
                options.append(
                    {
                        "type": "subnode",
                        "id": node_id,
                        "title": str(node.get("name") or node_id),
                        "description": str(node.get("description") or ""),
                        "kind": str(node.get("kind") or ""),
                        "location": location_name,
                    }
                )
            for index, edge in enumerate(self._subnode_external_edges(world, location_name, graph)):
                source_id = str(edge.get("from") or "")
                if movement != "free" and source_id != current_subnode:
                    continue
                target_location = str(edge.get("target_location") or "").strip()
                if not target_location:
                    continue
                external_targets.add(target_location)
                node_id = f"{SUBNODE_EXTERNAL_PREFIX}{index}"
                key = ("subnode", node_id)
                if key in seen:
                    continue
                seen.add(key)
                options.append(
                    {
                        "type": "subnode",
                        "id": node_id,
                        "title": target_location,
                        "description": str(edge.get("description") or ""),
                        "kind": "external",
                        "location": location_name,
                        "target_location": target_location,
                        "target_subnode": str(edge.get("target_subnode") or ""),
                        "source_subnode": source_id,
                        "external": True,
                    }
                )

        if self._current_subnode_allows_world_map_departure(world, location_name):
            world_graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), DEFAULT_WORLD_LOCATION_COUNT))
            world_nodes = world_graph.get("nodes", {}) if isinstance(world_graph.get("nodes"), dict) else {}
            for neighbor in self._world_neighbors(world, location_name):
                if not neighbor or neighbor in external_targets:
                    continue
                world_edge = self._world_edge_between(world, location_name, neighbor)
                if not world_edge or not self._current_subnode_can_reach_world_edge(world, location_name, world_edge):
                    continue
                node = world_nodes.get(neighbor, {}) if isinstance(world_nodes.get(neighbor), dict) else {}
                if _world_graph_node_is_facility(world, node):
                    continue
                key = ("world", neighbor)
                if key in seen:
                    continue
                seen.add(key)
                target_location = world.locations.get(neighbor)
                options.append(
                    {
                        "type": "world",
                        "id": neighbor,
                        "title": neighbor,
                        "description": str((target_location.description if target_location else "") or node.get("description") or ""),
                        "kind": str(node.get("kind") or (target_location.extra.get("location_kind") if target_location else "") or ""),
                        "location": location_name,
                        "visited": bool(node.get("visited")),
                    }
                )
        return options

    def _movement_options_ai_context(self, location_name: str) -> dict[str, Any]:
        location_name = str(location_name or self.state.current_location or self.state.world_data.starting_location).strip()
        options = self._movement_options_for_location(location_name)
        allowed_moves: list[dict[str, Any]] = []
        reachable_locations: list[str] = []
        reachable_subnodes: list[str] = []
        for option in options[:14]:
            if not isinstance(option, dict):
                continue
            option_type = str(option.get("type") or "").strip()
            title = str(option.get("title") or option.get("id") or "").strip()
            if not title:
                continue
            target_location = str(option.get("target_location") or "").strip()
            if option_type == "world":
                target_location = str(option.get("id") or title).strip()
            entry = _drop_empty(
                {
                    "type": option_type,
                    "title": title,
                    "target_location": target_location,
                    "target_subnode": str(option.get("id") or "") if option_type == "subnode" and not target_location else "",
                    "kind": str(option.get("kind") or ""),
                    "description": _short_text(str(option.get("description") or ""), 140),
                }
            )
            allowed_moves.append(entry)
            if target_location:
                reachable_locations.append(target_location)
            elif option_type == "subnode":
                reachable_subnodes.append(title)
        return {
            "current_location": location_name,
            "allowed_moves": allowed_moves,
            "reachable_location_names": _dedupe_strs(reachable_locations),
            "reachable_subnode_titles": _dedupe_strs(reachable_subnodes),
            "rule": (
                "Do not put movement/return/enter/leave/head-to choices in the response choices field. "
                "The game client adds a local Move menu from allowed_moves. Use allowed_moves only when judging "
                "whether an explicit player action can move with the move_player tool."
            ),
        }

    def _movement_choice_rule_prompt(self, *, include_context: bool = True) -> str:
        location_name = self.state.current_location or self.state.world_data.starting_location
        context_line = (
            f"allowed_movement_context: {_ai_json(self._movement_options_ai_context(location_name))}\n"
            if include_context
            else "Use world_data.movement_options.allowed_moves already supplied in the prompt.\n"
        )
        return (
            "Movement choice rule for the choices field:\n"
            f"{context_line}"
            "Never put movement choices in choices. Do not write choices like 'go deeper', 'go back', "
            "'return to town', 'enter', 'leave', 'head to X', '奥へ進む', '元の位置に戻る', or '○○へ向かう'. "
            "The game client adds the local movement menu from allowed_moves. Non-movement choices such as "
            "looking around, talking to a nearby NPC, treating a rescued NPC, or checking the situation are allowed."
        )

    def current_loot_inventory(self) -> tuple[str, list[dict[str, Any]]]:
        location_name = self.state.current_location or self.state.world_data.starting_location
        location = self.state.world_data.ensure_location(location_name)
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        subnode_id = self._current_subnode_id(location_name) if nodes else ""
        if subnode_id and subnode_id in nodes:
            node = nodes.get(subnode_id, {}) if isinstance(nodes.get(subnode_id), dict) else {}
            loot_store = location.extra.setdefault("subnode_loot", {})
            if not isinstance(loot_store, dict):
                loot_store = {}
                location.extra["subnode_loot"] = loot_store
            slot = loot_store.setdefault(subnode_id, {})
            if not isinstance(slot, dict):
                slot = {}
                loot_store[subnode_id] = slot
            inventory = slot.setdefault("inventory", [])
            if not isinstance(inventory, list):
                inventory = []
                slot["inventory"] = inventory
            if refresh_template_subnode_loot(self, location, subnode_id, node, slot):
                inventory = slot.setdefault("inventory", [])
                if not isinstance(inventory, list):
                    inventory = []
                    slot["inventory"] = inventory
            label = f"{location.name} / {node.get('name') or subnode_id}"
            return label, inventory
        inventory = location.extra.setdefault("inventory", [])
        if not isinstance(inventory, list):
            inventory = []
            location.extra["inventory"] = inventory
        if not location.flags.get("inventory_seeded") and not inventory:
            location.flags["inventory_seeded"] = True
        return location.name, inventory

    def subnode_map_data(self) -> dict[str, Any]:
        world = self.state.world_data
        location_name = self.state.current_location or world.starting_location
        graph = self._ensure_location_subnode_graph(world, location_name)
        if not graph:
            return {"current_location": location_name, "current_subnode": "", "movement": "", "nodes": [], "edges": []}
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        location = world.locations.get(location_name)
        if not nodes and location:
            self._ensure_basic_subnodes(location, graph)
            nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if not nodes:
            return {"current_location": location_name, "current_subnode": "", "movement": str(graph.get("movement") or ""), "nodes": [], "edges": []}
        current_id = self._current_subnode_id(location_name)
        if current_id not in nodes:
            fallback_current = ""
            for candidate in (DUNGEON_ENTRY_SUBNODE_ID, DEFAULT_SUBNODE_ID, str(graph.get("current") or "")):
                if candidate and candidate in nodes:
                    fallback_current = candidate
                    break
            if not fallback_current:
                fallback_current = str(next(iter(nodes), ""))
            if fallback_current:
                current_id = fallback_current
                graph["current"] = current_id
                self.state.flags[CURRENT_SUBNODE_FLAG] = {"location": location_name, "id": current_id}
        if current_id in nodes:
            nodes[current_id]["visited"] = True
        hide_unvisited = bool(location and _subnode_map_hides_unvisited(location))
        visible_node_ids = {
            str(node_id)
            for node_id, node in nodes.items()
            if isinstance(node, dict)
            and (
                not hide_unvisited
                or str(node_id) == current_id
                or bool(node.get("visited"))
                or bool(node.get("revealed"))
            )
        }
        local_nodes: list[dict[str, Any]] = []
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            if str(node_id) not in visible_node_ids:
                continue
            payload = dict(node)
            payload["id"] = str(node_id)
            payload["external"] = False
            payload["current"] = str(node_id) == current_id
            local_nodes.append(payload)
        local_edges = [
            dict(edge)
            for edge in graph.get("edges", [])
            if isinstance(edge, dict)
            and not edge.get("external")
            and str(edge.get("from") or "") in visible_node_ids
            and str(edge.get("to") or "") in visible_node_ids
        ]
        external_nodes: list[dict[str, Any]] = []
        external_edges: list[dict[str, Any]] = []
        external_edges_raw = self._subnode_external_edges(world, location_name, graph)
        external_node_size = 84
        external_spacing = 112
        external_gap = 180
        external_lane_x = (
            max((_safe_int(node.get("x"), 80) for node in local_nodes), default=80)
            + external_gap
        )
        occupied_boxes: list[tuple[int, int, int, int]] = []
        for node in local_nodes:
            x = _safe_int(node.get("x"), 80)
            y = _safe_int(node.get("y"), 80)
            occupied_boxes.append((x - 24, y - 24, x + external_node_size + 24, y + external_node_size + 24))

        def overlaps_existing(x: int, y: int) -> bool:
            box = (x, y, x + external_node_size, y + external_node_size)
            for left, top, right, bottom in occupied_boxes:
                if box[0] < right and box[2] > left and box[1] < bottom and box[3] > top:
                    return True
            return False

        source_counts: dict[str, int] = {}
        source_offsets: dict[str, int] = {}
        for edge in external_edges_raw:
            source_id = str(edge.get("from") or "")
            if source_id not in visible_node_ids:
                continue
            source_counts[source_id] = source_counts.get(source_id, 0) + 1
        for index, edge in enumerate(external_edges_raw):
            if str(edge.get("from") or "") not in visible_node_ids:
                continue
            source = nodes.get(str(edge.get("from") or ""), {})
            source_x = _safe_int(source.get("x") if isinstance(source, dict) else 80, 80)
            source_y = _safe_int(source.get("y") if isinstance(source, dict) else 80, 80)
            node_id = f"{SUBNODE_EXTERNAL_PREFIX}{index}"
            target_location = str(edge.get("target_location") or "")
            source_id = str(edge.get("from") or "")
            source_offset = source_offsets.get(source_id, 0)
            source_offsets[source_id] = source_offset + 1
            group_count = max(1, source_counts.get(source_id, 1))
            group_origin_y = source_y - ((group_count - 1) * external_spacing) // 2
            x = max(external_lane_x, source_x + external_gap)
            y = max(24, group_origin_y + source_offset * external_spacing)
            while overlaps_existing(x, y):
                y += external_spacing
            occupied_boxes.append((x - 24, y - 24, x + external_node_size + 24, y + external_node_size + 24))
            external_nodes.append(
                {
                    "id": node_id,
                    "name": target_location,
                    "description": str(edge.get("description") or ""),
                    "kind": "external",
                    "x": x,
                    "y": y,
                    "external": True,
                    "target_location": target_location,
                    "target_subnode": str(edge.get("target_subnode") or ""),
                    "source_subnode": str(edge.get("from") or ""),
                    "hours": _safe_int(edge.get("hours"), WORLD_MAP_EDGE_HOURS),
                }
            )
            external_edges.append({"from": str(edge.get("from") or ""), "to": node_id, "external": True, "kind": str(edge.get("kind") or "exit")})
        return {
            "current_location": location_name,
            "current_subnode": current_id,
            "movement": str(graph.get("movement") or "adjacent"),
            "nodes": local_nodes + external_nodes,
            "edges": local_edges + external_edges,
        }

    def _subnode_external_edges(self, world: WorldData, location_name: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
        location_name = str(location_name or "").strip()
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        world_graph = self._location_graph_for_update(world)
        result: list[dict[str, Any]] = []
        for edge in world_graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            a = str(edge.get("from") or "").strip()
            b = str(edge.get("to") or "").strip()
            if a != location_name and b != location_name:
                continue
            target = b if a == location_name else a
            if not target or target == location_name:
                continue
            self._ensure_world_edge_subnodes(world, edge)
            source_id = self._world_edge_subnode_for_location(world, edge, location_name)
            if source_id not in nodes:
                source_id = self._default_subnode_for_location(world.locations.get(location_name))
            if source_id not in nodes:
                continue
            result.append(
                {
                    "from": source_id,
                    "target_location": target,
                    "target_subnode": self._world_edge_subnode_for_location(world, edge, target),
                    "hours": _safe_int(edge.get("hours"), WORLD_MAP_EDGE_HOURS),
                    "kind": str(edge.get("kind") or "exit"),
                    "description": str(edge.get("description") or ""),
                }
            )
        return result

    def _declared_world_edge_subnode(self, edge: dict[str, Any], side: str, location_name: str) -> str:
        side = "from" if side == "from" else "to"
        key_groups = {
            "from": ("from_subnode", "source_subnode", "a_subnode", "from_node", "source_node"),
            "to": ("to_subnode", "target_subnode", "b_subnode", "to_node", "target_node"),
        }
        for key in key_groups[side]:
            value = str(edge.get(key) or "").strip()
            if value:
                return value
        subnodes = edge.get("subnodes")
        if isinstance(subnodes, dict):
            value = str(subnodes.get(location_name) or "").strip()
            if value:
                return value
        return ""

    def _default_external_source_subnode(self, world: WorldData, location_name: str, target_name: str) -> str:
        location = world.locations.get(location_name)
        target = world.locations.get(target_name)
        if _is_dungeon_location(location):
            return DUNGEON_DEEPEST_SUBNODE_ID if _is_dungeon_location(target) else DUNGEON_ENTRY_SUBNODE_ID
        if _is_settlement_location(location):
            return "gate"
        return self._default_subnode_for_location(location)

    def _default_external_target_subnode(self, world: WorldData, target_name: str, source_name: str) -> str:
        target = world.locations.get(target_name)
        if _is_dungeon_location(target):
            return DUNGEON_ENTRY_SUBNODE_ID
        if _is_settlement_location(target):
            return "gate"
        return self._default_subnode_for_location(target)

    def _activate_facility_for_subnode(self, location_name: str, node: dict[str, Any]) -> None:
        location = self.state.world_data.locations.get(location_name)
        if not location or not _is_settlement_location(location):
            return
        facility_name = str(node.get("facility_name") or "").strip()
        if not facility_name:
            self._clear_active_facility(reset_subnode=False)
            return
        facility = self._find_or_create_facility_record(location, facility_name)
        if facility:
            self._set_active_facility(location, facility)
            self._ensure_facility_npc(location, facility, location.name)

    def travel_subnode_to(self, node_id: str) -> str:
        precheck_message = self.subnode_travel_precheck_message(node_id)
        if precheck_message:
            raise ValueError(precheck_message)
        self.dismiss_active_cg()
        data = self.subnode_map_data()
        location_name = str(data.get("current_location") or self.state.current_location or self.state.world_data.starting_location)
        target_id = str(node_id or "").strip()
        node_lookup = {str(node.get("id") or ""): node for node in data.get("nodes", []) if isinstance(node, dict)}
        target = node_lookup.get(target_id)
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        if not target:
            nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
            node = nodes.get(target_id)
            if isinstance(node, dict):
                target = {**node, "id": target_id, "external": False}
        if not target:
            raise ValueError("その場所は現在の内部マップにありません。")
        current_id = str(data.get("current_subnode") or "")
        if target_id != current_id:
            block_reason = self._player_incapacitated_action_block(f"subnode travel {target_id}", for_movement=True)
            if block_reason:
                raise ValueError(self._player_incapacitated_message(block_reason))
        movement = str(data.get("movement") or "adjacent")
        if target.get("external"):
            source_id = str(target.get("source_subnode") or "")
            if movement != "free" and current_id != source_id:
                raise ValueError("その道を使うには、接続されている地点まで移動してください。")
            target_location = str(target.get("target_location") or "")
            if not target_location:
                raise ValueError("その道には移動先が設定されていません。")
            return self._travel_external_subnode(location_name, target, source_id)
        if target_id == current_id:
            return self.state.log_text(16)
        if movement != "free" and not self._subnode_has_edge(graph, current_id, target_id):
            raise ValueError("その場所へは隣接地点からしか移動できません。")
        name = str(target.get("name") or target_id)
        was_visited = bool(target.get("visited"))
        narrator_response = self._direct_travel_narrator(
            action=f"{name}へ移動",
            input_type="choice",
            travel_kind="subnode",
            source_name=location_name,
            destination_location=location_name,
            destination_name=name,
            destination_description=str(target.get("description") or ""),
            route_text=f"{location_name}内の{current_id}から{target_id}へ移動する。",
        )
        time_event: dict[str, Any] = {}
        if _is_dungeon_location(self.state.world_data.locations.get(location_name)):
            time_event = self._advance_world_time(1, source="dungeon_subnode_travel", reason="dungeon room travel", append_log=False)
        self._set_current_subnode(location_name, target_id)
        self._activate_facility_for_subnode(location_name, target)
        narration = str(narrator_response.get("narration") or f"{name}\u3078\u79fb\u52d5\u3057\u305f\u3002")
        choices = _exploration_choices(
            self._filter_llm_choices_for_display(_as_str_list(narrator_response.get("choices")))
            + self._location_default_choices(location_name)
        )
        narration, choices, _ = self._maybe_start_first_visit_danger_subnode_encounter(
            location_name,
            target_id,
            was_visited=was_visited,
            source="subnode_travel",
            action="\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5",
            narration=narration,
            choices=choices,
        )
        narration, choices, _ = self._evaluate_hostile_arrival(
            "\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5",
            "choice",
            "subnode_travel",
            location_name,
            narration,
            choices,
        )
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self._append_turn("\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5", narration, location_name, choices, input_type="choice")
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        self._apply_visual_intent(narrator_response, "subnode_travel", location_name, location_name)
        self.save_game()
        return self.state.log_text(16)

    def _travel_external_subnode(self, current_location: str, target: dict[str, Any], source_id: str) -> str:
        world = self.state.world_data
        target_location = str(target.get("target_location") or "").strip()
        if target_location not in world.locations:
            raise ValueError("その移動先はワールドに登録されていません。")
        previous_location = current_location
        hours = max(0, _safe_int(target.get("hours"), WORLD_MAP_EDGE_HOURS))
        narrator_response = self._direct_travel_narrator(
            action="\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5",
            input_type="choice",
            travel_kind="subnode_external",
            source_name=current_location,
            destination_location=target_location,
            destination_name=target_location,
            destination_description=str((world.locations.get(target_location).description if world.locations.get(target_location) else "") or target.get("description") or ""),
            route_text=f"{current_location}の{source_id}から{target_location}へ続く道を使う。",
            elapsed_hours=hours,
        )
        time_event = self._advance_world_time(hours, source="subnode_route", reason="subnode route travel", append_log=False)
        self._clear_active_facility(reset_subnode=False)
        self._mark_location_visited(world, target_location)
        target_graph = self._ensure_location_subnode_graph(world, target_location)
        target_subnode = str(target.get("target_subnode") or "")
        edge = self._world_edge_between(world, current_location, target_location)
        if (not target_subnode or target_subnode not in target_graph.get("nodes", {})) and edge:
            target_subnode = self._world_edge_subnode_for_location(world, edge, target_location)
        if not target_subnode or target_subnode not in target_graph.get("nodes", {}):
            target_subnode = self._default_subnode_for_location(world.locations.get(target_location))
        target_nodes = target_graph.get("nodes", {}) if isinstance(target_graph.get("nodes"), dict) else {}
        target_node = target_nodes.get(target_subnode) if target_subnode else {}
        was_visited = bool(target_node.get("visited")) if isinstance(target_node, dict) else False
        if edge:
            current_side = "from" if str(edge.get("from") or "") == current_location else "to"
            target_side = "to" if current_side == "from" else "from"
            source_subnode = str(source_id or self._current_subnode_id(current_location) or "")
            if source_subnode:
                edge[f"{current_side}_subnode"] = source_subnode
                edge.setdefault("subnodes", {})[current_location] = source_subnode
            if target_subnode:
                edge[f"{target_side}_subnode"] = target_subnode
                edge.setdefault("subnodes", {})[target_location] = target_subnode
        self._set_current_subnode(target_location, target_subnode)
        self._set_player_presence(target_location)
        narration = str(narrator_response.get("narration") or f"{previous_location} -> {target_location} \u3078\u79fb\u52d5\u3057\u305f\u3002")
        choices = _exploration_choices(
            self._filter_llm_choices_for_display(_as_str_list(narrator_response.get("choices")))
            + self._location_default_choices(target_location)
        )
        narration, choices, _ = self._maybe_start_first_visit_danger_subnode_encounter(
            target_location,
            target_subnode,
            was_visited=was_visited,
            source="subnode_external_travel",
            action="\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5",
            narration=narration,
            choices=choices,
        )
        narration, choices, _ = self._evaluate_hostile_arrival(
            "\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5",
            "choice",
            "subnode_external_travel",
            target_location,
            narration,
            choices,
        )
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self._append_turn("\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5", narration, target_location, choices, input_type="choice")
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        self._apply_visual_intent(narrator_response, "subnode_travel", target_location, previous_location)
        self.save_game()
        return self.state.log_text(16)

    def _shortest_world_path(self, world: WorldData, start: str, goal: str, *, visited_only: bool = False) -> list[str]:
        graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), 1))
        nodes = graph.get("nodes", {})
        if start not in nodes or goal not in nodes:
            return []
        queue: list[list[str]] = [[start]]
        seen = {start}
        while queue:
            path = queue.pop(0)
            current = path[-1]
            if current == goal:
                return path
            for neighbor in self._world_neighbors(world, current):
                if neighbor in seen:
                    continue
                if visited_only and not bool(nodes.get(neighbor, {}).get("visited")):
                    continue
                seen.add(neighbor)
                queue.append([*path, neighbor])
        return []

    def world_map_data(self) -> dict[str, Any]:
        world = self.state.world_data
        graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), DEFAULT_WORLD_LOCATION_COUNT))
        nodes = graph.get("nodes", {})
        visible_nodes = [
            dict(node)
            for node in nodes.values()
            if isinstance(node, dict) and (bool(node.get("visited")) or bool(node.get("discovered"))) and not _world_graph_node_is_facility(world, node)
        ]
        visible_names = {str(node.get("name") or "") for node in visible_nodes}
        edges: list[dict[str, Any]] = []
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                continue
            a = str(edge.get("from") or "")
            b = str(edge.get("to") or "")
            if a not in visible_names or b not in visible_names:
                continue
            self._ensure_world_edge_subnodes(world, edge)
            if not self._world_edge_subnode_for_location(world, edge, a):
                continue
            if not self._world_edge_subnode_for_location(world, edge, b):
                continue
            edges.append(dict(edge))
        return {
            "current_location": self.state.current_location,
            "edge_hours": WORLD_MAP_EDGE_HOURS,
            "nodes": visible_nodes,
            "edges": edges,
        }

    def travel_world_map_to(self, destination: str) -> str:
        precheck_message = self.world_map_travel_precheck_message(destination)
        if precheck_message:
            raise ValueError(precheck_message)
        self.dismiss_active_cg()
        world = self.state.world_data
        current = self.state.current_location or world.starting_location
        target = str(destination or "").strip()
        graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), DEFAULT_WORLD_LOCATION_COUNT))
        nodes = graph.get("nodes", {})
        if not target or target not in nodes or _world_graph_node_is_facility(world, nodes.get(target, {})):
            raise ValueError("その場所はまだ地図に記録されていません。")
        if target == current:
            return self.state.log_text(16)
        block_reason = self._player_incapacitated_action_block(f"world map travel {target}", for_movement=True)
        if block_reason:
            raise ValueError(self._player_incapacitated_message(block_reason))
        if not self._current_subnode_allows_world_map_departure(world, current):
            raise ValueError("危険地帯の奥からはワールドマップ移動できません。入口や安全な退避地点まで戻ってください。")
        if target in self._world_neighbors(world, current):
            path = [current, target]
        else:
            if not bool(nodes.get(target, {}).get("visited")):
                raise ValueError("その場所はまだ地図に記録されていません。")
            path = self._shortest_world_path(world, current, target, visited_only=True)
        if not path:
            raise ValueError("現在地からその場所までの道が見つかりません。")
        route = self._world_path_subnode_route(world, path)
        if route is None:
            raise ValueError(self._dangerous_fast_travel_message())
        hours = sum(max(0, _safe_int(step.get("edge", {}).get("hours"), WORLD_MAP_EDGE_HOURS)) for step in route)
        target_subnode = str(route[-1].get("to_subnode") or "") if route else self._current_subnode_id(target)
        target_location = world.locations.get(target)
        narrator_response = self._direct_travel_narrator(
            action="ワールドマップ移動",
            input_type="choice",
            travel_kind="world_map",
            source_name=current,
            destination_location=target,
            destination_name=target,
            destination_description=str(target_location.description if target_location else ""),
            route_text=" -> ".join(path),
            elapsed_hours=hours,
        )
        time_event = self._advance_world_time(hours, source="world_map_travel", reason="world map travel", append_log=False)
        narration = str(narrator_response.get("narration") or f"{' -> '.join(path)} の道をたどって移動した。")
        choices = _exploration_choices(
            self._filter_llm_choices_for_display(_as_str_list(narrator_response.get("choices")))
            + self._location_default_choices(target)
        )
        self._clear_active_facility(reset_subnode=False)
        self._set_player_presence(target)
        self._mark_location_visited(world, target)
        target_graph = self._ensure_location_subnode_graph(world, target)
        if target_graph:
            if target_subnode not in target_graph.get("nodes", {}):
                target_subnode = self._default_subnode_for_location(world.locations.get(target))
            target_nodes = target_graph.get("nodes", {}) if isinstance(target_graph.get("nodes"), dict) else {}
            target_node = target_nodes.get(target_subnode) if target_subnode else {}
            was_visited = bool(target_node.get("visited")) if isinstance(target_node, dict) else False
            self._set_current_subnode(target, target_subnode)
            narration, choices, _ = self._maybe_start_first_visit_danger_subnode_encounter(
                target,
                target_subnode,
                was_visited=was_visited,
                source="world_map_travel",
                action="world map travel",
                narration=narration,
                choices=choices,
            )
        narration, choices, _ = self._evaluate_hostile_arrival(
            "ワールドマップ移動",
            "choice",
            "world_map_travel",
            target,
            narration,
            choices,
        )
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self._append_turn("ワールドマップ移動", narration, target, choices, input_type="choice")
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        self._apply_visual_intent(narrator_response, "world_map_travel", target, current)
        self.save_game()
        return self.state.log_text(16)

    def _response_target_subnode_id(self, response: dict[str, Any], graph: dict[str, Any]) -> str:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        candidates: list[Any] = []
        for key in (
            "target_subnode_id",
            "target_subnode",
            "destination_subnode_id",
            "destination_subnode",
            "subnode_id",
            "subnode",
            "node_id",
        ):
            candidates.append(response.get(key))
        for key in ("movement", "travel", "move", "destination"):
            value = response.get(key)
            if isinstance(value, dict):
                for subkey in ("target_subnode_id", "target_subnode", "subnode_id", "subnode", "node_id"):
                    candidates.append(value.get(subkey))
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("id") or candidate.get("subnode_id") or candidate.get("name")
            text = str(candidate or "").strip()
            if not text:
                continue
            if text in nodes:
                return text
            normalized = _world_location_name_key(text)
            for node_id, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                node_name = str(node.get("name") or node_id)
                if normalized and normalized == _world_location_name_key(node_name):
                    return str(node_id)
        return ""

    def _normalize_response_subnode_movement(
        self,
        response: dict[str, Any],
        proposed_location: str,
        *,
        action: str = "",
        source: str = "response_subnode_movement",
    ) -> dict[str, Any] | None:
        if not isinstance(response, dict):
            return None
        world = self.state.world_data
        current = self.state.current_location or world.starting_location
        current_graph = self._ensure_location_subnode_graph(world, current)
        current_nodes = current_graph.get("nodes", {}) if isinstance(current_graph.get("nodes"), dict) else {}
        if not current_nodes:
            return None
        current_id = self._current_subnode_id(current)
        teleport = _teleport_movement_requested(response)
        target_location = str(
            response.get("target_location")
            or response.get("destination_location")
            or proposed_location
            or current
        ).strip() or current
        target_location = self._find_world_location_by_name(target_location) or target_location
        target_graph = current_graph if target_location == current else self._ensure_location_subnode_graph(world, target_location)
        target_subnode = self._response_target_subnode_id(response, target_graph if target_graph else current_graph)
        if not target_subnode and target_location == current:
            return None
        if target_location != current and not teleport:
            return None
        target_nodes = target_graph.get("nodes", {}) if isinstance(target_graph.get("nodes"), dict) else {}
        if target_location != current:
            if not target_subnode:
                target_subnode = self._default_subnode_for_location(world.locations.get(target_location))
            if target_subnode not in target_nodes:
                return {
                    "location": current,
                    "narration_lines": [self._dangerous_fast_travel_message()],
                    "status_lines": [],
                    "moved": False,
                    "denied": True,
                }
            if not self._remote_subnode_travel_allowed(current_graph, current_id, target_location, target_subnode):
                return {
                    "location": current,
                    "narration_lines": [self._dangerous_fast_travel_message()],
                    "status_lines": [],
                    "moved": False,
                    "denied": True,
                }
            self._clear_active_facility(reset_subnode=False)
            self._mark_location_visited(world, target_location)
            target_node = target_nodes.get(target_subnode) if target_subnode else {}
            was_visited = bool(target_node.get("visited")) if isinstance(target_node, dict) else False
            self._set_current_subnode(target_location, target_subnode)
            self._set_player_presence(target_location)
            encounter_narration, _, encounter_event = self._maybe_start_first_visit_danger_subnode_encounter(
                target_location,
                target_subnode,
                was_visited=was_visited,
                source=source,
                action=action,
                narration="",
                choices=[],
            )
            return {
                "location": target_location,
                "narration_lines": [encounter_narration] if encounter_narration else [],
                "status_lines": [],
                "moved": True,
                "denied": False,
                "random_encounter": encounter_event,
            }
        if not target_subnode or target_subnode not in current_nodes:
            return {
                "location": current,
                "narration_lines": ["指定された内部地点は現在のマップにありません。"],
                "status_lines": [],
                "moved": False,
                "denied": True,
            }
        if target_subnode == current_id:
            return {"location": current, "narration_lines": [], "status_lines": [], "moved": False, "denied": False}
        movement = str(current_graph.get("movement") or "adjacent")
        allowed = movement == "free" or self._subnode_has_edge(current_graph, current_id, target_subnode)
        if not allowed and teleport:
            allowed = self._remote_subnode_travel_allowed(current_graph, current_id, current, target_subnode)
        if not allowed:
            return {
                "location": current,
                "narration_lines": [self._dangerous_fast_travel_message()],
                "status_lines": [],
                "moved": False,
                "denied": True,
            }
        target_node = current_nodes.get(target_subnode, {}) if isinstance(current_nodes.get(target_subnode), dict) else {}
        was_visited = bool(target_node.get("visited")) if isinstance(target_node, dict) else False
        self._set_current_subnode(current, target_subnode)
        self._activate_facility_for_subnode(current, target_node)
        self._set_player_presence(current)
        encounter_narration, _, encounter_event = self._maybe_start_first_visit_danger_subnode_encounter(
            current,
            target_subnode,
            was_visited=was_visited,
            source=source,
            action=action,
            narration="",
            choices=[],
        )
        return {
            "location": current,
            "narration_lines": [encounter_narration] if encounter_narration else [],
            "status_lines": [],
            "moved": True,
            "denied": False,
            "random_encounter": encounter_event,
        }

    def _normalize_world_response_location(
        self,
        action: str,
        input_type: str,
        response: dict[str, Any],
        proposed_location: str,
    ) -> dict[str, Any]:
        world = self.state.world_data
        current = self.state.current_location or world.starting_location
        proposed = str(proposed_location or current).strip() or current
        self._ensure_world_location_graph(world, target_count=max(len(world.locations), DEFAULT_WORLD_LOCATION_COUNT))
        self._mark_location_visited(world, current)
        facility_result = self._normalize_facility_response_location(action, response, current, proposed)
        if facility_result is not None:
            return facility_result
        proposed = _collapse_same_location_subarea(world, current, proposed)
        subnode_result = self._normalize_response_subnode_movement(
            response,
            proposed,
            action=action,
            source=f"{input_type}_response_subnode_movement",
        )
        if subnode_result is not None:
            return subnode_result
        if proposed == current:
            if _facility_exit_requested(action, response):
                self._clear_active_facility()
            return {"location": current, "narration_lines": [], "status_lines": [], "moved": False, "denied": False}

        block_reason = self._player_incapacitated_action_block(action, for_movement=True)
        if block_reason:
            return {
                "location": current,
                "narration_lines": [self._player_incapacitated_message(block_reason)],
                "status_lines": [],
                "moved": False,
                "denied": True,
            }

        graph = world.extra.get("location_graph", {})
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        neighbors = self._world_neighbors(world, current)
        status_lines: list[str] = []
        narration_lines: list[str] = []
        teleport = _teleport_movement_requested(response)

        if teleport:
            return {
                "location": current,
                "narration_lines": [self._dangerous_fast_travel_message()],
                "status_lines": [],
                "moved": False,
                "denied": True,
            }

        if proposed in neighbors:
            if not self._current_subnode_allows_world_map_departure(world, current):
                return {
                    "location": current,
                    "narration_lines": [self._dangerous_fast_travel_message()],
                    "status_lines": [],
                    "moved": False,
                    "denied": True,
                }
            edge = self._world_edge_between(world, current, proposed)
            if not edge or not self._current_subnode_can_reach_world_edge(world, current, edge):
                return {
                    "location": current,
                    "narration_lines": [self._dangerous_fast_travel_message()],
                    "status_lines": [],
                    "moved": False,
                    "denied": True,
                }
            if proposed not in nodes:
                location = world.ensure_location(proposed, _short_text(str(response.get("narration") or ""), 220))
                kind = _infer_world_location_kind_for_request(action, response, proposed, location.description)
                location.extra["location_kind"] = kind
                self._set_location_graph_node(world, proposed, kind=kind, location=location)
            target_subnode = self._world_edge_subnode_for_location(world, edge, proposed)
            hours = max(0, _safe_int(edge.get("hours"), WORLD_MAP_EDGE_HOURS))
            event = self._advance_world_time(hours, source="world_travel", reason="adjacent location travel", append_log=False)
            if event.get("line"):
                status_lines.append(str(event["line"]))
            status_lines.extend(str(item) for item in event.get("companion_lines", []) if item)
            self._clear_active_facility(reset_subnode=False)
            self._mark_location_visited(world, proposed)
            target_graph = self._ensure_location_subnode_graph(world, proposed)
            if target_graph:
                if target_subnode not in target_graph.get("nodes", {}):
                    target_subnode = self._default_subnode_for_location(world.locations.get(proposed))
                target_nodes = target_graph.get("nodes", {}) if isinstance(target_graph.get("nodes"), dict) else {}
                target_node = target_nodes.get(target_subnode) if target_subnode else {}
                was_visited = bool(target_node.get("visited")) if isinstance(target_node, dict) else False
                self._set_current_subnode(proposed, target_subnode)
            boss_event = self._ensure_generated_dungeon_boss(proposed, action, response)
            if boss_event:
                status_lines.append(f"> [NPC] {boss_event.get('name')} が {proposed} の奥に配置されました。")
            if target_graph:
                encounter_narration, _, encounter_event = self._maybe_start_first_visit_danger_subnode_encounter(
                    proposed,
                    target_subnode,
                    was_visited=was_visited,
                    source=f"{input_type}_world_travel",
                    action=action,
                    narration="",
                    choices=[],
                )
                if encounter_narration:
                    narration_lines.append(encounter_narration)
            return {"location": proposed, "narration_lines": narration_lines, "status_lines": status_lines, "moved": True, "denied": False}

        if proposed in nodes:
            narration_lines.append(f"この場所から「{proposed}」へ直接向かう道は見つからない。隣接している場所から順に移動する必要がある。")
            return {"location": current, "narration_lines": narration_lines, "status_lines": [], "moved": False, "denied": True}

        description = _short_text(str(response.get("narration") or response.get("description") or ""), 220)
        explicit_generated_dungeon = _explicit_generated_dungeon_location_request(action, response, proposed, description)
        if (
            (_nearby_dynamic_location_requested(action, proposed) and len(neighbors) <= WORLD_MAP_MAX_DYNAMIC_DEGREE)
            or explicit_generated_dungeon
        ):
            if not self._current_subnode_allows_world_map_departure(world, current):
                return {
                    "location": current,
                    "narration_lines": [self._dangerous_fast_travel_message()],
                    "status_lines": [],
                    "moved": False,
                    "denied": True,
                }
            kind = _infer_world_location_kind_for_request(action, response, proposed, description)
            current_node = nodes.get(current, {}) if isinstance(nodes, dict) else {}
            danger = _clamp_world_danger(_safe_int(current_node.get("danger"), 0) + (5 if kind in {"dungeon", "wilderness"} else 0))
            location = world.ensure_location(proposed, description)
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = danger
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
            self._set_location_graph_node(world, proposed, kind=kind, danger=danger, location=location)
            self._connect_world_locations(world, current, proposed)
            edge = self._world_edge_between(world, current, proposed)
            target_subnode = ""
            if edge:
                current_side = "from" if str(edge.get("from") or "") == current else "to"
                target_side = "to" if current_side == "from" else "from"
                current_subnode = self._current_subnode_id(current)
                target_subnode = self._world_edge_subnode_for_location(world, edge, proposed)
                if current_subnode:
                    edge[f"{current_side}_subnode"] = current_subnode
                    edge.setdefault("subnodes", {})[current] = current_subnode
                if target_subnode:
                    edge[f"{target_side}_subnode"] = target_subnode
                    edge.setdefault("subnodes", {})[proposed] = target_subnode
            hours = max(0, _safe_int(edge.get("hours") if edge else WORLD_MAP_EDGE_HOURS, WORLD_MAP_EDGE_HOURS))
            event = self._advance_world_time(hours, source="world_travel", reason="new nearby location", append_log=False)
            if event.get("line"):
                status_lines.append(str(event["line"]))
            status_lines.extend(str(item) for item in event.get("companion_lines", []) if item)
            self._clear_active_facility(reset_subnode=False)
            self._mark_location_visited(world, proposed)
            target_graph = self._ensure_location_subnode_graph(world, proposed)
            if target_graph:
                if target_subnode not in target_graph.get("nodes", {}):
                    target_subnode = self._default_subnode_for_location(world.locations.get(proposed))
                target_nodes = target_graph.get("nodes", {}) if isinstance(target_graph.get("nodes"), dict) else {}
                target_node = target_nodes.get(target_subnode) if target_subnode else {}
                was_visited = bool(target_node.get("visited")) if isinstance(target_node, dict) else False
                self._set_current_subnode(proposed, target_subnode)
            boss_event = self._ensure_generated_dungeon_boss(proposed, action, response)
            if boss_event:
                status_lines.append(f"> [NPC] {boss_event.get('name')} が {proposed} の奥に配置されました。")
            status_lines.append(f"> [Map] 新しい地点を発見: {proposed}")
            encounter_narration = ""
            if target_graph:
                encounter_narration, _, encounter_event = self._maybe_start_first_visit_danger_subnode_encounter(
                    proposed,
                    target_subnode,
                    was_visited=was_visited,
                    source=f"{input_type}_new_world_travel",
                    action=action,
                    narration="",
                    choices=[],
                )
            return {
                "location": proposed,
                "narration_lines": [encounter_narration] if encounter_narration else [],
                "status_lines": status_lines,
                "moved": True,
                "denied": False,
            }

        narration_lines.append(f"この付近に「{proposed}」のような場所は見当たらない。")
        return {"location": current, "narration_lines": narration_lines, "status_lines": [], "moved": False, "denied": True}

    def _normalize_facility_response_location(
        self,
        action: str,
        response: dict[str, Any],
        current: str,
        proposed: str,
    ) -> dict[str, Any] | None:
        settlement = self._current_settlement_location()
        if settlement is None:
            return None
        requested = _facility_request_from_action(" ".join([action, proposed]), self._ensure_settlement_facilities(settlement))
        if not requested:
            requested = _facility_name_from_sub_location(settlement, proposed)
        if not requested:
            return None
        facility = self._find_or_create_facility_record(settlement, requested)
        if not facility:
            return None
        facility["location_name"] = settlement.name
        facility["sub_location"] = str(facility.get("name") or requested)
        self._set_active_facility(settlement, facility)
        self._ensure_facility_npc(settlement, facility, settlement.name)
        return {
            "location": settlement.name,
            "narration_lines": [],
            "status_lines": [],
            "moved": False,
            "denied": False,
        }

    def _location_default_choices(self, location_name: str) -> list[str]:
        if location_name == self.state.current_location and self._current_player_home():
            return self._home_choices()
        dangerous_choices = self._dangerous_subnode_default_choices(location_name)
        if dangerous_choices:
            return _exploration_choices(dangerous_choices)
        choices = ["休息する", "周囲を見る"]
        if self._location_has_movement_options(location_name):
            choices.append(MOVE_CHOICE_LABEL)
        active_facility = self._active_facility_record() if location_name == self.state.current_location else None
        active_is_guild = bool(active_facility and str(active_facility.get("type") or "").lower() == "guild")
        if self.state.active_quest:
            choices.insert(0, QUEST_ABANDON_CHOICE_LABEL)
            if self._active_quest_can_report_at(location_name):
                choices.insert(0, QUEST_REPORT_CHOICE_LABEL)
        elif (active_is_guild or _location_is_guild(self.state.world_data, location_name)) and not self.state.active_quest:
            choices.insert(0, QUEST_BOARD_CHOICE_LABEL)
        if location_name == self.state.current_location and active_facility and str(active_facility.get("type") or "").lower() == "town_hall":
            if not self._player_home_for_location(location_name):
                choices = [f"{cost}Goldで家を建てる" for cost in sorted(PLAYER_HOME_TOWN_HALL_PLANS)] + ["周囲を見る"]
        elif self._player_home_for_location(location_name):
            choices.insert(0, f"{PLAYER_HOME_NAME}へ移動")
        return _exploration_choices(choices)

    def _dangerous_subnode_default_choices(self, location_name: str) -> list[str]:
        world = self.state.world_data
        location = world.locations.get(str(location_name or "").strip())
        if not location or not (_is_dungeon_location(location) or _world_location_blocks_world_map_departure(location)):
            return []
        choices = ["休息する", "周囲を見る"]
        if self._location_has_movement_options(location_name):
            choices.append(MOVE_CHOICE_LABEL)
        return choices

    def _augment_location_choices(self, choices: list[str], location_name: str) -> list[str]:
        choices = self._filter_llm_choices_for_display(choices)
        dangerous_choices = self._dangerous_subnode_default_choices(location_name)
        if dangerous_choices:
            filtered = self._filter_dangerous_nonadjacent_move_choices(choices, location_name)
            if self._location_has_movement_options(location_name):
                filtered.append(MOVE_CHOICE_LABEL)
            return _exploration_choices([*filtered, *dangerous_choices])
        return _augment_location_choices_for_world(
            self.state.world_data,
            location_name,
            choices,
            active_quest=bool(self.state.active_quest),
            can_move=self._location_has_movement_options(location_name),
            quest_report_ready=self._active_quest_can_report_at(location_name),
        )

    def _filter_llm_choices_for_display(self, choices: list[str], *, keep_system_choices: bool = False) -> list[str]:
        return _filter_llm_display_choices(
            choices,
            keep_system_choices=keep_system_choices,
            allow_home_choices=self._current_player_home(),
        )

    def _filter_dangerous_nonadjacent_move_choices(self, choices: list[str], location_name: str) -> list[str]:
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        current_id = self._current_subnode_id(location_name)
        allowed_names: set[str] = set()
        for node_id in [current_id, *self._subnode_adjacent_ids(graph, current_id)]:
            node = nodes.get(node_id, {}) if isinstance(nodes.get(node_id), dict) else {}
            allowed_names.add(str(node.get("name") or node_id))
        for edge in self._subnode_external_edges(self.state.world_data, location_name, graph):
            if str(edge.get("from") or "") == current_id:
                allowed_names.add(str(edge.get("target_location") or ""))
        known_locations = [name for name in self.state.world_data.locations if name != location_name]
        result: list[str] = []
        for choice in choices:
            text = str(choice or "").strip()
            if not text:
                continue
            if not _choice_looks_like_movement(text):
                result.append(text)
                continue
            if any(allowed and allowed in text for allowed in allowed_names):
                result.append(text)
                continue
            if any(name and name in text for name in known_locations):
                continue
            if any(word in text for word in ("街", "町", "村", "外へ", "入口へ戻らず", "戻る", "ワールドマップ")):
                continue
            result.append(text)
        return result

    def _set_character_presence(self, character: Character, location: str, state: str = "present", subnode_id: str = "") -> None:
        self._ensure_character_runtime_data(character)
        requested_state = state or character.state or "present"
        if _character_state_is_dead(character) and requested_state not in {"dead", "corpse"}:
            self._mark_character_dead(character, source="presence_guard")
            return
        previous_subnode_location, previous_subnode_id = self._character_subnode_assignment(character)
        if location:
            character.location = location
            character.flags["current_location"] = location
            character.flags.setdefault("first_seen_location", location)
            character.extra.setdefault("origin_location", location)
            subnode_id = str(subnode_id or "").strip()
            if not subnode_id and previous_subnode_id and (not previous_subnode_location or previous_subnode_location == location):
                subnode_id = previous_subnode_id
            if not subnode_id and not character.flags.get("is_player"):
                location_data = self.state.world_data.locations.get(location)
                if location_data and _is_settlement_location(location_data):
                    facility = self._match_settlement_facility_for_character(location_data, character)
                    if facility:
                        subnode_id = self._stamp_character_facility_subnode(character, location_data, facility)
            if not subnode_id:
                subnode_id = self._runtime_subnode_for_presence(location)
            if subnode_id:
                self._set_character_subnode_fields(character, location, subnode_id)
            elif previous_subnode_location and previous_subnode_location != location:
                self._clear_character_subnode_fields(character)
        character.state = requested_state
        character.flags["state"] = character.state
        if _actor_state_is_present(character.state):
            character.flags["alive"] = True
        if character.state in {"dead", "corpse"}:
            self._mark_character_dead(character, source="presence")
        else:
            self._sync_companion_party_entry(character)

    def _ensure_character_runtime_data(
        self,
        character: Character,
        *,
        level: int | None = None,
        sync_vitals_to_formula: bool = False,
    ) -> None:
        if not character.uuid:
            character.uuid = uuid4().hex
        character.level = max(1, min(NPC_MAX_LEVEL, _safe_int(level if level is not None else character.level, 1)))
        attrs = _character_runtime_attributes(character)
        if not character.flags.get("is_player"):
            attrs = _npc_level_tendency_attributes(character, attrs)
        character.attributes = attrs
        character.extra["attributes"] = dict(attrs)
        ability = character.extra.setdefault("ability", {})
        if isinstance(ability, dict):
            ability["attributes"] = dict(attrs)
        old_current_hp = _safe_int(character.current_hp, 0)
        old_current_sp = _safe_int(character.current_sp, 0)
        calculated_hp = _character_calculated_max_hp(character)
        if sync_vitals_to_formula and not character.flags.get("is_player"):
            max_hp = calculated_hp
        else:
            max_hp = max(_safe_int(character.max_hp, 0), calculated_hp) if not character.flags.get("is_player") else (character.max_hp or calculated_hp)
        calculated_sp = _character_calculated_max_sp(character, max_hp=max_hp)
        if sync_vitals_to_formula and not character.flags.get("is_player"):
            max_sp = calculated_sp
        else:
            max_sp = max(_safe_int(character.max_sp, 0), calculated_sp) if not character.flags.get("is_player") else (character.max_sp or calculated_sp)
        character.max_hp = max(1, _safe_int(max_hp, 1))
        character.max_sp = max(1, _safe_int(max_sp, 1))
        current_hp = old_current_hp
        current_sp = old_current_sp
        if sync_vitals_to_formula and not character.flags.get("is_player") and not _character_state_is_dead(character):
            current_hp = character.max_hp
            current_sp = character.max_sp
        if current_hp <= 0 and not _character_state_is_dead(character):
            current_hp = character.max_hp
        if current_sp <= 0 and not _character_state_is_dead(character):
            current_sp = character.max_sp
        character.current_hp = max(0, min(character.max_hp, current_hp))
        character.current_sp = max(0, min(character.max_sp, current_sp))
        calculated_attack = _character_calculated_attack(character)
        calculated_defense = _character_calculated_defense(character)
        template_controlled = bool(character.extra.get("npc_template_id") or character.flags.get("npc_template_id"))
        if character.attack <= 0 or (
            not character.flags.get("is_player")
            and not template_controlled
            and character.attack < calculated_attack
        ):
            character.attack = calculated_attack
        if character.defense <= 0 or (
            not character.flags.get("is_player")
            and not template_controlled
            and character.defense < calculated_defense
        ):
            character.defense = calculated_defense
        character.extra["level"] = character.level
        character.extra["current_hp"] = character.current_hp
        character.extra["max_hp"] = character.max_hp
        character.extra["current_sp"] = character.current_sp
        character.extra["max_sp"] = character.max_sp
        character.extra["attack"] = character.attack
        character.extra["defense"] = character.defense
        character.flags["alive"] = not _character_state_is_dead(character)
        character.flags["uuid"] = character.uuid

    def _party_companions(self) -> list[Character]:
        refs = [str(item or "").strip() for item in self.state.party_uuids[1:] if str(item or "").strip()]
        for item in self.state.party[1:]:
            if not isinstance(item, dict):
                continue
            uuid = str(item.get("uuid") or "").strip()
            if uuid:
                refs.append(uuid)
                continue
            name = str(item.get("name") or item.get("character_name") or "").strip()
            if name:
                refs.append(name)
        result: list[Character] = []
        seen: set[str] = set()
        for ref in refs:
            character = self.state.world_data.character(ref)
            if not character or character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            if character.uuid in seen:
                continue
            seen.add(character.uuid)
            result.append(character)
        return result[:PARTY_COMPANION_LIMIT]

    def _sync_companion_party_entry(self, character: Character) -> None:
        if character.flags.get("is_player"):
            return
        for index, item in enumerate(self.state.party[1:], start=1):
            if not isinstance(item, dict):
                continue
            if item.get("name") != character.name and item.get("uuid") != character.uuid:
                continue
            entry = character.to_dict()
            entry["party_role"] = "companion"
            self.state.party[index] = entry
            return

    def _set_party_companion(self, character: Character | None, *, source: str, reason: str = "") -> list[str]:
        player = self.player_character()
        player_entry = player.to_dict() if player else None
        if character is None:
            if len(self.state.party_uuids) > 1 or len(self.state.party) > 1:
                removed = self.state.party[1:]
                for uuid in self.state.party_uuids[1:]:
                    npc = self.state.world_data.character(uuid)
                    if npc and not _character_state_is_dead(npc):
                        self._return_companion_to_origin(npc, source=source, reason=reason)
                self.state.party_uuids = [player.uuid] if player else []
                self.state.party = [player_entry] if player_entry else []
                for item in removed:
                    if isinstance(item, dict):
                        npc = self.state.world_data.character(str(item.get("uuid") or item.get("name") or ""))
                        if npc and not _character_state_is_dead(npc):
                            self._return_companion_to_origin(npc, source=source, reason=reason)
                return ["> [Party] Companion left the party."]
            return []
        if character.flags.get("is_player") or _character_state_is_dead(character):
            return []
        self._ensure_character_runtime_data(character)
        companions = self._party_companions()
        for existing in companions:
            if existing.name == character.name or existing.uuid == character.uuid:
                self._set_character_presence(existing, self.state.current_location or existing.location or self.state.world_data.starting_location, "party")
                self._sync_companion_party_entry(existing)
                return []
        if len(companions) >= PARTY_COMPANION_LIMIT:
            return [f"> [Party] Party is full. Dismiss a companion before inviting {character.name}."]
        self._set_character_presence(character, self.state.current_location or character.location or self.state.world_data.starting_location, "party")
        companions.append(character)
        companion_entries: list[dict[str, Any]] = []
        for companion in companions[:PARTY_COMPANION_LIMIT]:
            entry = companion.to_dict()
            entry["party_role"] = "companion"
            companion_entries.append(entry)
        self.state.party_uuids = ([player.uuid] if player else []) + [companion.uuid for companion in companions[:PARTY_COMPANION_LIMIT]]
        self.state.party = ([player_entry] if player_entry else []) + companion_entries
        event = {
            "source": source,
            "character": character.name,
            "uuid": character.uuid,
            "location": character.location,
            "reason": reason,
            "day": self.state.day,
        }
        self.state.world_data.extra.setdefault("party_events", []).append({**event, "action": "join"})
        reason_text = f" {reason}" if reason else ""
        return [f"> [Party] {character.name} joined the party.{reason_text}"]

    def _remove_party_companion(
        self,
        character: Character,
        *,
        source: str,
        reason: str = "",
        wait_at_current: bool = False,
    ) -> list[str]:
        before = (len(self.state.party), len(self.state.party_uuids))
        self.state.party_uuids = [uuid for uuid in self.state.party_uuids if uuid != character.uuid]
        self.state.party = [
            item
            for index, item in enumerate(self.state.party)
            if _party_entry_is_player(item, self.state.player_name)
            or not (isinstance(item, dict) and (item.get("name") == character.name or item.get("uuid") == character.uuid))
        ]
        if (len(self.state.party), len(self.state.party_uuids)) == before:
            return []
        if not _character_state_is_dead(character):
            if wait_at_current:
                self._set_companion_waiting(character, source=source, reason=reason)
            else:
                self._return_companion_to_origin(character, source=source, reason=reason)
        event = {
            "source": source,
            "character": character.name,
            "uuid": character.uuid,
            "location": character.location,
            "reason": reason,
            "day": self.state.day,
            "action": "leave",
        }
        self.state.world_data.extra.setdefault("party_events", []).append(event)
        reason_text = f" {reason}" if reason else ""
        action_text = "waits here" if wait_at_current else "returned home"
        return [f"> [Party] {character.name} left the party and {action_text}.{reason_text}"]

    def _set_companion_waiting(self, character: Character, *, source: str, reason: str = "") -> None:
        day = self.current_absolute_day()
        location = self.state.current_location or character.location or self.state.world_data.starting_location
        origin = self._character_origin_location(character)
        self._set_character_presence(character, location, "waiting")
        character.extra["party_waiting"] = {
            "source": source,
            "reason": reason,
            "started_day": day,
            "expires_day": day + COMPANION_WAIT_RETURN_DAYS,
            "wait_location": location,
            "origin_location": origin,
        }

    def _return_companion_to_origin(self, character: Character, *, source: str, reason: str = "") -> str:
        origin = self._character_origin_location(character)
        origin_subnode = self._character_origin_subnode_id(character)
        character.extra.pop("party_waiting", None)
        if origin:
            self.state.world_data.ensure_location(origin)
            self._set_character_presence(character, origin, "present", subnode_id=origin_subnode)
        else:
            self._set_character_presence(character, character.location or self.state.current_location, "present")
        character.extra.setdefault("party_return_events", []).append(
            {
                "source": source,
                "reason": reason,
                "location": character.location,
                "day": self.state.day,
            }
        )
        return character.location

    def _character_origin_location(self, character: Character) -> str:
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        for value in (
            extra.get("origin_location"),
            extra.get("home_location"),
            extra.get("spawn_location"),
            flags.get("first_seen_location"),
            flags.get("current_location"),
            character.location,
            self.state.world_data.starting_location,
        ):
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _character_origin_subnode_id(self, character: Character) -> str:
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        for value in (
            extra.get("origin_subnode_id"),
            extra.get("home_subnode_id"),
            extra.get("spawn_subnode_id"),
            extra.get(ACTOR_SUBNODE_ID_FLAG),
            flags.get(ACTOR_SUBNODE_ID_FLAG),
        ):
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _resolve_pending_companion_returns(self, *, source: str) -> list[str]:
        current_day = self.current_absolute_day()
        lines: list[str] = []
        for character in list(self.state.world_data.characters.values()):
            if character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            waiting = character.extra.get("party_waiting") if isinstance(character.extra, dict) else None
            if not isinstance(waiting, dict):
                continue
            started_day = _safe_int(waiting.get("started_day"), current_day)
            expires_day = _safe_int(waiting.get("expires_day"), started_day + COMPANION_WAIT_RETURN_DAYS)
            if current_day < expires_day:
                continue
            old_location = character.location or str(waiting.get("wait_location") or "")
            origin = self._character_origin_location(character)
            if self._companion_can_return_to_origin(character):
                destination = self._return_companion_to_origin(character, source=source, reason="wait_expired")
                line = f"> [Party] {character.name} returned from {old_location or '-'} to {destination or origin or '-'}."
                action = "return"
            else:
                character.extra.pop("party_waiting", None)
                self._mark_character_dead(character, source="companion_wait_timeout")
                line = f"> [Party] {character.name} could not return from {old_location or '-'} and died."
                action = "dead"
            self.state.world_data.extra.setdefault("companion_wait_events", []).append(
                {
                    "source": source,
                    "character": character.name,
                    "uuid": character.uuid,
                    "action": action,
                    "old_location": old_location,
                    "origin_location": origin,
                    "day": current_day,
                }
            )
            lines.append(line)
        return lines

    def _companion_can_return_to_origin(self, character: Character) -> bool:
        world = self.state.world_data
        origin = self._character_origin_location(character)
        current = character.location or str(character.flags.get("current_location") or "")
        if not origin or not current:
            return False
        if origin == current:
            return True
        if origin not in world.locations or current not in world.locations:
            return False
        if not _world_location_allows_world_map_departure(world, current):
            return False
        return bool(self._shortest_world_path(world, current, origin, visited_only=False))

    def _mark_character_dead(self, character: Character, *, source: str) -> None:
        if character.flags.get("is_player"):
            character.state = "dead"
            character.flags["state"] = "dead"
            character.flags["alive"] = False
            return
        character.state = "dead"
        character.current_hp = 0
        character.flags["state"] = "dead"
        character.flags["alive"] = False
        character.flags["dead"] = True
        character.extra["death_source"] = source
        dead_uuids = self.state.world_data.extra.setdefault("dead_npc_uuids", [])
        if isinstance(dead_uuids, list) and character.uuid not in dead_uuids:
            dead_uuids.append(character.uuid)
        dead_names = self.state.world_data.extra.setdefault("dead_npc_names", [])
        if isinstance(dead_names, list) and character.name not in dead_names:
            dead_names.append(character.name)
        self.state.party = [
            item
            for item in self.state.party
            if not (isinstance(item, dict) and (item.get("name") == character.name or item.get("uuid") == character.uuid))
        ]

    def prepare_vendor_inventory(self, character: Character) -> dict[str, Any]:
        day = self.current_absolute_day()
        extra = character.extra if isinstance(character.extra, dict) else {}
        if character.extra is not extra:
            character.extra = extra
        if _safe_int(extra.get("vendor_inventory_day"), 0) == day and character.inventory:
            return {"changed": False, "day": day}
        facility_type = str(extra.get("facility_type") or "").strip().lower()
        if not facility_type:
            location = self.state.world_data.locations.get(character.location or str(character.flags.get("current_location") or ""))
            facility_type = str((location.extra.get("facility_type") if location else "") or "").strip().lower()
        if not facility_type:
            facility_type = _facility_type_from_name(str(extra.get("facility") or character.role or character.name))
        template_shop_table = extra.get("shopItem") or extra.get("shop_item_table")
        if template_shop_table:
            character.inventory = generate_loot_table_items(
                template_shop_table,
                context=f"{character.name}:{facility_type}:day:{day}",
                danger_level=self._current_location_danger(character.location or self.state.current_location),
                seed=f"vendor-template|{self.state.world_name}|{character.uuid}|{day}",
                source="vendor_template",
            )
            character.gold = character.gold or 120
            extra["vendor_inventory_day"] = day
            extra["vendor_base_price_multiplier"] = SHOP_FACILITY_PRICE_MULTIPLIERS.get(facility_type, 1.0)
            extra["trade_price_multiplier"] = 1.0
            extra["trade_negotiation"] = {}
            event = {
                "character": character.name,
                "day": day,
                "location": self.state.current_location,
                "items": [normalise_item(item) for item in character.inventory],
                "source": "location_local_template",
            }
            self.state.world_data.extra.setdefault("vendor_inventory_events", []).append(event)
            return {"changed": True, "day": day, "event": event}
        loot_tabel_id = SHOP_LOOT_TABEL_BY_FACILITY_TYPE.get(facility_type, DEFAULT_VENDOR_LOOT_TABEL_ID)
        character.inventory = generate_loot_table_items(
            loot_tabel_id,
            context=f"{character.name}:{facility_type}:day:{day}",
            danger_level=self._current_location_danger(character.location or self.state.current_location),
            seed=f"vendor-fallback|{self.state.world_name}|{character.uuid}|{day}",
            source="vendor_fallback",
        )
        character.gold = character.gold or 120
        extra["vendor_inventory_day"] = day
        extra["vendor_base_price_multiplier"] = SHOP_FACILITY_PRICE_MULTIPLIERS.get(facility_type, 1.0)
        extra["trade_price_multiplier"] = 1.0
        extra["trade_negotiation"] = {}
        event = {
            "character": character.name,
            "day": day,
            "location": self.state.current_location,
            "items": [normalise_item(item) for item in character.inventory],
            "loot_tabel_id": loot_tabel_id,
            "source": "facility_type_fallback",
        }
        self.state.world_data.extra.setdefault("vendor_inventory_events", []).append(event)
        return {"changed": True, "day": day, "event": event}

    def vendor_price_multiplier(self, character: Character | None) -> float:
        if character is None or not isinstance(character.extra, dict):
            return 1.0
        try:
            base = float(character.extra.get("vendor_base_price_multiplier", 1.0))
        except (TypeError, ValueError):
            base = 1.0
        try:
            negotiation = float(character.extra.get("trade_price_multiplier", 1.0))
        except (TypeError, ValueError):
            negotiation = 1.0
        value = base * negotiation
        return max(0.5, min(4.5, value))

    def _current_trade_candidates(self) -> list[Character]:
        current_location = self.state.current_location or self.state.world_data.starting_location
        candidates: list[Character] = []
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, current_location):
                continue
            if not self._character_matches_active_facility(character):
                continue
            if self._character_can_trade(character):
                candidates.append(character)
        return candidates

    def _character_matches_trade_action(self, character: Character, action: str) -> bool:
        action_text = str(action or "").strip()
        if not action_text:
            return False
        folded_action = action_text.casefold()
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        terms = _character_reference_terms(character)
        terms.extend(
            [
                str(extra.get("facility") or flags.get("facility_name") or ""),
                str(extra.get("facility_type") or flags.get("facility_type") or ""),
            ]
        )
        for term in _dedupe_strs([str(item or "").strip() for item in terms]):
            if term and (term in action_text or term.casefold() in folded_action):
                return True
        return False

    def _trade_negotiation_target(self, action: str) -> Character | None:
        if not _is_trade_negotiation_action(action):
            return None
        candidates = self._current_trade_candidates()
        if not candidates:
            return None
        for character in candidates:
            if self._character_matches_trade_action(character, action):
                return character
        active = self._active_conversation_character()
        if active:
            for candidate in candidates:
                if candidate.name == active.name or str(candidate.uuid) == str(active.uuid):
                    return candidate
        resolved = self._resolve_context_reference(action, "trade_negotiation_target", allowed_target_types=["character"])
        resolved_character = self._match_character_reference_from_candidates(
            str(resolved.get("target_name") or ""),
            candidates,
        )
        if resolved_character:
            return resolved_character
        return candidates[0] if len(candidates) == 1 else None

    def _character_can_trade(self, character: Character) -> bool:
        if character.flags.get("is_player") or _character_state_is_dead(character):
            return False
        extra = character.extra if isinstance(character.extra, dict) else {}
        if character.inventory or extra.get("vendor_inventory_day") or extra.get("trade_price_multiplier") is not None:
            return True
        location = self.state.world_data.locations.get(character.location or str(character.flags.get("current_location") or ""))
        location_type = str((location.extra.get("facility_type") if location else "") or "").casefold()
        if location_type in SHOP_FACILITY_TYPES or location_type in {"weapon_shop", "armor_shop", "store"}:
            return True
        text = "\n".join(
            str(value or "")
            for value in (
                character.name,
                character.role,
                character.category,
                character.backstory,
                extra.get("facility"),
                extra.get("facility_type"),
                extra.get("occupation"),
                extra.get("archetype"),
            )
        ).casefold()
        return any(
            keyword in text
            for keyword in (
                "shop",
                "store",
                "market",
                "merchant",
                "vendor",
                "trader",
                "blacksmith",
                "black market",
                "apothecary",
                "food store",
                "material store",
                "general store",
                "magic store",
                "闇商店",
                "薬品店",
                "食料店",
                "素材店",
                "雑貨店",
                "魔術店",
                "店",
                "商人",
                "店主",
                "商店",
                "市場",
                "露店",
                "行商",
                "鍛冶",
                "武器",
                "防具",
                "道具",
                "薬",
            )
        )

    def _resolve_trade_negotiation_action(self, action: str, input_type: str, character: Character) -> str:
        location = self.state.current_location or character.location or self.state.world_data.starting_location
        vendor_event = self.prepare_vendor_inventory(character)
        event = self.roll_trade_negotiation(character, action)
        line = str(event.get("line") or "")
        roll = event.get("roll") if isinstance(event, dict) else None
        percent = int(round(self.vendor_price_multiplier(character) * 100))
        if event.get("already_done"):
            narration = line or f"{character.name}との今日の値引き交渉はすでに終わっている。"
        else:
            narration = f"{character.name}に値引き交渉を試みた。現在の購入価格は{percent}%になった。"
        choices = self.state.choices or self._location_default_choices(location)
        self._append_turn(action, narration, location, choices, input_type=input_type)
        if vendor_event.get("changed"):
            self.state.world_data.history.append(
                {
                    "manager": "prepare_vendor_inventory",
                    "character": character.name,
                    "location": location,
                    "response": vendor_event,
                }
            )
        display_lines: list[str] = []
        if isinstance(roll, dict) and roll.get("line"):
            display_lines.append(str(roll["line"]))
        if line:
            display_lines.append(line)
        display_lines.extend(str(item) for item in event.get("relationship_lines", []) if item)
        if display_lines:
            self.state.display_log.extend(display_lines)
        self.state.world_data.history.append(
            {
                "manager": "trade_negotiation",
                "character": character.name,
                "action": action,
                "input_type": input_type,
                "location": location,
                "event": event,
            }
        )
        self.save_game()
        return self.state.log_text(16)

    def roll_trade_negotiation(self, character: Character, action: str = "") -> dict[str, Any]:
        day = self.current_absolute_day()
        extra = character.extra if isinstance(character.extra, dict) else {}
        if character.extra is not extra:
            character.extra = extra
        previous = extra.get("trade_negotiation")
        if isinstance(previous, dict) and _safe_int(previous.get("day"), 0) == day:
            return {"changed": False, "already_done": True, "line": "> [交渉] 今日の値引き交渉はすでに終わっている。"}
        affinity = self._npc_affinity(character)
        target = 10
        if affinity >= 60:
            target = 7
        elif affinity >= 30:
            target = 8
        elif affinity <= -60:
            target = 13
        elif affinity <= -30:
            target = 12
        roll = self._make_action_roll(
            action.strip() or f"{character.name}に値引き交渉をする",
            purpose="conversation",
            forced_ability="cha",
            forced_target=target,
        )
        if roll.get("critical_success"):
            multiplier = 0.80
            affinity_delta = 1
        elif roll.get("success"):
            multiplier = 0.90
            affinity_delta = 0
        elif roll.get("critical_failure"):
            multiplier = 1.25
            affinity_delta = -1
        else:
            multiplier = 1.10
            affinity_delta = 0
        old_multiplier = self.vendor_price_multiplier(character)
        extra["trade_price_multiplier"] = multiplier
        extra["trade_negotiation"] = {
            "day": day,
            "action": action,
            "roll": roll,
            "old_multiplier": old_multiplier,
            "new_multiplier": multiplier,
        }
        relationship_lines: list[str] = []
        if affinity_delta:
            relationship_lines = self._apply_npc_affinity_delta(character, affinity_delta, source="trade_negotiation", reason="値引き交渉")
        percent = int(round(self.vendor_price_multiplier(character) * 100))
        outcome = "値引き" if multiplier < 1.0 else "値上げ"
        line = f"> [交渉] {character.name}: {outcome}（購入価格 {percent}%）"
        event = {
            "character": character.name,
            "day": day,
            "location": self.state.current_location,
            "action": action,
            "roll": roll,
            "old_multiplier": old_multiplier,
            "new_multiplier": multiplier,
            "line": line,
        }
        self.state.world_data.extra.setdefault("trade_negotiation_events", []).append(event)
        return {
            "changed": True,
            "character": character.name,
            "roll": roll,
            "multiplier": multiplier,
            "line": line,
            "relationship_lines": relationship_lines,
        }

    def _npc_affinity(self, character: Character) -> int:
        if not isinstance(character.extra, dict):
            character.extra = {}
        value = character.extra.get("affinity", character.extra.get("trust", 0))
        return max(NPC_AFFINITY_MIN, min(NPC_AFFINITY_MAX, _safe_int(value, 0)))

    def _apply_npc_affinity_delta(self, character: Character, delta: Any, *, source: str, reason: str = "") -> list[str]:
        if character.flags.get("is_player"):
            return []
        requested_delta = max(NPC_AFFINITY_DELTA_MIN, min(NPC_AFFINITY_DELTA_MAX, _safe_int(delta, 0)))
        if not requested_delta:
            return []
        old_value = self._npc_affinity(character)
        new_value = max(NPC_AFFINITY_MIN, min(NPC_AFFINITY_MAX, old_value + requested_delta))
        actual_delta = new_value - old_value
        if not actual_delta:
            return []
        character.extra["affinity"] = new_value
        character.extra["trust"] = new_value
        change = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "day": self.state.day,
            "old": old_value,
            "new": new_value,
            "delta": actual_delta,
        }
        character.extra.setdefault("relationship_changes", []).append(change)
        self.state.world_data.extra.setdefault("npc_affinity_events", []).append({"character": character.name, **change})
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        reason_text = f" {reason}" if reason else ""
        return [f"> [好感度] {character.name}: {old_value} -> {new_value} ({sign}){reason_text}"]

    def _apply_response_npc_move_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
        default_location: str = "",
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("npc_move", "npc_moves", "npc_movement", "npc_movements", "character_movement", "character_movements", "move_npc", "move_npcs"):
            entries.extend(_as_list(response.get(key)))
        fallback_location = default_location or str(response.get("location") or self.state.current_location or self.state.world_data.starting_location)
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            target_location = _movement_target_location(entry, fallback_location)
            if not target_location:
                continue
            old_location = character.location or str(character.flags.get("current_location") or "")
            state = _movement_target_state(entry, character.state or "present")
            if state in {"party", "companion"}:
                state = "present"
            self.state.world_data.ensure_location(target_location)
            self._set_character_presence(character, target_location, state)
            event = {
                "source": source,
                "character": character.name,
                "old_location": old_location,
                "new_location": target_location,
                "state": state,
                "day": self.state.day,
                "reason": _relationship_reason(entry),
            }
            self.state.world_data.extra.setdefault("npc_movement_events", []).append(event)
            if old_location != target_location:
                lines.append(f"> [NPC移動] {character.name}: {old_location or '-'} -> {target_location}")
        return lines

    def _apply_response_npc_join_party_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("npc_join_party", "join_party", "party_join", "followers", "escorted_npcs"):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            lines.extend(self._set_party_companion(character, source=source, reason=_relationship_reason(entry)))
        return lines

    def _apply_response_npc_remove_party_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
        default_location: str = "",
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("npc_remove_party", "remove_party", "leave_party", "party_leave", "dismiss_party_member"):
            entries.extend(_as_list(response.get(key)))
        fallback_location = default_location or self.state.current_location or self.state.world_data.starting_location
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            wait_here = bool(isinstance(entry, dict) and _as_bool(entry.get("wait") or entry.get("stay") or entry.get("wait_here")))
            lines.extend(self._remove_party_companion(character, source=source, reason=_relationship_reason(entry), wait_at_current=wait_here))
            if isinstance(entry, dict) and _movement_has_explicit_location(entry):
                target_location = _movement_target_location(entry, fallback_location)
                if target_location:
                    self.state.world_data.ensure_location(target_location)
                    self._set_character_presence(character, target_location, _movement_target_state(entry, "present"))
        return lines

    def _apply_response_npc_dead_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("npc_dead", "npc_death", "dead_npc", "dead_npcs", "kill_npc", "killed_npc"):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            self._mark_character_dead(character, source=source)
            self._remove_party_companion(character, source=source, reason=_relationship_reason(entry))
            lines.append(f"> [NPC] {character.name} is dead.")
        return lines

    def _apply_response_npc_memory_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("npc_update_memory", "memory_updates", "memory_update", "memories"):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            memory = _npc_memory_text(entry)
            if not memory:
                continue
            record = {"source": source, "day": self.state.day, "memory": memory}
            character.extra.setdefault("memory_updates", []).append(record)
            character.extra.setdefault("player_memories", []).append(record)
            lines.append(f"> [NPC Memory] {character.name}: {memory}")
        return lines

    def _apply_response_npc_description_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("npc_update_description", "npc_description_update", "npc_description_updates", "description_update"):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            updated = _npc_updated_description_text(entry)
            if not updated:
                continue
            old_description = str(character.extra.get("description") or character.backstory or "").strip()
            character.extra["previous_description"] = old_description
            character.extra["description"] = updated
            character.backstory = updated
            character.extra.setdefault("description_updates", []).append(
                {"source": source, "day": self.state.day, "old": old_description, "new": updated}
            )
            lines.append(f"> [NPC Description] {character.name} updated.")
        return lines

    def _apply_response_capture_relocation_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
        default_location: str = "",
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        explicit_capture = isinstance(response, dict) and any(
            key in response for key in ("npc_capture_player", "capture_player", "capture_relocation")
        )
        if encounter is None or not isinstance(response, dict) or not (explicit_capture or _response_implies_capture_relocation(response)):
            return []
        world = self.state.world_data
        location_name = str(default_location or (encounter or {}).get("location") or self.state.current_location or world.starting_location).strip()
        location = world.locations.get(location_name) if location_name else None
        if location is None:
            return []
        if not isinstance(location.extra.get(SUBNODE_GRAPH_KEY), dict):
            location.extra[SUBNODE_GRAPH_KEY] = {"nodes": {}, "edges": []}
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if not nodes:
            self._ensure_basic_subnodes(location, graph)
            nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if not nodes:
            return []

        opponent_name = ""
        if isinstance(default_character, Character):
            opponent_name = default_character.name
        if not opponent_name and isinstance(encounter, dict):
            opponent_name = str(encounter.get("opponent_name") or encounter.get("active_opponent_name") or "")
        node_id = f"capture:{_world_location_name_key(opponent_name) or 'site'}"
        name = _capture_subnode_name(response, opponent_name)
        description = _capture_subnode_description(response, opponent_name)
        parent = self._current_subnode_id(location.name) or self._subnode_anchor(graph, prefer_deep=True, exclude=node_id)
        if parent == node_id:
            parent = self._subnode_anchor(graph, prefer_deep=True, exclude=node_id)
        parent_node = nodes.get(parent, {}) if isinstance(nodes.get(parent), dict) else {}
        x = _safe_int(parent_node.get("x"), 320) + 120
        y = _safe_int(parent_node.get("y"), 220) + 100
        node = self._upsert_subnode_node(
            graph,
            node_id,
            name,
            description,
            "capture_site",
            x,
            y,
            capture_site=True,
            source=source,
            world_map_exit=False,
        )
        if parent:
            self._connect_subnodes(graph, parent, node_id, kind="capture_path")
        self._ensure_subnode_connected_to_anchor(graph, node_id, kind="capture_path", prefer_deep=True)
        start_node = DUNGEON_ENTRY_SUBNODE_ID if DUNGEON_ENTRY_SUBNODE_ID in nodes else self._current_subnode_id(location.name)
        self._mark_subnode_route_visited(graph, start_node, node_id)
        already_current = self._current_subnode_id(location.name) == node_id
        if not already_current:
            self._set_current_subnode(location.name, node_id)
        self.state.current_location = location.name
        self._set_player_presence(location.name)
        if isinstance(default_character, Character):
            self._set_character_presence(default_character, location.name, "present", subnode_id=node_id)
        if isinstance(encounter, dict):
            encounter["location"] = location.name
            encounter["player_status"] = str(encounter.get("player_status") or "captured")
            encounter["capture_relocated"] = True
            encounter["capture_subnode_id"] = node_id
            encounter["capture_subnode_name"] = str(node.get("name") or name)
        event = {
            "source": source,
            "location": location.name,
            "subnode_id": node_id,
            "subnode_name": str(node.get("name") or name),
            "opponent": opponent_name,
        }
        world.extra.setdefault("capture_relocation_events", []).append(event)
        return [] if already_current else [f"> [Move] Captured and moved to {event['subnode_name']}."]

    def _apply_response_home_construction_effects(self, response: dict[str, Any], source: str) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in ("home_construction", "player_home_construction", "home_building", "player_home_building"):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            lines.extend(
                self._apply_home_construction_entry(
                    entry,
                    source=source,
                    action="家を建てる",
                    input_type="free_action",
                    append_turn=False,
                )
            )
        return lines

    def _apply_response_map_reveals(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_location: str = "",
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in (
            "map_reveal",
            "map_reveals",
            "reveal_map",
            "reveal_maps",
            "world_map_reveal",
            "world_map_reveals",
            "reveal_world_map",
            "reveal_world_maps",
            "unlock_world_map_route",
            "unlock_world_map_routes",
            "map_route_reveal",
            "map_route_reveals",
        ):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            result = self._reveal_world_map_route(entry, source=source, default_location=default_location)
            if result.get("line"):
                lines.append(str(result["line"]))
        return lines

    def _reveal_world_map_route(self, entry: Any, *, source: str, default_location: str = "") -> dict[str, Any]:
        world = self.state.world_data
        graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), 1))
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        start = self._map_reveal_start_location(entry, default_location)
        target = self._map_reveal_target_location(entry)
        route = self._map_reveal_route_locations(entry)
        if not target and route:
            target = route[-1]
        if not start:
            start = self.state.current_location or world.starting_location
        start = self._find_world_location_by_name(start) or start
        target = self._find_world_location_by_name(target) or target
        if not start or start not in nodes:
            return {"changed": False, "reason": "missing_start"}
        if not target:
            return {"changed": False, "reason": "missing_target"}
        if target not in nodes and target in world.locations:
            self._set_location_graph_node(world, target, location=world.locations[target])
            nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if target not in nodes:
            return {"changed": False, "reason": "missing_target_node", "target": target}

        resolved_route = [self._find_world_location_by_name(name) or name for name in route]
        resolved_route = [name for name in resolved_route if name in nodes]
        if resolved_route:
            if resolved_route[0] != start:
                resolved_route.insert(0, start)
            if resolved_route[-1] != target:
                resolved_route.append(target)
            for a, b in zip(resolved_route, resolved_route[1:]):
                if not self._world_neighbors_no_ensure(world, a) or b not in self._world_neighbors_no_ensure(world, a):
                    self._connect_world_locations(world, a, b, kind="map_route")
            path = resolved_route
        else:
            path = self._shortest_world_path(world, start, target, visited_only=False)
            if not path:
                self._connect_world_locations(world, start, target, kind="map_route")
                path = [start, target]

        changed = False
        for name in path:
            node = nodes.get(name)
            was_visible = bool(isinstance(node, dict) and node.get("visited"))
            self._mark_location_visited(world, name)
            if not was_visible:
                changed = True
        event = {
            "source": source,
            "start": start,
            "target": target,
            "path": path,
            "reason": _map_reveal_reason(entry),
            "changed": changed,
        }
        world.extra.setdefault("map_reveal_events", []).append(event)
        line = f"> [Map] 地図に経路を記録: {' -> '.join(path)}"
        return {**event, "line": line}

    def _map_reveal_start_location(self, entry: Any, default_location: str = "") -> str:
        if isinstance(entry, dict):
            for key in ("from", "origin", "start", "source", "source_location", "current_location"):
                value = str(entry.get(key) or "").strip()
                if value:
                    return value
        return default_location or self.state.current_location or self.state.world_data.starting_location

    def _map_reveal_target_location(self, entry: Any) -> str:
        if entry is True:
            return self._active_quest_destination_location()
        if isinstance(entry, dict):
            quest_name = str(entry.get("quest") or entry.get("quest_name") or "").strip()
            if _map_reveal_value_means_active_quest(quest_name):
                quest_name = self.state.active_quest
            if quest_name:
                quest = self._find_quest_by_name(quest_name)
                if quest:
                    destination = quest.extra.get("destination") if isinstance(quest.extra, dict) else {}
                    if isinstance(destination, dict):
                        location = str(destination.get("location") or "").strip()
                        if location:
                            return location
            for key in ("target_location", "destination_location", "target", "destination", "to", "location"):
                value = str(entry.get(key) or "").strip()
                if not value:
                    continue
                if _map_reveal_value_means_active_quest(value):
                    return self._active_quest_destination_location()
                return value
            return self._active_quest_destination_location() if _as_bool(entry.get("active_quest") or entry.get("quest_destination")) else ""
        value = str(entry or "").strip()
        if _map_reveal_value_means_active_quest(value):
            return self._active_quest_destination_location()
        return value

    def _map_reveal_route_locations(self, entry: Any) -> list[str]:
        if not isinstance(entry, dict):
            return []
        for key in ("route", "path", "locations", "nodes", "route_locations", "path_locations"):
            values = _as_str_list(entry.get(key))
            if values:
                return values
        return []

    def _apply_response_world_mainnode_reveals(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_location: str = "",
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in (
            "world_mainnode_reveal",
            "world_mainnode_reveals",
            "mainnode_reveal",
            "mainnode_reveals",
            "world_route_reveal",
            "world_route_reveals",
        ):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            result = self._reveal_world_mainnode_route(entry, source=source, default_location=default_location)
            if result.get("line"):
                lines.append(str(result["line"]))
        return lines

    def _reveal_world_mainnode_route(self, entry: Any, *, source: str, default_location: str = "") -> dict[str, Any]:
        world = self.state.world_data
        start = self._map_reveal_start_location(entry, default_location)
        target = self._map_reveal_target_location(entry)
        if not start:
            start = self.state.current_location or world.starting_location
        start = self._find_world_location_by_name(start) or start
        target = self._find_world_location_by_name(target) or target
        if not start or start not in world.locations:
            return {"changed": False, "reason": "missing_start"}
        if not target or target not in world.locations:
            return {"changed": False, "reason": "missing_target"}
        path = self._shortest_world_path(world, start, target, visited_only=False)
        if not path:
            return {"changed": False, "reason": "missing_world_path", "start": start, "target": target}

        changed = False
        revealed_subnode_paths: list[dict[str, Any]] = []
        for index, location_name in enumerate(path):
            location = world.locations.get(location_name)
            if location is None:
                continue
            graph = self._ensure_location_subnode_graph(world, location_name)
            nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
            if not nodes:
                continue
            previous_location = path[index - 1] if index > 0 else ""
            next_location = path[index + 1] if index + 1 < len(path) else ""
            start_subnode = self._current_subnode_id(location_name) if location_name == start else ""
            if previous_location:
                previous_edge = self._world_edge_between(world, previous_location, location_name)
                if previous_edge:
                    start_subnode = self._world_edge_subnode_for_location(world, previous_edge, location_name)
            if not start_subnode or start_subnode not in nodes:
                start_subnode = self._default_subnode_for_location(location)
            target_subnode = start_subnode
            if next_location:
                next_edge = self._world_edge_between(world, location_name, next_location)
                if next_edge:
                    target_subnode = self._world_edge_subnode_for_location(world, next_edge, location_name)
            if not target_subnode or target_subnode not in nodes:
                target_subnode = self._default_subnode_for_location(location)
            subpath = self._subnode_path(graph, start_subnode, target_subnode)
            if not subpath and target_subnode in nodes:
                subpath = [target_subnode]
            named_path: list[str] = []
            for node_id in subpath:
                node = nodes.get(node_id)
                if not isinstance(node, dict):
                    continue
                if not node.get("revealed") and not node.get("visited"):
                    changed = True
                node["revealed"] = True
                named_path.append(str(node.get("name") or node_id))
            if named_path:
                revealed_subnode_paths.append({"location": location_name, "path": subpath, "named_path": named_path})
            world_graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), 1))
            world_nodes = world_graph.get("nodes", {}) if isinstance(world_graph.get("nodes"), dict) else {}
            if isinstance(world_nodes.get(location_name), dict) and not world_nodes[location_name].get("visited"):
                changed = True
            self._mark_location_visited(world, location_name)
        event = {
            "source": source,
            "start": start,
            "target": target,
            "path": path,
            "subnode_paths": revealed_subnode_paths,
            "reason": _map_reveal_reason(entry),
            "changed": changed,
        }
        world.extra.setdefault("mainnode_reveal_events", []).append(event)
        line = f"> [Map] ワールド経路を表示: {' -> '.join(path)}"
        return {**event, "line": line}

    def _apply_response_subnode_map_reveals(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_location: str = "",
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in (
            "subnode_map_reveal",
            "subnode_map_reveals",
            "reveal_subnode_map",
            "reveal_subnode_maps",
            "unlock_subnode_route",
            "unlock_subnode_routes",
        ):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            result = self._reveal_subnode_map_route(entry, source=source, default_location=default_location)
            if result.get("line"):
                lines.append(str(result["line"]))
        return lines

    def _apply_response_generate_dungeon_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_location: str = "",
    ) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {"created": False, "revealed": False, "lines": [], "events": []}
        raw_entries: list[Any] = []
        for key in ("generate_dungeon", "dungeon", "dungeons", "location"):
            value = response.get(key)
            if value not in (None, "", [], {}):
                raw_entries.extend(_as_list(value))
        if not raw_entries and any(
            key in response
            for key in ("name", "dungeon_name", "description", "dungeon_subtype", "location_kind", "anchor_location")
        ):
            raw_entries.append(response)
        events: list[dict[str, Any]] = []
        lines: list[str] = []
        for raw in raw_entries[:3]:
            entry = raw if isinstance(raw, dict) else {}
            event = self._generate_dungeon_from_tool_entry(entry, source=source, default_location=default_location)
            events.append(event)
            lines.extend(str(line) for line in event.get("lines", []) if str(line).strip())
        return {
            "created": any(bool(event.get("created")) for event in events),
            "revealed": any(bool(event.get("revealed")) for event in events),
            "location": next((str(event.get("location") or "") for event in events if event.get("location")), ""),
            "events": events,
            "lines": lines,
        }

    def _generate_dungeon_from_tool_entry(
        self,
        entry: dict[str, Any],
        *,
        source: str,
        default_location: str = "",
    ) -> dict[str, Any]:
        world = self.state.world_data
        current = self._tool_dungeon_current_location(default_location)
        anchor = self._tool_dungeon_anchor_location(entry, current)
        subtype = self._tool_dungeon_subtype(entry)
        reason = str(entry.get("reason") or entry.get("clue") or entry.get("source") or "dungeon clue").strip()
        explicit_name = str(
            entry.get("name")
            or entry.get("dungeon_name")
            or entry.get("location_name")
            or entry.get("target_location")
            or ""
        ).strip()
        resolved_existing = self._find_world_location_by_name(explicit_name) if explicit_name else ""
        location = world.locations.get(resolved_existing) if resolved_existing else None
        created = False
        if location is None or not _is_dungeon_location(location):
            base_name = explicit_name or self._tool_dungeon_fallback_name(anchor, subtype)
            location_name = _unique_world_location_name(world, base_name)
            description = str(
                entry.get("description")
                or entry.get("summary")
                or entry.get("overview")
                or entry.get("clue")
                or ""
            ).strip()
            if not description:
                description = f"{anchor}周辺で手がかりから存在が判明した探索地。"
            location = world.ensure_location(location_name, description)
            anchor_danger = self._current_location_danger(anchor)
            explicit_danger = _safe_int(entry.get("danger_level", entry.get("danger")), 0)
            danger = _clamp_world_danger(max(anchor_danger + 1, explicit_danger))
            location.extra.update(
                {
                    "location_kind": "dungeon",
                    "main_node_type": "dungeon",
                    "main_node_subtype": subtype,
                    "dungeon_subtype": subtype,
                    "role": "tool_generated_dungeon",
                    "danger_level": danger,
                    "danger_source": "llm_tool_generate_dungeon",
                    "boss_required": True,
                    "generated_dungeon_boss_required": True,
                    "generated_by_tool": "generate_dungeon",
                    "generated_reason": reason,
                    "branch_anchor_location": anchor,
                }
            )
            location.flags["dungeon"] = True
            location.flags["dangerous"] = True
            location.flags["discovered"] = True
            self._install_local_dungeon_subnode_graph(
                location,
                random.Random(f"tool-dungeon|{world.world_name}|{location.name}|{anchor}|{reason}"),
            )
            self._set_location_graph_node(world, location.name, kind="dungeon", danger=danger, location=location)
            created = True
        else:
            location.flags["discovered"] = True
            location.extra["boss_required"] = True
            location.extra["generated_dungeon_boss_required"] = True

        self._connect_tool_dungeon_route(world, anchor, location)
        self._assign_world_grid_position_if_missing(world, location.name, parent=anchor)
        self._sync_world_grid_danger(world, location.name)
        final_danger = _clamp_world_danger(
            max(
                _safe_int(location.extra.get("danger_level"), 0),
                self._current_location_danger(anchor) + 1,
                _safe_int(entry.get("danger_level", entry.get("danger")), 0),
            )
        )
        location.extra["danger_level"] = final_danger
        node = self._set_location_graph_node(world, location.name, kind="dungeon", danger=final_danger, location=location)
        node["discovered"] = True
        node["boss_required"] = True
        boss_response = dict(entry)
        boss_response["boss_required"] = True
        boss_response.setdefault("narration", location.description)
        boss_response.setdefault("discovered_location", {"location": location.name, "boss_required": True})
        boss_event = self._ensure_generated_dungeon_boss(location.name, reason or "generate_dungeon", boss_response)
        reveal = self._reveal_world_mainnode_route(
            {
                "from": current,
                "to": location.name,
                "reason": reason,
            },
            source=source,
            default_location=current,
        )
        line = f"> [Map] ダンジョンを発見: {location.name}（{anchor}周辺）"
        lines = [line]
        if reveal.get("line"):
            lines.append(str(reveal["line"]))
        if boss_event:
            lines.append(f"> [NPC] {boss_event.get('name')} が {location.name} の最奥部に配置されました。")
        event = {
            "source": source,
            "created": created,
            "revealed": bool(reveal.get("line")),
            "boss": boss_event or {},
            "location": location.name,
            "anchor": anchor,
            "current": current,
            "dungeon_subtype": subtype,
            "danger_level": final_danger,
            "reason": reason,
            "route": reveal.get("path") if isinstance(reveal, dict) else [],
            "lines": lines,
        }
        world.history.append({"manager": "llm_tool_generate_dungeon", **event})
        return event

    def _connect_tool_dungeon_route(self, world: WorldData, anchor: str, location: LocationData) -> None:
        if not anchor or anchor == location.name:
            return
        from_subnode = self._default_external_source_subnode(world, anchor, location.name)
        if not from_subnode:
            from_subnode = DEFAULT_SUBNODE_ID
        self._connect_world_locations_by_subnodes(
            world,
            anchor,
            location.name,
            from_subnode,
            DUNGEON_ENTRY_SUBNODE_ID,
            hours=WORLD_MAP_EDGE_HOURS,
            kind="generated_dungeon_route",
        )

    def _tool_dungeon_current_location(self, default_location: str = "") -> str:
        world = self.state.world_data
        for value in (default_location, self.state.current_location, world.starting_location):
            name = str(value or "").strip()
            if not name:
                continue
            resolved = self._find_world_location_by_name(name) or name
            if resolved in world.locations:
                return resolved
        return next(iter(world.locations), "")

    def _tool_dungeon_anchor_location(self, entry: dict[str, Any], current: str) -> str:
        world = self.state.world_data
        current = current if current in world.locations else self._tool_dungeon_current_location(current)
        allowed = _dedupe_strs([current, *self._world_neighbors_no_ensure(world, current)])
        requested = str(
            entry.get("anchor_location")
            or entry.get("near")
            or entry.get("near_location")
            or entry.get("source_location")
            or ""
        ).strip()
        if requested:
            resolved = self._find_world_location_by_name(requested) or requested
            if resolved in allowed:
                return resolved
        return current

    def _tool_dungeon_subtype(self, entry: dict[str, Any]) -> str:
        value = str(
            entry.get("dungeon_subtype")
            or entry.get("subtype")
            or entry.get("location_kind")
            or entry.get("kind")
            or "dungeon"
        ).strip().casefold().replace("-", "_").replace(" ", "_")
        aliases = {
            "woods": "forest",
            "wood": "forest",
            "wilds": "forest",
            "wilderness": "forest",
            "森": "forest",
            "山": "mountain",
            "洞窟": "cave",
            "洞穴": "cave",
            "遺跡": "ruin",
            "廃墟": "ruin",
            "鉱山": "mine",
            "迷宮": "labyrinth",
            "墓所": "crypt",
            "巣穴": "lair",
            "cavern": "cave",
            "caverns": "cave",
            "ruins": "ruin",
            "mines": "mine",
            "maze": "labyrinth",
        }
        value = aliases.get(value, value)
        if value in {"forest", "mountain", "ruin", "cave", "mine", "labyrinth", "crypt", "lair"}:
            return value
        return "dungeon"

    def _tool_dungeon_fallback_name(self, anchor: str, subtype: str) -> str:
        labels = {
            "forest": "森",
            "mountain": "山道",
            "ruin": "遺跡",
            "cave": "洞窟",
            "mine": "鉱山",
            "labyrinth": "迷宮",
            "crypt": "墓所",
            "lair": "巣穴",
            "dungeon": "ダンジョン",
        }
        label = labels.get(subtype, "ダンジョン")
        return f"{anchor}周辺の{label}"

    def _reveal_subnode_map_route(self, entry: Any, *, source: str, default_location: str = "") -> dict[str, Any]:
        world = self.state.world_data
        location_name = self._subnode_map_reveal_location(entry, default_location)
        location_name = self._find_world_location_by_name(location_name) or location_name
        location = world.locations.get(location_name) if location_name else None
        if location is None:
            return {"changed": False, "reason": "missing_location"}
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if not nodes:
            return {"changed": False, "reason": "missing_subnodes", "location": location.name}

        start = self._subnode_map_reveal_start(entry, location.name, graph)
        target = self._subnode_map_reveal_target(entry, graph)
        route = self._subnode_map_reveal_route(entry, graph)
        reveal_surroundings = self._subnode_map_reveal_is_surroundings(entry)
        if not target and route:
            target = route[-1]
        if not start:
            start = self._default_subnode_for_location(location)
        if start not in nodes:
            start = next(iter(nodes), "")
        if not target and not route and reveal_surroundings:
            path = [start, *self._subnode_adjacent_ids(graph, start)]
            target = path[-1] if path else start
        elif not target:
            return {"changed": False, "reason": "missing_target", "location": location.name}
        if target and target not in nodes:
            return {"changed": False, "reason": "missing_target_node", "location": location.name, "target": target}

        if reveal_surroundings and not route:
            path = _dedupe_strs([node_id for node_id in path if node_id in nodes])
        elif route:
            path = route
            if start and path[0] != start:
                path.insert(0, start)
            if path[-1] != target:
                path.append(target)
        else:
            path = self._subnode_path(graph, start, target)
            if not path and target in nodes:
                path = [target]

        changed = False
        for node_id in path:
            node = nodes.get(node_id)
            if not isinstance(node, dict):
                continue
            if not node.get("revealed") and not node.get("visited"):
                changed = True
            node["revealed"] = True
        named_path = [str(nodes.get(node_id, {}).get("name") or node_id) for node_id in path if node_id in nodes]
        event = {
            "source": source,
            "location": location.name,
            "start": start,
            "target": target,
            "path": path,
            "reason": _map_reveal_reason(entry),
            "changed": changed,
        }
        world.extra.setdefault("subnode_map_reveal_events", []).append(event)
        if not named_path:
            return {**event, "line": ""}
        line = f"> [Map] サブノードマップに経路を記録: {location.name}: {' -> '.join(named_path)}"
        return {**event, "line": line}

    def _subnode_map_reveal_location(self, entry: Any, default_location: str = "") -> str:
        if entry is True:
            return self._active_quest_destination_location() or default_location or self.state.current_location or self.state.world_data.starting_location
        if isinstance(entry, dict):
            quest_name = str(entry.get("quest") or entry.get("quest_name") or "").strip()
            if _map_reveal_value_means_active_quest(quest_name):
                quest_name = self.state.active_quest
            if quest_name:
                quest = self._find_quest_by_name(quest_name)
                if quest:
                    destination = quest.extra.get("destination") if isinstance(quest.extra, dict) else {}
                    if isinstance(destination, dict):
                        location = str(destination.get("location") or "").strip()
                        if location:
                            return location
            for key in ("location", "target_location", "destination_location", "dungeon", "area_location"):
                value = str(entry.get(key) or "").strip()
                if not value:
                    continue
                if _map_reveal_value_means_active_quest(value):
                    return self._active_quest_destination_location()
                return value
            if _as_bool(entry.get("active_quest") or entry.get("quest_destination")):
                active = self._active_quest_destination_location()
                if active:
                    return active
        value = str(entry or "").strip()
        if _map_reveal_value_means_active_quest(value):
            return self._active_quest_destination_location()
        return default_location or self.state.current_location or self.state.world_data.starting_location

    def _subnode_map_reveal_start(self, entry: Any, location_name: str, graph: dict[str, Any]) -> str:
        if isinstance(entry, dict):
            for key in ("from_subnode", "start_subnode", "source_subnode", "from", "start", "source"):
                node_id = self._resolve_subnode_ref(graph, entry.get(key))
                if node_id:
                    return node_id
        if location_name == (self.state.current_location or self.state.world_data.starting_location):
            return self._current_subnode_id(location_name)
        location = self.state.world_data.locations.get(location_name)
        return self._default_subnode_for_location(location)

    def _subnode_map_reveal_target(self, entry: Any, graph: dict[str, Any]) -> str:
        if entry is True:
            return self._active_quest_destination_subnode()
        if isinstance(entry, dict):
            quest_name = str(entry.get("quest") or entry.get("quest_name") or "").strip()
            if _map_reveal_value_means_active_quest(quest_name):
                quest_name = self.state.active_quest
            if quest_name:
                quest = self._find_quest_by_name(quest_name)
                if quest:
                    destination = quest.extra.get("destination") if isinstance(quest.extra, dict) else {}
                    if isinstance(destination, dict):
                        node_id = self._resolve_subnode_ref(graph, destination.get("objective_subnode_id") or destination.get("objective_subnode_name"))
                        if node_id:
                            return node_id
            for key in (
                "target_subnode",
                "target_subnode_id",
                "destination_subnode",
                "destination_subnode_id",
                "to_subnode",
                "to",
                "target",
                "destination",
                "subnode",
                "subnode_id",
            ):
                raw = entry.get(key)
                if isinstance(raw, str) and _map_reveal_value_means_active_quest(raw):
                    return self._active_quest_destination_subnode()
                node_id = self._resolve_subnode_ref(graph, raw)
                if node_id:
                    return node_id
            if _as_bool(entry.get("active_quest") or entry.get("quest_destination")):
                return self._active_quest_destination_subnode()
        return self._resolve_subnode_ref(graph, entry)

    def _subnode_map_reveal_route(self, entry: Any, graph: dict[str, Any]) -> list[str]:
        if not isinstance(entry, dict):
            return []
        for key in ("route_subnodes", "subnode_route", "route", "path", "nodes", "subnodes"):
            values = _as_list(entry.get(key))
            route: list[str] = []
            for value in values:
                node_id = self._resolve_subnode_ref(graph, value)
                if node_id:
                    route.append(node_id)
            if route:
                return _dedupe_strs(route)
        return []

    def _subnode_map_reveal_is_surroundings(self, entry: Any) -> bool:
        if not isinstance(entry, dict):
            return False
        scope = str(entry.get("scope") or entry.get("mode") or entry.get("type") or "").strip().casefold()
        if scope in {"surroundings", "around", "nearby", "adjacent", "look_around", "current_area"}:
            return True
        return _as_bool(entry.get("surroundings") or entry.get("nearby") or entry.get("adjacent"))

    def _resolve_subnode_ref(self, graph: dict[str, Any], value: Any) -> str:
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        if isinstance(value, dict):
            value = value.get("id") or value.get("subnode_id") or value.get("node_id") or value.get("name")
        text = str(value or "").strip()
        if not text:
            return ""
        if text in nodes:
            return text
        normalized = _world_location_name_key(text)
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            node_name = str(node.get("name") or node_id)
            if normalized and normalized == _world_location_name_key(node_name):
                return str(node_id)
        return ""

    def _apply_response_relationship_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in (
            "relationship_change",
            "relationship_changes",
            "npc_relationship_change",
            "npc_relationship_changes",
            "affinity_change",
            "affinity_changes",
            "npc_affinity_change",
            "npc_affinity_changes",
        ):
            entries.extend(_as_list(response.get(key)))
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None:
                continue
            delta = _relationship_delta(entry)
            reason = _relationship_reason(entry)
            lines.extend(self._apply_npc_affinity_delta(character, delta, source=source, reason=reason))
        return lines

    def _apply_response_npc_movements(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: Character | None = None,
        default_location: str = "",
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        entries: list[Any] = []
        for key in (
            "npc_movement",
            "npc_movements",
            "character_movement",
            "character_movements",
            "actor_movement",
            "actor_movements",
            "move_npc",
            "move_npcs",
            "moved_npcs",
            "followers",
            "escorted_npcs",
        ):
            for item in _as_list(response.get(key)):
                if key in {"followers", "escorted_npcs"}:
                    if isinstance(item, dict):
                        data = dict(item)
                        data.setdefault("follow_player", True)
                        data.setdefault("state", "party")
                        entries.append(data)
                    else:
                        entries.append({"name": item, "follow_player": True, "state": "party"})
                else:
                    entries.append(item)
        if not entries:
            return []
        fallback_location = default_location or str(response.get("location") or self.state.current_location or self.state.world_data.starting_location)
        lines: list[str] = []
        for entry in entries:
            character = self._character_from_effect_target(entry, default_character)
            if character is None or character.flags.get("is_player"):
                continue
            target_location = _movement_target_location(entry, fallback_location)
            if not target_location:
                continue
            old_location = character.location or str(character.flags.get("current_location") or "")
            state = _movement_target_state(entry, character.state or "present")
            party_action = _movement_party_action(entry, state)
            if party_action == "dead":
                self._mark_character_dead(character, source=source)
                lines.append(f"> [NPC] {character.name} is dead.")
                continue
            if party_action == "wait":
                lines.extend(self._remove_party_companion(character, source=source, reason=_relationship_reason(entry), wait_at_current=True))
                continue
            if party_action == "leave":
                lines.extend(self._remove_party_companion(character, source=source, reason=_relationship_reason(entry)))
                if _movement_has_explicit_location(entry) and target_location:
                    self.state.world_data.ensure_location(target_location)
                    self._set_character_presence(character, target_location, state if state not in {"party", "companion"} else "present")
                continue
            if party_action == "join":
                lines.extend(self._set_party_companion(character, source=source, reason=_relationship_reason(entry)))
                continue
            self.state.world_data.ensure_location(target_location)
            self._set_character_presence(character, target_location, state)
            event = {
                "source": source,
                "character": character.name,
                "old_location": old_location,
                "new_location": target_location,
                "state": state,
                "day": self.state.day,
                "reason": _relationship_reason(entry),
            }
            self.state.world_data.extra.setdefault("npc_movement_events", []).append(event)
            if old_location != target_location:
                lines.append(f"> [NPC移動] {character.name}: {old_location or '-'} -> {target_location}")
        return lines

    def _character_from_effect_target(self, value: Any, default_character: Character | None = None) -> Character | None:
        if isinstance(value, Character):
            return value
        if isinstance(value, dict):
            target = str(
                value.get("target")
                or value.get("character")
                or value.get("character_name")
                or value.get("npc")
                or value.get("npc_name")
                or value.get("name")
                or ""
            ).strip()
        else:
            target = str(value or "").strip()
        if not target or target.lower() in {"npc", "character", "speaker", "target", "companion", "follower"}:
            return default_character
        direct = self.state.world_data.character(target)
        if direct:
            return direct
        lowered = target.casefold()
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            terms = _character_reference_terms(character)
            if any(lowered == term.casefold() for term in terms if term):
                return character
        if default_character and lowered in {str(default_character.name).casefold(), str(default_character.role).casefold()}:
            return default_character
        return None

    def _active_visual_subjects(self, location: str) -> tuple[list[Character], list[Character]]:
        characters: list[Character] = []
        enemies: list[Character] = []
        seen_characters: set[str] = set()
        seen_enemies: set[str] = set()
        current_location = location or self.state.current_location or self.state.world_data.starting_location

        def add_character(character: Character | None) -> None:
            if not character or not character.name or character.name in seen_characters:
                return
            seen_characters.add(character.name)
            characters.append(character)

        def add_enemy(character: Character | None) -> None:
            if not character or not character.name or character.name in seen_enemies:
                return
            seen_enemies.add(character.name)
            enemies.append(character)

        add_character(self.player_character())

        active_encounter = self._active_encounter()
        if active_encounter:
            opponent_name = str(active_encounter.get("opponent_name") or "")
            opponent = self.state.world_data.character(opponent_name)
            add_enemy(opponent)
            add_character(opponent)

        active_conversation = self._active_conversation_character()
        add_character(active_conversation)

        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, current_location):
                continue
            if not self._character_matches_active_facility(character):
                continue
            add_character(character)
            if len(characters) >= 5:
                break

        return characters, enemies

    def cancel_current_task(self) -> None:
        self.llm.stop()
        stop_image = getattr(self.image_backend, "stop", None)
        if callable(stop_image):
            stop_image()

    def _check_world_content_violation(self, player_name: str, premise: str) -> dict[str, Any]:
        premise_context = _short_text(premise, 5000)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの世界生成前チェック担当です。"
                    "ゲーム側にはローカルの禁止語判定や安全判定がないため、"
                    "この入力を世界生成へ渡してよいかをLLMとして判断してください。"
                    "必ず content_violation, reason, message を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界生成の雰囲気/要望: {premise_context}\n"
                    "この内容をcreate_world_overviewへ渡してよいか判定してください。"
                ),
            },
        ]
        return self._chat_json(
            "check_world_content_violation",
            messages,
            max_tokens=350,
            world_name="unknown",
            player_name=player_name,
        )

    def _create_story(self, player_name: str, premise: str, world: WorldData) -> dict[str, Any]:
        premise_context = _short_text(premise, 5000)
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのストーリー設計担当です。"
                    "Fantasiaのcreate_story相当として、world_situation, flow, "
                    "current_rumor を持つJSONだけを返してください。"
                    "クエスト候補は返さないでください。クエストは街の掲示板を開いた時に別処理で生成します。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"雰囲気: {premise_context}\n"
                    f"世界データ: {world_payload}\n"
                    "この世界の初期ストーリー状況、進行の流れ、現在の噂だけを作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "create_story",
            messages,
            max_tokens=520,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _settlement_required_shop_slots(
        self,
        world: WorldData,
        settlement_name: str,
    ) -> list[dict[str, str]]:
        location = world.locations.get(settlement_name) if isinstance(world.locations, dict) else None
        world_text = " ".join(
            str(part or "")
            for part in (
                world.world_name,
                world.overview,
                world.structure_description,
                world.world_situation,
                getattr(location, "description", ""),
            )
        )
        rng = random.Random(f"settlement-required-shops:{world.world_name}:{settlement_name}:{world_text}")
        optional_types = list(SETTLEMENT_OPTIONAL_SHOP_TYPES)
        if any(marker in world_text.lower() for marker in ("black market", "underworld", "smuggl", "crime", "\u95c7", "\u88cf", "\u72af\u7f6a")):
            optional_types.append("black_market")
        rng.shuffle(optional_types)
        target_count = rng.randint(3, 5)
        selected_types = list(SETTLEMENT_REQUIRED_SHOP_TYPES)
        selected_types.extend(optional_types[: max(0, target_count - len(selected_types))])
        return [
            {
                "type": facility_type,
                "generic_name": _shop_type_generic_name(facility_type) or facility_type,
                "npc_role": _default_facility_role(facility_type),
            }
            for facility_type in selected_types[:5]
        ]

    def _append_missing_required_shop_facilities(
        self,
        settlement_name: str,
        facilities: list[dict[str, Any]],
        required_shop_slots: list[dict[str, str]],
    ) -> None:
        existing_types: set[str] = set()
        for item in facilities:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("facility_name") or item.get("title") or "")
            raw_type = str(item.get("type") or item.get("facility_type") or "").strip().lower()
            inferred_type = _facility_type_from_name(name)
            facility_type = raw_type or inferred_type
            if facility_type in {"facility", "shop", "market"} and inferred_type not in {"facility", "shop", "market"}:
                facility_type = inferred_type
            if facility_type in SHOP_FACILITY_TYPES:
                existing_types.add(facility_type)
        for slot in required_shop_slots:
            facility_type = str(slot.get("type") or "").strip().lower()
            if not facility_type or facility_type in existing_types:
                continue
            generic_name = str(slot.get("generic_name") or _shop_type_generic_name(facility_type) or facility_type)
            record = _facility_record(generic_name, settlement_name, facility_type=facility_type)
            record["source"] = "required_shop_facility_fallback"
            facilities.append(record)
            existing_types.add(facility_type)

    def _create_settlement_detail(
        self,
        player_name: str,
        world: WorldData,
        settlement_name: str,
    ) -> dict[str, Any]:
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True)
        )
        npc_template_payload = json.dumps(
            {
                "friendly_templates": npc_template_prompt_summaries(
                    FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                    danger_level=self._current_location_danger(settlement_name),
                    used_ids=used_npc_template_ids(world),
                    limit=12,
                )
            },
            ensure_ascii=False,
        )
        required_shop_slots = self._settlement_required_shop_slots(world, settlement_name)
        required_shop_payload = json.dumps(required_shop_slots, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの拠点詳細作成担当です。"
                    "Fantasiaのcreate_settlement_detail相当として、"
                    "settlement_structure_description, atmosphere, settlement_structure, facilities, residents, adventurers "
                    "を必ずトップレベルに持つJSONだけを返してください。"
                    "core や spots は settlement_structure の中だけに入れ、トップレベルに core/spots だけを返すことは禁止です。"
                    "facilities は name, type, description, npc_name, npc_role を持つ施設オブジェクトの配列にしてください。"
                    "施設は街や村の内部施設であり、ワールドマップ上のロケーションにはしないでください。"
                    "店の type は blacksmith, black_market, apothecary, food_store, material_store, general_store, magic_store を使用できます。"
                    "店には「鍛冶屋」「雑貨店」のような一般名だけでなく、その街固有の名前を付けてください。"
                    "residents と adventurers は人物オブジェクトの配列にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"対象拠点: {settlement_name}\n"
                    f"世界データ: {world_payload}\n"
                    "この拠点の構造、雰囲気、住人、滞在中の冒険者を作ってください。\n"
                    "必ず次の外枠を維持し、値だけを埋めてください: "
                    "{settlement_structure_description, atmosphere, settlement_structure, facilities, residents, adventurers}"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    f"required_shop_facilities: {required_shop_payload}\n"
                    "Required settlement shop rule: facilities must include one shop facility for every item "
                    "in required_shop_facilities. Use each listed type exactly. Generate an original in-world "
                    "shop name, description, npc_name, npc_role, npc_gender, npc_age, npc_look, and "
                    "npc_personality for each shop. These shops are already inside the settlement; do not "
                    "copy the shop/facility description into npc_look or npc_personality; those fields must describe the keeper as a person. "
                    "turn them into world-map locations, entrances, gates, plazas, or route nodes. Do not "
                    "use only generic labels such as blacksmith, apothecary, general store, shop, or market "
                    "as the visible name."
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Subnode/NPC placement rule: the settlement itself is the world-map location. Plaza, inn, guild, "
                    "shops, wells, and similar places may be represented as facilities or subnodes inside that "
                    "settlement, not as separate locations. Gates, entrances, the central plaza, and plazas are "
                    "fixed movement nodes, so do not return them as facilities, spots, shops, landmarks, places, "
                    "buildings, or districts. A well is not fixed; include a well only when it is an ordinary "
                    "generated facility/spot with a local name and description. Wells are never external links, "
                    "neighbor entrances, or world-map route endpoints. If a resident or adventurer works "
                    "at a facility, set that same person as the facility npc_name/npc_role or include "
                    "facility/facility_type on the person object so the game can place them in that facility "
                    "subnode. Do not place an innkeeper or shopkeeper in the central plaza unless they are "
                    "explicitly visiting the plaza."
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "NPC completeness rule: every person-like object in facilities, residents, and adventurers must "
                    "include age, gender, look, and personality. For facilities, put the facility keeper fields on the "
                    "facility object as npc_gender, npc_age, npc_look, and npc_personality. For residents/adventurers, "
                    "use gender, age, look, and personality. Facility descriptions describe the building or shop; "
                    "npc_look and npc_personality must describe the person working there and must not repeat the facility description. "
                    "gender must be female, male, none, or a matching localized "
                    "label. age should be a visible age range such as early 20s, late 30s, elderly, unknown, or adult. "
                    "look must describe visible appearance, clothes, body type/species traits, and atmosphere enough "
                    "for character image generation. For monsters or non-humans, use gender=none and a life-stage age "
                    "such as adult or unknown when a human age is not meaningful."
                ),
            }
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    f"NPC template candidates: {npc_template_payload}\n"
                    "Generate residents, adventurers, and facility keepers as variations of these templates. "
                    "When a template fits, include npc_template_id on the person or facility npc object; the game "
                    "will still select a template locally if the id is absent. Preserve the settlement tone, job, "
                    "and role while filling name, appearance, personality, and local flavor."
                ),
            }
        )
        return self._chat_json(
            "create_settlement_detail",
            messages,
            max_tokens=1400,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _facility_request_evaluator(self, action: str, requested_facility: str, settlement: LocationData) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=True, include_monsters=False, include_quests=False))
        facilities_payload = json.dumps(self._ensure_settlement_facilities(settlement), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Fantasia's settlement facility referee. Decide whether a requested facility can naturally exist in the current settlement.\n"
                    "Do not create facilities in wilderness, ruins, or dungeons. If the current settlement and world tone can support it, return allowed=true and a concrete facility plus its first NPC.\n"
                    "If it cannot exist, return allowed=false with a short in-world refusal. Return only JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"world_data: {world_payload}\n"
                    f"current_settlement: {settlement.name}\n"
                    f"settlement_description: {settlement.description}\n"
                    f"existing_facilities: {facilities_payload}\n"
                    f"requested_facility: {requested_facility}\n"
                    f"player_action: {action}\n"
                    "Judge whether this facility can be added. If allowed, include facility{name,type,description} and npc{name,role,gender,age,personality,look}. "
                    "npc.look and npc.personality must describe the person working there, not the facility or shop description. "
                    "Prefer ordinary settlement facilities such as guilds, blacksmiths, black markets, apothecaries, food stores, material stores, general stores, magic stores, inns, temples, clinics, libraries, stables, and markets when plausible. "
                    "Shop facilities must have a proper unique shop name instead of only a generic type name. "
                    "Do not create the settlement entrance, gate, central plaza, or plaza as facilities; those are fixed movement nodes."
                ),
            },
        ]
        return self._chat_json(
            "facility_request_evaluator",
            messages,
            max_tokens=650,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _facility_from_response(self, response: dict[str, Any], requested: str, settlement: LocationData) -> dict[str, Any]:
        raw = response.get("facility") if isinstance(response.get("facility"), dict) else response
        npc = response.get("npc") if isinstance(response.get("npc"), dict) else {}
        name = _clean_settlement_generated_text(raw.get("name") or raw.get("facility_name") or requested, settlement.name) or requested
        facility_type = str(raw.get("type") or raw.get("facility_type") or _facility_type_from_name(name)).strip()
        original_name = name
        facility_index = len(_as_list(settlement.extra.get("facilities")))
        name = _shop_facility_display_name(name, facility_type, settlement.name, facility_index)
        description = _clean_settlement_generated_text(
            raw.get("description") or raw.get("overview") or response.get("narration") or "",
            settlement.name,
        )
        return {
            "name": name,
            "type": facility_type,
            "description": description,
            "npc_name": _clean_settlement_generated_text(npc.get("name") or raw.get("npc_name") or "", settlement.name),
            "npc_role": _clean_settlement_generated_text(
                npc.get("role") or raw.get("npc_role") or _default_facility_role(facility_type),
                settlement.name,
            ),
            **_facility_keeper_fields({**raw, "npc": npc}, settlement.name, name, description),
            "location_name": settlement.name,
            "sub_location": name,
            "source": "facility_request_evaluator",
            "aliases": _facility_aliases(original_name, name, facility_type),
            "raw_facility_request_evaluator": _strip_response_metadata(response),
        }

    def _apply_story(self, world: WorldData, response: dict[str, Any]) -> None:
        world.world_situation = str(response.get("world_situation") or world.world_situation)
        world.flow = response.get("flow", world.flow)
        world.current_rumor = str(response.get("current_rumor") or world.current_rumor)
        world.extra["raw_create_story"] = _strip_response_metadata(response)

    def _apply_settlement_detail(
        self,
        world: WorldData,
        settlement_name: str,
        response: dict[str, Any],
    ) -> None:
        location = world.ensure_location(settlement_name)
        structure_description = _clean_settlement_generated_text(response.get("settlement_structure_description") or "", settlement_name)
        atmosphere = _clean_settlement_generated_text(response.get("atmosphere") or response.get("atomosphere") or "", settlement_name)
        if structure_description:
            location.description = structure_description
        if atmosphere:
            location.extra["atmosphere"] = atmosphere
        structure = _clean_settlement_structure_value(response.get("settlement_structure", {}), settlement_name)
        facilities: list[dict[str, Any]] = []
        for raw in _as_list(response.get("facilities")):
            if isinstance(raw, dict):
                name = _clean_settlement_generated_text(raw.get("name") or raw.get("facility_name") or raw.get("title") or "", settlement_name)
                if not name:
                    continue
                if _is_reserved_settlement_facility_name(name):
                    continue
                description = _facility_description_from_payload(
                    raw.get("description") or raw.get("overview") or "",
                    settlement_name,
                    name,
                )
                facilities.append(
                    {
                        "name": name,
                        "type": str(raw.get("type") or raw.get("facility_type") or _facility_type_from_name(name)).strip(),
                        "description": description,
                        "npc_name": _clean_settlement_generated_text(raw.get("npc_name") or raw.get("keeper") or raw.get("owner") or "", settlement_name),
                        "npc_role": _clean_settlement_generated_text(raw.get("npc_role") or raw.get("role") or "", settlement_name),
                        **_facility_keeper_fields(raw, settlement_name, name, description),
                        "location_name": settlement_name,
                        "sub_location": name,
                        "source": str(raw.get("source") or "create_settlement_detail"),
                    }
                )
            else:
                name = _clean_settlement_generated_text(raw or "", settlement_name)
                if name and not _is_reserved_settlement_facility_name(name):
                    facilities.append(_facility_record(name, settlement_name))
        for name in _facility_names_from_structure(structure):
            if _is_reserved_settlement_facility_name(name):
                continue
            if not _facility_exists(facilities, name):
                facilities.append(_facility_record(name, settlement_name))
        required_shop_slots = self._settlement_required_shop_slots(world, settlement_name)
        self._append_missing_required_shop_facilities(settlement_name, facilities, required_shop_slots)
        location.extra["settlement_structure"] = structure
        location.extra["required_shop_facilities"] = required_shop_slots
        location.extra["facilities"] = facilities
        location.extra["raw_create_settlement_detail"] = _strip_response_metadata(response)
        location.flags["settlement"] = True
        location.extra["location_kind"] = "settlement"
        self._ensure_settlement_facilities(location)

        danger_level = self._npc_template_danger_for_location(settlement_name)
        for index, item in enumerate(_as_list(response.get("residents"))):
            item = self._template_augmented_npc_raw(
                item,
                categories=FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                danger_level=danger_level,
                seed=f"settlement-resident:{world.world_name}:{settlement_name}:{index}",
                hostile=False,
            )
            character = _character_from_raw(item, index, category="resident")
            if _world_has_dead_npc_identity(world, name=character.name, uuid=character.uuid):
                continue
            character.name = _unique_character_name(world, character.name)
            self._finalize_generated_npc(
                character,
                location_name=settlement_name,
                danger_level=danger_level,
                role_hint="resident",
            )
            subnode_id = self._assign_settlement_character_subnode(world, location, character)
            self._set_character_presence(character, settlement_name, subnode_id=subnode_id)
            world.add_character(character)
        for index, item in enumerate(_as_list(response.get("adventurers"))):
            item = self._template_augmented_npc_raw(
                item,
                categories=FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                danger_level=danger_level,
                seed=f"settlement-adventurer:{world.world_name}:{settlement_name}:{index}",
                hostile=False,
            )
            character = _character_from_raw(item, index, category="adventurer")
            if _world_has_dead_npc_identity(world, name=character.name, uuid=character.uuid):
                continue
            character.name = _unique_character_name(world, character.name)
            self._finalize_generated_npc(
                character,
                location_name=settlement_name,
                danger_level=danger_level,
                role_hint="adventurer",
            )
            subnode_id = self._assign_settlement_character_subnode(world, location, character)
            self._set_character_presence(character, settlement_name, subnode_id=subnode_id)
            world.add_character(character)

    def _enrich_initial_characters(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_start: int = 70,
        progress_end: int = 82,
    ) -> None:
        targets = list(world.characters.values())[:6]
        if not targets:
            self._emit_world_generation_progress(progress_callback, "characters", "NPC生成をスキップ", progress_end, 100, item_current=0, item_total=0)
            return
        total = len(targets)
        for index, character in enumerate(targets, start=1):
            percent = progress_start + int((progress_end - progress_start) * (index - 1) / max(1, total))
            self._emit_world_generation_progress(
                progress_callback,
                "characters",
                f"NPC生成中（{index}/{total}: {character.name}）",
                percent,
                100,
                item_current=index,
                item_total=total,
            )
            try:
                profile = self._create_initial_character_profile(player_name, premise, world, character)
            except JsonResponseError as exc:
                self._append_character_enrichment_error(world, "create_initial_character_profile", character, exc)
                self._enrich_initial_character_legacy(player_name, premise, world, character)
            else:
                self._apply_character_profile(character, profile)
                self._apply_character_look(character, profile)
                self._apply_character_traits(character, profile)
                self._apply_character_skills(character, profile)
                character.extra["raw_create_initial_character_profile"] = _strip_response_metadata(profile)
                self._append_character_history(world, "create_initial_character_profile", character, profile)
            percent = progress_start + int((progress_end - progress_start) * index / max(1, total))
            self._emit_world_generation_progress(
                progress_callback,
                "characters",
                f"NPC生成中（{index}/{total}: {character.name}）",
                percent,
                100,
                item_current=index,
                item_total=total,
            )

    def _enrich_initial_character_legacy(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        character: Character,
    ) -> None:
        try:
            profile = self._create_character(player_name, premise, world, character)
        except JsonResponseError as exc:
            self._append_character_enrichment_error(world, "create_character", character, exc)
        else:
            self._apply_character_profile(character, profile)
            self._append_character_history(world, "create_character", character, profile)

        try:
            look = self._create_look(player_name, world, character)
        except JsonResponseError as exc:
            self._append_character_enrichment_error(world, "create_look", character, exc)
        else:
            self._apply_character_look(character, look)
            self._append_character_history(world, "create_look", character, look)

        try:
            traits = self._create_trait(player_name, world, character)
        except JsonResponseError as exc:
            self._append_character_enrichment_error(world, "create_trait", character, exc)
        else:
            self._apply_character_traits(character, traits)
            self._append_character_history(world, "create_trait", character, traits)

        try:
            skills = self._create_skill(player_name, world, character)
        except JsonResponseError as exc:
            self._append_character_enrichment_error(world, "create_skill", character, exc)
        else:
            self._apply_character_skills(character, skills)
            self._append_character_history(world, "create_skill", character, skills)

    def _append_character_enrichment_error(
        self,
        world: WorldData,
        manager_name: str,
        character: Character,
        exc: JsonResponseError,
    ) -> None:
        error = {
            "manager": manager_name,
            "character": character.name,
            "errors": list(exc.errors),
            "response": sanitize_retry_response(exc.response),
        }
        errors = character.extra.setdefault("enrichment_errors", [])
        if not isinstance(errors, list):
            errors = []
            character.extra["enrichment_errors"] = errors
        errors.append(error)
        world.history.append(
            {
                "manager": manager_name,
                "character": character.name,
                "error": list(exc.errors),
                "response": sanitize_retry_response(exc.response),
                "nonfatal": True,
            }
        )

    def _create_initial_character_profile(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        character: Character,
    ) -> dict[str, Any]:
        premise_context = _short_text(premise, 5000)
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True)
        )
        character_payload = _ai_json(_character_ai_context(character))
        power_instruction = _skill_power_instruction(character)
        element_options = ", ".join(f"{value}({tr_enum('element', value, 'ja', fallback=value)})" for value in ELEMENT_IDS)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Fantasia's combined initial NPC enrichment manager. "
                    "Return compact JSON only. Fill one character profile, appearance, traits, and skills in a single response. "
                    "Use Japanese for story text. Use concise English SDXL tags for image_generation_prompt. "
                    "Do not invent extra unrelated characters."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Player name: {player_name}\n"
                    f"World premise: {premise_context}\n"
                    f"World data: {world_payload}\n"
                    f"Character name: {character.name}\n"
                    f"Character role: {character.role}\n"
                    f"Existing character data: {character_payload}\n"
                    f"{power_instruction}\n"
                    f"Available element ids: {element_options}\n"
                    "Return fields: name, gender, age, role, category, backstory, personality, ability, "
                    "look, image_generation_prompt, traits, skills. "
                    "Each trait must include only name and desc. "
                    "Each skill should include name, desc, usesp, power, ability, element, and type. "
                    "usesp is 1-12, power is 1-5, ability is one of str/dex/con/int/wis/cha/magic/will, "
                    "and type is an array of combat effect IDs such as damage_hp_single, heal_single, or effect_self."
                ),
            },
        ]
        return self._chat_json(
            "create_initial_character_profile",
            messages,
            max_tokens=1500,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _create_character(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        character: Character,
    ) -> dict[str, Any]:
        premise_context = _short_text(premise, 5000)
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True)
        )
        character_payload = _ai_json(_character_ai_context(character))
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのキャラクター作成担当です。"
                    "Fantasiaのcreate_character相当として、既存の名前や役割を尊重しながら、"
                    "name, gender, age, backstory, personality, ability を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界の雰囲気: {premise_context}\n"
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"役割: {character.role}\n"
                    f"既存キャラクターデータ: {character_payload}\n"
                    "このキャラクターの基本プロフィール、背景、性格、能力を補完してください。"
                ),
            },
        ]
        return self._chat_json(
            "create_character",
            messages,
            max_tokens=750,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _create_look(self, player_name: str, world: WorldData, character: Character) -> dict[str, Any]:
        world_payload = _ai_json(
            _world_ai_context(
                world,
                include_locations=False,
                include_characters=False,
                include_monsters=False,
                include_quests=False,
            )
        )
        character_payload = _ai_json(_character_ai_context(character))
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのキャラクター外見作成担当です。"
                    "Fantasiaのcreate_look相当として、category, look, image_generation_prompt を持つJSONだけを返してください。"
                    "image_generation_prompt はSDXL向けの英語キーワード配列にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"役割: {character.role}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    "このキャラクターの外見説明とSDXL用プロンプトを作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "create_look",
            messages,
            max_tokens=650,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _create_trait(
        self,
        player_name: str,
        world: WorldData,
        character: Character,
        seed_name: str = "",
        seed_description: str = "",
    ) -> dict[str, Any]:
        world_payload = _ai_json(
            _world_ai_context(
                world,
                include_locations=False,
                include_characters=False,
                include_monsters=False,
                include_quests=False,
            )
        )
        character_payload = _ai_json(_character_ai_context(character, include_traits=False, include_skills=False))
        existing_traits_payload = _ai_json(_character_entry_duplicate_guard(character.traits, "traits"))
        seed_instruction = _character_entry_seed_instruction(seed_name, seed_description)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのキャラクター特徴作成担当です。"
                    "Fantasiaのcreate_trait相当として、traits を持つJSONだけを返してください。"
                    "traits は必ず新規1件だけを持つ配列にしてください。"
                    "各 trait は name と desc だけを持つオブジェクトにしてください。"
                    "他のキーは禁止です。"
                    "既存特質と同じ名前、説明文を返してはいけません。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    f"既存の特質一覧（重複禁止。コピーや言い換え禁止）: {existing_traits_payload}\n"
                    f"{seed_instruction}\n"
                    "既存とは別の新しい性格/特徴を1件だけ生成してください。"
                ),
            },
        ]
        return self._chat_json(
            "create_trait",
            messages,
            max_tokens=350,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _create_skill(
        self,
        player_name: str,
        world: WorldData,
        character: Character,
        desired_element: str = "",
        seed_name: str = "",
        seed_description: str = "",
    ) -> dict[str, Any]:
        world_payload = _ai_json(
            _world_ai_context(
                world,
                include_locations=False,
                include_characters=False,
                include_monsters=False,
                include_quests=False,
            )
        )
        character_payload = _ai_json(_character_ai_context(character, include_traits=False, include_skills=False))
        existing_skills_payload = _ai_json(_character_entry_duplicate_guard(character.skills, "skills"))
        existing_traits_payload = _ai_json(_character_entry_duplicate_guard(character.traits, "traits"))
        power_instruction = _skill_power_instruction(character)
        element_id = _normalise_element_id(desired_element, fallback="fire" if desired_element else "physical")
        element_label = tr_enum("element", element_id, "ja", fallback=element_id)
        element_options = ", ".join(f"{value}({tr_enum('element', value, 'ja', fallback=value)})" for value in ELEMENT_IDS)
        seed_instruction = _character_entry_seed_instruction(seed_name, seed_description)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのキャラクタースキル作成担当です。"
                    "Fantasiaのcreate_skill相当として、skills を持つJSONだけを返してください。"
                    "skills は必ず新規1件だけを持つ配列にしてください。"
                    "skills は name, desc, usesp, power, ability, element, type だけを持つオブジェクト配列にしてください。"
                    "usespは1から12、powerは1から5の整数です。"
                    "abilityはstr/dex/con/int/wis/cha/magic/willのいずれかです。"
                    "element は指定された属性IDだけを使ってください。"
                    "type は heal_single, heal_party, damage_hp_single, damage_hp_party, damage_sp_single, damage_sp_party, "
                    "absorption_single, absorption_party, effect_enemy_single, effect_enemy_party, effect_self, effect_ally_single, effect_ally_party の配列です。"
                    "複数回攻撃や複数効果のスキルでは、同じtypeを必要回数だけ重複して配列に入れてください。"
                    "例: 3回攻撃なら type=[\"damage_hp_single\",\"damage_hp_single\",\"damage_hp_single\"]。"
                    "既存スキルと同じ名前、説明文、効果文を返してはいけません。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    f"既存のスキル一覧（重複禁止。コピーや言い換え禁止）: {existing_skills_payload}\n"
                    f"既存の特質一覧（参考。スキル本文へコピー禁止）: {existing_traits_payload}\n"
                    f"{power_instruction}\n"
                    f"利用可能な属性ID: {element_options}\n"
                    f"今回生成するスキルの属性ID: {element_id}（{element_label}）\n"
                    f"{seed_instruction}\n"
                    "スキル名や説明に「3連」「三連」「3回」「複数回」などが含まれる場合、その回数分だけ damage_hp_single 等を重複させてください。\n"
                    "既存とは別の新しいスキルを新形式で1件だけ生成してください。"
                ),
            },
        ]
        return self._chat_json(
            "create_skill",
            messages,
            max_tokens=700,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _apply_character_profile(self, character: Character, response: dict[str, Any]) -> None:
        generated_name = str(response.get("name") or "").strip()
        if generated_name and character.name in {"unknown", ""}:
            character.name = generated_name
        elif generated_name and generated_name != character.name:
            character.extra["generated_name"] = generated_name
        character.gender = str(response.get("gender") or character.gender)
        character.age = str(response.get("age") or character.age)
        character.role = str(response.get("role") or character.role)
        character.category = str(response.get("category") or character.category)
        character.backstory = str(response.get("backstory") or character.backstory)
        character.personality = str(response.get("personality") or character.personality)
        if response.get("ability") is not None:
            character.extra["ability"] = response.get("ability")
        character.extra["raw_create_character"] = _strip_response_metadata(response)

    def _apply_character_look(self, character: Character, response: dict[str, Any]) -> None:
        character.category = str(response.get("category") or character.category)
        character.look = str(response.get("look") or character.look)
        prompt = _as_str_list(response.get("image_generation_prompt"))
        if prompt:
            character.image_generation_prompt = prompt
        character.prompts["create_look"] = {
            "prompt": prompt,
            "negative_prompt": str(response.get("negative_prompt") or ""),
        }
        character.extra["raw_create_look"] = _strip_response_metadata(response)

    def _apply_character_traits(self, character: Character, response: dict[str, Any]) -> None:
        traits = [_trait_entry(item) for item in _as_list(response.get("traits"))]
        traits = [trait for trait in traits if trait.get("name")]
        if traits:
            character.traits = traits
        character.extra["raw_create_trait"] = _strip_response_metadata(response)

    def _apply_character_skills(self, character: Character, response: dict[str, Any]) -> None:
        skills = [_normalise_skill(item) for item in _as_list(response.get("skills"))]
        skills = [skill for skill in skills if skill.get("name")]
        skills = _limit_power_entries_for_actor(character, skills, used_power=0)
        if skills:
            character.skills = skills
        character.extra["raw_create_skill"] = _strip_response_metadata(response)

    def _append_character_history(
        self,
        world: WorldData,
        manager_name: str,
        character: Character,
        response: dict[str, Any],
    ) -> None:
        world.history.append(
            {
                "manager": manager_name,
                "character": character.name,
                "response": _strip_response_metadata(response),
            }
        )

    def _create_initial_narration(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
    ) -> dict[str, Any]:
        premise_context = _short_text(premise, 5000)
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=True, include_monsters=True, include_quests=True)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの初回ナレーターです。"
                    "必ず日本語で、narration, location, choices を持つJSONだけを返してください。"
                    "narration はプレイヤーが操作を始められる導入文にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"雰囲気: {premise_context}\n"
                    f"世界データ: {world_payload}\n"
                    "この世界の最初の場面、現在地、最初に選べる行動を作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "narrator_initial",
            messages,
            max_tokens=700,
            world_name=world.world_name,
            player_name=player_name,
        )

    def generate_scene_image(self) -> ImageResult:
        pending_target = self.state.flags.get("pending_background_context")
        if isinstance(pending_target, dict):
            target = dict(pending_target)
        else:
            target = self._current_background_target(self.state.current_location or self.state.world_data.starting_location or "unknown")
        location = str(target.get("location") or self.state.current_location or self.state.world_data.starting_location or "unknown")
        display_name = str(target.get("display_name") or target.get("name") or location)
        target_kind = str(target.get("kind") or "location")
        target_description = str(target.get("description") or "")
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはSDXL用の背景画像プロンプト作成担当です。"
                    "必ず日本語ではなく英語の短い語句を配列にした prompt と、"
                    "必要なら negative_prompt を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界: {self.state.world_name}\n"
                    f"ロケーション: {location}\n"
                    f"表示対象: {display_name}\n"
                    f"表示対象種別: {target_kind}\n"
                    f"表示対象概要: {target_description}\n"
                    f"状況: {self.state.log_text(6)}\n"
                    "表示対象を表すファンタジーRPG背景画像のSDXLプロンプトを作ってください。"
                    "人物の立ち絵ではなく、場所の背景として使える構図にしてください。"
                ),
            },
        ]
        response = self._chat_json(
            "background_image_creator",
            messages,
            max_tokens=350,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

        prompt_parts = _as_str_list(response.get("prompt"))
        if not prompt_parts:
            prompt_parts = ["fantasy RPG background", display_name, "detailed environment"]
        prompt = ", ".join(prompt_parts)
        llm_negative_prompt = str(response.get("negative_prompt") or "")
        negative_prompt = self.image_backend.negative_prompt("background", llm_negative_prompt)
        image = self.image_backend.generate(prompt, negative_prompt=negative_prompt, purpose="background")

        prompt_record = {
            "manager": "background_image_creator",
            "prompt": image.prompt,
            "base_prompt": prompt,
            "prompt_parts": prompt_parts,
            "negative_prompt": negative_prompt,
            "negative_prompt_source": {
                "configured_purpose": "background",
                "llm_negative_prompt": llm_negative_prompt,
            },
            "background_target": _strip_response_metadata(target),
            "backend": image.backend,
            "generation_metadata": image.metadata,
            "source_response": _strip_response_metadata(response),
        }
        saved_image = self.save_store.save_background_asset(
            self.state.world_name,
            str(target.get("storage_key") or display_name or location),
            Path(image.path),
            prompt_record,
        )
        self._apply_background_image_to_target(target, saved_image, prompt_record)
        self.state.last_image_path = str(saved_image)
        if self.state.flags.get("pending_background_location") == location:
            self.state.flags.pop("pending_background_location", None)
        self.state.flags.pop("pending_background_context", None)
        self.save_game()
        return ImageResult(path=saved_image, backend=image.backend, prompt=image.prompt, metadata=image.metadata)

    def generate_cg_image(self, request: dict[str, Any] | None = None) -> ImageResult:
        if not isinstance(request, dict):
            request = {}
        else:
            request = dict(request)
        location = str(request.get("location") or self.state.current_location or self.state.world_data.starting_location or "unknown")
        visual_characters, visual_monsters = self._active_visual_subjects(location)
        if not request:
            request = self._manual_cg_request(location, visual_characters, visual_monsters)
        visual_subject_parts = _cg_subject_prompt_parts(visual_characters, visual_monsters)
        request_prompt_parts = _as_str_list(request.get("cg_prompt") or request.get("prompt"))
        description = str(request.get("cg_description") or request.get("description") or "")
        response = self._cg_image_creator(request, location, visual_characters, visual_monsters)
        refined_prompt_parts = _as_str_list(response.get("prompt"))
        description = description or str(response.get("description") or "")
        scene_brief_parts = _cg_scene_brief_parts(request, location)
        prompt_parts = _dedupe_strs(refined_prompt_parts + request_prompt_parts + scene_brief_parts + visual_subject_parts)
        if not prompt_parts:
            prompt_parts = [
                "fantasy RPG event CG",
                "cinematic scene illustration",
                location,
                self.state.log_text(4),
            ]
        prompt = ", ".join(_dedupe_strs(prompt_parts))
        llm_negative_prompt = str(response.get("negative_prompt") or request.get("negative_prompt") or "")
        negative_prompt = self.image_backend.negative_prompt("cg", llm_negative_prompt)
        image = self.image_backend.generate(prompt, negative_prompt=negative_prompt, purpose="cg")
        prompt_record = {
            "manager": "cg_image_creator",
            "prompt": image.prompt,
            "base_prompt": prompt,
            "prompt_parts": prompt_parts,
            "negative_prompt": negative_prompt,
            "negative_prompt_source": {
                "configured_purpose": "cg",
                "llm_negative_prompt": llm_negative_prompt,
            },
            "location": location,
            "description": description,
            "request": request,
            "scene_brief_parts": scene_brief_parts,
            "visual_subjects": _visual_subjects_context(visual_characters, visual_monsters),
            "backend": image.backend,
            "generation_metadata": image.metadata,
            "source_response": _strip_response_metadata(response),
        }
        saved_image = self.save_store.save_cg_asset(
            self.state.world_name,
            Path(image.path),
            prompt_record,
            scene_name=location,
        )
        self.state.flags["active_cg_image_path"] = str(saved_image)
        self.state.flags["active_cg_request"] = request
        self.state.flags.pop("pending_cg_request", None)
        self.state.world_data.extra.setdefault("cg_events", []).append(
            {
                "location": location,
                "path": str(saved_image),
                "request": request,
                "prompt": prompt,
            }
        )
        self.save_game()
        return ImageResult(path=saved_image, backend=image.backend, prompt=image.prompt, metadata=image.metadata)

    def _manual_cg_request(
        self,
        location: str,
        visual_characters: list[Character],
        visual_monsters: list[Character],
    ) -> dict[str, Any]:
        world = self.state.world_data
        location_data = world.locations.get(location)
        location_extra = location_data.extra if location_data and isinstance(location_data.extra, dict) else {}
        recent_story_lines = [
            line.strip()
            for line in self.state.display_log[-12:]
            if str(line).strip() and not str(line).lstrip().startswith((">", "["))
        ]
        graph = self._ensure_location_subnode_graph(world, location)
        subnode_id = self._current_subnode_id(location)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        subnode = nodes.get(subnode_id, {}) if isinstance(nodes, dict) else {}
        return _drop_empty(
            {
                "source": "manual_cg_button",
                "location": location,
                "recent_log": self.state.log_text(10),
                "latest_scene_text": "\n".join(recent_story_lines[-4:]),
                "location_context": _drop_empty(
                    {
                        "name": location,
                        "description": _short_text(location_data.description if location_data else "", 420),
                        "area": getattr(location_data, "area", "") if location_data else "",
                        "kind": location_extra.get("location_kind") or location_extra.get("kind"),
                        "danger_level": self._current_location_danger(location),
                        "current_subnode": _drop_empty(
                            {
                                "id": subnode_id,
                                "name": str(subnode.get("name") or ""),
                                "kind": str(subnode.get("kind") or ""),
                                "description": _short_text(str(subnode.get("description") or ""), 260),
                            }
                        ),
                    }
                ),
                "player_status_effects": _compact_value(self._actor_status_effects("player"), max_chars=700),
                "visible_subjects": _visual_subjects_context(visual_characters, visual_monsters),
                "prompt_goal": (
                    "Create one event CG prompt from the latest log, current location, visible player/NPC/enemy designs, "
                    "and status effects. Infer visible condition such as wounds, restraints, exhaustion, wet clothes, "
                    "or magical effects only when supported by the log or status data."
                ),
            }
        )

    def generate_character_image(self, character_name: str | None = None, save_game: bool = True) -> ImageResult:
        character = self._character_for_image(character_name)
        response = self._character_image_creator(character)
        prompt_parts = _as_str_list(response.get("prompt"))
        prompt_parts = _dedupe_strs(prompt_parts + _character_visual_feature_parts(character)) if prompt_parts else _character_prompt_parts(character)
        prompt = ", ".join(_dedupe_strs(prompt_parts))
        llm_negative_prompt = str(response.get("negative_prompt") or "")
        negative_prompt = self.image_backend.negative_prompt("character", llm_negative_prompt)
        negative_prompt = _append_negative_terms(negative_prompt, _subject_negative_terms())
        image = self.image_backend.generate(prompt, negative_prompt=negative_prompt, purpose="character")

        work_dir = GENERATED_DIR / "character_pipeline" / _safe_asset_segment(character.name)
        processed = process_subject_image(image.path, work_dir, source_image_name="generated_image.png")
        prompt_record = {
            "manager": "character_image_creator",
            "prompt": image.prompt,
            "base_prompt": prompt,
            "prompt_parts": prompt_parts,
            "negative_prompt": negative_prompt,
            "negative_prompt_source": {
                "configured_purpose": "character",
                "llm_negative_prompt": llm_negative_prompt,
            },
            "backend": image.backend,
            "generation_metadata": image.metadata,
            "postprocess": processed.metadata,
            "source_response": _strip_response_metadata(response),
        }
        saved_generated = self.save_store.save_character_asset(
            self.state.world_name,
            character.name,
            processed.source_image,
            "generated_image.png",
            prompt_record,
        )
        saved_no_bg = self.save_store.save_character_asset(
            self.state.world_name,
            character.name,
            processed.no_bg_image,
            "no_bg_image.png",
            prompt_record,
        )
        saved_face = self.save_store.save_character_asset(
            self.state.world_name,
            character.name,
            processed.face_image,
            "face_image.png",
            prompt_record,
        )
        saved_border = self.save_store.save_character_asset(
            self.state.world_name,
            character.name,
            processed.bordered_image,
            "add_border_image.png",
            prompt_record,
        )
        character.image_paths.update(
            {
                "generated_image": str(saved_generated),
                "no_bg_image": str(saved_no_bg),
                "face_image": str(saved_face),
                "add_border_image": str(saved_border),
            }
        )
        character.prompts["character_image_creator"] = prompt_record
        character.extra["image_pipeline"] = processed.metadata
        if character.flags.get("is_player") or str(character.uuid or "") == str(self.state.player_uuid or ""):
            character.flags.pop("portrait_generation_skipped", None)
            character.extra.pop("portrait_generation_skipped", None)
            self.state.flags["player_character"] = character.to_dict()
        self.state.last_image_path = str(saved_border)
        self.state.world_data.history.append(
            {
                "manager": "character_image_creator",
                "character": character.name,
                "response": _strip_response_metadata(response),
                "image_paths": dict(character.image_paths),
            }
        )
        if save_game:
            self.save_game()
        return ImageResult(path=saved_border, backend=image.backend, prompt=image.prompt, metadata=image.metadata)

    def generate_monster_image(self, monster_name: str | None = None) -> ImageResult:
        monster = self._monster_for_image(monster_name)
        response = self._monster_image_creator(monster)
        prompt_parts = _as_str_list(response.get("prompt"))
        if not prompt_parts:
            prompt_parts = _monster_prompt_parts(monster)
        prompt = ", ".join(_dedupe_strs(prompt_parts))
        llm_negative_prompt = str(response.get("negative_prompt") or "")
        negative_prompt = self.image_backend.negative_prompt("monster", llm_negative_prompt)
        negative_prompt = _append_negative_terms(negative_prompt, _subject_negative_terms())
        image = self.image_backend.generate(prompt, negative_prompt=negative_prompt, purpose="monster")

        work_dir = GENERATED_DIR / "monster_pipeline" / _safe_asset_segment(monster.name)
        processed = process_subject_image(image.path, work_dir, source_image_name="base_image.png")
        prompt_record = {
            "manager": "monster_image_creator",
            "prompt": image.prompt,
            "base_prompt": prompt,
            "prompt_parts": prompt_parts,
            "negative_prompt": negative_prompt,
            "negative_prompt_source": {
                "configured_purpose": "monster",
                "llm_negative_prompt": llm_negative_prompt,
            },
            "backend": image.backend,
            "generation_metadata": image.metadata,
            "postprocess": processed.metadata,
            "source_response": _strip_response_metadata(response),
        }
        saved_base = self.save_store.save_character_asset(
            self.state.world_name,
            monster.name,
            processed.source_image,
            "base_image.png",
            prompt_record,
        )
        saved_no_bg = self.save_store.save_character_asset(
            self.state.world_name,
            monster.name,
            processed.no_bg_image,
            "no_bg_image.png",
            prompt_record,
        )
        saved_face = self.save_store.save_character_asset(
            self.state.world_name,
            monster.name,
            processed.face_image,
            "face_image.png",
            prompt_record,
        )
        saved_border = self.save_store.save_character_asset(
            self.state.world_name,
            monster.name,
            processed.bordered_image,
            "add_border_image.png",
            prompt_record,
        )
        monster.image_paths.update(
            {
                "base_image": str(saved_base),
                "no_bg_image": str(saved_no_bg),
                "face_image": str(saved_face),
                "add_border_image": str(saved_border),
            }
        )
        monster.prompts["monster_image_creator"] = prompt_record
        monster.extra["image_pipeline"] = processed.metadata
        self.state.last_image_path = str(saved_border)
        self.state.world_data.history.append(
            {
                "manager": "monster_image_creator",
                "monster": monster.name,
                "response": _strip_response_metadata(response),
                "image_paths": dict(monster.image_paths),
            }
        )
        self.save_game()
        return ImageResult(path=saved_border, backend=image.backend, prompt=image.prompt, metadata=image.metadata)

    def _character_image_creator(self, character: Character) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False, include_monsters=False))
        character_payload = _ai_json(_character_ai_context(character))
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのキャラクター立ち絵用SDXLプロンプト担当です。"
                    "Fantasiaのキャラクター画像生成相当として、prompt と negative_prompt を持つJSONだけを返してください。"
                    "背景除去しやすいよう、単体、全身、白い単色背景、背景小物なしを明示してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    "外見、性格、特質、スキル、状態異常、装備、能力値を視覚的特徴として反映してください。"
                    "汎用的な人物ではなく、このキャラクター固有の印象が残る英語キーワード配列にしてください。"
                    "このキャラクターの立ち絵用SDXLプロンプトを作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "character_image_creator",
            messages,
            max_tokens=400,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _monster_image_creator(self, monster: Character) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False, include_monsters=False))
        monster_payload = _ai_json(_character_ai_context(monster))
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのモンスター画像用SDXLプロンプト担当です。"
                    "Fantasiaのモンスター画像生成相当として、prompt と negative_prompt を持つJSONだけを返してください。"
                    "背景除去しやすいよう、単体、全身、白い単色背景、背景小物なしを明示してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"モンスター名: {monster.name}\n"
                    f"モンスターデータ: {monster_payload}\n"
                    "このモンスターの表示用SDXLプロンプトを作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "monster_image_creator",
            messages,
            max_tokens=400,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _cg_image_creator(
        self,
        request: dict[str, Any],
        location: str,
        visual_characters: list[Character] | None = None,
        visual_monsters: list[Character] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(self._cg_world_context(location))
        subject_payload = _ai_json(_visual_subjects_context(visual_characters or [], visual_monsters or []))
        request_payload = json.dumps(request, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのイベントCG用SDXLプロンプト担当です。"
                    "通常背景ではなく、重要場面を一枚絵として表示するための英語プロンプトを作ってください。"
                    "UI、文字、吹き出し、枠を描かないようにしてください。"
                    "必ず prompt と negative_prompt を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {location}\n"
                    f"この場面に表示される人物・敵: {subject_payload}\n"
                    f"CGリクエスト: {request_payload}\n"
                    f"直近ログ:\n{self.state.log_text(8)}\n"
                    "表示されるプレイヤー、NPC、敵の外見、性格、特質、スキル、状態、装備をCGプロンプトへ反映してください。"
                    "UI、文字、吹き出し、枠は描かず、一枚絵として成立させてください。"
                    "この場面のCG画像プロンプトを作ってください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "CG prompt quality rules:\n"
                    "- Use the source narration as the single source of truth.\n"
                    "- Do not replace the event with a generic fantasy scene.\n"
                    "- Return concise English SDXL tags that preserve the exact action, location, mood, visible characters, visible monsters, and important objects.\n"
                    "- Include only concrete visual facts from the request, current log, and visible subject data.\n"
                    "- Keep established character and monster designs from subject data.\n"
                    "- Avoid UI, captions, speech bubbles, unrelated scenery, unrelated characters, and vague mood-only prompts.\n"
                ),
            }
        )
        return self._chat_json(
            "cg_image_creator",
            messages,
            max_tokens=350,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _cg_world_context(self, location: str) -> dict[str, Any]:
        world = self.state.world_data
        location_data = world.locations.get(location)
        location_extra = location_data.extra if location_data and isinstance(location_data.extra, dict) else {}
        return _drop_empty(
            {
                "world_name": world.world_name,
                "overview": _short_text(world.overview or world.world_situation, 520),
                "world_situation": _short_text(world.world_situation, 320),
                "current_location": _drop_empty(
                    {
                        "name": location,
                        "description": _short_text(location_data.description if location_data else "", 420),
                        "area": getattr(location_data, "area", "") if location_data else "",
                        "kind": location_extra.get("location_kind") or location_extra.get("kind"),
                        "danger_level": self._current_location_danger(location),
                    }
                ),
                "active_quest": self.state.active_quest,
                "world_time": _compact_value(world.extra.get("world_time"), max_chars=180) if isinstance(world.extra, dict) else None,
            }
        )

    def resolve_choice(self, choice: str) -> str:
        if self._is_game_over():
            return self.state.log_text(16)
        self.dismiss_active_cg()
        return self._resolve_player_input(choice, "choice")

    def resolve_action(self, action: str) -> str:
        if self._is_game_over():
            return self.state.log_text(16)
        self.dismiss_active_cg()
        return self._resolve_player_input(action, "free_action")

    def _is_generated_choice_input(self, action_text: str, input_type: str) -> bool:
        if input_type != "choice":
            return False
        normalized = action_text.strip()
        if not normalized:
            return False
        return any(normalized == str(choice).strip() for choice in self.state.choices if str(choice).strip())

    def _resolve_player_input(self, action: str, input_type: str) -> str:
        return resolve_player_action_input(
            self,
            action,
            input_type,
            as_bool=_as_bool,
            is_exploration_action=_is_exploration_action,
            is_skill_action=_is_skill_action,
            is_quest_abandon_action=_is_quest_abandon_action,
            is_quest_report_action=_quest_completion_report_action,
            strip_response_metadata=_strip_response_metadata,
        )

    def _input_dedupe_context(self) -> dict[str, Any]:
        active_encounter = self._active_encounter()
        encounter_key = ""
        if active_encounter:
            encounter_key = "|".join(
                str(active_encounter.get(key) or "")
                for key in ("opponent_name", "opponent_type", "location", "status")
            )
        active_conversation = self.state.flags.get("active_conversation")
        if isinstance(active_conversation, dict):
            conversation_key = str(active_conversation.get("name") or active_conversation.get("character") or "")
        else:
            conversation_key = str(active_conversation or "")
        return {
            "location": self.state.current_location,
            "screen_mode": str(self.state.flags.get("screen_mode") or ""),
            "active_quest": self.state.active_quest,
            "active_conversation": conversation_key,
            "active_encounter": encounter_key,
            "choices": tuple(str(choice) for choice in self.state.choices[:MAX_EXPLORATION_CHOICES]),
            "action_log_len": len(self.state.action_log),
            "display_log_len": len(self.state.display_log),
        }

    def _is_repeated_player_input(self, action: str, input_type: str, before_context: dict[str, Any]) -> bool:
        previous = self._last_resolved_input
        if not previous:
            return False
        if previous.get("action") != self._normalise_input_key(action):
            return False
        if previous.get("input_type") != input_type:
            return False
        if time.monotonic() - float(previous.get("time") or 0.0) > REPEATED_INPUT_DEDUPE_SECONDS:
            return False
        return before_context == previous.get("after_context")

    def _remember_resolved_input(self, action: str, input_type: str, before_context: dict[str, Any]) -> None:
        self._last_resolved_input = {
            "action": self._normalise_input_key(action),
            "input_type": input_type,
            "before_context": before_context,
            "after_context": self._input_dedupe_context(),
            "time": time.monotonic(),
        }

    @staticmethod
    def _normalise_input_key(action: str) -> str:
        return re.sub(r"\s+", " ", str(action or "").strip()).casefold()

    def _resolve_master_ai_turn(self, action: str, input_type: str, action_roll: dict[str, Any] | None = None) -> str:
        previous_location = self.state.current_location
        response = self._master_ai_facilitator(action, input_type, action_roll=action_roll)
        tool_payload = tool_effect_payload(response)
        content_violation = _as_bool(response.get("content_violation"))
        narration = str(
            response.get("narration")
            or response.get("text")
            or response.get("message")
            or response.get("reason")
            or "進行は静かに保留された。"
        )
        location = requested_location_from_tools(response, self.state.current_location)
        movement_result = {"location": location, "narration_lines": [], "status_lines": []}
        if not content_violation:
            movement_result = self._normalize_world_response_location(action, input_type, tool_payload, location)
            location = str(movement_result.get("location") or location)
            movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
            if movement_narration:
                narration = "\n".join([narration, *movement_narration]).strip()
        choices = self._filter_llm_choices_for_display(_as_str_list(response.get("choices")))
        if not choices:
            choices = self._filter_llm_choices_for_display(
                self.state.choices,
                keep_system_choices=True,
            )
        finished = _as_bool(response.get("finished"))
        history_entry = {
            "manager": "master_ai_facilitator",
            "action": action,
            "input_type": input_type,
            "location": location,
            "content_violation": content_violation,
            "finished": finished,
            "action_roll": action_roll,
            "response": _strip_response_metadata(response),
        }
        self.state.world_data.history.append(history_entry)

        generated_npcs: list[Character] = []
        if not content_violation:
            generated_npcs = self._generate_master_ai_npcs(action, input_type, response, location)
            if generated_npcs:
                history_entry["generated_npcs"] = [character.name for character in generated_npcs]
                choices = _exploration_choices(
                    choices + [f"{character.name}に話しかける" for character in generated_npcs]
                )

        summary: dict[str, Any] | None = None
        if not content_violation:
            summary = self._summarize_master_ai_process(action, input_type, response)
            if summary:
                history_entry["summary"] = _strip_response_metadata(summary)

        choices = self._augment_location_choices(choices, location)
        narration, choices, transition_response = self._maybe_start_combat_from_response(
            action,
            input_type,
            "master_ai_facilitator",
            tool_payload,
            location,
            narration,
            choices,
        )
        if transition_response:
            history_entry["combat_transition"] = _strip_response_metadata(transition_response)
        if not self._active_encounter() and movement_result.get("moved"):
            narration, choices, arrival_response = self._evaluate_hostile_arrival(
                action,
                input_type,
                "master_ai_facilitator_arrival",
                location,
                narration,
                choices,
            )
            if arrival_response:
                history_entry["hostile_arrival"] = _strip_response_metadata(arrival_response)
        self.state.flags["last_master_ai_finished"] = finished
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self._append_turn(action, narration, location, choices, input_type=input_type)
        self._set_player_presence(location)
        self._append_action_roll_log(action_roll)
        tool_result = apply_common_response_tools(
            self,
            response,
            source="master_ai_facilitator",
            action=action,
            input_type=input_type,
            location=location,
            previous_location=previous_location,
            movement_result=movement_result,
            default_target="player",
            content_violation=content_violation,
        )
        if tool_result.status_lines:
            history_entry["status_effects_applied"] = tool_result.status_lines
        if tool_result.results:
            history_entry["llm_tools"] = tool_result.to_record()
        item_event = tool_result.item_event
        if item_event and (
            item_event.get("items")
            or item_event.get("skipped_items")
            or item_event.get("lost_items")
            or item_event.get("equipment")
        ):
            history_entry["item_effects"] = item_event
        self.save_game()
        return self.state.log_text(16)

    def _generate_master_ai_npcs(
        self,
        action: str,
        input_type: str,
        facilitator_response: dict[str, Any],
        location: str,
    ) -> list[Character]:
        requests = _dedupe_npc_requests(
            _npc_generation_requests(tool_effect_payload(facilitator_response))
        )
        requests = _filter_npc_generation_requests(requests, self.state.world_data, location, self.state.player_name)
        if not requests:
            return []

        generated_response = self._master_ai_npc_generater(action, input_type, facilitator_response, requests, location)
        generated = self._apply_master_ai_npcs(generated_response, location)
        self.state.world_data.history.append(
            {
                "manager": "master_ai_npc_generater",
                "action": action,
                "input_type": input_type,
                "location": location,
                "requests": requests,
                "generated_npcs": [character.name for character in generated],
                "response": _strip_response_metadata(generated_response),
            }
        )

        for character in generated:
            detail = self._npc_detail_generater(action, input_type, facilitator_response, character)
            self._apply_npc_detail(character, detail)
            self.state.world_data.history.append(
                {
                    "manager": "npc_detail_generater",
                    "character": character.name,
                    "action": action,
                    "input_type": input_type,
                    "response": _strip_response_metadata(detail),
                }
            )
        return generated

    def _master_ai_npc_generater(
        self,
        action: str,
        input_type: str,
        facilitator_response: dict[str, Any],
        requests: list[Any],
        location: str,
    ) -> dict[str, Any]:
        return npc_generate.master_ai_npc_generater(
            self,
            action,
            input_type,
            facilitator_response,
            requests,
            location,
        )

    def _npc_detail_generater(
        self,
        action: str,
        input_type: str,
        facilitator_response: dict[str, Any],
        character: Character,
    ) -> dict[str, Any]:
        return npc_generate.npc_detail_generater(
            self,
            action,
            input_type,
            facilitator_response,
            character,
        )

    def _apply_master_ai_npcs(self, response: dict[str, Any], location: str) -> list[Character]:
        return npc_generate.apply_master_ai_npcs(self, response, location)

    def _apply_npc_detail(self, character: Character, response: dict[str, Any]) -> None:
        npc_generate.apply_npc_detail(self, character, response)
    def _master_ai_facilitator(
        self,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_context = self._focused_world_ai_context(include_recent_log=False)
        world_payload = _ai_json(world_context)
        recent_log = self.state.log_text(10)
        prior_summary_items = self.state.world_data.extra.get("master_ai_process_summaries", [])[-5:]
        prior_summaries = json.dumps(prior_summary_items, ensure_ascii=False) if prior_summary_items else ""
        has_action_roll = isinstance(action_roll, dict) and bool(action_roll)
        action_roll_payload = json.dumps(action_roll, ensure_ascii=False) if has_action_roll else ""
        system_lines = [
            "あなたはAI駆動RPGの中核進行管理AIです。",
            "Fantasiaのmaster_ai_facilitator相当として、入力の解釈、進行、状態更新候補、次の選択肢をまとめてください。",
            "content_violation はゲーム側では判定しないため、LLMとしてのみ判断してください。",
            "必ず content_violation, think, narration, process, finished を持つJSONだけを返してください。",
            "通常進行できる場合は content_violation を false にしてください。",
            "通常の移動はworld_mapの隣接地点だけにしてください。テレポート、ポータル等の明示的な処理がない限り遠隔地へ直接移動させないでください。",
            "世界データ.nearby_npcs にいるNPCは、現在地かつ現在サブノードにいてプレイヤーから見えるNPCです。",
            "nearby_npcs のNPCを「近くにいない」「姿が見えない」「別の場所にいる」と描写しないでください。",
        ]
        if has_action_roll:
            system_lines.append("game_side_action_roll が enabled=true の場合、成否・強制成功・強制失敗はゲーム側の確定判定として必ず尊重してください。")
        user_lines = [
            f"世界データ: {world_payload}",
            f"現在地: {self.state.current_location}",
            f"直近ログ:\n{recent_log}",
        ]
        if prior_summaries:
            user_lines.append(f"直近のmaster_ai要約:\n{prior_summaries}")
        user_lines.extend(
            [
                f"入力種別: {input_type}",
                f"プレイヤー行動: {action}",
            ]
        )
        if action_roll_payload:
            user_lines.append(f"game_side_action_roll: {action_roll_payload}")
        user_lines.extend(
            [
                "プレイヤー行動が現在地にいる既存NPCの名前、役割、別名を指している場合は、その既存NPCを対象にしてください。",
                "その人物を new_npc_requests で再生成しないでください。",
                "プレイヤー、主人公、あなた、自分、PC はNPC名として扱わないでください。",
                "この行動を中核AIとして進行し、必要なprocessと次の選択肢を返してください。",
            ]
        )
        messages = [
            {
                "role": "system",
                "content": "\n".join(system_lines),
            },
            {
                "role": "user",
                "content": "\n".join(user_lines),
            },
        ]
        messages.append({"role": "system", "content": tool_prompt_instruction()})
        messages.append({"role": "system", "content": self._movement_choice_rule_prompt(include_context=False)})
        return self._chat_json(
            "master_ai_facilitator",
            messages,
            max_tokens=900,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
            schema_instruction_text=self._master_ai_compact_schema_instruction(action, world_context, action_roll=action_roll),
        )

    def _master_ai_compact_schema_instruction(
        self,
        action: str,
        world_context: dict[str, Any],
        *,
        action_roll: dict[str, Any] | None = None,
    ) -> str:
        action_text = str(action or "").casefold()
        current_location = world_context.get("current_location") if isinstance(world_context, dict) else {}
        current_location = current_location if isinstance(current_location, dict) else {}
        current_subnode = world_context.get("current_subnode") if isinstance(world_context, dict) else {}
        current_subnode = current_subnode if isinstance(current_subnode, dict) else {}
        movement_options = world_context.get("movement_options") if isinstance(world_context, dict) else {}
        movement_options = movement_options if isinstance(movement_options, dict) else {}
        nearby_npcs = world_context.get("nearby_npcs") if isinstance(world_context, dict) else []
        active_quest = world_context.get("active_quest") if isinstance(world_context, dict) else {}
        has_action_roll = isinstance(action_roll, dict) and bool(action_roll)
        has_nearby_npcs = bool(nearby_npcs)
        has_active_quest = bool(active_quest)
        has_movement_options = bool(movement_options.get("allowed_moves"))
        dangerous_movement = str(current_location.get("dangerous_movement_rule") or current_subnode.get("movement_rule") or "").strip()

        def mentions(*terms: str) -> bool:
            return any(term and term.casefold() in action_text for term in terms)

        wants_person = has_nearby_npcs or mentions(
            "talk", "speak", "ask", "tell", "call", "meet", "npc", "person",
            "話", "聞", "尋", "呼", "会", "人物", "誰", "仲間", "同行",
        )
        wants_items = mentions(
            "item", "loot", "take", "pick", "buy", "sell", "give", "use", "equip", "gold", "reward",
            "拾", "取", "買", "売", "渡", "使", "装備", "報酬", "金", "素材", "食べ", "飲",
        )
        wants_craft = mentions(
            "craft", "make", "create", "combine", "synthesize", "forge", "cook", "brew", "mix",
            "クラフト", "作る", "作成", "制作", "合成", "加工", "鍛冶", "料理", "調理", "調合", "錬金",
        )
        wants_status = has_action_roll or mentions(
            "rest", "sleep", "heal", "treat", "eat", "drink", "injury", "damage", "train", "skill", "magic",
            "休", "眠", "治", "手当", "食", "飲", "怪我", "負傷", "訓練", "鍛", "魔法", "スキル",
        )
        wants_time = mentions("wait", "rest", "sleep", "search", "investigate", "study", "train", "待", "休", "眠", "探索", "調査", "勉強", "訓練")
        wants_home = mentions("build", "house", "home", "base", "furniture", "workshop", "construct", "建築", "家", "拠点", "家具", "工房", "作る")
        wants_map = has_active_quest or mentions(
            "map", "route", "path", "clue", "diary", "journal", "note",
            "探", "地図", "道", "経路", "手がかり", "周辺", "探索", "日記", "手記", "記録",
        )
        wants_game_over = mentions("die", "suicide", "fatal", "death", "死", "自殺", "致命", "破滅")

        lines = [
            "応答形式の厳守:",
            "- Markdownや説明文を付けず、JSONオブジェクトだけを返してください。",
            "- 必須キー: content_violation:boolean, think:string, narration:string, process:array|object|string, finished:boolean。",
            "- think と process は短く。process は後続要約用なので、通常行動では1-2項目で十分です。",
            "- 任意キーは必要な時だけ返してください: choices, recipients, reason, message。状態変更候補は必ず tool_judgements に confidence 付きで入れてください。",
            "- choices の配列の中身は文字列にしてください。",
        ]
        if has_action_roll:
            lines.append("- game_side_action_roll が渡されている場合は、その成功/失敗/強制結果を結果描写と状態更新に反映してください。")
        if has_movement_options or dangerous_movement:
            lines.append("- 移動する場合だけ tool_judgements に move_player を confidence=1.0 で入れてください。行き先は world_data.movement_options.allowed_moves にある場所だけです。")
            lines.append("- choices には移動系の選択肢を入れないでください。「奥へ進む」「元の位置に戻る」「○○へ向かう」「外に出る」などはゲーム側の移動メニューに任せます。")
            if has_active_quest:
                lines.append("- クエスト目標への経路や周辺部屋を明かす場合だけ tool_judgements の world_subnode_reveal に confidence=1.0 で subnode_map_reveal / unlock_subnode_route を入れてください。")
        if wants_person:
            lines.append("- nearby_npcs は同じロケーションかつ同じサブノードにいて、プレイヤーから見える場所のNPCです。そこにいるNPCを不在・遠方・見えない扱いにしないでください。")
            lines.append("- NPC対象がいる場合だけ recipients を使い、好感度は npc_change_relationship、NPC移動は npc_move / npc_join_party / npc_remove_party / npc_dead、新規NPC候補は request_npc_generation に入れてください。既存NPCを再生成しないでください。")
        if wants_items:
            lines.append("- アイテム入手は tool_judgements の item_add、消費・喪失・譲渡は item_remove、装備は item_equip、装備解除は item_unequip を confidence=1.0 で使ってください。所持金だけが増減する場合は gold_delta を使ってください。")
        if wants_craft:
            lines.append("- For explicit crafting/cooking/smithing/alchemy/combine actions, use tool_judgements craft with confidence=1.0 and arguments {consume_items:[...], craft_type:\"auto|mix|synthesis|smithing|alchemy|cooking\", content:\"intended result\"}. consume_items must use only names or item_uuid values listed in craft_candidates. Do not emit item_add or item_remove for the same craft.")
        if wants_status:
            lines.append("- HP/SP/空腹/状態異常が変わる場合だけ tool_judgements の hp_effects/sp_effects/hunger_delta/status_effects に confidence=1.0 で入れてください。")
        if wants_time:
            lines.append("- 明確に時間が経過する場合だけ tool_judgements の time_passage に confidence=1.0 で hours/days/reason を入れてください。")
        if wants_home:
            lines.append("- 家や拠点の建築・家具改善を素材で試みる時だけ tool_judgements の world_home_construction に confidence=1.0 で home_construction を入れてください。")
        if wants_map:
            lines.append("- ワールド地図や道順が新しく分かる時だけ tool_judgements の world_mainnode_reveal / world_subnode_reveal に confidence=1.0 で経路表示情報を入れてください。")
            lines.append("- 日記、手記、地図、噂、魔法的な手がかりから未知のダンジョン位置が確実に判明する場合だけ、tool_judgements の generate_dungeon に confidence=1.0 で name/description/dungeon_subtype/anchor_location/reason を入れてください。")
        if wants_game_over:
            lines.append("- 確実にゲームオーバーになる結果だけ tool_judgements の game_over に confidence=1.0 で reason/narration を入れてください。")
        lines.append(tool_prompt_instruction())
        lines.append(
            '例: {"content_violation": false, "intent": {"kind": "look", "summary": "周囲を見る"}, '
            '"narration": "短い描写", "process": [], "finished": false, "choices": ["周囲を見る"], "tool_judgements": []}'
        )
        return "\n".join(lines)

    def _summarize_master_ai_process(
        self,
        action: str,
        input_type: str,
        facilitator_response: dict[str, Any],
    ) -> dict[str, Any] | None:
        process = facilitator_response.get("process")
        if not process:
            return None
        recipients = _as_str_list(facilitator_response.get("recipients"))
        manager_name = (
            "master_ai_process_summarizer"
            if recipients
            else "master_ai_process_summarizer_with_no_recipients"
        )
        facilitator_payload = json.dumps(_strip_response_metadata(facilitator_response), ensure_ascii=False)
        process_payload = json.dumps(process, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの進行プロセス要約担当です。"
                    "master_ai_facilitatorのprocessを、後続AIが参照しやすい短い記憶へ圧縮してください。"
                    "宛先がある場合は master_ai_process_summarizer として summary, recipients を持つJSONだけを返してください。"
                    if recipients
                    else (
                        "あなたはAI駆動RPGの進行プロセス要約担当です。"
                        "master_ai_facilitatorのprocessを、特定の宛先なしで後続AIが参照しやすい短い記憶へ圧縮してください。"
                        "master_ai_process_summarizer_with_no_recipients として summary を持つJSONだけを返してください。"
                    )
                ),
            },
            {
                "role": "user",
                "content": (
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"宛先: {json.dumps(recipients, ensure_ascii=False)}\n"
                    f"facilitator応答: {facilitator_payload}\n"
                    f"process: {process_payload}\n"
                    "この進行プロセスを短く要約してください。"
                ),
            },
        ]
        response = self._chat_json(
            manager_name,
            messages,
            max_tokens=550,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )
        record = {
            "manager": manager_name,
            "action": action,
            "input_type": input_type,
            "recipients": recipients,
            "response": _strip_response_metadata(response),
        }
        self.state.world_data.extra.setdefault("master_ai_process_summaries", []).append(record)
        self.state.world_data.history.append(
            {
                "manager": manager_name,
                "action": action,
                "input_type": input_type,
                "recipients": recipients,
                "response": _strip_response_metadata(response),
            }
        )
        return response

    def _resolve_encounter_input(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        tool_result = self._resolve_combat_tool_choice(action, input_type, encounter)
        if tool_result is not None:
            return tool_result
        block_reason = self._player_incapacitated_action_block(action, encounter=encounter, for_movement=False)
        if block_reason:
            return self._resolve_blocked_player_action(action, input_type, block_reason, encounter=encounter)
        if _is_skill_action(action):
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_SKILL,
                action,
                input_type,
                encounter,
                {"action": action, "skill_name": self._extract_skill_name_for_combat(action)},
            )
        if _is_escape_action(action):
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_ESCAPE,
                action,
                input_type,
                encounter,
                {"action": action},
            )
        if _is_attack_action(action):
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_ATTACK,
                action,
                input_type,
                encounter,
                {"action": action, "target_name": _extract_attack_target(action)},
            )
        return self._resolve_player_any_input(action, input_type, encounter)

    def _resolve_combat_tool_choice(self, action: str, input_type: str, encounter: dict[str, Any]) -> str | None:
        text = str(action or "").strip()
        if not text:
            return None
        if text == COMBAT_CHOICE_BACK:
            self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
            self.state.choices = self._encounter_choices(encounter)
            self.save_game()
            return self.state.log_text(16)
        if text == COMBAT_CHOICE_ATTACK_MENU:
            self.state.flags[COMBAT_CHOICE_MENU_FLAG] = {"kind": "attack_target"}
            self.state.choices = self._encounter_choices(encounter)
            self.save_game()
            return self.state.log_text(16)
        if text == COMBAT_CHOICE_SKILL_MENU:
            self.state.flags[COMBAT_CHOICE_MENU_FLAG] = {"kind": "skill_list"}
            self.state.choices = self._encounter_choices(encounter)
            self.save_game()
            return self.state.log_text(16)
        if text == "使用できるスキルがない":
            self.state.choices = self._encounter_choices(encounter)
            self.save_game()
            return self.state.log_text(16)
        if text == COMBAT_CHOICE_ESCAPE:
            self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_ESCAPE,
                text,
                input_type,
                encounter,
                {"action": text},
            )
        if text == COMBAT_CHOICE_ACCEPT_SURRENDER:
            self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_ACCEPT_SURRENDER,
                text,
                input_type,
                encounter,
                {"action": text},
            )
        if text.startswith(COMBAT_CHOICE_ATTACK_PREFIX):
            target_name = text[len(COMBAT_CHOICE_ATTACK_PREFIX) :].strip()
            self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_ATTACK,
                text,
                input_type,
                encounter,
                {"target_name": target_name},
            )
        if text.startswith(COMBAT_CHOICE_SKILL_PREFIX):
            skill_name = self._combat_skill_name_from_choice(text)
            skill = self._find_player_skill(skill_name)
            if not skill:
                self.state.choices = self._encounter_choices(encounter)
                self.save_game()
                return self.state.log_text(16)
            target_mode = self._combat_skill_target_mode(skill)
            if target_mode == "none":
                self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
                return self._run_player_combat_tool(
                    CombatToolName.PLAYER_SKILL,
                    text,
                    input_type,
                    encounter,
                    {"skill_name": skill_name},
                )
            self.state.flags[COMBAT_CHOICE_MENU_FLAG] = {
                "kind": "skill_target",
                "skill_name": skill_name,
                "target_mode": target_mode,
            }
            self.state.choices = self._encounter_choices(encounter)
            self.save_game()
            return self.state.log_text(16)
        if text.startswith(COMBAT_CHOICE_TARGET_PREFIX):
            menu = self.state.flags.get(COMBAT_CHOICE_MENU_FLAG)
            if not isinstance(menu, dict) or str(menu.get("kind") or "") != "skill_target":
                return None
            skill_name = str(menu.get("skill_name") or "").strip()
            target_name = text[len(COMBAT_CHOICE_TARGET_PREFIX) :].strip()
            self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
            return self._run_player_combat_tool(
                CombatToolName.PLAYER_SKILL,
                text,
                input_type,
                encounter,
                {"skill_name": skill_name, "target_name": target_name},
            )
        return None

    def _run_player_combat_tool(
        self,
        tool_name: CombatToolName,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> str:
        result = run_combat_tool(
            self,
            CombatToolCall(
                tool_name,
                source="player_combat_choice",
                action=action,
                input_type=input_type,
                encounter=encounter,
                payload=payload or {},
            ),
        )
        self.state.world_data.history.append(
            {
                "manager": "player_combat_choice_tool",
                "action": action,
                "input_type": input_type,
                "tool": result.to_record(),
            }
        )
        self.save_game()
        return str(result.event.get("log_text") or self.state.log_text(16))

    def _combat_skill_name_from_choice(self, action: str) -> str:
        text = str(action or "").strip()
        if text.startswith(COMBAT_CHOICE_SKILL_PREFIX):
            text = text[len(COMBAT_CHOICE_SKILL_PREFIX) :].strip()
        if "(" in text:
            text = text.split("(", 1)[0].strip()
        return text.strip("「」[] ")

    def _combat_skill_target_mode(self, skill: dict[str, Any]) -> str:
        normalised = normalise_combat_skill(skill)
        effect_types = [combat_effect_type(effect) for effect in _as_list(normalised.get("type") or skill.get("type"))]
        if any(effect_type in {"damage_hp_party", "damage_sp_party", "absorption_party", "effect_enemy_party", "heal_party", "effect_ally_party", "effect_self"} for effect_type in effect_types):
            return "none"
        if any(effect_type in {"heal_single", "effect_ally_single"} for effect_type in effect_types):
            return "ally"
        return "enemy"

    def _combat_attack_target_choices(self, encounter: dict[str, Any]) -> list[str]:
        choices = [f"{COMBAT_CHOICE_ATTACK_PREFIX}{character.name}" for character in self._living_encounter_opponents(encounter)]
        return choices + [COMBAT_CHOICE_BACK]

    def _combat_skill_choices(self) -> list[str]:
        choices: list[str] = []
        for skill in self._player_skills():
            name = str(skill.get("name") or "").strip()
            if not name:
                continue
            cost = combat_skill_sp_cost(normalise_combat_skill(skill) or skill)
            choices.append(f"{COMBAT_CHOICE_SKILL_PREFIX}{name} (SP {cost})")
        if not choices:
            choices.append("使用できるスキルがない")
        return choices + [COMBAT_CHOICE_BACK]

    def _combat_skill_target_choices(self, encounter: dict[str, Any], target_mode: str) -> list[str]:
        if target_mode == "ally":
            choices = [f"{COMBAT_CHOICE_TARGET_PREFIX}プレイヤー"]
            choices.extend(f"{COMBAT_CHOICE_TARGET_PREFIX}{character.name}" for character in self._party_companions())
            return choices + [COMBAT_CHOICE_BACK]
        choices = [f"{COMBAT_CHOICE_TARGET_PREFIX}{character.name}" for character in self._living_encounter_opponents(encounter)]
        return choices + [COMBAT_CHOICE_BACK]

    def _select_player_skill_target_from_action(
        self,
        encounter: dict[str, Any],
        action: str,
        skill: dict[str, Any],
    ) -> Character | None:
        mode = self._combat_skill_target_mode(skill)
        if mode != "ally":
            return self._select_encounter_target_from_action(encounter, action)
        text = str(action or "")
        player = self.player_character()
        if player and ("プレイヤー" in text or self.state.player_name in text or player.name in text):
            return player
        for companion in self._party_companions():
            if companion.name and companion.name in text:
                return companion
        return player

    def _tool_message_event(self, tool_name: str, action: str, input_type: str, narration: str) -> dict[str, Any]:
        location = self.state.current_location or self.state.world_data.starting_location
        self._append_turn(action, narration, location, self._location_default_choices(location), input_type=input_type)
        self.save_game()
        return {"handled": True, "tool": tool_name, "log_text": self.state.log_text(16), "narration": narration}

    def _run_llm_action_tool(
        self,
        tool_name: LlmToolName,
        source: str,
        action: str,
        input_type: str,
        payload: dict[str, Any] | None = None,
    ) -> str | None:
        result = run_llm_tool(
            self,
            LlmToolCall(
                tool_name,
                source=source,
                action=action,
                input_type=input_type,
                location=self.state.current_location,
                payload=payload or {},
            ),
        )
        self.state.world_data.history.append(
            {
                "manager": "player_action_llm_tool",
                "action": action,
                "input_type": input_type,
                "tool": result.to_record(),
            }
        )
        self.save_game()
        return str(result.event.get("log_text") or self.state.log_text(16)) if result.acted else None

    def _resolve_quest_accept_tool_action(self, action: str, input_type: str, quest: QuestData | None = None) -> str | None:
        payload: dict[str, Any] = {}
        if quest:
            payload["quest_name"] = quest.name
        return self._run_llm_action_tool(LlmToolName.QUEST_ACCEPT, "player_choice", action, input_type, payload)

    def _resolve_quest_report_tool_action(self, action: str, input_type: str) -> str | None:
        return self._run_llm_action_tool(LlmToolName.QUEST_REPORT, "player_choice", action, input_type, {})

    def _resolve_quest_abandon_tool_action(self, action: str, input_type: str) -> str | None:
        return self._run_llm_action_tool(LlmToolName.QUEST_ABANDON, "player_choice", action, input_type, {})

    def _resolve_facility_tool_action(self, action: str, input_type: str) -> str | None:
        settlement = self._current_settlement_location()
        facilities = self.current_location_facilities()
        requested = _facility_request_from_action(action, facilities)
        if not requested:
            requested = _facility_request_from_creation_action(action, facilities)
        if not requested:
            return None
        existing = self._find_or_create_facility_record(settlement, requested) if settlement is not None else None
        tool_name = LlmToolName.FACILITY_VISIT if existing else LlmToolName.FACILITY_REQUEST
        return self._run_llm_action_tool(tool_name, "player_choice", action, input_type, {"facility_name": requested})

    def _resolve_conversation_tool_action(self, action: str, input_type: str) -> str | None:
        active = self._active_conversation_character()
        if active and _is_conversation_end_action(action):
            return self._run_llm_action_tool(
                LlmToolName.CONVERSATION_END,
                "player_choice",
                action,
                input_type,
                {"character_name": active.name},
            )
        target = None if active else self._find_conversation_target(action)
        if not target:
            return None
        return self._run_llm_action_tool(
            LlmToolName.CONVERSATION_START,
            "player_choice",
            action,
            input_type,
            {"character_name": target.name},
        )

    def _resolve_trade_negotiation_tool_action(self, action: str, input_type: str) -> str | None:
        target = self._trade_negotiation_target(action)
        if not target:
            return None
        return self._run_llm_action_tool(
            LlmToolName.TRADE_NEGOTIATION,
            "player_choice",
            action,
            input_type,
            {"character_name": target.name},
        )

    def _apply_response_quest_accept_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        if self.state.active_quest:
            return self._tool_message_event("quest_accept", action, input_type, "進行中の依頼があるため、別の依頼はまだ受けられない。")
        quest_name = str(response.get("quest_name") or response.get("target_name") or response.get("name") or "").strip()
        quest = self._find_quest_by_name(quest_name) if quest_name else None
        if quest is None:
            available = [item for item in self.state.world_data.quests if item.status in {"available", ""} and not item.flags.get("wild")]
            quest = available[0] if len(available) == 1 else None
        if quest is None or quest.status not in {"available", ""}:
            return self._tool_message_event("quest_accept", action, input_type, "その依頼は現在受けられない。")
        log_text = self._start_quest(action or f"依頼を受ける: {quest.name}", input_type or "choice", quest)
        return {"handled": True, "tool": "quest_accept", "quest_name": quest.name, "source": source, "log_text": log_text}

    def _apply_response_quest_report_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        quest = self._find_quest_by_name(self.state.active_quest)
        if not quest:
            return self._tool_message_event("quest_report", action, input_type, "報告できる進行中の依頼はない。")
        log_text = self._resolve_dedicated_quest_report(action or QUEST_REPORT_CHOICE_LABEL, input_type or "choice", quest)
        return {"handled": True, "tool": "quest_report", "quest_name": quest.name, "source": source, "log_text": log_text}

    def _apply_response_quest_abandon_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        quest = self._find_quest_by_name(self.state.active_quest)
        if not quest:
            return self._tool_message_event("quest_abandon", action, input_type, "放棄できる進行中の依頼はない。")
        previous_location = self.state.current_location
        location = previous_location or self.state.world_data.starting_location
        narration = _hide_internal_quest_tokens(f"依頼「{quest.name}」から撤退した。")
        self.state.flags["screen_mode"] = "exploration"
        self._finish_quest(quest, "abandoned", source or "quest_abandon_tool", {"narration": narration})
        choices = [_hide_internal_quest_tokens(choice) for choice in self._location_default_choices(location)]
        self._append_turn(action or "現在の依頼を放棄する", narration, location, choices, input_type=input_type or "choice")
        self._apply_visual_intent({}, "quest_abandon_tool", location, previous_location)
        self.save_game()
        return {"handled": True, "tool": "quest_abandon", "quest_name": quest.name, "source": source, "log_text": self.state.log_text(16)}

    def _apply_response_facility_visit_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        settlement = self._current_settlement_location()
        requested = str(response.get("facility_name") or response.get("target_name") or response.get("name") or "").strip()
        if not requested:
            facilities = self.current_location_facilities()
            requested = _facility_request_from_action(action, facilities) or _facility_request_from_creation_action(action, facilities)
        if settlement is None:
            return self._tool_message_event("facility_visit", action, input_type, f"この場所には「{requested or '施設'}」のような街の施設は存在しない。")
        facility = self._find_or_create_facility_record(settlement, requested)
        if not facility:
            return self._tool_message_event("facility_visit", action, input_type, f"{settlement.name}には「{requested}」という施設は見当たらない。")
        log_text = self._move_to_facility(settlement, facility, action=action or f"{requested}へ移動", input_type=input_type or "choice")
        return {"handled": True, "tool": "facility_visit", "facility_name": str(facility.get("name") or requested), "source": source, "log_text": log_text}

    def _apply_response_facility_request_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        requested = str(response.get("facility_name") or response.get("target_name") or response.get("name") or "").strip()
        action_text = action or (f"{requested}へ向かう" if requested else "施設へ向かう")
        log_text = self._create_facility_from_action(action_text, input_type or "choice")
        if log_text is None:
            return self._tool_message_event("facility_request", action_text, input_type or "choice", f"「{requested or 'その施設'}」は見つからなかった。")
        return {"handled": True, "tool": "facility_request", "facility_name": requested, "source": source, "log_text": log_text}

    def _apply_response_conversation_start_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        target_name = str(response.get("character_name") or response.get("target_name") or response.get("npc_name") or "").strip()
        target = self._match_character_reference_from_candidates(target_name, self._conversation_candidates()) if target_name else self._find_conversation_target(action)
        if not target:
            return self._tool_message_event("conversation_start", action, input_type, "会話できる相手は見当たらない。")
        log_text = self._start_conversation(action or f"{target.name}に話しかける", input_type or "choice", target)
        return {"handled": True, "tool": "conversation_start", "character_name": target.name, "source": source, "log_text": log_text}

    def _apply_response_conversation_end_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        target = self._active_conversation_character()
        if not target:
            return self._tool_message_event("conversation_end", action, input_type, "終了する会話はない。")
        log_text = self._continue_conversation(action or "会話を終える", input_type or "choice", target)
        return {"handled": True, "tool": "conversation_end", "character_name": target.name, "source": source, "log_text": log_text}

    def _apply_response_trade_negotiation_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
    ) -> dict[str, Any]:
        target_name = str(response.get("character_name") or response.get("target_name") or response.get("npc_name") or "").strip()
        candidates = self._current_trade_candidates()
        target = self._match_character_reference_from_candidates(target_name, candidates) if target_name else self._trade_negotiation_target(action)
        if not target:
            return self._tool_message_event("trade_negotiation", action, input_type, "値引き交渉できる相手は見当たらない。")
        log_text = self._resolve_trade_negotiation_action(action or f"{target.name}に値引き交渉をする", input_type or "choice", target)
        return {"handled": True, "tool": "trade_negotiation", "character_name": target.name, "source": source, "log_text": log_text}

    def _conversation_candidates(self) -> list[Character]:
        current_location = self.state.current_location or self.state.world_data.starting_location
        return [
            character
            for character in self.state.world_data.characters.values()
            if not character.flags.get("is_player")
            and _actor_present_at(character.location, character.state, character.flags, current_location)
            and self._character_matches_active_facility(character)
        ]

    def _resolve_start_combat_tool_action(self, action: str, input_type: str) -> str | None:
        if self._active_encounter():
            return None
        if not _combat_start_tool_candidate(action):
            return None
        response = self._start_combat_intent_evaluator(action, input_type)
        start_calls = [
            tool
            for tool in response_tool_calls(response, source="start_combat_intent_evaluator")
            if tool.get("name") == LlmToolName.START_COMBAT.value
        ]
        history_entry: dict[str, Any] = {
            "manager": "start_combat_intent_evaluator",
            "action": action,
            "input_type": input_type,
            "location": self.state.current_location,
            "response": _strip_response_metadata(response),
            "tool_called": bool(start_calls),
        }
        if not start_calls:
            self.state.world_data.history.append(history_entry)
            return None
        block_reason = self._player_incapacitated_action_block(action, combat_intent_confirmed=True)
        if block_reason:
            history_entry["blocked_reason"] = block_reason
            self.state.world_data.history.append(history_entry)
            return self._resolve_blocked_player_action(action, input_type, block_reason)
        result = run_llm_tool(
            self,
            LlmToolCall(
                LlmToolName.START_COMBAT,
                source="start_combat_intent_evaluator",
                action=action,
                input_type=input_type,
                location=self.state.current_location,
                payload=start_calls[0].get("arguments") or {},
            ),
        )
        history_entry["tool_result"] = result.to_record()
        self.state.world_data.history.append(history_entry)
        if not result.acted:
            return None
        encounter = self._active_encounter()
        if not encounter:
            return None
        event = result.event
        if _as_bool(event.get("surprise_attack") or event.get("surprise") or event.get("first_strike") or event.get("preemptive")):
            return self._resolve_player_attack(action, input_type, encounter)
        location = str(event.get("location") or encounter.get("location") or self.state.current_location)
        narration = str(event.get("narration") or "").strip()
        if not narration:
            opponent_name = str(event.get("opponent_name") or encounter.get("opponent_name") or "敵")
            narration = f"{opponent_name}との戦闘が始まった。"
        self._append_turn(action, narration, location, self._encounter_choices(encounter), input_type=input_type)
        self._request_background_if_needed(location)
        self.save_game()
        return self.state.log_text(16)

    def _start_combat_intent_evaluator(self, action: str, input_type: str) -> dict[str, Any]:
        context = self._start_combat_tool_context()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Fantasia's combat-start intent evaluator. Decide whether the current player input "
                    "definitely starts combat right now. Return compact JSON only. "
                    "Use tool_judgements start_combat with confidence exactly 1.0 only when the player explicitly "
                    "attacks, ambushes, or otherwise initiates immediate violence against a valid target, or when "
                    "the immediate result is that a present hostile enemy begins combat. "
                    "Do not start combat for inspecting attack traces, mentioning attacks, preparing, threatening, "
                    "negotiating, surrendering, calming someone, moving, quest reporting, reading, crafting, or any ambiguous action. "
                    "Never use top-level combat_started/start_combat/battle_started."
                ),
            },
            {
                "role": "user",
                "content": _ai_json(
                    {
                        "input_type": input_type,
                        "player_action": action,
                        "context": context,
                    }
                ),
            },
            {"role": "system", "content": tool_prompt_instruction()},
        ]
        schema = (
            "Return one JSON object with keys intent, narration, choices, tool_judgements. "
            "intent.kind must be combat_start, noncombat, or ambiguous. "
            "If combat does not definitely start now, tool_judgements must be []. "
            "If combat starts, tool_judgements must contain {\"name\":\"start_combat\",\"confidence\":1.0,"
            "\"arguments\":{\"opponent_name\":\"present target name\",\"surprise_attack\":false},\"reason\":\"...\"}. "
            "Do not include top-level side-effect keys."
        )
        try:
            return self._chat_json(
                "start_combat_intent_evaluator",
                messages,
                max_tokens=450,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
                schema_instruction_text=schema,
            )
        except Exception as exc:
            self.state.world_data.extra.setdefault("start_combat_intent_errors", []).append(
                {"action": action, "input_type": input_type, "location": self.state.current_location, "error": str(exc)}
            )
            return {"intent": {"kind": "ambiguous"}, "narration": "", "choices": [], "tool_judgements": []}

    def _start_combat_tool_context(self) -> dict[str, Any]:
        location_name = str(self.state.current_location or self.state.world_data.starting_location or "").strip()
        location_data = self.state.world_data.locations.get(location_name) if location_name else None
        subnode_id = self._current_subnode_id(location_name) if location_name and location_name in self.state.world_data.locations else ""
        subnode: dict[str, Any] = {}
        if location_name and subnode_id:
            graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
            node = graph.get("nodes", {}).get(subnode_id) if isinstance(graph, dict) else None
            if isinstance(node, dict):
                subnode = {
                    "id": subnode_id,
                    "name": str(node.get("name") or subnode_id),
                    "kind": str(node.get("kind") or ""),
                    "description": _short_text(str(node.get("description") or ""), 220),
                }
        nearby: list[dict[str, Any]] = []
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            if location_name and not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_active_facility(character):
                continue
            context = _character_ai_context(character, details=False, include_traits=False, include_skills=False)
            context["hostile"] = _character_is_hostile_actor(character)
            context["references"] = _character_reference_terms(character)
            nearby.append(context)
            if len(nearby) >= 12:
                break
        return _drop_empty(
            {
                "current_location": _location_ai_context(location_data) if location_data else {"name": location_name},
                "current_subnode": subnode,
                "nearby_characters": nearby,
                "recent_log": self.state.log_text(6),
            }
        )

    def _apply_response_start_combat_tool(
        self,
        response: dict[str, Any],
        source: str,
        *,
        action: str = "",
        input_type: str = "",
        location: str = "",
    ) -> dict[str, Any]:
        active = self._active_encounter()
        if active:
            return {"started": False, "reason": "active_encounter_exists", "opponent_name": active.get("opponent_name", "")}
        if not _as_bool(response.get("combat_started") or response.get("start_combat") or response.get("battle_started")):
            return {"started": False, "reason": "tool_not_requested"}
        location_name = str(location or self.state.current_location or self.state.world_data.starting_location or "").strip()
        requested_name = str(response.get("opponent_name") or response.get("target_name") or response.get("enemy_name") or "").strip()
        candidates = self._hostile_characters_at(location_name, limit=8)
        opponent = self._select_hostile_opponent(requested_name, candidates)
        if opponent is None and requested_name:
            opponent = self._select_present_combat_opponent(requested_name, location_name)
        if opponent is None and candidates:
            opponent = candidates[0]
        if opponent is None:
            opponent_type, opponent_name = self._find_or_create_encounter_opponent(
                "\n".join(part for part in (action, requested_name, str(response.get("reason") or "")) if str(part).strip())
            )
            opponent = self.state.world_data.character(opponent_name)
        if opponent is None:
            return {"started": False, "reason": "opponent_not_found", "opponent_name": requested_name}
        if not _character_is_hostile_actor(opponent):
            opponent.flags["hostile"] = True
            opponent.extra["hostile"] = True
        encounter = self._start_encounter_with_character(opponent, source=source, action=action, location=location_name)
        narration = str(response.get("narration") or "").strip() or f"{opponent.name}との戦闘が始まった。"
        event = {
            "started": True,
            "source": source,
            "action": action,
            "input_type": input_type,
            "location": location_name,
            "opponent_name": opponent.name,
            "opponent_uuid": opponent.uuid,
            "narration": narration,
            "surprise_attack": _as_bool(
                response.get("surprise_attack")
                or response.get("surprise")
                or response.get("first_strike")
                or response.get("preemptive")
            ),
            "player_initiated": _as_bool(response.get("player_initiated")),
            "reason": str(response.get("reason") or ""),
            "lines": [narration],
            "encounter": _strip_encounter_log(encounter),
        }
        self.state.world_data.extra.setdefault("start_combat_tool_events", []).append(
            {key: value for key, value in event.items() if key != "encounter"}
        )
        return event

    def _select_present_combat_opponent(self, requested_name: str, location: str) -> Character | None:
        location_name = str(location or self.state.current_location or self.state.world_data.starting_location or "").strip()
        candidates: list[Character] = []
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            if location_name and not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_active_facility(character):
                continue
            candidates.append(character)
        return self._select_hostile_opponent(requested_name, candidates)

    def _resolve_player_skill(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        return combat_flow.resolve_player_skill(self, action, input_type, encounter)

    def _resolve_player_escape(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        return combat_flow.resolve_player_escape(self, action, input_type, encounter)

    def _find_player_skill(self, name: str) -> dict[str, Any] | None:
        needle = str(name or "").strip().lower()
        for skill in self._player_skills():
            skill_name = str(skill.get("name") or "").strip()
            if not skill_name:
                continue
            if not needle or skill_name.lower() == needle or skill_name.lower() in needle or needle in skill_name.lower():
                return skill
        return None

    def _extract_skill_name_for_combat(self, action: str) -> str:
        return _extract_skill_name(action)

    def _strip_response_metadata_for_combat(self, response: dict[str, Any]) -> dict[str, Any]:
        return _strip_response_metadata(response)

    def _strip_encounter_log_for_combat(self, encounter: dict[str, Any]) -> dict[str, Any]:
        return _strip_encounter_log(encounter)

    def _game_over_choices_for_combat(self) -> list[str]:
        return _game_over_choices()

    def _player_skills(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        player = self.player_character()
        if player:
            skills.extend(player.skills)
        if self.state.party and isinstance(self.state.party[0], dict):
            skills.extend(_as_list(self.state.party[0].get("skills")))
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in skills:
            skill = _normalise_skill(raw)
            name = str(skill.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            result.append(skill)
        return result

    def _apply_opponent_hp_delta(
        self,
        encounter: dict[str, Any],
        delta: int,
        *,
        source: str,
        reason: str = "",
        message: str = "",
    ) -> dict[str, Any]:
        opponent = self._encounter_opponent(encounter)
        if isinstance(opponent, Character):
            if _safe_int(opponent.max_hp, 0) <= 0:
                self._ensure_character_runtime_data(opponent)
            old_hp = max(0, min(opponent.max_hp, _safe_int(opponent.current_hp, opponent.max_hp)))
            max_hp = max(1, _safe_int(opponent.max_hp, old_hp or 1))
        else:
            old_hp = max(0, _safe_int(encounter.get("opponent_hp"), 0))
            max_hp = max(1, _safe_int(encounter.get("opponent_max_hp"), old_hp or 1))
        new_hp = max(0, min(max_hp, old_hp + int(delta)))
        actual_delta = new_hp - old_hp
        encounter["opponent_hp"] = new_hp
        encounter["opponent_max_hp"] = max_hp
        if isinstance(opponent, Character):
            opponent.current_hp = new_hp
            opponent.max_hp = max_hp
            opponent.extra["current_hp"] = new_hp
            opponent.extra["max_hp"] = max_hp
            self._sync_encounter_opponent_entry(encounter, opponent)
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        name = str((opponent.name if isinstance(opponent, Character) else "") or encounter.get("opponent_name") or "相手")
        lines: list[str] = []
        if message:
            lines.append(f"> [戦闘] {message}")
        lines.append(f"> [HP] {name}: {old_hp}/{max_hp} -> {new_hp}/{max_hp} ({sign})")
        event = {
            "source": source,
            "reason": reason,
            "location": str(encounter.get("location") or self.state.current_location),
            "opponent": name,
            "old_hp": old_hp,
            "new_hp": new_hp,
            "max_hp": max_hp,
            "delta": actual_delta,
            "lines": lines,
        }
        self.state.world_data.extra.setdefault("hp_events", []).append(dict(event))
        return event

    def _set_encounter_opponent_combat_status(
        self,
        encounter: dict[str, Any],
        character: Character,
        status: str,
    ) -> None:
        entry = self._sync_encounter_opponent_entry(encounter, character)
        entry["status"] = status
        entry["opponent_status"] = status
        character.extra["combat_status"] = status
        if str(encounter.get("active_opponent_uuid") or "") == str(character.uuid or "") or str(encounter.get("opponent_uuid") or "") == str(character.uuid or ""):
            encounter["opponent_status"] = status
            encounter["opponent_hp"] = max(0, _safe_int(character.current_hp, encounter.get("opponent_hp") or 0))
            encounter["opponent_max_hp"] = max(1, _safe_int(character.max_hp, encounter.get("opponent_max_hp") or 1))

    def _encounter_opponent_combat_status(self, encounter: dict[str, Any], character: Character) -> str:
        entry = self._sync_encounter_opponent_entry(encounter, character)
        status = str(
            entry.get("opponent_status")
            or entry.get("status")
            or character.extra.get("combat_status")
            or character.flags.get("combat_status")
            or character.state
            or ""
        ).strip()
        if not status:
            status = "defeated" if _character_state_is_dead(character) or _safe_int(character.current_hp, 1) <= 0 else "active"
        entry["opponent_status"] = status
        if str(encounter.get("active_opponent_uuid") or encounter.get("opponent_uuid") or "") == str(character.uuid or ""):
            encounter["opponent_status"] = status
        return status

    def _apply_npc_action_tool(
        self,
        encounter: dict[str, Any],
        npc_response: dict[str, Any],
        rewrite_response: dict[str, Any],
    ) -> dict[str, Any]:
        return apply_llm_npc_action_tool(self, encounter, npc_response, rewrite_response)

    def _npc_surrender_from_encounter(self, encounter: dict[str, Any]) -> dict[str, Any]:
        result = run_combat_tool(
            self,
            CombatToolCall(
                CombatToolName.NPC_SURRENDER,
                source="legacy_npc_surrender_from_encounter",
                encounter=encounter,
                opponent=self._encounter_opponent(encounter),
            ),
        )
        return {"acted": result.acted, "kind": "surrender", "lines": result.lines, "event": result.event}

    def _npc_flee_from_encounter(self, encounter: dict[str, Any]) -> dict[str, Any]:
        result = run_combat_tool(
            self,
            CombatToolCall(
                CombatToolName.NPC_FLEE,
                source="legacy_npc_flee_from_encounter",
                encounter=encounter,
                opponent=self._encounter_opponent(encounter),
            ),
        )
        return {"acted": result.acted, "kind": "flee", "lines": result.lines, "event": result.event}

    def _npc_flee_destination(self, character: Character, location: str) -> dict[str, str]:
        world = self.state.world_data
        location = str(location or self.state.current_location or world.starting_location).strip()
        assigned_location, assigned_subnode = self._character_subnode_assignment(character)
        if assigned_location and assigned_location != location:
            assigned_subnode = ""
        current_subnode = assigned_subnode or self._current_subnode_id(location)
        graph = self._ensure_location_subnode_graph(world, location)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        if current_subnode and current_subnode in nodes:
            for edge in graph.get("edges", []):
                if not isinstance(edge, dict):
                    continue
                source = str(edge.get("from") or "")
                target = str(edge.get("to") or "")
                if source != current_subnode and target != current_subnode:
                    continue
                if edge.get("external"):
                    target_location = str(edge.get("target_location") or "").strip()
                    if target_location and target_location in world.locations:
                        target_subnode = str(edge.get("target_subnode") or "")
                        return {"location": target_location, "subnode": target_subnode, "label": target_location}
                    continue
                next_subnode = target if source == current_subnode else source
                if next_subnode and next_subnode in nodes:
                    node_name = str(nodes.get(next_subnode, {}).get("name") or next_subnode)
                    return {"location": location, "subnode": next_subnode, "label": node_name}
        for neighbor in self._world_neighbors_no_ensure(world, location):
            if neighbor in world.locations:
                return {"location": neighbor, "subnode": "", "label": neighbor}
        return {}

    def _accept_opponent_surrender(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        location = str(encounter.get("location") or self.state.current_location)
        accepted: list[str] = []
        for opponent in self._living_encounter_opponents(encounter):
            if not self._character_has_surrendered(opponent, encounter):
                continue
            self._set_encounter_opponent_combat_status(encounter, opponent, "surrender_accepted")
            opponent.flags["surrender_accepted"] = True
            opponent.extra["surrender_accepted"] = True
            opponent.flags["hostile"] = False
            opponent.extra["hostile"] = False
            accepted.append(opponent.name)
        acting = self._acting_encounter_opponents(encounter)
        if acting:
            encounter["status"] = "active"
            self._set_encounter_active_opponent(encounter, acting[0])
            self.state.flags["active_encounter"] = encounter
            self.state.flags["screen_mode"] = "battle"
            choices = self._encounter_choices(encounter)
        else:
            encounter["status"] = "ended"
            self.state.flags.pop("active_encounter", None)
            self.state.flags["screen_mode"] = "exploration"
            choices = self._location_default_choices(location)
        names = "、".join(accepted) if accepted else "相手"
        narration = f"{names}の降伏を受け入れた。"
        if acting:
            narration += " まだ戦意を失っていない相手が残っている。"
        else:
            narration += " 戦闘は終了した。"
        self._record_encounter_turn(
            action,
            input_type,
            encounter,
            [{"manager": "accept_opponent_surrender", "response": {"accepted": accepted, "remaining": [item.name for item in acting]}}],
        )
        self.state.world_data.history.append(
            {
                "manager": "accept_opponent_surrender",
                "action": action,
                "input_type": input_type,
                "encounter": _strip_encounter_log(encounter),
                "accepted": accepted,
                "remaining": [item.name for item in acting],
            }
        )
        self._append_turn(action, narration, location, choices, input_type=input_type)
        self.save_game()
        return self.state.log_text(16)

    def _resolve_player_attack(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any] | None = None,
    ) -> str:
        encounter = encounter or self._ensure_encounter(action)
        return combat_flow.resolve_player_attack(self, action, input_type, encounter)

    def _resolve_player_any_input(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        return combat_flow.resolve_player_free_action(self, action, input_type, encounter)

    def _ensure_encounter(self, action: str) -> dict[str, Any]:
        active = self._active_encounter()
        if active:
            self.state.flags["screen_mode"] = "battle"
            return active
        opponent_type, opponent_name = self._find_or_create_encounter_opponent(action)
        encounter = self._build_encounter(opponent_type, opponent_name, location=self.state.current_location)
        self.state.flags["active_encounter"] = encounter
        self.state.flags["screen_mode"] = "battle"
        self.state.world_data.extra.setdefault("encounters", []).append(
            {
                "event": "start",
                "opponent_type": opponent_type,
                "opponent_name": opponent_name,
                "enemy_strength": encounter.get("enemy_strength"),
                "danger_level": encounter.get("danger_level"),
                "opponent_attack": encounter.get("opponent_attack"),
                "opponent_defense": encounter.get("opponent_defense"),
                "location": self.state.current_location,
            }
        )
        return encounter

    def _active_encounter(self) -> dict[str, Any] | None:
        active = self.state.flags.get("active_encounter")
        if not isinstance(active, dict):
            return None
        if active.get("status") == "ended":
            return None
        return active

    def _hostile_characters_at(self, location: str, *, limit: int = 4) -> list[Character]:
        location_name = str(location or self.state.current_location or self.state.world_data.starting_location or "").strip()
        if not location_name:
            return []
        result: list[Character] = []
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            if _safe_int(character.max_hp, 0) > 0 and _safe_int(character.current_hp, 0) <= 0:
                continue
            self._ensure_character_runtime_data(character)
            if not _character_is_hostile_actor(character):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_current_subnode(character, location_name):
                continue
            if location_name == (self.state.current_location or self.state.world_data.starting_location) and not self._character_matches_active_facility(character):
                continue
            result.append(character)
            if len(result) >= limit:
                break
        return result

    def _select_hostile_opponent(self, requested_name: str, candidates: list[Character]) -> Character | None:
        target = _clean_generated_name(requested_name, "", kind="monster")
        if target:
            folded = target.casefold()
            for character in candidates:
                terms = _character_reference_terms(character)
                terms.extend(_as_str_list(character.flags.get("aliases")))
                terms.extend(_as_str_list(character.extra.get("aliases")))
                for term in _dedupe_strs([str(item or "").strip() for item in terms]):
                    if not term:
                        continue
                    if term == target or target in term or term in target or folded in term.casefold() or term.casefold() in folded:
                        return character
        return candidates[0] if candidates else None

    def _start_encounter_with_character(self, character: Character, *, source: str, action: str, location: str) -> dict[str, Any]:
        location_name = str(location or self.state.current_location or self.state.world_data.starting_location)
        subnode_id = self._current_subnode_id(location_name) if location_name else ""
        self._set_character_presence(character, location_name, "present", subnode_id=subnode_id)
        self._ensure_character_runtime_data(character)
        encounter = self._build_encounter("character", character.name, location=location_name)
        self.state.flags["active_encounter"] = encounter
        self.state.flags["screen_mode"] = "battle"
        self.state.world_data.extra.setdefault("encounters", []).append(
            {
                "event": "auto_start",
                "source": source,
                "action": action,
                "opponent_type": "character",
                "opponent_name": character.name,
                "opponent_uuid": character.uuid,
                "location": location_name,
                "subnode_id": subnode_id,
            }
        )
        return encounter

    def _danger_subnode_allows_random_encounter(
        self,
        location_name: str,
        subnode_id: str,
        node: dict[str, Any] | None = None,
        *,
        was_visited: bool = False,
    ) -> bool:
        if was_visited or self._active_encounter():
            return False
        location = self.state.world_data.locations.get(str(location_name or "").strip())
        if not location or not subnode_id:
            return False
        if _is_settlement_location(location) and not _world_location_blocks_world_map_departure(location):
            return False
        if not (_is_dungeon_location(location) or _world_location_blocks_world_map_departure(location)):
            return False
        danger = self._current_location_danger(location.name)
        if danger <= 0:
            return False
        graph = self._ensure_location_subnode_graph(self.state.world_data, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        current_node = node if isinstance(node, dict) else nodes.get(str(subnode_id or ""))
        if not isinstance(current_node, dict):
            return False
        return True

    def _maybe_start_first_visit_danger_subnode_encounter(
        self,
        location_name: str,
        subnode_id: str,
        *,
        was_visited: bool,
        source: str,
        action: str,
        narration: str = "",
        choices: list[str] | None = None,
    ) -> tuple[str, list[str], dict[str, Any]]:
        choices = list(choices or [])
        location_name = str(location_name or "").strip()
        subnode_id = str(subnode_id or "").strip()
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        node = graph.get("nodes", {}).get(subnode_id) if isinstance(graph, dict) else None
        if not self._danger_subnode_allows_random_encounter(location_name, subnode_id, node, was_visited=was_visited):
            return narration, choices, {}
        if self._hostile_characters_at(location_name):
            return narration, choices, {}
        roll_seed = f"danger-subnode-random-encounter:{self.state.world_name}:{location_name}:{subnode_id}"
        roll = random.Random(roll_seed).random()
        chance = (
            max(0.0, min(1.0, _safe_float(node.get("generate_enemy_rate"), DANGER_SUBNODE_RANDOM_ENCOUNTER_CHANCE)))
            if isinstance(node, dict) and "generate_enemy_rate" in node
            else DANGER_SUBNODE_RANDOM_ENCOUNTER_CHANCE
        )
        event: dict[str, Any] = {
            "source": source,
            "location": location_name,
            "subnode_id": subnode_id,
            "chance": chance,
            "roll": round(roll, 6),
            "triggered": False,
        }
        if roll >= chance:
            self.state.world_data.extra.setdefault("danger_subnode_random_encounters", []).append(event)
            return narration, choices, event
        monster = self._generate_random_danger_subnode_monster(
            location_name,
            subnode_id,
            node if isinstance(node, dict) else {},
            source=source,
            action=action,
        )
        if monster is None:
            event["error"] = "monster_generation_failed"
            self.state.world_data.extra.setdefault("danger_subnode_random_encounters", []).append(event)
            return narration, choices, event
        encounter = self._start_encounter_with_character(
            monster,
            source="danger_subnode_random_encounter",
            action=action,
            location=location_name,
        )
        subnode_name = str((node or {}).get("name") or subnode_id)
        line = f"{subnode_name}の気配が急に濃くなり、{monster.name}があなたの前に現れた。"
        narration = "\n".join(part for part in (narration, line) if str(part).strip())
        choices = self._encounter_choices(encounter)
        event.update(
            {
                "triggered": True,
                "monster_uuid": monster.uuid,
                "monster_name": monster.name,
                "danger_level": self._current_location_danger(location_name),
                "npc_template_id": monster.extra.get("npc_template_id") or monster.flags.get("npc_template_id"),
            }
        )
        self.state.world_data.extra.setdefault("danger_subnode_random_encounters", []).append(event)
        return narration, choices, event

    def _generate_random_danger_subnode_monster(
        self,
        location_name: str,
        subnode_id: str,
        node: dict[str, Any],
        *,
        source: str,
        action: str,
    ) -> Character | None:
        world = self.state.world_data
        location = world.locations.get(location_name)
        if not location:
            return None
        danger_level = max(1, self._current_location_danger(location_name))
        template_candidates = npc_template_prompt_summaries(
            ENEMY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger_level,
            used_ids=self._npc_template_used_ids(world),
            limit=12,
        )
        context = {
            "world": _world_ai_context(world, include_locations=False, include_characters=False, include_monsters=False, include_quests=True),
            "location": _location_ai_context(location),
            "subnode": {
                "id": subnode_id,
                "name": str(node.get("name") or subnode_id),
                "kind": str(node.get("kind") or ""),
                "description": _short_text(str(node.get("description") or ""), 500),
                "encounter_hint": str(node.get("encounter_hint") or ""),
            },
            "danger_level": danger_level,
            "enemy_templates": template_candidates,
            "recent_log": self.state.log_text(6),
            "movement_action": action,
            "source": source,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You generate one random hostile monster for a first-visit dangerous subnode encounter. "
                    "Choose the monster and npc_template_id from the current location, subnode, world tone, danger, "
                    "and supplied enemy_templates. Return JSON only. The monster must be hostile and suitable for immediate combat."
                ),
            },
            {"role": "user", "content": _ai_json(context)},
        ]
        try:
            response = self._chat_json(
                "danger_subnode_monster_generator",
                messages,
                max_tokens=650,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
        except Exception as exc:
            self.state.world_data.extra.setdefault("danger_subnode_monster_generation_errors", []).append(
                {
                    "location": location_name,
                    "subnode_id": subnode_id,
                    "error": str(exc),
                }
            )
            response = {}
        raw = dict(response) if isinstance(response, dict) else {}
        subnode_name = str(node.get("name") or subnode_id)
        raw.setdefault("name", f"{subnode_name}の魔物")
        raw.setdefault("role", "危険地帯の敵")
        raw.setdefault("category", "wild_encounter")
        raw.setdefault("gender", "none")
        raw.setdefault("age", "unknown")
        raw.setdefault("description", _short_text(f"{location.name}の{subnode_name}に潜んでいた敵対的な魔物。{location.description}", 260))
        raw.setdefault("personality", "縄張りに入った相手へ敵意を向ける。")
        raw.setdefault("look", raw.get("description") or raw.get("appearance") or "")
        raw.setdefault("hostile", True)
        raw.setdefault("image_generation_prompt", [raw.get("name"), "fantasy RPG monster", str(node.get("kind") or ""), location.name])
        raw_flags = raw.get("flags") if isinstance(raw.get("flags"), dict) else {}
        raw_extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
        raw["flags"] = {
            **raw_flags,
            "source": "danger_subnode_random_encounter",
            "hostile": True,
            "enemy_npc": True,
            "danger_level": danger_level,
        }
        raw["extra"] = {
            **raw_extra,
            "source": "danger_subnode_random_encounter",
            "origin_location": location.name,
            "origin_subnode_id": subnode_id,
            "spawn_subnode_id": subnode_id,
            "danger_level": danger_level,
            "subnode_kind": str(node.get("kind") or ""),
            "raw_danger_subnode_monster_generator": _strip_response_metadata(response) if isinstance(response, dict) else {},
        }
        npc_raw = self._template_augmented_npc_raw(
            raw,
            categories=ENEMY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger_level,
            seed=f"danger-subnode-monster:{world.world_name}:{location.name}:{subnode_id}",
            hostile=True,
        )
        character = _enemy_npc_from_raw(npc_raw, len(world.characters))
        character.name = _unique_character_name(world, character.name)
        character.category = "wild_encounter"
        character.flags["enemy_npc"] = True
        character.flags["hostile"] = True
        character.flags["danger_subnode_random_encounter"] = True
        character.extra["danger_subnode_random_encounter"] = True
        character.extra["spawn_subnode_id"] = subnode_id
        character.extra["origin_subnode_id"] = subnode_id
        self._finalize_generated_npc(
            character,
            location_name=location.name,
            danger_level=danger_level,
            role_hint="danger_subnode_random_encounter",
        )
        self._set_character_presence(character, location.name, "present", subnode_id=subnode_id)
        world.add_character(character)
        return character

    def _hostile_encounter_context(self, location: str, candidates: list[Character], narration: str = "") -> dict[str, Any]:
        world = self.state.world_data
        location_name = str(location or self.state.current_location or world.starting_location)
        location_data = world.locations.get(location_name)
        graph = self._ensure_location_subnode_graph(world, location_name)
        current_subnode = self._current_subnode_id(location_name) if graph else ""
        node = graph.get("nodes", {}).get(current_subnode, {}) if isinstance(graph, dict) else {}
        return {
            "world": _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True),
            "location": _location_ai_context(location_data) if location_data else {"name": location_name},
            "subnode": {
                "id": current_subnode,
                "name": str(node.get("name") or current_subnode),
                "kind": str(node.get("kind") or ""),
                "description": str(node.get("description") or ""),
            },
            "hostile_npcs": [_character_ai_context(character) for character in candidates],
            "recent_log": self.state.log_text(8),
            "current_narration": narration,
        }

    def _evaluate_hostile_arrival(
        self,
        action: str,
        input_type: str,
        source: str,
        location: str,
        narration: str,
        choices: list[str],
    ) -> tuple[str, list[str], dict[str, Any]]:
        if self._active_encounter():
            return narration, choices, {}
        candidates = self._hostile_characters_at(location)
        if not candidates:
            return narration, choices, {}
        context = self._hostile_encounter_context(location, candidates, narration)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはFantasiaの敵対NPC遭遇判定担当です。"
                    "プレイヤーが敵対的なNPCのいるロケーションまたはサブノードに入った直後、"
                    "NPCの性格、状態、世界観、場所を見て、その敵がどう反応するかを決めてください。"
                    "反応は、即座に襲い掛かる、様子をうかがう、まだ気付いていない、警告する、逃げるなどから自然に選んでください。"
                    "本当に攻撃を開始した場合だけ combat_started=true にしてください。"
                    "narration には、敵がこの場所に実在することがプレイヤーに分かる描写を入れてください。"
                    "必ず narration, combat_started を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": _ai_json(
                    {
                        "source": source,
                        "input_type": input_type,
                        "player_action": action,
                        "arrival_context": context,
                    }
                ),
            },
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    "When the hostile NPC actually starts combat now, emit tool_judgements with "
                    "start_combat confidence=1.0 and opponent_name. If the NPC only watches, warns, "
                    "threatens, blocks the way, or waits, tool_judgements must be []. "
                    "The game executes combat start only from the start_combat tool."
                ),
            }
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Tool judgement format: include tool_judgements as an array. "
                    "The game executes only items whose confidence is exactly 1.0. "
                    "For combat start, use {\"name\":\"start_combat\",\"confidence\":1.0,"
                    "\"arguments\":{\"opponent_name\":\"...\"},\"reason\":\"...\"}. "
                    "Use [] when combat does not definitely begin now."
                ),
            }
        )
        try:
            response = self._chat_json(
                "hostile_npc_encounter_evaluator",
                messages,
                max_tokens=550,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
        except Exception as exc:
            self.state.world_data.extra.setdefault("hostile_arrival_errors", []).append(
                {"source": source, "location": location, "error": str(exc), "candidates": [item.name for item in candidates]}
            )
            return narration, choices, {}
        encounter_line = str(response.get("narration") or response.get("text") or "").strip()
        if encounter_line:
            narration = "\n".join(part for part in (narration, encounter_line) if str(part).strip())
        response_choices = self._filter_llm_choices_for_display(_as_str_list(response.get("choices")))
        if response_choices:
            choices = _exploration_choices(response_choices + choices)
        tool_payload = tool_effect_payload(response)
        if _as_bool(tool_payload.get("combat_started")):
            result = run_llm_tool(
                self,
                LlmToolCall(
                    LlmToolName.START_COMBAT,
                    source=source,
                    action=action,
                    input_type=input_type,
                    location=location,
                    payload=tool_payload,
                ),
            )
            event = result.event
            if event.get("started"):
                encounter = self._active_encounter()
                choices = self._encounter_choices(encounter) if encounter else choices
        self.state.world_data.extra.setdefault("hostile_arrival_events", []).append(
            {
                "source": source,
                "location": location,
                "candidates": [character.name for character in candidates],
                "response": _strip_response_metadata(response),
            }
        )
        return narration, choices, response

    def _maybe_start_combat_from_response(
        self,
        action: str,
        input_type: str,
        source: str,
        response: dict[str, Any],
        location: str,
        narration: str,
        choices: list[str],
    ) -> tuple[str, list[str], dict[str, Any]]:
        active_encounter = self._active_encounter()
        if active_encounter:
            return narration, self._encounter_choices(active_encounter), {}
        tool_payload = tool_effect_payload(response)
        if not tool_payload and isinstance(response, dict) and not any(
            key in response for key in ("narration", "choices", "content_violation", "process", "intent", "tool_judgements")
        ):
            tool_payload = dict(response)
        explicit = _as_bool(tool_payload.get("combat_started"))
        if explicit:
            result = run_llm_tool(
                self,
                LlmToolCall(
                    LlmToolName.START_COMBAT,
                    source=source,
                    action=action,
                    input_type=input_type,
                    location=location,
                    payload=tool_payload,
                ),
            )
            event = result.event
            if not event.get("started"):
                return narration, choices, event
            line = str(event.get("narration") or "").strip()
            if line and line not in narration:
                narration = "\n".join(part for part in (narration, line) if str(part).strip())
            encounter = self._active_encounter()
            return narration, self._encounter_choices(encounter) if encounter else choices, event
        return narration, choices, {}

    def _find_or_create_encounter_opponent(self, action: str) -> tuple[str, str]:
        text = action.strip()
        current_location = self.state.current_location or self.state.world_data.starting_location
        self._write_temp_llm_context_log("encounter_target_input", action=text)
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, current_location):
                continue
            if not self._character_matches_active_facility(character):
                continue
            if character.name and character.name in text:
                return "character", character.name
        resolved_target = self._resolve_encounter_target_with_context(text, current_location)
        target_name = _clean_generated_name(
            resolved_target.get("target_name") or resolved_target.get("name") or resolved_target.get("monster_name"),
            "",
            kind="monster",
        )
        if not target_name:
            target_name = _clean_generated_name(_extract_attack_target(text), "", kind="monster")
        if not target_name:
            target_name = _clean_generated_name(_infer_encounter_target_from_context_text(f"{text}\n{self.state.log_text(16)}"), "", kind="monster")
        matched = self._match_present_encounter_target(target_name, current_location)
        if matched:
            return matched
        if not target_name:
            for character in self.state.world_data.characters.values():
                if character.flags.get("is_player"):
                    continue
                if not _actor_present_at(character.location, character.state, character.flags, current_location):
                    continue
                if not self._character_matches_active_facility(character):
                    continue
                return "character", character.name
        target_name = target_name or "未知の魔物"
        existing = self.state.world_data.character(target_name)
        if existing is None:
            profile = self._encounter_monster_profile(target_name, current_location, resolved_target)
            danger_level = self._npc_template_danger_for_location(current_location)
            npc_raw = self._template_augmented_npc_raw(
                {
                    "name": target_name,
                    "role": profile["category"] or "敵対者",
                    "category": "enemy_npc",
                    "gender": profile["gender"],
                    "age": profile["age"],
                    "description": profile["description"],
                    "personality": profile["personality"],
                    "look": profile["look"],
                    "traits": profile["traits"],
                    "image_generation_prompt": profile["image_generation_prompt"],
                    "flags": {
                        "source": "encounter_target_resolver",
                        "resolved_from_action": text,
                        "resolver": _strip_response_metadata(resolved_target),
                        "hostile": True,
                        "enemy_npc": True,
                    },
                    "extra": {
                        "aliases": _dedupe_strs([target_name, profile["category"], "敵", "魔物"]),
                        "description": profile["description"],
                        "appearance_prompt": ", ".join(profile["image_generation_prompt"]),
                    },
                },
                categories=ENEMY_NPC_TEMPLATE_CATEGORIES,
                danger_level=danger_level,
                seed=f"encounter-target:{self.state.world_name}:{current_location}:{target_name}",
                hostile=True,
            )
            character = _enemy_npc_from_raw(npc_raw, len(self.state.world_data.characters))
            character.name = _unique_character_name(self.state.world_data, character.name)
            self._set_character_presence(character, current_location, "present")
            self._finalize_generated_npc(
                character,
                location_name=current_location,
                danger_level=danger_level,
                role_hint="encounter_target",
            )
            self.state.world_data.add_character(character)
            target_name = character.name
        else:
            self._set_character_presence(existing, current_location, "present")
            self._ensure_character_runtime_data(existing)
        return "character", target_name

    def _match_present_encounter_target(self, target_name: str, location: str) -> tuple[str, str] | None:
        target = _clean_generated_name(target_name, "", kind="monster")
        if not target:
            return None

        def matches(term: Any) -> bool:
            text = str(term or "").strip()
            return bool(text and (text == target or target in text or text in target))

        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location):
                continue
            if not self._character_matches_active_facility(character):
                continue
            terms = [character.name, character.role, character.category]
            terms.extend(_as_str_list(character.flags.get("aliases")))
            terms.extend(_as_str_list(character.extra.get("aliases")))
            if any(matches(term) for term in terms):
                return "character", character.name
        return None

    def _resolve_encounter_target_with_context(self, action: str, location: str) -> dict[str, Any]:
        if not action.strip():
            return {}
        context_text = self._read_temp_llm_context_log()
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの戦闘相手解決担当です。"
                    "プレイヤー入力、現在地、直近ログから、今から戦闘になる相手だけを推定してください。"
                    "新しい敵名を創作しすぎず、入力や直近ログに出ている対象を優先してください。"
                    "target_name は固有名詞または種族名だけにし、「不意打ちで」「戦いを始める」などの行動語を混ぜないでください。"
                    "例: 「迫り来る蟲たちに向けて攻撃」なら target_name は「蟲」または文脈上の具体名だけです。"
                    "例: 「街道をふさぐモンスターへ斬りかかる」なら target_name は依頼やログにある魔物名、なければ「街道をふさぐ魔物」です。"
                    "必ず target_name, opponent_type, category, description を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"現在地: {location}\n"
                    f"プレイヤー行動: {action}\n"
                    f"一時コンテキストログ:\n{context_text}\n"
                    "この行動で戦闘相手にすべき対象を推定してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "New opponent profile rule: when the target is not an already-present character, include gender, "
                    "age, look, personality, and image_generation_prompt. Use gender=none and age=adult/ancient/unknown "
                    "for monsters or non-human entities when exact human-style values are not meaningful."
                ),
            }
        )
        try:
            response = self._chat_json(
                "encounter_target_resolver",
                messages,
                max_tokens=300,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
        except Exception as exc:
            self._write_temp_llm_context_log(
                "encounter_target_resolver_error",
                action=action,
                errors=[str(exc)],
            )
            return {}
        if not _clean_generated_name(response.get("target_name") or response.get("name") or response.get("monster_name"), "", kind="monster"):
            fallback_target = _infer_encounter_target_from_context_text(f"{action}\n{context_text}")
            if fallback_target:
                response["target_name"] = fallback_target
                response.setdefault("opponent_type", "character")
                response.setdefault("category", "wild_encounter")
                response.setdefault("reason", "LLMの対象名が代名詞だったため、一時ログ本文から明示対象を補正した。")
        self._write_temp_llm_context_log("encounter_target_resolved", action=action, response=response)
        return response

    def _resolve_context_reference(
        self,
        action: str,
        purpose: str,
        *,
        allowed_target_types: list[str] | None = None,
    ) -> dict[str, Any]:
        if not action.strip() or not _text_may_need_context_reference(action):
            return {}
        context_text = self._read_temp_llm_context_log()
        visible_payload = _ai_json(self._temp_llm_context_snapshot())
        allowed = allowed_target_types or ["character", "monster", "location", "quest", "facility", "item", "action", "unknown"]
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの曖昧参照解決担当です。"
                    "プレイヤー入力の「それ」「あの人」「さっきの場所」「その依頼」などが何を指すかを、"
                    "現在地、見えている対象、直近ログ、一時コンテキストから推定してください。"
                    "入力に明示された固有名詞やゲーム側確定情報を上書きしないでください。"
                    "target_name は対象名だけにし、行動語や説明文を混ぜないでください。"
                    "必ず target_type, target_name, confidence, reason を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用途: {purpose}\n"
                    f"許可対象種別: {json.dumps(allowed, ensure_ascii=False)}\n"
                    f"現在スナップショット: {visible_payload}\n"
                    f"プレイヤー行動: {action}\n"
                    f"一時コンテキストログ:\n{context_text}\n"
                    "この入力の曖昧な指示対象を推定してください。分からない場合は target_type=\"unknown\", target_name=\"\" を返してください。"
                ),
            },
        ]
        try:
            response = self._chat_json(
                "context_reference_resolver",
                messages,
                max_tokens=350,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
        except Exception as exc:
            self._write_temp_llm_context_log(
                "context_reference_resolver_error",
                action=action,
                errors=[str(exc)],
            )
            return {}
        target_type = str(response.get("target_type") or "").strip().casefold()
        if allowed and target_type and target_type not in {item.casefold() for item in allowed}:
            response["target_type"] = "unknown"
            response["target_name"] = ""
            response["reason"] = "推定対象種別が用途に合わなかったため破棄した。"
        self._write_temp_llm_context_log(f"context_reference_resolved:{purpose}", action=action, response=response)
        return response

    def _should_attach_temp_context(self, manager_name: str, action_text: str) -> bool:
        if manager_name not in TEMP_CONTEXT_AWARE_MANAGERS:
            return False
        return _text_may_need_context_reference(action_text)

    def _temp_context_reference_message(self, manager_name: str, action_text: str) -> dict[str, str]:
        context_text = self._read_temp_llm_context_log()
        return {
            "role": "user",
            "content": (
                "補助一時コンテキスト:\n"
                f"{context_text}\n"
                "上の補助情報は、プレイヤー行動の指示対象が曖昧な場合だけ参照してください。\n"
                "明示された固有名詞、現在の戦闘相手、会話相手、クエスト目的地、ゲーム側の確定判定を上書きしないでください。\n"
                f"対象manager: {manager_name}\n"
                f"曖昧さを含む可能性があるプレイヤー行動: {action_text}"
            ),
        }

    def _encounter_monster_profile(self, name: str, location: str, resolved: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved = resolved if isinstance(resolved, dict) else {}
        category = str(resolved.get("category") or resolved.get("monster_category") or "").strip()
        description = str(resolved.get("description") or resolved.get("summary") or "").strip()
        gender = str(resolved.get("gender") or "none").strip()
        age = str(resolved.get("age") or "unknown").strip()
        look = str(resolved.get("look") or resolved.get("appearance") or "").strip()
        personality = str(resolved.get("personality") or "").strip()
        if not category:
            category = "wild_encounter"
        if not description:
            description = f"{location}でプレイヤーの行動に反応して姿を現した魔物。"
        if not look:
            look = description
        if not personality:
            personality = "Acts according to its instincts, territory, and the current situation."
        traits = resolved.get("traits")
        normalised_traits = [
            trait for trait in (_trait_entry(item) for item in _as_list(traits)) if trait.get("name")
        ]
        if not normalised_traits:
            normalised_traits = [
                {"name": "慎重", "desc": "相手が降伏した場合は即座に殺さず、武装解除を優先する。"},
                {"name": "縄張り意識", "desc": "侵入者を殺すより追い払うことを優先する。"},
            ]
        prompt_parts = _as_str_list(resolved.get("image_generation_prompt") or resolved.get("visual_prompt"))
        if not prompt_parts:
            prompt_parts = ["fantasy RPG monster", name, category]
        return {
            "category": category,
            "description": description,
            "gender": gender,
            "age": age,
            "look": look,
            "personality": personality,
            "traits": normalised_traits,
            "image_generation_prompt": _dedupe_strs(prompt_parts),
        }

    def _temp_llm_context_path(self) -> Path:
        return Path(tempfile.gettempdir()) / "Fantasia" / "llm_context_recent.json"

    def _write_temp_llm_context_log(
        self,
        manager_name: str,
        *,
        action: str = "",
        response: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        try:
            event: dict[str, Any] = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "manager": manager_name,
            }
            if action:
                event["action"] = _short_text(action, 700)
            if response is not None:
                event["response"] = _compact_value(_strip_response_metadata(response), max_chars=1400)
            if errors:
                event["errors"] = [_short_text(item, 400) for item in errors]
            self._temp_llm_context_events.append(event)
            self._temp_llm_context_events = self._temp_llm_context_events[-TEMP_LLM_CONTEXT_EVENT_LIMIT:]
            payload = {
                "updated_at": event["time"],
                "context_file_note": "Temporary Fantasia runtime context for small LLM recovery prompts.",
                "current": self._temp_llm_context_snapshot(),
                "recent_events": list(self._temp_llm_context_events),
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            if len(text) > TEMP_LLM_CONTEXT_MAX_CHARS:
                payload["current"]["display_log"] = self.state.log_text(10)
                payload["recent_events"] = payload["recent_events"][-3:]
                text = json.dumps(payload, ensure_ascii=False, indent=2)
            if len(text) > TEMP_LLM_CONTEXT_MAX_CHARS:
                payload = {
                    "updated_at": event["time"],
                    "context_file_note": "Temporary Fantasia runtime context for small LLM recovery prompts.",
                    "current": _compact_value(payload.get("current", {}), max_chars=8000),
                    "recent_events": _compact_value(payload.get("recent_events", []), max_chars=3000),
                }
                text = json.dumps(payload, ensure_ascii=False, indent=2)
            path = self._temp_llm_context_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception:
            return

    def _read_temp_llm_context_log(self) -> str:
        try:
            path = self._temp_llm_context_path()
            if not path.exists():
                self._write_temp_llm_context_log("context_bootstrap")
            return path.read_text(encoding="utf-8")[-TEMP_LLM_CONTEXT_MAX_CHARS:]
        except Exception:
            return ""

    def _temp_llm_context_snapshot(self) -> dict[str, Any]:
        world = self.state.world_data
        location_name = self.state.current_location or world.starting_location
        subnode: dict[str, Any] = {}
        try:
            subnode_id = self._current_subnode_id(location_name)
            graph = self._ensure_location_subnode_graph(world, location_name)
            node = graph.get("nodes", {}).get(subnode_id) if isinstance(graph, dict) else None
            if isinstance(node, dict):
                subnode = {
                    "id": subnode_id,
                    "name": str(node.get("name") or subnode_id),
                    "kind": str(node.get("kind") or ""),
                    "description": _short_text(node.get("description") or "", 240),
                }
        except Exception:
            subnode = {}
        active_quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
        encounter = self._active_encounter()
        characters = []
        for character in world.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_active_facility(character):
                continue
            characters.append(
                {
                    "name": character.name,
                    "role": character.role,
                    "state": character.state,
                    "location": character.location,
                }
            )
        return _drop_empty(
            {
                "world_name": world.world_name,
                "player_name": self.state.player_name,
                "screen_mode": self.state.flags.get("screen_mode"),
                "current_location": location_name,
                "current_subnode": subnode,
                "choices": list(self.state.choices[:5]),
                "display_log": self.state.log_text(16),
                "visible_characters": characters[:6],
                "active_quest": _quest_ai_context(active_quest, include_log=True, include_extra=True) if active_quest else {},
                "active_encounter": _strip_encounter_log(encounter) if encounter else {},
            }
        )

    def _encounter_opponent_payload(self, encounter: dict[str, Any]) -> dict[str, Any]:
        name = str(encounter.get("opponent_name") or "")
        character = self.state.world_data.character(str(encounter.get("opponent_uuid") or name))
        if character:
            payload = _character_ai_context(character, details=True)
            payload["attack"] = character.attack
            payload["defense"] = character.defense
            payload["hostile"] = bool(character.flags.get("hostile") or character.extra.get("hostile"))
            payload["combat_status"] = self._encounter_opponent_combat_status(encounter, character)
            return _drop_empty(payload)
        return {"name": name, "type": "character"}

    def _encounter_player_payload(self, encounter: dict[str, Any]) -> dict[str, Any]:
        max_hp = max(1, _safe_int(encounter.get("player_max_hp"), self._player_max_hp()))
        current_hp = max(0, min(max_hp, _safe_int(encounter.get("player_hp"), self._player_current_hp(max_hp))))
        max_sp = max(1, _safe_int(encounter.get("player_max_sp"), self._player_max_sp()))
        current_sp = max(0, min(max_sp, _safe_int(encounter.get("player_sp"), self._player_current_sp(max_sp))))
        player = self.player_character()
        return _drop_empty(
            {
                "name": self.state.player_name,
                "current_hp": current_hp,
                "max_hp": max_hp,
                "hp_ratio": round(current_hp / max_hp, 3),
                "current_sp": current_sp,
                "max_sp": max_sp,
                "sp_ratio": round(current_sp / max_sp, 3),
                "hunger": self._player_hunger(),
                "max_hunger": PLAYER_MAX_HUNGER,
                "hunger_ratio": round(self._player_hunger() / PLAYER_MAX_HUNGER, 3),
                "player_status": encounter.get("player_status"),
                "player_status_effects": self._actor_status_effects("player", encounter),
                "player_character": _character_ai_context(player, details=True) if player else {},
            }
        )

    def _apply_encounter_update(
        self,
        encounter: dict[str, Any],
        update: Any,
        *,
        context_actor: Character | str | None = None,
        action_context: str = "",
        response_context: Any = None,
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        if isinstance(update, list):
            for item in update:
                applied.extend(
                    self._apply_encounter_update(
                        encounter,
                        item,
                        context_actor=context_actor,
                        action_context=action_context,
                        response_context=response_context,
                    )
                )
            return applied
        if not isinstance(update, dict):
            return applied
        for key, value in update.items():
            text_key = str(key)
            if text_key in {"player_status_effect", "player_status_effects", "add_player_status_effect", "add_player_status_effects"}:
                applied.extend(
                    self._add_actor_status_effects(
                        "player",
                        value,
                        source="encounter_update",
                        context_actor=context_actor,
                        action_context=action_context,
                        response_context=response_context,
                    )
                )
                continue
            if text_key in {"opponent_status_effect", "opponent_status_effects", "add_opponent_status_effect", "add_opponent_status_effects"}:
                applied.extend(
                    self._add_actor_status_effects(
                        "opponent",
                        value,
                        encounter=encounter,
                        source="encounter_update",
                        context_actor=context_actor,
                        action_context=action_context,
                        response_context=response_context,
                    )
                )
                continue
            if text_key in {"remove_player_status_effect", "remove_player_status_effects"}:
                self._remove_actor_status_effects("player", value)
                continue
            if text_key in {"remove_opponent_status_effect", "remove_opponent_status_effects"}:
                self._remove_actor_status_effects("opponent", value, encounter=encounter)
                continue
            if text_key == "status_effects":
                applied.extend(
                    self._add_targeted_status_effects(
                        encounter,
                        value,
                        source="encounter_update",
                        context_actor=context_actor,
                        action_context=action_context,
                        response_context=response_context,
                    )
                )
                continue
            if text_key in {"player_sp_delta", "sp_delta"}:
                self._apply_player_sp_delta(value, source="encounter_update", encounter=encounter)
                continue
            if text_key in {"player_hunger_delta", "hunger_delta"}:
                self._apply_player_hunger_delta(value, source="encounter_update")
                continue
            if text_key in {"player_sp", "current_sp"}:
                self._set_player_sp(value, max_sp=self._hp_number(encounter.get("player_max_sp"), self._player_max_sp()), encounter=encounter)
                continue
            if text_key in {"player_hunger", "current_hunger", "hunger"}:
                self._set_player_hunger(value)
                continue
            if text_key in {"player_max_sp", "max_sp"}:
                current_sp = self._player_current_sp(max(1, self._hp_number(value, self._player_max_sp())))
                self._set_player_sp(current_sp, max_sp=max(1, self._hp_number(value, self._player_max_sp())), encounter=encounter)
                continue
            if text_key.endswith("_delta"):
                delta = self._hp_number(value, 0)
                if delta == 0:
                    continue
                base_key = text_key[: -len("_delta")]
                if base_key == "opponent_hp":
                    self._apply_opponent_hp_delta(encounter, delta, source="encounter_update", reason=text_key)
                    continue
                encounter[base_key] = max(0, int(encounter.get(base_key, 0) or 0) + delta) if base_key.endswith("_hp") else int(encounter.get(base_key, 0) or 0) + delta
                continue
            if text_key in {"player_hp", "opponent_hp"}:
                if text_key == "opponent_hp":
                    current = max(0, self._hp_number(encounter.get("opponent_hp"), 0))
                    self._apply_opponent_hp_delta(encounter, self._hp_number(value, current) - current, source="encounter_update", reason=text_key)
                    continue
                encounter[text_key] = max(0, self._hp_number(value, 0))
                continue
            encounter[text_key] = value
            if text_key == "player_status":
                effect = _status_effect_from_status_text(str(value))
                if effect:
                    applied.extend(
                        self._add_actor_status_effects(
                            "player",
                            effect,
                            source="player_status",
                            context_actor=context_actor,
                            action_context=action_context,
                            response_context=response_context,
                        )
                    )
            elif text_key == "opponent_status":
                effect = _status_effect_from_status_text(str(value))
                if effect:
                    applied.extend(
                        self._add_actor_status_effects(
                            "opponent",
                            effect,
                            encounter=encounter,
                            source="opponent_status",
                            context_actor=context_actor,
                            action_context=action_context,
                            response_context=response_context,
                        )
                    )
        self._sync_encounter_status_effects(encounter)
        if int(encounter.get("opponent_hp") or 0) > 0 and not self._is_game_over():
            self._update_encounter_presence(encounter, "present")
        return applied

    def _add_actor_status_effects(
        self,
        target: str,
        value: Any,
        *,
        encounter: dict[str, Any] | None = None,
        source: str = "",
        context_actor: Character | str | None = None,
        action_context: str = "",
        response_context: Any = None,
    ) -> list[dict[str, Any]]:
        effects = [_normalise_status_effect(item, source=source) for item in _status_effect_items(value)]
        effects = [effect for effect in effects if effect]
        if effects:
            effects = [
                self._contextualise_combat_status_effect(
                    effect,
                    target=target,
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response_context,
                )
                for effect in effects
            ]
        if target == "player":
            effects = [effect for effect in effects if not self._player_is_immune_to_status(effect)]
        if not effects:
            return []
        status_list = self._actor_status_effects(target, encounter)
        for effect in effects:
            _merge_status_effect(status_list, effect)
        self._sync_actor_status_effects(target, status_list, encounter)
        return effects

    def _contextualise_combat_status_effect(
        self,
        effect: dict[str, Any],
        *,
        target: str,
        context_actor: Character | str | None = None,
        action_context: str = "",
        response_context: Any = None,
    ) -> dict[str, Any]:
        if target != "player" or not _status_effect_is_incapacitating(effect):
            return effect
        if not _status_effect_has_generic_incapacitated_text(effect):
            return effect
        actor_name = context_actor.name if isinstance(context_actor, Character) else str(context_actor or "")
        context_text = "\n".join(
            part
            for part in (
                action_context,
                _status_response_context_text(response_context),
                str(effect.get("effect") or ""),
                str(effect.get("description") or ""),
            )
            if part
        )
        detail = _contextual_incapacitated_status_details(actor_name, context_text)
        contextualised = dict(effect)
        if _status_effect_has_generic_incapacitated_name(contextualised):
            contextualised["name"] = detail["name"]
        if _status_effect_has_generic_incapacitated_description(contextualised):
            contextualised["description"] = detail["description"]
        if not str(contextualised.get("llm_effect") or contextualised.get("effect") or "").strip():
            contextualised["llm_effect"] = detail["effect"]
        contextualised["effect_id"] = "Inoperable"
        return contextualised

    def _add_targeted_status_effects(
        self,
        encounter: dict[str, Any],
        value: Any,
        *,
        source: str = "",
        context_actor: Character | str | None = None,
        action_context: str = "",
        response_context: Any = None,
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        if isinstance(value, dict):
            applied.extend(
                self._add_actor_status_effects(
                    "player",
                    value.get("player") or value.get("players") or value.get("player_status_effects"),
                    encounter=encounter,
                    source=source,
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response_context,
                )
            )
            applied.extend(
                self._add_actor_status_effects(
                    "opponent",
                    value.get("opponent") or value.get("enemy") or value.get("enemies") or value.get("opponent_status_effects"),
                    encounter=encounter,
                    source=source,
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response_context,
                )
            )
            if any(key in value for key in ("name", "title", "label", "status", "condition", "effect", "description")):
                target = _status_effect_target(value)
                if target:
                    applied.extend(
                        self._add_actor_status_effects(
                            target,
                            value,
                            encounter=encounter,
                            source=source,
                            context_actor=context_actor,
                            action_context=action_context,
                            response_context=response_context,
                        )
                    )
            return applied
        for item in _status_effect_items(value):
            target = _status_effect_target(item)
            if target:
                applied.extend(
                    self._add_actor_status_effects(
                        target,
                        item,
                        encounter=encounter,
                        source=source,
                        context_actor=context_actor,
                        action_context=action_context,
                        response_context=response_context,
                    )
                )
        return applied

    def _remove_actor_status_effects(self, target: str, value: Any, *, encounter: dict[str, Any] | None = None) -> None:
        remove_effects = [_normalise_status_effect(item) for item in _status_effect_items(value)]
        remove_keys = {_status_effect_merge_key(effect) for effect in remove_effects if effect.get("name")}
        remove_ids = {_status_effect_id(effect) for effect in remove_effects}
        remove_ids.discard("")
        if not remove_ids and not remove_keys:
            return
        status_list = [
            effect
            for effect in self._actor_status_effects(target, encounter)
            if _status_effect_merge_key(effect) not in remove_keys and (remove_keys or _status_effect_id(effect) not in remove_ids)
        ]
        self._sync_actor_status_effects(target, status_list, encounter)

    def _actor_status_effects(self, target: str, encounter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if target == "player":
            return self.state.status_effects
        opponent = self._encounter_opponent(encounter or {})
        if isinstance(opponent, Character):
            return opponent.status_effects
        raw = (encounter or {}).get("opponent_status_effects")
        return raw if isinstance(raw, list) else []

    def _player_incapacitated_effects(self) -> list[dict[str, Any]]:
        return [
            effect
            for effect in self._actor_status_effects("player")
            if isinstance(effect, dict) and (_combat_has_buff_type([effect], "restraint") or _combat_has_buff_type([effect], "psychosis"))
        ]

    def _player_active_status_effects(self) -> list[dict[str, Any]]:
        return [effect for effect in self._actor_status_effects("player") if isinstance(effect, dict)]

    def _player_skill_block_effects(self) -> list[dict[str, Any]]:
        return [effect for effect in self._player_active_status_effects() if _combat_status_blocks_skill([effect])]

    def _player_silence_block_effects(self) -> list[dict[str, Any]]:
        return []

    def _player_incapacitated_action_block(
        self,
        action: str,
        *,
        encounter: dict[str, Any] | None = None,
        for_movement: bool = False,
        combat_intent_confirmed: bool = False,
    ) -> str:
        if for_movement:
            return ""
        if _is_skill_action(action) and self._player_skill_block_effects():
            return "skill"
        if _status_effect_action_uses_mouth(action) and self._player_silence_block_effects():
            return "silence"
        if _is_escape_action(action):
            return "escape" if _combat_status_blocks_escape(self._actor_status_effects("player", encounter)) else ""
        if _is_attack_action(action) or _is_aggressive_player_action(action):
            if encounter is None and not combat_intent_confirmed:
                return ""
            return "attack" if _combat_status_blocks_attack(self._actor_status_effects("player", encounter)) else ""
        return ""

    def _player_incapacitated_message(self, reason: str = "") -> str:
        names = _dedupe_strs(
            str(effect.get("name") or INCAPACITATED_STATUS_NAME)
            for effect in self._player_incapacitated_effects()
            if isinstance(effect, dict)
        )
        label = " / ".join(names) if names else INCAPACITATED_STATUS_NAME
        if reason == "movement":
            return f"{label}のため、今は移動できない。まずその原因を解く必要がある。"
        if reason == "escape":
            return f"{label}のため、今は逃走できない。"
        if reason == "attack":
            return f"{label}のため、今は攻撃的な行動を取れない。"
        if reason == "skill":
            names = _dedupe_strs(str(effect.get("name") or "精神異常") for effect in self._player_skill_block_effects())
            skill_label = " / ".join(names) if names else "精神異常"
            return f"{skill_label}のため、今はスキルを使えない。"
        if reason == "silence":
            names = _dedupe_strs(str(effect.get("name") or "沈黙") for effect in self._player_silence_block_effects())
            silence_label = " / ".join(names) if names else "沈黙"
            return f"{silence_label}のため、今は声や口を使う行動ができない。"
        return f"{label}のため、今はその行動を取れない。"

    def _resolve_blocked_player_action(
        self,
        action: str,
        input_type: str,
        reason: str,
        *,
        encounter: dict[str, Any] | None = None,
    ) -> str:
        location = str((encounter or {}).get("location") or self.state.current_location)
        choices = self._encounter_choices(encounter) if encounter else self.state.choices
        self.state.flags["screen_mode"] = "battle" if encounter else self.state.flags.get("screen_mode", "exploration")
        narration = self._player_incapacitated_message(reason)
        self._append_turn(action, narration, location, choices, input_type=input_type)
        self.state.world_data.history.append(
            {
                "manager": "player_action_guard",
                "action": action,
                "input_type": input_type,
                "reason": reason,
                "status_effects": self._player_incapacitated_effects(),
            }
        )
        self.save_game()
        return self.state.log_text(16)

    def _sync_actor_status_effects(
        self,
        target: str,
        status_list: list[dict[str, Any]],
        encounter: dict[str, Any] | None = None,
    ) -> None:
        if target == "player":
            self.state.status_effects = status_list
            player = self.player_character()
            if player:
                player.status_effects = list(status_list)
            if self.state.party and isinstance(self.state.party[0], dict):
                self.state.party[0]["status_effects"] = list(status_list)
            if encounter is not None:
                encounter["player_status_effects"] = list(status_list)
            return

        opponent = self._encounter_opponent(encounter or {})
        if isinstance(opponent, Character):
            opponent.status_effects = list(status_list)
        if encounter is not None:
            encounter["opponent_status_effects"] = list(status_list)

    def _sync_encounter_status_effects(self, encounter: dict[str, Any]) -> None:
        self._sync_actor_status_effects("player", self._actor_status_effects("player", encounter), encounter)
        self._sync_actor_status_effects("opponent", self._actor_status_effects("opponent", encounter), encounter)

    def _apply_response_implied_statuses(
        self,
        encounter: dict[str, Any],
        response: dict[str, Any],
        target: str,
        *,
        context_actor: Character | str | None = None,
        action_context: str = "",
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        effects = response.get("status_effects") or response.get("conditions")
        if effects:
            applied.extend(
                self._add_actor_status_effects(
                    target,
                    effects,
                    encounter=encounter,
                    source="response",
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response,
                )
            )
        player_effects = response.get("player_status_effects") or response.get("add_player_status_effects")
        if player_effects:
            applied.extend(
                self._add_actor_status_effects(
                    "player",
                    player_effects,
                    encounter=encounter,
                    source="response",
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response,
                )
            )
        opponent_effects = response.get("opponent_status_effects") or response.get("add_opponent_status_effects")
        if opponent_effects:
            applied.extend(
                self._add_actor_status_effects(
                    "opponent",
                    opponent_effects,
                    encounter=encounter,
                    source="response",
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response,
                )
            )
        text = json.dumps(_strip_response_metadata(response), ensure_ascii=False)
        effect = _status_effect_from_status_text(text)
        if effect:
            applied.extend(
                self._add_actor_status_effects(
                    target,
                    effect,
                    encounter=encounter,
                    source="response_text",
                    context_actor=context_actor,
                    action_context=action_context,
                    response_context=response,
                )
            )
        return applied

    def _apply_response_status_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_target: str = "player",
        context_character: Character | None = None,
    ) -> list[str]:
        applied: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        for target, value in self._response_status_effect_entries(response, default_target, context_character):
            applied.extend(self._add_status_effects_to_target(target, value, source=source))
        for target, value in self._response_status_effect_removals(response, default_target, context_character):
            removed.extend(self._remove_status_effects_from_target(target, value, source=source))
        if not applied and not removed:
            return []
        record = {
            "source": source,
            "location": self.state.current_location,
            "day": self.state.day,
            "effects": applied,
            "removed_effects": removed,
        }
        self.state.world_data.extra.setdefault("status_effect_log", []).append(record)
        return [_status_effect_applied_line(item) for item in applied] + [_status_effect_removed_line(item) for item in removed]

    def remove_status_effect(
        self,
        target: str,
        status: Any,
        *,
        source: str = "manual",
        reason: str = "",
        treatment: str = "",
        save_game: bool = True,
    ) -> list[str]:
        removed = self._remove_status_effects_from_target(target, status, source=source, reason=reason, treatment=treatment)
        if not removed:
            return []
        record = {
            "source": source,
            "location": self.state.current_location,
            "day": self.state.day,
            "effects": [],
            "removed_effects": removed,
            "reason": reason,
            "treatment": treatment,
        }
        self.state.world_data.extra.setdefault("status_effect_log", []).append(record)
        lines = [_status_effect_removed_line(item) for item in removed]
        self.state.display_log.extend(lines)
        if save_game:
            self.save_game()
        return lines

    def treat_status_effect(
        self,
        target: str,
        status: Any,
        *,
        treatment: str = "",
        source: str = "treatment",
        save_game: bool = True,
    ) -> list[str]:
        return self.remove_status_effect(target, status, source=source, reason="treatment", treatment=treatment, save_game=save_game)

    def _response_status_effect_entries(
        self,
        response: dict[str, Any],
        default_target: str,
        context_character: Character | None,
    ) -> list[tuple[str, Any]]:
        context_target = context_character.name if context_character else default_target
        entries: list[tuple[str, Any]] = []
        for key in ("player_status_effect", "player_status_effects", "add_player_status_effect", "add_player_status_effects"):
            if response.get(key):
                entries.append(("player", response.get(key)))
        for key in ("character_status_effect", "character_status_effects", "npc_status_effect", "npc_status_effects"):
            if response.get(key):
                entries.extend(self._targeted_status_entries(response.get(key), context_target, context_target))
        for key in ("monster_status_effect", "monster_status_effects", "enemy_status_effect", "enemy_status_effects"):
            if response.get(key):
                entries.extend(self._targeted_status_entries(response.get(key), "opponent", context_target))
        for key in ("status_effects", "conditions", "long_term_statuses", "persistent_statuses", "character_status_updates"):
            if response.get(key):
                entries.extend(self._targeted_status_entries(response.get(key), default_target, context_target))
        return entries

    def _response_status_effect_removals(
        self,
        response: dict[str, Any],
        default_target: str,
        context_character: Character | None,
    ) -> list[tuple[str, Any]]:
        context_target = context_character.name if context_character else default_target
        entries: list[tuple[str, Any]] = []
        for key in (
            "remove_player_status_effect",
            "remove_player_status_effects",
            "cure_player_status_effects",
            "treated_player_status_effects",
            "resolved_player_status_effects",
        ):
            if response.get(key):
                entries.append(("player", response.get(key)))
        for key in (
            "remove_character_status_effect",
            "remove_character_status_effects",
            "remove_npc_status_effect",
            "remove_npc_status_effects",
            "cure_npc_status_effects",
            "cure_character_status_effects",
            "treated_npc_status_effects",
            "treated_character_status_effects",
            "resolved_npc_status_effects",
            "resolved_character_status_effects",
        ):
            if response.get(key):
                entries.extend(self._targeted_status_entries(response.get(key), context_target, context_target))
        for key in ("remove_status_effects", "cure_status_effects", "treated_status_effects", "resolved_status_effects"):
            if response.get(key):
                entries.extend(self._targeted_status_entries(response.get(key), default_target, context_target))
        return entries

    def _targeted_status_entries(self, value: Any, default_target: str, context_target: str) -> list[tuple[str, Any]]:
        if isinstance(value, dict):
            if any(key in value for key in ("name", "title", "label", "status", "condition", "effect", "description")):
                return [(_global_status_target(value, default_target, context_target), value)]
            entries: list[tuple[str, Any]] = []
            group_keys = {
                "player": "player",
                "players": "player",
                "pc": "player",
                "protagonist": "player",
                "self": default_target,
                "character": context_target,
                "characters": context_target,
                "npc": context_target,
                "npcs": context_target,
                "speaker": context_target,
                "monster": "opponent",
                "monsters": "opponent",
                "enemy": "opponent",
                "enemies": "opponent",
            }
            for key, item in value.items():
                key_text = str(key)
                target = group_keys.get(key_text.lower(), key_text)
                if item:
                    entries.append((target, item))
            return entries
        entries = []
        for item in _status_effect_items(value):
            target = _global_status_target(item, default_target, context_target)
            entries.append((target, item))
        return entries

    def _add_status_effects_to_target(self, target: str, value: Any, *, source: str) -> list[dict[str, Any]]:
        resolved = self._resolve_status_target(target)
        if not resolved:
            return []
        kind, name, status_list, label = resolved
        effects = [_normalise_status_effect(item, source=source) for item in _status_effect_items(value)]
        effects = [self._enrich_persistent_status_effect(effect) for effect in effects if effect]
        if kind == "player":
            effects = [effect for effect in effects if not self._player_is_immune_to_status(effect)]
        if not effects:
            return []
        for effect in effects:
            _merge_status_effect(status_list, effect)
        self._sync_status_target(kind, name, status_list)
        return [
            {
                "target_type": kind,
                "target": name,
                "label": label,
                "effect": effect,
            }
            for effect in effects
        ]

    def _remove_status_effects_from_target(
        self,
        target: str,
        value: Any,
        *,
        source: str = "",
        reason: str = "",
        treatment: str = "",
    ) -> list[dict[str, Any]]:
        resolved = self._resolve_status_target(target)
        if not resolved:
            return []
        kind, name, status_list, _label = resolved
        remove_effects = [_normalise_status_effect(item) for item in _status_effect_items(value)]
        remove_keys = {_status_effect_merge_key(effect) for effect in remove_effects if effect.get("name")}
        remove_ids = {_status_effect_id(effect) for effect in remove_effects}
        remove_ids.discard("")
        if not remove_ids and not remove_keys:
            return []
        removed = [
            effect
            for effect in status_list
            if _status_effect_merge_key(effect) in remove_keys or (not remove_keys and _status_effect_id(effect) in remove_ids)
        ]
        if not removed:
            return []
        kept = [
            effect
            for effect in status_list
            if _status_effect_merge_key(effect) not in remove_keys and (remove_keys or _status_effect_id(effect) not in remove_ids)
        ]
        self._sync_status_target(kind, name, kept)
        return [
            {
                "target_type": kind,
                "target": name,
                "label": _label,
                "effect": effect,
                "source": source,
                "reason": reason,
                "treatment": treatment,
            }
            for effect in removed
        ]

    def _resolve_status_target(self, target: str) -> tuple[str, str, list[dict[str, Any]], str] | None:
        text = str(target or "").strip()
        lowered = text.lower()
        if lowered in {"", "player", "pc", "hero", "protagonist", "you", "あなた", "プレイヤー"} or text == self.state.player_name:
            player = self.player_character()
            if player and player.status_effects and not self.state.status_effects:
                self.state.status_effects = list(player.status_effects)
            return ("player", self.state.player_name, self.state.status_effects, self.state.player_name or "Player")
        character = self.state.world_data.character(text)
        if character:
            return ("character", character.name, character.status_effects, character.name)
        if lowered in {"monster", "enemy", "opponent"}:
            active = self._active_encounter()
            if active:
                opponent = self._encounter_opponent(active)
                if isinstance(opponent, Character):
                    return ("character", opponent.name, opponent.status_effects, opponent.name)
        return None

    def _sync_status_target(self, kind: str, name: str, status_list: list[dict[str, Any]]) -> None:
        if kind == "player":
            self.state.status_effects = list(status_list)
            player = self.player_character()
            if player:
                player.status_effects = list(status_list)
            if self.state.party and isinstance(self.state.party[0], dict):
                self.state.party[0]["status_effects"] = list(status_list)
            return
        if kind == "character":
            character = self.state.world_data.character(name)
            if not character:
                return
            character.status_effects = list(status_list)
            if character.flags.get("is_player") or character.uuid == self.state.player_uuid:
                self._sync_status_target("player", name, status_list)
            return

    def _enrich_persistent_status_effect(self, effect: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(effect)
        enriched.setdefault("started_day", self.state.day)
        enriched.setdefault("started_location", self.state.current_location)
        if _safe_int(enriched.get("duration"), 0) == -1:
            enriched.setdefault("scope", "character")
        return enriched

    def _tick_encounter_status_effects(self, encounter: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        opponents = self._encounter_opponents(encounter)
        player_status_list = self._actor_status_effects("player", encounter)
        if player_status_list:
            updated, hp_delta, sp_delta, tick_lines = _combat_tick_buffs(player_status_list, self.state.player_name or "Player", combat_turn=True)
            lines.extend(tick_lines)
            if hp_delta:
                event = self._apply_player_hp_delta(hp_delta, source="status_tick", reason="status", encounter=encounter)
                if event.get("line"):
                    lines.append(str(event["line"]))
            if sp_delta:
                event = self._apply_player_sp_delta(sp_delta, source="status_tick", reason="status", encounter=encounter)
                if event.get("line"):
                    lines.append(str(event["line"]))
            self._sync_actor_status_effects("player", updated, encounter)
        active_uuid = str(encounter.get("active_opponent_uuid") or encounter.get("opponent_uuid") or "")
        active_name = str(encounter.get("active_opponent_name") or encounter.get("opponent_name") or "")
        for opponent in opponents:
            self._set_encounter_active_opponent(encounter, opponent)
            opponent_status_list = self._actor_status_effects("opponent", encounter)
            if not opponent_status_list:
                continue
            updated, hp_delta, sp_delta, tick_lines = _combat_tick_buffs(opponent_status_list, opponent.name, combat_turn=True)
            lines.extend(tick_lines)
            if hp_delta:
                event = self._apply_opponent_hp_delta(encounter, hp_delta, source="status_tick", reason="status")
                lines.extend(str(line) for line in event.get("lines", []) if line)
            if sp_delta:
                max_sp = max(0, _safe_int(opponent.max_sp, 0))
                old_sp = max(0, _safe_int(opponent.current_sp, 0))
                opponent.current_sp = max(0, min(max_sp if max_sp > 0 else old_sp + sp_delta, old_sp + sp_delta))
                opponent.extra["current_sp"] = opponent.current_sp
            self._sync_actor_status_effects("opponent", updated, encounter)
        restore = self._character_from_reference(active_name, active_uuid)
        if restore:
            self._set_encounter_active_opponent(encounter, restore)
        self._sync_player_battle_state(encounter)
        return lines

    def _apply_encounter_outcome(self, encounter: dict[str, Any]) -> dict[str, Any]:
        self._sync_player_battle_state(encounter)
        player_hp = int(encounter.get("player_hp") or 0)
        opponent_hp = int(encounter.get("opponent_hp") or 0)
        if player_hp > 0:
            opponent = self._encounter_opponent(encounter)
            if isinstance(opponent, Character):
                self._sync_encounter_opponent_entry(encounter, opponent)
                opponent_hp = max(0, _safe_int(opponent.current_hp, 0))
            living = self._living_encounter_opponents(encounter)
            if opponent_hp > 0 and not living and self._encounter_opponents(encounter):
                encounter["status"] = "ended"
                return {
                    "ended": True,
                    "opponent_state": str(encounter.get("opponent_status") or "left"),
                    "narration": "相手は戦闘を続けられる状態ではなくなった。戦闘は終了した。",
                }
            if opponent_hp <= 0:
                defeated_name = str((opponent.name if isinstance(opponent, Character) else "") or encounter.get("opponent_name") or "Opponent")
                defeated_uuid = str((opponent.uuid if isinstance(opponent, Character) else "") or encounter.get("opponent_uuid") or "")
                encounter["opponent_status"] = "defeated"
                self._add_actor_status_effects(
                    "opponent",
                    {"name": "defeated", "id": "defeated", "duration": 0},
                    encounter=encounter,
                    source="defeated",
                )
                if isinstance(opponent, Character):
                    self._mark_character_dead(opponent, source="encounter_defeated")
                    self._sync_encounter_opponent_entry(encounter, opponent)
                living = self._living_encounter_opponents(encounter)
                if living:
                    self._set_encounter_active_opponent(encounter, living[0])
                    return {
                        "ended": False,
                        "opponent_defeated": True,
                        "opponent_state": "dead",
                        "defeated_opponent_name": defeated_name,
                        "defeated_opponent_uuid": defeated_uuid,
                        "narration": f"{defeated_name} has fallen. The battle continues.",
                    }
                encounter["status"] = "ended"
                return {
                    "ended": True,
                    "opponent_defeated": True,
                    "opponent_state": "dead",
                    "defeated_opponent_name": defeated_name,
                    "defeated_opponent_uuid": defeated_uuid,
                    "narration": f"{defeated_name} has fallen. The battle is over.",
                }
        if player_hp <= 0:
            encounter["status"] = "ended"
            encounter["player_status"] = "dead"
            self._add_actor_status_effects("player", {"name": "死亡", "id": "dead", "duration": 0}, encounter=encounter, source="game_over")
            player = self.player_character()
            if player:
                player.state = "dead"
                player.flags["state"] = "dead"
            if self.state.party and isinstance(self.state.party[0], dict):
                self.state.party[0]["state"] = "dead"
            self.state.flags["game_over"] = {
                "reason": "player_hp_zero",
                "location": self.state.current_location,
                "turn": int(encounter.get("turn") or 0),
            }
            self.state.choices = _game_over_choices()
            return {
                "ended": True,
                "game_over": True,
                "narration": "あなたは力尽きた。視界が暗く沈み、冒険はここで終わった。",
            }
        if opponent_hp <= 0:
            encounter["status"] = "ended"
            encounter["opponent_status"] = "defeated"
            self._add_actor_status_effects("opponent", {"name": "戦闘不能", "id": "defeated", "duration": 0}, encounter=encounter, source="defeated")
            self._update_encounter_presence(encounter, "dead")
            return {
                "ended": True,
                "opponent_state": "dead",
                "narration": f"{encounter.get('opponent_name') or '相手'}は戦闘不能になった。",
            }
        return {"ended": False}

    def _sync_player_battle_state(self, encounter: dict[str, Any]) -> None:
        max_hp = max(1, int(encounter.get("player_max_hp") or self._player_max_hp()))
        hp = max(0, min(max_hp, int(encounter.get("player_hp") or 0)))
        max_sp = max(1, int(encounter.get("player_max_sp") or self._player_max_sp()))
        sp = max(0, min(max_sp, int(encounter.get("player_sp") or self._player_current_sp(max_sp))))
        encounter["player_hp"] = hp
        encounter["player_max_hp"] = max_hp
        encounter["player_sp"] = sp
        encounter["player_max_sp"] = max_sp
        encounter["player_hunger"] = self._player_hunger()
        encounter["player_max_hunger"] = PLAYER_MAX_HUNGER
        combat_stats = self.player_combat_stats()
        encounter["player_attack"] = combat_stats["attack"]
        encounter["player_attack_bonus"] = combat_stats["attack_bonus"]
        encounter["player_defense"] = combat_stats["defense"]
        encounter["player_defense_bonus"] = combat_stats["defense_bonus"]
        encounter["player_equipment"] = _compact_value(self.player_equipment_summary(), max_chars=900)
        self.state.flags["player_hp"] = hp
        self.state.flags["player_max_hp"] = max_hp
        self.state.flags["player_sp"] = sp
        self.state.flags["player_max_sp"] = max_sp
        self.state.extra["current_hp"] = hp
        self.state.extra["max_hp"] = max_hp
        self.state.extra["current_sp"] = sp
        self.state.extra["max_sp"] = max_sp
        player = self.player_character()
        if player:
            player.current_hp = hp
            player.max_hp = max_hp
            player.current_sp = sp
            player.max_sp = max_sp
            player.extra["current_hp"] = hp
            player.extra["max_hp"] = max_hp
            player.extra["current_sp"] = sp
            player.extra["max_sp"] = max_sp
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["hp"] = f"{hp}/{max_hp}"
            self.state.party[0]["sp"] = f"{sp}/{max_sp}"
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra["current_hp"] = hp
                extra["max_hp"] = max_hp
                extra["current_sp"] = sp
                extra["max_sp"] = max_sp

    def apply_player_hp_delta(
        self,
        delta: Any,
        *,
        source: str = "event",
        reason: str = "",
        encounter: dict[str, Any] | None = None,
        save_game: bool = True,
    ) -> dict[str, Any]:
        event = self._apply_player_hp_delta(delta, source=source, reason=reason, encounter=encounter)
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _apply_response_hp_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        lines: list[str] = []
        absolute_hp = self._response_player_hp_absolute(response)
        if absolute_hp is not None:
            max_hp = max(1, self._hp_number((encounter or {}).get("player_max_hp"), self._player_max_hp()))
            current_hp = self._player_current_hp(max_hp)
            if encounter is not None:
                current_hp = max(0, min(max_hp, self._hp_number(encounter.get("player_hp"), current_hp)))
            event = self._apply_player_hp_delta(
                absolute_hp - current_hp,
                source=source,
                reason=self._response_hp_reason(response),
                encounter=encounter,
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        delta = self._response_player_hp_delta(response)
        if delta:
            event = self._apply_player_hp_delta(
                delta,
                source=source,
                reason=self._response_hp_reason(response),
                encounter=encounter,
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        return lines

    def _apply_player_hp_delta(
        self,
        delta: Any,
        *,
        source: str,
        reason: str = "",
        encounter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        requested_delta = self._hp_number(delta, 0)
        if requested_delta == 0:
            return {"changed": False, "requested_delta": 0}
        target_encounter = encounter or self._active_encounter()
        max_hp = max(1, self._hp_number((target_encounter or {}).get("player_max_hp"), self._player_max_hp()))
        old_hp = self._player_current_hp(max_hp)
        if target_encounter is not None:
            old_hp = max(0, min(max_hp, self._hp_number(target_encounter.get("player_hp"), old_hp)))
        new_hp = max(0, min(max_hp, old_hp + requested_delta))
        actual_delta = new_hp - old_hp
        if actual_delta == 0:
            return {
                "changed": False,
                "requested_delta": requested_delta,
                "old_hp": old_hp,
                "new_hp": new_hp,
                "max_hp": max_hp,
            }
        self._set_player_hp(new_hp, max_hp=max_hp, encounter=target_encounter)
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        label = self.state.player_name or "Player"
        reason_text = f" {reason}" if reason else ""
        line = f"> [HP] {label}: {old_hp}/{max_hp} -> {new_hp}/{max_hp} ({sign}){reason_text}"
        event = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "day": self.state.day,
            "requested_delta": requested_delta,
            "actual_delta": actual_delta,
            "old_hp": old_hp,
            "new_hp": new_hp,
            "max_hp": max_hp,
            "line": line,
            "changed": True,
        }
        self.state.world_data.extra.setdefault("hp_events", []).append(dict(event))
        return event

    def _set_player_hp(
        self,
        hp: Any,
        *,
        max_hp: int | None = None,
        encounter: dict[str, Any] | None = None,
    ) -> None:
        equipment_bonus = _safe_int(self.player_equipment_summary().get("max_hp"), 0)
        if max_hp is None:
            base_max_hp = self._player_base_max_hp()
        else:
            candidate = max(1, int(max_hp))
            base_max_hp = max(1, candidate - equipment_bonus) if candidate == self._player_max_hp() else candidate
        resolved_max_hp = max(1, base_max_hp + equipment_bonus)
        resolved_hp = max(0, min(resolved_max_hp, self._hp_number(hp, resolved_max_hp)))
        if encounter is not None:
            encounter["player_hp"] = resolved_hp
            encounter["player_max_hp"] = resolved_max_hp
            self._sync_player_battle_state(encounter)
            return
        self.state.flags["player_hp"] = resolved_hp
        self.state.flags["player_max_hp"] = resolved_max_hp
        self.state.extra["current_hp"] = resolved_hp
        self.state.extra["max_hp"] = resolved_max_hp
        self.state.extra["base_max_hp"] = base_max_hp
        player = self.player_character()
        if player:
            player.current_hp = resolved_hp
            player.max_hp = resolved_max_hp
            player.extra["current_hp"] = resolved_hp
            player.extra["max_hp"] = resolved_max_hp
            player.extra["base_max_hp"] = base_max_hp
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["current_hp"] = resolved_hp
            self.state.party[0]["max_hp"] = resolved_max_hp
            self.state.party[0]["hp"] = f"{resolved_hp}/{resolved_max_hp}"
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra["current_hp"] = resolved_hp
                extra["max_hp"] = resolved_max_hp
                extra["base_max_hp"] = base_max_hp

    def _response_player_hp_delta(self, payload: Any) -> int:
        if isinstance(payload, list):
            return sum(self._response_player_hp_delta(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        total = 0
        effect_type = str(payload.get("type") or payload.get("name") or payload.get("kind") or "").strip().lower()
        value = self._hp_number(
            payload.get("value", payload.get("amount", payload.get("points", payload.get("hp", 0)))),
            0,
        )
        if effect_type in {"heal", "healing", "restore", "restore_hp", "recover", "recover_hp", "hp_restore", "cure", "treatment"}:
            total += abs(value)
        elif effect_type in {"damage", "hp_damage", "harm", "poison"}:
            total -= abs(value)
        for key, value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in {"player_hp_delta", "hp_delta", "health_delta"}:
                total += self._hp_number(value, 0)
            elif key_text in {"heal_hp", "healing", "restore_hp", "recover_hp", "hp_restore", "player_heal_hp", "player_recover_hp"}:
                total += abs(self._hp_number(value, 0))
            elif key_text in {"damage_hp", "hp_damage", "player_damage_hp", "harm_hp"}:
                total -= abs(self._hp_number(value, 0))
            elif key_text in {
                "hp_effect",
                "hp_effects",
                "player_hp_effect",
                "player_hp_effects",
                "health_effect",
                "health_effects",
                "recovery_effect",
                "recovery_effects",
            }:
                total += self._response_player_hp_delta(value)
        return total

    def _response_player_hp_absolute(self, response: dict[str, Any]) -> int | None:
        for key in ("player_hp", "current_hp"):
            if key in response:
                return self._hp_number(response.get(key), 0)
        return None

    def _response_hp_reason(self, response: dict[str, Any]) -> str:
        reason = response.get("hp_reason") or response.get("healing_reason") or response.get("reason") or response.get("event")
        if isinstance(reason, (dict, list)):
            return ""
        return _short_text(str(reason or "").strip(), 40)

    def apply_player_sp_delta(
        self,
        delta: Any,
        *,
        source: str = "event",
        reason: str = "",
        encounter: dict[str, Any] | None = None,
        save_game: bool = True,
    ) -> dict[str, Any]:
        event = self._apply_player_sp_delta(delta, source=source, reason=reason, encounter=encounter)
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _apply_response_sp_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        if not isinstance(response, dict):
            return []
        lines: list[str] = []
        absolute_sp = self._response_player_sp_absolute(response)
        if absolute_sp is not None:
            max_sp = max(1, self._hp_number((encounter or {}).get("player_max_sp"), self._player_max_sp()))
            current_sp = self._player_current_sp(max_sp)
            if encounter is not None:
                current_sp = max(0, min(max_sp, self._hp_number(encounter.get("player_sp"), current_sp)))
            event = self._apply_player_sp_delta(
                absolute_sp - current_sp,
                source=source,
                reason=self._response_sp_reason(response),
                encounter=encounter,
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        delta = self._response_player_sp_delta(response)
        if delta:
            event = self._apply_player_sp_delta(
                delta,
                source=source,
                reason=self._response_sp_reason(response),
                encounter=encounter,
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        return lines

    def _apply_player_sp_delta(
        self,
        delta: Any,
        *,
        source: str,
        reason: str = "",
        encounter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        requested_delta = self._hp_number(delta, 0)
        if requested_delta == 0:
            return {"changed": False, "requested_delta": 0}
        target_encounter = encounter or self._active_encounter()
        max_sp = max(1, self._hp_number((target_encounter or {}).get("player_max_sp"), self._player_max_sp()))
        old_sp = self._player_current_sp(max_sp)
        if target_encounter is not None:
            old_sp = max(0, min(max_sp, self._hp_number(target_encounter.get("player_sp"), old_sp)))
        new_sp = max(0, min(max_sp, old_sp + requested_delta))
        actual_delta = new_sp - old_sp
        if actual_delta == 0:
            return {
                "changed": False,
                "requested_delta": requested_delta,
                "old_sp": old_sp,
                "new_sp": new_sp,
                "max_sp": max_sp,
            }
        self._set_player_sp(new_sp, max_sp=max_sp, encounter=target_encounter)
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        label = self.state.player_name or "Player"
        reason_text = f" {reason}" if reason else ""
        line = f"> [SP] {label}: {old_sp}/{max_sp} -> {new_sp}/{max_sp} ({sign}){reason_text}"
        event = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "day": self.state.day,
            "requested_delta": requested_delta,
            "actual_delta": actual_delta,
            "old_sp": old_sp,
            "new_sp": new_sp,
            "max_sp": max_sp,
            "line": line,
            "changed": True,
        }
        self.state.world_data.extra.setdefault("sp_events", []).append(dict(event))
        return event

    def _set_player_sp(
        self,
        sp: Any,
        *,
        max_sp: int | None = None,
        encounter: dict[str, Any] | None = None,
    ) -> None:
        equipment_bonus = _safe_int(self.player_equipment_summary().get("max_sp"), 0)
        if max_sp is None:
            base_max_sp = self._player_base_max_sp()
        else:
            candidate = max(1, int(max_sp))
            base_max_sp = max(1, candidate - equipment_bonus) if candidate == self._player_max_sp() else candidate
        resolved_max_sp = max(1, base_max_sp + equipment_bonus)
        resolved_sp = max(0, min(resolved_max_sp, self._hp_number(sp, resolved_max_sp)))
        if encounter is not None:
            encounter["player_sp"] = resolved_sp
            encounter["player_max_sp"] = resolved_max_sp
            self._sync_player_battle_state(encounter)
            return
        self.state.flags["player_sp"] = resolved_sp
        self.state.flags["player_max_sp"] = resolved_max_sp
        self.state.extra["current_sp"] = resolved_sp
        self.state.extra["max_sp"] = resolved_max_sp
        self.state.extra["base_max_sp"] = base_max_sp
        player = self.player_character()
        if player:
            player.current_sp = resolved_sp
            player.max_sp = resolved_max_sp
            player.extra["current_sp"] = resolved_sp
            player.extra["max_sp"] = resolved_max_sp
            player.extra["base_max_sp"] = base_max_sp
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["current_sp"] = resolved_sp
            self.state.party[0]["max_sp"] = resolved_max_sp
            self.state.party[0]["sp"] = f"{resolved_sp}/{resolved_max_sp}"
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra["current_sp"] = resolved_sp
                extra["max_sp"] = resolved_max_sp
                extra["base_max_sp"] = base_max_sp

    def _response_player_sp_delta(self, payload: Any) -> int:
        if isinstance(payload, list):
            return sum(self._response_player_sp_delta(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        total = 0
        effect_type = str(payload.get("type") or payload.get("name") or payload.get("kind") or "").strip().lower()
        value = self._hp_number(
            payload.get("value", payload.get("amount", payload.get("points", payload.get("sp", 0)))),
            0,
        )
        if effect_type in {"restore_sp", "recover_sp", "sp_restore", "sp_recovery", "mana", "mp", "focus", "will"}:
            total += abs(value)
        elif effect_type in {"consume_sp", "sp_cost", "sp_damage", "drain_sp", "fatigue"}:
            total -= abs(value)
        for key, value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in {"player_sp_delta", "sp_delta", "mana_delta", "mp_delta"}:
                total += self._hp_number(value, 0)
            elif key_text in {"restore_sp", "recover_sp", "sp_restore", "sp_recovery", "player_sp_restore"}:
                total += abs(self._hp_number(value, 0))
            elif key_text in {"consume_sp", "sp_cost", "sp_damage", "drain_sp"}:
                total -= abs(self._hp_number(value, 0))
            elif key_text in {
                "sp_effect",
                "sp_effects",
                "player_sp_effect",
                "player_sp_effects",
                "mana_effect",
                "mana_effects",
            }:
                total += self._response_player_sp_delta(value)
        return total

    def _response_player_sp_absolute(self, response: dict[str, Any]) -> int | None:
        for key in ("player_sp", "current_sp"):
            if key in response:
                return self._hp_number(response.get(key), 0)
        return None

    def _response_sp_reason(self, response: dict[str, Any]) -> str:
        reason = response.get("sp_reason") or response.get("resource_reason") or response.get("reason") or response.get("event")
        if isinstance(reason, (dict, list)):
            return ""
        return _short_text(str(reason or "").strip(), 40)

    def player_hunger_status(self) -> tuple[int, int]:
        return self._player_hunger(), PLAYER_MAX_HUNGER

    def apply_player_hunger_delta(
        self,
        delta: Any,
        *,
        source: str = "event",
        reason: str = "",
        save_game: bool = True,
    ) -> dict[str, Any]:
        event = self._apply_player_hunger_delta(delta, source=source, reason=reason)
        if save_game and event.get("changed"):
            self.save_game()
        return event

    def _apply_response_hunger_effects(self, response: dict[str, Any], source: str) -> list[str]:
        if not isinstance(response, dict):
            return []
        lines: list[str] = []
        absolute_hunger = self._response_player_hunger_absolute(response)
        if absolute_hunger is not None:
            event = self._apply_player_hunger_delta(
                absolute_hunger - self._player_hunger(),
                source=source,
                reason=self._response_hunger_reason(response),
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        delta = self._response_player_hunger_delta(response)
        if delta:
            event = self._apply_player_hunger_delta(
                delta,
                source=source,
                reason=self._response_hunger_reason(response),
            )
            if event.get("line"):
                lines.append(str(event["line"]))
        return lines

    def _apply_player_hunger_delta(self, delta: Any, *, source: str, reason: str = "") -> dict[str, Any]:
        requested_delta = self._hp_number(delta, 0)
        if requested_delta == 0:
            return {"changed": False, "requested_delta": 0}
        old_hunger = self._player_hunger()
        new_hunger = max(0, min(PLAYER_MAX_HUNGER, old_hunger + requested_delta))
        actual_delta = new_hunger - old_hunger
        if actual_delta == 0:
            return {
                "changed": False,
                "requested_delta": requested_delta,
                "old_hunger": old_hunger,
                "new_hunger": new_hunger,
                "max_hunger": PLAYER_MAX_HUNGER,
            }
        self._set_player_hunger(new_hunger)
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        reason_text = f" {reason}" if reason else ""
        line = f"> [空腹度] {old_hunger}/{PLAYER_MAX_HUNGER} -> {new_hunger}/{PLAYER_MAX_HUNGER} ({sign}){reason_text}"
        event = {
            "source": source,
            "reason": reason,
            "location": self.state.current_location,
            "day": self.state.day,
            "requested_delta": requested_delta,
            "actual_delta": actual_delta,
            "old_hunger": old_hunger,
            "new_hunger": new_hunger,
            "max_hunger": PLAYER_MAX_HUNGER,
            "line": line,
            "changed": True,
        }
        self.state.world_data.extra.setdefault("hunger_events", []).append(dict(event))
        return event

    def _player_hunger(self) -> int:
        for value in (
            getattr(self.state, "hunger", None),
            self.state.flags.get("player_hunger"),
            self.state.extra.get("hunger"),
            self.state.extra.get("player_hunger"),
        ):
            if value is not None:
                hunger = max(0, min(PLAYER_MAX_HUNGER, self._hp_number(value, PLAYER_MAX_HUNGER)))
                self._set_player_hunger(hunger)
                return hunger
        self._set_player_hunger(PLAYER_MAX_HUNGER)
        return PLAYER_MAX_HUNGER

    def _set_player_hunger(self, hunger: Any) -> None:
        resolved = max(0, min(PLAYER_MAX_HUNGER, self._hp_number(hunger, PLAYER_MAX_HUNGER)))
        self.state.hunger = resolved
        self.state.flags["player_hunger"] = resolved
        self.state.flags["player_max_hunger"] = PLAYER_MAX_HUNGER
        self.state.extra["hunger"] = resolved
        self.state.extra["player_hunger"] = resolved
        self.state.extra["max_hunger"] = PLAYER_MAX_HUNGER
        self.state.extra["player_max_hunger"] = PLAYER_MAX_HUNGER
        player = self.player_character()
        if player:
            player.extra["hunger"] = resolved
            player.extra["max_hunger"] = PLAYER_MAX_HUNGER
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["hunger"] = f"{resolved}/{PLAYER_MAX_HUNGER}"
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra["hunger"] = resolved
                extra["max_hunger"] = PLAYER_MAX_HUNGER

    def _apply_starvation_turn_penalty(self) -> list[str]:
        if self._player_hunger() > 0:
            return []
        lines = ["> [空腹] 空腹で体力と気力が削られている。"]
        hp_event = self._apply_player_hp_delta(
            -PLAYER_STARVATION_HP_SP_DAMAGE,
            source="hunger",
            reason="空腹",
        )
        if hp_event.get("line"):
            lines.append(str(hp_event["line"]))
        sp_event = self._apply_player_sp_delta(
            -PLAYER_STARVATION_HP_SP_DAMAGE,
            source="hunger",
            reason="空腹",
        )
        if sp_event.get("line"):
            lines.append(str(sp_event["line"]))
        return lines

    def _response_player_hunger_delta(self, payload: Any) -> int:
        if isinstance(payload, list):
            return sum(self._response_player_hunger_delta(item) for item in payload)
        if not isinstance(payload, dict):
            return 0
        total = 0
        effect_type = str(payload.get("type") or payload.get("name") or payload.get("kind") or "").strip().lower()
        value = self._hp_number(
            payload.get("value", payload.get("amount", payload.get("points", payload.get("hunger", 0)))),
            0,
        )
        if effect_type in {"hunger", "hunger_heal", "restore_hunger", "recover_hunger", "meal", "food"}:
            total += abs(value)
        elif effect_type in {"hunger_damage", "starvation", "consume_hunger"}:
            total -= abs(value)
        for key, value in payload.items():
            key_text = str(key).strip().lower()
            if key_text in {"player_hunger_delta", "hunger_delta"}:
                total += self._hp_number(value, 0)
            elif key_text in {"restore_hunger", "recover_hunger", "hunger_restore", "hunger_heal", "meal_hunger"}:
                total += abs(self._hp_number(value, 0))
            elif key_text in {"consume_hunger", "hunger_damage", "starvation"}:
                total -= abs(self._hp_number(value, 0))
            elif key_text in {"hunger_effect", "hunger_effects", "player_hunger_effect", "player_hunger_effects"}:
                total += self._response_player_hunger_delta(value)
        return total

    def _response_player_hunger_absolute(self, response: dict[str, Any]) -> int | None:
        for key in ("player_hunger", "hunger", "current_hunger"):
            if key in response:
                return self._hp_number(response.get(key), PLAYER_MAX_HUNGER)
        return None

    def _response_hunger_reason(self, response: dict[str, Any]) -> str:
        reason = response.get("hunger_reason") or response.get("meal_reason") or response.get("reason") or response.get("event")
        if isinstance(reason, (dict, list)):
            return ""
        return _short_text(str(reason or "").strip(), 40)

    def _hp_number(self, value: Any, fallback: int = 0) -> int:
        if isinstance(value, bool):
            return fallback
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value or "").strip()
        if not text:
            return fallback
        match = re.search(r"[-+]?\d+", text)
        return int(match.group(0)) if match else fallback

    def _ensure_player_progress(self, character: Character | None = None) -> None:
        level = self._player_level(character)
        exp = self._player_exp(character)
        self._set_player_progress(level, exp, character=character)

    def _player_level(self, character: Character | None = None) -> int:
        player = character or self.player_character()
        candidates: list[Any] = [self.state.flags.get("player_level"), self.state.extra.get("level")]
        if player:
            candidates.extend([player.level, player.extra.get("level"), player.flags.get("level")])
        if self.state.party and isinstance(self.state.party[0], dict):
            party = self.state.party[0]
            extra = party.get("extra") if isinstance(party.get("extra"), dict) else {}
            candidates.extend([party.get("level"), party.get("lv"), extra.get("level")])
        for value in candidates:
            if value not in (None, ""):
                return max(1, min(PLAYER_MAX_LEVEL, _safe_int(value, 1)))
        return 1

    def _player_exp(self, character: Character | None = None) -> int:
        player = character or self.player_character()
        candidates: list[Any] = [self.state.flags.get("player_exp"), self.state.extra.get("exp")]
        if player:
            candidates.extend([player.extra.get("exp"), player.extra.get("experience"), player.flags.get("exp")])
        if self.state.party and isinstance(self.state.party[0], dict):
            party = self.state.party[0]
            extra = party.get("extra") if isinstance(party.get("extra"), dict) else {}
            candidates.extend([party.get("exp"), party.get("experience"), extra.get("exp")])
        for value in candidates:
            if value not in (None, ""):
                exp = max(0, _safe_int(value, 0))
                if self._player_level(character) >= PLAYER_MAX_LEVEL:
                    return min(exp, self._exp_to_next(PLAYER_MAX_LEVEL))
                return exp
        return 0

    def _exp_to_next(self, level: int) -> int:
        resolved_level = max(1, min(PLAYER_MAX_LEVEL, int(level or 1)))
        required = PLAYER_BASE_EXP_TO_NEXT
        for _ in range(1, resolved_level):
            required = min(PLAYER_MAX_EXP_TO_NEXT, int(required * 1.5))
        return max(1, min(PLAYER_MAX_EXP_TO_NEXT, int(required)))

    def _set_player_progress(self, level: int, exp: int, *, character: Character | None = None) -> None:
        resolved_level = max(1, min(PLAYER_MAX_LEVEL, int(level or 1)))
        resolved_exp = max(0, int(exp or 0))
        if resolved_level >= PLAYER_MAX_LEVEL:
            resolved_exp = min(resolved_exp, self._exp_to_next(PLAYER_MAX_LEVEL))
        self.state.flags["player_level"] = resolved_level
        self.state.flags["player_exp"] = resolved_exp
        self.state.extra["level"] = resolved_level
        self.state.extra["exp"] = resolved_exp
        self.state.extra["next_exp"] = self._exp_to_next(resolved_level)
        player = character or self.player_character()
        if player:
            player.level = resolved_level
            player.extra["level"] = resolved_level
            player.extra["exp"] = resolved_exp
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["level"] = resolved_level
            self.state.party[0]["exp"] = resolved_exp
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra["level"] = resolved_level
                extra["exp"] = resolved_exp

    def _sync_player_progress_to_character(self) -> None:
        self._set_player_progress(self._player_level(), self._player_exp())

    def _player_max_hp(self, character: Character | None = None) -> int:
        equipment_bonus = 0 if character is not None else _safe_int(self.player_equipment_summary().get("max_hp"), 0)
        base = self._player_base_max_hp(character)
        return max(1, base + equipment_bonus)

    def _player_base_max_hp(self, character: Character | None = None) -> int:
        player = character or self.player_character()
        if player:
            if player.max_hp:
                return max(1, _safe_int(player.max_hp, 10))
            for source in (player.extra, player.flags):
                if isinstance(source, dict):
                    value = source.get("base_max_hp") or source.get("original_max_hp") or source.get("max_hp")
                    if value:
                        return max(1, _safe_int(value, 10))
        state_value = self.state.extra.get("base_max_hp") or self.state.extra.get("max_hp")
        if state_value:
            return max(1, _safe_int(state_value, 10))
        return self._calculated_player_max_hp(character=player)

    def _calculated_player_max_hp(
        self,
        *,
        character: Character | None = None,
        level: int | None = None,
        attrs: dict[str, int] | None = None,
    ) -> int:
        resolved_attrs = attrs or self._player_attributes(character)
        resolved_level = level if level is not None else self._player_level(character)
        strength = resolved_attrs.get("str", 10)
        con = resolved_attrs.get("con", 10)
        will = resolved_attrs.get("will", resolved_attrs.get("wis", 10))
        return max(10, 8 + int(resolved_level) * 3 + con * 2 + strength // 2 + will // 3)

    def _player_current_hp(self, max_hp: int) -> int:
        for value in (
            self.state.flags.get("player_hp"),
            self.state.extra.get("current_hp"),
        ):
            if value is not None:
                return max(0, min(max_hp, _safe_int(value, max_hp)))
        player = self.player_character()
        if player:
            value = player.current_hp
            if value:
                return max(0, min(max_hp, _safe_int(value, max_hp)))
            value = player.extra.get("current_hp") if isinstance(player.extra, dict) else None
            if value is not None:
                return max(0, min(max_hp, _safe_int(value, max_hp)))
        return max_hp

    def _player_max_sp(self, character: Character | None = None) -> int:
        equipment_bonus = 0 if character is not None else _safe_int(self.player_equipment_summary().get("max_sp"), 0)
        base = self._player_base_max_sp(character)
        return max(1, base + equipment_bonus)

    def _player_base_max_sp(self, character: Character | None = None) -> int:
        player = character or self.player_character()
        if player:
            if player.max_sp:
                return max(1, _safe_int(player.max_sp, 12))
            for source in (player.extra, player.flags):
                if isinstance(source, dict):
                    value = source.get("base_max_sp") or source.get("original_max_sp") or source.get("max_sp")
                    if value:
                        return max(1, _safe_int(value, 12))
        state_value = self.state.extra.get("base_max_sp") or self.state.extra.get("max_sp")
        if state_value:
            return max(1, _safe_int(state_value, 12))
        return self._calculated_player_max_sp(character=player)

    def _calculated_player_max_sp(
        self,
        *,
        character: Character | None = None,
        level: int | None = None,
        max_hp: int | None = None,
        attrs: dict[str, int] | None = None,
    ) -> int:
        resolved_attrs = attrs or self._player_attributes(character)
        resolved_level = level if level is not None else self._player_level(character)
        resolved_max_hp = max_hp if max_hp is not None else self._player_max_hp(character)
        magic = resolved_attrs.get("magic") or resolved_attrs.get("mag") or resolved_attrs.get("int", 10)
        will = resolved_attrs.get("will") or resolved_attrs.get("wis", 10)
        return max(6, int(resolved_max_hp * 0.45) + int(magic) + int(will) + int(resolved_level) * 2)

    def _player_current_sp(self, max_sp: int) -> int:
        for value in (
            self.state.flags.get("player_sp"),
            self.state.extra.get("current_sp"),
        ):
            if value is not None:
                return max(0, min(max_sp, _safe_int(value, max_sp)))
        player = self.player_character()
        if player:
            value = player.current_sp
            if value:
                return max(0, min(max_sp, _safe_int(value, max_sp)))
            value = player.extra.get("current_sp") if isinstance(player.extra, dict) else None
            if value is not None:
                return max(0, min(max_sp, _safe_int(value, max_sp)))
        return max_sp

    def _player_attributes(self, character: Character | None = None) -> dict[str, int]:
        player = character or self.player_character()
        attrs: dict[str, Any] = {}
        if player and isinstance(player.attributes, dict):
            attrs.update(player.attributes)
        if player and isinstance(player.extra, dict):
            direct = player.extra.get("attributes")
            if isinstance(direct, dict):
                attrs.update(direct)
            ability = player.extra.get("ability")
            if isinstance(ability, dict):
                nested = ability.get("attributes")
                if isinstance(nested, dict):
                    attrs.update(nested)
        if self.state.party and isinstance(self.state.party[0], dict):
            extra = self.state.party[0].get("extra")
            if isinstance(extra, dict):
                direct = extra.get("attributes")
                if isinstance(direct, dict):
                    attrs.update(direct)
                ability = extra.get("ability")
                if isinstance(ability, dict):
                    nested = ability.get("attributes")
                    if isinstance(nested, dict):
                        attrs.update(nested)
        return {
            "str": _safe_int(attrs.get("str"), 10),
            "dex": _safe_int(attrs.get("dex"), 10),
            "con": _safe_int(attrs.get("con"), 10),
            "int": _safe_int(attrs.get("int"), 10),
            "wis": _safe_int(attrs.get("wis"), 10),
            "cha": _safe_int(attrs.get("cha"), 10),
            "magic": _safe_int(attrs.get("magic", attrs.get("mag", attrs.get("int", 10))), 10),
            "will": _safe_int(attrs.get("will", attrs.get("wis", 10)), 10),
        }

    def _action_roll_for_input(self, action: str, input_type: str, purpose: str = "action") -> dict[str, Any] | None:
        if not _should_use_action_roll(
            action,
            input_type,
            purpose,
            excluded_actions=(MOVE_CHOICE_LABEL, QUEST_BOARD_CHOICE_LABEL, QUEST_REPORT_CHOICE_LABEL, QUEST_ABANDON_CHOICE_LABEL),
            is_quest_abandon=_is_quest_abandon_action(action),
            is_conversation_end=_is_conversation_end_action(action),
        ):
            return None
        return self._make_action_roll(action, purpose=purpose)

    def roll_craft_check(self, ingredients: list[dict[str, Any]] | None = None, craft_intent: str = "auto") -> dict[str, Any]:
        plan = self._craft_plan_for_items(ingredients or [], craft_intent)
        return self._roll_craft_check_for_plan(plan)

    def _roll_craft_check_for_plan(self, plan: CraftPlan) -> dict[str, Any]:
        roll = self._make_action_roll(
            "craft",
            purpose="craft",
            forced_ability="dex",
            forced_target=plan.target,
            normalise_target=False,
        )
        roll["base_target"] = plan.base_target
        roll["home_furniture_level"] = plan.home_level
        roll["home_target_reduction"] = plan.home_reduction
        roll["craft_plan"] = plan.to_dict()
        if plan.base_target != plan.target:
            roll["line"] = f"{roll['line']} / クラフト補正: 目標値 {plan.base_target}->{plan.target}"
        return roll

    def _make_action_roll(
        self,
        action: str,
        *,
        purpose: str = "action",
        forced_ability: str = "",
        forced_target: int | None = None,
        normalise_target: bool = True,
    ) -> dict[str, Any]:
        judgement: dict[str, Any] | None = None
        if not forced_ability and forced_target is None:
            judgement = self._action_roll_llm_judgement(action, purpose)
        return _make_game_action_roll(
            action,
            purpose=purpose,
            attributes=self._player_attributes(),
            current_danger=self._current_location_danger(),
            forced_ability=forced_ability,
            forced_target=forced_target,
            normalise_target=normalise_target,
            judgement=judgement,
        )

    def _action_roll_llm_judgement(self, action: str, purpose: str) -> dict[str, Any] | None:
        context = action_roll_judgement_context(
            action,
            purpose,
            current_danger=self._current_location_danger(),
        )
        messages = [
            {"role": "system", "content": action_roll_system_prompt()},
            {"role": "user", "content": _ai_json(context)},
        ]
        try:
            response = self._chat_json(
                "action_roll_judger",
                messages,
                max_tokens=420,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=2,
            )
        except Exception as exc:
            self.state.world_data.extra.setdefault("action_roll_judgement_errors", []).append(
                {
                    "action": action,
                    "purpose": purpose,
                    "error": str(exc),
                }
            )
            return None
        judgement = normalise_action_roll_judgement(response)
        if judgement is None:
            self.state.world_data.extra.setdefault("action_roll_judgement_errors", []).append(
                {
                    "action": action,
                    "purpose": purpose,
                    "error": "invalid_action_roll_judgement",
                    "response": _strip_response_metadata(response),
                }
            )
            return None
        self.state.world_data.extra.setdefault("action_roll_judgements", []).append(
            {
                "action": action,
                "purpose": purpose,
                "judgement": judgement,
            }
        )
        return judgement

    def _append_action_roll_log(self, action_roll: dict[str, Any] | None) -> None:
        if isinstance(action_roll, dict) and action_roll.get("line"):
            self.state.display_log.append(str(action_roll["line"]))

    def _set_player_attributes(self, attrs: dict[str, int]) -> None:
        cleaned = {
            key: _safe_int(value, 10)
            for key, value in attrs.items()
            if key in {"str", "dex", "con", "int", "wis", "cha", "magic", "will"}
        }
        self.state.extra["attributes"] = dict(cleaned)
        player = self.player_character()
        if player:
            player.attributes.update(cleaned)
            player.extra.setdefault("attributes", {}).update(cleaned)
            ability = player.extra.setdefault("ability", {})
            if isinstance(ability, dict):
                ability.setdefault("attributes", {}).update(cleaned)
        if self.state.party and isinstance(self.state.party[0], dict):
            extra = self.state.party[0].setdefault("extra", {})
            if isinstance(extra, dict):
                extra.setdefault("attributes", {}).update(cleaned)
                ability = extra.setdefault("ability", {})
                if isinstance(ability, dict):
                    ability.setdefault("attributes", {}).update(cleaned)

    def _raise_random_player_attributes(self) -> dict[str, int]:
        attrs = self._player_attributes()
        keys = ["str", "dex", "con", "int", "wis", "cha"]
        count = random.randint(1, 3)
        selected = random.sample(keys, k=min(count, len(keys)))
        gains: dict[str, int] = {}
        for key in selected:
            attrs[key] = _safe_int(attrs.get(key), 10) + 1
            gains[key] = gains.get(key, 0) + 1
        attrs["magic"] = max(_safe_int(attrs.get("magic"), attrs.get("int", 10)), attrs.get("int", 10))
        attrs["will"] = max(_safe_int(attrs.get("will"), attrs.get("wis", 10)), attrs.get("wis", 10))
        self._set_player_attributes(attrs)
        return gains

    def _encounter_opponent(self, encounter: dict[str, Any]) -> Character | None:
        return self._character_from_reference(
            str(encounter.get("opponent_name") or ""),
            str(encounter.get("opponent_uuid") or encounter.get("active_opponent_uuid") or ""),
        )

    def _is_game_over(self) -> bool:
        return bool(self.state.flags.get("game_over"))

    def _set_game_over(
        self,
        *,
        source: str,
        reason: str = "",
        narration: str = "",
        encounter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reason = _short_text(str(reason or "game_over").strip(), 160)
        narration = str(narration or "冒険はここで終わった。").strip()
        event = {
            "reason": reason,
            "narration": narration,
            "source": source,
            "location": self.state.current_location,
            "day": self.state.day,
        }
        if encounter is not None:
            encounter["status"] = "ended"
            encounter["player_status"] = "game_over"
        active = self._active_encounter()
        if isinstance(active, dict):
            active["status"] = "ended"
            active["player_status"] = "game_over"
        self.state.flags["game_over"] = dict(event)
        self.state.flags["screen_mode"] = "game_over"
        self.state.flags.pop("active_encounter", None)
        self.state.flags.pop("active_conversation", None)
        self.state.choices = _game_over_choices()
        if self.state.narration_log:
            latest = self.state.narration_log[-1]
            if isinstance(latest, dict):
                latest["choices"] = _game_over_choices()
        player = self.player_character()
        if player:
            player.flags["game_over"] = True
            player.extra["game_over_reason"] = reason
        line = f"> [GameOver] {reason}"
        event["line"] = line
        self.state.world_data.extra.setdefault("game_over_events", []).append(dict(event))
        return event

    def _update_encounter_presence(self, encounter: dict[str, Any], state: str) -> None:
        location = str(encounter.get("location") or self.state.current_location or "")
        if not location:
            return
        requested_state = str(state or "").strip().lower()
        opponents = self._encounter_opponents(encounter)
        if not opponents:
            opponent_name = str(encounter.get("opponent_name") or "")
            character = self.state.world_data.character(opponent_name)
            opponents = [character] if isinstance(character, Character) else []
        current_subnode = self._runtime_subnode_for_presence(location)
        for character in opponents:
            if not isinstance(character, Character):
                continue
            entry = self._sync_encounter_opponent_entry(encounter, character)
            entry_status = str(entry.get("status") or entry.get("opponent_status") or character.extra.get("combat_status") or "").strip().lower()
            if _character_state_is_dead(character) or requested_state in {"dead", "corpse", "killed"} or entry_status in {"defeated", "dead", "corpse", "killed"}:
                self._set_character_presence(character, location, "dead")
                continue
            if requested_state in {FLED_STATUS_ID, "fled", "escaped", "retreated"} or entry_status in {FLED_STATUS_ID, "fled", "escaped", "retreated"}:
                continue
            visible_state = requested_state or "present"
            if visible_state in {"gone", "left", "ended", "inactive", "removed", "surrender_accepted"}:
                visible_state = "present"
            assigned_location, assigned_subnode = self._character_subnode_assignment(character)
            subnode_id = assigned_subnode if assigned_location == location else current_subnode
            if not subnode_id:
                subnode_id = current_subnode
            self._set_character_presence(character, location, visible_state, subnode_id=subnode_id)

    def _record_encounter_turn(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        manager_records: list[dict[str, Any]],
    ) -> None:
        encounter["turn"] = int(encounter.get("turn") or 0) + 1
        record = {
            "turn": encounter["turn"],
            "action": action,
            "input_type": input_type,
            "encounter": _strip_encounter_log(encounter),
            "managers": manager_records,
        }
        encounter.setdefault("log", []).append(record)
        self.state.world_data.extra.setdefault("encounter_log", []).append(record)

    def _encounter_choices(self, encounter: dict[str, Any]) -> list[str]:
        if encounter.get("status") == "ended":
            self.state.flags.pop(COMBAT_CHOICE_MENU_FLAG, None)
            return _quest_start_choices(self.state.world_data.quests) or ["周囲を見る"]
        menu = self.state.flags.get(COMBAT_CHOICE_MENU_FLAG)
        if isinstance(menu, dict):
            kind = str(menu.get("kind") or "").strip()
            if kind == "attack_target":
                return self._combat_attack_target_choices(encounter)
            if kind == "skill_list":
                return self._combat_skill_choices()
            if kind == "skill_target":
                return self._combat_skill_target_choices(encounter, str(menu.get("target_mode") or "enemy"))
        choices = [COMBAT_CHOICE_ATTACK_MENU, COMBAT_CHOICE_SKILL_MENU, COMBAT_CHOICE_ESCAPE]
        player_statuses = self._actor_status_effects("player", encounter)
        if _combat_status_blocks_attack(player_statuses):
            choices = [choice for choice in choices if choice != COMBAT_CHOICE_ATTACK_MENU]
        if _combat_status_blocks_escape(player_statuses):
            choices = [choice for choice in choices if choice != COMBAT_CHOICE_ESCAPE]
        if _combat_status_blocks_skill(player_statuses):
            choices = [choice for choice in choices if choice != COMBAT_CHOICE_SKILL_MENU]
        if self._encounter_has_surrendered_opponents(encounter):
            choices.append(COMBAT_CHOICE_ACCEPT_SURRENDER)
        return choices
    def _start_conversation(self, action: str, input_type: str, character: Character) -> str:
        previous_location = self.state.current_location
        response = self._conversation_starter(character, action, input_type)
        if _as_bool(response.get("content_violation")):
            narration = str(response.get("message") or response.get("reason") or response.get("narration") or "会話は始まらなかった。")
            choices = self.state.choices
            location = self.state.current_location
            self.state.world_data.history.append(
                {
                    "manager": "conversation_starter",
                    "character": character.name,
                    "action": action,
                    "input_type": input_type,
                    "content_violation": True,
                    "response": _strip_response_metadata(response),
                }
            )
            self._append_turn(action, narration, location, choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)

        location = requested_location_from_tools(response, self.state.current_location)
        self.state.flags["active_conversation"] = {
            "character": character.name,
            "location": location,
            "topic": str(response.get("topic") or ""),
        }
        self.state.flags["screen_mode"] = "conversation"
        narration = str(response.get("narration") or response.get("text") or f"{character.name}との会話を始めた。")
        self._set_character_presence(character, location)
        choices = self._filter_llm_choices_for_display(_as_str_list(response.get("choices")))
        self._record_conversation(character, "conversation_starter", action, input_type, response)
        self.state.world_data.history.append(
            {
                "manager": "conversation_starter",
                "character": character.name,
                "action": action,
                "input_type": input_type,
                "location": location,
                "response": _strip_response_metadata(response),
            }
        )
        self._append_turn(action, narration, location, choices, input_type=input_type)
        tool_result = apply_common_response_tools(
            self,
            response,
            source="conversation_starter",
            action=action,
            input_type=input_type,
            location=location,
            previous_location=previous_location,
            default_target=character.name,
            default_character=character,
        )
        if tool_result.results:
            self.state.world_data.history[-1]["llm_tools"] = tool_result.to_record()
        self.save_game()
        return self.state.log_text(16)

    def _conversation_character_reference_rule(self, character: Character) -> str:
        gender = str(character.gender or "").strip().casefold()
        if gender in {"male", "man", "boy"} or "男" in gender:
            reference = "The conversation target is male. Use his name, role, 男性, or 彼. Do not call him 彼女 or describe him as female."
        elif gender in {"female", "woman", "girl"} or "女" in gender:
            reference = "The conversation target is female. Use her name, role, 女性, or 彼女."
        elif gender in {"none", "neutral", "unknown", "nonbinary", "non-binary"}:
            reference = "The conversation target has no binary gender or unknown gender. Use the name, role, or その人物/その存在; avoid 彼女/彼 unless the profile explicitly establishes it."
        else:
            reference = "Do not infer the conversation target is female. Use the name or role unless the character profile clearly establishes a gendered reference."
        return (
            "Character reference rule:\n"
            f"- target_name: {character.name}\n"
            f"- target_gender: {character.gender or 'unknown'}\n"
            f"- {reference}\n"
            "- Match narration and speaker text to this profile; never default to feminine wording for party companions."
        )

    def _conversation_starter(
        self,
        character: Character,
        action: str,
        input_type: str,
    ) -> dict[str, Any]:
        world_payload = _ai_json(self._focused_world_ai_context(include_recent_log=False))
        character_payload = _ai_json(_character_ai_context(character))
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC会話開始担当です。"
                    "Fantasiaのconversation_starter相当として、"
                    "NPCとの会話の最初の応答、話題、次の選択肢を作ってください。"
                    "必要なら content_violation をLLMとしてのみ判断してください。"
                    "必ず narration, speaker, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"会話相手: {character.name}\n"
                    f"conversation_target_data: {character_payload}\n"
                    f"会話相手データ: {character_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    "このNPCとの会話を開始してください。"
                ),
            },
        ]
        messages.append({"role": "system", "content": self._conversation_character_reference_rule(character)})
        messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
        messages.append({"role": "system", "content": tool_prompt_instruction()})
        return self._chat_json(
            "conversation_starter",
            messages,
            max_tokens=700,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _continue_conversation(
        self,
        action: str,
        input_type: str,
        character: Character,
        action_roll: dict[str, Any] | None = None,
    ) -> str:
        previous_location = self.state.current_location
        response = self._conversation_facilitator(character, action, input_type, action_roll=action_roll)
        content_violation = _as_bool(response.get("content_violation"))
        finished = _as_bool(response.get("finished")) or _is_conversation_end_action(action)
        resolver_response: dict[str, Any] | None = None
        if finished and not content_violation:
            resolver_response = self._conversation_resolver(character, action, response)

        narration_parts = [str(response.get("narration") or response.get("text") or "")]
        if resolver_response:
            narration_parts.append(str(resolver_response.get("narration") or resolver_response.get("text") or ""))
        narration = "\n".join(part for part in narration_parts if part).strip() or "会話は静かに続いた。"
        resolver_payload = tool_effect_payload(resolver_response) if resolver_response else {}
        response_payload = tool_effect_payload(response)
        location = str(
            resolver_payload.get("location")
            or response_payload.get("location")
            or self.state.current_location
        )
        self._set_character_presence(character, location)
        choices = self._filter_llm_choices_for_display(
            _as_str_list((resolver_response or {}).get("choices") or response.get("choices"))
        )

        self._record_conversation(character, "conversation_facilitator", action, input_type, response)
        facilitator_history_index = len(self.state.world_data.history)
        self.state.world_data.history.append(
            {
                "manager": "conversation_facilitator",
                "character": character.name,
                "action": action,
                "input_type": input_type,
                "content_violation": content_violation,
                "finished": finished,
                "action_roll": action_roll,
                "response": _strip_response_metadata(response),
            }
        )
        resolver_history_index: int | None = None
        if resolver_response:
            self._record_conversation(character, "conversation_resolver", action, input_type, resolver_response)
            self._apply_conversation_resolution(character, resolver_response)
            resolver_history_index = len(self.state.world_data.history)
            self.state.world_data.history.append(
                {
                    "manager": "conversation_resolver",
                    "character": character.name,
                    "action": action,
                    "input_type": input_type,
                    "response": _strip_response_metadata(resolver_response),
                }
            )
        if finished or content_violation:
            self.state.flags.pop("active_conversation", None)
            self.state.flags["screen_mode"] = "exploration"
        else:
            self.state.flags["screen_mode"] = "conversation"

        self._append_turn(action, narration, location, choices, input_type=input_type)
        self._append_action_roll_log(action_roll)
        if not content_violation:
            facilitator_tools = apply_common_response_tools(
                self,
                response,
                source="conversation_facilitator",
                action=action,
                input_type=input_type,
                location=location,
                previous_location=previous_location,
                default_target=character.name,
                default_character=character,
            )
            if facilitator_tools.results:
                self.state.world_data.history[facilitator_history_index]["llm_tools"] = facilitator_tools.to_record()
        if resolver_response:
            resolver_tools = apply_common_response_tools(
                self,
                resolver_response,
                source="conversation_resolver",
                action=action,
                input_type=input_type,
                location=location,
                previous_location=previous_location,
                default_target=character.name,
                default_character=character,
            )
            if resolver_tools.results:
                target_index = resolver_history_index if resolver_history_index is not None else len(self.state.world_data.history) - 1
                self.state.world_data.history[target_index]["llm_tools"] = resolver_tools.to_record()
        self.save_game()
        return self.state.log_text(16)

    def _conversation_facilitator(
        self,
        character: Character,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(self._focused_world_ai_context(include_recent_log=False))
        character_payload = _ai_json(_character_ai_context(character))
        conversation_state = json.dumps(self.state.flags.get("active_conversation", {}), ensure_ascii=False)
        recent_log = self.state.log_text(10)
        action_roll_payload = json.dumps(action_roll or {}, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC会話進行担当です。"
                    "Fantasiaのconversation_facilitator相当として、"
                    "会話中のプレイヤー入力に対するNPC応答、関係変化、次の選択肢を作ってください。"
                    "必要なら content_violation をLLMとしてのみ判断してください。"
                    "必ず narration, speaker, choices を持つJSONだけを返してください。"
                    "game_side_action_roll が enabled=true の場合、会話行動の成否はゲーム側の確定判定として必ず尊重してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"会話相手: {character.name}\n"
                    f"conversation_target_data: {character_payload}\n"
                    f"会話状態: {conversation_state}\n"
                    f"直近ログ:\n{recent_log}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"game_side_action_roll: {action_roll_payload}\n"
                    "この会話を続けてください。会話が終わる場合は finished を true にしてください。"
                ),
            },
        ]
        messages.append({"role": "system", "content": self._conversation_character_reference_rule(character)})
        messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
        messages.append({"role": "system", "content": tool_prompt_instruction()})
        return self._chat_json(
            "conversation_facilitator",
            messages,
            max_tokens=800,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _conversation_resolver(
        self,
        character: Character,
        action: str,
        facilitator_response: dict[str, Any],
    ) -> dict[str, Any]:
        character_payload = _ai_json(_character_ai_context(character))
        facilitator_payload = json.dumps(_strip_response_metadata(facilitator_response), ensure_ascii=False)
        conversation_log = json.dumps(character.extra.get("conversation_log", [])[-8:], ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC会話解決担当です。"
                    "Fantasiaのconversation_resolver相当として、"
                    "会話終了時の要約、記憶更新、関係変化、次の選択肢を確定してください。"
                    "必ず narration, summary, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"会話相手: {character.name}\n"
                    f"conversation_target_data: {character_payload}\n"
                    f"プレイヤー行動: {action}\n"
                    f"直前のconversation_facilitator応答: {facilitator_payload}\n"
                    f"会話ログ: {conversation_log}\n"
                    "この会話を解決し、保存すべき要約を返してください。"
                ),
            },
        ]
        messages.append({"role": "system", "content": self._conversation_character_reference_rule(character)})
        messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
        messages.append({"role": "system", "content": tool_prompt_instruction()})
        return self._chat_json(
            "conversation_resolver",
            messages,
            max_tokens=650,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _apply_conversation_resolution(self, character: Character, response: dict[str, Any]) -> None:
        tool_payload = tool_effect_payload(response)
        summary = str(response.get("summary") or "")
        if summary:
            character.extra.setdefault("conversation_summaries", []).append(summary)
        if tool_payload.get("relationship_change"):
            character.extra.setdefault("relationship_changes", []).append(tool_payload.get("relationship_change"))
        for item in _as_list(tool_payload.get("memory_updates")):
            character.extra.setdefault("memory_updates", []).append(item)
        self.state.world_data.extra.setdefault("conversation_summaries", []).append(
            {
                "character": character.name,
                "summary": summary,
                "response": _strip_response_metadata(response),
            }
        )

    def _record_conversation(
        self,
        character: Character,
        manager_name: str,
        action: str,
        input_type: str,
        response: dict[str, Any],
    ) -> None:
        record = {
            "manager": manager_name,
            "action": action,
            "input_type": input_type,
            "response": _strip_response_metadata(response),
        }
        character.extra.setdefault("conversation_log", []).append(record)
        self.state.world_data.extra.setdefault("conversation_log", []).append(
            {
                "character": character.name,
                **record,
            }
        )

    def _should_run_field_event_evaluator(self, action: str, input_type: str) -> bool:
        return False

    def _roll_field_event_trigger(
        self,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        location_name = self.state.current_location or self.state.world_data.starting_location
        location = self.state.world_data.locations.get(location_name)
        extra = location.extra if location and isinstance(location.extra, dict) else {}
        kind = str(extra.get("location_kind") or extra.get("kind") or "").strip().lower()
        danger = max(0, self._current_location_danger(location_name))
        chance = 0.10
        reasons = ["base_exploration"]
        if input_type == "choice":
            chance += 0.02
            reasons.append("choice")
        lowered = str(action or "").casefold()
        if any(term in lowered for term in ("search", "investigate", "discover", "dungeon", "cave", "ruin", "forest", "help")):
            chance += 0.10
            reasons.append("explicit_exploration")
        if kind in {"dungeon"}:
            chance += 0.20
            reasons.append("dungeon_location")
        elif kind in {"wilderness", "road", "crossroad", "coast", "mountain", "river", "plain"}:
            chance += 0.12
            reasons.append("wild_location")
        elif kind in {"settlement", "town", "village", "city"}:
            chance += 0.02
            reasons.append("settlement_location")
        if danger:
            chance += min(0.22, danger / 160)
            reasons.append(f"danger:{danger}")

        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        subnode_id = self._current_subnode_id(location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        subnode = nodes.get(subnode_id, {}) if isinstance(nodes, dict) else {}
        subnode_kind = str(subnode.get("kind") or "").strip().lower()
        if any(term in subnode_kind for term in ("dungeon", "danger", "nest", "boss", "wild", "forest", "cave", "ruin")):
            chance += 0.10
            reasons.append(f"subnode:{subnode_kind}")

        hostile_present = False
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if bool(character.flags.get("hostile") or character.extra.get("hostile")):
                hostile_present = True
                break
        if hostile_present:
            chance += 0.14
            reasons.append("hostile_present")

        if isinstance(action_roll, dict):
            if _as_bool(action_roll.get("critical_success")) or _as_bool(action_roll.get("critical_failure")):
                chance += 0.14
                reasons.append("critical_roll")
            elif _as_bool(action_roll.get("success")):
                chance += 0.06
                reasons.append("successful_roll")
            elif _as_bool(action_roll.get("failure")):
                chance += 0.03
                reasons.append("failed_roll")

        turn_index = len(self.state.action_log)
        last_trigger_turn = _safe_int(self.state.world_data.extra.get("field_event_last_local_trigger_turn"), -9999)
        if turn_index - last_trigger_turn <= 2:
            chance *= 0.35
            reasons.append("recent_trigger_cooldown")

        chance = max(0.03, min(0.72, chance))
        seed = (
            f"field-event-trigger:{self.state.world_name}:{self.state.player_name}:"
            f"{self.state.day}:{turn_index}:{location_name}:{subnode_id}:{action}"
        )
        rng = random.Random(seed)
        roll = rng.random()
        triggered = roll < chance
        result = {
            "triggered": triggered,
            "chance": round(chance, 4),
            "roll": round(roll, 4),
            "location": location_name,
            "location_kind": kind,
            "subnode_id": subnode_id,
            "subnode_kind": subnode_kind,
            "danger": danger,
            "reasons": reasons,
            "seed": seed,
        }
        if triggered:
            self.state.world_data.extra["field_event_last_local_trigger_turn"] = turn_index
            self.state.world_data.extra["field_event_last_local_trigger"] = dict(result)
        return result

    def _field_event_evaluator(
        self,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
        field_event_trigger: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(self._focused_world_ai_context(include_recent_log=False))
        recent_log = self.state.log_text(10)
        action_roll_payload = json.dumps(action_roll or {}, ensure_ascii=False)
        field_event_trigger_payload = json.dumps(field_event_trigger or {}, ensure_ascii=False)
        danger_level = self._current_location_danger(self.state.current_location)
        npc_template_payload = json.dumps(
            {
                "enemy_templates": npc_template_prompt_summaries(
                    ENEMY_NPC_TEMPLATE_CATEGORIES,
                    danger_level=danger_level,
                    used_ids=self._npc_template_used_ids(),
                    limit=12,
                ),
                "friendly_templates": npc_template_prompt_summaries(
                    FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                    danger_level=danger_level,
                    used_ids=self._npc_template_used_ids(),
                    limit=12,
                ),
            },
            ensure_ascii=False,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのフィールドイベント判定担当です。"
                    "Fantasiaのfield_event_evaluator相当として、探索や移動中に"
                    "事前にゲーム側へ用意されていない突発イベントが起きるか判定してください。"
                    "ダンジョン発見、助けを求める人物、奇妙な痕跡などから、"
                    "必要なら野生のクエストを生成してください。"
                    "プレイヤーが明示的にダンジョンを生成・発見・移動したい場合、discovered_location は kind=dungeon にしてください。"
                    "そのダンジョンにボス、守護者、神、女神、主などが待つ内容なら boss_npc を返してください。"
                    "boss_npc は name, role, description, personality, look, image_generation_prompt, hostile を持つNPCとして返してください。"
                    "毎回イベントを起こす必要はありません。"
                    "必ず event_occurred, narration, location, choices を持つJSONだけを返してください。"
                    "game_side_action_roll が enabled=true の場合、探索行動の成否はゲーム側の確定判定として必ず尊重してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"直近ログ:\n{recent_log}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"game_side_action_roll: {action_roll_payload}\n"
                    "探索中の突発イベントが起きるか判定し、起きる場合は発見場所や野生クエストも返してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    f"Local field event trigger: {field_event_trigger_payload}\n"
                    "The game already ran this local roll before calling field_event_evaluator. "
                    "If triggered is true, create the triggered event content and return event_occurred=true unless that contradicts the current state."
                ),
            }
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Generated actor completeness rule: if you return npcs, enemies, opponents, or boss_npc, every "
                    "generated character object must include gender, age, look, personality, description, and "
                    "image_generation_prompt. For monsters/non-humans, use gender=none and age=adult/ancient/unknown "
                    "if exact human-style values are not meaningful."
                ),
            }
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    f"NPC template candidates: {npc_template_payload}\n"
                    "Generate each npc/enemy/boss as a world- and role-specific variation of these templates. "
                    "If a generated npc/enemy/boss matches a template, include npc_template_id on that character object. "
                    "The game will select a template locally if the id is absent. "
                    "Use enemy_templates for hostile enemies, monsters, blockers, and bosses. "
                    "Use friendly_templates for neutral or friendly NPCs."
                ),
            }
        )
        messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
        messages.append({"role": "system", "content": tool_prompt_instruction()})
        messages.append({"role": "system", "content": self._movement_choice_rule_prompt()})
        return self._chat_json(
            "field_event_evaluator",
            messages,
            max_tokens=900,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _apply_field_event(
        self,
        action: str,
        input_type: str,
        response: dict[str, Any],
        action_roll: dict[str, Any] | None = None,
        field_event_trigger: dict[str, Any] | None = None,
    ) -> str:
        previous_location = self.state.current_location
        tool_payload = tool_effect_payload(response)
        location = requested_location_from_tools(response, self.state.current_location)
        narration = str(response.get("narration") or response.get("text") or "探索中に何かが起きた。")
        movement_result = self._normalize_world_response_location(action, input_type, tool_payload, location)
        location = str(movement_result.get("location") or location)
        movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
        if movement_narration:
            narration = "\n".join([narration, *movement_narration]).strip()
        discovered_location = self._apply_discovered_location(tool_payload, action=action)
        generated_quests = self._apply_field_event_quests(tool_payload, location)
        generated_actors = self._apply_field_event_actors(tool_payload, location)
        boss_event = self._ensure_generated_dungeon_boss(discovered_location, action, tool_payload)
        if boss_event:
            generated_actors.append(boss_event)
        choices = self._augment_location_choices(
            self._filter_llm_choices_for_display(_as_str_list(response.get("choices"))),
            location,
        )

        if location:
            self.state.world_data.ensure_location(location)
        event_record = {
            "action": action,
            "input_type": input_type,
            "location": location,
            "discovered_location": discovered_location,
            "generated_quests": [quest.name for quest in generated_quests],
            "generated_actors": generated_actors,
            "action_roll": action_roll,
            "field_event_trigger": field_event_trigger,
            "event": tool_payload.get("event"),
            "response": _strip_response_metadata(response),
        }
        self.state.world_data.extra.setdefault("field_events", []).append(event_record)
        self.state.world_data.history.append(
            {
                "manager": "field_event_evaluator",
                "action": action,
                "input_type": input_type,
                "event_occurred": True,
                "location": location,
                "discovered_location": discovered_location,
                "generated_quests": [quest.name for quest in generated_quests],
                "generated_actors": generated_actors,
                "action_roll": action_roll,
                "field_event_trigger": field_event_trigger,
                "response": _strip_response_metadata(response),
            }
        )
        narration, choices, transition_response = self._maybe_start_combat_from_response(
            action,
            input_type,
            "field_event_evaluator",
            tool_payload,
            location,
            narration,
            choices,
        )
        if transition_response:
            event_record["combat_transition"] = _strip_response_metadata(transition_response)
        if not self._active_encounter() and movement_result.get("moved"):
            narration, choices, arrival_response = self._evaluate_hostile_arrival(
                action,
                input_type,
                "field_event_arrival",
                location,
                narration,
                choices,
            )
            if arrival_response:
                event_record["hostile_arrival"] = _strip_response_metadata(arrival_response)
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        narration = _hide_internal_quest_tokens(narration)
        choices = [_hide_internal_quest_tokens(choice) for choice in choices]
        self._append_turn(action, narration, location, choices, input_type=input_type)
        self._set_player_presence(location)
        self._append_action_roll_log(action_roll)
        tool_result = apply_common_response_tools(
            self,
            response,
            source="field_event_evaluator",
            action=action,
            input_type=input_type,
            location=location,
            previous_location=previous_location,
            movement_result=movement_result,
            default_target="player",
        )
        if tool_result.status_lines:
            event_record["status_effects_applied"] = tool_result.status_lines
        if tool_result.results:
            event_record["llm_tools"] = tool_result.to_record()
        item_event = tool_result.item_event
        if item_event and (item_event.get("items") or item_event.get("lost_items") or item_event.get("equipment")):
            event_record["item_effects"] = item_event
        self.save_game()
        return self.state.log_text(16)

    def _apply_discovered_location(self, response: dict[str, Any], *, action: str = "") -> str:
        raw = response.get("discovered_location")
        if not raw:
            return ""
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("location") or raw.get("title") or "").strip()
            if not name:
                return ""
            description = str(raw.get("description") or raw.get("overview") or raw.get("summary") or "")
            kind = _infer_world_location_kind_for_request(action, raw, name, description)
            if kind == "facility" and _add_facility_payload_to_settlement(self.state.world_data, name, description, str(raw.get("type") or raw.get("facility_type") or "")):
                return ""
            dungeon_parent = _existing_dungeon_location_for_subarea(self.state.world_data, name)
            if dungeon_parent:
                _record_location_subarea(self.state.world_data, dungeon_parent, name, description)
                return dungeon_parent
            location = self.state.world_data.ensure_location(name, description)
            location.area = str(raw.get("area") or location.area)
            location.flags["discovered"] = True
            location.flags["source"] = "field_event_evaluator"
            location.extra["raw_field_event_location"] = raw
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = _world_location_danger_from_payload(raw)
            self._set_location_graph_node(self.state.world_data, name, kind=kind, location=location)
            self._connect_world_locations(self.state.world_data, self.state.current_location, name)
            self._ensure_generated_dungeon_location(location, kind)
            return name
        name = str(raw).strip()
        if not name:
            return ""
        dungeon_parent = _existing_dungeon_location_for_subarea(self.state.world_data, name)
        if dungeon_parent:
            _record_location_subarea(self.state.world_data, dungeon_parent, name)
            return dungeon_parent
        location = self.state.world_data.ensure_location(name)
        location.flags["discovered"] = True
        location.flags["source"] = "field_event_evaluator"
        kind = _infer_world_location_kind_for_request(action, {}, name, location.description)
        location.extra["location_kind"] = kind
        self._set_location_graph_node(self.state.world_data, name, kind=kind, location=location)
        self._connect_world_locations(self.state.world_data, self.state.current_location, name)
        self._ensure_generated_dungeon_location(location, kind)
        return name

    def _ensure_generated_dungeon_location(self, location: LocationData, kind: str = "") -> dict[str, Any]:
        if str(kind or "").strip().lower() == "dungeon":
            location.extra["location_kind"] = "dungeon"
        if not _is_dungeon_location(location):
            return {}
        location.flags["dungeon"] = True
        graph = self._ensure_location_subnode_graph(self.state.world_data, location.name)
        if graph:
            graph.setdefault("created_for_generated_dungeon", True)
        return graph

    def _ensure_generated_dungeon_boss(
        self,
        location_name: str,
        action: str,
        response: dict[str, Any],
    ) -> dict[str, str] | None:
        location_name = str(location_name or "").strip()
        if not location_name:
            return None
        location = self.state.world_data.locations.get(location_name)
        if not location or not _is_dungeon_location(location):
            return None
        graph = self._ensure_generated_dungeon_location(location, "dungeon")
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        target_subnode = DUNGEON_DEEPEST_SUBNODE_ID if DUNGEON_DEEPEST_SUBNODE_ID in nodes else self._default_subnode_for_location(location)
        if not target_subnode:
            return None
        boss_payload = _generated_dungeon_boss_payload(response)
        boss_required = (
            _as_bool(location.extra.get("boss_required"))
            or _as_bool(location.extra.get("generated_dungeon_boss_required"))
            or _as_bool(location.flags.get("boss_required"))
            or _as_bool(location.flags.get("generated_dungeon_boss_required"))
            or str(location.extra.get("generated_by_tool") or "") == "generate_dungeon"
            or str(location.extra.get("role") or "") == "tool_generated_dungeon"
            or _generated_dungeon_boss_required(action, response, location)
        )
        if not boss_payload and not boss_required:
            return None
        if self._generated_dungeon_has_boss(location.name):
            return None
        if not boss_payload:
            boss_payload = _fallback_generated_dungeon_boss_payload(location, action, response)
        danger = max(5, _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0))
        boss_payload = self._template_augmented_npc_raw(
            boss_payload,
            categories=ENEMY_NPC_TEMPLATE_CATEGORIES,
            danger_level=danger,
            seed=f"generated-dungeon-boss:{self.state.world_name}:{location.name}:{action}",
            hostile=True,
            boss=True,
        )
        character = _enemy_npc_from_raw(boss_payload, len(self.state.world_data.characters))
        character.name = _unique_character_name(self.state.world_data, character.name)
        character.role = str(character.role or "ダンジョンボス")
        character.category = "enemy_npc"
        character.flags["enemy_npc"] = True
        character.flags["hostile"] = _as_bool(character.flags.get("hostile") if "hostile" in character.flags else True)
        character.flags["generated_dungeon_boss"] = True
        character.extra["generated_dungeon_boss"] = True
        character.extra["boss_location"] = location.name
        character.flags.setdefault("danger_level", danger)
        character.extra.setdefault("danger_level", danger)
        character.extra["spawn_subnode_id"] = target_subnode
        character.extra["origin_subnode_id"] = target_subnode
        character.extra["display_alias"] = str(character.extra.get("display_alias") or "ボス")
        character.extra["aliases"] = _dedupe_strs([character.name, "ボス", "守護者", *[str(value) for value in _as_list(character.extra.get("aliases"))]])
        character.level = max(_safe_int(character.level, 1), _generated_dungeon_boss_level(location))
        self._finalize_generated_npc(
            character,
            location_name=location.name,
            danger_level=danger,
            role_hint="generated_dungeon_boss",
            boss=True,
        )
        self._set_character_presence(character, location.name, "present", subnode_id=target_subnode)
        self.state.world_data.add_character(character)
        generated_bosses = location.extra.get("generated_bosses")
        if not isinstance(generated_bosses, list):
            generated_bosses = []
            location.extra["generated_bosses"] = generated_bosses
        generated_bosses.append(
            {
                "uuid": character.uuid,
                "name": character.name,
                "subnode_id": target_subnode,
                "source": "generated_dungeon_boss",
            }
        )
        return {"type": "character", "name": character.name, "role": "boss", "location": location.name, "subnode": target_subnode}

    def _generated_dungeon_has_boss(self, location_name: str) -> bool:
        for character in self.state.world_data.characters.values():
            if character.location != location_name:
                continue
            if _character_state_is_dead(character):
                continue
            if character.flags.get("generated_dungeon_boss") or character.extra.get("generated_dungeon_boss"):
                return True
            text = " ".join(str(value or "") for value in (character.role, character.category, character.extra.get("display_alias")))
            if any(marker in text.casefold() for marker in ("boss", "ボス", "守護者")):
                return True
        return False

    def _apply_field_event_actors(self, response: dict[str, Any], location: str) -> list[dict[str, str]]:
        generated: list[dict[str, str]] = []
        danger_level = self._current_location_danger(location)
        raw_characters = _as_list(response.get("npcs") or response.get("characters") or response.get("npc"))
        for item in raw_characters:
            item = self._template_augmented_npc_raw(
                item,
                categories=FRIENDLY_NPC_TEMPLATE_CATEGORIES,
                danger_level=danger_level,
                seed=f"field-event-npc:{self.state.world_name}:{location}:{len(generated)}",
                hostile=False,
            )
            character = _npc_from_raw(item, len(self.state.world_data.characters) + len(generated))
            if _world_has_dead_npc_identity(self.state.world_data, name=character.name, uuid=character.uuid):
                continue
            character.name = _unique_character_name(self.state.world_data, character.name)
            character.flags.setdefault("source", "field_event_evaluator")
            self._set_character_presence(character, location)
            self._finalize_generated_npc(
                character,
                location_name=location,
                danger_level=danger_level,
                role_hint="field_event_npc",
            )
            self.state.world_data.add_character(character)
            generated.append({"type": "character", "name": character.name})

        raw_opponents = _as_list(response.get("opponents") or response.get("enemies") or response.get("enemy_npcs") or response.get("enemy"))
        for item in raw_opponents:
            item = self._template_augmented_npc_raw(
                item,
                categories=ENEMY_NPC_TEMPLATE_CATEGORIES,
                danger_level=danger_level,
                seed=f"field-event-enemy:{self.state.world_name}:{location}:{len(generated)}",
                hostile=True,
            )
            character = _enemy_npc_from_raw(item, len(self.state.world_data.characters) + len(generated))
            character.name = _unique_character_name(self.state.world_data, character.name)
            character.flags.setdefault("source", "field_event_evaluator")
            character.flags["enemy_npc"] = True
            character.flags["hostile"] = _as_bool(character.flags.get("hostile") if "hostile" in character.flags else character.extra.get("hostile", True))
            self._set_character_presence(character, location)
            self._finalize_generated_npc(
                character,
                location_name=location,
                danger_level=danger_level,
                role_hint="field_event_enemy",
            )
            self.state.world_data.add_character(character)
            generated.append({"type": "character", "name": character.name})
        return generated

    def _input_gatekeeper(self, action: str, input_type: str, *, check_feasibility: bool = True) -> dict[str, Any]:
        context = (
            self._action_feasibility_context()
            if check_feasibility
            else {
                "world": {
                    "name": self.state.world_name,
                    "overview": _short_text(self.state.world_data.overview or self.state.world_data.world_situation, 500),
                },
                "location": {"name": self.state.current_location},
                "recent_log": self.state.log_text(4),
            }
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Fantasia's input gatekeeper. Judge LLM-side content safety and, when requested, "
                    "whether the player's action can plausibly be attempted in the current world state. "
                    "The game does not use local banned-word safety checks; content_violation is your judgement only. "
                    "Do not resolve the action. Do not decide success or failure of plausible attempts. "
                    "If check_feasibility is false, set action_possible=true unless content_violation=true. "
                    "Return only JSON with content_violation, action_possible, reason, message, and suggested_action."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"input_type: {input_type}\n"
                    f"player_action: {action}\n"
                    f"check_feasibility: {json.dumps(check_feasibility, ensure_ascii=False)}\n"
                    f"context: {_ai_json(context)}\n"
                    "Judge whether this input may be passed to the normal game managers."
                ),
            },
        ]
        messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
        return self._chat_json(
            "input_gatekeeper",
            messages,
            max_tokens=420,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _check_illegal_content(self, action: str, input_type: str) -> dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのプレイヤー入力チェック担当です。"
                    "ゲーム側にはローカルの禁止語判定や安全判定がないため、"
                    "この入力を通常ナレーションへ渡してよいかをLLMとして判断してください。"
                    "必ず content_violation, reason, message を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界: {self.state.world_name}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    "この行動を通常進行AIへ渡してよいか判定してください。"
                ),
            },
        ]
        return self._chat_json(
            "check_illegal_content",
            messages,
            max_tokens=350,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _check_action_feasibility(self, action: str, input_type: str) -> dict[str, Any]:
        context = self._action_feasibility_context()
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPG Fantasia の行動実現可能性チェック担当です。"
                    "禁止表現や安全判定ではなく、世界観、現在地、周囲の状況、所持品、NPC、直近ログから、"
                    "プレイヤーの行動を通常進行AIへ渡してよいかを判定してください。"
                    "必ず action_possible, reason, message を持つJSONだけを返してください。"
                    "判定は厳しすぎないでください。失敗しうる挑戦、無謀な行動、危険な行動、交渉、探索、攻撃、逃走、隠れる等は、"
                    "状況内で試みられるなら action_possible=true です。成否は後続の判定に任せます。"
                    "ただし、因果や手段なしに大金・希少品・新概念・勝利・敵の死亡・瞬間移動・NPCの性格改変・世界設定改変を"
                    "発生させる入力は action_possible=false にしてください。"
                    "例: 『いきなり50000Gold拾った』『超現象で敵がいきなり死んだ』『王都が突然ここに生えた』はfalse。"
                    "例: 『周囲を探して金目の物を探す』『敵に降伏を呼びかける』『不意打ちを狙う』はtrue。"
                    "falseの場合、messageはプレイヤー向けに短く自然な拒否文にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"状況JSON: {_ai_json(context)}\n"
                    "この入力を通常進行AIへ渡してよいか判定してください。"
                ),
            },
        ]
        messages.append({"role": "system", "content": self._npc_visibility_rule_prompt()})
        return self._chat_json(
            "check_action_feasibility",
            messages,
            max_tokens=420,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _action_feasibility_context(self) -> dict[str, Any]:
        world = self.state.world_data
        location_name = self.state.current_location or world.starting_location
        location = world.locations.get(location_name)
        graph = self._ensure_location_subnode_graph(world, location_name)
        subnode_id = self._current_subnode_id(location_name)
        subnode = graph.get("nodes", {}).get(subnode_id, {}) if isinstance(graph, dict) else {}
        active_facility = self._active_facility_record()
        active_encounter = self._active_encounter()
        nearby_npcs: list[dict[str, Any]] = []
        for character in world.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_active_facility(character):
                continue
            nearby_npcs.append(
                {
                    "name": character.name,
                    "uuid": character.uuid,
                    "role": character.role,
                    "state": character.state,
                    **self._visible_npc_context_fields(character, location_name),
                    "hostile": bool(character.flags.get("hostile") or character.extra.get("hostile")),
                    "personality": _short_text(character.personality or str(character.extra.get("personality") or ""), 160),
                }
            )
            if len(nearby_npcs) >= 6:
                break
        player = self.player_character()
        return {
            "world": {
                "name": world.world_name,
                "overview": _short_text(world.overview or world.world_situation, 900),
                "current_rumor": _short_text(world.current_rumor, 240),
            },
            "location": _location_ai_context(location) if location else {"name": location_name},
            "subnode": {
                "id": subnode_id,
                "name": str(subnode.get("name") or subnode_id),
                "kind": str(subnode.get("kind") or ""),
                "description": _short_text(str(subnode.get("description") or ""), 400),
            },
            "active_facility": active_facility or {},
            "player": _character_ai_context(player) if player else {"name": self.state.player_name},
            "player_gold": self.state.gold,
            "player_hunger": self._player_hunger(),
            "player_max_hunger": PLAYER_MAX_HUNGER,
            "player_inventory": [_compact_item_for_ai(item) for item in self._player_inventory()[:18] if isinstance(item, dict)],
            "npc_visibility_rule": self._npc_visibility_rule_prompt(),
            "nearby_npcs": nearby_npcs,
            "active_encounter": _compact_value(active_encounter or {}, max_chars=900),
            "active_quest": self.state.active_quest,
            "recent_log": self.state.log_text(8),
        }

    def _focused_world_ai_context(
        self,
        *,
        nearby_limit: int = 5,
        include_active_quest: bool = True,
        include_recent_log: bool = False,
    ) -> dict[str, Any]:
        world = self.state.world_data
        location_name = self.state.current_location or world.starting_location
        location = world.locations.get(location_name)
        location_extra = location.extra if location and isinstance(location.extra, dict) else {}
        graph = self._ensure_location_subnode_graph(world, location_name)
        subnode_id = self._current_subnode_id(location_name)
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        subnode = nodes.get(subnode_id, {}) if isinstance(nodes, dict) else {}
        subnode_edges = graph.get("edges", []) if isinstance(graph.get("edges"), list) else []
        adjacent_subnodes: list[str] = []
        for edge in subnode_edges:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or edge.get("source") or "")
            target = str(edge.get("to") or edge.get("target") or "")
            if source == subnode_id and target:
                adjacent_subnodes.append(target)
            elif target == subnode_id and source:
                adjacent_subnodes.append(source)
        subnode_movement = str(graph.get("movement") or "adjacent")
        remote_targets = self._remote_travel_targets_for_subnode(subnode) if isinstance(subnode, dict) else []
        movement_rule = "free"
        if location and (_subnode_map_hides_unvisited(location) or subnode_movement != "free"):
            movement_rule = "adjacent_only"

        nearby_npcs: list[dict[str, Any]] = []
        for character in world.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, location_name):
                continue
            if not self._character_matches_active_facility(character):
                continue
            nearby_npcs.append(
                _drop_empty(
                    {
                        "name": character.name,
                        "role": character.role,
                        "state": character.state,
                        **self._visible_npc_context_fields(character, location_name),
                        "level": character.level,
                        "current_hp": character.current_hp,
                        "max_hp": character.max_hp,
                        "current_sp": character.current_sp,
                        "max_sp": character.max_sp,
                        "hostile": bool(character.flags.get("hostile") or character.extra.get("hostile")),
                        "affinity": character.extra.get("affinity") if isinstance(character.extra, dict) else None,
                        "personality": _short_text(character.personality or str(character.extra.get("personality") or ""), 220),
                        "traits": _compact_value(character.traits, max_chars=260),
                        "skills": _compact_value(character.skills, max_chars=260),
                        "status_effects": _compact_value(character.status_effects, max_chars=260),
                    }
                )
            )
            if len(nearby_npcs) >= nearby_limit:
                break

        active_quest = self._find_quest_by_name(self.state.active_quest) if include_active_quest and self.state.active_quest else None
        data: dict[str, Any] = {
            "world_name": world.world_name,
            "overview": _short_text(world.overview or world.world_situation, 520),
            "world_situation": _short_text(world.world_situation, 420),
            "current_rumor": _short_text(world.current_rumor, 220),
            "world_time": _compact_value(world.extra.get("world_time"), max_chars=280) if isinstance(world.extra, dict) else None,
            "current_location": _drop_empty(
                {
                    "name": location_name,
                    "description": _short_text(location.description if location else "", 420),
                    "area": getattr(location, "area", "") if location else "",
                    "kind": location_extra.get("location_kind") or location_extra.get("kind"),
                    "danger_level": self._current_location_danger(location_name),
                    "dangerous_movement_rule": (
                        "dangerous areas allow only adjacent subnode movement unless the current subnode lists remote_travel_targets"
                        if movement_rule == "adjacent_only"
                        else ""
                    ),
                    "facilities": _compact_value(location_extra.get("facilities", []), max_chars=480),
                }
            ),
            "current_subnode": _drop_empty(
                {
                    "id": subnode_id,
                    "name": str(subnode.get("name") or subnode_id),
                    "kind": str(subnode.get("kind") or ""),
                    "description": _short_text(str(subnode.get("description") or ""), 340),
                    "adjacent_subnodes": adjacent_subnodes[:8],
                    "movement_rule": movement_rule,
                    "remote_travel_targets": remote_targets[:4],
                }
            ),
            "movement_options": self._movement_options_ai_context(location_name),
            "active_facility": self._active_facility_record() or {},
            "npc_visibility_rule": self._npc_visibility_rule_prompt(),
            "nearby_npcs": nearby_npcs,
            "active_quest": _compact_value(_quest_ai_context(active_quest, include_log=False, include_extra=True), max_chars=1400) if active_quest else {},
            "choices": list(self.state.choices[:5]),
        }
        craft_candidates = self._craft_tool_ai_candidates()
        if craft_candidates:
            data["craft_candidates"] = craft_candidates
        if include_recent_log:
            data["recent_log"] = self.state.log_text(5)
        return _drop_empty(data)

    def _random_settlement_home_subnode(self, settlement_name: str, seed: str) -> str:
        location = self.state.world_data.locations.get(str(settlement_name or "").strip())
        if not location:
            return ""
        graph = self._ensure_location_subnode_graph(self.state.world_data, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        if not isinstance(nodes, dict) or not nodes:
            return ""
        candidates: list[str] = []
        blocked_kinds = {"external", "dungeon", "danger", "trap", "monster_nest", "deepest"}
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            node_key = str(node_id or "").strip()
            if not node_key or node_key.startswith(SUBNODE_EXTERNAL_PREFIX):
                continue
            kind = str(node.get("kind") or "").strip().lower()
            if kind in blocked_kinds:
                continue
            candidates.append(node_key)
        if not candidates:
            candidates = [DEFAULT_SUBNODE_ID] if DEFAULT_SUBNODE_ID in nodes else [str(next(iter(nodes)))]
        rng = random.Random(f"{self.state.world_data.world_name}:{settlement_name}:{seed}")
        return rng.choice(candidates)

    def _route_skeleton_specs(self, world: WorldData) -> list[dict[str, Any]]:
        skeleton = world.extra.get("local_world_skeleton") if isinstance(world.extra, dict) else {}
        specs = skeleton.get("locations") if isinstance(skeleton, dict) else []
        if not isinstance(specs, list):
            return []
        result = [spec for spec in specs if isinstance(spec, dict) and str(spec.get("name") or "") in world.locations]
        result.sort(key=lambda item: _safe_int(item.get("coord_index"), _safe_int(item.get("grid_x"), 0)))
        return result

    def save_game(self) -> Path:
        return self.save_store.save_game(self.state)

    def load_game(self, world_name: str | None = None, player_name: str | None = None) -> str:
        if world_name and player_name:
            self.state = self.save_store.load_game(world_name, player_name)
        else:
            self.state = self.save_store.load_latest()
        self._set_world_time_total_hours(self._world_time_total_hours())
        self._sync_player_progress_to_character()
        return self.state.log_text()

    def list_saves(self) -> list[SaveSlot]:
        return self.save_store.list_saves()

    def _character_for_image(self, character_name: str | None) -> Character:
        ref = str(character_name or "").strip()
        player = self.player_character()
        if player and (
            not ref
            or ref == str(player.uuid or "")
            or ref == player.name
            or ref == str(self.state.player_uuid or "")
            or ref == str(self.state.player_name or "")
        ):
            return player
        if ref:
            character = self.state.world_data.character(ref)
            if character:
                return character
        if self.state.world_data.characters:
            return next(iter(self.state.world_data.characters.values()))
        character = Character(
            name=self.state.player_name or "Player",
            role="player",
            category="player",
            look="fantasy RPG adventurer",
            image_generation_prompt=["fantasy RPG adventurer", "single character", "full body"],
            flags={"source": "image_pipeline_fallback"},
        )
        self._set_character_presence(character, self.state.current_location or self.state.world_data.starting_location)
        self.state.world_data.add_character(character)
        return character

    def _monster_for_image(self, monster_name: str | None) -> Character:
        if monster_name:
            character = self.state.world_data.character(monster_name)
            if character:
                return character
        for character in self.state.world_data.characters.values():
            if character.flags.get("enemy_npc") or character.category in {"enemy_npc", "quest_objective"} or character.flags.get("hostile"):
                return character
        monster = Character(
            name="硝子森の影",
            role="敵対者",
            category="wild_encounter",
            backstory="霧と雨音の中から現れる、硝子森に棲む影のような魔物。",
            look="霧と雨音の中から現れる、硝子森に棲む影のような魔物。",
            traits=[
                {"name": "慎重", "desc": "相手の動きを見てから行動する。"},
                {"name": "霧まとい", "desc": "距離を取り、姿をぼかす。"},
            ],
            flags={"source": "image_pipeline_fallback", "enemy_npc": True, "hostile": True},
        )
        self._set_character_presence(monster, self.state.current_location or self.state.world_data.starting_location)
        self._ensure_character_runtime_data(monster)
        self.state.world_data.add_character(monster)
        return monster

    def stop(self) -> None:
        self.llm.stop()
        stop_image = getattr(self.image_backend, "stop", None)
        if callable(stop_image):
            stop_image()

    def _active_conversation_character(self) -> Character | None:
        active = self.state.flags.get("active_conversation")
        if not isinstance(active, dict):
            return None
        name = str(active.get("character") or "")
        if not name:
            return None
        character = self.state.world_data.character(name)
        if character is None:
            self.state.flags.pop("active_conversation", None)
            return None
        current_location = self.state.current_location or self.state.world_data.starting_location
        active_location = str(active.get("location") or "").strip()
        if active_location and current_location and active_location != current_location:
            self.state.flags.pop("active_conversation", None)
            return None
        if not _actor_present_at(character.location, character.state, character.flags, current_location):
            self.state.flags.pop("active_conversation", None)
            return None
        if not self._character_matches_active_facility(character):
            self.state.flags.pop("active_conversation", None)
            return None
        return character

    def _find_conversation_target(self, action: str) -> Character | None:
        if not _is_conversation_action(action):
            return None
        text = action.strip()
        current_location = self.state.current_location or self.state.world_data.starting_location
        characters = [
            character
            for character in self.state.world_data.characters.values()
            if not character.flags.get("is_player")
            and _actor_present_at(character.location, character.state, character.flags, current_location)
            and self._character_matches_active_facility(character)
        ]
        for character in characters:
            if character.name and character.name in text:
                return character
        for character in characters:
            if character.role and character.role in text:
                return character
        for character in characters:
            aliases = [str(item) for item in _as_list(character.extra.get("aliases"))]
            if any(alias and alias in text for alias in aliases):
                return character
        resolved = self._resolve_context_reference(text, "conversation_target", allowed_target_types=["character"])
        resolved_character = self._match_character_reference_from_candidates(
            str(resolved.get("target_name") or ""),
            characters,
        )
        if resolved_character:
            return resolved_character
        for character in characters:
            if character.category in {"resident", "adventurer"}:
                return character
        return characters[0] if characters else None

    def _match_character_reference_from_candidates(
        self,
        target_name: str,
        candidates: list[Character],
    ) -> Character | None:
        target = str(target_name or "").strip()
        if not target:
            return None
        folded = target.casefold()
        for character in candidates:
            terms = _character_reference_terms(character)
            terms.extend(_as_str_list(character.flags.get("aliases")))
            terms.extend(_as_str_list(character.extra.get("aliases")))
            for term in _dedupe_strs([str(item or "").strip() for item in terms]):
                if not term:
                    continue
                if target == term or folded == term.casefold() or target in term or term in target:
                    return character
        return None

    def _chat_json(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        world_name: str,
        player_name: str,
        retries: int = 2,
        schema_instruction_text: str | None = None,
    ) -> dict[str, Any]:
        templated_messages = self.prompt_templates.apply_messages(manager_name, messages)
        instruction = self.prompt_templates.apply_schema_instruction(
            manager_name,
            schema_instruction_text if schema_instruction_text is not None else schema_instruction(manager_name),
        )
        base_messages = _with_schema_instruction(templated_messages, instruction)
        last_user_prompt = next((item.get("content", "") for item in reversed(messages) if item.get("role") == "user"), "")
        context_action = _player_action_from_prompt(last_user_prompt)
        if self._should_attach_temp_context(manager_name, context_action):
            base_messages = base_messages + [self._temp_context_reference_message(manager_name, context_action)]
        attempt_messages = base_messages
        last_response: Any = {}
        last_errors: list[str] = []
        call_started = time.perf_counter()
        self._write_temp_llm_context_log(f"before_llm:{manager_name}", action=last_user_prompt)

        for attempt in range(retries + 1):
            attempt_started = time.perf_counter()
            prompt_chars = sum(
                len(str(item.get("role", ""))) + len(str(item.get("content", "")))
                for item in attempt_messages
            )
            try:
                result = self.llm.chat(manager_name, attempt_messages, max_tokens=max_tokens)
            except Exception as exc:
                self._append_llm_metric(
                    {
                        "manager": manager_name,
                        "world": world_name,
                        "player": player_name,
                        "status": "backend_error",
                        "attempt": attempt + 1,
                        "max_attempts": retries + 1,
                        "duration_ms": round((time.perf_counter() - attempt_started) * 1000, 2),
                        "total_duration_ms": round((time.perf_counter() - call_started) * 1000, 2),
                        "message_count": len(attempt_messages),
                        "prompt_chars": prompt_chars,
                        "response_chars": 0,
                        "max_tokens": max_tokens,
                        "error": str(exc),
                    }
                )
                raise
            response_chars = len(
                result.content
                if isinstance(result.content, str)
                else json.dumps(result.content, ensure_ascii=False, default=str)
            )
            response, errors = validate_manager_response(manager_name, result.content)
            if errors:
                failed_response = _as_dict(result.content)
                failed_response["_backend"] = result.backend
                if result.request_params:
                    failed_response["_completion_parameters"] = result.request_params
                failed_response["_validation"] = {
                    "ok": False,
                    "attempt": attempt + 1,
                    "errors": errors,
                }
                self.store.save_llm_exchange(
                    world_name,
                    player_name,
                    manager_name,
                    attempt_messages,
                    failed_response,
                )
                self._write_temp_llm_context_log(
                    f"llm_validation_error:{manager_name}",
                    action=last_user_prompt,
                    response=failed_response,
                    errors=errors,
                )
                self._append_llm_metric(
                    {
                        "manager": manager_name,
                        "world": world_name,
                        "player": player_name,
                        "backend": result.backend,
                        "status": "validation_error",
                        "attempt": attempt + 1,
                        "max_attempts": retries + 1,
                        "duration_ms": round((time.perf_counter() - attempt_started) * 1000, 2),
                        "total_duration_ms": round((time.perf_counter() - call_started) * 1000, 2),
                        "message_count": len(attempt_messages),
                        "prompt_chars": prompt_chars,
                        "response_chars": response_chars,
                        "max_tokens": max_tokens,
                        "request_params": result.request_params,
                        "validation_errors": errors,
                    }
                )
                last_response = failed_response
                last_errors = errors
                if attempt < retries:
                    retry_response = sanitize_retry_response(result.content)
                    attempt_messages = base_messages + [
                        {
                            "role": "user",
                            "content": retry_prompt(manager_name, errors, retry_response),
                        },
                    ]
                    continue
                raise JsonResponseError(manager_name, last_errors, last_response)

            response["_backend"] = result.backend
            if result.request_params:
                response["_completion_parameters"] = result.request_params
            response["_validation"] = {
                "ok": True,
                "attempts": attempt + 1,
                "repaired": attempt > 0,
            }
            self.store.save_llm_exchange(
                world_name,
                player_name,
                manager_name,
                attempt_messages,
                response,
            )
            self._write_temp_llm_context_log(f"after_llm:{manager_name}", action=last_user_prompt, response=response)
            self._append_llm_metric(
                {
                    "manager": manager_name,
                    "world": world_name,
                    "player": player_name,
                    "backend": result.backend,
                    "status": "ok",
                    "attempt": attempt + 1,
                    "max_attempts": retries + 1,
                    "repaired": attempt > 0,
                    "duration_ms": round((time.perf_counter() - attempt_started) * 1000, 2),
                    "total_duration_ms": round((time.perf_counter() - call_started) * 1000, 2),
                    "message_count": len(attempt_messages),
                    "prompt_chars": prompt_chars,
                    "response_chars": response_chars,
                    "max_tokens": max_tokens,
                    "request_params": result.request_params,
                }
            )
            return response

        raise JsonResponseError(manager_name, last_errors, last_response)

    def _append_llm_metric(self, metric: dict[str, Any]) -> None:
        try:
            self.store.append_llm_metric(metric)
        except Exception:
            return


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"text": str(value)}


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _dedupe_strs(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen or _is_invalid_runtime_control_choice(text):
            continue
        seen.add(text)
        result.append(text)
    return result


def _is_invalid_runtime_control_choice(text: str) -> bool:
    lowered = str(text or "").strip().casefold()
    return lowered in {"restart", "re-start", "retry", "リスタート", "再スタート", "やり直す", "ゲームを再開"}


def _exploration_choices(values: list[str]) -> list[str]:
    return _dedupe_strs(values)[:MAX_EXPLORATION_CHOICES]


def _system_choice_allowed_through_movement_filter(text: str, *, allow_home_choices: bool) -> bool:
    if text in {MOVE_CHOICE_LABEL, QUEST_BOARD_CHOICE_LABEL, QUEST_REPORT_CHOICE_LABEL, QUEST_ABANDON_CHOICE_LABEL}:
        return True
    if text == f"{PLAYER_HOME_NAME}へ移動":
        return True
    if allow_home_choices and text in PLAYER_HOME_CHOICES:
        return True
    return False


def _filter_llm_display_choices(
    values: list[str],
    *,
    keep_system_choices: bool = False,
    allow_home_choices: bool = False,
) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if keep_system_choices and _system_choice_allowed_through_movement_filter(text, allow_home_choices=allow_home_choices):
            result.append(text)
            continue
        if _choice_looks_like_movement(text):
            continue
        result.append(text)
    return result


def _choice_looks_like_movement(text: str) -> bool:
    lowered = str(text or "").casefold()
    if lowered in {"go", "move", "return", "enter", "leave", "exit"}:
        return True
    movement_words = (
        "へ移動",
        "へ進む",
        "へ向か",
        "に移動",
        "に進む",
        "に向か",
        "奥へ",
        "奥に",
        "先へ",
        "先に",
        "元の位置",
        "来た道",
        "引き返",
        "帰る",
        "立ち去",
        "離れる",
        "階段を降り",
        "階段を上",
        "階段を登",
        "扉を通",
        "門をくぐ",
        "戻る",
        "向かう",
        "出る",
        "入る",
        "go ",
        "go to",
        "go back",
        "go deeper",
        "move ",
        "travel",
        "head to",
        "return ",
        "enter ",
        "leave ",
        "exit ",
    )
    return any(word in text or word in lowered for word in movement_words)


def _character_prompt_parts(character: Character) -> list[str]:
    parts = [
        "masterpiece",
        "best quality",
        "anime fantasy RPG character portrait",
        "single character",
        "full body",
        "standing pose",
        "isolated cutout",
        "pure white background",
        "no scenery",
        "no background objects",
    ]
    parts.extend(_character_visual_feature_parts(character))
    return _dedupe_strs(parts)


def _character_visual_feature_parts(character: Character) -> list[str]:
    parts = [
        *character.image_generation_prompt,
        character.name,
        character.role,
        character.category,
        _age_gender_prompt(character.age, character.gender),
        character.look,
        character.personality,
        character.backstory,
    ]
    parts.extend(_dict_list_visual_parts(character.traits, ("name", "desc", "visual", "appearance")))
    parts.extend(_dict_list_visual_parts(character.skills, ("name", "desc", "effect", "element", "type", "visual_effect")))
    parts.extend(_dict_list_visual_parts(character.status_effects, ("name", "description", "llm_effect", "severity", "visual")))
    parts.extend(_ability_visual_parts(character.extra))
    parts.extend(_dict_list_visual_parts(character.inventory[:4], ("name", "category", "description")))
    return _dedupe_strs(parts)[:36]


def _monster_prompt_parts(monster: Character) -> list[str]:
    parts = [
        "masterpiece",
        "best quality",
        "fantasy RPG monster",
        "single creature",
        "full body",
        "isolated cutout",
        "pure white background",
        "no scenery",
        "no background objects",
        monster.name,
        monster.role,
        monster.category,
        monster.backstory,
        monster.look,
    ]
    parts.extend(_as_str_list(monster.prompts.get("image_generation_prompt")))
    parts.extend(_as_str_list(monster.image_generation_prompt))
    parts.extend(_monster_visual_feature_parts(monster))
    return _dedupe_strs(parts)


def _monster_visual_feature_parts(monster: Character) -> list[str]:
    parts = [
        monster.name,
        monster.role,
        monster.category,
        monster.backstory,
        monster.look,
    ]
    parts.extend(_dict_list_visual_parts(monster.traits, ("name", "desc", "visual", "appearance")))
    parts.extend(_dict_list_visual_parts(monster.skills, ("name", "desc", "effect", "element", "type", "visual_effect")))
    return _dedupe_strs(parts)[:28]


def _subject_negative_terms() -> list[str]:
    return [
        "background scenery",
        "background objects",
        "wall",
        "pillar",
        "column",
        "architecture",
        "furniture",
        "frame",
        "large block",
        "floating object",
        "extra object",
        "complex background",
        "gradient background",
    ]


def _append_negative_terms(base_prompt: str, terms: list[str]) -> str:
    base_parts = [part.strip() for part in str(base_prompt or "").split(",") if part.strip()]
    return ", ".join(_dedupe_strs(base_parts + terms))


def _cg_subject_prompt_parts(characters: list[Character], monsters: list[Character]) -> list[str]:
    if not characters and not monsters:
        return []
    parts = ["visible characters keep their established designs"]
    for character in characters[:5]:
        label = "player character" if character.flags.get("is_player") else "NPC"
        parts.append(f"{label}: {character.name}")
        parts.extend(_character_visual_feature_parts(character)[:18])
    for monster in monsters[:4]:
        parts.append(f"enemy creature: {monster.name}")
        parts.extend(_monster_visual_feature_parts(monster)[:14])
    return _dedupe_strs(parts)[:80]


def _cg_scene_brief_parts(request: dict[str, Any], location: str) -> list[str]:
    response = request.get("response") if isinstance(request.get("response"), dict) else {}
    parts = [
        "fantasy RPG event CG",
        "single cinematic scene illustration",
        "match the latest story narration",
        f"location: {location}",
    ]
    for key in ("cg_description", "description", "narration", "recent_log"):
        text = _short_text(request.get(key), 260)
        if text:
            parts.append(f"{key}: {text}")
    if isinstance(response, dict):
        for key in ("narration", "text", "event", "quest_progress", "quest_update", "relationship_change"):
            value = response.get(key)
            if value in (None, "", [], {}):
                continue
            parts.append(f"source {key}: {_short_text(_compact_value(value, max_chars=320), 320)}")
    return _dedupe_strs(parts)[:18]


def _visual_subjects_context(characters: list[Character], monsters: list[Character]) -> dict[str, Any]:
    return _drop_empty(
        {
            "characters": [
                _character_ai_context(character, details=True)
                for character in characters[:5]
            ],
            "opponents": [
                _character_ai_context(monster, details=True)
                for monster in monsters[:4]
            ],
        }
    )


def _age_gender_prompt(age: str, gender: str) -> str:
    parts = _age_visual_prompt_parts(age)
    if gender:
        parts.append(gender)
    return ", ".join(parts)


def _age_visual_prompt_parts(age: str) -> list[str]:
    text = str(age or "").strip()
    if not text:
        return []
    match = re.search(r"\d+", text)
    if match:
        value = int(match.group(0))
        return [
            f"apparent age around {value} years old",
            f"looks about {value} years old",
        ]
    return [
        f"apparent age: {text}",
        f"visual age matches: {text}",
    ]


def _dict_list_visual_parts(items: list[Any], fields: tuple[str, ...]) -> list[str]:
    parts: list[str] = []
    for item in items[:8]:
        if isinstance(item, dict):
            for field in fields:
                text = _short_text(item.get(field), 120)
                if text:
                    parts.append(text)
        else:
            text = _short_text(item, 120)
            if text:
                parts.append(text)
    return parts


def _ability_visual_parts(extra: dict[str, Any]) -> list[str]:
    if not isinstance(extra, dict):
        return []
    ability = extra.get("ability")
    if not isinstance(ability, dict):
        return []
    attributes = ability.get("attributes")
    if not isinstance(attributes, dict):
        return []
    labels = {
        "str": "strong physique",
        "dex": "nimble posture",
        "con": "sturdy build",
        "int": "intelligent expression",
        "wis": "calm perceptive eyes",
        "cha": "charismatic presence",
    }
    parts: list[str] = []
    for key, label in labels.items():
        try:
            value = int(attributes.get(key, 10))
        except (TypeError, ValueError):
            continue
        if value >= 14:
            parts.append(label)
    return parts


def _game_over_choices() -> list[str]:
    return ["ゲームオーバー"]


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _relationship_delta(value: Any) -> int:
    if isinstance(value, (int, float, str)):
        return max(NPC_AFFINITY_DELTA_MIN, min(NPC_AFFINITY_DELTA_MAX, _safe_int(value, 0)))
    if not isinstance(value, dict):
        return 0
    for key in (
        "delta",
        "change",
        "amount",
        "value",
        "affinity_delta",
        "trust_delta",
        "favor_delta",
        "relationship_delta",
        "affection_delta",
        "trust",
        "affinity",
        "favor",
        "affection",
    ):
        if key in value:
            return max(NPC_AFFINITY_DELTA_MIN, min(NPC_AFFINITY_DELTA_MAX, _safe_int(value.get(key), 0)))
    if _as_bool(value.get("positive") or value.get("liked") or value.get("success")):
        return 1
    if _as_bool(value.get("negative") or value.get("disliked") or value.get("failure")):
        return -1
    return 0


def _relationship_reason(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    reason = value.get("reason") or value.get("cause") or value.get("action") or value.get("summary") or ""
    if isinstance(reason, (dict, list)):
        return ""
    return _short_text(str(reason or "").strip(), 40)


def _npc_memory_text(value: Any) -> str:
    if isinstance(value, dict):
        raw = (
            value.get("memory")
            or value.get("text")
            or value.get("summary")
            or value.get("description")
            or value.get("event")
            or value.get("value")
            or ""
        )
    else:
        raw = value
    if isinstance(raw, (dict, list)):
        return ""
    return _short_text(str(raw or "").strip(), 240)


def _npc_updated_description_text(value: Any) -> str:
    if isinstance(value, dict):
        raw = (
            value.get("updated_description")
            or value.get("new_description")
            or value.get("description")
            or value.get("backstory")
            or value.get("summary")
            or value.get("value")
            or ""
        )
        if not raw:
            previous = value.get("previous_description") or value.get("old_description") or ""
            update = value.get("update") or value.get("event") or value.get("memory") or ""
            raw = f"{previous} {update}".strip()
    else:
        raw = value
    if isinstance(raw, (dict, list)):
        return ""
    return _short_text(str(raw or "").strip(), 1000)


def _item_effect_reference(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if any(key in value for key in ("name", "item_name", "title", "item_uuid", "item_uuids", "uuid", "slot", "equipment_slot")):
        return value
    item = value.get("item")
    if item in (None, "", [], {}):
        return value
    if isinstance(item, dict):
        reference = dict(item)
        for key in ("quantity", "count", "amount"):
            if key in value and key not in reference:
                reference[key] = value[key]
        return reference
    reference: dict[str, Any] = {"name": str(item)}
    for key in ("quantity", "count", "amount"):
        if key in value:
            reference[key] = value[key]
    return reference


def _item_effect_reason(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    reason = value.get("reason") or value.get("cause") or value.get("source") or ""
    if isinstance(reason, (dict, list)):
        return ""
    return _short_text(str(reason or "").strip(), 40)


def _is_trade_negotiation_action(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(
        keyword in text
        for keyword in (
            "値引",
            "値切",
            "まけて",
            "安く",
            "価格交渉",
            "値段交渉",
            "割引",
            "discount",
            "haggle",
            "bargain",
            "negotiate price",
            "lower price",
            "cheaper",
        )
    )


def _movement_target_location(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        return fallback
    if not isinstance(value, dict):
        return fallback
    location = str(
        value.get("location")
        or value.get("to")
        or value.get("destination")
        or value.get("new_location")
        or value.get("current_location")
        or ""
    ).strip()
    if not location and _as_bool(value.get("follow_player") or value.get("with_player") or value.get("following")):
        location = fallback
    if location.lower() in {"here", "current", "current_location", "player", "with_player", "follow_player"}:
        location = fallback
    return location or fallback


def _movement_has_explicit_location(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for key in ("location", "to", "destination", "new_location", "current_location"):
        text = str(value.get(key) or "").strip()
        if text and text.lower() not in {"here", "current", "current_location", "player", "with_player", "follow_player"}:
            return True
    return False


def _movement_target_state(value: Any, fallback: str) -> str:
    if not isinstance(value, dict):
        return fallback or "present"
    state = str(value.get("state") or value.get("status") or value.get("presence") or "").strip()
    if state:
        return state
    if _as_bool(value.get("left") or value.get("gone")):
        return "gone"
    return fallback or "present"


def _movement_party_action(value: Any, state: str) -> str:
    texts = [str(state or "")]
    if isinstance(value, dict):
        texts.extend(
            str(value.get(key) or "")
            for key in (
                "action",
                "party_action",
                "relationship",
                "status",
                "presence",
                "state",
                "reason",
            )
        )
        if _as_bool(
            value.get("dead")
            or value.get("killed")
            or value.get("is_dead")
            or value.get("died")
        ):
            return "dead"
        if _as_bool(
            value.get("wait")
            or value.get("waiting")
            or value.get("stay")
            or value.get("standby")
            or value.get("temporary_wait")
            or value.get("wait_here")
        ):
            return "wait"
        if _as_bool(
            value.get("leave_party")
            or value.get("party_leave")
            or value.get("dismiss")
            or value.get("dismissed")
            or value.get("separate")
        ):
            return "leave"
        if _as_bool(
            value.get("join_party")
            or value.get("party_join")
            or value.get("companion")
            or value.get("follow_player")
            or value.get("with_player")
            or value.get("following")
            or value.get("escort")
            or value.get("escorted")
        ):
            return "join"
    joined = " ".join(text.casefold() for text in texts if text)
    if any(word in joined for word in ("dead", "corpse", "killed", "died")):
        return "dead"
    if any(word in joined for word in ("wait", "waiting", "standby", "stay here", "temporary", "待機", "待つ", "ここで待")):
        return "wait"
    if any(word in joined for word in ("leave", "left", "depart", "dismiss", "separate", "gone", "removed")):
        return "leave"
    if any(word in joined for word in ("party", "companion", "join", "follow", "following", "escort", "ally")):
        return "join"
    return ""


def _party_entry_is_player(value: Any, player_name: str = "") -> bool:
    if not isinstance(value, dict):
        return False
    flags = value.get("flags")
    flags = flags if isinstance(flags, dict) else {}
    if flags.get("is_player"):
        return True
    category = str(value.get("category") or "").strip().casefold()
    role = str(value.get("role") or "").strip().casefold()
    name = str(value.get("name") or "").strip()
    return bool(category == "player" or role == "player" or (player_name and name == player_name))


def _normalise_element_id(value: Any, fallback: str = "physical") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    key = text.casefold()
    aliases = {
        "phys": "physical",
        "物理": "physical",
        "flame": "fire",
        "炎": "fire",
        "水": "water",
        "氷": "ice",
        "thunder": "lightning",
        "雷": "lightning",
        "土": "earth",
        "風": "wind",
        "plant": "grass",
        "草": "grass",
        "毒": "poison",
        "mind": "mental",
        "精神": "mental",
        "holy": "light",
        "光": "light",
        "darkness": "dark",
        "闇": "dark",
        "neutral": "none",
        "無": "none",
    }
    if key in aliases:
        return aliases[key]
    for element_id in ELEMENT_IDS:
        if key == element_id.casefold():
            return element_id
        if key == tr_enum("element", element_id, "ja", fallback=element_id).casefold():
            return element_id
        if key == tr_enum("element", element_id, "en", fallback=element_id).casefold():
            return element_id
    return fallback


def _character_entry_seed_instruction(seed_name: str = "", seed_description: str = "") -> str:
    lines: list[str] = []
    if str(seed_name or "").strip():
        lines.append(f"希望名: {str(seed_name).strip()}")
    if str(seed_description or "").strip():
        lines.append(f"希望説明: {str(seed_description).strip()}")
    if not lines:
        return ""
    return "ユーザー指定を優先して反映してください。\n" + "\n".join(lines)


def _character_entry_duplicate_guard(entries: Any, kind: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in _as_list(entries):
        if not isinstance(raw, dict):
            continue
        if kind == "skills":
            name = str(raw.get("name") or raw.get("skill") or raw.get("title") or "").strip()
        else:
            name = str(raw.get("name") or "").strip()
        description = str(
            raw.get("desc")
            if kind == "skills"
            else raw.get("desc") or ""
        ).strip()
        if not name and not description:
            continue
        item: dict[str, str] = {}
        if name:
            item["name"] = _short_text(name, 80)
        if description:
            item["desc" if kind == "traits" else "description"] = _short_text(description, 160)
        result.append(item)
    return result[:12]


def _normalise_skill(value: Any) -> dict[str, Any]:
    return normalise_combat_skill(value)


def _trait_entry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    trait = value
    name = str(trait.get("name") or "").strip()
    if not name:
        return {}
    return {"name": name, "desc": str(trait.get("desc") or "").strip()}


def _entry_power(value: Any, fallback: int = 1) -> int:
    if isinstance(value, dict):
        for key in ("power",):
            if value.get(key) not in (None, ""):
                return _entry_power(value.get(key), fallback=fallback)
        return max(SKILL_POWER_MIN, min(SKILL_POWER_MAX, int(fallback or 1)))
    text = str(value or "").strip().lower()
    if not text:
        return max(SKILL_POWER_MIN, min(SKILL_POWER_MAX, int(fallback or 1)))
    number = _safe_int(text, 0)
    if number:
        return max(SKILL_POWER_MIN, min(SKILL_POWER_MAX, number))
    mapping = {
        "very low": 1,
        "low": 1,
        "minor": 1,
        "small": 1,
        "medium": 3,
        "normal": 3,
        "high": 4,
        "major": 4,
        "very high": 5,
        "ultimate": 5,
        "legendary": 5,
        "weak": 1,
        "strong": 4,
    }
    for key, mapped in mapping.items():
        if key in text:
            return mapped
    if any(word in text for word in ("弱", "低", "小", "軽")):
        return 1
    if any(word in text for word in ("中", "標準", "普通")):
        return 3
    if any(word in text for word in ("強", "高", "大", "奥義", "必殺", "伝説")):
        return 5
    return max(SKILL_POWER_MIN, min(SKILL_POWER_MAX, int(fallback or 1)))


def _skill_power_from_text(skill: dict[str, Any]) -> int:
    text = json.dumps(skill, ensure_ascii=False).lower()
    if any(word in text for word in ("ultimate", "legendary", "decisive", "overturn", "奥義", "必殺", "伝説", "戦況をひっくり返")):
        return 5
    if any(word in text for word in ("powerful", "major", "large", "area", "aoe", "all", "revive", "death", "instant", "強力", "大", "全体", "蘇生", "即死")):
        return 4
    if any(word in text for word in ("support", "utility", "使い方次第", "応用")):
        return 3
    if any(word in text for word in ("low", "minor", "small", "weak", "軽", "小", "弱")):
        return 1
    return 2


def _skill_sp_floor(power: int) -> int:
    return {1: 2, 2: 4, 3: 7, 4: 11, 5: 16}.get(max(1, min(5, power)), 2)


def _entry_power_total(entries: list[dict[str, Any]]) -> int:
    return sum(_entry_power(entry) for entry in entries if isinstance(entry, dict))


def _is_player_power_actor(actor: Character) -> bool:
    if not isinstance(actor, Character):
        return False
    category = str(actor.category or "").lower()
    role = str(actor.role or "").lower()
    source = str(actor.flags.get("source") or actor.extra.get("source") or "").lower()
    return bool(actor.flags.get("is_player") or role == "player" or category == "player" or source.startswith("character_setup"))


def _actor_power_budget(actor: Character) -> int:
    if _is_player_power_actor(actor):
        return PLAYER_UNLIMITED_POWER_BUDGET
    for source in (getattr(actor, "extra", {}), getattr(actor, "flags", {})):
        if not isinstance(source, dict):
            continue
        for key in ("skill_power_budget", "power_budget", "ability_power_budget"):
            if source.get(key) not in (None, ""):
                return max(1, _safe_int(source.get(key), NPC_DEFAULT_POWER_BUDGET))
        for key in ("danger_level", "threat_level", "challenge_level", "level", "rank"):
            if source.get(key) not in (None, ""):
                level = _safe_int(source.get(key), 0)
                if level > 0:
                    return max(4, min(25, 5 + level // 2))
    text = " ".join(
        str(part or "").lower()
        for part in (
            getattr(actor, "category", ""),
            getattr(actor, "role", ""),
            getattr(actor, "description", ""),
            getattr(actor, "backstory", ""),
            getattr(actor, "personality", ""),
            getattr(actor, "extra", {}).get("archetype", "") if isinstance(getattr(actor, "extra", {}), dict) else "",
            getattr(actor, "extra", {}).get("rank", "") if isinstance(getattr(actor, "extra", {}), dict) else "",
            getattr(actor, "flags", {}).get("rank", "") if isinstance(getattr(actor, "flags", {}), dict) else "",
        )
    )
    if any(word in text for word in ("boss", "final", "legendary", "dragon", "demon lord", "ボス", "終盤", "魔王", "伝説")):
        return 22
    if any(word in text for word in ("elite", "veteran", "champion", "knight", "上級", "精鋭", "熟練")):
        return 16
    if any(word in text for word in ("mid", "experienced", "dangerous", "中盤", "危険")):
        return 12
    if any(word in text for word in ("early", "novice", "villager", "merchant", "traveler", "序盤", "初心者", "村人", "商人", "旅人")):
        return 6
    return NPC_DEFAULT_POWER_BUDGET


def _limit_power_entries_for_actor(
    actor: Character,
    entries: list[dict[str, Any]],
    *,
    used_power: int = 0,
) -> list[dict[str, Any]]:
    budget = _actor_power_budget(actor)
    if budget >= PLAYER_UNLIMITED_POWER_BUDGET:
        return entries
    result: list[dict[str, Any]] = []
    total = max(0, used_power)
    for entry in entries:
        power = _entry_power(entry)
        if total + power > budget:
            continue
        result.append(entry)
        total += power
    return result


def _normalise_actor_power_loadout(actor: Character) -> None:
    traits = [_trait_entry(item) for item in _as_list(getattr(actor, "traits", []))]
    traits = [trait for trait in traits if trait.get("name")]
    actor.traits = traits
    skills = [_normalise_skill(item) for item in _as_list(getattr(actor, "skills", []))]
    skills = [skill for skill in skills if skill.get("name")]
    actor.skills = _limit_power_entries_for_actor(actor, skills, used_power=0)


def _skill_power_instruction(character: Character) -> str:
    scale = (
        "強力度の目安: 1=あまり強力ではない、"
        "3=使い方次第で強力、"
        "5=これ1つで戦況をひっくり返せる可能性がある。"
    )
    if _is_player_power_actor(character):
        return (
            f"{scale} スキルはBPを消費しません。"
            "プレイヤーが自由に作れる要素なので、各スキルに power を1〜5で付けてください。"
        )
    budget = _actor_power_budget(character)
    used = _entry_power_total(character.skills)
    remaining = max(0, budget - used)
    return (
        f"{scale} このNPC/敵のスキル強力度合計上限は {budget} です。"
        f"既存分は {used}、追加可能な残りは {remaining} です。"
        "序盤や一般人は低く、終盤・精鋭・ボス級ほど高くしてください。"
    )


def _safe_asset_segment(value: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in str(value).strip())
    return cleaned or "unknown"


def _subnode_display_needs_fill(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.casefold()
    generic = {
        "objective",
        "quest_objective",
        "quest objective",
        "target",
        "destination",
        "依頼目標",
        "目的地",
        "目標地点",
    }
    if lowered in generic:
        return True
    if lowered.startswith(("quest:", "subarea:", "facility:", "capture:")):
        return True
    if re.fullmatch(r"[a-z0-9_:\-]+", lowered) and any(token in lowered for token in ("quest", "objective", "target", "node")):
        return True
    return False






























def _normalise_world_starting_location(world: WorldData, response: dict[str, Any] | None = None) -> None:
    original_start = str(world.starting_location or "").strip()
    if not original_start or original_start == "unknown":
        return
    payloads = _world_location_payloads(response or {})
    start_payload = next(
        (
            payload
            for payload in payloads
            if _world_location_name_key(_world_location_name_from_payload(payload)) == _world_location_name_key(original_start)
        ),
        {},
    )
    start_description = _world_location_description_from_payload(start_payload) if start_payload else ""
    start_kind = _infer_world_location_kind(start_payload, original_start, start_description)
    if _world_kind_is_settlement(start_kind) and not _looks_like_facility_location_name(original_start):
        location = world.ensure_location(original_start, start_description)
        location.flags["settlement"] = True
        location.extra["location_kind"] = "settlement"
        return

    settlement_payload = _starting_settlement_payload(payloads, original_start)
    if not settlement_payload:
        return
    settlement_name = _world_location_name_from_payload(settlement_payload)
    if not settlement_name or _world_location_name_key(settlement_name) == _world_location_name_key(original_start):
        return
    settlement_description = _world_location_description_from_payload(settlement_payload)
    old_location = world.locations.pop(original_start, None)
    settlement = world.ensure_location(settlement_name, settlement_description)
    settlement.flags["settlement"] = True
    settlement.extra["location_kind"] = "settlement"
    world.extra["raw_starting_location"] = original_start
    world.extra["initial_facility_name"] = original_start
    world.starting_location = settlement_name
    facility_description = start_description or (old_location.description if old_location else "")
    facilities = settlement.extra.get("facilities")
    if not isinstance(facilities, list):
        facilities = []
        settlement.extra["facilities"] = facilities
    facility_name = _clean_settlement_generated_text(original_start, settlement.name)
    if _is_reserved_settlement_facility_name(facility_name):
        return
    if not _facility_exists([item for item in facilities if isinstance(item, dict)], facility_name):
        record = _facility_record(facility_name, settlement.name, _facility_type_from_name(facility_name))
        record["description"] = _facility_description_from_payload(
            facility_description or str(record.get("description") or ""),
            settlement.name,
            facility_name,
        )
        record["source"] = "starting_location_normalizer"
        facilities.append(record)


def _starting_settlement_payload(payloads: list[dict[str, Any]], original_start: str) -> dict[str, Any] | None:
    candidates: list[tuple[int, dict[str, Any]]] = []
    start_key = _world_location_name_key(original_start)
    for index, payload in enumerate(payloads):
        name = _world_location_name_from_payload(payload)
        if not name or _world_location_name_key(name) == start_key:
            continue
        description = _world_location_description_from_payload(payload)
        kind = _infer_world_location_kind(payload, name, description)
        if not _world_kind_is_settlement(kind):
            continue
        score = index
        text = f"{name}\n{description}\n{json.dumps(payload, ensure_ascii=False, default=str)}".casefold()
        if any(word in text for word in ("start", "starting", "initial", "home", "拠点", "開始", "初期")):
            score -= 100
        if _same_base_location_name(name, original_start) or _same_base_location_name(original_start, name):
            score -= 50
        candidates.append((score, payload))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]












































def _fallback_generated_dungeon_boss_payload(
    location: LocationData,
    action: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    text = "\n".join(
        str(part or "")
        for part in (
            action,
            location.name,
            location.description,
            response.get("narration"),
            response.get("objective"),
        )
    )
    name = _generated_dungeon_boss_name_from_text(text) or f"{location.name}の守護者"
    description = _short_text(
        f"{location.name}の最奥部で待ち受ける強敵。{location.description or action}",
        260,
    )
    danger = max(5, _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0))
    return {
        "name": name,
        "role": "ダンジョンボス",
        "category": "boss",
        "gender": "none",
        "age": "unknown",
        "description": description,
        "personality": "侵入者の力と意志を試すように振る舞う。",
        "look": description,
        "hostile": True,
        "danger_level": danger,
        "level": _generated_dungeon_boss_level(location),
        "image_generation_prompt": [
            name,
            "fantasy dungeon boss",
            "final chamber guardian",
            "powerful presence",
        ],
        "aliases": [name, "ボス", "守護者"],
    }


def _generated_dungeon_boss_name_from_text(text: str) -> str:
    text = str(text or "")
    patterns = (
        r"([^\s、。,.「」『』（）()\[\]{}]{2,24})(?:が|は)(?:待つ|待って|待ち受け|鎮座|いる)",
        r"([^\s、。,.「」『』（）()\[\]{}]{1,18}の(?:女神|神|邪神|主|王|守護者))",
        r"(?:boss|guardian|deity|goddess|god|lord)[:：\s]+([A-Za-z0-9 _'\\-]{2,40})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip("「」『』 　")
            if value:
                return _clean_generated_name(value, "ダンジョンの守護者", kind="monster")
    return ""


def _generated_dungeon_boss_level(location: LocationData) -> int:
    danger = _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0)
    return max(5, min(NPC_MAX_LEVEL, 5 + danger * 2))
























def _subnode_map_hides_unvisited(location: LocationData) -> bool:
    if _is_settlement_location(location) and not _world_location_blocks_world_map_departure(location):
        return False
    return _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location)




def _settlement_crime_risk_multiplier(settlement: LocationData) -> float:
    if _as_bool(settlement.flags.get("crime_ignored")) or _as_bool(settlement.extra.get("crime_ignored")):
        return 0.0
    explicit = settlement.extra.get("crime_risk_multiplier", settlement.flags.get("crime_risk_multiplier"))
    if explicit not in (None, ""):
        return max(0.0, min(2.0, _safe_float(explicit, 1.0)))
    text = "\n".join(
        str(value or "")
        for value in (
            settlement.name,
            settlement.description,
            settlement.area,
            settlement.extra.get("security"),
            settlement.extra.get("law"),
            settlement.extra.get("atmosphere"),
        )
    ).casefold()
    multiplier = 1.0
    if any(word in text for word in ("lawless", "outlaw", "slum", "black market", "無法", "無秩序", "スラム", "闇市")):
        multiplier -= 0.6
    if any(word in text for word in ("guard", "garrison", "capital", "castle", "lawful", "strict", "衛兵", "守備隊", "城塞", "王都", "治安", "厳格")):
        multiplier += 0.5
    if any(word in text for word in ("holy", "temple", "church", "聖", "神殿", "寺院")):
        multiplier += 0.2
    return max(0.0, min(2.0, multiplier))


def _crime_severity(action: Any, response: Any) -> int:
    explicit = _crime_delta_from_payload(response)
    if explicit:
        return max(0, min(100, explicit))
    text = f"{action}\n{json.dumps(_strip_response_metadata(response), ensure_ascii=False, default=str) if isinstance(response, (dict, list)) else response}".casefold()
    if any(word in text for word in ("murder", "kill civilian", "kill npc", "homicide", "殺人", "殺害", "人殺し", "住民を殺", "店主を殺", "衛兵を殺")):
        return 100
    if any(word in text for word in ("robbery", "mug", "armed robbery", "強盗", "恐喝", "金を奪", "奪い取")):
        return 55
    if any(word in text for word in ("steal", "theft", "shoplift", "pickpocket", "盗む", "盗み", "窃盗", "万引", "スリ")):
        return 55
    if any(word in text for word in ("assault", "attack guard", "attack npc", "暴行", "襲う", "殴る", "斬りつけ", "攻撃する")):
        return 45
    if any(word in text for word in ("trespass", "break in", "lockpick", "不法侵入", "押し入", "鍵をこじ開け")):
        return 12
    return 0


def _crime_delta_from_payload(value: Any) -> int:
    if isinstance(value, list):
        return sum(_crime_delta_from_payload(item) for item in value)
    if not isinstance(value, dict):
        return 0
    for key in ("crime_delta", "criminality_delta", "wanted_delta", "crime_score_delta"):
        if key in value:
            return _safe_int(value.get(key), 0)
    total = 0
    for key in ("crime", "crime_effect", "crime_effects", "law_effect", "law_effects"):
        if key in value:
            total += _crime_delta_from_payload(value.get(key))
    effect_type = str(value.get("type") or value.get("kind") or value.get("name") or "").strip().lower()
    if effect_type in {"crime", "increase_crime", "criminality", "wanted"}:
        total += _safe_int(value.get("value", value.get("amount", 0)), 0)
    return total










def _unique_world_location_name(world: WorldData, base: str) -> str:
    name = str(base or "Location").strip() or "Location"
    if name not in world.locations:
        return name
    index = 2
    while f"{name} {index}" in world.locations:
        index += 1
    return f"{name} {index}"


def _nearby_dynamic_location_requested(action: str, proposed_location: str) -> bool:
    text = f"{action}\n{proposed_location}".lower()
    movement_words = (
        "go",
        "move",
        "travel",
        "head",
        "enter",
        "nearby",
        "around",
        "create",
        "generate",
        "discover",
        "探",
        "行",
        "向",
        "入",
        "近く",
        "周辺",
        "生成",
        "発見",
        "作",
        "生や",
    )
    location_words = (
        "dungeon",
        "cave",
        "ruin",
        "forest",
        "road",
        "crossroad",
        "coast",
        "mountain",
        "river",
        "plain",
        "tower",
        "mine",
        "temple",
        "shrine",
        "村",
        "街",
        "町",
        "洞窟",
        "迷宮",
        "森",
        "街道",
        "分岐路",
        "分かれ道",
        "海岸",
        "浜辺",
        "山",
        "川",
        "平原",
        "草原",
        "塔",
        "遺跡",
        "鉱山",
        "神殿",
        "寺院",
        "祠",
        "聖域",
    )
    return any(word in text for word in movement_words) and any(word in text for word in location_words)


def _teleport_movement_requested(response: dict[str, Any]) -> bool:
    if not isinstance(response, dict):
        return False
    text = " ".join(
        str(response.get(key) or "")
        for key in ("movement_type", "travel_type", "transport", "method", "process", "narration")
    ).lower()
    return any(word in text for word in ("teleport", "portal", "warp", "gate", "転移", "瞬間移動", "ポータル"))




def _is_settlement_location(location: LocationData) -> bool:
    if location.flags.get("settlement"):
        return True
    extra = location.extra if isinstance(location.extra, dict) else {}
    if extra.get("location_kind") in {"settlement", "town", "village", "city"}:
        return True
    return False


def _is_non_settlement_submap(world: WorldData, location_name: str) -> bool:
    name = str(location_name or "").strip()
    location = world.locations.get(name) if name else None
    if location and _is_settlement_location(location):
        return False
    if location and _is_facility_location(location):
        return False
    return _looks_like_non_settlement_area(name, location)


def _is_facility_location(location: LocationData) -> bool:
    if location.flags.get("facility"):
        return True
    extra = location.extra if isinstance(location.extra, dict) else {}
    if extra.get("facility") or extra.get("facility_name") or extra.get("facility_type"):
        return True
    location_kind = str(extra.get("location_kind") or "").strip().lower()
    return location_kind in {"facility", "shop", "inn", "guild", "temple", "clinic", "market"}


def _world_graph_node_is_facility(world: WorldData, node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    kind = str(node.get("kind") or node.get("type") or "").strip().lower()
    if kind in {"facility", "shop", "inn", "guild", "temple", "clinic", "market"}:
        return True
    name = str(node.get("name") or "").strip()
    location = world.locations.get(name)
    return bool(location and _is_facility_location(location))


def _looks_like_non_settlement_area(name: str, location: LocationData | None = None) -> bool:
    pieces = [_location_area_check_name(name)]
    if location:
        pieces.extend(
            [
                location.description,
                str(location.flags.get("location_kind") or ""),
                str(location.flags.get("type") or ""),
                str(location.flags.get("category") or ""),
            ]
        )
        extra = location.extra if isinstance(location.extra, dict) else {}
        pieces.extend(
            str(extra.get(key) or "")
            for key in (
                "location_kind",
                "kind",
                "type",
                "category",
                "biome",
                "terrain",
                "danger_level",
                "adventure_site",
                "quest_area",
            )
        )
    text = "\n".join(piece for piece in pieces if piece).lower()
    if not text:
        return False
    negative_markers = (
        "dungeon",
        "labyrinth",
        "cave",
        "cavern",
        "ruin",
        "ruins",
        "crypt",
        "catacomb",
        "sewer",
        "mine",
        "shaft",
        "tunnel",
        "lair",
        "den",
        "nest",
        "wilderness",
        "wild",
        "forest",
        "swamp",
        "marsh",
        "graveyard",
        "tomb",
        "battlefield",
        "hideout",
        "stronghold",
        "fortress",
        "maze",
        "ダンジョン",
        "迷宮",
        "地下迷宮",
        "洞窟",
        "洞穴",
        "洞",
        "遺跡",
        "廃墟",
        "地下道",
        "下水道",
        "坑道",
        "鉱山",
        "墓地",
        "墓所",
        "墓",
        "霊廟",
        "森",
        "森林",
        "沼",
        "湿地",
        "巣穴",
        "巣",
        "野営地",
        "荒野",
        "魔窟",
        "隠れ家",
        "砦",
        "要塞",
    )
    return any(marker in text for marker in negative_markers)


def _location_area_check_name(name: str) -> str:
    text = str(name or "").strip()
    if "/" not in text and "\\" not in text:
        return text
    parts = [part.strip() for part in re.split(r"[/\\]", text) if part.strip()]
    if len(parts) <= 1:
        return text
    return " / ".join(parts[1:])


def _collapse_same_location_subarea(world: WorldData, current_location: str, proposed_location: str) -> str:
    current = str(current_location or "").strip()
    proposed = str(proposed_location or "").strip()
    if not current or not proposed or proposed == current:
        return proposed or current
    current_data = world.locations.get(current)
    proposed_data = world.locations.get(proposed)
    if _is_dungeon_subarea_name(current, proposed):
        return current
    if proposed_data and current_data and _is_dungeon_location(current_data) and _same_base_location_name(current, proposed):
        return current
    for name, location in world.locations.items():
        if name == proposed and proposed_data:
            continue
        if _is_dungeon_location(location) and _is_dungeon_subarea_name(name, proposed):
            return name
    return proposed


def _add_facility_payload_to_settlement(world: WorldData, name: str, description: str, facility_type: str = "") -> bool:
    settlement = _first_settlement_location(world)
    if settlement is None:
        return False
    name = _clean_settlement_generated_text(name, settlement.name)
    if not name or _is_reserved_settlement_facility_name(name):
        return False
    facilities = settlement.extra.get("facilities")
    if not isinstance(facilities, list):
        facilities = []
    if _facility_exists([item for item in facilities if isinstance(item, dict)], name):
        settlement.extra["facilities"] = facilities
        return True
    record = _facility_record(name, settlement.name, facility_type)
    record["description"] = _facility_description_from_payload(
        description or str(record.get("description") or ""),
        settlement.name,
        name,
    )
    record["source"] = "world_location_payload"
    facilities.append(record)
    settlement.extra["facilities"] = facilities
    settlement.flags["settlement"] = True
    settlement.extra["location_kind"] = "settlement"
    return True


def _first_settlement_location(world: WorldData) -> LocationData | None:
    if world.starting_location:
        location = world.locations.get(world.starting_location)
        if location and _is_settlement_location(location):
            return location
    for location in world.locations.values():
        if _is_settlement_location(location):
            return location
    if world.starting_location:
        location = world.locations.get(world.starting_location)
        if location and not _looks_like_facility_location_name(location.name) and not _is_dungeon_location(location):
            location.flags["settlement"] = True
            location.extra["location_kind"] = "settlement"
            return location
    return None


def _existing_dungeon_location_for_subarea(world: WorldData, proposed_name: str) -> str:
    proposed = str(proposed_name or "").strip()
    if not proposed:
        return ""
    for name, location in world.locations.items():
        if name == proposed:
            continue
        if _is_dungeon_location(location) and _is_dungeon_subarea_name(name, proposed):
            return name
    return ""


def _record_location_subarea(world: WorldData, parent_name: str, subarea_name: str, description: str = "") -> None:
    parent = world.locations.get(parent_name)
    if parent is None:
        return
    subareas = parent.extra.setdefault("subareas", [])
    if not isinstance(subareas, list):
        subareas = []
        parent.extra["subareas"] = subareas
    normalized = _normalize_location_subarea_name(subarea_name)
    for item in subareas:
        if isinstance(item, dict) and _normalize_location_subarea_name(str(item.get("name") or "")) == normalized:
            if description and not item.get("description"):
                item["description"] = description
            return
    subareas.append({"name": subarea_name, "description": description})


def _is_dungeon_location(location: LocationData | None) -> bool:
    if location is None:
        return False
    extra = location.extra if isinstance(location.extra, dict) else {}
    kind = str(extra.get("location_kind") or extra.get("kind") or "").strip().lower()
    if kind in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair"}:
        return True
    text = "\n".join(
        str(value or "")
        for value in (
            location.name,
            location.description,
            extra.get("location_kind"),
            extra.get("terrain"),
            extra.get("category"),
        )
    ).casefold()
    return any(
        marker in text
        for marker in (
            "dungeon",
            "cave",
            "cavern",
            "ruin",
            "labyrinth",
            "mine",
            "crypt",
            "lair",
            "洞窟",
            "洞穴",
            "迷宮",
            "遺跡",
            "鉱山",
        )
    )


def _is_dungeon_subarea_name(base_name: str, proposed_name: str) -> bool:
    base = str(base_name or "").strip()
    proposed = str(proposed_name or "").strip()
    if not base or not proposed or proposed == base:
        return False
    if not _same_base_location_name(base, proposed):
        return False
    tail = proposed.replace(base, "", 1).strip(" /\\-:：・　")
    tail_text = tail.casefold()
    return any(
        marker in tail_text
        for marker in (
            "entrance",
            "inside",
            "interior",
            "inner",
            "depth",
            "deep",
            "入口",
            "入り口",
            "内部",
            "内側",
            "奥",
            "深部",
            "下層",
            "上層",
            "中層",
        )
    )


def _same_base_location_name(base_name: str, proposed_name: str) -> bool:
    base = _normalize_location_subarea_name(base_name)
    proposed = _normalize_location_subarea_name(proposed_name)
    return bool(base and proposed and (proposed.startswith(base) or base.startswith(proposed)))


def _normalize_location_subarea_name(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = re.split(r"[/\\]", text)[0].strip()
    for marker in (
        "入口",
        "入り口",
        "内部",
        "内側",
        "奥",
        "深部",
        "下層",
        "上層",
        "中層",
        "entrance",
        "inside",
        "interior",
        "inner",
        "depths",
        "depth",
        "deep",
    ):
        text = text.replace(marker, "")
    return re.sub(r"[\s　・/\\:：\\-]+", "", text)


def _facility_exit_requested(action: str, response: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            action,
            response.get("location"),
            response.get("narration"),
            response.get("text"),
        )
    ).casefold()
    return any(
        marker in text
        for marker in (
            "leave",
            "exit",
            "outside",
            "street",
            "戻る",
            "出る",
            "外",
            "通り",
            "広場",
            "街中",
        )
    )


def _settlement_location_for_name(world: WorldData, location_name: str) -> LocationData | None:
    name = str(location_name or "").strip()
    if _is_non_settlement_submap(world, name):
        return None
    location = world.locations.get(name)
    if location and _is_settlement_location(location):
        return location
    parent_name = _infer_settlement_parent_name(world, name)
    if parent_name:
        parent = world.locations.get(parent_name)
        if parent and _is_settlement_location(parent):
            return parent
    return None


def _infer_settlement_parent_name(world: WorldData, location_name: str) -> str:
    name = str(location_name or "").strip()
    if not name:
        return ""
    if _is_non_settlement_submap(world, name):
        return ""
    location = world.locations.get(name)
    if location:
        parent_name = str(location.extra.get("parent_location") or "").strip()
        if parent_name and _is_settlement_location(world.locations.get(parent_name, LocationData(name=parent_name))):
            return parent_name
        area = str(location.area or "").strip()
        if area:
            area_location = world.locations.get(area)
            if area_location and _is_settlement_location(area_location):
                return area
    for settlement_name, settlement in sorted(world.locations.items(), key=lambda item: len(item[0]), reverse=True):
        if settlement_name == name or not _is_settlement_location(settlement):
            continue
        if name.startswith(f"{settlement_name} /") or name.startswith(f"{settlement_name}/"):
            return settlement_name
        if name.startswith(settlement_name) and _looks_like_facility_location_name(name):
            return settlement_name
    return ""


def _link_location_to_settlement(world: WorldData, location_name: str, settlement_name: str) -> None:
    name = str(location_name or "").strip()
    parent_name = str(settlement_name or "").strip()
    if not name or not parent_name:
        return
    if _is_non_settlement_submap(world, name):
        return
    settlement = world.locations.get(parent_name)
    if not settlement or not _is_settlement_location(settlement):
        inferred = _infer_settlement_parent_name(world, name)
        parent_name = inferred or parent_name
        settlement = world.locations.get(parent_name)
    if not settlement or not _is_settlement_location(settlement):
        return
    if name == parent_name:
        settlement.flags["settlement"] = True
        settlement.extra["location_kind"] = "settlement"
        return
    location = world.ensure_location(name)
    location.area = location.area or parent_name
    location.extra["parent_location"] = parent_name
    location.flags["settlement_child"] = True
    facility = _facility_for_location(settlement, name)
    if facility:
        location.flags["facility"] = True
        location.extra["facility_name"] = str(facility.get("name") or "")
        location.extra["facility_type"] = str(facility.get("type") or _facility_type_from_name(str(facility.get("name") or "")))
        location.extra["facility"] = dict(facility)
    world.extra["initial_settlement_location"] = parent_name


def _location_is_guild(world: WorldData, location_name: str) -> bool:
    name = str(location_name or "").strip()
    if _is_non_settlement_submap(world, name):
        return False
    location = world.locations.get(name)
    if location and str(location.extra.get("facility_type") or "").lower() == "guild":
        return True
    settlement = _settlement_location_for_name(world, name)
    if settlement:
        facility = _facility_for_location(settlement, name)
        if facility and str(facility.get("type") or "").lower() == "guild":
            return True
    return bool(location and _looks_like_guild_name(location.name))


def _facility_for_location(settlement: LocationData, location_name: str) -> dict[str, Any] | None:
    name = str(location_name or "").strip()
    if not name:
        return None
    if name == settlement.name:
        return None
    normalized_name = _normalize_facility_name(name)
    location_tail = re.split(r"[/\\]", name)[-1].strip()
    normalized_tail = _normalize_facility_name(location_tail)
    facilities = settlement.extra.get("facilities")
    if not isinstance(facilities, list):
        return None
    for raw in facilities:
        if not isinstance(raw, dict):
            continue
        facility_name = str(raw.get("name") or raw.get("facility_name") or raw.get("title") or "").strip()
        facility_location = str(raw.get("location_name") or f"{settlement.name} / {facility_name}").strip()
        if facility_location != settlement.name and (name == facility_location or _normalize_facility_name(facility_location) == normalized_name):
            return raw
        if facility_name and _normalize_facility_name(facility_name) == normalized_tail:
            return raw
    return None


def _facility_name_from_sub_location(settlement: LocationData, location_name: str) -> str:
    name = str(location_name or "").strip()
    if not name or name == settlement.name:
        return ""
    tail = re.split(r"[/\\]", name)[-1].strip()
    facilities = settlement.extra.get("facilities")
    if not isinstance(facilities, list):
        return ""
    for raw in facilities:
        if not isinstance(raw, dict):
            continue
        facility_name = str(raw.get("name") or raw.get("facility_name") or raw.get("title") or "").strip()
        if facility_name and (_facility_name_matches(facility_name, tail) or _facility_name_matches(facility_name, name)):
            return facility_name
        for alias in _as_list(raw.get("aliases")):
            if str(alias or "").strip() and (_facility_name_matches(str(alias), tail) or _facility_name_matches(str(alias), name)):
                return facility_name or str(alias)
    requested_type = _facility_type_from_name(name)
    if requested_type != "facility":
        for raw in facilities:
            if not isinstance(raw, dict):
                continue
            facility_type = str(raw.get("type") or _facility_type_from_name(str(raw.get("name") or ""))).strip().lower()
            if facility_type == requested_type:
                return str(raw.get("name") or raw.get("facility_name") or raw.get("title") or "").strip()
    return ""


def _augment_location_choices_for_world(
    world: WorldData,
    location_name: str,
    choices: list[str],
    *,
    active_quest: bool,
    can_move: bool = False,
    quest_report_ready: bool = False,
) -> list[str]:
    result = list(choices)
    if can_move:
        result.insert(0, MOVE_CHOICE_LABEL)
    if quest_report_ready:
        result = [choice for choice in result if str(choice).strip() != QUEST_REPORT_CHOICE_LABEL]
        result.insert(0, QUEST_REPORT_CHOICE_LABEL)
    if active_quest:
        result = [choice for choice in result if str(choice).strip() != QUEST_ABANDON_CHOICE_LABEL]
        insert_at = 1 if result and result[0] == QUEST_REPORT_CHOICE_LABEL else 0
        result.insert(insert_at, QUEST_ABANDON_CHOICE_LABEL)
    elif _location_is_guild(world, location_name) and not active_quest:
        result = [choice for choice in result if not _is_direct_quest_accept_choice(choice)]
        result.insert(0, QUEST_BOARD_CHOICE_LABEL)
    return _exploration_choices(result)


def _is_direct_quest_accept_choice(choice: Any) -> bool:
    text = str(choice or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    if text == QUEST_BOARD_CHOICE_LABEL or "掲示板" in text or "quest board" in lowered or "bulletin" in lowered:
        return False
    accept_markers = ("受け", "受注", "引き受け", "引受", "請け", "accept", "take quest", "take the quest")
    quest_markers = ("依頼", "クエスト", "仕事", "quest", "request", "job")
    if any(marker in text for marker in accept_markers[:5]) and any(marker in text for marker in quest_markers[:3]):
        return True
    return any(marker in lowered for marker in accept_markers[5:]) and any(marker in lowered for marker in quest_markers[3:])


def _clean_settlement_generated_text(value: Any, settlement_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    replacement = str(settlement_name or "").strip() or "\u3053\u306e\u62e0\u70b9"
    replacements = (
        ("\u5192\u967a\u306e\u958b\u59cb\u5730\u70b9", f"{replacement}\u306e\u5916\u3078\u7d9a\u304f\u5834\u6240"),
        ("\u521d\u671f\u5730\u70b9\u306e\u8857", replacement),
        ("\u521d\u671f\u5730\u70b9\u306e\u753a", replacement),
        ("\u521d\u671f\u5730\u70b9\u306e\u6751", replacement),
        ("\u6700\u521d\u306e\u8857", replacement),
        ("\u6700\u521d\u306e\u753a", replacement),
        ("\u6700\u521d\u306e\u6751", replacement),
        ("\u958b\u59cb\u62e0\u70b9", replacement),
        ("\u521d\u671f\u62e0\u70b9", replacement),
        ("\u521d\u671f\u5730\u70b9", replacement),
        ("\u30b9\u30bf\u30fc\u30c8\u5730\u70b9", replacement),
        ("\u958b\u59cb\u5730\u70b9", replacement),
    )
    for needle, replacement_text in replacements:
        text = text.replace(needle, replacement_text)
    return text.strip()


def _clean_settlement_structure_value(value: Any, settlement_name: str) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        reserved_keys = {"gate", "gates", "entrance", "entrances", "plaza", "plazas", "central_plaza"}
        for key, item in value.items():
            if str(key).strip().lower() in reserved_keys:
                continue
            next_value = _clean_settlement_structure_value(item, settlement_name)
            if next_value in ("", [], {}):
                continue
            cleaned[key] = next_value
        return cleaned
    if isinstance(value, list):
        cleaned_items = []
        for item in value:
            next_value = _clean_settlement_structure_value(item, settlement_name)
            if next_value in ("", [], {}):
                continue
            cleaned_items.append(next_value)
        return cleaned_items
    if isinstance(value, str):
        text = _clean_settlement_generated_text(value, settlement_name)
        return "" if _is_reserved_settlement_facility_name(text) else text
    return value


def _is_reserved_settlement_facility_name(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    normalized = _normalize_facility_name(text)
    if not normalized:
        return False
    exact_names = (
        "\u4e2d\u592e\u5e83\u5834",
        "\u5e83\u5834",
        "\u9580",
        "\u6b63\u9580",
        "\u57ce\u9580",
        "\u5165\u53e3",
        "\u5165\u308a\u53e3",
        "\u51fa\u5165\u53e3",
        "\u753a\u306e\u5165\u308a\u53e3",
        "\u8857\u306e\u5165\u308a\u53e3",
        "\u6751\u306e\u5165\u308a\u53e3",
        "gate",
        "gates",
        "entrance",
        "entry",
        "plaza",
        "centralplaza",
    )
    reserved_exact = {_normalize_facility_name(name) for name in exact_names}
    if normalized in reserved_exact:
        return True
    reserved_fragments = (
        "\u4e2d\u592e\u5e83\u5834",
        "\u5165\u308a\u53e3",
        "\u5165\u53e3",
        "\u51fa\u5165\u53e3",
        "\u6b63\u9580",
        "\u57ce\u9580",
        "\u9580\u756a",
        "\u9580\u524d",
        "centralplaza",
        "entrance",
        "gateway",
        "gatehouse",
        "plaza",
    )
    if any(_normalize_facility_name(fragment) in normalized for fragment in reserved_fragments):
        return True
    return normalized == "\u9580" or normalized.startswith("\u9580") or normalized.endswith("\u9580")


def _facility_names_from_structure(value: Any) -> list[str]:
    names: list[str] = []
    if isinstance(value, dict):
        for key in ("facilities", "spots", "shops", "districts", "landmarks", "places", "buildings"):
            names.extend(_facility_names_from_structure(value.get(key)))
        for key, item in value.items():
            if key in {"core", "center", "name"} and isinstance(item, str):
                names.append(item)
    elif isinstance(value, list):
        for item in value:
            names.extend(_facility_names_from_structure(item))
    elif isinstance(value, str):
        text = value.strip()
        if text and not _is_reserved_settlement_facility_name(text):
            names.append(text)
    return _dedupe_strs(names)


def _shop_facility_display_name(name: str, facility_type: str, settlement_name: str, index: int = 0) -> str:
    clean_name = str(name or "").strip()
    resolved_type = str(facility_type or _facility_type_from_name(clean_name)).strip().lower()
    if resolved_type not in SHOP_FACILITY_TYPES:
        return clean_name
    normalized = _normalize_facility_name(clean_name)
    generic_names = {_normalize_facility_name(item) for item in GENERIC_SHOP_FACILITY_NAMES}
    if clean_name and normalized not in generic_names:
        return clean_name
    bank = SHOP_FACILITY_NAME_BANK.get(resolved_type) or SHOP_FACILITY_NAME_BANK["general_store"]
    rng = random.Random(f"facility-shop-name:{settlement_name}:{resolved_type}:{clean_name}:{index}")
    suffix = bank[rng.randrange(len(bank))]
    prefix = str(settlement_name or "").strip()
    return f"{prefix}の{suffix}" if prefix else suffix


def _facility_aliases(original_name: str, display_name: str, facility_type: str) -> list[str]:
    aliases = []
    for value in (original_name, _shop_type_generic_name(facility_type)):
        text = str(value or "").strip()
        if text and not _facility_name_matches(text, display_name) and text not in aliases:
            aliases.append(text)
    return aliases


def _shop_type_generic_name(facility_type: str) -> str:
    return {
        "blacksmith": "鍛冶屋",
        "black_market": "闇商店",
        "apothecary": "薬品店",
        "food_store": "食料店",
        "material_store": "素材店",
        "general_store": "雑貨店",
        "magic_store": "魔術店",
        "junk_store": "ジャンク店",
        "town_hall": "役場",
        "shop": "商店",
        "market": "市場",
    }.get(str(facility_type or "").strip().lower(), "")


def _facility_record_matches_requested(facility: dict[str, Any], requested: str) -> bool:
    requested_type = _facility_type_from_name(requested)
    facility_type = str(facility.get("type") or _facility_type_from_name(str(facility.get("name") or ""))).strip().lower()
    if _facility_name_matches(str(facility.get("name") or ""), requested):
        return True
    aliases = facility.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if _facility_name_matches(str(alias or ""), requested):
                return True
    return requested_type != "facility" and requested_type == facility_type


def _facility_description_from_payload(value: Any, settlement_name: str, facility_name: str) -> str:
    text = _clean_settlement_generated_text(value, settlement_name)
    if _is_placeholder_facility_description(text, settlement_name, facility_name):
        return ""
    return text


def _is_placeholder_facility_description(description: Any, settlement_name: str, facility_name: str) -> bool:
    text = str(description or "").strip()
    if not text:
        return False
    if any(marker in text for marker in ("未命名の街", "未命名の町", "未命名の村", "未命名の都市", "未命名の集落")):
        return True
    facility = str(facility_name or "").strip()
    settlement = str(settlement_name or "").strip()
    if not facility:
        return False
    generic_forms = {
        f"{settlement}にある{facility}",
        f"{settlement}にある{facility}。",
        f"{facility}は{settlement}にある施設",
        f"{facility}は{settlement}にある施設。",
    }
    return text in generic_forms


def _facility_record(name: str, settlement_name: str, facility_type: str = "") -> dict[str, Any]:
    name = _clean_settlement_generated_text(name, settlement_name)
    resolved_type = facility_type or _facility_type_from_name(name)
    original_name = str(name or "").strip()
    display_name = _shop_facility_display_name(original_name, resolved_type, settlement_name)
    return {
        "name": display_name,
        "type": resolved_type,
        "description": "",
        "npc_name": "",
        "npc_role": _default_facility_role(resolved_type),
        "location_name": settlement_name,
        "sub_location": display_name,
        "source": "create_settlement_detail",
        "aliases": _facility_aliases(original_name, display_name, resolved_type),
    }


def _facility_keeper_fields(
    raw: dict[str, Any],
    settlement_name: str,
    facility_name: str,
    facility_description: str = "",
) -> dict[str, str]:
    npc = raw.get("npc") if isinstance(raw.get("npc"), dict) else {}
    result = {
        "npc_gender": str(raw.get("npc_gender") or npc.get("gender") or raw.get("gender") or "").strip(),
        "npc_age": str(raw.get("npc_age") or npc.get("age") or raw.get("age") or "").strip(),
        "npc_look": str(
            raw.get("npc_look")
            or raw.get("npc_appearance")
            or npc.get("look")
            or npc.get("appearance")
            or ""
        ).strip(),
        "npc_personality": str(
            raw.get("npc_personality")
            or npc.get("personality")
            or ""
        ).strip(),
    }
    for key in ("npc_look", "npc_personality"):
        value = _clean_settlement_generated_text(result.get(key) or "", settlement_name)
        if _same_generated_facility_and_keeper_text(value, facility_description, facility_name):
            value = ""
        result[key] = value
    return result


def _same_generated_facility_and_keeper_text(value: str, facility_description: str, facility_name: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    description = str(facility_description or "").strip()
    if description and text == description:
        return True
    return bool(facility_name and text == str(facility_name).strip())


def _facility_exists(facilities: list[dict[str, Any]], name: str) -> bool:
    return any(
        _facility_record_matches_requested(item, name) if isinstance(item, dict) else False
        for item in facilities
    )


def _facility_name_matches(existing: str, requested: str) -> bool:
    left = _normalize_facility_name(existing)
    right = _normalize_facility_name(requested)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _normalize_facility_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s　「」『』\"'・/\\:_-]+", "", text)
    return text


def _facility_type_from_name(name: str) -> str:
    text = str(name or "").lower()
    if _looks_like_guild_name(name):
        return "guild"
    direct_mapping = (
        ("town_hall", ("town hall", "city hall", "municipal", "役場", "市庁舎", "行政庁", "役所")),
        ("black_market", ("black market", "black_market", "闇商店", "闇市", "裏市場")),
        ("blacksmith", ("blacksmith", "smith", "weapon shop", "armor shop", "鍛冶", "武具", "武器", "防具")),
        ("apothecary", ("apothecary", "potion", "medicine shop", "薬品店", "薬屋", "薬草", "回復")),
        ("food_store", ("food store", "grocery", "食料店", "食料", "食材")),
        ("material_store", ("material store", "素材店", "素材", "鉱石", "材料")),
        ("magic_store", ("magic store", "magic shop", "scroll", "魔術店", "魔法店", "巻物")),
        ("general_store", ("general store", "雑貨店", "よろず屋", "道具屋")),
        ("junk_store", ("junk store", "junk", "ジャンク店", "がらくた", "壊れ物")),
    )
    for facility_type, needles in direct_mapping:
        if any(needle in text for needle in needles):
            return facility_type
    mapping = (
        ("blacksmith", ("鍛冶", "武器", "防具", "smith", "blacksmith", "weapon", "armor")),
        ("shop", ("道具", "雑貨", "商店", "市場", "market", "shop", "store")),
        ("inn", ("宿", "inn", "lodging")),
        ("tavern", ("酒場", "tavern", "bar")),
        ("temple", ("教会", "神殿", "寺院", "church", "temple", "shrine")),
        ("clinic", ("診療", "病院", "薬", "clinic", "hospital", "apothecary")),
        ("library", ("図書", "library")),
        ("stable", ("厩舎", "馬小屋", "stable")),
        ("bath", ("浴場", "bath")),
        ("town_hall", ("役場", "市庁舎", "行政庁", "役所", "town hall", "city hall", "municipal")),
    )
    for facility_type, needles in mapping:
        if any(needle in text for needle in needles):
            return facility_type
    return "facility"


def _looks_like_guild_name(name: str) -> bool:
    text = str(name or "").lower()
    return any(word in text for word in ("guild", "adventurer", "quest board", "ギルド", "冒険者", "依頼掲示板"))


def _default_facility_role(facility_type: str) -> str:
    modern_roles = {
        "black_market": "闇商人",
        "apothecary": "薬師",
        "food_store": "食料店主",
        "material_store": "素材商",
        "general_store": "雑貨店主",
        "magic_store": "魔術商",
        "junk_store": "ジャンク屋",
        "town_hall": "役場職員",
    }
    normalized_type = str(facility_type or "").strip().lower()
    if normalized_type in modern_roles:
        return modern_roles[normalized_type]
    return {
        "guild": "ギルド受付",
        "blacksmith": "鍛冶職人",
        "shop": "店主",
        "inn": "宿の主人",
        "tavern": "酒場の主人",
        "temple": "司祭",
        "clinic": "治療師",
        "library": "司書",
        "stable": "馬丁",
        "bath": "番台",
        "town_hall": "役場職員",
    }.get(str(facility_type or ""), "施設の担当者")


def _default_facility_npc_name(facility_name: str, facility_type: str) -> str:
    role = _default_facility_role(facility_type)
    clean = str(facility_name or "").strip() or "施設"
    return f"{clean}の{role}"


def _default_facility_npc_look(facility_name: str, facility_type: str, role: str = "") -> str:
    facility = str(facility_name or "").strip()
    role_text = str(role or _default_facility_role(facility_type)).strip()
    templates = {
        "guild": "整えた受付服と書類鞄を身につけ、旅人の出入りを落ち着いて見渡している人物。",
        "blacksmith": "煤のついた作業着と厚い革手袋を身につけ、鍛冶場の熱に慣れた力強い職人。",
        "black_market": "暗色の外套で顔を半ば隠し、値踏みするような鋭い視線を持つ取引人。",
        "apothecary": "薬草の香りが染みた前掛けをつけ、小瓶と調合道具を手元に並べている薬師。",
        "food_store": "清潔な前掛けと袖まくりの服装で、食材の鮮度を確かめている店主。",
        "material_store": "丈夫な作業服に道具袋を下げ、素材の傷や質を見抜く目を持つ商人。",
        "general_store": "棚札と帳簿を手に、旅人向けの品を手早く並べ替えている店主。",
        "magic_store": "古い刺繍入りのローブをまとい、巻物や触媒を慎重に扱う魔術商。",
        "junk_store": "修理跡の多い外套を羽織り、壊れた道具の価値を見抜く目を持つ店主。",
        "town_hall": "整った事務服を着て、印章と書類を抱えながら来訪者に対応する職員。",
        "shop": "店の雰囲気に合った実用的な服装で、品物と客の様子をよく見ている店主。",
        "market": "活気ある市場向けの身軽な服装で、品物を示しながら客を呼び込む商人。",
    }
    base = templates.get(str(facility_type or "").strip().lower(), "施設の仕事に合った身なりで、来訪者に対応している人物。")
    if facility and role_text:
        return f"{facility}で働く{role_text}。{base}"
    if facility:
        return f"{facility}で働いている。{base}"
    return base


def _default_facility_npc_personality(facility_name: str, facility_type: str, role: str = "") -> str:
    templates = {
        "guild": "情報整理に長け、冒険者には事務的だが面倒見よく接する。",
        "blacksmith": "頑固で職人気質だが、装備を預ける相手には誠実に向き合う。",
        "black_market": "用心深く疑り深いが、価値を認めた相手とは取引を惜しまない。",
        "apothecary": "観察力があり、怪我や体調の変化にすぐ気づく慎重な性格。",
        "food_store": "世話好きで話しやすく、旅人の空腹や疲れにも目ざとい。",
        "material_store": "実利的で目利きに自信があり、素材の扱いには厳しい。",
        "general_store": "客の要望を聞き分けるのが早く、必要な品を現実的に勧める。",
        "magic_store": "知識欲が強く、珍しい品や術式の話になると饒舌になる。",
        "town_hall": "規則を重んじるが、困っている住民や旅人には手順を丁寧に説明する。",
        "shop": "商売熱心で、客の財布と必要品の両方を見ながら勧め方を変える。",
        "market": "明るく押しが強いが、常連には気前よく接する。",
    }
    return templates.get(str(facility_type or "").strip().lower(), "仕事には真面目で、施設を訪れる相手をよく観察して対応する。")


def _facility_request_from_action(action: str, facilities: list[dict[str, Any]]) -> str:
    text = str(action or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    movement = any(word in lowered or word in text for word in MOVEMENT_KEYWORDS)
    if not movement:
        return ""
    for facility in facilities:
        name = str(facility.get("name") or "")
        if name and name in text:
            return name
    for keyword in FACILITY_KEYWORDS:
        if keyword and (keyword.lower() in lowered or keyword in text):
            return _canonical_facility_name(keyword)
    match = re.search(r"(.{2,24}?)(?:へ|に)(?:行く|向かう|入る|寄る|訪ねる)", text)
    if match:
        candidate = match.group(1).strip("「」『』 　")
        if candidate and _looks_like_facility_term(candidate):
            return candidate
    return ""


def _facility_request_from_creation_action(action: str, facilities: list[dict[str, Any]]) -> str:
    text = str(action or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    creation = any(word in lowered or word in text for word in ("作", "建", "開", "設け", "用意", "追加", "生成", "欲しい", "必要", "request", "create", "build", "add"))
    if not creation:
        return ""
    for facility in facilities:
        name = str(facility.get("name") or "")
        if name and name in text:
            return name
    for keyword in FACILITY_KEYWORDS:
        if keyword and (keyword.lower() in lowered or keyword in text):
            return _canonical_facility_name(keyword)
    match = re.search(r"(.{2,24}?)(?:を|が|の)?(?:作る|建てる|開く|設ける|用意|追加|生成|欲しい|必要)", text)
    if match:
        candidate = match.group(1).strip("「」『』 　")
        if candidate and _looks_like_facility_term(candidate):
            return candidate
    return ""


def _looks_like_facility_term(value: str) -> bool:
    text = str(value or "").strip()
    lowered = text.lower()
    if any(keyword.lower() in lowered or keyword in text for keyword in FACILITY_KEYWORDS):
        return True
    return text.endswith(("屋", "店", "館", "院", "場", "所", "堂", "港", "局", "ギルド", "掲示板"))


def _canonical_facility_name(keyword: str) -> str:
    text = str(keyword or "")
    lowered = text.lower()
    if any(word in lowered or word in text for word in ("town hall", "city hall", "municipal", "役場", "市庁舎", "役所")):
        return "役場"
    if any(word in lowered or word in text for word in ("black market", "black_market", "闇商店", "闇市", "裏市場")):
        return "闇商店"
    if any(word in lowered or word in text for word in ("apothecary", "potion", "medicine shop", "薬品店", "薬屋", "薬草")):
        return "薬品店"
    if any(word in lowered or word in text for word in ("food store", "grocery", "食料店", "食料", "食材")):
        return "食料店"
    if any(word in lowered or word in text for word in ("material store", "素材店", "素材", "鉱石", "材料")):
        return "素材店"
    if any(word in lowered or word in text for word in ("magic store", "magic shop", "scroll", "魔術店", "魔法店", "巻物")):
        return "魔術店"
    if any(word in lowered or word in text for word in ("general store", "雑貨店", "よろず屋")):
        return "雑貨店"
    if any(word in lowered or word in text for word in ("guild", "adventurer", "ギルド", "冒険者", "依頼掲示板")):
        return DEFAULT_GUILD_NAME
    if any(word in lowered or word in text for word in ("blacksmith", "smith", "weapon", "armor", "鍛冶", "武器", "防具")):
        return "鍛冶屋"
    if any(word in lowered or word in text for word in ("inn", "宿")):
        return "宿屋"
    if any(word in lowered or word in text for word in ("tavern", "bar", "酒場")):
        return "酒場"
    if any(word in lowered or word in text for word in ("temple", "church", "shrine", "教会", "神殿", "寺院")):
        return "神殿"
    if any(word in lowered or word in text for word in ("clinic", "hospital", "apothecary", "診療", "病院", "薬")):
        return "診療所"
    if any(word in lowered or word in text for word in ("library", "図書")):
        return "図書館"
    if any(word in lowered or word in text for word in ("stable", "厩舎", "馬小屋")):
        return "厩舎"
    if any(word in lowered or word in text for word in ("market", "shop", "store", "市場", "店", "道具", "雑貨")):
        return "道具屋"
    return text


















def _town_hall_home_plan_from_action(action: str) -> tuple[int, int] | None:
    text = str(action or "")
    lowered = text.lower()
    for cost in sorted(PLAYER_HOME_TOWN_HALL_PLANS, reverse=True):
        if str(cost) in lowered or f"{cost}gold" in lowered.replace(" ", "") or f"{cost}g" in lowered.replace(" ", ""):
            return cost, PLAYER_HOME_TOWN_HALL_PLANS[cost]
    if any(word in text for word in ("高級", "豪華", "最高", "10000")):
        return 10000, PLAYER_HOME_TOWN_HALL_PLANS[10000]
    if any(word in text for word in ("標準", "普通", "1000")):
        return 1000, PLAYER_HOME_TOWN_HALL_PLANS[1000]
    if any(word in text for word in ("安い", "小さ", "最低", "500")):
        return 500, PLAYER_HOME_TOWN_HALL_PLANS[500]
    return None


def _loose_name_match(left: str, right: str) -> bool:
    left_text = "".join(str(left or "").casefold().split())
    right_text = "".join(str(right or "").casefold().split())
    if not left_text or not right_text:
        return False
    return left_text == right_text or left_text in right_text or right_text in left_text


def _compact_item_for_ai(item: dict[str, Any]) -> dict[str, Any]:
    normalised = normalise_item(item)
    data = {
        "name": normalised.get("name"),
        "category": normalised.get("category"),
        "description": normalised.get("description"),
        "quantity": normalised.get("quantity"),
        "rarity": normalised.get("rarity"),
        "value": normalised.get("value"),
        "use_effect": normalised.get("use_effect"),
        "power": normalised.get("power"),
        "send_llm": normalised.get("send_llm"),
        "element": normalised.get("element"),
        "effects": normalised.get("effects"),
        "llm_effects": normalised.get("llm_effects"),
        "attack": normalised.get("attack"),
        "defense": normalised.get("defense"),
    }
    return _drop_empty(data)


def _roll_rarity_rank(rarity: str) -> int:
    order = ("common", "uncommon", "rare", "epic", "legendary", "artifact")
    value = str(rarity or "common").strip().lower().replace(" ", "_").replace("-", "_")
    return order.index(value) if value in order else 0


def _is_exploration_action(action: str) -> bool:
    text = action.strip()
    if not text:
        return False
    if text.startswith("クエスト"):
        return False
    keywords = (
        "探索",
        "探す",
        "調べ",
        "周囲",
        "外",
        "森",
        "道",
        "洞窟",
        "ダンジョン",
        "遺跡",
        "進む",
        "向か",
        "行く",
        "入る",
        "歩",
        "移動",
        "旅",
    )
    return any(keyword in text for keyword in keywords)


def _is_attack_action(action: str) -> bool:
    text = action.strip()
    if not text:
        return False
    lowered = text.lower()
    if any(keyword in text for keyword in ("攻撃", "殴", "斬", "刺", "撃", "射", "戦う")):
        return True
    if any(keyword in lowered for keyword in ("attack", "strike", "slash", "stab", "shoot", "fight")):
        return True
    keywords = (
        "攻撃",
        "斬る",
        "斬り",
        "撃つ",
        "撃ち",
        "殴る",
        "殴り",
        "刺す",
        "戦う",
        "襲う",
        "矢を放",
        "魔法を放",
    )
    return any(keyword in text for keyword in keywords)


def _is_aggressive_player_action(action: str) -> bool:
    text = action.strip()
    if not text:
        return False
    lowered = text.casefold()
    if _is_attack_action(text):
        return True
    japanese_keywords = ("襲う", "殺す", "殺そう", "殴る", "蹴る", "斬る", "刺す", "撃つ", "傷つける", "叩く")
    english_keywords = (
        "attack",
        "assault",
        "kill",
        "murder",
        "strike",
        "slash",
        "stab",
        "shoot",
        "punch",
        "kick",
        "hurt",
    )
    return any(word in text for word in japanese_keywords) or any(word in lowered for word in english_keywords)


def _is_movement_intent(action: str) -> bool:
    text = action.strip()
    if not text:
        return False
    lowered = text.casefold()
    japanese_keywords = (
        "移動",
        "行く",
        "向かう",
        "進む",
        "戻る",
        "入る",
        "出る",
        "離れる",
        "地図",
        "マップ",
        "ワールドマップ",
        "サブノード",
    )
    english_keywords = (
        "move",
        "go to",
        "head to",
        "travel",
        "enter",
        "leave",
        "return",
        "map",
        "world map",
        "subnode",
    )
    return any(word in text for word in japanese_keywords) or any(word in lowered for word in english_keywords)


def _is_surprise_attack_action(action: str) -> bool:
    text = action.strip().lower()
    return any(keyword in text for keyword in ("不意打ち", "奇襲", "先制", "背後から", "ambush", "surprise", "sneak attack"))


def _combat_start_tool_candidate(action: str) -> bool:
    text = str(action or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    if _is_attack_action(text) or _is_aggressive_player_action(text) or _is_surprise_attack_action(text):
        return True
    english_keywords = (
        "ambush",
        "charge",
        "draw weapon",
        "draw my weapon",
        "open fire",
        "first strike",
        "preemptive",
        "sneak attack",
        "start combat",
        "begin combat",
        "battle",
    )
    japanese_keywords = (
        "戦闘",
        "攻撃",
        "奇襲",
        "不意打ち",
        "先制",
        "殴",
        "斬",
        "刺",
        "撃",
        "射",
        "襲",
    )
    return any(word in lowered for word in english_keywords) or any(word in text for word in japanese_keywords)


def _is_skill_action(action: str) -> bool:
    text = action.strip().lower()
    return any(keyword in text for keyword in ("スキル", "skill", "spell", "魔法", "術", "技:"))


def _is_escape_action(action: str) -> bool:
    text = action.strip().lower()
    return any(keyword in text for keyword in ("逃走", "逃げ", "離脱", "退却", "run away", "escape", "flee"))


def _is_accept_surrender_action(action: str) -> bool:
    text = action.strip()
    if not text:
        return False
    lowered = text.casefold()
    japanese = ("降伏を受け入", "降参を受け入", "降伏を認め", "降参を認め", "戦闘を止め", "見逃す", "許す")
    english = ("accept surrender", "accept their surrender", "spare", "show mercy", "stop fighting")
    return any(word in text for word in japanese) or any(word in lowered for word in english)


def _extract_skill_name(action: str) -> str:
    text = action.strip()
    if not text:
        return ""
    for prefix in ("スキル:", "スキル：", "skill:", "Skill:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    for separator in ("->", "→", "を", "に", "で", "("):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
    return text.strip("「」[] ")


def _is_conversation_action(action: str) -> bool:
    text = action.strip()
    if not text:
        return False
    keywords = (
        "話",
        "聞く",
        "尋ね",
        "相談",
        "頼む",
        "会話",
        "挨拶",
        "呼び",
        "声をかけ",
    )
    return any(keyword in text for keyword in keywords)


def _is_conversation_end_action(action: str) -> bool:
    text = action.strip()
    keywords = ("会話を終える", "話を終える", "別れる", "離れる", "切り上げる")
    return any(keyword in text for keyword in keywords)


def _extract_attack_target(action: str) -> str:
    text = action.strip()
    patterns = (
        r"(.{1,60}?)(?:と|との)(?:戦い|戦闘|バトル|決闘)(?:を)?(?:始め|開始|する|行う|挑|挑む)?",
        r"(.{1,60}?)(?:と|に|へ)(?:戦う|戦闘する|交戦する)",
        r"(.{1,60}?)(?:に|へ|を)(?:向けて|めがけて|狙って)(?:攻撃|斬りかか|斬|撃|殴|刺|襲|仕掛)",
        r"(.{1,60}?)(?:に|へ|を)(?:不意打ち|奇襲|先制攻撃|先制|背後から|こっそり)?(?:攻撃|斬りかか|斬|撃|殴|刺|襲|仕掛)",
        r"(?:不意打ち|奇襲|先制攻撃|先制|背後から|こっそり)(?:で|に|から)?(.{1,40}?)(?:を|に|へ)(?:攻撃|斬|撃|殴|刺|襲)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            target = _strip_attack_target_noise(match.group(1))
            if target:
                return target
    separators = (
        "を攻撃",
        "に攻撃",
        "を斬",
        "を撃",
        "を殴",
        "を刺",
        "との戦い",
        "と戦い",
        "との戦闘",
        "と戦闘",
        "とのバトル",
        "とバトル",
        "と戦",
        "を襲",
    )
    for separator in separators:
        if separator in text:
            target = text.split(separator, 1)[0].strip()
            return _strip_attack_target_noise(target)
    return ""


def _infer_encounter_target_from_context_text(text: str) -> str:
    source = str(text or "")
    patterns = (
        r"([^\s、。,.「」『』（）()\[\]{}:：にへをが]{1,24})(?:の魔物|のモンスター|の敵)",
        r"([^\s、。,.「」『』（）()\[\]{}:：にへをが]{1,24})(?:が現れ|が潜|が襲)",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if not match:
            continue
        target = _strip_attack_target_noise(match.group(1))
        if target:
            return target
    return ""


def _player_action_from_prompt(prompt: str) -> str:
    text = str(prompt or "")
    marker = "プレイヤー行動:"
    if marker in text:
        return text.rsplit(marker, 1)[-1].splitlines()[0].strip()
    marker = "プレイヤー入力:"
    if marker in text:
        return text.rsplit(marker, 1)[-1].splitlines()[0].strip()
    marker = "行動:"
    if marker in text:
        return text.rsplit(marker, 1)[-1].splitlines()[0].strip()
    return text.strip()


def _text_may_need_context_reference(text: str) -> bool:
    source = str(text or "").strip()
    if not source:
        return False
    lowered = source.casefold()
    english_terms = (
        "that",
        "it",
        "them",
        "him",
        "her",
        "there",
        "the previous",
        "the last",
        "the same",
    )
    if any(term in lowered for term in english_terms):
        return True
    japanese_terms = (
        "それ",
        "これ",
        "あれ",
        "そこ",
        "ここ",
        "さっき",
        "先ほど",
        "直前",
        "今の",
        "その",
        "この",
        "あの",
        "例の",
        "同じ",
        "彼",
        "彼女",
        "相手",
        "あいつ",
        "そいつ",
        "こいつ",
        "やつ",
        "奴",
        "店主",
        "受付",
        "依頼主",
        "掲示板の依頼",
    )
    return any(term in source for term in japanese_terms)


def _strip_action_prefix(text: str) -> str:
    prefixes = ("現れた", "迫り来る", "迫ってくる", "目の前の", "近くの", "その", "あの", "この", "例の", "敵の")
    result = text.strip()
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :].strip()
    return result


def _strip_attack_target_noise(text: str) -> str:
    result = _strip_action_prefix(str(text or "").strip())
    if not result:
        return ""
    leading_phrases = (
        "不意打ち",
        "奇襲",
        "先制攻撃",
        "先制",
        "背後から",
        "死角から",
        "物陰から",
        "こっそり",
        "隠れて",
        "突然",
        "素早く",
        "勢いよく",
    )
    changed = True
    while changed:
        changed = False
        for phrase in leading_phrases:
            if result.startswith(phrase):
                result = result[len(phrase) :].strip()
                result = re.sub(r"^(?:で|に|から|して|の|、|。|\s)+", "", result).strip()
                changed = True
    result = re.sub(r"(?:への|に対する)?(?:不意打ち|奇襲|先制攻撃|先制)$", "", result).strip()
    result = re.sub(r"(?:に|へ|を)?(?:向けて|めがけて|狙って)?(?:攻撃|斬りかかる|斬りかか|斬る|撃つ|殴る|刺す|襲う)$", "", result).strip()
    result = re.sub(r"(?:たち|達)$", "", result).strip()
    return result.strip("「」[] ")


def _strip_encounter_log(encounter: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in encounter.items() if key != "log"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "はい"}
    return bool(value)


def _as_named_dict(value: Any, default_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        data = dict(value)
        data["name"] = str(data.get("name") or default_name)
        return data
    return {"name": default_name, "description": str(value)}


def _merge_named_dicts(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(item) for item in existing if isinstance(item, dict)]
    seen = {str(item.get("name") or "") for item in result}
    for item in additions:
        name = str(item.get("name") or "")
        if name and name in seen:
            continue
        result.append(dict(item))
        if name:
            seen.add(name)
    return result


def _is_player_reference(name: str, world: WorldData, player_name: str = "") -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    aliases = {
        "player",
        "pc",
        "hero",
        "protagonist",
        "you",
        "self",
        "me",
        "プレイヤー",
        "プレイヤ",
        "主人公",
        "あなた",
        "自分",
        "自分自身",
        "私",
        "わたし",
        "俺",
        "僕",
    }
    if lowered in aliases or text in aliases:
        return True
    if player_name and text == player_name:
        return True
    for character in world.characters.values():
        if character.flags.get("is_player"):
            if text == character.name:
                return True
            for alias in _character_reference_terms(character):
                if text == alias:
                    return True
    return False


def _existing_scene_character_matches(world: WorldData, term: str, location: str, player_name: str = "") -> bool:
    text = str(term or "").strip()
    if not text:
        return False
    for character in world.characters.values():
        if _is_player_reference(character.name, world, player_name) or character.flags.get("is_player"):
            continue
        if text == character.name:
            return True
        if location and not _actor_present_at(character.location, character.state, character.flags, location):
            continue
        if text in _character_reference_terms(character):
            return True
    return False


def _character_reference_terms(character: Character) -> list[str]:
    terms = [
        character.name,
        character.role,
        str(character.extra.get("occupation") or ""),
        str(character.extra.get("archetype") or ""),
        str(character.extra.get("display_alias") or character.flags.get("display_alias") or ""),
        str(character.extra.get("role_label") or character.flags.get("role_label") or ""),
    ]
    terms.extend(str(item) for item in _as_list(character.extra.get("aliases")))
    return _dedupe_strs([term for term in terms if term])


def _with_schema_instruction(messages: list[dict[str, str]], instruction: str) -> list[dict[str, str]]:
    if not instruction:
        return [dict(message) for message in messages]
    copied = [dict(message) for message in messages]
    for message in copied:
        if message.get("role") == "system":
            message["content"] = f"{message.get('content', '')}\n\n{instruction}"
            return copied
    return [{"role": "system", "content": instruction}, *copied]


def _ai_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _world_ai_context(
    world: WorldData,
    *,
    include_locations: bool = True,
    include_characters: bool = True,
    include_monsters: bool = True,
    include_quests: bool = True,
    location_limit: int = 8,
    character_limit: int = 8,
    quest_limit: int = 8,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "world_name": world.world_name,
        "overview": _short_text(world.overview, 900),
        "structure_description": _short_text(world.structure_description, 900),
        "world_situation": _short_text(world.world_situation, 900),
        "current_rumor": _short_text(world.current_rumor, 500),
        "flow": _compact_value(world.flow, max_chars=1200),
        "starting_location": world.starting_location,
        "structure": _compact_value(world.structure, max_chars=1400),
    }
    if isinstance(world.extra, dict) and world.extra.get("world_time"):
        data["world_time"] = _compact_value(world.extra.get("world_time"), max_chars=400)
    if isinstance(world.extra, dict) and isinstance(world.extra.get("location_graph"), dict):
        graph = world.extra.get("location_graph") or {}
        nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
        edges = graph.get("edges", []) if isinstance(graph.get("edges"), list) else []
        data["world_map"] = {
            "movement_rule": "normal movement is limited to adjacent locations; each edge takes 2 hours",
            "known_nodes": [
                {
                    "name": name,
                    "kind": node.get("kind"),
                    "danger": node.get("danger"),
                    "visited": node.get("visited"),
                }
                for name, node in list(nodes.items())[:location_limit]
                if isinstance(node, dict)
            ],
            "connections": edges[: max(0, location_limit * 2)],
        }
    if include_locations:
        data["locations"] = [
            _location_ai_context(location)
            for location in list(world.locations.values())[:location_limit]
        ]
    if include_characters:
        data["characters"] = [
            _character_ai_context(character, details=False)
            for character in list(world.characters.values())[:character_limit]
        ]
    if include_quests:
        data["quests"] = [
            _quest_ai_context(quest, include_log=False, include_extra=False)
            for quest in world.quests[:quest_limit]
        ]
    return _drop_empty(data)


def _location_ai_context(location: Any) -> dict[str, Any]:
    extra = getattr(location, "extra", {}) if isinstance(getattr(location, "extra", {}), dict) else {}
    data = {
        "name": getattr(location, "name", ""),
        "description": _short_text(getattr(location, "description", ""), 700),
        "area": getattr(location, "area", ""),
        "atmosphere": extra.get("atmosphere", ""),
        "settlement_structure": _compact_value(extra.get("settlement_structure", {}), max_chars=900),
        "facilities": _compact_value(extra.get("facilities", []), max_chars=900),
        "parent_location": extra.get("parent_location", ""),
        "facility_type": extra.get("facility_type", ""),
    }
    return _drop_empty(data)


def _character_reference_guidance(character: Character) -> dict[str, str]:
    gender = str(character.gender or "").strip().casefold()
    if gender in {"male", "man", "boy"} or "男" in gender:
        return {
            "reference": "name_or_he",
            "instruction": "Use this character's name, role, 男性, or 彼. Do not use 彼女 or female-default wording.",
        }
    if gender in {"female", "woman", "girl"} or "女" in gender:
        return {
            "reference": "name_or_she",
            "instruction": "Use this character's name, role, 女性, or 彼女.",
        }
    return {
        "reference": "name_or_role",
        "instruction": "Use this character's name, role, その人物, or その存在; avoid gendered pronouns unless the profile explicitly establishes them.",
    }


def _character_ai_context(
    character: Character,
    *,
    details: bool = True,
    include_traits: bool = True,
    include_skills: bool = True,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "uuid": character.uuid,
        "name": character.name,
        "role": character.role,
        "category": character.category,
        "location": character.location,
        "state": character.state,
        "alive": not _character_state_is_dead(character),
        "level": character.level,
        "current_hp": character.current_hp,
        "max_hp": character.max_hp,
        "current_sp": character.current_sp,
        "max_sp": character.max_sp,
        "attack": character.attack,
        "defense": character.defense,
        "attributes": _compact_value(character.attributes, max_chars=500),
        "resistance": _compact_value(character.resistance, max_chars=300),
        "gender": character.gender,
        "age": character.age,
        "backstory": _short_text(character.backstory, 700 if details else 280),
        "personality": _short_text(character.personality, 500 if details else 240),
        "look": _short_text(character.look, 500 if details else 240),
        "reference_guidance": _character_reference_guidance(character),
        "gold": character.gold,
    }
    if not character.flags.get("is_player"):
        affinity = character.extra.get("affinity", character.extra.get("trust", 0)) if isinstance(character.extra, dict) else 0
        data["affinity"] = max(NPC_AFFINITY_MIN, min(NPC_AFFINITY_MAX, _safe_int(affinity, 0)))
        data["affinity_scale"] = "-100: fully hostile, 0: neutral, 100: fully trusted; one event should usually change -10 to +10"
    if isinstance(character.extra, dict):
        for source_key, target_key in (
            ("level", "level"),
            ("exp", "exp"),
            ("current_hp", "current_hp"),
            ("max_hp", "max_hp"),
            ("current_sp", "current_sp"),
            ("max_sp", "max_sp"),
        ):
            if character.extra.get(source_key) not in (None, ""):
                data[target_key] = character.extra.get(source_key)
    if not _is_player_power_actor(character):
        data["skill_power_budget"] = _actor_power_budget(character)
        data["skill_power_used"] = _entry_power_total(character.skills)
    if character.image_generation_prompt:
        data["image_generation_prompt"] = [str(item) for item in character.image_generation_prompt[:12]]
    combat_attacks = character.extra.get("combat_attacks") if isinstance(character.extra, dict) else None
    if not combat_attacks and isinstance(character.extra, dict):
        combat_attacks = character.extra.get("attacks")
    if combat_attacks:
        data["combat_attacks"] = _compact_value(combat_attacks, max_chars=500)
    if details:
        if include_traits:
            data["traits"] = _compact_value(character.traits, max_chars=900)
        if include_skills:
            data["skills"] = _compact_value(character.skills, max_chars=1000)
        data["status_effects"] = _compact_value(character.status_effects, max_chars=500)
        data["inventory"] = _compact_value(character.inventory, max_chars=500)
        ability = character.extra.get("ability") if isinstance(character.extra, dict) else None
        if ability:
            data["ability"] = _compact_value(ability, max_chars=900)
        equipment = character.extra.get("equipment") if isinstance(character.extra, dict) else None
        if isinstance(equipment, dict):
            data["equipment"] = _compact_value(equipment, max_chars=900)
            data["equipment_summary"] = _compact_value(calculate_equipment_summary(equipment), max_chars=900)
    return _drop_empty(data)










def _compact_value(value: Any, *, max_chars: int = 1000, list_limit: int = 12, dict_limit: int = 16) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _short_text(value, max_chars)
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        return [
            _compact_value(item, max_chars=max(160, max_chars // 2), list_limit=list_limit, dict_limit=dict_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= dict_limit:
                break
            key_text = str(key)
            if _is_ai_metadata_key(key_text):
                continue
            result[key_text] = _compact_value(
                item,
                max_chars=max(160, max_chars // 2),
                list_limit=list_limit,
                dict_limit=dict_limit,
            )
        return _drop_empty(result)
    return _short_text(str(value), max_chars)


def _short_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in ("", None, [], {})}


def _is_ai_metadata_key(key: str) -> bool:
    return (
        key.startswith("_")
        or key.startswith("raw_")
        or key
        in {
            "history",
            "prompts",
            "image_paths",
            "image_pipeline",
            "generation_metadata",
            "postprocess",
            "source_response",
            "request",
            "request_params",
            "response_info",
            "prompt_debug",
        }
    )


def _strip_response_metadata(response: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in response.items() if not key.startswith("_")}




def _local_world_placeholder_location_name(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.casefold()
    if any(marker in text for marker in ("未命名", "仮名", "仮称")):
        return True
    if any(marker in lowered for marker in ("unnamed", "placeholder", "todo", "tbd")):
        return True
    return lowered in {
        "unknown",
        "location",
        "world location",
        "final destination",
        "final_destination",
        "最終地点",
        "最終領域",
        "ロケーション",
    }


def _local_world_placeholder_location_description(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.casefold()
    if any(
        marker in text
        for marker in (
            "単体サブノード",
            "複数のサブノード",
            "複数ノード",
            "ローカル生成",
            "種別:",
            "危険度",
            "slot_id",
            "grid",
        )
    ):
        return True
    return any(
        marker in lowered
        for marker in (
            "single-subnode",
            "single subnode",
            "multi-node",
            "placeholder",
            "unnamed",
            "internal label",
        )
    )


def _local_world_location_needs_llm_description(location: LocationData, spec: dict[str, Any]) -> bool:
    if _local_world_placeholder_location_name(location.name):
        return True
    if _local_world_placeholder_location_description(location.description):
        return True
    return str(spec.get("role") or "") == "final_destination" and _local_world_placeholder_location_name(location.name)


def _character_from_raw(item: Any, index: int, category: str) -> Character:
    if isinstance(item, dict):
        data = dict(item)
        name = str(data.get("name") or data.get("character_name") or f"{category.title()} {index + 1}")
        role = str(data.get("role") or data.get("job") or data.get("occupation") or "")
        description = str(data.get("description") or data.get("backstory") or data.get("summary") or "")
        character = Character.from_dict(data, default_name=name)
        character.name = name
        character.role = role
        character.category = category
        if description and not character.backstory:
            character.backstory = description
        if data.get("appearance") and not character.look:
            character.look = str(data.get("appearance"))
        if description and not character.look:
            character.look = description
        character.extra.setdefault("raw_create_settlement_detail_entry", data)
        return character
    return Character(
        name=f"{category.title()} {index + 1}",
        role=category,
        category=category,
        backstory=str(item),
    )


def _clean_generated_name(value: Any, fallback: str, *, kind: str = "actor") -> str:
    text = str(value or "").strip()
    text = _strip_generated_name_notes(text)
    if kind == "monster":
        text = _strip_attack_target_noise(text)
    text = re.sub(r"^[\s\"':：,，、。・\-~～|/\\]+|[\s\"':：,，、。・\-~～|/\\]+$", "", text)
    if not _is_valid_generated_name(text):
        return fallback
    if kind == "monster" and text.lower() in {
        "enemy",
        "monster",
        "foe",
        "target",
        "opponent",
        "敵",
        "モンスター",
        "魔物",
        "怪物",
        "未知の魔物",
        "未知の敵",
        "不明な敵",
        "不明な魔物",
        "相手",
        "あいつ",
        "そいつ",
        "こいつ",
        "やつ",
        "奴",
    }:
        return fallback
    if kind == "character" and text.lower() in {"npc", "character", "person"}:
        return fallback
    return text


def _strip_generated_name_notes(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""
    note_words = (
        "討伐",
        "入手",
        "獲得",
        "報酬",
        "戦利品",
        "ドロップ",
        "出現",
        "登場",
        "drop",
        "loot",
        "reward",
        "obtained",
        "acquired",
    )

    def replace_note(match: re.Match[str]) -> str:
        segment = match.group(0).lower()
        return "" if any(word.lower() in segment for word in note_words) else match.group(0)

    source = re.sub(r"[\(（\[\【][^\)）\]\】]{0,40}[\)）\]\】]", replace_note, source)
    lowered = source.lower()
    if any(word.lower() == lowered for word in note_words):
        return ""
    for word in note_words:
        if lowered.startswith(word.lower() + ":") or lowered.startswith(word.lower() + "："):
            return source.split(":", 1)[-1].split("：", 1)[-1].strip()
    source = re.sub(r"^(?:不意打ち|奇襲|先制攻撃|先制)(?:で|に|から)?", "", source).strip()
    return source.strip()


def _is_valid_generated_name(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    invalid = {
        "none",
        "null",
        "unknown",
        "n/a",
        "enemy",
        "monster",
        "foe",
        "敵",
        "モンスター",
        "魔物",
        "怪物",
        "相手",
        "討伐時入手",
        "入手",
        "獲得",
        "報酬",
        "戦利品",
        "ドロップ",
        "出現",
        "登場",
        "drop",
        "loot",
        "reward",
    }
    if lowered in invalid:
        return False
    return any(ch.isalnum() for ch in text)


def _unique_character_name(world: WorldData, name: str) -> str:
    base = _clean_generated_name(name, "NPC", kind="character")
    if not world.has_character_name(base):
        return base
    suffix = 2
    while world.has_character_name(f"{base} {suffix}"):
        suffix += 1
    return f"{base} {suffix}"


def _actor_present_at(location: str, state: str, flags: dict[str, Any], current_location: str) -> bool:
    actor_location = location or str(flags.get("current_location") or "")
    if not actor_location or actor_location != current_location:
        return False
    actor_state = str(state or flags.get("state") or "present").strip().lower()
    if not actor_state:
        actor_state = "present"
    return _actor_state_is_present(actor_state)


def _character_is_hostile_actor(character: Character) -> bool:
    flags = character.flags if isinstance(character.flags, dict) else {}
    extra = character.extra if isinstance(character.extra, dict) else {}
    if _as_bool(flags.get("surrendered")) or _as_bool(extra.get("surrendered")):
        return False
    if str(extra.get("combat_status") or flags.get("combat_status") or "").strip().lower() == SURRENDERED_STATUS_ID:
        return False
    if any(_status_effect_id(_normalise_status_effect(effect)) == SURRENDERED_STATUS_ID for effect in character.status_effects):
        return False
    if _as_bool(flags.get("hostile")) or _as_bool(extra.get("hostile")):
        return True
    if _as_bool(flags.get("enemy_npc")) or _as_bool(extra.get("enemy_npc")):
        return True
    return str(character.category or "").strip().lower() in {"enemy_npc", "wild_encounter", "hostile", "monster"}


def _actor_state_is_present(value: str) -> bool:
    actor_state = str(value or "present").strip().lower()
    if not actor_state:
        actor_state = "present"
    return actor_state not in {"absent", "gone", "left", "hidden", "dead", "ended", "inactive", "removed", "fled", "escaped", "retreated"}


def _install_quest_modules() -> None:
    from . import quest_board
    from . import quest_deadline
    from . import quest_destination
    from . import quest_generate
    from . import quest_objective
    from . import quest_referee
    from . import quest_reward

    moved_global_names = (
        "_quest_investigation_point_name",
        "_quest_procurement_requirement_name",
        "_quest_procurement_requirement_text",
        "_quest_procurement_category_words",
        "_quest_objective_kind",
        "_quest_objective_npc_name",
        "_quest_objective_npc_fallback_design",
        "_quest_objective_item_name",
        "_quest_delivery_target_name",
        "_quest_delivery_item_name",
        "_quest_objective_item_category",
        "_quest_objective_npc_action",
        "_quest_objective_item_action",
        "_quest_delivery_action",
        "_quest_investigation_action",
        "_quest_procurement_action",
        "_quest_captor_resolution_action",
        "_quest_completion_report_action",
    )
    for name in moved_global_names:
        globals()[name] = getattr(quest_objective, name)

    modules = (
        quest_board,
        quest_deadline,
        quest_destination,
        quest_generate,
        quest_objective,
        quest_referee,
        quest_reward,
    )
    shared_globals = {name: value for name, value in globals().items() if not name.startswith("__")}
    for module in modules:
        module.__dict__.update(shared_globals)

    method_sources = {
        quest_board: (
            "available_quest_board_quests",
            "_quest_board_target_count",
            "_refresh_quest_board_for_settlement",
            "accept_quest_from_board",
            "_active_quest_can_report_at",
            "_resolve_dedicated_quest_report",
        ),
        quest_deadline: (
            "active_quest_remaining_hours",
            "active_quest_remaining_time_label",
            "_quest_remaining_hours",
            "_fail_expired_active_quest",
            "_fail_quest_if_deadline_expired",
        ),
        quest_generate: (
            "_generate_settlement_quests",
            "_apply_settlement_quests",
            "_apply_field_event_quests",
        ),
        quest_reward: (
            "_assign_quest_danger",
            "_ensure_quest_reward",
            "_grant_quest_reward",
            "_finish_quest",
            "_maybe_finish_active_quest_from_response",
        ),
        quest_destination: (
            "_active_quest_destination_location",
            "_active_quest_destination_subnode",
            "_ensure_quest_destination",
            "_quest_origin_subnode_id",
            "_quest_origin_location",
            "_quest_anchor_location",
            "_quest_hint_requests_dungeon",
            "_quest_dungeon_branch_anchor",
            "_create_quest_dungeon_location",
            "_quest_destination_location",
            "_find_world_location_by_name",
            "_find_nearby_location_by_kind",
            "_ensure_quest_objective_subnode",
            "_ensure_quest_branch_node",
            "_quest_branch_parent",
            "_ensure_quest_branch_connection",
            "_quest_objective_subnode_display",
            "_quest_destination_for_action",
        ),
        quest_objective: (
            "_apply_quest_encounter_outcome",
            "_initialize_quest_state",
            "_quest_objective_pack",
            "_quest_objective_entries",
            "_ensure_quest_objective_entities",
            "_quest_objective_npc_design",
            "_create_quest_objective_npc",
            "_create_quest_objective_item",
            "_create_quest_delivery_item",
            "_create_quest_investigation_marker",
            "_create_quest_procurement_requirement",
            "_quest_objective_character",
            "_quest_objective_item_in_player_inventory",
            "_quest_objective_item_in_location_inventory",
            "_quest_procurement_candidates",
            "_quest_procurement_checker",
            "_at_quest_objective_place",
            "_quest_flags",
            "_set_quest_flag",
            "_quest_entries_by_role",
            "_quest_blockers_resolved",
            "_refresh_quest_objective_state",
            "_apply_quest_objective_action",
            "_sync_quest_objective_escorts",
            "_quest_objective_completion_allowed",
            "_quest_objectives_returned",
            "_quest_report_location_matches",
            "_settle_rescued_quest_character",
            "_complete_quest_objectives",
            "_close_quest_objectives",
        ),
        quest_referee: (
            "_quest_starter_location",
            "_start_quest",
            "_quest_starter",
            "_resolve_active_quest_action",
            "_quest_referee_with_free_action",
            "_quest_referee_event_resolve",
            "_find_quest_to_start",
            "_find_quest_by_name",
        ),
    }
    for module, names in method_sources.items():
        for name in names:
            setattr(GameEngine, name, getattr(module, name))


_install_quest_modules()
