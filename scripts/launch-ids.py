
#!/usr/bin/env python3
# /// script
# requires-python = "==3.13"
# dependencies = ["argcomplete"]
# ///
#
# IDS uEye Camera Control Script with UDP Exposure Control
#
# This script streams video from an IDS uEye camera via UDP and provides
# a UDP control interface for dynamically adjusting exposure and framerate.
# All parameters are configurable via command-line arguments with sensible defaults.
#
# Setup:
#   Run with: . .\scripts\setup_gstreamer_env.ps1 && uv run .\scripts\launch-ids.py
#
# Basic Usage:
#   uv run .\scripts\launch-ids.py                    # Use all defaults
#   uv run .\scripts\launch-ids.py --help             # Show all options
#   uv run .\scripts\launch-ids.py -e 16 -f 30        # Set exposure & framerate
#   uv run .\scripts\launch-ids.py --port 6000        # Custom streaming port
#   uv run .\scripts\launch-ids.py --no-crop --quiet  # No cropping, minimal output
#   uv run .\scripts\launch-ids.py --display          # Enable 1/4 sized preview window
#
# Features:
#   - Configurable video streaming (default: UDP port 5000 to 127.0.0.1)
#   - Optional control interface (default: UDP port 5001 on 0.0.0.0)
#   - Dynamic exposure control (0.015-30000 milliseconds, default: 10ms)
#   - Dynamic framerate control (1-20000 fps, default: 750fps)
#   - Dynamic camera ID selection (0-254, default: 0 for first found)
#   - Dynamic device ID selection (0-254, system enumeration ID)
#   - Configurable video cropping (default: crop 3 pixels from bottom)
#   - Verbose/quiet output modes
#   - Custom camera configuration files
#
# Control Commands (when control server enabled):
#   SET_EXPOSURE <value>  - Set exposure in milliseconds (e.g., 16)
#   GET_EXPOSURE          - Get current exposure value
#   SET_FRAMERATE <value> - Set framerate in Hz (e.g., 30)
#   GET_FRAMERATE         - Get current framerate
#   SET_CAMERA_ID <value> - Set camera ID (0-254, 0 is first found)
#   GET_CAMERA_ID         - Get current camera ID
#   SET_DEVICE_ID <value> - Set device ID (0-254, system enumeration)
#   GET_DEVICE_ID         - Get current device ID
#   SET_GAIN <value>      - Set master gain (0-100, 0 for auto)
#   GET_GAIN              - Get current gain value
#   STATUS                - Get pipeline status and current settings
#
# Example Control Usage:
#   echo "SET_EXPOSURE 10" | nc -u 127.0.0.1 5001
#   echo "GET_EXPOSURE" | nc -u 127.0.0.1 5001
#
# Testing:
#   Run test client: uv run .\scripts\camera_control.py
#
# Documentation:
#   See scripts/UDP_CONTROL_PROTOCOL.md for full protocol details
#
# Add GStreamer Python packages
import argparse
import argcomplete
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
            print("  Commands: SET_EXPOSURE <val>, GET_EXPOSURE, SET_FRAMERATE <val>, GET_FRAMERATE,")
            print("            SET_CAMERA_ID <val>, GET_CAMERA_ID, SET_DEVICE_ID <val>, GET_DEVICE_ID,")
            print("            SET_GAIN <val>, GET_GAIN, STATUS")
            
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
            elif cmd == "SET_CAMERA_ID":
                return self.handle_set_camera_id(parts)
            elif cmd == "GET_CAMERA_ID":
                return self.handle_get_camera_id()
            elif cmd == "SET_DEVICE_ID":
                return self.handle_set_device_id(parts)
            elif cmd == "GET_DEVICE_ID":
                return self.handle_get_device_id()
            elif cmd == "SET_GAIN":
                return self.handle_set_gain(parts)
            elif cmd == "GET_GAIN":
                return self.handle_get_gain()
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
            if value < 1.0 or value > 30000:
                return "ERROR OUT_OF_RANGE: Exposure must be 0.015-30000 milliseconds"
            
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
            if value < 1.0 or value > 20200.0:
                return "ERROR OUT_OF_RANGE: Framerate must be 1.0-20200.0 Hz"
            
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
    
    def handle_set_camera_id(self, parts):
        """Handle SET_CAMERA_ID command"""
        if len(parts) != 2:
            return "ERROR INVALID_SYNTAX: Usage: SET_CAMERA_ID <value>"
        
        try:
            value = int(parts[1])
            if value < 0 or value > 254:
                return "ERROR OUT_OF_RANGE: Camera ID must be 0-254"
            
            self.src.set_property("camera-id", value)
            actual = self.src.get_property("camera-id")
            return f"OK {actual}"
        
        except ValueError:
            return "ERROR INVALID_SYNTAX: Camera ID must be an integer"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_get_camera_id(self):
        """Handle GET_CAMERA_ID command"""
        try:
            value = self.src.get_property("camera-id")
            return f"OK {value}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_set_device_id(self, parts):
        """Handle SET_DEVICE_ID command"""
        if len(parts) != 2:
            return "ERROR INVALID_SYNTAX: Usage: SET_DEVICE_ID <value>"
        
        try:
            value = int(parts[1])
            if value < 0 or value > 254:
                return "ERROR OUT_OF_RANGE: Device ID must be 0-254"
            
            self.src.set_property("device-id", value)
            actual = self.src.get_property("device-id")
            return f"OK {actual}"
        
        except ValueError:
            return "ERROR INVALID_SYNTAX: Device ID must be an integer"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_get_device_id(self):
        """Handle GET_DEVICE_ID command"""
        try:
            value = self.src.get_property("device-id")
            return f"OK {value}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_set_gain(self, parts):
        """Handle SET_GAIN command"""
        if len(parts) != 2:
            return "ERROR INVALID_SYNTAX: Usage: SET_GAIN <value>"
        
        try:
            value = int(parts[1])
            if value < 0 or value > 100:
                return "ERROR OUT_OF_RANGE: Gain must be 0-100 (0 for auto)"
            
            self.src.set_property("gain", value)
            actual = self.src.get_property("gain")
            return f"OK {actual}"
        
        except ValueError:
            return "ERROR INVALID_SYNTAX: Gain must be an integer"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_get_gain(self):
        """Handle GET_GAIN command"""
        try:
            value = self.src.get_property("gain")
            return f"OK {value}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def handle_status(self):
        """Handle STATUS command"""
        try:
            exposure = self.src.get_property("exposure")
            framerate = self.src.get_property("framerate")
            camera_id = self.src.get_property("camera-id")
            device_id = self.src.get_property("device-id")
            gain = self.src.get_property("gain")
            
            # Get pipeline state
            state = "UNKNOWN"
            if self.pipeline:
                _, current_state, _ = self.pipeline.get_state(0)
                state = current_state.value_nick.upper()
            
            return f"OK exposure={exposure} framerate={framerate} camera_id={camera_id} device_id={device_id} gain={gain} state={state}"
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def send_response(self, response, addr):
        """Send response back to client"""
        try:
            self.sock.sendto((response + '\n').encode(), addr)
        except Exception as e:
            print(f"Failed to send response: {e}")


def parse_arguments():
    """Parse command line arguments with nice defaults"""
    parser = argparse.ArgumentParser(
        description='IDS uEye Camera Control Script with UDP Exposure Control',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use all defaults
  %(prog)s --exposure 16 --framerate 30      # Basic video settings
  %(prog)s --config custom.ini --port 6000   # Custom config and streaming port
  %(prog)s --host 192.168.1.100 --no-crop   # Stream to remote host without cropping
  %(prog)s --control-port 6001 --verbose     # Custom control port with verbose output
  %(prog)s --display                         # Enable 1/4 sized preview window
        """,
        add_help=True
    )
    
    # Camera configuration
    camera_group = parser.add_argument_group('Camera Settings')
    camera_group.add_argument(
        '--config', '--config-file',
        type=str,
        default='ini/100fps-10exp-2456x4pix-500top-cw-extragain.ini',
        metavar='PATH',
        help='Camera configuration file path'
    )
    camera_group.add_argument(
        '--exposure', '-e',
        type=float,
        default=10.0,
        metavar='MS',
        help='Camera exposure time in milliseconds (0.015-30000)'
    )
    camera_group.add_argument(
        '--framerate', '--fps', '-f',
        type=float,
        default=750.0,
        metavar='HZ',
        help='Camera framerate in Hz (1.0-20200.0)'
    )
    camera_group.add_argument(
        '--camera-id',
        type=int,
        default=0,
        metavar='ID',
        help='Camera ID (0 is first found, 0-254)'
    )
    camera_group.add_argument(
        '--device-id',
        type=int,
        default=0,
        metavar='ID',
        help='Device ID (system enumeration, 0 is first, 0-254)'
    )
    camera_group.add_argument(
        '--gain', '-g',
        type=int,
        default=0,
        metavar='GAIN',
        help='Master gain (0-100, 0 for auto/default)'
    )
    
    # Video processing
    video_group = parser.add_argument_group('Video Processing')
    video_group.add_argument(
        '--crop-bottom',
        type=int,
        default=3,
        metavar='PIXELS',
        help='Number of pixels to crop from bottom (0 to disable)'
    )
    video_group.add_argument(
        '--no-crop',
        action='store_true',
        help='Disable video cropping (equivalent to --crop-bottom 0)'
    )
    video_group.add_argument(
        '--queue-size',
        type=int,
        default=None,
        metavar='BUFFERS',
        help='Queue buffer size (default: use GStreamer defaults)'
    )
    video_group.add_argument(
        '--display',
        action='store_true',
        help='Enable 1/4 sized preview window using autovideosink'
    )
    
    # Network settings
    network_group = parser.add_argument_group('Network Settings')
    network_group.add_argument(
        '--host', '--udp-host',
        type=str,
        default='127.0.0.1',
        metavar='IP',
        help='UDP streaming destination host'
    )
    network_group.add_argument(
        '--port', '--udp-port',
        type=int,
        default=5000,
        metavar='PORT',
        help='UDP streaming port'
    )
    network_group.add_argument(
        '--control-port',
        type=int,
        default=5001,
        metavar='PORT',
        help='UDP control server port'
    )
    network_group.add_argument(
        '--disable-control',
        action='store_true',
        help='Disable UDP control server'
    )
    
    # General options
    general_group = parser.add_argument_group('General Options')
    general_group.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    general_group.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress non-error output'
    )
    
    # Enable tab completion
    argcomplete.autocomplete(parser)
    
    args = parser.parse_args()
    
    # Validation
    if args.exposure < 1.0 or args.exposure > 30000:
        parser.error(f"Exposure must be between 1.0 and 30000 ms, got {args.exposure}")
    
    if args.framerate < 1.0 or args.framerate > 20200.0:
        parser.error(f"Framerate must be between 1.0 and 20200.0 Hz, got {args.framerate}")
    
    if args.camera_id < 0 or args.camera_id > 254:
        parser.error(f"Camera ID must be between 0 and 254, got {args.camera_id}")
    
    if args.device_id < 0 or args.device_id > 254:
        parser.error(f"Device ID must be between 0 and 254, got {args.device_id}")
    
    if args.gain < 0 or args.gain > 100:
        parser.error(f"Gain must be between 0 and 100, got {args.gain}")
    
    if args.port < 1 or args.port > 65535:
        parser.error(f"UDP port must be between 1 and 65535, got {args.port}")
    
    if args.control_port < 1 or args.control_port > 65535:
        parser.error(f"Control port must be between 1 and 65535, got {args.control_port}")
    
    if args.crop_bottom < 0:
        parser.error(f"Crop bottom must be non-negative, got {args.crop_bottom}")
    
    if args.no_crop:
        args.crop_bottom = 0
    
    if args.verbose and args.quiet:
        parser.error("Cannot specify both --verbose and --quiet")
    
    # Convert Windows paths to forward slashes for GStreamer compatibility
    if args.config:
        # Convert backslashes to forward slashes
        args.config = args.config.replace('\\', '/')
        
        # Handle Windows drive letters (C:/ -> C:/)
        if len(args.config) >= 3 and args.config[1:3] == ':/':
            # Already in correct format
            pass
        elif len(args.config) >= 2 and args.config[1] == ':':
            # Convert C: to C:/
            args.config = args.config[0] + ':/' + args.config[2:].lstrip('/')
    
    # Check if config file exists (using original path format for file system check)
    config_check_path = args.config.replace('/', os.sep) if args.config else None
    if config_check_path and not os.path.exists(config_check_path):
        if not args.quiet:
            print(f"WARNING: Config file '{config_check_path}' does not exist")
            print("Camera will use default settings")
    
    return args


# Parse command line arguments
args = parse_arguments()

Gst.init(None)

pipeline = Gst.Pipeline()

src = Gst.ElementFactory.make("idsueyesrc", "src")
src.set_property("config-file", args.config)

# Exposure in milliseconds
src.set_property("exposure", args.exposure)

# Frame rate
src.set_property("framerate", args.framerate)

# Camera ID and Device ID
src.set_property("camera-id", args.camera_id)
src.set_property("device-id", args.device_id)

# Gain (0 for auto/default)
src.set_property("gain", args.gain)

# Video crop to remove bottom pixels (if enabled)
elements_to_link = [src]
if args.crop_bottom > 0:
    videocrop = Gst.ElementFactory.make("videocrop", "crop")
    videocrop.set_property("bottom", args.crop_bottom)
    elements_to_link.append(videocrop)

# If display is enabled, use tee to split the stream
if args.display:
    tee = Gst.ElementFactory.make("tee", "tee")
    elements_to_link.append(tee)
    
    # UDP branch
    queue_udp = Gst.ElementFactory.make("queue", "queue_udp")
    if args.queue_size is not None:
        queue_udp.set_property("max-size-buffers", args.queue_size)
    
    udpsink = Gst.ElementFactory.make("udpsink", "sink")
    udpsink.set_property("host", args.host)
    udpsink.set_property("port", args.port)
    
    # Display branch - 1/4 scale
    queue_display = Gst.ElementFactory.make("queue", "queue_display")
    videoscale = Gst.ElementFactory.make("videoscale", "scale")
    videoconvert = Gst.ElementFactory.make("videoconvert", "convert")
    autovideosink = Gst.ElementFactory.make("autovideosink", "display")
    
    # Add all elements to pipeline
    pipeline.add(src)
    for element in elements_to_link[1:]:
        pipeline.add(element)
    pipeline.add(queue_udp)
    pipeline.add(udpsink)
    pipeline.add(queue_display)
    pipeline.add(videoscale)
    pipeline.add(videoconvert)
    pipeline.add(autovideosink)
    
    # Link main chain up to tee
    for i in range(len(elements_to_link) - 1):
        if not elements_to_link[i].link(elements_to_link[i + 1]):
            element_names = [elem.get_name() for elem in elements_to_link]
            print(f"ERROR: Failed to link {element_names[i]} to {element_names[i + 1]}")
            exit(1)
    
    # Link UDP branch
    if not tee.link(queue_udp):
        print("ERROR: Failed to link tee to queue_udp")
        exit(1)
    if not queue_udp.link(udpsink):
        print("ERROR: Failed to link queue_udp to udpsink")
        exit(1)
    
    # Link display branch with 1/4 scale caps filter
    tee_src_pad = tee.get_request_pad("src_%u")
    queue_display_sink_pad = queue_display.get_static_pad("sink")
    if tee_src_pad.link(queue_display_sink_pad) != Gst.PadLinkReturn.OK:
        print("ERROR: Failed to link tee to queue_display")
        exit(1)
    
    # Get original caps to calculate 1/4 size
    # We'll use a caps filter after videoscale
    caps_filter = Gst.ElementFactory.make("capsfilter", "scale_caps")
    pipeline.add(caps_filter)
    
    # Link: queue_display -> videoscale -> caps_filter -> videoconvert -> autovideosink
    if not queue_display.link(videoscale):
        print("ERROR: Failed to link queue_display to videoscale")
        exit(1)
    if not videoscale.link(caps_filter):
        print("ERROR: Failed to link videoscale to caps_filter")
        exit(1)
    if not caps_filter.link(videoconvert):
        print("ERROR: Failed to link caps_filter to videoconvert")
        exit(1)
    if not videoconvert.link(autovideosink):
        print("ERROR: Failed to link videoconvert to autovideosink")
        exit(1)
    
    # Set up a callback to configure the caps filter once we know the source caps
    def on_pad_added(element, pad):
        caps = pad.get_current_caps()
        if caps:
            structure = caps.get_structure(0)
            width = structure.get_value('width')
            height = structure.get_value('height')
            if width and height:
                # Set 1/4 scale (half width, half height)
                new_width = width // 2
                new_height = height // 2
                new_caps = Gst.Caps.from_string(f"video/x-raw,width={new_width},height={new_height}")
                caps_filter.set_property("caps", new_caps)
    
    # Get the src pad from the last element before tee to monitor caps
    if args.crop_bottom > 0:
        videocrop.get_static_pad("src").connect("notify::caps", lambda pad, param: on_pad_added(videocrop, pad))
    else:
        src.get_static_pad("src").connect("notify::caps", lambda pad, param: on_pad_added(src, pad))
    
    pipeline_description = " -> ".join([elem.get_name() for elem in elements_to_link])
    if args.crop_bottom > 0:
        pipeline_description = pipeline_description.replace("crop", f"videocrop(bottom={args.crop_bottom})")
    pipeline_description += " -> [UDP: queue_udp -> udpsink] + [Display: queue_display -> videoscale(1/4) -> videoconvert -> autovideosink]"

else:
    # No display - simple pipeline
    queue = Gst.ElementFactory.make("queue", "queue")
    if args.queue_size is not None:
        queue.set_property("max-size-buffers", args.queue_size)
    
    udpsink = Gst.ElementFactory.make("udpsink", "sink")
    udpsink.set_property("host", args.host)
    udpsink.set_property("port", args.port)
    
    # Add elements to pipeline and build dynamic linking chain
    pipeline.add(src)
    elements_to_link.append(queue)
    elements_to_link.append(udpsink)
    
    for element in elements_to_link[1:]:  # Skip src which is already added
        pipeline.add(element)
    
    # Link elements dynamically based on pipeline configuration
    for i in range(len(elements_to_link) - 1):
        if not elements_to_link[i].link(elements_to_link[i + 1]):
            element_names = [elem.get_name() for elem in elements_to_link]
            print(f"ERROR: Failed to link {element_names[i]} to {element_names[i + 1]}")
            exit(1)
    
    # Build pipeline description for output
    pipeline_description = " -> ".join([elem.get_name() for elem in elements_to_link])
    if args.crop_bottom > 0:
        pipeline_description = pipeline_description.replace("crop", f"videocrop(bottom={args.crop_bottom})")

if not args.quiet:
    print("=" * 60)
    print("IDS uEye Camera - Pipeline Configuration")
    print("=" * 60)
    print(f"Camera config:  {args.config}")
    print(f"Camera ID:      {args.camera_id}")
    print(f"Device ID:      {args.device_id}")
    print(f"Exposure:       {args.exposure} ms")
    print(f"Framerate:      {args.framerate} Hz")
    print(f"Gain:           {args.gain} (0=auto)")
    if args.crop_bottom > 0:
        print(f"Crop bottom:    {args.crop_bottom} pixels")
    else:
        print(f"Crop:           disabled")
    if args.queue_size is not None:
        print(f"Queue size:     {args.queue_size} buffers")
    print()
    print(f"Video stream:   UDP {args.host}:{args.port}")
    if args.display:
        print(f"Display:        1/4 sized preview window enabled")
    else:
        print(f"Display:        disabled")
    if not args.disable_control:
        print(f"Control port:   UDP 0.0.0.0:{args.control_port}")
    else:
        print(f"Control:        disabled")
    print()
    print(f"Pipeline:       {pipeline_description}")
    print("=" * 60)
    print()

# Create and start control server
if not args.disable_control:
    control_server = ControlServer(src, pipeline, port=args.control_port)
    control_server.start()
else:
    control_server = None
    if args.verbose:
        print("Control server disabled")

# Start the pipeline
ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("ERROR: Unable to set the pipeline to the playing state")
    exit(1)

if not args.quiet:
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
                if msg.src == pipeline and args.verbose:
                    old_state, new_state, pending_state = msg.parse_state_changed()
                    print(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}")

except KeyboardInterrupt:
    print("\nInterrupted by user")

# Cleanup
if not args.quiet:
    print("Stopping control server...")
if control_server:
    control_server.stop()
if not args.quiet:
    print("Stopping pipeline...")
pipeline.set_state(Gst.State.NULL)
if not args.quiet:
    print("Pipeline stopped")
