from __future__ import annotations

import ctypes
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .paths import BIN_DIR


@dataclass(frozen=True)
class DeviceInfo:
    memory_size_gb: int = 0
    vram_size_gb: int = 0
    gpu_names: list[str] = field(default_factory=list)
    is_torch_cuda_usable: bool = False
    is_vulkan_usable: bool = False
    recommended_llm_backend: str = "llama_cpp_completion_cpu"
    recommended_image_backend: str = "stable_diffusion_cpp"
    notes: list[str] = field(default_factory=list)

    def to_config(self) -> dict[str, object]:
        return {
            "memory_size": self.memory_size_gb,
            "vram_size": self.vram_size_gb,
            "gpu_names": list(self.gpu_names),
            "is_torch_cuda_usable": self.is_torch_cuda_usable,
            "is_vulkan_usable": self.is_vulkan_usable,
            "recommended_llm_backend": self.recommended_llm_backend,
            "recommended_image_backend": self.recommended_image_backend,
            "notes": list(self.notes),
        }


def detect_device() -> DeviceInfo:
    memory_size_gb = _system_memory_gb()
    gpu_names, vram_size_gb = _nvidia_smi_gpus()
    if not gpu_names:
        gpu_names, vram_size_gb = _windows_video_controllers()
    has_nvidia = any("nvidia" in name.lower() or "geforce" in name.lower() for name in gpu_names)
    cuda_usable = bool(has_nvidia and _server_exists("cuda"))
    vulkan_usable = _has_vulkan_runtime() and _server_exists("vulkan")
    notes: list[str] = []
    if not gpu_names:
        notes.append("nvidia_smi_not_found_or_no_nvidia_gpu")
    if gpu_names and not _server_exists("cuda"):
        notes.append("llama_cuda_server_not_found")
    if not vulkan_usable:
        notes.append("vulkan_backend_unavailable")
    recommended = "llama_cpp_completion_cpu"
    if cuda_usable:
        recommended = "llama_cpp_completion_cuda"
    elif vulkan_usable:
        recommended = "llama_cpp_completion_vulkan"
    return DeviceInfo(
        memory_size_gb=memory_size_gb,
        vram_size_gb=vram_size_gb,
        gpu_names=gpu_names,
        is_torch_cuda_usable=cuda_usable,
        is_vulkan_usable=vulkan_usable,
        recommended_llm_backend=recommended,
        notes=notes,
    )


def device_report(info: DeviceInfo, language: str = "ja") -> str:
    if language == "en":
        gpu = ", ".join(info.gpu_names) if info.gpu_names else "not detected"
        return "\n".join(
            [
                f"GPU: {gpu}",
                f"VRAM: {info.vram_size_gb or '-'} GB",
                f"RAM: {info.memory_size_gb or '-'} GB",
                f"CUDA backend: {'available' if info.is_torch_cuda_usable else 'unavailable'}",
                f"Vulkan backend: {'available' if info.is_vulkan_usable else 'unavailable'}",
                f"Recommended LLM backend: {info.recommended_llm_backend}",
            ]
        )
    gpu = ", ".join(info.gpu_names) if info.gpu_names else "未検出"
    return "\n".join(
        [
            f"GPU: {gpu}",
            f"VRAM: {info.vram_size_gb or '-'} GB",
            f"RAM: {info.memory_size_gb or '-'} GB",
            f"CUDAバックエンド: {'利用可能' if info.is_torch_cuda_usable else '利用不可'}",
            f"Vulkanバックエンド: {'利用可能' if info.is_vulkan_usable else '利用不可'}",
            f"推奨LLMバックエンド: {info.recommended_llm_backend}",
        ]
    )


def _server_exists(kind: str) -> bool:
    paths = {
        "cpu": BIN_DIR / "llama" / "llama-server.exe",
        "vulkan": BIN_DIR / "llama" / "llama-server.exe",
        "cuda": BIN_DIR / "llama-cuda" / "llama-server.exe",
    }
    return paths[kind].is_file()


def _system_memory_gb() -> int:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return max(1, round(status.ullTotalPhys / (1024**3)))
    except Exception:
        return 0
    return 0


def _nvidia_smi_gpus() -> tuple[list[str], int]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return [], 0
    try:
        completed = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except Exception:
        return [], 0
    if completed.returncode != 0:
        return [], 0
    names: list[str] = []
    total_mb = 0
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if not parts or not parts[0]:
            continue
        names.append(parts[0])
        if len(parts) > 1:
            try:
                total_mb += int(float(parts[1]))
            except ValueError:
                pass
    return names, round(total_mb / 1024) if total_mb else 0


def _windows_video_controllers() -> tuple[list[str], int]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return [], 0
    command = [
        powershell,
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_VideoController | ForEach-Object { \"$($_.Name)|$($_.AdapterRAM)\" }",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            check=False,
        )
    except Exception:
        return [], 0
    if completed.returncode != 0:
        return [], 0
    names: list[str] = []
    total_bytes = 0
    for line in completed.stdout.splitlines():
        name, _, ram = line.partition("|")
        name = name.strip()
        if not name:
            continue
        names.append(name)
        try:
            total_bytes += int(ram.strip() or "0")
        except ValueError:
            pass
    return names, round(total_bytes / (1024**3)) if total_bytes else 0


def _has_vulkan_runtime() -> bool:
    if shutil.which("vulkaninfo"):
        return True
    common = [
        Path("C:/Windows/System32/vulkan-1.dll"),
        Path("C:/Windows/SysWOW64/vulkan-1.dll"),
    ]
    return any(path.exists() for path in common)
