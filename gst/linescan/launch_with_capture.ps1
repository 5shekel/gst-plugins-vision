# Linescan Pipeline Example - PowerShell GStreamer Launch
#
# This script demonstrates a GStreamer linescan pipeline using gst-launch-1.0.
# NOTE: This saves EVERY frame using multifilesink, not just on rollover.
#
# For proper rollover-only saving, use the Python scripts instead:
#   - launch_with_signal.py (full-featured with camera)
#   - rollover_example.py (simple demo)
#
# This script is kept as a reference for the pipeline structure.
#
# Prerequisites:
#   1. Build the plugins: .\build.ps1
#   2. Run from workspace root: c:\dev\gst-plugins-vision
#
# Usage:
#   .\gst\linescan\launch_with_capture.ps1
#
# Pipeline:
#   idsueyesrc -> intervalometer -> videocrop -> queue -> linescan -> videoconvert -> autovideosink
#
# WARNING: This example saves every output frame, not just on rollover!
# Use Python scripts for rollover-based capture.

$env:GST_DEBUG="linescan:5"

# Simple pipeline - display only (no file saving)
# For file saving on rollover, use launch_with_signal.py instead
gst-launch-1.0 idsueyesrc config-file=ini/roi-night.ini `
    exposure=5.25 framerate=200 gain=42 name=cam device-id=2 ! `
    intervalometer enabled=true camera-element=cam `
    ramp-rate=vslow `
    update-interval=1000 `
    gain-max=52 `
    log-file=linescan_timelapse.csv ! `
    videocrop bottom=3 ! `
    queue ! `
    linescan direction=vertical output-size=1900 ! `
    videoconvert ! autovideosink

# Note: multifilesink has been removed because it saves EVERY frame.
# To save only on rollover events, use the Python scripts which connect
# to the rollover signal and save via PIL/numpy.