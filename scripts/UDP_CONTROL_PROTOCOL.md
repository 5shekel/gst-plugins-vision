# UDP Control Protocol Specification

## Overview

This document describes the UDP-based control protocol for dynamically controlling the IDS uEye camera exposure during runtime.

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
- **Encoding**: ASCII text
- **Delimiter**: Newline (`\n`)

## Command Format

### General Structure
```
COMMAND [PARAMETERS]\n
```

Commands are case-insensitive, but UPPERCASE is recommended for clarity.

## Supported Commands

### 1. SET_EXPOSURE

**Description**: Sets the camera exposure time.

**Syntax**:
```
SET_EXPOSURE <value>
```

**Parameters**:
- `<value>`: Exposure time in milliseconds (float)
  - Range: 1.0 to 1000.0 milliseconds
  - Examples: `16` (16ms), `1` (1ms), `100` (100ms)

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
Client: SET_EXPOSURE 16\n
Server: OK 16\n

Client: SET_EXPOSURE 2000\n
Server: ERROR Value out of range (1.0-1000.0)\n
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
Server: OK 16\n
```

### 3. SET_FRAMERATE

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

### 4. GET_FRAMERATE

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

### 5. STATUS

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
Server: OK exposure=16 framerate=22.0 state=PLAYING\n
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
| `INVALID_SYNTAX` | Malformed command | `ERROR INVALID_SYNTAX: Missing parameter` |
| `OUT_OF_RANGE` | Value out of valid range | `ERROR OUT_OF_RANGE: Exposure must be 1.0-1000.0` |
| `PIPELINE_ERROR` | Pipeline not running | `ERROR PIPELINE_ERROR: Pipeline not in PLAYING state` |

## Implementation Notes

### Thread Safety
- The control server runs in a separate daemon thread
- GStreamer properties are inherently thread-safe (GObject properties)
- The `src.set_property()` method can be safely called from the control thread

### Non-Blocking Operation
- Control server uses non-blocking socket with timeout
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
- Add `SET_GAIN` / `GET_GAIN` commands
- Add `SAVE_CONFIG` to save current settings to INI file
- Add `RESET` to restore default settings
- Support batch commands (multiple commands in one packet)
- Add authentication/security for production use