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
# By default a tee is inserted after linescan and a second branch feeds a live
# video sink (scaled to --display-size, throttled to --display-fps), mirroring
# the preview chain that print_camera_cli.py emits. Pass --no-preview for the
# bare recorder-only pipeline.
#
#   linescan -> tee -+-> queue -> videoconvert -> fakesink        (rollover -> JPEG)
#                    +-> queue -> videoconvert -> videoscale -> videorate -> queue(leaky) -> d3d12videosink
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
# Output: results/<date>/<funny-name>/linescan_capture_<YYYYMMDD_HHMMSS_us>.jpg
#         (override the dir with --output-dir; timestamp names let a dir be reused
#          across restarts without overwriting earlier captures)
#
# Usage:
#   uv run gst/linescan/launch_with_signal.py
#   uv run gst/linescan/launch_with_signal.py --mode night
#   uv run gst/linescan/launch_with_signal.py --config ini/roi-night.ini
#   uv run gst/linescan/launch_with_signal.py --run-seconds 20 --debug
#   uv run gst/linescan/launch_with_signal.py --gst-debug
#
# Framerate is adaptive by default: --framerate is only a seed and the
# intervalometer varies the camera rate as its 4th brightness rung within
# [--framerate-min, --framerate-max] (with a lower --framerate-max-boost ceiling
# at night), so one launch runs the line as fast as the light allows across
# dawn/dusk with no restart. --no-adaptive-framerate pins it to a fixed rate.
# See docs/NIGHT_FPS_TUNING.md.
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
            # Timestamp name (not a running counter) so an --output-dir can be
            # reused across restarts without clobbering earlier captures. The
            # microsecond field also keeps it unique well above the ~13/min
            # rollover rate. e.g. linescan_capture_20260829_143017_284519.jpg
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = os.path.join(output_dir, f"linescan_capture_{stamp}.jpg")
            image.save(filename, "JPEG", quality=JPEG_QUALITY)
            print(f"Wrote frame {frame_counter} ({stamp}): {filename}")
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
  %(prog)s --no-preview                       # Recorder only, no live video sink
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
    parser.add_argument('--log-file', metavar='CSV',
                        help='Intervalometer CSV log path (default: timelapse_<date>.csv). '
                             'Opened in append mode - one row per update-interval, restarts '
                             'keep history.')
    parser.add_argument('--config', '-c', default=DEFAULT_CONFIG, metavar='INI',
                        help=f'Camera config .ini (default: {DEFAULT_CONFIG})')
    parser.add_argument('--mode', '-m', choices=['day', 'night'], default='day',
                        help='Camera mode: day (0.02ms exposure, 0 gain, gain-boost off) or '
                             'night (5ms exposure, 68 gain, gain-boost on) (default: day). '
                             'Only a seed - the intervalometer takes over within seconds; '
                             'the night seed is placed at the measured operating point so a '
                             'night (re)start converges fast instead of walking the slow ramp.')
    parser.add_argument('--auto-gain-boost', action=argparse.BooleanOptionalAction, default=True,
                        help='Let the intervalometer toggle the camera gain-boost as a third '
                             'rung (exposure -> gain -> gain-boost) so dawn/dusk needs no restart '
                             '(default: on). With this on the --mode gain-boost bit is just a seed.')
    parser.add_argument('--boost-min-dwell', type=float, default=120.0, metavar='SEC',
                        help='Min seconds to hold a gain-boost state before it can toggle back '
                             '(anti-chatter at dusk; default: 120)')
    parser.add_argument('--gain-max', type=int, default=25, metavar='N',
                        help='Intervalometer gain ceiling, 1-100 (default: 25). Lower it to cut '
                             'noise - the whole ladder tops out sooner. NOTE: 0 is not "no gain", '
                             'it is the intervalometer sentinel for "use the camera max (100)".')
    parser.add_argument('--gain-max-boost', type=int, default=0, metavar='N',
                        help='Separate, lower gain ceiling that applies only while gain-boost is '
                             'on (0 = disabled, use --gain-max in both states). Lets gain still '
                             'climb high at dusk to delay boost, then stay capped once boosted so '
                             'boost x gain does not blow up the noise. Try ~40.')
    parser.add_argument('--framerate', '-r', type=int, default=None, metavar='FPS',
                        help='Camera framerate in fps. With --adaptive-framerate (default) this '
                             'is only the startup SEED - the intervalometer then drives fps as '
                             'its 4th rung within [--framerate-min, --framerate-max]. If omitted, '
                             'the seed is --framerate-max (day) or --framerate-max-boost (night). '
                             'With --no-adaptive-framerate it is the fixed rate (default: 200).')
    parser.add_argument('--adaptive-framerate', action=argparse.BooleanOptionalAction, default=True,
                        help='Let the intervalometer vary the camera framerate as a 4th rung '
                             '(exposure -> gain -> gain-boost -> framerate): lower fps when still '
                             'dark with the first three pinned (buys a longer 1/fps exposure cap), '
                             'raise fps when there is surplus light. Keeps the line rate as high '
                             'as the light allows around the clock (default: on).')
    parser.add_argument('--framerate-min', type=float, default=150.0, metavar='FPS',
                        help='Adaptive-fps floor (default: 150). The darkest-night line rate.')
    parser.add_argument('--framerate-max', type=float, default=800.0, metavar='FPS',
                        help='Adaptive-fps ceiling / full-sun daytime target (default: 800). '
                             'Also sizes --emit-every auto.')
    parser.add_argument('--framerate-max-boost', type=float, default=400.0, metavar='FPS',
                        help='Separate, lower fps ceiling that applies only while gain-boost is on '
                             '(= night); fps is snapped down to it when boost engages at dusk '
                             '(0 = use --framerate-max in both states; default: 400).')
    parser.add_argument('--framerate-step', type=float, default=1.15, metavar='MULT',
                        help='Multiplicative fps step per rung-4 adjustment (default: 1.15 = +/-15%%).')
    parser.add_argument('--framerate-min-dwell', type=float, default=20.0, metavar='SEC',
                        help='Min seconds to hold an fps before rung 4 changes it again '
                             '(anti-chatter at dawn/dusk; default: 20).')
    parser.add_argument('--device-id', type=int, default=1, metavar='ID',
                        help='IDS uEye device id (default: 1)')
    parser.add_argument('--num-buffers', type=int, metavar='N',
                        help='Stop after capturing N source frames (useful for verification runs)')
    parser.add_argument('--aspect', default=DEFAULT_ASPECT, metavar='W:H',
                        help=f'Aspect ratio used to derive the roll width from the ROI (default: {DEFAULT_ASPECT})')
    parser.add_argument('--output-size', type=int, default=None, metavar='N',
                        help='Lines to accumulate before rollover = image width (default: derived from --aspect and the ROI)')
    parser.add_argument('--emit-every', default='auto', metavar='N',
                        help='Push the full roll buffer downstream only every Nth camera frame '
                             '(one column is still accumulated per frame, and rollover always '
                             'emits). Keeps the ~20 MB per-frame copy off the hot path at high '
                             'framerates. "auto" (default) = round(peak-framerate / --display-fps), '
                             'where peak-framerate is --framerate-max when adaptive fps is on; '
                             'use 1 to emit every frame.')
    parser.add_argument('--run-seconds', type=int, metavar='N',
                        help='Run for N seconds, then stop cleanly (useful for verification runs)')
    parser.add_argument('--preview', action=argparse.BooleanOptionalAction, default=True,
                        help='Tee the linescan output to a live video sink as well as the JPEG '
                             'recorder (default: on; --no-preview for recorder only)')
    parser.add_argument('--preview-sink', default='d3d12videosink', metavar='ELEM',
                        help='Sink element for the --preview branch (default: d3d12videosink). '
                             'autovideosink also works but gives a plain titled window.')
    parser.add_argument('--fullscreen', action=argparse.BooleanOptionalAction, default=True,
                        help='Borderless-fullscreen the preview window (default: on). Applied only '
                             'when the --preview-sink exposes a "fullscreen" property (d3d12videosink '
                             'does; autovideosink does not). Alt+Enter toggles it at runtime.')
    parser.add_argument('--display-width', type=int, default=1920, metavar='W',
                        help='Preview window width in px (default: 1920)')
    parser.add_argument('--display-height', type=int, default=1080, metavar='H',
                        help='Preview window height in px (default: 1080)')
    parser.add_argument('--display-fps', type=int, default=30, metavar='FPS',
                        help='Throttle the preview branch to this framerate (default: 30)')

    args = parser.parse_args()

    # gain-max=0 is the intervalometer's "query from camera" sentinel (-> 100),
    # never a real limit. Reject it here so it can't silently mean "no cap".
    if args.gain_max < 1:
        parser.error("--gain-max must be >= 1 (0 means 'use camera max' inside the "
                     "intervalometer, which is the opposite of a limit)")
    if args.gain_max_boost and args.gain_max_boost >= args.gain_max:
        parser.error(f"--gain-max-boost ({args.gain_max_boost}) must be below --gain-max "
                     f"({args.gain_max}) to have any effect")

    # Resolve the framerate: with adaptive control on, --framerate is only a seed
    # and the intervalometer owns the rate within [min, max]; otherwise it is the
    # fixed rate. fps_ceiling is the highest rate the run can reach and is what
    # --emit-every auto must be sized for.
    adaptive_fps = args.adaptive_framerate
    if adaptive_fps:
        if args.framerate_min >= args.framerate_max:
            parser.error(f"--framerate-min ({args.framerate_min:g}) must be < "
                         f"--framerate-max ({args.framerate_max:g})")
        if args.framerate_max_boost and not (
                args.framerate_min < args.framerate_max_boost <= args.framerate_max):
            parser.error(f"--framerate-max-boost ({args.framerate_max_boost:g}) must be 0 or in "
                         f"(--framerate-min, --framerate-max] = "
                         f"({args.framerate_min:g}, {args.framerate_max:g}]")
        fps_ceiling = args.framerate_max
        if args.framerate is not None:
            seed_framerate = args.framerate
        elif args.mode == 'night':
            seed_framerate = int(args.framerate_max_boost or args.framerate_max)
        else:
            seed_framerate = int(args.framerate_max)
    else:
        seed_framerate = args.framerate if args.framerate is not None else 200
        fps_ceiling = seed_framerate

    # Resolve emit-every: "auto" tracks the preview cadence so downstream only
    # sees ~--display-fps roll buffers/s at the run's peak framerate.
    if str(args.emit_every).lower() == 'auto':
        emit_every = max(1, round(fps_ceiling / max(1, args.display_fps)))
    else:
        try:
            emit_every = max(1, int(args.emit_every))
        except ValueError:
            parser.error(f"--emit-every must be an integer or 'auto', got {args.emit_every!r}")

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

    # --- Optional live-preview branch: tee off the linescan output ---
    tee = None
    preview_elements = ()
    if args.preview:
        tee = Gst.ElementFactory.make("tee", "tee")
        preview_queue = Gst.ElementFactory.make("queue", "preview_queue")
        preview_convert = Gst.ElementFactory.make("videoconvert", "preview_convert")
        preview_scale = Gst.ElementFactory.make("videoscale", "preview_scale")
        preview_caps = Gst.ElementFactory.make("capsfilter", "preview_caps")
        preview_rate = Gst.ElementFactory.make("videorate", "preview_rate")
        preview_rate_caps = Gst.ElementFactory.make("capsfilter", "preview_rate_caps")
        preview_leaky = Gst.ElementFactory.make("queue", "preview_leaky")
        preview_sink = Gst.ElementFactory.make(args.preview_sink, "preview_sink")

        preview_elements = (
            preview_queue, preview_convert, preview_scale, preview_caps,
            preview_rate, preview_rate_caps, preview_leaky, preview_sink,
        )

        elements.update({
            'tee': tee,
            'preview_queue': preview_queue,
            'preview_convert': preview_convert,
            'preview_scale': preview_scale,
            'preview_caps': preview_caps,
            'preview_rate': preview_rate,
            'preview_rate_caps': preview_rate_caps,
            'preview_leaky': preview_leaky,
            f'preview_sink ({args.preview_sink})': preview_sink,
        })

        if preview_caps is not None:
            # pixel-aspect-ratio=1/1 keeps videoscale from re-stretching via a
            # non-square PAR that the sink would then undo.
            preview_caps.set_property("caps", Gst.Caps.from_string(
                f"video/x-raw,width={args.display_width},"
                f"height={args.display_height},pixel-aspect-ratio=1/1"
            ))
        if preview_rate_caps is not None:
            # linescan emits a roll buffer every `emit-every` camera frames
            # (~display-fps by default); throttle to a sane preview rate anyway
            # so the video sink doesn't drop "late" buffers on cadence jitter.
            preview_rate_caps.set_property("caps", Gst.Caps.from_string(
                f"video/x-raw,framerate={args.display_fps}/1"
            ))
        if preview_leaky is not None:
            # drop stale roll frames instead of back-pressuring linescan.
            preview_leaky.set_property("leaky", 2)  # downstream
            preview_leaky.set_property("max-size-buffers", 2)
        if preview_sink is not None:
            preview_sink.set_property("sync", False)
            # Borderless fullscreen when the sink supports it. d3d12videosink
            # takes plain "fullscreen"/"fullscreen-on-alt-enter" booleans;
            # autovideosink has neither, so guard on the property.
            if args.fullscreen and preview_sink.find_property("fullscreen"):
                preview_sink.set_property("fullscreen", True)
                if preview_sink.find_property("fullscreen-on-alt-enter"):
                    preview_sink.set_property("fullscreen-on-alt-enter", True)

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

    # Set camera parameters based on mode. These are only a seed - the
    # intervalometer overrides exposure/gain/gain-boost within seconds.
    if args.mode == 'day':
        exposure = 0.02
        gain = 0
        gain_boost = False
    else:  # night
        # Measured 200 fps night operating point: exposure pinned at the
        # 1/framerate cap (~4.96 ms; 5.25 sits above it so idsueyesrc clamps it
        # there at once), gain ~68, gain-boost on. Seeding here means a night
        # start or a mid-night restart converges in seconds rather than crawling
        # the slow ramp up from a dark day seed (~18 min from exposure 0.02).
        exposure = 5.25
        gain = 68
        gain_boost = True

    # Clamp the seed to the ceiling the intervalometer will enforce, so the
    # camera never physically starts above the limit (otherwise the control loop
    # spends ~tens of seconds ramping the mode seed back down).
    seed_ceiling = args.gain_max
    if gain_boost and args.gain_max_boost > 0:
        seed_ceiling = min(seed_ceiling, args.gain_max_boost)
    gain_seed_clamped = gain > seed_ceiling
    if gain_seed_clamped:
        gain = seed_ceiling

    framerate = seed_framerate
    device_id = args.device_id

    source.set_property("exposure", exposure)
    source.set_property("framerate", framerate)
    source.set_property("gain", gain)
    source.set_property("gain-boost", gain_boost)
    source.set_property("device-id", device_id)
    if args.num_buffers is not None:
        source.set_property("num-buffers", args.num_buffers)

    if args.debug:
        print(f"Camera mode: {args.mode}")
        print(f"Camera settings: exposure={exposure}ms, framerate={framerate}fps, gain={gain}, "
              f"gain-boost={gain_boost}, device-id={device_id}")

    # Configure intervalometer. ramp-rate=slow keeps the diurnal brightness ramp
    # smooth; the --mode seed above lands near the operating point so a cold
    # start still converges quickly despite the slow ramp. gain-max=82 is the
    # night ceiling (see docs/NIGHT_FPS_TUNING.md); above it, gain-boost
    # takes over as the third rung.
    iv_ramp_rate = "slow"
    iv_update_interval = 1000
    iv_target_brightness = 80.0
    iv_gain_max = args.gain_max
    intervalometer.set_property("enabled", True)
    intervalometer.set_property("camera-element", "source")
    intervalometer.set_property("ramp-rate", iv_ramp_rate)
    intervalometer.set_property("update-interval", iv_update_interval)
    intervalometer.set_property("brightness-deadband", 10.0)
    intervalometer.set_property("gain-max", iv_gain_max)
    intervalometer.set_property("target-brightness", iv_target_brightness)
    log_file = args.log_file or f"timelapse_{datetime.now().strftime('%Y%m%d')}.csv"
    intervalometer.set_property("log-file", log_file)
    intervalometer.set_property("log-append", True)
    intervalometer.set_property("auto-gain-boost", args.auto_gain_boost)
    intervalometer.set_property("boost-min-dwell", args.boost_min_dwell)
    if args.gain_max_boost > 0:
        intervalometer.set_property("gain-max-boost", args.gain_max_boost)

    # Adaptive framerate = 4th rung (exposure -> gain -> gain-boost -> framerate).
    # Only engages once the first three are pinned, so it never perturbs the
    # normal diurnal ramp until that ramp hits a rail. See docs/NIGHT_FPS_TUNING.md.
    if adaptive_fps:
        intervalometer.set_property("framerate-min", float(args.framerate_min))
        intervalometer.set_property("framerate-max", float(args.framerate_max))
        if args.framerate_max_boost > 0:
            intervalometer.set_property("framerate-max-boost", float(args.framerate_max_boost))
        intervalometer.set_property("framerate-step", float(args.framerate_step))
        intervalometer.set_property("framerate-min-dwell", float(args.framerate_min_dwell))

    # Rotate 90 degrees. The two cameras are mounted with opposite handedness,
    # so the rotation direction depends on which one we're reading:
    #   device-id 1 -> method=1 (CW 90)
    #   device-id 2 -> method=3 (CCW 90)
    flip_method = 3 if device_id == 2 else 1
    videoflip.set_property("method", flip_method)

    # Configure linescan: extract a vertical column per frame, stack horizontally
    linescan.set_property("direction", 1)  # vertical
    linescan.set_property("output-size", output_size)
    linescan.set_property("emit-every", emit_every)

    if args.debug:
        print(f"Recording output directory: {output_dir}")
        print(f"Camera rotated 90 (videoflip method={flip_method}), then vertical linescan "
              f"with output-size={output_size} (aspect {args.aspect}), emit-every={emit_every}")
        if args.preview:
            fs_txt = " fullscreen" if args.fullscreen else ""
            print(f"Preview branch: tee -> {args.preview_sink}{fs_txt} "
                  f"({args.display_width}x{args.display_height} @ {args.display_fps}fps)")

    # Connect rollover signal
    linescan.connect("rollover", on_rollover)

    # Add all elements to pipeline
    for elem in (
        source, intervalometer, videoflip, queue1, linescan,
        queue2, videoconvert, videosink
    ):
        pipeline.add(elem)

    if args.preview:
        pipeline.add(tee)
        for elem in preview_elements:
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
    if args.preview:
        # linescan -> tee -+-> queue2 -> ... -> fakesink   (rollover -> JPEG)
        #                  +-> preview branch -> live video sink
        if not linescan.link(tee):
            print("ERROR: Could not link linescan to tee")
            return -1
        if not tee.link(queue2):
            print("ERROR: Could not link tee to queue2")
            return -1
        preview_chain = [
            tee, preview_queue, preview_convert, preview_scale, preview_caps,
            preview_rate, preview_rate_caps, preview_leaky, preview_sink,
        ]
        for a, b in zip(preview_chain, preview_chain[1:]):
            if not a.link(b):
                print(f"ERROR: Could not link {a.get_name()} to {b.get_name()}")
                return -1
    elif not linescan.link(queue2):
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
        # DEBUG, not LOG: keeps "Rollover occurred" but drops the per-frame
        # "output dropped" / "Processed frame" spam from emit-every decimation.
        Gst.debug_set_threshold_for_name("linescan", Gst.DebugLevel.DEBUG)
        if args.debug:
            print("Enabled DEBUG level logging for linescan element")

    # Set up message handling before starting
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_message)

    if args.debug:
        print("\nStarting pipeline...")
        print(f"Pipeline state: {pipeline.get_state(0)[1].value_nick}")

    # Start pipeline - always echo the resolved config so it is obvious at a
    # glance whether e.g. --mode night was actually passed.
    boost_txt = (f"auto (dwell {args.boost_min_dwell:g}s)"
                 if args.auto_gain_boost else "static (from --mode seed)")
    if adaptive_fps:
        fps_hdr = (f"{framerate} fps seed -> adaptive {args.framerate_min:g}-{args.framerate_max:g}"
                   + (f" ({args.framerate_max_boost:g} night)" if args.framerate_max_boost > 0 else ""))
    else:
        fps_hdr = f"{framerate} fps fixed"
    print(f"linescan recorder  |  mode={args.mode}  |  {fps_hdr}  |  device-id={device_id}")
    print(f"  camera seed   : exposure={exposure} ms, gain={gain}, gain-boost={gain_boost}")
    gain_max_txt = (f"{iv_gain_max}" if args.gain_max_boost <= 0
                    else f"{iv_gain_max} ({args.gain_max_boost} while boosted)")
    print(f"  intervalometer: target-brightness={iv_target_brightness:g}, gain-max={gain_max_txt}, "
          f"ramp-rate={iv_ramp_rate}, gain-boost={boost_txt}")
    if adaptive_fps:
        fmb = (f", {args.framerate_max_boost:g} while boosted"
               if args.framerate_max_boost > 0 else "")
        print(f"  adaptive fps  : {args.framerate_min:g}-{args.framerate_max:g} fps{fmb}, "
              f"x{args.framerate_step:g}/step, {args.framerate_min_dwell:g}s dwell (rung 4)")
    print(f"  linescan      : output-size={output_size}, emit-every={emit_every}"
          f"{' (preview off)' if not args.preview else ''}")
    if args.preview:
        print(f"  preview       : {args.preview_sink}, {args.display_width}x{args.display_height} "
              f"@ {args.display_fps} fps"
              f"{', borderless fullscreen (Alt+Enter toggles)' if args.fullscreen else ''}")
    print(f"  writing JPEGs : {output_dir}/")
    print(f"  csv log       : {log_file} (append, 1 row / {iv_update_interval} ms)")
    if args.mode == 'day':
        print("  note: 'day' seed in the dark takes ~18 min to ramp up; use --mode night at night")
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
