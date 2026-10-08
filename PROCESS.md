# PROCESS.md

How this project is developed: Agile iteration, Spec-Driven Development (SDD), and Test-Driven Development (TDD).
This document exists because the advisor asked to see the process, not just the code — it is written to stand
on its own, without the chat history behind it.

---

## Why these three together

- **Agile** — work in short, demo-able increments instead of one long build, and let what a real test run shows
  change the next increment. `BACKLOG.md` is the backlog; each phase (P0-P7) in `PRD.md` is an increment with
  its own gate, and the status line at the top of each epic in `BACKLOG.md` reflects where it actually stands.
- **Spec-Driven Development** — before writing a fix or a new module, write down the behavior it must satisfy as
  numbered, falsifiable clauses. `PRD.md` §4 holds the project-level gates; a module gets its own clause list
  when its behavior is non-trivial (see the `Tracker` example below).
- **Test-Driven Development** — turn each spec clause into a test before writing the implementation, watch it
  fail for the right reason, then write the minimum code to pass it.

None of this is ceremony for its own sake: a solo project where the advisor isn't reviewing every step needs a
written contract that a reader — or a later version of the author — can check against, and tests that catch a
plausible-sounding fix that turns out to be wrong before it reaches real hardware.

---

## Toolchain

- `pytest`, installed via `apt install python3-pytest` (the Pi's system Python is externally managed — a bare
  `pip install` outside a venv is refused)
- `python3 -m pytest -q` runs the full suite; `python3 -m pytest tests/test_tracking.py` runs one file;
  `python3 -m pytest -k s4` runs one test
- Modules without pytest coverage yet (`turbidity_dct.py`, `synthetic_data.py`) have a `__main__` self-check
  instead; `demo.py` is the end-to-end smoke test
- Every hardware-free module (`boundary_detection`, `tracking`, `turbidity_dct`, `volume_model`,
  `synthetic_data`) can be tested on any machine — no Pi or camera required

---

## Worked example: fixing `Tracker`'s false re-seeds

This is the clearest example so far of the process catching a wrong idea before it shipped.

**1. The problem, from data.** The first live drain test (`records/rec_20260904_115249.csv`, 219s) showed the
right trend (the smoothed interface position moved 104 px, matching the water drained) but spiked as much as
151 px when the detector briefly locked onto the wrong row.

**2. Spec, written before touching the implementation.** `tests/test_tracking.py` encodes six clauses (S1-S6),
each named and each traceable to either the PRD gate or this failure:

| Clause | Requirement |
|---|---|
| S1 | A clean signal (steps <= `TRACK_MAX_STEP`) passes through with only median lag |
| S2 | A lone outlier is rejected |
| S3 | A frame with `conf` below threshold contributes nothing |
| S4 | While draining, the output must never re-seed onto a far position |
| S5 | While *not* draining, a sustained far reading is followed (re-acquisition) |
| S6 | While draining, a step that pulls the output backwards past a slack value is rejected |

**3. Red.** The first implementation hypothesis — only re-seed when the new position's confidence is close to
the confidence seen while locked — passed S1, S2, S3, and its own unit tests written for S4/S5. It looked right.

**4. The check that mattered: replay against the real recording, not just the unit tests.** Feeding the real
drain CSV through that implementation made the actual metric *worse*: max jump 151 -> 194 px. The hypothesis was
wrong — on this data, confidence during a false lock wasn't reliably lower than confidence during a correct
lock, so the gate let bad re-seeds through anyway.

**5. Green, from what the data actually showed.** During a controlled drain the interface only creeps —
it never makes a fast, legitimate jump. So every re-seed observed in the data was a false one. The fix:
`Tracker` never re-seeds while `draining=True`, full stop; re-seeding stays available only for the not-draining
case (re-aiming the camera in the live view). Re-running the same replay: max jump 151 -> **12 px**, jumps over
20px: 14 -> **0**.

**6. What's still open.** This is strong replay evidence, not a live confirmation — the next step in
`BACKLOG.md` (epic P1) is a fresh live drain with the fixed tracker, to close the gate formally.

The lesson this enforces going forward: a hypothesis that passes unit tests derived from the spec is not
evidence it is correct — only a replay against a real recording, or a fresh live run, is.

---

## A second example: a spec that turned out to be wrong, and had to be rewritten

Testing the row-gradient detector against a real separatory funnel (not the beaker used for the drain test
above) found it locking onto a metal stopcock instead of the actual water/oil interface. Direct measurement
confirmed why: the stopcock's edge scores |grad| ~13, while the real interface — clearly visible by eye — never
registered as a gradient peak at all. Re-reading Chem-SDI with this result in hand showed their row-gradient
step always runs after an ML segmentation mask removes exactly this kind of clutter; that step was deliberately
left out of this project's design. This is now documented as risk 1 in `PRD.md` §5, and the choice between
narrowing the ROI further versus building a color-independent motion-differencing detector is an open item in
`BACKLOG.md` epic P1, to be resolved the same way as the `Tracker` fix: spec it, test it, then validate against
real data before trusting it.

---

## How a new piece of work gets built

1. State the behavior as numbered clauses, grounded in either a PRD requirement/gate or an observed failure —
   not in what "feels right."
2. Write the test(s) for those clauses. Confirm they fail, and fail for the stated reason, not a typo.
3. Write the minimum implementation to pass them.
4. If the behavior touches anything measured from real hardware, replay the fix against the real data on file
   (`records/*.csv`) before trusting it — unit tests alone have already proved insufficient once (see above).
5. Update `BACKLOG.md`, and `PRD.md` §4/§6 if a gate's status changed.
6. Commit with a message that states the reasoning, not just what changed — `git log` is part of the evidence
   trail for this project.

---

## Boundary on AI-assisted development

Code and documentation in this repository were developed with AI assistance (Claude). The division of labor:

- **AI-assisted:** boilerplate (Flask routes, CSV I/O, test scaffolding), implementing a technique already
  chosen by the author (e.g. the DCT/gradient math taken from Chem-SDI), debugging environment-specific issues
  (the exposure clamp, the R/B channel swap, the camera cable), documentation formatting and translation.
- **Author-driven:** the research question and its motivation; every design decision and its justification
  (beaker vs. funnel, no fluorescent tracer, motion differencing vs. a conductivity probe); interpreting results
  (e.g. what the stopcock-lock finding means for the detection approach); running physical experiments and
  collecting real data by hand; understanding the code well enough to defend it in review; the report's
  discussion and conclusions.

A practical check used throughout: if a question about a specific design choice (for example, why a constant is
set to a particular value, or what a piece of the detection pipeline computes) can't be answered without
reopening the chat history, that choice has not actually been understood yet, and needs to be before it is
relied on.
