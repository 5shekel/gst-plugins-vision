#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///

"""
Simple UDP Receiver for port 5000 on 127.0.0.1
This uses raw sockets (built-in) - no external dependencies needed
Usage: uv run scripts/udp_sniffer_raw.py

Note: This RECEIVES UDP packets (not sniffing like pcap/scapy)
"""

import socket
import sys
from datetime import datetime

def main():
    print("=" * 70)
    print("UDP Receiver - Port 5000, 127.0.0.1")
    print("=" * 70)
    print("Press Ctrl+C to stop\n")
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        # Bind to localhost port 5000
        sock.bind(("127.0.0.1", 5000))
        print(f"Listening on 127.0.0.1:5000...\n")
        
        packet_count = 0
        while True:
            # Receive data
            data, addr = sock.recvfrom(65535)  # Max UDP packet size
            packet_count += 1
            
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] Packet #{packet_count}")
            print(f"  From: {addr[0]}:{addr[1]}")
            print(f"  Size: {len(data)} bytes")
            
            # Print first 64 bytes in hex
            hex_str = ' '.join(f'{b:02x}' for b in data[:64])
            print(f"  Data: {hex_str}{'...' if len(data) > 64 else ''}")
            
            # Try to decode as ASCII (for text data)
            try:
                text = data[:100].decode('ascii', errors='ignore').strip()
                if text and text.isprintable():
                    print(f"  Text: {text[:80]}{'...' if len(text) > 80 else ''}")
            except:
                pass
            
            print()
            
    except KeyboardInterrupt:
        print(f"\n\nReceived {packet_count} packets. Stopped by user.")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    finally:
        sock.close()

if __name__ == "__main__":
    main()