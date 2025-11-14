# how to send a line

real data 
```powershell
gst-launch-1.0 idsueyesrc config-file=ini/200fps-2456x4pix-cw.ini exposure=5 framerate=300  `
    ! videoconvert ! queue `   
    ! udpsink host=127.0.0.1 port=5000
```

### Python/OpenCV Receiver
```pwsh
uv run scripts/recv_raw_column.py
```
or rolling like 
```pwsh
uv run .\scripts\recv_raw_rolling.py
```
See [`scripts/recv_raw_column.py`](scripts/recv_raw_column.py) for the Python implementation with debug options.


# demo data
## Sender (crop to first column, send raw over UDP)
```pwsh
gst-launch-1.0 -v `
    videotestsrc pattern=smpte ! `
    videocrop left=0 right=639 top=0 bottom=0 ! `
    video/x-raw,format=RGB,width=1,height=640,framerate=30/1 ! `
    udpsink host=127.0.0.1 port=5000
```

### GStreamer Receiver (raw UDP → display)
```pwsh
gst-launch-1.0 -v `
    udpsrc port=5000 caps="video/x-raw,format=RGB,width=1,height=640,framerate=30/1" ! `
    videoconvert ! `
    autovideosink
```

