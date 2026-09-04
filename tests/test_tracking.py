"""Spec for tracking.Tracker — clauses S1-S6 (see tracking.py docstring, PRD §4).

Numbers are grounded in records/rec_20260904_115249.csv: while locked the
detector reports conf ~8-12; during the glitches conf drops to ~2-7.
"""

import pytest

from tracking import (
    CONFIDENCE_THRESHOLD,
    TRACK_MAX_STEP,
    TRACK_MONO_SLACK,
    TRACK_RESEED_AFTER,
    TRACK_WIN,
    Tracker,
)

FAR = TRACK_MAX_STEP + 100  # a jump well past the "off position" threshold


def _settle(t: Tracker, y: int, conf: float = 10.0, n: int = TRACK_WIN + 3) -> float:
    for _ in range(n):
        t.update(y, conf)
    return t.smooth


# S1 -----------------------------------------------------------------------------
def test_s1_clean_signal_passes_through():
    t = Tracker()
    step = 3
    truth = list(range(400, 460, step))  # +step px/frame, well under TRACK_MAX_STEP
    out = [t.update(y, conf=10.0) for y in truth]
    assert all(b >= a for a, b in zip(out, out[1:]))       # follows, never backtracks
    # a k-wide median lags a ramp by ~(k-1)/2 frames -> (k-1)/2 * step px, no more
    assert abs(out[-1] - truth[-1]) <= (TRACK_WIN - 1) // 2 * step + 2


# S2 -----------------------------------------------------------------------------
def test_s2_lone_outlier_rejected():
    t = Tracker()
    before = _settle(t, 500)
    spiked = t.update(500 + 150, conf=10.0)  # one frame, far away
    after = t.update(500, conf=10.0)
    assert abs(spiked - before) <= 2
    assert abs(after - 500) <= 2


# S3 -----------------------------------------------------------------------------
def test_s3_sub_threshold_conf_is_ignored():
    t = Tracker()
    _settle(t, 500)
    held = t.update(650, conf=CONFIDENCE_THRESHOLD - 1.0)  # far, but not trusted
    assert held == pytest.approx(500, abs=2)


# S4 -- the drain-test bug: no re-seed while draining -------------------------
def test_s4_never_reseeds_while_draining():
    t = Tracker()
    locked = _settle(t, 500, conf=10.0)
    for _ in range(TRACK_RESEED_AFTER + 30):     # a long, stable wrong lock, full conf
        t.update(500 + FAR, conf=10.0, draining=True)
    assert abs(t.smooth - locked) <= TRACK_MAX_STEP  # held; never jumped to the far value


# S5 -- re-acquisition in the live view (not draining) ----------------------
def test_s5_reacquires_a_sustained_far_run_when_not_draining():
    t = Tracker()
    _settle(t, 500, conf=10.0)
    for _ in range(TRACK_RESEED_AFTER + 5):
        t.update(500 + FAR, conf=10.0, draining=False)
    assert abs(t.smooth - (500 + FAR)) <= TRACK_MAX_STEP


# S6 -----------------------------------------------------------------------------
def test_s6_no_backward_motion_while_draining():
    t = Tracker()
    for y in range(400, 520, 4):                 # interface descending (drain)
        t.update(y, conf=10.0, draining=True)
    top = t.smooth
    for _ in range(5):                           # frames that pull it back up, within MAX_STEP
        t.update(int(top) - 15, conf=10.0, draining=True)
    assert t.smooth >= top - TRACK_MONO_SLACK
