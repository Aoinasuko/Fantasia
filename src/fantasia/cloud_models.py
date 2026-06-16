from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from .config import AppConfig


def fetch_cloud_model_ids(config: AppConfig, provider: str, api_key_override: str = "") -> list[str]:
    provider = provider.strip().lower()
    api_key = api_key_override.strip() or _cloud_api_key(config, provider)
    if provider in {"openai", "xai"}:
        base_url = _cloud_base_url(config, provider, _default_base_url(provider)).rstrip("/")
        endpoint = f"{base_url}/language-models" if provider == "xai" else f"{base_url}/models"
        data = _get_json(endpoint, _bearer_headers(api_key))
        return _model_ids_from_openai_compatible(data)
    if provider == "gemini":
        base_url = _cloud_base_url(config, provider, _default_base_url(provider)).rstrip("/")
        return _fetch_gemini_model_ids(base_url, api_key)
    raise ValueError(f"Unsupported cloud provider: {provider}")


def cached_cloud_model_ids(config: AppConfig, provider: str) -> tuple[str, ...]:
    cache = config.cloud_llm.get("model_cache")
    if isinstance(cache, dict):
        values = cache.get(provider)
        if isinstance(values, list):
            result = tuple(str(item) for item in values if str(item).strip())
            if result:
                return result
    return _fallback_models(provider)


def _get_json(url: str, headers: dict[str, str]) -> Any:
    request_headers = {"User-Agent": "Fantasia/0.1", "Accept": "application/json"}
    request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _bearer_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _fetch_gemini_model_ids(base_url: str, api_key: str) -> list[str]:
    values = []
    page_token = ""
    while True:
        query = {"key": api_key, "pageSize": "1000"}
        if page_token:
            query["pageToken"] = page_token
        endpoint = f"{base_url}/models?{urllib.parse.urlencode(query)}"
        data = _get_json(endpoint, {})
        values.extend(_model_ids_from_gemini(data))
        if not isinstance(data, dict):
            break
        page_token = str(data.get("nextPageToken") or "").strip()
        if not page_token:
            break
    return _unique_sorted(values)


def _model_ids_from_openai_compatible(data: Any) -> list[str]:
    values = []
    if isinstance(data, dict):
        raw_items = data.get("data") or data.get("models") or []
    elif isinstance(data, list):
        raw_items = data
    else:
        raw_items = []
    for item in raw_items:
        if isinstance(item, str):
            values.append(item)
            continue
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("model_id") or item.get("name")
            if model_id:
                values.append(str(model_id))
    return _unique_sorted(values)


def _model_ids_from_gemini(data: Any) -> list[str]:
    values = []
    raw_items = data.get("models", []) if isinstance(data, dict) else []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods")
        if isinstance(methods, list) and "generateContent" not in methods:
            continue
        name = str(item.get("name") or "").strip()
        if name.startswith("models/"):
            name = name.removeprefix("models/")
        if name:
            values.append(name)
    return _unique_sorted(values)


def _unique_sorted(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return sorted(result)


def _cloud_api_key(config: AppConfig, provider: str) -> str:
    env_name = _cloud_value(config, provider, "api_key_env", _default_env(provider))
    env_setting = config.environment_setting
    candidates = [
        env_setting.get(env_name),
        env_setting.get(str(env_name).lower()),
        env_setting.get(f"{provider}_api_key"),
        os.environ.get(str(env_name)),
    ]
    api_key = next((str(value).strip() for value in candidates if str(value or "").strip()), "")
    if not api_key:
        raise ValueError(f"{provider} API key is not configured.")
    return api_key


def _cloud_base_url(config: AppConfig, provider: str, default: str) -> str:
    return str(_cloud_value(config, provider, "base_url", default))


def _cloud_value(config: AppConfig, provider: str, key: str, default: str = "") -> str:
    cloud_llm = config.cloud_llm
    provider_config = cloud_llm.get(provider)
    if isinstance(provider_config, dict) and provider_config.get(key):
        return str(provider_config[key])
    value = cloud_llm.get(key)
    if isinstance(value, dict):
        return str(value.get(provider, default))
    return str(value or default)


def _default_env(provider: str) -> str:
    return {
        "openai": "OPENAI_API_KEY",
        "xai": "XAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }[provider]


def _default_base_url(provider: str) -> str:
    return {
        "openai": "https://api.openai.com/v1",
        "xai": "https://api.x.ai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
    }[provider]


def _fallback_models(provider: str) -> tuple[str, ...]:
    return {
        "openai": ("gpt-5.1-mini", "gpt-5.1", "gpt-5.1-nano"),
        "xai": ("grok-4.3", "grok-4.3-mini", "grok-4"),
        "gemini": ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"),
    }.get(provider, ())
