# gst-plugins-vision

GStreamer plugins for IDS uEye cameras with frame analysis capabilities.

#### TODO
 - []  idsueyesrc doesnt respect auto exposure set in ini file. need to be set in filter  `exposure=0.5`
 - []  


## Supported Elements

### Image Acquisition
- **idsueyesrc**: Video source for [IDS uEye cameras][1] (GigE Vision, USB 2/3, USB3 Vision)

### Video Analysis
- **rollingsum**: Drops frames based on rolling mean analysis of a single column. Analyzes pixel column deviation from rolling baseline to detect anomalies or changes in the scene.


## Usage Examples

### Basic capture from IDS uEye camera
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/whole-presacler64_autoexp-binningx2.ini exposure=0.5 ! queue ! autovideosink
```

### Frame filtering based on column analysis
Drop frames when column mean deviates from rolling baseline by more than 0.5:
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/whole-presacler64_autoexp-binningx2.ini exposure=0.5 ! videoconvert ! video/x-raw,format=GRAY8 ! rollingsum window-size=1000 column-index=1 threshold=0.5 ! queue ! autovideosink
```

**Note:** The `rollingsum` element analyzes a single column of pixels and drops frames when the column mean deviates from the rolling mean baseline by more than the threshold. Use `videoconvert` to ensure proper format negotiation.

### Additional rollingsum examples

Analyze column 320 with larger window:
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/whole-presacler64_autoexp-binningx2.ini exposure=0.5 ! videoconvert ! video/x-raw,format=GRAY8 ! rollingsum window-size=5000 column-index=320 threshold=0.3 ! queue ! autovideosink
```

Use stride for faster processing (sample every 2 rows):
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/whole-presacler64_autoexp-binningx2.ini exposure=0.5 ! videoconvert ! video/x-raw,format=GRAY8 ! rollingsum window-size=1000 column-index=1 stride=2 threshold=0.5 ! queue ! autovideosink
```

Lower threshold for more sensitive detection:
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/whole-presacler64_autoexp-binningx2.ini exposure=0.5 ! videoconvert ! video/x-raw,format=GRAY8 ! rollingsum threshold=0.2 ! queue ! autovideosink
```

## Dependencies

- GStreamer 1.2.x or newer
- IDS uEye SDK (for camera support)

## Building on Windows

### Quick Start with PowerShell Script

The easiest way to build is using the provided PowerShell script:

```powershell
# Set the plugin installation path
$env:GST_PLUGIN_PATH = "C:\path\to\your\plugins"

# Build all plugins (IDS uEye + rollingsum) and auto-copy to GST_PLUGIN_PATH
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

The `build.ps1` script automatically copies plugins to `$env:GST_PLUGIN_PATH` if set. Alternatively:

1. Set `GST_PLUGIN_PATH` environment variable to point to your plugin directory
2. Copy the built DLLs manually:
   - `build\sys\idsueye\Release\libgstidsueye.dll`
   - `build\gst\rollingsum\Release\libgstrollingsum.dll`

### Verify Installation

```powershell
gst-inspect-1.0 idsueyesrc
gst-inspect-1.0 rollingsum
```

## Documentation

- [Rolling Sum Filter Design](DESIGN_ROLLINGSUM.md)
