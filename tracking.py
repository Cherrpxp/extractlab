"""Temporal filter for the per-frame ``boundary_y`` from ``boundary_detection``.

Hardware-free (numpy only) so it is unit-testable without a camera.
``realtime_stream.py`` imports :class:`Tracker` from here.

Behaviour contract — see ``tests/test_tracking.py`` (clauses S1-S6) and PRD §4:

  S1  a clean signal (steps <= TRACK_MAX_STEP) passes straight through, median lag only
  S2  a lone outlier is rejected
  S3  a frame with conf < CONFIDENCE_THRESHOLD contributes nothing (hold last)
  S4  a persistent wrong lock at *marginal* confidence must NOT re-seed the output
  S5  a genuine fast move (strong confidence at the new position) IS followed
  S6  with draining=True, motion that pulls the output backwards past
      TRACK_MONO_SLACK px is rejected
"""

from __future__ import annotations

from collections import deque

import numpy as np

CONFIDENCE_THRESHOLD = 3.0      # conf below this -> "no boundary this frame"
TRACK_WIN = 9                   # median window (frames)
TRACK_MAX_STEP = 30             # px; a larger jump from the smoothed value is "off position"
TRACK_RESEED_AFTER = 15         # consecutive off-position frames before a re-seed
TRACK_RESEED_CONF_FRAC = 0.8    # re-seed only if off-position conf >= frac * reference conf
TRACK_MONO_SLACK = 8            # px of backward motion tolerated while draining


class Tracker:
    def __init__(self) -> None:
        self._hist: deque[int] = deque(maxlen=TRACK_WIN)
        self._smooth: float | None = None
        self._rejects = 0

    @property
    def smooth(self) -> float | None:
        return self._smooth

    def update(self, raw: int, conf: float, draining: bool = False) -> float | None:
        found = conf >= CONFIDENCE_THRESHOLD
        if not found:
            return self._smooth  # S3: hold last during a dropout

        if self._smooth is None or abs(raw - self._smooth) <= TRACK_MAX_STEP \
                or self._rejects >= TRACK_RESEED_AFTER:
            if self._smooth is not None and abs(raw - self._smooth) > TRACK_MAX_STEP:
                self._hist.clear()  # re-seeding after a sustained move
            self._hist.append(int(raw))
            self._smooth = float(np.median(self._hist))
            self._rejects = 0
        else:
            self._rejects += 1
        return self._smooth
