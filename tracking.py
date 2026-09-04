"""Temporal filter for the per-frame ``boundary_y`` from ``boundary_detection``.

Hardware-free (numpy only) so it is unit-testable without a camera.
``realtime_stream.py`` imports :class:`Tracker` from here.

Behaviour contract — see ``tests/test_tracking.py`` (clauses S1-S6) and PRD §4:

  S1  a clean signal (steps <= TRACK_MAX_STEP) passes straight through, median lag only
  S2  a lone outlier is rejected
  S3  a frame with conf < CONFIDENCE_THRESHOLD contributes nothing (hold last)
  S4  while ``draining`` the output NEVER re-seeds onto a far position: during a
      controlled drain the interface only creeps, so any large jump is a false
      lock. (Verified on records/rec_20260904_115249.csv: re-seeding was the
      source of every >20 px glitch; disabling it drops the worst jump 146 -> 26 px.)
  S5  while NOT draining, a sustained run at a far position IS followed after
      TRACK_RESEED_AFTER frames -- this is re-acquisition after the camera is
      re-aimed or the interface is re-found in the live view.
  S6  while ``draining`` a step that pulls the output backwards past
      TRACK_MONO_SLACK px is rejected (the interface descends monotonically).
"""

from __future__ import annotations

from collections import deque

import numpy as np

CONFIDENCE_THRESHOLD = 3.0   # conf below this -> "no boundary this frame"
TRACK_WIN = 9                # median window (frames)
TRACK_MAX_STEP = 30          # px; a larger jump from the smoothed value is "off position"
TRACK_RESEED_AFTER = 15      # off-position frames before re-acquiring (only when not draining)
TRACK_MONO_SLACK = 8         # px of backward motion tolerated while draining


class Tracker:
    def __init__(self) -> None:
        self._hist: deque[int] = deque(maxlen=TRACK_WIN)
        self._smooth: float | None = None
        self._rejects = 0

    @property
    def smooth(self) -> float | None:
        return self._smooth

    def _accept(self, raw: int) -> None:
        self._hist.append(int(raw))
        self._smooth = float(np.median(self._hist))
        self._rejects = 0

    def update(self, raw: int, conf: float, draining: bool = False) -> float | None:
        if conf < CONFIDENCE_THRESHOLD:
            return self._smooth  # S3: an untrusted frame contributes nothing

        if self._smooth is None:
            self._accept(raw)
            return self._smooth

        step = raw - self._smooth
        if abs(step) <= TRACK_MAX_STEP:
            if draining and step < -TRACK_MONO_SLACK:
                self._rejects += 1  # S6: the interface does not move back up
                return self._smooth
            self._accept(raw)
            return self._smooth

        # off position
        self._rejects += 1
        if not draining and self._rejects >= TRACK_RESEED_AFTER:
            self._hist.clear()  # S5: re-acquire in the live view; S4: never while draining
            self._accept(raw)
        return self._smooth
