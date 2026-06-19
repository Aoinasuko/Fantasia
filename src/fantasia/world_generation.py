from __future__ import annotations

import json
import random
import re
from typing import Any

from .world_model import LocationData, WorldData


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "??"}
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _short_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "... [truncated]"


def _character_state_is_dead(character: Any) -> bool:
    flags = getattr(character, "flags", {}) if isinstance(getattr(character, "flags", {}), dict) else {}
    state = str(getattr(character, "state", "") or flags.get("state") or "").strip().lower()
    if state in {"dead", "corpse", "killed"}:
        return True
    if flags.get("dead") is True or flags.get("alive") is False:
        return True
    return False


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
