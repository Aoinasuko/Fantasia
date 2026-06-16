from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .paths import ROOT


TEXT_EXTENSIONS = {
    ".cfg",
    ".cs",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

SOURCE_DIRS = {"assets", "docs", "scripts", "src", "TODO"}
SOURCE_FILES = {"config.json", "main.py", "README.md", "requirements.txt"}
EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "bin",
    "dist",
    "publish",
    "runtime",
    "log",
    "crashlog",
}
GENERATED_DIRS = {"output_data", "log", "crashlog"}

MOJIBAKE_TOKENS = (
    "\u7e3a",
    "\u7e67",
    "\u8b41",
    "\u9aeb",
    "\u83a0",
    "\u8373",
    "\u8708",
    "\u879f",
    "\u9a65",
    "\u90b1",
    "\u9015",
    "\u8c4c",
    "\u8763",
    "\u8b5b",
    "\ufffd",
)


@dataclass(frozen=True)
class EncodingCheck:
    path: Path
    ok: bool
    detail: str


def configure_stdio_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if not stream or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def check_project_encoding(include_generated: bool = False) -> list[EncodingCheck]:
    checks: list[EncodingCheck] = []
    for path in _iter_text_files(ROOT, include_generated):
        checks.append(_check_text_file(path))
    return checks


def format_encoding_report(checks: Iterable[EncodingCheck]) -> str:
    items = list(checks)
    if not items:
        return "[OK] Encoding: no text files matched"
    issues = [check for check in items if not check.ok]
    if not issues:
        return f"[OK] Encoding: {len(items)} text files are UTF-8 without BOM or mojibake markers"
    lines = [f"[NG] Encoding: {len(issues)} issue(s) in {len(items)} checked text files"]
    for issue in issues:
        lines.append(f"- {issue.path.relative_to(ROOT)}: {issue.detail}")
    return "\n".join(lines)


def _iter_text_files(root: Path, include_generated: bool) -> Iterable[Path]:
    excluded = set(EXCLUDED_DIRS)
    if not include_generated:
        excluded.update(GENERATED_DIRS)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in excluded for part in rel.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if include_generated:
            yield path
            continue
        if rel.parts[0] in SOURCE_DIRS or str(rel) in SOURCE_FILES:
            yield path


def _check_text_file(path: Path) -> EncodingCheck:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return EncodingCheck(path, False, "UTF-8 BOM is present; use UTF-8 without BOM")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return EncodingCheck(path, False, f"not valid UTF-8: {exc}")
    for line_no, line in enumerate(text.splitlines(), 1):
        hit = next((token for token in MOJIBAKE_TOKENS if token in line), "")
        if hit:
            marker = hit.encode("unicode_escape").decode("ascii")
            return EncodingCheck(path, False, f"possible mojibake marker {marker} at line {line_no}")
    return EncodingCheck(path, True, "UTF-8")
