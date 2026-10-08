# ROADMAP.md

A table-first, scannable view of the plan: Roadmap -> Milestones -> Sprints -> Stories -> Sprint Backlog. This
document exists to be skimmed quickly; the reasoning behind each item lives in `PRD.md` (requirements + gates)
and `BACKLOG.md` (per-item discussion). `CHANGELOG.md` has the dated, verified history behind the "Done" rows.

---

## Roadmap

One row per phase (epic in `BACKLOG.md`). This is the top-level sequence the whole project follows.

| Phase | Goal | Gate (PRD §4) | Status |
|---|---|---|---|
| P0 | System & algorithm setup | `demo.py` -> `RESULT: PASS` | **Done** |
| P1 | Detect & track the interface on real liquids | `boundary_y_smooth` monotonic during a drain, no jump > 30 px, interface found in >= 95% of frames | **In progress** |
| P2 | Calibrate height -> volume | Predicted-volume RMSE < 2 mL | Not started |
| P3 | Wire the pump safely | Wiring reviewed, starts/stops on command, flow rate measured | Not started |
| P4 | Closed loop (detect -> decide -> pump -> stop) | Clean separation, pump stops within target | Not started |
| P5 | Repeatability study | RMSE < 2 mL across 10 runs, no run off by > 5 mL | Not started |
| P6 | Switch to real water-cyclohexane | RMSE comparable to water/oil (within 50%) | Not started |
| P7 | Write the report | — | Not started |

---

## Milestones

Phases grouped into four checkpoints — each one answers a specific question the thesis needs answered.

| Milestone | Phases | Answers | Done when | Status |
|---|---|---|---|---|
| **M1 — Detection proven** | P0, P1 | Can a classical (non-ML) pipeline find and track the interface reliably? | P1 gate closed (`P1-08`) | In progress — P0 done, P1 open items `P1-07`-`P1-09` |
| **M2 — Volume + hardware ready** | P2, P3 | Can height convert to volume, and can the pump be driven safely? | P2 and P3 gates both closed | Not started |
| **M3 — Closed loop validated** | P4, P5 | Does the whole system work unattended, repeatably? | P5 gate closed (10-run RMSE) | Not started |
| **M4 — Cyclohexane + report** | P6, P7 | Does it hold up on the real target pair, and is it written up? | P6 gate closed, report submitted | Not started |

---

## Sprints

Reconstructed from `git log`, not planned in advance on a fixed calendar — this is a solo project with irregular
availability (a month-long gap is visible below), so a sprint here means "one dated unit of work," not a fixed
weekly cadence.

| Sprint | Dates | Scope (story IDs) | Outcome |
|---|---|---|---|
| Sprint 1 | 2026-08-29 | `P0-01`, `P0-02`, `P0-03`, `P0-07` | Initial pipeline committed, pushed to GitHub |
| Sprint 2 | 2026-09-04 | `P0-04`, `P0-05`, `P0-06`, `P1-01`-`P1-06` | Recording + watchdog shipped; `Tracker` extracted and fixed (replay 151 -> 12 px); real-funnel test found the stopcock-lock risk |
| *(paused)* | 2026-09-05 - 2026-10-07 | — | Away from the project |
| Sprint 3 | 2026-10-08 | docs translation, `BACKLOG.md`/`PROCESS.md`/`CHANGELOG.md`, architecture + logic diagrams | Full English documentation trail established |
| **Sprint 4 (current)** | 2026-10-08 - | `P1-07`, `P1-08`, `P1-09` | Deciding ROI-narrowing vs. motion differencing; confirming the P1 gate live |

---

## Stories

Every backlog item, one row each. Full reasoning for any row lives in `BACKLOG.md` under the matching epic.

| ID | Phase | Status | Story |
|---|---|---|---|
| P0-01 | P0 | Done | Camera exposure/WB tuned on the Pi; fixed a BGR/RGB swap + the `FrameDurationLimits` clamp |
| P0-02 | P0 | Done | Core modules pass against synthetic data (`demo.py` -> `RESULT: PASS`) |
| P0-03 | P0 | Done | `realtime_stream.py` — live view + status panel + `/status` |
| P0-04 | P0 | Done | In-browser recording + a CSV browse page |
| P0-05 | P0 | Done | `boundary_y_smooth` — median-of-9 + jump rejection |
| P0-06 | P0 | Done | Watchdog + `run_stream.sh` supervisor |
| P0-07 | P0 | Done | Pushed to GitHub (`Cherrpxp/extractlab`) |
| P1-01 | P1 | Done | Black background + a tight ROI locks the real interface (`conf` ~12 vs. threshold 3) |
| P1-02 | P1 | Done | First live drain test, 219s, recorded + analyzed |
| P1-03 | P1 | Done | Extracted `Tracker` into `tracking.py`, spec S1-S6, unit-tested |
| P1-04 | P1 | Done (reverted) | First fix hypothesis invalidated by replay (max jump 151 -> 194 px) |
| P1-05 | P1 | Done | Correct fix: never re-seed while draining (replay 151 -> 12 px, jumps>20px 14 -> 0) |
| P1-06 | P1 | Done | Found the detector locks onto a stopcock on a real funnel; root-caused against Chem-SDI |
| P1-07 | P1 | **Open** | Decide: narrow the ROI further vs. build a motion-differencing detector |
| P1-08 | P1 | **Open** | Re-run a live drain to confirm the P1 gate formally |
| P1-09 | P1 | Open | If motion differencing: spec -> test (red) -> implement |
| P2-01 | P2 | Done | `CalibrationTable` written + unit-tested |
| P2-02 | P2 | Open | Measure the beaker's diameter, mm/px scale, zero-volume row |
| P2-03 | P2 | Open | Fill to 2-3 known volumes, fit a line |
| P2-04 | P2 | Open | Verify against a held-out volume (target RMSE < 2 mL) |
| P3-01 | P3 | Open | Confirm `vcgencmd get_throttled` reads `0x0` before wiring |
| P3-02 | P3 | Open | Source a 12V supply + a 5V-logic relay module |
| P3-03 | P3 | Open | Wire 12V -> relay -> pump (never through Pi GPIO/5V/GND) |
| P3-04 | P3 | Open | Test relay switching from GPIO with no liquid |
| P3-05 | P3 | Open | Measure the pump's flow rate (mL/s) |
| P3-06 | P3 | Open | Write `pump.py` (`start`/`stop`/`flow_rate`/`run_volume`/`purge`) |
| P4-01 | P4 | Open | Combine detection -> volume -> pump start/stop |
| P4-02 | P4 | Open | Gate pump start on turbidity |
| P4-03 | P4 | Open | Safety timeout + emergency-stop condition |
| P4-04 | P4 | Open | Check vision-loop timing holds with the pump running |
| P4-05 | P4 | Open | Dry run with water + oil |
| P5-01 | P5 | Open | Run the full loop 10x |
| P5-02 | P5 | Open | Record actual vs. predicted volume |
| P5-03 | P5 | Open | Report RMSE, mean error, standard deviation |
| P6-01 | P6 | Open | Re-run a shortened P1 with cyclohexane |
| P6-02 | P6 | Open | Re-run P2 if needed |
| P6-03 | P6 | Open | Repeat the 10-run study with cyclohexane |
| P7-01 | P7 | Open | Methods + results write-up |
| P7-02 | P7 | Open | Comparison against Chem-SDI |
| P7-03 | P7 | Open | Limitations + future work |
| P7-04 | P7 | Open | Disclose AI-assisted development |

---

## Sprint Backlog (current — Sprint 4)

What's actually being worked on right now, nothing else.

| ID | Story | Status |
|---|---|---|
| P1-07 | Decide: narrow the ROI further vs. build a motion-differencing detector | **Next — blocking everything else in P1** |
| P1-08 | Re-run a live drain to confirm the P1 gate formally | Blocked on P1-07 |
| P1-09 | If motion differencing is chosen: spec -> test (red) -> implement | Blocked on P1-07 |
