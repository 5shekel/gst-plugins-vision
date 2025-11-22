#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

"""
Concatenate a sequence of frames into a video using ffmpeg.
Scales to 1920 width and allows control of video speed via fps.
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


def create_video_ffmpeg(
    input_dir: Path,
    output_file: Path,
    fps: int = 30,
    width: int = 1920,
    crf: int = 18,
    pattern: str = "*.jpeg",
    max_frames: int = None
) -> None:
    """
    Create video from image sequence using ffmpeg.
    
    Args:
        input_dir: Directory containing the frames
        output_file: Output video file path
        fps: Frames per second (controls playback speed)
        width: Output video width in pixels (height auto-scales)
        crf: Constant Rate Factor for quality (lower = better, 18-23 recommended)
        pattern: File pattern to match frame files
    """
    frames = find_frames(input_dir, pattern)
    
    if not frames:
        print(f"Error: No frames found in {input_dir} matching pattern {pattern}")
        sys.exit(1)
    
    total_frames = len(frames)
    
    # Limit frames if max_frames is specified
    if max_frames is not None and max_frames > 0:
        frames = frames[:max_frames]
        print(f"Found {total_frames} frames in {input_dir}, processing first {len(frames)} frames")
    else:
        print(f"Found {len(frames)} frames in {input_dir}")
    print(f"First frame: {frames[0].name}")
    print(f"Last frame: {frames[-1].name}")
    
    # Check if frames are sequential (no gaps)
    first_frame = frames[0]
    is_sequential = True
    
    # Extract frame numbers and check for gaps
    name_parts = first_frame.stem.rsplit('_', 1)
    if len(name_parts) == 2 and name_parts[1].isdigit():
        frame_numbers = []
        for frame in frames:
            parts = frame.stem.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                frame_numbers.append(int(parts[1]))
            else:
                is_sequential = False
                break
        
        # Check if there are gaps in the sequence
        if is_sequential and frame_numbers:
            expected_count = frame_numbers[-1] - frame_numbers[0] + 1
            if len(frame_numbers) != expected_count:
                is_sequential = False
                print(f"Warning: Detected gaps in frame sequence (have {len(frame_numbers)} frames, expected {expected_count})")
    else:
        is_sequential = False
    
    # Use concat method for reliability (works with gaps, non-sequential naming, etc.)
    # Create concat file
    concat_file = input_dir / "concat_list.txt"
    with open(concat_file, 'w') as f:
        for frame in frames:
            # Use absolute paths to avoid issues
            f.write(f"file '{frame.absolute()}'\n")
    
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-vf", f"scale={width}:-2,fps={fps}",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_file)
    ]
    
    print(f"\nCreating video with:")
    print(f"  FPS: {fps}")
    print(f"  Width: {width}px")
    print(f"  CRF (quality): {crf}")
    print(f"  Output: {output_file}")
    print(f"\nRunning: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n✓ Video created successfully: {output_file}")
        
        # Show file size
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"  File size: {size_mb:.2f} MB")
        
    except subprocess.CalledProcessError as e:
        print(f"Error: ffmpeg command failed with return code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: ffmpeg not found. Please install ffmpeg and ensure it's in your PATH.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Concatenate frame sequences into a video using ffmpeg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with default settings (30 fps, 1920 width)
  python append_signals.py C:\\dev\\gst-plugins-vision\\results\\20251122\\bumpy-filter
  
  # Slow motion (10 fps)
  python append_signals.py C:\\dev\\gst-plugins-vision\\results\\20251122\\bumpy-filter --fps 10
  
  # Fast playback (60 fps) with custom output name
  python append_signals.py results/20251122/bumpy-filter --fps 60 -o timelapse.mp4
  
  # Higher quality (lower CRF)
  python append_signals.py results/20251122/bumpy-filter --crf 15
  
  # Custom width
  python append_signals.py results/20251122/bumpy-filter --width 3840
  
  # Process only first 100 frames for testing
  python append_signals.py results/20251122/bumpy-filter --max-frames 100
        """
    )
    
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory containing the frame sequence"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output video file (default: output.mp4 in input directory)"
    )
    
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Output video framerate/playback speed (default: 30)"
    )
    
    parser.add_argument(
        "--width",
        type=int,
        default=1920,
        help="Output video width in pixels (default: 1920)"
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
    
    # Set output file
    if args.output is None:
        # Generate filename: input_folder_name_unixtime.mp4
        unix_time = int(time.time())
        folder_name = args.input_dir.name
        output_filename = f"{folder_name}_{unix_time}.mp4"
        output_file = args.input_dir / output_filename
    else:
        output_file = args.output
    
    # Validate CRF range
    if not 0 <= args.crf <= 51:
        print("Error: CRF must be between 0 and 51")
        sys.exit(1)
    
    create_video_ffmpeg(
        input_dir=args.input_dir,
        output_file=output_file,
        fps=args.fps,
        width=args.width,
        crf=args.crf,
        pattern=args.pattern,
        max_frames=args.max_frames
    )


if __name__ == "__main__":
    main()