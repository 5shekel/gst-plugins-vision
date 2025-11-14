# GStreamer Rolling Sum Plugin Guide

## Overview

The `rollingsum` plugin analyzes video frames in real-time by tracking the mean pixel intensity of a specific column across frames. It maintains a rolling window of these values and can drop frames that deviate significantly from the rolling mean, useful for detecting and filtering unstable or anomalous frames.

## How It Works

1. **Column Analysis**: Extracts mean pixel intensity from a specified vertical column
2. **Rolling Window**: Maintains a circular buffer of recent column means
3. **Deviation Detection**: Calculates how much each frame deviates from the rolling mean
4. **Frame Filtering**: Optionally drops frames exceeding the deviation threshold
5. **CSV Logging**: Records all frame statistics for analysis

## Plugin Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `window-size` | int | 1000 | Number of frames in rolling window (1-100000) |
| `column-index` | int | 1 | Which vertical column to analyze (0-based) |
| `stride` | int | 1 | Row sampling stride (1 = every row) |
| `threshold` | double | 0.5 | Normalized deviation threshold for dropping frames (0.0-1.0) |
| `csv-file` | string | NULL | Path to CSV file for logging (NULL = no logging) |

### Understanding Normalized Deviation

- **Range**: 0.0 to 1.0
- **Calculation**: `absolute_deviation / 255.0` (for 8-bit video)
- **Meaning**: Fraction of the full pixel range
  - `0.001` = deviation of ~0.255 pixel values
  - `0.01` = deviation of ~2.55 pixel values
  - `0.1` = deviation of ~25.5 pixel values

## Basic Usage

### Simple Pipeline

```bash
gst-launch-1.0 idsueyesrc config-file=config.ini ! \
  videoconvert ! \
  video/x-raw,format=GRAY8 ! \
  rollingsum window-size=1000 column-index=1 threshold=0.0002 ! \
  autovideosink
```

### With CSV Logging

```bash
gst-launch-1.0 idsueyesrc config-file=config.ini exposure=0.5 ! \
  videoconvert ! \
  video/x-raw,format=GRAY8 ! \
  rollingsum window-size=1000 column-index=1 threshold=0.0002 csv-file=output.csv ! \
  fakesink
```

## Debugging

### Enable Debug Output

Use the `GST_DEBUG` environment variable to see detailed plugin operation:

#### Windows PowerShell

```powershell
$env:GST_DEBUG="rollingsum:5"; gst-launch-1.0 [pipeline...]
```

#### Windows CMD

```cmd
set GST_DEBUG=rollingsum:5 && gst-launch-1.0 [pipeline...]
```

#### Linux/Mac

```bash
GST_DEBUG=rollingsum:5 gst-launch-1.0 [pipeline...]
```

### Debug Levels

| Level | Output |
|-------|--------|
| `rollingsum:1` | Errors only |
| `rollingsum:2` | Warnings |
| `rollingsum:3` | Info messages (file open/close) |
| `rollingsum:4` | Debug (caps negotiation) |
| `rollingsum:5` | Log (all frame processing) |

### Example Debug Output

```
0:00:04.029432200 DEBUG rollingsum gstrollingsum.c:436: Extracted column mean: 10.07
0:00:04.032257100 DEBUG rollingsum gstrollingsum.c:466: Frame 1: mean=10.07, rolling_mean=10.07, deviation=0.00 (normalized=0.0000)
```

**Key Fields:**
- `Frame N`: Frame number
- `mean`: Current frame's column mean
- `rolling_mean`: Average of last N frames (window-size)
- `deviation`: Absolute difference
- `normalized`: Deviation as fraction of 255

### Common Debug Scenarios

#### 1. Verify Plugin Loaded

```bash
gst-inspect-1.0 rollingsum
```

Should show plugin details. If not found, check `GST_PLUGIN_PATH`.

#### 2. Check CSV File Creation

Look for this in debug output:
```
INFO rollingsum: Opened CSV file: output.csv
```

#### 3. Monitor Frame Drops

Look for:
```
DEBUG rollingsum: Dropping frame 42: deviation 0.0005 > threshold 0.0002
```

#### 4. Verify Caps Negotiation

```
DEBUG rollingsum: set_caps
DEBUG rollingsum: Video format: GRAY8, 1224x1026
```

## CSV Analysis

### CSV Format

The output CSV contains:

```csv
frame,column_mean,rolling_mean,deviation,normalized_deviation,dropped
1,10.071150,10.071150,0.000000,0.000000,0
2,10.059454,10.065302,0.005848,0.000023,0
...
```

### Analyze Results

Use the included analysis script:

```bash
uv run analyze_sma.py output.csv
```

**Output includes:**
- Statistical summary (min/max/mean/std)
- Threshold recommendations based on percentiles
- Standard deviation-based suggestions
- Visualization plots (`output_analysis.png`)

### Interpreting Results

The analysis provides threshold recommendations:

| Percentile | Description | Use Case |
|------------|-------------|----------|
| 99th | Drops top 1% | Very conservative, catch only extreme outliers |
| 95th | Drops top 5% | Conservative, good for quality control |
| 90th | Drops top 10% | Balanced, moderate filtering |
| 75th | Drops top 25% | Aggressive, maximum quality |

## Recommended Thresholds

Based on analysis of stable camera footage:

### For General Use

```bash
# Conservative (1-2% frame drop)
threshold=0.0003

# Moderate (5-10% frame drop)
threshold=0.0002

# Aggressive (20-25% frame drop)
threshold=0.0001
```

### For Specific Scenarios

**High-speed acquisition** (minimal processing):
```bash
window-size=100 threshold=0.0005
```

**Quality-focused** (stable scenes):
```bash
window-size=1000 threshold=0.0001
```

**Real-time monitoring** (fast response):
```bash
window-size=50 threshold=0.0002
```

## Troubleshooting

### No frames being dropped (threshold too high)

**Symptom**: `dropped` column always 0 in CSV

**Solution**:
1. Run with CSV logging
2. Analyze with `uv run analyze_sma.py output.csv`
3. Use recommended threshold from 90th-99th percentile

### Too many frames dropped (threshold too low)

**Symptom**: Most frames have `dropped=1`, choppy video

**Solution**:
1. Increase threshold (try doubling current value)
2. Check if column_index is appropriate
3. Verify video is stable (not shaking/moving)

### CSV file not created

**Check**:
1. File path is writable
2. Look for "Opened CSV file" in debug output (`GST_DEBUG=rollingsum:3`)
3. Verify csv-file property is set correctly

### Column index out of range

**Symptom**:
```
WARNING rollingsum: Column index 1000 >= width 1224, using column 0
```

**Solution**: Set `column-index` to value < video width

### Inconsistent results

**Possible causes**:
1. Window size too small (< 50 frames)
2. Sampling moving/dynamic content
3. Column contains edge/artifact data

**Solutions**:
- Increase `window-size` to 500-1000
- Choose different `column-index` (avoid edges)
- Use `stride=2` or higher for faster processing

## Performance Tips

1. **Larger window = more stable** but slower to adapt to scene changes
2. **Stride > 1** reduces computation but less accurate column mean
3. **CSV logging** has minimal performance impact
4. **Debug level 5** can produce massive logs, use only when needed

## Integration Examples

### Python Script Control

```python
import subprocess

# Run pipeline with CSV logging
subprocess.run([
    'gst-launch-1.0',
    'idsueyesrc', 'config-file=config.ini',
    '!', 'videoconvert',
    '!', 'video/x-raw,format=GRAY8',
    '!', 'rollingsum',
        'window-size=1000',
        'column-index=1',
        'threshold=0.0002',
        'csv-file=output.csv',
    '!', 'fakesink'
])

# Analyze results
subprocess.run(['uv', 'run', 'analyze_sma.py', 'output.csv'])
```

### Adaptive Threshold

Use analysis results to set optimal threshold for next run:

```python
import pandas as pd

# Analyze previous run
df = pd.read_csv('output.csv')
recommended_threshold = df['normalized_deviation'].quantile(0.95)

print(f"Recommended threshold: {recommended_threshold:.6f}")
```

## Developer Notes

### Adding New Features

Key files:
- [`gst/rollingsum/gstrollingsum.c`](gst/rollingsum/gstrollingsum.c) - Main implementation
- [`gst/rollingsum/gstrollingsum.h`](gst/rollingsum/gstrollingsum.h) - Header/structures
- [`gst/rollingsum/CMakeLists.txt`](gst/rollingsum/CMakeLists.txt) - Build config

### Rebuild After Changes

```bash
.\build.ps1  # Windows
./build.sh   # Linux
```

### Testing

```bash
# Quick test
gst-inspect-1.0 rollingsum

# Full pipeline test with debug
$env:GST_DEBUG="rollingsum:5"
gst-launch-1.0 videotestsrc ! rollingsum ! fakesink
```

## References

- [DESIGN_ROLLINGSUM.md](DESIGN_ROLLINGSUM.md) - Design document
- [analyze_sma.py](analyze_sma.py) - Analysis tool
- GStreamer documentation: https://gstreamer.freedesktop.org/documentation/

## Support

For issues or questions:
1. Enable debug output (`GST_DEBUG=rollingsum:5`)
2. Generate CSV log and analyze
3. Check this guide's troubleshooting section
4. Review debug output for errors/warnings