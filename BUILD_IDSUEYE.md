# Building IDS uEye Plugin Only

This guide explains how to build only the IDS uEye GStreamer plugin from the gst-plugins-vision project.

## Prerequisites

1. **IDS uEye SDK** must be installed on your system
   - Default location (Windows): `C:\Program Files\IDS\uEye\Develop`
   - If installed elsewhere, set the `IDSUEYE_DIR` CMake variable

2. **Build tools**:
   - CMake (version 2.8.0 or higher)
   - Visual Studio 2019 or newer (on Windows)
   - GStreamer development files (1.2.0 or higher)

3. **Required GStreamer components**:
   - GStreamer base library
   - GStreamer video library
   - GLib2
   - GObject

## Building

### Quick Build (Windows)

Simply run the provided batch script:

```batch
build_idsueye_only.bat
```

Or provide a custom GStreamer path:

```batch
build_idsueye_only.bat "C:\path\to\gstreamer"
```

This will:
1. Create a `build_idsueye` directory
2. Use the standalone IDS uEye CMakeLists configuration
3. Configure the project with CMake
4. Build only the IDS uEye plugin
5. Output: `build_idsueye\sys\idsueye\Release\libgstidsueye.dll`

**Default GStreamer location:** `C:\bin\gstreamer\1.0\msvc_x86_64`

### Manual Build

If you prefer manual control or need to customize the build:

```batch
# Create build directory
mkdir build_idsueye
cd build_idsueye

# Configure (adjust generator as needed)
cmake .. -G "Visual Studio 16 2019" -A x64

# Build only IDS uEye target
cmake --build . --config Release --target gstidsueye

# Or for Debug build
cmake --build . --config Debug --target gstidsueye
```

### Custom IDS uEye SDK Location

If your IDS uEye SDK is installed in a non-standard location:

```batch
cmake .. -G "Visual Studio 16 2019" -A x64 -DIDSUEYE_DIR="C:\Path\To\IDS\uEye\Develop"
```

### Linux Build

```bash
mkdir build_idsueye
cd build_idsueye
cmake ..
make gstidsueye
```

## Output

The built plugin will be located at:
- **Windows Release**: `build_idsueye\sys\idsueye\Release\libgstidsueye.dll`
- **Windows Debug**: `build_idsueye\sys\idsueye\Debug\libgstidsueye.dll`
- **Linux**: `build_idsueye/sys/idsueye/libgstidsueye.so`

## Installation

To install the plugin to the GStreamer plugin directory:

```batch
cmake --build . --config Release --target install
```

Or manually copy the DLL to your GStreamer plugins directory (typically `C:\gstreamer\1.0\msvc_x86_64\lib\gstreamer-1.0\`).

## Troubleshooting

### IDS uEye SDK Not Found

If CMake cannot find the IDS uEye SDK:
1. Verify the SDK is installed
2. Check the installation path
3. Set `IDSUEYE_DIR` explicitly in the CMake command

### Missing Dependencies

If GStreamer dependencies are not found:
1. Ensure GStreamer and development headers are installed
2. Add GStreamer to your system PATH
3. Set `GSTREAMER_ROOT` environment variable if needed

### Link Errors

Make sure you're building for the correct architecture (x64 vs x86) matching your IDS uEye SDK installation.