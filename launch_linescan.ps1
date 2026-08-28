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
  day   - Day mode: exposure=0.2ms, gain=0, framerate=200fps (default)
  night - Night mode: exposure=5.25ms, gain=65, framerate=200fps

This launcher records linescan output to MKV fragments using:
  gst\linescan\launch_with_signal.py

Default settings:
  - Config: ini/roi-night.ini
  - Device ID: 2
  - Intervalometer: enabled
  - Ramp rate: slow
  - Update interval: 1000ms
  - Brightness deadband: 10.0
  - Gain max: 82
  - Target brightness: 80
  - Log file: timelapse.csv
  - Output: results/<date>/<funny-name>/linescan_capture_*.mkv

Examples:
  .\launch_linescan.ps1                # Run in day mode (default)
  .\launch_linescan.ps1 day            # Run in day mode (explicit)
  .\launch_linescan.ps1 night          # Run in night mode
  .\launch_linescan.ps1 night captures # Write MKV fragments to .\captures
  .\launch_linescan.ps1 -Help          # Show this help
"@
    exit 0
}

$env:GST_DEBUG="linescan:5"

Write-Host "Launching linescan recording pipeline in $Mode mode..."
Write-Host ""

# launch_with_signal.py handles the linescan pipeline and MKV output.
$args = @(
    '.\gst\linescan\launch_with_signal.py',
    '--mode', $Mode
)

if ($OutputDir) {
    $args += @('--output-dir', $OutputDir)
}

uv run @args
