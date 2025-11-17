#Requires -Version 5.1

<#
.SYNOPSIS
    Build GStreamer Vision Plugins

.DESCRIPTION
    Builds GStreamer vision plugins (IDS uEye, Rolling Sum, etc.) and copies them to GST_PLUGIN_PATH

.PARAMETER GStreamerRoot
    Path to GStreamer installation directory. Defaults to C:\bin\gstreamer\1.0\msvc_x86_64

.PARAMETER BuildType
    Type of build: 'All' (default), 'IDSuEyeOnly'
    
.PARAMETER Config
    Build configuration: 'Release' (default) or 'Debug'

.PARAMETER NoCopy
    Skip copying plugins to GST_PLUGIN_PATH

.EXAMPLE
    .\build.ps1
    Build all plugins with default settings

.EXAMPLE
    .\build.ps1 -GStreamerRoot "C:\custom\gstreamer\path"
    Build all plugins with custom GStreamer path

.EXAMPLE
    .\build.ps1 -BuildType IDSuEyeOnly
    Build only IDS uEye plugin

.EXAMPLE
    .\build.ps1 -Config Debug -NoCopy
    Build in Debug mode without copying to GST_PLUGIN_PATH
#>

param(
    [string]$GStreamerRoot = "",
    [ValidateSet('All', 'IDSuEyeOnly')]
    [string]$BuildType = 'All',
    [ValidateSet('Release', 'Debug')]
    [string]$Config = 'Release',
    [switch]$NoCopy
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Banner
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "GStreamer Vision Plugins Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Determine GStreamer root path
$defaultGStreamerRoot = "C:\bin\gstreamer\1.0\msvc_x86_64"

if ($GStreamerRoot) {
    Write-Host "Using GStreamer from parameter: $GStreamerRoot" -ForegroundColor Green
} elseif ($env:GSTREAMER_ROOT) {
    $GStreamerRoot = $env:GSTREAMER_ROOT
    Write-Host "Using GStreamer from environment: $GStreamerRoot" -ForegroundColor Green
} else {
    $GStreamerRoot = $defaultGStreamerRoot
    Write-Host "Using default GStreamer location: $GStreamerRoot" -ForegroundColor Green
}

# Verify GStreamer directory exists
if (-not (Test-Path $GStreamerRoot)) {
    Write-Host ""
    Write-Host "ERROR: GStreamer directory does not exist: $GStreamerRoot" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please provide correct GStreamer path:" -ForegroundColor Yellow
    Write-Host "  .\build.ps1 -GStreamerRoot 'C:\path\to\gstreamer'" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "Build Configuration:" -ForegroundColor Cyan
Write-Host "  Build Type: $BuildType" -ForegroundColor White
Write-Host "  Config: $Config" -ForegroundColor White
Write-Host "  GStreamer: $GStreamerRoot" -ForegroundColor White
Write-Host ""

# Determine build directory and CMakeLists configuration
if ($BuildType -eq 'IDSuEyeOnly') {
    $buildDir = "build_idsueye"
    $useStandaloneCMake = $true
    $pluginPaths = @(
        @{ Name = "libgstidsueye.dll"; RelPath = "Release\libgstidsueye.dll" }
    )
    Write-Host "Building: IDS uEye plugin only" -ForegroundColor Yellow
} else {
    $buildDir = "build"
    $useStandaloneCMake = $false
    $pluginPaths = @(
        @{ Name = "libgstidsueye.dll"; RelPath = "sys\idsueye\Release\libgstidsueye.dll" },
        @{ Name = "libgstrollingsum.dll"; RelPath = "gst\rollingsum\Release\libgstrollingsum.dll" },
        @{ Name = "libgstintervalometer.dll"; RelPath = "gst\intervalometer\Release\libgstintervalometer.dll" },
        @{ Name = "libgstlinescan.dll"; RelPath = "gst\linescan\Release\libgstlinescan.dll" }
    )
    Write-Host "Building: All plugins (IDS uEye, Rolling Sum, Intervalometer, Linescan)" -ForegroundColor Yellow
}

Write-Host ""

# Create build directory
if (-not (Test-Path $buildDir)) {
    New-Item -ItemType Directory -Path $buildDir | Out-Null
    Write-Host "Created build directory: $buildDir" -ForegroundColor Green
} else {
    Write-Host "Using existing build directory: $buildDir" -ForegroundColor Green
}

# Copy standalone CMakeLists if building IDS uEye only
if ($useStandaloneCMake) {
    Copy-Item -Path "CMakeLists_idsueye_only.txt" -Destination "$buildDir\CMakeLists.txt" -Force
    Write-Host "Using standalone IDS uEye CMakeLists configuration" -ForegroundColor Green
}

Write-Host ""

# Configure CMake
Write-Host "Configuring CMake..." -ForegroundColor Cyan
Write-Host ""

Push-Location $buildDir
try {
    if ($useStandaloneCMake) {
        # For standalone build, configure from current directory
        $cmakeArgs = @(
            ".",
            "-G", "Visual Studio 16 2019",
            "-A", "x64",
            "-DGSTREAMER_ROOT=$GStreamerRoot",
            "-DCMAKE_PREFIX_PATH=$GStreamerRoot"
        )
    } else {
        # For full build, configure from parent directory
        $cmakeArgs = @(
            "..",
            "-G", "Visual Studio 16 2019",
            "-A", "x64",
            "-DGSTREAMER_ROOT=$GStreamerRoot",
            "-DCMAKE_PREFIX_PATH=$GStreamerRoot"
        )
    }

    & cmake $cmakeArgs
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "CMake configuration failed!" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "Common issues:" -ForegroundColor Yellow
        Write-Host "1. GStreamer not properly installed at: $GStreamerRoot" -ForegroundColor Yellow
        Write-Host "2. IDS uEye SDK not found (default: C:\Program Files\IDS\uEye\Develop)" -ForegroundColor Yellow
        Write-Host "3. Missing GStreamer development files" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "To specify custom IDS uEye SDK location:" -ForegroundColor Yellow
        Write-Host "  `$env:IDSUEYE_DIR='C:\path\to\ueye\sdk'" -ForegroundColor Yellow
        Write-Host "  .\build.ps1" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }

    # Build the plugins
    Write-Host ""
    Write-Host "Building plugins..." -ForegroundColor Cyan
    Write-Host ""
    
    & cmake --build . --config $Config
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "Build failed!" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
        exit 1
    }

    # Collect built plugin paths (resolve to absolute paths while in build directory)
    $builtPlugins = @()
    foreach ($pluginInfo in $pluginPaths) {
        $pluginPath = $pluginInfo.RelPath
        if (Test-Path $pluginPath) {
            $fullPath = (Resolve-Path $pluginPath).Path
            $builtPlugins += $fullPath
            Write-Host "Found plugin: $fullPath" -ForegroundColor Gray
        } else {
            Write-Host "Warning: Expected plugin not found: $pluginPath" -ForegroundColor Yellow
        }
    }

    Pop-Location

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Build completed successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""

    # Display built plugins
    Write-Host "Built plugins:" -ForegroundColor Cyan
    foreach ($plugin in $builtPlugins) {
        Write-Host "  - $plugin" -ForegroundColor White
    }
    Write-Host ""

    # Copy plugins to GST_PLUGIN_PATH if requested
    if (-not $NoCopy) {
        if ($env:GST_PLUGIN_PATH) {
            Write-Host "Copying plugins to GST_PLUGIN_PATH..." -ForegroundColor Cyan
            Write-Host "  Destination: $env:GST_PLUGIN_PATH" -ForegroundColor White
            Write-Host "  Plugin count: $($builtPlugins.Count)" -ForegroundColor Gray

            if ($builtPlugins.Count -eq 0) {
                Write-Host ""
                Write-Host "Warning: No plugins found to copy!" -ForegroundColor Yellow
                Write-Host "Build may have failed or plugins built to unexpected location." -ForegroundColor Yellow
            } else {
                Write-Host ""

                # Ensure the directory exists
                if (-not (Test-Path $env:GST_PLUGIN_PATH)) {
                    New-Item -ItemType Directory -Path $env:GST_PLUGIN_PATH -Force | Out-Null
                    Write-Host "Created GST_PLUGIN_PATH directory: $env:GST_PLUGIN_PATH" -ForegroundColor Green
                    Write-Host ""
                }

                # Copy each plugin
                $copiedCount = 0
                foreach ($plugin in $builtPlugins) {
                    Write-Host "  Copying: $plugin" -ForegroundColor Gray
                    $destPath = Join-Path -Path $env:GST_PLUGIN_PATH -ChildPath (Split-Path -Leaf $plugin)
                    Write-Host "  To: $destPath" -ForegroundColor Gray
                    
                    # Verify source exists
                    if (-not (Test-Path $plugin)) {
                        Write-Host "  ✗ Source file not found: $plugin" -ForegroundColor Red
                        continue
                    }
                    
                    try {
                        Copy-Item -Path $plugin -Destination $destPath -Force -ErrorAction Stop
                        Write-Host "  ✓ Copied: $(Split-Path -Leaf $plugin)" -ForegroundColor Green
                        $copiedCount++
                    } catch {
                        Write-Host "  ✗ Failed to copy $(Split-Path -Leaf $plugin): $_" -ForegroundColor Red
                    }
                    Write-Host ""
                }

                if ($copiedCount -eq $builtPlugins.Count) {
                    Write-Host "Successfully copied $copiedCount plugin(s) to GST_PLUGIN_PATH" -ForegroundColor Green
                } elseif ($copiedCount -gt 0) {
                    Write-Host "Copied $copiedCount of $($builtPlugins.Count) plugin(s)" -ForegroundColor Yellow
                } else {
                    Write-Host "Failed to copy any plugins!" -ForegroundColor Red
                }
            }
        } else {
            Write-Host "GST_PLUGIN_PATH environment variable is not set" -ForegroundColor Yellow
            Write-Host "Skipping automatic copy. Plugins remain in build directory." -ForegroundColor Yellow
            Write-Host ""
            Write-Host "To set GST_PLUGIN_PATH:" -ForegroundColor Yellow
            Write-Host "  `$env:GST_PLUGIN_PATH = 'C:\path\to\plugins'" -ForegroundColor White
            Write-Host ""
            Write-Host "Or manually copy plugins to your GStreamer plugins directory:" -ForegroundColor Yellow
            Write-Host "  $GStreamerRoot\lib\gstreamer-1.0\" -ForegroundColor White
        }
    } else {
        Write-Host "Skipping copy to GST_PLUGIN_PATH (-NoCopy specified)" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Next Steps" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    if ($BuildType -eq 'IDSuEyeOnly') {
        Write-Host "Verify installation with:" -ForegroundColor Yellow
        Write-Host "  gst-inspect-1.0 idsueyesrc" -ForegroundColor White
        Write-Host ""
        Write-Host "Example pipeline:" -ForegroundColor Yellow
        Write-Host "  gst-launch-1.0 idsueyesrc ! autovideosink" -ForegroundColor White
    } else {
        Write-Host "Verify installation with:" -ForegroundColor Yellow
        Write-Host "  gst-inspect-1.0 idsueyesrc" -ForegroundColor White
        Write-Host "  gst-inspect-1.0 rollingsum" -ForegroundColor White
        Write-Host "  gst-inspect-1.0 intervalometer" -ForegroundColor White
        Write-Host "  gst-inspect-1.0 linescan" -ForegroundColor White
        Write-Host ""
        Write-Host "Example pipelines:" -ForegroundColor Yellow
        Write-Host "  # Rolling sum detection:" -ForegroundColor Gray
        Write-Host "  gst-launch-1.0 idsueyesrc config-file=config.ini ! rollingsum window-size=1000 column-index=1 threshold=0.5 ! autovideosink" -ForegroundColor White
        Write-Host ""
        Write-Host "  # Auto-exposure time-lapse:" -ForegroundColor Gray
        Write-Host "  gst-launch-1.0 idsueyesrc name=cam ! intervalometer enabled=true camera-element=cam exposure-min=0.85 exposure-max=1.24 gain-min=0 gain-max=52 ! autovideosink" -ForegroundColor White
        Write-Host ""
        Write-Host "  # Line scan camera (horizontal):" -ForegroundColor Gray
        Write-Host "  gst-launch-1.0 idsueyesrc ! linescan direction=horizontal line-index=100 output-size=800 ! videoconvert ! autovideosink" -ForegroundColor White
    }
    Write-Host ""

} catch {
    Pop-Location
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Build script failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    exit 1
}