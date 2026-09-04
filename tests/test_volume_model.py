"""Regression net for volume_model — the P2 building block.

These pass today; they lock in the contract before real beaker geometry and
calibration data replace the placeholder FrustumModel numbers.
"""

import math

import pytest

from volume_model import CalibrationTable, FrustumModel, pixel_row_to_height_mm


def test_frustum_zero_and_monotonic():
    m = FrustumModel()
    assert m.volume_ml(0) == 0.0
    vs = [m.volume_ml(h) for h in range(0, int(m.valid_max_height_mm) + 1, 5)]
    assert all(b >= a for a, b in zip(vs, vs[1:]))


def test_frustum_returns_nan_above_the_cone():
    m = FrustumModel()
    assert math.isnan(m.volume_ml(m.valid_max_height_mm + 10))


def test_calibration_inverse_roundtrips():
    cal = CalibrationTable.from_model(FrustumModel())
    for v in (1.0, 5.0, 10.0):
        assert cal.volume_ml(cal.height_mm(v)) == pytest.approx(v, abs=1e-6)


def test_calibration_rejects_non_monotonic_volume():
    with pytest.raises(ValueError):
        CalibrationTable([0, 10, 20], [0, 50, 40])  # volume must not decrease with height


def test_pixel_row_to_height_is_linear_and_inverted():
    # rows increase downward, so a smaller row = higher liquid = larger height
    h_low = pixel_row_to_height_mm(row=690, row_at_zero=700, mm_per_px=0.34)
    h_high = pixel_row_to_height_mm(row=600, row_at_zero=700, mm_per_px=0.34)
    assert h_high > h_low
    assert h_low == pytest.approx(10 * 0.34)
