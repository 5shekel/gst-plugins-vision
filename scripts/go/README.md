# Go UDP Receiver - High-Performance UDP Testing Tool

A high-performance Go implementation for testing UDP reception performance. This version focuses purely on UDP performance without any GUI/display components, making it ideal for benchmarking network throughput and detecting dropped frames.

## Features

- **Pure UDP Performance**: No GUI overhead, focuses on network performance
- **High Throughput**: Go's native performance handles 200+ fps easily
- **Low Latency**: Dedicated goroutine for UDP reception
- **Drop Detection**: Tracks and reports dropped frames based on timing
- **Bandwidth Monitoring**: Real-time bandwidth usage statistics
- **Clean Output**: Console-based statistics ideal for logging and analysis

## Prerequisites

- **Go 1.21+**: Download from https://go.dev/dl/
- **No other dependencies**: Pure Go implementation using only standard library

## Building

### Windows (PowerShell)

```powershell
# From project root
.\scripts\build_go_receiver.ps1

# Or manually from scripts/go directory
cd scripts\go
go build -o recv_raw_rolling.exe main.go
```

### Linux/macOS

```bash
# From project root
./scripts/build_go_receiver.sh

# Or manually from scripts/go directory
cd scripts/go
go build -o recv_raw_rolling main.go
```

## Running

```bash
# Windows
cd scripts\go
.\recv_raw_rolling.exe

# Linux/macOS
cd scripts/go
./recv_raw_rolling
```

Press `Ctrl+C` to stop and display final statistics.

## Configuration

Edit the constants in [`main.go`](main.go:13) to match your setup:

- `COLUMN_WIDTH`: Width of incoming data (default: 4)
- `COLUMN_HEIGHT`: Height of incoming data (default: 2456)
- `CHANNELS`: Number of color channels (default: 3 for RGB)
- `UDP_PORT`: UDP port to listen on (default: 5000)
- `EXPECTED_FPS`: Expected frame rate for drop detection (default: 200)

## Output

The receiver displays statistics every 100 frames:

```
Frame    100: Real FPS:  198.5 | Instant:  200.2 | BW:  34.56 MB/s
Frame    200: Real FPS:  199.1 | Instant:  199.8 | BW:  34.62 MB/s
Frame    300: Real FPS:  199.8 | Instant:  200.1 | BW:  34.59 MB/s | ⚠️  2 drops
```

On shutdown (Ctrl+C), it displays final statistics:

```
=== Final Statistics ===
Total Frames: 1234
Total Time: 6.17 seconds
Average FPS: 200.0
Instant FPS: 199.8
Total Drops: 5
Total Data: 35.67 MB
Bandwidth: 34.58 MB/s
```

## Performance Comparison

| Implementation | Typical FPS | CPU Usage | Overhead |
|---------------|-------------|-----------|----------|
| Python (OpenCV) | ~100 fps | High | Display rendering |
| **Go (Console)** | **200+ fps** | **Minimal** | **None** |

## Use Cases

- **UDP Performance Testing**: Measure maximum UDP throughput
- **Network Diagnostics**: Detect packet loss and timing issues
- **Benchmarking**: Compare network setups and configurations
- **Automated Testing**: Console output suitable for CI/CD pipelines
- **High-Speed Data Acquisition**: Validate 200+ fps data streams

## Technical Details

- **Concurrent UDP Reception**: Dedicated goroutine prevents frame drops
- **16MB Receive Buffer**: Configured for high-throughput scenarios
- **Zero Display Overhead**: Pure console output for maximum performance
- **Graceful Shutdown**: Handles Ctrl+C and displays final statistics
- **No External Dependencies**: Pure Go standard library

## Troubleshooting

### Build Errors

Ensure you have Go 1.21+ installed:
```bash
go version
```

### Port Already in Use

If port 5000 is in use, edit `UDP_PORT` in [`main.go`](main.go:31) and rebuild.

### High Drop Rate

1. Check network configuration with [`scripts/udp_optimize.ps1`](../udp_optimize.ps1) (Windows)
2. Verify sender is transmitting at correct rate
3. Check for network congestion or interference
4. Consider increasing receive buffer size in code

## Comparison with Python Version

The Python version ([`scripts/recv_raw_rolling.py`](../recv_raw_rolling.py)) includes visual display but has lower throughput:

- **Use Go version for**: Performance testing, benchmarking, headless servers
- **Use Python version for**: Visual debugging, development, seeing actual data

## Changes from Previous Version

This version has been simplified to focus purely on UDP performance:

- ✅ Removed SDL2 dependency
- ✅ Removed GUI/display components  
- ✅ Added comprehensive statistics
- ✅ Improved drop detection
- ✅ Added bandwidth monitoring
- ✅ Zero external dependencies