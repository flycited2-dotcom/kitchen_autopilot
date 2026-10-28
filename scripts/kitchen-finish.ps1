# Сборка роликов дня из clips\, images\, voice\ + финальная проверка. Без параметра — завтрашний день.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\kitchen-finish.ps1 [2026-11-02]
param([string]$Date)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
if (-not $Date) { $Date = (Get-Date).Date.AddDays(1).ToString("yyyy-MM-dd") }
$run = Join-Path $root "runs\$Date"
if (-not (Test-Path $run)) { Write-Host "Нет папки $run — сначала scripts\kitchen-day.ps1 $Date"; exit 1 }
New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null
Set-Location $root
claude -p "/kitchen-finish $Date" --setting-sources project --settings scripts/headless-settings.json --strict-mcp-config --output-format json |
    Out-File -Encoding utf8 (Join-Path $root "logs\finish-$Date.json")
Get-Content (Join-Path $run "summary.txt") -Encoding UTF8 -ErrorAction SilentlyContinue
explorer.exe $run
