# Windows Startup Script for Linescan System
# This script starts both launch_linescan.ps1 and launch_with_signal.py
# Designed to run on system boot with configurable delay
#
# Usage:
#   .\startup_linescan.ps1                    # Run with default 30s delay
#   .\startup_linescan.ps1 -DelaySeconds 60   # Run with custom delay
#   .\startup_linescan.ps1 -NoDelay           # Run immediately
#   .\startup_linescan.ps1 -Help              # Show help
#
# To register for startup, run:
#   .\register_startup.ps1

param(
    [Parameter()]
    [int]$DelaySeconds = 10,
    
    [Parameter()]
    [switch]$NoDelay,
    
    [Parameter()]
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Windows Startup Script for Linescan System

This script launches both linescan components on system startup:
  1. launch_linescan.ps1 (pipeline launcher wrapper)
  2. gst/linescan/launch_with_signal.py (signal capture)

Usage:
  .\startup_linescan.ps1                    # Default 30 second delay
  .\startup_linescan.ps1 -DelaySeconds 60   # Custom delay
  .\startup_linescan.ps1 -NoDelay           # No delay (immediate start)
  .\startup_linescan.ps1 -Help              # Show this help

Parameters:
  -DelaySeconds <int>  Delay in seconds before starting (default: 30)
  -NoDelay             Skip delay and start immediately
  -Help                Show this help message

Installation:
  To register this script to run on Windows startup, use:
    .\register_startup.ps1

  This will create a Task Scheduler task that runs this script
  automatically when Windows starts (after user login).

Notes:
  - Both scripts run in separate PowerShell windows for monitoring
  - Scripts are launched from workspace root: c:\dev\gst-plugins-vision
  - Logs are written to: startup_linescan.log
  - Windows must be closed manually (Ctrl+C) to stop the pipelines
"@
    exit 0
}

# Define paths (relative to workspace root)
$workspaceRoot = "c:\dev\gst-plugins-vision"
$logFile = Join-Path $workspaceRoot "startup_linescan.log"

# Function to write to log file
function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] $Message"
    Write-Host $logMessage
    Add-Content -Path $logFile -Value $logMessage
}

# Start logging
Write-Log "=== Linescan Startup Script Started ==="
Write-Log "Workspace: $workspaceRoot"

# Verify workspace directory exists
if (-not (Test-Path $workspaceRoot)) {
    Write-Log "ERROR: Workspace directory not found: $workspaceRoot"
    Write-Log "Please update the `$workspaceRoot variable in this script"
    exit 1
}

# Change to workspace directory
Set-Location $workspaceRoot
Write-Log "Working directory: $(Get-Location)"

# Apply delay if requested
if (-not $NoDelay) {
    Write-Log "Waiting $DelaySeconds seconds for system to stabilize..."
    Start-Sleep -Seconds $DelaySeconds
    Write-Log "Delay complete, starting scripts..."
}

# Determine mode based on time of day (after 5pm = night mode)
$currentHour = (Get-Date).Hour
if ($currentHour -ge 17) {
    $mode = "night"
    Write-Log "Time-based mode selection: After 5pm (hour=$currentHour), using night mode"
} else {
    $mode = "day"
    Write-Log "Time-based mode selection: Before 5pm (hour=$currentHour), using day mode"
}

# Launch launch_linescan.ps1 in a new PowerShell window
$script1Path = Join-Path $workspaceRoot "launch_linescan.ps1"
if (Test-Path $script1Path) {
    Write-Log "Starting launch_linescan.ps1..."
    
    # Start in new PowerShell window with time-based mode
    # Use cd in command since powershell.exe doesn't have -WorkingDirectory
    $process1 = Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$workspaceRoot'; & '$script1Path' $mode"
    ) -PassThru
    
    Write-Log "launch_linescan.ps1 started in $mode mode (PID: $($process1.Id))"
} else {
    Write-Log "WARNING: launch_linescan.ps1 not found at: $script1Path"
}

# Small delay between launches
Start-Sleep -Seconds 2

# Launch gst/linescan/launch_with_signal.py in a new PowerShell window
$script2Path = Join-Path $workspaceRoot "gst\linescan\launch_with_signal.py"
if (Test-Path $script2Path) {
    Write-Log "Starting launch_with_signal.py..."
    
    # Start in new PowerShell window using uv run
    # Use cd in command since powershell.exe doesn't have -WorkingDirectory
    $process2 = Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$workspaceRoot'; uv run '$script2Path'"
    ) -PassThru
    
    Write-Log "launch_with_signal.py started (PID: $($process2.Id))"
} else {
    Write-Log "WARNING: launch_with_signal.py not found at: $script2Path"
}

Write-Log "=== All scripts launched successfully ==="
Write-Log "Log file: $logFile"
Write-Log ""
Write-Log "To stop the pipelines:"
Write-Log "  1. Press Ctrl+C in each PowerShell window"
Write-Log "  2. Or close the PowerShell windows"
Write-Log ""
Write-Log "Startup script completed. Check individual windows for output."
