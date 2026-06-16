function Get-FantasiaRuntimeProfile {
    param(
        [Parameter(Mandatory = $true)]$Config,
        [ValidateSet("auto", "cuda", "vulkan", "cpu", "all")]
        [string]$RequestedProfile = "auto"
    )

    if ($RequestedProfile -ne "auto") {
        return $RequestedProfile
    }

    $modelSetting = $Config.ai_setting.local_model_setting
    $llmBackend = [string]$modelSetting.llm_backend
    $sdServerPath = [string]$modelSetting.sdxl.sd_server_path

    if ($llmBackend -like "*cuda*" -or $sdServerPath -like "*-cuda*") {
        return "cuda"
    }
    if ($llmBackend -like "*vulkan*" -or $sdServerPath -like "*vulkan*") {
        return "vulkan"
    }
    return "cpu"
}

function Assert-FantasiaPathUnder {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside target root: $resolvedPath"
    }
}

function Get-FantasiaRuntimeFolderChoices {
    param(
        [ValidateSet("cuda", "vulkan", "cpu", "all")]
        [string]$Profile
    )

    $choices = switch ($Profile) {
        "cuda" {
            [pscustomobject]@{ Choices = @("llama-cuda") }
            [pscustomobject]@{ Choices = @("stable-diffusion.cpp-cuda") }
        }
        "vulkan" {
            [pscustomobject]@{ Choices = @("llama-vulkan", "llama") }
            [pscustomobject]@{ Choices = @("stable-diffusion.cpp-vulkan", "stable-diffusion.cpp") }
        }
        "cpu" {
            [pscustomobject]@{ Choices = @("llama") }
            [pscustomobject]@{ Choices = @("stable-diffusion.cpp") }
        }
        "all" {
            [pscustomobject]@{ Choices = @("llama") }
            [pscustomobject]@{ Choices = @("llama-vulkan") }
            [pscustomobject]@{ Choices = @("llama-cuda") }
            [pscustomobject]@{ Choices = @("stable-diffusion.cpp") }
            [pscustomobject]@{ Choices = @("stable-diffusion.cpp-vulkan") }
            [pscustomobject]@{ Choices = @("stable-diffusion.cpp-cuda") }
        }
    }
    return $choices
}

function Sync-FantasiaRuntimeBinaries {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$DistRoot,
        [Parameter(Mandatory = $true)]$Config,
        [ValidateSet("auto", "cuda", "vulkan", "cpu", "all")]
        [string]$RuntimeProfile = "auto"
    )

    $profile = Get-FantasiaRuntimeProfile -Config $Config -RequestedProfile $RuntimeProfile
    $sourceBin = Join-Path $Root "bin"
    $distBin = Join-Path $DistRoot "bin"
    New-Item -ItemType Directory -Force -Path $distBin | Out-Null

    $knownFolders = @(
        "llama",
        "llama-vulkan",
        "llama-cuda",
        "stable-diffusion.cpp",
        "stable-diffusion.cpp-vulkan",
        "stable-diffusion.cpp-cuda"
    )

    foreach ($folder in $knownFolders) {
        $target = Join-Path $distBin $folder
        Assert-FantasiaPathUnder -Path $target -Root $distBin
        if (Test-Path $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
            Write-Host "Removed runtime bin: bin\$folder"
        }
    }

    $copied = New-Object System.Collections.Generic.List[string]
    foreach ($group in Get-FantasiaRuntimeFolderChoices -Profile $profile) {
        $choices = @($group.Choices)
        $selected = ""
        foreach ($choice in $choices) {
            $source = Join-Path $sourceBin $choice
            if (Test-Path $source) {
                $selected = $choice
                break
            }
        }
        if ([string]::IsNullOrWhiteSpace($selected)) {
            Write-Warning "No runtime folder found for choices: $($choices -join ', ')"
            continue
        }

        if ($copied.Contains($selected)) {
            continue
        }
        $sourcePath = Join-Path $sourceBin $selected
        $targetPath = Join-Path $distBin $selected
        Assert-FantasiaPathUnder -Path $targetPath -Root $distBin
        Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Recurse -Force
        $copied.Add($selected) | Out-Null
        Write-Host "Copied runtime bin: bin\$selected"
    }

    Write-Host "Runtime binary profile: $profile"
}
