# Register Linescan Startup Script with Windows Task Scheduler
# This script creates a scheduled task that runs startup_linescan.ps1 on user login
#
# Usage:
#   .\register_startup.ps1              # Register with default settings
#   .\register_startup.ps1 -Unregister  # Remove the scheduled task
#   .\register_startup.ps1 -Help        # Show help

param(
    [Parameter()]
    [switch]$Unregister,
    
    [Parameter()]
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Register Linescan Startup Script with Windows Task Scheduler

This script creates or removes a Windows Task Scheduler task that automatically
runs startup_linescan.ps1 when you log in to Windows.

Usage:
  .\register_startup.ps1              # Register startup task
  .\register_startup.ps1 -Unregister  # Remove startup task
  .\register_startup.ps1 -Help        # Show this help

Parameters:
  -Unregister  Remove the scheduled task instead of creating it
  -Help        Show this help message

Task Details:
  Task Name: LineScanStartup
  Trigger:   At user logon
  Action:    Run startup_linescan.ps1
  User:      Current user
  Elevated:  No (runs as normal user)

Notes:
  - Must be run from workspace root: c:\dev\gst-plugins-vision
  - Task runs with delay configured in startup_linescan.ps1 (default 30s)
  - Scripts will launch in visible PowerShell windows for monitoring
  - You can also manage the task via Task Scheduler GUI (taskschd.msc)

After Registration:
  - Task will run automatically on next login
  - View task status: Get-ScheduledTask -TaskName "LineScanStartup"
  - Run manually: Start-ScheduledTask -TaskName "LineScanStartup"
  - Disable task: Disable-ScheduledTask -TaskName "LineScanStartup"

"@
    exit 0
}

# Configuration
$taskName = "LineScanStartup"
$workspaceRoot = "c:\dev\gst-plugins-vision"
$scriptPath = Join-Path $workspaceRoot "startup_linescan.ps1"

# Check if running as administrator (not required, but good to know)
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host "=== Linescan Startup Task Registration ==="
Write-Host "Workspace: $workspaceRoot"
Write-Host "Script: $scriptPath"
Write-Host "Running as administrator: $isAdmin"
Write-Host ""

# Verify workspace and script exist
if (-not (Test-Path $workspaceRoot)) {
    Write-Host "ERROR: Workspace directory not found: $workspaceRoot" -ForegroundColor Red
    Write-Host "Please update the `$workspaceRoot variable in this script" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Startup script not found: $scriptPath" -ForegroundColor Red
    Write-Host "Please ensure startup_linescan.ps1 exists in the workspace root" -ForegroundColor Red
    exit 1
}

if ($Unregister) {
    # Remove existing task
    Write-Host "Unregistering scheduled task: $taskName"
    
    try {
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        
        if ($existingTask) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "SUCCESS: Scheduled task '$taskName' has been removed" -ForegroundColor Green
        } else {
            Write-Host "Task '$taskName' not found - nothing to unregister" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "ERROR: Failed to unregister task: $_" -ForegroundColor Red
        exit 1
    }
} else {
    # Register new task
    Write-Host "Registering scheduled task: $taskName"
    
    # Check if task already exists
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "WARNING: Task '$taskName' already exists" -ForegroundColor Yellow
        $response = Read-Host "Do you want to replace it? (Y/N)"
        if ($response -ne 'Y' -and $response -ne 'y') {
            Write-Host "Cancelled by user" -ForegroundColor Yellow
            exit 0
        }
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Existing task removed"
    }
    
    try {
        # Create task action - run PowerShell with the startup script
        # Using -WindowStyle Normal so the windows are visible for monitoring
        $action = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Normal -File `"$scriptPath`"" `
            -WorkingDirectory $workspaceRoot
        
        # Create task trigger - at user logon
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        
        # Create task settings
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -RunOnlyIfNetworkAvailable:$false `
            -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
            -RestartCount 0
        
        # Create task principal (run as current user, no elevation required)
        $principal = New-ScheduledTaskPrincipal `
            -UserId $env:USERNAME `
            -LogonType Interactive `
            -RunLevel Limited
        
        # Register the task
        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description "Automatically starts linescan pipeline scripts (launch_linescan.ps1 and launch_with_signal.py) with time-based mode selection on user login" | Out-Null
        
        Write-Host ""
        Write-Host "SUCCESS: Scheduled task '$taskName' has been registered!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Task Details:"
        Write-Host "  Task Name: $taskName"
        Write-Host "  Trigger: At logon for user: $env:USERNAME"
        Write-Host "  Action: Run $scriptPath"
        Write-Host "  Working Directory: $workspaceRoot"
        Write-Host ""
        Write-Host "The task will:"
        Write-Host "  1. Wait 30 seconds after login (configurable in startup_linescan.ps1)"
        Write-Host "  2. Automatically select day/night mode based on time (after 5pm = night)"
        Write-Host "  3. Launch launch_linescan.ps1 in a PowerShell window"
        Write-Host "  4. Launch launch_with_signal.py in a separate PowerShell window"
        Write-Host ""
        Write-Host "Next Steps:"
        Write-Host "  - Task will run automatically on next login"
        Write-Host "  - To test now: Start-ScheduledTask -TaskName '$taskName'"
        Write-Host "  - To disable: Disable-ScheduledTask -TaskName '$taskName'"
        Write-Host "  - To view: Get-ScheduledTask -TaskName '$taskName' | Format-List *"
        Write-Host "  - Open Task Scheduler GUI: taskschd.msc"
        Write-Host ""
        
    } catch {
        Write-Host "ERROR: Failed to register task: $_" -ForegroundColor Red
        Write-Host ""
        Write-Host "Troubleshooting:"
        Write-Host "  - Try running PowerShell as Administrator"
        Write-Host "  - Check if Task Scheduler service is running"
        Write-Host "  - Verify paths are correct in this script"
        exit 1
    }
}

Write-Host "=== Registration Complete ==="
