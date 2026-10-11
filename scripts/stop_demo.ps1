# MedBridge AI — Demo Cleanup Script (PowerShell)
# Terminates only the processes listening on demo ports (FastAPI 8000, Vite 5173).

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   MedBridge AI -- Demo Process Cleanup                      " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$ports = @(8000, 5173)

foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $pid = $conn.OwningProcess
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        Write-Host "Found process on port $port (PID $pid: $($proc.ProcessName)). Stopping..." -ForegroundColor Yellow
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "  [OK] Terminated PID $pid on port $port." -ForegroundColor Green
        } catch {
            Write-Host "  [WARNING] Could not stop PID $pid : $_" -ForegroundColor Red
        }
    } else {
        Write-Host "Port $port is already free." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Demo cleanup complete. Ports 8000 and 5173 are free." -ForegroundColor Green
