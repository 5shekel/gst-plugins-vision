#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pillow",
# ]
# ///

"""
Stitch linescan frame sequences horizontally and create scrolling video.
Linescan images are concatenated side-by-side and played as a scrolling video.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List
from PIL import Image


def find_frames(directory: Path, pattern: str = "*.jpeg") -> List[Path]:
    """Find all frame files matching the pattern, sorted by name."""
    frames = sorted(directory.glob(pattern))
    if not frames:
        frames = sorted(directory.glob("*.jpg"))
    if not frames:
        frames = sorted(directory.glob("*.png"))
    return frames


def stitch_images_horizontally(
    frames: List[Path],
    output_file: Path,
    max_frames: int = None
) -> tuple[int, int]:
    """
    Stitch images horizontally into a single wide image.
    Returns (width, height) of stitched image.
    """
    if max_frames is not None and max_frames > 0:
        frames = frames[:max_frames]
    
    print(f"Loading {len(frames)} images for stitching...")
    
    # Load first image to get dimensions
    first_img = Image.open(frames[0])
    img_width, img_height = first_img.size
    
    # Calculate total width
    total_width = img_width * len(frames)
    
    print(f"Creating stitched image: {total_width}x{img_height} pixels")
    print(f"  Individual frame size: {img_width}x{img_height}")
    print(f"  Total frames: {len(frames)}")
    
    # Create large canvas
    stitched = Image.new('RGB', (total_width, img_height))
    
    # Paste images
    x_offset = 0
    for i, frame_path in enumerate(frames):
        if i % 50 == 0:
            print(f"  Stitching frame {i+1}/{len(frames)}...")
        img = Image.open(frame_path)
        stitched.paste(img, (x_offset, 0))
        x_offset += img_width
    
    print(f"Saving stitched image to {output_file}...")
    stitched.save(output_file, quality=95)
    
    return total_width, img_height


def create_scrolling_video(
    stitched_image: Path,
    output_file: Path,
    total_width: int,
    height: int,
    output_width: int = 1920,
    scroll_speed: float = 750.0,
    fps: int = 30,
    crf: int = 18,
    lines_per_second: float = 750.0
) -> None:
    """
    Create scrolling video from stitched image.
    
    Args:
        stitched_image: Path to stitched horizontal image
        output_file: Output video file
        total_width: Total width of stitched image
        height: Height of image
        output_width: Width of output video viewport
        scroll_speed: Scroll speed multiplier (1.0 = real-time @ 750 lines/sec)
        fps: Output video framerate
        crf: Quality (lower = better)
        lines_per_second: Linescan capture rate (pixels per second)
    """
    # Calculate scroll parameters
    # At scroll_speed=1.0, we scroll at the actual capture rate
    pixels_per_second = lines_per_second * scroll_speed
    pixels_per_frame = pixels_per_second / fps
    
    # Calculate video duration
    scrollable_width = total_width - output_width
    duration = scrollable_width / pixels_per_second
    total_frames = int(duration * fps)
    
    print(f"\nScrolling video parameters:")
    print(f"  Output viewport: {output_width}x{height}")
    print(f"  Scroll speed: {scroll_speed}x real-time ({pixels_per_second:.1f} pixels/sec)")
    print(f"  Pixels per frame: {pixels_per_frame:.2f}")
    print(f"  Video duration: {duration:.2f} seconds")
    print(f"  Total frames: {total_frames}")
    print(f"  Output FPS: {fps}")
    
    # FFmpeg crop filter with horizontal scrolling
    # crop=w:h:x:y where x moves from 0 to (total_width - output_width)
    # The 't' variable represents time in seconds
    crop_expr = f"crop={output_width}:{height}:min({pixels_per_second}*t\\,{total_width-output_width}):0"
    
    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(stitched_image),
        "-vf", crop_expr,
        "-t", str(duration),
        "-r", str(fps),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_file)
    ]
    
    print(f"\nRunning ffmpeg...")
    print(f"Command: {' '.join(cmd)}\n")
    
    try:
        subprocess.run(cmd, check=True)
        print(f"\n✓ Scrolling video created successfully: {output_file}")
        
        # Show file size
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"  File size: {size_mb:.2f} MB")
        print(f"  Duration: {duration:.2f} seconds")
        
    except subprocess.CalledProcessError as e:
        print(f"Error: ffmpeg command failed with return code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg and ensure it's in your PATH.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Stitch linescan images horizontally and create scrolling video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Real-time playback (1.0x speed, 750 lines/second)
  python append_signals.py results/20251122/bumpy-filter
  
  # Slow motion (0.5x speed)
  python append_signals.py results/20251122/bumpy-filter --scroll-speed 0.5
  
  # Fast playback (2x speed)
  python append_signals.py results/20251122/bumpy-filter --scroll-speed 2.0
  
  # Process only first 100 frames
  python append_signals.py results/20251122/bumpy-filter --max-frames 100
  
  # Higher FPS for smoother scrolling
  python append_signals.py results/20251122/bumpy-filter --fps 60
  
  # Custom output width (4K)
  python append_signals.py results/20251122/bumpy-filter --width 3840
        """
    )
    
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing the linescan frame sequence"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output video file (default: {folder_name}_{timestamp}.mp4 in input dir)"
    )
    
    parser.add_argument(
        "--scroll-speed",
        type=float,
        default=1.0,
        help="Scroll speed multiplier (1.0 = real-time at 750 lines/sec, default: 1.0)"
    )
    
    parser.add_argument(
        "--lines-per-second",
        type=float,
        default=750.0,
        help="Linescan capture rate in lines/pixels per second (default: 750)"
    )
    
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Output video framerate (default: 30)"
    )
    
    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Output video viewport width in pixels (default: 1920)"
    )
    
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="Constant Rate Factor for quality, lower=better (default: 18, range: 0-51)"
    )
    
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.jpeg",
        help="File pattern to match frames (default: *.jpeg)"
    )
    
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Maximum number of frames to process (default: all frames)"
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.input_dir.exists():
        print(f"Error: Input directory does not exist: {args.input_dir}")
        sys.exit(1)
    
    if not args.input_dir.is_dir():
        print(f"Error: Input path is not a directory: {args.input_dir}")
        sys.exit(1)
    
    # Find frames
    frames = find_frames(args.input_dir, args.pattern)
    
    if not frames:
        print(f"Error: No frames found in {args.input_dir} matching pattern {args.pattern}")
        sys.exit(1)
    
    total_frames = len(frames)
    if args.max_frames is not None and args.max_frames > 0:
        frames = frames[:args.max_frames]
        print(f"Found {total_frames} frames, processing first {len(frames)} frames")
    else:
        print(f"Found {len(frames)} frames in {args.input_dir}")
    
    # Set output file (one folder up from input directory)
    if args.output is None:
        unix_time = int(time.time())
        folder_name = args.input_dir.name
        output_filename = f"{folder_name}_scroll_{unix_time}.mp4"
        output_file = args.input_dir.parent / output_filename
    else:
        output_file = args.output
    
    # Validate CRF range
    if not 0 <= args.crf <= 51:
        print("Error: CRF must be between 0 and 51")
        sys.exit(1)
    
    # Create temporary stitched image
    stitched_filename = f"stitched_temp_{int(time.time())}.jpg"
    stitched_path = args.input_dir / stitched_filename
    
    try:
        # Stitch images
        total_width, img_height = stitch_images_horizontally(
            frames=frames,
            output_file=stitched_path,
            max_frames=args.max_frames
        )
        
        # Create scrolling video
        create_scrolling_video(
            stitched_image=stitched_path,
            output_file=output_file,
            total_width=total_width,
            height=img_height,
            output_width=args.width,
            scroll_speed=args.scroll_speed,
            fps=args.fps,
            crf=args.crf,
            lines_per_second=args.lines_per_second
        )
        
    finally:
        # Clean up temporary stitched image
        if stitched_path.exists():
            print(f"\nCleaning up temporary file: {stitched_filename}")
            stitched_path.unlink()


if __name__ == "__main__":
    main()