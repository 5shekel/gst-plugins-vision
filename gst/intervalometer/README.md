# GStreamer Intervalometer Filter

**Automatic Exposure Control for IDS uEye Cameras**

Inspired by [YASS (Yet Another Sunset Script)](../../yass/README.md) for CHDK cameras.

## Overview

The `intervalometer` element is a GStreamer filter that automatically adjusts camera exposure and gain settings during changing light conditions. It analyzes video brightness in real-time and smoothly ramps camera parameters to maintain optimal exposure - perfect for time-lapse photography during sunset, sunrise, or other variable lighting scenarios.

## Features

- **Automatic Exposure Ramping**: Smoothly adjusts exposure time based on scene brightness
- **Automatic Gain Control**: Increases/decreases sensor gain when exposure limits are reached
- **Configurable Ranges**: Set custom min/max values for exposure (0.85-1.24ms) and gain (0-52)
- **Multiple Ramp Rates**: Choose from VSlow/Slow/Medium/Fast/VFast adjustment speeds
- **Exposure Compensation**: Fine-tune brightness with ±4 stops of compensation
- **CSV Logging**: Optional detailed logging of all exposure parameters
- **Multiple Format Support**: Works with GRAY8, GRAY16, RGB, BGR, and BGRA video

## Requirements

- GStreamer 1.0+
- IDS uEye camera with `idsueyesrc` element
- Camera must support runtime exposure and gain property changes

## Installation

The filter is built as part of the gst-plugins-vision project. Build and install normally:

```bash
mkdir build
cd build
cmake ..
make
make install
```

## Properties

### Control Properties

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `enabled` | boolean | - | TRUE | Enable/disable auto-exposure |
| `target-brightness` | double | 0-255 | 128.0 | Target average brightness level |
| `compensation` | double | -4.0 to 4.0 | 0.0 | Exposure compensation in stops |
| `camera-element` | string | - | "" | Name of upstream idsueyesrc element |

### Exposure Range

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `exposure-min` | double | 0.01-1000.0 | 0.85 | Minimum exposure time (ms) |
| `exposure-max` | double | 0.01-1000.0 | 1.24 | Maximum exposure time (ms) |

### Gain Range

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `gain-min` | int | 0-100 | 0 | Minimum gain value |
| `gain-max` | int | 0-100 | 52 | Maximum gain value |

### Ramping

| Property | Type | Values | Default | Description |
|----------|------|--------|---------|-------------|
| `ramp-rate` | enum | VSlow, Slow, Medium, Fast, VFast | Medium | Speed of parameter changes |

### Logging

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `log-file` | string | - | "" | Path to CSV log file (empty = disabled) |

## Usage Examples

### Basic Auto-Exposure

```bash
gst-launch-1.0 idsueyesrc name=cam ! \
  intervalometer enabled=true camera-element=cam ! \
  videoconvert ! autovideosink
```

### Custom Range for Day/Night Transition

Configure for the typical day (0.85ms exposure, gain 52) to night (1.24ms exposure, gain 0) range:

```bash
gst-launch-1.0 idsueyesrc name=cam ! \
  intervalometer enabled=true camera-element=cam \
    exposure-min=0.85 exposure-max=1.24 \
    gain-min=0 gain-max=52 \
    ramp-rate=medium ! \
  videoconvert ! autovideosink
```

### With Exposure Compensation

Adjust overall brightness with compensation:

```bash
gst-launch-1.0 idsueyesrc name=cam ! \
  intervalometer enabled=true camera-element=cam \
    compensation=1.0 \
    target-brightness=140 ! \
  videoconvert ! autovideosink
```

### With CSV Logging

Log all exposure data to a CSV file:

```bash
gst-launch-1.0 idsueyesrc name=cam ! \
  intervalometer enabled=true camera-element=cam \
    log-file=exposure_log.csv ! \
  videoconvert ! autovideosink
```

### Complete Time-Lapse Pipeline

Record a time-lapse with auto-exposure:

```bash
gst-launch-1.0 idsueyesrc name=cam framerate=1 ! \
  intervalometer enabled=true camera-element=cam \
    exposure-min=0.85 exposure-max=1.24 \
    gain-min=0 gain-max=52 \
    ramp-rate=slow \
    log-file=timelapse_exposure.csv ! \
  videoconvert ! x264enc ! mp4mux ! \
  filesink location=timelapse.mp4
```

## How It Works

### Exposure Control Algorithm

The filter uses a YASS-inspired algorithm:

1. **Brightness Analysis**: Calculates average brightness of each frame
2. **Error Calculation**: Compares to target brightness (with compensation)
3. **Ramping Priority**:
   - When too bright: Decreases exposure first, then gain
   - When too dark: Increases exposure first (up to max), then gain
4. **Smooth Ramping**: Changes are gradual based on ramp-rate setting

### Typical Behavior

- **Daytime**: Fast shutter (low exposure), high gain for noise reduction
- **Sunset/Dusk**: Gradually increases exposure time as light fades
- **Night**: Maximum exposure time, minimum gain

### CSV Log Format

When logging is enabled, the filter creates a CSV file with:

```csv
Frame,Time_s,Brightness,Exposure_ms,Gain,Target_Brightness
0,0.000,145.32,0.850,52,128.00
1,0.033,143.21,0.851,52,128.00
2,0.067,142.15,0.853,52,128.00
...
```

## Camera Property Control

The filter finds and controls the upstream `idsueyesrc` element using the `camera-element` property. It sets:

- **exposure**: Exposure time in milliseconds
- **gain**: Master gain (0-100 range)

Ensure your camera source is named and the name matches the `camera-element` property.

## Ramp Rates

| Rate | Multiplier | Best For |
|------|------------|----------|
| VSlow | 0.5x | Very slow light changes, maximum smoothness |
| Slow | 1.0x | Gradual sunset/sunrise over hours |
| Medium | 2.0x | Normal time-lapse scenarios |
| Fast | 4.0x | Faster light changes, clouds passing |
| VFast | 8.0x | Quick adaptation, testing |

## Tips for Best Results

### Time-Lapse Settings

```
exposure-min: 0.85 (or camera-specific minimum)
exposure-max: 1.24 (or 1/framerate to avoid motion blur)
gain-min: 0 (cleanest image)
gain-max: 52 (or camera's limit)
ramp-rate: slow or medium
target-brightness: 128-140
```

### Fast Changing Conditions

```
ramp-rate: fast or vfast
compensation: Adjust to preference (-1.0 for darker, +1.0 for brighter)
```

### Maximum Image Quality

```
gain-max: 20-30 (lower max gain = less noise)
ramp-rate: slow (smoother transitions)
```

## Troubleshooting

**Filter not adjusting exposure:**
- Verify `camera-element` property matches your camera source name
- Check that camera allows runtime exposure/gain changes
- Ensure `enabled=true` is set

**Changes too fast/slow:**
- Adjust `ramp-rate` property
- Check `exposure-min`/`exposure-max` range is appropriate

**Brightness not reaching target:**
- Increase `gain-max` to allow more gain
- Increase `exposure-max` if not motion-limited
- Adjust `target-brightness` or use `compensation`

**Log file not created:**
- Check file path is writable
- Verify `log-file` property is set before starting pipeline

## Comparison to YASS

| Feature | YASS (CHDK) | Intervalometer (GStreamer) |
|---------|-------------|---------------------------|
| Platform | Canon cameras with CHDK | IDS uEye cameras |
| Control | Shutter speed + ISO | Exposure time + Gain |
| Integration | Standalone Lua script | GStreamer pipeline element |
| Real-time | Script-based intervals | Frame-by-frame analysis |
| Logging | CSV to SD card | CSV to filesystem |

## License

This filter is part of gst-plugins-vision and released under the GNU Library General Public License (LGPL).

Inspired by YASS (Yet Another Sunset Script) by waterwingz, based on work by Fbonomi and soulf2, released under GPL.

## See Also

- [YASS Documentation](../../yass/README.md) - Original CHDK script that inspired this filter
- [idsueyesrc](../../sys/idsueye/gstidsueyesrc.c) - IDS uEye camera source element