# Adaptive Framerate — the intervalometer's 4th rung

**Added:** 2026-08-28. Implements item #4 ("make framerate adaptive") from
[`NIGHT_FPS_TUNING.md`](NIGHT_FPS_TUNING.md) → *Transitions*.

**Goal:** run the line scan as fast as the light allows, around the clock, from a
single launch — no dusk/dawn restart, no external scheduler, no image-quality
hit from over-requesting fps at night.

---

## Why this is possible cheaply

- **`idsueyesrc` already takes a runtime `framerate` change.** Setting the
  `framerate` GObject property while streaming calls
  `gst_idsueyesrc_set_framerate_exposure()` →
  `is_SetFrameRate(hCam, fps, &new_fps)` and then re-clamps exposure to `~1/fps`
  ([`gstidsueyesrc.c:271-276`](../../sys/idsueye/gstidsueyesrc.c#L271-L276),
  [`:1051`](../../sys/idsueye/gstidsueyesrc.c#L1051)).
- **`framerate` is never written into the src caps**
  ([`gstidsueyesrc.c:551-554`](../../sys/idsueye/gstidsueyesrc.c#L551-L554) sets
  only format/width/height). So changing it mid-stream triggers **no caps
  renegotiation** — it is a pure side-band SDK call. The pipeline already
  tolerates buffer-rate ≠ nominal-rate (the `emit-every` decimator does the same
  thing; the preview branch re-times with `videorate`).
- The **intervalometer** already owns the camera element, the smoothed
  brightness signal, a rung ladder (exposure → gain → gain-boost), dwell /
  anti-chatter machinery, and the CSV. Framerate becomes **rung 4**.

> **Note on the "~160 fps night wall"** in `NIGHT_FPS_TUNING.md`: those bench
> runs used `emit-every=1`, so ~160 was mostly the *pipeline* memcpy wall, not a
> sensor limit. With `--emit-every auto` (the launcher default) the night limit
> moves to `~1/exposure` minus readout, so night framerate genuinely is a
> variable worth controlling.

---

## The 4-rung ladder

`gst_intervalometer_update_camera_settings()` in
[`../intervalometer/gstintervalometer.c`](../intervalometer/gstintervalometer.c).
Framerate is appended as the **outermost rung on both sides** — it only moves
once every existing rung is exhausted, so the well-tuned diurnal exposure/gain
ramp is byte-for-byte unchanged until it hits a rail.

```
too dark  (brightness < target − deadband):
    raise exposure ── to exposure_max (= 1/fps cap)
    → raise gain ──── to effective gain ceiling
    → gain-boost on ─ (rung 3, if auto-gain-boost)
    → LOWER fps ───── rung 4: fps /= framerate-step   [dwell-gated]
                      raises exposure_max, exposure rung then climbs into it

too bright (brightness > target + deadband):
    lower exposure ── to exposure_min (~0.02 ms floor)
    → lower gain ──── to gain floor
    → gain-boost off  (rung 3 mirror)
    → RAISE fps ───── rung 4: fps *= framerate-step   [dwell-gated]
                      shrinks exposure_max; exposure rung refills toward it
```

Because rung 4 sits *after* the `else if` chain, the dark-side lower only fires
when exposure is already at the `1/fps` cap **and** gain is at its ceiling
**and** gain-boost is already on (or `auto-gain-boost` is off). The bright-side
raise only fires when exposure is floored, gain is floored, and boost is off.
That is exactly "every cleaner knob is spent".

### Effective ceiling — the day/night split

`gst_intervalometer_effective_framerate_max(filter, boosted)` mirrors
`effective_gain_max`:

| state | ceiling |
|---|---|
| gain-boost **off** (day) | `framerate-max` |
| gain-boost **on** (night) | `framerate-max-boost` (if set, else `framerate-max`) |

`boost_active` is the controller's structural proxy for "it's night" (boost can
only engage after exposure *and* gain are both pinned). When boost engages at
dusk, `update_camera_settings()` **snaps fps down** to `framerate-max-boost`
immediately (dwell bypassed), same as the gain snap-down. When boost drops at
dawn, the ceiling rises again and rung 4 ramps fps up gradually.

### Anti-chatter

- `framerate-min-dwell` (default 20 s) — minimum hold between rung-4 changes.
  Ceiling snap-downs bypass it.
- Inherited: `update-interval` (1 s), `brightness-deadband` (10), `ramp-rate`,
  and the "all lower rungs pinned first" structural gate.
- Step is multiplicative (`fps *= 1.15` / `fps /= 1.15`). Full 800→150 descent ≈
  `log₁.₁₅(800/150)` ≈ 12 steps ≈ 4 min at 20 s dwell — comfortably inside a
  20–40 min dusk.

### exposure_max coupling

Every `set_framerate()` re-derives `exposure_max` from the camera
(`is_Exposure GET_EXPOSURE_RANGE`, fallback `1000/fps`) and pulls
`current_exposure` / `target_exposure` back under the new cap. **Pinning
`exposure-max` while adaptive fps is active is therefore unsupported** — the
launcher leaves it auto-queried, which is the norm.

---

## New intervalometer properties

| property | type | default | meaning |
|---|---|---|---|
| `framerate-min` | double | 0 | Rung-4 floor (fps). **Adaptive fps is active iff `framerate-min > 0` AND `framerate-max > framerate-min` AND the camera has a `framerate` property.** 0/0 ⇒ feature inert (full backward compat). |
| `framerate-max` | double | 0 | Rung-4 ceiling / daytime target. |
| `framerate-max-boost` | double | 0 | Lower ceiling while gain-boost is on (= night). 0 ⇒ use `framerate-max` in both states. |
| `framerate-step` | double | 1.15 | Multiplicative step per adjustment. |
| `framerate-min-dwell` | double | 20 | Min seconds between rung-4 changes. |

`current_framerate` is seeded from the camera in `gst_intervalometer_reset()`
(also used for the new CSV column) and snapped into `[min, effective-max]` if the
`--mode` seed left it outside.

### CSV

`timelapse_<date>.csv` gains a trailing **`Framerate`** column (controller's
tracked value, like `GainBoost`). Header is now:

```
Frame,Time_s,Brightness,Exposure_ms,Gain,Target_Brightness,GainBoost,Framerate
```

Appending to a pre-change 7-column file yields a one-day mix of 7- and 8-wide
rows — cosmetic only.

---

## `launch_with_signal.py` wiring

- `--adaptive-framerate` / `--no-adaptive-framerate` — **on by default**.
- `--framerate` is now only a **seed** (and the fixed rate when adaptive is off).
  Omitted ⇒ seed = `framerate-max` (day) or `framerate-max-boost` (night).
- `--framerate-min` **150**, `--framerate-max` **800**, `--framerate-max-boost`
  **400**, `--framerate-step` **1.15**, `--framerate-min-dwell` **20** — the
  values chosen for this rig (night range 150–400, day range 300–800; the day
  floor of 300 is where the controller naturally settles, not a hard clamp — the
  hard floor is 150).
- `--emit-every auto` is now `round(framerate-max / --display-fps)` = `round(800
  / 30)` = **27**, sized for the run's *peak* rate. At a night fps of ~200 the
  live preview then runs at ~7 fps; JPEG cadence is unaffected (linescan always
  emits on rollover).

---

## Transition walk-throughs

**Dusk.** Light falls → exposure climbs to the `1/fps` cap → gain climbs to
`gain-max` → gain-boost engages (rung 3), gain recentres, **fps snaps 800→400**
→ gain climbs again to the boosted ceiling → **rung 4 lowers fps** 400→348→…→150
by ÷1.15 every ≥20 s, each step lifting `exposure_max` so the exposure rung
refills. Monotonic, no scheduler.

**Dawn.** Mirror. Light rises → exposure drops to floor → gain drops to floor →
gain-boost drops (rung 3 mirror), ceiling rises 400→800 → **rung 4 raises fps**
by ×1.15 until `exposure` can no longer be held at floor without going bright,
or 800 is reached.

**Steady daylight.** Brightness in the deadband ⇒ `update_camera_settings()`
returns early ⇒ fps holds. If fps overshot (image went dark) brightness drops
below the band → dark side → rung 4 lowers it back. The deadband is the stable
attractor: *the highest fps that still meets target brightness.*

---

## Known v1 characteristics / limitations

1. **Daytime settles with exposure near its floor**, not a mid value — rung 4 is
   appended after the exposure rung, so exposure is spent down before fps climbs.
   Harmless (0.02 ms is what `--mode day` already runs), but it means the dawn
   fps ramp *lags* the exposure drop by a few minutes. If that proves too
   sluggish on-rig, reorder the bright side to `boost↓ → gain↓ → fps↑ →
   exposure↓` with a `current_exposure < 0.7·exposure_max` guard.
2. **`emit-every` is fixed for the run** at the `framerate-max` cadence, so night
   preview is slow (~7 fps). Clean follow-up: have the intervalometer also drive
   `linescan`'s `emit-every` on each fps change (needs the linescan element name
   + target display-fps passed in).
3. **CSV schema bump** (see above).
4. **`framerate-max` 800 in daytime is unverified on-rig** — throughput was only
   bench-tested at night with a black image. Confirm brightness holds at 800 fps
   (1.25 ms exposure cap) in real daylight, and that the pipeline sustains 800
   with `--output-size 3584` + `emit-every 27`.

---

## Test plan

### Bench (no real sky — walk the setpoint instead)

```
uv run gst/linescan/launch_with_signal.py --mode night --run-seconds 180 \
  --gst-debug --gst-debug-level 4 --no-preview
```

- `GST_DEBUG=intervalometer:5,idsueyesrc:4` — watch `Framerate rung: X -> Y fps`
  and idsueyesrc `is_SetFrameRate` lines.
- Force a "gets brighter" ramp: bump `target-brightness` down over the run (or
  uncover the lens); confirm fps climbs by ×1.15 steps, capped at the effective
  ceiling, dwell respected.
- Force "gets darker": raise `target-brightness` / cover the lens; confirm the
  full ladder runs (exposure → gain → boost → **fps down**) and fps floors at
  `framerate-min`.
- Restart mid-run with a stale high seed (`--framerate 700 --mode night`);
  confirm `reset()` snaps it to 400 at once, not via a ramp.
- `timelapse_<date>.csv` has the `Framerate` column and it moves.

### On-rig (the real check)

- One launch spanning a full dusk **and** dawn with `--gst-debug-level 4`; grep
  the log for every `Framerate rung` / `snapping down` and eyeball the JPEGs at
  each plateau for noise/brightness.
- Confirm the night plateau image quality at whatever fps rung 4 settles on with
  `--gain-max 35 --framerate-max-boost 400`.
- Daylight: confirm 800 fps holds brightness and the pipeline sustains it
  (`achieved fps` in the CSV ≈ 800).
