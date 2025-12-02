# Linescan Pipeline Launcher
# Simple wrapper around launch-ids.py with sensible defaults
# Run from workspace root: c:\dev\gst-plugins-vision

param(
    [Parameter(Position=0)]
    [ValidateSet('day', 'night')]
    [string]$Mode = 'day',
    
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Linescan Pipeline Launcher

Usage: .\launch_linescan.ps1 [day|night] [-Help]

Modes:
  day   - Day mode: exposure=0.2ms, gain=0, framerate=200fps (default)
  night - Night mode: exposure=5.25ms, gain=65, framerate=200fps

All settings are configured in launch-ids.py with these defaults:
  - Config: ini/roi-night.ini
  - Device ID: 1
  - Intervalometer: enabled
  - Ramp rate: fast
  - Update interval: 500ms
  - Brightness deadband: 10.0
  - Gain max: 82
  - Target brightness: 80
  - Log file: timelapse.csv

Examples:
  .\launch_linescan.ps1           # Run in day mode (default)
  .\launch_linescan.ps1 day       # Run in day mode (explicit)
  .\launch_linescan.ps1 night     # Run in night mode
  .\launch_linescan.ps1 -Help     # Show this help
"@
    exit 0
}

$env:GST_DEBUG="linescan:5"

Write-Host "Launching linescan pipeline in $Mode mode..."
Write-Host ""

# All configuration is handled by launch-ids.py defaults
uv run .\scripts\launch-ids.py --mode $Mode --device-id 2