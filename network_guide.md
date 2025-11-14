# how to send a line

## Sender (crop to first column, send raw over UDP)
```pwsh
gst-launch-1.0 -v `
    videotestsrc pattern=smpte ! `
    videocrop left=0 right=639 top=0 bottom=0 ! `
    video/x-raw,format=RGB,width=1,height=640,framerate=30/1 ! `
    udpsink host=127.0.0.1 port=5000
```

**Note:** Default `videotestsrc` height is 640, not 480. Adjust caps to match your actual frame size.

## Receiver Options

### GStreamer Receiver (raw UDP → display)
```pwsh
gst-launch-1.0 -v `
    udpsrc port=5000 caps="video/x-raw,format=RGB,width=1,height=640,framerate=30/1" ! `
    videoconvert ! `
    autovideosink
```

### Python/OpenCV Receiver
```pwsh
uv run scripts/recv_raw_column.py
```

See [`scripts/recv_raw_column.py`](scripts/recv_raw_column.py) for the Python implementation with debug options.