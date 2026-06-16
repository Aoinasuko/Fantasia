from __future__ import annotations

import base64
import os
import json
import shlex
import socket
import subprocess
import threading
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig
from .paths import BIN_DIR, GENERATED_DIR, LOG_DIR, ROOT, resolve_model_path


QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "draft": {"width": 512, "height": 512, "steps": 8, "cfg_scale": 5.5},
    "balanced": {"width": 1024, "height": 1024, "steps": 24, "cfg_scale": 7.0},
    "quality": {"width": 1024, "height": 1024, "steps": 32, "cfg_scale": 7.5},
    "ultra": {"width": 1216, "height": 1216, "steps": 40, "cfg_scale": 8.0},
}

DEFAULT_NEGATIVE_PROMPTS = {
    "default": "low quality, worst quality, blurry, text, watermark",
    "background": "low quality, worst quality, blurry, text, watermark, logo, signature",
    "character": "low quality, worst quality, blurry, text, watermark, extra fingers, bad hands, malformed hands, extra limbs",
    "monster": "low quality, worst quality, blurry, text, watermark, cropped, extra limbs, extra heads, deformed anatomy",
}


class ImageBackendError(RuntimeError):
    pass


@dataclass
class ImageResult:
    path: Path
    backend: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageQueueToken:
    ticket: int
    queued_at: float
    started_at: float = 0.0
    completed_at: float = 0.0
    queue_position: int = 0


class BaseImageBackend:
    name = "base"

    def generate(self, prompt: str, negative_prompt: str = "", purpose: str = "image") -> ImageResult:
        raise NotImplementedError

    def negative_prompt(self, purpose: str, llm_negative_prompt: str = "") -> str:
        return _merge_negative_prompts("", llm_negative_prompt)

    def stop(self) -> None:
        pass

    def generation_settings(self) -> dict[str, Any]:
        return {}


class ImageGenerationQueue:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._next_ticket = 1
        self._serving_ticket = 1

    def enter(self) -> ImageQueueToken:
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            token = ImageQueueToken(
                ticket=ticket,
                queued_at=time.time(),
                queue_position=max(0, ticket - self._serving_ticket),
            )
            while ticket != self._serving_ticket:
                self._condition.wait()
            token.started_at = time.time()
            return token

    def leave(self, token: ImageQueueToken) -> dict[str, Any]:
        with self._condition:
            token.completed_at = time.time()
            self._serving_ticket += 1
            self._condition.notify_all()
        return {
            "ticket": token.ticket,
            "queue_position": token.queue_position,
            "queued_at": _iso_from_timestamp(token.queued_at),
            "started_at": _iso_from_timestamp(token.started_at),
            "completed_at": _iso_from_timestamp(token.completed_at),
            "wait_sec": round(max(0.0, token.started_at - token.queued_at), 3),
            "run_sec": round(max(0.0, token.completed_at - token.started_at), 3),
        }


class MockSdxlBackend(BaseImageBackend):
    name = "mock_sdxl"

    def __init__(self, config: AppConfig) -> None:
        image_config = _merged_image_config(config.image_backend)
        self.width = int(image_config.get("width", 1024))
        self.height = int(image_config.get("height", 576))
        self.negative_prompts = _negative_prompts(config.image_backend)

    def generate(self, prompt: str, negative_prompt: str = "", purpose: str = "image") -> ImageResult:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path = GENERATED_DIR / "latest_scene.png"
        image = Image.new("RGB", (self.width, self.height), (29, 31, 36))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        for y in range(self.height):
            shade = int(30 + 55 * (y / max(self.height, 1)))
            draw.line([(0, y), (self.width, y)], fill=(shade, 42, 58))
        draw.rectangle((36, 36, self.width - 36, self.height - 36), outline=(220, 190, 120), width=3)
        draw.text((64, 64), "MOCK SDXL SCENE", fill=(245, 232, 188), font=font)
        wrapped = textwrap.wrap(prompt, width=72)[:12]
        y = 108
        for line in wrapped:
            draw.text((64, y), line, fill=(235, 235, 235), font=font)
            y += 22
        image.save(path)
        return ImageResult(path=path, backend=self.name, prompt=prompt, metadata=self.generation_settings())

    def negative_prompt(self, purpose: str, llm_negative_prompt: str = "") -> str:
        return _merge_negative_prompts(self.negative_prompts.get(purpose, self.negative_prompts.get("default", "")), llm_negative_prompt)

    def generation_settings(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "width": self.width,
            "height": self.height,
        }


class SdWebUiApiBackend(BaseImageBackend):
    name = "sdwebui_api"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        image_config = _merged_image_config(config.image_backend)
        self.width = int(image_config.get("width", 1024))
        self.height = int(image_config.get("height", 576))
        self.steps = int(image_config.get("steps", 20))
        self.cfg_scale = float(image_config.get("cfg_scale", 7.0))
        self.quality_preset = str(config.image_backend.get("quality_preset", "balanced"))
        self.sampling_method = str(image_config.get("sampling_method", "DPM++ 2M Karras")).strip()
        self.scheduler = str(image_config.get("scheduler", "")).strip()
        self.negative_prompts = _negative_prompts(config.image_backend)
        self.base_url = config.server_parameters.get(self.name, "http://127.0.0.1:7860").rstrip("/")

    def generate(self, prompt: str, negative_prompt: str = "", purpose: str = "image") -> ImageResult:
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "sampler_name": self.sampling_method or "DPM++ 2M Karras",
        }
        if self.scheduler:
            payload["scheduler"] = self.scheduler
        data = _post_json(f"{self.base_url}/sdapi/v1/txt2img", payload, timeout=600)
        images = data.get("images") if isinstance(data, dict) else None
        if not images:
            raise ImageBackendError("SD WebUI API returned no images")

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        path = GENERATED_DIR / "latest_scene.png"
        raw = images[0].split(",", 1)[-1]
        path.write_bytes(base64.b64decode(raw))
        return ImageResult(path=path, backend=self.name, prompt=prompt, metadata=self._metadata(payload, data))

    def negative_prompt(self, purpose: str, llm_negative_prompt: str = "") -> str:
        return _merge_negative_prompts(self.negative_prompts.get(purpose, self.negative_prompts.get("default", "")), llm_negative_prompt)

    def generation_settings(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "base_url": self.base_url,
            "quality_preset": self.quality_preset,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "sampling_method": self.sampling_method,
            "scheduler": self.scheduler,
        }

    def _metadata(self, payload: dict[str, Any], response: Any) -> dict[str, Any]:
        metadata = self.generation_settings()
        metadata["request"] = _metadata_payload(payload)
        if isinstance(response, dict) and response.get("info") is not None:
            metadata["response_info"] = response.get("info")
        return metadata


class StableDiffusionCppBackend(BaseImageBackend):
    name = "stable_diffusion_cpp"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        raw_image_config = config.image_backend
        image_config = _merged_image_config(raw_image_config)
        sdxl_config = config.sdxl
        self.width = int(image_config.get("width", 1024))
        self.height = int(image_config.get("height", 1024))
        self.steps = int(image_config.get("steps", 24))
        self.cfg_scale = float(image_config.get("cfg_scale", 7.0))
        self.seed = int(image_config.get("seed", -1))
        self.sampling_method = str(image_config.get("sampling_method", "")).strip()
        self.scheduler = str(image_config.get("scheduler", "")).strip()
        self.quality_preset = str(raw_image_config.get("quality_preset", "balanced")).strip() or "balanced"
        self.lora_prompt = str(raw_image_config.get("lora_prompt", "")).strip()
        self.negative_prompts = _negative_prompts(raw_image_config)
        self.timeout_sec = int(image_config.get("timeout_sec", 1800))
        self.startup_timeout_sec = int(image_config.get("startup_timeout_sec", 180))
        self.exe = _resolve_path(_sd_server_path(sdxl_config))
        self.model = _resolve_graphic_model_path(sdxl_config.get("checkpoint_path"))
        self.vae = _optional_model_path(sdxl_config.get("vae_path"))
        self.taesd = _optional_model_path(sdxl_config.get("taesd_path"))
        self.lora_model_dir = _optional_model_path(sdxl_config.get("lora_model_dir"))
        self.queue = ImageGenerationQueue()
        self.process: subprocess.Popen[str] | None = None
        self.log_handle = None
        self.log_path: Path | None = None
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"

    def generate(self, prompt: str, negative_prompt: str = "", purpose: str = "image") -> ImageResult:
        token = self.queue.enter()
        queue_metadata: dict[str, Any] = {}
        try:
            final_prompt = _merge_prompt_addition(prompt, self.lora_prompt)
            payload = self._txt2img_payload(final_prompt, negative_prompt)
            self._ensure_started()
            if not self.health_check():
                self.restart("health check failed before image request")
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            path = GENERATED_DIR / "latest_scene.png"
            if path.exists():
                path.unlink()
            try:
                data = _post_json(f"{self.base_url}/sdapi/v1/txt2img", payload, timeout=self.timeout_sec)
            except Exception:
                self.restart("txt2img request failed")
                data = _post_json(f"{self.base_url}/sdapi/v1/txt2img", payload, timeout=self.timeout_sec)

            image_bytes = _first_image_bytes(data)
            if not image_bytes:
                raise ImageBackendError("sd-server returned no image data")
            path.write_bytes(image_bytes)
            if not path.exists():
                raise ImageBackendError(f"sd-server did not create an image: {path}")
            queue_metadata = self.queue.leave(token)
            return ImageResult(
                path=path,
                backend=f"{self.name}:sd-server",
                prompt=final_prompt,
                metadata=self._metadata(payload, data, purpose, queue_metadata),
            )
        finally:
            if not queue_metadata:
                self.queue.leave(token)

    def negative_prompt(self, purpose: str, llm_negative_prompt: str = "") -> str:
        return _merge_negative_prompts(self.negative_prompts.get(purpose, self.negative_prompts.get("default", "")), llm_negative_prompt)

    def generation_settings(self) -> dict[str, Any]:
        return {
            "backend": f"{self.name}:sd-server",
            "quality_preset": self.quality_preset,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "seed": self.seed,
            "sampling_method": self.sampling_method,
            "scheduler": self.scheduler,
            "model": str(self.model),
            "sd_server": str(self.exe),
            "vae": str(self.vae) if self.vae else "",
            "taesd": str(self.taesd) if self.taesd else "",
            "lora_model_dir": str(self.lora_model_dir) if self.lora_model_dir else "",
            "lora_prompt": self.lora_prompt,
        }

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self._write_log_line("stopping sd-server")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._write_log_line("terminate timed out; killing sd-server")
                self.process.kill()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self.process = None
        self._close_log_handle()

    def restart(self, reason: str) -> None:
        self._write_log_line(f"restart requested: {reason}")
        self.stop()
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._ensure_started()

    def health_check(self) -> bool:
        if not self.process or self.process.poll() is not None:
            return False
        for endpoint in ("/sdapi/v1/sd-models", "/sdapi/v1/options"):
            try:
                _get_json(f"{self.base_url}{endpoint}", timeout=3)
                return True
            except Exception:
                continue
        self._write_log_line("health check failed")
        return False

    def _ensure_started(self) -> None:
        if self.process and self.process.poll() is None and self.health_check():
            return

        self.stop()
        self._validate()
        command = [
            str(self.exe),
            "--model",
            str(self.model),
            "--listen-ip",
            "127.0.0.1",
            "--listen-port",
            str(self.port),
        ]
        if self.vae:
            command.extend(["--vae", str(self.vae)])
        if self.taesd:
            command.extend(["--taesd", str(self.taesd)])
        if self.lora_model_dir:
            command.extend(["--lora-model-dir", str(self.lora_model_dir)])
        command.extend(_split_params(self.config.server_parameters.get(self.name, "")))
        env = os.environ.copy()
        self._open_log_handle(command)
        self._write_log_line(f"starting sd-server on {self.base_url}")
        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.time() + self.startup_timeout_sec
        while time.time() < deadline:
            if self.process and self.process.poll() is not None:
                raise ImageBackendError(
                    "sd-server exited before becoming ready"
                    + (f"\nlog={self.log_path}\n{_tail_file(self.log_path)}" if self.log_path else "")
                )
            if self.health_check():
                self._write_log_line("sd-server is ready")
                return
            time.sleep(1)
        raise ImageBackendError(
            "sd-server did not become ready in time"
            + (f"\nlog={self.log_path}\n{_tail_file(self.log_path)}" if self.log_path else "")
        )

    def _txt2img_payload(self, prompt: str, negative_prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "seed": self.seed,
            "batch_size": 1,
            "n_iter": 1,
        }
        if self.sampling_method:
            payload["sampler_name"] = self.sampling_method
        if self.scheduler:
            payload["scheduler"] = self.scheduler
        return payload

    def _metadata(self, payload: dict[str, Any], response: Any, purpose: str, queue_metadata: dict[str, Any]) -> dict[str, Any]:
        metadata = self.generation_settings()
        metadata.update(
            {
                "purpose": purpose,
                "base_url": self.base_url,
                "log_path": str(self.log_path) if self.log_path else "",
                "request": _metadata_payload(payload),
                "queue": queue_metadata,
            }
        )
        if isinstance(response, dict) and response.get("info") is not None:
            metadata["response_info"] = response.get("info")
        return metadata

    def _open_log_handle(self, command: list[str]) -> None:
        self._close_log_handle()
        folder = LOG_DIR / "sd-server"
        folder.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = folder / f"{timestamp}-{self.name}.log"
        self.log_handle = self.log_path.open("a", encoding="utf-8", errors="replace")
        self._write_log_line("command: " + _quote_command(command))

    def _write_log_line(self, message: str) -> None:
        if not self.log_handle:
            return
        self.log_handle.write(f"[fantasia {datetime.now().isoformat(timespec='seconds')}] {message}\n")
        self.log_handle.flush()

    def _close_log_handle(self) -> None:
        if self.log_handle:
            try:
                self.log_handle.close()
            except OSError:
                pass
        self.log_handle = None

    def _validate(self) -> None:
        if not self.exe.exists():
            raise ImageBackendError(f"sd-server.exe not found: {self.exe}")
        if not self.model.exists():
            raise ImageBackendError(f"SDXL checkpoint not found: {self.model}")
        if self.model.stat().st_size < 1024 * 1024:
            raise ImageBackendError(f"SDXL checkpoint is too small or incomplete: {self.model}")


def create_image_backend(config: AppConfig) -> BaseImageBackend:
    if config.image_backend_name == "stable_diffusion_cpp":
        return StableDiffusionCppBackend(config)
    if config.image_backend_name == "sdwebui_api":
        return SdWebUiApiBackend(config)
    return MockSdxlBackend(config)


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _resolve_graphic_model_path(value: object) -> Path:
    if isinstance(value, Path):
        return value
    return resolve_model_path(str(value or ""), "graphic")


def _sd_server_path(sdxl_config: dict[str, Any]) -> str:
    if sdxl_config.get("sd_server_path"):
        return str(sdxl_config["sd_server_path"])
    if sdxl_config.get("server_path"):
        return str(sdxl_config["server_path"])
    if sdxl_config.get("sd_cli_path"):
        return str(Path(str(sdxl_config["sd_cli_path"])).with_name("sd-server.exe"))
    return str(BIN_DIR / "stable-diffusion.cpp-cuda" / "sd-server.exe")


def _optional_model_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _resolve_path(text)


def _merged_image_config(image_config: dict[str, Any]) -> dict[str, Any]:
    result = dict(image_config)
    presets = {key: dict(value) for key, value in QUALITY_PRESETS.items()}
    custom_presets = image_config.get("quality_presets")
    if isinstance(custom_presets, dict):
        for name, preset in custom_presets.items():
            if isinstance(preset, dict):
                presets[str(name)] = dict(preset)
    preset_name = str(image_config.get("quality_preset", "balanced")).strip()
    if preset_name and preset_name != "custom" and preset_name in presets:
        for key, value in presets[preset_name].items():
            result[key] = value
    return result


def _negative_prompts(image_config: dict[str, Any]) -> dict[str, str]:
    result = dict(DEFAULT_NEGATIVE_PROMPTS)
    configured = image_config.get("negative_prompts")
    if isinstance(configured, dict):
        for key, value in configured.items():
            result[str(key)] = str(value or "").strip()
    return result


def _merge_negative_prompts(configured: str, llm_negative_prompt: str = "") -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for source in (configured, llm_negative_prompt):
        for item in str(source or "").replace("\n", ",").split(","):
            text = item.strip()
            key = text.lower()
            if text and key not in seen:
                parts.append(text)
                seen.add(key)
    return ", ".join(parts)


def _merge_prompt_addition(prompt: str, addition: str) -> str:
    base = str(prompt or "").strip()
    extra = str(addition or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    if extra in base:
        return base
    return f"{base}, {extra}"


def _metadata_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"init_images", "mask"}}


def _iso_from_timestamp(value: float) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value).isoformat(timespec="seconds")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _split_params(params: str) -> list[str]:
    return shlex.split(params) if params.strip() else []


def _tail_file(path: Path | None, lines: int = 40) -> str:
    if not path or not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def _first_image_bytes(data: Any) -> bytes:
    images = data.get("images") if isinstance(data, dict) else None
    if not isinstance(images, list) or not images:
        return b""
    first = images[0]
    if not isinstance(first, str) or not first:
        return b""
    raw = first.split(",", 1)[-1]
    try:
        return base64.b64decode(raw)
    except Exception as exc:
        raise ImageBackendError(f"sd-server returned invalid base64 image data: {exc}") from exc


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ImageBackendError(f"{url} returned HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc


def _get_json(url: str, timeout: int) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ImageBackendError(f"{url} returned HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc


def _quote_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)
