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
                    help='Save rolling display to MJPEG video file (e.g., output.avi). Uses display-fps if set, otherwise 30 fps')
args = parser.parse_args()

# Import OpenCV only if display is enabled
ENABLE_DISPLAY = not args.no_display
if ENABLE_DISPLAY:
    import cv2

# Debug flag - set to True to see frame reception details
DEBUG = False

# Line drop detection parameters
EXPECTED_FPS = 200  # Expected frame rate (from 200fps ini file)
EXPECTED_INTERVAL_MS = 1000.0 / EXPECTED_FPS  # 5ms for 200fps
DROP_THRESHOLD_MS = EXPECTED_INTERVAL_MS * 2.5  # Alert if gap > 2.5x expected (12.5ms)
STATS_WINDOW_SIZE = 100  # Track stats over last N frames
STATUS_INTERVAL = 100  # Print status every N frames

# OPTIMIZED: Using NumPy indexing instead of cv2.rotate() for better performance
# Extracting first row and reversing it is equivalent to ROTATE_90_COUNTERCLOCKWISE + first column

# Stream parameters (match your GStreamer sender)
COLUMN_WIDTH = 4  # Width from 200fps-2456x4pix-cw.ini
COLUMN_HEIGHT = 2456  # Height from 200fps-2456x4pix-cw.ini
CHANNELS = 3
FRAME_SIZE = COLUMN_WIDTH * COLUMN_HEIGHT * CHANNELS  # bytes (29472)

# Display parameters
DISPLAY_WIDTH = 800  # Width of rolling display in pixels
DISPLAY_HEIGHT = COLUMN_HEIGHT

UDP_IP = "0.0.0.0"
UDP_PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16777216)  # 16MB buffer

sock.bind((UDP_IP, UDP_PORT))

print(f"Receiving raw {COLUMN_WIDTH}x{COLUMN_HEIGHT} RGB columns on UDP port {UDP_PORT}")
if ENABLE_DISPLAY:
    if args.display_fps > 0:
        print(f"Display: ENABLED - Rolling display ({DISPLAY_WIDTH}x{DISPLAY_HEIGHT}) @ {args.display_fps} Hz (throttled)")
    else:
        print(f"Display: ENABLED - Rolling display ({DISPLAY_WIDTH}x{DISPLAY_HEIGHT}) @ full rate")
else:
    print(f"Display: DISABLED - Stats only mode (max performance)")
if DEBUG:
    print(f"Expected frame size: {FRAME_SIZE} bytes")

# Initialize display if enabled
if ENABLE_DISPLAY:
    cv2.namedWindow("Rolling Column Stream", cv2.WINDOW_NORMAL)
    rolling_buffer = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, CHANNELS), dtype=np.uint8)
    current_column = 0
    
    # Display throttling support
    if args.display_fps > 0:
        display_interval = 1.0 / args.display_fps  # seconds between display updates
        last_display_time = 0
    else:
        display_interval = 0  # Update every frame
        last_display_time = 0
    
    # MJPEG video writer setup
    video_writer = None
    if args.save_mjpeg:
        # Use display-fps if set, otherwise default to 30 fps for video
        video_fps = args.display_fps if args.display_fps > 0 else 30
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        video_writer = cv2.VideoWriter(args.save_mjpeg, fourcc, video_fps,
                                       (DISPLAY_WIDTH, DISPLAY_HEIGHT))
        print(f"Recording to: {args.save_mjpeg} @ {video_fps} fps")

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
    
    # Line drop detection
    if last_frame_time is not None:
        interval_ms = (current_time - last_frame_time) * 1000
        frame_intervals.append(interval_ms)
        
        # Detect line drop
        if interval_ms > DROP_THRESHOLD_MS:
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

    if ENABLE_DISPLAY:
        # Parse the incoming data - ALWAYS process every frame
        frame = np.frombuffer(data, dtype=np.uint8).reshape((COLUMN_WIDTH, COLUMN_HEIGHT, CHANNELS))
        
        # OPTIMIZED: Extract first row and transpose to column (equivalent to rotating and taking first column)
        # This avoids expensive cv2.rotate() - uses NumPy indexing instead
        # For ROTATE_90_COUNTERCLOCKWISE: first column of rotated = first row reversed
        column = frame[0, ::-1, :].reshape(COLUMN_HEIGHT, 1, CHANNELS)

        # Insert the single column into the rolling buffer at the current position
        # This happens for EVERY received frame
        rolling_buffer[:, current_column:current_column+1, :] = column

        # Move to the next column position, wrapping around when reaching the end
        current_column = (current_column + 1) % DISPLAY_WIDTH

        # Display throttling: only refresh display at specified rate
        # This reduces cv2.imshow() / cv2.waitKey() overhead while keeping all data
        should_display = True
        if args.display_fps > 0:
            if current_time - last_display_time >= display_interval:
                last_display_time = current_time
                should_display = True
            else:
                should_display = False
        
        if should_display:
            # Display the rolling buffer (clean, no overlays)
            cv2.imshow("Rolling Column Stream", rolling_buffer)
            
            # Write frame to video if recording
            if video_writer is not None:
                video_writer.write(rolling_buffer)

            if cv2.waitKey(1) == 27:  # ESC to quit
                break
    else:
        # No display mode - just validate the data can be reshaped
        frame = np.frombuffer(data, dtype=np.uint8).reshape((COLUMN_WIDTH, COLUMN_HEIGHT, CHANNELS))

if ENABLE_DISPLAY:
    if video_writer is not None:
        video_writer.release()
        print(f"Video saved: {args.save_mjpeg}")
    cv2.destroyAllWindows()