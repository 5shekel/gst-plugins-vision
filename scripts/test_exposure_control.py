#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///

"""
Test client for UDP exposure control
Usage: uv run scripts/test_exposure_control.py

This script tests the UDP control interface for the IDS uEye camera.
Make sure launch-ids.py is running before executing this test.
"""

import socket
import time
import sys

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

def main():
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
    response = send_command("SET_EXPOSURE 0.110")
    print_test(2, "Set exposure to 10ms", "SET_EXPOSURE 0.010", response)
    time.sleep(5.2)
    
    # Test 3: Verify exposure was set
    response = send_command("GET_EXPOSURE")
    print_test(3, "Verify exposure changed", "GET_EXPOSURE", response)
    time.sleep(0.2)
    
    # Test 4: Set exposure to 20ms
    response = send_command("SET_EXPOSURE 0.020")
    print_test(4, "Set exposure to 20ms", "SET_EXPOSURE 0.020", response)
    time.sleep(0.2)
    
    # Test 5: Get framerate
    response = send_command("GET_FRAMERATE")
    print_test(5, "Get current framerate", "GET_FRAMERATE", response)
    time.sleep(0.2)
    
    # Test 6: Set framerate
    response = send_command("SET_FRAMERATE 30")
    print_test(6, "Set framerate to 30 fps", "SET_FRAMERATE 30", response)
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
    
    # Test 10: Out of range exposure (too high)
    response = send_command("SET_EXPOSURE 5.0")
    print_test(10, "Out of range exposure (5.0s)", "SET_EXPOSURE 5.0", response)
    time.sleep(0.2)
    
    # Test 11: Out of range exposure (too low)
    response = send_command("SET_EXPOSURE 0.0001")
    print_test(11, "Out of range exposure (0.1ms)", "SET_EXPOSURE 0.0001", response)
    time.sleep(0.2)
    
    # Test 12: Invalid syntax (missing parameter)
    response = send_command("SET_EXPOSURE")
    print_test(12, "Invalid syntax (missing param)", "SET_EXPOSURE", response)
    time.sleep(0.2)
    
    # Test 13: Invalid syntax (non-numeric)
    response = send_command("SET_EXPOSURE abc")
    print_test(13, "Invalid syntax (non-numeric)", "SET_EXPOSURE abc", response)
    time.sleep(0.2)
    
    # Test 14: Restore original exposure (16ms)
    response = send_command("SET_EXPOSURE 0.016")
    print_test(14, "Restore exposure to 16ms", "SET_EXPOSURE 0.016", response)
    time.sleep(0.2)
    
    # Test 15: Restore original framerate (22 fps)
    response = send_command("SET_FRAMERATE 22")
    print_test(15, "Restore framerate to 22 fps", "SET_FRAMERATE 22", response)
    
    print()
    print("=" * 70)
    print("Test completed!")
    print()
    print("Quick reference:")
    print("  echo 'SET_EXPOSURE 0.010' | nc -u 127.0.0.1 5001")
    print("  echo 'GET_EXPOSURE' | nc -u 127.0.0.1 5001")
    print("  echo 'STATUS' | nc -u 127.0.0.1 5001")
    print("=" * 70)

if __name__ == "__main__":
    main()