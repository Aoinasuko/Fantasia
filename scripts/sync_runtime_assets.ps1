param(
    [switch]$Copy,
    [switch]$IncludeModels,
    [switch]$Force,
    [ValidateSet("auto", "cuda", "vulkan", "cpu", "all")]
    [string]$RuntimeProfile = "auto",
    [string]$DistRoot = "",
    [string]$ModelRoot = ""
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($DistRoot)) {
    $DistRoot = Join-Path $root "publish\.fantasia_runtime"
}
$distRoot = $DistRoot
$configPath = Join-Path $root "config.json"

. (Join-Path $PSScriptRoot "runtime_binaries.ps1")

if (-not (Test-Path $distRoot)) {
    throw "Build output not found: $distRoot. Run scripts\build_exe.ps1 first."
}

if ([string]::IsNullOrWhiteSpace($ModelRoot)) {
    $ModelRoot = Join-Path (Split-Path -Parent $distRoot) "model"
}

$config = Get-Content -Raw -Encoding UTF8 $configPath | ConvertFrom-Json
$modelSetting = $config.ai_setting.local_model_setting

Sync-FantasiaRuntimeBinaries -Root $root -DistRoot $distRoot -Config $config -RuntimeProfile $RuntimeProfile

function Resolve-ProjectPath([string]$path) {
    if ([System.IO.Path]::IsPathRooted($path)) {
        return $path
    }
    return Join-Path $root $path
}

function Resolve-ModelSourcePath([string]$relativeModelPath) {
    $workspaceSource = Resolve-ProjectPath $relativeModelPath
    if (Test-Path $workspaceSource) {
        return $workspaceSource
    }

    $publishModelRoot = Join-Path (Split-Path -Parent $distRoot) "model"
    $publishCandidate = Join-Path $publishModelRoot $relativeModelPath
    if (Test-Path $publishCandidate) {
        return $publishCandidate
    }

    return $workspaceSource
}

function Assert-TargetPath([string]$target) {
    $resolvedTarget = [System.IO.Path]::GetFullPath($target)
    $resolvedDist = [System.IO.Path]::GetFullPath($distRoot)
    if (-not $resolvedTarget.StartsWith($resolvedDist, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to sync outside publish runtime folder: $resolvedTarget"
    }
}

function Assert-ModelTargetPath([string]$target) {
    $resolvedTarget = [System.IO.Path]::GetFullPath($target)
    $resolvedModelRoot = [System.IO.Path]::GetFullPath($ModelRoot)
    if (-not $resolvedTarget.StartsWith($resolvedModelRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to sync model outside model folder: $resolvedTarget"
    }
}

function Normalize-ModelRelative([string]$value) {
    $normalized = $value.Trim().Replace("\\", "/")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return ""
    }

    if ($normalized -like "model/*") {
        return $normalized.Substring(6)
    }
    if ($normalized -like "text/*" -or $normalized -like "graphic/*") {
        return $normalized
    }
    if ($normalized -like "runtime/models/llama_cpp/*") {
        return "text/" + $normalized.Substring("runtime/models/llama_cpp/".Length)
    }
    if ($normalized -like "runtime/models/sdxl/*") {
        return "graphic/" + $normalized.Substring("runtime/models/sdxl/".Length)
    }

    $ext = [System.IO.Path]::GetExtension($normalized).ToLowerInvariant()
    if ($ext -eq ".gguf") {
        return "text/$normalized"
    }
    if ($ext -in ".safetensors", ".ckpt", ".pt", ".bin") {
        return "graphic/$normalized"
    }
    return $normalized
}

function Sync-File([string]$relativePath) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        Write-Warning "Skipped empty asset path"
        return
    }
    if ([System.IO.Path]::IsPathRooted($relativePath)) {
        Write-Warning "Skipped absolute asset path for safe packaging: $relativePath"
        return
    }
    $source = Resolve-ProjectPath $relativePath
    $target = Join-Path $distRoot $relativePath
    Assert-TargetPath $target

    if (-not (Test-Path $source)) {
        Write-Warning "Missing source asset: $source"
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null

    if (Test-Path $target) {
        $sourceSize = (Get-Item $source).Length
        $targetSize = (Get-Item $target).Length
        if ($sourceSize -eq $targetSize) {
            Write-Host "Already synced: $relativePath"
            return
        }
        if (-not $Force) {
            Write-Warning "Target already exists with a different size, skipped: $target"
            return
        } else {
            $backup = "$target.bak.$(Get-Date -Format yyyyMMddHHmmss)"
            Move-Item -LiteralPath $target -Destination $backup
            Write-Warning "Backed up different target: $backup"
        }
    }

    $tempTarget = "$target.tmp.$([guid]::NewGuid().ToString('N'))"
    if ($Copy) {
        Copy-Item -LiteralPath $source -Destination $tempTarget
        Move-Item -LiteralPath $tempTarget -Destination $target
        Write-Host "Copied: $relativePath"
        return
    }

    try {
        New-Item -ItemType HardLink -Path $tempTarget -Target $source | Out-Null
        Move-Item -LiteralPath $tempTarget -Destination $target
        Write-Host "Hardlinked: $relativePath"
    } catch {
        if (Test-Path $tempTarget) {
            Remove-Item -LiteralPath $tempTarget -Force
        }
        Copy-Item -LiteralPath $source -Destination $tempTarget
        Move-Item -LiteralPath $tempTarget -Destination $target
        Write-Host "Copied: $relativePath"
    }
}

function Sync-ModelFile([string]$relativePath) {
    $normalized = Normalize-ModelRelative $relativePath
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        Write-Warning "Skipped empty model path"
        return
    }
    if ([System.IO.Path]::IsPathRooted($normalized)) {
        Write-Warning "Skipped absolute model path for safe packaging: $normalized"
        return
    }

    $source = Resolve-ModelSourcePath $normalized
    $target = Join-Path $ModelRoot $normalized
    Assert-ModelTargetPath $target

    if (-not (Test-Path $source)) {
        Write-Warning "Missing source model: $source"
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null

    if (Test-Path $target) {
        $sourceSize = (Get-Item $source).Length
        $targetSize = (Get-Item $target).Length
        if ($sourceSize -eq $targetSize) {
            Write-Host "Already synced model: $normalized"
            return
        }
        if (-not $Force) {
            Write-Warning "Target model already exists with different size, skipped: $target"
            return
        } else {
            $backup = "$target.bak.$(Get-Date -Format yyyyMMddHHmmss)"
            Move-Item -LiteralPath $target -Destination $backup
            Write-Warning "Backed up different model target: $backup"
        }
    }

    $tempTarget = "$target.tmp.$([guid]::NewGuid().ToString('N'))"
    if ($Copy) {
        Copy-Item -LiteralPath $source -Destination $tempTarget
        Move-Item -LiteralPath $tempTarget -Destination $target
        Write-Host "Synced model: $normalized"
        return
    }

    try {
        New-Item -ItemType HardLink -Path $tempTarget -Target $source | Out-Null
        Move-Item -LiteralPath $tempTarget -Destination $target
        Write-Host "Synced model: $normalized"
    } catch {
        if (Test-Path $tempTarget) {
            Remove-Item -LiteralPath $tempTarget -Force
        }
        Copy-Item -LiteralPath $source -Destination $tempTarget
        Move-Item -LiteralPath $tempTarget -Destination $target
        Write-Host "Synced model: $normalized"
    }
}

function Remove-DistFile([string]$relativePath) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        return
    }
    if ([System.IO.Path]::IsPathRooted($relativePath)) {
        return
    }
    $normalized = Normalize-ModelRelative $relativePath
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return
    }
    if ([System.IO.Path]::IsPathRooted($normalized)) {
        return
    }
    $target = Join-Path $ModelRoot $normalized
    Assert-ModelTargetPath $target
    if (Test-Path $target) {
        Remove-Item -LiteralPath $target -Force
        Write-Host "Removed bundled model: $relativePath"
    }
}

New-Item -ItemType Directory -Force -Path `
    (Join-Path $distRoot "runtime\generated"), `
    (Join-Path $ModelRoot "text"), `
    (Join-Path $ModelRoot "graphic") | Out-Null

if ($IncludeModels) {
    if ([string]$modelSetting.llm_backend -like "llama_cpp_completion*") {
        Sync-ModelFile ([string]$modelSetting.local_llm.model_path)
    }

    if ($modelSetting.image_backend.name -eq "stable_diffusion_cpp") {
        Sync-ModelFile ([string]$modelSetting.sdxl.checkpoint_path)
    }
} else {
    if ([string]$modelSetting.llm_backend -like "llama_cpp_completion*") {
        Remove-DistFile ([string]$modelSetting.local_llm.model_path)
    }

    if ($modelSetting.image_backend.name -eq "stable_diffusion_cpp") {
        Remove-DistFile ([string]$modelSetting.sdxl.checkpoint_path)
    }
    Write-Host "Skipped model sync. Use -IncludeModels to package local GGUF/SDXL files."
}
