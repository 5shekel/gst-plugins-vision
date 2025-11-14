#!/usr/bin/env python3
# /// script
# requires-python = "<=3.10"
# dependencies = [
#   "opencv-python",
#   "numpy",
# ]
# ///

import socket
import numpy as np
import cv2

# Debug flag - set to True to see frame reception details
DEBUG = False

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

while True:
    data, addr = sock.recvfrom(65536)
    
    if len(data) != FRAME_SIZE:
        if DEBUG:
            print(f"Received {len(data)} bytes (expected {FRAME_SIZE}), skipping...")
        continue
    
    if DEBUG:
        frame_count += 1
        if frame_count % 30 == 0:
            print(f"Received {frame_count} frames, current column: {current_column}")

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

    # Display the rolling buffer
    cv2.imshow("Rolling Column Stream", rolling_buffer)

    if cv2.waitKey(1) == 27:  # ESC to quit
        break

cv2.destroyAllWindows()