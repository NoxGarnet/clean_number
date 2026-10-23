param(
    [string]$Python,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$toolRoot = $PSScriptRoot
$stateRoot = Join-Path $toolRoot '.local-ui'
$serverMarker = Join-Path $stateRoot 'server.json'
New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null

try {
    if (Test-Path -LiteralPath $serverMarker) {
        $saved = Get-Content -LiteralPath $serverMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.url -match '^http://127\.0\.0\.1:\d+/$') {
            try {
                $health = Invoke-RestMethod -Uri ($saved.url + 'api/health') -TimeoutSec 2
                if ($health.app -eq 'clean_number_ui' -and $health.tool_root -eq $toolRoot) {
                    if (-not $NoBrowser) { Start-Process $saved.url }
                    Write-Output $saved.url
                    exit 0
                }
            } catch { }
        }
    }

    $candidates = @()
    if ($Python) { $candidates += $Python }
    $candidates += (Join-Path $toolRoot '.venv\Scripts\python.exe')
    $systemPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($systemPython) { $candidates += $systemPython.Source }
    $selectedPython = $null
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        & $candidate -c 'import numpy,pandas,matplotlib,scipy,yaml,openpyxl,xlrd' 2>$null
        if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
    }
    if (-not $selectedPython) {
        throw 'No usable Python environment found. Follow docs/LOCAL_UI.md to install requirements.txt, then launch again.'
    }

    $serverScript = Join-Path $toolRoot 'local_ui.py'
    $arguments = @('-u', ('"' + $serverScript + '"'), '--no-browser', '--state-dir', ('"' + $stateRoot + '"'))
    $outLog = Join-Path $stateRoot 'server.log'
    $errLog = Join-Path $stateRoot 'server-error.log'
    $serverProcess = Start-Process -FilePath $selectedPython -ArgumentList $arguments -WorkingDirectory $toolRoot -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    $readyUrl = $null
    $startupClock = [System.Diagnostics.Stopwatch]::StartNew()
    while ($startupClock.Elapsed.TotalSeconds -lt 60) {
        Start-Sleep -Milliseconds 200
        $serverProcess.Refresh()
        if (Test-Path -LiteralPath $serverMarker) {
            try {
                $started = Get-Content -LiteralPath $serverMarker -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($started.tool_root -eq $toolRoot -and $started.url -match '^http://127\.0\.0\.1:\d+/$') {
                    $health = Invoke-RestMethod -Uri ($started.url + 'api/health') -TimeoutSec 1
                    if ($health.app -eq 'clean_number_ui' -and $health.tool_root -eq $toolRoot -and $health.pid -eq $started.pid) {
                        $readyUrl = $started.url; break
                    }
                }
            } catch { }
        }
        if ($serverProcess.HasExited) { throw ('Workbench could not start. See ' + $errLog) }
    }
    if (-not $readyUrl) { throw ('Workbench startup timed out. See ' + $errLog) }
    if (-not $NoBrowser) { Start-Process $readyUrl }
    Write-Output $readyUrl
} catch {
    $message = $_.Exception.Message
    $message | Out-File -LiteralPath (Join-Path $stateRoot 'launcher-error.log') -Encoding utf8
    if ($NoBrowser) { Write-Output $message } else {
        $shellPopup = New-Object -ComObject WScript.Shell
        $null = $shellPopup.Popup($message, 0, 'clean_number', 16)
    }
    exit 1
}
