from __future__ import annotations

import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig
from .paths import MODEL_GRAPHIC_DIR, MODEL_TEXT_DIR, ROOT, resolve_model_path


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ModelDownloadOption:
    model_id: str
    display_name: str
    filename: str
    url: str
    path: Path
    min_size: int = 1024 * 1024 * 1024
    context_size: int = 8192
    description: str = ""


DEFAULT_LOCAL_LLM_MODELS = {
    "gemma4_medium": {
        "display_name": "Gemma 4 12B IT Q4_K_M",
        "filename": "gemma-4-12b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/unsloth/gemma-4-12b-it-GGUF/resolve/main/gemma-4-12b-it-Q4_K_M.gguf?download=true",
        "path": "text/gemma4_medium/gemma-4-12b-it-Q4_K_M.gguf",
        "min_size": 1024 * 1024 * 1024,
        "context_size": 8192,
        "description": "Medium Gemma-family local GGUF model.",
    },
    "qwen3_6_medium": {
        "display_name": "Qwen3.6 27B Q4_K_M",
        "filename": "Qwen3.6-27B-Q4_K_M.gguf",
        "url": "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/main/Qwen3.6-27B-Q4_K_M.gguf?download=true",
        "path": "text/qwen3_6_medium/Qwen3.6-27B-Q4_K_M.gguf",
        "min_size": 1024 * 1024 * 1024,
        "context_size": 8192,
        "description": "Medium Qwen3.6 local GGUF model.",
    },
}


DEFAULT_SDXL_MODELS = {
    "sdxl_base_1_0": {
        "display_name": "Stable Diffusion XL Base 1.0",
        "filename": "sd_xl_base_1.0.safetensors",
        "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors?download=true",
        "path": "graphic/sdxl_base_1_0/sd_xl_base_1.0.safetensors",
        "min_size": 1024 * 1024 * 1024,
        "context_size": 0,
        "description": "Official Stability AI SDXL Base 1.0 checkpoint.",
    },
}


def local_llm_model_options(config: AppConfig) -> list[ModelDownloadOption]:
    return _model_options(config, "local_llm", DEFAULT_LOCAL_LLM_MODELS, "text")


def sdxl_model_options(config: AppConfig) -> list[ModelDownloadOption]:
    return _model_options(config, "sdxl", DEFAULT_SDXL_MODELS, "graphic")


def _model_options(
    config: AppConfig,
    catalog_key: str,
    default_catalog: dict[str, dict[str, Any]],
    default_folder: str,
) -> list[ModelDownloadOption]:
    raw_catalog = config.raw.get("model_catalog", {})
    local_catalog = raw_catalog.get(catalog_key) if isinstance(raw_catalog, dict) else {}
    catalog = dict(default_catalog)
    if isinstance(local_catalog, dict):
        catalog.update(local_catalog)
    result: list[ModelDownloadOption] = []
    model_type = "sdxl" if catalog_key == "sdxl" else "local_llm"
    for model_id, raw in catalog.items():
        if not isinstance(raw, dict):
            continue
        path = _resolve_model_path(raw.get("path") or raw.get("model_path") or "", model_type)
        filename = str(raw.get("filename") or path.name or f"{model_id}.gguf")
        if not path.name:
            path = _resolve_path(f"{default_folder}/{model_id}/{filename}")
        result.append(
            ModelDownloadOption(
                model_id=str(model_id),
                display_name=str(raw.get("display_name") or raw.get("name") or model_id),
                filename=filename,
                url=str(raw.get("url") or raw.get("download_url") or ""),
                path=path,
                min_size=max(1024 * 1024, int(raw.get("min_size") or 1024 * 1024 * 1024)),
                context_size=max(1024, int(raw.get("context_size") or 8192)),
                description=str(raw.get("description") or ""),
            )
        )
    return _merge_scanned_model_options(result, model_type)


def model_label(option: ModelDownloadOption) -> str:
    suffix = "installed" if option.path.is_file() else "not installed"
    return f"{option.display_name} ({suffix})"


def model_labels(config: AppConfig) -> tuple[str, ...]:
    return tuple(model_label(option) for option in local_llm_model_options(config))


def option_from_label(config: AppConfig, label: str) -> ModelDownloadOption | None:
    clean_label = str(label).strip()
    for option in [*local_llm_model_options(config), *sdxl_model_options(config)]:
        if clean_label in {model_label(option), option.display_name, option.model_id}:
            return option
        if clean_label.startswith(option.display_name):
            return option
    return None


def option_to_local_llm(option: ModelDownloadOption, existing: dict[str, Any]) -> dict[str, Any]:
    local_llm = dict(existing)
    local_llm["name"] = option.display_name
    model_path = option.path
    if _is_relative_to(model_path, MODEL_TEXT_DIR):
        model_path = Path("text") / model_path.relative_to(MODEL_TEXT_DIR)
    local_llm["model_path"] = str(model_path)
    local_llm["selected_model_id"] = option.model_id
    local_llm["download_url"] = option.url
    local_llm["context_size"] = option.context_size
    return local_llm


def download_model(option: ModelDownloadOption, progress: ProgressCallback | None = None) -> Path:
    if not option.url:
        raise ValueError(f"Download URL is not configured for {option.display_name}.")
    option.path.parent.mkdir(parents=True, exist_ok=True)
    if option.path.exists() and option.path.stat().st_size >= option.min_size:
        return option.path

    part_path = option.path.with_suffix(option.path.suffix + ".part")
    request = urllib.request.Request(_download_url(option.url), headers=_download_headers(option.url))
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(option.path.parent), prefix=option.path.name + ".", suffix=".tmp") as handle:
            temp_path = Path(handle.name)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)

    try:
        if temp_path.stat().st_size < option.min_size:
            raise ValueError(f"Downloaded model is too small: {temp_path.stat().st_size} bytes")
        if part_path.exists():
            part_path.unlink()
        temp_path.replace(option.path)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
    return option.path


def _download_url(url: str) -> str:
    civitai_token = os.environ.get("CIVITAI_TOKEN")
    if civitai_token and "civitai.com" in url and "token=" not in url:
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}token={civitai_token}"
    return url


def _download_headers(url: str) -> dict[str, str]:
    headers = {"User-Agent": "Fantasia/0.1"}
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {token}"
    civitai_token = os.environ.get("CIVITAI_TOKEN")
    if civitai_token and "civitai.com" in url:
        headers["Authorization"] = f"Bearer {civitai_token}"
    return headers


def _resolve_path(value: object) -> Path:
    if isinstance(value, Path):
        raw = str(value)
    else:
        raw = str(value or "")
    return resolve_model_path(raw)


def _merge_scanned_model_options(
    catalog_options: list[ModelDownloadOption],
    model_type: str,
) -> list[ModelDownloadOption]:
    result = list(catalog_options)
    seen_paths = {_path_key(option.path) for option in result}
    seen_names = {option.path.name.lower() for option in result if option.path.is_file()}
    for path in _scan_model_files(model_type):
        resolved_key = _path_key(path)
        if resolved_key in seen_paths:
            continue
        if path.name.lower() in seen_names and any(option.path.name.lower() == path.name.lower() for option in result):
            continue
        result.append(_scanned_model_option(path, model_type))
        seen_paths.add(resolved_key)
        seen_names.add(path.name.lower())
    result.sort(key=lambda option: (0 if option.path.is_file() else 1, option.display_name.lower()))
    return result


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def _scan_model_files(model_type: str) -> list[Path]:
    roots = _model_scan_roots(model_type)
    extensions = {".gguf"} if model_type == "local_llm" else {".safetensors", ".ckpt", ".pt"}
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions:
                files.append(path)
    return sorted(files, key=lambda path: str(path).lower())


def _model_scan_roots(model_type: str) -> list[Path]:
    primary = MODEL_TEXT_DIR if model_type == "local_llm" else MODEL_GRAPHIC_DIR
    subfolder = "text" if model_type == "local_llm" else "graphic"
    roots = [primary]
    publish_root = ROOT / "publish" / "model" / subfolder
    if publish_root != primary:
        roots.append(publish_root)
    return roots


def _scanned_model_option(path: Path, model_type: str) -> ModelDownloadOption:
    stem = path.stem.strip() or path.name
    model_id = f"local_{model_type}_{_safe_model_id(stem)}"
    return ModelDownloadOption(
        model_id=model_id,
        display_name=stem,
        filename=path.name,
        url="",
        path=path,
        min_size=1024 * 1024,
        context_size=8192 if model_type == "local_llm" else 0,
        description="Detected local model file.",
    )


def _safe_model_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return cleaned or "model"


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _resolve_model_path(raw: object, model_type: str) -> Path:
    if model_type == "sdxl":
        return resolve_model_path(raw, "graphic")
    return resolve_model_path(raw, "text")
