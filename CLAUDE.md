# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Automated water–oil liquid-liquid extraction system: a camera plus classical computer vision locates the
interface between two liquid phases, then drives a pump to withdraw the lower layer to a target point. Water and
vegetable oil are the target pair — the research question is whether classical CV is enough, not whether the
solvent is hazardous, so a non-toxic organic solvent satisfies it. Runs entirely on a single Raspberry Pi 5.
Adapted from Chem-SDI (Fu et al., *Microchemical Journal* 227, 2026), with deep learning and bespoke hardware
removed.

Full documentation: [`PRD.md`](docs/PRD.md) (requirements + pass/fail gates) · [`README.md`](README.md) (code layout) ·
[`BACKLOG.md`](docs/BACKLOG.md) (Agile backlog by phase, each item with a short ID) · [`docs/developments/`](docs/developments/)
(roadmap -> milestones -> sprints -> stories -> sprint backlog, numbered `0X_*.md`, tables + Mermaid diagrams) ·
[`PROCESS.md`](docs/PROCESS.md)
(development workflow: Agile, Spec-Driven Development, Test-Driven Development) · [`CHANGELOG.md`](CHANGELOG.md)
(dated, verified history) · research-plan flow diagram (separate artifact).

---

## Hardware

| Component | Spec | Notes |
|---|---|---|
| Raspberry Pi 5 | Single board, does both vision and control | `ssh somdui@<pi-ip>` — IP changes with network (has been 192.168.100.242, 172.20.10.3) |
| Camera | Camera Module 3 (imx708 sensor) via `picamera2` | Manual exposure/AWB (auto disabled) — values are specific to the lighting on site |
| Vessel | **Pear-shaped separatory funnel, 125 mL** | Stopcock physically removed · the pump draws from a tube entering through the top, not the bottom · not a cylinder — V = πr²h does not apply, needs multi-point calibration |
| Pump | GROTHEN G928 peristaltic pump, 24V | Driven via an HW-039 (BTS7960) motor driver, not a relay — **not wired yet** |
| PSU | S-50-24 switching supply, 24V 2A | Voltage confirmed matching the pump's rating |

---

## Running things

```bash
# On the Pi — live stream + web page (http://<pi-ip>:5000)
cd ~/extractlab
nohup ./run_stream.sh > run_stream.log 2>&1 &     # supervisor: relaunches itself if the camera stalls
#   to stop for good: kill <pid of run_stream.sh>  or  pkill -f run_stream

# Tune camera/ROI without touching code — env vars:
EXPOSURE_US=25000 GAIN=8 WB_RED=2.14 WB_BLUE=1.76 \
ROI_X=555 ROI_Y=370 ROI_W=175 ROI_H=290 python3 realtime_stream.py

# Tests
python3 -m pytest -q                       # unit — tests/test_tracking.py (S1-S6), test_volume_model.py
python3 -m pytest tests/test_tracking.py   # "run a single test file"
python3 -m pytest -k s4                    # "run a single test"
python3 demo.py            # integration smoke test — must print RESULT: PASS
python3 turbidity_dct.py   # modules without pytest coverage yet have a __main__ self-check
python3 volume_model.py
python3 synthetic_data.py
# no lint/build step · boundary_detection.py is exercised through demo.py

# Analyze one real photo
python3 analyze_real_photo.py photo.jpg --roi X Y W H --profile-csv prof.csv

# Record a run while draining: click the record button on the web page -> records/rec_*.csv
#   or from another machine: python3 track_log.py drain.csv
```

`picamera2` comes from apt, not pip: `sudo apt install -y python3-picamera2` · a venv needs `--system-site-packages`

---

## File layout

| File | Role |
|---|---|
| `boundary_detection.py` | Finds `boundary_y` + `conf` from a row-wise intensity gradient — pure numpy/OpenCV array math, no camera I/O |
| `tracking.py` | `Tracker` — filters `boundary_y` over time (median + jump-reject + a `draining` gate) · hardware-free · owns `CONFIDENCE_THRESHOLD` + `TRACK_*` · has pytest coverage |
| `turbidity_dct.py` | `dct_sharpness()` + `TurbidityMonitor` — decides warming_up / turbid / clearing / clear |
| `volume_model.py` | `FrustumModel` + `CalibrationTable` (interpolate / JSON / inverse) — the geometry is still a placeholder |
| `synthetic_data.py` | Generates fake frames/draining sequences to test against before real data existed |
| `demo.py` | Wires the four modules above together, runs them against synthetic data + assertions (smoke test) |
| `analyze_real_photo.py` | CLI: boundary + sharpness against a single image, `--roi`, `--calib`, `--profile-csv` |
| `realtime_stream.py` | MJPEG stream + status panel + `/status` `/records` `/record/start|stop` endpoints · `Tracker` filters `boundary_y_smooth` · watchdog against a stalled camera |
| `run_stream.sh` | Supervisor: relaunches `realtime_stream.py` every time it exits (pairs with the watchdog) |
| `track_log.py` | Polls `/status` -> CSV from another machine |
| `records/` | CSV output from drain-test runs (one row per frame) |

---

## Architecture — runtime data flow

The code splits into two clearly separate worlds:

**1. Hardware-free analysis modules** — `boundary_detection`, `turbidity_dct`, `volume_model`.
Pure functions/classes that take numpy arrays (no camera I/O, no `picamera2`/`flask` imports).
`demo.py` wires all three together and runs them against frames from `synthetic_data.py` — the algorithm can be
fully tested on any machine. The detection chain in `boundary_detection.py`: crop the ROI -> per-row mean
brightness -> smooth -> `np.gradient` -> `argmax(|grad|)` (with an edge margin) -> that row is the interface,
`|grad|` there is `conf`.

**2. The live system `realtime_stream.py`** (needs a Pi + camera) — shaped as **a single producer thread with
several Flask-threaded consumers**:
- The `_capture_loop` thread is the single producer: `capture_array()` -> `detect_boundary(frame, ROI)` ->
  `tracking.Tracker.update(raw, conf, draining=_rec["on"])` -> writes `_latest_jpeg` + the `_status` dict + (while
  recording) one CSV row. **`draining=True` while recording -> the Tracker never re-seeds** (during a drain the
  interface moves slowly, so a large jump always means a false lock · replay of `rec_20260904_115249.csv`: max
  jump 151 -> 12 px).
- Flask only serves: `/video_feed` streams `_latest_jpeg`, `/status` returns `_status` plus recording state,
  `/records` + `/record/start|stop` manage files under `records/`.
- The `_watchdog` thread: if no new frame for 15s -> `os._exit(1)`, then `run_stream.sh` (the outer loop)
  relaunches it -> a stalled camera recovers on its own.
- **All configuration lives as module-level constants in `realtime_stream.py`**; most are overridable by env var
  (`ROI_X/Y/W/H`, `EXPOSURE_US`, `GAIN`, `WB_RED/BLUE`). `CONFIDENCE_THRESHOLD` and the `Tracker` parameters
  (`TRACK_*`, in `tracking.py`) are constants — the knobs that Phase 1's work (making the smoothed value stable)
  is currently tuning.

One frame cycle, producer side, matches this prose exactly:

```mermaid
sequenceDiagram
    participant Cap as _capture_loop (producer)
    participant Cam as picamera2
    participant Det as detect_boundary()
    participant Trk as Tracker.update()
    participant St as _status dict
    participant CSV as records/*.csv
    participant Web as Flask (video_feed, status, records)

    loop every frame
        Cap->>Cam: capture_array()
        Cam-->>Cap: frame (BGR)
        Cap->>Det: detect_boundary(frame, ROI)
        Det-->>Cap: boundary_y, conf
        Cap->>Trk: update(boundary_y, conf, draining=_rec["on"])
        Trk-->>Cap: boundary_y_smooth
        Cap->>St: write _latest_jpeg + _status
        opt recording is on
            Cap->>CSV: append one row
        end
    end

    Web->>St: read (on each request, no writes)
```

The `_status` dict is the contract between the two halves: the capture loop is the only writer, `/status` (and
`track_log.py`, the web page) are readers.

---

## Design decisions (vs. the paper)

| Topic | Paper | What we use | Why |
|---|---|---|---|
| Finding the liquid region | YOLOv8n-seg | Hand-cropped ROI | The research question is "is classical enough?" — bringing ML back in makes it meaningless |
| Help seeing the interface | — | None (try the direct approach first) | Prove the signal is strong enough with real data before adding anything |
| Height -> volume | Frustum | Frustum / multi-point calibration — same as the paper here | The vessel is a funnel, not a cylinder, so no simpler linear fit is available |
| Phase separation | Stopcock + stepper motor | Stopcock removed; pump draws through a tube entering the top + motor driver | Use what's on hand, no stepper needed |
| Compute | Orange Pi + STM32 | Single Pi 5 + GPIO + motor driver | Less hardware (risk: timing jitter untested) |

Kept from the paper: DCT turbidity monitoring and row-wise gradient boundary detection (both purely classical).

---

## Status (as of 13 Oct 2026)

- **P0 done** — core modules + tooling complete, git + pushed to GitHub (`Cherrpxp/extractlab`)
- **P1 nearly done — one item left (`P1-08`)** — black background + tight ROI -> the detector locks onto the
  real water/oil interface (`conf` ~12 vs. a threshold of 3). First real drain test, 219s: the trend was correct
  (moved 104 px) · the `Tracker` was fixed to never re-seed during a drain -> replaying the same data: max jump
  151 -> 12 px, jumps over 20px: 14 -> 0. A separate finding — the detector locking onto a metal stopcock instead
  of the real interface — turned out to be specific to the funnel's old configuration; the stopcock has since
  been physically removed (the pump now draws from a tube entering through the top), so that failure mode no
  longer applies. **Still need a fresh live drain run on the reconfigured funnel to formally confirm the gate.**
- **P2–P7 not started** (calibrate volume (funnel geometry, not linear) -> wire the pump (24V + motor driver) ->
  closed loop -> RMSE over 10 runs -> report).

---

## Known gotchas (read before touching)

- **`git push` from the Pi's terminal doesn't work** — no credential (`could not read Username`) · push via the
  Sync button in VS Code instead.
- **The camera's CSI cable is fragile** — handling/moving the camera a lot causes it to drop out intermittently
  (`Camera frontend has timed out`) · the sensor enumerates fine but delivers no frames = a cable or connector
  issue · the camera needs to be mounted rigidly with strain relief · a watchdog + `run_stream.sh` already
  recover at the software level, which treats the symptom, not the cause.
- **`picamera2`'s `"RGB888"` format already returns a BGR array** — do not call
  `cvtColor(..., RGB2BGR)` on top of it (this once turned the yellow organic layer blue).
- **`FrameDurationLimits` must be set wide**, or the pipeline silently clamps `ExposureTime` to ~33 ms.
- **Camera settings (exposure/gain/WB) are specific to the lighting where they were tuned** — moving the rig or
  changing the lights requires recalibrating (run AWB+AE in auto, read the values back, bake them in as manual
  again).
- **Calibration (ROI, mm/px, threshold, the volume table) is tied to the exact setup it was measured on** — it
  breaks the moment the camera or vessel moves.
- **Never wire the pump into the Pi's GPIO / 5V / GND pins** — the pump runs on 24V, far above GPIO's safe
  ~16 mA · this has happened once already, on the earlier 12V pump · `vcgencmd get_throttled` currently reads
  0x0 (board is healthy). Only the HW-039 driver's logic pins (RPWM, R_EN, GND) connect to GPIO — its B+/B-/M+/M-
  power terminals never do.
- **A VPN on the machine viewing the web page** can block access to the Pi on the same LAN — disable it first if
  the page won't load.
- `pkill -f realtime_stream` from the terminal will kill its own shell if that same command line contains the
  string `realtime_stream` — kill by PID, or run it as a separate command.
