# BACKLOG.md

Agile-style backlog for extractlab, organized by phase (epic). Each phase has a goal, a list of backlog items,
and the PRD gate that closes it. Status: `[x]` done, `[~]` in progress, `[ ]` not started. Each item has a short
ID (`P<phase>-NN`) used to cross-reference it from `CHANGELOG.md` and from commit messages (`type(P1-05): ...`).

See `PRD.md` for full requirements and reasoning, `PROCESS.md` for the development workflow, `CHANGELOG.md` for
the dated, verified history, `developments/` for the same items rolled up into roadmap/milestones/sprints/
stories/sprint-backlog tables (numbered `0X_*.md`, with Mermaid diagrams), and `CLAUDE.md` for architecture and
operational notes.

Numbering note: P6 (switching to cyclohexane) was removed entirely once the advisor confirmed water-oil is the
final target pair, not a rehearsal for a harder solvent — the gap from P5 to P7 is intentional, not a missing
file.

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
- [x] **P1-06** Tested against the separatory funnel while it still had its **stopcock attached** and found the
      detector locks onto the metal stopcock instead of the interface; confirmed by direct gradient measurement;
      traced to the detector having no concept of "interface," only "strongest edge in the ROI." Chem-SDI avoids
      this by running an ML segmentation mask before its row-gradient step, which this project deliberately does
      not have.
- [x] **P1-07** Resolved by removing the stopcock from the funnel, not by new code: the pump now draws from a
      tube entering through the top instead of through the stopcock, so the object that caused the mis-lock is
      no longer in frame. There is no recorded instance of the detector mis-locking on the reconfigured rig
      (`conf` ~12 vs. threshold 3, clean). Building a motion-differencing detector now would spec new work
      against a failure that's been fixed at the hardware level — against `PROCESS.md`'s own rule to spec from a
      real, current failure.
- [ ] **P1-08** **Re-run a live drain on the reconfigured funnel with the current tracker and confirm the P1
      gate formally** (replay evidence only so far — see PRD §4) — the one remaining item in this epic

Gate: `boundary_y_smooth` moves monotonically during a drain, no jump > 30 px between consecutive frames, the
interface is found in >= 95% of frames. See PRD §4.

---

## Epic P2 — Calibrate height -> volume (NOT STARTED)

Goal: convert `boundary_y` into a volume estimate. The vessel is a funnel, not a cylinder, so this needs a
multi-point calibration table rather than a linear fit.

- [x] **P2-01** `volume_model.py` — `CalibrationTable` (interpolate / JSON / inverse) written and unit-tested
- [x] **P2-02** Superseded by a better approach than the planned mm/px-ruler-photo method: skip the mm/px/
      zero-row conversion entirely and calibrate `boundary_y` (camera pixel row) -> `volume_ml` directly.
      First attempt at the original `EXPOSURE_US=25000` default failed -- a false structural edge at the
      bulb/cone transition (detector locks onto it instead of the real surface around 30-37 mL) and poor
      repeatability elsewhere (15 mL spread 43px / ~10-12 mL equivalent across 5 cylinder-measured repeats).
      **Root cause: insufficient exposure, not geometry.** Raising `EXPOSURE_US` to 45000 (ROI brightness
      ~100-120 -> ~136-157/255) fixed it -- every one of 10/15/20/25/30/35/40 mL re-checked within 1-5px of
      a single clean reading, and 35 mL specifically got 4 fresh repeats within 2px of each other. Saved as
      `records/pixel_calibration_table.json`; full investigation log in `records/pixel_calibration.json`
- [x] **P2-03** Filled the funnel to 4 known water volumes (10/20/30/40 mL, graduated cylinder) from empty,
      read the water-surface height in cm at each with a ruler, built `CalibrationTable` from
      (height_mm, volume_ml) pairs — saved to `records/calibration_table.json`. Not pixel-row-based (see
      P2-02); a first, looser attempt via draining + two divergent fluids (water/oil) is kept in
      `records/calibration_points_v2.json` for reference but was not used (it didn't reproduce cleanly — see
      the discussion recorded there)
- [x] **P2-04** Verified against held-out volumes not used for fitting, on both tables:
      ruler-based (15, 35 mL) — RMSE = 0.589 mL; camera-direct, `EXPOSURE_US=45000` (15, 25, 35 mL) —
      RMSE = 0.436 mL. Both well under the 2 mL target

Gate: predicted-volume RMSE < 2 mL against a graduated cylinder. **Met by both tables** — ruler-based
(0.589 mL, `records/calibration_table.json`) and camera-direct (0.436 mL, `records/pixel_calibration_table.json`,
the one the live system should actually read from since it needs no manual ruler step).

---

## Epic P3 — Wire the pump safely (NOT STARTED)

Goal: drive the 24V pump from an isolated supply through the HW-039 (BTS7960) motor driver, with the Pi's GPIO
only switching logic.

- [ ] **P3-01** Confirm `vcgencmd get_throttled` reads `0x0` before wiring anything (board health check)
- [x] **P3-02** Source a 24V 2A supply (S-50-24) + the HW-039 motor driver — hardware in hand, voltages confirmed
      matching
- [ ] **P3-03** Wire 24V -> HW-039 (B+/B-) -> pump (M+/M-); GPIO -> RPWM/R_EN; share ground — **never through Pi
      GPIO/5V/GND directly**; prefer a separate 5V source for the driver's logic VCC over the Pi's own 5V pin
- [ ] **P3-04** Confirm the HW-039's RPWM/R_EN pins respond to 3.3V GPIO logic, then test motor driver switching
      with no liquid in the loop
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

## Epic P7 — Write the report (NOT STARTED)

- [ ] **P7-01** Methods, calibration results, RMSE results
- [ ] **P7-02** Comparison against Chem-SDI — what was cut, what was kept, how the results differ
- [ ] **P7-03** Limitations (risks 1-4 in PRD §5, including the camera-cable fragility) and future work
- [ ] **P7-04** Disclose AI-assisted development (this backlog, the PRD, and the SDD/TDD process in
      `PROCESS.md`), per department policy
