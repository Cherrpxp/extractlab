# BACKLOG.md

Agile-style backlog for extractlab, organized by phase (epic). Each phase has a goal, a list of backlog items,
and the PRD gate that closes it. Status: `[x]` done, `[~]` in progress, `[ ]` not started.

See `PRD.md` for full requirements and reasoning, `PROCESS.md` for the development workflow, and `CLAUDE.md` for
architecture and operational notes.

---

## Epic P0 — System & algorithm setup (DONE)

Goal: working hardware, a stable camera, and the core algorithms + tooling in place.

- [x] SSH into the Pi 5; manual exposure/WB for the camera (fixed a BGR/RGB channel-swap bug, and the
      `FrameDurationLimits` clamp that silently capped exposure)
- [x] `boundary_detection`, `turbidity_dct`, `volume_model`, `synthetic_data`, `demo` — pass against synthetic
      data (`demo.py` -> `RESULT: PASS`)
- [x] `realtime_stream.py` — live view + status panel + `/status`
- [x] In-browser recording (start/stop -> `records/*.csv`) + a page to browse/download CSVs
- [x] `boundary_y_smooth` — median-of-9 + jump rejection
- [x] Watchdog + `run_stream.sh` supervisor — self-heals a stalled camera
- [x] `git init`, pushed to GitHub (`Cherrpxp/extractlab`)

---

## Epic P1 — Detect and track the interface on real liquids (IN PROGRESS)

Goal: prove the interface can be detected and tracked reliably enough to trigger the pump, without a fluorescent
tracer or any machine-learning model.

- [x] Black background + a tight ROI -> the detector locks the real water/oil interface (`conf` ~12 vs.
      threshold 3)
- [x] First live drain test, 219s, recorded + analyzed
- [x] Extract `Tracker` into `tracking.py` (hardware-free, unit-tested) — spec clauses S1-S6
- [x] First fix hypothesis (gate re-seeding on confidence) written, tested, **then invalidated by replaying it
      against real drain data** (max jump got worse: 151 -> 194 px) — reverted
- [x] Correct fix found from what the real data showed: never re-seed while draining -> replay of the same data:
      max jump 151 -> 12 px, jumps over 20px: 14 -> 0
- [x] Tested against a real separatory funnel (not the beaker) and found the detector locks onto a stopcock
      instead of the interface — confirmed by direct gradient measurement; traced to the detector having no
      concept of "interface," only "strongest edge in the ROI." Chem-SDI avoids this by running an ML
      segmentation mask before its row-gradient step, which this project deliberately does not have.
- [ ] Decide between: (A) narrow the ROI further to exclude clutter, then re-run a live drain to close this
      epic with the existing detector, or (B) build a motion-differencing detector (the interface is the only
      thing moving during a drain, regardless of color) as a color-independent alternative that would also work
      for cyclohexane
- [ ] **Re-run a live drain with the current tracker and confirm the P1 gate formally** (replay evidence only so
      far — see PRD §4)
- [ ] If (B): spec -> test (red) -> implement motion differencing, validated first against `synthetic_data.py`

Gate: `boundary_y_smooth` moves monotonically during a drain, no jump > 30 px between consecutive frames, the
interface is found in >= 95% of frames. See PRD §4.

---

## Epic P2 — Calibrate height -> volume (NOT STARTED)

Goal: convert `boundary_y` into a volume estimate, using the fact that a cylindrical beaker makes
height <-> volume linear.

- [x] `volume_model.py` — `CalibrationTable` (interpolate / JSON / inverse) written and unit-tested
- [ ] Measure the beaker's inner diameter + the mm/px scale (photograph a ruler) + the zero-volume reference row
- [ ] Fill the beaker to 2-3 known volumes, record the pixel row at each, fit a line
- [ ] Verify against a volume not used for fitting — target RMSE < 2 mL (see PRD §4 for why)

Gate: predicted-volume RMSE < 2 mL against a graduated cylinder.

---

## Epic P3 — Wire the pump safely (NOT STARTED)

Goal: drive the 12V pump from an isolated supply through a relay, with the Pi's GPIO only switching logic.

- [ ] Confirm `vcgencmd get_throttled` reads `0x0` before wiring anything (board health check)
- [ ] Source a 12V >=1A supply + a 5V-logic relay module
- [ ] Wire 12V -> relay -> pump; GPIO -> relay IN; share ground — **never through Pi GPIO/5V/GND directly**
- [ ] Test relay switching from GPIO with no liquid in the loop
- [ ] Measure the pump's flow rate (mL/s) — needed for a time-based volume fallback and for safety timeouts
- [ ] Write `pump.py`: `start()` / `stop()` / `flow_rate` / `run_volume(ml, stop_check)` / `purge()` — see
      `PROCESS.md` for the sibling-project API this is adapted from

Gate: wiring reviewed for safety, pump starts/stops on command, flow rate measured and recorded.

---

## Epic P4 — Closed loop (NOT STARTED)

Goal: detection -> decision -> pump -> stop, running unattended for one drain cycle.

- [ ] Combine the pieces: interface (filtered) -> volume -> start the pump at the target level, stop it at the
      target volume
- [ ] Gate pump starts on turbidity (`turbidity_dct`) — don't act while the phases are still mixed
- [ ] Safety timeout + an emergency-stop condition; consider a conductivity probe as a secondary trigger
- [ ] Check vision-loop timing holds up while the pump runs (risk 2 in PRD §5)
- [ ] Dry run with water + oil

Gate: separation is clean (no upper-phase carryover) and the pump stops within target.

---

## Epic P5 — Repeatability study (NOT STARTED)

Goal: quantify accuracy across repeated runs.

- [ ] Run the full loop 10x with water + oil, same starting volume each time
- [ ] Record actual separated volume (weighed/measured) vs. predicted
- [ ] Report RMSE, mean error, standard deviation

Gate: RMSE < 2 mL, no single run off by more than 5 mL.

---

## Epic P6 — Switch to real water-cyclohexane (NOT STARTED)

Goal: validate against the actual target pair.

- [ ] Re-run a shortened P1 — brightness-gradient likely insufficient (near-identical refractive index); fall
      back to whatever P1 decided (motion differencing / conductivity probe)
- [ ] Re-run P2 if needed (different meniscus shape/density)
- [ ] Repeat P5's 10-run study with cyclohexane

Gate: RMSE comparable to the water/oil result (within 50%).

---

## Epic P7 — Write the report (NOT STARTED)

- [ ] Methods, calibration results, RMSE results (water/oil vs. cyclohexane)
- [ ] Comparison against Chem-SDI — what was cut, what was kept, how the results differ
- [ ] Limitations (risks 1-4 in PRD §5, including the camera-cable fragility) and future work
- [ ] Disclose AI-assisted development (this backlog, the PRD, and the SDD/TDD process in `PROCESS.md`), per
      department policy
