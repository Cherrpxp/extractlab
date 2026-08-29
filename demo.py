"""End-to-end dry run of the vision pipeline on synthetic data.

Ties the three analysis modules together over a simulated draining sequence:

    synthetic_data   -> frames of a funnel whose interface descends while an
                        initial emulsion clears
    turbidity_dct    -> per-frame settle state (act only when 'clear')
    boundary_detection -> interface row from the row-wise brightness gradient
    volume_model     -> retained volume below the interface

Prints a per-frame table and a summary, and doubles as a smoke test: the
boundary error on genuinely clear frames must stay small.
"""

from __future__ import annotations

import sys

import numpy as np

from boundary_detection import detect_boundary_row
from synthetic_data import make_draining_sequence, make_frame
from turbidity_dct import TurbidityMonitor, dct_sharpness
from volume_model import CalibrationTable, FrustumModel, pixel_row_to_height_mm


def run() -> int:
    height, width = 560, 160
    frames, metas = make_draining_sequence(
        28, height=height, width=width, start_frac=0.72, end_frac=0.20,
        turbidity0=0.85, clear_by_frac=0.5, upper_level=150.0, lower_level=118.0,
        noise=3.0, seed=1,
    )

    # image -> physical height: pretend the column bottom is the zero mark and
    # the calibrated cone (FrustumModel) spans its lower part.
    fm = FrustumModel()
    cal = CalibrationTable.from_model(fm)
    row_zero = height - 1
    mm_per_px = fm.valid_max_height_mm / (0.75 * height)  # cone ~ lower 3/4

    # calibrate the turbidity reference once on a known-clear view, as the real
    # rig would (single settled liquid, same lighting).
    ref_frame, _ = make_frame(height, width, interface_frac=0.5, turbidity=0.0, seed=99)
    mon = TurbidityMonitor(reference_sharpness=dct_sharpness(ref_frame))

    print(f"{'f':>2} {'turb':>5} {'state':>10} {'true':>5} {'det':>5} {'err':>4} "
          f"{'conf':>6} {'h_mm':>6} {'vol_mL':>7}")
    errs_clear = []
    saw_clear = False
    for i, (img, m) in enumerate(zip(frames, metas)):
        t = mon.update(img)
        row, conf, _, _ = detect_boundary_row(img, smooth_kernel=5)
        err = row - m.interface_row
        h_mm = pixel_row_to_height_mm(row, row_zero, mm_per_px)
        h_mm = float(np.clip(h_mm, 0.0, fm.valid_max_height_mm))
        vol = cal.volume_ml(h_mm)

        if t["state"] == "clear":
            saw_clear = True
            errs_clear.append(err)

        print(f"{i:>2} {m.turbidity:>5.2f} {t['state']:>10} {m.interface_row:>5} "
              f"{row:>5} {err:>+4d} {conf:>6.1f} {h_mm:>6.2f} {vol:>7.2f}")

    print("\nsummary")
    print(f"  frames                : {len(frames)}")
    print(f"  reached 'clear'        : {saw_clear}")
    if errs_clear:
        rmse = float(np.sqrt(np.mean(np.square(errs_clear))))
        print(f"  boundary RMSE (clear) : {rmse:.2f} px  over {len(errs_clear)} frames")
    print(f"  final retained volume  : {vol:.2f} mL")

    # smoke-test assertions
    ok = True
    truly_clear = [(detect_boundary_row(f, 5)[0] - m.interface_row)
                   for f, m in zip(frames, metas) if m.turbidity == 0.0]
    if truly_clear:
        rmse0 = float(np.sqrt(np.mean(np.square(truly_clear))))
        ok &= rmse0 <= 4.0
        print(f"  [check] RMSE on turbidity==0 frames = {rmse0:.2f} px (want <= 4.0)")
    ok &= saw_clear
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
