# gst-plugins-vision

Custom GStreamer elements for an IDS uEye line-scan camera rig, plus the
Python/PowerShell tooling around it. The rig points a short, wide sensor ROI at
a scene and accumulates one column per frame into a slowly scrolling "roll"
image (think photo-finish / strip photography).

## Supported Elements

Inspect any of these with `gst-inspect-1.0 <name>` for the full property list.

### Image Acquisition
- **idsueyesrc** (`sys/idsueye/`): video source for [IDS uEye cameras][1]
  (GigE Vision, USB 2/3, USB3 Vision). Always pass `config-file=` pointing at a
  uEye `.ini` (see [`ini/`](ini/)); without it the element tries to load presets
  from camera EEPROM and fails with a misleading error. Key properties:
  `device-id`, `config-file`, `exposure` (ms), `framerate`, `gain`, `gain-boost`.

### Video Analysis
- **linescan** (`gst/linescan/`): extracts one row (`direction=horizontal`) or
  column (`direction=vertical`) per input frame and stacks them into a scrolling
  line-scan image. `line-index=-1` picks the middle. `output-size` is the number
  of lines accumulated before the buffer wraps; on each wrap it emits a
  `rollover` signal carrying the completed image. See
  [gst/linescan/README.md](gst/linescan/README.md).
- **intervalometer** (`gst/intervalometer/`): brightness-driven auto-exposure
  for `idsueyesrc`. Sits directly downstream of the camera, reaches back to it
  by element name (`camera-element=`), and ramps `exposure`/`gain` to hold
  `target-brightness`. Logs every adjustment to a CSV.
- **rollingsum**: *deprecated* frame-dropping filter (rolling-mean deviation of
  a single column). Source removed; kept here only for reference.

Other plugin dirs exist for narrower jobs (`appendsignals`, `bayerutils`,
`extractcolor`, `klv`, `misb`, `select`, `sensorfx`, `videoadjust`) —
`gst-inspect-1.0` them as needed.

## Line-scan capture

The two scripts under [`gst/linescan/`](gst/linescan/) are the primary workflow.
Both build the same acquisition front end and differ only in what they do with
the linescan output.

```
idsueyesrc → intervalometer → videoflip method=3 (CCW 90°) → queue → linescan direction=vertical
```

Geometry, using [`ini/roi-dusk.ini`](ini/roi-dusk.ini) (sensor ROI 2016 × 20,
W × H):

| stage | result |
|-------|--------|
| `videoflip method=3` (CCW 90°) | 20 × 2016 |
| `linescan direction=vertical`  | `output-size` × 2016 — one column per frame, roll grows left→right |

`output-size` (the roll width) defaults to whatever makes the raw image 16:9 for
its height: `2016 × 16/9 = 3584`. Keep the raw roll wide and downscale it at
view time. Override with `--output-size N`; change the target ratio with
`--aspect W:H`. Both scripts read the ROI width straight from the `.ini`, so
pointing `--config` at a different ROI recomputes the geometry.

Camera settings are shared: `--mode day` → 0.02 ms exposure, gain 0;
`--mode night` → 5.25 ms exposure, gain 65. Defaults: `--framerate 200`,
`--device-id 1`. The intervalometer runs enabled with `target-brightness 80`,
`gain-max 82`, `ramp-rate slow`, logging to `timelapse.csv`.

### Live preview — [`print_camera_cli.py`](gst/linescan/print_camera_cli.py)

Prints (does not run) a `gst-launch-1.0` one-liner that shows the scrolling roll
in a window. The tail of the pipeline downscales to `--display-width` ×
`--display-height` and throttles to `--display-fps` (linescan emits one frame
per *camera* frame, i.e. 200–1300 fps, which a video sink would otherwise drop
as "late"), then feeds a leaky queue into `autovideosink sync=false`.

```pwsh
# copy-paste the printed command, or on PowerShell:
uv run gst/linescan/print_camera_cli.py --mode day | Invoke-Expression
```

Useful flags: `--sink glimagesink`, `--output-size`, `--aspect`,
`--display-width/-height/-fps`, `--config`.

### Recording — [`launch_with_signal.py`](gst/linescan/launch_with_signal.py)

Builds the pipeline in Python, connects the `rollover` signal, and writes one
JPEG per completed roll to `results/<date>/<funny-name>/linescan_capture_NNNNNN.jpg`
(override with `--output-dir`). The display branch is a `fakesink`; the JPEGs are
the output.

```pwsh
uv run gst/linescan/launch_with_signal.py                 # day mode, defaults
uv run gst/linescan/launch_with_signal.py --mode night
uv run gst/linescan/launch_with_signal.py --config ini/roi-night.ini
uv run gst/linescan/launch_with_signal.py --run-seconds 20 --debug   # timed check
```

Stop with Ctrl+C. `--num-buffers N` / `--run-seconds N` give bounded verification
runs; `--gst-debug` raises the GStreamer log level.

Prerequisites for both: build the plugins (`.\build.ps1`), run from the
workspace root so `--config` resolves, and have `GSTREAMER_1_0_ROOT_MSVC_X86_64`
set (the script adds the GI typelibs and DLL bin dir from it).

### Startup automation

[`launch_linescan.ps1`](launch_linescan.ps1) is a thin wrapper
(`.\launch_linescan.ps1 day|night [output-dir]`).
[`startup_linescan.ps1`](startup_linescan.ps1) +
[`register_startup.ps1`](register_startup.ps1) register a Task Scheduler job that
launches the recorder on login, picking day/night mode from the clock. See
[STARTUP.md](STARTUP.md).

## Network streaming

A separate path (`scripts/launch-ids.py`) crops the camera to a single line and
sends raw `video/x-raw` over `udpsink`, with a plain-text UDP control protocol on
port 5001 for live parameter changes. This needs a genuine one-row-per-frame ROI
such as [`ini/2456x4pix-500top-cw-extragain.ini`](ini/2456x4pix-500top-cw-extragain.ini)
(`videocrop bottom=3` → 2456 × 1); a UDP datagram cannot exceed 65507 bytes, so a
tall ROI will not fit. See [network_guide.md](network_guide.md),
[scripts/UDP_STREAM_TESTING.md](scripts/UDP_STREAM_TESTING.md), and
[scripts/UDP_CONTROL_PROTOCOL.md](scripts/UDP_CONTROL_PROTOCOL.md).

## Dependencies

- GStreamer 1.2.x or newer (dev box runs 1.26.8 MSVC x86_64)
- IDS uEye SDK (for camera support)
- [`uv`](https://docs.astral.sh/uv/) for the Python scripts

## Building on Linux/ARM64

### Quick Start with Build Script

The easiest way to build on Linux (including ARM64/aarch64) is using the provided build script:

```bash
# Build all plugins and install to system directories
./build.sh

# Build only IDS uEye plugin
./build.sh --build-type idsueye-only

# Build in debug mode without installing
./build.sh --config debug --no-install

# Show help
./build.sh --help
```

### Manual Build Process

1. Install dependencies:
```bash
sudo apt-get update
sudo apt-get install cmake build-essential
sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
sudo apt-get install liborc-0.4-dev libglib2.0-dev
```

2. Install IDS uEye SDK (for camera support):
   - Download ARM64 version from [IDS website](https://en.ids-imaging.com)
   - Or use system packages if available

3. Build:
```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
sudo make install
```

### Verification
```bash
# Verify plugin installation
gst-inspect-1.0 idsueyesrc
gst-inspect-1.0 linescan
gst-inspect-1.0 intervalometer

# Test with IDS camera (if connected)
gst-launch-1.0 idsueyesrc device-id=1 num-buffers=100 ! videoconvert ! autovideosink
```

**Tested Platforms:**
- ✅ Linux ARM64 (aarch64) - Jetson Xavier/Orin with Ubuntu 20.04 LTS
- ✅ Linux x86_64
- ✅ Windows x86_64

## Building on Windows

### Quick Start with PowerShell Script

The easiest way to build is using the provided PowerShell script:

```powershell
# Set the plugin installation path
$env:GST_PLUGIN_PATH = "C:\path\to\your\plugins"

# Build all plugins and auto-copy to GST_PLUGIN_PATH
.\build.ps1
```

For more options, see:
```powershell
Get-Help .\build.ps1 -Detailed
```

### Manual Build Process

If you prefer to build manually:

1. Install [CMake](https://cmake.org/)
2. Install [GStreamer distribution](https://gstreamer.freedesktop.org/download/) (default path: `C:\bin\gstreamer\1.0\msvc_x86_64`)
3. Install [IDS uEye SDK](https://www.ids-imaging.com) (default path: `C:\Program Files\IDS\uEye\Develop`)
4. Run:

```powershell
git clone https://github.com/joshdoe/gst-plugins-vision.git
cd gst-plugins-vision
mkdir build
cd build
cmake .. -G "Visual Studio 16 2019" -A x64 -DGSTREAMER_ROOT="C:\bin\gstreamer\1.0\msvc_x86_64"
cmake --build . --config Release
```

### Installation

The `build.ps1` script automatically copies plugins to `$env:GST_PLUGIN_PATH` if
set (on this dev box that is `C:\dev\gst-plugins-vision\gst_plugs`). Otherwise
set `GST_PLUGIN_PATH` to your plugin directory and copy the built DLLs there.

### Verify Installation

```powershell
gst-inspect-1.0 idsueyesrc
gst-inspect-1.0 linescan
gst-inspect-1.0 intervalometer
```

## Debugging

Set a per-element log level, e.g. `$env:GST_DEBUG="linescan:5"`.

For a pipeline graph, set `$env:GST_DEBUG_DUMP_DOT_DIR='.'`, run the pipeline,
then render a `.dot` dump with [GraphvizOnline](https://dreampuf.github.io/GraphvizOnline/)
or:
```pwsh
dot -Tsvg 0.00.02.922833100-gst-launch.PAUSED_PLAYING.dot -o same.svg
```

[1]: https://en.ids-imaging.com
