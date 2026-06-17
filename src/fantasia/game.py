from __future__ import annotations

import json
import random
import re
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
from .world_model import CharacterData, GameStateData, LocationData, MonsterData, QuestData, WorldData


SEASONS = ("春", "夏", "秋", "冬")
DAYS_PER_SEASON = 60
HOURS_PER_DAY = 24
WORLD_DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
INITIAL_WORLD_TIME_HOURS = 8
PLAYER_MAX_LEVEL = 50
PLAYER_BASE_EXP_TO_NEXT = 5
PLAYER_MAX_EXP_TO_NEXT = 100_000_000
MAX_EXPLORATION_CHOICES = 5
WORLD_LOCATION_COUNT_OPTIONS = {"small": 30, "normal": 60, "many": 90}
DEFAULT_WORLD_LOCATION_COUNT = WORLD_LOCATION_COUNT_OPTIONS["normal"]
WORLD_CRIME_RISK_OPTIONS = {"none", "normal", "strict"}
DEFAULT_WORLD_CRIME_RISK = "none"
WORLD_ENEMY_STRENGTH_OPTIONS = {"weak", "normal", "strong"}
DEFAULT_WORLD_ENEMY_STRENGTH = "normal"
WORLD_LOCATION_BATCH_MIN = 3
WORLD_LOCATION_BATCH_MAX = 5
WORLD_MAP_EDGE_HOURS = 2
WORLD_MAP_MAX_DYNAMIC_DEGREE = 3
SUBNODE_GRAPH_KEY = "subnode_graph"
CURRENT_SUBNODE_FLAG = "current_subnode"
DEFAULT_SUBNODE_ID = "center"
DUNGEON_ENTRY_SUBNODE_ID = "entrance"
DUNGEON_DEEPEST_SUBNODE_ID = "deepest"
SUBNODE_EXTERNAL_PREFIX = "external:"
REPEATED_INPUT_DEDUPE_SECONDS = 4.0
DEFAULT_GUILD_NAME = "冒険者ギルド"
QUEST_BOARD_NAME = "依頼掲示板"
MAP_CHOICE_LABEL = "地図を見る"
QUEST_BOARD_CHOICE_LABEL = "依頼掲示板を見る"
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
    ) -> None:
        self.llm = llm
        self.image_backend = image_backend
        self.store = store
        self.save_store = save_store or SaveStore()
        self.prompt_templates = prompt_templates or PromptTemplateStore()
        self.state = GameStateData()
        self._last_resolved_input: dict[str, Any] = {}

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
                    "基本的に開始地点から遠いほど危険度を高くしてください。ただし物語上の例外は許可します。"
                    "街の施設（宿屋、鍛冶屋、ギルド、店など）はロケーションにせず、街の内部施設として扱ってください。"
                    "洞窟やダンジョンの入口・内部・奥は同じダンジョンロケーション内のサブ地点として扱い、別ロケーションにしないでください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"希望世界名: {requested_world_name or 'AIに任せる'}\n"
                    f"初期ロケーション数: {target_location_count}\n"
                    f"ゲーム設定: {json.dumps(customization, ensure_ascii=False)}\n"
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
                    "3-5 location batches using the overview, existing map summary, neighboring terrain, danger, and world tone."
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
                    "each location is."
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

    def _character_matches_active_facility(self, character: CharacterData) -> bool:
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
        location = self.state.world_data.ensure_location(self.state.current_location)
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

    def _apply_response_progress_effects(self, response: dict[str, Any], source: str) -> list[str]:
        lines: list[str] = []
        lines.extend(self._apply_response_gold_effects(response, source))
        lines.extend(self._apply_response_time_effects(response, source))
        lines.extend(self._apply_response_exp_effects(response, source))
        lines.extend(self._apply_equipment_regen_effects(source))
        return lines

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
        }
        day_keys = {
            "time_passed_days",
            "passed_days",
            "elapsed_days",
            "advance_days",
            "advance_time_days",
            "days_passed",
        }
        nested_keys = {"time_effect", "time_effects", "time_passage", "elapsed_time"}
        effect_type = str(payload.get("type") or payload.get("kind") or payload.get("name") or "").strip().lower()
        if effect_type in {"time_passes", "advance_time", "elapsed_time"}:
            total += self._hp_number(payload.get("hours", payload.get("amount", 0)), 0)
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
        location_data = self.state.world_data.ensure_location(location)
        if not location_data.image_path:
            self.state.flags["pending_background_location"] = location

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
        return max(0, min(9, danger))

    def _opponent_combat_profile(self, opponent_type: str, opponent_name: str, *, location: str = "") -> dict[str, Any]:
        danger = self._current_location_danger(location)
        combat_stats = self.player_combat_stats()
        player_attack = max(0, int(combat_stats.get("attack") or 0) + int(combat_stats.get("attack_bonus") or 0))
        player_defense = max(0, int(combat_stats.get("defense") or 0) + int(combat_stats.get("defense_bonus") or 0))
        setting = self._enemy_strength_setting()
        base_attack = max(0, 1 + danger * 2)
        base_defense = max(0, danger)
        base_hp = max(8, 10 + danger * 4)
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
        opponent = self.state.world_data.characters.get(opponent_name) if opponent_type == "character" else self.state.world_data.monsters.get(opponent_name)
        if isinstance(opponent, CharacterData):
            hp = max(hp, _safe_int(opponent.max_hp or opponent.extra.get("max_hp"), hp))
            attack = max(attack, _safe_int(opponent.extra.get("attack"), attack))
            defense = max(defense, _safe_int(opponent.extra.get("defense"), defense))
        elif isinstance(opponent, MonsterData):
            for source in (opponent.extra, opponent.flags):
                if isinstance(source, dict):
                    hp = max(hp, _safe_int(source.get("max_hp") or source.get("hp"), hp))
                    attack = max(attack, _safe_int(source.get("attack"), attack))
                    defense = max(defense, _safe_int(source.get("defense"), defense))
        return {
            "enemy_strength": setting,
            "danger_level": danger,
            "opponent_attack": max(0, int(attack)),
            "opponent_defense": max(0, int(defense)),
            "opponent_hp": max(1, int(hp)),
            "opponent_max_hp": max(1, int(hp)),
        }

    def _build_encounter(self, opponent_type: str, opponent_name: str, *, location: str = "") -> dict[str, Any]:
        location_name = location or self.state.current_location
        player_max_hp = self._player_max_hp()
        player_hp = self._player_current_hp(player_max_hp)
        player_max_sp = self._player_max_sp()
        player_sp = self._player_current_sp(player_max_sp)
        combat_stats = self.player_combat_stats()
        equipment_summary = self.player_equipment_summary()
        opponent_profile = self._opponent_combat_profile(opponent_type, opponent_name, location=location_name)
        encounter = {
            "status": "active",
            "turn": 0,
            "opponent_type": opponent_type,
            "opponent_name": opponent_name,
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
            "log": [],
        }
        encounter.update(opponent_profile)
        self._sync_encounter_status_effects(encounter)
        self._update_encounter_presence(encounter, "present")
        return encounter

    def _ensure_settlement_facilities(self, settlement: LocationData) -> list[dict[str, Any]]:
        raw = settlement.extra.get("facilities")
        facilities = [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if not any(_looks_like_guild_name(str(item.get("name") or "")) for item in facilities):
            facilities.insert(0, _facility_record(DEFAULT_GUILD_NAME, settlement.name, facility_type="guild"))
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
        facility["location_name"] = settlement.name
        facility["sub_location"] = facility_name
        settlement.flags["settlement"] = True
        settlement.flags["discovered"] = True
        settlement.extra["location_kind"] = "settlement"
        self._mark_location_visited(self.state.world_data, settlement.name)
        self._set_active_facility(settlement, facility)
        npc = self._ensure_facility_npc(settlement, facility, settlement.name)
        choices = self._location_default_choices(settlement.name) + _as_str_list((response or {}).get("choices"))
        if npc:
            choices.append(f"{npc.name}に話しかける")
        narration = str((response or {}).get("narration") or f"{facility_name}へ移動した。")
        self._set_player_presence(settlement.name)
        self.state.flags["screen_mode"] = "exploration"
        self.state.append_turn(action, narration, settlement.name, _exploration_choices(choices), input_type=input_type)
        self._apply_visual_intent(response or {}, "facility_travel", settlement.name, previous_location)
        self.save_game()
        return self.state.log_text(16)

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
        self._set_character_presence(character, location_name)
        return character

    def _set_player_presence(self, location: str) -> None:
        player = self.state.world_data.characters.get(self.state.player_name)
        if player:
            self._set_character_presence(player, location)
        if self.state.party and isinstance(self.state.party[0], dict):
            self.state.party[0]["location"] = location
            flags = self.state.party[0].setdefault("flags", {})
            if isinstance(flags, dict):
                flags["current_location"] = location
        for companion in self._party_companions():
            self._set_character_presence(companion, location, "party")

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
            kind = _infer_world_location_kind(payload, name, description)
            danger = _world_location_danger_from_payload(payload)
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
            location.flags["discovered"] = bool(name == world.starting_location)
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
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
            danger = max(0, min(9, (len(nodes) // 8) + rng.randint(0, 1)))
            description = _fallback_world_location_description(kind, danger)
            location = world.ensure_location(name, description)
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = danger
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
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
        self._recalculate_world_graph_layout(world)
        return world.extra["location_graph"]

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
                        "are subareas of one dungeon location. Return JSON only."
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
                or _safe_int(node.get("danger"), 0) >= 6
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
                "Danger should usually increase as generated_count grows, with occasional world-appropriate exceptions.",
                "Every generated location must be connected by a 2-hour edge to an existing or same-batch location.",
                "Do not generate town facilities as world-map locations.",
                "Do not split dungeon entrances, interiors, or depths into separate locations.",
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
            if _safe_int(node.get("danger"), 0) >= 6:
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
            kind = _infer_world_location_kind(payload, name, description)
            danger = _world_location_danger_from_payload(payload)
            if kind == "facility" and _add_facility_payload_to_settlement(world, name, description, str(payload.get("type") or payload.get("facility_type") or "")):
                continue
            dungeon_parent = _existing_dungeon_location_for_subarea(world, name)
            if dungeon_parent:
                _record_location_subarea(world, dungeon_parent, name, description)
                continue
            if not any(key in payload for key in ("danger", "danger_level", "threat", "threat_level", "difficulty", "rank")):
                danger = max(0, min(9, len(nodes) // 8))
            location = world.ensure_location(name, description)
            location.extra["location_kind"] = kind
            location.extra["danger_level"] = danger
            if _world_kind_is_settlement(kind):
                location.flags["settlement"] = True
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
                "danger": max(0, resolved_danger),
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
        self._upsert_subnode_node(graph, DUNGEON_ENTRY_SUBNODE_ID, "\u5165\u53e3", "\u5916\u3068\u5185\u90e8\u3092\u3064\u306a\u3050\u51fa\u5165\u53e3\u3002", "entrance", 80, 180, world_map_exit=True)
        self._upsert_subnode_node(graph, "passage", "\u901a\u8def", "\u5965\u3078\u7d9a\u304f\u901a\u8def\u3002", "passage", 240, 180)
        self._upsert_subnode_node(graph, "fork", "\u5206\u5c90", "\u8907\u6570\u306e\u9053\u306b\u5206\u304b\u308c\u308b\u5834\u6240\u3002", "fork", 400, 180)
        self._upsert_subnode_node(graph, "depths", "\u6df1\u90e8", "\u5371\u967a\u304c\u5897\u3059\u5965\u306e\u9818\u57df\u3002", "depths", 560, 180)
        self._upsert_subnode_node(graph, DUNGEON_DEEPEST_SUBNODE_ID, "\u6700\u5965\u90e8", "\u30c0\u30f3\u30b8\u30e7\u30f3\u306e\u4e2d\u6838\u306b\u8fd1\u3044\u5834\u6240\u3002", "deepest", 720, 180)
        self._connect_subnodes(graph, DUNGEON_ENTRY_SUBNODE_ID, "passage")
        self._connect_subnodes(graph, "passage", "fork")
        self._connect_subnodes(graph, "fork", "depths")
        self._connect_subnodes(graph, "depths", DUNGEON_DEEPEST_SUBNODE_ID)
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
            self._connect_subnodes(graph, "fork" if index % 2 else "passage", node_id)

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
        current_id = self._current_subnode_id(location_name)
        local_nodes: list[dict[str, Any]] = []
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
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
            and str(edge.get("from") or "") in nodes
            and str(edge.get("to") or "") in nodes
        ]
        external_nodes: list[dict[str, Any]] = []
        external_edges: list[dict[str, Any]] = []
        for index, edge in enumerate(self._subnode_external_edges(world, location_name, graph)):
            source = nodes.get(str(edge.get("from") or ""), {})
            source_x = _safe_int(source.get("x") if isinstance(source, dict) else 80, 80)
            source_y = _safe_int(source.get("y") if isinstance(source, dict) else 80, 80)
            node_id = f"{SUBNODE_EXTERNAL_PREFIX}{index}"
            target_location = str(edge.get("target_location") or "")
            external_nodes.append(
                {
                    "id": node_id,
                    "name": target_location,
                    "description": str(edge.get("description") or ""),
                    "kind": "external",
                    "x": source_x + 170,
                    "y": source_y - 80 + (index % 3) * 80,
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
        self._set_current_subnode(location_name, target_id)
        self._activate_facility_for_subnode(location_name, target)
        name = str(target.get("name") or target_id)
        narration = f"{name}\u3078\u79fb\u52d5\u3057\u305f\u3002"
        self.state.flags["screen_mode"] = "exploration"
        self.state.append_turn("\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5", narration, location_name, self._location_default_choices(location_name), input_type="choice")
        self.save_game()
        return self.state.log_text(16)

    def _travel_external_subnode(self, current_location: str, target: dict[str, Any], source_id: str) -> str:
        world = self.state.world_data
        target_location = str(target.get("target_location") or "").strip()
        if target_location not in world.locations:
            raise ValueError("その移動先はワールドに登録されていません。")
        previous_location = current_location
        hours = max(0, _safe_int(target.get("hours"), WORLD_MAP_EDGE_HOURS))
        time_event = self._advance_world_time(hours, source="subnode_route", reason="subnode route travel", append_log=False)
        self._clear_active_facility(reset_subnode=False)
        self._mark_location_visited(world, target_location)
        target_graph = self._ensure_location_subnode_graph(world, target_location)
        target_subnode = str(target.get("target_subnode") or "")
        if not target_subnode or target_subnode not in target_graph.get("nodes", {}):
            target_subnode = self._default_subnode_for_location(world.locations.get(target_location))
        self._set_current_subnode(target_location, target_subnode)
        self._set_player_presence(target_location)
        self.state.flags["screen_mode"] = "exploration"
        narration = f"{previous_location} -> {target_location} \u3078\u79fb\u52d5\u3057\u305f\u3002"
        self.state.append_turn("\u30b5\u30d6\u30de\u30c3\u30d7\u79fb\u52d5", narration, target_location, self._location_default_choices(target_location), input_type="choice")
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        self._apply_visual_intent({}, "subnode_travel", target_location, previous_location)
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
        if not self._current_subnode_allows_world_map_departure(world, current):
            raise ValueError("危険地帯の奥からはワールドマップ移動できません。入口や安全な退避地点まで戻ってください。")
        path = self._shortest_world_path(world, current, target, visited_only=True)
        if not path:
            raise ValueError("現在地からその場所までの道が見つかりません。")
        hours = (len(path) - 1) * WORLD_MAP_EDGE_HOURS
        time_event = self._advance_world_time(hours, source="world_map_travel", reason="world map travel", append_log=False)
        narration = f"{' -> '.join(path)} の道をたどって移動した。"
        choices = self._location_default_choices(target)
        self._clear_active_facility(reset_subnode=False)
        self._set_player_presence(target)
        self.state.flags["screen_mode"] = "exploration"
        self._mark_location_visited(world, target)
        target_graph = self._ensure_location_subnode_graph(world, target)
        if target_graph:
            self._set_current_subnode(target, self._default_subnode_for_location(world.locations.get(target)))
        self.state.append_turn("ワールドマップ移動", narration, target, choices, input_type="choice")
        if time_event.get("line"):
            self.state.display_log.append(str(time_event["line"]))
        self.state.display_log.extend(str(item) for item in time_event.get("companion_lines", []) if item)
        self._apply_visual_intent({}, "world_map_travel", target, current)
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

        graph = world.extra.get("location_graph", {})
        nodes = graph.get("nodes", {}) if isinstance(graph, dict) else {}
        neighbors = self._world_neighbors(world, current)
        status_lines: list[str] = []
        narration_lines: list[str] = []
        teleport = _teleport_movement_requested(response)

        if proposed in neighbors or teleport:
            if proposed not in nodes:
                location = world.ensure_location(proposed, _short_text(str(response.get("narration") or ""), 220))
                kind = _infer_world_location_kind({}, proposed, location.description)
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
            return {"location": proposed, "narration_lines": narration_lines, "status_lines": status_lines, "moved": True, "denied": False}

        if proposed in nodes:
            narration_lines.append(f"この場所から「{proposed}」へ直接向かう道は見つからない。隣接している場所から順に移動する必要がある。")
            return {"location": current, "narration_lines": narration_lines, "status_lines": [], "moved": False, "denied": True}

        if _nearby_dynamic_location_requested(action, proposed) and len(neighbors) <= WORLD_MAP_MAX_DYNAMIC_DEGREE:
            description = _short_text(str(response.get("narration") or response.get("description") or ""), 220)
            kind = _infer_world_location_kind({}, proposed, description)
            current_node = nodes.get(current, {}) if isinstance(nodes, dict) else {}
            danger = max(0, _safe_int(current_node.get("danger"), 0) + (1 if kind in {"dungeon", "wilderness"} else 0))
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
        choices = ["周囲を見る"]
        for neighbor in self._world_neighbors(self.state.world_data, location_name)[:3]:
            choices.append(f"{neighbor}へ移動")
        if _settlement_location_for_name(self.state.world_data, location_name):
            choices.insert(0, MAP_CHOICE_LABEL)
        active_facility = self._active_facility_record() if location_name == self.state.current_location else None
        active_is_guild = bool(active_facility and str(active_facility.get("type") or "").lower() == "guild")
        if (active_is_guild or _location_is_guild(self.state.world_data, location_name)) and not self.state.active_quest:
            choices.insert(0, QUEST_BOARD_CHOICE_LABEL)
        return _exploration_choices(choices)

    def _augment_location_choices(self, choices: list[str], location_name: str) -> list[str]:
        return _augment_location_choices_for_world(
            self.state.world_data,
            location_name,
            choices,
            active_quest=bool(self.state.active_quest),
        )

    def _set_character_presence(self, character: CharacterData, location: str, state: str = "present") -> None:
        self._ensure_character_runtime_data(character)
        requested_state = state or character.state or "present"
        if _character_state_is_dead(character) and requested_state not in {"dead", "corpse"}:
            self._mark_character_dead(character, source="presence_guard")
            return
        if location:
            character.location = location
            character.flags["current_location"] = location
            character.flags.setdefault("first_seen_location", location)
            character.extra.setdefault("origin_location", location)
        character.state = requested_state
        character.flags["state"] = character.state
        if _actor_state_is_present(character.state):
            character.flags["alive"] = True
        if character.state in {"dead", "corpse"}:
            self._mark_character_dead(character, source="presence")
        else:
            self._sync_companion_party_entry(character)

    def _set_monster_presence(self, monster: MonsterData, location: str, state: str = "present") -> None:
        if location:
            monster.location = location
            monster.flags["current_location"] = location
            monster.flags.setdefault("first_seen_location", location)
        monster.state = state or monster.state or "present"
        monster.flags["state"] = monster.state

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
        character.extra["level"] = character.level
        character.extra["current_hp"] = character.current_hp
        character.extra["max_hp"] = character.max_hp
        character.extra["current_sp"] = character.current_sp
        character.extra["max_sp"] = character.max_sp
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
        character.extra.pop("party_waiting", None)
        if origin:
            self.state.world_data.ensure_location(origin)
            self._set_character_presence(character, origin, "present")
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
        return lines

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

    def _active_visual_subjects(self, location: str) -> tuple[list[CharacterData], list[MonsterData]]:
        characters: list[CharacterData] = []
        monsters: list[MonsterData] = []
        seen_characters: set[str] = set()
        seen_monsters: set[str] = set()
        current_location = location or self.state.current_location or self.state.world_data.starting_location

        def add_character(character: CharacterData | None) -> None:
            if not character or not character.name or character.name in seen_characters:
                return
            seen_characters.add(character.name)
            characters.append(character)

        def add_monster(monster: MonsterData | None) -> None:
            if not monster or not monster.name or monster.name in seen_monsters:
                return
            seen_monsters.add(monster.name)
            monsters.append(monster)

        add_character(self.state.world_data.characters.get(self.state.player_name))

        active_encounter = self._active_encounter()
        if active_encounter:
            opponent_name = str(active_encounter.get("opponent_name") or "")
            if active_encounter.get("opponent_type") == "monster":
                add_monster(self.state.world_data.monsters.get(opponent_name))
            else:
                add_character(self.state.world_data.characters.get(opponent_name))

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

        for monster in self.state.world_data.monsters.values():
            if not _actor_present_at(monster.location, monster.state, monster.flags, current_location):
                continue
            add_monster(monster)
            if len(monsters) >= 4:
                break

        return characters, monsters

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
                    "この拠点の構造、雰囲気、住人、滞在中の冒険者を作ってください。"
                ),
            },
        ]
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
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGの拠点クエスト生成担当です。"
                    "Fantasiaのsettlement_quest_generator相当として、"
                    "quests を持つJSONだけを返してください。"
                    "quests はクエスト候補オブジェクトの配列にしてください。"
                    "各クエストには reward として gold, exp, 任意のitems, description を含めてください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"プレイヤー名: {player_name}\n"
                    f"対象拠点: {settlement_name}\n"
                    f"世界データ: {world_payload}\n"
                    "この拠点で自然に発生する複数のクエスト候補を作ってください。"
                ),
            },
        ]
        return self._chat_json(
            "settlement_quest_generator",
            messages,
            max_tokens=900,
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
            self._set_character_presence(character, settlement_name)
            world.characters[character.name] = character
        for index, item in enumerate(_as_list(response.get("adventurers"))):
            character = _character_from_raw(item, index, category="adventurer")
            self._set_character_presence(character, settlement_name)
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
            if quest.name not in self.state.completed_quests:
                self.state.completed_quests.append(quest.name)
            event["reward"] = self._grant_quest_reward(quest)
        quest.flags["finished"] = True
        quest.flags["finish_source"] = source
        quest.log.append(event)
        self.state.world_data.extra.setdefault("quest_finish_events", []).append(event)
        return event

    def _maybe_finish_active_quest_from_response(self, response: dict[str, Any], source: str, action: str) -> dict[str, Any] | None:
        if not self.state.active_quest or not isinstance(response, dict):
            return None
        quest_signal_keys = {
            "quest_finished",
            "quest_completed",
            "complete_quest",
            "completed_quest",
            "quest_failed",
            "quest_abandoned",
            "quest_status",
            "quest_outcome",
        }
        if not any(key in response for key in quest_signal_keys):
            return None
        quest = self._find_quest_by_name(self.state.active_quest)
        if not quest:
            self.state.active_quest = ""
            return None
        status = _quest_explicit_finish_status(response, None)
        if not status:
            return None
        return self._finish_quest(quest, status, source, response)

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
        location = self.state.current_location or self.state.world_data.starting_location or "unknown"
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
                    f"現在地: {location}\n"
                    f"状況: {self.state.log_text(6)}\n"
                    "現在地を表すファンタジーRPG背景画像のSDXLプロンプトを作ってください。"
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
            prompt_parts = ["fantasy RPG background", location, "detailed environment"]
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
            "backend": image.backend,
            "generation_metadata": image.metadata,
            "source_response": _strip_response_metadata(response),
        }
        saved_image = self.save_store.save_background_asset(
            self.state.world_name,
            location,
            Path(image.path),
            prompt_record,
        )
        location_data = self.state.world_data.ensure_location(location)
        location_data.image_path = str(saved_image)
        location_data.prompts = prompt_record
        self.state.last_image_path = str(saved_image)
        if self.state.flags.get("pending_background_location") == location:
            self.state.flags.pop("pending_background_location", None)
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
        saved_base = self.save_store.save_monster_asset(
            self.state.world_name,
            monster.name,
            processed.source_image,
            "base_image.png",
            prompt_record,
        )
        saved_no_bg = self.save_store.save_monster_asset(
            self.state.world_name,
            monster.name,
            processed.no_bg_image,
            "no_bg_image.png",
            prompt_record,
        )
        saved_face = self.save_store.save_monster_asset(
            self.state.world_name,
            monster.name,
            processed.face_image,
            "face_image.png",
            prompt_record,
        )
        saved_border = self.save_store.save_monster_asset(
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
                    "背景除去しやすいよう、単体、全身、明るい単色背景を明示してください。"
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

    def _monster_image_creator(self, monster: MonsterData) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=False, include_monsters=False))
        monster_payload = _ai_json(_monster_ai_context(monster))
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのモンスター画像用SDXLプロンプト担当です。"
                    "Fantasiaのモンスター画像生成相当として、prompt と negative_prompt を持つJSONだけを返してください。"
                    "背景除去しやすいよう、単体、全身、明るい単色背景を明示してください。"
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
        visual_monsters: list[MonsterData] | None = None,
    ) -> dict[str, Any]:
        world_payload = _ai_json(_world_ai_context(self.state.world_data, include_characters=True, include_monsters=True, include_quests=True))
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
            return finish(self.state.log_text(16))
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

        guard_result = self._maybe_start_guard_encounter(action_text, input_type)
        if guard_result:
            return finish(guard_result)

        active_encounter = self._active_encounter()
        if active_encounter:
            return finish(self._resolve_encounter_input(action_text, input_type, active_encounter))

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

        self.state.flags["last_master_ai_finished"] = finished
        self.state.flags["screen_mode"] = "exploration"
        choices = self._augment_location_choices(choices, location)
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
            message=_combat_damage_message(damage, max_hp, action_name="攻撃"),
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
            lines = [_combat_heal_message(actual, skill_name)]
            if result.get("line"):
                lines.append(str(result["line"]))
            calc = {
                "type": "player_skill_heal",
                "skill": skill_name,
                "ability": ability,
                "ability_score": ability_score,
                "power": power,
                "healing": raw_power,
                "actual_healing": actual,
            }
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
                message=_combat_damage_message(damage, max_hp, action_name=skill_name),
            )
            lines = [str(line) for line in result.get("lines", [])]
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
        old_hp = max(0, _safe_int(encounter.get("opponent_hp"), 0))
        max_hp = max(1, _safe_int(encounter.get("opponent_max_hp"), old_hp or 1))
        new_hp = max(0, min(max_hp, old_hp + int(delta)))
        actual_delta = new_hp - old_hp
        encounter["opponent_hp"] = new_hp
        encounter["opponent_max_hp"] = max_hp
        sign = f"+{actual_delta}" if actual_delta > 0 else str(actual_delta)
        name = str(encounter.get("opponent_name") or "相手")
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

    def _apply_npc_combat_damage(
        self,
        encounter: dict[str, Any],
        npc_response: dict[str, Any],
        rewrite_response: dict[str, Any],
    ) -> list[str]:
        if int(encounter.get("opponent_hp") or 0) <= 0:
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
        message = _combat_damage_message(damage, max_hp, action_name=f"{opponent_name}の攻撃")
        event = self._apply_player_hp_delta(-damage, source="npc_attack", reason=opponent_name, encounter=encounter)
        lines = [f"> [戦闘] {message}"]
        if event.get("line"):
            lines.append(str(event["line"]))
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
        player_response = self._referee_player_attack_new_new(action, input_type, encounter)
        self._strip_game_controlled_hp_updates(player_response, target="opponent")
        self._apply_encounter_update(encounter, player_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, player_response, "opponent")
        self._apply_player_attack_damage(encounter, player_response, action)
        return self._resolve_npc_turn(action, input_type, encounter, player_response, "referee_player_attack_new_new")

    def _resolve_player_any_input(self, action: str, input_type: str, encounter: dict[str, Any]) -> str:
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
        status_lines.extend(self._apply_response_progress_effects(player_response, player_manager))
        opponent = self._encounter_opponent(encounter)
        status_lines.extend(
            self._apply_response_world_state_effects(
                player_response,
                player_manager,
                default_character=opponent if isinstance(opponent, CharacterData) else None,
                default_location=str(encounter.get("location") or self.state.current_location),
            )
        )
        if int(encounter.get("opponent_hp") or 0) <= 0:
            npc_response = {"finished": True, "narration": ""}
        else:
            npc_response = self._referee_npc(action, input_type, encounter, player_response)
        self._strip_game_controlled_hp_updates(npc_response, target="player")
        self._apply_encounter_update(encounter, npc_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, npc_response, "player")
        status_lines.extend(self._apply_response_hp_effects(npc_response, "referee_npc", encounter=encounter))
        status_lines.extend(self._apply_response_sp_effects(npc_response, "referee_npc", encounter=encounter))
        status_lines.extend(self._apply_response_progress_effects(npc_response, "referee_npc"))
        status_lines.extend(
            self._apply_response_world_state_effects(
                npc_response,
                "referee_npc",
                default_character=opponent if isinstance(opponent, CharacterData) else None,
                default_location=str(encounter.get("location") or self.state.current_location),
            )
        )
        if int(encounter.get("opponent_hp") or 0) <= 0:
            rewrite_response = {}
        else:
            rewrite_response = self._referee_npc_rewrite(action, input_type, encounter, player_response, npc_response)
        self._strip_game_controlled_hp_updates(rewrite_response, target="player")
        self._apply_encounter_update(encounter, rewrite_response.get("encounter_update"))
        self._apply_response_implied_statuses(encounter, rewrite_response, "player")
        status_lines.extend(self._apply_response_hp_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
        status_lines.extend(self._apply_response_sp_effects(rewrite_response, "referee_npc_rewrite", encounter=encounter))
        status_lines.extend(self._apply_response_progress_effects(rewrite_response, "referee_npc_rewrite"))
        status_lines.extend(
            self._apply_response_world_state_effects(
                rewrite_response,
                "referee_npc_rewrite",
                default_character=opponent if isinstance(opponent, CharacterData) else None,
                default_location=str(encounter.get("location") or self.state.current_location),
            )
        )
        status_lines.extend(self._apply_npc_combat_damage(encounter, npc_response, rewrite_response))
        status_lines.extend(self._tick_encounter_status_effects(encounter))
        outcome = self._apply_encounter_outcome(encounter)
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
            or _as_bool(npc_response.get("finished"))
            or _as_bool(npc_response.get("should_end_encounter"))
            or _as_bool(rewrite_response.get("finished"))
            or _as_bool(outcome.get("ended"))
        )
        game_over = _as_bool(outcome.get("game_over"))
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
                    "weakness_multiplier from 0.0 to 3.0. If it does not attack, set offensive false."
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
        encounter_payload = json.dumps(_strip_encounter_log(encounter), ensure_ascii=False)
        player_payload = json.dumps(_strip_response_metadata(player_response), ensure_ascii=False)
        npc_payload = json.dumps(_strip_response_metadata(npc_response), ensure_ascii=False)
        opponent_payload = json.dumps(self._encounter_opponent_payload(encounter), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "あなたはAI駆動RPGのNPC行動リライト担当です。"
                    "Fantasiaのreferee_npc_rewrite相当として、referee_npcの判定を"
                    "世界観、NPCの性格、プレイヤーの降伏/交渉などの文脈に合う自然な描写へ整えてください。"
                    "判定が文脈に反して単調な攻撃になっている場合は、理由を保ったまま妥当な行動に補正してください。"
                    "必ず narration, choices を持つJSONだけを返してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"敵対者: {encounter.get('opponent_name')}\n"
                    f"敵対者データ: {opponent_payload}\n"
                    f"戦闘状態: {encounter_payload}\n"
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"プレイヤー側判定: {player_payload}\n"
                    f"NPC側判定: {npc_payload}\n"
                    "このNPC/敵の行動を自然文として整え、必要なら文脈に合うように補正してください。"
                ),
            },
        ]
        return self._chat_json(
            "referee_npc_rewrite",
            messages,
            max_tokens=700,
            world_name=self.state.world_name,
            player_name=self.state.player_name,
        )

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

    def _find_or_create_encounter_opponent(self, action: str) -> tuple[str, str]:
        text = action.strip()
        current_location = self.state.current_location or self.state.world_data.starting_location
        for character in self.state.world_data.characters.values():
            if character.flags.get("is_player"):
                continue
            if not _actor_present_at(character.location, character.state, character.flags, current_location):
                continue
            if not self._character_matches_active_facility(character):
                continue
            if character.name and character.name in text:
                return "character", character.name
        for monster in self.state.world_data.monsters.values():
            if not _actor_present_at(monster.location, monster.state, monster.flags, current_location):
                continue
            if monster.name and monster.name in text:
                return "monster", monster.name
        target_name = _clean_generated_name(_extract_attack_target(text), "", kind="monster")
        if not target_name and self.state.world_data.monsters:
            for monster in self.state.world_data.monsters.values():
                if _actor_present_at(monster.location, monster.state, monster.flags, current_location):
                    return "monster", monster.name
        target_name = target_name or "硝子森の影"
        if target_name not in self.state.world_data.monsters:
            self.state.world_data.monsters[target_name] = MonsterData(
                name=target_name,
                category="wild_encounter",
                description="硝子森の霧から現れた、慎重で縄張り意識の強い影。",
                traits=[
                    {"name": "慎重", "effect": "相手が降伏した場合は即座に殺さず、武装解除を優先する"},
                    {"name": "縄張り意識", "effect": "追い払うことを優先する"},
                ],
                flags={"source": "referee_player_attack_new_new"},
            )
            self._set_monster_presence(self.state.world_data.monsters[target_name], current_location)
        else:
            self._set_monster_presence(self.state.world_data.monsters[target_name], current_location)
        return "monster", target_name

    def _encounter_opponent_payload(self, encounter: dict[str, Any]) -> dict[str, Any]:
        name = str(encounter.get("opponent_name") or "")
        opponent_type = str(encounter.get("opponent_type") or "")
        if opponent_type == "character" and name in self.state.world_data.characters:
            return self.state.world_data.characters[name].to_dict()
        if name in self.state.world_data.monsters:
            return self.state.world_data.monsters[name].to_dict()
        return {"name": name, "type": opponent_type}

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
                encounter[base_key] = max(0, int(encounter.get(base_key, 0) or 0) + delta) if base_key.endswith("_hp") else int(encounter.get(base_key, 0) or 0) + delta
                continue
            if text_key in {"player_hp", "opponent_hp"}:
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
        if isinstance(opponent, (CharacterData, MonsterData)):
            return opponent.status_effects
        raw = (encounter or {}).get("opponent_status_effects")
        return raw if isinstance(raw, list) else []

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
        if isinstance(opponent, (CharacterData, MonsterData)):
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
        for key in ("monster_status_effect", "monster_status_effects"):
            if response.get(key):
                entries.extend(self._targeted_status_entries(response.get(key), "monster", context_target))
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
                "monster": "monster",
                "monsters": "monster",
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
                if isinstance(opponent, MonsterData):
                    return ("monster", opponent.name, opponent.status_effects, opponent.name)
                if isinstance(opponent, CharacterData):
                    return ("character", opponent.name, opponent.status_effects, opponent.name)
        monster = self.state.world_data.monsters.get(text)
        if monster:
            return ("monster", monster.name, monster.status_effects, monster.name)
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
        if kind == "monster" and name in self.state.world_data.monsters:
            self.state.world_data.monsters[name].status_effects = list(status_list)

    def _enrich_persistent_status_effect(self, effect: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(effect)
        enriched.setdefault("started_day", self.state.day)
        enriched.setdefault("started_location", self.state.current_location)
        if enriched.get("long_term") or enriched.get("persistent") or enriched.get("permanent"):
            enriched.setdefault("scope", "character")
        return enriched

    def _tick_encounter_status_effects(self, encounter: dict[str, Any]) -> list[str]:
        lines: list[str] = []
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
        return self._make_action_roll(
            "craft",
            purpose="craft",
            forced_ability="dex",
            forced_target=_craft_roll_target(ingredients or []),
        )

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

    def _encounter_opponent(self, encounter: dict[str, Any]) -> CharacterData | MonsterData | None:
        name = str(encounter.get("opponent_name") or "")
        if str(encounter.get("opponent_type") or "") == "character":
            return self.state.world_data.characters.get(name)
        return self.state.world_data.monsters.get(name)

    def _is_game_over(self) -> bool:
        return bool(self.state.flags.get("game_over"))

    def _update_encounter_presence(self, encounter: dict[str, Any], state: str) -> None:
        location = str(encounter.get("location") or self.state.current_location or "")
        opponent_name = str(encounter.get("opponent_name") or "")
        opponent_type = str(encounter.get("opponent_type") or "")
        if opponent_type == "monster":
            monster = self.state.world_data.monsters.get(opponent_name)
            if monster:
                self._set_monster_presence(monster, location, state)
        elif opponent_type == "character":
            character = self.state.world_data.characters.get(opponent_name)
            if character:
                self._set_character_presence(character, location, state)

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
        return ["攻撃", "スキル", "行動", "逃走"]
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
        discovered_location = self._apply_discovered_location(response)
        generated_quests = self._apply_field_event_quests(response, location)
        generated_actors = self._apply_field_event_actors(response, location)
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
        self.state.flags["screen_mode"] = "exploration"
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

    def _apply_discovered_location(self, response: dict[str, Any]) -> str:
        raw = response.get("discovered_location")
        if not raw:
            return ""
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("location") or raw.get("title") or "").strip()
            if not name:
                return ""
            description = str(raw.get("description") or raw.get("overview") or raw.get("summary") or "")
            kind = _infer_world_location_kind(raw, name, description)
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
        kind = _infer_world_location_kind({}, name, location.description)
        location.extra["location_kind"] = kind
        self._set_location_graph_node(self.state.world_data, name, kind=kind, location=location)
        self._connect_world_locations(self.state.world_data, self.state.current_location, name)
        return name

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

        raw_monsters = _as_list(response.get("monsters") or response.get("monster") or response.get("enemies") or response.get("enemy"))
        for item in raw_monsters:
            monster = _monster_from_raw(item, len(self.state.world_data.monsters) + len(generated))
            monster.name = _unique_monster_name(self.state.world_data, monster.name)
            monster.flags.setdefault("source", "field_event_evaluator")
            self._set_monster_presence(monster, location)
            self.state.world_data.monsters[monster.name] = monster
            generated.append({"type": "monster", "name": monster.name})
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

    def _start_quest(self, action: str, input_type: str, quest: QuestData) -> str:
        previous_location = self.state.current_location
        response = self._quest_starter(quest)
        quest.status = "active"
        self.state.active_quest = quest.name
        objective = str(response.get("objective") or "")
        if objective:
            quest.extra["objective"] = objective

        narration = str(response.get("narration") or response.get("text") or f"クエスト「{quest.name}」を開始した。")
        location = self._quest_starter_location(action, response)
        choices = self._augment_location_choices(_as_str_list(response.get("choices")), location)
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
        if status_lines:
            self.state.display_log.extend(status_lines)
        self._apply_visual_intent(response, "quest_starter", location, previous_location)
        self.save_game()
        return self.state.log_text(16)

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
                ),
            },
            {
                "role": "user",
                "content": (
                    f"世界データ: {world_payload}\n"
                    f"クエスト名: {quest.name}\n"
                    f"クエストデータ: {quest_payload}\n"
                    "このクエストの導入文、最初の目標、選択肢を作ってください。"
                    "まだ目的地へは移動せず、まだ依頼は完了していません。"
                ),
            },
        ]
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
        if _is_quest_abandon_action(action):
            narration = f"依頼「{quest.name}」から撤退した。"
            location = self.state.current_location or self.state.world_data.starting_location
            choices = self._location_default_choices(location)
            self.state.flags["screen_mode"] = "exploration"
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
        movement_response = event_resolution or referee
        movement_result = self._normalize_world_response_location(action, input_type, movement_response, raw_location)
        location = str(movement_result.get("location") or raw_location)
        movement_narration = [str(line) for line in movement_result.get("narration_lines", []) if str(line).strip()]
        if movement_narration:
            narration = "\n".join([narration, *movement_narration]).strip()
        choices = self._augment_location_choices(
            _as_str_list((event_resolution or {}).get("choices") or referee.get("choices")),
            location,
        )
        finished = _as_bool(referee.get("finished")) or _as_bool((event_resolution or {}).get("finished"))
        inferred_finish_status = _infer_quest_finish_status(quest, action, referee, event_resolution, narration, location)
        if inferred_finish_status:
            finished = True
            finish_status = inferred_finish_status
            referee.setdefault("finished", True)
            referee.setdefault("quest_status", finish_status)
        else:
            finish_status = _quest_finish_status(action, referee, event_resolution) if finished else ""
            if finished and not finish_status:
                finished = False

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

        self.state.flags["screen_mode"] = "exploration"
        self.state.append_turn(action, narration, location, choices, input_type=input_type)
        self._set_player_presence(location)
        self._append_action_roll_log(action_roll)
        visual_response = event_resolution or referee
        status_lines = self._apply_response_status_effects(referee, "quest_referee_with_free_action", default_target="player")
        status_lines.extend(str(line) for line in movement_result.get("status_lines", []) if str(line).strip())
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
                    f"入力種別: {input_type}\n"
                    f"プレイヤー行動: {action}\n"
                    f"game_side_action_roll: {action_roll_payload}\n"
                    "この行動がクエストをどう進めるか判定してください。"
                ),
            },
        ]
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

    def _monster_for_image(self, monster_name: str | None) -> MonsterData:
        if monster_name:
            monster = self.state.world_data.monsters.get(monster_name)
            if monster:
                return monster
        if self.state.world_data.monsters:
            return next(iter(self.state.world_data.monsters.values()))
        monster = MonsterData(
            name="硝子森の影",
            category="wild_encounter",
            description="霧と雨音の中から現れる、硝子森に棲む影のような魔物。",
            traits=[
                {"name": "慎重", "effect": "相手の動きを見てから行動する。"},
                {"name": "霧まとい", "effect": "距離を取り、姿をぼかす。"},
            ],
            flags={"source": "image_pipeline_fallback"},
        )
        self._set_monster_presence(monster, self.state.current_location or self.state.world_data.starting_location)
        self.state.world_data.monsters[monster.name] = monster
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
        if "クエスト" in text or "依頼" in text:
            for quest in self.state.world_data.quests:
                if quest.status in {"available", ""}:
                    return quest
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
        attempt_messages = base_messages
        last_response: Any = {}
        last_errors: list[str] = []

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
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


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
        "plain light background",
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


def _monster_prompt_parts(monster: MonsterData) -> list[str]:
    parts = [
        "masterpiece",
        "best quality",
        "fantasy RPG monster",
        "single creature",
        "full body",
        "plain light background",
        monster.name,
        monster.category,
        monster.description,
    ]
    parts.extend(_as_str_list(monster.prompts.get("image_generation_prompt")))
    parts.extend(_monster_visual_feature_parts(monster))
    return _dedupe_strs(parts)


def _monster_visual_feature_parts(monster: MonsterData) -> list[str]:
    parts = [
        monster.name,
        monster.category,
        monster.description,
    ]
    parts.extend(_dict_list_visual_parts(monster.traits, ("name", "description", "effect", "severity", "visual", "appearance")))
    parts.extend(_dict_list_visual_parts(monster.skills, ("name", "description", "effect", "element", "skill_type", "visual_effect")))
    return _dedupe_strs(parts)[:28]


def _cg_subject_prompt_parts(characters: list[CharacterData], monsters: list[MonsterData]) -> list[str]:
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


def _visual_subjects_context(characters: list[CharacterData], monsters: list[MonsterData]) -> dict[str, Any]:
    return _drop_empty(
        {
            "characters": [
                _character_ai_context(character, details=True)
                for character in characters[:5]
            ],
            "monsters": [
                _monster_ai_context(monster, details=True)
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
        return {"id": "paralyzed", "name": "麻痺", "duration": 2, "damage_per_turn": 0, "description": "体がうまく動かない。"}
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


def _is_player_power_actor(actor: CharacterData | MonsterData) -> bool:
    if not isinstance(actor, CharacterData):
        return False
    category = str(actor.category or "").lower()
    role = str(actor.role or "").lower()
    source = str(actor.flags.get("source") or actor.extra.get("source") or "").lower()
    return bool(actor.flags.get("is_player") or role == "player" or category == "player" or source.startswith("character_setup"))


def _actor_power_budget(actor: CharacterData | MonsterData) -> int:
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
    actor: CharacterData | MonsterData,
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


def _normalise_actor_power_loadout(actor: CharacterData | MonsterData) -> None:
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
            return max(0, _safe_int(payload.get(key), 0))
    return 0


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
            return value
    text = f"{name}\n{description}".lower()
    if _looks_like_facility_location_name(name):
        return "facility"
    if any(word in text for word in ("dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair", "洞窟", "迷宮", "遺跡", "鉱山")):
        return "dungeon"
    if any(word in text for word in ("town", "village", "city", "settlement", "村", "街", "町", "都市", "宿場")):
        return "settlement"
    if any(word in text for word in ("forest", "swamp", "mountain", "plain", "wilderness", "森", "沼", "山", "荒野", "平原")):
        return "wilderness"
    return "landmark"


def _world_kind_is_settlement(kind: str) -> bool:
    return str(kind or "").strip().lower() in {"settlement", "town", "village", "city", "hamlet", "base"}


def _world_location_allows_world_map_departure(world: WorldData, name: str) -> bool:
    location = world.locations.get(str(name or "").strip())
    if location is None:
        return False
    if _world_location_is_world_map_exit(location):
        return True
    return not _world_location_blocks_world_map_departure(location)


def _world_location_blocks_world_map_departure(location: LocationData) -> bool:
    kind = str(location.extra.get("location_kind") or "").strip().lower()
    danger = _safe_int(location.extra.get("danger_level"), 0)
    if kind in {"dungeon", "cave", "ruin", "labyrinth", "mine", "crypt", "lair"}:
        return True
    if kind in {"wilderness", "forest", "swamp", "mountain", "wilds"} and danger >= 2:
        return True
    if location.flags.get("dangerous") or location.flags.get("dungeon"):
        return True
    return False


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
    return rng.choice(("wilderness", "landmark", "dungeon", "settlement", "wilderness"))


def _fallback_world_location_name(kind: str, index: int) -> str:
    prefix = {
        "settlement": "Settlement",
        "dungeon": "Dungeon",
        "wilderness": "Wilds",
        "landmark": "Landmark",
        "facility": "Facility",
    }.get(kind, "Location")
    return f"{prefix} {index:02d}"


def _fallback_world_location_description(kind: str, danger: int) -> str:
    labels = {
        "settlement": "A settled place connected to the local roads.",
        "dungeon": "A dangerous site where stronger threats may appear.",
        "wilderness": "Open wilderness between safer places.",
        "landmark": "A notable place on the road.",
    }
    return f"{labels.get(kind, 'A location in the world.')} Danger {danger}."


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
    movement_words = ("go", "move", "travel", "head", "enter", "nearby", "around", "探", "行", "向", "入", "近く", "周辺")
    location_words = (
        "dungeon",
        "cave",
        "ruin",
        "forest",
        "tower",
        "mine",
        "村",
        "街",
        "町",
        "洞窟",
        "迷宮",
        "森",
        "塔",
        "遺跡",
        "鉱山",
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
        result.insert(0, QUEST_BOARD_CHOICE_LABEL)
    return _exploration_choices(result)


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


def _is_surprise_attack_action(action: str) -> bool:
    text = action.strip().lower()
    return any(keyword in text for keyword in ("不意打ち", "奇襲", "先制", "背後から", "ambush", "surprise", "sneak attack"))


def _is_skill_action(action: str) -> bool:
    text = action.strip().lower()
    return any(keyword in text for keyword in ("スキル", "skill", "spell", "魔法", "術", "技:"))


def _is_escape_action(action: str) -> bool:
    text = action.strip().lower()
    return any(keyword in text for keyword in ("逃走", "逃げ", "離脱", "退却", "run away", "escape", "flee"))


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
    separators = ("を攻撃", "に攻撃", "を斬", "を撃", "を殴", "を刺", "と戦", "を襲")
    for separator in separators:
        if separator in text:
            target = text.split(separator, 1)[0].strip()
            return _strip_action_prefix(target)
    return ""


def _strip_action_prefix(text: str) -> str:
    prefixes = ("現れた", "目の前の", "近くの", "その", "敵の")
    result = text.strip()
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :].strip()
    return result


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
    if name == world.world_name or name in world.characters or name in world.monsters:
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
    monster_limit: int = 8,
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
    if include_monsters:
        data["monsters"] = [
            _monster_ai_context(monster)
            for monster in list(world.monsters.values())[:monster_limit]
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


def _monster_ai_context(monster: MonsterData, *, details: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": monster.name,
        "category": monster.category,
        "description": _short_text(monster.description, 700 if details else 260),
        "skill_trait_power_budget": _actor_power_budget(monster),
        "skill_trait_power_used": _entry_power_total(monster.traits) + _entry_power_total(monster.skills),
    }
    if details:
        data["traits"] = _compact_value(monster.traits, max_chars=800)
        data["skills"] = _compact_value(monster.skills, max_chars=900)
        data["status_effects"] = _compact_value(monster.status_effects, max_chars=500)
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
        "neighboring_settlement": quest.neighboring_settlement,
        "choices": [str(item) for item in quest.choices[:6]],
        "reward": _compact_value(quest.extra.get("reward", {}), max_chars=600),
    }
    if include_log and quest.log:
        data["recent_log"] = _compact_value(quest.log[-6:], max_chars=1400)
    if include_extra and quest.extra:
        data["details"] = _compact_value(quest.extra, max_chars=2400)
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


def _quest_from_raw(item: Any, index: int) -> QuestData:
    if isinstance(item, dict):
        data = dict(item)
        data["name"] = str(data.get("name") or data.get("quest_name") or data.get("title") or f"Quest {index + 1}")
        data["overview"] = str(data.get("overview") or data.get("description") or data.get("summary") or "")
        return QuestData.from_dict(data, default_name=f"Quest {index + 1}")
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


def _monster_from_raw(item: Any, index: int) -> MonsterData:
    if isinstance(item, dict):
        data = dict(item)
        name = _clean_generated_name(
            data.get("name") or data.get("monster_name") or data.get("enemy_name"),
            f"Monster {index + 1}",
            kind="monster",
        )
        category = str(data.get("category") or data.get("monster_category") or data.get("type") or "wild_encounter")
        description = str(data.get("description") or data.get("summary") or data.get("overview") or "")
        monster = MonsterData.from_dict(data, default_name=name)
        monster.name = name
        monster.category = category
        if description and not monster.description:
            monster.description = description
        if data.get("image_generation_prompt"):
            monster.prompts["image_generation_prompt"] = _as_str_list(data.get("image_generation_prompt"))
        if data.get("skills"):
            monster.skills = [skill for skill in (_normalise_skill(item) for item in _as_list(data.get("skills"))) if skill.get("name")]
        if data.get("traits"):
            monster.traits = [trait for trait in (_normalise_trait(item) for item in _as_list(data.get("traits"))) if trait.get("name")]
        _normalise_actor_power_loadout(monster)
        monster.extra.setdefault("raw_field_event_monster", data)
        return monster
    return MonsterData(
        name=f"Monster {index + 1}",
        category="wild_encounter",
        description=str(item),
    )


def _clean_generated_name(value: Any, fallback: str, *, kind: str = "actor") -> str:
    text = str(value or "").strip()
    text = _strip_generated_name_notes(text)
    text = re.sub(r"^[\s\"':：,，、。・\-~～|/\\]+|[\s\"':：,，、。・\-~～|/\\]+$", "", text)
    if not _is_valid_generated_name(text):
        return fallback
    if kind == "monster" and text.lower() in {"enemy", "monster", "foe"}:
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


def _unique_monster_name(world: WorldData, name: str) -> str:
    base = _clean_generated_name(name, "Monster", kind="monster")
    if base not in world.monsters:
        return base
    suffix = 2
    while f"{base} {suffix}" in world.monsters:
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


def _actor_state_is_present(value: str) -> bool:
    actor_state = str(value or "present").strip().lower()
    if not actor_state:
        actor_state = "present"
    return actor_state not in {"absent", "gone", "left", "hidden", "dead", "ended", "inactive", "removed"}
