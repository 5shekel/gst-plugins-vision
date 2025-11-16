#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["argcomplete"]
# ///

"""
client for UDP camera control

Usage:
  uv run scripts/camera_control.py                    # Get all camera settings (default)
  uv run scripts/camera_control.py get-all            # Get all camera settings
  uv run scripts/camera_control.py exposure           # Get current exposure
  uv run scripts/camera_control.py exposure 10        # Set exposure to 10ms
  uv run scripts/camera_control.py framerate          # Get current framerate
  uv run scripts/camera_control.py framerate 30       # Set framerate to 30fps
  uv run scripts/camera_control.py gain               # Get current gain
  uv run scripts/camera_control.py gain 50            # Set gain to 50
  uv run scripts/camera_control.py auto-exposure      # Get auto-exposure status
  uv run scripts/camera_control.py auto-exposure 1    # Enable auto-exposure
  uv run scripts/camera_control.py auto-gain          # Get auto-gain status
  uv run scripts/camera_control.py auto-gain 1        # Enable auto-gain
  uv run scripts/camera_control.py gain-boost         # Get gain boost status
  uv run scripts/camera_control.py gain-boost 1       # Enable gain boost
  uv run scripts/camera_control.py status             # Get pipeline status

This script provides control commands
for the UDP control interface for the IDS uEye camera.
Make sure launch-ids.py is running before executing commands.
"""

import argparse
import socket
import time
import sys

try:
    import argcomplete
except ImportError:
    argcomplete = None

def send_command(command, host="127.0.0.1", port=5001, timeout=1.0):
    """Send a command and return the response"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    
    try:
        # Send command
        sock.sendto(command.encode() + b'\n', (host, port))
        
        # Receive response
        response, _ = sock.recvfrom(1024)
        return response.decode().strip()
    
    except socket.timeout:
        return "ERROR: Timeout waiting for response (is launch-ids.py running?)"
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        sock.close()


def simple_command(command, description="Command", host="127.0.0.1", port=5001, timeout=1.0):
    """Execute a single command and print the result"""
    print(f"{description}...")
    response = send_command(command, host, port, timeout)
    print(f"Response: {response}")
    
    # Check if response indicates success
    if response.startswith("OK"):
        return True
    elif response.startswith("ERROR"):
        print(f"Error: {response}")
        return False
    else:
        print(f"Unknown response: {response}")
        return False

def get_all_settings(host="127.0.0.1", port=5001, timeout=1.0):
    """Get all camera settings"""
    print("=" * 70)
    print("Camera Settings")
    print("=" * 70)
    
    settings = [
        ("Exposure", "GET_EXPOSURE"),
        ("Exposure Range", "GET_EXPOSURE_RANGE"),
        ("Framerate", "GET_FRAMERATE"),
        ("Gain", "GET_GAIN"),
        ("Auto-Exposure", "GET_AUTO_EXPOSURE"),
        ("Auto-Gain", "GET_AUTO_GAIN"),
        ("Gain Boost", "GET_GAIN_BOOST"),
    ]
    
    all_success = True
    for name, command in settings:
        response = send_command(command, host, port, timeout)
        print(f"{name:20s}: {response}")
        if response.startswith("ERROR"):
            all_success = False
    
    print("=" * 70)
    return all_success

def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(
        description="UDP Camera Control Client",
        epilog="""
Examples:
  %(prog)s                                 # Get all camera settings (default)
  %(prog)s get-all                         # Get all camera settings
  %(prog)s exposure                        # Get current exposure
  %(prog)s exposure 10                     # Set exposure to 10ms
  %(prog)s framerate                       # Get current framerate
  %(prog)s framerate 30                    # Set framerate to 30fps
  %(prog)s gain                            # Get current gain
  %(prog)s gain 50                         # Set gain to 50
  %(prog)s auto-exposure                   # Get auto-exposure status
  %(prog)s auto-exposure 1                 # Enable auto-exposure
  %(prog)s auto-gain                       # Get auto-gain status
  %(prog)s auto-gain 1                     # Enable auto-gain
  %(prog)s gain-boost                      # Get gain boost status
  %(prog)s gain-boost 1                    # Enable gain boost
  %(prog)s status                          # Get pipeline status
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('property',
                        nargs='?',
                        choices=['get-all', 'exposure', 'framerate', 'gain',
                                'auto-exposure', 'auto-gain', 'gain-boost', 'status'],
                        help='Property to get or set')
    
    parser.add_argument('value',
                        nargs='?',
                        help='Value to set (if not provided, gets current value)')
    
    parser.add_argument('--host',
                        default='127.0.0.1',
                        metavar='IP',
                        help='Host address (default: 127.0.0.1)')
    
    parser.add_argument('--port',
                        type=int,
                        default=5001,
                        metavar='PORT',
                        help='Port number (default: 5001)')
    
    parser.add_argument('--timeout',
                        type=float,
                        default=1.0,
                        metavar='SECONDS',
                        help='Timeout for UDP requests in seconds (default: 1.0)')
    
    # Enable tab completion if argcomplete is available
    if argcomplete:
        argcomplete.autocomplete(parser)
    
    args = parser.parse_args()
    
    # If no property provided, run get-all by default
    if args.property is None:
        success = get_all_settings(host=args.host, port=args.port, timeout=args.timeout)
        sys.exit(0 if success else 1)
    
    # Handle special commands
    if args.property == 'get-all':
        success = get_all_settings(host=args.host, port=args.port, timeout=args.timeout)
    elif args.property == 'status':
        success = simple_command("STATUS", "Getting pipeline status",
                                host=args.host, port=args.port, timeout=args.timeout)
    
    # Handle property-based commands
    elif args.property == 'exposure':
        if args.value is None:
            # Get exposure
            success = simple_command("GET_EXPOSURE", "Getting current exposure",
                                    host=args.host, port=args.port, timeout=args.timeout)
        else:
            # Set exposure
            try:
                exposure_value = float(args.value)
                success = simple_command(f"SET_EXPOSURE {exposure_value}",
                                       f"Setting exposure to {exposure_value}ms",
                                       host=args.host, port=args.port, timeout=args.timeout)
            except ValueError:
                print(f"Error: Invalid exposure value '{args.value}'. Must be a number.")
                sys.exit(1)
    
    elif args.property == 'framerate':
        if args.value is None:
            # Get framerate
            success = simple_command("GET_FRAMERATE", "Getting current framerate",
                                    host=args.host, port=args.port, timeout=args.timeout)
        else:
            # Set framerate
            try:
                framerate_value = float(args.value)
                success = simple_command(f"SET_FRAMERATE {framerate_value}",
                                       f"Setting framerate to {framerate_value}fps",
                                       host=args.host, port=args.port, timeout=args.timeout)
            except ValueError:
                print(f"Error: Invalid framerate value '{args.value}'. Must be a number.")
                sys.exit(1)
    
    elif args.property == 'gain':
        if args.value is None:
            # Get gain
            success = simple_command("GET_GAIN", "Getting current gain",
                                    host=args.host, port=args.port, timeout=args.timeout)
        else:
            # Set gain
            try:
                gain_value = int(float(args.value))
                if gain_value < 0 or gain_value > 100:
                    print("Error: Gain must be between 0 and 100 (0 for auto)")
                    sys.exit(1)
                success = simple_command(f"SET_GAIN {gain_value}",
                                       f"Setting gain to {gain_value}",
                                       host=args.host, port=args.port, timeout=args.timeout)
            except ValueError:
                print(f"Error: Invalid gain value '{args.value}'. Must be a number 0-100.")
                sys.exit(1)
    
    elif args.property == 'auto-exposure':
        if args.value is None:
            # Get auto-exposure
            success = simple_command("GET_AUTO_EXPOSURE", "Getting auto-exposure status",
                                    host=args.host, port=args.port, timeout=args.timeout)
        else:
            # Set auto-exposure
            try:
                ae_value = int(float(args.value))
                if ae_value not in [0, 1]:
                    print("Error: Auto-exposure must be 0 (off) or 1 (on)")
                    sys.exit(1)
                success = simple_command(f"SET_AUTO_EXPOSURE {ae_value}",
                                       f"{'Enabling' if ae_value else 'Disabling'} auto-exposure",
                                       host=args.host, port=args.port, timeout=args.timeout)
            except ValueError:
                print(f"Error: Invalid auto-exposure value '{args.value}'. Must be 0 or 1.")
                sys.exit(1)
    
    elif args.property == 'auto-gain':
        if args.value is None:
            # Get auto-gain
            success = simple_command("GET_AUTO_GAIN", "Getting auto-gain status",
                                    host=args.host, port=args.port, timeout=args.timeout)
        else:
            # Set auto-gain
            try:
                ag_value = int(float(args.value))
                if ag_value not in [0, 1]:
                    print("Error: Auto-gain must be 0 (off) or 1 (on)")
                    sys.exit(1)
                success = simple_command(f"SET_AUTO_GAIN {ag_value}",
                                       f"{'Enabling' if ag_value else 'Disabling'} auto-gain",
                                       host=args.host, port=args.port, timeout=args.timeout)
            except ValueError:
                print(f"Error: Invalid auto-gain value '{args.value}'. Must be 0 or 1.")
                sys.exit(1)
    
    elif args.property == 'gain-boost':
        if args.value is None:
            # Get gain-boost
            success = simple_command("GET_GAIN_BOOST", "Getting gain boost status",
                                    host=args.host, port=args.port, timeout=args.timeout)
        else:
            # Set gain-boost
            try:
                gb_value = int(float(args.value))
                if gb_value not in [0, 1]:
                    print("Error: Gain boost must be 0 (off) or 1 (on)")
                    sys.exit(1)
                success = simple_command(f"SET_GAIN_BOOST {gb_value}",
                                       f"{'Enabling' if gb_value else 'Disabling'} gain boost",
                                       host=args.host, port=args.port, timeout=args.timeout)
            except ValueError:
                print(f"Error: Invalid gain boost value '{args.value}'. Must be 0 or 1.")
                sys.exit(1)
    
    else:
        print(f"Error: Unknown property '{args.property}'")
        parser.print_help()
        sys.exit(1)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()