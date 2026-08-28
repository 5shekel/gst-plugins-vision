# Windows Startup Scripts for Linescan System

Automated startup system for running linescan pipelines on Windows boot with intelligent time-based mode selection.

## Overview

This system automatically launches both linescan components when Windows starts:
1. [`launch_linescan.ps1`](../launch_linescan.ps1) - Pipeline launcher wrapper
2. [`gst/linescan/launch_with_signal.py`](../gst/linescan/launch_with_signal.py) - Signal capture pipeline

**Key Features:**
- ⏰ **Automatic time-based mode selection**: Day mode before 5pm, night mode after 5pm
- 🕐 **Configurable startup delay** (default 30 seconds)
- 📊 **Visible monitoring windows** for each pipeline
- 📝 **Comprehensive logging** to track startup events
- 🔧 **Easy Task Scheduler integration**

## Quick Start

### 1. Register for Automatic Startup

Run the registration script to create a Windows Task Scheduler task:

```powershell
.\register_startup.ps1
```

This creates a task that will automatically run on user login.

### 2. Test Manually (Optional)

Before relying on automatic startup, test the script manually:

```powershell
.\startup_linescan.ps1
```

### 3. Reboot and Verify

Log out and log back in (or reboot). After 30 seconds, you should see two PowerShell windows open automatically:
- Window 1: Running `launch_linescan.ps1` (in day or night mode)
- Window 2: Running `launch_with_signal.py`

## Files

| File | Purpose |
|------|---------|
| [`startup_linescan.ps1`](../startup_linescan.ps1) | Main startup script that launches both pipelines |
| [`register_startup.ps1`](../register_startup.ps1) | Registers/unregisters the Task Scheduler task |
| `docs/STARTUP.md` | This documentation file |

## Usage

### Main Startup Script

```powershell
# Default behavior (30 second delay, auto mode selection)
.\startup_linescan.ps1

# Custom delay
.\startup_linescan.ps1 -DelaySeconds 60

# No delay (immediate start)
.\startup_linescan.ps1 -NoDelay

# Show help
.\startup_linescan.ps1 -Help
```

### Registration Script

```powershell
# Register for startup
.\register_startup.ps1

# Remove from startup
.\register_startup.ps1 -Unregister

# Show help
.\register_startup.ps1 -Help
```

## Time-Based Mode Selection

The startup script automatically selects the camera mode based on time of day:

- **Before 5:00 PM (17:00)**: Day mode
  - Exposure: 0.2ms
  - Gain: 0
  - Framerate: 200fps

- **After 5:00 PM (17:00)**: Night mode
  - Exposure: 5.25ms
  - Gain: 65
  - Framerate: 200fps

The mode is determined when the script runs, logged for reference.

## Configuration

### Modify Startup Delay

Edit [`startup_linescan.ps1`](../startup_linescan.ps1:16):

```powershell
param(
    [Parameter()]
    [int]$DelaySeconds = 30,  # Change default delay here
    ...
)
```

### Change Time Threshold for Night Mode

Edit [`startup_linescan.ps1`](../startup_linescan.ps1:96-102):

```powershell
# Determine mode based on time of day
$currentHour = (Get-Date).Hour
if ($currentHour -ge 17) {  # Change 17 to your desired hour (24-hour format)
    $mode = "night"
    ...
}
```

### Change Workspace Path

If your workspace is not at `c:\dev\gst-plugins-vision`, update both scripts:

[`startup_linescan.ps1`](../startup_linescan.ps1:61):
```powershell
$workspaceRoot = "c:\dev\gst-plugins-vision"  # Update this path
```

[`register_startup.ps1`](../register_startup.ps1:50):
```powershell
$workspaceRoot = "c:\dev\gst-plugins-vision"  # Update this path
```

## Logging

All startup events are logged to `startup_linescan.log` in the workspace root.

**Log location**: `c:\dev\gst-plugins-vision\startup_linescan.log`

Example log entries:
```
[2026-01-25 23:30:15] === Linescan Startup Script Started ===
[2026-01-25 23:30:15] Workspace: c:\dev\gst-plugins-vision
[2026-01-25 23:30:45] Delay complete, starting scripts...
[2026-01-25 23:30:45] Time-based mode selection: After 5pm (hour=23), using night mode
[2026-01-25 23:30:45] launch_linescan.ps1 started in night mode (PID: 12345)
[2026-01-25 23:30:47] launch_with_signal.py started (PID: 12346)
[2026-01-25 23:30:47] === All scripts launched successfully ===
```

## Managing the Scheduled Task

### Using PowerShell

```powershell
# View task details
Get-ScheduledTask -TaskName "LineScanStartup" | Format-List *

# Run task now (without waiting for login)
Start-ScheduledTask -TaskName "LineScanStartup"

# Disable task (stop automatic startup)
Disable-ScheduledTask -TaskName "LineScanStartup"

# Enable task (resume automatic startup)
Enable-ScheduledTask -TaskName "LineScanStartup"

# Remove task completely
Unregister-ScheduledTask -TaskName "LineScanStartup" -Confirm:$false
# Or use: .\register_startup.ps1 -Unregister
```

### Using Task Scheduler GUI

1. Press `Win+R` and type `taskschd.msc`
2. Navigate to "Task Scheduler Library"
3. Find "LineScanStartup"
4. Right-click for options: Run, Disable, Delete, Properties, etc.

## Stopping the Pipelines

The scripts run in visible PowerShell windows. To stop them:

1. **Press Ctrl+C** in each PowerShell window, or
2. **Close the windows** (click the X button)

The pipelines will shut down gracefully.

## Troubleshooting

### Task doesn't run on startup

1. Check if task is registered:
   ```powershell
   Get-ScheduledTask -TaskName "LineScanStartup"
   ```

2. Check task history in Task Scheduler GUI (`taskschd.msc`)

3. Verify the task is enabled:
   ```powershell
   Enable-ScheduledTask -TaskName "LineScanStartup"
   ```

### Scripts don't launch

1. Check the log file: `c:\dev\gst-plugins-vision\startup_linescan.log`

2. Verify paths are correct in [`startup_linescan.ps1`](../startup_linescan.ps1:61)

3. Test manually:
   ```powershell
   .\startup_linescan.ps1 -NoDelay
   ```

### Wrong mode selected

1. Check current time: The mode is based on 24-hour clock (17 = 5:00 PM)

2. Check the log file to see which mode was selected and why

3. Adjust the time threshold in the script if needed (see Configuration section)

### Pipelines fail to start

1. Check individual script documentation:
   - [`launch_linescan.ps1`](../launch_linescan.ps1) help: `.\launch_linescan.ps1 -Help`
   - [`launch_with_signal.py`](../gst/linescan/launch_with_signal.py) help: `uv run .\gst\linescan\launch_with_signal.py --help`

2. Verify GStreamer environment is set up:
   ```powershell
   . .\scripts\setup_gstreamer_env.ps1
   ```

3. Check if camera is connected and accessible

### Need to modify behavior

See the [Configuration](#configuration) section above for common modifications.

## Advanced Usage

### Custom Launch Arguments

To pass custom arguments to the underlying scripts, modify [`startup_linescan.ps1`](../startup_linescan.ps1):

For `launch_linescan.ps1` (line 104):
```powershell
"-Command", "& '$script1Path' $mode --custom-arg value" `
```

For `launch_with_signal.py` (line 124):
```powershell
"-Command", "uv run '$script2Path' --format png --debug" `
```

### Run Without Task Scheduler

You can place a shortcut to [`startup_linescan.ps1`](../startup_linescan.ps1) in the Windows Startup folder:

1. Press `Win+R` and type: `shell:startup`
2. Create a shortcut to `startup_linescan.ps1` in that folder
3. Edit shortcut properties to set "Start in" to `c:\dev\gst-plugins-vision`

However, Task Scheduler is recommended as it provides better logging and control.

### Multiple Configurations

To support multiple startup configurations (e.g., different camera settings), create copies of [`startup_linescan.ps1`](../startup_linescan.ps1) with different parameters and register multiple tasks with different names.

## See Also

- [`launch_linescan.ps1`](../launch_linescan.ps1) - Pipeline launcher wrapper
- [`gst/linescan/launch_with_signal.py`](../gst/linescan/launch_with_signal.py) - Signal capture pipeline
- [`scripts/launch-ids.py`](../scripts/launch-ids.py) - Core pipeline launcher
- [GStreamer Linescan Plugin README](../gst/linescan/README.md)

## Support

For issues or questions:
1. Check the log file: `startup_linescan.log`
2. Run scripts manually with `-Help` flag
3. Review individual component documentation
