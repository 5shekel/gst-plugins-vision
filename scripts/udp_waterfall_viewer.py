#!/usr/bin/env python3
# /// script
# requires-python = "==3.10"
# dependencies = [
#   "numpy",
#   "matplotlib",
#   "scipy",
# ]
# ///

"""
UDP Waterfall Viewer with Signal/Blob Detection
Receives line scan data from port 5000 and displays as scrolling waterfall plot

Based on network_guide.md:
- Real data: 2456x1 BGR (7368 bytes per line)
- Each UDP packet = one line of the waterfall

Features:
- Real-time waterfall visualization
- Blob/signal detection with threshold
- Automatic contrast adjustment
- Rolling buffer for smooth display

Usage: uv run scripts/udp_waterfall_viewer.py
Press 'q' to quit, 't' to adjust threshold
"""

import socket
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Rectangle
from scipy import ndimage
from datetime import datetime
from collections import deque

class WaterfallViewer:
    def __init__(self, buffer_lines=500, width=2456, threshold_percentile=95):
        """
        Initialize waterfall viewer
        
        Args:
            buffer_lines: Number of lines to keep in buffer (displayed horizontally)
            width: Expected line width (2456 for real camera, displayed vertically)
            threshold_percentile: Percentile for blob detection threshold
        """
        self.buffer_lines = buffer_lines
        self.width = width
        self.threshold_percentile = threshold_percentile
        
        # Pre-allocated numpy array for waterfall display (faster than deque)
        self.waterfall_buffer = np.zeros((width, buffer_lines), dtype=np.uint8)
        self.buffer_index = 0  # Current position in circular buffer
        self.buffer_filled = False  # Track if buffer has wrapped around
        
        # Statistics
        self.packet_count = 0
        self.dropped_packets = 0
        self.blob_count = 0
        self.start_time = datetime.now()
        self.last_fps_update = datetime.now()
        self.frames_since_update = 0
        self.current_fps = 0.0
        
        # UDP socket with larger buffer
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2*1024*1024)  # 2MB buffer
        self.sock.bind(("127.0.0.1", 5000))
        self.sock.settimeout(0.01)  # 10ms timeout for better responsiveness
        
        # Blob detection parameters
        self.min_blob_size = 5  # Minimum pixels for a blob
        self.blob_history = deque(maxlen=100)  # Track recent blobs
        
        # Adaptive threshold caching (recalculate only every N frames)
        self.cached_threshold = 0
        self.threshold_update_counter = 0
        self.threshold_update_interval = 5  # Update threshold every 5 frames
        
        print("=" * 70)
        print("UDP Waterfall Viewer - Signal/Blob Detection")
        print("=" * 70)
        print(f"Listening on 127.0.0.1:5000")
        print(f"Buffer: {buffer_lines} lines, Width: {width} pixels")
        print(f"Threshold: {threshold_percentile}th percentile")
        print(f"Min blob size: {self.min_blob_size} pixels")
        print("=" * 70)
        print("Controls:")
        print("  q - Quit")
        print("  t/T - Decrease/Increase threshold")
        print("  +/- - Adjust min blob size")
        print("=" * 70)
        print()
    
    def bgr_to_gray(self, bgr_data):
        """Convert BGR line to grayscale using luminosity formula"""
        # BGR order: Blue, Green, Red
        bgr = np.frombuffer(bgr_data, dtype=np.uint8).reshape(-1, 3)
        # Luminosity: 0.114*B + 0.587*G + 0.299*R
        gray = (0.114 * bgr[:, 0] + 0.587 * bgr[:, 1] + 0.299 * bgr[:, 2]).astype(np.uint8)
        return gray
    
    def detect_blobs(self, line_data, threshold):
        """
        Detect blobs/signals in a line using threshold
        
        Returns: List of (start_idx, end_idx, max_value) tuples
        """
        # Threshold the line
        binary = line_data > threshold
        
        # Find connected components
        labeled, num_features = ndimage.label(binary)
        
        blobs = []
        for i in range(1, num_features + 1):
            blob_mask = labeled == i
            blob_size = np.sum(blob_mask)
            
            if blob_size >= self.min_blob_size:
                indices = np.where(blob_mask)[0]
                start_idx = int(indices[0])
                end_idx = int(indices[-1])
                max_value = int(np.max(line_data[blob_mask]))
                blobs.append((start_idx, end_idx, max_value))
        
        return blobs
    
    def receive_line(self):
        """Receive one line from UDP socket"""
        try:
            data, addr = self.sock.recvfrom(65535)
            
            # Check if it's the expected size (7368 bytes = 2456x1x3 BGR)
            if len(data) == 7368:
                gray = self.bgr_to_gray(data)
                
                # Verify width matches
                if len(gray) == self.width:
                    self.packet_count += 1
                    return gray
                else:
                    self.dropped_packets += 1
            else:
                self.dropped_packets += 1
                
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Error receiving: {e}")
        
        return None
    
    def update_display(self, frame):
        """Animation update function - optimized for live updates"""
        # Process ALL available data in socket buffer (not just a fixed number)
        lines_received = 0
        recent_line = None
        
        # Keep receiving until socket is empty (with timeout)
        max_lines_per_frame = 100  # Safety limit
        while lines_received < max_lines_per_frame:
            line = self.receive_line()
            if line is None:
                break
            
            # Add to circular buffer
            self.waterfall_buffer[:, self.buffer_index] = line
            recent_line = line
            
            self.buffer_index = (self.buffer_index + 1) % self.buffer_lines
            if self.buffer_index == 0:
                self.buffer_filled = True
            
            lines_received += 1
        
        # Track FPS
        self.frames_since_update += 1
        now = datetime.now()
        fps_elapsed = (now - self.last_fps_update).total_seconds()
        if fps_elapsed >= 1.0:  # Update FPS once per second
            self.current_fps = self.frames_since_update / fps_elapsed
            self.frames_since_update = 0
            self.last_fps_update = now
        
        # Return early if no data
        if not self.buffer_filled and self.buffer_index == 0:
            return [self.im]
        
        # Get current view of buffer (reorder to show newest on right)
        if self.buffer_filled:
            # Buffer has wrapped, reorder it
            waterfall = np.hstack([
                self.waterfall_buffer[:, self.buffer_index:],
                self.waterfall_buffer[:, :self.buffer_index]
            ])
        else:
            # Buffer not full yet, just use what we have
            waterfall = self.waterfall_buffer[:, :self.buffer_index]
        
        # Update threshold periodically (not every frame for performance)
        self.threshold_update_counter += 1
        if self.threshold_update_counter >= self.threshold_update_interval or self.cached_threshold == 0:
            self.cached_threshold = np.percentile(waterfall, self.threshold_percentile)
            self.threshold_update_counter = 0
        
        # Detect blobs in the most recent line
        if lines_received > 0 and recent_line is not None:
            blobs = self.detect_blobs(recent_line, self.cached_threshold)
            
            if len(blobs) > 0:
                self.blob_count += len(blobs)
                self.blob_history.append({
                    'time': now,
                    'count': len(blobs),
                    'blobs': blobs
                })
        
        # Update image (no need to transpose, already in correct orientation)
        self.im.set_data(waterfall)
        
        # Update contrast limits less frequently for performance
        if self.threshold_update_counter == 0:
            self.im.set_clim(vmin=np.percentile(waterfall, 1),
                           vmax=np.percentile(waterfall, 99))
        
        # Update title with live statistics
        elapsed = (now - self.start_time).total_seconds()
        avg_fps = self.packet_count / max(elapsed, 0.001)
        
        title_str = f"Waterfall - {self.packet_count} lines | Avg: {avg_fps:.1f} l/s | Live: {self.current_fps:.1f} fps"
        if lines_received > 0:
            title_str += f" | NEW: {lines_received}"
        if self.blob_count > 0:
            title_str += f" | BLOBS: {self.blob_count}"
        self.title.set_text(title_str)
        
        # Update statistics
        stats_str = f"Threshold: {self.cached_threshold:.1f} ({self.threshold_percentile}th %ile) | Min blob: {self.min_blob_size}px"
        if len(self.blob_history) > 0:
            recent_blobs = sum(b['count'] for b in list(self.blob_history)[-10:])
            stats_str += f"\nRecent blobs (last 10 lines): {recent_blobs}"
        if self.dropped_packets > 0:
            stats_str += f" | WARNING: Dropped: {self.dropped_packets}"
        self.stats_text.set_text(stats_str)
        
        # Return only the image for blit (title and stats are figure elements)
        return [self.im]
    
    def on_key(self, event):
        """Handle keyboard events"""
        if event.key == 'q':
            plt.close('all')
            sys.exit(0)
        elif event.key == 't':
            self.threshold_percentile = max(50, self.threshold_percentile - 5)
            print(f"Threshold: {self.threshold_percentile}th percentile")
        elif event.key == 'T':
            self.threshold_percentile = min(99, self.threshold_percentile + 5)
            print(f"Threshold: {self.threshold_percentile}th percentile")
        elif event.key == '+' or event.key == '=':
            self.min_blob_size += 1
            print(f"Min blob size: {self.min_blob_size} pixels")
        elif event.key == '-':
            self.min_blob_size = max(1, self.min_blob_size - 1)
            print(f"Min blob size: {self.min_blob_size} pixels")
    
    def run(self):
        """Start the waterfall display"""
        # Create figure and axis
        self.fig, self.ax = plt.subplots(figsize=(14, 8))
        self.fig.canvas.manager.set_window_title('UDP Waterfall Viewer')
        
        # Initialize with empty data (transposed: height=pixels, width=time)
        initial_data = np.zeros((self.width, self.buffer_lines), dtype=np.uint8)
        
        # Create image
        self.im = self.ax.imshow(initial_data, aspect='auto', cmap='viridis', 
                                interpolation='nearest', origin='upper')
        
        # Setup axes (time flows left to right)
        self.ax.set_xlabel('Time (line number) →')
        self.ax.set_ylabel('Pixel Position')
        self.title = self.ax.set_title('Waiting for data...')
        
        # Add colorbar
        cbar = plt.colorbar(self.im, ax=self.ax, label='Intensity')
        
        # Add statistics text
        self.stats_text = self.fig.text(0.02, 0.02, '', fontsize=8, 
                                       family='monospace',
                                       bbox=dict(boxstyle='round', 
                                               facecolor='wheat', 
                                               alpha=0.5))
        
        # Connect keyboard events
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        
        # Setup animation with faster update rate for live display
        # Keep reference to prevent garbage collection
        self.ani = animation.FuncAnimation(self.fig, self.update_display,
                                          interval=16,  # ~60 FPS for smoother live updates
                                          blit=False,  # Disable blit for title/stats updates
                                          cache_frame_data=False)
        
        plt.tight_layout()
        plt.show()
    
    def cleanup(self):
        """Cleanup resources"""
        self.sock.close()
        
        print("\n" + "=" * 70)
        print("SESSION SUMMARY")
        print("=" * 70)
        print(f"Total lines received: {self.packet_count}")
        print(f"Dropped packets: {self.dropped_packets}")
        print(f"Total blobs detected: {self.blob_count}")
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print(f"Duration: {elapsed:.1f} seconds")
        print(f"Average rate: {self.packet_count / max(elapsed, 0.001):.1f} lines/sec")
        print("=" * 70)

def main():
    viewer = WaterfallViewer(
        buffer_lines=500,      # Show 500 lines at once
        width=2456,            # Camera line width
        threshold_percentile=95  # Start with 95th percentile threshold
    )
    
    try:
        viewer.run()
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        viewer.cleanup()

if __name__ == "__main__":
    main()