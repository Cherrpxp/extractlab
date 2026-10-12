# Project Requirements Document (PRD)
### Vision-Guided Automated Liquid–Liquid Separation for Water–Oil

*Last updated 13 October 2026 (hardware and scope synced with the current setup) ·
companion docs: [`README.md`](../README.md) (code layout), [`CLAUDE.md`](../CLAUDE.md) (context and hardware),
[`BACKLOG.md`](BACKLOG.md) (Agile backlog), [`PROCESS.md`](PROCESS.md) (Agile/SDD/TDD workflow), the research-plan
flow diagram (a separate artifact)*

---

## 1. Background and the Gap in Prior Work

Liquid–liquid extraction (LLE) requires separating two phases after they have been shaken and left to settle.
Done by hand, the experimenter watches the position of the interface between the two layers and opens and
closes a valve themselves; the timing of that valve depends on eyesight and reaction time, so the volume
separated varies from run to run. The hardest version of this problem is when both phases are clear and
colorless (e.g. water–cyclohexane), where the only visible cue is a faint meniscus line and the way light
refracts at the interface. **This project targets a more tractable pair — water and vegetable oil** — chosen
because it is a non-toxic organic solvent that still poses the same underlying detection problem; extending to
a colorless-colorless pair like water–cyclohexane is future work, outside this project's scope.

Fu et al.'s work (Chem-SDI, *Microchemical Journal* 227, 2026) solves the detection problem — including the
harder colorless-colorless case — with a segmentation model (YOLOv8n-seg), a two-board control stack (Orange Pi
+ STM32), and a stepper motor driving the stopcock. That accuracy is paid for with a labeled dataset, a
model-training step, and purpose-built hardware.

**This project's question:** are the two *classical* techniques in that same paper — DCT-based turbidity
monitoring and row-wise brightness-gradient interface detection — enough on their own to drive an automated
separation system on a **single Raspberry Pi 5**, using a cheap pump through a motor driver instead of a
stepper-driven stopcock? If so, the method travels to any lab bench without a GPU and without the effort of
labeling data.

---

## 2. What the System Must Do

### 2.1 Seeing and Tracking the Interface

The heart of the system is reading the interface position from the image continuously and stably enough to
trigger the pump. The camera only looks inside a configured ROI around the liquid column, computes the average
row-wise brightness gradient, and picks the row with the strongest change in brightness as the interface, along
with a confidence value `conf` (the size of the gradient at that row). Because the per-frame reading can jump a
lot when it briefly locks onto a different edge, the system must also publish a time-filtered value
(`boundary_y_smooth`) alongside the raw one, and must assess the turbidity around the interface (a DCT-based
sharpness index) to tell whether the layers have settled.

### 2.2 Converting Position to Volume

The interface position (a pixel row) must convert to a real height, then to the volume of the layer below it.
The vessel is a **pear-shaped separatory funnel**, not a cylinder, so the height–volume relationship is not
linear. The system needs a calibration table (interpolated from real measured points, not a single formula)
that can be saved and loaded, with an inverse lookup (the height at a target volume) to compute where the pump
should stop.

### 2.3 Pump Control and Safety *(not started)*

The Pi's GPIO only drives the logic pins (RPWM, R_EN) of a motor driver module (HW-039/BTS7960), switching a
pump powered by a separate 24V supply; pump power must never pass through any Pi pin. The system starts the pump once the (filtered) interface reaches
the starting level and the layers have settled, and stops it once the interface reaches the target level. There
must be emergency-stop conditions: the interface is lost, the camera stalls, or a time limit is exceeded.

### 2.4 Interface and Data Logging

The experimenter watches the live image with the detected line drawn on it, reads the status (position, `conf`,
ROI brightness, frame rate), and can start/stop a recording from a web page on another machine on the same LAN.
Each recording writes one CSV row per frame to `records/`, browsable and downloadable from the same page. When
the camera stalls (a CSI timeout), the system must recover on its own without SSH-ing in to fix it.

### Functional Requirements Summary

| ID | Requirement | Status |
|---|---|---|
| FR-1 | Read `boundary_y` and `conf` from every frame inside the ROI | Done |
| FR-2 | Filter over time into `boundary_y_smooth` (median + reject abnormal jumps) | Done — the draining re-seed bug is fixed (see §4); still needs a fresh live run to confirm the gate |
| FR-3 | Assess turbidity via DCT and report settled vs. still-turbid | Done |
| FR-4 | ROI, exposure, white balance adjustable via env var, no code changes | Done |
| FR-5 | Convert `boundary_y` -> height -> volume (funnel geometry, multi-point calibration) with an inverse lookup | Model done, waiting on real calibration measurements |
| FR-6 | GPIO -> motor driver (HW-039) -> a separate 24V pump; start/stop based on interface position and turbidity | Not started |
| FR-7 | Emergency-stop conditions (interface lost / camera stalled / timeout) | Not started |
| FR-8 | Live view + status panel + recording button + a page to open/download CSVs | Done |
| FR-9 | Camera/stream recovers on its own within ~20 seconds of stalling | Done (watchdog + supervisor) |

---

## 3. Scope — What We Deliberately Don't Do, and Why

The following limits are deliberate choices, meant to keep the system reproducible on common hardware and
within the timeframe of one term's research.

- **No machine learning** — the whole project is a test of whether classical techniques are enough; adding a
  model back in would make the research question meaningless.
- **One calibration per setup** — the pixel↔millimeter and volume lookup tables are inherently tied to the
  camera's position and the vessel; if either moves, the calibrated values no longer apply, so the system
  assumes everything stays fixed for the duration of an experiment.
- **One vessel, two layers** — does not support more than two liquid phases or a persistent emulsion.
- **An experimenter present at all times** — the system is not meant to run unattended.
- **No custom circuit/board design** — uses an off-the-shelf motor driver module and a separate 24V supply.
- **Configured through files/env vars** — no full settings GUI; the user is the researcher, who has code access.

---

## 4. Success Metrics

Each phase in the work plan has a "gate" that must be passed before moving on. The numbers below are starting
targets with their reasoning, to be reconfirmed after phases 1–2 are done.

**Tracking the interface (Phase 1 gate).**
The filtered value `boundary_y_smooth` must move in one direction (down) throughout a drain, and must not jump
more than ~30 pixels between two consecutive frames. The 30-pixel threshold comes from its effect on the
decision: at the current framing, 30 pixels is on the order of a few millimeters of height. If a 100+ pixel jump
from a false lock were allowed through and the pump-stop logic acted on it, the system would over- or
under-drain by roughly 10 mL. The interface must also be detected (`conf` above threshold) in at least 95% of
frames.
*Result of the 4 Sep drain test (219 seconds): the trend was correct — the filtered value moved down 104 pixels
as water was drained, and the interface was detected in 100% of frames. But the filter (the version in use at
the time) spiked as much as 151 pixels from a false re-seed when `conf` dropped. `tracking.Tracker` was changed
to never re-seed during a drain (`draining=True`), and replaying the same recording brought the worst jump down
to 12 pixels, with no jump over 20 pixels remaining (covered by tests S1–S6 in `tests/test_tracking.py`) —
**a fresh live drain is still needed to confirm this gate formally.***

**Volume accuracy (Phase 2 gate).**
RMSE of the predicted volume, from a position not known in advance, against a graduated cylinder, must be under
**2 mL**. For a cylinder this converts directly to a height-reading precision target (e.g. ~1 mm for a 5 cm
beaker); the vessel is a funnel, so mL-per-mm varies with height instead of being constant — the equivalent
precision requirement needs to be re-derived from the real calibration measurements (`P2-02`/`P2-03`) once they
exist, rather than assumed in advance.

**Repeatability (Phase 5 gate).**
Run the full loop 10 times with water + oil at the same starting volume, report RMSE and the worst single error.
Target: RMSE < 2 mL and no single run off by more than 5 mL — one badly-off run counts as a failure, because it
means the stop logic isn't robust. This is also the project's final accuracy result — there is no later phase
against a different solvent pair.

**Non-functional requirements.**
The whole system runs on a single Raspberry Pi 5 (Python 3, OpenCV, picamera2, Flask); the vision loop runs at
>= 25 fps at 1280x720 (currently ~39 fps); the time from the interface reaching its target to the pump stopping
is < 300 ms; every script can be tested against synthetic data without a camera; raw data from every run is kept
under `records/`.

---

## 5. Key Assumptions and Risks That Could Sink the Project

**Load-bearing assumptions:** the camera, vessel, and lighting stay fixed; there is a uniform, opaque background
behind the vessel and no bright light shining directly into the camera; position is only measured once the
layers have settled, not while they are still an emulsion.

**Risk 1 — the classical detector's signal-to-clutter ratio.**
Measurements show hardware edges and lines on the bench produce a gradient around 11–21, while the real
water/oil interface produces less than 1. With a narrow ROI and a uniform dark background, the detector does
lock the interface (`conf` ~12). This risk is not hypothetical: an earlier test against the separatory funnel,
before its stopcock was removed, showed the detector lock onto the metal stopcock instead of the real interface
— confirmed by measuring the gradient directly (stopcock |grad| ~13, the real interface did not register as a
peak at all). **The stopcock has since been physically removed from the funnel** (the pump now draws from a
tube entering through the top); there is no recorded instance of this failure on the apparatus as currently
configured. The underlying weakness it exposed — the detector has no notion of "interface," only "strongest edge
in the ROI" — is kept on record here as a general risk if the scene ever gets less constrained again, not as an
active failure on the current rig. Reading Chem-SDI again with this in mind: their row-gradient step is always
run *after* an ML segmentation mask removes clutter — a step this project deliberately does not have.
*Fallback approaches if brightness alone isn't enough:* a striped backdrop, reading the pattern's displacement
against a reference frame (background-oriented schlieren); a motion cue from frame differencing while the liquid
is actually flowing (the interface is the only thing moving during a drain, regardless of color); or two
conductivity electrodes in the outflow tube as the actual pump-stop trigger, with vision used only for coarse
guidance.

**Risk 2 — one board doing both vision and control.**
Untested so far: whether the vision loop's load causes timing jitter when triggering the pump. If it's
significant, control moves to a separate process.

**Risk 3 — the camera and its cable are fragile.**
In earlier testing, the camera's CSI connection dropped intermittently from frequent handling (a frontend
timeout). Before collecting quantitative data, the camera and its ribbon cable need to be rigidly mounted with
strain relief; a software watchdog already restarts a stalled capture, but that only treats the symptom.

**The pump and its wiring.** The pump (GROTHEN G928 peristaltic, 24V) is not wired yet; it must go through a
separate 24V supply and an HW-039 motor driver, never through the Pi's GPIO/5V/GND pins (this has been done
incorrectly once already, on the earlier 12V pump). `vcgencmd get_throttled` currently reads `0x0`, so the board
appears healthy.

---

## 6. Current Status and Remaining Work

Vision, turbidity-monitoring, and volume-conversion modules are written and pass against synthetic data. The
web page has a live view, CSV recording, and a watchdog that recovers a stalled camera on its own. The first
real drain test was recorded and analyzed; the `Tracker`'s false-re-seed bug found in that test has since been
fixed and validated by replaying the same recording (see §4). A separate test then surfaced the stopcock-lock
finding in risk 1 above, since resolved by removing the stopcock from the funnel.

**Remaining work, in order:** re-run a live drain on the reconfigured funnel with the current tracker to
formally confirm the P1 gate (the only remaining P1 item) -> measure the funnel and calibrate height-to-volume
with real water (multi-point, not linear) -> wire the pump safely through 24V + the HW-039 motor driver -> close
the loop between detection and pump control -> repeat 10 runs and collect RMSE -> write the report.

---

## References

Fu, X. et al. "Chem-SDI: Segmentation, detection, and inference model for AI robotic chemists in
automated liquid-liquid extraction workflow." *Microchemical Journal* 227 (2026): 118844.
