
#!/usr/bin/env python3
# /// script
# requires-python = "==3.13"
# dependencies = []
# ///
#
# IDS uEye Camera Control Script with UDP Exposure Control
#
# This script streams video from an IDS uEye camera via UDP and provides
# a UDP control interface for dynamically adjusting exposure and framerate.
#
# Setup:
#   Run with: . .\scripts\setup_gstreamer_env.ps1 && uv run .\scripts\launch-ids.py
#
# Features:
#   - Video streaming on UDP port 5000 (127.0.0.1)
#   - Control interface on UDP port 5001 (0.0.0.0)
#   - Dynamic exposure control (0.001-1.0 seconds)
#   - Dynamic framerate control (1-500 fps)
#
# Control Commands:
#   SET_EXPOSURE <value>  - Set exposure in seconds (e.g., 0.016)
#   GET_EXPOSURE          - Get current exposure value
#   SET_FRAMERATE <value> - Set framerate in Hz (e.g., 30)
#   GET_FRAMERATE         - Get current framerate
#   STATUS                - Get pipeline status and current settings
#
# Example Usage:
#   echo "SET_EXPOSURE 0.010" | nc -u 127.0.0.1 5001
#   echo "GET_EXPOSURE" | nc -u 127.0.0.1 5001
#
# Testing:
#   Run test client: uv run .\scripts\test_exposure_control.py
#
# Documentation:
#   See scripts/UDP_CONTROL_PROTOCOL.md for full protocol details
#
# Add GStreamer Python packages
import os
import sys
import socket
import threading

# Check for required environment variable
gst_root = os.environ.get("GSTREAMER_1_0_ROOT_MSVC_X86_64")
if not gst_root:
    print("ERROR: GSTREAMER_1_0_ROOT_MSVC_X86_64 environment variable is not set")
    print("Expected: C:\\bin\\gstreamer\\1.0\\msvc_x86_64\\")
    print("Please run: . .\\scripts\\setup_gstreamer_env.ps1")
    sys.exit(1)
else:
    # Remove trailing backslash if present
    gst_root = gst_root.rstrip("\\")

    gst_site_packages = os.path.join(gst_root, "lib", "site-packages")
    sys.path.insert(0, gst_site_packages)

    # Add GI typelibs
    os.environ["GI_TYPELIB_PATH"] = os.path.join(gst_root, "lib", "girepository-1.0")

    # Add GStreamer DLL bin directory
    os.environ["PATH"] = os.path.join(gst_root, "bin") + ";" + os.environ["PATH"]

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

class ControlServer:
    """UDP server for controlling camera parameters during runtime"""
    
    def __init__(self, src, pipeline=None, port=5001):
        self.src = src
        self.pipeline = pipeline
        self.port = port
        self.running = False
        self.sock = None
        self.thread = None
    
    def start(self):
        """Start the control server in a separate thread"""
        self.running = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop the control server"""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        if self.thread:
            self.thread.join(timeout=2.0)
    
    def run(self):
        """Main server loop"""
        try:
            # Create UDP socket
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(0.5)  # Non-blocking with timeout
            
            try:
                self.sock.bind(("0.0.0.0", self.port))
            except OSError as e:
                print(f"ERROR: Could not bind control server to port {self.port}: {e}")
                print("Control server disabled. Video streaming will continue.")
                return
            
            print(f"Control server listening on UDP port {self.port}")
            print("  Commands: SET_EXPOSURE <val>, GET_EXPOSURE, SET_FRAMERATE <val>, GET_FRAMERATE, STATUS")
            
            while self.running:
                try:
                    # Receive command
                    data, addr = self.sock.recvfrom(1024)
                    command = data.decode('utf-8', errors='ignore').strip()
                    
                    if command:
                        # Process command
                        response = self.process_command(command, addr)
                        
                        # Send response
                        self.send_response(response, addr)
                
                except socket.timeout:
                    # Normal timeout, continue loop
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Control server error: {e}")
        
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
    
    def process_command(self, command, addr):
        """Process incoming command and return response"""
        try:
            parts = command.strip().upper().split()
            if not parts:
                return "ERROR INVALID_SYNTAX: Empty command"
            
            cmd = parts[0]
            
            if cmd == "SET_EXPOSURE":
                return self.handle_set_exposure(parts)
            elif cmd == "GET_EXPOSURE":
                return self.handle_get_exposure()
            elif cmd == "SET_FRAMERATE":
                return self.handle_set_framerate(parts)
            elif cmd == "GET_FRAMERATE":
                return self.handle_get_framerate()
            elif cmd == "STATUS":
                return self.handle_status()
            else:
                return f"ERROR INVALID_COMMAND: Unknown command '{cmd}'"
        
        except Exception as e:
            return f"ERROR PROCESSING: {str(e)}"
    
    def handle_set_exposure(self, parts):
        """Handle SET_EXPOSURE command"""
        if len(parts) != 2:
            return "ERROR INVALID_SYNTAX: Usage: SET_EXPOSURE <value>"
        
        try:
            value = float(parts[1])
            if value < 0.001 or value > 1.0:
                return "ERROR OUT_OF_RANGE: Exposure must be 0.001-1.0 seconds"
            
            self.src.set_property("exposure", value)
            # Verify the value was set
            actual = self.src.get_property("exposure")
            return f"OK {actual}"
        
        except ValueError:
            return "ERROR INVALID_SYNTAX: Exposure must be a number"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_get_exposure(self):
        """Handle GET_EXPOSURE command"""
        try:
            value = self.src.get_property("exposure")
            return f"OK {value}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_set_framerate(self, parts):
        """Handle SET_FRAMERATE command"""
        if len(parts) != 2:
            return "ERROR INVALID_SYNTAX: Usage: SET_FRAMERATE <value>"
        
        try:
            value = float(parts[1])
            if value < 1.0 or value > 500.0:
                return "ERROR OUT_OF_RANGE: Framerate must be 1.0-500.0 Hz"
            
            self.src.set_property("framerate", value)
            actual = self.src.get_property("framerate")
            return f"OK {actual}"
        
        except ValueError:
            return "ERROR INVALID_SYNTAX: Framerate must be a number"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_get_framerate(self):
        """Handle GET_FRAMERATE command"""
        try:
            value = self.src.get_property("framerate")
            return f"OK {value}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_status(self):
        """Handle STATUS command"""
        try:
            exposure = self.src.get_property("exposure")
            framerate = self.src.get_property("framerate")
            
            # Get pipeline state
            state = "UNKNOWN"
            if self.pipeline:
                _, current_state, _ = self.pipeline.get_state(0)
                state = current_state.value_nick.upper()
            
            return f"OK exposure={exposure} framerate={framerate} state={state}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def send_response(self, response, addr):
        """Send response back to client"""
        try:
            self.sock.sendto((response + '\n').encode(), addr)
        except Exception as e:
            print(f"Failed to send response: {e}")


Gst.init(None)

pipeline = Gst.Pipeline()

src = Gst.ElementFactory.make("idsueyesrc", "src")
src.set_property("config-file", "ini/100fps-10exp-2456x4pix-500top-cw-extragain.ini")

# Exposure in seconds (e.g., 0.016)
src.set_property("exposure", 0.016)

# Frame rate
src.set_property("framerate", 22)

# Video crop to remove bottom 3 pixels
videocrop = Gst.ElementFactory.make("videocrop", "crop")
videocrop.set_property("bottom", 3)

# Queue for buffering
queue = Gst.ElementFactory.make("queue", "queue")

# UDP sink to send the raw data
udpsink = Gst.ElementFactory.make("udpsink", "sink")
udpsink.set_property("host", "127.0.0.1")
udpsink.set_property("port", 5000)

# Add elements to pipeline
pipeline.add(src)
pipeline.add(videocrop)
pipeline.add(queue)
pipeline.add(udpsink)

# Link elements: src -> videocrop -> queue -> udpsink
if not src.link(videocrop):
    print("ERROR: Failed to link src to videocrop")
    exit(1)
if not videocrop.link(queue):
    print("ERROR: Failed to link videocrop to queue")
    exit(1)
if not queue.link(udpsink):
    print("ERROR: Failed to link queue to udpsink")
    exit(1)

print("Pipeline created successfully")
print(f"Video stream: UDP port 5000 (host: 127.0.0.1)")
print("Pipeline: idsueyesrc -> videocrop (bottom=3) -> queue -> udpsink")
print()

# Create and start control server
control_server = ControlServer(src, pipeline, port=5001)
control_server.start()

# Start the pipeline
ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("ERROR: Unable to set the pipeline to the playing state")
    exit(1)

print()
print("Pipeline is PLAYING...")
print("Press Ctrl+C to stop")

# Wait until error or EOS
bus = pipeline.get_bus()

try:
    while True:
        # Use timeout to allow Ctrl+C to be caught quickly
        msg = bus.timed_pop_filtered(
            100 * Gst.MSECOND,  # 100ms timeout
            Gst.MessageType.ERROR | Gst.MessageType.EOS | Gst.MessageType.STATE_CHANGED
        )
        
        if msg:
            t = msg.type
            if t == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"ERROR: {err.message}")
                print(f"Debug info: {debug}")
                break
            elif t == Gst.MessageType.EOS:
                print("End-Of-Stream reached")
                break
            elif t == Gst.MessageType.STATE_CHANGED:
                if msg.src == pipeline:
                    old_state, new_state, pending_state = msg.parse_state_changed()
                    print(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}")

except KeyboardInterrupt:
    print("\nInterrupted by user")

# Cleanup
print("Stopping control server...")
control_server.stop()
print("Stopping pipeline...")
pipeline.set_state(Gst.State.NULL)
print("Pipeline stopped")
