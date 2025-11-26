#!/bin/bash
set -e

# GStreamer Vision Plugins Build Script for Linux
# 
# Usage Examples:
#   ./build.sh
#   ./build.sh --build-type all --config release
#   ./build.sh --build-type idsueye-only --config debug --no-install
#   ./build.sh --help

# Default values
BUILD_TYPE="all"
CONFIG="release"
NO_INSTALL=""
BUILD_DIR=""
GSTREAMER_ROOT=""
INSTALL_PREFIX=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${CYAN}========================================"
    echo "GStreamer Vision Plugins Build Script"
    echo "Linux/ARM64 Compatible Version"
    echo -e "========================================${NC}"
    echo ""
}

print_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --build-type TYPE     Build type: 'all' (default) or 'idsueye-only'"
    echo "  --config CONFIG       Build config: 'release' (default) or 'debug'"
    echo "  --no-install          Skip installing plugins to system directories"
    echo "  --build-dir DIR       Custom build directory (default: build)"
    echo "  --install-prefix DIR  Custom install prefix"
    echo "  --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./build.sh                                    # Build all plugins in release mode"
    echo "  ./build.sh --build-type idsueye-only         # Build only IDS uEye plugin"
    echo "  ./build.sh --config debug --no-install       # Debug build without system install"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build-type)
            BUILD_TYPE="$2"
            shift 2
            ;;
        --config)
            CONFIG="$2"
            shift 2
            ;;
        --no-install)
            NO_INSTALL="yes"
            shift
            ;;
        --build-dir)
            BUILD_DIR="$2"
            shift 2
            ;;
        --install-prefix)
            INSTALL_PREFIX="$2"
            shift 2
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}" >&2
            print_help
            exit 1
            ;;
    esac
done

print_banner

# Validate build type
case $BUILD_TYPE in
    "all"|"idsueye-only")
        ;;
    *)
        echo -e "${RED}Error: Invalid build type '$BUILD_TYPE'. Use 'all' or 'idsueye-only'${NC}" >&2
        exit 1
        ;;
esac

# Validate config
case $CONFIG in
    "release"|"debug")
        ;;
    *)
        echo -e "${RED}Error: Invalid config '$CONFIG'. Use 'release' or 'debug'${NC}" >&2
        exit 1
        ;;
esac

# Set build directory
if [ -z "$BUILD_DIR" ]; then
    if [ "$BUILD_TYPE" = "idsueye-only" ]; then
        BUILD_DIR="build_idsueye"
    else
        BUILD_DIR="build"
    fi
fi

# Detect architecture
ARCH=$(uname -m)
echo -e "${CYAN}Build Configuration:${NC}"
echo -e "  Build Type: ${WHITE}$BUILD_TYPE${NC}"
echo -e "  Config: ${WHITE}$(echo $CONFIG | tr '[:lower:]' '[:upper:]')${NC}"
echo -e "  Architecture: ${WHITE}$ARCH${NC}"
echo -e "  Build Directory: ${WHITE}$BUILD_DIR${NC}"
echo ""

# Check dependencies
echo -e "${CYAN}Checking dependencies...${NC}"

# Check if cmake is available
if ! command -v cmake >/dev/null 2>&1; then
    echo -e "${RED}Error: cmake not found. Please install cmake.${NC}" >&2
    echo "  sudo apt-get install cmake" >&2
    exit 1
fi

# Check if make is available
if ! command -v make >/dev/null 2>&1; then
    echo -e "${RED}Error: make not found. Please install build-essential.${NC}" >&2
    echo "  sudo apt-get install build-essential" >&2
    exit 1
fi

# Check GStreamer development packages
if ! pkg-config --exists gstreamer-1.0; then
    echo -e "${RED}Error: GStreamer development packages not found.${NC}" >&2
    echo "Please install GStreamer development files:" >&2
    echo "  sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev" >&2
    exit 1
fi

# Check for IDS uEye SDK if building IDS components
if [ "$BUILD_TYPE" = "all" ] || [ "$BUILD_TYPE" = "idsueye-only" ]; then
    if [ ! -f "/opt/ids/ueye/lib/$(uname -m)-linux-gnu/libueye_api.so" ] && [ ! -f "/usr/lib/$(uname -m)-linux-gnu/libueye_api.so" ]; then
        echo -e "${YELLOW}Warning: IDS uEye SDK not found. IDS uEye plugin will be skipped.${NC}"
        echo "Install IDS uEye SDK for camera support."
    else
        echo -e "${GREEN}✓ IDS uEye SDK found${NC}"
    fi
fi

echo -e "${GREEN}✓ All required dependencies found${NC}"
echo ""

# Create build directory
if [ ! -d "$BUILD_DIR" ]; then
    mkdir -p "$BUILD_DIR"
    echo -e "${GREEN}Created build directory: $BUILD_DIR${NC}"
else
    echo -e "${GREEN}Using existing build directory: $BUILD_DIR${NC}"
fi

echo ""

# Configure CMake
echo -e "${CYAN}Configuring CMake...${NC}"
echo ""

cd "$BUILD_DIR"

# Prepare CMake arguments
CMAKE_ARGS="../"
if [ "$CONFIG" = "debug" ]; then
    CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_BUILD_TYPE=Debug"
else
    CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_BUILD_TYPE=Release"
fi

# Add custom install prefix if specified
if [ -n "$INSTALL_PREFIX" ]; then
    CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_INSTALL_PREFIX=$INSTALL_PREFIX"
fi

# Configure and build
if ! cmake $CMAKE_ARGS; then
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}CMake configuration failed!${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Common issues:${NC}"
    echo -e "${YELLOW}1. Missing GStreamer development packages${NC}"
    echo -e "${YELLOW}2. IDS uEye SDK not found (install from IDS website)${NC}"
    echo -e "${YELLOW}3. Missing build dependencies (cmake, build-essential)${NC}"
    echo ""
    echo -e "${YELLOW}Install dependencies:${NC}"
    echo -e "${WHITE}  sudo apt-get update${NC}"
    echo -e "${WHITE}  sudo apt-get install cmake build-essential${NC}"
    echo -e "${WHITE}  sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev${NC}"
    echo ""
    exit 1
fi

# Build the plugins
echo ""
echo -e "${CYAN}Building plugins...${NC}"
echo ""

CPU_CORES=$(nproc)
if ! make -j$CPU_CORES; then
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Build failed!${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi

# Collect built plugin information
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Build completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Find built plugins
BUILT_PLUGINS=$(find . -name "libgst*.so" -type f)
PLUGIN_COUNT=$(echo "$BUILT_PLUGINS" | grep -c "libgst" || true)

echo -e "${CYAN}Built plugins ($PLUGIN_COUNT total):${NC}"
for plugin in $BUILT_PLUGINS; do
    plugin_name=$(basename "$plugin")
    echo -e "  - ${WHITE}$plugin_name${NC} (${plugin})"
done
echo ""

# Install plugins if requested
if [ "$NO_INSTALL" != "yes" ]; then
    echo -e "${CYAN}Installing plugins...${NC}"
    
    # Check if we have permission to install
    if [ "$EUID" -eq 0 ]; then
        # Running as root
        if make install; then
            echo -e "${GREEN}✓ Successfully installed plugins to system directories${NC}"
        else
            echo -e "${RED}✗ Installation failed${NC}"
            exit 1
        fi
    else
        # Not running as root, ask for sudo
        echo -e "${YELLOW}Installing plugins requires root privileges...${NC}"
        if sudo make install; then
            echo -e "${GREEN}✓ Successfully installed plugins to system directories${NC}"
        else
            echo -e "${RED}✗ Installation failed${NC}"
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}Skipping installation (--no-install specified)${NC}"
    echo -e "${YELLOW}Plugins remain in build directory${NC}"
fi

cd ..

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Next Steps${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

echo -e "${YELLOW}Verify installation:${NC}"
echo -e "${WHITE}  gst-inspect-1.0 idsueyesrc${NC}"
echo -e "${WHITE}  gst-inspect-1.0 linescan${NC}"
echo -e "${WHITE}  gst-inspect-1.0 intervalometer${NC}"
echo ""

echo -e "${YELLOW}Example usage:${NC}"
echo -e "${WHITE}  # Record from IDS camera to MP4:${NC}"
echo -e "${WHITE}  gst-launch-1.0 idsueyesrc device-id=1 num-buffers=300 ! videoconvert ! x264enc ! mp4mux ! filesink location=test.mp4${NC}"
echo ""
echo -e "${WHITE}  # Stream to network:${NC}"
echo -e "${WHITE}  gst-launch-1.0 idsueyesrc device-id=1 ! queue ! videoconvert ! x264enc tune=zerolatency ! rtph264pay ! udpsink host=TARGET_HOST port=5000${NC}"
echo ""
echo -e "${WHITE}  # Line scan operation:${NC}"
echo -e "${WHITE}  gst-launch-1.0 idsueyesrc ! linescan direction=horizontal line-index=100 output-size=800 ! videoconvert ! autovideosink${NC}"
echo ""

if [ "$BUILD_TYPE" = "all" ]; then
    echo -e "${GREEN}✓ All plugins built successfully for $ARCH!${NC}"
else
    echo -e "${GREEN}✓ IDS uEye plugin built successfully for $ARCH!${NC}"
fi