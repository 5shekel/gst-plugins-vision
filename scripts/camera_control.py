#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["argcomplete"]
# ///

"""
Test client for UDP exposure control

Usage:
  uv run scripts/camera_control.py                    # Run full test suite
  uv run scripts/camera_control.py get-exposure       # Get current exposure
  uv run scripts/camera_control.py set-exposure 10    # Set exposure to 10ms
  uv run scripts/camera_control.py get-framerate      # Get current framerate
  uv run scripts/camera_control.py set-framerate 30   # Set framerate to 30fps
  uv run scripts/camera_control.py get-gain           # Get current gain
  uv run scripts/camera_control.py set-gain 50        # Set gain to 50
  uv run scripts/camera_control.py status             # Get pipeline status

This script provides both individual control commands and full test suite functionality
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

def print_test(test_num, description, command, response):
    """Print formatted test result"""
    print(f"\nTest {test_num}: {description}")
    print(f"  Command:  {command}")
    print(f"  Response: {response}")
    
    # Check if response indicates success
    if response.startswith("OK"):
        print("  ✓ PASS")
    elif response.startswith("ERROR"):
        if "OUT_OF_RANGE" in response or "INVALID" in response:
            print("  ✓ PASS (Expected error)")
        else:
            print("  ✗ FAIL (Unexpected error)")
    else:
        print("  ? UNKNOWN")

def simple_command(command, description="Command"):
    """Execute a single command and print the result"""
    print(f"{description}...")
    response = send_command(command)
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

def run_full_tests():
    """Run the full test suite (original functionality)"""
    print("=" * 70)
    print("UDP Exposure Control Test Client")
    print("=" * 70)
    print("Testing UDP control interface on 127.0.0.1:5001")
    print()
    
    # Check if server is reachable
    print("Checking if control server is reachable...")
    response = send_command("STATUS", timeout=2.0)
    if "Timeout" in response:
        print("✗ FAILED: Control server not responding")
        print("  Make sure launch-ids.py is running first!")
        sys.exit(1)
    print("✓ Control server is reachable\n")
    
    time.sleep(0.2)
    
    # Test 1: Get current exposure
    response = send_command("GET_EXPOSURE")
    print_test(1, "Get current exposure", "GET_EXPOSURE", response)
    time.sleep(0.2)
    
    # Test 2: Set exposure to 10ms
    response = send_command("SET_EXPOSURE 10")
    print_test(2, "Set exposure to 10ms", "SET_EXPOSURE 10", response)
    time.sleep(5.2)
    
    # Test 3: Verify exposure was set
    response = send_command("GET_EXPOSURE")
    print_test(3, "Verify exposure changed", "GET_EXPOSURE", response)
    time.sleep(0.2)
    
    # Test 4: Set exposure to 2ms
    response = send_command("SET_EXPOSURE 2")
    print_test(4, "Set exposure to 2ms", "SET_EXPOSURE 2", response)
    time.sleep(0.2)
    
    # Test 5: Get framerate
    response = send_command("GET_FRAMERATE")
    print_test(5, "Get current framerate", "GET_FRAMERATE", response)
    time.sleep(0.2)
    
    # Test 6: Set framerate
    response = send_command("SET_FRAMERATE 44")
    print_test(6, "Set framerate to 44 fps", "SET_FRAMERATE 44", response)
    time.sleep(0.2)
    
    # Test 7: Verify framerate
    response = send_command("GET_FRAMERATE")
    print_test(7, "Verify framerate changed", "GET_FRAMERATE", response)
    time.sleep(0.2)
    
    # Test 8: Get status
    response = send_command("STATUS")
    print_test(8, "Get pipeline status", "STATUS", response)
    time.sleep(0.2)
    
    # Test 9: Invalid command
    response = send_command("INVALID_CMD")
    print_test(9, "Send invalid command", "INVALID_CMD", response)
    time.sleep(0.2)
    
    # Test 14: Restore original exposure (2ms)
    response = send_command("SET_EXPOSURE 2")
    print_test(14, "Restore exposure to 2ms", "SET_EXPOSURE 2", response)
    time.sleep(0.2)
    
    # Test 15: Restore original framerate (22 fps)
    response = send_command("SET_FRAMERATE 22")
    print_test(15, "Restore framerate to 22 fps", "SET_FRAMERATE 22", response)
    
    print()
    print("=" * 70)
    print("Test completed!")
    print()
    print("Quick reference:")
    print("  echo 'SET_EXPOSURE 10' | nc -u 127.0.0.1 5001")
    print("  echo 'GET_EXPOSURE' | nc -u 127.0.0.1 5001")
    print("  echo 'STATUS' | nc -u 127.0.0.1 5001")
    print("=" * 70)

def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(
        description="UDP Exposure Control Test Client",
        epilog="""
Examples:
  %(prog)s                                 # Show this help
  %(prog)s test                            # Run full test suite
  %(prog)s get-exposure                    # Get current exposure
  %(prog)s set-exposure 10                 # Set exposure to 10ms
  %(prog)s get-framerate                   # Get current framerate
  %(prog)s set-framerate 30                # Set framerate to 30fps
  %(prog)s get-gain                        # Get current gain
  %(prog)s set-gain 50                     # Set gain to 50
  %(prog)s status                          # Get pipeline status
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('command',
                        nargs='?',
                        choices=['test', 'get-exposure', 'set-exposure', 'get-framerate', 'set-framerate',
                                'get-gain', 'set-gain', 'status'],
                        help='Command to execute')
    
    parser.add_argument('value',
                        nargs='?',
                        type=float,
                        help='Value for set commands (exposure in ms, framerate in fps)')
    
    parser.add_argument('--host',
                        default='127.0.0.1',
                        help='Host address (default: 127.0.0.1)')
    
    parser.add_argument('--port',
                        type=int,
                        default=5001,
                        help='Port number (default: 5001)')
    
    # Enable tab completion if argcomplete is available
    if argcomplete:
        argcomplete.autocomplete(parser)
    
    args = parser.parse_args()
    
    # If no command provided, show help
    if args.command is None:
        parser.print_help()
        return
    
    # Handle test command (full test suite)
    if args.command == 'test':
        run_full_tests()
        return
    
    # Handle individual commands
    if args.command == 'get-exposure':
        success = simple_command("GET_EXPOSURE", "Getting current exposure")
        
    elif args.command == 'set-exposure':
        if args.value is None:
            print("Error: set-exposure requires a value (exposure in milliseconds)")
            parser.print_help()
            sys.exit(1)
        success = simple_command(f"SET_EXPOSURE {args.value}", f"Setting exposure to {args.value}ms")
        
    elif args.command == 'get-framerate':
        success = simple_command("GET_FRAMERATE", "Getting current framerate")
        
    elif args.command == 'set-framerate':
        if args.value is None:
            print("Error: set-framerate requires a value (framerate in fps)")
            parser.print_help()
            sys.exit(1)
        success = simple_command(f"SET_FRAMERATE {args.value}", f"Setting framerate to {args.value}fps")
        
    elif args.command == 'get-gain':
        success = simple_command("GET_GAIN", "Getting current gain")
        
    elif args.command == 'set-gain':
        if args.value is None:
            print("Error: set-gain requires a value (0-100, 0 for auto)")
            parser.print_help()
            sys.exit(1)
        # Convert to int for gain
        gain_value = int(args.value)
        if gain_value < 0 or gain_value > 100:
            print("Error: Gain must be between 0 and 100 (0 for auto)")
            sys.exit(1)
        success = simple_command(f"SET_GAIN {gain_value}", f"Setting gain to {gain_value}")
        
    elif args.command == 'status':
        success = simple_command("STATUS", "Getting pipeline status")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()