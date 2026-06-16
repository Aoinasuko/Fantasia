from __future__ import annotations

import json
import platform
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from .paths import CONFIG_PATH, CRASHLOG_DIR, ROOT


_installed = False
_previous_sys_excepthook = sys.excepthook
_previous_threading_excepthook = getattr(threading, "excepthook", None)


def install_crash_logging() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    sys.excepthook = _sys_excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook


def install_tk_crash_logging(root: Any) -> None:
    previous = getattr(root, "report_callback_exception", None)

    def report_callback_exception(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        path = write_crash_log("tkinter_callback", exc_type, exc, tb)
        stderr = getattr(sys, "stderr", None)
        if stderr:
            print(f"Fantasia callback error logged: {path}", file=stderr)
        if callable(previous):
            try:
                previous(exc_type, exc, tb)
            except Exception:
                traceback.print_exception(exc_type, exc, tb)
        else:
            traceback.print_exception(exc_type, exc, tb)

    root.report_callback_exception = report_callback_exception


def write_crash_log(
    source: str,
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
    *,
    extra: dict[str, Any] | None = None,
) -> Path:
    CRASHLOG_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    filename = f"{now.strftime('%Y%m%d-%H%M%S')}-{source}.log"
    path = _unique_path(CRASHLOG_DIR / filename)
    payload = {
        "created_at": now.isoformat(timespec="seconds"),
        "source": source,
        "exception_type": exc_type.__name__,
        "exception": str(exc),
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "argv": sys.argv,
        "root": str(ROOT),
        "config": str(CONFIG_PATH),
        "extra": extra or {},
    }
    lines = [
        "Fantasia crashlog",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "",
        "Traceback:",
        "".join(traceback.format_exception(exc_type, exc, tb)),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    _trim_old_crashlogs()
    return path


def _sys_excepthook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        _previous_sys_excepthook(exc_type, exc, tb)
        return
    path = write_crash_log("unhandled", exc_type, exc, tb)
    stderr = getattr(sys, "stderr", None)
    if stderr:
        print(f"Fantasia crash logged: {path}", file=stderr)
    _previous_sys_excepthook(exc_type, exc, tb)


def _threading_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is None or args.exc_value is None:
        return
    if issubclass(args.exc_type, KeyboardInterrupt):
        if callable(_previous_threading_excepthook):
            _previous_threading_excepthook(args)
        return
    path = write_crash_log(
        "thread",
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        extra={"thread": getattr(args.thread, "name", "")},
    )
    stderr = getattr(sys, "stderr", None)
    if stderr:
        print(f"Fantasia thread crash logged: {path}", file=stderr)
    if callable(_previous_threading_excepthook):
        _previous_threading_excepthook(args)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{stem}-{datetime.now().timestamp():.6f}{suffix}")


def _trim_old_crashlogs(limit: int = 50) -> None:
    try:
        logs = sorted(CRASHLOG_DIR.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return
    for path in logs[limit:]:
        try:
            path.unlink()
        except OSError:
            pass
