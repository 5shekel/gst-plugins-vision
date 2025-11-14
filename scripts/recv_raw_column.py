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

# Stream parameters (match your GStreamer sender)
WIDTH = 1
HEIGHT = 640  # Default videotestsrc height
CHANNELS = 3
FRAME_SIZE = WIDTH * HEIGHT * CHANNELS  # bytes

UDP_IP = "0.0.0.0"
UDP_PORT = 5000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Receiving raw {WIDTH}x{HEIGHT} RGB frames on UDP port {UDP_PORT}")
if DEBUG:
    print(f"Expected frame size: {FRAME_SIZE} bytes")

cv2.namedWindow("Raw Column Stream", cv2.WINDOW_NORMAL)

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
            print(f"Received {frame_count} frames")

    frame = np.frombuffer(data, dtype=np.uint8).reshape((HEIGHT, WIDTH, CHANNELS))

    # scale for visibility
    frame_large = cv2.resize(
        frame, (200, HEIGHT), interpolation=cv2.INTER_NEAREST
    )

    cv2.imshow("Raw Column Stream", frame_large)

    if cv2.waitKey(1) == 27:  # ESC to quit
        break

cv2.destroyAllWindows()
