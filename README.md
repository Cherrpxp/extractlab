# extractlab — Automated Water–Oil LLE

Detects the interface between two immiscible liquid phases with a camera, then drives a pump to separate them
automatically. Water and vegetable oil are the target pair — the research question is whether classical
computer vision is enough, not whether the solvent is hazardous, so a non-toxic organic solvent satisfies it.
Uses **classical computer vision only** — no model training.

Adapted from **Chem-SDI** (Fu et al., *Microchemical Journal* 227, 2026), with the deep-learning and bespoke-
hardware parts removed, keeping DCT turbidity monitoring and row-wise gradient boundary detection.

Full requirements and reasoning: [`PRD.md`](docs/PRD.md) · working context for development: [`CLAUDE.md`](CLAUDE.md) ·
Agile backlog: [`BACKLOG.md`](docs/BACKLOG.md) · roadmap/milestones/sprints/stories/sprint-backlog:
[`docs/developments/`](docs/developments/) · development process (Agile/SDD/TDD): [`PROCESS.md`](docs/PROCESS.md) ·
dated, verified history: [`CHANGELOG.md`](CHANGELOG.md) · research-plan flow diagram (separate artifact).

```
extractlab/
├── README.md, CLAUDE.md        # repo-root docs (GitHub / Claude Code conventions)
├── CHANGELOG.md                # dated, verified history — see docs/BACKLOG.md for item IDs
├── docs/                       # PRD.md, BACKLOG.md, PROCESS.md
│   └── developments/           # 01_roadmap .. 05_sprint_backlog.md (tables + Mermaid)
├── boundary_detection.py       # core algorithms — flat, no build step, run directly
├── tracking.py
├── turbidity_dct.py
├── volume_model.py
├── synthetic_data.py
├── demo.py                     # integration smoke test
├── analyze_real_photo.py       # CLI tools
├── track_log.py
├── realtime_stream.py          # the live system (needs a Pi + camera)
├── run_stream.sh               # supervisor for realtime_stream.py
├── tests/                      # pytest suite
├── records/                    # CSV output from drain tests
└── requirements.txt
```

---

## How it works

Gray/dashed = not built yet — see `docs/BACKLOG.md` for the phase ID on each pending step.

```mermaid
flowchart TD
    A["Camera frame (BGR)"] --> B["Crop ROI"]
    B --> C["Row-wise mean brightness -> smooth -> np.gradient -> argmax(abs)"]
    C --> D["boundary_y, conf"]
    D --> E["Tracker.update()\nmedian + jump-reject + draining gate"]
    E --> F["boundary_y_smooth"]

    A --> G["dct_sharpness() / TurbidityMonitor"]
    G --> H["warming_up / turbid / clearing / clear"]

    F -. "P2" .-> I["CalibrationTable: height -> volume (mL)"]
    H -. "gates start" .-> J
    I --> J["Pump start/stop decision — P4"]
    J -. "P3, not wired" .-> K["HW-039 motor driver -> 24V pump"]

    classDef pending fill:#f5f5f5,stroke:#999,stroke-dasharray: 4 4,color:#666
    class I,J,K pending
```

`boundary_detection.py` + `turbidity_dct.py` run off the same frame in parallel; `tracking.py` is the only part
that remembers anything across frames. See `CLAUDE.md` for the full producer/consumer thread diagram around this.

---

## Project Timeline

The five `crit` milestones are real deadlines from the department syllabus (`2302493/499`, academic year
2569/2026), not estimates — everything else is a proposed pace. Full detail and the rationale behind the pacing:
[`docs/developments/02_milestones.md`](docs/developments/02_milestones.md).

```mermaid
gantt
    title extractlab timeline — anchored to the 2302493/2302499 syllabus
    dateFormat YYYY-MM-DD
    axisFormat %b %Y

    section Fixed deadlines (syllabus, not estimates)
    Safety cert exam, 20% of 2302493        :crit, milestone, dl1, 2026-09-30, 0d
    Progress report, P ภาคต้น (SP_CH_S4)     :crit, milestone, dl2, 2026-11-27, 0d
    Full report due, 20% of 2302499         :crit, milestone, dl3, 2027-04-23, 0d
    Oral + poster exhibition, 30%           :crit, milestone, dl4, 2027-05-13, 0d
    Final complete report                   :crit, milestone, dl5, 2027-05-18, 0d

    section P1 - detect & track (estimated)
    P1-08 confirm live                      :active, p1, 2026-10-08, 10d

    section P2 - calibrate volume
    P2-02..04 measure, fit, verify          :done, p2, 2026-10-16, 1d

    section P3 - wire the pump (estimated)
    P3-01..06 motor driver + pump.py        :p3, after p1, 25d

    section P4 - closed loop (estimated)
    P4-01..05 combine + dry run             :p4, 2027-01-05, 26d

    section P5 - repeatability study (estimated)
    P5-01..03 10-run RMSE                   :p5, after p4, 26d

    section P6 - write the report (estimated)
    Draft report                            :p6, after p5, 40d
    Rehearse presentation                   :p6b, 2027-05-01, 12d
```

---

## Status at a glance

**Current phase: P1/P2** (detect & track the interface; height -> volume calibration) — see
[`CHANGELOG.md`](CHANGELOG.md) for the dated, verified history behind this table and
[`BACKLOG.md`](docs/BACKLOG.md) for the one open P1 item (`P1-08`).

| Done | In progress | Not started |
|---|---|---|
| Core algorithms: `boundary_detection`, `turbidity_dct`, `volume_model`, `synthetic_data`, `demo` (`RESULT: PASS`) | Re-running a live drain on the reconfigured funnel to formally confirm the P1 gate | Wiring the pump safely (24V + HW-039 motor driver) |
| `tracking.py` — temporal filter, unit-tested (`tests/`), validated by replaying a real drain recording | | Closed-loop control, a 10-run RMSE study, the final report |
| `realtime_stream.py` — live view, status panel, in-browser recording, CSV browser, self-healing watchdog | | |
| Height -> volume calibration: ruler-based (RMSE 0.589 mL) and camera-direct (RMSE 0.436 mL) tables, both under the 2 mL target | | |

The detector reliably locks the real water/oil interface in a tightly-cropped, dark-background setup
(`conf` ~12 vs. a threshold of 3). It has **not yet** been confirmed live with the current tracker fix. A
separate finding — the detector locking onto a stopcock instead of the interface — turned out to be specific to
an earlier funnel configuration; the stopcock has since been physically removed (the pump now draws from a tube
entering through the top), so that failure mode no longer applies. See `PRD.md` §5, risk 1, for the full
reasoning.

---

## Hardware

| Component | Spec | Notes |
|---|---|---|
| Raspberry Pi 5 | Single-board compute, vision + control | `ssh somdui@<pi-ip>` — IP varies by network |
| Camera | Camera Module 3 (imx708) via `picamera2` | Manual exposure/AWB tuned on site |
| Vessel | Pear-shaped separatory funnel, 125 mL | Stopcock physically removed; the pump draws from a tube entering through the top, not the bottom |
| Pump | GROTHEN G928 peristaltic pump, 24V | Driven via an HW-039 (BTS7960) motor driver, not a relay — **not wired yet** |
| PSU | S-50-24 switching supply, 24V 2A | Voltage confirmed matching the pump's rating |

### Pump safety

**Never wire the pump directly into the Pi's GPIO / 5V / GND pins.** The pump runs on 24V, far above what GPIO
safely supplies. This has been done by mistake once already, on the earlier 12V pump (`vcgencmd get_throttled`
currently reads `0x0` — the board appears unharmed).

**The correct wiring (not yet built):** the 24V PSU feeds the HW-039 motor driver's power terminals (B+/B-),
which drive the pump (M+/M-) — none of that touches the Pi. Only the driver's logic side (RPWM, R_EN, GND, and
ideally VCC from a separate 5V source rather than the Pi's own 5V pin) connects to GPIO. Verify the driver's
RPWM/R_EN pins actually respond to 3.3V logic before wiring anything live (`P3-04`).

### Network

The Pi lives on the dorm Wi-Fi. If SSH or the web stream won't connect, **disable any VPN on the viewing
machine first** — a VPN client blocks access to other devices on the same LAN.

---

## Setup

Runs on a Raspberry Pi 5. `picamera2` and `pytest` come from apt, not pip:

```bash
sudo apt install -y python3-picamera2 python3-pytest
python3 -m venv --system-site-packages .venv    # so the venv can see picamera2
source .venv/bin/activate
pip install -r requirements.txt                  # flask, opencv-python-headless, numpy
```

`boundary_detection.py`, `tracking.py`, `turbidity_dct.py`, `volume_model.py`, and `synthetic_data.py` only need
`numpy`/`opencv` — they run, and can be tested, on any machine, camera or no camera.

---

## Code layout

| File | Role |
|---|---|
| `boundary_detection.py` | Finds the interface row from a row-wise pixel gradient — pure numpy/OpenCV, no camera I/O |
| `tracking.py` | `Tracker` — temporal filter for the detected row (median + jump-reject + a `draining` gate); unit-tested |
| `turbidity_dct.py` | `dct_sharpness()` (image sharpness from high-frequency DCT energy) + `TurbidityMonitor`, which tracks warming_up / turbid / clearing / clear across frames with a sliding-window slope |
| `volume_model.py` | `FrustumModel` (placeholder geometry) + `CalibrationTable` (interpolated from real height-volume measurements, JSON save/load, with the inverse `height_mm(volume)` used to compute the pump's stop point) |
| `synthetic_data.py` | Generates fake frames/draining sequences (a descending interface, an emulsion slowly clearing) to test the pipeline before real data exists |
| `demo.py` | Wires the four modules above together, runs them on a synthetic draining sequence, prints a per-frame table and an RMSE summary — doubles as a smoke test |
| `analyze_real_photo.py` | CLI that runs boundary detection + `dct_sharpness` on one real photo (`--roi`), writes an annotated image + `--profile-csv` for threshold tuning, and `--calib` to convert to volume |
| `realtime_stream.py` | Live MJPEG stream + status panel at `http://<pi-ip>:5000` (needs `picamera2` + a camera); in-browser recording to `records/`; a watchdog that recovers from a stalled camera |
| `run_stream.sh` | Supervisor that relaunches `realtime_stream.py` whenever it exits |
| `track_log.py` | Polls `/status` from another machine and writes a CSV |
| `tests/` | `pytest` suite — `test_tracking.py` (temporal-filter spec, clauses S1-S6) and `test_volume_model.py` |
| `records/` | CSV output from drain-test runs, one row per frame |
| `requirements.txt` | Dependencies and the picamera2 install note |

Every script runs stand-alone (`python3 demo.py`, `python3 turbidity_dct.py`, ...) for a synthetic-data
self-check, and `python3 -m pytest -q` runs the full unit suite. See `CLAUDE.md` for the full architecture and
the list of known gotchas, and `PROCESS.md` for how new work gets specified and tested before it's built.

---

## Usage

### Live stream on the Pi

```bash
./run_stream.sh                 # or: nohup ./run_stream.sh > run_stream.log 2>&1 &
# open http://<pi-ip>:5000
```

Camera/ROI/threshold tuning is done through environment variables, not by editing the file — see `CLAUDE.md`
"Running things".

### Calling the detector from code

```python
import cv2
from boundary_detection import detect_boundary

frame = cv2.imread("vial.jpg")                       # BGR
boundary_y, confidence = detect_boundary(frame, roi=(560, 80, 160, 560))
# boundary_y = vertical pixel coordinate in the full frame, confidence = |gradient| at that row
```

### Testing the pipeline and analyzing a real photo

```bash
python3 -m pytest -q                                  # unit tests
python3 demo.py                                       # full synthetic dry run, must print RESULT: PASS
python3 analyze_real_photo.py photo.jpg --roi 610 235 110 150 --profile-csv prof.csv
```

---

## Known risks

See `PRD.md` §5 for the full, reasoned risk list. In short:

1. **The classical detector's signal-to-clutter ratio** — it locks onto whichever edge in the ROI has the
   strongest gradient, not "the interface" specifically. This was confirmed to cause a real failure once (the
   detector locking onto a stopcock), fixed by removing the stopcock from the apparatus — but the underlying
   limitation (no concept of "interface," just "strongest edge") is still there as a general risk if the scene
   ever gets less constrained again.
2. **A single Pi 5 does both vision and control** — timing jitter during pump control is untested.
3. **The calibration table is tied to the exact vessel and camera position measured** — it breaks if either
   moves. The vessel is a funnel (frustum-shaped), not a cylinder, so this needs a multi-point calibration, not
   a linear fit.
4. **The pump is not wired yet** — see the safety section above.

---

## References

Fu, X. et al. "Chem-SDI: Segmentation, detection, and inference model for AI robotic chemists in
automated liquid-liquid extraction workflow." *Microchemical Journal* 227 (2026): 118844.
