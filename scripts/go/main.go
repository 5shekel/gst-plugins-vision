package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"
)

const (
	// Stream parameters (match your GStreamer sender)
	COLUMN_WIDTH  = 4
	COLUMN_HEIGHT = 2456
	CHANNELS      = 3
	FRAME_SIZE    = COLUMN_WIDTH * COLUMN_HEIGHT * CHANNELS // 29472 bytes

	// Line drop detection parameters
	EXPECTED_FPS         = 200
	EXPECTED_INTERVAL_MS = 1000.0 / EXPECTED_FPS // 5ms for 200fps
	DROP_THRESHOLD_MS    = EXPECTED_INTERVAL_MS * 2.5
	STATS_WINDOW_SIZE    = 100
	STATUS_INTERVAL      = 100

	UDP_PORT = 5000
)

type FrameStats struct {
	intervals      []float64
	totalDrops     int
	dropsSince     int
	frameCount     int
	firstFrameTime time.Time
	lastFrameTime  time.Time
	totalBytes     int64
}

func newFrameStats() *FrameStats {
	return &FrameStats{
		intervals: make([]float64, 0, STATS_WINDOW_SIZE),
	}
}

func (fs *FrameStats) addInterval(intervalMs float64) {
	if len(fs.intervals) >= STATS_WINDOW_SIZE {
		fs.intervals = fs.intervals[1:]
	}
	fs.intervals = append(fs.intervals, intervalMs)
}

func (fs *FrameStats) avgInterval() float64 {
	if len(fs.intervals) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range fs.intervals {
		sum += v
	}
	return sum / float64(len(fs.intervals))
}

func (fs *FrameStats) printSummary() {
	if fs.frameCount == 0 {
		return
	}
	elapsed := time.Since(fs.firstFrameTime).Seconds()
	avgFPS := float64(fs.frameCount) / elapsed
	avgInterval := fs.avgInterval()
	instantFPS := 0.0
	if avgInterval > 0 {
		instantFPS = 1000.0 / avgInterval
	}
	
	bandwidth := float64(fs.totalBytes) / elapsed / (1024 * 1024) // MB/s
	
	fmt.Println("\n=== Final Statistics ===")
	fmt.Printf("Total Frames: %d\n", fs.frameCount)
	fmt.Printf("Total Time: %.2f seconds\n", elapsed)
	fmt.Printf("Average FPS: %.2f\n", avgFPS)
	fmt.Printf("Instant FPS: %.2f\n", instantFPS)
	fmt.Printf("Total Drops: %d\n", fs.totalDrops)
	fmt.Printf("Total Data: %.2f MB\n", float64(fs.totalBytes)/(1024*1024))
	fmt.Printf("Bandwidth: %.2f MB/s\n", bandwidth)
}

func main() {
	// Setup UDP socket
	addr := net.UDPAddr{
		Port: UDP_PORT,
		IP:   net.ParseIP("0.0.0.0"),
	}
	conn, err := net.ListenUDP("udp", &addr)
	if err != nil {
		log.Fatal("UDP listen failed:", err)
	}
	defer conn.Close()

	// Set receive buffer size to 16MB
	if err := conn.SetReadBuffer(16 * 1024 * 1024); err != nil {
		log.Printf("Warning: Failed to set recv buffer: %v", err)
	}

	fmt.Printf("High-Performance UDP Receiver for Raw %dx%d RGB columns\n", COLUMN_WIDTH, COLUMN_HEIGHT)
	fmt.Printf("Listening on UDP port %d\n", UDP_PORT)
	fmt.Printf("Expected frame size: %d bytes\n", FRAME_SIZE)
	fmt.Printf("Press Ctrl+C to stop\n\n")

	stats := newFrameStats()
	buffer := make([]byte, 65536)

	// Handle graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	
	// Channel for shutdown
	done := make(chan bool)
	
	// Start UDP receiver goroutine
	go func() {
		for {
			select {
			case <-done:
				return
			default:
				n, _, err := conn.ReadFromUDP(buffer)
				if err != nil {
					select {
					case <-done:
						return
					default:
						log.Printf("UDP read error: %v", err)
						continue
					}
				}

				if n != FRAME_SIZE {
					// Wrong packet size, skip
					continue
				}

				currentTime := time.Now()

				// Initialize timing on first frame
				if stats.firstFrameTime.IsZero() {
					stats.firstFrameTime = currentTime
					fmt.Println("Started receiving frames...")
				}

				// Line drop detection
				if !stats.lastFrameTime.IsZero() {
					intervalMs := float64(currentTime.Sub(stats.lastFrameTime).Microseconds()) / 1000.0
					stats.addInterval(intervalMs)

					if intervalMs > DROP_THRESHOLD_MS {
						stats.totalDrops++
						stats.dropsSince++
					}
				}

				stats.lastFrameTime = currentTime
				stats.frameCount++
				stats.totalBytes += int64(n)

				// Print status
				if stats.frameCount%STATUS_INTERVAL == 0 {
					elapsed := currentTime.Sub(stats.firstFrameTime).Seconds()
					realFPS := float64(stats.frameCount) / elapsed
					avgInterval := stats.avgInterval()
					instantFPS := 0.0
					if avgInterval > 0 {
						instantFPS = 1000.0 / avgInterval
					}

					bandwidth := float64(stats.totalBytes) / elapsed / (1024 * 1024) // MB/s

					status := fmt.Sprintf("Frame %6d: Real FPS: %6.1f | Instant: %6.1f | BW: %6.2f MB/s",
						stats.frameCount, realFPS, instantFPS, bandwidth)
					if stats.dropsSince > 0 {
						status += fmt.Sprintf(" | ⚠️  %d drops", stats.dropsSince)
						stats.dropsSince = 0
					} else if stats.totalDrops > 0 {
						status += fmt.Sprintf(" | Total drops: %d", stats.totalDrops)
					}
					fmt.Println(status)
				}
			}
		}
	}()

	// Wait for shutdown signal
	<-sigChan
	fmt.Println("\nShutdown signal received...")
	close(done)
	
	// Give a moment for cleanup
	time.Sleep(100 * time.Millisecond)
	
	// Print final statistics
	stats.printSummary()
	fmt.Println("Goodbye!")
}