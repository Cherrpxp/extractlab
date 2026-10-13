"""Spec for motion_detection — clauses M1-M4 (see motion_detection.py docstring).

Reproduces the real failure mode found against real photos on 2026-10-13: a
static structural edge (glass curve, valve, air/oil surface) scores a stronger
gradient than the real interface, so boundary_detection.detect_boundary keeps
locking onto whichever is strongest regardless of ROI placement. Motion-
differencing instead looks at what changed between two frames -- the real
interface is the one thing that moves while draining; every false edge found
that day was static.
"""

from synthetic_data import make_frame

from motion_detection import detect_boundary_motion, detect_motion_row


# M1 -----------------------------------------------------------------------------
def test_m1_finds_row_near_a_small_real_shift():
    a, _ = make_frame(interface_row=250, noise=1.5, seed=1)
    b, _ = make_frame(interface_row=253, noise=1.5, seed=2)
    row, conf, _ = detect_motion_row(a, b)
    assert 235 <= row <= 268  # near the shift, with margin for the soft edge + smoothing
    assert conf > 1.0


# M2 -----------------------------------------------------------------------------
def test_m2_identical_frames_give_near_zero_confidence():
    a, _ = make_frame(interface_row=250, noise=1.0, seed=5)
    row, conf, profile = detect_motion_row(a, a.copy())
    assert conf < 1.0
    assert profile.max() < 1.0


# M3 -- the key regression test: a static false edge must NOT win ---------------
def test_m3_ignores_a_static_bright_stripe_when_interface_moves_elsewhere():
    a, _ = make_frame(interface_row=150, noise=1.5, seed=1)
    b, _ = make_frame(interface_row=155, noise=1.5, seed=2)
    a, b = a.copy(), b.copy()
    # A fixed, strong bright stripe at the same rows in BOTH frames -- simulates
    # a structural edge (glass curve / valve) that a static-gradient detector
    # would lock onto, but that never changes frame-to-frame.
    stripe = slice(400, 404)
    a[stripe, :] = 255
    b[stripe, :] = 255
    row, conf, _ = detect_motion_row(a, b)
    assert not (395 <= row <= 409)  # must not lock onto the static stripe
    assert 135 <= row <= 170        # finds the real, small moving shift instead


# M4 -----------------------------------------------------------------------------
def test_m4_no_previous_frame_returns_not_found():
    frame, _ = make_frame(bgr=True, seed=9)
    row, conf = detect_boundary_motion(None, frame)
    assert row is None
    assert conf == 0.0
