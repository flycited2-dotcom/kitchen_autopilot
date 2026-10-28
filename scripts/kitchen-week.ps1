# План на неделю: plans\<понедельник>.json и .txt. Без параметра — ближайший следующий понедельник.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts\kitchen-week.ps1 [2026-11-02]
param([string]$Date)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
if (-not $Date) {
    $d = (Get-Date).Date.AddDays(1)
    while ($d.DayOfWeek -ne [DayOfWeek]::Monday) { $d = $d.AddDays(1) }
    $Date = $d.ToString("yyyy-MM-dd")
}
New-Item -ItemType Directory -Force (Join-Path $root "plans"), (Join-Path $root "logs") | Out-Null
Set-Location $root
# Песочница: только настройки проекта + headless-settings.json, без пользовательских разрешений и MCP-серверов.
claude -p "/kitchen-week $Date" --setting-sources project --settings scripts/headless-settings.json --strict-mcp-config --output-format json |
    Out-File -Encoding utf8 (Join-Path $root "logs\week-$Date.json")
Get-Content (Join-Path $root "plans\$Date.txt") -Encoding UTF8 -ErrorAction SilentlyContinue
