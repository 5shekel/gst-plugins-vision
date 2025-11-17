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
- Processing overhead is minimal (single memcpy per frame)
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