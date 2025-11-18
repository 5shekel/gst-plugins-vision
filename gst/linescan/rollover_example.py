#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
#
# Simple Rollover Example - Linescan Buffer Capture Demo
#
# This is a minimal example showing how to capture linescan images using
# the rollover signal with a videotestsrc. Files are saved via Python/PIL
# in the rollover callback, demonstrating the correct approach.
#
# Prerequisites:
#   1. Build the GStreamer plugins: .\build.ps1
#   2. Ensure GST_PLUGIN_PATH includes the build directory
#
# Usage:
#   uv run .\gst\linescan\rollover_example.py              # Run with defaults
#   python gst/linescan/rollover_example.py                # Alternative without uv
#
# Features:
#   - Uses videotestsrc (ball pattern) for testing
#   - Saves images on rollover signal (not every frame)
#   - Live preview window showing linescan accumulation
#   - JPEG output to current directory
#
# Pipeline:
#   videotestsrc -> linescan -> videoconvert -> autovideosink
#                       ↓
#               (rollover signal)
#                       ↓
#           Python callback saves file
#
# See launch_with_signal.py for a full-featured version with camera support.

import os
import sys

# Check for required environment variable
gst_root = os.environ.get("GSTREAMER_1_0_ROOT_MSVC_X86_64")
if not gst_root:
    print("ERROR: GSTREAMER_1_0_ROOT_MSVC_X86_64 environment variable is not set")
    print("Expected: C:\\bin\\gstreamer\\1.0\\msvc_x86_64\\")
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
import numpy as np
from PIL import Image

frame_counter = 0

def on_rollover(linescan, buffer):
    """Callback when rollover signal is emitted - save buffer to JPEG"""
    global frame_counter
    
    filename = f"linescan_frame_{frame_counter:04d}.jpeg"
    
    # Map the buffer to get image data
    success, mapinfo = buffer.map(Gst.MapFlags.READ)
    if not success:
        print(f"[ERROR] Failed to map buffer for frame {frame_counter}")
        return
    
    try:
        # Get caps to determine image dimensions
        caps = linescan.get_static_pad("src").get_current_caps()
        structure = caps.get_structure(0)
        width = structure.get_value('width')
        height = structure.get_value('height')
        format_str = structure.get_value('format')
        
        # Convert buffer data to numpy array
        data = np.frombuffer(mapinfo.data, dtype=np.uint8)
        
        # Handle different formats
        if format_str in ['RGB', 'BGR']:
            channels = 3
            data = data.reshape((height, width, channels))
            if format_str == 'BGR':
                data = data[:, :, ::-1]  # Convert BGR to RGB
        elif format_str == 'GRAY8':
            channels = 1
            data = data.reshape((height, width))
        else:
            data = data.reshape((height, width, -1))
        
        # Create PIL Image and save
        if channels == 1:
            img = Image.fromarray(data, mode='L')
        else:
            img = Image.fromarray(data, mode='RGB')
        
        img.save(filename, 'JPEG', quality=95)
        print(f"[ROLLOVER] Frame {frame_counter} saved to: {filename}")
        
    except Exception as e:
        print(f"[ERROR] Failed to save frame {frame_counter}: {e}")
    finally:
        buffer.unmap(mapinfo)
        frame_counter += 1

def main():
    Gst.init(None)
    
    # Create pipeline - simplified without file branch
    # videotestsrc -> linescan -> videoconvert -> autovideosink
    #                     ↓
    #            (rollover callback saves files)
    
    pipeline = Gst.Pipeline.new("rollover-pipeline")
    
    # Create elements
    source = Gst.ElementFactory.make("videotestsrc", "source")
    linescan = Gst.ElementFactory.make("linescan", "linescan")
    convert = Gst.ElementFactory.make("videoconvert", "convert")
    videosink = Gst.ElementFactory.make("autovideosink", "videosink")
    
    if not all([pipeline, source, linescan, convert, videosink]):
        print("ERROR: Not all elements could be created")
        print("Make sure linescan plugin is built and in GST_PLUGIN_PATH")
        return -1
    
    # Configure elements
    source.set_property("pattern", 18)  # ball pattern
    linescan.set_property("direction", 0)  # horizontal
    linescan.set_property("line-index", 100)
    linescan.set_property("output-size", 400)
    
    # Connect to rollover signal - files saved in callback
    linescan.connect("rollover", on_rollover)
    
    # Add elements to pipeline
    pipeline.add(source)
    pipeline.add(linescan)
    pipeline.add(convert)
    pipeline.add(videosink)
    
    # Link elements - simple chain
    if not source.link(linescan):
        print("ERROR: Could not link source to linescan")
        return -1
    if not linescan.link(convert):
        print("ERROR: Could not link linescan to convert")
        return -1
    if not convert.link(videosink):
        print("ERROR: Could not link convert to videosink")
        return -1
    
    # Start playing
    pipeline.set_state(Gst.State.PLAYING)
    
    # Create main loop
    loop = GLib.MainLoop()
    
    # Handle bus messages
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    
    def on_message(bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("\nEnd-of-stream")
            loop.quit()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"\nError: {err}, {debug}")
            loop.quit()
    
    bus.connect("message", on_message)
    
    print("Pipeline running. Files saved on rollover to current directory.")
    print("Press Ctrl+C to stop.\n")
    try:
        loop.run()
    except KeyboardInterrupt:
        print("\nStopping...")
    
    # Cleanup
    pipeline.set_state(Gst.State.NULL)
    print(f"Captured {frame_counter} rollover frames")
    return 0

if __name__ == "__main__":
    sys.exit(main())