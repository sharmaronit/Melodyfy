# Melodyfy Server - Auto-restart watchdog
# Run this once: powershell -ExecutionPolicy Bypass -File start_server.ps1

$python = "D:\Ronit Sharma\vs code\ML Models\.conda\python.exe"
$script = "D:\Ronit Sharma\vs code\ML Models\hack\api_server.py"
$dir    = "D:\Ronit Sharma\vs code\ML Models\hack"

Write-Host "=== Melodyfy Server Watchdog ===" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

while ($true) {
    Write-Host "[$(Get-Date -f 'HH:mm:ss')] Starting server..." -ForegroundColor Green
    Set-Location $dir
    & $python $script
    $code = $LASTEXITCODE
    Write-Host "[$(Get-Date -f 'HH:mm:ss')] Server exited (code $code). Restarting in 3s..." -ForegroundColor Red
    Start-Sleep 3
}
