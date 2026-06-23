from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from .paths import NPC_TEMPLATE_DIR, ROOT


NPC_TEMPLATE_CATEGORY_IDS = (
    "enemy_common",
    "enemy_unique",
    "npc_common",
    "npc_unique",
)
ENEMY_NPC_TEMPLATE_CATEGORIES = ("enemy_common", "enemy_unique")
FRIENDLY_NPC_TEMPLATE_CATEGORIES = ("npc_common", "npc_unique")
NPC_TEMPLATE_ATTRIBUTE_KEYS = ("str", "dex", "con", "int", "wis", "cha")
NPC_TEMPLATE_LOAD_ERRORS: list[str] = []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_str_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _template_dirs() -> list[Path]:
    candidates = [NPC_TEMPLATE_DIR, ROOT / "Data" / "Template" / "NPC"]
    result: list[Path] = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def _template_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in NPC_TEMPLATE_CATEGORY_IDS else ""


def _normalise_attributes(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key in NPC_TEMPLATE_ATTRIBUTE_KEYS:
        if key in value:
            result[key] = max(1, _safe_int(value.get(key), 1))
    return result


def _normalise_named_entries(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            entry = deepcopy(item)
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            result.append(entry)
        else:
            text = str(item or "").strip()
            if text:
                result.append({"name": text})
    return result


def _trait_entries(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        result.append({"name": name, "desc": str(item.get("desc") or "").strip()})
    return result


def _normalise_attacks(value: Any) -> list[dict[str, Any]]:
    attacks: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("attack") or "").strip()
            if not name:
                continue
            attacks.append({"name": name, "type": str(item.get("type") or item.get("element") or "physical").strip()})
        else:
            text = str(item or "").strip()
            if text:
                attacks.append({"name": text, "type": "physical"})
    return attacks


def _normalise_resistance(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        element = str(item.get("type") or "").strip()
        if not element:
            continue
        amount = max(0.0, min(1.0, _safe_float(item.get("amount"), 0.0)))
        result.append({"type": element, "amount": amount})
    return result


def _normalise_npc_template(raw: Any, source_path: Path) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    category = _template_category(raw.get("category"))
    template_id = str(raw.get("id") or raw.get("template_id") or "").strip()
    role = str(raw.get("role") or raw.get("title") or "").strip()
    name = str(raw.get("name") or raw.get("base_name") or role or template_id).strip()
    if not category or not template_id or not name:
        return None
    image_prompt = _as_str_list(raw.get("image_prompt") or raw.get("image_generation_prompt"))
    skills_defined = "skills" in raw
    traits_defined = "traits" in raw
    return {
        "id": template_id,
        "name": name,
        "role": role or name,
        "look": str(raw.get("look") or raw.get("appearance") or "").strip(),
        "personality": str(raw.get("personality") or "").strip(),
        "image_prompt": image_prompt,
        "image_generation_prompt": image_prompt,
        "gender": str(raw.get("gender") or "").strip(),
        "age": str(raw.get("age") or "").strip(),
        "age_min": max(0, _safe_int(raw.get("age_min"), 0)),
        "age_max": max(0, _safe_int(raw.get("age_max"), 0)),
        "usenamelist": bool(raw.get("usenamelist")),
        "rescued": bool(raw.get("rescued")),
        "category": category,
        "level": max(0, _safe_int(raw.get("level"), 0)),
        "atk": max(0, _safe_int(raw.get("atk"), 0)),
        "def": max(0, _safe_int(raw.get("def", raw.get("defense")), 0)),
        "attributes": _normalise_attributes(raw.get("attributes")),
        "resistance": _normalise_resistance(raw.get("resistance")),
        "attacks": _normalise_attacks(raw.get("attacks")),
        "skills": _normalise_named_entries(raw.get("skills")) if skills_defined else None,
        "traits": _trait_entries(raw.get("traits")) if traits_defined else None,
        "skills_defined": skills_defined,
        "traits_defined": traits_defined,
        "source_path": str(source_path),
        "raw": deepcopy(raw),
    }


def _load_npc_templates() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = {category: [] for category in NPC_TEMPLATE_CATEGORY_IDS}
    NPC_TEMPLATE_LOAD_ERRORS.clear()
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for template_path in sorted(directory.glob("*.json")):
            try:
                raw_items = json.loads(template_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                NPC_TEMPLATE_LOAD_ERRORS.append(f"{template_path}: {exc}")
                continue
            if not isinstance(raw_items, list):
                NPC_TEMPLATE_LOAD_ERRORS.append(f"{template_path}: root must be a JSON array")
                continue
            for raw in raw_items:
                template = _normalise_npc_template(raw, template_path)
                if template is None:
                    continue
                loaded.setdefault(str(template["category"]), []).append(template)
    return {category: values for category, values in loaded.items() if values}


NPC_TEMPLATES = _load_npc_templates()
NPC_TEMPLATES_BY_ID = {
    str(template.get("id")): template
    for templates in NPC_TEMPLATES.values()
    for template in templates
    if str(template.get("id") or "").strip()
}


def npc_template_by_id(template_id: Any) -> dict[str, Any] | None:
    template = NPC_TEMPLATES_BY_ID.get(str(template_id or "").strip())
    return deepcopy(template) if template else None


def used_npc_template_ids(world: Any) -> set[str]:
    result: set[str] = set()
    characters = getattr(world, "characters", {}) or {}
    if not isinstance(characters, dict):
        return result
    for character in characters.values():
        for source in (getattr(character, "extra", {}), getattr(character, "flags", {})):
            if not isinstance(source, dict):
                continue
            for key in ("npc_template_id", "template_id", "source_template_id"):
                value = str(source.get(key) or "").strip()
                if value:
                    result.add(value)
    return result


def _template_is_unique(template: dict[str, Any]) -> bool:
    return str(template.get("category") or "").endswith("_unique")


def npc_templates_for_categories(
    categories: list[str] | tuple[str, ...],
    *,
    danger_level: int = 0,
    used_ids: set[str] | None = None,
    rescued: bool | None = None,
) -> list[dict[str, Any]]:
    used_ids = used_ids or set()
    level = max(0, _safe_int(danger_level, 0))
    candidates: list[dict[str, Any]] = []
    for category in categories:
        for template in NPC_TEMPLATES.get(str(category), []):
            if _template_is_unique(template) and str(template.get("id") or "") in used_ids:
                continue
            if rescued is not None and bool(template.get("rescued")) != bool(rescued):
                continue
            if _safe_int(template.get("level"), 0) <= level:
                candidates.append(template)
    if candidates:
        return [deepcopy(item) for item in candidates]
    for category in categories:
        for template in NPC_TEMPLATES.get(str(category), []):
            if _template_is_unique(template) and str(template.get("id") or "") in used_ids:
                continue
            if rescued is not None and bool(template.get("rescued")) != bool(rescued):
                continue
            candidates.append(template)
    return [deepcopy(item) for item in candidates]


def npc_template_ids_from_payloads(*payloads: Any) -> list[str]:
    keys = {
        "npc_template_id",
        "template_id",
        "target_npc_template_id",
        "target_template_id",
        "objective_npc_template_id",
        "objective_template_id",
        "enemy_template_id",
        "monster_template_id",
        "boss_template_id",
        "blocker_template_id",
        "rescue_target_template_id",
        "defeat_target_template_id",
        "delivery_target_template_id",
        "target_id",
        "enemy_id",
        "monster_id",
        "boss_id",
    }
    found: list[str] = []

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 4:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key or "").strip()
                if key_text in keys:
                    text = str(item or "").strip()
                    if text and text in NPC_TEMPLATES_BY_ID and text not in found:
                        found.append(text)
                elif key_text in {"destination_hint", "destination", "objective", "target", "enemy", "monster", "boss", "extra"}:
                    visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value[:20]:
                visit(item, depth + 1)

    for payload in payloads:
        visit(payload)
    return found


def choose_npc_template(
    categories: list[str] | tuple[str, ...],
    *,
    danger_level: int = 0,
    preferred_ids: list[str] | tuple[str, ...] | None = None,
    used_ids: set[str] | None = None,
    seed: str = "",
    rescued: bool | None = None,
) -> dict[str, Any] | None:
    used_ids = used_ids or set()
    for template_id in preferred_ids or ():
        template = NPC_TEMPLATES_BY_ID.get(str(template_id or "").strip())
        if not template:
            continue
        if str(template.get("category") or "") not in set(categories):
            continue
        if _template_is_unique(template) and str(template.get("id") or "") in used_ids:
            continue
        if rescued is not None and bool(template.get("rescued")) != bool(rescued):
            continue
        return deepcopy(template)
    candidates = npc_templates_for_categories(categories, danger_level=danger_level, used_ids=used_ids, rescued=rescued)
    if not candidates:
        return None
    rng = random.Random(seed or f"npc-template:{danger_level}:{','.join(categories)}")
    return deepcopy(rng.choice(candidates))


def npc_template_ai_context(template: dict[str, Any] | None) -> dict[str, Any]:
    if not template:
        return {}
    return {
        "id": template.get("id"),
        "name": template.get("name"),
        "role": template.get("role"),
        "look": template.get("look"),
        "personality": template.get("personality"),
        "image_prompt": template.get("image_prompt") or [],
        "gender": template.get("gender"),
        "age": template.get("age"),
        "age_min": template.get("age_min"),
        "age_max": template.get("age_max"),
        "category": template.get("category"),
        "level": template.get("level"),
        "atk": template.get("atk"),
        "def": template.get("def"),
        "attributes": template.get("attributes") or {},
        "resistance": template.get("resistance") or [],
        "attacks": template.get("attacks") or [],
        "skills": template.get("skills") if template.get("skills_defined") else "generate_if_needed",
        "traits": template.get("traits") if template.get("traits_defined") else "generate_if_needed",
        "usenamelist": bool(template.get("usenamelist")),
        "rescued": bool(template.get("rescued")),
    }


def npc_template_prompt_summaries(
    categories: list[str] | tuple[str, ...],
    *,
    danger_level: int = 0,
    used_ids: set[str] | None = None,
    limit: int = 12,
    rescued: bool | None = None,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for template in npc_templates_for_categories(categories, danger_level=danger_level, used_ids=used_ids, rescued=rescued)[: max(0, limit)]:
        summaries.append(
            {
                "id": template.get("id"),
                "name": template.get("name"),
                "role": template.get("role"),
                "category": template.get("category"),
                "level": template.get("level"),
                "look": template.get("look"),
                "personality": template.get("personality"),
                "attacks": template.get("attacks") or [],
                "resistance": template.get("resistance") or [],
                "usenamelist": bool(template.get("usenamelist")),
                "rescued": bool(template.get("rescued")),
            }
        )
    return summaries


def _enemy_stat_multiplier(enemy_strength: str, rng: random.Random) -> float:
    setting = str(enemy_strength or "normal").strip().lower()
    if setting == "weak":
        return 1.0 + rng.uniform(-0.50, 0.0)
    if setting == "strong":
        return 1.0 + rng.uniform(0.0, 0.50)
    return 1.0 + rng.uniform(-0.20, 0.20)


def _resolved_gender(template: dict[str, Any], rng: random.Random) -> str:
    gender = str(template.get("gender") or "").strip()
    if gender.lower() == "random":
        return rng.choice(["male", "female"])
    return gender


def _resolved_age(template: dict[str, Any], rng: random.Random) -> str:
    age = str(template.get("age") or "").strip()
    if age:
        return age
    age_min = _safe_int(template.get("age_min"), 0)
    age_max = _safe_int(template.get("age_max"), 0)
    if age_min > 0 and age_max >= age_min:
        return str(rng.randint(age_min, age_max))
    return ""


def npc_template_to_character_payload(
    template: dict[str, Any] | None,
    *,
    danger_level: int = 0,
    enemy_strength: str = "normal",
    seed: str = "",
    hostile: bool | None = None,
    boss: bool = False,
) -> dict[str, Any]:
    if not template:
        return {}
    rng = random.Random(seed or f"npc-template-payload:{template.get('id')}:{danger_level}")
    danger = max(0, _safe_int(danger_level, 0))
    category = str(template.get("category") or "")
    enemy = category in ENEMY_NPC_TEMPLATE_CATEGORIES
    multiplier = _enemy_stat_multiplier(enemy_strength, rng) if enemy else 1.0
    attack = int(round(max(0, _safe_int(template.get("atk"), 0) + danger) * multiplier))
    defense = int(round(max(0, _safe_int(template.get("def"), 0) + danger) * multiplier))
    if boss:
        attack = max(1, int(round(attack * 1.25)))
        defense = max(0, int(round(defense * 1.25)))
    attributes = {
        key: max(1, _safe_int((template.get("attributes") or {}).get(key), 10) + danger // 2)
        for key in NPC_TEMPLATE_ATTRIBUTE_KEYS
    }
    payload: dict[str, Any] = {
        "name": str(template.get("name") or template.get("id") or "NPC"),
        "role": str(template.get("role") or template.get("name") or ""),
        "category": "enemy_npc" if enemy else "npc",
        "level": max(1, _safe_int(template.get("level"), 1)),
        "gender": _resolved_gender(template, rng),
        "age": _resolved_age(template, rng),
        "personality": str(template.get("personality") or ""),
        "look": str(template.get("look") or ""),
        "description": str(template.get("look") or template.get("personality") or ""),
        "image_generation_prompt": _as_str_list(template.get("image_prompt") or template.get("image_generation_prompt")),
        "attack": max(0, attack),
        "defense": max(0, defense),
        "attributes": attributes,
        "resistance": deepcopy(template.get("resistance") or []),
        "extra": {
            "npc_template_id": str(template.get("id") or ""),
            "npc_template_category": category,
            "npc_template_source": str(template.get("source_path") or ""),
            "attacks": deepcopy(template.get("attacks") or []),
            "combat_attacks": deepcopy(template.get("attacks") or []),
            "base_attack": max(0, _safe_int(template.get("atk"), 0)),
            "base_defense": max(0, _safe_int(template.get("def"), 0)),
            "base_level": max(1, _safe_int(template.get("level"), 1)),
            "usenamelist": bool(template.get("usenamelist")),
            "rescued": bool(template.get("rescued")),
        },
        "flags": {
            "npc_template_id": str(template.get("id") or ""),
        },
    }
    if hostile is not None:
        payload["flags"]["hostile"] = bool(hostile)
        payload["extra"]["hostile"] = bool(hostile)
    if enemy:
        payload["flags"]["enemy_npc"] = True
        payload["flags"]["hostile"] = bool(True if hostile is None else hostile)
        payload["extra"]["hostile"] = bool(True if hostile is None else hostile)
    if template.get("skills_defined"):
        payload["skills"] = deepcopy(template.get("skills") or [])
    if template.get("traits_defined"):
        payload["traits"] = deepcopy(template.get("traits") or [])
    return payload


def merge_npc_template_payload(template_payload: dict[str, Any], raw_payload: Any) -> dict[str, Any]:
    raw = dict(raw_payload) if isinstance(raw_payload, dict) else {"name": str(raw_payload or "")}
    if not template_payload:
        return raw
    merged = deepcopy(template_payload)
    for key, value in raw.items():
        if key in {"extra", "flags", "prompts"} and isinstance(value, dict):
            base = merged.setdefault(key, {})
            if isinstance(base, dict):
                base.update(value)
            continue
        if key in {"skills", "traits", "image_generation_prompt", "image_prompt"} and value in (None, ""):
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    if "image_prompt" in merged and "image_generation_prompt" not in merged:
        merged["image_generation_prompt"] = _as_str_list(merged.get("image_prompt"))
    return merged
