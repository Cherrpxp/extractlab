"""Spec for boundary_detection.detect_boundary_saturation.

Grounded in a real photo measured 2026-10-13 (water-oil funnel): at the
eye-confirmed true interface, HSV saturation's gradient (~4.7) was more than
double grayscale's (~2.1) there. Oil's colour (high saturation) vs water's
near-colourless appearance (low saturation) is a real signal brightness
alone discards -- these tests build a synthetic BGR image where the two
bands differ mainly in saturation, not brightness, to pin that down.
"""

import cv2
import numpy as np

from boundary_detection import detect_boundary, detect_boundary_saturation


def _two_band_bgr(split_row: int = 100, height: int = 200, width: int = 100) -> np.ndarray:
    """Upper band: desaturated grey (~water). Lower band: saturated yellow
    (~oil). Brightness (max channel) matches on both sides by construction,
    so a grayscale detector has much less to work with than a saturation one.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:split_row] = (180, 180, 180)  # BGR grey: R=G=B -> saturation 0
    img[split_row:] = (40, 180, 180)   # BGR yellow-ish: low B, high G/R -> saturated
    return img


def test_saturation_finds_the_band_transition():
    img = _two_band_bgr(split_row=100)
    row, confidence = detect_boundary_saturation(img, roi=(0, 0, 100, 200))
    assert 90 <= row <= 110
    assert confidence > 10


def test_saturation_beats_grayscale_when_only_colour_differs():
    img = _two_band_bgr(split_row=100)
    roi = (0, 0, 100, 200)
    _, sat_conf = detect_boundary_saturation(img, roi=roi)
    _, gray_conf = detect_boundary(img, roi=roi)
    assert sat_conf > gray_conf * 1.5  # not just marginally better


def test_saturation_matches_grayscale_api_shape():
    # Same call shape as detect_boundary: roi=None uses the whole frame.
    img = _two_band_bgr(split_row=50, height=100, width=60)
    row, confidence = detect_boundary_saturation(img)
    assert 40 <= row <= 60
    assert confidence > 0
