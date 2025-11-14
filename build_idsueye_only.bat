@echo off
REM Script to build only IDS uEye plugin

echo ========================================
echo Building IDS uEye Plugin Only
echo ========================================
echo.

REM Set default GStreamer path (can be overridden by environment variable or command line)
set DEFAULT_GSTREAMER_ROOT=C:\bin\gstreamer\1.0\msvc_x86_64

REM Allow override via command line parameter
if not "%~1"=="" (
    set GSTREAMER_ROOT=%~1
    echo Using GStreamer from command line: %GSTREAMER_ROOT%
) else if defined GSTREAMER_ROOT (
    echo Using GStreamer from environment: %GSTREAMER_ROOT%
) else (
    set GSTREAMER_ROOT=%DEFAULT_GSTREAMER_ROOT%
    echo Using default GStreamer location: %GSTREAMER_ROOT%
)

REM Verify GStreamer directory exists
if not exist "%GSTREAMER_ROOT%" (
    echo ERROR: GStreamer directory does not exist: %GSTREAMER_ROOT%
    echo.
    echo Please provide correct GStreamer path:
    echo   build_idsueye_only.bat "C:\path\to\gstreamer"
    echo.
    exit /b 1
)

echo.

REM Create build directory
if not exist build_idsueye (
    mkdir build_idsueye
    echo Created build directory: build_idsueye
)

REM Copy standalone CMakeLists to build directory for configuration
copy /Y CMakeLists_idsueye_only.txt build_idsueye\CMakeLists.txt >nul
echo Using standalone IDS uEye CMakeLists configuration
echo.

cd build_idsueye

REM Configure CMake
echo Configuring CMake...
echo.
cmake . -G "Visual Studio 16 2019" -A x64 ^
    -DGSTREAMER_ROOT="%GSTREAMER_ROOT%" ^
    -DCMAKE_PREFIX_PATH="%GSTREAMER_ROOT%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo CMake configuration failed!
    echo ========================================
    echo.
    echo Common issues:
    echo 1. GStreamer not properly installed at: %GSTREAMER_ROOT%
    echo 2. IDS uEye SDK not found (default: C:\Program Files\IDS\uEye\Develop)
    echo 3. Missing GStreamer development files
    echo.
    echo To specify custom IDS uEye SDK location:
    echo   set IDSUEYE_DIR=C:\path\to\ueye\sdk
    echo   build_idsueye_only.bat
    echo.
    cd ..
    exit /b 1
)

REM Build the plugin
echo.
echo Building gstidsueye plugin...
echo.
cmake --build . --config Release

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo Build failed!
    echo ========================================
    cd ..
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo ========================================
echo.
echo Plugin location: build_idsueye\Release\libgstidsueye.dll
echo.
echo To install to GStreamer plugins directory, run:
echo   cmake --build build_idsueye --config Release --target install
echo.

cd ..