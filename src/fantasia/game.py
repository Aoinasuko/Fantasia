from __future__ import annotations

import json
import random
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .image_pipeline import process_subject_image
from .imagegen import BaseImageBackend, ImageResult
from .i18n import ELEMENT_IDS, tr_enum
from .items import (
    EQUIPMENT_SLOT_LABELS,
    EQUIPMENT_SLOTS,
    ITEM_CATEGORY_IDS,
    add_item_stack,
    calculate_equipment_summary,
    can_add_item_stack,
    equipment_slot_for_category,
    extract_response_rewards,
    generate_vendor_items,
    inventory_slot_count,
    is_equipment_item,
    item_label,
    normalise_item,
    reward_log_lines,
    take_item_stack,
)
from .json_response import JsonResponseError, retry_prompt, sanitize_retry_response, schema_instruction, validate_manager_response
from .json_store import JsonStore
from .llm import BaseLlmBackend
from .paths import GENERATED_DIR
from .prompt_templates import PromptTemplateStore
from .save_store import SaveSlot, SaveStore
from .world_model import CharacterData, GameStateData, LocationData, QuestData, WorldData


SEASONS = ("春", "夏", "秋", "冬")
DAYS_PER_SEASON = 60
HOURS_PER_DAY = 24
WORLD_DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
INITIAL_WORLD_TIME_HOURS = 8
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
    "check_action_feasibility",
    "craft_item_generator",
    "referee_player_any_input_new_new",
    "referee_npc",
    "referee_npc_rewrite",
}
INTERNAL_QUEST_NPC_ROLES = {
    "rescue_target",
    "blocker",
    "defeat_target",
    "delivery_target",
}
INTERNAL_QUEST_TOKEN_LABELS = {
    "rescue_target": "救出対象",
    "blocker": "妨害者",
    "defeat_target": "討伐対象",
    "delivery_target": "配達先",
    "retrieve_item": "回収品",
    "delivery_item": "配達品",
    "investigation_point": "調査地点",
    "procurement_requirement": "調達条件",
}
WORLD_LOCATION_COUNT_OPTIONS = {"small": 30, "normal": 60, "many": 90}
DEFAULT_WORLD_LOCATION_COUNT = WORLD_LOCATION_COUNT_OPTIONS["normal"]
WORLD_CRIME_RISK_OPTIONS = {"none", "normal", "strict"}
DEFAULT_WORLD_CRIME_RISK = "none"
WORLD_ENEMY_STRENGTH_OPTIONS = {"weak", "normal", "strong"}
DEFAULT_WORLD_ENEMY_STRENGTH = "normal"
COMBAT_MAX_OPPONENTS = 3
INCAPACITATED_STATUS_ID = "incapacitated"
INCAPACITATED_STATUS_NAME = "行動不能"
SURRENDERED_STATUS_ID = "surrendered"
FLED_STATUS_ID = "fled"
WORLD_LOCATION_BATCH_MIN = 3
WORLD_LOCATION_BATCH_MAX = 5
WORLD_MAP_EDGE_HOURS = 2
WORLD_MAP_MAX_DYNAMIC_DEGREE = 3
WORLD_DANGER_MAX = 50
WORLD_FINAL_DANGER_MIN = 40
WORLD_FINAL_DANGER_MAX = 45
WORLD_LOCATION_KIND_OPTIONS = (
    "settlement",
    "wilderness",
    "dungeon",
    "landmark",
    "road",
    "crossroad",
    "coast",
    "mountain",
    "river",
    "plain",
)
WORLD_LOCATION_KIND_LABELS = {
    "settlement": "街/村/拠点",
    "wilderness": "森/荒野/湿地",
    "dungeon": "洞窟/遺跡/迷宮",
    "landmark": "目印/名所",
    "road": "街道",
    "crossroad": "分岐路",
    "coast": "海岸",
    "mountain": "山",
    "river": "川",
    "plain": "平原",
}
FANTASY_LOCATION_PREFIXES = (
    "エル",
    "ルナ",
    "セラ",
    "ヴェル",
    "ノクス",
    "アルカ",
    "ミスト",
    "リュミ",
    "オル",
    "ファル",
)
FANTASY_LOCATION_STEMS = (
    "ディア",
    "フィル",
    "ノア",
    "グラン",
    "シア",
    "リス",
    "ヴェイン",
    "ティス",
    "レム",
    "カイル",
)
SUBNODE_GRAPH_KEY = "subnode_graph"
CURRENT_SUBNODE_FLAG = "current_subnode"
ACTOR_SUBNODE_ID_FLAG = "current_subnode_id"
ACTOR_SUBNODE_LOCATION_FLAG = "current_subnode_location"
DEFAULT_SUBNODE_ID = "center"
DUNGEON_ENTRY_SUBNODE_ID = "entrance"
DUNGEON_DEEPEST_SUBNODE_ID = "deepest"
DUNGEON_SUBNODE_LAYOUT_VERSION = 2
DUNGEON_SUBNODE_MIN_COUNT = 5
DUNGEON_SUBNODE_MAX_COUNT = 20
DUNGEON_SUBNODE_KIND_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("ore_vein", "鉱脈の広間", "壁一面に鉱石が走る、採掘の痕跡が残る空間。"),
    ("herb_grove", "薬草の群生地", "淡い光を浴びた薬草が群生している湿った場所。"),
    ("treasure_room", "宝箱の間", "古びた宝箱や台座が置かれ、罠の気配が漂う部屋。"),
    ("underground_stream", "地下水脈", "冷たい水が細く流れ、足場が不安定な通路。"),
    ("collapsed_passage", "崩落通路", "天井や壁が崩れ、迂回や慎重な移動が必要な道。"),
    ("monster_nest", "魔物の巣", "獣臭と爪痕が残る、魔物の気配が濃い場所。"),
    ("ancient_altar", "古代祭壇", "読めない文字が刻まれた祭壇が鎮座している部屋。"),
    ("crystal_cavity", "水晶洞", "結晶が光を反射し、視界を惑わせる美しい洞穴。"),
    ("mushroom_grove", "発光茸の群生地", "発光する茸が壁や床に広がる幻想的な空間。"),
    ("trap_hall", "罠の回廊", "床や壁に不自然な継ぎ目がある緊張感のある回廊。"),
    ("storage_ruins", "朽ちた保管庫", "壊れた木箱や棚が並び、古い物資が眠っている部屋。"),
    ("hidden_chamber", "隠し部屋", "本道から外れた場所にある、ひっそりとした小部屋。"),
)
SUBNODE_EXTERNAL_PREFIX = "external:"
REPEATED_INPUT_DEDUPE_SECONDS = 4.0
DEFAULT_GUILD_NAME = "冒険者ギルド"
QUEST_BOARD_NAME = "依頼掲示板"
MAP_CHOICE_LABEL = "地図を見る"
QUEST_BOARD_CHOICE_LABEL = "依頼掲示板を見る"
PLAYER_HOMES_KEY = "player_homes"
PLAYER_HOME_CONSTRUCTION_KEY = "player_home_construction"
PLAYER_HOME_SUBNODE_ID = "player_home"
PLAYER_HOME_KIND = "player_home"
PLAYER_HOME_NAME = "プレイヤーの家"
PLAYER_HOME_MAX_LEVEL = 10
PLAYER_HOME_BUILD_PROGRESS_STEP = 25
PLAYER_HOME_REST_HOURS = 8
PLAYER_HOME_TOWN_HALL_PLANS = {500: 3, 1000: 5, 10000: 7}
PLAYER_HOME_CHOICES = ("休息する", "クラフトをする", "家の保存箱を開く", "外に出る")
SKILL_TRAIT_POWER_MIN = 1
SKILL_TRAIT_POWER_MAX = 5
NPC_DEFAULT_POWER_BUDGET = 8
PLAYER_UNLIMITED_POWER_BUDGET = 999
CHARACTER_DEFAULT_ATTRIBUTES = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}
NPC_MAX_LEVEL = 50
NPC_AFFINITY_MIN = -100
NPC_AFFINITY_MAX = 100
NPC_AFFINITY_DELTA_MIN = -10
NPC_AFFINITY_DELTA_MAX = 10
COMPANION_WAIT_RETURN_DAYS = 3
PLAYER_INVENTORY_MAX_SLOTS = 27
QUEST_DEADLINE_HOURS = 48
QUEST_TYPES = {"rescue", "retrieve", "defeat", "delivery", "investigate", "procure"}
QUEST_REPORT_STAGE = "report_ready"
SETTLEMENT_QUEST_MAX_PER_SETTLEMENT = 9
SETTLEMENT_QUEST_BATCH_MIN = 2
SETTLEMENT_QUEST_BATCH_MAX = 3

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
    "shop",
    "market",
}

SHOP_FACILITY_PRICE_MULTIPLIERS = {
    "black_market": 3.0,
}

SHOP_FACILITY_NAME_BANK = {
    "blacksmith": ("鋼火鍛冶", "赤炉工房", "槌音鍛冶店", "黒鉄武具店"),
    "black_market": ("影市", "月裏商会", "黒帳武具店", "夜鴉商店"),
    "apothecary": ("若葉薬品店", "月露薬房", "白瓶堂", "癒し草の薬屋"),
    "food_store": ("麦籠食料店", "香草食料店", "旅腹亭", "朝市食材店"),
    "material_store": ("素材蔵", "石と根の素材店", "採集者の棚", "原石商会"),
    "general_store": ("よろず屋", "旅支度雑貨店", "何でも棚", "道具箱商店"),
    "magic_store": ("星灯魔術店", "巻物堂", "青燐魔法店", "古文書の塔"),
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
    ) -> None:
        self.llm = llm
        self.image_backend = image_backend
        self.store = store
        self.save_store = save_store or SaveStore()
        self.prompt_templates = prompt_templates or PromptTemplateStore()
        self.allow_any_action_concept = bool(allow_any_action_concept)
        self.state = GameStateData()
        self._last_resolved_input: dict[str, Any] = {}
        self._temp_llm_context_events: list[dict[str, Any]] = []

    def create_world(
        self,
        world_name: str,
        premise: str,
        player_character: CharacterData | None = None,
        save_game: bool = True,
        location_count: int = DEFAULT_WORLD_LOCATION_COUNT,
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
            elif initial_location and initial_location != settlement_location and _looks_like_facility_location_name(initial_location):
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
            _as_str_list(initial.get("choices") or response.get("choices")),
            active_quest=False,
        )
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

    def apply_player_character(self, character: CharacterData) -> str:
        if not self.state.world_data or self.state.world_data.world_name == "unknown":
            raise RuntimeError("No generated world is waiting for character setup.")
        self._install_player_character(character)
        self.save_game()
        return self.state.log_text()

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
        character: CharacterData,
        seed_name: str = "",
        seed_description: str = "",
    ) -> list[dict[str, Any]]:
        response = self._create_trait(
            character.name or self.state.player_name,
            self.state.world_data,
            character,
            seed_name=seed_name,
            seed_description=seed_description,
        )
        self._apply_character_traits(character, response)
        return character.traits

    def generate_character_setup_skills(
        self,
        character: CharacterData,
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

    def _install_player_character(self, character: CharacterData) -> None:
        name = character.name.strip() or "Player"
        character.name = name
        character.role = character.role or "Player"
        character.category = character.category or "player"
        character.flags["is_player"] = True
        character.flags.setdefault("source", "character_setup")
        _normalise_actor_power_loadout(character)
        self.state.player_name = name
        self.state.gold = int(character.gold or 0)
        self.state.inventory = list(character.inventory)
        character.inventory = self.state.inventory
        character.location = self.state.current_location or self.state.world_data.starting_location
        character.state = "present"
        self._ensure_character_runtime_data(character)
        self._ensure_player_progress(character)
        self.state.party = [character.to_dict()]
        self.state.world_data.characters[name] = character
        self.state.flags["player_character"] = character.to_dict()
        max_hp = self._player_max_hp(character)
        current_hp = self._player_current_hp(max_hp)
        self._set_player_hp(current_hp, max_hp=max_hp)
        max_sp = self._player_max_sp(character)
        current_sp = self._player_current_sp(max_sp)
        self._set_player_sp(current_sp, max_sp=max_sp)
        self.state.flags["player_character"] = character.to_dict()
        self.state.world_data.history.append(
            {
                "manager": "character_setup",
                "character": name,
                "response": _character_ai_context(character),
            }
        )

    def _player_inventory(self) -> list[dict[str, Any]]:
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
        character = self.state.world_data.characters.get(self.state.player_name)
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
        home = self._current_player_home()
        if not home:
            return self.state.log_text(16)
        max_hp = self._player_max_hp()
        max_sp = self._player_max_sp()
        old_hp = self._player_current_hp(max_hp)
        old_sp = self._player_current_sp(max_sp)
        self._set_player_hp(max_hp, max_hp=max_hp)
        self._set_player_sp(max_sp, max_sp=max_sp)
        time_event = self._advance_world_time(
            PLAYER_HOME_REST_HOURS,
            source="player_home_rest",
            reason="home rest",
            append_log=False,
        )
        narration = "自分の家で身体を休めた。家具の整った静かな空間で、疲労がゆっくりと抜けていく。"
        self.state.append_turn(action, narration, self.state.current_location, self._home_choices(), input_type=input_type)
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.append(f"> [休息] HP {old_hp}/{max_hp} -> {max_hp}/{max_hp} / SP {old_sp}/{max_sp} -> {max_sp}/{max_sp}")
        self.save_game()
        return self.state.log_text(16)

    def _resolve_home_exit(self, action: str, input_type: str) -> str:
        home = self._current_player_home()
        if not home:
            return self.state.log_text(16)
        location_name = self.state.current_location or self.state.world_data.starting_location
        parent = str(home.get("parent_subnode_id") or DEFAULT_SUBNODE_ID)
        self._set_current_subnode(location_name, parent)
        narration = "家を出て、外の空気を吸い込んだ。"
        choices = self._location_default_choices(location_name)
        self.state.append_turn(action, narration, location_name, choices, input_type=input_type)
        self.save_game()
        return self.state.log_text(16)

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

    def _set_character_subnode_fields(self, character: CharacterData, location_name: str, subnode_id: str) -> None:
        location_name = str(location_name or "").strip()
        subnode_id = str(subnode_id or "").strip()
        if not location_name or not subnode_id:
            return
        character.flags[ACTOR_SUBNODE_ID_FLAG] = subnode_id
        character.flags[ACTOR_SUBNODE_LOCATION_FLAG] = location_name
        character.extra[ACTOR_SUBNODE_ID_FLAG] = subnode_id
        character.extra[ACTOR_SUBNODE_LOCATION_FLAG] = location_name

    def _clear_character_subnode_fields(self, character: CharacterData) -> None:
        for mapping in (character.flags, character.extra):
            if isinstance(mapping, dict):
                mapping.pop(ACTOR_SUBNODE_ID_FLAG, None)
                mapping.pop(ACTOR_SUBNODE_LOCATION_FLAG, None)

    def _character_subnode_assignment(self, character: CharacterData) -> tuple[str, str]:
        extra = character.extra if isinstance(character.extra, dict) else {}
        flags = character.flags if isinstance(character.flags, dict) else {}
        subnode_id = str(extra.get(ACTOR_SUBNODE_ID_FLAG) or flags.get(ACTOR_SUBNODE_ID_FLAG) or "").strip()
        location_name = str(extra.get(ACTOR_SUBNODE_LOCATION_FLAG) or flags.get(ACTOR_SUBNODE_LOCATION_FLAG) or "").strip()
        return location_name, subnode_id

    def _ensure_character_subnode_assignment_for_location(self, character: CharacterData, location_name: str) -> str:
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

    def _character_matches_current_subnode(self, character: CharacterData, location_name: str | None = None) -> bool:
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

    def _character_matches_active_facility(self, character: CharacterData) -> bool:
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

    def available_quest_board_quests(self) -> list[QuestData]:
        if self.state.active_quest:
            return []
        if not self.is_current_location_guild():
            return []
        settlement = self._current_settlement_location()
        settlement_name = settlement.name if settlement else self.state.current_location
        quests: list[QuestData] = []
        for quest in self.state.world_data.quests:
            if quest.status not in {"available", ""}:
                continue
            if quest.flags.get("wild"):
                continue
            if quest.neighboring_settlement and settlement_name and quest.neighboring_settlement != settlement_name:
                continue
            quests.append(quest)
        return quests

    def travel_to_facility(self, facility_name: str) -> str:
        settlement = self._current_settlement_location()
        if settlement is None:
            narration = "ここは街や村ではないため、施設の地図は使えない。"
            self.state.append_turn(MAP_CHOICE_LABEL, narration, self.state.current_location, self.state.choices, input_type="choice")
            self.save_game()
            return self.state.log_text(16)

        facility = self._find_or_create_facility_record(settlement, facility_name)
        if not facility:
            narration = f"{settlement.name}には「{facility_name}」という施設は見当たらない。"
            self.state.append_turn(MAP_CHOICE_LABEL, narration, self.state.current_location, self._location_default_choices(settlement.name), input_type="choice")
            self.save_game()
            return self.state.log_text(16)

        return self._move_to_facility(settlement, facility, action=f"{facility.get('name') or facility_name}へ移動", input_type="choice")

    def accept_quest_from_board(self, quest_name: str) -> str:
        if self.state.active_quest:
            self.state.append_turn(
                QUEST_BOARD_CHOICE_LABEL,
                "進行中の依頼があるため、別の依頼はまだ受けられない。",
                self.state.current_location,
                self._location_default_choices(self.state.current_location),
                input_type="choice",
            )
            self.save_game()
            return self.state.log_text(16)
        if not self.is_current_location_guild():
            self.state.append_turn(
                QUEST_BOARD_CHOICE_LABEL,
                "依頼掲示板はギルドの中で確認できる。",
                self.state.current_location,
                self._location_default_choices(self.state.current_location),
                input_type="choice",
            )
            self.save_game()
            return self.state.log_text(16)
        quest = self._find_quest_by_name(quest_name)
        if not quest or quest.status not in {"available", ""} or quest.flags.get("wild"):
            self.state.append_turn(
                QUEST_BOARD_CHOICE_LABEL,
                "その依頼は現在受けられない。",
                self.state.current_location,
                self._location_default_choices(self.state.current_location),
                input_type="choice",
            )
            self.save_game()
            return self.state.log_text(16)
        return self._start_quest(f"依頼を受ける: {quest.name}", "choice", quest)

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
        character = self.state.world_data.characters.get(self.state.player_name)
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
        bonuses = {"attack": 0, "defense": 0}
        active = self._active_encounter()
        effects: list[Any] = []
        effects.extend(self.state.status_effects)
        player = self.state.world_data.characters.get(self.state.player_name)
        if player:
            effects.extend(player.status_effects)
        if isinstance(active, dict):
            effects.extend(_as_list(active.get("player_status_effects")))
        for effect in effects:
            if not isinstance(effect, dict):
                continue
            for key in ("attack_delta", "atk_delta", "attack_bonus", "atk_bonus"):
                if key in effect:
                    bonuses["attack"] += _safe_int(effect.get(key), 0)
            for key in ("defense_delta", "def_delta", "defense_bonus", "def_bonus"):
                if key in effect:
                    bonuses["defense"] += _safe_int(effect.get(key), 0)
            effect_type = str(effect.get("type") or effect.get("stat") or effect.get("name") or "").strip().lower()
            value = _safe_int(effect.get("value", effect.get("amount", 0)), 0)
            if effect_type in {"attack", "atk", "attack_up", "attack_down"}:
                bonuses["attack"] += value
            elif effect_type in {"defense", "def", "defense_up", "defense_down"}:
                bonuses["defense"] += value
        return bonuses

    def _player_status_immunity_ids(self) -> set[str]:
        summary = self.player_equipment_summary()
        result: set[str] = set()
        for value in summary.get("status_immunities", []):
            effect = _normalise_status_effect({"name": value})
            effect_id = _status_effect_id(effect)
            if effect_id:
                result.add(effect_id)
            text = str(value or "").strip().lower()
            if text:
                result.add(text)
        return result

    def _player_is_immune_to_status(self, effect: dict[str, Any]) -> bool:
        effect_id = _status_effect_id(effect)
        if not effect_id:
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

    def _add_gold(self, amount: int) -> int:
        gained = max(0, int(amount or 0))
        if gained:
            event = self._apply_gold_delta(gained, source="reward", reason="", append_log=False)
            return int(event.get("actual_delta") or 0)
        return gained

    def _apply_response_rewards(self, response: Any, source: str) -> dict[str, Any]:
        items, gold = extract_response_rewards(response, source=source)
        added_items: list[dict[str, Any]] = []
        skipped_items: list[dict[str, Any]] = []
        if items:
            for item in items:
                added = self._add_player_item_stack(item, source=source)
                if added:
                    added_items.append(added)
                else:
                    skipped_items.append(normalise_item(item, source=source))
        lost_items = self._apply_response_item_losses(response, source)
        gained_gold = self._add_gold(gold)
        equipment_events = self._apply_response_equipment_effects(response, source, added_items=added_items)
        if not added_items and not skipped_items and not lost_items and not gained_gold and not equipment_events:
            return {"items": [], "skipped_items": [], "lost_items": [], "gold": 0, "equipment": []}

        self._sync_player_inventory()
        event = {
            "source": source,
            "items": added_items,
            "skipped_items": skipped_items,
            "lost_items": lost_items,
            "gold": gained_gold,
            "equipment": equipment_events,
        }
        self.state.world_data.extra.setdefault("inventory_events", []).append(event)
        self.state.display_log.extend(reward_log_lines(added_items, gained_gold))
        self.state.display_log.extend(self._inventory_full_line(item) for item in skipped_items)
        self.state.display_log.extend(f"> [喪失] {item_label(item)}" for item in lost_items)
        self.state.display_log.extend(str(item.get("line")) for item in equipment_events if item.get("line"))
        return event

    def resolve_craft_from_selected_items(self, ingredients: list[dict[str, Any]], intent: str = "") -> str:
        action = intent.strip() or "クラフトする"
        items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
        return self._resolve_craft_with_ingredients(action, "free_action", items, source="craft_menu")

    def _resolve_home_action(self, action: str, input_type: str) -> str | None:
        text = str(action or "").strip()
        if not text:
            return None
        if self._current_player_home():
            if any(word in text for word in ("休息", "休む", "寝る", "rest")):
                return self._resolve_home_rest(action, input_type)
            if any(word in text for word in ("外に出", "出る", "leave", "exit")):
                return self._resolve_home_exit(action, input_type)
            if any(word in text for word in ("保存箱", "倉庫", "storage", "stash")):
                self.state.append_turn(action, "家の保存箱を開いた。", self.state.current_location, self._home_choices(), input_type=input_type)
                self.save_game()
                return self.state.log_text(16)
            if any(word in text for word in ("クラフト", "合成", "調合", "鍛冶", "料理", "craft")):
                self.state.append_turn(action, "家の作業台を使う準備をした。", self.state.current_location, self._home_choices(), input_type=input_type)
                self.save_game()
                return self.state.log_text(16)

        home_travel = self._resolve_player_home_travel(action, input_type)
        if home_travel is not None:
            return home_travel

        town_hall_result = self._resolve_town_hall_home_purchase(action, input_type)
        if town_hall_result is not None:
            return town_hall_result

        if _is_home_construction_action(action):
            return self._resolve_home_construction_action(action, input_type)
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
        self.state.append_turn(action, narration, location_name, self._home_choices(), input_type=input_type)
        self.save_game()
        return self.state.log_text(16)

    def _resolve_town_hall_home_purchase(self, action: str, input_type: str) -> str | None:
        active = self._active_facility_record()
        if not active or str(active.get("type") or "").lower() != "town_hall":
            return None
        text = str(action or "")
        if not any(word in text for word in ("家", "自宅", "住居", "home", "house")):
            return None
        settlement = self._current_settlement_location()
        if settlement is None:
            return None
        if self._player_home_for_location(settlement.name):
            narration = f"{settlement.name}には、すでにあなたの家がある。"
            self.state.append_turn(action, narration, settlement.name, self._location_default_choices(settlement.name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        plan = _town_hall_home_plan_from_action(action)
        if not plan:
            choices = [f"{cost}Goldで家を建てる" for cost in sorted(PLAYER_HOME_TOWN_HALL_PLANS)]
            narration = "役場では、土地と小さな家の手続きを行える。500Gold、1000Gold、10000Goldの三つのプランが提示された。"
            self.state.append_turn(action, narration, settlement.name, _exploration_choices(choices), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        cost, level = plan
        if self.state.gold < cost:
            narration = f"役場職員は首を横に振った。{cost}Goldの支払いには所持金が足りない。"
            self.state.append_turn(action, narration, settlement.name, self._location_default_choices(settlement.name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        gold_event = self._apply_gold_delta(-cost, source="town_hall_home", reason="家の購入", append_log=False)
        self._create_player_home(settlement.name, level, source="town_hall", parent_subnode_id=DEFAULT_SUBNODE_ID, cost=cost)
        narration = f"役場で{cost}Goldを支払い、{settlement.name}にあなたの家を用意した。家具レベルは{level}。"
        choices = [f"{PLAYER_HOME_NAME}へ移動", MAP_CHOICE_LABEL, "周囲を見る"]
        self.state.append_turn(action, narration, settlement.name, _exploration_choices(choices), input_type=input_type)
        if gold_event.get("line"):
            self.state.display_log.append(str(gold_event["line"]))
        self.save_game()
        return self.state.log_text(16)

    def _resolve_home_construction_action(self, action: str, input_type: str) -> str:
        location_name = self.state.current_location or self.state.world_data.starting_location
        if self._current_settlement_location() is not None:
            narration = "街の中で自分の家を増築するには、役場で土地と建物の手続きを行う必要がある。"
            self.state.append_turn(action, narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if self._player_home_for_location(location_name):
            narration = "このロケーションには、すでにあなたの家がある。"
            self.state.append_turn(action, narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        material = self._home_build_material_from_action(action)
        if not material:
            narration = "家の建築に使う具体的な建材が見つからない。所持品か周囲にある素材を指定する必要がある。"
            self.state.append_turn(action, narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        response = self._home_construction_evaluator(action, material)
        lines = self._apply_home_construction_entry(
            response,
            source="home_construction_evaluator",
            action=action,
            input_type=input_type,
            preselected_item=material,
        )
        if lines:
            self.state.display_log.extend(lines)
        self.save_game()
        return self.state.log_text(16)

    def _home_build_material_from_action(self, action: str) -> dict[str, Any] | None:
        items, _missing = self._craft_ingredients_from_action(action)
        if items:
            return dict(items[0])
        text = str(action or "")
        for candidate in self._craft_item_candidates():
            item = dict(candidate["item"])
            name = str(item.get("name") or "")
            if not name or name not in text:
                continue
            item["_craft_source"] = candidate["source"]
            item["_craft_source_uuid"] = str(item.get("item_uuid") or "")
            return item
        return None

    def _home_construction_evaluator(self, action: str, material: dict[str, Any]) -> dict[str, Any]:
        location_name = self.state.current_location or self.state.world_data.starting_location
        location = self.state.world_data.locations.get(location_name)
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        subnode_id = self._current_subnode_id(location_name)
        subnode = graph.get("nodes", {}).get(subnode_id, {}) if isinstance(graph, dict) else {}
        payload = {
            "world": _world_ai_context(self.state.world_data, include_characters=False, include_monsters=False, include_quests=True),
            "location": _location_ai_context(location) if location else {"name": location_name},
            "subnode": {
                "id": subnode_id,
                "name": str(subnode.get("name") or subnode_id),
                "description": str(subnode.get("description") or ""),
                "kind": str(subnode.get("kind") or ""),
            },
            "player_action": action,
            "material_item": _compact_item_for_ai(material),
            "rules": {
                "progress_step": PLAYER_HOME_BUILD_PROGRESS_STEP,
                "max_furniture_level_gain_per_item": 3,
                "max_final_furniture_level": PLAYER_HOME_MAX_LEVEL,
            },
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはFantasiaのプレイヤーの家建築評価担当です。"
                    "指定されたアイテムが家の建材、家具、作業設備、生活設備として妥当かを判断してください。"
                    "返答は usable, narration, reason, furniture_level_gain, consume_item を持つJSONだけにしてください。"
                    "furniture_level_gainは0から3で、素材が良いほど高くします。"
                ),
            },
            {"role": "user", "content": _ai_json(payload)},
        ]
        try:
            return self._chat_json(
                "home_construction_evaluator",
                messages,
                max_tokens=350,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
        except Exception as exc:
            return {
                "usable": False,
                "narration": f"建材として使えるか判断できなかった: {exc}",
                "reason": str(exc),
                "furniture_level_gain": 0,
                "consume_item": False,
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
                self.state.append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            return []
        if not item:
            narration = "建築に使う素材が見つからない。"
            if append_turn:
                self.state.append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
            return []
        if self._player_home_for_location(location_name):
            narration = "このロケーションには、すでにあなたの家がある。"
            if append_turn:
                self.state.append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
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
                    self.state.append_turn(action or "家を建てる", narration, location_name, self._location_default_choices(location_name), input_type=input_type)
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
            self.state.append_turn(action or "家を建てる", narration, location_name, choices, input_type=input_type)
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

    def _resolve_craft_action(self, action: str, input_type: str) -> str | None:
        if not _is_craft_action_text(action):
            return None
        items, missing = self._craft_ingredients_from_action(action)
        if missing:
            message = "指定された素材が見つかりません: " + ", ".join(missing)
            self.state.append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if len(items) < 2:
            message = "クラフトには、所持品か周囲にある素材を2つ以上指定してください。"
            self.state.append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        return self._resolve_craft_with_ingredients(action, input_type, items, source="free_action")

    def _resolve_craft_with_ingredients(
        self,
        action: str,
        input_type: str,
        ingredients: list[dict[str, Any]],
        *,
        source: str,
    ) -> str:
        items = [normalise_item(item, source="craft") for item in ingredients if isinstance(item, dict)]
        if len(items) < 2:
            message = "クラフトには素材が2つ以上必要です。"
            self.state.append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if not self._craft_ingredients_available(items):
            message = "指定された素材は、すでに所持品や周囲から見つかりません。"
            self.state.append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if not self._craft_result_can_fit_after_consumption(items):
            message = self._inventory_full_line()
            self.state.append_turn(action, message, self.state.current_location, self.state.choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)

        craft_roll = self.roll_craft_check(items)
        ingredient_labels = [item_label(item) for item in items]
        if craft_roll.get("critical_failure"):
            removed = self._consume_craft_ingredients(items, source=source)
            narration = "クラフトは失敗し、素材は失われました。"
            self.state.append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
            self._append_action_roll_log(craft_roll)
            self.state.world_data.extra.setdefault("craft_events", []).append(
                {
                    "source": source,
                    "ingredients": ingredient_labels,
                    "removed": removed,
                    "roll": craft_roll,
                    "failed": True,
                }
            )
            self._sync_player_inventory()
            self.save_game()
            return self.state.log_text(16)

        response = self._craft_item_generator(action, items, craft_roll)
        result = self._crafted_item_from_response(response, items)
        removed = self._consume_craft_ingredients(items, source=source)
        added = self._add_player_item_stack(result, source="craft")
        narration = str(response.get("narration") or response.get("text") or "素材を組み合わせ、新しいアイテムを作り上げました。")
        if not added:
            location_inventory = self._current_location_inventory()
            added_to_location = add_item_stack(location_inventory, result, source="craft_overflow")
            if added_to_location:
                narration = "\n".join([narration, "所持品に空きがないため、完成品はその場に置かれました。"])
        self.state.append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
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
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False, include_monsters=False, include_quests=True))
        location = self.state.world_data.locations.get(self.state.current_location)
        location_payload = _ai_json(_location_ai_context(location)) if location else "{}"
        ingredients_payload = _ai_json([_compact_item_for_ai(item) for item in ingredients])
        roll_payload = json.dumps(craft_roll, ensure_ascii=False)
        categories = ", ".join(ITEM_CATEGORY_IDS)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのクラフト結果生成AIです。"
                    "素材、プレイヤーの意図、世界観、ゲーム側の2d6判定を尊重し、JSONだけを返してください。"
                    "戻り値は narration と item を中心にし、item は name, category, description, quantity, value, rarity を含めます。"
                    "category は次のIDから選んでください: "
                    f"{categories}。"
                    "判定が高いほど品質や価値を上げ、critical_success なら特別な希少性や効果を与えてください。"
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

    def _crafted_item_from_response(self, response: dict[str, Any], ingredients: list[dict[str, Any]]) -> dict[str, Any]:
        raw = response.get("item") or response.get("crafted_item") or response.get("result")
        if not isinstance(raw, dict):
            raw = {
                "name": str(response.get("name") or "クラフト品"),
                "category": str(response.get("category") or _craft_fallback_category(ingredients)),
                "description": str(response.get("description") or response.get("narration") or "素材を加工して作られた品。"),
                "quantity": 1,
                "value": max(1, sum(_safe_int(item.get("value"), 0) for item in ingredients)),
                "rarity": str(response.get("rarity") or "common"),
            }
        return normalise_item(raw, source="craft", fallback_category=_craft_fallback_category(ingredients))

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

    def _apply_response_equipment_effects(
        self,
        response: Any,
        source: str,
        *,
        added_items: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(response, dict):
            return []
        events: list[dict[str, Any]] = []
        equip_values: list[Any] = []
        for key in ("equip_item", "equip_items", "equipped_item", "auto_equip", "auto_equips", "equipment_equip"):
            equip_values.extend(_as_list(response.get(key)))
        for item in added_items or []:
            if isinstance(item, dict) and _as_bool(item.get("equip") or item.get("auto_equip") or item.get("equipped")):
                equip_values.append(item)
        for value in equip_values:
            event = self._equip_player_item_reference(value, source=source)
            if event.get("changed"):
                events.append(event)

        for value in _as_list(response.get("equipment_changes")):
            if not isinstance(value, dict):
                continue
            action = str(value.get("action") or value.get("type") or "").strip().lower()
            if action in {"equip", "wear", "wield"}:
                event = self._equip_player_item_reference(value.get("item") or value, source=source, reason=str(value.get("reason") or ""))
                if event.get("changed"):
                    events.append(event)
            elif action in {"unequip", "remove", "disarm", "strip"}:
                event = self._unequip_player_reference(value, source=source, reason=str(value.get("reason") or ""))
                if event.get("changed"):
                    events.append(event)

        for key in ("unequip_item", "unequip_items", "remove_equipment", "removed_equipment", "disarm", "strip_equipment"):
            for value in _as_list(response.get(key)):
                event = self._unequip_player_reference(value, source=source)
                if event.get("changed"):
                    events.append(event)
        return events

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

    def _apply_response_progress_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        encounter: dict[str, Any] | None = None,
    ) -> list[str]:
        lines: list[str] = []
        lines.extend(self._apply_response_gold_effects(response, source))
        lines.extend(self._apply_response_time_effects(response, source))
        lines.extend(self._apply_response_exp_effects(response, source))
        lines.extend(self._apply_equipment_regen_effects(source))
        lines.extend(self._apply_response_game_over_effects(response, source, encounter=encounter))
        return lines

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

    def _apply_equipment_regen_effects(self, source: str) -> list[str]:
        summary = self.player_equipment_summary()
        lines: list[str] = []
        hp_regen = _safe_int(summary.get("hp_regen"), 0)
        sp_regen = _safe_int(summary.get("sp_regen"), 0)
        if hp_regen:
            event = self._apply_player_hp_delta(hp_regen, source=f"{source}:equipment", reason="equipment regen")
            if event.get("line"):
                lines.append(str(event["line"]))
        if sp_regen:
            event = self._apply_player_sp_delta(sp_regen, source=f"{source}:equipment", reason="equipment regen")
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

    def active_quest_remaining_hours(self) -> int | None:
        quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
        if not quest or quest.status != "active":
            return None
        deadline = _safe_int(quest.extra.get("deadline_hours"), -1)
        if deadline < 0:
            return None
        return max(0, deadline - self._world_time_total_hours())

    def active_quest_remaining_time_label(self) -> str:
        remaining = self.active_quest_remaining_hours()
        if remaining is None:
            return "-"
        days, hours = divmod(int(remaining), HOURS_PER_DAY)
        if days:
            return f"{days}d {hours}h"
        return f"{hours}h"

    def _quest_remaining_hours(self, quest: QuestData) -> int | None:
        deadline = _safe_int(quest.extra.get("deadline_hours"), -1)
        if deadline < 0:
            return None
        return max(0, deadline - self._world_time_total_hours())

    def _fail_expired_active_quest(self, *, source: str, append_log: bool = False) -> dict[str, Any] | None:
        quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
        if not quest:
            return None
        return self._fail_quest_if_deadline_expired(quest, source=source, append_log=append_log)

    def _fail_quest_if_deadline_expired(self, quest: QuestData, *, source: str, append_log: bool = False) -> dict[str, Any] | None:
        if quest.status != "active":
            return None
        deadline = _safe_int(quest.extra.get("deadline_hours"), -1)
        if deadline < 0 or self._world_time_total_hours() < deadline:
            return None
        event = self._finish_quest(quest, "failed", source, {"reason": "deadline_expired"})
        quest.extra["quest_stage"] = "failed"
        quest.extra["failure_reason"] = "deadline_expired"
        line = f"> [Quest] {quest.name} failed: time limit expired."
        if append_log:
            self.state.display_log.append(line)
        event["line"] = line
        return event

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

    def _apply_response_exp_effects(self, response: dict[str, Any], source: str) -> list[str]:
        if not isinstance(response, dict):
            return []
        amount = self._response_player_exp_delta(response)
        if not amount:
            return []
        event = self._apply_player_exp(amount, source=source, reason=self._response_exp_reason(response))
        return [str(line) for line in event.get("lines", [])]

    def _apply_player_exp(self, amount: Any, *, source: str, reason: str = "") -> dict[str, Any]:
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
            self._set_player_hp(old_current_hp + max(0, new_max_hp - old_max_hp), max_hp=new_max_hp)
            self._set_player_sp(old_current_sp + max(0, new_max_sp - old_max_sp), max_sp=new_max_sp)
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
        moved = bool(previous_location and location_name and previous_location != location_name)
        if moved:
            self.state.flags.pop("active_cg_image_path", None)
            self.state.flags.pop("active_cg_request", None)

        cg_prompt = response.get("cg_prompt") or response.get("cg_image_prompt")
        cg_description = str(response.get("cg_description") or response.get("cg") or "")
        display_cg = _as_bool(response.get("display_cg")) or bool(cg_prompt or cg_description)
        if display_cg:
            self.state.flags["pending_cg_request"] = {
                "source": source,
                "location": location_name,
                "cg_prompt": cg_prompt,
                "cg_description": cg_description,
                "narration": str(response.get("narration") or response.get("text") or response.get("message") or ""),
                "choices": _as_str_list(response.get("choices")),
                "recent_log": self.state.log_text(8),
                "response": _strip_response_metadata(response),
            }
            return

        self.state.flags.pop("pending_cg_request", None)
        if source not in {"background_image_creator", "cg_image_creator"}:
            self.state.flags.pop("active_cg_image_path", None)
            self.state.flags.pop("active_cg_request", None)
        self._request_background_if_needed(location_name)

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
        self.state.append_turn(action, narration, self.state.current_location, self._encounter_choices(encounter), input_type=input_type)
        self.state.display_log.append(f"> [警備] お尋ね者として衛兵に見つかった。")
        self.save_game()
        return self.state.log_text(16)

    def _ensure_guard_character(self, settlement: LocationData) -> CharacterData:
        base_name = f"{settlement.name}の衛兵"
        character = self.state.world_data.characters.get(base_name)
        if character is None or _character_state_is_dead(character):
            name = base_name if character is None else _unique_character_name(self.state.world_data, base_name)
            character = CharacterData(
                name=name,
                role="衛兵",
                category="guard",
                backstory=f"{settlement.name}の治安を守る衛兵。",
                personality="職務に忠実で、街中の犯罪者を見逃さない。",
                flags={"source": "crime_guard", "guard": True},
            )
            self.state.world_data.characters[character.name] = character
        self._set_character_presence(character, self.state.current_location or settlement.name)
        return character

    def _current_location_danger(self, location_name: str = "") -> int:
        name = location_name or self.state.current_location or self.state.world_data.starting_location
        location = self.state.world_data.locations.get(name)
        danger = _safe_int((location.extra.get("danger_level") if location else 0), 0)
        graph = self.state.world_data.extra.get("location_graph") if isinstance(self.state.world_data.extra, dict) else None
        nodes = graph.get("nodes") if isinstance(graph, dict) else None
        node = nodes.get(name) if isinstance(nodes, dict) else None
        if isinstance(node, dict):
            danger = max(danger, _safe_int(node.get("danger"), danger))
        return _clamp_world_danger(danger)

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
        opponent = self.state.world_data.characters.get(opponent_name)
        if isinstance(opponent, CharacterData):
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

    def _encounter_opponent_names_for_start(self, primary: CharacterData | None, location: str) -> list[str]:
        names: list[str] = []
        if isinstance(primary, CharacterData) and primary.name:
            names.append(primary.name)
        if isinstance(primary, CharacterData) and not _character_is_hostile_actor(primary):
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

    def _encounter_opponent_entry(self, character: CharacterData, *, location: str) -> dict[str, Any]:
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

    def _sync_encounter_opponent_entry(self, encounter: dict[str, Any], character: CharacterData) -> dict[str, Any]:
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

    def _set_encounter_active_opponent(self, encounter: dict[str, Any], character: CharacterData | None) -> None:
        if not isinstance(character, CharacterData):
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

    def _encounter_opponents(self, encounter: dict[str, Any]) -> list[CharacterData]:
        opponents: list[CharacterData] = []
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

    def _living_encounter_opponents(self, encounter: dict[str, Any]) -> list[CharacterData]:
        living: list[CharacterData] = []
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

    def _acting_encounter_opponents(self, encounter: dict[str, Any]) -> list[CharacterData]:
        return [character for character in self._living_encounter_opponents(encounter) if not self._character_has_surrendered(character, encounter)]

    def _character_has_surrendered(self, character: CharacterData, encounter: dict[str, Any] | None = None) -> bool:
        if not isinstance(character, CharacterData):
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

    def _select_encounter_target_from_action(self, encounter: dict[str, Any], action: str) -> CharacterData | None:
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

    def _character_from_reference(self, name: str = "", uuid: str = "") -> CharacterData | None:
        uuid = str(uuid or "").strip()
        if uuid:
            for character in self.state.world_data.characters.values():
                if str(character.uuid or "") == uuid:
                    return character
        name = str(name or "").strip()
        if name:
            return self.state.world_data.characters.get(name)
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
        opponent = self.state.world_data.characters.get(opponent_name)
        opponent_names = self._encounter_opponent_names_for_start(opponent if isinstance(opponent, CharacterData) else None, location_name)
        opponent_entries: list[dict[str, Any]] = []
        for name in opponent_names:
            character = self.state.world_data.characters.get(name)
            if isinstance(character, CharacterData):
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
        if isinstance(opponent, CharacterData):
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
            name = str(item.get("name") or item.get("facility_name") or item.get("title") or "").strip()
            if not name:
                continue
            facility_type = str(item.get("type") or item.get("facility_type") or _facility_type_from_name(name)).strip()
            original_name = name
            name = _shop_facility_display_name(name, facility_type, settlement.name, len(normalized))
            record = {
                "name": name,
                "type": facility_type,
                "description": str(item.get("description") or item.get("overview") or ""),
                "npc_name": str(item.get("npc_name") or item.get("keeper") or item.get("owner") or ""),
                "npc_role": str(item.get("npc_role") or item.get("role") or ""),
                "location_name": settlement.name,
                "sub_location": name,
                "source": str(item.get("source") or "settlement"),
                "aliases": _facility_aliases(original_name, name, facility_type),
            }
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
        requested = _facility_request_from_action(action, self.current_location_facilities())
        if not requested:
            return None
        if settlement is None:
            narration = f"この場所には「{requested}」のような街の施設は存在しない。"
            self.state.append_turn(action, narration, self.state.current_location, self.state.choices, input_type=input_type)
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
            self.state.append_turn(action, narration, settlement.name, self._location_default_choices(settlement.name), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)

        facility = self._facility_from_response(response, requested, settlement)
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
            self.state.append_turn(action, narration, location_name, self._location_default_choices(location_name), input_type=input_type)
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
        choices = self._location_default_choices(settlement.name) + _as_str_list((response or {}).get("choices")) + _as_str_list(narrator_response.get("choices"))
        if npc:
            choices.append(f"{npc.name}に話しかける")
        narration = str(narrator_response.get("narration") or (response or {}).get("narration") or f"{facility_name}へ移動した。")
        self._set_player_presence(settlement.name)
        choices = _exploration_choices(choices)
        narration, choices, _ = self._evaluate_hostile_arrival(action, input_type, "facility_travel", settlement.name, narration, choices)
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        self.state.append_turn(action, narration, settlement.name, choices, input_type=input_type)
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
                    "重要な発見や印象的な場面でない限り display_cg は false にしてください。"
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
        for key in ("narration", "choices", "display_cg", "cg_prompt", "cg_description"):
            if key in overlay:
                merged[key] = overlay[key]
        return merged

    def _match_settlement_facility_for_character(
        self,
        settlement: LocationData,
        character: CharacterData,
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
        character: CharacterData,
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
        character: CharacterData,
    ) -> str:
        facility = self._match_settlement_facility_for_character(settlement, character)
        if facility:
            return self._stamp_character_facility_subnode(character, settlement, facility)
        graph = self._ensure_location_subnode_graph(world, settlement.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        subnode_id = DEFAULT_SUBNODE_ID if DEFAULT_SUBNODE_ID in nodes else next(iter(nodes), DEFAULT_SUBNODE_ID)
        self._set_character_subnode_fields(character, settlement.name, subnode_id)
        return subnode_id

    def _ensure_facility_npc(self, settlement: LocationData, facility: dict[str, Any], location_name: str) -> CharacterData | None:
        npc_name = str(facility.get("npc_name") or "").strip()
        if not npc_name:
            npc_name = _default_facility_npc_name(str(facility.get("name") or ""), str(facility.get("type") or ""))
            facility["npc_name"] = npc_name
        if _world_has_dead_npc_identity(self.state.world_data, name=npc_name):
            return None
        character = self.state.world_data.characters.get(npc_name)
        if character is None:
            character = CharacterData(
                name=_unique_character_name(self.state.world_data, npc_name),
                role=str(facility.get("npc_role") or _default_facility_role(str(facility.get("type") or ""))),
                category="facility_npc",
                backstory=str(facility.get("description") or ""),
                personality="仕事に慣れており、訪問者に必要な案内をする。",
            )
            facility["npc_name"] = character.name
            character.flags["source"] = "facility"
            character.flags["facility_name"] = str(facility.get("name") or "")
            character.flags["facility_type"] = str(facility.get("type") or _facility_type_from_name(str(facility.get("name") or "")))
            character.extra["facility"] = str(facility.get("name") or "")
            character.extra["facility_type"] = str(facility.get("type") or _facility_type_from_name(str(facility.get("name") or "")))
            character.extra["parent_settlement"] = settlement.name
            self.state.world_data.characters[character.name] = character
        else:
            character.flags["facility_name"] = str(facility.get("name") or character.flags.get("facility_name") or "")
            character.flags["facility_type"] = str(facility.get("type") or character.flags.get("facility_type") or _facility_type_from_name(str(facility.get("name") or "")))
            character.extra["facility"] = str(facility.get("name") or character.extra.get("facility") or "")
            character.extra["facility_type"] = str(facility.get("type") or character.extra.get("facility_type") or _facility_type_from_name(str(facility.get("name") or "")))
            character.extra["parent_settlement"] = settlement.name
        subnode_id = self._stamp_character_facility_subnode(character, settlement, facility)
        self._set_character_presence(character, location_name, subnode_id=subnode_id)
        return character

    def _set_player_presence(self, location: str) -> None:
        player = self.state.world_data.characters.get(self.state.player_name)
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
        premise_context = premise if _world_generation_premise_refers_to_location(premise, location.name) else ""
        if not _generated_dungeon_boss_payload(response) and not _generated_dungeon_boss_required(premise_context, response, location):
            return None
        graph = self._ensure_location_subnode_graph(world, location.name)
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        target_subnode = DUNGEON_DEEPEST_SUBNODE_ID if DUNGEON_DEEPEST_SUBNODE_ID in nodes else self._default_subnode_for_location(location)
        if not target_subnode:
            return None
        boss_payload = _generated_dungeon_boss_payload(response) or _fallback_generated_dungeon_boss_payload(location, premise_context, response)
        character = _enemy_npc_from_raw(boss_payload, len(world.characters))
        character.name = _unique_character_name(world, character.name)
        character.role = str(character.role or "ダンジョンボス")
        character.category = "enemy_npc"
        danger = max(1, _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0))
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
        _scale_character_for_danger(character, danger, boss=True)
        self._ensure_character_runtime_data(character)
        character.location = location.name
        character.state = "present"
        character.flags["state"] = character.state
        character.flags["alive"] = True
        character.flags["current_location"] = location.name
        character.flags.setdefault("first_seen_location", location.name)
        character.extra.setdefault("origin_location", location.name)
        self._set_character_subnode_fields(character, location.name, target_subnode)
        world.characters[character.name] = character
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
        resolved_danger = _safe_int(extra.get("danger_level"), 0) if danger is None else int(danger)
        node = nodes.setdefault(key, {})
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
        edge_key = {a, b}
        for edge in graph.setdefault("edges", []):
            if {str(edge.get("from") or ""), str(edge.get("to") or "")} == edge_key:
                edge["hours"] = WORLD_MAP_EDGE_HOURS
                return
        graph.setdefault("edges", []).append({"from": a, "to": b, "hours": int(hours or WORLD_MAP_EDGE_HOURS), "kind": kind})

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
        if location is None:
            return False
        extra = location.extra if isinstance(location.extra, dict) else {}
        if isinstance(extra.get(SUBNODE_GRAPH_KEY), dict):
            return True
        if _is_settlement_location(location) or _is_dungeon_location(location):
            return True
        if extra.get("subareas") or extra.get("subnodes"):
            return True
        return _world_location_blocks_world_map_departure(location)

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
        self._upsert_subnode_node(graph, "gate", "\u9580", "\u5916\u306e\u9053\u306b\u7d9a\u304f\u51fa\u5165\u53e3\u3002", "gate", 120, 40, world_map_exit=True)
        self._upsert_subnode_node(graph, "well", "\u4e95\u6238", "\u5730\u4e0b\u306b\u7d9a\u304f\u53ef\u80fd\u6027\u304c\u3042\u308b\u5834\u6240\u3002", "well", 120, 320, world_map_exit=True)
        self._connect_subnodes(graph, DEFAULT_SUBNODE_ID, "gate")
        self._connect_subnodes(graph, DEFAULT_SUBNODE_ID, "well")
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

    def has_current_subnode_map(self) -> bool:
        return bool(self.subnode_map_data().get("nodes"))

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
            source_side = "from" if a == location_name else "to"
            target_side = "to" if a == location_name else "from"
            source_id = self._declared_world_edge_subnode(edge, source_side, location_name) or self._default_external_source_subnode(world, location_name, target)
            if source_id not in nodes:
                source_id = self._default_subnode_for_location(world.locations.get(location_name))
            if source_id not in nodes:
                continue
            result.append(
                {
                    "from": source_id,
                    "target_location": target,
                    "target_subnode": self._declared_world_edge_subnode(edge, target_side, target) or self._default_external_target_subnode(world, target, location_name),
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
            return "well" if self._subnode_connection_uses_well(location, target) else "gate"
        return self._default_subnode_for_location(location)

    def _default_external_target_subnode(self, world: WorldData, target_name: str, source_name: str) -> str:
        target = world.locations.get(target_name)
        source = world.locations.get(source_name)
        if _is_dungeon_location(target):
            return DUNGEON_ENTRY_SUBNODE_ID
        if _is_settlement_location(target):
            return "well" if self._subnode_connection_uses_well(target, source) else "gate"
        return self._default_subnode_for_location(target)

    def _subnode_connection_uses_well(self, location: LocationData | None, target: LocationData | None) -> bool:
        text = "\n".join(
            str(value or "")
            for value in (
                location.name if location else "",
                location.description if location else "",
                target.name if target else "",
                target.description if target else "",
            )
        ).casefold()
        return any(word in text for word in ("sewer", "well", "underground", "\u4e0b\u6c34", "\u4e95\u6238", "\u5730\u4e0b"))

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
        data = self.subnode_map_data()
        location_name = str(data.get("current_location") or self.state.current_location or self.state.world_data.starting_location)
        target_id = str(node_id or "").strip()
        node_lookup = {str(node.get("id") or ""): node for node in data.get("nodes", []) if isinstance(node, dict)}
        target = node_lookup.get(target_id)
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
        graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
        if movement != "free" and not self._subnode_has_edge(graph, current_id, target_id):
            raise ValueError("その場所へは隣接地点からしか移動できません。")
        name = str(target.get("name") or target_id)
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
        self._set_current_subnode(location_name, target_id)
        self._activate_facility_for_subnode(location_name, target)
        narration = str(narrator_response.get("narration") or f"{name}\u3078\u79fb\u52d5\u3057\u305f\u3002")
        choices = _exploration_choices(_as_str_list(narrator_response.get("choices")) + self._location_default_choices(location_name))
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
        self.state.append_turn("\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5", narration, location_name, choices, input_type="choice")
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
        if not target_subnode or target_subnode not in target_graph.get("nodes", {}):
            target_subnode = self._default_subnode_for_location(world.locations.get(target_location))
        self._set_current_subnode(target_location, target_subnode)
        self._set_player_presence(target_location)
        narration = str(narrator_response.get("narration") or f"{previous_location} -> {target_location} \u3078\u79fb\u52d5\u3057\u305f\u3002")
        choices = _exploration_choices(_as_str_list(narrator_response.get("choices")) + self._location_default_choices(target_location))
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
        self.state.append_turn("\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5", narration, target_location, choices, input_type="choice")
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
        visited_nodes = [
            dict(node)
            for node in nodes.values()
            if isinstance(node, dict) and bool(node.get("visited")) and not _world_graph_node_is_facility(world, node)
        ]
        visited_names = {str(node.get("name") or "") for node in visited_nodes}
        edges = [
            dict(edge)
            for edge in graph.get("edges", [])
            if str(edge.get("from") or "") in visited_names and str(edge.get("to") or "") in visited_names
        ]
        return {
            "current_location": self.state.current_location,
            "edge_hours": WORLD_MAP_EDGE_HOURS,
            "nodes": visited_nodes,
            "edges": edges,
        }

    def travel_world_map_to(self, destination: str) -> str:
        world = self.state.world_data
        current = self.state.current_location or world.starting_location
        target = str(destination or "").strip()
        graph = self._ensure_world_location_graph(world, target_count=max(len(world.locations), DEFAULT_WORLD_LOCATION_COUNT))
        nodes = graph.get("nodes", {})
        if not target or target not in nodes or _world_graph_node_is_facility(world, nodes.get(target, {})) or not bool(nodes.get(target, {}).get("visited")):
            raise ValueError("その場所はまだ地図に記録されていません。")
        if target == current:
            return self.state.log_text(16)
        block_reason = self._player_incapacitated_action_block(f"world map travel {target}", for_movement=True)
        if block_reason:
            raise ValueError(self._player_incapacitated_message(block_reason))
        if not self._current_subnode_allows_world_map_departure(world, current):
            raise ValueError("危険地帯の奥からはワールドマップ移動できません。入口や安全な退避地点まで戻ってください。")
        path = self._shortest_world_path(world, current, target, visited_only=True)
        if not path:
            raise ValueError("現在地からその場所までの道が見つかりません。")
        hours = (len(path) - 1) * WORLD_MAP_EDGE_HOURS
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
        choices = _exploration_choices(_as_str_list(narrator_response.get("choices")) + self._location_default_choices(target))
        self._clear_active_facility(reset_subnode=False)
        self._set_player_presence(target)
        self._mark_location_visited(world, target)
        target_graph = self._ensure_location_subnode_graph(world, target)
        if target_graph:
            self._set_current_subnode(target, self._default_subnode_for_location(world.locations.get(target)))
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
        self.state.append_turn("ワールドマップ移動", narration, target, choices, input_type="choice")
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        self._apply_visual_intent(narrator_response, "world_map_travel", target, current)
        self.save_game()
        return self.state.log_text(16)

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

        if proposed in neighbors or teleport:
            if proposed not in nodes:
                location = world.ensure_location(proposed, _short_text(str(response.get("narration") or ""), 220))
                kind = _infer_world_location_kind_for_request(action, response, proposed, location.description)
                location.extra["location_kind"] = kind
                self._set_location_graph_node(world, proposed, kind=kind, location=location)
            if not teleport:
                event = self._advance_world_time(WORLD_MAP_EDGE_HOURS, source="world_travel", reason="adjacent location travel", append_log=False)
                if event.get("line"):
                    status_lines.append(str(event["line"]))
                status_lines.extend(str(item) for item in event.get("companion_lines", []) if item)
            self._clear_active_facility(reset_subnode=False)
            self._mark_location_visited(world, proposed)
            target_graph = self._ensure_location_subnode_graph(world, proposed)
            if target_graph:
                self._set_current_subnode(proposed, self._default_subnode_for_location(world.locations.get(proposed)))
            boss_event = self._ensure_generated_dungeon_boss(proposed, action, response)
            if boss_event:
                status_lines.append(f"> [NPC] {boss_event.get('name')} が {proposed} の奥に配置されました。")
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
            event = self._advance_world_time(WORLD_MAP_EDGE_HOURS, source="world_travel", reason="new nearby location", append_log=False)
            if event.get("line"):
                status_lines.append(str(event["line"]))
            status_lines.extend(str(item) for item in event.get("companion_lines", []) if item)
            self._clear_active_facility(reset_subnode=False)
            self._mark_location_visited(world, proposed)
            target_graph = self._ensure_location_subnode_graph(world, proposed)
            if target_graph:
                self._set_current_subnode(proposed, self._default_subnode_for_location(world.locations.get(proposed)))
            boss_event = self._ensure_generated_dungeon_boss(proposed, action, response)
            if boss_event:
                status_lines.append(f"> [NPC] {boss_event.get('name')} が {proposed} の奥に配置されました。")
            status_lines.append(f"> [Map] 新しい地点を発見: {proposed}")
            return {"location": proposed, "narration_lines": [], "status_lines": status_lines, "moved": True, "denied": False}

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
        choices = ["周囲を見る"]
        for neighbor in self._world_neighbors(self.state.world_data, location_name)[:3]:
            choices.append(f"{neighbor}へ移動")
        if _settlement_location_for_name(self.state.world_data, location_name):
            choices.insert(0, MAP_CHOICE_LABEL)
        active_facility = self._active_facility_record() if location_name == self.state.current_location else None
        active_is_guild = bool(active_facility and str(active_facility.get("type") or "").lower() == "guild")
        if (active_is_guild or _location_is_guild(self.state.world_data, location_name)) and not self.state.active_quest:
            choices.insert(0, QUEST_BOARD_CHOICE_LABEL)
        if location_name == self.state.current_location and active_facility and str(active_facility.get("type") or "").lower() == "town_hall":
            if not self._player_home_for_location(location_name):
                choices = [f"{cost}Goldで家を建てる" for cost in sorted(PLAYER_HOME_TOWN_HALL_PLANS)] + ["周囲を見る"]
        elif self._player_home_for_location(location_name):
            choices.insert(0, f"{PLAYER_HOME_NAME}へ移動")
        return _exploration_choices(choices)

    def _augment_location_choices(self, choices: list[str], location_name: str) -> list[str]:
        return _augment_location_choices_for_world(
            self.state.world_data,
            location_name,
            choices,
            active_quest=bool(self.state.active_quest),
        )

    def _set_character_presence(self, character: CharacterData, location: str, state: str = "present", subnode_id: str = "") -> None:
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

    def _ensure_character_runtime_data(self, character: CharacterData, *, level: int | None = None) -> None:
        if not character.uuid:
            character.uuid = uuid4().hex
        character.level = max(1, min(NPC_MAX_LEVEL, _safe_int(level if level is not None else character.level, 1)))
        attrs = _character_runtime_attributes(character)
        character.attributes = attrs
        character.extra["attributes"] = dict(attrs)
        ability = character.extra.setdefault("ability", {})
        if isinstance(ability, dict):
            ability["attributes"] = dict(attrs)
        max_hp = character.max_hp or _character_calculated_max_hp(character)
        max_sp = character.max_sp or _character_calculated_max_sp(character, max_hp=max_hp)
        character.max_hp = max(1, _safe_int(max_hp, 1))
        character.max_sp = max(1, _safe_int(max_sp, 1))
        current_hp = _safe_int(character.current_hp, 0)
        current_sp = _safe_int(character.current_sp, 0)
        if current_hp <= 0 and not _character_state_is_dead(character):
            current_hp = character.max_hp
        if current_sp <= 0 and not _character_state_is_dead(character):
            current_sp = character.max_sp
        character.current_hp = max(0, min(character.max_hp, current_hp))
        character.current_sp = max(0, min(character.max_sp, current_sp))
        if character.attack <= 0:
            character.attack = _character_calculated_attack(character)
        if character.defense <= 0:
            character.defense = _character_calculated_defense(character)
        character.extra["level"] = character.level
        character.extra["current_hp"] = character.current_hp
        character.extra["max_hp"] = character.max_hp
        character.extra["current_sp"] = character.current_sp
        character.extra["max_sp"] = character.max_sp
        character.extra["attack"] = character.attack
        character.extra["defense"] = character.defense
        character.flags["alive"] = not _character_state_is_dead(character)
        character.flags["uuid"] = character.uuid

    def _party_companions(self) -> list[CharacterData]:
        names: list[str] = []
        for item in self.state.party[1:2]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("character_name") or "").strip()
            if name:
                names.append(name)
                continue
            uuid = str(item.get("uuid") or "").strip()
            if uuid:
                for character in self.state.world_data.characters.values():
                    if character.uuid == uuid:
                        names.append(character.name)
                        break
        result: list[CharacterData] = []
        for name in names:
            character = self.state.world_data.characters.get(name)
            if not character or character.flags.get("is_player") or _character_state_is_dead(character):
                continue
            result.append(character)
        return result[:1]

    def _sync_companion_party_entry(self, character: CharacterData) -> None:
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

    def _set_party_companion(self, character: CharacterData | None, *, source: str, reason: str = "") -> list[str]:
        player_entry = self.state.party[0] if self.state.party and isinstance(self.state.party[0], dict) else None
        if character is None:
            if len(self.state.party) > 1:
                removed = self.state.party[1:]
                self.state.party = [player_entry] if player_entry else []
                for item in removed:
                    if isinstance(item, dict):
                        npc = self.state.world_data.characters.get(str(item.get("name") or ""))
                        if npc and not _character_state_is_dead(npc):
                            self._return_companion_to_origin(npc, source=source, reason=reason)
                return ["> [Party] Companion left the party."]
            return []
        if character.flags.get("is_player") or _character_state_is_dead(character):
            return []
        self._ensure_character_runtime_data(character)
        for existing in self._party_companions():
            if existing.name == character.name or existing.uuid == character.uuid:
                continue
            self._return_companion_to_origin(existing, source=source, reason="replaced")
        self._set_character_presence(character, self.state.current_location or character.location or self.state.world_data.starting_location, "party")
        entry = character.to_dict()
        entry["party_role"] = "companion"
        self.state.party = ([player_entry] if player_entry else []) + [entry]
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
        character: CharacterData,
        *,
        source: str,
        reason: str = "",
        wait_at_current: bool = False,
    ) -> list[str]:
        before = len(self.state.party)
        self.state.party = [
            item
            for index, item in enumerate(self.state.party)
            if index == 0 or not (isinstance(item, dict) and (item.get("name") == character.name or item.get("uuid") == character.uuid))
        ]
        if len(self.state.party) == before:
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

    def _set_companion_waiting(self, character: CharacterData, *, source: str, reason: str = "") -> None:
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

    def _return_companion_to_origin(self, character: CharacterData, *, source: str, reason: str = "") -> str:
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

    def _character_origin_location(self, character: CharacterData) -> str:
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

    def _character_origin_subnode_id(self, character: CharacterData) -> str:
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

    def _companion_can_return_to_origin(self, character: CharacterData) -> bool:
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

    def _mark_character_dead(self, character: CharacterData, *, source: str) -> None:
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

    def prepare_vendor_inventory(self, character: CharacterData) -> dict[str, Any]:
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
        context = " ".join(
            part
            for part in (
                f"facility_type:{facility_type}",
                character.role,
                character.category,
                character.personality,
                character.backstory,
                str(extra.get("facility") or ""),
                f"day:{day}",
            )
            if part
        )
        character.inventory = generate_vendor_items(character.name, context)
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
        }
        self.state.world_data.extra.setdefault("vendor_inventory_events", []).append(event)
        return {"changed": True, "day": day, "event": event}

    def vendor_price_multiplier(self, character: CharacterData | None) -> float:
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

    def _current_trade_candidates(self) -> list[CharacterData]:
        current_location = self.state.current_location or self.state.world_data.starting_location
        candidates: list[CharacterData] = []
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

    def _character_matches_trade_action(self, character: CharacterData, action: str) -> bool:
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

    def _trade_negotiation_target(self, action: str) -> CharacterData | None:
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

    def _character_can_trade(self, character: CharacterData) -> bool:
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

    def _resolve_trade_negotiation_action(self, action: str, input_type: str, character: CharacterData) -> str:
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
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
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

    def roll_trade_negotiation(self, character: CharacterData, action: str = "") -> dict[str, Any]:
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

    def _npc_affinity(self, character: CharacterData) -> int:
        if not isinstance(character.extra, dict):
            character.extra = {}
        value = character.extra.get("affinity", character.extra.get("trust", 0))
        return max(NPC_AFFINITY_MIN, min(NPC_AFFINITY_MAX, _safe_int(value, 0)))

    def _apply_npc_affinity_delta(self, character: CharacterData, delta: Any, *, source: str, reason: str = "") -> list[str]:
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

    def _apply_response_world_state_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: CharacterData | None = None,
        default_location: str = "",
    ) -> list[str]:
        lines: list[str] = []
        lines.extend(self._apply_response_relationship_effects(response, source, default_character=default_character))
        lines.extend(self._apply_response_npc_movements(response, source, default_character=default_character, default_location=default_location))
        lines.extend(self._apply_response_map_reveals(response, source, default_location=default_location))
        lines.extend(self._apply_response_home_construction_effects(response, source))
        return lines

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

    def _active_quest_destination_location(self) -> str:
        quest = self._find_quest_by_name(self.state.active_quest) if self.state.active_quest else None
        if not quest or not isinstance(quest.extra, dict):
            return ""
        destination = quest.extra.get("destination")
        if isinstance(destination, dict):
            return str(destination.get("location") or "").strip()
        return str(quest.extra.get("objective_location") or "").strip()

    def _map_reveal_route_locations(self, entry: Any) -> list[str]:
        if not isinstance(entry, dict):
            return []
        for key in ("route", "path", "locations", "nodes", "route_locations", "path_locations"):
            values = _as_str_list(entry.get(key))
            if values:
                return values
        return []

    def _apply_response_relationship_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_character: CharacterData | None = None,
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
        default_character: CharacterData | None = None,
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

    def _character_from_effect_target(self, value: Any, default_character: CharacterData | None = None) -> CharacterData | None:
        if isinstance(value, CharacterData):
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
        if target in self.state.world_data.characters:
            return self.state.world_data.characters[target]
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

    def _active_visual_subjects(self, location: str) -> tuple[list[CharacterData], list[CharacterData]]:
        characters: list[CharacterData] = []
        enemies: list[CharacterData] = []
        seen_characters: set[str] = set()
        seen_enemies: set[str] = set()
        current_location = location or self.state.current_location or self.state.world_data.starting_location

        def add_character(character: CharacterData | None) -> None:
            if not character or not character.name or character.name in seen_characters:
                return
            seen_characters.add(character.name)
            characters.append(character)

        def add_enemy(character: CharacterData | None) -> None:
            if not character or not character.name or character.name in seen_enemies:
                return
            seen_enemies.add(character.name)
            enemies.append(character)

        add_character(self.state.world_data.characters.get(self.state.player_name))

        active_encounter = self._active_encounter()
        if active_encounter:
            opponent_name = str(active_encounter.get("opponent_name") or "")
            opponent = self.state.world_data.characters.get(opponent_name)
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
                    "current_rumor, story_quests を持つJSONだけを返してください。"
                    "story_quests は複数のクエスト候補の配列にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"雰囲気: {premise_context}\n"
                    f"世界データ: {world_payload}\n"
                    "この世界の初期ストーリー状況、進行の流れ、現在の噂、クエスト候補を作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "create_story",
            messages,
            max_tokens=900,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _create_settlement_detail(
        self,
        player_name: str,
        world: WorldData,
        settlement_name: str,
    ) -> dict[str, Any]:
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=False, include_monsters=False, include_quests=True)
        )
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
                    "Subnode/NPC placement rule: the settlement itself is the world-map location. Plaza, inn, guild, "
                    "shops, gates, wells, and similar places must be represented as facilities or subnodes inside "
                    "that settlement, not as separate locations. If a resident or adventurer works at a facility, "
                    "set that same person as the facility npc_name/npc_role or include facility/facility_type on "
                    "the person object so the game can place them in that facility subnode. Do not place an innkeeper "
                    "or shopkeeper in the central plaza unless they are explicitly visiting the plaza."
                ),
            }
        )
        return self._chat_json(
            "create_settlement_detail",
            messages,
            max_tokens=1000,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _generate_settlement_quests(
        self,
        player_name: str,
        world: WorldData,
        settlement_name: str,
    ) -> dict[str, Any]:
        world_payload = _ai_json(
            _world_ai_context(world, include_characters=True, include_monsters=False, include_quests=True)
        )
        collected: list[dict[str, Any]] = []
        seen_names = {quest.name for quest in world.quests}
        batch_records: list[dict[str, Any]] = []
        batch_index = 1
        while len(collected) < SETTLEMENT_QUEST_MAX_PER_SETTLEMENT:
            remaining = SETTLEMENT_QUEST_MAX_PER_SETTLEMENT - len(collected)
            requested_count = min(SETTLEMENT_QUEST_BATCH_MAX, remaining)
            if requested_count < SETTLEMENT_QUEST_BATCH_MIN and collected:
                break
            messages = [
                {
                    "role": "system",
                    "content": (
                        "あなたはAI駆動RPGの拠点クエスト生成担当です。"
                        "Fantasiaのsettlement_quest_generator相当として、"
                        "quests を持つJSONだけを返してください。"
                        "quests はクエスト候補オブジェクトの配列にしてください。"
                        f"このバッチでは {SETTLEMENT_QUEST_BATCH_MIN}〜{requested_count} 件だけ生成してください。"
                        f"1つの拠点に登録する依頼は最大 {SETTLEMENT_QUEST_MAX_PER_SETTLEMENT} 件です。"
                        "各クエストには quest_type を必ず含め、rescue/retrieve/defeat/delivery/investigate/procure のいずれかにしてください。"
                        "街道をふさぐ魔物や危険生物の排除、討伐、退治、狩猟は必ず quest_type=\"defeat\" です。"
                        "薬や食料など指定品をどこかから調達する依頼だけ quest_type=\"procure\" にしてください。"
                        "各クエストには reward として gold, exp, 任意のitems, description を含めてください。"
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
                        f"今回の生成件数: {SETTLEMENT_QUEST_BATCH_MIN}〜{requested_count}\n"
                        f"既存依頼名: {json.dumps(sorted(seen_names), ensure_ascii=False)}\n"
                        f"世界データ: {world_payload}\n"
                        "この拠点で自然に発生するクエスト候補を、既存依頼と重複しないように作ってください。"
                    ),
                },
            ]
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
                if len(collected) >= SETTLEMENT_QUEST_MAX_PER_SETTLEMENT:
                    break
            if added <= 0:
                break
            batch_index += 1
        return {"quests": collected, "batches": batch_records, "settlement": settlement_name}

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
                    "Judge whether this facility can be added. If allowed, include facility{name,type,description} and npc{name,role,personality,look}. "
                    "Prefer ordinary settlement facilities such as guilds, blacksmiths, black markets, apothecaries, food stores, material stores, general stores, magic stores, inns, temples, clinics, libraries, stables, and markets when plausible. "
                    "Shop facilities must have a proper unique shop name instead of only a generic type name."
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
        name = str(raw.get("name") or raw.get("facility_name") or requested).strip() or requested
        facility_type = str(raw.get("type") or raw.get("facility_type") or _facility_type_from_name(name)).strip()
        original_name = name
        facility_index = len(_as_list(settlement.extra.get("facilities")))
        name = _shop_facility_display_name(name, facility_type, settlement.name, facility_index)
        return {
            "name": name,
            "type": facility_type,
            "description": str(raw.get("description") or raw.get("overview") or response.get("narration") or ""),
            "npc_name": str(npc.get("name") or raw.get("npc_name") or ""),
            "npc_role": str(npc.get("role") or raw.get("npc_role") or _default_facility_role(facility_type)),
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
        story_quests = response.get("story_quests")
        if isinstance(story_quests, list):
            world.quests = [_quest_from_raw(item, index) for index, item in enumerate(story_quests)]
            for quest in world.quests:
                self._ensure_quest_reward(quest)
        world.extra["raw_create_story"] = _strip_response_metadata(response)

    def _apply_settlement_detail(
        self,
        world: WorldData,
        settlement_name: str,
        response: dict[str, Any],
    ) -> None:
        location = world.ensure_location(settlement_name)
        structure_description = str(response.get("settlement_structure_description") or "")
        atmosphere = str(response.get("atmosphere") or response.get("atomosphere") or "")
        if structure_description:
            location.description = structure_description
        if atmosphere:
            location.extra["atmosphere"] = atmosphere
        structure = response.get("settlement_structure", {})
        facilities: list[dict[str, Any]] = []
        for raw in _as_list(response.get("facilities")):
            if isinstance(raw, dict):
                name = str(raw.get("name") or raw.get("facility_name") or raw.get("title") or "").strip()
                if not name:
                    continue
                facilities.append(
                    {
                        "name": name,
                        "type": str(raw.get("type") or raw.get("facility_type") or _facility_type_from_name(name)).strip(),
                        "description": str(raw.get("description") or raw.get("overview") or ""),
                        "npc_name": str(raw.get("npc_name") or raw.get("keeper") or raw.get("owner") or ""),
                        "npc_role": str(raw.get("npc_role") or raw.get("role") or ""),
                        "location_name": settlement_name,
                        "sub_location": name,
                        "source": str(raw.get("source") or "create_settlement_detail"),
                    }
                )
            else:
                name = str(raw or "").strip()
                if name:
                    facilities.append(_facility_record(name, settlement_name))
        for name in _facility_names_from_structure(structure):
            if not _facility_exists(facilities, name):
                facilities.append(_facility_record(name, settlement_name))
        location.extra["settlement_structure"] = structure
        location.extra["facilities"] = facilities
        location.extra["raw_create_settlement_detail"] = _strip_response_metadata(response)
        location.flags["settlement"] = True
        location.extra["location_kind"] = "settlement"
        self._ensure_settlement_facilities(location)

        for index, item in enumerate(_as_list(response.get("residents"))):
            character = _character_from_raw(item, index, category="resident")
            subnode_id = self._assign_settlement_character_subnode(world, location, character)
            self._set_character_presence(character, settlement_name, subnode_id=subnode_id)
            world.characters[character.name] = character
        for index, item in enumerate(_as_list(response.get("adventurers"))):
            character = _character_from_raw(item, index, category="adventurer")
            subnode_id = self._assign_settlement_character_subnode(world, location, character)
            self._set_character_presence(character, settlement_name, subnode_id=subnode_id)
            world.characters[character.name] = character

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
            self._ensure_quest_reward(quest)
            world.quests.append(quest)
            existing.add(quest.name)
        world.extra["raw_settlement_quest_generator"] = _strip_response_metadata(response)

    def _ensure_quest_reward(self, quest: QuestData) -> None:
        reward = quest.extra.get("reward") or quest.extra.get("rewards")
        if isinstance(reward, dict):
            quest.extra["reward"] = reward
            return
        if isinstance(reward, list):
            quest.extra["reward"] = {"items": reward}
            return
        base = max(1, len(quest.overview or quest.name))
        quest.extra["reward"] = {
            "gold": min(300, 25 + base),
            "exp": min(80, 5 + base // 4),
            "description": "依頼達成時にギルドから支払われる基本報酬。",
        }

    def _grant_quest_reward(self, quest: QuestData) -> dict[str, Any]:
        if quest.flags.get("reward_granted"):
            return {"items": [], "lost_items": [], "gold": 0, "exp": 0, "lines": []}
        self._ensure_quest_reward(quest)
        reward = quest.extra.get("reward")
        payload: dict[str, Any] = {}
        if isinstance(reward, dict):
            payload.update(reward)
            if reward.get("items") and not payload.get("item_rewards"):
                payload["item_rewards"] = reward.get("items")
            if reward.get("gold") is not None and not any(key in payload for key in ("receive_gold", "gain_gold", "gold_delta")):
                payload["receive_gold"] = reward.get("gold")
            if reward.get("exp") is not None and not any(key in payload for key in ("reward_exp", "exp", "player_exp_delta")):
                payload["reward_exp"] = reward.get("exp")
        elif reward:
            payload["item_rewards"] = _as_list(reward)
        reward_event = self._apply_response_rewards(payload, "quest_reward")
        lines = self._apply_response_progress_effects(payload, "quest_reward")
        if lines:
            self.state.display_log.extend(lines)
        quest.flags["reward_granted"] = True
        quest.log.append({"manager": "quest_reward", "reward": reward, "lines": lines})
        return {
            **reward_event,
            "exp": _safe_int(payload.get("reward_exp") or payload.get("exp") or payload.get("player_exp_delta"), 0),
            "lines": lines,
        }

    def _finish_quest(self, quest: QuestData, status: str, source: str, response: dict[str, Any] | None = None) -> dict[str, Any]:
        final_status = status if status in {"completed", "failed", "abandoned", "cancelled"} else "completed"
        quest.status = final_status
        self.state.active_quest = ""
        event: dict[str, Any] = {
            "quest": quest.name,
            "status": final_status,
            "source": source,
            "location": self.state.current_location,
            "response": _strip_response_metadata(response or {}),
        }
        if final_status == "completed":
            event["objectives"] = self._complete_quest_objectives(quest, source=source)
            quest.extra["quest_stage"] = "completed"
            self._set_quest_flag(quest, "reported", True)
            if quest.name not in self.state.completed_quests:
                self.state.completed_quests.append(quest.name)
            event["reward"] = self._grant_quest_reward(quest)
        elif final_status in {"failed", "abandoned", "cancelled"}:
            event["objectives"] = self._close_quest_objectives(quest, final_status, source=source)
        quest.flags["finished"] = True
        quest.flags["finish_source"] = source
        quest.log.append(event)
        self.state.world_data.extra.setdefault("quest_finish_events", []).append(event)
        return event

    def _maybe_finish_active_quest_from_response(self, response: dict[str, Any], source: str, action: str) -> dict[str, Any] | None:
        return None

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

    def _append_character_enrichment_error(
        self,
        world: WorldData,
        manager_name: str,
        character: CharacterData,
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

    def _create_character(
        self,
        player_name: str,
        premise: str,
        world: WorldData,
        character: CharacterData,
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

    def _create_look(self, player_name: str, world: WorldData, character: CharacterData) -> dict[str, Any]:
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
        character: CharacterData,
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
        character_payload = _ai_json(_character_ai_context(character))
        power_instruction = _skill_trait_power_instruction(character)
        seed_instruction = _character_entry_seed_instruction(seed_name, seed_description)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのキャラクター特徴作成担当です。"
                    "Fantasiaのcreate_trait相当として、traits を持つJSONだけを返してください。"
                    "traits は性格、特徴、重症度、行動への影響を含むオブジェクト配列にしてください。"
                    "各体質/特徴には power と strength_level を1から5の整数で必ず付けてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    f"{power_instruction}\n"
                    f"{seed_instruction}\n"
                    "このキャラクターの性格/特徴/重症度/行動影響を生成してください。"
                ),
            },
        ]
        return self._chat_json(
            "create_trait",
            messages,
            max_tokens=650,
            world_name=world.world_name,
            player_name=player_name,
        )

    def _create_skill(
        self,
        player_name: str,
        world: WorldData,
        character: CharacterData,
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
        character_payload = _ai_json(_character_ai_context(character))
        power_instruction = _skill_trait_power_instruction(character)
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
                    "skills は effects, skill_type, sp_cost, usefulness を含むオブジェクト配列にしてください。"
                    "skills の各要素には element を必ず含め、指定された属性IDだけを使ってください。"
                    "各スキルには power と strength_level を1から5の整数で必ず付けてください。"
                    "回数制ではなくSP制です。強力なスキルほどsp_costを高くしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"世界データ: {world_payload}\n"
                    f"キャラクター名: {character.name}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    f"{power_instruction}\n"
                    f"利用可能な属性ID: {element_options}\n"
                    f"今回生成するスキルの属性ID: {element_id}（{element_label}）\n"
                    f"{seed_instruction}\n"
                    "このキャラクターのスキル、効果、属性、SPコスト、有用性を生成してください。"
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

    def _apply_character_profile(self, character: CharacterData, response: dict[str, Any]) -> None:
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

    def _apply_character_look(self, character: CharacterData, response: dict[str, Any]) -> None:
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

    def _apply_character_traits(self, character: CharacterData, response: dict[str, Any]) -> None:
        traits = [_normalise_trait(item) for item in _as_list(response.get("traits"))]
        traits = [trait for trait in traits if trait.get("name")]
        traits = _limit_power_entries_for_actor(character, traits, used_power=0)
        if traits:
            character.traits = traits
        character.extra["raw_create_trait"] = _strip_response_metadata(response)

    def _apply_character_skills(self, character: CharacterData, response: dict[str, Any]) -> None:
        skills = [_normalise_skill(item) for item in _as_list(response.get("skills"))]
        skills = [skill for skill in skills if skill.get("name")]
        skills = _limit_power_entries_for_actor(character, skills, used_power=_entry_power_total(character.traits))
        if skills:
            character.skills = skills
        character.extra["raw_create_skill"] = _strip_response_metadata(response)

    def _append_character_history(
        self,
        world: WorldData,
        manager_name: str,
        character: CharacterData,
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

    def generate_cg_image(self) -> ImageResult:
        request = self.state.flags.get("pending_cg_request")
        if not isinstance(request, dict):
            request = {}
        location = str(request.get("location") or self.state.current_location or self.state.world_data.starting_location or "unknown")
        visual_characters, visual_monsters = self._active_visual_subjects(location)
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

    def _character_image_creator(self, character: CharacterData) -> dict[str, Any]:
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

    def _monster_image_creator(self, monster: CharacterData) -> dict[str, Any]:
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
        visual_characters: list[CharacterData] | None = None,
        visual_monsters: list[CharacterData] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=True, include_monsters=False, include_quests=True))
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

    def resolve_choice(self, choice: str) -> str:
        if self._is_game_over():
            return self.state.log_text(16)
        return self._resolve_player_input(choice, "choice")

    def resolve_action(self, action: str) -> str:
        if self._is_game_over():
            return self.state.log_text(16)
        return self._resolve_player_input(action, "free_action")

    def _resolve_player_input(self, action: str, input_type: str) -> str:
        action_text = action.strip() or "周囲を見る"
        before_context = self._input_dedupe_context()
        if self._is_repeated_player_input(action_text, input_type, before_context):
            return self.state.log_text(16)

        def finish(result: str) -> str:
            self._remember_resolved_input(action_text, input_type, before_context)
            return result

        timeout_event = self._fail_expired_active_quest(source="quest_deadline", append_log=True)
        if timeout_event:
            self.save_game()
            return finish(self.state.log_text(16))

        illegal_check = self._check_illegal_content(action_text, input_type)
        if _as_bool(illegal_check.get("content_violation")):
            message = str(illegal_check.get("message") or illegal_check.get("reason") or "その行動は処理されませんでした。")
            self.state.append_turn(
                action_text,
                message,
                self.state.current_location,
                self.state.choices,
                input_type=input_type,
            )
            self.state.world_data.history.append(
                {
                    "manager": "check_illegal_content",
                    "action": action_text,
                    "input_type": input_type,
                    "response": _strip_response_metadata(illegal_check),
                }
            )
            self.save_game()
            return self.state.log_text(16)

        if not self.allow_any_action_concept:
            feasibility_check = self._check_action_feasibility(action_text, input_type)
            if not _as_bool(feasibility_check.get("action_possible")):
                message = str(
                    feasibility_check.get("message")
                    or feasibility_check.get("reason")
                    or "その行動は、現在の状況では実現できない。"
                )
                self.state.append_turn(
                    action_text,
                    message,
                    self.state.current_location,
                    self.state.choices,
                    input_type=input_type,
                )
                self.state.world_data.history.append(
                    {
                        "manager": "check_action_feasibility",
                        "action": action_text,
                        "input_type": input_type,
                        "allowed": False,
                        "response": _strip_response_metadata(feasibility_check),
                    }
                )
                self.save_game()
                return self.state.log_text(16)

        block_reason = self._player_incapacitated_action_block(action_text)
        if block_reason:
            return finish(self._resolve_blocked_player_action(action_text, input_type, block_reason))

        guard_result = self._maybe_start_guard_encounter(action_text, input_type)
        if guard_result:
            return finish(guard_result)

        active_encounter = self._active_encounter()
        if active_encounter:
            return finish(self._resolve_encounter_input(action_text, input_type, active_encounter))

        home_result = self._resolve_home_action(action_text, input_type)
        if home_result is not None:
            return finish(home_result)

        if _is_attack_action(action_text):
            if _is_surprise_attack_action(action_text):
                return finish(self._resolve_player_attack(action_text, input_type))
            return finish(self._start_encounter_from_attack(action_text, input_type))

        craft_result = self._resolve_craft_action(action_text, input_type)
        if craft_result is not None:
            return finish(craft_result)

        trade_negotiation_target = self._trade_negotiation_target(action_text)
        if trade_negotiation_target:
            return finish(self._resolve_trade_negotiation_action(action_text, input_type, trade_negotiation_target))

        facility_result = self._create_facility_from_action(action_text, input_type)
        if facility_result is not None:
            return finish(facility_result)

        quest_to_start = self._find_quest_to_start(action_text)
        if quest_to_start:
            return finish(self._start_quest(action_text, input_type, quest_to_start))

        if self.state.active_quest:
            active_quest = self._find_quest_by_name(self.state.active_quest)
            if active_quest:
                action_roll = self._action_roll_for_input(action_text, input_type, "quest")
                return finish(self._resolve_active_quest_action(action_text, input_type, active_quest, action_roll=action_roll))
            self.state.active_quest = ""

        active_conversation = self._active_conversation_character()
        if active_conversation:
            action_roll = self._action_roll_for_input(action_text, input_type, "conversation")
            return finish(self._continue_conversation(action_text, input_type, active_conversation, action_roll=action_roll))

        conversation_target = self._find_conversation_target(action_text)
        if conversation_target:
            return finish(self._start_conversation(action_text, input_type, conversation_target))

        action_roll: dict[str, Any] | None = None
        if _is_exploration_action(action_text):
            action_roll = self._action_roll_for_input(action_text, input_type, "exploration")
            field_event = self._field_event_evaluator(action_text, input_type, action_roll=action_roll)
            if _as_bool(field_event.get("event_occurred")):
                return finish(self._apply_field_event(action_text, input_type, field_event, action_roll=action_roll))
            self.state.world_data.history.append(
                {
                    "manager": "field_event_evaluator",
                    "action": action_text,
                    "input_type": input_type,
                    "action_roll": action_roll,
                    "event_occurred": False,
                    "response": _strip_response_metadata(field_event),
                }
            )

        if action_roll is None:
            action_roll = self._action_roll_for_input(action_text, input_type, "action")
        return finish(self._resolve_master_ai_turn(action_text, input_type, action_roll=action_roll))

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
        content_violation = _as_bool(response.get("content_violation"))
        narration = str(
            response.get("narration")
            or response.get("text")
            or response.get("message")
            or response.get("reason")
            or "進行は静かに保留された。"
        )
        location = str(response.get("location") or self.state.current_location)
        movement_result = {"location": location, "narration_lines": [], "status_lines": []}
        if not content_violation:
            movement_result = self._normalize_world_response_location(action, input_type, response, location)
            location = str(movement_result.get("location") or location)
            movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
            if movement_narration:
                narration = "\n".join([narration, *movement_narration]).strip()
        choices = _as_str_list(response.get("choices")) or self.state.choices
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

        generated_npcs: list[CharacterData] = []
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
            response,
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
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._set_player_presence(location)
        self._append_action_roll_log(action_roll)
        status_lines = [] if content_violation else self._apply_response_status_effects(response, "master_ai_facilitator", default_target="player")
        if not content_violation:
            status_lines.extend(str(line) for line in movement_result.get("status_lines", []) if str(line).strip())
            status_lines.extend(self._apply_response_hp_effects(response, "master_ai_facilitator"))
            status_lines.extend(self._apply_response_sp_effects(response, "master_ai_facilitator"))
            status_lines.extend(self._apply_response_progress_effects(response, "master_ai_facilitator"))
            status_lines.extend(self._apply_response_world_state_effects(response, "master_ai_facilitator", default_location=location))
            status_lines.extend(self._apply_crime_risk(action, response, "master_ai_facilitator", location=location))
        if status_lines:
            self.state.display_log.extend(status_lines)
            history_entry["status_effects_applied"] = status_lines
        self._apply_visual_intent(response, "master_ai_facilitator", location, previous_location)
        if not content_violation:
            reward_event = self._apply_response_rewards(response, "master_ai_facilitator")
            if reward_event["items"] or reward_event.get("skipped_items") or reward_event["lost_items"] or reward_event["gold"]:
                history_entry["rewards"] = reward_event
        self.save_game()
        return self.state.log_text(16)

    def _generate_master_ai_npcs(
        self,
        action: str,
        input_type: str,
        facilitator_response: dict[str, Any],
        location: str,
    ) -> list[CharacterData]:
        requests = _dedupe_npc_requests(
            _npc_generation_requests(facilitator_response)
            + _infer_npc_generation_requests(facilitator_response, action, location, self.state.world_data)
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
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        facilitator_payload = json.dumps(_strip_response_metadata(facilitator_response), ensure_ascii=False)
        request_payload = json.dumps(requests, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC生成担当です。"
                    "Fantasiaのmaster_ai_npc_generater相当として、"
                    "master_ai_facilitatorが必要とした未登場NPCを生成してください。"
                    "NPCカテゴリ、説明、性格、外見、職業、archetype、skillsを持つJSONだけを返してください。"
                    "skillsやtraitsを返す場合は各項目にpowerとstrength_levelを1から5で付け、"
                    "序盤・一般NPCは合計4〜8、通常NPCは8〜12、終盤・精鋭・ボス級は16〜25を目安にしてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {location}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"master_ai_facilitator応答: {facilitator_payload}\n"
                    f"NPC生成要求: {request_payload}\n"
                    "既存NPCと重複しない、現在の場面で自然に登場できるNPCを生成してください。"
                ),
            },
        ]
        return self._chat_json(
            "master_ai_npc_generater",
            messages,
            max_tokens=900,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _npc_detail_generater(
        self,
        action: str,
        input_type: str,
        facilitator_response: dict[str, Any],
        character: CharacterData,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False))
        character_payload = _ai_json(_character_ai_context(character))
        facilitator_payload = json.dumps(_strip_response_metadata(facilitator_response), ensure_ascii=False)
        power_instruction = _skill_trait_power_instruction(character)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC詳細補完担当です。"
                    "Fantasiaのnpc_detail_generater相当として、"
                    "話し方、archetype、skills、会話トピック、行動方針を補完してください。"
                    "必ず name, talk_style, archetype, skills を持つJSONだけを返してください。"
                    "skillsにはpowerとstrength_levelを1から5で必ず付けてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"master_ai_facilitator応答: {facilitator_payload}\n"
                    f"対象キャラクター: {character.name}\n"
                    f"キャラクターデータ: {character_payload}\n"
                    f"{power_instruction}\n"
                    "このNPCを会話、探索、戦闘判断で使えるように詳細化してください。"
                ),
            },
        ]
        return self._chat_json(
            "npc_detail_generater",
            messages,
            max_tokens=750,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _apply_master_ai_npcs(self, response: dict[str, Any], location: str) -> list[CharacterData]:
        raw_npcs = _as_list(response.get("npcs") or response.get("characters") or response.get("npc"))
        generated: list[CharacterData] = []
        for item in raw_npcs:
            character = _npc_from_raw(item, len(self.state.world_data.characters) + len(generated))
            if _world_has_dead_npc_identity(self.state.world_data, name=character.name, uuid=character.uuid):
                continue
            character.name = _unique_character_name(self.state.world_data, character.name)
            character.flags.setdefault("source", "master_ai_npc_generater")
            character.flags.setdefault("generated", True)
            if location:
                character.flags.setdefault("first_seen_location", location)
                self._set_character_presence(character, location)
            character.extra["raw_master_ai_npc_generater"] = _strip_response_metadata(response)
            self.state.world_data.characters[character.name] = character
            generated.append(character)

            self.state.world_data.extra.setdefault("generated_npcs", []).append(
                {
                    "manager": "master_ai_npc_generater",
                    "name": character.name,
                    "location": location,
                    "response": _strip_response_metadata(response),
                }
            )
        return generated

    def _apply_npc_detail(self, character: CharacterData, response: dict[str, Any]) -> None:
        generated_name = str(response.get("name") or "").strip()
        if generated_name and generated_name != character.name:
            character.extra["detail_generated_name"] = generated_name
        if response.get("talk_style") is not None:
            character.extra["talk_style"] = str(response.get("talk_style") or "")
        if response.get("archetype") is not None:
            character.extra["archetype"] = str(response.get("archetype") or "")
        if response.get("behavior_policy") is not None:
            character.extra["behavior_policy"] = str(response.get("behavior_policy") or "")
        if response.get("conversation_topics") is not None:
            character.extra["conversation_topics"] = _as_str_list(response.get("conversation_topics"))
        if response.get("memory_updates") is not None:
            character.extra["memory_updates"] = _as_list(response.get("memory_updates"))
        if response.get("relationship") is not None:
            character.extra["relationship"] = response.get("relationship")
        response_location = str(response.get("location") or response.get("current_location") or "").strip()
        if response_location:
            self._set_character_presence(character, response_location, str(response.get("state") or character.state or "present"))
        elif character.location:
            self._set_character_presence(character, character.location, character.state or "present")

        detail_skills = [_normalise_skill(item) for item in _as_list(response.get("skills"))]
        detail_skills = [skill for skill in detail_skills if skill.get("name")]
        if detail_skills:
            merged_skills = _merge_named_dicts(character.skills, detail_skills)
            character.skills = _limit_power_entries_for_actor(
                character,
                merged_skills,
                used_power=_entry_power_total(character.traits),
            )
        self._apply_response_status_effects(response, "npc_detail_generater", default_target=character.name, context_character=character)
        character.extra["raw_npc_detail_generater"] = _strip_response_metadata(response)

    def _master_ai_facilitator(
        self,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        recent_log = self.state.log_text(10)
        prior_summaries = json.dumps(
            self.state.world_data.extra.get("master_ai_process_summaries", [])[-5:],
            ensure_ascii=False,
        )
        action_roll_payload = json.dumps(action_roll or {}, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの中核進行管理AIです。"
                    "Fantasiaのmaster_ai_facilitator相当として、"
                    "入力の解釈、進行、状態更新候補、次の選択肢をまとめてください。"
                    "content_violation はゲーム側では判定しないため、LLMとしてのみ判断してください。"
                    "必ず content_violation, think, narration, process, finished を持つJSONだけを返してください。"
                    "通常進行できる場合は content_violation を false にしてください。"
                    "game_side_action_roll が enabled=true の場合、成否・強制成功・強制失敗はゲーム側の確定判定として必ず尊重してください。"
                    "通常の移動はworld_mapの隣接地点だけにしてください。テレポート、ポータル等の明示的な処理がない限り遠隔地へ直接移動させないでください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"直近ログ:\n{recent_log}\n"
                    f"直近のmaster_ai要約:\n{prior_summaries}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"game_side_action_roll: {action_roll_payload}\n"
                    "プレイヤー行動が現在地にいる既存NPCの名前、役割、別名を指している場合は、その既存NPCを対象にしてください。"
                    "その人物を new_npc_requests で再生成しないでください。"
                    "プレイヤー、主人公、あなた、自分、PC はNPC名として扱わないでください。"
                    "この行動を中核AIとして進行し、必要なprocessと次の選択肢を返してください。"
                ),
            },
        ]
        return self._chat_json(
            "master_ai_facilitator",
            messages,
            max_tokens=900,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

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
        if self._encounter_has_surrendered_opponents(encounter) and _is_accept_surrender_action(action):
            return self._accept_opponent_surrender(action, input_type, encounter)
        block_reason = self._player_incapacitated_action_block(action, encounter=encounter, for_movement=False)
        if block_reason:
            return self._resolve_blocked_player_action(action, input_type, block_reason, encounter=encounter)
        if _is_skill_action(action):
            return self._resolve_player_skill(action, input_type, encounter)
        if _is_escape_action(action):
            return self._resolve_player_any_input(action, input_type, encounter)
        if _is_attack_action(action):
            return self._resolve_player_attack(action, input_type, encounter)
        return self._resolve_player_any_input(action, input_type, encounter)

    def _start_encounter_from_attack(self, action: str, input_type: str) -> str:
        encounter = self._ensure_encounter(action)
        encounter["status"] = "active"
        self.state.flags["active_encounter"] = encounter
        self.state.flags["screen_mode"] = "battle"
        opponent_name = str(encounter.get("opponent_name") or "敵")
        location = str(encounter.get("location") or self.state.current_location)
        narration = f"{opponent_name}があなたの敵意に反応し、戦闘態勢に入った。"
        self.state.append_turn(action, narration, location, self._encounter_choices(encounter), input_type=input_type)
        self.state.world_data.extra.setdefault("encounters", []).append(
            {
                "event": "engage",
                "action": action,
                "opponent_type": encounter.get("opponent_type"),
                "opponent_name": opponent_name,
                "location": location,
            }
        )
        self._request_background_if_needed(location)
        self.save_game()
        return self.state.log_text(16)

    def _resolve_player_skill(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        skill_name = _extract_skill_name(action)
        skill = self._find_player_skill(skill_name)
        if not skill:
            narration = f"スキル「{skill_name or action}」は使用できない。"
            self.state.flags["screen_mode"] = "battle"
            self.state.append_turn(action, narration, str(encounter.get("location") or self.state.current_location), self._encounter_choices(encounter), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        cost = max(0, _safe_int(skill.get("sp_cost"), _skill_sp_cost(skill)))
        max_sp = self._hp_number(encounter.get("player_max_sp"), self._player_max_sp())
        current_sp = max(0, min(max_sp, self._hp_number(encounter.get("player_sp"), self._player_current_sp(max_sp))))
        if cost > current_sp:
            narration = f"SPが足りない。{skill.get('name')} はSP {cost} 必要。"
            self.state.flags["screen_mode"] = "battle"
            self.state.append_turn(action, narration, str(encounter.get("location") or self.state.current_location), self._encounter_choices(encounter), input_type=input_type)
            self.save_game()
            return self.state.log_text(16)
        if cost:
            event = self._apply_player_sp_delta(-cost, source="skill", reason=str(skill.get("name") or ""), encounter=encounter)
            if event.get("line"):
                encounter.setdefault("pending_resource_lines", []).append(str(event["line"]))
        self._select_encounter_target_from_action(encounter, action)
        player_response = self._referee_player_any_input_new_new(action, input_type, encounter)
        self._strip_game_controlled_hp_updates(player_response, target="opponent")
        self._strip_game_controlled_hp_updates(player_response, target="player")
        self._apply_encounter_update(encounter, player_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, player_response, "opponent")
        if _as_bool(player_response.get("content_violation")):
            return self._finish_content_violation_encounter_turn(
                action,
                input_type,
                encounter,
                player_response,
                "referee_player_any_input_new_new",
            )
        self._apply_player_skill_resolution(encounter, skill, player_response, action)
        return self._resolve_npc_turn(action, input_type, encounter, player_response, "referee_player_any_input_new_new")

    def _find_player_skill(self, name: str) -> dict[str, Any] | None:
        needle = str(name or "").strip().lower()
        for skill in self._player_skills():
            skill_name = str(skill.get("name") or "").strip()
            if not skill_name:
                continue
            if not needle or skill_name.lower() == needle or skill_name.lower() in needle or needle in skill_name.lower():
                return skill
        return None

    def _player_skills(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        player = self.state.world_data.characters.get(self.state.player_name)
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

    def _strip_game_controlled_hp_updates(self, response: dict[str, Any], *, target: str) -> None:
        if not isinstance(response, dict):
            return
        top_keys = _game_controlled_hp_keys(target, top_level=True)
        for key in list(response.keys()):
            if str(key).strip().lower() in top_keys:
                response.pop(key, None)
        if "encounter_update" in response:
            response["encounter_update"] = _strip_hp_update_value(response.get("encounter_update"), target)

    def _apply_player_attack_damage(self, encounter: dict[str, Any], response: dict[str, Any], action: str) -> None:
        old_hp = max(0, _safe_int(encounter.get("opponent_hp"), 0))
        max_hp = max(old_hp, _safe_int(encounter.get("opponent_max_hp"), old_hp or 1))
        attack = max(0, _safe_int(encounter.get("player_attack"), 0) + _safe_int(encounter.get("player_attack_bonus"), 0))
        defense = max(0, _safe_int(encounter.get("opponent_defense"), 0))
        attrs = self._player_attributes()
        strength = max(1, _safe_int(attrs.get("str"), 10))
        strength_factor = strength / 10.0
        weakness = _combat_weakness_multiplier(response)
        base = max(1, attack - defense)
        raw_damage = base * strength_factor * weakness
        damage = 0 if weakness <= 0 else max(1, int(round(raw_damage)))
        result = self._apply_opponent_hp_delta(
            encounter,
            -damage,
            source="player_attack",
            reason="attack",
        )
        calc = {
            "type": "player_attack",
            "action": action,
            "attack": attack,
            "defense": defense,
            "base_damage": base,
            "strength": strength,
            "strength_factor": round(strength_factor, 3),
            "weakness_multiplier": weakness,
            "damage": damage,
            "old_hp": old_hp,
            "new_hp": result.get("new_hp", old_hp),
            "max_hp": max_hp,
        }
        narration = self._combat_damage_narration(
            actor_name=self.state.player_name or "Player",
            target_name=str(encounter.get("opponent_name") or "相手"),
            action_name=action or "攻撃",
            source_response=response,
            combat_result=calc,
        )
        if narration:
            response["narration"] = narration
            calc["narration"] = narration
        response["game_combat_result"] = calc
        self.state.world_data.extra.setdefault("combat_events", []).append(dict(calc))
        for line in result.get("lines", []):
            encounter.setdefault("pending_resource_lines", []).append(str(line))

    def _apply_player_skill_resolution(
        self,
        encounter: dict[str, Any],
        skill: dict[str, Any],
        response: dict[str, Any],
        action: str,
    ) -> None:
        skill = _normalise_skill(skill)
        skill_name = str(skill.get("name") or action or "スキル")
        healing = _skill_is_healing(skill, response)
        power = _entry_power(skill, fallback=_skill_power_from_text(skill))
        ability = _combat_ability_from_response(response, skill=skill, healing=healing)
        attrs = self._player_attributes()
        ability_score = max(1, _safe_int(attrs.get(ability), 10))
        raw_power = ability_score * 5 * max(SKILL_TRAIT_POWER_MIN, min(SKILL_TRAIT_POWER_MAX, power))
        if healing:
            result = self._apply_player_hp_delta(raw_power, source="player_skill", reason=skill_name, encounter=encounter)
            actual = max(0, _safe_int(result.get("actual_delta"), 0))
            calc = {
                "type": "player_skill_heal",
                "skill": skill_name,
                "ability": ability,
                "ability_score": ability_score,
                "power": power,
                "healing": raw_power,
                "actual_healing": actual,
                "old_hp": result.get("old_hp"),
                "new_hp": result.get("new_hp"),
                "max_hp": result.get("max_hp"),
            }
            narration = self._combat_heal_narration(
                actor_name=self.state.player_name or "Player",
                target_name=self.state.player_name or "Player",
                action_name=action or skill_name,
                skill_name=skill_name,
                source_response=response,
                combat_result=calc,
            )
            if narration:
                response["narration"] = narration
                calc["narration"] = narration
            lines = []
            if result.get("line"):
                lines.append(str(result["line"]))
        else:
            defense_applies = _combat_apply_defense(response, default=_skill_default_uses_defense(skill))
            defense = max(0, _safe_int(encounter.get("opponent_defense"), 0)) if defense_applies else 0
            weakness = _combat_weakness_multiplier(response)
            before_weakness = max(0, raw_power - defense)
            raw_damage = before_weakness * weakness
            damage = 0 if weakness <= 0 or before_weakness <= 0 else max(1, int(round(raw_damage)))
            max_hp = max(1, _safe_int(encounter.get("opponent_max_hp"), _safe_int(encounter.get("opponent_hp"), 1)))
            result = self._apply_opponent_hp_delta(
                encounter,
                -damage,
                source="player_skill",
                reason=skill_name,
            )
            calc = {
                "type": "player_skill_damage",
                "skill": skill_name,
                "ability": ability,
                "ability_score": ability_score,
                "power": power,
                "raw_power": raw_power,
                "defense_applies": defense_applies,
                "defense": defense,
                "weakness_multiplier": weakness,
                "damage": damage,
                "old_hp": result.get("old_hp"),
                "new_hp": result.get("new_hp"),
                "max_hp": result.get("max_hp"),
            }
            narration = self._combat_damage_narration(
                actor_name=self.state.player_name or "Player",
                target_name=str(encounter.get("opponent_name") or "相手"),
                action_name=action or skill_name,
                source_response=response,
                combat_result=calc,
            )
            if narration:
                response["narration"] = narration
                calc["narration"] = narration
            lines = [str(line) for line in result.get("lines", [])]
        calc["action"] = action
        response["game_combat_result"] = calc
        self.state.world_data.extra.setdefault("combat_events", []).append(dict(calc))
        for line in lines:
            encounter.setdefault("pending_resource_lines", []).append(str(line))

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
        if isinstance(opponent, CharacterData):
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
        if isinstance(opponent, CharacterData):
            opponent.current_hp = new_hp
            opponent.max_hp = max_hp
            opponent.extra["current_hp"] = new_hp
            opponent.extra["max_hp"] = max_hp
            self._sync_encounter_opponent_entry(encounter, opponent)
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        name = str((opponent.name if isinstance(opponent, CharacterData) else "") or encounter.get("opponent_name") or "相手")
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
        character: CharacterData,
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

    def _apply_npc_action_tool(
        self,
        encounter: dict[str, Any],
        npc_response: dict[str, Any],
        rewrite_response: dict[str, Any],
    ) -> dict[str, Any]:
        action = _npc_action_tool_kind(npc_response, rewrite_response)
        if action == "surrender":
            return self._npc_surrender_from_encounter(encounter)
        if action == "flee":
            return self._npc_flee_from_encounter(encounter)
        return {"acted": False, "lines": []}

    def _npc_surrender_from_encounter(self, encounter: dict[str, Any]) -> dict[str, Any]:
        opponent = self._encounter_opponent(encounter)
        if not isinstance(opponent, CharacterData):
            encounter["opponent_status"] = SURRENDERED_STATUS_ID
            return {"acted": True, "kind": "surrender", "lines": ["> [戦闘] 相手は降伏し、行動を止めた。"]}
        effect = _normalise_status_effect(
            {
                "id": SURRENDERED_STATUS_ID,
                "name": "降伏",
                "description": "戦闘で降伏し、敵対行動を止めている。",
                "duration": 0,
                "combat_state": SURRENDERED_STATUS_ID,
            },
            source="npc_surrender",
        )
        _merge_status_effect(opponent.status_effects, effect)
        opponent.flags["surrendered"] = True
        opponent.flags["hostile"] = False
        opponent.extra["surrendered"] = True
        opponent.extra["hostile"] = False
        self._set_encounter_opponent_combat_status(encounter, opponent, SURRENDERED_STATUS_ID)
        return {"acted": True, "kind": "surrender", "lines": [f"> [戦闘] {opponent.name}は降伏し、行動を止めた。"]}

    def _npc_flee_from_encounter(self, encounter: dict[str, Any]) -> dict[str, Any]:
        opponent = self._encounter_opponent(encounter)
        if not isinstance(opponent, CharacterData):
            encounter["opponent_status"] = FLED_STATUS_ID
            encounter["status"] = "ended"
            return {"acted": True, "kind": "flee", "lines": ["> [戦闘] 相手は逃亡し、戦闘から外れた。"]}
        location = str(encounter.get("location") or opponent.location or self.state.current_location)
        destination = self._npc_flee_destination(opponent, location)
        opponent.flags["fled_from_combat"] = True
        opponent.extra["fled_from_combat"] = True
        self._set_encounter_opponent_combat_status(encounter, opponent, FLED_STATUS_ID)
        if destination.get("location"):
            self._set_character_presence(
                opponent,
                str(destination["location"]),
                "present",
                subnode_id=str(destination.get("subnode") or ""),
            )
            label = str(destination.get("label") or destination.get("location") or "")
            line = f"> [戦闘] {opponent.name}は{label}へ逃亡し、戦闘から外れた。"
        else:
            opponent.state = FLED_STATUS_ID
            opponent.flags["state"] = FLED_STATUS_ID
            opponent.extra["state"] = FLED_STATUS_ID
            line = f"> [戦闘] {opponent.name}はその場から逃げ去り、戦闘から外れた。"
        return {"acted": True, "kind": "flee", "lines": [line]}

    def _npc_flee_destination(self, character: CharacterData, location: str) -> dict[str, str]:
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
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self.save_game()
        return self.state.log_text(16)

    def _apply_npc_combat_damage(
        self,
        encounter: dict[str, Any],
        npc_response: dict[str, Any],
        rewrite_response: dict[str, Any],
    ) -> list[str]:
        if int(encounter.get("opponent_hp") or 0) <= 0:
            return []
        opponent = self._encounter_opponent(encounter)
        if isinstance(opponent, CharacterData) and self._character_has_surrendered(opponent, encounter):
            return []
        if _surrender_control_prevents_npc_damage(encounter, npc_response, rewrite_response):
            return []
        if not _npc_response_is_offensive(npc_response, rewrite_response):
            return []
        attack = max(0, _safe_int(encounter.get("opponent_attack"), 0))
        defense = max(0, _safe_int(encounter.get("player_defense"), 0) + _safe_int(encounter.get("player_defense_bonus"), 0))
        weakness = _combat_weakness_multiplier(
            rewrite_response,
            default=_combat_weakness_multiplier(npc_response, default=1.0),
        )
        base = max(1, attack - defense)
        raw_damage = base * weakness
        damage = 0 if weakness <= 0 else max(1, int(round(raw_damage)))
        opponent_name = str(encounter.get("opponent_name") or "相手")
        max_hp = max(1, _safe_int(encounter.get("player_max_hp"), self._player_max_hp()))
        event = self._apply_player_hp_delta(-damage, source="npc_attack", reason=opponent_name, encounter=encounter)
        calc = {
            "type": "npc_attack",
            "opponent": opponent_name,
            "attack": attack,
            "defense": defense,
            "base_damage": base,
            "weakness_multiplier": weakness,
            "damage": damage,
            "player_old_hp": event.get("old_hp"),
            "player_new_hp": event.get("new_hp"),
            "player_max_hp": event.get("max_hp"),
        }
        narration = self._combat_damage_narration(
            actor_name=opponent_name,
            target_name=self.state.player_name or "Player",
            action_name=f"{opponent_name}の攻撃",
            source_response=rewrite_response or npc_response,
            combat_result=calc,
        )
        if narration:
            target_response = rewrite_response if isinstance(rewrite_response, dict) and rewrite_response else npc_response
            target_response["narration"] = narration
            calc["narration"] = narration
        lines = []
        if event.get("line"):
            lines.append(str(event["line"]))
        rewrite_response["game_combat_result"] = calc
        self.state.world_data.extra.setdefault("combat_events", []).append(dict(calc))
        return lines

    def _resolve_player_attack(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any] | None = None,
    ) -> str:
        encounter = encounter or self._ensure_encounter(action)
        self._select_encounter_target_from_action(encounter, action)
        player_response = self._referee_player_attack_new_new(action, input_type, encounter)
        self._strip_game_controlled_hp_updates(player_response, target="opponent")
        self._apply_encounter_update(encounter, player_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, player_response, "opponent")
        self._apply_player_attack_damage(encounter, player_response, action)
        return self._resolve_npc_turn(action, input_type, encounter, player_response, "referee_player_attack_new_new")

    def _resolve_player_any_input(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
        self._select_encounter_target_from_action(encounter, action)
        player_response = self._referee_player_any_input_new_new(action, input_type, encounter)
        self._apply_encounter_update(encounter, player_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, player_response, "opponent")
        if _as_bool(player_response.get("content_violation")):
            narration = str(player_response.get("narration") or player_response.get("message") or "その行動は戦闘に反映されなかった。")
            choices = _as_str_list(player_response.get("choices")) or self._encounter_choices(encounter)
            previous_location = self.state.current_location
            location = str(encounter.get("location") or self.state.current_location)
            self._record_encounter_turn(
                action,
                input_type,
                encounter,
                [
                    {
                        "manager": "referee_player_any_input_new_new",
                        "response": _strip_response_metadata(player_response),
                    }
                ],
            )
            self.state.flags["screen_mode"] = "battle"
            self.state.append_turn(action, narration, location, choices, input_type=input_type)
            self._apply_visual_intent(player_response, "referee_player_any_input_new_new", location, previous_location)
            self.save_game()
            return self.state.log_text(16)
        return self._resolve_npc_turn(action, input_type, encounter, player_response, "referee_player_any_input_new_new")

    def _finish_content_violation_encounter_turn(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        player_response: dict[str, Any],
        manager_name: str,
    ) -> str:
        narration = str(player_response.get("narration") or player_response.get("message") or "その行動は戦闘に反映されなかった。")
        choices = _as_str_list(player_response.get("choices")) or self._encounter_choices(encounter)
        previous_location = self.state.current_location
        location = str(encounter.get("location") or self.state.current_location)
        self._record_encounter_turn(
            action,
            input_type,
            encounter,
            [
                {
                    "manager": manager_name,
                    "response": _strip_response_metadata(player_response),
                }
            ],
        )
        self.state.flags["screen_mode"] = "battle"
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._apply_visual_intent(player_response, manager_name, location, previous_location)
        self.save_game()
        return self.state.log_text(16)

    def _resolve_group_npc_turn(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        player_response: dict[str, Any],
        player_manager: str,
        status_lines: list[str],
    ) -> str:
        location = str(encounter.get("location") or self.state.current_location)
        previous_location = self.state.current_location
        manager_records: list[dict[str, Any]] = [
            {"manager": player_manager, "response": _strip_response_metadata(player_response)}
        ]
        narration_parts: list[str] = [str(player_response.get("narration") or player_response.get("text") or "")]
        terminal_outcome = self._apply_encounter_outcome(encounter)
        status_lines.extend(self._apply_quest_encounter_outcome(encounter, terminal_outcome))
        if terminal_outcome.get("narration"):
            narration_parts.append(str(terminal_outcome.get("narration") or ""))

        finished = _as_bool(player_response.get("finished")) or _as_bool(terminal_outcome.get("ended"))
        if not finished and not self._is_game_over():
            for opponent in list(self._acting_encounter_opponents(encounter))[:COMBAT_MAX_OPPONENTS]:
                self._set_encounter_active_opponent(encounter, opponent)
                if max(0, _safe_int(opponent.current_hp, 0)) <= 0:
                    continue
                npc_response = self._referee_npc(action, input_type, encounter, player_response)
                self._strip_game_controlled_hp_updates(npc_response, target="player")
                self._apply_encounter_update(encounter, npc_response.get("encounter_update"))
                self._apply_response_implied_statuses(encounter, npc_response, "player")
                status_lines.extend(self._apply_response_hp_effects(npc_response, "referee_npc", encounter=encounter))
                status_lines.extend(self._apply_response_sp_effects(npc_response, "referee_npc", encounter=encounter))
                status_lines.extend(self._apply_response_progress_effects(npc_response, "referee_npc", encounter=encounter))
                status_lines.extend(
                    self._apply_response_world_state_effects(
                        npc_response,
                        "referee_npc",
                        default_character=opponent,
                        default_location=location,
                    )
                )

                if max(0, _safe_int(opponent.current_hp, 0)) <= 0:
                    rewrite_response: dict[str, Any] = {}
                else:
                    rewrite_response = self._referee_npc_rewrite(action, input_type, encounter, player_response, npc_response)
                self._strip_game_controlled_hp_updates(rewrite_response, target="player")
                self._apply_encounter_update(encounter, rewrite_response.get("encounter_update"))
                self._apply_response_implied_statuses(encounter, rewrite_response, "player")
                status_lines.extend(self._apply_response_hp_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
                status_lines.extend(self._apply_response_sp_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
                status_lines.extend(self._apply_response_progress_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
                status_lines.extend(
                    self._apply_response_world_state_effects(
                        rewrite_response,
                        "referee_npc_rewrite",
                        default_character=opponent,
                        default_location=location,
                    )
                )
                npc_tool_result = self._apply_npc_action_tool(encounter, npc_response, rewrite_response)
                npc_tool_kind = str(npc_tool_result.get("kind") or "")
                status_lines.extend(str(line) for line in npc_tool_result.get("lines", []) if line)
                if not _as_bool(npc_tool_result.get("acted")):
                    status_lines.extend(self._apply_npc_combat_damage(encounter, npc_response, rewrite_response))
                if rewrite_response.get("narration") or rewrite_response.get("text") or npc_response.get("narration") or npc_response.get("text"):
                    narration_parts.append(
                        str(
                            rewrite_response.get("narration")
                            or rewrite_response.get("text")
                            or npc_response.get("narration")
                            or npc_response.get("text")
                            or ""
                        )
                    )
                manager_records.extend(
                    [
                        {"manager": "referee_npc", "opponent": opponent.name, "response": _strip_response_metadata(npc_response)},
                        {
                            "manager": "referee_npc_rewrite",
                            "opponent": opponent.name,
                            "response": _strip_response_metadata(rewrite_response),
                        },
                    ]
                )
                for manager_name, response in (
                    ("referee_npc", npc_response),
                    ("referee_npc_rewrite", rewrite_response),
                ):
                    self._apply_response_rewards(response, manager_name)
                    self._maybe_finish_active_quest_from_response(response, manager_name, action)
                terminal_outcome = self._apply_encounter_outcome(encounter)
                status_lines.extend(self._apply_quest_encounter_outcome(encounter, terminal_outcome))
                if terminal_outcome.get("narration"):
                    narration_parts.append(str(terminal_outcome.get("narration") or ""))
                if self._is_game_over() or _as_bool(terminal_outcome.get("game_over")):
                    finished = True
                    break
                if (
                    npc_tool_kind != "surrender"
                    and (
                        _as_bool(npc_response.get("finished"))
                        or _as_bool(npc_response.get("should_end_encounter"))
                        or _as_bool(rewrite_response.get("finished"))
                    )
                    or _as_bool(terminal_outcome.get("ended"))
                ):
                    finished = True
                    break

        if not self._is_game_over() and not _as_bool(terminal_outcome.get("ended")):
            status_lines.extend(self._tick_encounter_status_effects(encounter))
            terminal_outcome = self._apply_encounter_outcome(encounter)
            status_lines.extend(self._apply_quest_encounter_outcome(encounter, terminal_outcome))
            if terminal_outcome.get("narration"):
                narration_parts.append(str(terminal_outcome.get("narration") or ""))

        game_over = self._is_game_over() or _as_bool(terminal_outcome.get("game_over"))
        living = self._living_encounter_opponents(encounter)
        if game_over:
            self.state.flags["screen_mode"] = "game_over"
            self.state.flags.pop("active_encounter", None)
            self.state.flags.pop("active_conversation", None)
        elif finished or _as_bool(terminal_outcome.get("ended")) or not living:
            encounter["status"] = "ended"
            self.state.flags.pop("active_encounter", None)
            self.state.flags["screen_mode"] = "exploration"
        else:
            encounter["status"] = "active"
            acting = self._acting_encounter_opponents(encounter)
            self._set_encounter_active_opponent(encounter, (acting or living)[0])
            for opponent in living:
                self._set_character_presence(opponent, location, "present")
                self._sync_encounter_opponent_entry(encounter, opponent)
            self.state.flags["active_encounter"] = encounter
            self.state.flags["screen_mode"] = "battle"

        narration = "\n".join(part for part in [*narration_parts, "\n".join(status_lines)] if part).strip()
        if not narration:
            narration = "The battle situation changed."
        if game_over:
            choices = _game_over_choices()
        else:
            choices = _dedupe_strs(_as_str_list(player_response.get("choices")) + ([] if not finished else _quest_start_choices(self.state.world_data.quests)))
            if self._encounter_has_surrendered_opponents(encounter):
                choices = _dedupe_strs(choices + ["降伏を受け入れる"])
            if not choices:
                choices = self._encounter_choices(encounter)
        self._record_encounter_turn(action, input_type, encounter, manager_records)
        for record in manager_records:
            self.state.world_data.history.append(
                {
                    "manager": record["manager"],
                    "action": action,
                    "input_type": input_type,
                    "opponent": record.get("opponent"),
                    "encounter": _strip_encounter_log(encounter),
                    "response": record["response"],
                }
            )
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._apply_visual_intent(player_response, player_manager, location, previous_location)
        self._apply_response_rewards(player_response, player_manager)
        self._maybe_finish_active_quest_from_response(player_response, player_manager, action)
        self.save_game()
        return self.state.log_text(16)

    def _resolve_npc_turn(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        player_response: dict[str, Any],
        player_manager: str,
    ) -> str:
        status_lines = list(encounter.pop("pending_resource_lines", []))
        status_lines.extend(self._apply_response_hp_effects(player_response, player_manager, encounter=encounter))
        status_lines.extend(self._apply_response_sp_effects(player_response, player_manager, encounter=encounter))
        status_lines.extend(self._apply_response_progress_effects(player_response, player_manager, encounter=encounter))
        opponent = self._encounter_opponent(encounter)
        status_lines.extend(
            self._apply_response_world_state_effects(
                player_response,
                player_manager,
                default_character=opponent if isinstance(opponent, CharacterData) else None,
                default_location=str(encounter.get("location") or self.state.current_location),
            )
        )
        if len(self._encounter_opponents(encounter)) > 1:
            return self._resolve_group_npc_turn(action, input_type, encounter, player_response, player_manager, status_lines)
        opponent_surrendered = isinstance(opponent, CharacterData) and self._character_has_surrendered(opponent, encounter)
        if int(encounter.get("opponent_hp") or 0) <= 0:
            npc_response = {"finished": True, "narration": ""}
        elif opponent_surrendered:
            npc_response = {"finished": False, "narration": ""}
        else:
            npc_response = self._referee_npc(action, input_type, encounter, player_response)
        self._strip_game_controlled_hp_updates(npc_response, target="player")
        self._apply_encounter_update(encounter, npc_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, npc_response, "player")
        status_lines.extend(self._apply_response_hp_effects(npc_response, "referee_npc", encounter=encounter))
        status_lines.extend(self._apply_response_sp_effects(npc_response, "referee_npc", encounter=encounter))
        status_lines.extend(self._apply_response_progress_effects(npc_response, "referee_npc", encounter=encounter))
        status_lines.extend(
            self._apply_response_world_state_effects(
                npc_response,
                "referee_npc",
                default_character=opponent if isinstance(opponent, CharacterData) else None,
                default_location=str(encounter.get("location") or self.state.current_location),
            )
        )
        opponent_surrendered = isinstance(opponent, CharacterData) and self._character_has_surrendered(opponent, encounter)
        if int(encounter.get("opponent_hp") or 0) <= 0 or opponent_surrendered:
            rewrite_response = {}
        else:
            rewrite_response = self._referee_npc_rewrite(action, input_type, encounter, player_response, npc_response)
        self._strip_game_controlled_hp_updates(rewrite_response, target="player")
        self._apply_encounter_update(encounter, rewrite_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, rewrite_response, "player")
        status_lines.extend(self._apply_response_hp_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
        status_lines.extend(self._apply_response_sp_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
        status_lines.extend(self._apply_response_progress_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
        status_lines.extend(
            self._apply_response_world_state_effects(
                rewrite_response,
                "referee_npc_rewrite",
                default_character=opponent if isinstance(opponent, CharacterData) else None,
                default_location=str(encounter.get("location") or self.state.current_location),
            )
        )
        npc_tool_result = self._apply_npc_action_tool(encounter, npc_response, rewrite_response)
        npc_tool_kind = str(npc_tool_result.get("kind") or "")
        status_lines.extend(str(line) for line in npc_tool_result.get("lines", []) if line)
        if not _as_bool(npc_tool_result.get("acted")):
            status_lines.extend(self._apply_npc_combat_damage(encounter, npc_response, rewrite_response))
        status_lines.extend(self._tick_encounter_status_effects(encounter))
        outcome = self._apply_encounter_outcome(encounter)
        status_lines.extend(self._apply_quest_encounter_outcome(encounter, outcome))
        if (
            _as_bool(outcome.get("ended"))
            and str(outcome.get("opponent_state") or "") == "dead"
            and str(encounter.get("opponent_type") or "") == "character"
        ):
            status_lines.extend(
                self._apply_crime_risk(
                    action,
                    {"crime_delta": 100, "reason": "killed_character_in_town"},
                    "encounter_outcome",
                    location=str(encounter.get("location") or self.state.current_location),
                )
            )

        finished = (
            _as_bool(player_response.get("finished"))
            or (
                npc_tool_kind != "surrender"
                and (
                    _as_bool(npc_response.get("finished"))
                    or _as_bool(npc_response.get("should_end_encounter"))
                    or _as_bool(rewrite_response.get("finished"))
                )
            )
            or _as_bool(outcome.get("ended"))
        )
        game_over = self._is_game_over() or _as_bool(outcome.get("game_over"))
        if game_over:
            self.state.flags["screen_mode"] = "game_over"
            self.state.flags.pop("active_encounter", None)
            self.state.flags.pop("active_conversation", None)
        elif finished:
            encounter["status"] = "ended"
            self._update_encounter_presence(encounter, str(outcome.get("opponent_state") or "gone"))
            self.state.flags.pop("active_encounter", None)
            self.state.flags["screen_mode"] = "exploration"
        else:
            encounter["status"] = "active"
            self._update_encounter_presence(encounter, "present")
            self.state.flags["active_encounter"] = encounter
            self.state.flags["screen_mode"] = "battle"

        narration = "\n".join(
            part
            for part in [
                str(player_response.get("narration") or player_response.get("text") or ""),
                str(rewrite_response.get("narration") or rewrite_response.get("text") or npc_response.get("narration") or npc_response.get("text") or ""),
                "\n".join(status_lines),
                str(outcome.get("narration") or ""),
            ]
            if part
        ).strip() or "戦闘の状況が変化した。"
        if game_over:
            choices = _game_over_choices()
        else:
            choices = _dedupe_strs(
                _as_str_list(rewrite_response.get("choices") or npc_response.get("choices") or player_response.get("choices"))
                + ([] if not finished else _quest_start_choices(self.state.world_data.quests))
            )
            if self._encounter_has_surrendered_opponents(encounter):
                choices = _dedupe_strs(choices + ["降伏を受け入れる"])
        if not choices:
            choices = self._encounter_choices(encounter)

        manager_records = [
            {"manager": player_manager, "response": _strip_response_metadata(player_response)},
            {"manager": "referee_npc", "response": _strip_response_metadata(npc_response)},
            {"manager": "referee_npc_rewrite", "response": _strip_response_metadata(rewrite_response)},
        ]
        self._record_encounter_turn(action, input_type, encounter, manager_records)
        for record in manager_records:
            self.state.world_data.history.append(
                {
                    "manager": record["manager"],
                    "action": action,
                    "input_type": input_type,
                    "encounter": _strip_encounter_log(encounter),
                    "response": record["response"],
                }
            )

        previous_location = self.state.current_location
        location = str(encounter.get("location") or self.state.current_location)
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        visual_response = rewrite_response or npc_response or player_response
        self._apply_visual_intent(visual_response, "referee_npc_rewrite", location, previous_location)
        for manager_name, response in (
            (player_manager, player_response),
            ("referee_npc", npc_response),
            ("referee_npc_rewrite", rewrite_response),
        ):
            self._apply_response_rewards(response, manager_name)
            self._maybe_finish_active_quest_from_response(response, manager_name, action)
        self.save_game()
        return self.state.log_text(16)

    def _referee_player_attack_new_new(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        encounter_payload = json.dumps(_strip_encounter_log(encounter), ensure_ascii=False)
        opponent_payload = json.dumps(self._encounter_opponent_payload(encounter), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのプレイヤー攻撃判定担当です。"
                    "Fantasiaのreferee_player_attack_new_new相当として、"
                    "プレイヤーの攻撃が当たるか、効果、戦闘状態更新、次の選択肢を判定してください。"
                    "必ず narration, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"対象: {encounter.get('opponent_name')}\n"
                    f"対象データ: {opponent_payload}\n"
                    f"戦闘状態: {encounter_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    "この攻撃の結果を判定してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "Combat HP is controlled by the game. Do not directly decide opponent_hp or opponent_hp_delta. "
                    "For this attack, return combat_judgement with weakness_multiplier from 0.0 to 3.0 and a short reason. "
                    "0 means no effect, 1 means normal, values above 1 mean weakness or excellent matchup."
                ),
            }
        )
        return self._chat_json(
            "referee_player_attack_new_new",
            messages,
            max_tokens=700,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _referee_player_any_input_new_new(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        encounter_payload = json.dumps(_strip_encounter_log(encounter), ensure_ascii=False)
        opponent_payload = json.dumps(self._encounter_opponent_payload(encounter), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの戦闘中自由入力判定担当です。"
                    "Fantasiaのreferee_player_any_input_new_new相当として、"
                    "降伏、交渉、防御、逃走など攻撃以外の入力意図と戦闘状態更新を判定してください。"
                    "content_violation はゲーム側では判定しないため、必要な場合だけLLMとして判断してください。"
                    "必ず narration, intent, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"現在地: {self.state.current_location}\n"
                    f"対象: {encounter.get('opponent_name')}\n"
                    f"対象データ: {opponent_payload}\n"
                    f"戦闘状態: {encounter_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    "この戦闘中の自由入力を判定してください。"
                ),
            },
        ]
        if _is_skill_action(action):
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Skill HP is controlled by the game. Do not directly decide player_hp, player_hp_delta, "
                        "opponent_hp, or opponent_hp_delta. For this skill, return combat_judgement with: "
                        "effect_type damage or heal, ability one of str/dex/con/int/wis/cha/magic/will, "
                        "apply_defense true or false, weakness_multiplier from 0.0 to 3.0, and a short reason."
                    ),
                }
            )
        return self._chat_json(
            "referee_player_any_input_new_new",
            messages,
            max_tokens=700,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _referee_npc(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        player_response: dict[str, Any],
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        encounter_payload = json.dumps(_strip_encounter_log(encounter), ensure_ascii=False)
        player_payload = json.dumps(_strip_response_metadata(player_response), ensure_ascii=False)
        opponent_payload = json.dumps(self._encounter_opponent_payload(encounter), ensure_ascii=False)
        player_battle_payload = json.dumps(self._encounter_player_payload(encounter), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC/敵行動判定担当です。"
                    "Fantasiaのreferee_npc相当として、プレイヤー行動後のNPC/敵の行動を判定してください。"
                    "NPCの性格、役割、世界観、敵対理由、直前のプレイヤー行動を必ず考慮してください。"
                    "降伏、交渉、恐怖、慈悲、職業倫理などにより、攻撃以外の行動も自然に選んでください。"
                    "必ず narration, npc_action, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"敵対者: {encounter.get('opponent_name')}\n"
                    f"敵対者データ: {opponent_payload}\n"
                    f"プレイヤー戦闘データ: {player_battle_payload}\n"
                    f"戦闘状態: {encounter_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"プレイヤー側判定: {player_payload}\n"
                    "このNPC/敵が次に取る行動を判定してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "Player HP damage is controlled by the game. Do not directly decide player_hp or player_hp_delta. "
                    "If the NPC or enemy attacks this turn, return combat_judgement with offensive true and "
                    "weakness_multiplier from 0.0 to 3.0. If it does not attack, set offensive false. "
                    "Capture, restraint, disarming, watching, accepting surrender, or non-damaging entanglement after "
                    "surrender are not HP-damage attacks; use status effects and combat_judgement.offensive=false for them. "
                    "Choose the NPC action from its personality, traits, role, world context, the player's current HP ratio, "
                    "player_status, and player_status_effects. If this NPC would capture weak prey, intimidate, restrain, "
                    "feed, bargain, flee, or watch instead of simply damaging, describe that action and set offensive=false "
                    "unless it is a real HP-damaging attack. Treat world data, world overview, theme, laws, and setting notes "
                    "as shared NPC behavior rules. If the world says NPCs avoid killing, capture weakened enemies, honor surrender, "
                    "or prefer survival, reflect that in this NPC's action. Available explicit NPC action tools: "
                    "set npc_action='flee' when the NPC escapes to an adjacent node/location, or npc_action='surrender' when the NPC yields and stops acting. "
                    "Surrender does not end the encounter by itself; the player may accept the surrender or keep fighting. "
                    "For flee or surrender, set combat_judgement.offensive=false and do not describe HP damage."
                ),
            }
        )
        return self._chat_json(
            "referee_npc",
            messages,
            max_tokens=800,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _referee_npc_rewrite(
        self,
        action: str,
        input_type: str,
        encounter: dict[str, Any],
        player_response: dict[str, Any],
        npc_response: dict[str, Any],
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        encounter_payload = json.dumps(_strip_encounter_log(encounter), ensure_ascii=False)
        player_payload = json.dumps(_strip_response_metadata(player_response), ensure_ascii=False)
        npc_payload = json.dumps(_strip_response_metadata(npc_response), ensure_ascii=False)
        opponent_payload = json.dumps(self._encounter_opponent_payload(encounter), ensure_ascii=False)
        player_battle_payload = json.dumps(self._encounter_player_payload(encounter), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC行動リライト担当です。"
                    "Fantasiaのreferee_npc_rewrite相当として、referee_npcの判定を"
                    "世界観、NPCの性格、プレイヤーの降伏/交渉などの文脈に合う自然な描写へ整えてください。"
                    "判定が文脈に反して単調な攻撃になっている場合は、理由を保ったまま妥当な行動に補正してください。"
                    "降伏後の拘束、捕獲、武装解除、監視、非致傷の絡め取りはHPダメージ攻撃ではないため、"
                    "必要なら combat_judgement.offensive=false に補正してください。"
                    "必ず narration, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"敵対者: {encounter.get('opponent_name')}\n"
                    f"敵対者データ: {opponent_payload}\n"
                    f"プレイヤー戦闘データ: {player_battle_payload}\n"
                    f"戦闘状態: {encounter_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"プレイヤー側判定: {player_payload}\n"
                    f"NPC側判定: {npc_payload}\n"
                    "このNPC/敵の行動を自然文として整え、必要なら文脈に合うように補正してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "Rewrite the NPC action while preserving the game judgement. Consider player_hp/player_max_hp, "
                    "player_status, player_status_effects, the world setting/worldview, and the NPC's personality/traits. "
                    "If the world setting says NPCs avoid killing, capture weakened enemies, honor surrender, flee from danger, "
                    "or act by a shared code, preserve that behavior. Do not turn capture, "
                    "restraint, surrender acceptance, stalking, intimidation, or feeding preparation into a generic damage attack "
                    "unless combat_judgement.offensive is truly appropriate. Preserve npc_action='flee' or npc_action='surrender' "
                    "when that is the chosen tool, keep combat_judgement.offensive=false for those tools, and do not mark surrender as encounter finished unless the player accepted it."
                ),
            }
        )
        return self._chat_json(
            "referee_npc_rewrite",
            messages,
            max_tokens=700,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _combat_damage_narration(
        self,
        *,
        actor_name: str,
        target_name: str,
        action_name: str,
        source_response: dict[str, Any],
        combat_result: dict[str, Any],
    ) -> str:
        payload = {
            "actor": actor_name,
            "target": target_name,
            "action": action_name,
            "source_narration": str(source_response.get("narration") or source_response.get("text") or ""),
            "npc_action": source_response.get("npc_action"),
            "intent": source_response.get("intent"),
            "combat_judgement": source_response.get("combat_judgement"),
            "result": _combat_narration_payload(combat_result),
        }
        fallback = _combat_damage_message(
            _safe_int(payload["result"].get("damage"), 0),
            max(1, _safe_int(payload["result"].get("max_hp"), 1)),
            action_name=action_name,
        )
        try:
            response = self._chat_json(
                "combat_damage_narrator",
                [
                    {
                        "role": "system",
                        "content": (
                            "あなたはAI駆動RPGの戦闘結果描写担当です。"
                            "ゲーム側で確定したダメージ、倍率、HP変化に合わせて、"
                            "攻撃手段と結果が矛盾しない戦闘ログ用の短い自然文を作ってください。"
                            "HPやダメージ量を変更してはいけません。"
                            "damage が小さい場合は浅い傷やかすめた描写にし、"
                            "lethal=true または new_hp=0 の場合はその攻撃で対象が力尽きたことを含めてください。"
                            "必ず narration だけを持つJSONを返してください。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "次の計算済み戦闘結果を、ログに表示する1〜2文へ整えてください。\n"
                            f"{json.dumps(payload, ensure_ascii=False)}"
                        ),
                    },
                ],
                max_tokens=220,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
            narration = str(response.get("narration") or response.get("message") or "").strip()
            return narration or fallback
        except Exception as exc:
            self.state.world_data.extra.setdefault("combat_narration_errors", []).append(
                {"manager": "combat_damage_narrator", "error": str(exc), "payload": payload}
            )
            return fallback

    def _combat_heal_narration(
        self,
        *,
        actor_name: str,
        target_name: str,
        action_name: str,
        skill_name: str,
        source_response: dict[str, Any],
        combat_result: dict[str, Any],
    ) -> str:
        payload = {
            "actor": actor_name,
            "target": target_name,
            "action": action_name,
            "skill": skill_name,
            "source_narration": str(source_response.get("narration") or source_response.get("text") or ""),
            "combat_judgement": source_response.get("combat_judgement"),
            "result": _combat_narration_payload(combat_result),
        }
        fallback = _combat_heal_message(_safe_int(payload["result"].get("healing"), 0), skill_name)
        if fallback.startswith("> [戦闘] "):
            fallback = fallback[len("> [戦闘] ") :]
        try:
            response = self._chat_json(
                "combat_heal_narrator",
                [
                    {
                        "role": "system",
                        "content": (
                            "あなたはAI駆動RPGの回復結果描写担当です。"
                            "ゲーム側で確定した回復量とHP変化に合わせて、"
                            "回復手段と効果が矛盾しない戦闘ログ用の短い自然文を作ってください。"
                            "HPや回復量を変更してはいけません。"
                            "回復量が小さい場合は少し楽になった程度にし、回復量が0なら効果が薄い描写にしてください。"
                            "必ず narration だけを持つJSONを返してください。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "次の計算済み回復結果を、ログに表示する1〜2文へ整えてください。\n"
                            f"{json.dumps(payload, ensure_ascii=False)}"
                        ),
                    },
                ],
                max_tokens=220,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
            narration = str(response.get("narration") or response.get("message") or "").strip()
            return narration or fallback
        except Exception as exc:
            self.state.world_data.extra.setdefault("combat_narration_errors", []).append(
                {"manager": "combat_heal_narrator", "error": str(exc), "payload": payload}
            )
            return fallback

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

    def _hostile_characters_at(self, location: str, *, limit: int = 4) -> list[CharacterData]:
        location_name = str(location or self.state.current_location or self.state.world_data.starting_location or "").strip()
        if not location_name:
            return []
        result: list[CharacterData] = []
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

    def _select_hostile_opponent(self, requested_name: str, candidates: list[CharacterData]) -> CharacterData | None:
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

    def _start_encounter_with_character(self, character: CharacterData, *, source: str, action: str, location: str) -> dict[str, Any]:
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

    def _hostile_encounter_context(self, location: str, candidates: list[CharacterData], narration: str = "") -> dict[str, Any]:
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
        response_choices = _as_str_list(response.get("choices"))
        if response_choices:
            choices = _exploration_choices(response_choices + choices)
        if _as_bool(response.get("combat_started") or response.get("start_combat") or response.get("battle_started")):
            opponent = self._select_hostile_opponent(str(response.get("opponent_name") or response.get("target_name") or ""), candidates)
            if opponent:
                encounter = self._start_encounter_with_character(opponent, source=source, action=action, location=location)
                choices = self._encounter_choices(encounter)
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
        if self._active_encounter():
            return narration, choices, {}
        explicit = _as_bool(response.get("combat_started") or response.get("start_combat") or response.get("battle_started"))
        trigger_text = _combat_trigger_text(action, response, narration, choices)
        candidates = self._hostile_characters_at(location)
        if not explicit and not _text_implies_combat_started(trigger_text):
            return narration, choices, {}
        context = self._hostile_encounter_context(location, candidates, narration)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはFantasiaの戦闘突入検出担当です。"
                    "通常進行のLLM応答を読み、敵や魔物が実際に襲い掛かった、攻撃を開始した、戦闘に突入した場合だけ combat_started=true にしてください。"
                    "単に敵を見つけた、睨んでいる、選択肢として攻撃できる、警戒しているだけなら false です。"
                    "true の場合は opponent_name に戦闘相手の名前または種族名だけを書いてください。"
                ),
            },
            {
                "role": "user",
                "content": _ai_json(
                    {
                        "source": source,
                        "input_type": input_type,
                        "player_action": action,
                        "response": _strip_response_metadata(response),
                        "narration": narration,
                        "choices": choices,
                        "context": context,
                    }
                ),
            },
        ]
        try:
            detector = self._chat_json(
                "combat_transition_detector",
                messages,
                max_tokens=350,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
                retries=1,
            )
        except Exception as exc:
            self.state.world_data.extra.setdefault("combat_transition_errors", []).append(
                {"source": source, "location": location, "error": str(exc)}
            )
            return narration, choices, {}
        detector_started = _as_bool(detector.get("combat_started") or detector.get("start_combat") or detector.get("battle_started"))
        if explicit and not detector_started:
            detector["combat_started"] = True
            detector.setdefault("reason", "Upstream response explicitly requested combat start.")
            detector_started = True
        if not detector_started:
            return narration, choices, detector
        opponent = self._select_hostile_opponent(str(detector.get("opponent_name") or response.get("opponent_name") or ""), candidates)
        if opponent is None:
            opponent_type, opponent_name = self._find_or_create_encounter_opponent(
                "\n".join(part for part in (action, narration, str(detector.get("opponent_name") or "")) if str(part).strip())
            )
            opponent = self.state.world_data.characters.get(opponent_name)
        if opponent is None:
            return narration, choices, detector
        line = str(detector.get("narration") or "").strip()
        if line and line not in narration:
            narration = "\n".join(part for part in (narration, line) if str(part).strip())
        encounter = self._start_encounter_with_character(opponent, source=source, action=action, location=location)
        return narration, self._encounter_choices(encounter), detector

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
        if target_name not in self.state.world_data.characters:
            profile = self._encounter_monster_profile(target_name, current_location, resolved_target)
            character = CharacterData(
                name=_unique_character_name(self.state.world_data, target_name),
                role=profile["category"] or "敵対者",
                category="enemy_npc",
                backstory=profile["description"],
                look=profile["description"],
                traits=profile["traits"],
                image_generation_prompt=profile["image_generation_prompt"],
                flags={
                    "source": "encounter_target_resolver",
                    "resolved_from_action": text,
                    "resolver": _strip_response_metadata(resolved_target),
                    "hostile": True,
                    "enemy_npc": True,
                },
                extra={
                    "aliases": _dedupe_strs([target_name, profile["category"], "敵", "魔物"]),
                    "description": profile["description"],
                    "appearance_prompt": ", ".join(profile["image_generation_prompt"]),
                },
            )
            self._set_character_presence(character, current_location, "present")
            self._ensure_character_runtime_data(character)
            self.state.world_data.characters[character.name] = character
            target_name = character.name
        else:
            self._set_character_presence(self.state.world_data.characters[target_name], current_location, "present")
            self._ensure_character_runtime_data(self.state.world_data.characters[target_name])
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
        if not category:
            category = "wild_encounter"
        if not description:
            description = f"{location}でプレイヤーの行動に反応して姿を現した魔物。"
        traits = resolved.get("traits")
        normalised_traits = [
            trait for trait in (_normalise_trait(item) for item in _as_list(traits)) if trait.get("name")
        ]
        if not normalised_traits:
            normalised_traits = [
                {"name": "慎重", "effect": "相手が降伏した場合は即座に殺さず、武装解除を優先する。"},
                {"name": "縄張り意識", "effect": "侵入者を殺すより追い払うことを優先する。"},
            ]
        prompt_parts = _as_str_list(resolved.get("image_generation_prompt") or resolved.get("visual_prompt"))
        if not prompt_parts:
            prompt_parts = ["fantasy RPG monster", name, category]
        return {
            "category": category,
            "description": description,
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
        if name in self.state.world_data.characters:
            return self.state.world_data.characters[name].to_dict()
        return {"name": name, "type": "character"}

    def _encounter_player_payload(self, encounter: dict[str, Any]) -> dict[str, Any]:
        max_hp = max(1, _safe_int(encounter.get("player_max_hp"), self._player_max_hp()))
        current_hp = max(0, min(max_hp, _safe_int(encounter.get("player_hp"), self._player_current_hp(max_hp))))
        max_sp = max(1, _safe_int(encounter.get("player_max_sp"), self._player_max_sp()))
        current_sp = max(0, min(max_sp, _safe_int(encounter.get("player_sp"), self._player_current_sp(max_sp))))
        player = self.state.world_data.characters.get(self.state.player_name)
        return _drop_empty(
            {
                "name": self.state.player_name,
                "current_hp": current_hp,
                "max_hp": max_hp,
                "hp_ratio": round(current_hp / max_hp, 3),
                "current_sp": current_sp,
                "max_sp": max_sp,
                "sp_ratio": round(current_sp / max_sp, 3),
                "player_status": encounter.get("player_status"),
                "player_status_effects": self._actor_status_effects("player", encounter),
                "player_character": _character_ai_context(player, details=True) if player else {},
            }
        )

    def _apply_encounter_update(self, encounter: dict[str, Any], update: Any) -> None:
        if isinstance(update, list):
            for item in update:
                self._apply_encounter_update(encounter, item)
            return
        if not isinstance(update, dict):
            return
        for key, value in update.items():
            text_key = str(key)
            if text_key in {"player_status_effect", "player_status_effects", "add_player_status_effect", "add_player_status_effects"}:
                self._add_actor_status_effects("player", value, source="encounter_update")
                continue
            if text_key in {"opponent_status_effect", "opponent_status_effects", "add_opponent_status_effect", "add_opponent_status_effects"}:
                self._add_actor_status_effects("opponent", value, encounter=encounter, source="encounter_update")
                continue
            if text_key in {"remove_player_status_effect", "remove_player_status_effects"}:
                self._remove_actor_status_effects("player", value)
                continue
            if text_key in {"remove_opponent_status_effect", "remove_opponent_status_effects"}:
                self._remove_actor_status_effects("opponent", value, encounter=encounter)
                continue
            if text_key == "status_effects":
                self._add_targeted_status_effects(encounter, value, source="encounter_update")
                continue
            if text_key in {"player_sp_delta", "sp_delta"}:
                self._apply_player_sp_delta(value, source="encounter_update", encounter=encounter)
                continue
            if text_key in {"player_sp", "current_sp"}:
                self._set_player_sp(value, max_sp=self._hp_number(encounter.get("player_max_sp"), self._player_max_sp()), encounter=encounter)
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
                    self._add_actor_status_effects("player", effect, source="player_status")
            elif text_key == "opponent_status":
                effect = _status_effect_from_status_text(str(value))
                if effect:
                    self._add_actor_status_effects("opponent", effect, encounter=encounter, source="opponent_status")
        self._sync_encounter_status_effects(encounter)
        if int(encounter.get("opponent_hp") or 0) > 0 and not self._is_game_over():
            self._update_encounter_presence(encounter, "present")

    def _add_actor_status_effects(
        self,
        target: str,
        value: Any,
        *,
        encounter: dict[str, Any] | None = None,
        source: str = "",
    ) -> list[dict[str, Any]]:
        effects = [_normalise_status_effect(item, source=source) for item in _status_effect_items(value)]
        effects = [effect for effect in effects if effect]
        if target == "player":
            effects = [effect for effect in effects if not self._player_is_immune_to_status(effect)]
        if not effects:
            return []
        status_list = self._actor_status_effects(target, encounter)
        for effect in effects:
            _merge_status_effect(status_list, effect)
        self._sync_actor_status_effects(target, status_list, encounter)
        return effects

    def _add_targeted_status_effects(self, encounter: dict[str, Any], value: Any, *, source: str = "") -> None:
        if isinstance(value, dict):
            self._add_actor_status_effects(
                "player",
                value.get("player") or value.get("players") or value.get("player_status_effects"),
                encounter=encounter,
                source=source,
            )
            self._add_actor_status_effects(
                "opponent",
                value.get("opponent") or value.get("enemy") or value.get("enemies") or value.get("opponent_status_effects"),
                encounter=encounter,
                source=source,
            )
            if any(key in value for key in ("name", "title", "label", "status", "condition", "effect", "description")):
                target = _status_effect_target(value)
                if target:
                    self._add_actor_status_effects(target, value, encounter=encounter, source=source)
            return
        for item in _status_effect_items(value):
            target = _status_effect_target(item)
            if target:
                self._add_actor_status_effects(target, item, encounter=encounter, source=source)

    def _remove_actor_status_effects(self, target: str, value: Any, *, encounter: dict[str, Any] | None = None) -> None:
        remove_ids = {_status_effect_id(item) for item in _status_effect_items(value)}
        remove_ids.discard("")
        if not remove_ids:
            return
        status_list = [
            effect
            for effect in self._actor_status_effects(target, encounter)
            if _status_effect_id(effect) not in remove_ids
        ]
        self._sync_actor_status_effects(target, status_list, encounter)

    def _actor_status_effects(self, target: str, encounter: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if target == "player":
            return self.state.status_effects
        opponent = self._encounter_opponent(encounter or {})
        if isinstance(opponent, CharacterData):
            return opponent.status_effects
        raw = (encounter or {}).get("opponent_status_effects")
        return raw if isinstance(raw, list) else []

    def _player_incapacitated_effects(self) -> list[dict[str, Any]]:
        effects: list[dict[str, Any]] = []
        for raw in self._actor_status_effects("player"):
            effect = _normalise_status_effect(raw)
            if not effect:
                continue
            if _status_effect_blocks_action(effect) or _status_effect_blocks_movement(effect):
                effects.append(effect)
        return effects

    def _player_incapacitated_action_block(
        self,
        action: str,
        *,
        encounter: dict[str, Any] | None = None,
        for_movement: bool = False,
    ) -> str:
        effects = self._player_incapacitated_effects()
        if not effects:
            return ""
        if for_movement:
            return "movement" if any(_status_effect_blocks_movement(effect) for effect in effects) else ""
        if _is_escape_action(action):
            return "escape" if any(_status_effect_blocks_escape(effect) for effect in effects) else ""
        if _is_attack_action(action) or _is_aggressive_player_action(action):
            return "attack" if any(_status_effect_blocks_attack(effect) for effect in effects) else ""
        if encounter and _is_movement_intent(action):
            return "movement" if any(_status_effect_blocks_movement(effect) for effect in effects) else ""
        return ""

    def _player_incapacitated_message(self, reason: str = "") -> str:
        names = _dedupe_strs(
            str(effect.get("name") or INCAPACITATED_STATUS_NAME)
            for effect in self._player_incapacitated_effects()
            if isinstance(effect, dict)
        )
        label = " / ".join(names) if names else INCAPACITATED_STATUS_NAME
        if reason == "movement":
            return f"{label}のため、今は移動できない。まず拘束や行動不能の原因を解く必要がある。"
        if reason == "escape":
            return f"{label}のため、今は逃走できない。"
        if reason == "attack":
            return f"{label}のため、今は攻撃的な行動を取れない。"
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
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
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
            player = self.state.world_data.characters.get(self.state.player_name)
            if player:
                player.status_effects = list(status_list)
            if self.state.party and isinstance(self.state.party[0], dict):
                self.state.party[0]["status_effects"] = list(status_list)
            if encounter is not None:
                encounter["player_status_effects"] = list(status_list)
            return

        opponent = self._encounter_opponent(encounter or {})
        if isinstance(opponent, CharacterData):
            opponent.status_effects = list(status_list)
        if encounter is not None:
            encounter["opponent_status_effects"] = list(status_list)

    def _sync_encounter_status_effects(self, encounter: dict[str, Any]) -> None:
        self._sync_actor_status_effects("player", self._actor_status_effects("player", encounter), encounter)
        self._sync_actor_status_effects("opponent", self._actor_status_effects("opponent", encounter), encounter)

    def _apply_response_implied_statuses(self, encounter: dict[str, Any], response: dict[str, Any], target: str) -> None:
        effects = response.get("status_effects") or response.get("conditions")
        if effects:
            self._add_actor_status_effects(target, effects, encounter=encounter, source="response")
        player_effects = response.get("player_status_effects") or response.get("add_player_status_effects")
        if player_effects:
            self._add_actor_status_effects("player", player_effects, encounter=encounter, source="response")
        opponent_effects = response.get("opponent_status_effects") or response.get("add_opponent_status_effects")
        if opponent_effects:
            self._add_actor_status_effects("opponent", opponent_effects, encounter=encounter, source="response")
        text = json.dumps(_strip_response_metadata(response), ensure_ascii=False)
        effect = _status_effect_from_status_text(text)
        if effect:
            self._add_actor_status_effects(target, effect, encounter=encounter, source="response_text")

    def _apply_response_status_effects(
        self,
        response: dict[str, Any],
        source: str,
        *,
        default_target: str = "player",
        context_character: CharacterData | None = None,
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
        context_character: CharacterData | None,
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
        context_character: CharacterData | None,
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
        remove_ids = {_status_effect_id(item) for item in _status_effect_items(value)}
        remove_ids.discard("")
        if not remove_ids:
            return []
        removed = [effect for effect in status_list if _status_effect_id(effect) in remove_ids]
        if not removed:
            return []
        kept = [effect for effect in status_list if _status_effect_id(effect) not in remove_ids]
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
            player = self.state.world_data.characters.get(self.state.player_name)
            if player and player.status_effects and not self.state.status_effects:
                self.state.status_effects = list(player.status_effects)
            return ("player", self.state.player_name, self.state.status_effects, self.state.player_name or "Player")
        character = self.state.world_data.characters.get(text)
        if character:
            return ("character", character.name, character.status_effects, character.name)
        if lowered in {"monster", "enemy", "opponent"}:
            active = self._active_encounter()
            if active:
                opponent = self._encounter_opponent(active)
                if isinstance(opponent, CharacterData):
                    return ("character", opponent.name, opponent.status_effects, opponent.name)
        return None

    def _sync_status_target(self, kind: str, name: str, status_list: list[dict[str, Any]]) -> None:
        if kind == "player":
            self.state.status_effects = list(status_list)
            player = self.state.world_data.characters.get(self.state.player_name)
            if player:
                player.status_effects = list(status_list)
            if self.state.party and isinstance(self.state.party[0], dict):
                self.state.party[0]["status_effects"] = list(status_list)
            return
        if kind == "character" and name in self.state.world_data.characters:
            self.state.world_data.characters[name].status_effects = list(status_list)
            if name == self.state.player_name:
                self._sync_status_target("player", name, status_list)
            return

    def _enrich_persistent_status_effect(self, effect: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(effect)
        enriched.setdefault("started_day", self.state.day)
        enriched.setdefault("started_location", self.state.current_location)
        if enriched.get("long_term") or enriched.get("persistent") or enriched.get("permanent"):
            enriched.setdefault("scope", "character")
        return enriched

    def _tick_encounter_status_effects(self, encounter: dict[str, Any]) -> list[str]:
        lines: list[str] = []
        opponents = self._encounter_opponents(encounter)
        if opponents:
            player_status_list = self._actor_status_effects("player", encounter)
            if player_status_list:
                hp = max(0, int(encounter.get("player_hp") or 0))
                updated, hp_delta, tick_lines = _tick_status_effects(player_status_list, self.state.player_name or "Player")
                if hp_delta:
                    max_hp = _safe_int(encounter.get("player_max_hp"), hp)
                    hp = max(0, min(max_hp if max_hp > 0 else hp + hp_delta, hp + hp_delta))
                    encounter["player_hp"] = hp
                lines.extend(tick_lines)
                self._sync_actor_status_effects("player", updated, encounter)
            active_uuid = str(encounter.get("active_opponent_uuid") or encounter.get("opponent_uuid") or "")
            active_name = str(encounter.get("active_opponent_name") or encounter.get("opponent_name") or "")
            for opponent in opponents:
                self._set_encounter_active_opponent(encounter, opponent)
                opponent_status_list = self._actor_status_effects("opponent", encounter)
                if not opponent_status_list:
                    continue
                updated, hp_delta, tick_lines = _tick_status_effects(opponent_status_list, opponent.name)
                if hp_delta:
                    self._apply_opponent_hp_delta(encounter, hp_delta, source="status_tick", reason="status")
                lines.extend(tick_lines)
                self._sync_actor_status_effects("opponent", updated, encounter)
            restore = self._character_from_reference(active_name, active_uuid)
            if restore:
                self._set_encounter_active_opponent(encounter, restore)
            self._sync_player_battle_state(encounter)
            return lines
        for target, hp_key, label in (
            ("player", "player_hp", "あなた"),
            ("opponent", "opponent_hp", str(encounter.get("opponent_name") or "相手")),
        ):
            status_list = self._actor_status_effects(target, encounter)
            if not status_list:
                continue
            hp = max(0, int(encounter.get(hp_key) or 0))
            updated, hp_delta, tick_lines = _tick_status_effects(status_list, label)
            if hp_delta:
                max_hp = _safe_int(encounter.get("player_max_hp" if target == "player" else "opponent_max_hp"), hp)
                hp = max(0, min(max_hp if max_hp > 0 else hp + hp_delta, hp + hp_delta))
                encounter[hp_key] = hp
            lines.extend(tick_lines)
            self._sync_actor_status_effects(target, updated, encounter)
        self._sync_player_battle_state(encounter)
        return lines

    def _apply_encounter_outcome(self, encounter: dict[str, Any]) -> dict[str, Any]:
        self._sync_player_battle_state(encounter)
        player_hp = int(encounter.get("player_hp") or 0)
        opponent_hp = int(encounter.get("opponent_hp") or 0)
        if player_hp > 0:
            opponent = self._encounter_opponent(encounter)
            if isinstance(opponent, CharacterData):
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
                defeated_name = str((opponent.name if isinstance(opponent, CharacterData) else "") or encounter.get("opponent_name") or "Opponent")
                defeated_uuid = str((opponent.uuid if isinstance(opponent, CharacterData) else "") or encounter.get("opponent_uuid") or "")
                encounter["opponent_status"] = "defeated"
                self._add_actor_status_effects(
                    "opponent",
                    {"name": "defeated", "id": "defeated", "duration": 0},
                    encounter=encounter,
                    source="defeated",
                )
                if isinstance(opponent, CharacterData):
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
            player = self.state.world_data.characters.get(self.state.player_name)
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
        player = self.state.world_data.characters.get(self.state.player_name)
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
        player = self.state.world_data.characters.get(self.state.player_name)
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
        player = self.state.world_data.characters.get(self.state.player_name)
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

    def _ensure_player_progress(self, character: CharacterData | None = None) -> None:
        level = self._player_level(character)
        exp = self._player_exp(character)
        self._set_player_progress(level, exp, character=character)

    def _player_level(self, character: CharacterData | None = None) -> int:
        player = character or self.state.world_data.characters.get(self.state.player_name)
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

    def _player_exp(self, character: CharacterData | None = None) -> int:
        player = character or self.state.world_data.characters.get(self.state.player_name)
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

    def _set_player_progress(self, level: int, exp: int, *, character: CharacterData | None = None) -> None:
        resolved_level = max(1, min(PLAYER_MAX_LEVEL, int(level or 1)))
        resolved_exp = max(0, int(exp or 0))
        if resolved_level >= PLAYER_MAX_LEVEL:
            resolved_exp = min(resolved_exp, self._exp_to_next(PLAYER_MAX_LEVEL))
        self.state.flags["player_level"] = resolved_level
        self.state.flags["player_exp"] = resolved_exp
        self.state.extra["level"] = resolved_level
        self.state.extra["exp"] = resolved_exp
        self.state.extra["next_exp"] = self._exp_to_next(resolved_level)
        player = character or self.state.world_data.characters.get(self.state.player_name)
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

    def _player_max_hp(self, character: CharacterData | None = None) -> int:
        equipment_bonus = 0 if character is not None else _safe_int(self.player_equipment_summary().get("max_hp"), 0)
        base = self._player_base_max_hp(character)
        return max(1, base + equipment_bonus)

    def _player_base_max_hp(self, character: CharacterData | None = None) -> int:
        player = character or self.state.world_data.characters.get(self.state.player_name)
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
        character: CharacterData | None = None,
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
        player = self.state.world_data.characters.get(self.state.player_name)
        if player:
            value = player.current_hp
            if value:
                return max(0, min(max_hp, _safe_int(value, max_hp)))
            value = player.extra.get("current_hp") if isinstance(player.extra, dict) else None
            if value is not None:
                return max(0, min(max_hp, _safe_int(value, max_hp)))
        return max_hp

    def _player_max_sp(self, character: CharacterData | None = None) -> int:
        equipment_bonus = 0 if character is not None else _safe_int(self.player_equipment_summary().get("max_sp"), 0)
        base = self._player_base_max_sp(character)
        return max(1, base + equipment_bonus)

    def _player_base_max_sp(self, character: CharacterData | None = None) -> int:
        player = character or self.state.world_data.characters.get(self.state.player_name)
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
        character: CharacterData | None = None,
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
        player = self.state.world_data.characters.get(self.state.player_name)
        if player:
            value = player.current_sp
            if value:
                return max(0, min(max_sp, _safe_int(value, max_sp)))
            value = player.extra.get("current_sp") if isinstance(player.extra, dict) else None
            if value is not None:
                return max(0, min(max_sp, _safe_int(value, max_sp)))
        return max_sp

    def _player_attributes(self, character: CharacterData | None = None) -> dict[str, int]:
        player = character or self.state.world_data.characters.get(self.state.player_name)
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
        if not _should_use_action_roll(action, input_type, purpose):
            return None
        return self._make_action_roll(action, purpose=purpose)

    def roll_craft_check(self, ingredients: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        base_target = _craft_roll_target(ingredients or [])
        target, home_level, home_reduction = self._home_craft_target(base_target)
        roll = self._make_action_roll(
            "craft",
            purpose="craft",
            forced_ability="dex",
            forced_target=target,
        )
        roll["base_target"] = base_target
        roll["home_furniture_level"] = home_level
        roll["home_target_reduction"] = home_reduction
        if home_level and home_reduction:
            roll["line"] = f"{roll['line']} / 家具Lv{home_level}補正: 目標値 {base_target}->{target}"
        return roll

    def _make_action_roll(
        self,
        action: str,
        *,
        purpose: str = "action",
        forced_ability: str = "",
        forced_target: int | None = None,
    ) -> dict[str, Any]:
        ability = forced_ability or _roll_ability_for_action(action, purpose)
        attrs = self._player_attributes()
        ability_score = _safe_int(attrs.get(ability), 10)
        bonus = ability_score // 3
        target = _normalise_roll_target(forced_target if forced_target is not None else _roll_target_for_action(action, purpose))
        die_1 = random.randint(1, 6)
        die_2 = random.randint(1, 6)
        natural = die_1 + die_2
        total = natural + bonus
        critical_failure = natural == 2
        critical_success = natural == 12
        success = critical_success or (not critical_failure and total >= target)
        ability_label = _roll_ability_label(ability)
        if critical_success:
            outcome = "強制成功"
        elif critical_failure:
            outcome = "強制失敗"
        else:
            outcome = "成功" if success else "失敗"
        line = f"> [判定] 目標値 {target} / 2d6 {die_1}+{die_2} + {ability_label}ボーナス{bonus} = {total} : {outcome}"
        return {
            "enabled": True,
            "rule": "2d6 + floor(relevant_ability / 3) vs target. Natural 2 is forced failure. Natural 12 is forced success.",
            "purpose": purpose,
            "action": action,
            "ability": ability,
            "ability_label": ability_label,
            "ability_score": ability_score,
            "bonus": bonus,
            "dice": [die_1, die_2],
            "roll": natural,
            "target": target,
            "total": total,
            "success": success,
            "failure": not success,
            "critical_success": critical_success,
            "critical_failure": critical_failure,
            "margin": total - target,
            "line": line,
        }

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
        player = self.state.world_data.characters.get(self.state.player_name)
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

    def _encounter_opponent(self, encounter: dict[str, Any]) -> CharacterData | None:
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
        player = self.state.world_data.characters.get(self.state.player_name)
        if player:
            player.flags["game_over"] = True
            player.extra["game_over_reason"] = reason
        line = f"> [GameOver] {reason}"
        event["line"] = line
        self.state.world_data.extra.setdefault("game_over_events", []).append(dict(event))
        return event

    def _update_encounter_presence(self, encounter: dict[str, Any], state: str) -> None:
        location = str(encounter.get("location") or self.state.current_location or "")
        opponent_name = str(encounter.get("opponent_name") or "")
        character = self.state.world_data.characters.get(opponent_name)
        if character:
            self._set_character_presence(character, location, state)

    def _apply_quest_encounter_outcome(self, encounter: dict[str, Any], outcome: dict[str, Any]) -> list[str]:
        if not self.state.active_quest or not (_as_bool(outcome.get("ended")) or _as_bool(outcome.get("opponent_defeated"))):
            return []
        quest = self._find_quest_by_name(self.state.active_quest)
        if not quest or quest.status != "active":
            return []
        opponent_uuid = str(outcome.get("defeated_opponent_uuid") or encounter.get("opponent_uuid") or "").strip()
        if not opponent_uuid:
            opponent_name = str(outcome.get("defeated_opponent_name") or encounter.get("opponent_name") or "")
            opponent = self.state.world_data.characters.get(opponent_name)
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
            return _quest_start_choices(self.state.world_data.quests) or ["周囲を見る"]
        choices = ["攻撃", "スキル", "行動", "逃走"]
        if self._player_incapacitated_effects():
            choices = [choice for choice in choices if choice not in {"攻撃", "逃走"}]
        if self._encounter_has_surrendered_opponents(encounter):
            choices.append("降伏を受け入れる")
        return choices
    def _start_conversation(self, action: str, input_type: str, character: CharacterData) -> str:
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
            self.state.append_turn(action, narration, location, choices, input_type=input_type)
            self.save_game()
            return self.state.log_text(16)

        self.state.flags["active_conversation"] = {
            "character": character.name,
            "location": str(response.get("location") or self.state.current_location),
            "topic": str(response.get("topic") or ""),
        }
        self.state.flags["screen_mode"] = "conversation"
        narration = str(response.get("narration") or response.get("text") or f"{character.name}との会話を始めた。")
        location = str(response.get("location") or self.state.current_location)
        self._set_character_presence(character, location)
        choices = _as_str_list(response.get("choices"))
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
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        status_lines = self._apply_response_status_effects(response, "conversation_starter", default_target=character.name, context_character=character)
        status_lines.extend(self._apply_response_hp_effects(response, "conversation_starter"))
        status_lines.extend(self._apply_response_sp_effects(response, "conversation_starter"))
        status_lines.extend(self._apply_response_progress_effects(response, "conversation_starter"))
        status_lines.extend(self._apply_response_world_state_effects(response, "conversation_starter", default_character=character, default_location=location))
        status_lines.extend(self._apply_crime_risk(action, response, "conversation_starter", location=location))
        if status_lines:
            self.state.display_log.extend(status_lines)
        self._apply_visual_intent(response, "conversation_starter", location, previous_location)
        self._apply_response_rewards(response, "conversation_starter")
        self.save_game()
        return self.state.log_text(16)

    def _conversation_starter(
        self,
        character: CharacterData,
        action: str,
        input_type: str,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False))
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
                    f"会話相手データ: {character_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    "このNPCとの会話を開始してください。"
                ),
            },
        ]
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
        character: CharacterData,
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
        location = str((resolver_response or {}).get("location") or response.get("location") or self.state.current_location)
        self._set_character_presence(character, location)
        choices = _as_str_list((resolver_response or {}).get("choices") or response.get("choices"))

        self._record_conversation(character, "conversation_facilitator", action, input_type, response)
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
        if resolver_response:
            self._record_conversation(character, "conversation_resolver", action, input_type, resolver_response)
            self._apply_conversation_resolution(character, resolver_response)
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

        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._append_action_roll_log(action_roll)
        visual_response = resolver_response or response
        status_lines = [] if content_violation else self._apply_response_status_effects(response, "conversation_facilitator", default_target=character.name, context_character=character)
        if not content_violation:
            status_lines.extend(self._apply_response_hp_effects(response, "conversation_facilitator"))
            status_lines.extend(self._apply_response_sp_effects(response, "conversation_facilitator"))
            status_lines.extend(self._apply_response_progress_effects(response, "conversation_facilitator"))
            status_lines.extend(self._apply_response_world_state_effects(response, "conversation_facilitator", default_character=character, default_location=location))
            status_lines.extend(self._apply_crime_risk(action, response, "conversation_facilitator", location=location))
        if resolver_response:
            status_lines.extend(self._apply_response_status_effects(resolver_response, "conversation_resolver", default_target=character.name, context_character=character))
            status_lines.extend(self._apply_response_hp_effects(resolver_response, "conversation_resolver"))
            status_lines.extend(self._apply_response_sp_effects(resolver_response, "conversation_resolver"))
            status_lines.extend(self._apply_response_progress_effects(resolver_response, "conversation_resolver"))
            status_lines.extend(self._apply_response_world_state_effects(resolver_response, "conversation_resolver", default_character=character, default_location=location))
            status_lines.extend(self._apply_crime_risk(action, resolver_response, "conversation_resolver", location=location))
        if status_lines:
            self.state.display_log.extend(status_lines)
        self._apply_visual_intent(visual_response, "conversation_resolver" if resolver_response else "conversation_facilitator", location, previous_location)
        if not content_violation:
            self._apply_response_rewards(response, "conversation_facilitator")
            if resolver_response:
                self._apply_response_rewards(resolver_response, "conversation_resolver")
        self.save_game()
        return self.state.log_text(16)

    def _conversation_facilitator(
        self,
        character: CharacterData,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
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
                    f"会話状態: {conversation_state}\n"
                    f"直近ログ:\n{recent_log}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"game_side_action_roll: {action_roll_payload}\n"
                    "この会話を続けてください。会話が終わる場合は finished を true にしてください。"
                ),
            },
        ]
        return self._chat_json(
            "conversation_facilitator",
            messages,
            max_tokens=800,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _conversation_resolver(
        self,
        character: CharacterData,
        action: str,
        facilitator_response: dict[str, Any],
    ) -> dict[str, Any]:
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
                    f"プレイヤー行動: {action}\n"
                    f"直前のconversation_facilitator応答: {facilitator_payload}\n"
                    f"会話ログ: {conversation_log}\n"
                    "この会話を解決し、保存すべき要約を返してください。"
                ),
            },
        ]
        return self._chat_json(
            "conversation_resolver",
            messages,
            max_tokens=650,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _apply_conversation_resolution(self, character: CharacterData, response: dict[str, Any]) -> None:
        summary = str(response.get("summary") or "")
        if summary:
            character.extra.setdefault("conversation_summaries", []).append(summary)
        if response.get("relationship_change"):
            character.extra.setdefault("relationship_changes", []).append(response.get("relationship_change"))
        for item in _as_list(response.get("memory_updates")):
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
        character: CharacterData,
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

    def _field_event_evaluator(
        self,
        action: str,
        input_type: str,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        recent_log = self.state.log_text(10)
        action_roll_payload = json.dumps(action_roll or {}, ensure_ascii=False)
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
    ) -> str:
        previous_location = self.state.current_location
        location = str(response.get("location") or self.state.current_location)
        narration = str(response.get("narration") or response.get("text") or "探索中に何かが起きた。")
        movement_result = self._normalize_world_response_location(action, input_type, response, location)
        location = str(movement_result.get("location") or location)
        movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
        if movement_narration:
            narration = "\n".join([narration, *movement_narration]).strip()
        discovered_location = self._apply_discovered_location(response, action=action)
        generated_quests = self._apply_field_event_quests(response, location)
        generated_actors = self._apply_field_event_actors(response, location)
        boss_event = self._ensure_generated_dungeon_boss(discovered_location, action, response)
        if boss_event:
            generated_actors.append(boss_event)
        choices = self._augment_location_choices(_as_str_list(response.get("choices")), location)

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
            "event": response.get("event"),
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
                "response": _strip_response_metadata(response),
            }
        )
        narration, choices, transition_response = self._maybe_start_combat_from_response(
            action,
            input_type,
            "field_event_evaluator",
            response,
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
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._set_player_presence(location)
        self._append_action_roll_log(action_roll)
        status_lines = self._apply_response_status_effects(response, "field_event_evaluator", default_target="player")
        status_lines.extend(str(line) for line in movement_result.get("status_lines", []) if str(line).strip())
        status_lines.extend(self._apply_response_hp_effects(response, "field_event_evaluator"))
        status_lines.extend(self._apply_response_sp_effects(response, "field_event_evaluator"))
        status_lines.extend(self._apply_response_progress_effects(response, "field_event_evaluator"))
        status_lines.extend(self._apply_response_world_state_effects(response, "field_event_evaluator", default_location=location))
        status_lines.extend(self._apply_crime_risk(action, response, "field_event_evaluator", location=location))
        if status_lines:
            self.state.display_log.extend(status_lines)
            event_record["status_effects_applied"] = status_lines
        self._apply_visual_intent(response, "field_event_evaluator", location, previous_location)
        reward_event = self._apply_response_rewards(response, "field_event_evaluator")
        if reward_event["items"] or reward_event["lost_items"] or reward_event["gold"]:
            event_record["rewards"] = reward_event
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
        if not boss_payload and not _generated_dungeon_boss_required(action, response, location):
            return None
        if self._generated_dungeon_has_boss(location.name):
            return None
        if not boss_payload:
            boss_payload = _fallback_generated_dungeon_boss_payload(location, action, response)
        character = _enemy_npc_from_raw(boss_payload, len(self.state.world_data.characters))
        character.name = _unique_character_name(self.state.world_data, character.name)
        character.role = str(character.role or "ダンジョンボス")
        character.category = "enemy_npc"
        character.flags["enemy_npc"] = True
        character.flags["hostile"] = _as_bool(character.flags.get("hostile") if "hostile" in character.flags else True)
        character.flags["generated_dungeon_boss"] = True
        character.extra["generated_dungeon_boss"] = True
        character.extra["boss_location"] = location.name
        danger = max(5, _safe_int(location.extra.get("danger_level", location.extra.get("danger")), 0))
        character.flags.setdefault("danger_level", danger)
        character.extra.setdefault("danger_level", danger)
        character.extra["spawn_subnode_id"] = target_subnode
        character.extra["origin_subnode_id"] = target_subnode
        character.extra["display_alias"] = str(character.extra.get("display_alias") or "ボス")
        character.extra["aliases"] = _dedupe_strs([character.name, "ボス", "守護者", *[str(value) for value in _as_list(character.extra.get("aliases"))]])
        character.level = max(_safe_int(character.level, 1), _generated_dungeon_boss_level(location))
        _scale_character_for_danger(character, danger, boss=True)
        self._ensure_character_runtime_data(character)
        self._set_character_presence(character, location.name, "present", subnode_id=target_subnode)
        self.state.world_data.characters[character.name] = character
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
        raw_characters = _as_list(response.get("npcs") or response.get("characters") or response.get("npc"))
        for item in raw_characters:
            character = _npc_from_raw(item, len(self.state.world_data.characters) + len(generated))
            if _world_has_dead_npc_identity(self.state.world_data, name=character.name, uuid=character.uuid):
                continue
            character.name = _unique_character_name(self.state.world_data, character.name)
            character.flags.setdefault("source", "field_event_evaluator")
            self._set_character_presence(character, location)
            self.state.world_data.characters[character.name] = character
            generated.append({"type": "character", "name": character.name})

        raw_opponents = _as_list(response.get("opponents") or response.get("enemies") or response.get("enemy_npcs") or response.get("enemy"))
        for item in raw_opponents:
            character = _enemy_npc_from_raw(item, len(self.state.world_data.characters) + len(generated))
            character.name = _unique_character_name(self.state.world_data, character.name)
            character.flags.setdefault("source", "field_event_evaluator")
            character.flags["enemy_npc"] = True
            character.flags["hostile"] = _as_bool(character.flags.get("hostile") if "hostile" in character.flags else character.extra.get("hostile", True))
            self._set_character_presence(character, location)
            _scale_character_for_danger(character, self._current_location_danger(location))
            self._ensure_character_runtime_data(character)
            self.state.world_data.characters[character.name] = character
            generated.append({"type": "character", "name": character.name})
        return generated

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
                    "location": character.location,
                    "hostile": bool(character.flags.get("hostile") or character.extra.get("hostile")),
                    "personality": _short_text(character.personality or str(character.extra.get("personality") or ""), 160),
                }
            )
            if len(nearby_npcs) >= 6:
                break
        player = world.characters.get(self.state.player_name)
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
            "player_inventory": [_compact_item_for_ai(item) for item in self._player_inventory()[:18] if isinstance(item, dict)],
            "nearby_npcs": nearby_npcs,
            "active_encounter": _compact_value(active_encounter or {}, max_chars=900),
            "active_quest": self.state.active_quest,
            "recent_log": self.state.log_text(8),
        }

    def _start_quest(self, action: str, input_type: str, quest: QuestData) -> str:
        previous_location = self.state.current_location
        quest_destination = self._ensure_quest_destination(quest)
        response = self._quest_starter(quest)
        quest_destination = self._ensure_quest_destination(quest, response)
        quest.status = "active"
        self.state.active_quest = quest.name
        state_lines = self._initialize_quest_state(quest, quest_destination, response)
        objective = str(response.get("objective") or "")
        if objective:
            quest.extra["objective"] = objective
        objective_lines = self._ensure_quest_objective_entities(quest, quest_destination, response)

        narration = str(response.get("narration") or response.get("text") or f"クエスト「{quest.name}」を開始した。")
        location = self._quest_starter_location(action, response)
        choices = self._augment_location_choices(
            _as_str_list(response.get("choices")) + self._quest_destination_choices(quest_destination, location),
            location,
        )
        quest.log.append(
            {
                "manager": "quest_starter",
                "action": action,
                "response": _strip_response_metadata(response),
            }
        )
        self.state.world_data.history.append(
            {
                "manager": "quest_starter",
                "quest": quest.name,
                "action": action,
                "response": _strip_response_metadata(response),
            }
        )
        self.state.flags["screen_mode"] = "exploration"
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        status_lines = self._apply_response_status_effects(response, "quest_starter", default_target="player")
        status_lines.extend(self._apply_response_hp_effects(response, "quest_starter"))
        status_lines.extend(self._apply_response_sp_effects(response, "quest_starter"))
        status_lines.extend(self._apply_response_progress_effects(response, "quest_starter"))
        status_lines.extend(self._apply_response_world_state_effects(response, "quest_starter", default_location=location))
        status_lines.extend(self._apply_crime_risk(action, response, "quest_starter", location=location))
        status_lines.extend(state_lines)
        status_lines.extend(objective_lines)
        if status_lines:
            status_lines = [_hide_internal_quest_tokens(line) for line in status_lines if str(line).strip()]
            self.state.display_log.extend(status_lines)
        self._apply_visual_intent(response, "quest_starter", location, previous_location)
        self.save_game()
        return self.state.log_text(16)

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
        fallback = _quest_objective_npc_fallback_design(quest, response, objective_role=objective_role)
        location = self.state.world_data.locations.get(location_name)
        subnode_context: dict[str, Any] = {}
        if location:
            try:
                graph = self._ensure_location_subnode_graph(self.state.world_data, location_name)
                node = graph.get("nodes", {}).get(subnode_id) if isinstance(graph, dict) else None
                if isinstance(node, dict):
                    subnode_context = {
                        "id": subnode_id,
                        "name": str(node.get("name") or subnode_id),
                        "kind": str(node.get("kind") or ""),
                        "description": str(node.get("description") or ""),
                    }
            except Exception:
                subnode_context = {"id": subnode_id}
        messages = [
            {
                "role": "system",
                "content": (
                    "You design one concrete quest objective NPC for Fantasia. Return JSON only. "
                    "Use the world tone, quest request, destination, and objective role to decide a player-facing name, "
                    "epithet, role label, description, personality, appearance, and whether the NPC is hostile. "
                    "For a rescue blocker/captor/obstacle, make it match the request: if the quest implies tentacles, beasts, "
                    "spirits, bandits, curses, or another non-human threat, do not default to a generic human. "
                    "Do not output UUIDs or internal ids such as rescue_target, blocker, defeat_target, or delivery_target."
                ),
            },
            {
                "role": "user",
                "content": _ai_json(
                    {
                        "objective_role": objective_role,
                        "fallback": fallback,
                        "quest": _quest_ai_context(quest, include_log=False, include_extra=True),
                        "destination": {
                            "location": location_name,
                            "location_kind": str((location.extra if location else {}).get("location_kind") or ""),
                            "danger_level": _safe_int((location.extra if location else {}).get("danger_level"), 0),
                            "description": str(location.description if location else ""),
                            "subnode": subnode_context,
                        },
                        "quest_response_hints": _compact_value(response, max_chars=1200),
                        "source_text": _quest_destination_source_text(quest, response),
                    }
                ),
            },
        ]
        try:
            generated = self._chat_json(
                "quest_objective_npc_designer",
                messages,
                max_tokens=600,
                world_name=self.state.world_name,
                player_name=self.state.player_name,
            )
        except Exception as exc:
            fallback["designer_error"] = str(exc)
            return fallback

        design = dict(fallback)
        for key in ("name", "display_alias", "role_label", "description", "personality", "look", "species", "category"):
            value = str(generated.get(key) or "").strip()
            if value:
                design[key] = value
        image_prompt = generated.get("image_prompt")
        if isinstance(image_prompt, list):
            image_prompt = ", ".join(str(item).strip() for item in image_prompt if str(item).strip())
        if str(image_prompt or "").strip():
            design["image_prompt"] = str(image_prompt).strip()
        aliases = [str(item).strip() for item in _as_list(generated.get("aliases")) if str(item).strip()]
        if aliases:
            design["aliases"] = aliases
        if "hostile" in generated:
            design["hostile"] = _as_bool(generated.get("hostile"))
        design["name"] = _clean_generated_name(design.get("name"), fallback.get("name") or "依頼対象", kind="character")
        if not str(design.get("display_alias") or "").strip():
            design["display_alias"] = design["name"]
        if not str(design.get("role_label") or "").strip():
            design["role_label"] = INTERNAL_QUEST_TOKEN_LABELS.get(objective_role, "依頼対象")
        return design

    def _create_quest_objective_npc(
        self,
        quest: QuestData,
        location_name: str,
        subnode_id: str,
        response: dict[str, Any] | None = None,
        *,
        objective_role: str = "rescue_target",
    ) -> dict[str, Any]:
        response = response or {}
        design = self._quest_objective_npc_design(quest, location_name, subnode_id, response, objective_role=objective_role)
        base_name = str(design.get("name") or _quest_objective_npc_name(quest, response, objective_role=objective_role))
        name = _unique_character_name(self.state.world_data, base_name)
        role_label = str(design.get("role_label") or INTERNAL_QUEST_TOKEN_LABELS.get(objective_role, "依頼対象"))
        display_alias = str(design.get("display_alias") or name)
        aliases = _dedupe_strs([display_alias, role_label, *[str(item) for item in _as_list(design.get("aliases"))]])
        hostile = bool(design.get("hostile")) if "hostile" in design else objective_role in {"defeat_target", "blocker"}
        description = str(design.get("description") or response.get("objective_npc_description") or response.get("objective") or quest.overview)
        personality = str(design.get("personality") or response.get("objective_npc_personality") or "")
        look = str(design.get("look") or design.get("image_prompt") or "")
        character = CharacterData(
            name=name,
            role=role_label,
            category=str(design.get("category") or "quest_objective"),
            backstory=description,
            personality=personality,
            look=look,
            image_generation_prompt=[
                part
                for part in (str(design.get("image_prompt") or "").strip(), look, description)
                if part
            ],
            flags={
                "source": "quest_objective",
                "quest_objective": True,
                "quest_name": quest.name,
                "quest_objective_kind": "npc",
                "quest_objective_role": objective_role,
                "hostile": hostile,
                "display_alias": display_alias,
                "role_label": role_label,
            },
            extra={
                "quest_name": quest.name,
                "quest_objective": True,
                "quest_objective_role": objective_role,
                "internal_role": objective_role,
                "display_alias": display_alias,
                "role_label": role_label,
                "aliases": aliases,
                "species": str(design.get("species") or ""),
                "appearance_prompt": str(design.get("image_prompt") or look),
                "objective_location": location_name,
                "objective_subnode_id": subnode_id,
                "origin_location": quest.extra.get("origin_location") or self._quest_origin_location(quest),
            },
            prompts={
                "character": str(design.get("image_prompt") or look),
                "quest_objective": description,
            },
        )
        self._ensure_character_runtime_data(character)
        self._set_character_presence(character, location_name, "quest_objective", subnode_id=subnode_id)
        self.state.world_data.characters[character.name] = character
        return {
            "kind": "npc",
            "uuid": character.uuid,
            "name": character.name,
            "display_alias": display_alias,
            "role_label": role_label,
            "location": location_name,
            "subnode_id": subnode_id,
            "role": objective_role,
            "status": "waiting",
        }

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

    def _quest_objective_character(self, entry: dict[str, Any]) -> CharacterData | None:
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
        for entry in pack.get("npcs", []):
            if not isinstance(entry, dict) or str(entry.get("status") or "") != "escorting":
                continue
            character = self._quest_objective_character(entry)
            if character and not _character_state_is_dead(character):
                self._set_character_presence(character, location, "escorted", subnode_id=subnode_id)

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
        if not report_subnode:
            return True
        try:
            return self._current_subnode_id(origin) == report_subnode
        except Exception:
            return False

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

    def _settle_rescued_quest_character(
        self,
        quest: QuestData,
        entry: dict[str, Any],
        character: CharacterData,
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
        node_name = str(hint.get("objective_subnode_name") or hint.get("objective_name") or "依頼目標").strip()
        description = str(hint.get("objective_subnode_description") or hint.get("objective_description") or quest.overview or "").strip()
        existing = nodes.get(node_id)
        if isinstance(existing, dict):
            existing["quest_name"] = quest.name
            existing["quest_objective"] = True
            if description and not existing.get("description"):
                existing["description"] = description
            return existing
        x = 560
        y = 360 + (len(nodes) % 3) * 90
        if DUNGEON_DEEPEST_SUBNODE_ID in nodes:
            parent = DUNGEON_DEEPEST_SUBNODE_ID
            x = _safe_int(nodes[parent].get("x"), 720) + 170
            y = _safe_int(nodes[parent].get("y"), 180)
        elif "depths" in nodes:
            parent = "depths"
            x = _safe_int(nodes[parent].get("x"), 560) + 170
            y = _safe_int(nodes[parent].get("y"), 180)
        elif "fork" in nodes:
            parent = "fork"
        else:
            parent = graph.get("current") if str(graph.get("current") or "") in nodes else next(iter(nodes), DEFAULT_SUBNODE_ID)
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
        return node

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
    ) -> dict[str, Any]:
        destination = quest.extra.get("destination")
        if not isinstance(destination, dict):
            return {}
        location_name = str(destination.get("location") or "").strip()
        if not location_name or location_name not in self.state.world_data.locations:
            return {}
        objective_name = str(destination.get("objective_subnode_name") or "").strip()
        objective_id = str(destination.get("objective_subnode_id") or "").strip()
        text_parts = [action]
        for payload in (referee, event_resolution):
            if isinstance(payload, dict):
                text_parts.extend(
                    str(payload.get(key) or "")
                    for key in ("location", "narration", "quest_progress")
                )
                text_parts.extend(_as_str_list(payload.get("choices")))
        text = "\n".join(part for part in text_parts if part)
        if location_name and location_name in text:
            return destination
        if objective_name and objective_name in text:
            return destination
        if objective_id and objective_id in text:
            return destination
        lowered = text.casefold()
        if any(word in lowered for word in ("目的地", "現地", "target site", "destination")) and any(
            word in lowered for word in ("向か", "行", "移動", "出発", "go", "travel", "move", "head")
        ):
            return destination
        return {}

    def _quest_starter_location(self, action: str, response: dict[str, Any]) -> str:
        current = self.state.current_location or self.state.world_data.starting_location
        proposed = str(response.get("location") or current).strip() or current
        facility_result = self._normalize_facility_response_location(action, response, current, proposed)
        if facility_result is not None:
            return str(facility_result.get("location") or current)
        settlement = self._current_settlement_location()
        if settlement is not None and proposed != settlement.name and _looks_like_facility_location_name(proposed):
            facility_name = _facility_name_from_sub_location(settlement, proposed)
            if facility_name:
                facility = self._find_or_create_facility_record(settlement, facility_name)
                if facility:
                    self._set_active_facility(settlement, facility)
            return settlement.name
        return current

    def _quest_starter(self, quest: QuestData) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        quest_payload = _ai_json(_quest_ai_context(quest))
        destination_payload = _ai_json(quest.extra.get("destination") if isinstance(quest.extra.get("destination"), dict) else {})
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのクエスト開始担当です。"
                    "Fantasiaのquest_starter相当として、"
                    "narration, choices を持つJSONだけを返してください。"
                    "必要なら quest_name, objective, location も含めてください。"
                    "この担当は依頼を受けた瞬間の導入だけを作ります。"
                    "プレイヤーを目的地へ移動させたり、依頼達成扱いにしたり、報酬を渡したりしないでください。"
                    "location は現在いる街または街の中の施設だけにしてください。"
                    "quest_destination が渡された場合、その場所と objective_subnode がゲーム側で確定した目的地です。"
                    "目的地名や目標地点名を別名へ言い換えたり、新しい目的地を作ったりしないでください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"クエスト名: {quest.name}\n"
                    f"クエストデータ: {quest_payload}\n"
                    f"quest_destination: {destination_payload}\n"
                    "このクエストの導入文、最初の目標、選択肢を作ってください。"
                    "まだ目的地へは移動せず、まだ依頼は完了していません。"
                    "選択肢には、準備や聞き込みに加えて、確定済みの目的地へ向かう行動を入れてください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "user",
                "content": (
                    "Quest objective entity rule: the game will create concrete objective NPCs, objective items, "
                    "investigation markers, or procurement requirements at quest start. Do not invent a second "
                    "different target. The game tracks objectives internally and will only complete the quest after "
                    "the exact NPC/item/marker/requirement state is satisfied and reported at the quest origin. "
                    "Never write internal ids or UUID-like identifiers in narration or choices. "
                    "Do not decide quest completion or failure. The game controls quest flags, deadline, completion, and failure."
                ),
            }
        )
        return self._chat_json(
            "quest_starter",
            messages,
            max_tokens=700,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _resolve_active_quest_action(
        self,
        action: str,
        input_type: str,
        quest: QuestData,
        action_roll: dict[str, Any] | None = None,
    ) -> str:
        previous_location = self.state.current_location
        timeout_event = self._fail_quest_if_deadline_expired(quest, source="quest_deadline", append_log=True)
        if timeout_event:
            self.save_game()
            return self.state.log_text(16)
        if _is_quest_abandon_action(action):
            narration = f"依頼「{quest.name}」から撤退した。"
            location = self.state.current_location or self.state.world_data.starting_location
            choices = self._location_default_choices(location)
            self.state.flags["screen_mode"] = "exploration"
            narration = _hide_internal_quest_tokens(narration)
            choices = [_hide_internal_quest_tokens(choice) for choice in choices]
            self.state.append_turn(action, narration, location, choices, input_type=input_type)
            self._finish_quest(quest, "abandoned", "player_abandoned", {"narration": narration})
            self._apply_visual_intent({}, "quest_abandoned", location, previous_location)
            self.save_game()
            return self.state.log_text(16)
        referee = self._quest_referee_with_free_action(action, input_type, quest, action_roll=action_roll)
        if action_roll:
            referee.setdefault("game_side_action_roll", action_roll)
        event_resolution: dict[str, Any] | None = None
        event_payload = referee.get("event")
        if _quest_event_needs_resolve(event_payload):
            event_resolution = self._quest_referee_event_resolve(action, quest, referee)

        narration_parts = [_quest_response_narration(referee)]
        if event_resolution:
            narration_parts.append(_quest_response_narration(event_resolution))
        narration = "\n".join(part for part in narration_parts if part).strip() or "クエストは静かに進行した。"

        raw_location = str(
            (event_resolution or {}).get("location")
            or referee.get("location")
            or self.state.current_location
        )
        quest_destination = self._quest_destination_for_action(quest, action, referee, event_resolution)
        if quest_destination:
            raw_location = str(quest_destination.get("location") or raw_location)
        movement_response = event_resolution or referee
        movement_result = self._normalize_world_response_location(action, input_type, movement_response, raw_location)
        location = str(movement_result.get("location") or raw_location)
        if quest.status == "failed":
            self.state.flags["screen_mode"] = "exploration"
            self.save_game()
            return self.state.log_text(16)
        if quest_destination and location == str(quest_destination.get("location") or ""):
            objective_subnode_id = str(quest_destination.get("objective_subnode_id") or "").strip()
            if objective_subnode_id:
                self._set_current_subnode(location, objective_subnode_id)
        self._set_player_presence(location)
        objective_lines = self._apply_quest_objective_action(quest, action, location)
        movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
        if movement_narration:
            narration = "\n".join([narration, *movement_narration]).strip()
        choices = self._augment_location_choices(
            _as_str_list((event_resolution or {}).get("choices") or referee.get("choices")),
            location,
        )
        finished = False
        finish_status = ""
        objective_pack = self._quest_objective_pack(quest)
        has_objective_entities = bool(
            objective_pack.get("npcs")
            or objective_pack.get("items")
            or objective_pack.get("markers")
            or objective_pack.get("requirements")
        )
        if has_objective_entities and not finished and self._quest_objective_completion_allowed(quest, action, location, event_resolution or referee):
            if _quest_completion_report_action(action):
                finished = True
                finish_status = "completed"
        completion_blocked_line = ""
        if _quest_completion_report_action(action) and has_objective_entities and not finished:
            completion_blocked_line = "> [Quest] 依頼はまだ報告できません: 目的が未達成、または報告先に戻っていません。"

        quest.log.append(
            {
                "manager": "quest_referee_with_free_action",
                "action": action,
                "input_type": input_type,
                "action_roll": action_roll,
                "response": _strip_response_metadata(referee),
            }
        )
        if event_resolution:
            quest.log.append(
                {
                    "manager": "quest_referee_event_resolve",
                    "action": action,
                    "response": _strip_response_metadata(event_resolution),
                }
            )
            quest.extra["last_event_resolution"] = _strip_response_metadata(event_resolution)
        elif event_payload:
            quest.extra["last_event"] = _strip_response_metadata(event_payload) if isinstance(event_payload, dict) else event_payload
        if referee.get("quest_progress"):
            quest.extra["quest_progress"] = str(referee.get("quest_progress"))
        if (event_resolution or {}).get("quest_update"):
            quest.extra["quest_update"] = (event_resolution or {}).get("quest_update")
        if finished:
            if not choices:
                choices = self._location_default_choices(location)

        self.state.world_data.history.append(
            {
                "manager": "quest_referee_with_free_action",
                "quest": quest.name,
                "action": action,
                "input_type": input_type,
                "action_roll": action_roll,
                "response": _strip_response_metadata(referee),
            }
        )
        if event_resolution:
            self.state.world_data.history.append(
                {
                    "manager": "quest_referee_event_resolve",
                    "quest": quest.name,
                    "action": action,
                    "response": _strip_response_metadata(event_resolution),
                }
            )

        visual_response = event_resolution or referee
        combat_source = "quest_referee_event_resolve" if event_resolution else "quest_referee_with_free_action"
        narration, choices, transition_response = self._maybe_start_combat_from_response(
            action,
            input_type,
            combat_source,
            visual_response,
            location,
            narration,
            choices,
        )
        if transition_response:
            quest.extra["last_combat_transition"] = _strip_response_metadata(transition_response)
        if not self._active_encounter() and movement_result.get("moved"):
            narration, choices, arrival_response = self._evaluate_hostile_arrival(
                action,
                input_type,
                "quest_arrival",
                location,
                narration,
                choices,
            )
            if arrival_response:
                quest.extra["last_hostile_arrival"] = _strip_response_metadata(arrival_response)
        if not self._active_encounter():
            self.state.flags["screen_mode"] = "exploration"
        narration = _hide_internal_quest_tokens(narration)
        choices = [_hide_internal_quest_tokens(choice) for choice in choices]
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._append_action_roll_log(action_roll)
        status_lines = self._apply_response_status_effects(referee, "quest_referee_with_free_action", default_target="player")
        status_lines.extend(str(line) for line in movement_result.get("status_lines", []) if str(line).strip())
        status_lines.extend(objective_lines)
        if completion_blocked_line:
            status_lines.append(completion_blocked_line)
        status_lines.extend(self._apply_response_hp_effects(referee, "quest_referee_with_free_action"))
        status_lines.extend(self._apply_response_sp_effects(referee, "quest_referee_with_free_action"))
        status_lines.extend(self._apply_response_progress_effects(referee, "quest_referee_with_free_action"))
        status_lines.extend(self._apply_response_world_state_effects(referee, "quest_referee_with_free_action", default_location=location))
        status_lines.extend(self._apply_crime_risk(action, referee, "quest_referee_with_free_action", location=location))
        if event_resolution:
            status_lines.extend(self._apply_response_status_effects(event_resolution, "quest_referee_event_resolve", default_target="player"))
            status_lines.extend(self._apply_response_hp_effects(event_resolution, "quest_referee_event_resolve"))
            status_lines.extend(self._apply_response_sp_effects(event_resolution, "quest_referee_event_resolve"))
            status_lines.extend(self._apply_response_progress_effects(event_resolution, "quest_referee_event_resolve"))
            status_lines.extend(self._apply_response_world_state_effects(event_resolution, "quest_referee_event_resolve", default_location=location))
            status_lines.extend(self._apply_crime_risk(action, event_resolution, "quest_referee_event_resolve", location=location))
        if status_lines:
            status_lines = [_hide_internal_quest_tokens(line) for line in status_lines if str(line).strip()]
            self.state.display_log.extend(status_lines)
        self._apply_visual_intent(visual_response, "quest_referee_event_resolve" if event_resolution else "quest_referee_with_free_action", location, previous_location)
        self._apply_response_rewards(referee, "quest_referee_with_free_action")
        if event_resolution:
            self._apply_response_rewards(event_resolution, "quest_referee_event_resolve")
        if finished:
            self._finish_quest(quest, finish_status, "quest_referee_event_resolve" if event_resolution else "quest_referee_with_free_action", event_resolution or referee)
        self.save_game()
        return self.state.log_text(16)

    def _quest_referee_with_free_action(
        self,
        action: str,
        input_type: str,
        quest: QuestData,
        action_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        quest_payload = _ai_json(_quest_ai_context(quest))
        destination_payload = _ai_json(quest.extra.get("destination") if isinstance(quest.extra.get("destination"), dict) else {})
        action_roll_payload = json.dumps(action_roll or {}, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのクエスト進行判定担当です。"
                    "Fantasiaのquest_referee_with_free_action相当として、"
                    "プレイヤーの自由行動をクエスト進行へ変換してください。"
                    "narration, choices を持つJSONだけを返してください。"
                    "必要なら location, quest_progress, event, finished も含めてください。"
                    "game_side_action_roll が enabled=true の場合、クエスト行動の成否はゲーム側の確定判定として必ず尊重してください。"
                    "event は未解決で追加判定が必要な突発事象だけに使い、単なる進捗や結果済みの出来事は quest_progress に書いてください。"
                    "quest_destination がある場合、目的地と objective_subnode はゲーム側で確定済みです。"
                    "目的地へ向かう行動では location に quest_destination.location を返し、別名の新規ロケーションを作らないでください。"
                    "クエスト目標は objective_subnode に存在するものとして扱い、同じ目標を別の場所へ移動させないでください。"
                    "救出対象を保護して依頼主へ報告し、報酬や経験値を渡す段階まで到達したら finished=true と quest_status=\"completed\" を必ず返してください。"
                    "依頼の説明を聞いた、目的地や報酬を確認した、準備を始めた、だけの段階では finished や quest_status=\"completed\" を返さないでください。"
                    "完了後に新しい探索フックを提示する場合も、このクエスト自体は完了として扱ってください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"クエスト名: {quest.name}\n"
                    f"クエストデータ: {quest_payload}\n"
                    f"quest_destination: {destination_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"game_side_action_roll: {action_roll_payload}\n"
                    "この行動がクエストをどう進めるか判定してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    "Override quest completion behavior: never decide quest completion or failure in this response. "
                    "Do not output finished=true, quest_status, quest_completed, quest_failed, completed_quest, or complete_quest. "
                    "The game-side quest state machine owns all quest flags, deadlines, completion, and failure."
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Important game-side objective rule: if quest_data.details.objective_entities exists, those listed objective entries "
                    "are the only valid quest targets. Do not replace them with similarly named NPCs, items, places, or requirements. "
                    "Narrate rescue, retrieval, defeat, delivery, investigation, procurement, escort, and reporting around those game-side tracked entities. The game "
                    "will block completion until the exact objective entry state has been satisfied and reported. "
                    "Never write internal ids or UUID-like identifiers in narration or choices. "
                    "Do not set finished, quest_status, quest_completed, quest_failed, or completed_quest. "
                    "Describe the scene and offer helpful choices; the game-side quest pipeline updates flags."
                ),
            }
        )
        return self._chat_json(
            "quest_referee_with_free_action",
            messages,
            max_tokens=800,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

    def _quest_referee_event_resolve(
        self,
        action: str,
        quest: QuestData,
        referee_response: dict[str, Any],
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data))
        quest_payload = _ai_json(_quest_ai_context(quest))
        referee_payload = json.dumps(_strip_response_metadata(referee_response), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのクエストイベント解決担当です。"
                    "Fantasiaのquest_referee_event_resolve相当として、"
                    "発生したイベントの結果を確定してください。"
                    "narration, choices を持つJSONだけを返してください。"
                    "必要なら location, quest_update, finished も含めてください。"
                    "イベント解決後に元の目的が達成、失敗、撤退のいずれかに到達した場合は finished=true と quest_status を必ず返してください。"
                    "結果済みの進捗をもう一度描写し直さず、必要な差分だけを短く返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"クエスト名: {quest.name}\n"
                    f"クエストデータ: {quest_payload}\n"
                    f"プレイヤー行動: {action}\n"
                    f"直前の判定: {referee_payload}\n"
                    "イベント解決後の描写、クエスト更新、次の選択肢を確定してください。"
                ),
            },
        ]
        messages.append(
            {
                "role": "system",
                "content": (
                    "Override quest completion behavior: never decide quest completion or failure in this response. "
                    "Do not output finished=true, quest_status, quest_completed, quest_failed, completed_quest, or complete_quest. "
                    "The game-side quest state machine owns all quest flags, deadlines, completion, and failure."
                ),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "Use quest_data.details.objective_entities when present. The game validates completion with internal objective entries, "
                    "so event resolution must not complete a quest unless the exact objective NPC, item, marker, or "
                    "procurement requirement has reached the game-side report-ready state. Do not write internal ids or UUID-like identifiers. "
                    "Do not decide completion or failure; the game-side flags do that."
                ),
            }
        )
        return self._chat_json(
            "quest_referee_event_resolve",
            messages,
            max_tokens=800,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

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

    def _character_for_image(self, character_name: str | None) -> CharacterData:
        if character_name:
            character = self.state.world_data.characters.get(character_name)
            if character:
                return character
        if self.state.world_data.characters:
            return next(iter(self.state.world_data.characters.values()))
        character = CharacterData(
            name=self.state.player_name or "Player",
            role="player",
            category="player",
            look="fantasy RPG adventurer",
            image_generation_prompt=["fantasy RPG adventurer", "single character", "full body"],
            flags={"source": "image_pipeline_fallback"},
        )
        self._set_character_presence(character, self.state.current_location or self.state.world_data.starting_location)
        self.state.world_data.characters[character.name] = character
        return character

    def _monster_for_image(self, monster_name: str | None) -> CharacterData:
        if monster_name:
            character = self.state.world_data.characters.get(monster_name)
            if character:
                return character
        for character in self.state.world_data.characters.values():
            if character.flags.get("enemy_npc") or character.category in {"enemy_npc", "quest_objective"} or character.flags.get("hostile"):
                return character
        monster = CharacterData(
            name="硝子森の影",
            role="敵対者",
            category="wild_encounter",
            backstory="霧と雨音の中から現れる、硝子森に棲む影のような魔物。",
            look="霧と雨音の中から現れる、硝子森に棲む影のような魔物。",
            traits=[
                {"name": "慎重", "effect": "相手の動きを見てから行動する。"},
                {"name": "霧まとい", "effect": "距離を取り、姿をぼかす。"},
            ],
            flags={"source": "image_pipeline_fallback", "enemy_npc": True, "hostile": True},
        )
        self._set_character_presence(monster, self.state.current_location or self.state.world_data.starting_location)
        self._ensure_character_runtime_data(monster)
        self.state.world_data.characters[monster.name] = monster
        return monster

    def stop(self) -> None:
        self.llm.stop()
        stop_image = getattr(self.image_backend, "stop", None)
        if callable(stop_image):
            stop_image()

    def _active_conversation_character(self) -> CharacterData | None:
        active = self.state.flags.get("active_conversation")
        if not isinstance(active, dict):
            return None
        name = str(active.get("character") or "")
        if not name:
            return None
        character = self.state.world_data.characters.get(name)
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

    def _find_conversation_target(self, action: str) -> CharacterData | None:
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

    def _find_quest_to_start(self, action: str) -> QuestData | None:
        if not self.state.flags.get("allow_direct_quest_start"):
            return None
        if self.state.active_quest:
            return None
        text = action.strip()
        if not text:
            return None
        for quest in self.state.world_data.quests:
            if quest.status not in {"available", ""}:
                continue
            if quest.name and quest.name in text:
                return quest
        available_quests = [quest for quest in self.state.world_data.quests if quest.status in {"available", ""}]
        if available_quests and _text_may_need_context_reference(text):
            resolved = self._resolve_context_reference(text, "quest_start_target", allowed_target_types=["quest"])
            target_name = str(resolved.get("target_name") or "").strip()
            if target_name:
                for quest in available_quests:
                    if quest.name == target_name or target_name in quest.name or quest.name in target_name:
                        return quest
        if "クエスト" in text or "依頼" in text:
            if len(available_quests) == 1:
                return available_quests[0]
            return available_quests[0] if available_quests else None
        return None

    def _match_character_reference_from_candidates(
        self,
        target_name: str,
        candidates: list[CharacterData],
    ) -> CharacterData | None:
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

    def _find_quest_by_name(self, name: str) -> QuestData | None:
        for quest in self.state.world_data.quests:
            if quest.name == name:
                return quest
        return None

    def _chat_json(
        self,
        manager_name: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        world_name: str,
        player_name: str,
        retries: int = 2,
    ) -> dict[str, Any]:
        templated_messages = self.prompt_templates.apply_messages(manager_name, messages)
        instruction = self.prompt_templates.apply_schema_instruction(manager_name, schema_instruction(manager_name))
        base_messages = _with_schema_instruction(templated_messages, instruction)
        last_user_prompt = next((item.get("content", "") for item in reversed(messages) if item.get("role") == "user"), "")
        context_action = _player_action_from_prompt(last_user_prompt)
        if self._should_attach_temp_context(manager_name, context_action):
            base_messages = base_messages + [self._temp_context_reference_message(manager_name, context_action)]
        attempt_messages = base_messages
        last_response: Any = {}
        last_errors: list[str] = []
        self._write_temp_llm_context_log(f"before_llm:{manager_name}", action=last_user_prompt)

        for attempt in range(retries + 1):
            result = self.llm.chat(manager_name, attempt_messages, max_tokens=max_tokens)
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
            return response

        raise JsonResponseError(manager_name, last_errors, last_response)


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


def _character_prompt_parts(character: CharacterData) -> list[str]:
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


def _character_visual_feature_parts(character: CharacterData) -> list[str]:
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
    parts.extend(_dict_list_visual_parts(character.traits, ("name", "description", "effect", "severity", "visual", "appearance")))
    parts.extend(_dict_list_visual_parts(character.skills, ("name", "description", "effect", "element", "skill_type", "visual_effect")))
    parts.extend(_dict_list_visual_parts(character.status_effects, ("name", "description", "effect", "severity", "visual")))
    parts.extend(_ability_visual_parts(character.extra))
    parts.extend(_dict_list_visual_parts(character.inventory[:4], ("name", "category", "description")))
    return _dedupe_strs(parts)[:36]


def _monster_prompt_parts(monster: CharacterData) -> list[str]:
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


def _monster_visual_feature_parts(monster: CharacterData) -> list[str]:
    parts = [
        monster.name,
        monster.role,
        monster.category,
        monster.backstory,
        monster.look,
    ]
    parts.extend(_dict_list_visual_parts(monster.traits, ("name", "description", "effect", "severity", "visual", "appearance")))
    parts.extend(_dict_list_visual_parts(monster.skills, ("name", "description", "effect", "element", "skill_type", "visual_effect")))
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


def _cg_subject_prompt_parts(characters: list[CharacterData], monsters: list[CharacterData]) -> list[str]:
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


def _visual_subjects_context(characters: list[CharacterData], monsters: list[CharacterData]) -> dict[str, Any]:
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


def _status_effect_target(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    text = str(value.get("target") or value.get("actor") or value.get("recipient") or "").strip().lower()
    if text in {"player", "pc", "hero", "self", "you", "あなた", "プレイヤー"}:
        return "player"
    if text in {"opponent", "enemy", "monster", "npc", "target", "foe", "相手", "敵", "対象"}:
        return "opponent"
    return ""


def _global_status_target(value: Any, default_target: str, context_target: str) -> str:
    if not isinstance(value, dict):
        return default_target
    text = str(
        value.get("target")
        or value.get("actor")
        or value.get("recipient")
        or value.get("character")
        or value.get("character_name")
        or value.get("npc")
        or value.get("npc_name")
        or ""
    ).strip()
    lowered = text.lower()
    if lowered in {"", "default"}:
        return default_target
    if lowered in {"player", "pc", "hero", "protagonist", "you", "あなた", "プレイヤー"}:
        return "player"
    if lowered in {"self"}:
        return default_target
    if lowered in {"speaker", "npc", "character", "target"}:
        return context_target or default_target
    if lowered in {"monster", "enemy", "opponent"}:
        return "monster"
    return text


def _status_effect_applied_line(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("target") or "対象")
    effect = item.get("effect") if isinstance(item.get("effect"), dict) else {}
    name = str(effect.get("name") or "状態")
    marker = "長期状態" if effect.get("long_term") or effect.get("persistent") or effect.get("permanent") else "状態"
    stage = str(effect.get("stage") or "")
    suffix = f" ({stage})" if stage else ""
    return f"[{marker}] {label}に{name}{suffix}が付与された。"


def _status_effect_removed_line(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("target") or "target")
    effect = item.get("effect") if isinstance(item.get("effect"), dict) else {}
    name = str(effect.get("name") or "status")
    marker = "long-term status removed" if effect.get("long_term") or effect.get("persistent") or effect.get("permanent") else "status removed"
    treatment = str(item.get("treatment") or "")
    suffix = f" ({treatment})" if treatment else ""
    return f"[{marker}] {label}: {name}{suffix}"


def _status_effect_items(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        if any(
            key in value
            for key in (
                "name",
                "title",
                "label",
                "id",
                "status",
                "condition",
                "effect",
                "effect_text",
                "description",
                "mechanics",
            )
        ):
            return [value]
        result: list[Any] = []
        for item in value.values():
            result.extend(_status_effect_items(item))
        return result
    return [value]


def _normalise_status_effect(value: Any, *, source: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        raw_name = str(
            value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("id")
            or value.get("status")
            or value.get("condition")
            or ""
        ).strip()
        data = {str(key): item for key, item in value.items()}
    else:
        raw_name = str(value).strip()
        data = {"name": raw_name}
    effect_text = _first_status_text(
        data,
        "effect",
        "effect_text",
        "mechanics",
        "mechanical_effect",
        "rule",
        "rules",
    )
    description = _first_status_text(data, "description", "summary", "detail")
    raw_name = raw_name or _status_name_from_text(effect_text or description)
    if not raw_name:
        return {}
    preset = _status_effect_preset(" ".join(part for part in (raw_name, effect_text, description) if part))
    effect_id = str(data.get("id") or preset.get("id") or _slug_status(raw_name))
    name = str(data.get("name") or preset.get("name") or raw_name)
    inferred_duration = _infer_status_duration(effect_text or description or raw_name)
    duration_value = data.get("duration", data.get("turns", preset.get("duration", inferred_duration)))
    permanent = _is_permanent_status_duration(duration_value) or _as_bool(data.get("permanent") or data.get("persistent") or preset.get("persistent"))
    long_term = permanent or _as_bool(data.get("long_term") or data.get("longterm") or preset.get("long_term"))
    duration = 0 if permanent else _safe_int(
        duration_value,
        _safe_int(preset.get("duration", inferred_duration), 0),
    )
    if duration <= 0 and inferred_duration > 0:
        duration = inferred_duration
    remaining = _safe_int(data.get("remaining_turns", duration), duration)
    damage = _safe_int(
        data.get(
            "damage_per_turn",
            data.get("tick_damage", data.get("hp_damage_per_turn", preset.get("damage_per_turn", 0))),
        ),
        _safe_int(preset.get("damage_per_turn"), 0),
    )
    hp_delta = _status_hp_delta_per_turn(data, effect_text or description or raw_name, damage)
    result = {
        "id": effect_id,
        "name": name,
        "description": description or str(preset.get("description") or ""),
        "effect": effect_text,
        "duration": duration,
        "remaining_turns": remaining,
        "damage_per_turn": damage,
        "hp_delta_per_turn": hp_delta,
        "source": source or str(data.get("source") or ""),
    }
    for key in (
        "severity",
        "category",
        "scope",
        "stage",
        "progress",
        "visual",
        "tick_text",
        "expire_text",
        "apply_text",
        "remove_condition",
        "started_day",
        "started_location",
        "expected_day",
        "due_day",
        "expires_day",
        "notes",
        "tags",
        "modifiers",
        "stat_modifiers",
        "prevents_action",
        "prevents_movement",
        "prevents_attack",
        "prevents_escape",
        "blocked_actions",
        "combat_state",
    ):
        item = data.get(key) if key in data else preset.get(key)
        if item not in (None, "", [], {}):
            result[key] = item
    if permanent:
        result["permanent"] = True
        result["persistent"] = True
    if long_term:
        result["long_term"] = True
    return _drop_empty(result)


def _first_status_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()
    return ""


def _status_name_from_text(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    for separator in ("。", ".", "、", ",", ":", "：", "\n"):
        if separator in cleaned:
            cleaned = cleaned.split(separator, 1)[0].strip()
            break
    return cleaned[:28] + ("..." if len(cleaned) > 28 else "")


def _infer_status_duration(text: str) -> int:
    source = str(text or "")
    patterns = (
        r"(\d+)\s*(?:ターン|turns?)",
        r"(?:for|next)\s+(\d+)\s+turns?",
    )
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.IGNORECASE)
        if match:
            return max(0, _safe_int(match.group(1), 0))
    return 0


def _is_permanent_status_duration(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {
        "permanent",
        "persistent",
        "indefinite",
        "until_removed",
        "until removed",
        "long_term",
        "long term",
        "永続",
        "恒久",
        "長期",
        "解除まで",
    }


def _status_hp_delta_per_turn(data: dict[str, Any], text: str, damage_per_turn: int) -> int:
    for key in ("hp_delta_per_turn", "hp_delta_each_turn", "health_delta_per_turn"):
        if key in data:
            return _safe_int(data.get(key), 0)
    for key in ("heal_per_turn", "healing_per_turn", "regeneration_per_turn"):
        if key in data:
            return max(0, _safe_int(data.get(key), 0))
    if damage_per_turn:
        return -max(0, damage_per_turn)
    inferred = _infer_status_hp_delta(text)
    return inferred


def _infer_status_hp_delta(text: str) -> int:
    source = str(text or "")
    lowered = source.lower()
    heal_words = ("回復", "癒", "heal", "regenerat", "restore")
    damage_words = ("ダメージ", "損傷", "傷", "減る", "失う", "damage", "lose hp", "hp loss")
    if any(word in lowered for word in heal_words):
        amount = _first_int_near_status_word(source, heal_words)
        if amount:
            return amount
    if any(word in lowered for word in damage_words):
        amount = _first_int_near_status_word(source, damage_words)
        if amount:
            return -amount
    return 0


def _first_int_near_status_word(text: str, words: tuple[str, ...]) -> int:
    source = str(text or "")
    lowered = source.lower()
    for word in words:
        index = lowered.find(str(word).lower())
        if index < 0:
            continue
        after = source[index : index + 36]
        match = re.search(r"(\d+)", after)
        if match:
            return max(0, _safe_int(match.group(1), 0))
        before = source[max(0, index - 36) : index]
        matches = list(re.finditer(r"(\d+)", before))
        if matches:
            return max(0, _safe_int(matches[-1].group(1), 0))
    match = re.search(r"(\d+)", source)
    return max(0, _safe_int(match.group(1), 0)) if match else 0


def _format_status_template(template: Any, actor_label: str, name: str, hp_delta: int) -> str:
    text = str(template or "").strip()
    if not text:
        return ""
    values = {
        "actor": actor_label,
        "name": name,
        "damage": abs(hp_delta) if hp_delta < 0 else 0,
        "heal": hp_delta if hp_delta > 0 else 0,
        "hp_delta": hp_delta,
    }
    try:
        return text.format(**values)
    except (KeyError, ValueError):
        return text


def _status_effect_preset(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if (
        any(
            word in lowered
            for word in (
                "incapacitated",
                "immobilized",
                "immobilised",
                "restrained",
                "bound",
                "tied up",
                "unable to act",
                "cannot act",
            )
        )
        or any(word in text for word in ("行動不能", "拘束", "捕縛", "縛ら", "身動き", "動けない", "動けず"))
    ):
        return {
            "id": INCAPACITATED_STATUS_ID,
            "name": INCAPACITATED_STATUS_NAME,
            "duration": 0,
            "damage_per_turn": 0,
            "description": "拘束や麻痺などにより、攻撃・逃走・移動ができない。",
            "category": "control",
            "prevents_action": True,
            "prevents_movement": True,
            "prevents_attack": True,
            "prevents_escape": True,
            "blocked_actions": ["attack", "escape", "aggressive_action", "movement"],
            "tags": ["incapacitated", "restraint"],
        }
    if "pregnan" in lowered or "妊娠" in text:
        return {
            "id": "pregnancy",
            "name": "妊娠",
            "duration": 0,
            "damage_per_turn": 0,
            "description": "長期的に保持される身体状態。",
            "category": "long_term_condition",
            "scope": "character",
            "long_term": True,
            "persistent": True,
        }
    if any(word in lowered for word in ("poison", "venom")) or "毒" in text:
        return {"id": "poison", "name": "毒", "duration": 3, "damage_per_turn": 1, "description": "毒が体力を削る。"}
    if any(word in lowered for word in ("bleed", "bleeding")) or "出血" in text:
        return {"id": "bleeding", "name": "出血", "duration": 3, "damage_per_turn": 1, "description": "出血が続いている。"}
    if any(word in lowered for word in ("burn", "burning")) or "火傷" in text or "炎上" in text:
        return {"id": "burning", "name": "火傷", "duration": 2, "damage_per_turn": 1, "description": "火傷が痛む。"}
    if any(word in lowered for word in ("paralysis", "paralyzed", "stun", "stunned")) or "麻痺" in text or "しびれ" in text or "気絶" in text:
        return {
            "id": "paralyzed",
            "name": "麻痺",
            "duration": 2,
            "damage_per_turn": 0,
            "description": "体がうまく動かない。",
            "prevents_action": True,
            "prevents_movement": True,
            "prevents_attack": True,
            "prevents_escape": True,
            "blocked_actions": ["attack", "escape", "aggressive_action", "movement"],
        }
    if any(word in lowered for word in ("dead", "death")) or "死亡" in text:
        return {"id": "dead", "name": "死亡", "duration": 0, "damage_per_turn": 0}
    if any(word in lowered for word in ("defeated", "unconscious")) or "戦闘不能" in text:
        return {"id": "defeated", "name": "戦闘不能", "duration": 0, "damage_per_turn": 0}
    if any(word in lowered for word in ("wounded", "injured")) or "負傷" in text or "重傷" in text:
        return {"id": "wounded", "name": "負傷", "duration": 0, "damage_per_turn": 0}
    return {}


def _status_effect_from_status_text(text: str) -> dict[str, Any]:
    preset = _status_effect_preset(text)
    return _normalise_status_effect(preset, source="status_text") if preset else {}


def _status_effect_id_matches(effect: dict[str, Any], ids: set[str]) -> bool:
    effect_id = _status_effect_id(effect)
    if effect_id in ids:
        return True
    text = json.dumps(effect, ensure_ascii=False, default=str).casefold()
    return any(item.casefold() in text for item in ids)


def _status_effect_blocked_actions(effect: dict[str, Any]) -> set[str]:
    raw = effect.get("blocked_actions")
    actions: set[str] = set()
    if isinstance(raw, str):
        actions.update(part.strip().casefold() for part in re.split(r"[,/| ]+", raw) if part.strip())
    elif isinstance(raw, (list, tuple, set)):
        actions.update(str(part or "").strip().casefold() for part in raw if str(part or "").strip())
    return actions


def _status_effect_blocks_action(effect: dict[str, Any]) -> bool:
    if _as_bool(effect.get("prevents_action")):
        return True
    if _status_effect_id_matches(effect, {INCAPACITATED_STATUS_ID, "paralyzed", "stunned"}):
        return True
    blocked = _status_effect_blocked_actions(effect)
    return bool(blocked.intersection({"action", "actions", "all", "attack", "escape", "aggressive_action"}))


def _status_effect_blocks_movement(effect: dict[str, Any]) -> bool:
    if _as_bool(effect.get("prevents_movement")):
        return True
    if _status_effect_id_matches(effect, {INCAPACITATED_STATUS_ID, "paralyzed", "stunned"}):
        return True
    return bool(_status_effect_blocked_actions(effect).intersection({"movement", "move", "travel", "map", "subnode"}))


def _status_effect_blocks_attack(effect: dict[str, Any]) -> bool:
    if _as_bool(effect.get("prevents_attack")):
        return True
    if _status_effect_blocks_action(effect):
        return True
    return bool(_status_effect_blocked_actions(effect).intersection({"attack", "aggressive_action"}))


def _status_effect_blocks_escape(effect: dict[str, Any]) -> bool:
    if _as_bool(effect.get("prevents_escape")):
        return True
    if _status_effect_blocks_movement(effect):
        return True
    return bool(_status_effect_blocked_actions(effect).intersection({"escape", "flee", "run"}))


def _status_effect_is_surrendered_or_fled(effect: dict[str, Any]) -> bool:
    return _status_effect_id(effect) in {SURRENDERED_STATUS_ID, FLED_STATUS_ID}


def _merge_status_effect(status_list: list[dict[str, Any]], effect: dict[str, Any]) -> None:
    effect_id = _status_effect_id(effect)
    for existing in status_list:
        if _status_effect_id(existing) != effect_id:
            continue
        existing.update({key: value for key, value in effect.items() if value not in (None, "", [])})
        existing["remaining_turns"] = max(
            _safe_int(existing.get("remaining_turns"), 0),
            _safe_int(effect.get("remaining_turns"), 0),
        )
        existing["duration"] = max(_safe_int(existing.get("duration"), 0), _safe_int(effect.get("duration"), 0))
        existing["damage_per_turn"] = max(_safe_int(existing.get("damage_per_turn"), 0), _safe_int(effect.get("damage_per_turn"), 0))
        return
    status_list.append(effect)


def _tick_status_effects(status_list: list[dict[str, Any]], actor_label: str) -> tuple[list[dict[str, Any]], int, list[str]]:
    updated: list[dict[str, Any]] = []
    total_hp_delta = 0
    lines: list[str] = []
    for raw in status_list:
        effect = _normalise_status_effect(raw, source=str(raw.get("source") or "") if isinstance(raw, dict) else "")
        if not effect:
            continue
        name = str(effect.get("name") or "状態異常")
        hp_delta = _safe_int(effect.get("hp_delta_per_turn"), -max(0, _safe_int(effect.get("damage_per_turn"), 0)))
        if hp_delta:
            total_hp_delta += hp_delta
            tick_text = _format_status_template(effect.get("tick_text"), actor_label, name, hp_delta)
            if tick_text:
                lines.append(tick_text)
            elif hp_delta < 0:
                lines.append(f"[状態] {actor_label}は{name}により{abs(hp_delta)}ダメージを受けた。")
            else:
                lines.append(f"[状態] {actor_label}は{name}により{hp_delta}回復した。")
        elif effect.get("tick_text"):
            lines.append(_format_status_template(effect.get("tick_text"), actor_label, name, hp_delta))
        elif effect.get("effect") and _safe_int(effect.get("remaining_turns"), 0) > 0:
            lines.append(f"[状態] {actor_label}は{name}の影響を受けている: {effect.get('effect')}")
        remaining = _safe_int(effect.get("remaining_turns"), 0)
        if remaining > 0:
            remaining -= 1
            if remaining <= 0:
                expire_text = _format_status_template(effect.get("expire_text"), actor_label, name, hp_delta)
                lines.append(expire_text or f"[状態] {actor_label}の{name}は治まった。")
                continue
            effect["remaining_turns"] = remaining
        updated.append(effect)
    return updated, total_hp_delta, lines


def _status_effect_id(value: Any) -> str:
    if isinstance(value, dict):
        text = str(
            value.get("id")
            or value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("status")
            or value.get("condition")
            or value.get("effect")
            or value.get("description")
            or ""
        )
    else:
        text = str(value)
    preset = _status_effect_preset(text)
    return str(preset.get("id") or _slug_status(text))


def _slug_status(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text).strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "status"


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


def _normalise_skill(value: Any) -> dict[str, Any]:
    skill = _as_named_dict(value, "Skill")
    name = str(skill.get("name") or skill.get("skill") or skill.get("title") or "").strip()
    if not name:
        return {}
    skill["name"] = name
    skill_type = str(skill.get("skill_type") or skill.get("type") or skill.get("category") or "physical").strip().lower()
    skill["skill_type"] = skill_type or "physical"
    skill["element"] = _normalise_element_id(skill.get("element") or skill.get("attribute") or skill.get("element_type") or skill.get("category") or skill.get("skill_type"))
    skill["category"] = skill["element"]
    power = _entry_power(skill, fallback=_skill_power_from_text(skill))
    skill["power"] = power
    skill["strength_level"] = power
    skill["sp_cost"] = _skill_sp_cost(skill)
    for old_key in ("max_uses", "uses", "remaining_uses", "current_uses"):
        skill.pop(old_key, None)
    return skill


def _normalise_trait(value: Any) -> dict[str, Any]:
    trait = _as_named_dict(value, "Trait")
    name = str(trait.get("name") or trait.get("trait") or trait.get("title") or "").strip()
    if not name:
        return {}
    trait["name"] = name
    power = _entry_power(trait, fallback=1)
    trait["power"] = power
    trait["strength_level"] = power
    trait["severity"] = power
    return trait


def _game_controlled_hp_keys(target: str, *, top_level: bool = False) -> set[str]:
    if target == "opponent":
        return {
            "opponent_hp",
            "enemy_hp",
            "target_hp",
            "opponent_current_hp",
            "opponent_hp_delta",
            "enemy_hp_delta",
            "target_hp_delta",
            "opponent_damage_hp",
            "enemy_damage_hp",
            "target_damage_hp",
            "opponent_heal_hp",
            "enemy_heal_hp",
            "target_heal_hp",
        }
    keys = {
        "player_hp",
        "player_current_hp",
        "player_hp_delta",
        "hp_delta",
        "health_delta",
        "damage_hp",
        "hp_damage",
        "player_damage_hp",
        "harm_hp",
        "heal_hp",
        "healing",
        "restore_hp",
        "recover_hp",
        "hp_restore",
        "player_heal_hp",
        "player_recover_hp",
        "hp_effect",
        "hp_effects",
        "player_hp_effect",
        "player_hp_effects",
        "health_effect",
        "health_effects",
        "recovery_effect",
        "recovery_effects",
    }
    if top_level:
        keys.add("current_hp")
    return keys


def _strip_hp_update_value(value: Any, target: str) -> Any:
    if isinstance(value, list):
        return [_strip_hp_update_value(item, target) for item in value]
    if not isinstance(value, dict):
        return value
    blocked = _game_controlled_hp_keys(target)
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if str(key).strip().lower() in blocked:
            continue
        cleaned[key] = _strip_hp_update_value(item, target)
    return cleaned


def _combat_response_candidates(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    candidates = [response]
    for key in (
        "combat_judgement",
        "combat_judgment",
        "combat_result",
        "damage_judgement",
        "damage_judgment",
        "damage_calculation",
        "skill_judgement",
        "skill_judgment",
        "skill_calculation",
        "attack_result",
        "game_combat_result",
    ):
        value = response.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    return candidates


def _combat_value_from_response(response: Any, keys: tuple[str, ...]) -> Any:
    for candidate in _combat_response_candidates(response):
        for key in keys:
            if key in candidate and candidate.get(key) not in (None, ""):
                return candidate.get(key)
    return None


def _combat_weakness_multiplier(response: Any, default: float = 1.0) -> float:
    value = _combat_value_from_response(
        response,
        (
            "weakness_multiplier",
            "weakness_modifier",
            "weakness",
            "damage_multiplier",
            "effectiveness",
            "element_multiplier",
            "element_modifier",
            "multiplier",
        ),
    )
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        number_match = re.search(r"-?\d+(?:\.\d+)?", text)
        if number_match:
            value = number_match.group(0)
        elif any(word in text for word in ("immune", "無効", "効かない", "通らない")):
            return 0.0
        elif any(word in text for word in ("resist", "耐性", "軽減", "半減")):
            return 0.5
        elif any(word in text for word in ("very weak", "大弱点", "致命的", "critical")):
            return 2.0
        elif any(word in text for word in ("weak", "弱点", "有効")):
            return 1.5
        else:
            return default
    multiplier = _safe_float(value, default)
    if multiplier > 3 and multiplier <= 300:
        multiplier /= 100.0
    return max(0.0, min(3.0, multiplier))


def _combat_apply_defense(response: Any, *, default: bool) -> bool:
    ignore_value = _combat_value_from_response(response, ("ignore_defense", "pierce_defense", "defense_ignored"))
    if ignore_value not in (None, "") and _as_bool(ignore_value):
        return False
    value = _combat_value_from_response(
        response,
        ("apply_defense", "uses_defense", "use_defense", "defense_applies", "subtract_defense"),
    )
    if value in (None, ""):
        return default
    return _as_bool(value)


def _combat_ability_from_response(response: Any, *, skill: dict[str, Any], healing: bool) -> str:
    value = _combat_value_from_response(
        response,
        ("ability", "attribute", "ability_id", "attribute_id", "damage_ability", "scaling_attribute"),
    )
    ability = _normalise_combat_ability(value)
    if ability:
        return ability
    return _skill_default_ability(skill, healing=healing)


def _normalise_combat_ability(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    aliases = {
        "str": "str",
        "strength": "str",
        "power": "str",
        "筋力": "str",
        "力": "str",
        "dex": "dex",
        "dexterity": "dex",
        "agi": "dex",
        "agility": "dex",
        "器用": "dex",
        "敏捷": "dex",
        "con": "con",
        "constitution": "con",
        "endurance": "con",
        "耐久": "con",
        "int": "int",
        "intelligence": "int",
        "knowledge": "int",
        "知力": "int",
        "wis": "wis",
        "will": "will",
        "wisdom": "wis",
        "spirit": "will",
        "意志": "will",
        "精神": "wis",
        "cha": "cha",
        "charisma": "cha",
        "charm": "cha",
        "魅力": "cha",
        "交渉": "cha",
        "magic": "magic",
        "mag": "magic",
        "魔力": "magic",
    }
    return aliases.get(text, "")


def _skill_is_healing(skill: dict[str, Any], response: Any) -> bool:
    value = _combat_value_from_response(response, ("effect_type", "skill_effect", "intent", "result_type", "type"))
    text = " ".join(
        str(item or "")
        for item in (
            value,
            skill.get("name"),
            skill.get("skill_type"),
            skill.get("element"),
            skill.get("description"),
            skill.get("effect"),
            skill.get("effects"),
        )
    ).lower()
    return any(word in text for word in ("heal", "healing", "recover", "recovery", "restore", "cure", "treat", "回復", "治療", "癒", "応急"))


def _skill_default_uses_defense(skill: dict[str, Any]) -> bool:
    text = " ".join(str(skill.get(key) or "") for key in ("skill_type", "element", "category", "description", "effect")).lower()
    if any(word in text for word in ("magic", "spell", "arcane", "mental", "poison", "light", "dark", "fire", "water", "ice", "lightning")):
        return False
    if any(word in text for word in ("support", "heal", "healing", "recover", "回復", "治療", "補助")):
        return False
    return True


def _skill_default_ability(skill: dict[str, Any], *, healing: bool) -> str:
    text = " ".join(str(skill.get(key) or "") for key in ("skill_type", "element", "category", "description", "effect")).lower()
    if healing:
        return "wis"
    if any(word in text for word in ("physical", "weapon", "slash", "strike", "none", "物理")):
        return "str"
    if any(word in text for word in ("support", "mental", "spirit", "精神")):
        return "wis"
    if any(word in text for word in ("magic", "spell", "arcane", "fire", "water", "ice", "lightning", "earth", "wind", "light", "dark", "魔法", "魔力")):
        return "magic"
    if any(word in text for word in ("poison", "grass", "tool", "道具", "毒", "草")):
        return "dex"
    return "str"


def _combat_damage_message(damage: int, max_hp: int, *, action_name: str) -> str:
    hp = max(1, int(max_hp or 1))
    ratio = max(0.0, damage / hp)
    if damage <= 0:
        return f"{action_name}は通らず、相手に有効な傷を与えられなかった。"
    if damage <= 2 or ratio <= 0.05:
        return f"勢いよく{action_name}したが、かすり傷しか与えられなかった。"
    if ratio <= 0.15:
        return f"{action_name}が浅く入り、相手に小さな傷を負わせた。"
    if ratio <= 0.35:
        return f"{action_name}がしっかり命中し、確かなダメージを与えた。"
    if ratio <= 0.60:
        return f"重い{action_name}が入り、相手の体勢を大きく崩した。"
    return f"{action_name}が急所を捉え、致命的な傷を与えた。"


def _combat_heal_message(amount: int, skill_name: str) -> str:
    if amount <= 0:
        return f"> [戦闘] {skill_name}を使ったが、HPは回復しなかった。"
    if amount <= 5:
        return f"> [戦闘] {skill_name}で少し体勢を立て直した。"
    if amount <= 20:
        return f"> [戦闘] {skill_name}が傷を癒やし、HPを回復した。"
    return f"> [戦闘] {skill_name}が大きく傷を癒やし、HPを大幅に回復した。"


def _combat_narration_payload(combat_result: dict[str, Any]) -> dict[str, Any]:
    old_hp = _first_int(combat_result, ("old_hp", "player_old_hp"), 0)
    new_hp = _first_int(combat_result, ("new_hp", "player_new_hp"), old_hp)
    max_hp = max(1, _first_int(combat_result, ("max_hp", "player_max_hp"), max(old_hp, new_hp, 1)))
    damage = _first_int(combat_result, ("damage",), max(0, old_hp - new_hp))
    actual_damage = max(0, old_hp - new_hp)
    healing = _first_int(combat_result, ("actual_healing", "healing"), max(0, new_hp - old_hp))
    payload = {
        "type": combat_result.get("type"),
        "damage": damage,
        "actual_damage": actual_damage,
        "healing": healing,
        "old_hp": old_hp,
        "new_hp": new_hp,
        "max_hp": max_hp,
        "lethal": new_hp <= 0 and damage > 0,
        "weakness_multiplier": combat_result.get("weakness_multiplier"),
        "base_damage": combat_result.get("base_damage"),
        "attack": combat_result.get("attack"),
        "defense": combat_result.get("defense"),
        "ability": combat_result.get("ability"),
        "ability_score": combat_result.get("ability_score"),
        "power": combat_result.get("power"),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _first_int(data: dict[str, Any], keys: tuple[str, ...], default: int = 0) -> int:
    for key in keys:
        if key in data:
            return _safe_int(data.get(key), default)
    return default


def _npc_response_is_offensive(*responses: Any) -> bool:
    texts: list[str] = []
    explicit: bool | None = None
    for response in responses:
        if not isinstance(response, dict):
            continue
        for candidate in _combat_response_candidates(response):
            for key in ("offensive", "attack", "attacks", "damage_intent", "hostile_action"):
                if key in candidate and candidate.get(key) not in (None, ""):
                    explicit = _as_bool(candidate.get(key))
        for key in ("npc_action", "action", "intent", "narration", "text", "message"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=400)
            texts.append(str(value or ""))
    if explicit is not None:
        return explicit
    joined = " ".join(texts).lower()
    if not joined.strip():
        return False
    if any(word in joined for word in ("降伏", "逃走", "退却", "交渉", "防御", "様子", "hesitate", "surrender", "flee", "defend", "negotiate")):
        return False
    return any(
        word in joined
        for word in (
            "攻撃",
            "襲",
            "斬",
            "刺",
            "殴",
            "噛",
            "爪",
            "撃つ",
            "矢",
            "魔法を放",
            "ダメージ",
            "attack",
            "strike",
            "slash",
            "stab",
            "bite",
            "claw",
            "shoot",
            "cast",
            "damage",
        )
    )


def _surrender_control_prevents_npc_damage(encounter: dict[str, Any], *responses: Any) -> bool:
    if not _encounter_player_surrendered(encounter):
        return False
    joined = _combat_action_text(*responses).lower()
    if not joined.strip():
        return False
    control_terms = (
        "accept_surrender",
        "surrender_accepted",
        "approach_and_entangle",
        "entangle",
        "restrain",
        "restrained",
        "capture",
        "bind",
        "grapple",
        "disarm",
        "watch",
        "guard",
        "拘束",
        "絡め",
        "絡み",
        "包み込",
        "包囲",
        "捕獲",
        "確保",
        "監視",
        "見張",
        "武装解除",
        "降伏を受け入",
        "屈服",
        "身を委ね",
        "警戒",
    )
    if not any(term in joined for term in control_terms):
        return False
    damaging_terms = (
        "damage",
        "hp",
        "kill",
        "strike",
        "slash",
        "stab",
        "bite",
        "claw",
        "shoot",
        "cast",
        "ダメージ",
        "殺",
        "致命",
        "襲",
        "斬",
        "刺",
        "殴",
        "噛",
        "爪",
        "裂",
        "貫",
        "焼",
        "燃",
        "締め付け",
        "締め上げ",
    )
    return not any(term in joined for term in damaging_terms)


def _encounter_player_surrendered(encounter: dict[str, Any]) -> bool:
    if _as_bool(encounter.get("player_surrendered")):
        return True
    status_text = " ".join(
        str(encounter.get(key) or "")
        for key in ("player_status", "intent", "last_player_intent")
    ).lower()
    return any(term in status_text for term in ("surrender", "surrendering", "surrender_accepted", "降伏", "屈服"))


def _combat_action_text(*responses: Any) -> str:
    parts: list[str] = []
    for response in responses:
        if not isinstance(response, dict):
            continue
        for key in ("npc_action", "action", "intent", "narration", "text", "message"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=400)
            if value:
                parts.append(str(value))
        update = response.get("encounter_update")
        if isinstance(update, (dict, list)):
                parts.append(json.dumps(_compact_value(update, max_chars=500), ensure_ascii=False))
    return " ".join(parts)


def _npc_action_tool_kind(*responses: Any) -> str:
    surrender_values = {"surrender", "yield", "give_up", "giveup", "降伏", "降伏する", "降参", "降参する"}
    flee_values = {"flee", "escape", "run_away", "runaway", "retreat", "withdraw", "逃亡", "逃走", "逃げる", "退却", "離脱"}
    for response in responses:
        if not isinstance(response, dict):
            continue
        if _as_bool(response.get("npc_surrender") or response.get("surrender")):
            return "surrender"
        if _as_bool(response.get("npc_flee") or response.get("flee")):
            return "flee"
        values: list[str] = []
        for key in ("npc_action", "npc_tool", "tool", "intent"):
            value = response.get(key)
            if isinstance(value, (dict, list)):
                value = _compact_value(value, max_chars=120)
            value_text = str(value or "").strip()
            if value_text:
                values.append(value_text)
        update = response.get("encounter_update")
        if isinstance(update, dict):
            for key in ("opponent_status", "npc_action", "npc_tool", "intent"):
                value_text = str(update.get(key) or "").strip()
                if value_text:
                    values.append(value_text)
        for value in values:
            normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized in surrender_values or value.strip() in surrender_values:
                return "surrender"
            if normalized in flee_values or value.strip() in flee_values:
                return "flee"
    return ""


def _skill_sp_cost(skill: dict[str, Any]) -> int:
    skill_type = str(skill.get("skill_type") or skill.get("type") or skill.get("category") or "").lower()
    text = json.dumps(skill, ensure_ascii=False).lower()
    if "passive" in skill_type or "常時" in text:
        return 0
    power = _entry_power(skill, fallback=_skill_power_from_text(skill))
    power_floor = _skill_sp_floor(power)
    explicit = (
        skill.get("sp_cost")
        or skill.get("cost_sp")
        or skill.get("sp")
        or skill.get("mp_cost")
        or skill.get("mana_cost")
    )
    if explicit not in (None, ""):
        return max(0, min(99, max(_safe_int(explicit, 0), power_floor)))
    cost = 5
    if any(word in skill_type for word in ("magic", "spell", "arcane", "support")):
        cost += 2
    if any(word in skill_type for word in ("ultimate", "special", "burst", "奥義", "必殺")):
        cost += 8
    effect_count = len(skill.get("effects")) if isinstance(skill.get("effects"), list) else 0
    cost += min(6, effect_count * 2)
    numeric_values = [abs(_safe_int(match.group(0), 0)) for match in re.finditer(r"\d+", text)]
    if numeric_values:
        cost += min(8, max(numeric_values) // 2)
    if any(word in text for word in ("high", "very", "powerful", "great", "major", "large", "area", "aoe", "all", "revive", "death", "instant", "強力", "大", "全体", "蘇生", "即死")):
        cost += 5
    if any(word in text for word in ("low", "minor", "small", "weak", "軽", "小")):
        cost -= 2
    return max(1, min(30, max(cost, power_floor)))


def _entry_power(value: Any, fallback: int = 1) -> int:
    if isinstance(value, dict):
        for key in ("power", "strength_level", "strength", "power_level", "severity", "level", "rank"):
            if value.get(key) not in (None, ""):
                return _entry_power(value.get(key), fallback=fallback)
        return max(SKILL_TRAIT_POWER_MIN, min(SKILL_TRAIT_POWER_MAX, int(fallback or 1)))
    text = str(value or "").strip().lower()
    if not text:
        return max(SKILL_TRAIT_POWER_MIN, min(SKILL_TRAIT_POWER_MAX, int(fallback or 1)))
    number = _safe_int(text, 0)
    if number:
        return max(SKILL_TRAIT_POWER_MIN, min(SKILL_TRAIT_POWER_MAX, number))
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
    return max(SKILL_TRAIT_POWER_MIN, min(SKILL_TRAIT_POWER_MAX, int(fallback or 1)))


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


def _is_player_power_actor(actor: CharacterData) -> bool:
    if not isinstance(actor, CharacterData):
        return False
    category = str(actor.category or "").lower()
    role = str(actor.role or "").lower()
    source = str(actor.flags.get("source") or actor.extra.get("source") or "").lower()
    return bool(actor.flags.get("is_player") or role == "player" or category == "player" or source.startswith("character_setup"))


def _actor_power_budget(actor: CharacterData) -> int:
    if _is_player_power_actor(actor):
        return PLAYER_UNLIMITED_POWER_BUDGET
    for source in (getattr(actor, "extra", {}), getattr(actor, "flags", {})):
        if not isinstance(source, dict):
            continue
        for key in ("skill_trait_power_budget", "power_budget", "ability_power_budget"):
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
    actor: CharacterData,
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


def _normalise_actor_power_loadout(actor: CharacterData) -> None:
    traits = [_normalise_trait(item) for item in _as_list(getattr(actor, "traits", []))]
    traits = [trait for trait in traits if trait.get("name")]
    traits = _limit_power_entries_for_actor(actor, traits, used_power=0)
    actor.traits = traits
    skills = [_normalise_skill(item) for item in _as_list(getattr(actor, "skills", []))]
    skills = [skill for skill in skills if skill.get("name")]
    actor.skills = _limit_power_entries_for_actor(actor, skills, used_power=_entry_power_total(traits))


def _skill_trait_power_instruction(character: CharacterData) -> str:
    scale = (
        "強力度の目安: 1=あまり強力ではない、"
        "3=使い方次第で強力、"
        "5=これ1つで戦況をひっくり返せる可能性がある。"
    )
    if _is_player_power_actor(character):
        return (
            f"{scale} スキルや体質はBPを消費しません。"
            "プレイヤーが自由に作れる要素なので、各項目に power と strength_level を1〜5で付けてください。"
        )
    budget = _actor_power_budget(character)
    used = _entry_power_total(character.traits) + _entry_power_total(character.skills)
    remaining = max(0, budget - used)
    return (
        f"{scale} このNPC/敵のスキルと体質の強力度合計上限は {budget} です。"
        f"既存分は {used}、追加可能な残りは {remaining} です。"
        "序盤や一般人は低く、終盤・精鋭・ボス級ほど高くしてください。"
    )


def _safe_asset_segment(value: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in str(value).strip())
    return cleaned or "unknown"


def _character_runtime_attributes(character: CharacterData) -> dict[str, int]:
    attrs: dict[str, Any] = {}
    if isinstance(character.attributes, dict):
        attrs.update(character.attributes)
    if isinstance(character.extra, dict):
        direct = character.extra.get("attributes")
        if isinstance(direct, dict):
            attrs.update(direct)
        ability = character.extra.get("ability")
        if isinstance(ability, dict) and isinstance(ability.get("attributes"), dict):
            attrs.update(ability["attributes"])
    resolved = {
        key: max(1, _safe_int(attrs.get(key), default))
        for key, default in CHARACTER_DEFAULT_ATTRIBUTES.items()
    }
    resolved["magic"] = max(1, _safe_int(attrs.get("magic", attrs.get("mag", resolved["int"])), resolved["int"]))
    resolved["will"] = max(1, _safe_int(attrs.get("will", resolved["wis"]), resolved["wis"]))
    return resolved


def _character_calculated_max_hp(character: CharacterData) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    return max(10, 8 + level * 3 + attrs["con"] * 2 + attrs["str"] // 2 + attrs["will"] // 3)


def _character_calculated_max_sp(character: CharacterData, *, max_hp: int | None = None) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    resolved_max_hp = max_hp if max_hp is not None else _character_calculated_max_hp(character)
    return max(6, int(resolved_max_hp * 0.45) + attrs["magic"] + attrs["will"] + level * 2)


def _character_calculated_attack(character: CharacterData) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    return max(1, level + attrs["str"] // 3 + attrs["dex"] // 5)


def _character_calculated_defense(character: CharacterData) -> int:
    attrs = _character_runtime_attributes(character)
    level = max(1, _safe_int(character.level, 1))
    return max(0, level // 2 + attrs["con"] // 4 + attrs["wis"] // 6)


def _danger_scaled_level_floor(danger: Any, *, boss: bool = False) -> int:
    resolved = _clamp_world_danger(danger)
    base = 1 + int(round(resolved * 0.72))
    if boss:
        base += 8
    return max(1, min(NPC_MAX_LEVEL, base))


def _danger_scaled_attribute_floor(danger: Any, *, boss: bool = False) -> int:
    resolved = _clamp_world_danger(danger)
    base = 10 + resolved // 5
    if boss:
        base += 5
    return max(1, base)


def _scale_character_for_danger(character: CharacterData, danger: Any, *, boss: bool = False) -> None:
    if not isinstance(character, CharacterData) or character.flags.get("is_player"):
        return
    resolved_danger = _clamp_world_danger(danger)
    boss = bool(
        boss
        or character.flags.get("generated_dungeon_boss")
        or character.extra.get("generated_dungeon_boss")
        or str(character.role or "").casefold() in {"boss", "ボス", "ダンジョンボス"}
        or "boss" in str(character.category or "").casefold()
    )
    level_floor = _danger_scaled_level_floor(resolved_danger, boss=boss)
    if _safe_int(character.level, 1) < level_floor:
        character.level = level_floor

    attrs = _character_runtime_attributes(character)
    floor = _danger_scaled_attribute_floor(resolved_danger, boss=boss)
    for key in CHARACTER_DEFAULT_ATTRIBUTES:
        attrs[key] = max(_safe_int(attrs.get(key), CHARACTER_DEFAULT_ATTRIBUTES[key]), floor)
    attrs["con"] = max(attrs["con"], floor + (2 if boss else 0))
    attrs["str"] = max(attrs["str"], floor + (1 if boss else 0))
    attrs["wis"] = max(attrs["wis"], floor)
    attrs["magic"] = max(_safe_int(attrs.get("magic"), attrs["int"]), attrs["int"])
    attrs["will"] = max(_safe_int(attrs.get("will"), attrs["wis"]), attrs["wis"])
    character.attributes = attrs
    character.extra["attributes"] = dict(attrs)
    ability = character.extra.setdefault("ability", {})
    if isinstance(ability, dict):
        ability["attributes"] = dict(attrs)
    character.flags["danger_level"] = resolved_danger
    character.extra["danger_level"] = resolved_danger

    old_max_hp = max(0, _safe_int(character.max_hp, 0))
    old_current_hp = max(0, _safe_int(character.current_hp, 0))
    calculated_hp = _character_calculated_max_hp(character)
    if old_max_hp <= 0 or old_max_hp < calculated_hp:
        character.max_hp = calculated_hp
        if old_current_hp <= 0 or old_current_hp >= old_max_hp:
            character.current_hp = calculated_hp
        else:
            character.current_hp = min(calculated_hp, old_current_hp)
    calculated_sp = _character_calculated_max_sp(character, max_hp=character.max_hp)
    if _safe_int(character.max_sp, 0) < calculated_sp:
        character.max_sp = calculated_sp
        if _safe_int(character.current_sp, 0) <= 0:
            character.current_sp = calculated_sp
    character.attack = max(_safe_int(character.attack, 0), _character_calculated_attack(character))
    character.defense = max(_safe_int(character.defense, 0), _character_calculated_defense(character))


def _danger_scaled_placeholder_enemy(name: str, danger: Any) -> CharacterData:
    character = CharacterData(name=str(name or "Enemy"), role="敵対者", category="enemy_npc")
    _scale_character_for_danger(character, danger)
    return character


def _character_state_is_dead(character: CharacterData) -> bool:
    state = str(character.state or character.flags.get("state") or "").strip().lower()
    if state in {"dead", "corpse", "killed"}:
        return True
    if character.flags.get("dead") is True or character.flags.get("alive") is False:
        return True
    return False


def _world_location_target_count(value: Any) -> int:
    requested = _safe_int(value, DEFAULT_WORLD_LOCATION_COUNT)
    candidates = sorted(WORLD_LOCATION_COUNT_OPTIONS.values())
    return min(candidates, key=lambda item: abs(item - requested))


def _world_customization_settings(crime_risk: Any, enemy_strength: Any) -> dict[str, str]:
    crime = str(crime_risk or DEFAULT_WORLD_CRIME_RISK).strip().lower().replace("-", "_").replace(" ", "_")
    strength = str(enemy_strength or DEFAULT_WORLD_ENEMY_STRENGTH).strip().lower().replace("-", "_").replace(" ", "_")
    if crime not in WORLD_CRIME_RISK_OPTIONS:
        crime = DEFAULT_WORLD_CRIME_RISK
    if strength not in WORLD_ENEMY_STRENGTH_OPTIONS:
        strength = DEFAULT_WORLD_ENEMY_STRENGTH
    return {
        "crime_risk": crime,
        "enemy_strength": strength,
    }


def _world_overview_max_tokens(target_count: Any) -> int:
    count = _world_location_target_count(target_count)
    return max(1400, min(2600, 1000 + count * 12))


def _world_location_batch_size(remaining: int) -> int:
    if remaining <= 0:
        return 0
    if remaining < WORLD_LOCATION_BATCH_MIN:
        return remaining
    return min(WORLD_LOCATION_BATCH_MAX, remaining)


def _world_location_batch_max_tokens(batch_size: int) -> int:
    return max(700, min(1500, 450 + max(1, int(batch_size)) * 180))


def _world_location_name_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _quest_destination_hint(quest: QuestData, response: dict[str, Any] | None = None) -> dict[str, Any]:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    destination_raw = extra.get("destination") if isinstance(extra.get("destination"), dict) else {}
    hint_raw = extra.get("destination_hint") if isinstance(extra.get("destination_hint"), dict) else {}
    text = _quest_destination_source_text(quest, response)
    location_name = str(
        response.get("destination_location")
        or response.get("target_location")
        or hint_raw.get("location")
        or hint_raw.get("destination_location")
        or destination_raw.get("location")
        or extra.get("destination_location")
        or extra.get("target_location")
        or ""
    ).strip()
    kind = str(
        response.get("destination_kind")
        or response.get("location_kind")
        or hint_raw.get("kind")
        or hint_raw.get("location_kind")
        or destination_raw.get("location_kind")
        or ""
    ).strip().lower()
    if not kind:
        kind = _quest_location_kind_from_text(text)
    anchor_kind = str(hint_raw.get("anchor_kind") or "").strip().lower()
    if not anchor_kind:
        anchor_kind = _quest_anchor_kind_from_text(text, kind)
    objective_name = str(
        response.get("objective_subnode_name")
        or response.get("objective_name")
        or hint_raw.get("objective_subnode_name")
        or hint_raw.get("objective_name")
        or destination_raw.get("objective_subnode_name")
        or ""
    ).strip()
    objective_description = str(
        response.get("objective_subnode_description")
        or response.get("objective_description")
        or hint_raw.get("objective_subnode_description")
        or hint_raw.get("objective_description")
        or destination_raw.get("objective_subnode_description")
        or quest.overview
        or ""
    ).strip()
    return {
        "source_text": text,
        "location": location_name,
        "location_kind": kind,
        "anchor_kind": anchor_kind,
        "anchor_location": str(hint_raw.get("anchor_location") or destination_raw.get("anchor_location") or "").strip(),
        "description": str(hint_raw.get("description") or destination_raw.get("description") or "").strip(),
        "objective_subnode_id": str(destination_raw.get("objective_subnode_id") or "").strip(),
        "objective_subnode_name": objective_name or _quest_objective_name_from_text(text),
        "objective_subnode_description": objective_description,
    }


def _quest_destination_source_text(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    parts: list[str] = [
        quest.name,
        quest.overview,
        quest.neighboring_settlement,
        json.dumps(quest.choices, ensure_ascii=False, default=str),
        json.dumps(extra, ensure_ascii=False, default=str),
    ]
    if response:
        parts.append(json.dumps(_strip_response_metadata(response), ensure_ascii=False, default=str))
    return "\n".join(part for part in parts if str(part or "").strip())


def _quest_location_kind_from_text(text: str) -> str:
    lowered = str(text or "").casefold()
    if any(word in lowered for word in ("dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair", "洞窟", "迷宮", "遺跡", "鉱山", "巣穴", "巣")):
        return "dungeon"
    if any(word in lowered for word in ("forest", "woods", "swamp", "wild", "森", "樹海", "沼", "荒野")):
        return "wilderness"
    if any(word in lowered for word in ("coast", "beach", "shore", "seaside", "海岸", "浜辺", "岬")):
        return "coast"
    if any(word in lowered for word in ("mountain", "peak", "ridge", "山", "峠", "尾根")):
        return "mountain"
    if any(word in lowered for word in ("river", "stream", "brook", "川", "河", "沢", "渡し")):
        return "river"
    if any(word in lowered for word in ("plain", "field", "grassland", "meadow", "平原", "草原", "牧野")):
        return "plain"
    if any(word in lowered for word in ("crossroad", "junction", "fork", "分岐路", "分かれ道", "辻")):
        return "crossroad"
    if any(word in lowered for word in ("road", "trail", "route", "街道", "古道", "小道")):
        return "road"
    if any(word in lowered for word in ("rescue", "save", "討伐", "救出", "救助", "行方不明", "連れ去", "魔物", "モンスター")):
        return "wilderness"
    return "wilderness"


def _quest_anchor_kind_from_text(text: str, destination_kind: str) -> str:
    lowered = str(text or "").casefold()
    near_words = ("near", "nearby", "around", "近く", "周辺", "付近", "そば")
    if not any(word in lowered for word in near_words):
        return ""
    if any(word in lowered for word in ("road", "trail", "route", "街道", "古道", "小道")) and destination_kind != "road":
        return "road"
    if any(word in lowered for word in ("crossroad", "junction", "分岐路", "分かれ道", "辻")) and destination_kind != "crossroad":
        return "crossroad"
    if any(word in lowered for word in ("river", "stream", "川", "河", "沢")) and destination_kind != "river":
        return "river"
    return ""


def _quest_location_kind_label(kind: str) -> str:
    return {
        "dungeon": "ダンジョン",
        "wilderness": "森",
        "road": "街道",
        "crossroad": "分岐路",
        "coast": "海岸",
        "mountain": "山",
        "river": "川辺",
        "plain": "平原",
        "landmark": "目標地点",
    }.get(str(kind or "").strip().lower(), "探索地")


def _quest_destination_name(quest: QuestData, hint: dict[str, Any], origin: str, anchor: str) -> str:
    kind = str(hint.get("location_kind") or "wilderness").strip().lower()
    anchor_kind = str(hint.get("anchor_kind") or "").strip().lower()
    label = _quest_location_kind_label(kind)
    text = str(hint.get("source_text") or "")
    anchor_name = str(anchor or origin or "").strip()
    if kind == "wilderness" and any(word in text for word in ("森", "forest", "woods")):
        label = "森"
    elif kind == "dungeon" and any(word in text for word in ("洞窟", "cave", "cavern")):
        label = "洞窟"
    if anchor_kind == "road" and anchor_name:
        return f"{str(origin or anchor_name).strip()}近郊の街道沿いの{label}"
    if anchor_kind == "crossroad" and anchor_name:
        return f"{str(origin or anchor_name).strip()}近郊の分岐路そばの{label}"
    if anchor_name:
        return f"{anchor_name}近くの{label}"
    return f"{quest.name}の{label}"


def _quest_objective_name_from_text(text: str) -> str:
    lowered = str(text or "").casefold()
    if any(word in lowered for word in ("rescue", "save", "救出", "救助", "娘", "行方不明")):
        return "救出対象のいる地点"
    if any(word in lowered for word in ("defeat", "討伐", "退治", "倒")):
        return "討伐目標のいる地点"
    if any(word in lowered for word in ("collect", "採取", "収集", "回収", "入手")):
        return "回収目標のある地点"
    if any(word in lowered for word in ("investigate", "調査", "確認", "探索")):
        return "調査目標地点"
    return "依頼目標地点"


def _quest_destination_danger(hint: dict[str, Any], kind: str, base_danger: int) -> int:
    text = str(hint.get("source_text") or "").casefold()
    danger = max(1, int(base_danger) + 5)
    if kind in {"dungeon", "wilderness", "mountain"}:
        danger = max(10, danger)
    if any(word in text for word in ("危険", "討伐", "魔物", "モンスター", "monster", "defeat", "rescue", "救出")):
        danger += 5
    return _clamp_world_danger(danger)


def _quest_text_requests_new_site(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(word in lowered for word in ("未知", "新しい", "隠れ", "未踏", "hidden", "unknown", "undiscovered"))


def _map_reveal_value_means_active_quest(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    return text in {
        "active_quest",
        "quest",
        "quest_destination",
        "objective_location",
        "target_location",
        "current_quest",
        "依頼目的地",
        "クエスト目的地",
        "目的地",
    }


def _map_reveal_reason(entry: Any) -> str:
    if isinstance(entry, dict):
        for key in ("reason", "source", "item", "map_name", "description"):
            value = str(entry.get(key) or "").strip()
            if value:
                return _short_text(value, 80)
    if entry is True:
        return "map reveal"
    return _short_text(str(entry or ""), 80)


def _normalise_quest_type_id(value: Any) -> str:
    explicit = str(value or "").strip().lower()
    aliases = {
        "rescue": "rescue",
        "search": "rescue",
        "find_person": "rescue",
        "escort": "rescue",
        "retrieve": "retrieve",
        "collect": "retrieve",
        "gather": "retrieve",
        "lost_item": "retrieve",
        "defeat": "defeat",
        "hunt": "defeat",
        "slay": "defeat",
        "subjugation": "defeat",
        "delivery": "delivery",
        "deliver": "delivery",
        "errand": "delivery",
        "investigate": "investigate",
        "investigation": "investigate",
        "survey": "investigate",
        "inspect": "investigate",
        "procure": "procure",
        "procurement": "procure",
        "supply": "procure",
        "acquire": "procure",
    }
    return aliases.get(explicit, "")


def _quest_type(quest: QuestData, response: dict[str, Any] | None = None) -> str:
    response = response or {}
    extra = quest.extra if isinstance(quest.extra, dict) else {}
    explicit = _normalise_quest_type_id(
        response.get("quest_type")
        or response.get("objective_type")
        or extra.get("quest_type")
        or extra.get("objective_type")
        or extra.get("type")
        or extra.get("kind")
        or ""
    )
    if explicit:
        return explicit
    text = _quest_destination_source_text(quest, response)
    lowered = text.casefold()
    if any(word in lowered for word in ("deliver", "delivery", "errand", "courier")) or any(
        word in text for word in ("\u914d\u9054", "\u5c4a\u3051", "\u304a\u4f7f\u3044", "\u904b\u642c", "\u5c4a\u3051\u7269")
    ):
        return "delivery"
    if any(word in lowered for word in ("defeat", "slay", "hunt", "subjugate", "kill")) or any(
        word in text for word in ("\u8a0e\u4f10", "\u9000\u6cbb", "\u5012", "\u72e9", "\u6226")
    ):
        return "defeat"
    if any(word in lowered for word in ("rescue", "save", "escort", "hostage", "kidnap", "missing person")) or any(
        word in text for word in ("\u6551\u51fa", "\u6551\u52a9", "\u4fdd\u8b77", "\u8b77\u9001", "\u4eba\u8cea", "\u652b", "\u5a18", "\u884c\u65b9\u4e0d\u660e")
    ):
        return "rescue"
    if any(word in lowered for word in ("investigate", "investigation", "survey", "inspect", "research")) or any(
        word in text for word in ("\u8abf\u67fb", "\u8abf\u3079", "\u63a2\u308b", "\u63a2\u7d22", "\u78ba\u8a8d", "\u8e0f\u67fb", "\u5075\u5bdf", "\u6700\u6df1\u90e8")
    ):
        return "investigate"
    if any(word in lowered for word in ("procure", "procurement", "acquire", "obtain", "supply", "bring me")) or any(
        word in text for word in ("\u8abf\u9054", "\u7528\u610f", "\u624b\u306b\u5165\u308c\u3066", "\u5165\u624b\u3057\u3066", "\u8cb7\u3063\u3066", "\u4ed5\u5165\u308c")
    ):
        return "procure"
    return "retrieve"


def _quest_requires_captor(quest: QuestData, response: dict[str, Any] | None = None) -> bool:
    response = response or {}
    explicit = response.get("requires_captor") or response.get("captor_required") or quest.extra.get("requires_captor")
    if explicit not in (None, "", [], {}):
        return _as_bool(explicit)
    return False


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
    text = str(action or "").casefold()
    if any(
        word in str(action or "")
        for word in (
            "\u5831\u544a",
            "\u5b8c\u4e86",
            "\u9054\u6210",
            "\u4f9d\u983c\u4e3b",
            "\u30ae\u30eb\u30c9",
            "\u53d7\u4ed8",
            "\u623b",
            "\u5e30\u9084",
            "\u5831\u916c",
        )
    ):
        return True
    return any(word in text for word in ("report", "complete", "turn in", "return to client", "claim reward", "guild")) or any(
        word in str(action or "")
        for word in ("報告", "完了", "達成", "依頼主", "ギルド", "受付", "戻", "帰還", "報酬")
    )


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
    if not _facility_exists([item for item in facilities if isinstance(item, dict)], original_start):
        record = _facility_record(original_start, settlement.name, _facility_type_from_name(original_start))
        record["description"] = facility_description or str(record.get("description") or "")
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


def _world_location_payloads(value: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in ("locations", "location_nodes", "map_locations", "nodes"):
            payloads.extend(_world_location_payloads(value.get(key)))
        structure = value.get("structure")
        if isinstance(structure, (dict, list)):
            payloads.extend(_world_location_payloads(structure))
        if any(key in value for key in ("name", "title", "location_name", "id")):
            payloads.append(dict(value))
    elif isinstance(value, list):
        for item in value:
            payloads.extend(_world_location_payloads(item))
    elif isinstance(value, str):
        text = value.strip()
        if text:
            payloads.append({"name": text})
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        name = _world_location_name_from_payload(payload)
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(payload)
    return result


def _world_connection_payloads(value: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in ("connections", "edges", "routes", "roads", "links", "paths"):
            payloads.extend(_world_connection_payloads(value.get(key)))
        structure = value.get("structure")
        if isinstance(structure, (dict, list)):
            payloads.extend(_world_connection_payloads(structure))
        if any(key in value for key in ("from", "source", "a")) and any(key in value for key in ("to", "target", "b")):
            payloads.append(dict(value))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                payloads.extend(_world_connection_payloads(item))
    return payloads


def _world_location_name_from_payload(payload: dict[str, Any]) -> str:
    for key in ("name", "title", "location_name", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _world_location_description_from_payload(payload: dict[str, Any]) -> str:
    for key in ("description", "overview", "summary", "detail", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _world_location_danger_from_payload(payload: dict[str, Any]) -> int:
    for key in ("danger", "danger_level", "threat", "threat_level", "difficulty", "rank"):
        if key in payload:
            return _clamp_world_danger(payload.get(key))
    return 0


def _clamp_world_danger(value: Any, default: int = 0) -> int:
    return max(0, min(WORLD_DANGER_MAX, _safe_int(value, default)))


def _world_default_danger_for_index(index: int, target_count: int, rng: random.Random | None = None) -> int:
    if target_count <= 1:
        return 0
    rng = rng or random.Random(f"world-default-danger|{index}|{target_count}")
    progress = max(0.0, min(1.0, float(index) / max(1, target_count - 1)))
    base = int(progress * 38)
    jitter = rng.randint(0, 3)
    return _clamp_world_danger(base + jitter)


def _world_generation_location_danger(
    payload: dict[str, Any],
    name: str,
    description: str,
    premise: str,
    index: int,
    target_count: int,
    rng: random.Random | None = None,
) -> int:
    if _world_location_is_final_endpoint_candidate(premise, payload, name, description):
        seed = f"final-danger|{premise}|{name}|{description}"
        local_rng = random.Random(seed)
        return local_rng.randint(WORLD_FINAL_DANGER_MIN, WORLD_FINAL_DANGER_MAX)
    if any(key in payload for key in ("danger", "danger_level", "threat", "threat_level", "difficulty", "rank")):
        return _world_location_danger_from_payload(payload)
    return _world_default_danger_for_index(index, target_count, rng)


def _looks_like_facility_location_name(value: Any) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return False
    return any(
        word in text
        for word in (
            "inn",
            "guild",
            "shop",
            "store",
            "market",
            "blacksmith",
            "smith",
            "apothecary",
            "tavern",
            "temple",
            "church",
            "clinic",
            "workshop",
            "宿屋",
            "亭",
            "ギルド",
            "店",
            "商店",
            "鍛冶",
            "鍛冶屋",
            "薬屋",
            "薬品店",
            "酒場",
            "市場",
            "神殿",
            "教会",
            "診療所",
            "工房",
        )
    )


def _infer_world_location_kind(payload: dict[str, Any], name: str, description: str = "") -> str:
    for key in ("kind", "type", "category", "location_kind"):
        value = str(payload.get(key) or "").strip().lower()
        if value:
            if value in {"town", "village", "city", "settlement", "hamlet", "base"}:
                return "settlement"
            if value in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair"}:
                return "dungeon"
            if value in {"facility", "shop", "inn", "guild", "temple", "market"}:
                return "facility"
            if value in {"road", "highway", "trail", "path", "route", "街道", "道"}:
                return "road"
            if value in {"crossroad", "crossroads", "fork", "junction", "branch", "分岐路", "分かれ道", "辻"}:
                return "crossroad"
            if value in {"coast", "beach", "shore", "seaside", "海岸", "浜辺", "岬"}:
                return "coast"
            if value in {"mountain", "mountains", "peak", "ridge", "山", "山岳", "峠"}:
                return "mountain"
            if value in {"river", "stream", "brook", "ford", "川", "河", "沢", "渡し"}:
                return "river"
            if value in {"plain", "plains", "field", "grassland", "meadow", "平原", "草原", "野"}:
                return "plain"
            return value
    text = f"{name}\n{description}".lower()
    if _looks_like_facility_location_name(name):
        return "facility"
    if any(word in text for word in ("dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair", "洞窟", "迷宮", "遺跡", "鉱山")):
        return "dungeon"
    if any(word in text for word in ("crossroad", "crossroads", "junction", "fork", "分岐路", "分かれ道", "辻")):
        return "crossroad"
    if any(word in text for word in ("road", "highway", "trail", "route", "街道", "古道", "小道")):
        return "road"
    if any(word in text for word in ("coast", "beach", "shore", "seaside", "海岸", "浜辺", "岬", "河口")):
        return "coast"
    if any(word in text for word in ("mountain", "mountains", "peak", "ridge", "山", "山岳", "峠", "尾根")):
        return "mountain"
    if any(word in text for word in ("river", "stream", "brook", "ford", "川", "河", "沢", "渡し")):
        return "river"
    if any(word in text for word in ("plain", "plains", "field", "grassland", "meadow", "平原", "草原", "牧野")):
        return "plain"
    if any(word in text for word in ("town", "village", "city", "settlement", "村", "街", "町", "都市", "宿場")):
        return "settlement"
    if any(word in text for word in ("forest", "swamp", "wilderness", "森", "沼", "荒野")):
        return "wilderness"
    return "landmark"


def _infer_world_location_kind_for_request(
    action: str,
    payload: dict[str, Any],
    name: str,
    description: str = "",
) -> str:
    kind = _infer_world_location_kind(payload, name, description)
    if _explicit_dungeon_location_request(action, payload, name, description):
        return "dungeon"
    return kind


def _infer_world_location_kind_for_world_generation(
    premise: str,
    payload: dict[str, Any],
    name: str,
    description: str = "",
) -> str:
    kind = _infer_world_location_kind(payload, name, description)
    if _explicit_dungeon_location_request("", payload, name, description):
        return "dungeon"
    if _world_generation_named_location_requested_as_dungeon(premise, payload, name, description):
        return "dungeon"
    return kind


def _explicit_dungeon_location_request(action: str, payload: dict[str, Any], name: str, description: str = "") -> bool:
    explicit = str(
        payload.get("kind")
        or payload.get("type")
        or payload.get("category")
        or payload.get("location_kind")
        or ""
    ).strip().casefold()
    if explicit in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair"}:
        return True
    text = "\n".join(
        str(part or "")
        for part in (
            action,
            name,
            description,
            payload.get("description"),
            payload.get("overview"),
            payload.get("summary"),
            payload.get("objective"),
        )
    ).casefold()
    if not text:
        return False
    dungeon_words = (
        "dungeon",
        "labyrinth",
        "crypt",
        "lair",
        "ダンジョン",
        "迷宮",
        "地下迷宮",
        "洞窟",
        "洞穴",
        "遺跡",
    )
    temple_words = ("temple", "shrine", "神殿", "祠", "聖域")
    if any(word in text for word in dungeon_words):
        return True
    if any(word in text for word in temple_words) and _generated_dungeon_boss_text_implies_boss(text):
        return True
    return False


def _world_location_is_final_endpoint_candidate(
    premise: str,
    payload: dict[str, Any],
    name: str,
    description: str = "",
) -> bool:
    local_text = "\n".join(
        str(part or "")
        for part in (
            name,
            description,
            payload.get("role"),
            payload.get("purpose"),
            payload.get("summary"),
            payload.get("objective"),
            payload.get("boss_npc"),
            payload.get("boss"),
        )
    ).casefold()
    if not local_text:
        return False
    premise_text = str(premise or "").casefold()
    text = f"{local_text}\n{premise_text if _world_generation_premise_refers_to_location(premise, name) else ''}"
    final_markers = (
        "final",
        "last",
        "endgame",
        "final boss",
        "journey's end",
        "旅の最終",
        "最終地点",
        "終着",
        "終盤",
        "ラスボス",
        "最終神殿",
        "最奥の神殿",
        "最後の",
        "終焉",
    )
    if any(marker in text for marker in final_markers):
        return True
    place_markers = ("神殿", "temple", "shrine", "聖域", "迷宮", "dungeon", "lair")
    return any(marker in text for marker in place_markers) and _generated_dungeon_boss_text_implies_boss(text)


def _world_generation_named_location_requested_as_dungeon(
    premise: str,
    payload: dict[str, Any],
    name: str,
    description: str = "",
) -> bool:
    if not _world_generation_premise_refers_to_location(premise, name):
        return False
    return _explicit_dungeon_location_request(premise, payload, name, description)


def _world_generation_premise_refers_to_location(premise: str, name: str) -> bool:
    premise_key = _world_location_name_key(premise)
    name_key = _world_location_name_key(name)
    return bool(name_key and len(name_key) >= 3 and name_key in premise_key)


def _world_generation_dungeon_has_boss(world: WorldData, location_name: str) -> bool:
    for character in world.characters.values():
        if character.location != location_name:
            continue
        if _character_state_is_dead(character):
            continue
        if character.flags.get("generated_dungeon_boss") or character.extra.get("generated_dungeon_boss"):
            return True
        text = " ".join(str(value or "") for value in (character.role, character.category, character.extra.get("display_alias"))).casefold()
        if any(marker in text for marker in ("boss", "ボス", "守護者", "主")):
            return True
    return False


def _explicit_generated_dungeon_location_request(
    action: str,
    response: dict[str, Any],
    name: str,
    description: str = "",
) -> bool:
    if not _explicit_dungeon_location_request(action, response, name, description):
        return False
    if response.get("discovered_location") or _generated_dungeon_boss_payload(response):
        return True
    text = "\n".join(
        str(part or "")
        for part in (
            action,
            response.get("narration"),
            response.get("text"),
            response.get("message"),
            description,
        )
    ).casefold()
    return any(
        marker in text
        for marker in (
            "create",
            "generate",
            "discover",
            "spawn",
            "生成",
            "発見",
            "出現",
            "現れ",
            "生や",
        )
    )


def _generated_dungeon_boss_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        for key in ("boss_npc", "boss", "boss_enemy", "final_boss", "guardian", "ruler", "keeper"):
            raw = value.get(key)
            payload = _generated_dungeon_boss_payload(raw)
            if payload:
                return payload
        discovered = value.get("discovered_location")
        if isinstance(discovered, dict):
            payload = _generated_dungeon_boss_payload(discovered)
            if payload:
                return payload
        for key in ("enemies", "opponents", "enemy_npcs", "npcs", "characters"):
            for item in _as_list(value.get(key)):
                if not isinstance(item, dict):
                    continue
                text = json.dumps(item, ensure_ascii=False).casefold()
                if any(marker in text for marker in ("boss", "final", "guardian", "ボス", "守護者", "主", "女神")):
                    return dict(item)
        return {}
    if isinstance(value, list):
        for item in value:
            payload = _generated_dungeon_boss_payload(item)
            if payload:
                return payload
    if isinstance(value, str) and value.strip():
        return {"name": value.strip(), "description": value.strip(), "hostile": True}
    return {}


def _generated_dungeon_boss_required(action: str, response: dict[str, Any], location: LocationData) -> bool:
    if _generated_dungeon_boss_payload(response):
        return True
    for key in ("has_boss", "boss_required", "requires_boss", "place_boss", "spawn_boss"):
        if key in response and _as_bool(response.get(key)):
            return True
    discovered = response.get("discovered_location")
    if isinstance(discovered, dict):
        for key in ("has_boss", "boss_required", "requires_boss", "place_boss", "spawn_boss"):
            if key in discovered and _as_bool(discovered.get(key)):
                return True
    text = "\n".join(
        str(part or "")
        for part in (
            action,
            location.name,
            location.description,
            response.get("narration"),
            response.get("objective"),
            response.get("event"),
            response.get("discovered_location"),
        )
    ).casefold()
    if any(marker in text for marker in ("no boss", "ボスはいない", "ボスなし", "守護者はいない")):
        return False
    return _generated_dungeon_boss_text_implies_boss(text)


def _generated_dungeon_boss_text_implies_boss(text: str) -> bool:
    text = str(text or "").casefold()
    if not text:
        return False
    direct_markers = (
        "boss",
        "final boss",
        "guardian",
        "overlord",
        "demon lord",
        "ボス",
        "ラスボス",
        "守護者",
        "支配者",
        "魔王",
        "主が",
        "主は",
    )
    if any(marker in text for marker in direct_markers):
        return True
    waiting_markers = ("待つ", "待って", "待ち受け", "鎮座", "await", "waiting", "waits")
    entity_markers = ("女神", "神", "神格", "邪神", "主", "王", "deity", "goddess", "god", "lord")
    return any(marker in text for marker in waiting_markers) and any(marker in text for marker in entity_markers)


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


def _world_kind_is_settlement(kind: str) -> bool:
    return str(kind or "").strip().lower() in {"settlement", "town", "village", "city", "hamlet", "base"}


def _world_location_allows_world_map_departure(world: WorldData, name: str) -> bool:
    location = world.locations.get(str(name or "").strip())
    if location is None:
        return False
    if _world_location_is_world_map_exit(location):
        return True
    return not _world_location_blocks_world_map_departure(location)


def _dungeon_subnode_target_count(location: LocationData) -> int:
    extra = location.extra if isinstance(location.extra, dict) else {}
    for key in ("subnode_count", "dungeon_subnode_count", "room_count", "dungeon_room_count", "scale_count"):
        if extra.get(key) not in (None, ""):
            return max(DUNGEON_SUBNODE_MIN_COUNT, min(DUNGEON_SUBNODE_MAX_COUNT, _safe_int(extra.get(key), DUNGEON_SUBNODE_MIN_COUNT)))
    scale = _dungeon_scale_label(location)
    scale_counts = {
        "tiny": 5,
        "small": 7,
        "normal": 10,
        "medium": 11,
        "large": 15,
        "huge": 20,
        "labyrinth": 18,
    }
    if scale in scale_counts:
        return scale_counts[scale]
    danger = _safe_int(extra.get("danger_level", extra.get("danger")), 0)
    text = "\n".join(str(value or "") for value in (location.name, location.description, extra.get("location_kind"), extra.get("scale"), extra.get("size"))).casefold()
    danger_step = danger if danger <= 9 else danger // 5
    base = 6 + max(0, min(9, danger_step))
    if any(word in text for word in ("labyrinth", "maze", "迷宮", "迷路", "巨大", "広大", "大規模")):
        base += 5
    elif any(word in text for word in ("ruin", "mine", "遺跡", "鉱山", "廃坑")):
        base += 2
    elif any(word in text for word in ("small", "shallow", "小さ", "浅い")):
        base -= 2
    rng = random.Random(f"dungeon-subnode-count|{location.name}|{location.description}|{danger}")
    base += rng.randint(0, 2)
    return max(DUNGEON_SUBNODE_MIN_COUNT, min(DUNGEON_SUBNODE_MAX_COUNT, base))


def _dungeon_scale_label(location: LocationData) -> str:
    extra = location.extra if isinstance(location.extra, dict) else {}
    raw = str(extra.get("scale") or extra.get("size") or extra.get("dungeon_scale") or extra.get("rank") or "").strip().casefold()
    if raw:
        if any(word in raw for word in ("tiny", "very small", "miniscule", "極小")):
            return "tiny"
        if any(word in raw for word in ("small", "minor", "小", "浅")):
            return "small"
        if any(word in raw for word in ("large", "big", "major", "大", "広")):
            return "large"
        if any(word in raw for word in ("huge", "vast", "giant", "massive", "巨大", "広大")):
            return "huge"
        if any(word in raw for word in ("labyrinth", "maze", "迷宮", "迷路")):
            return "labyrinth"
        if any(word in raw for word in ("normal", "medium", "standard", "普通", "中")):
            return "normal"
    text = f"{location.name}\n{location.description}".casefold()
    if any(word in text for word in ("labyrinth", "maze", "迷宮", "迷路")):
        return "labyrinth"
    if any(word in text for word in ("huge", "vast", "massive", "巨大", "広大")):
        return "huge"
    if any(word in text for word in ("large", "big", "大き", "広い")):
        return "large"
    if any(word in text for word in ("small", "shallow", "小さ", "浅い")):
        return "small"
    return ""


def _protected_dungeon_subnodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
    protected: dict[str, dict[str, Any]] = {}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        node_id_text = str(node_id)
        kind = str(node.get("kind") or "").strip()
        if node_id_text.startswith("quest:") or kind == "quest_objective" or bool(node.get("quest_objective")):
            protected[node_id_text] = dict(node)
    return protected


def _fallback_dungeon_subnode_layout(location: LocationData, target_count: int) -> dict[str, Any]:
    target_count = max(DUNGEON_SUBNODE_MIN_COUNT, min(DUNGEON_SUBNODE_MAX_COUNT, int(target_count or DUNGEON_SUBNODE_MIN_COUNT)))
    rng = random.Random(f"dungeon-subnodes|{location.name}|{location.description}|{target_count}")
    catalog = list(DUNGEON_SUBNODE_KIND_CATALOG)
    rng.shuffle(catalog)
    interior_count = max(3, target_count - 2)
    main_count = max(3, min(interior_count, interior_count // 2 + 1))
    side_count = max(0, interior_count - main_count)
    x_step = max(120, min(170, 900 // max(4, main_count + 1)))
    nodes: list[dict[str, Any]] = [
        {
            "id": DUNGEON_ENTRY_SUBNODE_ID,
            "name": "入口",
            "kind": "entrance",
            "description": "外と内部をつなぐ出入口。",
            "x": 80,
            "y": 240,
            "world_map_exit": True,
        }
    ]
    main_ids: list[str] = []
    for index in range(main_count):
        kind, name, description = catalog[index % len(catalog)]
        node_id = f"main_{index + 1:02d}"
        main_ids.append(node_id)
        nodes.append(
            {
                "id": node_id,
                "name": name,
                "kind": kind,
                "description": description,
                "x": 220 + index * x_step,
                "y": 220 + (index % 2) * 44,
            }
        )
    side_ids: list[str] = []
    for index in range(side_count):
        kind, name, description = catalog[(main_count + index) % len(catalog)]
        node_id = f"side_{index + 1:02d}"
        side_ids.append(node_id)
        parent_index = index % max(1, main_count)
        y_lane = 80 if index % 2 == 0 else 390
        nodes.append(
            {
                "id": node_id,
                "name": name,
                "kind": kind,
                "description": description,
                "x": 220 + parent_index * x_step + (60 if index % 3 == 0 else 0),
                "y": y_lane + (index // 2 % 2) * 34,
            }
        )
    deepest_x = 220 + main_count * x_step
    nodes.append(
        {
            "id": DUNGEON_DEEPEST_SUBNODE_ID,
            "name": "最奥部",
            "kind": "deepest",
            "description": "ダンジョンの中核に近い場所。",
            "x": deepest_x,
            "y": 240,
            "world_map_exit": False,
        }
    )
    edges: list[dict[str, Any]] = []

    def add_edge(a: str, b: str, kind: str = "path") -> None:
        if not a or not b or a == b:
            return
        if any({edge.get("from"), edge.get("to")} == {a, b} for edge in edges):
            return
        edges.append({"from": a, "to": b, "kind": kind})

    add_edge(DUNGEON_ENTRY_SUBNODE_ID, main_ids[0])
    for a, b in zip(main_ids, main_ids[1:]):
        add_edge(a, b)
    add_edge(main_ids[-1], DUNGEON_DEEPEST_SUBNODE_ID)
    for index, node_id in enumerate(side_ids):
        parent = main_ids[index % len(main_ids)]
        add_edge(parent, node_id, "branch")
        if index % 2 == 0 and index + 1 < len(main_ids):
            add_edge(node_id, main_ids[index % len(main_ids) + 1], "loop")
        elif index > 0:
            add_edge(node_id, side_ids[index - 1], "narrow_path")
    for index in range(0, len(main_ids) - 2, 2):
        if rng.random() < 0.7:
            add_edge(main_ids[index], main_ids[index + 2], "shortcut")
    if side_ids and rng.random() < 0.8:
        add_edge(DUNGEON_ENTRY_SUBNODE_ID, side_ids[0], "side_path")
    return {"nodes": nodes[:target_count], "edges": edges, "summary": "fallback maze dungeon layout"}


def _merge_dungeon_subnode_layout(fallback: dict[str, Any], llm_layout: dict[str, Any], target_count: int) -> dict[str, Any]:
    result = {
        "nodes": [dict(node) for node in _as_list(fallback.get("nodes")) if isinstance(node, dict)],
        "edges": [dict(edge) for edge in _as_list(fallback.get("edges")) if isinstance(edge, dict)],
        "summary": str(fallback.get("summary") or ""),
    }
    if not isinstance(llm_layout, dict):
        return result
    llm_nodes = [node for node in _as_list(llm_layout.get("nodes") or llm_layout.get("subnodes")) if isinstance(node, dict)]
    if not llm_nodes:
        return result
    fallback_interior = [
        node
        for node in result["nodes"]
        if str(node.get("id") or "") not in {DUNGEON_ENTRY_SUBNODE_ID, DUNGEON_DEEPEST_SUBNODE_ID}
    ]
    llm_interior = [
        node
        for node in llm_nodes
        if str(node.get("id") or node.get("role") or "").strip() not in {DUNGEON_ENTRY_SUBNODE_ID, DUNGEON_DEEPEST_SUBNODE_ID, "entrance", "deepest"}
    ]
    for fallback_node, llm_node in zip(fallback_interior, llm_interior):
        name = str(llm_node.get("name") or llm_node.get("title") or "").strip()
        kind = str(llm_node.get("kind") or llm_node.get("type") or llm_node.get("category") or "").strip()
        description = str(llm_node.get("description") or llm_node.get("summary") or "").strip()
        if name:
            fallback_node["name"] = _short_text(name, 48)
        if kind:
            fallback_node["kind"] = _safe_subnode_kind(kind)
        if description:
            fallback_node["description"] = _short_text(description, 180)
        for key in ("resource_hint", "encounter_hint", "loot_hint"):
            value = str(llm_node.get(key) or "").strip()
            if value:
                fallback_node[key] = _short_text(value, 120)
    summary = str(llm_layout.get("summary") or llm_layout.get("layout_summary") or "").strip()
    if summary:
        result["summary"] = _short_text(summary, 240)
    return result


def _safe_subnode_kind(value: str) -> str:
    key = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    key = re.sub(r"[^a-z0-9_\u3040-\u30ff\u3400-\u9fff]+", "_", key).strip("_")
    return key or "room"


def _ensure_dungeon_graph_connected(graph: dict[str, Any]) -> None:
    nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
    if DUNGEON_ENTRY_SUBNODE_ID not in nodes:
        return
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict) and not edge.get("external")]
    connected = {DUNGEON_ENTRY_SUBNODE_ID}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            a = str(edge.get("from") or "")
            b = str(edge.get("to") or "")
            if a in connected and b in nodes and b not in connected:
                connected.add(b)
                changed = True
            if b in connected and a in nodes and a not in connected:
                connected.add(a)
                changed = True
    anchor = DUNGEON_ENTRY_SUBNODE_ID
    for node_id in list(nodes):
        if node_id in connected:
            anchor = node_id
            continue
        graph.setdefault("edges", []).append({"from": anchor, "to": node_id, "kind": "path"})
        connected.add(node_id)
        anchor = node_id


def _dungeon_branch_parent(graph: dict[str, Any], index: int) -> str:
    nodes = graph.get("nodes", {}) if isinstance(graph.get("nodes"), dict) else {}
    candidates = [node_id for node_id in nodes if str(node_id).startswith("main_")]
    if not candidates:
        candidates = [node_id for node_id in ("main_02", "main_01", "side_01", DUNGEON_DEEPEST_SUBNODE_ID, DUNGEON_ENTRY_SUBNODE_ID) if node_id in nodes]
    if not candidates:
        return next(iter(nodes), DUNGEON_ENTRY_SUBNODE_ID)
    return str(candidates[index % len(candidates)])


def _world_location_blocks_world_map_departure(location: LocationData) -> bool:
    kind = str(location.extra.get("location_kind") or "").strip().lower()
    danger = _clamp_world_danger(location.extra.get("danger_level", location.extra.get("danger")))
    if kind in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair"}:
        return True
    if kind in {"wilderness", "forest", "swamp", "mountain", "wilds"} and danger >= 10:
        return True
    if location.flags.get("dangerous") or location.flags.get("dungeon"):
        return True
    return False


def _subnode_map_hides_unvisited(location: LocationData) -> bool:
    if _is_settlement_location(location) and not _world_location_blocks_world_map_departure(location):
        return False
    return _is_dungeon_location(location) or _world_location_blocks_world_map_departure(location)


def _world_location_is_world_map_exit(location: LocationData) -> bool:
    for key in (
        "world_map_departure_allowed",
        "world_map_exit",
        "fast_travel_exit",
        "dungeon_entrance",
        "entrance",
        "exit",
        "safe_exit",
    ):
        if _as_bool(location.flags.get(key)) or _as_bool(location.extra.get(key)):
            return True
    text = "\n".join(
        str(value or "")
        for value in (
            location.name,
            location.description,
            location.area,
            location.extra.get("location_kind"),
            location.extra.get("kind"),
            location.extra.get("type"),
            location.extra.get("category"),
        )
    ).lower()
    return any(
        marker in text
        for marker in (
            "entrance",
            "exit",
            "gate",
            "foyer",
            "checkpoint",
            "camp",
            "safe room",
            "入口",
            "入り口",
            "出入口",
            "出口",
            "門",
            "前庭",
            "退避",
            "野営",
            "キャンプ",
        )
    )


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


def _fallback_world_location_kind(rng: random.Random, index: int) -> str:
    if index == 0:
        return "settlement"
    return rng.choice(
        (
            "wilderness",
            "landmark",
            "dungeon",
            "settlement",
            "road",
            "crossroad",
            "coast",
            "mountain",
            "river",
            "plain",
            "wilderness",
        )
    )


def _fallback_world_location_name(kind: str, index: int) -> str:
    suffix_by_kind = {
        "road": "街道",
        "crossroad": "分岐路",
        "coast": "海岸",
        "mountain": "山脈",
        "river": "河",
        "plain": "平原",
        "settlement": "の街",
        "dungeon": "迷宮",
        "wilderness": "原野",
        "landmark": "遺標",
    }
    safe_index = max(1, int(index))
    prefix = FANTASY_LOCATION_PREFIXES[(safe_index - 1) % len(FANTASY_LOCATION_PREFIXES)]
    stem = FANTASY_LOCATION_STEMS[((safe_index - 1) // len(FANTASY_LOCATION_PREFIXES)) % len(FANTASY_LOCATION_STEMS)]
    suffix = suffix_by_kind.get(str(kind or "").strip().lower(), "地点")
    return f"{prefix}{stem}{suffix}"


def _fallback_world_location_description(kind: str, danger: int) -> str:
    labels = {
        "settlement": "人々が暮らす拠点。道や周辺地形とつながっている。",
        "dungeon": "危険な探索地。内部はサブノードとして扱われる。",
        "wilderness": "安全地帯の間に広がる野外地形。",
        "landmark": "道中の目印になる特徴的な場所。",
        "road": "別の場所へ続く街道。",
        "crossroad": "複数の道が交わる分岐路。",
        "coast": "海に面した開けた地形。",
        "mountain": "険しい山や峠道を含む地形。",
        "river": "川沿いや渡し場を含む地形。",
        "plain": "見通しのよい平原や草原。",
    }
    return f"{labels.get(kind, '世界地図上の地点。')} 危険度 {danger}。"


def _world_location_kind_guidance() -> list[dict[str, str]]:
    return [
        {"id": kind, "label": WORLD_LOCATION_KIND_LABELS.get(kind, kind)}
        for kind in WORLD_LOCATION_KIND_OPTIONS
    ]


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


def _quest_start_choices(quests: list[QuestData]) -> list[str]:
    return []


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
    facilities = settlement.extra.get("facilities")
    if not isinstance(facilities, list):
        facilities = []
    if _facility_exists([item for item in facilities if isinstance(item, dict)], name):
        settlement.extra["facilities"] = facilities
        return True
    record = _facility_record(name, settlement.name, facility_type)
    record["description"] = description or str(record.get("description") or "")
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
) -> list[str]:
    result = list(choices)
    if _settlement_location_for_name(world, location_name):
        result.insert(0, MAP_CHOICE_LABEL)
    if _location_is_guild(world, location_name) and not active_quest:
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
        if text:
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


def _facility_record(name: str, settlement_name: str, facility_type: str = "") -> dict[str, Any]:
    resolved_type = facility_type or _facility_type_from_name(name)
    original_name = str(name or "").strip()
    display_name = _shop_facility_display_name(original_name, resolved_type, settlement_name)
    return {
        "name": display_name,
        "type": resolved_type,
        "description": f"{settlement_name}にある{name}。",
        "npc_name": "",
        "npc_role": _default_facility_role(resolved_type),
        "location_name": settlement_name,
        "sub_location": display_name,
        "source": "create_settlement_detail",
        "aliases": _facility_aliases(original_name, display_name, resolved_type),
    }


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


def _quest_response_narration(response: dict[str, Any] | None) -> str:
    if not isinstance(response, dict):
        return ""
    return str(response.get("narration") or response.get("text") or response.get("narr") or "").strip()


def _quest_event_needs_resolve(event: Any) -> bool:
    if not event:
        return False
    if isinstance(event, list):
        return any(_quest_event_needs_resolve(item) for item in event)
    if not isinstance(event, dict):
        text = str(event).strip()
        lowered = text.lower()
        return any(word in lowered or word in text for word in ("unresolved", "pending", "needs_resolution", "未解決", "保留", "判定待ち"))

    explicit_keys = (
        "requires_resolution",
        "needs_resolution",
        "unresolved",
        "pending",
        "choice_required",
        "combat_required",
    )
    for key in explicit_keys:
        if key in event:
            return _as_bool(event.get(key))

    status = str(event.get("status") or event.get("state") or "").strip().lower()
    if status in {"unresolved", "pending", "open", "needs_resolution", "active", "未解決", "保留", "継続中"}:
        return True
    if status in {"resolved", "complete", "completed", "done", "解決", "完了"}:
        return False

    if any(key in event for key in ("result", "outcome", "resolved_result", "summary")):
        return False
    return True


def _quest_payload_has_reward(payload: Any) -> bool:
    if isinstance(payload, list):
        return any(_quest_payload_has_reward(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    reward_keys = {
        "reward",
        "rewards",
        "item_rewards",
        "items",
        "receive_items",
        "gain_items",
        "gold_delta",
        "player_gold_delta",
        "receive_gold",
        "gain_gold",
        "reward_gold",
        "exp",
        "xp",
        "reward_exp",
        "player_exp_delta",
        "experience_delta",
    }
    for key in reward_keys:
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        if key in {"gold_delta", "player_gold_delta", "receive_gold", "gain_gold", "reward_gold", "exp", "xp", "reward_exp", "player_exp_delta", "experience_delta"}:
            if _safe_int(value, 0) <= 0:
                continue
        return True
    for value in payload.values():
        if isinstance(value, (dict, list)) and _quest_payload_has_reward(value):
            return True
    return False


def _quest_explicit_finish_status(referee: dict[str, Any] | None, event_resolution: dict[str, Any] | None) -> str:
    return ""
    for payload in (event_resolution or {}, referee or {}):
        status = str(
            payload.get("quest_status")
            or payload.get("quest_outcome")
            or ""
        ).strip().lower()
        if status in {"completed", "complete", "success", "succeeded", "cleared", "達成", "成功", "完了", "解決"}:
            return "completed"
        if status in {"failed", "failure", "fail", "失敗"}:
            return "failed"
        if status in {"abandoned", "withdrawn", "retreated", "cancelled", "canceled", "撤退", "放棄", "中止"}:
            return "abandoned"
        if _as_bool(payload.get("quest_finished") or payload.get("quest_completed") or payload.get("complete_quest") or payload.get("completed_quest")):
            return "completed"
        if _as_bool(payload.get("quest_failed")):
            return "failed"
        if _as_bool(payload.get("quest_abandoned")):
            return "abandoned"
    return ""


def _quest_completion_text(
    quest: QuestData,
    action: str,
    referee: dict[str, Any],
    event_resolution: dict[str, Any] | None,
    narration: str,
    location: str,
) -> str:
    parts: list[str] = [
        str(quest.extra.get("objective") or ""),
        str(quest.extra.get("quest_progress") or ""),
        action,
        narration,
        location,
    ]
    for payload in (referee, event_resolution or {}):
        if not isinstance(payload, dict):
            continue
        for key in ("quest_progress", "quest_update", "event", "reward", "rewards"):
            value = payload.get(key)
            if value not in (None, "", [], {}):
                if isinstance(value, (dict, list)):
                    parts.append(json.dumps(value, ensure_ascii=False, default=str))
                else:
                    parts.append(str(value))
    return "\n".join(part for part in parts if part)


def _infer_quest_finish_status(
    quest: QuestData,
    action: str,
    referee: dict[str, Any],
    event_resolution: dict[str, Any] | None,
    narration: str,
    location: str,
) -> str:
    return ""
    explicit = _quest_explicit_finish_status(referee, event_resolution)
    if explicit:
        return explicit
    if _is_quest_abandon_action(action):
        return "abandoned"

    text = _quest_completion_text(quest, action, referee, event_resolution, narration, location)
    lowered = text.lower()
    quest_text = f"{quest.name}\n{quest.overview}\n{quest.extra.get('objective') or ''}"
    quest_lowered = quest_text.lower()

    rescue_quest = any(word in quest_lowered or word in quest_text for word in ("rescue", "save", "救出", "救助", "助け", "娘", "行方不明", "連れ去"))
    rescued = any(word in lowered or word in text for word in ("rescued", "saved", "救出した", "救助した", "保護した", "無事に保護", "解放した", "拘束を解除した"))
    returned = any(word in lowered or word in text for word in ("returned", "brought back", "帰還した", "連れて帰った", "連れ帰った", "連れ帰り", "連れ戻した", "戻った"))
    reported = any(word in lowered or word in text for word in ("reported", "reported to", "quest giver", "client", "報告した", "報告を終え", "依頼主へ報告", "依頼人へ報告", "ギルドへ報告"))
    completed = any(word in lowered or word in text for word in ("quest completed", "quest complete", "cleared quest", "依頼を達成", "依頼達成", "クエスト達成", "達成した", "完了した", "完遂した", "解決した"))
    reward_claimed = any(word in lowered or word in text for word in ("reward received", "received reward", "報酬を受け取", "報酬を受領", "報酬が支払"))
    reward_seen = _quest_payload_has_reward(referee) or _quest_payload_has_reward(event_resolution)

    if reward_seen and (completed or reward_claimed):
        return "completed"
    if rescue_quest and rescued and returned and (reported or completed or reward_claimed):
        return "completed"
    if completed and (reported or reward_claimed):
        return "completed"
    return ""


def _quest_finish_status(action: str, referee: dict[str, Any], event_resolution: dict[str, Any] | None) -> str:
    return ""
    for payload in (event_resolution or {}, referee or {}):
        status = str(payload.get("quest_status") or payload.get("quest_outcome") or "").strip().lower()
        if status in {"completed", "complete", "success", "succeeded", "達成", "成功"}:
            return "completed"
        if status in {"failed", "failure", "fail", "失敗"}:
            return "failed"
        if status in {"abandoned", "withdrawn", "retreated", "cancelled", "canceled", "撤退", "放棄", "中止"}:
            return "abandoned"
        if _as_bool(payload.get("quest_completed") or payload.get("complete_quest") or payload.get("completed_quest")):
            return "completed"
        if _as_bool(payload.get("quest_failed")):
            return "failed"
        if _as_bool(payload.get("quest_abandoned")):
            return "abandoned"
    action_text = str(action or "").lower()
    if any(word in action_text for word in ("撤退", "放棄", "諦め", "やめる", "retreat", "abandon", "withdraw", "give up")):
        return "abandoned"
    return ""


def _is_quest_abandon_action(action: str) -> bool:
    text = str(action or "").lower()
    return any(word in text for word in ("撤退", "放棄", "諦め", "やめる", "retreat", "abandon", "withdraw", "give up"))


def _is_craft_action_text(action: str) -> bool:
    text = str(action or "").strip()
    lowered = text.lower()
    craft_words = (
        "craft",
        "combine",
        "make",
        "create",
        "forge",
        "process",
        "加工",
        "合成",
        "クラフト",
        "作る",
        "作成",
        "製作",
        "鍛造",
        "強化",
    )
    if not any(word in lowered or word in text for word in craft_words):
        return False
    material_connectors = ("と", "、", ",", "+", " and ", " with ", " using ", "から", "で")
    return any(connector in lowered or connector in text for connector in material_connectors)


def _is_home_construction_action(action: str) -> bool:
    text = str(action or "").strip()
    lowered = text.lower()
    if not any(word in lowered or word in text for word in ("house", "home", "hut", "cabin", "家", "自宅", "小屋", "住居")):
        return False
    return any(
        word in lowered or word in text
        for word in ("build", "construct", "repair", "improve", "建て", "建築", "建設", "作る", "造る", "修理", "増築", "進める")
    )


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


def _craft_material_phrases(action: str) -> list[str]:
    text = str(action or "").strip()
    if not text:
        return []
    material_part = text
    for result_marker in ("を作る", "を作成", "を製作", "をクラフト", "を作"):
        if result_marker not in text:
            continue
        prefix = text.split(result_marker, 1)[0]
        for separator in ("で", "から"):
            if separator in prefix:
                material_part = prefix.rsplit(separator, 1)[0]
                break
        if material_part != text:
            break
    for marker in ("を加工", "を合成", "をクラフト", "を強化", "を使", "から", "で作", "でクラフト", "to make", "into"):
        index = material_part.lower().find(marker.lower()) if marker.isascii() else material_part.find(marker)
        if index > 0:
            material_part = material_part[:index]
            break
    material_part = re.sub(r"^(所持品の|持っている|周囲の|近くの|nearby|my)\s*", "", material_part, flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:と|、|,|\+| and | with | using )\s*", material_part, flags=re.IGNORECASE)
    cleaned: list[str] = []
    for part in parts:
        value = str(part or "").strip(" \t\r\n。、,.+\"'")
        value = re.sub(r"(を|で|から|素材|材料)$", "", value).strip()
        if value and len(value) <= 80:
            cleaned.append(value)
    return cleaned


def _match_craft_candidate(phrase: str, candidates: list[dict[str, Any]], used_uuids: set[str]) -> dict[str, Any] | None:
    needle = str(phrase or "").strip().casefold()
    if not needle:
        return None
    for candidate in candidates:
        item = candidate.get("item") if isinstance(candidate, dict) else {}
        if not isinstance(item, dict):
            continue
        item_uuid = str(item.get("item_uuid") or "")
        if item_uuid in used_uuids:
            continue
        name = str(item.get("name") or "")
        haystack = name.casefold()
        if needle == haystack or needle in haystack or haystack in needle:
            return candidate
    return None


def _compact_item_for_ai(item: dict[str, Any]) -> dict[str, Any]:
    normalised = normalise_item(item)
    data = {
        "name": normalised.get("name"),
        "category": normalised.get("category"),
        "description": normalised.get("description"),
        "quantity": normalised.get("quantity"),
        "rarity": normalised.get("rarity"),
        "value": normalised.get("value"),
        "effects": normalised.get("effects"),
        "llm_effects": normalised.get("llm_effects"),
        "attack": normalised.get("attack"),
        "defense": normalised.get("defense"),
    }
    return _drop_empty(data)


def _craft_fallback_category(ingredients: list[dict[str, Any]]) -> str:
    for item in ingredients:
        category = str(item.get("category") or "")
        if category.startswith("weapon_"):
            return category
        if category.startswith("armor_") or category.startswith("accessory_"):
            return category
    if any(str(item.get("category") or "").startswith("material_") for item in ingredients):
        return "tool"
    return "junk"


def _should_use_action_roll(action: str, input_type: str, purpose: str) -> bool:
    text = str(action or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if text in {MAP_CHOICE_LABEL, QUEST_BOARD_CHOICE_LABEL}:
        return False
    if _is_quest_abandon_action(text) or _is_conversation_end_action(text):
        return False
    if purpose == "craft":
        return True
    if _contains_any_action_roll_keyword(text, lowered):
        return True
    if _looks_like_simple_auto_action(text, lowered):
        return False
    if purpose in {"quest", "conversation", "exploration"}:
        return input_type == "free_action"
    return input_type == "free_action"


def _roll_ability_for_action(action: str, purpose: str) -> str:
    text = str(action or "")
    lowered = text.lower()
    if purpose == "craft":
        return "dex"
    ability_keywords = (
        ("str", ("force", "break", "lift", "carry", "push", "pull", "bend", "smash", "筋力", "力ずく", "壊す", "破壊", "持ち上げ", "押す", "引く")),
        ("dex", ("dex", "agile", "sneak", "hide", "steal", "lockpick", "pick lock", "disarm", "dodge", "climb", "jump", "throw", "器用", "隠れる", "忍び", "盗む", "鍵", "開錠", "解除", "罠", "避け", "登る", "跳ぶ", "投げ")),
        ("con", ("endure", "resist", "withstand", "swim", "stamina", "poison", "耐える", "抵抗", "泳ぐ", "毒", "我慢")),
        ("int", ("decipher", "study", "analyze", "remember", "research", "solve", "read", "知識", "解読", "分析", "研究", "調査", "読む", "思い出")),
        ("wis", ("search", "investigate", "track", "notice", "sense", "listen", "find", "探索", "探す", "調べ", "追跡", "気配", "聞き耳", "発見", "観察")),
        ("cha", ("persuade", "convince", "negotiate", "deceive", "lie", "threaten", "perform", "bargain", "説得", "交渉", "騙す", "嘘", "脅す", "演奏", "値切", "魅力")),
        ("magic", ("magic", "spell", "ritual", "mana", "arcane", "cast", "魔法", "呪文", "儀式", "魔力", "詠唱")),
        ("will", ("will", "focus", "fear", "curse", "mental", "spirit", "意志", "集中", "恐怖", "呪い", "精神")),
    )
    for ability, keywords in ability_keywords:
        if any(keyword in lowered or keyword in text for keyword in keywords):
            return ability
    if purpose == "conversation":
        return "cha"
    if purpose == "exploration":
        return "wis"
    return "wis"


def _roll_target_for_action(action: str, purpose: str) -> int:
    text = str(action or "")
    lowered = text.lower()
    target = 10
    if purpose == "conversation":
        target = 10
    elif purpose == "exploration":
        target = 8
    if any(word in lowered or word in text for word in ("easy", "simple", "trivial", "簡単", "容易", "素人でも簡単")):
        target = min(target, 6)
    if any(word in lowered or word in text for word in ("quick", "ordinary", "basic", "軽い", "普通", "5分")):
        target = min(target, 8)
    if any(word in lowered or word in text for word in ("locked", "trap", "sneak", "persuade", "negotiate", "heal", "repair", "鍵", "罠", "忍び", "説得", "交渉", "治療", "修理")):
        target = max(target, 10)
    if any(word in lowered or word in text for word in ("hard", "difficult", "complex", "dangerous", "ritual", "expert", "難しい", "複雑", "危険", "儀式", "熟練", "精通")):
        target = max(target, 12)
    if any(word in lowered or word in text for word in ("very hard", "severe", "delicate", "ancient", "呪い", "古代", "繊細", "かなり難しい")):
        target = max(target, 14)
    if any(word in lowered or word in text for word in ("master", "legendary", "impossible", "dragon", "artifact", "熟練の技術", "伝説", "不可能", "神器")):
        target = max(target, 16)
    if any(word in lowered or word in text for word in ("miracle", "fate", "one chance", "奇跡", "時の運", "一か八か")):
        target = max(target, 18)
    return _normalise_roll_target(target)


def _craft_roll_target(ingredients: list[dict[str, Any]]) -> int:
    items = [normalise_item(item) for item in ingredients if isinstance(item, dict)]
    target = 10
    if any(is_equipment_item(item) for item in items):
        target = 12
    rarity_rank = max((_roll_rarity_rank(str(item.get("rarity") or "common")) for item in items), default=0)
    target += min(4, rarity_rank)
    categories = {str(item.get("category") or "") for item in items}
    if categories & {"relic", "material_magical", "material_gem"}:
        target += 2
    if len(items) >= 4:
        target += 2
    return _normalise_roll_target(target)


def _normalise_roll_target(value: Any) -> int:
    number = max(6, min(18, _safe_int(value, 10)))
    return min((6, 8, 10, 12, 14, 16, 18), key=lambda target: (abs(target - number), target))


def _roll_ability_label(ability: str) -> str:
    return {
        "str": "筋力",
        "dex": "器用",
        "con": "耐久",
        "int": "知力",
        "wis": "判断",
        "cha": "魅力",
        "magic": "魔力",
        "will": "意志",
    }.get(str(ability or ""), str(ability or "能力"))


def _contains_any_action_roll_keyword(text: str, lowered: str) -> bool:
    keywords = (
        "search",
        "investigate",
        "examine",
        "unlock",
        "lockpick",
        "pick lock",
        "force",
        "break",
        "climb",
        "jump",
        "swim",
        "sneak",
        "hide",
        "steal",
        "persuade",
        "convince",
        "threaten",
        "deceive",
        "negotiate",
        "bargain",
        "craft",
        "combine",
        "upgrade",
        "repair",
        "disarm",
        "track",
        "decipher",
        "cast",
        "ritual",
        "heal",
        "treat",
        "resist",
        "endure",
        "dodge",
        "chase",
        "trap",
        "forage",
        "harvest",
        "mine",
        "brew",
        "探索",
        "探す",
        "調べ",
        "開錠",
        "鍵",
        "こじ開け",
        "破壊",
        "登る",
        "跳ぶ",
        "泳ぐ",
        "忍び",
        "隠れる",
        "盗む",
        "説得",
        "交渉",
        "脅す",
        "騙す",
        "値切",
        "クラフト",
        "合成",
        "強化",
        "修理",
        "罠",
        "解読",
        "魔法",
        "儀式",
        "治療",
        "耐える",
        "避け",
        "追跡",
        "採取",
        "採掘",
        "調合",
    )
    return any(keyword in lowered or keyword in text for keyword in keywords)


def _looks_like_simple_auto_action(text: str, lowered: str) -> bool:
    simple_keywords = (
        "go to",
        "move to",
        "head to",
        "visit",
        "enter",
        "leave",
        "open map",
        "map",
        "quest board",
        "inventory",
        "status",
        "look around",
        "wait",
        "rest",
        "talk to",
        "speak to",
        "行く",
        "向かう",
        "移動",
        "入る",
        "出る",
        "地図",
        "掲示板",
        "インベントリ",
        "所持品",
        "周囲を見る",
        "待つ",
        "休む",
        "話しかけ",
    )
    return any(keyword in lowered or keyword in text for keyword in simple_keywords)


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


def _npc_generation_requests(response: dict[str, Any]) -> list[Any]:
    for key in (
        "new_npc_requests",
        "new_npc_request",
        "npc_requests",
        "npc_request",
        "new_npcs",
        "needed_npcs",
        "required_npcs",
        "npc_to_generate",
        "npcs_to_generate",
    ):
        if key not in response:
            continue
        value = response.get(key)
        if value is True:
            return [{"reason": key}]
        if value:
            return _as_list(value)
    return []


def _infer_npc_generation_requests(response: dict[str, Any], action: str, location: str, world: WorldData) -> list[Any]:
    inferred: list[Any] = []
    for item in _as_list(response.get("recipients")):
        name = _clean_generated_name(item, "", kind="character")
        if _should_generate_npc_name(world, name, location=location):
            inferred.append(
                {
                    "name": name,
                    "role": "npc",
                    "reason": "master_ai_facilitator named this recipient, but the character is not registered yet.",
                    "location": location,
                }
            )

    for item in _collect_nested_npc_requests(response):
        inferred.append(item)

    text_blob = json.dumps(_strip_response_metadata(response), ensure_ascii=False)
    for name in _extract_npc_candidate_names(action + "\n" + text_blob):
        if _should_generate_npc_name(world, name, location=location):
            inferred.append(
                {
                    "name": name,
                    "role": "npc",
                    "reason": "The recent narration or choices refer to this unregistered NPC.",
                    "location": location,
                }
            )
    return inferred


def _dedupe_npc_requests(requests: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in requests:
        if isinstance(item, dict):
            data = dict(item)
            name = _clean_generated_name(
                data.get("name") or data.get("character_name") or data.get("npc_name") or "",
                "",
                kind="character",
            )
            if name:
                data["name"] = name
            key = json.dumps(
                {
                    "name": name,
                    "role": data.get("role") or data.get("occupation") or data.get("job") or data.get("category") or "",
                    "reason": data.get("reason") or data.get("description") or data.get("summary") or "",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            value: Any = data
        else:
            name = _clean_generated_name(item, "", kind="character")
            key = name or str(item)
            value = {"name": name, "reason": str(item)} if name else item
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _filter_npc_generation_requests(
    requests: list[Any],
    world: WorldData,
    location: str,
    player_name: str,
) -> list[Any]:
    result: list[Any] = []
    for item in requests:
        name = _npc_request_name(item)
        if name and not _should_generate_npc_name(world, name, location=location, player_name=player_name):
            continue
        if _npc_request_matches_existing_scene_character(item, world, location, player_name):
            continue
        if _npc_request_is_player(item, world, player_name):
            continue
        result.append(item)
    return result


def _npc_request_name(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_generated_name(
            value.get("name") or value.get("character_name") or value.get("npc_name") or value.get("target") or value.get("recipient"),
            "",
            kind="character",
        )
    return _clean_generated_name(value, "", kind="character")


def _npc_request_terms(value: Any) -> list[str]:
    if isinstance(value, dict):
        terms: list[str] = []
        for key in (
            "name",
            "character_name",
            "npc_name",
            "target",
            "recipient",
            "role",
            "occupation",
            "job",
            "title",
            "alias",
        ):
            cleaned = _clean_generated_name(value.get(key), "", kind="character")
            if cleaned:
                terms.append(cleaned)
        for key in ("aliases", "tags"):
            for item in _as_list(value.get(key)):
                cleaned = _clean_generated_name(item, "", kind="character")
                if cleaned:
                    terms.append(cleaned)
        return _dedupe_strs(terms)
    name = _clean_generated_name(value, "", kind="character")
    return [name] if name else []


def _npc_request_matches_existing_scene_character(value: Any, world: WorldData, location: str, player_name: str) -> bool:
    terms = _npc_request_terms(value)
    if not terms:
        return False
    for term in terms:
        if _existing_scene_character_matches(world, term, location, player_name):
            return True
    return False


def _npc_request_is_player(value: Any, world: WorldData, player_name: str) -> bool:
    return any(_is_player_reference(term, world, player_name) for term in _npc_request_terms(value))


def _collect_nested_npc_requests(value: Any, depth: int = 0) -> list[Any]:
    if depth > 5:
        return []
    if isinstance(value, dict):
        result: list[Any] = []
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in {
                "new_npc_request",
                "new_npc_requests",
                "npc_request",
                "npc_requests",
                "needed_npc",
                "needed_npcs",
                "required_npc",
                "required_npcs",
                "npc_to_generate",
                "npcs_to_generate",
            }:
                result.extend(_as_list(item))
                continue
            result.extend(_collect_nested_npc_requests(item, depth + 1))
        return result
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            result.extend(_collect_nested_npc_requests(item, depth + 1))
        return result
    return []


def _extract_npc_candidate_names(text: str) -> list[str]:
    source = str(text or "")
    names: list[str] = []
    patterns = (
        r"([^\s、。,.「」『』（）()\[\]{}:：]{2,20})(?:に話しかける|と話す|に尋ねる|を呼ぶ|に会う)",
        r"(?:talk to|speak to|ask|meet)\s+([A-Za-z][A-Za-z0-9 _'\-]{1,32})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source, flags=re.IGNORECASE):
            cleaned = _clean_generated_name(match.group(1), "", kind="character")
            if cleaned:
                names.append(cleaned)
    return _dedupe_strs(names)


def _should_generate_npc_name(
    world: WorldData,
    name: str,
    *,
    location: str = "",
    player_name: str = "",
) -> bool:
    if not name:
        return False
    if name == world.world_name or name in world.characters:
        return False
    if _world_has_dead_npc_identity(world, name=name):
        return False
    lowered = name.lower()
    if lowered in {"player", "pc", "npc", "character", "unknown", "monster", "enemy", "hero", "protagonist", "you"}:
        return False
    if _is_player_reference(name, world, player_name):
        return False
    if _existing_scene_character_matches(world, name, location, player_name):
        return False
    return True


def _world_has_dead_npc_identity(world: WorldData, *, name: str = "", uuid: str = "") -> bool:
    extra = world.extra if isinstance(world.extra, dict) else {}
    dead_names = extra.get("dead_npc_names")
    if name and isinstance(dead_names, list):
        if any(str(item) == name for item in dead_names):
            return True
    dead_uuids = extra.get("dead_npc_uuids")
    if uuid and isinstance(dead_uuids, list):
        if any(str(item) == uuid for item in dead_uuids):
            return True
    return False


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


def _character_reference_terms(character: CharacterData) -> list[str]:
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


def _character_ai_context(character: CharacterData, *, details: bool = True) -> dict[str, Any]:
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
        "attributes": _compact_value(character.attributes, max_chars=500),
        "gender": character.gender,
        "age": character.age,
        "backstory": _short_text(character.backstory, 700 if details else 280),
        "personality": _short_text(character.personality, 500 if details else 240),
        "look": _short_text(character.look, 500 if details else 240),
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
        data["skill_trait_power_budget"] = _actor_power_budget(character)
        data["skill_trait_power_used"] = _entry_power_total(character.traits) + _entry_power_total(character.skills)
    if character.image_generation_prompt:
        data["image_generation_prompt"] = [str(item) for item in character.image_generation_prompt[:12]]
    if details:
        data["traits"] = _compact_value(character.traits, max_chars=900)
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


def _quest_ai_context(
    quest: QuestData,
    *,
    include_log: bool = True,
    include_extra: bool = True,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": quest.name,
        "overview": _short_text(quest.overview, 900),
        "status": quest.status,
        "quest_type": quest.extra.get("quest_type"),
        "quest_stage": quest.extra.get("quest_stage"),
        "deadline_hours": quest.extra.get("deadline_hours"),
        "neighboring_settlement": quest.neighboring_settlement,
        "choices": [str(item) for item in quest.choices[:6]],
        "reward": _compact_value(quest.extra.get("reward", {}), max_chars=600),
    }
    if include_log and quest.log:
        data["recent_log"] = _compact_value(_quest_ai_public_value(quest.log[-6:]), max_chars=1400)
    if include_extra and quest.extra:
        data["details"] = _compact_value(_quest_ai_public_value(quest.extra), max_chars=2400)
    return _drop_empty(data)


def _quest_ai_public_value(value: Any, *, key: str = "") -> Any:
    key_text = str(key or "")
    if key_text in {"uuid", "item_uuid", "item_uuids", "accepted_item_uuid"} or key_text.endswith("_uuid"):
        return None
    if isinstance(value, str):
        return _hide_internal_quest_tokens(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        result = [
            _quest_ai_public_value(item)
            for item in value
        ]
        return [item for item in result if item is not None]
    if isinstance(value, dict):
        if key_text == "objective_entities":
            return _quest_objective_entities_ai_view(value)
        result: dict[str, Any] = {}
        for child_key, child_value in value.items():
            child_key_text = str(child_key)
            if child_key_text in {"uuid", "item_uuid", "item_uuids", "accepted_item_uuid"} or child_key_text.endswith("_uuid"):
                continue
            public_value = _quest_ai_public_value(child_value, key=child_key_text)
            if public_value is not None:
                result[child_key_text] = public_value
        return result
    return _hide_internal_quest_tokens(str(value))


def _quest_objective_entities_ai_view(pack: dict[str, Any]) -> dict[str, Any]:
    def public_entries(group: str, prefix: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for index, entry in enumerate(_as_list(pack.get(group)), start=1):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").strip()
            label = str(entry.get("role_label") or entry.get("display_alias") or INTERNAL_QUEST_TOKEN_LABELS.get(role, role) or prefix)
            entries.append(
                _drop_empty(
                    {
                        "ref": f"{prefix}_{index}",
                        "name": _hide_internal_quest_tokens(entry.get("name")),
                        "display_alias": _hide_internal_quest_tokens(entry.get("display_alias") or label),
                        "role_label": _hide_internal_quest_tokens(label),
                        "role": INTERNAL_QUEST_TOKEN_LABELS.get(role, role),
                        "status": str(entry.get("status") or ""),
                        "location": str(entry.get("location") or ""),
                        "subnode_id": str(entry.get("subnode_id") or ""),
                    }
                )
            )
        return entries

    return _drop_empty(
        {
            "version": pack.get("version"),
            "quest_type": pack.get("quest_type"),
            "location": pack.get("location"),
            "subnode_id": pack.get("subnode_id"),
            "status": pack.get("status"),
            "npcs": public_entries("npcs", "objective_npc"),
            "items": public_entries("items", "objective_item"),
            "markers": public_entries("markers", "objective_marker"),
            "requirements": public_entries("requirements", "objective_requirement"),
            "flags": _quest_ai_public_value(pack.get("flags", {})),
        }
    )


def _hide_internal_quest_tokens(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"(?i)\s*\bUUID\s*[:=]\s*[0-9a-f-]{8,}\b", "", text)
    text = re.sub(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "対象",
        text,
    )
    text = re.sub(r"(?i)\b[0-9a-f]{24,36}\b", "対象", text)
    text = re.sub(r"(?i)\s*\bUUID\s*[:=]\s*対象\b", "", text)
    text = re.sub(r"\s*[\(（]\s*対象\s*[\)）]", "", text)
    for token, label in INTERNAL_QUEST_TOKEN_LABELS.items():
        text = re.sub(rf"\b{re.escape(token)}\b", label, text)
    return text


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


def _quest_from_raw(item: Any, index: int) -> QuestData:
    if isinstance(item, dict):
        data = dict(item)
        data["name"] = str(data.get("name") or data.get("quest_name") or data.get("title") or f"Quest {index + 1}")
        data["overview"] = str(data.get("overview") or data.get("description") or data.get("summary") or "")
        quest = QuestData.from_dict(data, default_name=f"Quest {index + 1}")
        quest_type = _normalise_quest_type_id(
            data.get("quest_type")
            or data.get("objective_type")
            or data.get("type")
            or data.get("kind")
            or quest.extra.get("quest_type")
            or quest.extra.get("objective_type")
        )
        if not quest_type:
            quest_type = _quest_type(quest, data)
        quest.extra["quest_type"] = quest_type
        quest.extra["objective_type"] = quest_type
        return quest
    return QuestData(name=f"Quest {index + 1}", overview=str(item))


def _character_from_raw(item: Any, index: int, category: str) -> CharacterData:
    if isinstance(item, dict):
        data = dict(item)
        name = str(data.get("name") or data.get("character_name") or f"{category.title()} {index + 1}")
        role = str(data.get("role") or data.get("job") or data.get("occupation") or "")
        description = str(data.get("description") or data.get("backstory") or data.get("summary") or "")
        character = CharacterData.from_dict(data, default_name=name)
        character.name = name
        character.role = role
        character.category = category
        if description and not character.backstory:
            character.backstory = description
        character.extra.setdefault("raw_create_settlement_detail_entry", data)
        return character
    return CharacterData(
        name=f"{category.title()} {index + 1}",
        role=category,
        category=category,
        backstory=str(item),
    )


def _npc_from_raw(item: Any, index: int) -> CharacterData:
    if isinstance(item, dict):
        data = dict(item)
        name = _clean_generated_name(
            data.get("name") or data.get("character_name") or data.get("npc_name"),
            f"NPC {index + 1}",
            kind="character",
        )
        category = str(data.get("category") or data.get("npc_category") or "npc")
        role = str(data.get("role") or data.get("occupation") or data.get("job") or category)
        character = CharacterData.from_dict(data, default_name=name)
        character.name = name
        character.category = category
        character.role = role
        description = str(data.get("description") or data.get("backstory") or data.get("summary") or "")
        if description and not character.backstory:
            character.backstory = description
        if data.get("personality") and not character.personality:
            character.personality = str(data.get("personality"))
        if data.get("look") and not character.look:
            character.look = str(data.get("look"))
        if data.get("appearance") and not character.look:
            character.look = str(data.get("appearance"))
        if data.get("image_generation_prompt") and not character.image_generation_prompt:
            character.image_generation_prompt = _as_str_list(data.get("image_generation_prompt"))
        if data.get("skills"):
            character.skills = [skill for skill in (_normalise_skill(item) for item in _as_list(data.get("skills"))) if skill.get("name")]
        if data.get("traits"):
            character.traits = [trait for trait in (_normalise_trait(item) for item in _as_list(data.get("traits"))) if trait.get("name")]
        _normalise_actor_power_loadout(character)
        if data.get("aliases"):
            character.extra["aliases"] = _as_str_list(data.get("aliases"))
        if data.get("description"):
            character.extra["description"] = str(data.get("description"))
        if data.get("occupation"):
            character.extra["occupation"] = str(data.get("occupation"))
        if data.get("archetype"):
            character.extra["archetype"] = str(data.get("archetype"))
        return character
    return CharacterData(
        name=f"NPC {index + 1}",
        role="npc",
        category="npc",
        backstory=str(item),
    )


def _enemy_npc_from_raw(item: Any, index: int) -> CharacterData:
    if isinstance(item, dict):
        data = dict(item)
        name = _clean_generated_name(
            data.get("name") or data.get("monster_name") or data.get("enemy_name"),
            f"Enemy {index + 1}",
            kind="monster",
        )
        category = str(data.get("category") or data.get("monster_category") or data.get("type") or "wild_encounter")
        description = str(data.get("description") or data.get("summary") or data.get("overview") or "")
        character = CharacterData.from_dict(data, default_name=name)
        character.name = name
        character.role = str(data.get("role") or data.get("role_label") or category or "敵対者")
        character.category = "enemy_npc"
        if description and not character.backstory:
            character.backstory = description
        if description and not character.look:
            character.look = description
        if data.get("image_generation_prompt"):
            character.image_generation_prompt = _as_str_list(data.get("image_generation_prompt"))
            character.prompts["image_generation_prompt"] = _as_str_list(data.get("image_generation_prompt"))
        if data.get("skills"):
            character.skills = [skill for skill in (_normalise_skill(item) for item in _as_list(data.get("skills"))) if skill.get("name")]
        if data.get("traits"):
            character.traits = [trait for trait in (_normalise_trait(item) for item in _as_list(data.get("traits"))) if trait.get("name")]
        character.flags["enemy_npc"] = True
        character.flags["hostile"] = _as_bool(data.get("hostile", True))
        character.extra["aliases"] = _dedupe_strs([name, category, "敵", "魔物", *[str(value) for value in _as_list(data.get("aliases"))]])
        character.extra["description"] = description
        character.extra.setdefault("raw_field_event_enemy", data)
        _normalise_actor_power_loadout(character)
        return character
    return CharacterData(
        name=f"Enemy {index + 1}",
        role="敵対者",
        category="enemy_npc",
        backstory=str(item),
        look=str(item),
        flags={"enemy_npc": True, "hostile": True},
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
    if base not in world.characters:
        return base
    suffix = 2
    while f"{base} {suffix}" in world.characters:
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


def _character_is_hostile_actor(character: CharacterData) -> bool:
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


def _combat_trigger_text(action: str, response: dict[str, Any], narration: str, choices: list[str]) -> str:
    parts = [
        action,
        narration,
        str(response.get("narration") or ""),
        str(response.get("text") or ""),
        str(response.get("message") or ""),
        str(response.get("event") or ""),
        json.dumps(_as_list(response.get("choices")) + choices, ensure_ascii=False, default=str),
    ]
    return "\n".join(part for part in parts if str(part or "").strip())


def _text_implies_combat_started(text: str) -> bool:
    source = str(text or "")
    lowered = source.casefold()
    english = (
        "attacks",
        "starts attacking",
        "is attacking",
        "attacked you",
        "attacks you",
        "attack begins",
        "battle begins",
        "combat begins",
        "lunges at you",
        "charges at you",
        "pounces on you",
    )
    japanese = (
        "襲い掛か",
        "襲いかか",
        "襲ってき",
        "攻撃してき",
        "飛びかか",
        "飛び掛か",
        "突進してき",
        "戦闘が始",
        "戦闘に突入",
        "戦いが始",
        "牙をむいて飛び",
        "爪を振りかざ",
        "こちらへ襲",
        "こちらに襲",
    )
    return any(word in lowered for word in english) or any(word in source for word in japanese)
