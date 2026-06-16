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

$env:PYTHONPATH = Join-Path $root "src"
& $python -m fantasia.app
