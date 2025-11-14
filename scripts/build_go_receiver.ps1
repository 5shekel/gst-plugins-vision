# Build script for Go UDP receiver on Windows
# Run this script to compile the high-performance Go receiver

$ErrorActionPreference = "Stop"

Write-Host "Building Go UDP Receiver..." -ForegroundColor Cyan

# Check if Go is installed
try {
    $goVersion = go version
    Write-Host "✓ Found Go: $goVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Go is not installed or not in PATH" -ForegroundColor Red
    Write-Host "  Download from: https://go.dev/dl/" -ForegroundColor Yellow
    exit 1
}

# Navigate to scripts/go directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$goDir = Join-Path $scriptDir "go"
Set-Location $goDir

# Clean dependencies
Write-Host "`nCleaning dependencies..." -ForegroundColor Cyan
go mod tidy

# Build the executable
Write-Host "`nBuilding executable..." -ForegroundColor Cyan
go build -o recv_raw_rolling.exe main.go

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Build successful!" -ForegroundColor Green
    Write-Host "  Executable: scripts\go\recv_raw_rolling.exe" -ForegroundColor Green
    Write-Host "`nTo run:" -ForegroundColor Yellow
    Write-Host "  cd scripts\go" -ForegroundColor White
    Write-Host "  .\recv_raw_rolling.exe" -ForegroundColor White
    Write-Host "`nPress ESC to quit the application" -ForegroundColor Gray
} else {
    Write-Host "`n✗ Build failed!" -ForegroundColor Red
    Write-Host "  See scripts\go\README.md for troubleshooting" -ForegroundColor Yellow
    exit 1
}