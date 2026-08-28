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

### Gain Boost (third rung)

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `auto-gain-boost` | boolean | - | FALSE | Toggle the camera's `gain-boost` as a rung below exposure and gain: enable it when exposure **and** gain are both maxed and still too dark; disable it when both are floored and too bright. On each toggle, gain is recentred to mid-range (boost ≈ 2× sensitivity). Boost can never engage in daylight because gain must be pinned at `gain-max` first. Needs an upstream `idsueyesrc` with a `gain-boost` property. |
| `boost-min-dwell` | double | 0.0-3600.0 | 120.0 | Minimum seconds to hold a `gain-boost` state before it may toggle back (anti-chatter on a passing cloud at dusk). Only used when `auto-gain-boost` is enabled. |

### Ramping

| Property | Type | Values | Default | Description |
|----------|------|--------|---------|-------------|
| `ramp-rate` | enum | VSlow, Slow, Medium, Fast, VFast | Medium | Speed of parameter changes |
| `update-interval` | int | 10-10000 | 100 | Time between exposure updates (ms) |

### Brightness Filtering

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `brightness-smoothing` | double | 0.0-1.0 | 0.1 | Temporal smoothing factor (EMA alpha) |
| `brightness-deadband` | double | 0.0-50.0 | 10.0 | Deadband zone to prevent oscillation (0=disabled) |

### Logging

| Property | Type | Range | Default | Description |
|----------|------|-------|---------|-------------|
| `log-file` | string | - | "" | Path to CSV log file (empty = disabled) |

CSV columns: `Frame,Time_s,Brightness,Exposure_ms,Gain,Target_Brightness,GainBoost`
(`GainBoost` is the controller's tracked 0/1 state, not a camera readback).

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

### Dawn/Dusk Time-Lapse (Recommended)

Optimized settings for smooth sunrise/sunset time-lapse:

```bash
gst-launch-1.0 \
  idsueyesrc config-file=ini/whole-presacler64_autoexp-binningx2.ini \
    exposure=0.85 framerate=50 gain=0 name=cam device-id=2 ! \
  intervalometer enabled=true camera-element=cam \
    ramp-rate=vslow \
    update-interval=1000 \
    brightness-smoothing=0.1 \
    brightness-deadband=10.0 \
    log-file=timelapse.csv ! \
  videocrop bottom=3 ! queue ! videoconvert ! autovideosink
```

**Key settings:**
- `ramp-rate=vslow`: 5% exposure steps per update (smooth transitions)
- `update-interval=1000`: Updates every 1 second (not too aggressive)
- `brightness-smoothing=0.1`: Filters out moving objects (cars, people, birds)
- `brightness-deadband=10.0`: Prevents oscillation by creating a stable zone

### Complete Time-Lapse Recording

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

The filter uses a YASS-inspired algorithm with deadband control:

1. **Brightness Analysis**: Calculates average brightness of each frame
2. **Deadband Check**: If brightness is within deadband zone, skip adjustments (prevents oscillation)
3. **Error Calculation**: Compares to target brightness (with compensation)
4. **Ramping Priority**:
   - When too bright: Decreases exposure first, then gain
   - When too dark: Increases exposure first (up to max), then gain
5. **Smooth Ramping**: Changes are gradual based on ramp-rate setting

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

## Configuration Reference

### Ramp Rates

| Rate | Multiplier | Step Size | Best For |
|------|------------|-----------|----------|
| VSlow | 0.5x | 5% per update | Dawn/dusk time-lapse (recommended) |
| Slow | 1.0x | 10% per update | Gradual sunset/sunrise over hours |
| Medium | 2.0x | 20% per update | Normal time-lapse scenarios |
| Fast | 4.0x | 40% per update | Faster light changes, clouds passing |
| VFast | 8.0x | 80% per update | Quick adaptation, testing |

**Note:** The base ramping rate is 10% of the delta between current and target values, multiplied by the ramp rate setting.

### Update Intervals

| Interval | Updates/sec | Best For |
|----------|-------------|----------|
| 100ms | 10 Hz | Fast-changing scenes (clouds, indoor) |
| 500ms | 2 Hz | Moderate changes |
| **1000ms** | **1 Hz** | **Dawn/dusk time-lapse (recommended)** |
| 2000ms | 0.5 Hz | Very slow lighting changes |
| 5000ms | 0.2 Hz | Extremely slow changes |

**Important:** At high frame rates (50fps), avoid very short update intervals (< 500ms) to prevent oscillation and flickering.

### Brightness Smoothing

The `brightness-smoothing` property uses Exponential Moving Average (EMA) to filter out transient brightness changes from moving objects:

```
smoothed_brightness = (alpha × current_brightness) + ((1 - alpha) × previous_smoothed)
```

| Value | Behavior | Best For |
|-------|----------|----------|
| 0.05 | Very heavy smoothing | High traffic scenes |
| **0.1** | **Heavy smoothing (default)** | **Time-lapse with moving objects** |
| 0.3 | Moderate smoothing | Some filtering needed |
| 0.5 | Light smoothing | Quick response |
| 1.0 | No smoothing | Instant response to changes |

**Effect:** With `brightness-smoothing=0.1`, the algorithm effectively averages brightness over ~10 frames, filtering out cars, people, and birds while still tracking slow lighting trends.

### Brightness Deadband

The `brightness-deadband` property creates a tolerance zone around the target brightness where no adjustments are made. This prevents oscillation caused by continuous micro-adjustments.

**How it works:**
- When brightness is within ±deadband of target, no changes are made
- When brightness exceeds the deadband, normal adjustments resume
- Allows fast corrections when needed, prevents hunting when stable

| Value | Behavior | Best For |
|-------|----------|----------|
| 0.0 | No deadband (disabled) | Maximum responsiveness (may oscillate) |
| 5.0 | Narrow deadband | Slow update rates (>500ms) |
| **10.0** | **Standard deadband (default)** | **Fast update rates (10-100ms), prevents oscillation** |
| 20.0 | Wide deadband | Very stable, less responsive |

**Example:**
- With `target-brightness=128` and `brightness-deadband=10.0`
- No adjustments when brightness is between 118-138
- Adjustments resume when brightness < 118 or > 138

**Important:** Higher deadband = more stability but less precision. Lower deadband = more precision but potential oscillation at fast update rates.

## Tips for Best Results

### Dawn/Dusk Time-Lapse (Recommended Configuration)

```
ramp-rate: vslow (5% steps - very gradual)
update-interval: 1000 (1 second between updates)
brightness-smoothing: 0.1 (filter moving objects)
brightness-deadband: 10.0 (prevent oscillation)
exposure-min: 0.85 (or camera minimum)
exposure-max: 1.24 (or 1/framerate)
gain-min: 0 (cleanest image)
gain-max: 52 (or camera limit)
target-brightness: 128
```

**Why these settings:**
- `vslow` ramp rate prevents visible exposure jumps
- 1000ms update interval allows camera hardware to settle
- Brightness smoothing filters transient changes (cars, people)
- Results in smooth, flicker-free time-lapse

### Fast Changing Conditions (with Fast Update Rates)

```
ramp-rate: fast or vfast
update-interval: 10-100 (very fast updates)
brightness-smoothing: 0.3-1.0 (more responsive)
brightness-deadband: 10.0-15.0 (ESSENTIAL to prevent oscillation)
compensation: Adjust to preference (-1.0 for darker, +1.0 for brighter)
```

**Critical:** When using fast update rates (10-100ms), `brightness-deadband` is ESSENTIAL to prevent oscillation. Without it, the algorithm will continuously overshoot and create flickering.

### Maximum Image Quality

```
gain-max: 20-30 (lower max gain = less noise)
ramp-rate: slow or vslow (smoother transitions)
update-interval: 1000-2000
```

### Avoiding Flickering and Oscillation

If you experience flickering or oscillation:
1. **Enable deadband (MOST IMPORTANT)**: Set `brightness-deadband=10.0` or higher
2. **Increase update-interval**: Start with 1000ms for slow changes, or keep at 10-100ms with deadband for fast response
3. **Decrease ramp-rate**: Use `vslow` or `slow`
4. **Enable brightness-smoothing**: Set to 0.1 or lower

**The New Solution:** With the `brightness-deadband` parameter, you can now use fast update rates (10ms) with fast ramp rates without oscillation! The deadband creates a stable zone that prevents continuous micro-adjustments.

## Troubleshooting

**Filter not adjusting exposure:**
- Verify `camera-element` property matches your camera source name
- Check that camera allows runtime exposure/gain changes
- Ensure `enabled=true` is set

**Flickering or oscillating exposure:**
- **Primary cause:** No deadband zone at fast update rates
- **Solution:** Set `brightness-deadband=10.0` (or higher)
- **Alternative:** Increase `update-interval` to 1000ms
- **Also try:** Set `ramp-rate=vslow` and `brightness-smoothing=0.1`
- **New capability:** With deadband enabled, you CAN use fast update intervals (10-100ms) for rapid response without oscillation!

**Changes too fast/slow:**
- Adjust `ramp-rate` property
- Modify `update-interval` (higher = slower convergence)
- Check `exposure-min`/`exposure-max` range is appropriate

**Brightness oscillates with moving objects:**
- Enable `brightness-smoothing=0.1` to filter transients
- Lower values (0.05) provide even more smoothing
- This filters cars, people, birds while tracking lighting trends

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

## Technical Notes

### Flickering Fix (2025)

The original implementation had a critical bug where exposure ramping was not actually implemented - the code would instantly jump to target values instead of gradually ramping. This caused visible flickering, especially with short update intervals.

**Fixed in [`gstintervalometer.c:688-716`](gst/intervalometer/gstintervalometer.c:688-716):**
- Implemented proper gradual ramping using the `ramp_step` variable
- Each update now applies a percentage of the delta (not instant jumps)
- Formula: `current_exposure += (target_exposure - current_exposure) × ramp_step`

### Exposure Range Query Fix

The original implementation used GObject property specs to query exposure limits, which returned incorrect values (0.0 min, DBL_MAX max). This has been fixed to use the IDS uEye SDK directly:

**Changes made:**
- Added IDS SDK header include and camera handle support
- Added `hcam` property to `idsueyesrc` to expose camera handle
- Use `is_Exposure(IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE)` for proper hardware limits
- Result: Proper min/max values (e.g., [0.019 - 19.943] ms) from camera

### Brightness Smoothing

Added Exponential Moving Average (EMA) filtering to handle transient brightness changes from moving objects (cars, people, birds). This prevents exposure oscillation while maintaining responsiveness to actual lighting changes.

### Brightness Deadband (Anti-Oscillation)

Added deadband control to prevent continuous micro-adjustments that cause oscillation. When brightness is within the deadband zone (default ±10 units), no adjustments are made. This allows:
- Fast update rates (10-100ms) without oscillation
- Rapid response when changes exceed deadband
- Stable operation at any ramp rate

**Implementation in [`gstintervalometer.c:698-707`](gst/intervalometer/gstintervalometer.c:698-707):**
- Checks absolute error against deadband before making adjustments
- Skips exposure/gain changes when within tolerance
- Allows full-speed corrections when brightness significantly deviates

## License

This filter is part of gst-plugins-vision and released under the GNU Library General Public License (LGPL).

Inspired by YASS (Yet Another Sunset Script) by waterwingz, based on work by Fbonomi and soulf2, released under GPL.

## See Also

- [YASS Documentation](../../yass/README.md) - Original CHDK script that inspired this filter
- [idsueyesrc](../../sys/idsueye/gstidsueyesrc.c) - IDS uEye camera source element