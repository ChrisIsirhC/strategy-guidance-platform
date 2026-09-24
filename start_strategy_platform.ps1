$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = 'C:\Users\chris\AppData\Local\Programs\Python\Python313\python.exe'
$sitePort = 8511
$syncPort = 4174
$siteUrl = "http://127.0.0.1:$sitePort/"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python not found: $python"
}

function Get-ListenerPid([int]$port) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::1', '::') } |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Assert-OurListener([int]$port, [string]$expected) {
    $listenerPid = Get-ListenerPid $port
    if (-not $listenerPid) { return $false }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerPid" -ErrorAction SilentlyContinue
    if (-not $process -or $process.CommandLine -notmatch [regex]::Escape($expected)) {
        throw "Port $port is already in use by PID $listenerPid. Close that program before starting the strategy platform."
    }
    return $true
}

try {
    Set-Location -LiteralPath $projectRoot

    # Keep local incremental sync in the background; the browser opens Streamlit.
    if (-not (Assert-OurListener $syncPort 'strategy_platform_server.py')) {
        Start-Process -FilePath $python -ArgumentList @(('"' + (Join-Path $projectRoot 'strategy_platform_server.py') + '"'), '--port', "$syncPort") -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
        Write-Host 'Local daily-sheet sync started.'
    }

    if (-not (Assert-OurListener $sitePort 'app.py')) {
        $stdoutLog = Join-Path $env:TEMP 'strategy-platform-streamlit.out.log'
        $stderrLog = Join-Path $env:TEMP 'strategy-platform-streamlit.err.log'
        $siteProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'streamlit', 'run', ('"' + (Join-Path $projectRoot 'app.py') + '"'), "--server.port=$sitePort", '--server.address=127.0.0.1', '--server.headless=true', '--browser.gatherUsageStats=false') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
        Write-Host 'Current Streamlit site started.'
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($siteProcess) {
            $siteProcess.Refresh()
            if ($siteProcess.HasExited) {
                $details = Get-Content -LiteralPath $stderrLog -Tail 8 -ErrorAction SilentlyContinue
                throw "Streamlit exited with code $($siteProcess.ExitCode). $details"
            }
        }
        try {
            $response = Invoke-WebRequest -Uri "$siteUrl`_stcore/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and $response.Content.Trim() -eq 'ok') {
                $ready = $true
                break
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Streamlit did not become ready at $siteUrl within 20 seconds." }

    Start-Process $siteUrl | Out-Null
    Write-Host "Opened $siteUrl"
} catch {
    Write-Error $_
    exit 1
}
