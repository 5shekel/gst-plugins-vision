#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "numpy>=1.24.0",
#   "matplotlib>=3.7.0",
# ]
# ///

"""
Real-time Line Visualization for Camera Data
Displays RGB/BGR channel values across the line width in real-time

Usage: uv run visualize_line_realtime.py [--format BGR|RGB] [--port 5000]
"""

import socket
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import argparse
from collections import deque

# Parse arguments
parser = argparse.ArgumentParser(description='Real-time line channel visualization')
parser.add_argument('--format', type=str, default='BGR', choices=['BGR', 'RGB'],
                    help='Input format (default: BGR)')
parser.add_argument('--port', type=int, default=5000,
                    help='UDP port (default: 5000)')
parser.add_argument('--width', type=int, default=2456,
                    help='Line width in pixels (default: 2456)')
parser.add_argument('--fps-limit', type=int, default=30,
                    help='Maximum display fps (default: 30)')
args = parser.parse_args()

# Stream parameters
LINE_WIDTH = args.width
LINE_HEIGHT = 1
CHANNELS = 3
FRAME_SIZE = LINE_WIDTH * LINE_HEIGHT * CHANNELS

UDP_IP = "0.0.0.0"
UDP_PORT = args.port

# Create UDP socket with minimal buffer to avoid buffering old packets
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)  # Minimal buffer (64KB)
sock.setblocking(False)  # Non-blocking for animation
sock.bind((UDP_IP, UDP_PORT))

print(f"Receiving {LINE_WIDTH}x{LINE_HEIGHT} {args.format} on UDP port {UDP_PORT}")
print(f"Display update rate: {args.fps_limit} fps max")
print("Close the plot window to exit")

# Initialize plot
fig, axes = plt.subplots(2, 1, figsize=(15, 8))
fig.suptitle(f'Real-time {args.format} Channel Visualization - Line Sensor', 
             fontsize=14, fontweight='bold')

# Channel order based on format
if args.format == 'BGR':
    channel_names = ['Blue', 'Green', 'Red']
    channel_colors = ['b', 'g', 'r']
    channel_indices = [0, 1, 2]  # BGR order
else:  # RGB
    channel_names = ['Red', 'Green', 'Blue']
    channel_colors = ['r', 'g', 'b']
    channel_indices = [0, 1, 2]  # RGB order

# Initialize line data
x_data = np.arange(LINE_WIDTH)
y_data = [np.zeros(LINE_WIDTH) for _ in range(CHANNELS)]
y_grayscale = np.zeros(LINE_WIDTH)  # Combined grayscale

# Top plot - GRAYSCALE ONLY
line_gray, = axes[0].plot(x_data, y_grayscale, 'k-', linewidth=1.0)

axes[0].set_xlim(0, LINE_WIDTH)
axes[0].set_ylim(0, 255)
axes[0].set_xlabel('Pixel Position')
axes[0].set_ylabel('Grayscale Value')
axes[0].set_title('Grayscale (Luminance-weighted)')
axes[0].grid(True, alpha=0.3)

# Bottom plot - RGB/BGR channels with color
lines_separate = []
for i in range(CHANNELS):
    line, = axes[1].plot(x_data, y_data[i], channel_colors[i] + '-',
                         label=channel_names[i], alpha=0.7, linewidth=0.8)
    lines_separate.append(line)

axes[1].set_xlim(0, LINE_WIDTH)
axes[1].set_ylim(0, 255)
axes[1].set_xlabel('Pixel Position')
axes[1].set_ylabel('Pixel Value')
axes[1].set_title(f'{args.format} Channels: {" | ".join(channel_names)}')
axes[1].legend(loc='upper right')
axes[1].grid(True, alpha=0.3)

# Statistics text
stats_text = axes[0].text(0.02, 0.98, '', transform=axes[0].transAxes,
                          verticalalignment='top', fontfamily='monospace',
                          fontsize=9, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

# Frame counter
frame_count = [0]
last_update = [0]
fps_buffer = deque(maxlen=30)

# Animation update function
def update_plot(frame):
    """Update plot with new UDP data"""
    import time
    
    current_time = time.time()
    
    # Rate limiting
    if args.fps_limit > 0:
        min_interval = 1.0 / args.fps_limit
        if current_time - last_update[0] < min_interval:
            return [line_gray] + lines_separate + [stats_text]
    
    # Drain all buffered packets and only use the latest one
    latest_data = None
    packets_drained = 0
    try:
        # Read all available packets, keep only the last one
        while True:
            try:
                data, addr = sock.recvfrom(65536)
                if len(data) == FRAME_SIZE:
                    latest_data = data
                    packets_drained += 1
            except BlockingIOError:
                # No more packets available
                break
        
        # Only process if we got valid data
        if latest_data is None:
            return [line_gray] + lines_separate + [stats_text]
        
        # Parse frame
        line_data = np.frombuffer(latest_data, dtype=np.uint8).reshape((LINE_HEIGHT, LINE_WIDTH, CHANNELS))
        
        # Extract channels based on format
        for i in range(CHANNELS):
            y_data[i] = line_data[0, :, channel_indices[i]]
        
        # Calculate grayscale (luminance using standard weights for RGB)
        # For BGR: weights are [0.114, 0.587, 0.299]
        # For RGB: weights are [0.299, 0.587, 0.114]
        if args.format == 'BGR':
            y_grayscale = (0.114 * y_data[0] + 0.587 * y_data[1] + 0.299 * y_data[2])
        else:  # RGB
            y_grayscale = (0.299 * y_data[0] + 0.587 * y_data[1] + 0.114 * y_data[2])
        
        # Update top plot (grayscale only)
        line_gray.set_ydata(y_grayscale)
        
        # Update bottom plot (RGB/BGR channels)
        for i, line in enumerate(lines_separate):
            line.set_ydata(y_data[i])
        
        # Calculate statistics
        stats = []
        for i in range(CHANNELS):
            ch_data = y_data[i]
            stats.append(f"{channel_names[i]:5s}: min={ch_data.min():3d} max={ch_data.max():3d} "
                        f"mean={ch_data.mean():6.2f} std={ch_data.std():6.2f}")
        
        # Add grayscale stats
        stats.append(f"Gray : min={y_grayscale.min():6.2f} max={y_grayscale.max():6.2f} "
                    f"mean={y_grayscale.mean():6.2f} std={y_grayscale.std():6.2f}")
        
        # Calculate FPS
        frame_count[0] += 1
        if last_update[0] > 0:
            fps = 1.0 / (current_time - last_update[0])
            fps_buffer.append(fps)
            avg_fps = np.mean(fps_buffer)
        else:
            avg_fps = 0
        
        last_update[0] = current_time
        
        # Update stats text
        stats_str = f"Frame: {frame_count[0]}  FPS: {avg_fps:.1f}\n" + "\n".join(stats)
        stats_text.set_text(stats_str)
        
    except BlockingIOError:
        # No data available
        pass
    except Exception as e:
        print(f"Error: {e}")
    
    return [line_gray] + lines_separate + [stats_text]

# Set up animation with blit for better performance
ani = animation.FuncAnimation(fig, update_plot, interval=10, blit=True, cache_frame_data=False)

plt.tight_layout()
plt.show()

# Cleanup
sock.close()
print(f"\nReceived {frame_count[0]} frames total")