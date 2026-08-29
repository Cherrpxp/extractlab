"""Run the boundary + turbidity checks on a single real photo.

    python3 analyze_real_photo.py photo.jpg --roi 610 235 110 150
    python3 analyze_real_photo.py photo.jpg --roi 610 235 110 150 \
        --calib funnel_calib.json --row-zero 690 --mm-per-px 0.34

Writes an annotated PNG (ROI box + detected interface line + readout) and,
with --profile-csv, the per-row intensity/gradient so a threshold can be tuned
in a spreadsheet.
"""

from __future__ import annotations

import argparse
import os

import cv2
import numpy as np

from boundary_detection import detect_boundary_row
from turbidity_dct import dct_sharpness


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
                    help="crop box around the funnel column; default = whole frame")
    ap.add_argument("--smooth", type=int, default=5, help="row-profile smoothing window")
    ap.add_argument("--calib", help="CalibrationTable JSON -> also report volume")
    ap.add_argument("--row-zero", type=float, help="frame row of the zero-volume mark")
    ap.add_argument("--mm-per-px", type=float, help="vertical scale from a ruler shot")
    ap.add_argument("--out", help="annotated PNG path (default <image>_annotated.png)")
    ap.add_argument("--profile-csv", help="write row,intensity,gradient to this CSV")
    args = ap.parse_args()

    frame = cv2.imread(args.image)
    if frame is None:
        raise SystemExit(f"cannot read {args.image}")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if args.roi:
        x, y, w, h = args.roi
    else:
        x, y, w, h = 0, 0, gray.shape[1], gray.shape[0]
    roi = gray[y:y + h, x:x + w]
    if roi.size == 0:
        raise SystemExit("ROI is empty - check --roi against the image size")

    row, confidence, profile, gradient = detect_boundary_row(roi, args.smooth)
    boundary_y = y + row
    sharpness = dct_sharpness(roi)

    print(f"image           {args.image}  ({frame.shape[1]}x{frame.shape[0]})")
    print(f"roi             x={x} y={y} w={w} h={h}")
    print(f"boundary row    {row} in ROI  ->  y={boundary_y} in frame")
    print(f"confidence      {confidence:.2f}   (|gradient| at the detected row)")
    print(f"dct sharpness   {sharpness:.4f}   (higher = sharper/clearer; ~0 = turbid)")

    if args.calib:
        from volume_model import CalibrationTable, pixel_row_to_height_mm
        if args.row_zero is None or args.mm_per_px is None:
            raise SystemExit("--calib needs --row-zero and --mm-per-px")
        cal = CalibrationTable.load(args.calib)
        height_mm = pixel_row_to_height_mm(boundary_y, args.row_zero, args.mm_per_px)
        vol = cal.volume_ml(height_mm)
        flag = "  (OUT OF CALIBRATED RANGE)" if cal.out_of_range(height_mm) else ""
        print(f"height          {height_mm:.2f} mm above the zero mark")
        print(f"volume below    {vol:.2f} mL{flag}")

    if args.profile_csv:
        with open(args.profile_csv, "w") as fh:
            fh.write("row,intensity,gradient\n")
            for i, (p, g) in enumerate(zip(profile, gradient)):
                fh.write(f"{i},{p:.4f},{g:.4f}\n")
        print(f"wrote           {args.profile_csv}")

    out = args.out or f"{os.path.splitext(args.image)[0]}_annotated.png"
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 1)
    cv2.line(frame, (x, boundary_y), (x + w, boundary_y), (0, 0, 255), 2)
    cv2.putText(frame, f"y={boundary_y} conf={confidence:.1f} sharp={sharpness:.3f}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imwrite(out, frame)
    print(f"wrote           {out}")


if __name__ == "__main__":
    main()
