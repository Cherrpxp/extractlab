#!/usr/bin/env bash
# Supervisor for realtime_stream.py: restarts it whenever it exits — including
# the hard exit the in-process watchdog does when the camera stalls (a knock to
# the camera / CSI glitch makes picamera2's capture_array() block forever).
#
#   ./run_stream.sh            # foreground, Ctrl+C to stop for good
#   nohup ./run_stream.sh >run_stream.log 2>&1 &
#
# ROI / exposure overrides still work: pass them in the environment before this.
cd "$(dirname "$0")" || exit 1
trap 'echo "run_stream: stopping"; exit 0' INT TERM
while true; do
    echo "run_stream: starting realtime_stream.py at $(date '+%H:%M:%S')"
    python3 realtime_stream.py
    code=$?
    echo "run_stream: realtime_stream.py exited ($code) — restarting in 2s"
    sleep 2
done
