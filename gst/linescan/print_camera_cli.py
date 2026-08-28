#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///

import argparse
import configparser
import shlex


CONFIG_FILE = "ini/roi-dusk.ini"
DEFAULT_ASPECT = "16:9"


def _roi_line_length(config_path):
    """Raw linescan output height = IDS ini [Image size] Width (ROI is rotated
    90 degrees before linescan). Returns None if the ini can't be read."""
    try:
        cp = configparser.ConfigParser()
        # IDS ini files are written with a UTF-8 BOM.
        if not cp.read(config_path, encoding="utf-8-sig"):
            return None
        return cp.getint("Image size", "Width")
    except (configparser.Error, ValueError, OSError):
        return None


def _derive_output_size(line_length, aspect):
    aw, ah = (int(x) for x in aspect.split(":"))
    return round(line_length * aw / ah)


def resolve_output_size(args):
    if args.output_size is not None:
        return args.output_size
    line_length = _roi_line_length(args.config)
    if line_length:
        return _derive_output_size(line_length, args.aspect)
    return 1920


def build_command(args):
    if args.mode == "day":
        exposure = 0.02
        gain = 0
    else:
        exposure = 5.25
        gain = 65

    output_size = resolve_output_size(args)

    # The two cameras are mounted with opposite handedness, so the 90-degree
    # rotation direction depends on which one we're reading:
    #   device-id 1 -> method=1 (CW 90)
    #   device-id 2 -> method=3 (CCW 90)
    flip_method = 3 if args.device_id == 2 else 1

    # Geometry (roi-dusk.ini): camera ROI is 2016 x 20 (W x H).
    #   videoflip method=1/3 (90 CW/CCW, per device-id) -> 20 x 2016
    #   linescan direction=1        -> picks one column, stacks horizontally
    #                              -> output-size x 2016  (roll grows left..right)
    #   videoscale                  -> display-width x display-height (fit the screen)
    #
    # output-size defaults to the 16:9 width for the ROI (2016 * 16/9 = 3584) so
    # the raw roll downscales to the display size without distortion.
    #
    # No videocrop: linescan already selects a single line (line-index, default
    # = middle column), so trimming rows off the ROI first is redundant.
    # pixel-aspect-ratio=1/1 keeps videoscale from re-stretching via a non-square
    # PAR that the sink would then undo.
    display_caps = (
        f"video/x-raw,width={args.display_width},"
        f"height={args.display_height},pixel-aspect-ratio=1/1"
    )

    command = [
        "gst-launch-1.0",
        "idsueyesrc",
        "name=source",
        f"device-id={args.device_id}",
        f"config-file={shlex.quote(args.config)}",
        f"exposure={exposure}",
        f"framerate={args.framerate}",
        f"gain={gain}",
        "!",
        "intervalometer",
        "enabled=true",
        "camera-element=source",
        "ramp-rate=slow",
        "update-interval=1000",
        "brightness-deadband=10.0",
        "gain-max=82",
        "target-brightness=80.0",
        "log-file=timelapse.csv",
        "!",
        "videoflip",
        f"method={flip_method}",
        "!",
        "queue",
        "!",
        "linescan",
        "direction=1",
        # roll starts at left=0 and fills to output-size on the right
        f"output-size={output_size}",
        "!",
        "queue",
        "max-size-buffers=3",
        "max-size-bytes=0",
        "max-size-time=0",
        "!",
        "videoconvert",
        "!",
        "videoscale",
        "!",
        display_caps,
        "!",
        # linescan emits one frame per *camera* frame (200-1300 fps); throttle
        # to a sane preview rate or the video sink drops "late" buffers.
        "videorate",
        "!",
        f"video/x-raw,framerate={args.display_fps}/1",
        "!",
        # leaky queue: drop stale roll frames instead of back-pressuring linescan.
        "queue",
        "leaky=downstream",
        "max-size-buffers=2",
        "!",
        args.sink,
        "sync=false",
    ]

    return " ".join(command)


def main():
    parser = argparse.ArgumentParser(
        description="Print a gst-launch-1.0 command matching launch_with_signal.py camera settings"
    )
    parser.add_argument("--mode", choices=["day", "night"], default="day")
    parser.add_argument("--framerate", type=int, default=200)
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--config", default=CONFIG_FILE,
                        help=f"Camera config .ini (default: {CONFIG_FILE})")
    parser.add_argument("--sink", default="autovideosink")
    parser.add_argument("--aspect", default=DEFAULT_ASPECT, metavar="W:H",
                        help=f"Aspect ratio used to derive the roll width from the ROI (default: {DEFAULT_ASPECT})")
    parser.add_argument("--output-size", type=int, default=None,
                        help="Roll length in px (default: derived from --aspect and the ROI)")
    parser.add_argument("--display-width", type=int, default=1920,
                        help="Preview window width in px (default: 1920)")
    parser.add_argument("--display-height", type=int, default=1080,
                        help="Preview window height in px (default: 1080)")
    parser.add_argument("--display-fps", type=int, default=30,
                        help="Throttle the preview to this framerate (default: 30)")
    args = parser.parse_args()

    print(build_command(args))


if __name__ == "__main__":
    main()
