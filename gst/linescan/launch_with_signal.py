#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["Pillow"]
# ///
#
# Linescan capture -> JPEG on rollover
#
# Builds a GStreamer pipeline from an IDS uEye line-scan camera:
#
#   idsueyesrc -> intervalometer -> videoflip -> queue -> linescan -> queue -> videoconvert -> fakesink
#
# linescan accumulates one column per camera frame into an `output-size`-wide
# image. On every buffer rollover the "rollover" signal fires and on_rollover()
# writes the accumulated image out as a JPEG.
#
# Geometry (ini/roi-dusk.ini, ROI 2016 x 20):
#   videoflip method=1/3 (90 CW/CCW, per device-id)  -> 20 x 2016
#   linescan direction=1                             -> <output-size> x 2016   (roll fills left..right)
#
# output-size (the roll width) defaults to whatever makes the raw image match
# --aspect (16:9) given its height: 2016 * 16/9 = 3584. Keep the raw image wide
# and downscale it at view time; pass --output-size N to override.
#
# No videocrop: linescan already selects a single line (line-index, default =
# middle column), so trimming rows off the ROI first is redundant.
#
# Output: results/<date>/<funny-name>/linescan_capture_NNNNNN.jpg
#         (override with --output-dir)
#
# Usage:
#   uv run gst/linescan/launch_with_signal.py
#   uv run gst/linescan/launch_with_signal.py --mode night
#   uv run gst/linescan/launch_with_signal.py --config ini/roi-night.ini
#   uv run gst/linescan/launch_with_signal.py --run-seconds 20 --debug
#   uv run gst/linescan/launch_with_signal.py --gst-debug
#
# Prerequisites:
#   - Build the custom plugins: .\build.ps1  (idsueyesrc, intervalometer, linescan)
#   - Set up the environment: . .\scripts\setup_gstreamer_env.ps1
#   - Run from the workspace root so the --config path resolves.
#
# Stop with Ctrl+C. The rollover signal is defined in gst/linescan/gstlinescan.c.

import os
import sys
import time

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
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GLib, GstVideo
import argparse
import configparser
from datetime import datetime
import random

from PIL import Image


frame_counter = 0
output_dir = None  # Set in main()

# Funny two-word name lists
ADJECTIVES = [
    "happy", "sleepy", "grumpy", "bouncy", "fuzzy", "dizzy", "sparkly", "wobbly",
    "quirky", "snappy", "zippy", "jolly", "fluffy", "bumpy", "zesty", "peppy"
]
NOUNS = [
    "pixel", "photon", "widget", "gadget", "scanner", "buffer", "tensor", "matrix",
    "vector", "sensor", "filter", "shutter", "aperture", "capture", "snapshot", "frame"
]

# Camera config, relative to the workspace root.
DEFAULT_CONFIG = "ini/roi-dusk.ini"

# Preferred aspect ratio of the raw linescan image. The roll width (output-size)
# is derived from it so the output can be downscaled at view time without
# distortion. Keep the raw image wide; scale it down in the viewer.
DEFAULT_ASPECT = "16:9"


def _roi_line_length(config_path):
    """Length in px of the line linescan extracts, i.e. the raw output height.

    The IDS ini stores the sensor ROI as [Image size] Width x Height. The
    pipeline rotates the frame 90 degrees (videoflip method=1/3) before
    linescan, so the ROI *Width* becomes the linescan output height.
    Returns None if the ini can't be read.
    """
    try:
        cp = configparser.ConfigParser()
        # IDS ini files are written with a UTF-8 BOM.
        if not cp.read(config_path, encoding="utf-8-sig"):
            return None
        return cp.getint("Image size", "Width")
    except (configparser.Error, ValueError, OSError):
        return None


def _derive_output_size(line_length, aspect):
    """Roll width for the given line length (output height) and 'W:H' aspect."""
    aw, ah = (int(x) for x in aspect.split(":"))
    return round(line_length * aw / ah)


JPEG_QUALITY = 90


def on_rollover(linescan, buffer):
    """Called when the linescan buffer wraps around - write it out as a JPEG."""
    global frame_counter
    caps = linescan.get_static_pad("src").get_current_caps()
    if not caps or caps.is_empty():
        return

    try:
        info = GstVideo.VideoInfo.new_from_caps(caps)
        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            return

        try:
            structure = caps.get_structure(0)
            width = structure.get_value("width")
            height = structure.get_value("height")
            fmt = structure.get_value("format")

            if fmt != "BGR":
                return

            stride = info.stride[0]
            row_bytes = width * 3
            raw = bytearray(row_bytes * height)
            for y in range(height):
                start = y * stride
                raw[y * row_bytes:(y + 1) * row_bytes] = \
                    map_info.data[start:start + row_bytes]

            image = Image.frombuffer(
                "RGB", (width, height), bytes(raw), "raw", "BGR", 0, 1
            )
            filename = os.path.join(output_dir, f"linescan_capture_{frame_counter:06d}.jpg")
            image.save(filename, "JPEG", quality=JPEG_QUALITY)
            print(f"Wrote frame {frame_counter}: {filename}")
            frame_counter += 1
        finally:
            buffer.unmap(map_info)
    except Exception as e:
        print(f"Failed to save rollover frame: {e}")


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
    global loop, output_dir

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Linescan pipeline with direct JPEG recording on rollover',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                                    # Run with defaults (day mode)
  %(prog)s --mode night                       # Night mode (higher exposure & gain)
  %(prog)s --config ini/roi-night.ini         # Use a different camera config
  %(prog)s --output-dir my_captures           # Custom output directory
  %(prog)s --run-seconds 20 --debug           # Timed verification run
  %(prog)s --gst-debug                        # Enable GStreamer debug
        '''
    )

    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug output from this script')
    parser.add_argument('--gst-debug', action='store_true',
                        help='Enable GStreamer debug output (level 3)')
    parser.add_argument('--gst-debug-level', type=int, metavar='LEVEL',
                        help='Set GStreamer debug level (0-9, default: 3 if --gst-debug)')
    parser.add_argument('--output-dir', '-o', metavar='DIR',
                        help='Output directory (default: results/<date>/<funny-name>)')
    parser.add_argument('--config', '-c', default=DEFAULT_CONFIG, metavar='INI',
                        help=f'Camera config .ini (default: {DEFAULT_CONFIG})')
    parser.add_argument('--mode', '-m', choices=['day', 'night'], default='day',
                        help='Camera mode: day (0.02ms exposure, 0 gain) or night (5.25ms exposure, 65 gain) (default: day)')
    parser.add_argument('--framerate', '-r', type=int, default=200, metavar='FPS',
                        help='Camera framerate in fps (default: 200)')
    parser.add_argument('--device-id', type=int, default=1, metavar='ID',
                        help='IDS uEye device id (default: 1)')
    parser.add_argument('--num-buffers', type=int, metavar='N',
                        help='Stop after capturing N source frames (useful for verification runs)')
    parser.add_argument('--aspect', default=DEFAULT_ASPECT, metavar='W:H',
                        help=f'Aspect ratio used to derive the roll width from the ROI (default: {DEFAULT_ASPECT})')
    parser.add_argument('--output-size', type=int, default=None, metavar='N',
                        help='Lines to accumulate before rollover = image width (default: derived from --aspect and the ROI)')
    parser.add_argument('--run-seconds', type=int, metavar='N',
                        help='Run for N seconds, then stop cleanly (useful for verification runs)')

    args = parser.parse_args()

    # Resolve the roll width: explicit --output-size wins, otherwise derive it
    # from the ROI line length and the target aspect ratio.
    if args.output_size is not None:
        output_size = args.output_size
    else:
        line_length = _roi_line_length(args.config)
        if line_length:
            output_size = _derive_output_size(line_length, args.aspect)
        else:
            output_size = 1920
            print(f"WARNING: could not read ROI Width from {args.config}; "
                  f"falling back to --output-size {output_size}")

    # Set up output directory
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

    # Create pipeline
    pipeline = Gst.Pipeline.new("linescan-capture")

    # --- Processing chain elements ---
    source = Gst.ElementFactory.make("idsueyesrc", "source")
    intervalometer = Gst.ElementFactory.make("intervalometer", "intervalometer")
    videoflip = Gst.ElementFactory.make("videoflip", "flip")
    queue1 = Gst.ElementFactory.make("queue", "queue1")
    linescan = Gst.ElementFactory.make("linescan", "linescan")
    queue2 = Gst.ElementFactory.make("queue", "queue2")
    videoconvert = Gst.ElementFactory.make("videoconvert", "convert")
    videosink = Gst.ElementFactory.make("fakesink", "videosink")
    # Let the post-linescan queue hold a couple of ~12 MB frames without
    # blocking linescan on back-pressure from the sink.
    queue2.set_property("max-size-buffers", 3)
    queue2.set_property("max-size-bytes", 0)
    queue2.set_property("max-size-time", 0)
    videosink.set_property("sync", False)

    # Check which elements failed to create
    elements = {
        'pipeline': pipeline,
        'idsueyesrc': source,
        'intervalometer': intervalometer,
        'flip': videoflip,
        'queue1': queue1,
        'linescan': linescan,
        'queue2': queue2,
        'videoconvert': videoconvert,
        'videosink': videosink,
    }

    failed_elements = [name for name, elem in elements.items() if elem is None]

    if failed_elements:
        print("ERROR: Failed to create the following elements:")
        for name in failed_elements:
            print(f"  - {name}")
        print("\nTroubleshooting:")
        if 'linescan' in failed_elements or 'idsueyesrc' in failed_elements:
            print("  Custom plugins not found. Make sure:")
            print("  1. Run .\\build.ps1 to build the plugins")
            print("  2. Set GST_PLUGIN_PATH to include the build directory")
            print("  3. Verify with: gst-inspect-1.0 linescan")
        if 'intervalometer' in failed_elements:
            print("  Intervalometer plugin not found (custom plugin)")
        return -1

    if args.debug:
        print("All elements created successfully")

    # Configure source
    if args.debug:
        print(f"Configuring camera with config file: {args.config}")

    if not os.path.exists(args.config):
        print(f"WARNING: Config file not found: {args.config}")
        print("Continuing without config file...")
    else:
        source.set_property("config-file", args.config)

    # Set camera parameters based on mode
    if args.mode == 'day':
        exposure = 0.02
        gain = 0
    else:  # night
        exposure = 5.25
        gain = 65

    framerate = args.framerate
    device_id = args.device_id

    source.set_property("exposure", exposure)
    source.set_property("framerate", framerate)
    source.set_property("gain", gain)
    source.set_property("device-id", device_id)
    if args.num_buffers is not None:
        source.set_property("num-buffers", args.num_buffers)

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

    # Rotate 90 degrees. The two cameras are mounted with opposite handedness,
    # so the rotation direction depends on which one we're reading:
    #   device-id 1 -> method=1 (CW 90)
    #   device-id 2 -> method=3 (CCW 90)
    flip_method = 3 if device_id == 2 else 1
    videoflip.set_property("method", flip_method)

    # Configure linescan: extract a vertical column per frame, stack horizontally
    linescan.set_property("direction", 1)  # vertical
    linescan.set_property("output-size", output_size)

    if args.debug:
        print(f"Recording output directory: {output_dir}")
        print(f"Camera rotated 90 (videoflip method={flip_method}), then vertical linescan "
              f"with output-size={output_size} (aspect {args.aspect})")

    # Connect rollover signal
    linescan.connect("rollover", on_rollover)

    # Add all elements to pipeline
    for elem in (
        source, intervalometer, videoflip, queue1, linescan,
        queue2, videoconvert, videosink
    ):
        pipeline.add(elem)

    # Link processing chain
    if not source.link(intervalometer):
        print("ERROR: Could not link source to intervalometer")
        return -1
    if not intervalometer.link(videoflip):
        print("ERROR: Could not link intervalometer to videoflip")
        return -1
    if not videoflip.link(queue1):
        print("ERROR: Could not link videoflip to queue1")
        return -1
    if not queue1.link(linescan):
        print("ERROR: Could not link queue1 to linescan")
        return -1
    if not linescan.link(queue2):
        print("ERROR: Could not link linescan to queue2")
        return -1
    if not queue2.link(videoconvert):
        print("ERROR: Could not link queue2 to videoconvert")
        return -1
    if not videoconvert.link(videosink):
        print("ERROR: Could not link videoconvert to videosink")
        return -1

    if args.run_seconds is not None:
        def on_stop_timer():
            loop.quit()
            return False

        GLib.timeout_add_seconds(args.run_seconds, on_stop_timer)

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
    print(f"JPEG frames will be written to: {output_dir}/")
    print("Press Ctrl+C to stop\n")

    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("\nERROR: Unable to set pipeline to playing state")
        print("\nPossible causes:")
        print(f"  1. Camera not connected or unavailable (device-id={device_id})")
        print(f"  2. Config file issue: check if {args.config} exists and is valid")
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
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
    finally:
        time.sleep(0.1)

    # Cleanup
    pipeline.set_state(Gst.State.NULL)
    print(f"\nCaptured {frame_counter} rollover frames -> {output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
