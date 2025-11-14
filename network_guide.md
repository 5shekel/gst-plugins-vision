# How to Send a Single Line (2456x1)

## Real Data - Single Line Transmission

The camera captures 2456x4 pixels, but we extract and transmit only **one line (2456x1)** using `videocrop`.

### Daytime Configuration (200fps)
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/200fps-2456x4pix-cw.ini exposure=5 framerate=200 `
    ! videocrop bottom=3 `
    ! queue `
    ! udpsink host=127.0.0.1 port=5000
```

### Nighttime Configuration (100fps, extra gain)
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/100fps-10exp-2456x4pix-500top-cw-extragain.ini exposure=10 framerate=100 `
    ! videocrop bottom=3 `
    ! queue `
    ! udpsink host=127.0.0.1 port=5000
```

**Key Parameters:**
- `videocrop bottom=3` - Extracts only the top line (removes bottom 3 rows from 2456x4 image)
- Input: 2456x4 BGR from camera
- Output: 2456x1 BGR line transmitted via UDP
- Frame size: 7368 bytes (2456 × 1 × 3 channels)

**Alternative:** To extract the bottom line instead, use `videocrop top=3`

### Python/OpenCV Receiver
```pwsh
# Basic rolling display
uv run .\scripts\recv_raw_rolling.py
```

```pwsh
# With display throttling and recording
uv run .\scripts\recv_raw_rolling.py --display-fps 60 --save-mjpeg .\results\output_60fps.avi
```

```pwsh
# Max performance (no display, stats only)
uv run .\scripts\recv_raw_rolling.py --no-display
```

See [`scripts/recv_raw_rolling.py`](scripts/recv_raw_rolling.py) for the Python implementation with debug options.

### UDP Traffic Analysis & Debugging

To inspect and analyze the raw UDP packets being transmitted:

```pwsh
# Detailed payload analyzer - shows format, dimensions, pixel statistics
uv run .\scripts\udp_payload_analyzer.py
```

**Example Output:**
```
================================================================================
PACKET #1 @ 17:45:23.456
================================================================================
Source: 127.0.0.1:52341
Total Size: 7368 bytes

PROTOCOL ANALYSIS:
--------------------------------------------------------------------------------
  protocol            : RAW
  header_size         : 0
  payload_size        : 7368

VIDEO PAYLOAD ANALYSIS:
--------------------------------------------------------------------------------
  📹 Real camera data - Single line 2456x1 BGR
  Format: BGR
  Dimensions: 2456x1
  Channels: 3

PIXEL STATISTICS:
--------------------------------------------------------------------------------
  Channel 0 (B/R)     : min=  0, max=110, mean= 28.63, std= 16.16
  Channel 1 (G)       : min= 17, max=233, mean= 62.39, std= 36.93
  Channel 2 (R/B)     : min= 25, max=255, mean= 99.76, std= 49.81

HEX PREVIEW (first 32 bytes):
--------------------------------------------------------------------------------
  19 2e 4a 12 30 41 0a 2f 3f 01 32 3e 00 32 40 00 31 45 18 2d 4c 1e 2d...

SESSION SUMMARY:
Total Packets: 235
Total Bytes: 1,731,480 (7368 bytes/packet)
```

The analyzer automatically detects the format, shows pixel statistics per color channel, and provides a hex preview for debugging. Perfect for verifying data transmission and diagnosing issues.

```pwsh
# Simple packet receiver (no analysis, just basic info)
uv run .\scripts\udp_sniffer_raw.py
```

## Configuration Notes

Both INI files are configured with:
- Start Y = 500 (captures from row 500 of the sensor)
- Height = 4 pixels
- Width = 2456 pixels
- This optimizes for the center region of the sensor

**Note:** `exposure=5` (5ms) may be too fast for some applications. Adjust based on your requirements.

---

# Demo Data (Testing)
## Sender (crop to first column, send raw over UDP)
```pwsh
gst-launch-1.0 -v `
    videotestsrc pattern=smpte ! `
    videocrop left=0 right=639 top=0 bottom=0 ! `
    video/x-raw,format=RGB,width=1,height=640,framerate=30/1 ! `
    udpsink host=127.0.0.1 port=5000
```

### GStreamer Receiver (raw UDP → display)
```pwsh
gst-launch-1.0 -v `
    udpsrc port=5000 caps="video/x-raw,format=RGB,width=1,height=640,framerate=30/1" ! `
    videoconvert ! `
    autovideosink
```