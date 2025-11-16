# YASS - Yet Another Sunset Script

**Version 4.8** for CHDK-enabled Canon cameras

## Overview

YASS (Yet Another Sunset Script) is an advanced intervalometer script for CHDK that automatically adjusts camera exposure settings during sunset, sunrise, or other changing light conditions. It maintains optimal exposure by intelligently ramping shutter speed and ISO as light levels change.

## Features

- **Automatic Exposure Ramping**: Smoothly adjusts shutter speed and ISO as light changes
- **Intelligent ND Filter Control**: Automatically engages/disengages ND filter based on conditions
- **Focus Lock Options**: AFL (Auto Focus Lock) or MF (Manual Focus) at infinity
- **Configurable Intervals**: Shot rates from 1 second to 1 hour
- **RAW Support**: Optional RAW capture alongside JPEG
- **CSV Logging**: Detailed logging of exposure parameters for each shot
- **Battery Saving**: Display blanking and LED control options
- **Delayed Start**: Optional startup delay up to 4 hours

## Requirements

- Canon camera with CHDK firmware installed
- **Minimum CHDK version**: 1.2.0 build 3276 or higher
- **Recommended**: CHDK 1.3.0 build 3383 or higher
- Sufficient SD card space (configurable shutdown threshold)

## Installation

1. Copy [`yass4.lua`](yass/yass4.lua) to your CHDK scripts folder (typically `CHDK/SCRIPTS/`)
2. Load the script from the CHDK menu
3. Configure parameters as needed
4. Start the script

## Parameters

### Timing & Interval
- **Shot Rate (t)**: Interval between shots (1-3600 seconds, default: 10s)
- **First Shot Delay (m)**: Startup delay (0-240 minutes, default: 0)

### Exposure Control
- **Compensation (o)**: Exposure compensation (-4.0 to +4.0 stops, default: 0.0)
- **Tv normal limit (e)**: Maximum shutter speed threshold (default: 1/6s)
- **Tv low limit (b)**: Minimum shutter speed (1.0-32 seconds, default: 5.0s)
- **Exposure ramp rate (f)**: Speed of exposure changes (VSlow/Slow/Medium/Fast/VFast)

### ISO Settings
- **ISO default (c)**: Starting ISO value (80-1600, default: 100)
- **ISO upper limit (d)**: Maximum ISO (80-1600, default: 400)

### Aperture & ND Filter
- **Aperture Setting (a)**: F-stop to use (min_Av to f16, default: min_Av)
- **Use ND Filter (w)**: Enable automatic ND filter control (0=off, 1=on)

### Focus & Zoom
- **Focus @ Infinity Mode (x)**: None/AFL/MF (default: None)
- **Zoom step position (z)**: Zoom position (-1=current, 0-100)

### File & Display Options
- **RAW enable (r)**: Capture RAW files (0=off, 1=on)
- **Free Disk MB Shut down (h)**: Stop when disk space below threshold (10-100 MB)
- **Status LED (y)**: LED indicator mode (Off/0-8)
- **Display blanking mode (n)**: None/BKLite/DispKey/ShrtCut
- **Logging (l)**: Off/Screen/SDCard/Both

## How It Works

1. **Initialization**: Script sets up camera (disables flash, IS, AF assist)
2. **Exposure Calculation**: Reads current brightness and calculates needed exposure
3. **Ramping Logic**:
   - When light is bright: Uses fast shutter speeds at default ISO
   - As light dims: Gradually increases shutter speed
   - When shutter reaches low limit: Begins increasing ISO
   - ND filter engages automatically for very bright conditions
4. **Continuous Shooting**: Captures images at specified interval
5. **Logging**: Records exposure data to `A/yass4.csv` (if enabled)

## Usage Tips

### Sunset/Sunrise Time-lapse
```
Shot Rate: 10-30 seconds
Tv low limit: 5-15 seconds
ISO upper limit: 800-1600
Exposure ramp rate: Medium or Slow
Focus mode: MF (Manual Focus at infinity)
```

### Long Duration Sessions
```
Display blanking mode: BKLite or ShrtCut (saves battery)
Status LED: Off or low setting
Logging: SDCard (for analysis)
First Shot Delay: Set to start automatically
```

### Bright Conditions
```
Use ND Filter: On
Aperture: f5.6 or smaller
ISO default: 80 or 100
```

## Log File Format

The script creates `A/yass4.csv` with the following columns:
```
Shot, Image, Compensation, Tv_target, Tv, Tv+, ND, ISO_target, ISO, f-stop, focus, Tv96, Sv96, Av96, Bv96
```

## Credits

- **Based on**: Scripts by Fbonomi and soulf2
- **Author**: waterwingz
- **License**: GPL (GNU General Public License)

## Troubleshooting

- **Script won't start**: Check CHDK version meets minimum requirements
- **Exposure issues**: Adjust compensation parameter and ramp rate
- **Focus problems**: Try different focus modes (AFL vs MF)
- **Battery drain**: Enable display blanking and reduce LED usage
- **Disk full**: Increase shutdown threshold or use larger SD card

## Version History

**v4.8** (Current)
- Enhanced CHDK 1.3.0 compatibility
- Improved exposure ramping algorithm
- Better ND filter control
- Extended logging capabilities

---

*For more information about CHDK, visit the [CHDK Wiki](https://chdk.fandom.com/)*