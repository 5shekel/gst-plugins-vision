# Pipeline with tee to display and save frames on rollover
# Run from workspace root: c:\dev\gst-plugins-vision
# Or adjust the config-file path below

$env:GST_DEBUG="linescan:5"

# Note: Run this from the workspace root (c:\dev\gst-plugins-vision)
# If running from gst/linescan/, use: config-file=../../ini/roi-night.ini
uv run .\scripts\launch-ids.py `
     --config .\ini\2456x4pix-500top-cw-extragain.ini `
     --device-id 1 `
     --framerate 750 `
     --gain 0 `
     --gain-boost `
     --exposure 0.04 `
     --host 10.81.2.183 `
     --port 5000 `
     --control-port 5001