"""Frame-differencing interface detection: finds the row that changed most
between two consecutive frames, instead of the row with the strongest static
gradient (boundary_detection.py).

Hardware-agnostic: operates on numpy/OpenCV image arrays only, no camera I/O.
Only meaningful while the interface is actually moving (draining) -- every
false edge found against real photos on 2026-10-13 (the bulb/cone glass
curve, the air/oil surface, the valve fitting) was static, so it registers
near zero here even though it dominates the gradient-based detector.
"""

import cv2
import numpy as np

# Reverted to the original placeholder: raising it to 15 (based on
# records/rec_20261013_185728.csv, which ranged 34-96) made a later live
# drain visibly worse, so that data point doesn't generalize as safely as
# assumed. Needs a cleaner re-tune from more than one real recording before
# moving off this placeholder again.
MOTION_CONFIDENCE_THRESHOLD = 2.0


def row_diff_profile(gray_roi_prev: np.ndarray, gray_roi_curr: np.ndarray) -> np.ndarray:
    """Mean |pixel difference| per row between two grayscale ROI crops."""
    diff = cv2.absdiff(gray_roi_curr, gray_roi_prev)
    return diff.mean(axis=1).astype(np.float64)


def detect_motion_row(gray_roi_prev: np.ndarray, gray_roi_curr: np.ndarray,
                       smooth_kernel: int = 5) -> tuple[int, float, np.ndarray]:
    """Find the row with the most frame-to-frame change.

    Returns (row, confidence, smoothed_profile) -- row/confidence are relative
    to the ROI crops (row 0 = top). confidence is the smoothed diff magnitude
    at that row; compare against MOTION_CONFIDENCE_THRESHOLD (tuned from real
    data, same discipline as boundary_detection's CONFIDENCE_THRESHOLD).
    """
    profile = row_diff_profile(gray_roi_prev, gray_roi_curr)
    if smooth_kernel > 1:
        pad = smooth_kernel // 2
        padded = np.pad(profile, pad, mode="edge")
        kernel = np.ones(smooth_kernel) / smooth_kernel
        profile = np.convolve(padded, kernel, mode="valid")
    row = int(np.argmax(profile))
    confidence = float(profile[row])
    return row, confidence, profile


def detect_boundary_motion(frame_bgr_prev: np.ndarray | None, frame_bgr_curr: np.ndarray,
                            roi: tuple[int, int, int, int] | None = None,
                            smooth_kernel: int = 5) -> tuple[int | None, float]:
    """Motion-based interface detection across a full frame pair.

    Same call shape as boundary_detection.detect_boundary, so the two can be
    swapped in realtime_stream.py's capture loop based on whether a drain is
    running. Returns (None, 0.0) if frame_bgr_prev is None -- no diff is
    possible yet (the first frame right after a drain starts).
    """
    if frame_bgr_prev is None:
        return None, 0.0
    gray_prev = cv2.cvtColor(frame_bgr_prev, cv2.COLOR_BGR2GRAY)
    gray_curr = cv2.cvtColor(frame_bgr_curr, cv2.COLOR_BGR2GRAY)
    if roi is not None:
        x, y, w, h = roi
        gray_prev = gray_prev[y:y + h, x:x + w]
        gray_curr = gray_curr[y:y + h, x:x + w]
    else:
        y = 0
    row, confidence, _profile = detect_motion_row(gray_prev, gray_curr, smooth_kernel)
    return row + y, confidence
