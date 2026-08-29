"""Interface height -> retained liquid volume for the pear-shaped 125 mL
separatory funnel.

Two models:

  FrustumModel      analytic cone-frustum volume. Valid ONLY up the lower
                    conical section; the pear bulb above it is not a frustum,
                    so above `valid_max_height_mm` it returns NaN. No
                    calibration, good for a sanity check.

  CalibrationTable  monotonic interpolation through (height, volume) pairs
                    measured by adding known volumes of water. This is what
                    phase P2 populates and what the running system should use
                    (see risk #3 in CLAUDE.md: the table is specific to the
                    vessel it was measured on). JSON save / load.

`pixel_row_to_height_mm` maps an image row (from boundary_detection) to a
physical height above the stopcock, given one calibration mark.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


def pixel_row_to_height_mm(row: float, row_at_zero: float, mm_per_px: float) -> float:
    """Row index -> height above the stopcock. Rows increase downward, so a
    smaller row = higher liquid. `row_at_zero` is the row of the zero-volume
    reference (stopcock / cone tip); `mm_per_px` comes from imaging a ruler."""
    return (row_at_zero - row) * mm_per_px


@dataclass
class FrustumModel:
    # placeholder geometry for THIS funnel -- measure and replace in P2.
    r_bottom_mm: float = 1.5          # radius at the cone tip / stopcock bore
    r_top_mm: float = 16.0            # radius where the cone meets the bulb
    cone_height_mm: float = 42.0      # height of the straight conical section

    @property
    def valid_max_height_mm(self) -> float:
        return self.cone_height_mm

    def _radius_at(self, h: float) -> float:
        f = h / self.cone_height_mm
        return self.r_bottom_mm + (self.r_top_mm - self.r_bottom_mm) * f

    def volume_ml(self, height_mm: float) -> float:
        """Volume from the tip up to `height_mm`, in mL. NaN above the cone."""
        if height_mm <= 0:
            return 0.0
        if height_mm > self.valid_max_height_mm + 1e-6:
            return math.nan
        r0, r1 = self.r_bottom_mm, self._radius_at(height_mm)
        vol_mm3 = math.pi * height_mm / 3.0 * (r0 * r0 + r0 * r1 + r1 * r1)
        return vol_mm3 / 1000.0


class CalibrationTable:
    """Monotonic (height_mm -> volume_ml) lookup with linear interpolation."""

    def __init__(self, heights_mm, volumes_ml):
        pairs = sorted(zip(map(float, heights_mm), map(float, volumes_ml)))
        self.heights = [h for h, _ in pairs]
        self.volumes = [v for _, v in pairs]
        if any(b < a for a, b in zip(self.volumes, self.volumes[1:])):
            raise ValueError("volumes must be non-decreasing with height")
        if len(self.heights) < 2:
            raise ValueError("need at least two calibration points")

    @staticmethod
    def _interp(x: float, xs: list[float], ys: list[float]) -> tuple[float, bool]:
        clamped = x < xs[0] or x > xs[-1]
        if x <= xs[0]:
            return ys[0], clamped
        if x >= xs[-1]:
            return ys[-1], clamped
        i = max(j for j in range(len(xs)) if xs[j] <= x)
        t = (x - xs[i]) / (xs[i + 1] - xs[i])
        return ys[i] + t * (ys[i + 1] - ys[i]), clamped

    def volume_ml(self, height_mm: float) -> float:
        return self._interp(height_mm, self.heights, self.volumes)[0]

    def height_mm(self, volume_ml: float) -> float:
        """Inverse: the height at which `volume_ml` is retained below the
        interface -- use this to compute a pump stop target."""
        return self._interp(volume_ml, self.volumes, self.heights)[0]

    def out_of_range(self, height_mm: float) -> bool:
        return self._interp(height_mm, self.heights, self.volumes)[1]

    def add_point(self, height_mm: float, volume_ml: float) -> None:
        self.__init__(self.heights + [height_mm], self.volumes + [volume_ml])

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump({"heights_mm": self.heights, "volumes_ml": self.volumes}, fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "CalibrationTable":
        with open(path) as fh:
            d = json.load(fh)
        return cls(d["heights_mm"], d["volumes_ml"])

    @classmethod
    def from_model(cls, model: FrustumModel, n: int = 12) -> "CalibrationTable":
        """Seed a table from the analytic model (placeholder until real water
        measurements exist)."""
        hs = [model.valid_max_height_mm * k / (n - 1) for k in range(n)]
        return cls(hs, [model.volume_ml(h) for h in hs])


if __name__ == "__main__":
    fm = FrustumModel()
    print("frustum model (placeholder geometry):")
    for h in (0, 10, 20, 30, 42):
        print(f"  h={h:>2} mm  ->  {fm.volume_ml(h):6.2f} mL")
    print(f"  h=60 mm  ->  {fm.volume_ml(60)} (above the cone)")

    cal = CalibrationTable.from_model(fm)
    print("\ncalibration table round-trip:")
    for v in (1.0, 5.0, 10.0):
        h = cal.height_mm(v)
        print(f"  keep {v:>4.1f} mL  ->  stop when interface reaches h={h:5.2f} mm "
              f"->  back to {cal.volume_ml(h):.2f} mL")
