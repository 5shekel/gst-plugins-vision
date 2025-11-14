#!/usr/bin/env python3
# /// script
# requires-python = "<=3.10"
# dependencies = [
#   "opencv-python",
#   "numpy",
# ]
# ///
#
# NOTE: For higher performance (200+ fps), see the Go implementation:
#       scripts/go/main.go - Significantly faster, handles 200+ fps easily
#       Build: Run scripts/build_go_receiver.ps1 (Windows) or scripts/build_go_receiver.sh (Linux/macOS)
#       See scripts/go/README.md for setup instructions

import socket
import numpy as np
import cv2
import time
from collections import deque

# Debug flag - set to True to see frame reception details
DEBUG = False

# Line drop detection parameters
EXPECTED_FPS = 200  # Expected frame rate (from 200fps ini file)
EXPECTED_INTERVAL_MS = 1000.0 / EXPECTED_FPS  # 5ms for 200fps
DROP_THRESHOLD_MS = EXPECTED_INTERVAL_MS * 2.5  # Alert if gap > 2.5x expected (12.5ms)
STATS_WINDOW_SIZE = 100  # Track stats over last N frames
STATUS_INTERVAL = 100  # Print status every N frames

# Rotation mode - set to rotate incoming data before display
# Options: None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180
ROTATION = cv2.ROTATE_90_COUNTERCLOCKWISE  # Rotate rows to columns

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
print(f"Display width: {DISPLAY_WIDTH} pixels (rolling)")
if DEBUG:
    print(f"Expected frame size: {FRAME_SIZE} bytes")

cv2.namedWindow("Rolling Column Stream", cv2.WINDOW_NORMAL)

# Initialize the rolling buffer
rolling_buffer = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, CHANNELS), dtype=np.uint8)
current_column = 0
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

    # Parse the incoming data
    frame = np.frombuffer(data, dtype=np.uint8).reshape((COLUMN_WIDTH, COLUMN_HEIGHT, CHANNELS))
    
    # Apply rotation if configured
    if ROTATION is not None:
        rotated = cv2.rotate(frame, ROTATION)
    else:
        rotated = frame
    
    # Extract only the first column for smoother rolling (1 pixel/frame)
    column = rotated[:, 0:1, :]

    # Insert the single column into the rolling buffer at the current position
    rolling_buffer[:, current_column:current_column+1, :] = column

    # Move to the next column position, wrapping around when reaching the end
    current_column = (current_column + 1) % DISPLAY_WIDTH

    # Display the rolling buffer (clean, no overlays)
    cv2.imshow("Rolling Column Stream", rolling_buffer)

    if cv2.waitKey(1) == 27:  # ESC to quit
        break

cv2.destroyAllWindows()