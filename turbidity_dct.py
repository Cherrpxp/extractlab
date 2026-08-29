"""Turbidity (clear vs cloudy) monitoring via the DCT high-frequency ratio,
with a sliding-window slope test to decide when an emulsion has settled.

A sharp, well-separated image keeps energy in the high-frequency DCT
coefficients (crisp meniscus, texture, glass edges). A turbid emulsion
scatters light, washes out contrast and blurs detail, so that high-frequency
energy collapses. Following the metric across successive frames and fitting a
slope over a sliding window tells you whether it is still clearing or has
plateaued -- i.e. whether it is safe to act on the boundary yet.

Classical only (OpenCV DCT + a linear fit), no training.
"""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np


def dct_sharpness(gray_roi: np.ndarray, cutoff: float = 0.25) -> float:
    """Exposure-normalised high-frequency DCT energy of a patch.

    Large for a crisp, well-separated view (fine glass/meniscus texture, sharp
    edges); it collapses toward 0 when a turbid emulsion scatters light and
    blurs detail. Normalised by mean intensity so it does not move with
    lighting. Absolute (not a fraction of total energy), so a strong low-
    frequency feature like the interface step does not distort it.
    """
    g = gray_roi.astype(np.float32)
    if g.ndim == 3:
        g = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    g = g[:h - (h % 2), :w - (w % 2)]          # cv2.dct needs even sides
    if g.shape[0] < 4 or g.shape[1] < 4:
        return 0.0
    mu = float(g.mean()) + 1e-6

    p = cv2.dct(g - g.mean()) ** 2
    fi = np.arange(p.shape[0])[:, None] / p.shape[0]
    fj = np.arange(p.shape[1])[None, :] / p.shape[1]
    hf = np.hypot(fi, fj) > cutoff
    return float(np.sqrt(p[hf].mean()) / mu)


def turbidity_index(gray_roi: np.ndarray, reference_sharpness: float,
                    cutoff: float = 0.25) -> float:
    """0 (clear) .. 1 (turbid), given a known clear-state sharpness value."""
    if reference_sharpness <= 0:
        return 0.0
    s = dct_sharpness(gray_roi, cutoff)
    return float(np.clip(1.0 - s / reference_sharpness, 0.0, 1.0))


class TurbidityMonitor:
    """Frame-by-frame settle detector.

    Feed the ROI around the interface each frame. State transitions:
      warming_up -> not enough history yet
      turbid     -> sharpness well below the clear reference
      clearing   -> sharpness still trending (slope over the window is large)
      clear      -> sharp and flat  (``settled`` is True)
    """

    def __init__(self, window: int = 8, rel_clear: float = 0.8,
                 slope_tol: float = 0.01, cutoff: float = 0.25,
                 reference_sharpness: float | None = None):
        """reference_sharpness: the high-frequency ratio of a known-clear view
        (empty funnel or single settled liquid, same lighting). Measure it once
        with :func:`dct_sharpness` and pass it in for a stable threshold.
        If omitted, a running maximum is used and 'clear' is only declared
        after a rise-then-plateau, so a mix that was turbid from frame 1 is not
        mistaken for already-settled."""
        self.window = window
        self.rel_clear = rel_clear
        self.slope_tol = slope_tol
        self.cutoff = cutoff
        self._fixed = reference_sharpness
        self.reset()

    def reset(self) -> None:
        self._hist: deque[float] = deque(maxlen=self.window)
        self._ref = self._fixed or 1e-6
        self._n = 0
        self._seen_clearing = self._fixed is not None

    def update(self, gray_roi: np.ndarray) -> dict:
        r = dct_sharpness(gray_roi, self.cutoff)
        if self._fixed is None:
            self._ref = max(self._ref, r)
        self._hist.append(r)
        self._n += 1

        # decide on the windowed MEAN, not the (noisy) single-frame ratio
        hist = np.array(self._hist, dtype=np.float64)
        rel = float(hist.mean() / max(self._ref, 1e-9))
        slope = 0.0
        if len(hist) >= 3:
            xs = np.arange(len(hist))
            slope = float(np.polyfit(xs, hist / max(self._ref, 1e-9), 1)[0])
        if slope > self.slope_tol:
            self._seen_clearing = True

        if len(self._hist) < 3:
            state = "warming_up"
        elif slope > self.slope_tol:
            state = "clearing"
        elif rel >= self.rel_clear and self._seen_clearing:
            state = "clear"
        elif rel < self.rel_clear:
            state = "turbid"
        else:
            state = "clearing"

        return {"ratio": r, "rel": rel, "slope": slope, "state": state,
                "settled": state == "clear", "frame": self._n}


if __name__ == "__main__":
    # settle demo on synthetic data: turbid -> clearing -> clear
    from synthetic_data import make_draining_sequence

    from synthetic_data import make_frame

    frames, metas = make_draining_sequence(24, turbidity0=0.85, clear_by_frac=0.5)
    ref, _ = make_frame(560, 160, interface_frac=0.5, turbidity=0.0, seed=7)
    mon = TurbidityMonitor(reference_sharpness=dct_sharpness(ref))
    print(f"{'f':>2} {'turb_true':>9} {'sharp':>7} {'rel':>6} {'slope':>8}  state")
    for f, m in zip(frames, metas):
        s = mon.update(f)
        print(f"{s['frame']:>2} {m.turbidity:>9.2f} {s['ratio']:>7.4f} "
              f"{s['rel']:>6.2f} {s['slope']:>8.4f}  {s['state']}")
