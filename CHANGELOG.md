# Changelog

Notable changes to extractlab, grouped by backlog phase — see `docs/BACKLOG.md` for the full item list and
`docs/PRD.md` §4 for the gate each phase must close. Dates are commit dates (`git log`).

An entry marked **Verified:** closes or partially closes a gate, with the actual evidence behind it — not just
"tests pass." See `docs/PROCESS.md` for why a unit-test pass alone isn't trusted here before replaying against
real recorded data.

## [Unreleased]

### Phase P1 — Detect and track the interface on real liquids (in progress)

- **2026-10-08** — Translated all documentation to English; added `docs/BACKLOG.md` and `docs/PROCESS.md`; moved
  `PRD.md` / `BACKLOG.md` / `PROCESS.md` into `docs/` (`c991272`, `abb3121`)
  **Verified:** `python3 -m pytest -q` — 11 passed; `python3 demo.py` — `RESULT: PASS` (reorg broke nothing)
- **2026-09-04** — **P1-06** Tested the detector against a real separatory funnel (not the beaker used for the
  drain test) and found it locking onto a metal stopcock instead of the water/oil interface
  **Verified:** direct gradient measurement — stopcock `|grad|` ≈ 13, the real interface never registered as a
  gradient peak at all. Root-caused against Chem-SDI (`docs/PROCESS.md`, second worked example): their
  row-gradient step always runs after an ML segmentation mask, which this project deliberately omits.
- **2026-09-04** — **P1-04** First fix hypothesis for `Tracker` (re-seed gated on confidence) written and
  unit-tested, then invalidated by replaying it against the real drain recording — reverted, not merged
  **Verified (failed):** replay of `records/rec_20260904_115249.csv` — max jump got *worse*, 151 → 194 px
- **2026-09-04** — **P1-03 / P1-05** Extracted `Tracker` into `tracking.py` with spec clauses S1-S6
  (`tests/test_tracking.py`, `1fd938c` RED); fixed it to never re-seed while draining (`7adef09` GREEN)
  **Verified:** replay of the same recording — max jump 151 → **12 px**, jumps over 20 px: 14 → **0**
  (`python3 -m pytest tests/test_tracking.py` — 6 passed)
- **2026-09-04** — **P1-02** First live drain test, 219s, recorded and analyzed — correct trend (interface moved
  104 px, matching the water drained), but spiked up to 151 px on false locks (see P1-04/P1-05 above)
- **2026-09-04** — **P1-01** Black background + a tight ROI → the detector locks the real water/oil interface
  **Verified:** `conf` ≈ 12 against a threshold of 3

Still open in this phase: choosing between narrowing the ROI further vs. a motion-differencing detector
(P1-07), and a fresh live drain to confirm the gate formally (P1-08) — see `docs/BACKLOG.md`.

### Phase P0 — System & algorithm setup (done)

- **2026-09-04** — **P0-06** Watchdog + `run_stream.sh` supervisor (`c9d2a38`) — self-heals a stalled camera
- **2026-09-04** — **P0-04 / P0-05** In-browser drain recording, CSV browse page, `boundary_y_smooth`
  (median-of-9 + jump rejection) (`a1fd81c`, `28aea1c`)
- **2026-08-29** — **P0-01 / P0-02 / P0-03 / P0-07** Initial commit: classical-CV LLE vision pipeline
  (`a727b30`) — `boundary_detection`, `turbidity_dct`, `volume_model`, `synthetic_data`, `demo.py`
  (`RESULT: PASS`), `realtime_stream.py` live view, git init + push to GitHub (`Cherrpxp/extractlab`)
  **Verified:** `python3 demo.py` — `RESULT: PASS` against synthetic data
