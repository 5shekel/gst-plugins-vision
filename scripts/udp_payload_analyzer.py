#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "numpy",
# ]
# ///

"""
UDP Payload Analyzer for GStreamer Raw Video
Analyzes UDP packets on port 5000 and reports on payload structure

Based on docs/network_guide.md:
- Real data: 2456x1 BGR (7368 bytes per line)
- Demo data: 1x640 RGB (1920 bytes per frame)

Usage: uv run scripts/udp_payload_analyzer.py
"""

import socket
import sys
import struct
import numpy as np
from datetime import datetime
from collections import defaultdict

class PayloadAnalyzer:
    def __init__(self):
        self.packet_sizes = defaultdict(int)
        self.total_packets = 0
        self.total_bytes = 0
        
    def analyze_gstreamer_header(self, data):
        """Try to detect and parse GStreamer RTP/UDP headers"""
        info = {}
        
        # Check if it's RTP (GStreamer sometimes uses RTP)
        if len(data) >= 12:
            # RTP header format
            byte0 = data[0]
            version = (byte0 >> 6) & 0x03
            padding = (byte0 >> 5) & 0x01
            extension = (byte0 >> 4) & 0x01
            csrc_count = byte0 & 0x0F
            
            if version == 2:  # RTP version 2
                info['protocol'] = 'RTP'
                info['version'] = version
                info['padding'] = bool(padding)
                info['extension'] = bool(extension)
                
                byte1 = data[1]
                info['marker'] = bool(byte1 >> 7)
                info['payload_type'] = byte1 & 0x7F
                
                info['sequence'] = struct.unpack('!H', data[2:4])[0]
                info['timestamp'] = struct.unpack('!I', data[4:8])[0]
                info['ssrc'] = struct.unpack('!I', data[8:12])[0]
                
                payload_offset = 12 + (csrc_count * 4)
                info['header_size'] = payload_offset
                info['payload_size'] = len(data) - payload_offset
                
                return info, payload_offset
        
        # Raw video data (no RTP)
        info['protocol'] = 'RAW'
        info['header_size'] = 0
        info['payload_size'] = len(data)
        return info, 0
    
    def analyze_video_payload(self, data, offset=0):
        """Analyze raw video data"""
        payload = data[offset:]
        size = len(payload)
        
        analysis = {
            'size': size,
            'format': 'unknown'
        }
        
        # Check for known video formats from docs/network_guide.md
        if size == 7368:  # 2456 × 1 × 3 (BGR)
            analysis['format'] = 'BGR'
            analysis['width'] = 2456
            analysis['height'] = 1
            analysis['channels'] = 3
            analysis['description'] = 'Real camera data - Single line 2456x1 BGR'
            
        elif size == 1920:  # 1 × 640 × 3 (RGB)
            analysis['format'] = 'RGB'
            analysis['width'] = 1
            analysis['height'] = 640
            analysis['channels'] = 3
            analysis['description'] = 'Demo data - Single column 1x640 RGB'
            
        else:
            # Try to guess format
            # Common raw video sizes
            possible_formats = []
            
            # Try BGR/RGB (3 channels)
            if size % 3 == 0:
                pixels = size // 3
                possible_formats.append(f'{pixels} pixels @ 3 channels (BGR/RGB)')
                
            # Try GRAY (1 channel)
            possible_formats.append(f'{size} pixels @ 1 channel (GRAY)')
            
            # Try RGBA (4 channels)
            if size % 4 == 0:
                pixels = size // 4
                possible_formats.append(f'{pixels} pixels @ 4 channels (RGBA)')
            
            analysis['possible_formats'] = possible_formats
        
        # Pixel statistics (if manageable size)
        if size <= 100000:  # Only analyze if < 100KB
            try:
                if 'channels' in analysis and analysis['channels'] == 3:
                    # Reshape as color image
                    pixels = size // 3
                    arr = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3)
                    
                    analysis['pixel_stats'] = {
                        'min': [int(arr[:, i].min()) for i in range(3)],
                        'max': [int(arr[:, i].max()) for i in range(3)],
                        'mean': [float(arr[:, i].mean()) for i in range(3)],
                        'std': [float(arr[:, i].std()) for i in range(3)]
                    }
                else:
                    # Treat as grayscale
                    arr = np.frombuffer(payload, dtype=np.uint8)
                    analysis['pixel_stats'] = {
                        'min': int(arr.min()),
                        'max': int(arr.max()),
                        'mean': float(arr.mean()),
                        'std': float(arr.std())
                    }
            except:
                pass
        
        # First 32 bytes in hex
        hex_preview = ' '.join(f'{b:02x}' for b in payload[:32])
        analysis['hex_preview'] = hex_preview + ('...' if size > 32 else '')
        
        return analysis
    
    def print_report(self, packet_num, addr, data):
        """Print detailed analysis report"""
        self.total_packets += 1
        self.total_bytes += len(data)
        self.packet_sizes[len(data)] += 1
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        print("=" * 80)
        print(f"PACKET #{packet_num} @ {timestamp}")
        print("=" * 80)
        print(f"Source: {addr[0]}:{addr[1]}")
        print(f"Total Size: {len(data)} bytes")
        print()
        
        # Analyze header
        header_info, payload_offset = self.analyze_gstreamer_header(data)
        
        print("PROTOCOL ANALYSIS:")
        print("-" * 80)
        for key, value in header_info.items():
            print(f"  {key:20s}: {value}")
        print()
        
        # Analyze video payload
        video_info = self.analyze_video_payload(data, payload_offset)
        
        print("VIDEO PAYLOAD ANALYSIS:")
        print("-" * 80)
        
        if 'description' in video_info:
            print(f"  📹 {video_info['description']}")
            print(f"  Format: {video_info['format']}")
            print(f"  Dimensions: {video_info['width']}x{video_info['height']}")
            print(f"  Channels: {video_info['channels']}")
        else:
            print(f"  Size: {video_info['size']} bytes")
            if 'possible_formats' in video_info:
                print(f"  Possible formats:")
                for fmt in video_info['possible_formats']:
                    print(f"    - {fmt}")
        
        print()
        
        if 'pixel_stats' in video_info:
            print("PIXEL STATISTICS:")
            print("-" * 80)
            stats = video_info['pixel_stats']
            if isinstance(stats['min'], list):
                # Color image (BGR/RGB)
                channels = ['Channel 0 (B/R)', 'Channel 1 (G)', 'Channel 2 (R/B)']
                for i, ch in enumerate(channels):
                    print(f"  {ch:20s}: min={stats['min'][i]:3d}, max={stats['max'][i]:3d}, mean={stats['mean'][i]:6.2f}, std={stats['std'][i]:6.2f}")
            else:
                # Grayscale
                print(f"  Grayscale: min={stats['min']}, max={stats['max']}, mean={stats['mean']:.2f}, std={stats['std']:.2f}")
            print()
        
        print("HEX PREVIEW (first 32 bytes):")
        print("-" * 80)
        print(f"  {video_info['hex_preview']}")
        print()
        
    def print_summary(self):
        """Print statistics summary"""
        print("\n" + "=" * 80)
        print("SESSION SUMMARY")
        print("=" * 80)
        print(f"Total Packets: {self.total_packets}")
        print(f"Total Bytes: {self.total_bytes:,}")
        print(f"Average Packet Size: {self.total_bytes / max(self.total_packets, 1):.2f} bytes")
        print()
        print("Packet Size Distribution:")
        for size in sorted(self.packet_sizes.keys()):
            count = self.packet_sizes[size]
            print(f"  {size:6d} bytes: {count:4d} packets")
        print()

def main():
    print("=" * 80)
    print("UDP PAYLOAD ANALYZER - Port 5000, 127.0.0.1")
    print("Specialized for GStreamer Raw Video Analysis")
    print("=" * 80)
    print("Press Ctrl+C to stop and see summary\n")
    
    analyzer = PayloadAnalyzer()
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        sock.bind(("127.0.0.1", 5000))
        print(f"Listening on 127.0.0.1:5000...\n")
        print("Waiting for packets...\n")
        
        packet_count = 0
        while True:
            data, addr = sock.recvfrom(65535)
            packet_count += 1
            
            analyzer.print_report(packet_count, addr, data)
            
            # Print summary every 100 packets
            if packet_count % 100 == 0:
                print(f"\n[Received {packet_count} packets so far... continuing capture]\n")
            
    except KeyboardInterrupt:
        print("\n\nCapture stopped by user.")
        analyzer.print_summary()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    finally:
        sock.close()

if __name__ == "__main__":
    main()