import numpy as np
import imageio.v3 as iio
from tqdm import tqdm
import concurrent.futures
import os

# --- Configuration ---
DATA_SOURCE = "data/760-004_cropped_ZTjMVf.avi"
RING_BUFFER_SIZE = 32000
OUTPUT_DIR = "output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

write_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
futures = []

def submit_write_job(ring_buffer, index, length, ring_index):
    try:
        # copy data so it doesnt run away
        data_to_write = np.take(ring_buffer, range(ring_index-length, ring_index), axis=0, mode='wrap').copy() 
    except Exception as e:
        print(f"Error taking data from ring buffer: {e}")
        return None

    def _write_task(data):
        filename = f"{OUTPUT_DIR}/object-{index-length}-{index}-{length}.png"
        iio.imwrite(filename, data)

    future = write_executor.submit(_write_task, data_to_write)
    return future

props = iio.improps(DATA_SOURCE) # overwrite manually if live video source

window_size = 12000

ema_mean = 0.74
ema_var  = 0.05
baseline_alpha = 0.001
variance_alpha = 0.01
default_diff = 0.52

stride=1
frameskip=1

postcutoff_variance_threshold = 2.5
cutoff_variance_threshold = 3.5
precutoff_variance_threshold = 0.05

is_recording = False
recording_length = 0
patience_default = 600
patience = patience_default
patience_length = 0
recorded_images = 0
frames_since_last_recording = 0
index = 0

ring_buffer = np.zeros((RING_BUFFER_SIZE, props.shape[2], props.shape[3]), dtype=props.dtype)
sum_ring_buffer = np.zeros((RING_BUFFER_SIZE), dtype=np.uint64)
ema_var_ring = np.zeros((RING_BUFFER_SIZE), dtype=np.float32)
sum_buffer = np.zeros_like(sum_ring_buffer[0:window_size])
stride_indices = np.arange(0, props.shape[2], stride)

for frame in tqdm(iio.imiter(DATA_SOURCE, plugin="pyav"), total=props.n_images):
    effective_window_size = min(index, window_size)
    ring_index = index%RING_BUFFER_SIZE

    time_indices = np.arange(ring_index - effective_window_size, ring_index) % RING_BUFFER_SIZE
    sum_buffer[:len(time_indices)] = sum_ring_buffer[time_indices[:]]

    # splayed out for perf debugging
    s4 = frame[0:1,::stride,1]
    frame_mean = np.divide(np.sum(s4),s4.size)
    s2 = sum_buffer[:len(time_indices)]
    s11 = np.sum(s2)
    s1 = np.divide(s11,s2.size) if s2.size > 0 else 0 # Avoid division by zero
    s0 = np.abs(frame_mean - s1)
    s00 = np.mean(s0)
    value = s00 if index > 0 else default_diff

    if ema_mean is None: 
        ema_mean, ema_var = value, 1.0

    deviation = value - ema_mean

    ema_mean_temp = (1 - baseline_alpha) * ema_mean + baseline_alpha * value
    ema_var_temp = (1 - variance_alpha) * ema_var + variance_alpha * (deviation ** 2)

    ring_buffer[ring_index:ring_index+1, :, :] = frame[0:1,:,:]
    sum_ring_buffer[ring_index] = frame_mean

    if is_recording == False or abs(deviation) < 3 * np.sqrt(ema_var):
        ema_var = ema_var_temp
        ema_mean = ema_mean_temp
    if (is_recording == False and ema_var > cutoff_variance_threshold):
        is_recording = True
        
        quiet_indices = np.argwhere(np.take(ema_var_ring, range(ring_index-RING_BUFFER_SIZE, ring_index), mode='wrap') < precutoff_variance_threshold)

        if quiet_indices.size > 0:
            last_quiet_index = quiet_indices[-1].item()
            recording_length = min(RING_BUFFER_SIZE - last_quiet_index + patience_default, frames_since_last_recording)
        else:
            recording_length = frames_since_last_recording 
        patience = patience_default
        patience_length = 0

    if is_recording:
        if (ema_var < postcutoff_variance_threshold):
            patience -= 1
            patience_length += 1
        if (ema_var >= postcutoff_variance_threshold):
            recording_length += 1
            patience_length = 0
            patience = patience_default
        if (patience == 0):
            print(f"Dumping image starting at index {index-recording_length} ending at {index}, length {recording_length}")
            future = submit_write_job(ring_buffer, index, recording_length, ring_index-patience_length)
            if future:
                futures.append(future)

            ema_var_ring[ring_index-patience_length] = 0.0
            recorded_images += 1
            frames_since_last_recording = patience_length
            patience_length = 0
            is_recording = False

    ema_var_ring[ring_index] = ema_var
    index += 1
    frames_since_last_recording += 1

# handle final recording
if is_recording:
    print(f"Dumping final image starting at index {index-recording_length} ending at {index}, length {recording_length}")
    final_future = submit_write_job(ring_buffer, index, recording_length, ring_index-patience_length)
    if final_future:
        futures.append(final_future)
    recorded_images += 1

# wait for image writes to complete
print("Processing complete. Waiting for all background writing tasks to finish...")
concurrent.futures.wait(futures)
write_executor.shutdown() # Cleanly release resources
print(f"All images written. Recorded {recorded_images} objects.")