from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import ASSETS_DIR, ROOT


class PromptTemplateStore:
    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = template_dir or (ASSETS_DIR / "prompt_templates")
        self._base = self._read_json(self.template_dir / "base.json")

    def apply_messages(self, manager_name: str, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        template = self._template_for(manager_name)
        result = [dict(message) for message in messages]
        self._apply_role_text(result, "system", template.get("system_prefix"), before=True)
        self._apply_role_text(result, "system", template.get("system_suffix"), before=False)
        self._apply_role_text(result, "user", template.get("user_prefix"), before=True)
        self._apply_role_text(result, "user", template.get("user_suffix"), before=False)

        prepend = template.get("prepend_messages")
        if isinstance(prepend, list):
            result = _message_list(prepend) + result
        append = template.get("append_messages")
        if isinstance(append, list):
            result = result + _message_list(append)
        return result

    def apply_schema_instruction(self, manager_name: str, instruction: str) -> str:
        template = self._template_for(manager_name)
        override = template.get("schema_instruction")
        if isinstance(override, str) and override.strip():
            return override.strip()
        prefix = str(template.get("schema_instruction_prefix") or "").strip()
        suffix = str(template.get("schema_instruction_suffix") or "").strip()
        parts = [part for part in (prefix, instruction.strip(), suffix) if part]
        return "\n\n".join(parts)

    def _template_for(self, manager_name: str) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        default = self._base.get("default")
        if isinstance(default, dict):
            merged.update(default)
        managers = self._base.get("managers")
        if isinstance(managers, dict) and isinstance(managers.get(manager_name), dict):
            merged.update(managers[manager_name])
        manager_file = self._read_json(self.template_dir / "managers" / f"{manager_name}.json")
        merged.update(manager_file)
        return merged

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _apply_role_text(messages: list[dict[str, str]], role: str, text: Any, before: bool) -> None:
        addition = str(text or "").strip()
        if not addition:
            return
        for message in messages:
            if message.get("role") != role:
                continue
            content = str(message.get("content") or "")
            message["content"] = f"{addition}\n\n{content}" if before else f"{content}\n\n{addition}"
            return
        messages.insert(0 if before else len(messages), {"role": role, "content": addition})


def resolve_prompt_template_dir(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _message_list(value: list[Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "system")
        content = str(item.get("content") or "")
        if content:
            result.append({"role": role, "content": content})
    return result
