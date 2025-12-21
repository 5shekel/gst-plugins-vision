#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["argcomplete", "numpy", "pillow"]
# ///
#
# Linescan Pipeline with Rollover Signal Capture
#
# This script creates a GStreamer pipeline that captures linescan images from an IDS uEye camera
# and saves frames only when the linescan buffer wraps around (rollover events).
# Features dual output: live preview display and automatic file saving on rollover.
#
# Prerequisites:
#   1. Build the GStreamer plugins first: .\build.ps1
#   2. Ensure GST_PLUGIN_PATH includes the build directory with custom plugins
#   3. The custom linescan plugin must be built and available to GStreamer
#
# Basic Usage:
#   uv run .\gst\linescan\launch_with_signal.py                      # Run with defaults (day mode)
#   uv run .\gst\linescan\launch_with_signal.py --mode night         # Night mode (higher exposure & gain)
#   uv run .\gst\linescan\launch_with_signal.py --debug              # Enable debug output
#   uv run .\gst\linescan\launch_with_signal.py --format png         # Save as PNG
#   uv run .\gst\linescan\launch_with_signal.py --output-dir custom  # Custom output directory
#   uv run .\gst\linescan\launch_with_signal.py --gst-debug          # Enable GStreamer debug (level 3)
#   uv run .\gst\linescan\launch_with_signal.py --help               # Show all options
#   python gst/linescan/launch_with_signal.py                        # Alternative without uv
#
# Features:
#   - Automatic capture on linescan buffer rollover (precise frame control)
#   - Live preview display window (autovideosink)
#   - File output with automatic sequential numbering
#   - IDS uEye camera source with intervalometer integration
#   - Configurable camera settings (exposure, framerate, gain)
#   - Camera rotated 90° clockwise, then vertical linescan with 1900px output size
#   - 3-pixel bottom crop for sensor cleanup
#   - Dual output via tee element (display + file save)
#
# Pipeline Architecture:
#   idsueyesrc -> intervalometer -> videocrop -> videoflip -> queue -> linescan -> videoconvert -> autovideosink
#
#   Note: Files are saved via Python in the rollover signal callback, not through the pipeline
#
# Configuration:
#   - Camera config: ini/roi-night.ini (adjust CONFIG_FILE variable if needed)
#   - Camera modes:
#     * Day mode (default): exposure=0.4ms, gain=0, framerate=200fps
#     * Night mode: exposure=5.25ms, gain=65, framerate=200fps
#   - Device ID: 2 (set in source.set_property)
#   - Linescan output size: 1900 pixels (set in linescan.set_property)
#   - Output directory: results/<date>/<funny-name>/ (auto-created with funny names)
#   - Output format: JPEG (quality 95) or PNG (lossless)
#
# Output Files:
#   - Format: linescan_rollover_####.jpeg (or .png with --format png)
#   - Location: results/<date>/<funny-name>/ by default (e.g., "fuzzy-photon")
#              or custom path with --output-dir
#   - Triggered by: Buffer rollover events
#   - Quality: JPEG=95, PNG=lossless
#   - Sequential numbering: 0000, 0001, 0002, etc.
#   - Example: results/20251118/bouncy-pixel/linescan_rollover_0000.jpeg
#
# Stopping:
#   Press Ctrl+C to stop the pipeline gracefully
#
# Troubleshooting:
#
#
#   Error: "No such element 'linescan'" or "No such element 'idsueyesrc'"
#   - Cause: Custom plugins not found in GST_PLUGIN_PATH
#   - Solution:
#     1. Verify plugins are built in the output directory
#     2. Set GST_PLUGIN_PATH to include the build directory
#     3. Run: gst-inspect-1.0 --print-plugin-auto-install-info to check plugins
#
# Performance Notes:
#   - Files are saved via Python/PIL in the rollover callback (only when buffer wraps)
#   - The display shows the live linescan accumulation
#   - No buffer drops related to encoding since file saving is outside the pipeline
#   - Rollover occurs after accumulating output-size (1900) lines from camera frames
#
# Notes:
#   - Requires GStreamer with custom vision plugins installed (build with .\build.ps1)
#   - Must run from workspace root (c:/dev/gst-plugins-vision) or adjust CONFIG_FILE path
#   - GST_PLUGIN_PATH must include the directory containing built custom plugins
#   - Enable GStreamer debug logging by modifying Gst.debug_set_threshold_for_name() call
#   - Intervalometer provides automatic gain ramping for timelapse scenarios
#   - The rollover signal is defined in gst/linescan/gstlinescan.c:178-182
#   - To check if plugin is loaded: GST_DEBUG=2 gst-inspect-1.0 linescan
#   - Uses multifilesink for automatic sequential file numbering
#

import os
import sys

# Check for required environment variable
gst_root = os.environ.get("GSTREAMER_1_0_ROOT_MSVC_X86_64")
if not gst_root:
    print("ERROR: GSTREAMER_1_0_ROOT_MSVC_X86_64 environment variable is not set")
    print("Expected: C:\\bin\\gstreamer\\1.0\\msvc_x86_64\\")
    print("Please run: . .\\scripts\\setup_gstreamer_env.ps1")
    sys.exit(1)
else:
    # Remove trailing backslash if present
    gst_root = gst_root.rstrip("\\")

    gst_site_packages = os.path.join(gst_root, "lib", "site-packages")
    sys.path.insert(0, gst_site_packages)

    # Add GI typelibs
    os.environ["GI_TYPELIB_PATH"] = os.path.join(gst_root, "lib", "girepository-1.0")

    # Add GStreamer DLL bin directory
    os.environ["PATH"] = os.path.join(gst_root, "bin") + ";" + os.environ["PATH"]


import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import argparse
from datetime import datetime
import random
import numpy as np
from PIL import Image

frame_counter = 0
output_dir = None  # Will be set in main()

# Funny two-word name lists
ADJECTIVES = [
    "happy", "sleepy", "grumpy", "bouncy", "fuzzy", "dizzy", "sparkly", "wobbly",
    "quirky", "snappy", "zippy", "jolly", "fluffy", "bumpy", "zesty", "peppy"
]
NOUNS = [
    "pixel", "photon", "widget", "gadget", "scanner", "buffer", "tensor", "matrix",
    "vector", "sensor", "filter", "shutter", "aperture", "capture", "snapshot", "frame"
]

# Config file path - adjust if running from different directory
# From workspace root: "ini/roi-night.ini"
# From gst/linescan: "../../ini/roi-night.ini"
CONFIG_FILE = "ini/roi-night.ini"

def on_rollover(linescan, buffer):
    """Called when linescan buffer wraps around - save the buffer to file"""
    global frame_counter
    
    # Create output directory if needed
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Get format from args if available, otherwise default to jpeg
    import __main__
    file_format = getattr(__main__, 'output_format', 'jpeg')
    
    # Generate filename
    filename = os.path.join(output_dir, f"linescan_rollover_{frame_counter:04d}.{file_format}")
    
    # Map the buffer to get image data
    success, mapinfo = buffer.map(Gst.MapFlags.READ)
    if not success:
        print(f"[ROLLOVER ERROR] Failed to map buffer for frame {frame_counter}")
        return
    
    try:
        # Get caps to determine image dimensions
        caps = buffer.get_caps() if hasattr(buffer, 'get_caps') else linescan.get_static_pad("src").get_current_caps()
        structure = caps.get_structure(0)
        width = structure.get_value('width')
        height = structure.get_value('height')
        format_str = structure.get_value('format')
        
        # Convert buffer data to numpy array
        data = np.frombuffer(mapinfo.data, dtype=np.uint8)
        
        # Determine number of channels based on format
        if format_str in ['RGB', 'BGR']:
            channels = 3
            data = data.reshape((height, width, channels))
            if format_str == 'BGR':
                # Convert BGR to RGB for PIL
                data = data[:, :, ::-1]
        elif format_str in ['GRAY8']:
            channels = 1
            data = data.reshape((height, width))
        else:
            print(f"[ROL LOVER WARNING] Unsupported format {format_str}, saving as-is")
            data = data.reshape((height, width, -1))
        
        # Create PIL Image and save
        if channels == 1:
            img = Image.fromarray(data, mode='L')
        else:
            img = Image.fromarray(data, mode='RGB')
        
        if file_format == 'png':
            img.save(filename, 'PNG')
        else:
            img.save(filename, 'JPEG', quality=95)
        
        # print(f"[ROLLOVER] Frame {frame_counter} saved to: {filename}")
        
    except Exception as e:
        print(f"[ROLLOVER ERROR] Failed to save frame {frame_counter}: {e}")
    finally:
        buffer.unmap(mapinfo)
        frame_counter += 1

def on_message(bus, message):
    """Handle pipeline messages"""
    t = message.type
    if t == Gst.MessageType.EOS:
        print("\nEnd-of-stream")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"\nError: {err}")
        print(f"Debug: {debug}")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        warn, debug = message.parse_warning()
        print(f"\nWarning: {warn}")

def main():
    global loop, output_format
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Linescan pipeline with rollover signal capture',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                                    # Run with defaults (day mode)
  %(prog)s --mode night                       # Night mode (higher exposure & gain)
  %(prog)s --debug                            # Enable debug output
  %(prog)s --format png                       # Save as PNG instead of JPEG
  %(prog)s --output-dir my_captures           # Custom output directory
  %(prog)s --gst-debug                        # Enable GStreamer debug
  %(prog)s --gst-debug-level 4                # Set custom GStreamer debug level
        '''
    )
    
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug output from this script')
    parser.add_argument('--gst-debug', action='store_true',
                        help='Enable GStreamer debug output (level 3)')
    parser.add_argument('--gst-debug-level', type=int, metavar='LEVEL',
                        help='Set GStreamer debug level (0-9, default: 3 if --gst-debug)')
    parser.add_argument('--format', '-f', choices=['jpeg', 'png'], default='jpeg',
                        help='Output image format (default: jpeg)')
    parser.add_argument('--output-dir', '-o', metavar='DIR',
                        help='Output directory (default: results/<date>/<funny-name>)')
    parser.add_argument('--mode', '-m', choices=['day', 'night'], default='day',
                        help='Camera mode: day (0.2ms exposure, 0 gain) or night (5.25ms exposure, 65 gain) (default: day)')
    
    args = parser.parse_args()
    
    # Make format globally available for rollover callback
    output_format = args.format
    
    # Set up output directory
    global output_dir
    if args.output_dir:
        output_dir = args.output_dir
    else:
        # Create default: results/<date>/<funny-name>
        date_str = datetime.now().strftime("%Y%m%d")
        results_base = os.path.join("results", date_str)
        
        # Generate funny name: adjective-noun
        funny_name = f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}"
        output_dir = os.path.join(results_base, funny_name)
        
        # If name exists, add number suffix
        if os.path.exists(output_dir):
            seq = 1
            while True:
                output_dir = os.path.join(results_base, f"{funny_name}-{seq}")
                if not os.path.exists(output_dir):
                    break
                seq += 1
        
        if args.debug:
            print(f"Using auto-generated output directory: {output_dir}")
    
    # Set GStreamer debug level
    if args.gst_debug_level is not None:
        debug_level = args.gst_debug_level
    elif args.gst_debug:
        debug_level = 3
    else:
        debug_level = None
    
    if debug_level is not None:
        os.environ['GST_DEBUG'] = str(debug_level)
        if args.debug:
            print(f"Setting GST_DEBUG={debug_level}")
    
    Gst.init(None)
    
    if args.debug:
        print("Initializing GStreamer pipeline...")
        print(f"GStreamer version: {Gst.version_string()}")
    
    # Create output directory early
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        if args.debug:
            print(f"Created output directory: {output_dir}")
    
    # Create pipeline with tee to split output
    pipeline = Gst.Pipeline.new("linescan-capture")
    
    # Source chain
    source = Gst.ElementFactory.make("idsueyesrc", "source")
    intervalometer = Gst.ElementFactory.make("intervalometer", "intervalometer")
    videocrop = Gst.ElementFactory.make("videocrop", "crop")
    videoflip = Gst.ElementFactory.make("videoflip", "flip")
    queue1 = Gst.ElementFactory.make("queue", "queue1")
    linescan = Gst.ElementFactory.make("linescan", "linescan")
    
    # Display output
    videoconvert = Gst.ElementFactory.make("videoconvert", "convert")
    videosink = Gst.ElementFactory.make("autovideosink", "videosink")
    
    # Check which elements failed to create
    elements = {
        'pipeline': pipeline,
        'idsueyesrc': source,
        'intervalometer': intervalometer,
        'videocrop': videocrop,
        'queue1': queue1,
        'linescan': linescan,
        'videoflip': videoflip,
        'videoconvert': videoconvert,
        'videosink': videosink
    }
    
    failed_elements = [name for name, elem in elements.items() if elem is None]
    
    if failed_elements:
        print("ERROR: Failed to create the following elements:")
        for name in failed_elements:
            print(f"  - {name}")
        print("\nTroubleshooting:")
        if 'linescan' in failed_elements or 'idsueyesrc' in failed_elements:
            print("  Custom plugins not found. Make sure:")
            print("  1. Run .\build.ps1 to build the plugins")
            print("  2. Set GST_PLUGIN_PATH to include the build directory")
            print("  3. Verify with: gst-inspect-1.0 linescan")
        if 'intervalometer' in failed_elements:
            print("  Intervalometer plugin not found (custom plugin)")
        return -1
    
    if args.debug:
        print("All elements created successfully")
    
    # Configure source
    if args.debug:
        print(f"Configuring camera with config file: {CONFIG_FILE}")
    
    if not os.path.exists(CONFIG_FILE):
        print(f"WARNING: Config file not found: {CONFIG_FILE}")
        print("Continuing without config file...")
    else:
        source.set_property("config-file", CONFIG_FILE)
    
    # Set camera parameters based on mode
    if args.mode == 'day':
        exposure = 0.02
        gain = 0
    else:  # night
        exposure = 5.25
        gain = 65
    
    framerate = 200  # Same for both modes
    device_id = 1
    
    source.set_property("exposure", exposure)
    source.set_property("framerate", framerate)
    source.set_property("gain", gain)
    source.set_property("device-id", device_id)
    
    if args.debug:
        print(f"Camera mode: {args.mode}")
        print(f"Camera settings: exposure={exposure}ms, framerate={framerate}fps, gain={gain}, device-id={device_id}")
    
    # Configure intervalometer
    intervalometer.set_property("enabled", True)
    intervalometer.set_property("camera-element", "source")
    intervalometer.set_property("ramp-rate", "slow")
    intervalometer.set_property("update-interval", 1000)
    intervalometer.set_property("brightness-deadband", 10.0)
    intervalometer.set_property("gain-max", 82)
    intervalometer.set_property("target-brightness", 80.0)
    intervalometer.set_property("log-file", "timelapse.csv")
    
    # Configure videocrop
    videocrop.set_property("bottom", 3)
    
    # Configure videoflip to rotate 90 degrees clockwise (method=1 is clockwise)
    # Available methods: 0:none, 1:clockwise, 2:rotate-180, 3:counterclockwise, 
    # 4:horizontal-flip, 5:vertical-flip, 6:upper-left-diagonal, 7:upper-right-diagonal, 8:automatic
    videoflip.set_property("method", 1)
    
    # Configure linescan
    linescan.set_property("direction", 1)  # vertical
    linescan.set_property("output-size", 1900)
    
    if args.debug:
        print(f"Camera rotated 90° clockwise, then vertical linescan with output-size=1900")
    
    # Connect rollover signal - files are saved in the callback
    linescan.connect("rollover", on_rollover)
    
    # Add all elements to pipeline
    pipeline.add(source)
    pipeline.add(intervalometer)
    pipeline.add(videocrop)
    pipeline.add(videoflip)
    pipeline.add(queue1)
    pipeline.add(linescan)
    pipeline.add(videoconvert)
    pipeline.add(videosink)
    
    # Link elements - simple chain now
    if not source.link(intervalometer):
        print("ERROR: Could not link source to intervalometer")
        return -1
    if not intervalometer.link(videocrop):
        print("ERROR: Could not link intervalometer to videocrop")
        return -1
    if not videocrop.link(videoflip):
        print("ERROR: Could not link videocrop to videoflip")
        return -1
    if not videoflip.link(queue1):
        print("ERROR: Could not link videoflip to queue1")
        return -1
    if not queue1.link(linescan):
        print("ERROR: Could not link queue1 to linescan")
        return -1
    if not linescan.link(videoconvert):
        print("ERROR: Could not link linescan to videoconvert")
        return -1
    if not videoconvert.link(videosink):
        print("ERROR: Could not link videoconvert to videosink")
        return -1
    
    # Enable debug for linescan if requested
    if args.debug or args.gst_debug:
        Gst.debug_set_threshold_for_name("linescan", Gst.DebugLevel.LOG)
        if args.debug:
            print("Enabled LOG level debugging for linescan element")
    
    # Set up message handling before starting
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)
    
    if args.debug:
        print("\nStarting pipeline...")
        print(f"Pipeline state: {pipeline.get_state(0)[1].value_nick}")
    
    # Start pipeline
    print(f"Frames will be saved to: {output_dir}/")
    print("Press Ctrl+C to stop\n")
    
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("\nERROR: Unable to set pipeline to playing state")
        print("\nPossible causes:")
        print("  1. Camera not connected or unavailable (device-id=2)")
        print("  2. Config file issue: check if ini/roi-night.ini exists and is valid")
        print("  3. Element compatibility issues")
        print("\nTo debug further:")
        print("  - Run with --debug flag for more information")
        print("  - Run with --gst-debug to see GStreamer messages")
        print("  - Check camera with: gst-launch-1.0 idsueyesrc ! fakesink")
        print("  - Verify config file exists and camera is connected")
        
        # Try to get more error info from bus
        bus = pipeline.get_bus()
        msg = bus.timed_pop_filtered(Gst.SECOND, Gst.MessageType.ERROR | Gst.MessageType.WARNING)
        if msg:
            if msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"\nGStreamer Error: {err}")
                if debug:
                    print(f"Debug info: {debug}")
        
        return -1
    
    if args.debug:
        # Wait for state change to complete
        state_ret, state, pending = pipeline.get_state(Gst.CLOCK_TIME_NONE)
        print(f"Pipeline state change: {state_ret.value_nick}")
        print(f"Current state: {state.value_nick}")
        if pending != Gst.State.VOID_PENDING:
            print(f"Pending state: {pending.value_nick}")
    
    # Run main loop
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n\nStopping pipeline...")
    
    # Cleanup
    pipeline.set_state(Gst.State.NULL)
    print(f"\nCaptured {frame_counter} rollover frames")
    return 0

if __name__ == "__main__":
    sys.exit(main())