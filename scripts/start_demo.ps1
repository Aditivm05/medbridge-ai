# MedBridge AI — Hackathon Demo Starter Script (PowerShell)
# Starts FastAPI Backend (port 8000) and Vite Frontend (port 5173) in local demo mode.
# Features: dynamic Node discovery, port conflict diagnostics, and readiness polling.

param (
    [switch]$CheckOnly
)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   MedBridge AI -- Care Coordination Hackathon Demo Launcher " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

# 1. Verify Virtual Environment
if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: Backend virtual environment not found at:" -ForegroundColor Red
    Write-Host "  $VenvPython" -ForegroundColor Red
    Write-Host "Please set up the venv first: python -m venv backend\.venv" -ForegroundColor Yellow
    exit 1
}

# 2. Resolve Node.js Dynamically (Avoid hardcoded machine paths)
$NodeDir = ""
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    $NodeDir = Split-Path $nodeCmd.Source -Parent
} else {
    $wingetNode = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Filter "node.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetNode) {
        $NodeDir = $wingetNode.DirectoryName
    } elseif (Test-Path "C:\Program Files\nodejs\node.exe") {
        $NodeDir = "C:\Program Files\nodejs"
    }
}

if (-not $NodeDir) {
    Write-Host "WARNING: Node.js executable could not be found in PATH or standard locations." -ForegroundColor Yellow
    Write-Host "Vite dev server may fail if node is not accessible." -ForegroundColor Yellow
} else {
    Write-Host "OK: Node.js resolved: $NodeDir" -ForegroundColor Green
}

# 3. Check Port 8000 (Backend)
$port8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$backendAlreadyRunning = $false

if ($port8000) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
        if ($health.status -eq "healthy") {
            Write-Host "INFO: Backend is already running and healthy on http://127.0.0.1:8000 (PID: $($port8000.OwningProcess))" -ForegroundColor Green
            $backendAlreadyRunning = $true
        }
    } catch {
        Write-Host "WARNING: Port 8000 is occupied by PID $($port8000.OwningProcess), but /health did not respond." -ForegroundColor Yellow
        Write-Host "If this is a stale process, terminate it before continuing: Stop-Process -Id $($port8000.OwningProcess)" -ForegroundColor Yellow
    }
}

if (-not $backendAlreadyRunning -and -not $CheckOnly) {
    Write-Host "1. Starting FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Yellow
    $backendCmd = "cd '$BackendDir'; `$env:TESTING='1'; .\.venv\Scripts\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

    # Poll readiness for up to 10 seconds
    Write-Host "   Waiting for backend health check..." -NoNewline
    $ready = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Seconds 1
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1
            if ($h.status -eq "healthy") {
                $ready = $true
                break
            }
        } catch {}
        Write-Host "." -NoNewline
    }
    Write-Host ""
    if ($ready) {
        Write-Host "OK: Backend is healthy and ready!" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Backend took longer than expected to report healthy. Check the backend window." -ForegroundColor Yellow
    }
}

# 4. Check Port 5173 (Frontend)
$port5173 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$frontendAlreadyRunning = $false

if ($port5173) {
    Write-Host "INFO: Frontend is already running on http://127.0.0.1:5173 (PID: $($port5173.OwningProcess))" -ForegroundColor Green
    $frontendAlreadyRunning = $true
}

if (-not $frontendAlreadyRunning -and -not $CheckOnly) {
    Write-Host "2. Starting Vite Frontend on http://127.0.0.1:5173..." -ForegroundColor Yellow
    $nodeInject = ""
    if ($NodeDir) {
        $nodeInject = "`$env:Path = '$NodeDir;' + `$env:Path; "
    }
    $frontendCmd = "cd '$FrontendDir'; $nodeInject npm run dev -- --host 127.0.0.1 --port 5173"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
    Start-Sleep -Seconds 2
    Write-Host "OK: Frontend launched." -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   DEMO STATUS: READY FOR REHEARSAL AND PRESENTATION        " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Frontend Application: http://127.0.0.1:5173" -ForegroundColor White
Write-Host "FastAPI Health Probe: http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host "FastAPI Swagger Docs: http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "NOTE: Demo runs in in-memory simulation mode (TESTING=1)." -ForegroundColor Yellow
Write-Host "Data is kept in memory during the session and resets upon restart." -ForegroundColor Yellow
Write-Host "To verify the complete live journey anytime, run:" -ForegroundColor Cyan
Write-Host "  python scripts\verify_live_demo.py" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
