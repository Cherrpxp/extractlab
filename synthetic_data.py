"""Synthetic separatory-funnel frames for testing the vision pipeline before
real data is available.

A frame is a grayscale (or BGR) image of the funnel column holding two liquid
layers with slightly different mean brightness, a soft interface, optional
turbidity (an emulsion that scatters light and washes out contrast), optional
edge glare, and sensor noise. `make_draining_sequence` builds a time series
where the interface descends and an initially turbid mix clears.

Pure numpy + OpenCV — no plotting or scipy dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FrameMeta:
    interface_row: int          # ground-truth interface, row index (0 = top)
    turbidity: float            # 0 clear .. 1 fully emulsified
    upper_level: float          # mean grey of the upper (lighter organic) layer
    lower_level: float          # mean grey of the lower (aqueous) layer


_TEXTURE_SEED = 20240501  # fixed wall/glass micro-texture (only photon noise varies)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def make_frame(height: int = 560, width: int = 160, *,
               interface_row: int | None = None, interface_frac: float = 0.5,
               upper_level: float = 148.0, lower_level: float = 120.0,
               edge_softness: float = 3.0, turbidity: float = 0.0,
               glare: float = 0.0, noise: float = 3.0,
               seed: int | None = None, bgr: bool = False):
    """One synthetic frame plus its ground-truth :class:`FrameMeta`.

    interface_row overrides interface_frac when given. turbidity in [0, 1]
    collapses the layer contrast toward the column mean and adds blurred
    scatter, mimicking an unsettled emulsion.
    """
    rng = np.random.default_rng(seed)
    if interface_row is None:
        interface_row = int(round(interface_frac * height))
    interface_row = int(np.clip(interface_row, 1, height - 2))

    y = np.arange(height, dtype=np.float64)
    # smooth step from upper_level (above) to lower_level (below)
    w = _sigmoid((y - interface_row) / max(edge_softness, 1e-3))
    col = upper_level * (1.0 - w) + lower_level * w
    img = np.repeat(col[:, None], width, axis=1)

    # faint FIXED fine structure (glass, meniscus micro-relief, wall texture) so
    # a "clear" frame is not a detail-free desert -- this is what turbidity then
    # blurs away, and what the DCT high-frequency metric keys on. Deterministic
    # in (height, width), so successive clear frames match to within sensor noise.
    trng = np.random.default_rng(_TEXTURE_SEED)
    tex = (3.5 * np.sin(y * 0.9)[:, None]
           + cv2.GaussianBlur(trng.normal(0.0, 6.0, (height, width)), (3, 3), 0))
    img = img + tex

    if turbidity > 0:
        # scattering: blur out detail, lose contrast, add a pale haze
        k = max(int(round(1 + 10 * turbidity)) | 1, 3)
        img = cv2.GaussianBlur(img, (k, k), 0)
        mean = 0.5 * (upper_level + lower_level)
        img = mean + (img - mean) * (1.0 - 0.88 * turbidity) + 18.0 * turbidity

    if glare > 0:
        gx = int(width * 0.7)
        band = np.exp(-0.5 * ((np.arange(width) - gx) / max(width * 0.04, 1)) ** 2)
        img = img + glare * 90.0 * band[None, :]

    img = img + rng.normal(0.0, noise, (height, width))
    img = np.clip(img, 0, 255).astype(np.uint8)
    if bgr:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    return img, FrameMeta(interface_row, float(turbidity), upper_level, lower_level)


def make_draining_sequence(n_frames: int = 30, *, height: int = 560, width: int = 160,
                           start_frac: float = 0.75, end_frac: float = 0.18,
                           turbidity0: float = 0.8, clear_by_frac: float = 0.45,
                           seed: int | None = 0, bgr: bool = False, **frame_kw):
    """A draining run: interface goes start_frac -> end_frac while an initial
    emulsion (turbidity0) clears linearly, reaching 0 at clear_by_frac of the run.

    Returns (frames, metas) as parallel lists.
    """
    rng = np.random.default_rng(seed)
    frames, metas = [], []
    for i in range(n_frames):
        t = i / max(n_frames - 1, 1)
        frac = start_frac + (end_frac - start_frac) * t
        turb = turbidity0 * max(0.0, 1.0 - t / max(clear_by_frac, 1e-3))
        img, meta = make_frame(height, width, interface_frac=frac, turbidity=turb,
                               seed=int(rng.integers(0, 2**31)), bgr=bgr, **frame_kw)
        frames.append(img)
        metas.append(meta)
    return frames, metas


def save_video(frames, path: str, fps: int = 10) -> None:
    """Write frames (grayscale or BGR) to an MJPG .avi for eyeballing."""
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    for f in frames:
        vw.write(f if f.ndim == 3 else cv2.cvtColor(f, cv2.COLOR_GRAY2BGR))
    vw.release()


if __name__ == "__main__":
    frames, metas = make_draining_sequence(24)
    save_video(frames, "synthetic_drain.avi")
    print(f"wrote synthetic_drain.avi  ({len(frames)} frames, {frames[0].shape})")
    print("interface rows:", [m.interface_row for m in metas])
    print("turbidity:     ", [round(m.turbidity, 2) for m in metas])
