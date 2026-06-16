from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TASK_EVENT_FILE = "generation_events.jsonl"


LOG_TEXT = {
    "en": {
        "type": "Type",
        "label": "Label",
        "path": "Path",
        "updated": "Updated",
        "summary": "Summary",
        "could_not_read_log": "Could not read log: {error}",
    },
    "ja": {
        "type": "種類",
        "label": "ラベル",
        "path": "パス",
        "updated": "更新日時",
        "summary": "概要",
        "could_not_read_log": "ログを読み込めませんでした: {error}",
    },
}


@dataclass(frozen=True)
class GenerationLogEntry:
    kind: str
    label: str
    path: Path
    updated_at: float
    detail_hint: str = ""
    event: dict[str, Any] | None = None


def append_task_event(data_dir: Path, event: dict[str, Any]) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / TASK_EVENT_FILE
    payload = dict(event)
    payload.setdefault("kind", "task")
    payload.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def list_generation_logs(
    output_dir: Path,
    worlds_dir: Path,
    log_dir: Path,
    crashlog_dir: Path,
    limit: int = 300,
) -> list[GenerationLogEntry]:
    entries: list[GenerationLogEntry] = []
    entries.extend(_list_task_events(log_dir / TASK_EVENT_FILE))
    entries.extend(_list_crash_logs(crashlog_dir))
    entries.extend(_list_llama_server_logs(log_dir / "llama-server"))
    entries.extend(_list_sd_server_logs(log_dir / "sd-server"))
    entries.extend(_list_llm_logs(output_dir))
    entries.extend(_list_image_prompt_logs(worlds_dir))
    entries.sort(key=lambda item: item.updated_at, reverse=True)
    return entries[:limit]


def format_generation_log_detail(entry: GenerationLogEntry, language: str = "ja") -> str:
    label = lambda key: _log_text(language, key)
    lines = [
        f"{label('type')}: {entry.kind}",
        f"{label('label')}: {entry.label}",
        f"{label('path')}: {entry.path}",
        f"{label('updated')}: {_format_time(entry.updated_at)}",
    ]
    if entry.detail_hint:
        lines.append(f"{label('summary')}: {entry.detail_hint}")
    lines.append("")

    if entry.event is not None:
        lines.append(json.dumps(entry.event, ensure_ascii=False, indent=2))
        return "\n".join(lines)

    if entry.kind in {"crashlog", "llama_server", "sd_server"}:
        try:
            lines.append(entry.path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            lines.append(label("could_not_read_log").format(error=exc))
        return "\n".join(lines)

    try:
        data = json.loads(entry.path.read_text(encoding="utf-8"))
    except Exception as exc:
        lines.append(label("could_not_read_log").format(error=exc))
        return "\n".join(lines)

    lines.append(json.dumps(data, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def _list_task_events(path: Path) -> list[GenerationLogEntry]:
    if not path.exists():
        return []
    entries: list[GenerationLogEntry] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for index, line in enumerate(lines[-300:], start=max(1, len(lines) - 299)):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        status = str(event.get("status") or "event")
        name = str(event.get("name") or event.get("task") or "task")
        created = str(event.get("created_at") or "")
        updated_at = _timestamp_from_iso(created) or path.stat().st_mtime
        label = f"TASK / {status} / {name}"
        hint = str(event.get("message") or event.get("error") or "")
        entries.append(
            GenerationLogEntry(
                kind="task",
                label=label,
                path=path,
                updated_at=updated_at + index * 0.000001,
                detail_hint=hint,
                event=event,
            )
        )
    return entries


def _list_crash_logs(log_dir: Path) -> list[GenerationLogEntry]:
    if not log_dir.exists():
        return []
    entries: list[GenerationLogEntry] = []
    for path in log_dir.glob("*.log"):
        entries.append(
            GenerationLogEntry(
                kind="crashlog",
                label=f"CRASHLOG / {path.name}",
                path=path,
                updated_at=path.stat().st_mtime,
                detail_hint="unhandled exception traceback",
            )
        )
    return entries


def _list_llama_server_logs(log_dir: Path) -> list[GenerationLogEntry]:
    if not log_dir.exists():
        return []
    entries: list[GenerationLogEntry] = []
    for path in log_dir.glob("*.log"):
        entries.append(
            GenerationLogEntry(
                kind="llama_server",
                label=f"LLAMA SERVER / {path.name}",
                path=path,
                updated_at=path.stat().st_mtime,
                detail_hint="llama-server stdout/stderr",
            )
        )
    return entries


def _list_sd_server_logs(log_dir: Path) -> list[GenerationLogEntry]:
    if not log_dir.exists():
        return []
    entries: list[GenerationLogEntry] = []
    for path in log_dir.glob("*.log"):
        entries.append(
            GenerationLogEntry(
                kind="sd_server",
                label=f"SD SERVER / {path.name}",
                path=path,
                updated_at=path.stat().st_mtime,
                detail_hint="sd-server stdout/stderr",
            )
        )
    return entries


def _list_llm_logs(output_dir: Path) -> list[GenerationLogEntry]:
    if not output_dir.exists():
        return []
    entries: list[GenerationLogEntry] = []
    for path in output_dir.rglob("*.json"):
        rel = path.relative_to(output_dir)
        if len(rel.parts) < 4:
            continue
        world_name, player_name, manager_name = rel.parts[0], rel.parts[1], rel.parts[2]
        status = ""
        backend = ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            response = data.get("response") if isinstance(data, dict) else {}
            if isinstance(response, dict):
                validation = response.get("_validation")
                if isinstance(validation, dict):
                    status = "OK" if validation.get("ok") else "ERROR"
                backend = str(response.get("_backend") or "")
        except Exception:
            status = "UNREADABLE"
        suffix = f" / {status}" if status else ""
        label = f"LLM / {world_name} / {player_name} / {manager_name} / {path.stem}{suffix}"
        entries.append(
            GenerationLogEntry(
                kind="llm",
                label=label,
                path=path,
                updated_at=path.stat().st_mtime,
                detail_hint=backend,
            )
        )
    return entries


def _list_image_prompt_logs(worlds_dir: Path) -> list[GenerationLogEntry]:
    if not worlds_dir.exists():
        return []
    entries: list[GenerationLogEntry] = []
    for path in worlds_dir.rglob("prompts.json"):
        rel = path.relative_to(worlds_dir)
        if len(rel.parts) < 4:
            continue
        world_name, asset_type, subject = rel.parts[0], rel.parts[1], rel.parts[2]
        manager = ""
        backend = ""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                manager = str(data.get("manager") or "")
                backend = str(data.get("backend") or "")
        except Exception:
            manager = "unreadable"
        label = f"IMAGE / {world_name} / {asset_type} / {subject}"
        if manager:
            label += f" / {manager}"
        entries.append(
            GenerationLogEntry(
                kind="image",
                label=label,
                path=path,
                updated_at=path.stat().st_mtime,
                detail_hint=backend,
            )
        )
    return entries


def _format_time(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _log_text(language: str, key: str) -> str:
    table = LOG_TEXT.get(language, LOG_TEXT["ja"])
    return table.get(key, LOG_TEXT["en"].get(key, key))


def _timestamp_from_iso(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0
