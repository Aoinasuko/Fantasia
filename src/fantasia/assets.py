from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .paths import BIN_DIR, ROOT, resolve_model_path
from .prompt_templates import resolve_prompt_template_dir
from .ui_font import resolve_app_path


@dataclass(frozen=True)
class AssetCheck:
    name: str
    path: Path | None
    ok: bool
    detail: str


ASSET_TEXT = {
    "en": {
        "missing": "MISSING",
        "file_missing": "file does not exist",
        "not_file": "path is not a file",
        "too_small": "file is too small ({size} bytes)",
        "dir_missing": "directory does not exist",
        "not_dir": "path is not a directory",
        "dir_exists": "directory exists",
        "base_missing": "base.json does not exist",
        "configured": "configured",
        "not_configured": "not configured",
        "cloud_key_detail": "{env} is {status}",
        "sdwebui_api_detail": "expects a running server at {url}",
        "download_required": "download required: {name}",
    },
    "ja": {
        "missing": "不足",
        "file_missing": "ファイルが存在しません",
        "not_file": "ファイルではありません",
        "too_small": "ファイルサイズが小さすぎます ({size} bytes)",
        "dir_missing": "フォルダが存在しません",
        "not_dir": "フォルダではありません",
        "dir_exists": "フォルダがあります",
        "base_missing": "base.jsonが存在しません",
        "configured": "設定済み",
        "not_configured": "未設定",
        "cloud_key_detail": "{env} は{status}です",
        "sdwebui_api_detail": "{url} で起動中のサーバーを使用します",
        "download_required": "ダウンロードが必要です: {name}",
    },
}


ASSET_NAME_TEXT = {
    "ja": {
        "GGUF model": "GGUFモデル",
        "SDXL checkpoint": "SDXLチェックポイント",
        "LoRA dir": "LoRAフォルダ",
        "SD WebUI API": "SD WebUI API",
        "UI font": "UIフォント",
        "Prompt templates": "プロンプトテンプレート",
    },
}


def check_runtime_assets(config: AppConfig) -> list[AssetCheck]:
    checks: list[AssetCheck] = []

    if _llm_backend_kind(config.llm_backend):
        kind = _llm_backend_kind(config.llm_backend)
        llama_server = _llama_server_path(config.local_llm, kind)
        gguf_model = _resolve_model_path(config.local_llm.get("model_path", ""))
        checks.append(_file_check(f"llama-server.exe ({kind})", llama_server, min_size=1024 * 1024))
        model_check = _file_check("GGUF model", gguf_model, min_size=1024 * 1024)
        if not model_check.ok and config.local_llm.get("download_url"):
            model_name = str(config.local_llm.get("name") or config.local_llm.get("selected_model_id") or "GGUF")
            model_check = AssetCheck(model_check.name, model_check.path, model_check.ok, f"download_required:{model_name}")
        checks.append(model_check)
    elif config.llm_backend.startswith("cloud_"):
        provider = _cloud_provider(config.llm_backend)
        checks.append(_cloud_key_check(config, provider))

    if config.image_backend_name == "stable_diffusion_cpp":
        sd_server = _resolve_path(_sd_server_path(config.sdxl))
        checkpoint = _resolve_model_path(config.sdxl.get("checkpoint_path", ""), "graphic")
        checks.append(_file_check("sd-server.exe", sd_server, min_size=512 * 1024))
        checkpoint_check = _file_check("SDXL checkpoint", checkpoint, min_size=1024 * 1024)
        if not checkpoint_check.ok and config.sdxl.get("download_url"):
            model_name = str(config.sdxl.get("model_name") or config.sdxl.get("selected_model_id") or "SDXL")
            checkpoint_check = AssetCheck(
                checkpoint_check.name,
                checkpoint_check.path,
                checkpoint_check.ok,
                f"download_required:{model_name}",
            )
        checks.append(checkpoint_check)
        optional_vae = _optional_path(config.sdxl.get("vae_path"))
        optional_taesd = _optional_path(config.sdxl.get("taesd_path"))
        optional_lora_dir = _optional_path(config.sdxl.get("lora_model_dir"))
        if optional_vae:
            checks.append(_file_check("VAE", optional_vae, min_size=1024))
        if optional_taesd:
            checks.append(_file_check("TAESD", optional_taesd, min_size=1024))
        if optional_lora_dir:
            checks.append(_directory_check("LoRA dir", optional_lora_dir))
    elif config.image_backend_name == "sdwebui_api":
        checks.append(
            AssetCheck(
                "SD WebUI API",
                None,
                True,
                f"sdwebui_api:{config.server_parameters.get('sdwebui_api', 'http://127.0.0.1:7860')}",
            )
        )

    checks.append(_file_check("UI font", resolve_app_path(config.font_path), min_size=64 * 1024))
    checks.append(_prompt_templates_check("Prompt templates", resolve_prompt_template_dir(config.prompt_template_path)))
    return checks


def format_asset_report(checks: list[AssetCheck], language: str = "ja") -> str:
    lines = []
    for check in checks:
        status = "OK" if check.ok else _asset_text(language, "missing")
        target = f" ({check.path})" if check.path else ""
        lines.append(f"[{status}] {_asset_name(check.name, language)}{target}: {_asset_detail(check.detail, language)}")
    return "\n".join(lines)


def _file_check(name: str, path: Path, min_size: int) -> AssetCheck:
    if not path.exists():
        return AssetCheck(name, path, False, "file_missing")
    if not path.is_file():
        return AssetCheck(name, path, False, "not_file")
    size = path.stat().st_size
    if size < min_size:
        return AssetCheck(name, path, False, f"too_small:{size}")
    return AssetCheck(name, path, True, f"{size} bytes")


def _directory_check(name: str, path: Path) -> AssetCheck:
    if not path.exists():
        return AssetCheck(name, path, False, "dir_missing")
    if not path.is_dir():
        return AssetCheck(name, path, False, "not_dir")
    return AssetCheck(name, path, True, "dir_exists")


def _optional_path(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _resolve_path(text)


def _prompt_templates_check(name: str, path: Path) -> AssetCheck:
    if not path.exists():
        return AssetCheck(name, path, False, "dir_missing")
    if not path.is_dir():
        return AssetCheck(name, path, False, "not_dir")
    base = path / "base.json"
    if not base.exists():
        return AssetCheck(name, base, False, "base_missing")
    return AssetCheck(name, path, True, f"base={base}")


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _resolve_model_path(value: object, kind: str) -> Path:
    if isinstance(value, Path):
        return value
    if not str(value or "").strip():
        if kind.lower() == "graphic":
            return resolve_model_path("model.safetensors", "graphic")
        return resolve_model_path("model.gguf", "text")
    return resolve_model_path(value, kind)


def _sd_server_path(sdxl: dict) -> str:
    if sdxl.get("sd_server_path"):
        return str(sdxl["sd_server_path"])
    if sdxl.get("server_path"):
        return str(sdxl["server_path"])
    if sdxl.get("sd_cli_path"):
        return str(Path(str(sdxl["sd_cli_path"])).with_name("sd-server.exe"))
    return str(BIN_DIR / "stable-diffusion.cpp-cuda" / "sd-server.exe")


def _llm_backend_kind(backend: str) -> str:
    mapping = {
        "llama_cpp_completion": "cuda",
        "llama_cpp_completion_cpu": "cpu",
        "llama_cpp_completion_vulkan": "vulkan",
        "llama_cpp_completion_cuda": "cuda",
    }
    return mapping.get(backend, "")


def _llama_server_path(local_llm: dict, kind: str) -> Path:
    server_paths = local_llm.get("server_paths")
    if isinstance(server_paths, dict) and server_paths.get(kind):
        return _resolve_path(str(server_paths[kind]))
    explicit_key = f"{kind}_server_path"
    if local_llm.get(explicit_key):
        return _resolve_path(str(local_llm[explicit_key]))
    if local_llm.get("server_path"):
        return _resolve_path(str(local_llm["server_path"]))
    defaults = {
        "cpu": BIN_DIR / "llama" / "llama-server.exe",
        "vulkan": BIN_DIR / "llama" / "llama-server.exe",
        "cuda": BIN_DIR / "llama-cuda" / "llama-server.exe",
    }
    return _resolve_path(defaults[kind])


def _cloud_provider(backend: str) -> str:
    if backend in {"cloud_openai", "cloud_chatgpt"}:
        return "openai"
    if backend == "cloud_xai":
        return "xai"
    if backend == "cloud_gemini":
        return "gemini"
    return backend.removeprefix("cloud_")


def _cloud_key_check(config: AppConfig, provider: str) -> AssetCheck:
    defaults = {
        "openai": "OPENAI_API_KEY",
        "xai": "XAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    cloud_llm = config.cloud_llm
    provider_config = cloud_llm.get(provider)
    env_name = ""
    if isinstance(provider_config, dict):
        env_name = str(provider_config.get("api_key_env") or "")
    api_key_env = cloud_llm.get("api_key_env")
    if not env_name and isinstance(api_key_env, dict):
        env_name = str(api_key_env.get(provider) or "")
    env_name = env_name or defaults.get(provider, "")
    env_setting = config.environment_setting
    configured = bool(
        env_setting.get(env_name)
        or env_setting.get(env_name.lower())
        or env_setting.get(f"{provider}_api_key")
        or os.environ.get(env_name)
    )
    return AssetCheck(
        f"Cloud LLM API key ({provider})",
        None,
        configured,
        f"cloud_key:{env_name}:{'configured' if configured else 'not_configured'}",
    )


def _asset_text(language: str, key: str) -> str:
    table = ASSET_TEXT.get(language, ASSET_TEXT["ja"])
    return table.get(key, ASSET_TEXT["en"].get(key, key))


def _asset_name(name: str, language: str) -> str:
    if name.startswith("llama-server.exe"):
        return name
    return ASSET_NAME_TEXT.get(language, {}).get(name, name)


def _asset_detail(detail: str, language: str) -> str:
    if detail.startswith("too_small:"):
        return _asset_text(language, "too_small").format(size=detail.split(":", 1)[1])
    if detail.startswith("png_frames:"):
        return _asset_text(language, "png_frames").format(count=detail.split(":", 1)[1])
    if detail.startswith("cloud_key:"):
        _prefix, env, status = detail.split(":", 2)
        return _asset_text(language, "cloud_key_detail").format(env=env, status=_asset_text(language, status))
    if detail.startswith("sdwebui_api:"):
        return _asset_text(language, "sdwebui_api_detail").format(url=detail.split(":", 1)[1])
    if detail.startswith("download_required:"):
        return _asset_text(language, "download_required").format(name=detail.split(":", 1)[1])
    return _asset_text(language, detail)
