# Line-scan FPS / Exposure Tuning — Day & Night Findings

**Date:** 2026-08-28
**Rig:** IDS uEye line-scan camera, `device-id=1`, `ini/roi-dusk.ini`
**Pipeline:** idsueyesrc → intervalometer → videoflip → linescan → …
(bench: `gst/linescan/print_camera_cli.py`; production: `gst/linescan/launch_with_signal.py`)

**Goal:** run the line scan as fast as possible around the clock.

- **Night** — highest framerate that still yields a usable image. The limit is
  light: exposure (`≤ 1/fps`), then gain, then gain-boost.
- **Day** — highest framerate the *pipeline* can sustain. Light is not the limit
  (sensor does 1312 fps, exposure ~0.02–1.25 ms); the `linescan` per-frame roll
  copy is.
- **Transitions** — cross dawn/dusk unattended for months with no manual retuning
  (one control loop owns exposure + gain + gain-boost).

---

## TL;DR

### Night (light-limited)

- **Framerate is not auto-managed.** You set `--framerate`; the camera pins it and
  clamps *exposure* to `~1/fps`. Nothing in the pipeline lowers fps to gain light.
- **Sensor ceiling for this ROI is ~150–160 fps.** Requesting 200/250/300/400 all
  deliver ~155–160 fps actual. Requesting above ~200 only shortens the exposure cap
  for frames you never get — strictly worse.
- **Without gain-boost the scene is too dark at every framerate.** The intervalometer
  pegs exposure *and* gain (82) and still never reaches `target-brightness=80`.
- **With `gain-boost=true` the target band (70–90) is met from 100 up to ~300 fps.**
  Roughly doubles sensitivity.
- **Best night operating point: `--framerate 200` + gain-boost on.** ≈160 fps (the
  sensor ceiling), exposure auto-caps ~4.96 ms, gain settles ~69/82 with margin,
  brightness ~78.
- Gain-boost degrades image quality and is wrong for daytime — it is **not** set in
  `roi-dusk.ini` (that ini is shared by the day launch). Instead:
  - **`print_camera_cli.py`** emits `gain-boost=true` only for `--mode night` (bench).
  - **`launch_with_signal.py`** seeds `gain-boost` from `--mode`, and by default
    (`--auto-gain-boost`) hands ongoing control to the intervalometer, which
    toggles it as the third rung of its ladder — see [Running for months](#running-for-months--seamless-daynight-operation).

### Day (pipeline-limited)

- **The camera is not the limit; `linescan` is.** The sensor does 1312 fps at this
  ROI. The recorder pipeline caps at **~180 fps** because `linescan` re-`memcpy`s the
  whole `output-size`-wide roll (~21.7 MB) on *every* input frame.
- **Ceiling scales linearly with `output-size`:** `achieved ≈ 180 × 3584 / output-size`.
  `--output-size 448` reaches 800 fps — but that also shrinks the JPEG width 8× and
  makes rollovers 8× more frequent.
- **Fix (done):** the linescan `emit-every=N` property — accumulation stays
  per-frame, the big copy/push happens only every Nth frame (plus every rollover).
  `launch_with_signal.py --emit-every auto` sets `N = framerate / --display-fps`,
  so day runs full-rate at the default geometry. See "Higher framerate in daytime".

### Transitions (months, unattended)

- **Done:** gain-boost is now the intervalometer's third rung (exposure → gain →
  gain-boost) via `auto-gain-boost` (on by default in `launch_with_signal.py`), so
  dawn/dusk needs no manual mode switch or restart.
- **Still open:** `timelapse.csv` grows ~0.5 GB/day (logged every frame) and is wiped
  on restart — must be fixed for a long run.

---

## How the elements actually behave

### `idsueyesrc` pins fps, clamps exposure

Every runtime `g_object_set(cam, "exposure", …)` (the intervalometer does this
continuously) re-enters `gst_idsueyesrc_set_framerate_exposure()`
([`sys/idsueye/gstidsueyesrc.c:265-269`](../../sys/idsueye/gstidsueyesrc.c#L265-L269)),
which:

1. Re-asserts `is_SetFrameRate(hCam, src->framerate, &new_fps)` first
   ([`:1057`](../../sys/idsueye/gstidsueyesrc.c#L1057)) — fps stays exactly what you asked.
2. Queries the exposure range *at that fps* and clamps the requested exposure to
   `[min, ~1/fps]` ([`:1093-1102`](../../sys/idsueye/gstidsueyesrc.c#L1093-L1102)).

The `new_fps` out-param (the rate the sensor can actually sustain) is **discarded**,
so requesting more than the sensor can deliver is silent — you just get a shorter
exposure cap.

### `intervalometer` adjusts exposure + gain only

`gst_intervalometer_update_camera_settings()`
([`gst/intervalometer/gstintervalometer.c:704-796`](../intervalometer/gstintervalometer.c#L704-L796)):
when too dark it raises exposure first (up to `exposure-max`), then gain (up to
`gain-max`). It never touches framerate and has no gain-boost property.

`exposure-max` was left unset in `print_camera_cli.py`, so it is auto-queried from
the camera at startup — and the queried value already equals `1/fps` exactly
(9.96 / 6.62 / 4.96 ms at 100 / 150 / 200 fps), so the controller's model matched
the hardware. No explicit `exposure-max` needed.

The CSV logs the controller's *belief* (`filter->current_exposure`), not the camera
readback ([`:817-823`](../intervalometer/gstintervalometer.c#L817-L823)). They agreed
in these tests, but that is not guaranteed at the clamp boundary.

---

## Method

For each framerate: emit the night pipeline via `print_camera_cli.py`, swap sink for
`fakesink`, speed up convergence for the bench (`ramp-rate=fast`,
`update-interval=250` — steady state is ramp-rate independent), bound the run with
`num-buffers = fps * 25`, `GST_DEBUG=idsueyesrc:5,intervalometer:5`, snapshot
`timelapse.csv`. All runs fully converged (brightness at 90 % of run ≈ brightness at
end); gain reached its ceiling within 7–16 s.

"actual fps" = frames ÷ (last timestamp − first timestamp) in steady state.
"cap" next to an exposure value = exposure sat at the `1/fps` ceiling.

---

## Results — no gain-boost (`GainBoost=0`, as shipped)

| req fps | actual fps | exposure (ms) | gain | final brightness | in target 70–90? |
|--------:|-----------:|--------------:|-----:|-----------------:|:-----------------|
| 100 | ~100 | 9.96 | 82 (max) | **63** | no |
| 150 | ~150 | 6.62 | 82 (max) | **45** | no |
| 200 | ~161 | 4.96 (cap) | 82 (max) | **35** | no |
| 250 | ~160 | 3.96 (cap) | 82 (max) | **29** | no |
| 300 | ~158 | 3.30 (cap) | 82 (max) | **25** | no |
| 400 | ~156 | 2.46 (cap) | 82 (max) | **20** | no |

Every point is fully pegged and still under target. Brightness scales ~linearly with
exposure (gain fixed): ≈6.4–7.9 brightness units per ms.

## Results — `gain-boost=true`

| req fps | actual fps | exposure (ms) | gain | final brightness | in target 70–90? |
|--------:|-----------:|--------------:|-----:|-----------------:|:-----------------|
| 100 | ~100 | 5.25 | 65 | **73** | yes — exposure + gain both have headroom |
| 150 | ~150 | 5.46 | 65 | **76** | yes — headroom |
| 200 | ~160 | 4.96 (cap) | 69 | **78** | yes — gain headroom |
| 250 | ~157 | 3.96 (cap) | 74 | **73** | yes |
| 300 | ~160 | 3.30 (cap) | 80 | **78** | yes — barely, gain almost maxed |
| 400 | ~150 | 2.46 (cap) | 82 (max) | **66** | no — pegged, falls short |

Confirmed working at runtime: log shows `idsueyesrc … Gain boost enabled`
(`is_SetGainBoost`, [`gstidsueyesrc.c:300-308`](../../sys/idsueye/gstidsueyesrc.c#L300-L308)).

---

## Recommendations

### Params (no rebuild)

- **`--framerate 200` at night** — this is the sensor ceiling (~160 fps actual).
  Anything higher gives the same fps with a shorter exposure cap and a dimmer image.
- **Enable gain-boost at night** (see below). Without it, night is unusable at any fps.
- `--framerate 100` if you need a brighter/cleaner image and can accept half the
  line rate (brightness ~73 with boost, gain still at its floor).
- `target-brightness=80` is unreachable without boost — with boost it is met; leaving
  it at 80 is fine.
- Optional: raise `gain-max` toward 100 for ~+20 % brightness at the cost of noise.
- To lift the ~150–160 fps ROI ceiling itself, edit `roi-dusk.ini` (pixel clock /
  ROI height) — not the pipeline.

### Gain-boost per mode — done, in the launchers, not the ini

`roi-dusk.ini` is used by **both** the day and night launches, so `GainBoost=1`
there would also hit daytime (exposure 0.02 ms, abundant light) where boost only adds
noise. So it is set from `--mode` in the launchers instead:

- **`print_camera_cli.py`** (`build_command()`): emits `gain-boost=false` for
  `--mode day`, `gain-boost=true` for `--mode night`.
- **`launch_with_signal.py`**: same `--mode` seed on `idsueyesrc`, then the
  intervalometer owns it at runtime (next section).

### Optional `.c` changes (only if this becomes routine tuning)

- **`idsueyesrc`**: warn when `is_SetFrameRate`'s returned `new_fps` is well below the
  requested value — would flag 300/400 fps requests as unachievable instead of
  silently shrinking the exposure cap.
- **`intervalometer` CSV**: also log the camera readback
  (`g_object_get(cam, "exposure"/"gain"/"framerate")`) next to the controller's
  belief, so the log is trustworthy at the clamp boundary. (The CSV now has a
  `GainBoost` column, but it logs the controller's tracked state, not a readback.)

---

## Running for months — seamless day/night operation

The production recorder is
[`gst/linescan/launch_with_signal.py`](launch_with_signal.py) (long-lived Python
process, builds the pipeline via the GI API). `--mode day|night` is chosen **once at
launch** and only seeds `exposure`/`gain`/`gain-boost`; the intervalometer overrides
all three within seconds and then handles the whole diurnal brightness ramp on its
own (that part is already seamless — it is what the element is for).

Of the three things that were **not** seamless for a months-long run, #1 is now
done; #2 and #3 remain.

### 1. Gain-boost as the intervalometer's third rung — done

`gain-boost` roughly doubles sensitivity. Night is unusable without it (see tables
above); daytime is needlessly noisy with it. It is a runtime `idsueyesrc` property
(`is_SetGainBoost`); the intervalometer now drives it as the **third rung of its
ladder** (exposure → gain → **gain-boost**), so the full cycle is autonomous with no
external scheduler and daytime boost is structurally impossible — it only engages
when exposure *and* gain are both already pinned at max and the frame is still
outside the deadband on the dark side.

Implemented in `gst_intervalometer_update_camera_settings()` /
`gst_intervalometer_toggle_gain_boost()`
([`gstintervalometer.c`](../intervalometer/gstintervalometer.c)):

- new props: **`auto-gain-boost`** (bool, default FALSE) and **`boost-min-dwell`**
  (seconds, default 120) — the dwell blocks re-toggling on a passing cloud at dusk.
- `boost_active` is seeded from the camera's `gain-boost` in
  `query_camera_capabilities()`, then tracked.
- **too-dark**, after exposure and gain are both maxed: `gain-boost → TRUE`,
  `boost_active = TRUE`, gain snapped to mid-range (boost ~2×, so brightness
  doesn't jump), `last_boost_toggle_time` stamped.
- **too-bright**, after exposure and gain are both floored: `gain-boost → FALSE`,
  gain snapped to mid-range.
- Hysteresis: existing `update-interval` (1 s) + `brightness-deadband` (10) +
  `ramp-rate=slow`, plus the "both rails pinned before toggling" rule and
  `boost-min-dwell`.
- The CSV gained a trailing `GainBoost` column.

`launch_with_signal.py` sets `auto-gain-boost` (default on, `--no-auto-gain-boost`
to disable) and `boost-min-dwell` (`--boost-min-dwell`). The `--mode` gain-boost
bit is now just the startup seed. `print_camera_cli.py` (bench) does **not** enable
`auto-gain-boost` — it keeps the static `--mode` seed for deterministic runs.

### 2. `timelapse.csv` grows without bound

`gst_intervalometer_write_log()` is called **every frame** and `fflush`es every frame
([`gstintervalometer.c:589-592`](../intervalometer/gstintervalometer.c#L589-L592),
[`:817-825`](../intervalometer/gstintervalometer.c#L817-L825)). At ~160 fps that is
~13.8 M rows/day (~0.5 GB/day, ~160 fsync/s) — untenable over months. The path is
also a fixed relative `timelapse.csv` opened `"w"`, so every restart wipes history.

Fix (small): move the `write_log()` call **inside** the `if (should_update)` block so
it logs once per `update-interval` (1 Hz → ~3 MB/day). Also make the path a property
and open `"a"`, or have `launch_with_signal.py` pass a dated filename
(`timelapse_YYYYMMDD.csv`).

### 3. Framerate at night: leave it at 200

At night the intervalometer holds a long exposure, so `1/exposure` is the practical
cap and ~150–200 fps is all you get regardless. Leave `--framerate 200`.

**Daytime is different — see the next section.**

---

## Higher framerate in daytime — the pipeline is the limit, not the camera

The camera is not the 200 fps limit. `ini/roi-dusk.ini` was captured at
**1312 fps** (`[Timing] Framerate=1312.056738`, `Pixelclock=474`, ROI 2016×20), and
daytime exposure (~0.02–1.25 ms) never constrains fps.

**The recorder pipeline caps at ~180 fps**, and it is
[`gstlinescan.c:623`](gstlinescan.c#L623):

```c
memcpy (map_out.data, filter->line_buffer, map_out.size);
```

`linescan` is not in-place and re-emits the **entire accumulated roll** on *every
input frame*. At `output-size=3584` that is a ~21.7 MB (3584×2016×3) alloc + memcpy +
`videoconvert` pass + free per frame ≈ 3.9 GB/s at 180 fps. That memcpy is the wall.
The preview branch (`videoconvert`+`videoscale` on the same 21.7 MB frames) is a
second, smaller tax on top.

### Measured (night, `--no-preview`; brightness irrelevant, this is a throughput test)

`launch_with_signal.py --mode day --framerate 800 --output-size N --no-preview`,
achieved fps from `timelapse.csv`:

| `output-size` | roll buffer | achieved fps |
|--------------:|------------:|-------------:|
| 3584 (default) | 21.7 MB | **180** |
| 1792 | 10.8 MB | **365** |
| 896 | 5.4 MB | **722** |
| 448 | 2.7 MB | **796** (= the 800 request; true ceiling higher) |
| 224 | 1.4 MB | **801** (= the 800 request) |

Dead linear: `achieved ≈ 180 × 3584 / output-size`. Also confirmed the ceiling is
*not* the camera and *not* the preview branch — these runs were `--no-preview` and
requesting 200/400/800/1312 with `output-size=3584` all pinned at ~180.

### To hit 800 fps in daytime

**Run day mode with `--output-size 448`** (delivers 800 with margin; 896 gets only
~720). But `output-size` is not free — it is simultaneously:

- the roll **width** in px = JPEG width (448 vs 3584 → 8× less horizontal resolution);
- **frames per rollover** = JPEG cadence (at 800 fps, 448 → a JPEG every 0.56 s vs
  4.5 s at 3584 → ~8× more, smaller files);
- the basis of the `--aspect` derivation (448×2016 is a tall strip, not 16:9).

So decide the daytime roll geometry deliberately; smaller `output-size` is a
resolution/cadence trade, not a pure win.

### Proper fix (implemented): decouple emit rate from accumulation

Nothing downstream needs 800 full-roll buffers/sec — the preview wants ~30 fps and the
JPEG path only fires at rollover. `linescan` now has an **`emit-every=N`** property
(default 1 = old behaviour): it keeps accumulating one column per frame (cheap), but
only runs the 21.7 MB memcpy + `gst_pad_push` every Nth frame, and always emits one
at rollover so the JPEG cadence is unchanged. On the skipped frames it returns
`GST_BASE_TRANSFORM_FLOW_DROPPED` and its `prepare_output_buffer` override hands
BaseTransform an empty placeholder, so the ~21.7 MB output buffer is never even
allocated on those frames.

`launch_with_signal.py` exposes `--emit-every` (default `auto` =
`round(framerate / --display-fps)`), so day mode runs the camera at full rate with
`output-size=3584` and the roll geometry intact:

```
uv run gst/linescan/launch_with_signal.py --mode day --framerate 800
# auto -> emit-every 27 (800/30); preview + JPEG cadence unchanged
```

Implementation: [`gstlinescan.c`](gstlinescan.c) `gst_linescan_transform` /
`gst_linescan_prepare_output_buffer`; property state `emit_every` /
`frames_since_emit` / `will_emit` in [`gstlinescan.h`](gstlinescan.h).

**Caveat:** the src caps still carry the camera `framerate`, so downstream sees a
buffer rate lower than the declared framerate (typical for a decimator). The preview
branch already re-times with `videorate` + a `framerate=N/1` capsfilter, and the
JPEG branch only reacts to the `rollover` signal, so neither is affected. Anything
new that keys off linescan's output-buffer timing at the full rate would need a
`transform_caps` fix to divide the framerate by `emit-every`.

### Still needs a real daytime check

These throughput runs were at night (exposure floored, image black). What tonight
cannot verify: image brightness at 800 fps in daylight, where exposure is capped at
`1/800 = 1.25 ms`. Likely fine in full sun, but confirm when it's light out.

### Also for an unattended months-long run

- Supervise the process (Task Scheduler / `launch_linescan.ps1` per `STARTUP.md`) so
  a camera hiccup that hits `on_message` ERROR → `loop.quit()` gets restarted.
- Watch results-disk free space; JPEG-per-rollover accumulates.

---

## Live monitoring

- `Get-Content timelapse.csv -Wait -Tail 20` — CSV is `fflush`ed per frame; watch
  brightness / exposure / gain converge in real time.
- Startup line `intervalometer … Queried exposure_max: N ms` — the key diagnostic;
  equals `1/fps` when framerate is achievable.
- `GST_DEBUG=idsueyesrc:5` — per-set exposure clamp messages
  (`Requested exposure … above maximum … clamping`).

---

## Raw data

Scratchpad for this session:
`night_<fps>.csv` (no boost), `night_gb_<fps>.csv` (boost),
`stderr_<fps>.log` / `stderr_gb_<fps>.log`, `cmd_<fps>.txt` / `cmd_gb_<fps>.txt`,
sweep scripts `night_fps_sweep.sh` / `night_fps_sweep_gainboost.sh`.
