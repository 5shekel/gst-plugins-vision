# UDP Control Protocol Specification

## Overview

This document describes the UDP-based control protocol for dynamically controlling the IDS uEye camera during runtime.

## Architecture

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

## Connection Details

- **Control Port**: 5001 (UDP)
- **Bind Address**: 0.0.0.0 (accepts from any interface)
- **Video Port**: 5000 (UDP) - existing video stream, unchanged
- **Protocol**: UDP (connectionless, stateless)
- **Encoding**: ASCII/UTF-8 text
- **Delimiter**: Newline (`\n`)

## Command Format

### General Structure
```
COMMAND [PARAMETERS]\n
```

Commands are case-insensitive (the server uppercases the whole line before parsing).

### Size Limits
- **Receive Buffer**: 8192 bytes (8KB)
- **Maximum Command Length**: 1024 characters
- Commands exceeding 1024 characters will be rejected with `ERROR INVALID_SYNTAX: Command too long (max 1024 chars)`

## Supported Commands

### 1. SET_EXPOSURE

**Description**: Sets the camera exposure time.

**Syntax**:
```
SET_EXPOSURE <value>
```

**Parameters**:
- `<value>`: Exposure time in milliseconds (float)
  - Range: 0.015 to 30000.0 milliseconds
  - Examples: `16` (16ms), `1` (1ms), `100` (100ms)

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_code>: <error_message>
```

**Examples**:
```
Client: SET_EXPOSURE 16\n
Server: OK 16.0\n

Client: SET_EXPOSURE 50000\n
Server: ERROR OUT_OF_RANGE: Exposure must be 0.015-30000 milliseconds\n
```

### 2. GET_EXPOSURE

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
Server: OK 16.0\n
```

### 3. GET_EXPOSURE_RANGE

**Description**: Returns the theoretical exposure range from the API documentation. The real-time min/max/increment is sensor-dependent and is queried by the underlying C code (`gstidsueyesrc.c`) via `is_Exposure`/`IS_EXPOSURE_CMD_GET_EXPOSURE_RANGE` before each `SET_EXPOSURE` call, so this command's `inc` field is intentionally not a concrete number.

**Syntax**:
```
GET_EXPOSURE_RANGE
```

**Parameters**: None

**Response**:
```
OK min=0.015 max=30000.0 inc=varies_by_sensor
```

**Example**:
```
Client: GET_EXPOSURE_RANGE\n
Server: OK min=0.015 max=30000.0 inc=varies_by_sensor\n
```

### 4. SET_FRAMERATE

**Description**: Sets the camera frame rate.

**Syntax**:
```
SET_FRAMERATE <value>
```

**Parameters**:
- `<value>`: Frame rate in Hz (float)
  - Range: 1.0 to 20200.0 fps
  - Examples: `22`, `30.5`, `750`

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_code>: <error_message>
```

**Example**:
```
Client: SET_FRAMERATE 30\n
Server: OK 30.0\n
```

### 5. GET_FRAMERATE

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

### 6. SET_CAMERA_ID

**Description**: Sets the camera ID property on the source element.

**Syntax**:
```
SET_CAMERA_ID <value>
```

**Parameters**:
- `<value>`: Integer, 0-254

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_code>: <error_message>
```

**Example**:
```
Client: SET_CAMERA_ID 1\n
Server: OK 1\n
```

### 7. GET_CAMERA_ID

**Description**: Retrieves the current camera ID.

**Syntax**:
```
GET_CAMERA_ID
```

**Response**:
```
OK <current_value>
```

### 8. SET_DEVICE_ID

**Description**: Sets the device ID property on the source element.

**Syntax**:
```
SET_DEVICE_ID <value>
```

**Parameters**:
- `<value>`: Integer, 0-254

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_code>: <error_message>
```

### 9. GET_DEVICE_ID

**Description**: Retrieves the current device ID.

**Syntax**:
```
GET_DEVICE_ID
```

**Response**:
```
OK <current_value>
```

### 10. SET_GAIN

**Description**: Sets the camera gain.

**Syntax**:
```
SET_GAIN <value>
```

**Parameters**:
- `<value>`: Integer, 0-100 (0 for auto)

**Response**:
```
OK <actual_value>
```
or
```
ERROR <error_code>: <error_message>
```

### 11. GET_GAIN

**Description**: Retrieves the current gain.

**Syntax**:
```
GET_GAIN
```

**Response**:
```
OK <current_value>
```

### 12. SET_AUTO_EXPOSURE

**Description**: Enables or disables automatic exposure.

**Syntax**:
```
SET_AUTO_EXPOSURE <0|1>
```

**Parameters**:
- `<value>`: `0` (off) or `1` (on)

**Response**:
```
OK <0|1>
```
or
```
ERROR <error_code>: <error_message>
```

### 13. GET_AUTO_EXPOSURE

**Description**: Retrieves the current auto-exposure state.

**Syntax**:
```
GET_AUTO_EXPOSURE
```

**Response**:
```
OK <0|1>
```

### 14. SET_AUTO_GAIN

**Description**: Enables or disables automatic gain.

**Syntax**:
```
SET_AUTO_GAIN <0|1>
```

**Parameters**:
- `<value>`: `0` (off) or `1` (on)

**Response**:
```
OK <0|1>
```
or
```
ERROR <error_code>: <error_message>
```

### 15. GET_AUTO_GAIN

**Description**: Retrieves the current auto-gain state.

**Syntax**:
```
GET_AUTO_GAIN
```

**Response**:
```
OK <0|1>
```

### 16. SET_GAIN_BOOST

**Description**: Enables or disables gain boost.

**Syntax**:
```
SET_GAIN_BOOST <0|1>
```

**Parameters**:
- `<value>`: `0` (off) or `1` (on)

**Response**:
```
OK <0|1>
```
or
```
ERROR <error_code>: <error_message>
```

### 17. GET_GAIN_BOOST

**Description**: Retrieves the current gain-boost state.

**Syntax**:
```
GET_GAIN_BOOST
```

**Response**:
```
OK <0|1>
```

### 18. STATUS

**Description**: Get overall pipeline status and current settings.

**Syntax**:
```
STATUS
```

**Parameters**: None

**Response**:
```
OK exposure=<value> framerate=<value> camera_id=<value> device_id=<value> gain=<value> auto_exposure=<0|1> auto_gain=<0|1> gain_boost=<0|1> state=<PLAYING|PAUSED|NULL|READY>
```

`state` is the uppercased GStreamer pipeline state nick (`Gst.State.value_nick`), or `UNKNOWN` if no pipeline was attached to the server.

**Example**:
```
Client: STATUS\n
Server: OK exposure=16.0 framerate=22.0 camera_id=0 device_id=0 gain=0 auto_exposure=0 auto_gain=0 gain_boost=0 state=PLAYING\n
```

## Error Handling

### Error Response Format
```
ERROR <error_code>: <error_message>
```

### Common Error Codes

| Code | Description | Example |
|------|-------------|---------|
| `INVALID_COMMAND` | Unknown command | `ERROR INVALID_COMMAND: Unknown command 'FOO'` |
| `INVALID_SYNTAX` | Malformed command, wrong argument count, or non-numeric value | `ERROR INVALID_SYNTAX: Usage: SET_EXPOSURE <value>` |
| `OUT_OF_RANGE` | Value out of valid range | `ERROR OUT_OF_RANGE: Exposure must be 0.015-30000 milliseconds` |
| `PROCESSING` | Unexpected exception while dispatching the command | `ERROR PROCESSING: <exception message>` |

Individual property getters/setters that raise an unexpected exception (e.g. a GObject property error) return a bare `ERROR: <message>` without a code.

## Implementation Notes

### Thread Safety
- The control server runs in a separate daemon thread
- GStreamer properties are inherently thread-safe (GObject properties)
- The `src.set_property()` method can be safely called from the control thread

### Non-Blocking Operation
- Control server uses a non-blocking socket with a 0.5s timeout
- Does not interfere with GStreamer pipeline operation
- Minimal latency for command processing

### Response Timing
- Responses are sent immediately after processing
- Property changes take effect on the next frame capture
- No guaranteed synchronization with video stream

## Usage Examples

### Python Client Example
```python
import socket

def send_command(command):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(command.encode() + b'\n', ('127.0.0.1', 5001))
    sock.settimeout(1.0)
    response, _ = sock.recvfrom(1024)
    sock.close()
    return response.decode().strip()

# Set exposure to 10ms
print(send_command("SET_EXPOSURE 10"))

# Get current exposure
print(send_command("GET_EXPOSURE"))

# Set framerate to 30fps
print(send_command("SET_FRAMERATE 30"))

# Enable auto-exposure
print(send_command("SET_AUTO_EXPOSURE 1"))

# Get full status
print(send_command("STATUS"))
```

### Command Line (netcat/nc)
```bash
# Set exposure
echo "SET_EXPOSURE 20" | nc -u 127.0.0.1 5001

# Get exposure
echo "GET_EXPOSURE" | nc -u 127.0.0.1 5001

# Get status
echo "STATUS" | nc -u 127.0.0.1 5001
```

### PowerShell Client
```powershell
$udpClient = New-Object System.Net.Sockets.UdpClient
$endpoint = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse("127.0.0.1"), 5001)

# Send command
$bytes = [System.Text.Encoding]::ASCII.GetBytes("SET_EXPOSURE 15`n")
$udpClient.Send($bytes, $bytes.Length, $endpoint)

# Receive response
$udpClient.Client.ReceiveTimeout = 1000
$receiveBytes = $udpClient.Receive([ref]$endpoint)
$response = [System.Text.Encoding]::ASCII.GetString($receiveBytes)
Write-Host $response

$udpClient.Close()
```

## Testing

A test client script is provided: `scripts/camera_control.py`

```bash
# Run the camera pipeline
uv run scripts/launch-ids.py

# In another terminal, test exposure control
uv run scripts/camera_control.py
```

## Future Enhancements

Possible extensions to the protocol:
- Add `SAVE_CONFIG` to save current settings to INI file
- Add `RESET` to restore default settings
- Support batch commands (multiple commands in one packet)
- Add authentication/security for production use
