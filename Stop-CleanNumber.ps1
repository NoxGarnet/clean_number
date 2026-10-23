$ErrorActionPreference = 'Stop'
$serverMarker = Join-Path $PSScriptRoot '.local-ui\server.json'
if (-not (Test-Path -LiteralPath $serverMarker)) { Write-Output 'Workbench is not running.'; exit 0 }
$saved = Get-Content -LiteralPath $serverMarker -Raw -Encoding UTF8 | ConvertFrom-Json
if ($saved.url -notmatch '^http://127\.0\.0\.1:\d+/$') { throw 'Invalid workbench address.' }
try { $health = Invoke-RestMethod -Uri ($saved.url + 'api/health') -TimeoutSec 2 } catch { Write-Output 'Workbench is already stopped.'; exit 0 }
if ($health.app -ne 'clean_number_ui' -or $health.tool_root -ne $PSScriptRoot -or $health.pid -ne $saved.pid) {
    throw 'Server identity did not match; no process was stopped.'
}
# Ask this specific local server to stop so an active child analysis is also
# terminated and its partial output remains visible as cancelled.
$page = (Invoke-WebRequest -UseBasicParsing -Uri $saved.url -TimeoutSec 2).Content
$match = [regex]::Match($page, 'name="local-api-token"\s+content="([^"]+)"')
if (-not $match.Success) { throw 'Could not identify the local session.' }
$headers = @{ 'X-Clean-Number-Token' = $match.Groups[1].Value }
$null = Invoke-RestMethod -Uri ($saved.url + 'api/shutdown') -Method Post -Headers $headers -ContentType 'application/json' -Body '{}' -TimeoutSec 3
Write-Output 'Workbench stopped.'
