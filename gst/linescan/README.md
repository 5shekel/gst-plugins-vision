# GStreamer Linescan Plugin

## Overview

The `linescan` plugin simulates a line scan camera by extracting a single row or column of pixels from each input frame and stacking them to create a line scan image over time. This is particularly useful for analyzing fast-moving objects captured with high frame rate cameras (typically 200-750 fps).

## Features

- **Horizontal mode**: Extracts a single row from each frame and stacks them vertically
- **Vertical mode**: Extracts a single column from each frame and stacks them horizontally
- **Configurable line selection**: Choose which row/column to extract, or use the middle automatically
- **Configurable output size**: Set the number of lines to accumulate before wrapping around
- **Supports multiple pixel formats**: GRAY8, GRAY16_LE, GRAY16_BE, RGB, BGR, BGRA, RGBx

## Properties

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `direction` | enum | horizontal | Direction to extract line: `horizontal` (row) or `vertical` (column) |
| `line-index` | int | -1 | Index of row/column to extract (-1 for middle of image) |
| `output-size` | int | 800 | Number of lines to accumulate (width for horizontal mode, height for vertical mode) |
| `emit-every` | int | 1 | Push the accumulated roll buffer downstream only every Nth input frame (a column is still accumulated every frame, and a rollover frame always emits). `1` = emit every frame. Raise it (≈ `framerate / consumer_fps`) at high framerates so the full-roll copy stays off the per-frame hot path — see [Performance Considerations](#performance-considerations). |

## Signals

### `rollover`

```c
void user_function (GstElement *linescan,
                    GstBuffer  *buffer,
                    gpointer    user_data)
```

Emitted when the buffer position wraps around to 0 after accumulating `output-size` lines. The `buffer` parameter contains the completed line scan image at the moment of rollover.

**Parameters:**
- `linescan`: The linescan element emitting the signal
- `buffer`: The completed line scan buffer (read-only, contains full image)
- `user_data`: User data set when the signal handler was connected

**Use cases:**
- Save completed line scan images to disk automatically
- Process completed frames (e.g., run image analysis)
- Trigger external actions when a scan cycle completes
- Capture periodic snapshots during continuous operation

## Usage Examples

### Basic Horizontal Line Scan (Extract Row 100)
```bash
gst-launch-1.0 videotestsrc ! \
    linescan direction=horizontal line-index=100 output-size=800 ! \
    videoconvert ! autovideosink
```

### Vertical Line Scan (Extract Middle Column)
```bash
gst-launch-1.0 videotestsrc ! \
    linescan direction=vertical line-index=-1 output-size=600 ! \
    videoconvert ! autovideosink
```

### High-Speed Camera Line Scan
```bash
gst-launch-1.0 idsueyesrc framerate=500 ! \
    videocrop bottom=3 ! \
    linescan direction=horizontal line-index=50 output-size=1000 ! \
    videoconvert ! autovideosink
```

### Save Line Scan to File
```bash
gst-launch-1.0 idsueyesrc config-file=config.ini framerate=200 ! \
    linescan direction=horizontal output-size=2000 ! \
    videoconvert ! \
    pngenc ! filesink location=linescan.png
```

### Capturing Frames on Rollover (Using Signal)

The `rollover` signal fires when the buffer wraps around, allowing you to capture completed frames:

**Python example** (`rollover_example.py`):
```python
#!/usr/bin/env python3
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

frame_counter = 0

def on_rollover(linescan, buffer, filesink):
    global frame_counter
    filename = f"linescan_{frame_counter:04d}.raw"
    print(f"Rollover! Saving to: {filename}")
    filesink.set_property('location', filename)
    frame_counter += 1

Gst.init(None)
pipeline = Gst.parse_launch(
    "videotestsrc pattern=ball ! "
    "linescan direction=horizontal line-index=100 output-size=400 ! "
    "tee name=t "
    "t. ! queue ! videoconvert ! autovideosink "
    "t. ! queue ! filesink name=fsink location=init.raw"
)

linescan = pipeline.get_by_name("linescan")
filesink = pipeline.get_by_name("fsink")
linescan.connect("rollover", on_rollover, filesink)

pipeline.set_state(Gst.State.PLAYING)
# ... run main loop ...
```

**Alternative: Using multifilesink with tee** (no signal needed):
```bash
# Automatically saves each output frame with incrementing counter
gst-launch-1.0 videotestsrc pattern=ball ! \
    linescan direction=horizontal line-index=100 output-size=400 ! \
    tee name=t \
    t. ! queue ! videoconvert ! autovideosink \
    t. ! queue ! multifilesink location="frame_%04d.raw" max-files=100
```

**Real-world example with IDS uEye camera:**
```powershell
# PowerShell script (see launch_with_capture.ps1)
$env:GST_DEBUG="linescan:5"

gst-launch-1.0 idsueyesrc config-file=ini/roi-night.ini `
    exposure=5.25 framerate=200 gain=42 name=cam device-id=2 ! `
    intervalometer enabled=true camera-element=cam `
    ramp-rate=vslow update-interval=1000 gain-max=52 log-file=timelapse.csv ! `
    videocrop bottom=3 ! queue ! `
    linescan direction=vertical output-size=1900 ! `
    tee name=t `
    t. ! queue ! videoconvert ! autovideosink `
    t. ! queue ! multifilesink location="linescan_%04d.raw" max-files=100
```

See examples:
- [`rollover_example.py`](rollover_example.py) - Basic rollover signal demo
- [`launch_with_signal.py`](launch_with_signal.py) - Full IDS camera pipeline with signal
- [`launch_with_capture.ps1`](launch_with_capture.ps1) - PowerShell script with multifilesink

## How It Works

### Horizontal Mode (default)
1. Extracts one horizontal row from each input frame
2. The row is determined by `line-index` (or middle if -1)
3. Each extracted row is stacked vertically to build the output image
4. Output dimensions: `output-size` (width) × `input_height` (height)
5. When the buffer fills up (after `input_height` frames), it wraps around and starts overwriting from the top

### Vertical Mode
1. Extracts one vertical column from each input frame
2. The column is determined by `line-index` (or middle if -1)
3. Each extracted column is stacked horizontally to build the output image
4. Output dimensions: `input_width` (width) × `output-size` (height)
5. When the buffer fills up (after `input_width` frames), it wraps around and starts overwriting from the left

## Typical Use Cases

1. **Conveyor Belt Inspection**: Capture a continuous image of objects moving on a conveyor belt
2. **High-Speed Object Analysis**: Analyze fast-moving objects frame-by-frame at high framerates
3. **Barcode/Text Reading**: Extract a horizontal line across moving barcodes or text
4. **Web Inspection**: Continuous inspection of paper, textile, or other web materials
5. **Sports Analysis**: Track trajectory or movement patterns of fast-moving objects

## Pipeline Tips

### For Best Results
- Use a high framerate camera (200-750 fps recommended)
- Ensure consistent object motion
- Adjust `line-index` to capture the region of interest
- Set `output-size` based on expected duration or object size
- Use `videocrop` before linescan if needed to reduce processing

### Common Pipeline Patterns
```bash
# Pattern 1: Crop + Linescan + Display
camera ! videocrop ! linescan ! videoconvert ! autovideosink

# Pattern 2: Linescan + Encode + Save
camera ! linescan ! videoconvert ! x264enc ! mp4mux ! filesink

# Pattern 3: Linescan + Network Stream
camera ! linescan ! videoconvert ! jpegenc ! multipartmux ! tcpserversink
```

## Performance Considerations

- The plugin maintains an internal buffer equal to the full output image size
- Memory usage = `output_width × output_height × bytes_per_pixel`
- Per input frame the element does two copies: a cheap one-column copy into the
  internal roll buffer, and a copy of the **entire** roll buffer into a freshly
  allocated output buffer that is pushed downstream. The second copy (plus the
  alloc/free and any downstream `videoconvert` pass) is what limits throughput at
  high framerates — e.g. a 3584×2016×3 roll is ~21.7 MB copied every frame.
- **`emit-every=N`** decouples the push rate from the accumulation rate: the
  one-column copy still happens every frame, but the big copy + `gst_pad_push`
  only happen every Nth frame (and always on the frame that completes a roll, so
  the `rollover` signal / downstream image cadence is unchanged). On the skipped
  frames no output buffer is allocated at all. Set `emit-every ≈ framerate /
  consumer_fps` (the consumer being a ~30 fps live preview; the rollover/JPEG
  path is unaffected either way) to run the camera at full rate without the
  per-frame roll copy on the hot path.
- No frame buffering - processes each frame immediately

## Troubleshooting

### "Could not link" errors
- Ensure videocrop or other upstream elements provide fixed caps
- Try adding `videoconvert` before linescan if needed

### Line index out of range
- Check that `line-index` is less than input height (horizontal) or width (vertical)
- Use `-1` to automatically select the middle

### Wrapping/Rolling effect
- This is normal when the buffer fills up
- Adjust `output-size` to match your capture duration needs

## See Also

- [intervalometer](../intervalometer/README.md) - Auto-exposure control
- [rollingsum](../rollingsum/README.md) - Moving window sum detection
- [GStreamer Documentation](https://gstreamer.freedesktop.org/documentation/)