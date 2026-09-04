"""Poll the running realtime_stream server and log the detected interface over
time -- for the P1 drain test: does the red line track the interface as the
lower layer is removed, and does confidence stay above threshold?

    python3 track_log.py drain1.csv           # Ctrl+C to stop
    python3 track_log.py drain1.csv --hz 5 --seconds 90

Writes CSV: elapsed_s, boundary_y, confidence, found, roi_brightness, fps
Prints a live line each sample and a summary on exit.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

URL = "http://127.0.0.1:5000/status"


def sample() -> dict:
    with urllib.request.urlopen(URL, timeout=3) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="output CSV path")
    ap.add_argument("--hz", type=float, default=4.0, help="samples per second (default 4)")
    ap.add_argument("--seconds", type=float, default=0, help="auto-stop after N s (0 = until Ctrl+C)")
    args = ap.parse_args()

    dt = 1.0 / args.hz
    rows: list[tuple] = []
    t0 = time.monotonic()
    print(f"logging {URL} -> {args.csv}   (Ctrl+C to stop)")
    print(f"{'t':>7} {'y':>5} {'conf':>6} {'found':>6} {'roi_bri':>8} {'fps':>5}")
    try:
        while True:
            t = time.monotonic() - t0
            try:
                s = sample()
            except Exception as e:  # server restart / hiccup - keep going
                print(f"{t:7.1f}  (no data: {e})")
                time.sleep(dt)
                continue
            row = (round(t, 2), s["boundary_y"], s["confidence"], int(s["found"]),
                   s["roi_brightness"], s["fps"])
            rows.append(row)
            print(f"{t:7.1f} {row[1]:5d} {row[2]:6.1f} {row[3]:6d} {row[4]:8.1f} {row[5]:5.1f}")
            if args.seconds and t >= args.seconds:
                break
            time.sleep(dt)
    except KeyboardInterrupt:
        print("\nstopped.")

    with open(args.csv, "w") as fh:
        fh.write("elapsed_s,boundary_y,confidence,found,roi_brightness,fps\n")
        for r in rows:
            fh.write(",".join(str(v) for v in r) + "\n")

    if rows:
        ys = [r[1] for r in rows]
        cs = [r[2] for r in rows]
        found_frac = sum(r[3] for r in rows) / len(rows)
        # largest single-step jump in y (a false re-lock shows up as a big spike)
        jumps = [abs(b - a) for a, b in zip(ys, ys[1:])] or [0]
        print(f"\nsummary ({len(rows)} samples, {rows[-1][0]:.0f}s)")
        print(f"  boundary_y : {min(ys)} .. {max(ys)}   (moved {max(ys) - min(ys)} px)")
        print(f"  confidence : min {min(cs):.1f}  mean {sum(cs)/len(cs):.1f}  max {max(cs):.1f}")
        print(f"  found      : {found_frac*100:.0f}% of samples above threshold")
        print(f"  biggest y jump between samples : {max(jumps)} px "
              f"({'looks smooth' if max(jumps) < 25 else 'CHECK - possible false re-lock'})")
    print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
