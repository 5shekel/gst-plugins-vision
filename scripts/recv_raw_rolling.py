#!/usr/bin/env python3
# /// script
# requires-python = "<=3.10"
# dependencies = [
#   "opencv-python",
#   "numpy",
# ]
# ///
#
# NOTE: For higher performance (?), see the Go implementation:
#       scripts/go/main.go -
#       Build: Run scripts/build_go_receiver.ps1 (Windows) or scripts/build_go_receiver.sh (Linux/macOS)
#       See scripts/go/README.md for setup instructions
#
# Usage:
#   python recv_raw_rolling.py              # With OpenCV display (default)
#   python recv_raw_rolling.py --no-display # Stats only, no display (max performance)

import socket
import numpy as np
import time
import argparse
from collections import deque

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Receive raw column stream via UDP')
parser.add_argument('--no-display', action='store_true',
                    help='Disable OpenCV display for maximum performance (stats only)')
parser.add_argument('--display-fps', type=int, default=0,
                    help='Limit display refresh rate (0=every frame, 60=60fps, etc). Reduces cv2.imshow() overhead while receiving all frames')
parser.add_argument('--save-mjpeg', type=str, default=None,
                    help='Save rolling display to MJPEG video file (e.g., output.avi). Works independently of display')
parser.add_argument('--record-fps', type=int, default=30,
                    help='Recording frame rate for --save-mjpeg (default: 30 fps). Independent of display-fps')
args = parser.parse_args()

# Import OpenCV only if display or recording is enabled
ENABLE_DISPLAY = not args.no_display
ENABLE_RECORDING = args.save_mjpeg is not None
if ENABLE_DISPLAY or ENABLE_RECORDING:
    import cv2

# Debug flag - set to True to see frame reception details
DEBUG = False

# Frame statistics parameters
STATS_WINDOW_SIZE = 100  # Track stats over last N frames
STATUS_INTERVAL = 100  # Print status every N frames
DROP_THRESHOLD_MULTIPLIER = 2.5  # Alert if gap > 2.5x rolling average
MIN_SAMPLES_FOR_DROP_DETECTION = 10  # Need at least N samples to detect drops

# OPTIMIZED: Using NumPy indexing instead of cv2.rotate() for better performance
# Extracting first row and reversing it is equivalent to ROTATE_90_COUNTERCLOCKWISE + first column

# Stream parameters (match your GStreamer sender)
# Modified to receive single line: 2456x1 instead of 4x2456
COLUMN_WIDTH = 2456  # One line width
COLUMN_HEIGHT = 1     # One line height
CHANNELS = 3
FRAME_SIZE = COLUMN_WIDTH * COLUMN_HEIGHT * CHANNELS  # bytes (7368)

# Display parameters
DISPLAY_WIDTH = 800  # Width of rolling display in pixels
DISPLAY_HEIGHT = COLUMN_WIDTH  # 2456 pixels tall (the line width becomes display height)

UDP_IP = "0.0.0.0"
UDP_PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16777216)  # 16MB buffer

sock.bind((UDP_IP, UDP_PORT))

print(f"Receiving raw {COLUMN_WIDTH}x{COLUMN_HEIGHT} BGR line on UDP port {UDP_PORT}")
if ENABLE_DISPLAY:
    if args.display_fps > 0:
        print(f"Display: ENABLED - Rolling display ({DISPLAY_WIDTH}x{DISPLAY_HEIGHT}) @ {args.display_fps} Hz (throttled)")
    else:
        print(f"Display: ENABLED - Rolling display ({DISPLAY_WIDTH}x{DISPLAY_HEIGHT}) @ full rate")
else:
    print(f"Display: DISABLED")
if ENABLE_RECORDING:
    print(f"Recording: ENABLED - {args.save_mjpeg} @ {args.record_fps} fps")
else:
    print(f"Recording: DISABLED")
if DEBUG:
    print(f"Expected frame size: {FRAME_SIZE} bytes")

# Initialize display if enabled
display_buffer_obj = None
display_current_column = 0
last_display_time = 0
display_interval = 0

if ENABLE_DISPLAY:
    cv2.namedWindow("Rolling Column Stream", cv2.WINDOW_NORMAL)
    display_buffer_obj = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, CHANNELS), dtype=np.uint8)
    
    # Display throttling support
    if args.display_fps > 0:
        display_interval = 1.0 / args.display_fps  # seconds between display updates
    else:
        display_interval = 0  # Update every frame

# Initialize recording if enabled (independent of display)
record_buffer_obj = None
record_current_column = 0
last_record_time = 0
record_interval = 0
video_writer = None

if ENABLE_RECORDING:
    record_buffer_obj = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, CHANNELS), dtype=np.uint8)
    record_interval = 1.0 / args.record_fps if args.record_fps > 0 else 0
    
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    video_writer = cv2.VideoWriter(args.save_mjpeg, fourcc, args.record_fps,
                                   (DISPLAY_WIDTH, DISPLAY_HEIGHT))
    print(f"Recording initialized: {args.save_mjpeg} @ {args.record_fps} fps")

frame_count = 0

# Line drop detection state
last_frame_time = None
first_frame_time = None
frame_intervals = deque(maxlen=STATS_WINDOW_SIZE)
total_drops = 0
drops_since_last_status = 0

while True:
    current_time = time.time()
    data, addr = sock.recvfrom(65536)
    
    if len(data) != FRAME_SIZE:
        if DEBUG:
            print(f"Received {len(data)} bytes (expected {FRAME_SIZE}), skipping...")
        continue
    
    # Initialize timing on first frame
    if first_frame_time is None:
        first_frame_time = current_time
    
    # Frame interval tracking and drop detection
    if last_frame_time is not None:
        interval_ms = (current_time - last_frame_time) * 1000
        frame_intervals.append(interval_ms)
        
        # Detect drops based on rolling average (only after we have enough samples)
        if len(frame_intervals) >= MIN_SAMPLES_FOR_DROP_DETECTION:
            avg_interval = np.mean(frame_intervals)
            drop_threshold = avg_interval * DROP_THRESHOLD_MULTIPLIER
            if interval_ms > drop_threshold:
                total_drops += 1
                drops_since_last_status += 1
    
    last_frame_time = current_time
    frame_count += 1
    
    # Print status every STATUS_INTERVAL frames
    if frame_count % STATUS_INTERVAL == 0:
        elapsed_time = current_time - first_frame_time
        real_fps = frame_count / elapsed_time if elapsed_time > 0 else 0
        avg_interval = np.mean(frame_intervals) if len(frame_intervals) > 0 else 0
        instant_fps = 1000.0 / avg_interval if avg_interval > 0 else 0
        
        status = f"Frame {frame_count}: Real FPS: {real_fps:.1f} | Instant: {instant_fps:.1f}"
        if drops_since_last_status > 0:
            status += f" | ⚠️  {drops_since_last_status} drops detected"
            drops_since_last_status = 0
        else:
            status += f" | Total drops: {total_drops}"
        
        print(status)

    # Parse the incoming data - process for display and/or recording
    if ENABLE_DISPLAY or ENABLE_RECORDING:
        # Receiving 2456x1 line directly - reshape as a vertical column
        # Input is 2456 pixels wide x 1 pixel tall, we want it as 2456 tall x 1 wide
        frame = np.frombuffer(data, dtype=np.uint8).reshape((COLUMN_HEIGHT, COLUMN_WIDTH, CHANNELS))
        
        # Transpose to vertical and flip to correct 180-degree rotation: (1, 2456, 3) -> (2456, 1, 3) flipped
        column = frame.transpose(1, 0, 2)[::-1]
    
    # Update display buffer and show if enabled
    if ENABLE_DISPLAY:
        # Insert the single column into the display rolling buffer
        display_buffer_obj[:, display_current_column:display_current_column+1, :] = column
        display_current_column = (display_current_column - 1) % DISPLAY_WIDTH

        # Display throttling: only refresh display at specified rate
        should_display = True
        if args.display_fps > 0:
            if current_time - last_display_time >= display_interval:
                last_display_time = current_time
                should_display = True
            else:
                should_display = False
        
        if should_display:
            # Flip horizontally for display to correct orientation (using efficient slicing)
            display_frame = display_buffer_obj[:, ::-1]
            cv2.imshow("Rolling Column Stream", display_frame)

            if cv2.waitKey(1) == 27:  # ESC to quit
                break
    
    # Update recording buffer and write if enabled (independent of display)
    if ENABLE_RECORDING:
        # Insert the single column into the recording rolling buffer
        record_buffer_obj[:, record_current_column:record_current_column+1, :] = column
        record_current_column = (record_current_column - 1) % DISPLAY_WIDTH
        
        # Recording throttling: only write frames at specified rate
        should_record = True
        if record_interval > 0:
            if current_time - last_record_time >= record_interval:
                last_record_time = current_time
                should_record = True
            else:
                should_record = False
        
        if should_record and video_writer is not None:
            # Flip horizontally for recording to correct orientation
            record_frame = record_buffer_obj[:, ::-1]
            video_writer.write(record_frame)
    
    # For stats-only mode, just validate the data can be reshaped
    if not ENABLE_DISPLAY and not ENABLE_RECORDING:
        frame = np.frombuffer(data, dtype=np.uint8).reshape((COLUMN_HEIGHT, COLUMN_WIDTH, CHANNELS))

# Cleanup
if video_writer is not None:
    video_writer.release()
    print(f"Video saved: {args.save_mjpeg}")

if ENABLE_DISPLAY:
    cv2.destroyAllWindows()