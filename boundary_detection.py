"""Row-wise gradient boundary detection for a liquid-liquid interface.

Hardware-agnostic: operates on numpy/OpenCV image arrays only, no camera I/O.
Works on real frames (BGR from OpenCV/picamera2) or synthetic test images.
"""

import cv2
import numpy as np


def row_intensity_profile(gray_roi: np.ndarray) -> np.ndarray:
    """Mean pixel intensity per row, averaged across the ROI width."""
    return gray_roi.mean(axis=1).astype(np.float64)


def detect_boundary_row(gray_roi: np.ndarray, smooth_kernel: int = 5) -> tuple[int, float, np.ndarray, np.ndarray]:
    """Find the row index with the strongest vertical intensity gradient.

    Returns (boundary_row, confidence, smoothed_profile, gradient) where
    boundary_row/confidence are relative to gray_roi (row 0 = top of ROI).
    confidence is the raw |gradient| at the detected row — compare against
    a threshold tuned from real data to reject false positives (e.g. glare).
    """
    profile = row_intensity_profile(gray_roi)
    if smooth_kernel > 1:
        # Edge-replicate padding before convolving, so the smoothed profile
        # doesn't taper toward zero at the ROI's top/bottom rows (that taper
        # would otherwise look like a strong gradient and get picked as the
        # "boundary" even with no real interface there).
        pad = smooth_kernel // 2
        padded = np.pad(profile, pad, mode="edge")
        kernel = np.ones(smooth_kernel) / smooth_kernel
        profile = np.convolve(padded, kernel, mode="valid")
    gradient = np.gradient(profile)
    # Exclude a margin at the edges from the search: even with edge-replicate
    # padding, a real interface right at the ROI boundary can't be told apart
    # from crop-edge artifacts, so the ROI should be framed with margin above
    # and below the expected interface position.
    margin = smooth_kernel if smooth_kernel > 1 else 0
    if len(gradient) > 2 * margin:
        search = np.abs(gradient[margin:len(gradient) - margin])
        boundary_row = margin + int(np.argmax(search))
    else:
        boundary_row = int(np.argmax(np.abs(gradient)))
    confidence = float(np.abs(gradient[boundary_row]))
    return boundary_row, confidence, profile, gradient


def detect_boundary(frame_bgr: np.ndarray, roi: tuple[int, int, int, int] | None = None,
                     smooth_kernel: int = 5) -> tuple[int, float]:
    """Detect the liquid-liquid interface in a full frame.

    roi: (x, y, w, h) pixel box cropping the vial column, in frame coordinates.
         Pass None to use the whole frame.
    Returns (boundary_y, confidence) in full-frame pixel coordinates.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if roi is not None:
        x, y, w, h = roi
        gray_roi = gray[y:y + h, x:x + w]
    else:
        gray_roi = gray
        y = 0
    row, confidence, _profile, _gradient = detect_boundary_row(gray_roi, smooth_kernel)
    return row + y, confidence