# BACKLOG.md

Agile-style backlog for extractlab, organized by phase (epic). Each phase has a goal, a list of backlog items,
and the PRD gate that closes it. Status: `[x]` done, `[~]` in progress, `[ ]` not started. Each item has a short
ID (`P<phase>-NN`) used to cross-reference it from `CHANGELOG.md` and from commit messages (`type(P1-05): ...`).

See `PRD.md` for full requirements and reasoning, `PROCESS.md` for the development workflow, `CHANGELOG.md` for
the dated, verified history, and `CLAUDE.md` for architecture and operational notes.

---

## Epic P0 — System & algorithm setup (DONE)

Goal: working hardware, a stable camera, and the core algorithms + tooling in place.

- [x] **P0-01** SSH into the Pi 5; manual exposure/WB for the camera (fixed a BGR/RGB channel-swap bug, and the
      `FrameDurationLimits` clamp that silently capped exposure)
- [x] **P0-02** `boundary_detection`, `turbidity_dct`, `volume_model`, `synthetic_data`, `demo` — pass against
      synthetic data (`demo.py` -> `RESULT: PASS`)
- [x] **P0-03** `realtime_stream.py` — live view + status panel + `/status`
- [x] **P0-04** In-browser recording (start/stop -> `records/*.csv`) + a page to browse/download CSVs
- [x] **P0-05** `boundary_y_smooth` — median-of-9 + jump rejection
- [x] **P0-06** Watchdog + `run_stream.sh` supervisor — self-heals a stalled camera
- [x] **P0-07** `git init`, pushed to GitHub (`Cherrpxp/extractlab`)

---

## Epic P1 — Detect and track the interface on real liquids (IN PROGRESS)

Goal: prove the interface can be detected and tracked reliably enough to trigger the pump, without a fluorescent
tracer or any machine-learning model.

- [x] **P1-01** Black background + a tight ROI -> the detector locks the real water/oil interface (`conf` ~12
      vs. threshold 3)
- [x] **P1-02** First live drain test, 219s, recorded + analyzed
- [x] **P1-03** Extract `Tracker` into `tracking.py` (hardware-free, unit-tested) — spec clauses S1-S6
- [x] **P1-04** First fix hypothesis (gate re-seeding on confidence) written, tested, **then invalidated by
      replaying it against real drain data** (max jump got worse: 151 -> 194 px) — reverted
- [x] **P1-05** Correct fix found from what the real data showed: never re-seed while draining -> replay of the
      same data: max jump 151 -> 12 px, jumps over 20px: 14 -> 0
- [x] **P1-06** Tested against a real separatory funnel (not the beaker) and found the detector locks onto a
      stopcock instead of the interface — confirmed by direct gradient measurement; traced to the detector
      having no concept of "interface," only "strongest edge in the ROI." Chem-SDI avoids this by running an ML
      segmentation mask before its row-gradient step, which this project deliberately does not have.
- [ ] **P1-07** Decide between: (A) narrow the ROI further to exclude clutter, then re-run a live drain to close
      this epic with the existing detector, or (B) build a motion-differencing detector (the interface is the
      only thing moving during a drain, regardless of color) as a color-independent alternative that would also
      work for cyclohexane
- [ ] **P1-08** **Re-run a live drain with the current tracker and confirm the P1 gate formally** (replay
      evidence only so far — see PRD §4)
- [ ] **P1-09** If (B): spec -> test (red) -> implement motion differencing, validated first against
      `synthetic_data.py`

Gate: `boundary_y_smooth` moves monotonically during a drain, no jump > 30 px between consecutive frames, the
interface is found in >= 95% of frames. See PRD §4.

---

## Epic P2 — Calibrate height -> volume (NOT STARTED)

Goal: convert `boundary_y` into a volume estimate, using the fact that a cylindrical beaker makes
height <-> volume linear.

- [x] **P2-01** `volume_model.py` — `CalibrationTable` (interpolate / JSON / inverse) written and unit-tested
- [ ] **P2-02** Measure the beaker's inner diameter + the mm/px scale (photograph a ruler) + the zero-volume
      reference row
- [ ] **P2-03** Fill the beaker to 2-3 known volumes, record the pixel row at each, fit a line
- [ ] **P2-04** Verify against a volume not used for fitting — target RMSE < 2 mL (see PRD §4 for why)

Gate: predicted-volume RMSE < 2 mL against a graduated cylinder.

---

## Epic P3 — Wire the pump safely (NOT STARTED)

Goal: drive the 12V pump from an isolated supply through a relay, with the Pi's GPIO only switching logic.

- [ ] **P3-01** Confirm `vcgencmd get_throttled` reads `0x0` before wiring anything (board health check)
- [ ] **P3-02** Source a 12V >=1A supply + a 5V-logic relay module
- [ ] **P3-03** Wire 12V -> relay -> pump; GPIO -> relay IN; share ground — **never through Pi GPIO/5V/GND
      directly**
- [ ] **P3-04** Test relay switching from GPIO with no liquid in the loop
- [ ] **P3-05** Measure the pump's flow rate (mL/s) — needed for a time-based volume fallback and for safety
      timeouts
- [ ] **P3-06** Write `pump.py`: `start()` / `stop()` / `flow_rate` / `run_volume(ml, stop_check)` / `purge()` —
      see `PROCESS.md` for the sibling-project API this is adapted from

Gate: wiring reviewed for safety, pump starts/stops on command, flow rate measured and recorded.

---

## Epic P4 — Closed loop (NOT STARTED)

Goal: detection -> decision -> pump -> stop, running unattended for one drain cycle.

- [ ] **P4-01** Combine the pieces: interface (filtered) -> volume -> start the pump at the target level, stop
      it at the target volume
- [ ] **P4-02** Gate pump starts on turbidity (`turbidity_dct`) — don't act while the phases are still mixed
- [ ] **P4-03** Safety timeout + an emergency-stop condition; consider a conductivity probe as a secondary
      trigger
- [ ] **P4-04** Check vision-loop timing holds up while the pump runs (risk 2 in PRD §5)
- [ ] **P4-05** Dry run with water + oil

Gate: separation is clean (no upper-phase carryover) and the pump stops within target.

---

## Epic P5 — Repeatability study (NOT STARTED)

Goal: quantify accuracy across repeated runs.

- [ ] **P5-01** Run the full loop 10x with water + oil, same starting volume each time
- [ ] **P5-02** Record actual separated volume (weighed/measured) vs. predicted
- [ ] **P5-03** Report RMSE, mean error, standard deviation

Gate: RMSE < 2 mL, no single run off by more than 5 mL.

---

## Epic P6 — Switch to real water-cyclohexane (NOT STARTED)

Goal: validate against the actual target pair.

- [ ] **P6-01** Re-run a shortened P1 — brightness-gradient likely insufficient (near-identical refractive
      index); fall back to whatever P1 decided (motion differencing / conductivity probe)
- [ ] **P6-02** Re-run P2 if needed (different meniscus shape/density)
- [ ] **P6-03** Repeat P5's 10-run study with cyclohexane

Gate: RMSE comparable to the water/oil result (within 50%).

---

## Epic P7 — Write the report (NOT STARTED)

- [ ] **P7-01** Methods, calibration results, RMSE results (water/oil vs. cyclohexane)
- [ ] **P7-02** Comparison against Chem-SDI — what was cut, what was kept, how the results differ
- [ ] **P7-03** Limitations (risks 1-4 in PRD §5, including the camera-cable fragility) and future work
- [ ] **P7-04** Disclose AI-assisted development (this backlog, the PRD, and the SDD/TDD process in
      `PROCESS.md`), per department policy
