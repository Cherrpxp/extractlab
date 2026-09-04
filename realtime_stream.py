"""Live MJPEG stream of the separatory funnel with the detected liquid-liquid
interface drawn on top, plus an on-page panel that explains what the system is
doing, what to do next, and what it is working toward.

Runs on the Raspberry Pi 5 (needs picamera2 + the camera hardware).
View it in a browser at http://<pi-ip>:5000 while on the same WiFi network.

    python3 realtime_stream.py

If the page won't load, check CLAUDE.md's networking note: a VPN on the
viewing PC can block access to devices on the dorm WiFi LAN.
"""

import csv
import datetime
import os
import re
import threading
import time
from collections import deque

import cv2
import numpy as np
from flask import Flask, Response, jsonify, send_from_directory
from picamera2 import Picamera2

from boundary_detection import detect_boundary

# --- Camera framing --------------------------------------------------------
# (x, y, w, h) in pixel coordinates of the full 1280x720 frame, cropped to
# the LIQUID COLUMN only — inside the vessel walls, bracketing where the
# liquid-liquid interface sits and will travel while draining. Exclude the
# top air/liquid surface and the vessel base. Override without editing:
#   ROI_X=555 ROI_Y=370 ROI_W=175 ROI_H=290 python3 realtime_stream.py
# Current values: beaker on a black background, lab bench (2026-09-04).
ROI = (
    int(os.environ.get("ROI_X", 555)),
    int(os.environ.get("ROI_Y", 370)),
    int(os.environ.get("ROI_W", 175)),
    int(os.environ.get("ROI_H", 290)),
)
_ROI_IS_PLACEHOLDER = False

# Row-profile smoothing window (pixels). Larger = smoother but coarser.
SMOOTH_KERNEL = 5

# Temporal filter for the per-frame boundary_y. The raw detection jumps ±50 px
# (and occasionally ~200 px) when it briefly locks onto a competing edge. We
# publish a smoothed value: reject any raw sample that leaps more than
# TRACK_MAX_STEP px from the current smoothed position, and report the median
# of the last TRACK_WIN accepted samples. If raw stays far away for
# TRACK_RESEED_AFTER frames the interface really did move fast (or was
# re-acquired) — re-seed on it.
TRACK_WIN = 9
TRACK_MAX_STEP = 30
TRACK_RESEED_AFTER = 15

# Below this |gradient| the frame is treated as "no boundary found" (e.g.
# camera not settled yet, or the interface signal is too weak without dye).
# Tune this from real footage — watch the conf value on the page.
CONFIDENCE_THRESHOLD = 3.0

FRAME_SIZE = (1280, 720)
JPEG_QUALITY = 80

# Manual exposure/white balance — keep AE/AWB off so brightness and colour
# are stable and comparable frame-to-frame (auto would fight the detector).
# Override without editing the file, e.g.:
#   EXPOSURE_US=120000 GAIN=8 WB_RED=1.7 WB_BLUE=2.1 python3 realtime_stream.py
# Higher ExposureTime = brighter but more motion blur and lower FPS. Higher
# AnalogueGain = brighter but noisier (gain > ~8 gets visibly grainy). In a
# dim room raise exposure first, then gain — and really, add a light: no gain
# setting recovers a clean signal from a near-black scene.
# Current values: lab bench, beaker on black background (2026-09-04) — ROI mean
# ~150/255. GAIN 8 is a bit grainy; trade toward EXPOSURE_US if the bench is
# stable enough for the lower frame rate.
EXPOSURE_US = int(os.environ.get("EXPOSURE_US", 25000))
GAIN = float(os.environ.get("GAIN", 8.0))
# White balance (red gain, blue gain), read off AWB under the current lighting.
# Re-run the AWB calibration if the lighting changes.
WB_RED = float(os.environ.get("WB_RED", 2.14))
WB_BLUE = float(os.environ.get("WB_BLUE", 1.76))

app = Flask(__name__)

picam2 = Picamera2()
_config = picam2.create_video_configuration(main={"size": FRAME_SIZE, "format": "RGB888"})
picam2.configure(_config)
picam2.set_controls({
    "AeEnable": False,
    "AwbEnable": False,
    "ColourGains": (WB_RED, WB_BLUE),
    # Without a wide FrameDurationLimits, the video pipeline pins the frame
    # rate (~30 FPS) and silently clamps ExposureTime to ~33 ms, so long
    # exposures set below would be ignored. Allow up to 1 s per frame; the
    # actual rate then follows ExposureTime (250 ms exposure -> ~4 FPS).
    "FrameDurationLimits": (100, 1_000_000),
    "ExposureTime": EXPOSURE_US,
    "AnalogueGain": GAIN,
})
picam2.start()
time.sleep(1)  # let exposure/gain settle before streaming

# Latest detection result, shared with the /status endpoint. Updated once per
# processed frame by the single capture loop.
_status_lock = threading.Lock()
_status = {
    "boundary_y": None,
    "boundary_y_smooth": None,
    "confidence": 0.0,
    "found": False,
    "roi_brightness": 0.0,
    "fps": 0.0,
    "hint": "starting up",
}


class _Tracker:
    """Median filter with jump rejection for the boundary row. See the
    TRACK_* constants above."""

    def __init__(self):
        self._hist: deque[int] = deque(maxlen=TRACK_WIN)
        self._smooth: float | None = None
        self._rejects = 0

    def update(self, raw: int, found: bool) -> float | None:
        if not found:
            return self._smooth  # hold last during a dropout
        if self._smooth is None or abs(raw - self._smooth) <= TRACK_MAX_STEP \
                or self._rejects >= TRACK_RESEED_AFTER:
            if self._smooth is not None and abs(raw - self._smooth) > TRACK_MAX_STEP:
                self._hist.clear()  # re-seeding after a real fast move
            self._hist.append(raw)
            self._smooth = float(np.median(self._hist))
            self._rejects = 0
        else:
            self._rejects += 1
        return self._smooth

# In-browser recording: the ⏺ button on the page starts/stops a CSV that gets
# one row per processed frame. Used for the drain test — run it while pumping
# the lower layer out, then read the summary the ⏹ button prints.
RECORD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "records")
_rec_lock = threading.Lock()
_rec = {"on": False, "path": None, "fh": None, "writer": None, "n": 0, "t0": 0.0}


def _hint_for(found: bool, confidence: float, roi_brightness: float) -> str:
    """One-line, situation-aware guidance shown live on the page."""
    if roi_brightness < 15:
        return "ROI มืดมาก — เล็งกล้องให้กรวยอยู่ในกรอบเขียว หรือเพิ่ม GAIN/EXPOSURE_US"
    if roi_brightness > 245:
        return "ROI สว่างจนล้น — ลด EXPOSURE_US/GAIN หรือกันแสงหน้าต่างที่ส่องตรงเข้ากรวย"
    if not found:
        return ("ยังไม่เจอรอยต่อ — เติมน้ำ+น้ำมันลงกรวย, เอากระดาษขาวบังฉากหลัง, "
                "แล้วหด ROI ให้เหลือแค่ตัวป่องกลางกรวย")
    return "เจอสัญญาณแล้ว — เช็คว่าเส้นแดงตรงกับรอยต่อน้ำ/น้ำมันจริงไหม แล้วจดค่า conf"


_frame_count = 0  # advanced every processed frame; watched for camera stalls


def _watchdog():
    """picamera2's capture_array() can block forever if the camera is knocked
    or the CSI link glitches — the Flask server keeps answering with a stale
    frame and no error. If no frame has been processed for ~15 s, exit hard so
    a supervisor (run_stream.sh / systemd) can restart with a fresh camera."""
    last_seen, last_change = _frame_count, time.monotonic()
    while True:
        time.sleep(5)
        if _frame_count != last_seen:
            last_seen, last_change = _frame_count, time.monotonic()
        elif time.monotonic() - last_change > 15:
            print("watchdog: no frames for 15s — camera stalled, exiting for restart",
                  flush=True)
            os._exit(1)


def _capture_loop():
    """Single producer: grab frames, run detection, publish JPEG + status."""
    global _latest_jpeg, _frame_count
    x, y, w, h = ROI
    tracker = _Tracker()
    prev = time.monotonic()
    fps = 0.0
    while True:
        # picamera2's "RGB888" format delivers the numpy array in BGR channel
        # order already (libcamera naming quirk) — exactly what OpenCV wants
        # (imencode, drawing, BGR2GRAY below). Do NOT colour-convert here:
        # an RGB<->BGR swap turns the yellow organic layer blue.
        frame = picam2.capture_array()

        boundary_y, confidence = detect_boundary(frame, roi=ROI, smooth_kernel=SMOOTH_KERNEL)
        found = bool(confidence >= CONFIDENCE_THRESHOLD)
        y_smooth = tracker.update(int(boundary_y), found)
        roi_gray = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
        roi_brightness = float(roi_gray.mean())

        now = time.monotonic()
        dt = now - prev
        prev = now
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 1)
        if found:
            cv2.line(frame, (x, boundary_y), (x + w, boundary_y), (0, 0, 255), 1)  # raw, thin
        if y_smooth is not None:
            ys = int(round(y_smooth))
            cv2.line(frame, (x, ys), (x + w, ys), (0, 255, 255), 2)  # smoothed, thick yellow
        label = (f"y={boundary_y} (smooth {int(round(y_smooth))})" if y_smooth is not None
                 else f"y={boundary_y}") + f" conf={confidence:.1f}" + ("" if found else "  (no boundary)")
        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if found else (0, 165, 255), 2)

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            _latest_jpeg = buf.tobytes()
        _frame_count += 1

        with _status_lock:
            _status.update(
                boundary_y=int(boundary_y),
                boundary_y_smooth=None if y_smooth is None else int(round(y_smooth)),
                confidence=round(confidence, 2),
                found=found,
                roi_brightness=round(roi_brightness, 1),
                fps=round(fps, 1),
                hint=_hint_for(found, confidence, roi_brightness),
            )

        with _rec_lock:
            if _rec["on"]:
                _rec["writer"].writerow([
                    round(time.monotonic() - _rec["t0"], 2), int(boundary_y),
                    "" if y_smooth is None else int(round(y_smooth)),
                    round(confidence, 3), int(found), round(roi_brightness, 1),
                    round(fps, 1),
                ])
                _rec["n"] += 1
                _rec["fh"].flush()


_latest_jpeg = b""
threading.Thread(target=_capture_loop, daemon=True).start()
threading.Thread(target=_watchdog, daemon=True).start()


def gen_frames():
    while True:
        if _latest_jpeg:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + _latest_jpeg + b"\r\n")
        time.sleep(0.05)


PAGE = """<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLE boundary — live</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #0f1115; color: #e6e6e6;
         font: 14px/1.55 system-ui, -apple-system, "Noto Sans Thai", sans-serif; }
  .wrap { display: flex; flex-wrap: wrap; gap: 16px; padding: 16px; }
  .video { flex: 1 1 620px; min-width: 320px; }
  .video img { width: 100%; display: block; border-radius: 8px; background: #000; }
  .panel { flex: 1 1 340px; min-width: 300px; max-width: 460px; }
  .card { background: #171a21; border: 1px solid #262b36; border-radius: 8px;
          padding: 14px 16px; margin-bottom: 14px; }
  h1 { font-size: 16px; margin: 0 0 4px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
       color: #8a93a6; margin: 0 0 10px; }
  .sub { color: #8a93a6; margin: 0 0 14px; }
  .kv { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0;
        border-bottom: 1px dashed #262b36; }
  .kv:last-child { border-bottom: 0; }
  .kv b { font-variant-numeric: tabular-nums; }
  .pill { display: inline-block; padding: 2px 10px; border-radius: 999px;
          font-weight: 600; font-size: 13px; }
  .ok { background: #12351f; color: #57d98a; }
  .wait { background: #3a2a12; color: #f0b085; }
  .hint { margin-top: 10px; padding: 10px 12px; background: #10131a;
          border-left: 3px solid #f0b085; border-radius: 4px; }
  ol, ul { margin: 6px 0 0; padding-left: 20px; }
  li { margin: 5px 0; }
  li.done { color: #6d7688; text-decoration: line-through; }
  .warn { background: #3a1c1c; border-color: #6b2b2b; color: #f0a3a3; }
  code { background: #262b36; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
  button { font: inherit; padding: 9px 18px; border-radius: 6px; border: 1px solid #3a4150;
           background: #1e3a2a; color: #e6e6e6; cursor: pointer; }
  button:hover { filter: brightness(1.18); }
  button.rec { background: #5a1e1e; }
</style></head><body>
<div class="wrap">
  <div class="video"><img src="/video_feed" alt="live stream"></div>
  <div class="panel">

    <div class="card">
      <h1>ระบบตรวจจับรอยต่อของเหลว (Water–Cyclohexane LLE)</h1>
      <p class="sub">คลาสสิก computer vision — ไม่ใช้โมเดล deep learning</p>
      <h2>กำลังทำอะไรอยู่</h2>
      <p>กล้องจับภาพกรวยแยกเฉพาะในกรอบเขียว (ROI) แล้วหาค่าความสว่างเฉลี่ยของ
      แต่ละแถวพิกเซล มองหาแถวที่ความสว่าง<b>เปลี่ยนแรงที่สุด</b> = ตำแหน่งรอยต่อ
      ระหว่างชั้นน้ำกับชั้นน้ำมัน</p>
      <p><span style="color:#ffd23f">เส้นเหลือง</span> = ค่าที่กรองแล้ว (ใช้อันนี้) &nbsp;·&nbsp;
      <span style="color:#ff5c5c">เส้นแดงบาง</span> = ค่าดิบรายเฟรม &nbsp;·&nbsp;
      <span style="color:#57d98a">กรอบเขียว</span> = ROI &nbsp;·&nbsp;
      <code>conf</code> ต้อง ≥ เกณฑ์ถึงจะนับว่าเจอ</p>
    </div>

    <div class="card" id="statusCard">
      <h2>สถานะสด</h2>
      <div class="kv"><span>สถานะ</span><span id="pill" class="pill wait">—</span></div>
      <div class="kv"><span>y (กรอง / ดิบ)</span><b><span id="ys">—</span> <span style="color:#8a93a6">/ <span id="y">—</span></span></b></div>
      <div class="kv"><span>conf / เกณฑ์</span><b><span id="conf">—</span> / __THRESH__</b></div>
      <div class="kv"><span>ความสว่าง ROI</span><b id="bri">—</b> <span style="color:#8a93a6">/ 255</span></div>
      <div class="kv"><span>FPS</span><b id="fps">—</b></div>
      <div class="hint" id="hint">—</div>
    </div>

    <div class="card">
      <h2>บันทึกผล (drain test)</h2>
      <button id="recBtn">⏺ เริ่มบันทึก</button>
      <p class="sub" style="margin:12px 0 0" id="recInfo">
        กดเริ่มก่อนดูดน้ำออก · กดหยุดเมื่อเสร็จ
      </p>
      <h2 style="margin:16px 0 8px">ไฟล์ที่บันทึกไว้</h2>
      <div id="recFiles" class="sub">—</div>
    </div>

    <div class="card __ROIWARN__" id="roiCard">
      <h2>ต้องทำอะไรต่อ</h2>
      <ol>
        <li>เติม <b>น้ำ + น้ำมันพืช</b> ลงกรวย ให้เห็นรอยต่อชัดด้วยตาก่อน</li>
        <li>เอา <b>กระดาษขาว</b> บังหลังกรวยโดยตรง ลดฉากหลังรก (ม่าน/ถุง/เชือก)</li>
        <li>ปรับ <code>ROI</code> ใน <code>realtime_stream.py</code> ให้เหลือแค่
            <b>ตัวป่องกลางกรวย</b> — ตัดคอกรวยบนกับก้าน+stopcock ล่างออก</li>
        <li>ดูว่าเส้นแดงเกาะรอยต่อจริงไหม จดค่า <code>conf</code> ตอน<b>มี</b>และ<b>ไม่มี</b>รอยต่อ</li>
        <li>จูน <code>CONFIDENCE_THRESHOLD</code> จากค่าที่จดได้</li>
      </ol>
      <p class="sub" style="margin:10px 0 0" id="roiNote"></p>
    </div>

    <div class="card">
      <h2>กำลังจะไปสู่อะไร</h2>
      <ul>
        <li><b>ตอนนี้:</b> พิสูจน์ว่าสัญญาณความสว่างธรรมชาติพอจับรอยต่อของเหลวใส
            2 ชนิดได้ โดยไม่ต้องใช้สารเรืองแสง</li>
        <li>Calibrate ตารางความสูง → ปริมาตร ด้วยน้ำจริง</li>
        <li>ต่อปั๊มผ่านไฟ 12V + relay อย่างปลอดภัย (ห้ามต่อ GPIO ตรงเข้าปั๊ม)</li>
        <li>เชื่อมโค้ดตรวจจับ + ควบคุมปั๊ม → ระบบแยกของเหลวอัตโนมัติครบวงจร</li>
        <li>ทดสอบซ้ำ 10 รอบ เก็บ RMSE → เปลี่ยนไปใช้น้ำ–ไซโคลเฮกเซนจริง</li>
      </ul>
    </div>

  </div>
</div>
<script>
const recBtn = document.getElementById('recBtn');
const recInfo = document.getElementById('recInfo');
const recFiles = document.getElementById('recFiles');
let recOn = false;

async function loadFiles() {
  try {
    const list = await (await fetch('/records')).json();
    recFiles.innerHTML = list.length
      ? list.map(f =>
          `<div style="padding:3px 0;border-bottom:1px dashed #262b36">`
          + `<a href="/records/${f.name}" target="_blank" style="color:#7db5ff">${f.name}</a>`
          + ` &nbsp;<span style="color:#8a93a6">${f.rows} แถว · ${f.kb} KB · ${f.mtime}</span></div>`
        ).join('')
      : '(ยังไม่มีไฟล์)';
  } catch (e) { recFiles.textContent = 'โหลดรายการไม่ได้'; }
}

recBtn.onclick = async () => {
  recBtn.disabled = true;
  try {
    if (!recOn) {
      const r = await (await fetch('/record/start', {method: 'POST'})).json();
      recInfo.textContent = r.ok ? 'กำลังบันทึก… ' + r.name : ('เริ่มไม่ได้: ' + r.error);
    } else {
      const r = await (await fetch('/record/stop', {method: 'POST'})).json();
      const s = r.summary || {};
      const warn = s.max_jump > 25 ? `  ⚠️ smooth ยังกระโดด ${s.max_jump}px` : '  ✓ เรียบ';
      recInfo.textContent = r.ok
        ? `${r.name} · ${r.n} samples · ${r.seconds}s · y ${s.y_min}–${s.y_max} `
          + `(เลื่อน ${s.y_span}px) · conf ${s.conf_min}–${s.conf_max} · พบ ${s.found_pct}% · `
          + `jump raw ${s.max_jump_raw}px → smooth ${s.max_jump}px${warn}`
        : ('หยุดไม่ได้: ' + r.error);
      loadFiles();
    }
  } catch (e) { recInfo.textContent = 'error: ' + e; }
  recBtn.disabled = false;
};
loadFiles();

async function tick() {
  try {
    const s = await (await fetch('/status')).json();
    const pill = document.getElementById('pill');
    pill.textContent = s.found ? 'เจอรอยต่อ' : 'กำลังหา…';
    pill.className = 'pill ' + (s.found ? 'ok' : 'wait');
    document.getElementById('y').textContent = s.boundary_y ?? '—';
    document.getElementById('ys').textContent = s.boundary_y_smooth ?? '—';
    document.getElementById('conf').textContent = s.confidence?.toFixed(1) ?? '—';
    document.getElementById('bri').textContent = s.roi_brightness?.toFixed(0) ?? '—';
    document.getElementById('fps').textContent = s.fps?.toFixed(1) ?? '—';
    document.getElementById('hint').textContent = '👉 ' + s.hint;
    recOn = s.rec_on;
    recBtn.textContent = recOn ? `⏹ หยุด  (${s.rec_seconds}s · ${s.rec_n})` : '⏺ เริ่มบันทึก';
    recBtn.className = recOn ? 'rec' : '';
  } catch (e) { /* keep last values on a hiccup */ }
}
setInterval(tick, 1000); tick();
</script>
</body></html>"""

PAGE = (PAGE
        .replace("__THRESH__", f"{CONFIDENCE_THRESHOLD:.1f}")
        .replace("__ROIWARN__", "warn" if _ROI_IS_PLACEHOLDER else ""))


@app.route("/")
def index():
    note = ("⚠️ ROI ยังเป็นค่า placeholder — กรอบเขียวยังไม่ตรงกับกรวยจริง"
            if _ROI_IS_PLACEHOLDER else f"ROI ปัจจุบัน = {ROI}")
    return PAGE.replace('id="roiNote"></p>', f'id="roiNote">{note}</p>')


@app.route("/status")
def status():
    with _status_lock:
        d = dict(_status)
    with _rec_lock:
        d["rec_on"] = _rec["on"]
        d["rec_n"] = _rec["n"]
        d["rec_seconds"] = round(time.monotonic() - _rec["t0"], 1) if _rec["on"] else 0
        d["rec_name"] = os.path.basename(_rec["path"]) if _rec["path"] else None
    return jsonify(d)


@app.route("/record/start", methods=["GET", "POST"])
def record_start():
    with _rec_lock:
        if _rec["on"]:
            return jsonify(ok=False, error="already recording", name=os.path.basename(_rec["path"]))
        os.makedirs(RECORD_DIR, exist_ok=True)
        path = os.path.join(RECORD_DIR, "rec_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv")
        fh = open(path, "w", newline="")
        wr = csv.writer(fh)
        wr.writerow(["elapsed_s", "boundary_y", "boundary_y_smooth",
                     "confidence", "found", "roi_brightness", "fps"])
        _rec.update(on=True, path=path, fh=fh, writer=wr, n=0, t0=time.monotonic())
    return jsonify(ok=True, name=os.path.basename(path))


@app.route("/record/stop", methods=["GET", "POST"])
def record_stop():
    with _rec_lock:
        if not _rec["on"]:
            return jsonify(ok=False, error="not recording")
        _rec["fh"].flush()
        _rec["fh"].close()
        path, n = _rec["path"], _rec["n"]
        seconds = round(time.monotonic() - _rec["t0"], 1)
        _rec.update(on=False, fh=None, writer=None)

    summary = {}
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    if rows:
        raw = [int(r["boundary_y"]) for r in rows]
        sm = [int(r["boundary_y_smooth"]) for r in rows if r["boundary_y_smooth"] not in ("", None)]
        cs = [float(r["confidence"]) for r in rows]
        fs = [int(r["found"]) for r in rows]
        rjump = max((abs(b - a) for a, b in zip(raw, raw[1:])), default=0)
        sjump = max((abs(b - a) for a, b in zip(sm, sm[1:])), default=0)
        series = sm or raw
        summary = {
            "y_min": min(series), "y_max": max(series), "y_span": max(series) - min(series),
            "conf_min": round(min(cs), 1), "conf_max": round(max(cs), 1),
            "found_pct": round(100 * sum(fs) / len(fs)),
            "max_jump": sjump, "max_jump_raw": rjump,
        }
    return jsonify(ok=True, name=os.path.basename(path), n=n, seconds=seconds, summary=summary)


_REC_NAME_RE = re.compile(r"^rec_\d{8}_\d{6}\.csv$")


@app.route("/records")
def records_list():
    out = []
    if os.path.isdir(RECORD_DIR):
        for name in sorted(os.listdir(RECORD_DIR), reverse=True):
            if not _REC_NAME_RE.match(name):
                continue
            p = os.path.join(RECORD_DIR, name)
            with open(p) as fh:
                n = max(sum(1 for _ in fh) - 1, 0)
            st = os.stat(p)
            out.append({"name": name, "rows": n, "kb": round(st.st_size / 1024, 1),
                        "mtime": time.strftime("%m-%d %H:%M", time.localtime(st.st_mtime))})
    return jsonify(out)


@app.route("/records/<name>")
def records_get(name):
    if not _REC_NAME_RE.match(name):
        return "bad name", 400
    return send_from_directory(RECORD_DIR, name, mimetype="text/csv",
                               as_attachment=False)


@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
