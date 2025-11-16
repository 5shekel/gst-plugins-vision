# How to Send a Single Line (2456x1)

## Real Data - Single Line Transmission

The camera captures 2456x4 pixels, but we extract and transmit only **one line (2456x1)** using `videocrop`.

### Daytime Configuration (200fps)
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/100fps-10exp-2456x4pix-500top-cw-extragain.ini exposure=0.05 framerate=200 `
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

---

## Python-Based Control with Dynamic Parameter Adjustment

For more advanced control including runtime exposure and framerate adjustments, use the Python-based launcher with UDP control interface.

### Launch Camera with Control Interface

See [`scripts/launch-ids.py`](scripts/launch-ids.py) for the complete implementation.

```pwsh
# Setup GStreamer environment and run
. .\scripts\setup_gstreamer_env.ps1
uv run .\scripts\launch-ids.py
```

**Features:**
- Video streaming on UDP port 5000 (127.0.0.1)
- Control interface on UDP port 5001 (0.0.0.0)
- Dynamic exposure control (0.001-1.0 seconds)
- Dynamic framerate control (1-500 fps)
- Real-time parameter updates without restarting

**Control Commands:**

| Command | Description | Example |
|---------|-------------|---------|
| `SET_EXPOSURE <value>` | Set exposure in seconds | `SET_EXPOSURE 0.016` |
| `GET_EXPOSURE` | Get current exposure value | `GET_EXPOSURE` |
| `SET_FRAMERATE <value>` | Set framerate in Hz | `SET_FRAMERATE 30` |
| `GET_FRAMERATE` | Get current framerate | `GET_FRAMERATE` |
| `STATUS` | Get pipeline status and settings | `STATUS` |

**Example Usage:**
```pwsh
# Using netcat (nc) or PowerShell
echo "SET_EXPOSURE 0.010" | nc -u 127.0.0.1 5001
echo "GET_EXPOSURE" | nc -u 127.0.0.1 5001
echo "STATUS" | nc -u 127.0.0.1 5001
```

### Testing the Control Interface

See [`scripts/camera_control.py`](scripts/camera_control.py) for automated testing.

```pwsh
# Run comprehensive test suite (15 tests)
uv run .\scripts\camera_control.py
```

**Test Coverage:**
- Get/Set exposure and framerate
- Verify parameter changes take effect
- Test input validation and error handling
- Verify range limits (0.001-1.0s for exposure, 1-500 fps)
- Test invalid commands and syntax

**Example Test Output:**
```
Test 1: Get current exposure
  Command:  GET_EXPOSURE
  Response: OK 0.016
  ✓ PASS

Test 2: Set exposure to 10ms
  Command:  SET_EXPOSURE 0.010
  Response: OK 0.01
  ✓ PASS
```

---

## UDP Control Protocol Specification

Complete technical details for the UDP-based control interface.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     launch-ids.py Process                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐         ┌──────────────────────────┐  │
│  │   Main Thread    │         │  Control Server Thread   │  │
│  │                  │         │                          │  │
│  │  GStreamer       │◄────────┤  UDP Socket (Port 5001)  │  │
│  │  Pipeline        │ Thread- │  Command Parser          │  │
│  │  - idsueyesrc    │  Safe   │  Property Setter         │  │
│  │  - videocrop     │ Updates │  Response Handler        │  │
│  │  - queue         │         │                          │  │
│  │  - udpsink:5000  │         └──────────────────────────┘  │
│  └──────────────────┘                    ▲                   │
│                                           │                   │
└───────────────────────────────────────────┼───────────────────┘
                                            │
                                            │ UDP Commands
                                            │
                                   ┌────────┴────────┐
                                   │  Control Client │
                                   │  (Any UDP tool) │
                                   └─────────────────┘
```

### Connection Details

- **Control Port**: 5001 (UDP)
- **Bind Address**: 0.0.0.0 (accepts from any interface)
- **Video Port**: 5000 (UDP) - existing video stream, unchanged
- **Protocol**: UDP (connectionless, stateless)
- **Encoding**: ASCII text
- **Delimiter**: Newline (`\n`)

### Command Format

Commands follow this general structure:
```
COMMAND [PARAMETERS]\n
```

Commands are case-insensitive, but UPPERCASE is recommended for clarity.

### Detailed Command Reference

#### 1. SET_EXPOSURE

**Description**: Sets the camera exposure time.

**Syntax**:
```
SET_EXPOSURE <value>
```

**Parameters**:
- `<value>`: Exposure time in seconds (float)
  - Range: 0.001 to 1.0 seconds (1ms to 1000ms)
  - Examples: `0.016` (16ms), `0.001` (1ms), `0.100` (100ms)

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_message>
```

**Examples**:
```
Client: SET_EXPOSURE 0.016\n
Server: OK 0.016\n

Client: SET_EXPOSURE 2.0\n
Server: ERROR OUT_OF_RANGE: Exposure must be 0.001-1.0 seconds\n
```

#### 2. GET_EXPOSURE

**Description**: Retrieves the current exposure time.

**Syntax**:
```
GET_EXPOSURE
```

**Parameters**: None

**Response**:
```
OK <current_value>
```

**Example**:
```
Client: GET_EXPOSURE\n
Server: OK 0.016\n
```

#### 3. SET_FRAMERATE

**Description**: Sets the camera frame rate.

**Syntax**:
```
SET_FRAMERATE <value>
```

**Parameters**:
- `<value>`: Frame rate in Hz (float)
  - Range: 1.0 to 500.0 fps
  - Examples: `22`, `30.5`, `100`

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_message>
```

**Example**:
```
Client: SET_FRAMERATE 30\n
Server: OK 30.0\n
```

#### 4. GET_FRAMERATE

**Description**: Retrieves the current frame rate.

**Syntax**:
```
GET_FRAMERATE
```

**Parameters**: None

**Response**:
```
OK <current_value>
```

**Example**:
```
Client: GET_FRAMERATE\n
Server: OK 22.0\n
```

#### 5. STATUS

**Description**: Get overall pipeline status and current settings.

**Syntax**:
```
STATUS
```

**Parameters**: None

**Response**:
```
OK exposure=<value> framerate=<value> state=<PLAYING|PAUSED|NULL>
```

**Example**:
```
Client: STATUS\n
Server: OK exposure=0.016 framerate=22.0 state=PLAYING\n
```

### Error Handling

**Error Response Format**:
```
ERROR <error_code>: <error_message>
```

**Common Error Codes**:

| Code | Description | Example |
|------|-------------|---------|
| `INVALID_COMMAND` | Unknown command | `ERROR INVALID_COMMAND: Unknown command 'FOO'` |
| `INVALID_SYNTAX` | Malformed command | `ERROR INVALID_SYNTAX: Missing parameter` |
| `OUT_OF_RANGE` | Value out of valid range | `ERROR OUT_OF_RANGE: Exposure must be 0.001-1.0` |
| `PROCESSING` | Internal processing error | `ERROR PROCESSING: Failed to set property` |

### Client Implementation Examples

#### Python Client
```python
import socket

def send_command(command, host="127.0.0.1", port=5001):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(command.encode() + b'\n', (host, port))
    sock.settimeout(1.0)
    response, _ = sock.recvfrom(1024)
    sock.close()
    return response.decode().strip()

# Set exposure to 10ms
print(send_command("SET_EXPOSURE 0.010"))

# Get current exposure
print(send_command("GET_EXPOSURE"))

# Set framerate to 30fps
print(send_command("SET_FRAMERATE 30"))
```

#### Command Line (netcat/nc)
```bash
# Set exposure
echo "SET_EXPOSURE 0.020" | nc -u 127.0.0.1 5001

# Get exposure
echo "GET_EXPOSURE" | nc -u 127.0.0.1 5001

# Get status
echo "STATUS" | nc -u 127.0.0.1 5001
```

#### PowerShell Client
```powershell
$udpClient = New-Object System.Net.Sockets.UdpClient
$endpoint = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse("127.0.0.1"), 5001)

# Send command
$bytes = [System.Text.Encoding]::ASCII.GetBytes("SET_EXPOSURE 0.015`n")
$udpClient.Send($bytes, $bytes.Length, $endpoint)

# Receive response
$udpClient.Client.ReceiveTimeout = 1000
$receiveBytes = $udpClient.Receive([ref]$endpoint)
$response = [System.Text.Encoding]::ASCII.GetString($receiveBytes)
Write-Host $response

$udpClient.Close()
```

### Implementation Notes

#### Thread Safety
- The control server runs in a separate daemon thread
- GStreamer properties are inherently thread-safe (GObject properties)
- The `src.set_property()` method can be safely called from the control thread

#### Non-Blocking Operation
- Control server uses non-blocking socket with timeout
- Does not interfere with GStreamer pipeline operation
- Minimal latency for command processing

#### Response Timing
- Responses are sent immediately after processing
- Property changes take effect on the next frame capture
- No guaranteed synchronization with video stream

### Future Enhancements

Possible extensions to the protocol:
- Add `SET_GAIN` / `GET_GAIN` commands
- Add `SAVE_CONFIG` to save current settings to INI file
- Add `RESET` to restore default settings
- Support batch commands (multiple commands in one packet)
- Add authentication/security for production use

---

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

### Real-time Channel Visualization

For live visualization of RGB/BGR channel values across the line sensor, use the real-time plotter.

See [`scripts/visualize_line_realtime.py`](scripts/visualize_line_realtime.py) for the implementation.

```pwsh
# Basic usage (assumes BGR format, 2456 width, port 5000)
uv run .\scripts\visualize_line_realtime.py
```

```pwsh
# With custom parameters
uv run .\scripts\visualize_line_realtime.py --format BGR --port 5000 --width 2456 --fps-limit 30
```

**Features:**
- **Dual Plot Display:**
  - Top plot: Grayscale luminance (weighted: BGR→0.114B+0.587G+0.299R)
  - Bottom plot: Individual RGB/BGR color channels
- **Real-time Statistics:**
  - Per-channel min/max/mean/std deviation
  - Display FPS counter
  - Frame counter
- **Optimized Performance:**
  - Packet draining (always displays latest frame)
  - Configurable display rate limiting
  - Minimal buffer size to reduce latency

**Command-line Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--format` | `BGR` | Input format (`BGR` or `RGB`) |
| `--port` | `5000` | UDP port to receive on |
| `--width` | `2456` | Line width in pixels |
| `--fps-limit` | `30` | Maximum display update rate |

**Example Output:**

The visualization shows live channel data with statistics overlay:
```
Frame: 1523  FPS: 29.8
Blue : min= 12 max=203 mean= 45.32 std= 28.45
Green: min= 28 max=241 mean= 68.91 std= 35.12
Red  : min= 35 max=255 mean=102.76 std= 48.23
Gray : min= 41.23 max=241.67 mean= 72.45 std= 36.89
```

**Use Cases:**
- Verify camera line sensor is working correctly
- Monitor real-time brightness and color balance
- Debug exposure and gain settings
- Analyze scene illumination changes
- Quality control and calibration

Close the plot window to exit.

---

## Configuration Notes

 INI file is configured with:
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