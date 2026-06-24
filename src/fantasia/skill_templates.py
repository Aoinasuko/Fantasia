from __future__ import annotations

import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any

from .combat_model import normalise_combat_skill
from .paths import ROOT, SKILL_TEMPLATE_DIR


SKILL_TEMPLATE_CATEGORY_IDS = ("fighter", "magic")
RANDOM_SKILL_MODES = ("none", "fighter", "magic", "both")
SKILL_TEMPLATE_LOAD_ERRORS: list[str] = []


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _template_dirs() -> list[Path]:
    candidates = [SKILL_TEMPLATE_DIR, ROOT / "Data" / "Template" / "Skill"]
    result: list[Path] = []
    for candidate in candidates:
        if candidate not in result:
            result.append(candidate)
    return result


def skill_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SKILL_TEMPLATE_CATEGORY_IDS else ""


def random_skill_mode(value: Any) -> str:
    text = str(value or "none").strip().lower()
    return text if text in RANDOM_SKILL_MODES else "none"


def _raw_skill_items(raw_items: Any) -> list[Any]:
    if isinstance(raw_items, dict) and isinstance(raw_items.get("entries"), list):
        return list(raw_items["entries"])
    if isinstance(raw_items, list):
        return raw_items
    if isinstance(raw_items, dict):
        return [raw_items]
    return []


def _normalise_skill_template(raw: Any, source_path: Path) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    template_id = str(raw.get("id") or raw.get("skill_id") or "").strip()
    category = skill_category(raw.get("category"))
    skill = normalise_combat_skill(raw)
    if not template_id or not category or not skill:
        return None
    skill["id"] = template_id
    skill["skill_template_id"] = template_id
    skill["category"] = category
    skill["source_path"] = str(source_path)
    return skill


def _load_skill_templates() -> dict[str, list[dict[str, Any]]]:
    loaded: dict[str, list[dict[str, Any]]] = {category: [] for category in SKILL_TEMPLATE_CATEGORY_IDS}
    SKILL_TEMPLATE_LOAD_ERRORS.clear()
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for template_path in sorted(directory.glob("*.json")):
            try:
                raw_items = json.loads(template_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                SKILL_TEMPLATE_LOAD_ERRORS.append(f"{template_path}: {exc}")
                continue
            for raw in _raw_skill_items(raw_items):
                template = _normalise_skill_template(raw, template_path)
                if template is None:
                    continue
                loaded.setdefault(str(template["category"]), []).append(template)
    return {category: values for category, values in loaded.items() if values}


SKILL_TEMPLATES = _load_skill_templates()
SKILL_TEMPLATES_BY_ID = {
    str(template.get("id")): template
    for templates in SKILL_TEMPLATES.values()
    for template in templates
    if str(template.get("id") or "").strip()
}


def skill_template_by_id(template_id: Any) -> dict[str, Any] | None:
    template = SKILL_TEMPLATES_BY_ID.get(str(template_id or "").strip())
    return deepcopy(template) if template else None


def skill_templates_for_categories(categories: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for category in categories:
        result.extend(deepcopy(item) for item in SKILL_TEMPLATES.get(skill_category(category), []))
    return result


def _categories_for_random_mode(mode: Any) -> tuple[str, ...]:
    resolved = random_skill_mode(mode)
    if resolved == "fighter":
        return ("fighter",)
    if resolved == "magic":
        return ("magic",)
    if resolved == "both":
        return ("fighter", "magic")
    return ()


def _character_skill_entry(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(template.get("id") or ""),
        "name": str(template.get("name") or ""),
        "desc": str(template.get("desc") or ""),
        "usesp": template.get("usesp"),
        "power": template.get("power"),
        "ability": str(template.get("ability") or ""),
        "element": str(template.get("element") or ""),
        "type": deepcopy(template.get("type") or []),
        "skill_template_id": str(template.get("skill_template_id") or template.get("id") or ""),
    }


def choose_random_skill_templates(
    mode: Any,
    *,
    seed: str = "",
    existing_skills: Any = None,
    max_count: int = 3,
) -> list[dict[str, Any]]:
    categories = _categories_for_random_mode(mode)
    if not categories:
        return []
    candidates = skill_templates_for_categories(categories)
    if not candidates:
        return []
    existing_ids: set[str] = set()
    existing_names: set[str] = set()
    for skill in _as_list(existing_skills):
        if not isinstance(skill, dict):
            continue
        for key in ("id", "skill_template_id", "template_id"):
            value = str(skill.get(key) or "").strip()
            if value:
                existing_ids.add(value)
        name = str(skill.get("name") or "").strip()
        if name:
            existing_names.add(name)
    filtered = [
        template
        for template in candidates
        if str(template.get("id") or "").strip() not in existing_ids
        and str(template.get("name") or "").strip() not in existing_names
    ]
    if not filtered:
        return []
    rng = random.Random(seed or f"skill-template:{random_skill_mode(mode)}")
    rng.shuffle(filtered)
    count = rng.randint(0, min(max(0, int(max_count)), len(filtered)))
    return [_character_skill_entry(template) for template in filtered[:count]]

