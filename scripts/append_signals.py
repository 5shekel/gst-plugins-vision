#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""
Create scrolling panorama videos from linescan image sequences.

This script uses ffmpeg's streaming filters to efficiently process linescan images
without loading the entire stitched panorama into memory. Images are horizontally
concatenated and scrolled left-to-right on-the-fly.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List


def find_frames(directory: Path, pattern: str = "*.jpeg") -> List[Path]:
    """Find all frame files matching the pattern, sorted by name."""
    frames = sorted(directory.glob(pattern))
    if not frames:
        frames = sorted(directory.glob("*.jpg"))
    if not frames:
        frames = sorted(directory.glob("*.png"))
    return frames


def create_scrolling_video_efficient(
    frames: List[Path],
    output_file: Path,
    output_width: int = 1920,
    scroll_speed: float = 1.0,
    fps: int = 30,
    crf: int = 18,
    lines_per_second: float = 750.0
) -> None:
    """
    Create scrolling video from image sequence using ffmpeg streaming.
    Memory-efficient - doesn't create intermediate stitched image.
    
    Args:
        frames: List of image file paths
        output_file: Output video file
        output_width: Width of output video viewport
        scroll_speed: Scroll speed multiplier (1.0 = real-time @ 750 lines/sec)
        fps: Output video framerate
        crf: Quality (lower = better)
        lines_per_second: Linescan capture rate (pixels per second)
    """
    num_frames = len(frames)
    
    # Get dimensions from first frame
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        str(frames[0])
    ]
    
    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        img_width, img_height = map(int, result.stdout.strip().split('x'))
    except Exception as e:
        print(f"Error probing image dimensions: {e}")
        sys.exit(1)
    
    # Calculate total width and video parameters
    total_width = img_width * num_frames
    pixels_per_second = lines_per_second * scroll_speed
    pixels_per_frame = pixels_per_second / fps
    scrollable_width = total_width - output_width
    duration = scrollable_width / pixels_per_second
    total_frames = int(duration * fps)
    
    print(f"\nVideo parameters:")
    print(f"  Input: {num_frames} images of {img_width}x{img_height}")
    print(f"  Total panorama width: {total_width} pixels")
    print(f"  Output viewport: {output_width}x{img_height}")
    print(f"  Scroll speed: {scroll_speed}x real-time ({pixels_per_second:.1f} pixels/sec)")
    print(f"  Pixels per frame: {pixels_per_frame:.2f}")
    print(f"  Video duration: {duration:.2f} seconds")
    print(f"  Total frames: {total_frames}")
    print(f"  Output FPS: {fps}")
    
    # Create concat file for ffmpeg
    concat_file = frames[0].parent / f"concat_temp_{int(time.time())}.txt"
    try:
        with open(concat_file, 'w') as f:
            for frame in frames:
                f.write(f"file '{frame.absolute()}'\n")
        
        # Build scrolling crop expression: x position moves based on time
        crop_expr = f"crop={output_width}:{img_height}:min({pixels_per_second}*t\\,{scrollable_width}):0"
        
        # Filter chain: tile creates horizontal panorama, loop repeats it, crop scrolls
        filter_complex = f"tile=layout={num_frames}x1[pano];[pano]loop=loop=-1:size=1:start=0,{crop_expr}"
        
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-filter_complex", filter_complex,
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
            
    finally:
        # Clean up concat file
        if concat_file.exists():
            concat_file.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Create scrolling panorama videos from linescan images (memory-efficient)",
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

Note: This version uses ffmpeg's tile filter for memory-efficient processing.
No intermediate stitched image is created - everything is streamed.
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
        help="Output video file (default: {folder_name}_scroll_{timestamp}.mp4)"
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
    
    # Create scrolling video using efficient streaming method
    create_scrolling_video_efficient(
        frames=frames,
        output_file=output_file,
        output_width=args.width,
        scroll_speed=args.scroll_speed,
        fps=args.fps,
        crf=args.crf,
        lines_per_second=args.lines_per_second
    )


if __name__ == "__main__":
    main()