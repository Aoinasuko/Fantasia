param(
    [ValidateSet("auto", "cuda", "vulkan", "cpu", "all")]
    [string]$RuntimeProfile = "auto",
    [switch]$IncludeModels
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    & (Join-Path $PSScriptRoot "setup_env.ps1")
}

$entry = Join-Path $root "main.py"
$buildRoot = Join-Path $root "build\nuitka"
$publishRoot = Join-Path $root "publish"
$runtimeRoot = Join-Path $publishRoot ".fantasia_runtime"
$configPath = Join-Path $root "config.json"
$playGuideSource = Join-Path $root "docs\PLAY_GUIDE.txt"
$dllLicenseSource = Join-Path $root "docs\DLL_LICENSES.txt"
$iconSource = Join-Path $root "docs\icon.png"
$iconPath = Join-Path $buildRoot "Fantasia.ico"

. (Join-Path $PSScriptRoot "runtime_binaries.ps1")

function Assert-PathUnderRoot([string]$Path, [string]$RootPath) {
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($RootPath)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside workspace: $resolvedPath"
    }
}

function Reset-Directory([string]$Path) {
    Assert-PathUnderRoot -Path $Path -RootPath $root
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Get-CSharpCompiler() {
    $where = Get-Command csc.exe -ErrorAction SilentlyContinue
    if ($where) {
        return $where.Source
    }
    $frameworkCsc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if (Test-Path $frameworkCsc) {
        return $frameworkCsc
    }
    throw "csc.exe was not found. Install .NET Framework SDK or Visual Studio Build Tools."
}

function Write-PlayGuide([string]$Path) {
    $lines = @(
        "Fantasia Play Guide",
        "",
        "1. Start the game with Fantasia.exe.",
        "2. On first launch, configure or download the LLM and image generation models from Settings.",
        "3. Save data, worlds, and exports are stored under %LOCALAPPDATA%\BlueEggplant\Fantasia.",
        "4. Runtime logs are created in the log folder beside Fantasia.exe.",
        "5. Crash logs are created in the crashlog folder beside Fantasia.exe.",
        "",
        "The hidden .fantasia_runtime folder contains the game runtime.",
        "Do not move the runtime folder; launch the game through Fantasia.exe."
    )
    [System.IO.File]::WriteAllLines($Path, $lines, $utf8NoBom)
}

function Convert-PngToIcon([string]$SourcePath, [string]$TargetPath) {
    if (-not (Test-Path $SourcePath)) {
        Write-Warning "Icon source not found: $SourcePath"
        return $false
    }
    $script = @'
from pathlib import Path
import sys
from PIL import Image

source = Path(sys.argv[1])
target = Path(sys.argv[2])
target.parent.mkdir(parents=True, exist_ok=True)
image = Image.open(source).convert("RGBA")
image.save(
    target,
    format="ICO",
    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
)
'@
    & $python -c $script $SourcePath $TargetPath
    return (Test-Path $TargetPath)
}

Reset-Directory $buildRoot
Reset-Directory $publishRoot

$hasIcon = Convert-PngToIcon -SourcePath $iconSource -TargetPath $iconPath

$previousPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = "$root\src"
} else {
    $env:PYTHONPATH = "$root\src;$previousPythonPath"
}

try {
    $nuitkaArgs = @(
        "--standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=tk-inter",
        "--include-package=fantasia",
        "--output-dir=$buildRoot",
        "--output-filename=fantasia.exe",
        "--include-data-files=$root\config.json=config.json",
        "--include-data-dir=$root\assets=assets"
    )
    if ($hasIcon) {
        $nuitkaArgs += "--windows-icon-from-ico=$iconPath"
    }
    & $python -m nuitka @nuitkaArgs $entry
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

$distRoot = Join-Path $buildRoot "main.dist"
$config = Get-Content -Raw -Encoding UTF8 $configPath | ConvertFrom-Json
Sync-FantasiaRuntimeBinaries -Root $root -DistRoot $distRoot -Config $config -RuntimeProfile $RuntimeProfile

New-Item -ItemType Directory -Force -Path `
    (Join-Path $distRoot "runtime\generated") | Out-Null

New-Item -ItemType Directory -Force -Path `
    (Join-Path $publishRoot "model\text"), `
    (Join-Path $publishRoot "model\graphic") | Out-Null

if ($IncludeModels) {
    & (Join-Path $PSScriptRoot "sync_runtime_assets.ps1") -DistRoot $distRoot -ModelRoot (Join-Path $publishRoot "model") -IncludeModels -RuntimeProfile $RuntimeProfile -Force
}

Copy-Item -LiteralPath $distRoot -Destination $runtimeRoot -Recurse -Force
$runtimeItem = Get-Item -LiteralPath $runtimeRoot -Force
$runtimeItem.Attributes = $runtimeItem.Attributes -bor [System.IO.FileAttributes]::Hidden

$csc = Get-CSharpCompiler
$launcherSource = Join-Path $PSScriptRoot "FantasiaLauncher.cs"
$launcherExe = Join-Path $publishRoot "Fantasia.exe"
$cscArgs = @("/nologo", "/target:winexe", "/out:$launcherExe")
if ($hasIcon) {
    $cscArgs += "/win32icon:$iconPath"
}
$cscArgs += $launcherSource
& $csc @cscArgs

$playGuideTarget = Join-Path $publishRoot "PLAY_GUIDE.txt"
if (Test-Path $playGuideSource) {
    Copy-Item -LiteralPath $playGuideSource -Destination $playGuideTarget -Force
} else {
    Write-PlayGuide $playGuideTarget
}

$dllLicenseTarget = Join-Path $publishRoot "DLL_LICENSES.txt"
if (Test-Path $dllLicenseSource) {
    Copy-Item -LiteralPath $dllLicenseSource -Destination $dllLicenseTarget -Force
}

Write-Host "Built publish folder: $publishRoot"
Write-Host "Launcher: $launcherExe"
Write-Host "Runtime: $runtimeRoot"
Write-Host "Use scripts\sync_runtime_assets.ps1 after placing model files, or rerun build_exe.ps1 -IncludeModels when intentionally packaging local model files."
