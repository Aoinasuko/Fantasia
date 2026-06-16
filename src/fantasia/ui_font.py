from __future__ import annotations

import ctypes
import struct
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from .config import AppConfig
from .paths import ROOT


@dataclass(frozen=True)
class UiFonts:
    family: str
    size: int
    path: Path
    loaded: bool

    def normal(self, delta: int = 0) -> tuple[str, int]:
        return (self.family, self._size(delta))

    def bold(self, delta: int = 0) -> tuple[str, int, str]:
        return (self.family, self._size(delta), "bold")

    def _size(self, delta: int) -> int:
        return max(6, self.size + delta)


def configure_ui_fonts(root: tk.Misc, config: AppConfig) -> UiFonts:
    size = max(6, config.font_size)
    path = resolve_app_path(config.font_path)
    loaded = False
    family = "Yu Gothic UI"

    if path.is_file():
        loaded = _load_private_font(path)
        family = _read_ttf_family(path) or path.stem

    fonts = UiFonts(family=family, size=size, path=path, loaded=loaded)
    _configure_named_fonts(root, fonts)
    _configure_ttk(root, fonts)
    root.option_add("*Font", f"{{{fonts.family}}} {fonts.size}")
    return fonts


def resolve_app_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _configure_named_fonts(root: tk.Misc, fonts: UiFonts) -> None:
    named_fonts = (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    )
    for name in named_fonts:
        try:
            tkfont.nametofont(name).configure(family=fonts.family, size=fonts.size)
        except tk.TclError:
            continue
    try:
        tkfont.nametofont("TkHeadingFont").configure(weight="bold")
    except tk.TclError:
        pass


def _configure_ttk(root: tk.Misc, fonts: UiFonts) -> None:
    try:
        style = ttk.Style(root)
        style.configure(".", font=fonts.normal())
        style.configure("TButton", font=fonts.normal())
        style.configure("TEntry", font=fonts.normal())
    except tk.TclError:
        pass


def _load_private_font(path: Path) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        added = ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)
    except (AttributeError, OSError):
        return False
    return bool(added)


def _read_ttf_family(path: Path) -> str:
    try:
        data = path.read_bytes()
        num_tables = struct.unpack_from(">H", data, 4)[0]
    except (OSError, struct.error, IndexError):
        return ""

    name_offset = 0
    name_length = 0
    for index in range(num_tables):
        record_offset = 12 + index * 16
        try:
            tag, _checksum, offset, length = struct.unpack_from(">4sIII", data, record_offset)
        except struct.error:
            return ""
        if tag == b"name":
            name_offset = offset
            name_length = length
            break

    if not name_offset or name_offset + name_length > len(data):
        return ""

    try:
        _format, count, string_offset = struct.unpack_from(">HHH", data, name_offset)
    except struct.error:
        return ""

    names: list[tuple[int, int, str]] = []
    for index in range(count):
        record_offset = name_offset + 6 + index * 12
        try:
            platform_id, _encoding_id, language_id, name_id, length, offset = struct.unpack_from(">HHHHHH", data, record_offset)
        except struct.error:
            continue
        if name_id not in {1, 4}:
            continue
        raw_start = name_offset + string_offset + offset
        raw_end = raw_start + length
        if raw_start < 0 or raw_end > len(data):
            continue
        raw = data[raw_start:raw_end]
        text = _decode_name(raw, platform_id).strip("\x00 \t\r\n")
        if text:
            priority = _name_priority(platform_id, language_id, name_id)
            names.append((priority, len(text), text))

    if not names:
        return ""
    names.sort()
    return names[0][2]


def _decode_name(raw: bytes, platform_id: int) -> str:
    encodings = ("utf-16-be", "mac_roman") if platform_id in {0, 3} else ("mac_roman", "utf-16-be")
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text:
            return text
    return ""


def _name_priority(platform_id: int, language_id: int, name_id: int) -> int:
    priority = 100
    if platform_id == 3:
        priority -= 50
    if language_id in {0x0411, 0x0409}:
        priority -= 20
    if name_id == 1:
        priority -= 10
    return priority
