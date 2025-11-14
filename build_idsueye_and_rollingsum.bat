@echo off
REM Script to build IDS uEye and Rolling Sum plugins

echo ========================================
echo Building IDS uEye and Rolling Sum Plugins
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
    echo   build_idsueye_and_rollingsum.bat "C:\path\to\gstreamer"
    echo.
    exit /b 1
)

echo.

REM Create build directory
if not exist build (
    mkdir build
    echo Created build directory: build
) else (
    echo Using existing build directory: build
)

echo.

cd build

REM Configure CMake
echo Configuring CMake...
echo.
cmake .. -G "Visual Studio 16 2019" -A x64 ^
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
    echo   build_idsueye_and_rollingsum.bat
    echo.
    cd ..
    exit /b 1
)

REM Build the plugins
echo.
echo Building plugins...
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

REM Install the plugins
echo.
echo Installing plugins to GStreamer directory...
echo.
cmake --build . --config Release --target install

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo Installation failed!
    echo ========================================
    echo.
    echo You may need administrator privileges to install.
    echo Try running this script as administrator.
    echo.
    cd ..
    exit /b 1
)

echo.
echo ========================================
echo Build and installation completed successfully!
echo ========================================
echo.
echo Installed plugins:
echo   - libgstidsueye.dll (IDS uEye camera source)
echo   - libgstrollingsum.dll (Rolling sum filter)
echo.
echo Installation location: %GSTREAMER_ROOT%\lib\gstreamer-1.0\
echo.
echo Verify installation with:
echo   gst-inspect-1.0 idsueyesrc
echo   gst-inspect-1.0 rollingsum
echo.
echo Example pipeline:
echo   gst-launch-1.0 idsueyesrc config-file=config.ini ! rollingsum window-size=1000 column-index=1 threshold=0.5 ! autovideosink
echo.

cd ..