# Linescan Pipeline Launcher
# Simple wrapper around the linescan recording pipeline with sensible defaults
# Run from workspace root: c:\dev\gst-plugins-vision

param(
    [Parameter(Position=0)]
    [ValidateSet('day', 'night')]
    [string]$Mode = 'day',

    [Parameter(Position=1)]
    [string]$OutputDir,
    
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Linescan Pipeline Launcher

Usage: .\launch_linescan.ps1 [day|night] [output-dir] [-Help]

Modes:
  day   - Day mode: exposure=0.02ms, gain=0, framerate=200fps (default)
  night - Night mode: exposure=5.25ms, gain=65, framerate=200fps

This launcher records linescan output to JPEG frames using:
  gst\linescan\launch_with_signal.py

Default settings (inherited from launch_with_signal.py):
  - Config: ini/roi-dusk.ini
  - Device ID: 1
  - Intervalometer: enabled
  - Ramp rate: slow
  - Update interval: 1000ms
  - Brightness deadband: 10.0
  - Gain max: 82
  - Target brightness: 80
  - Log file: timelapse.csv
  - Output: results/<date>/<funny-name>/linescan_capture_*.jpg

Examples:
  .\launch_linescan.ps1                # Run in day mode (default)
  .\launch_linescan.ps1 day            # Run in day mode (explicit)
  .\launch_linescan.ps1 night          # Run in night mode
  .\launch_linescan.ps1 night captures # Write JPEG frames to .\captures
  .\launch_linescan.ps1 -Help          # Show this help
"@
    exit 0
}

$env:GST_DEBUG="linescan:5"

Write-Host "Launching linescan recording pipeline in $Mode mode..."
Write-Host ""

# launch_with_signal.py handles the linescan pipeline and JPEG output.
$args = @(
    '.\gst\linescan\launch_with_signal.py',
    '--mode', $Mode
)

if ($OutputDir) {
    $args += @('--output-dir', $OutputDir)
}

uv run @args
