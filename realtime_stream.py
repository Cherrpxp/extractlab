"""Live MJPEG stream of the separatory funnel with the detected liquid-liquid
interface drawn on top, plus an on-page panel that explains what the system is
doing, what to do next, and what it is working toward.

Runs on the Raspberry Pi 5 (needs picamera2 + the camera hardware).
View it in a browser at http://<pi-ip>:5000 while on the same WiFi network.

    python3 realtime_stream.py

If the page won't load, check CLAUDE.md's networking note: a VPN on the
viewing PC can block access to devices on the dorm WiFi LAN.
"""

import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify
from picamera2 import Picamera2

from boundary_detection import detect_boundary

# --- Camera framing --------------------------------------------------------
# (x, y, w, h) in pixel coordinates of the full 1280x720 frame, cropped to
# just the funnel column with margin above/below the expected interface.
# THESE ARE PLACEHOLDERS — set them to match your actual camera framing
# (capture a still, read pixel coordinates off it, crop to just the pear
# body: exclude the neck at the top and the stopcock/stem at the bottom).
ROI = (560, 80, 160, 560)
_ROI_IS_PLACEHOLDER = ROI == (560, 80, 160, 560)

# Row-profile smoothing window (pixels). Larger = smoother but coarser.
SMOOTH_KERNEL = 5

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
EXPOSURE_US = int(os.environ.get("EXPOSURE_US", 120000))
GAIN = float(os.environ.get("GAIN", 8.0))
# White balance (red gain, blue gain), read off AWB after it settled under
# the current room lighting. Re-run the AWB calibration if the lighting changes.
WB_RED = float(os.environ.get("WB_RED", 1.97))
WB_BLUE = float(os.environ.get("WB_BLUE", 1.73))

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
    "confidence": 0.0,
    "found": False,
    "roi_brightness": 0.0,
    "fps": 0.0,
    "hint": "starting up",
}


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


def _capture_loop():
    """Single producer: grab frames, run detection, publish JPEG + status."""
    global _latest_jpeg
    x, y, w, h = ROI
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
        roi_gray = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
        roi_brightness = float(roi_gray.mean())

        now = time.monotonic()
        dt = now - prev
        prev = now
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 1)
        if found:
            cv2.line(frame, (x, boundary_y), (x + w, boundary_y), (0, 0, 255), 2)
        label = f"y={boundary_y} conf={confidence:.1f}" + ("" if found else "  (no boundary)")
        cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0) if found else (0, 165, 255), 2)

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            _latest_jpeg = buf.tobytes()

        with _status_lock:
            _status.update(
                boundary_y=int(boundary_y),
                confidence=round(confidence, 2),
                found=found,
                roi_brightness=round(roi_brightness, 1),
                fps=round(fps, 1),
                hint=_hint_for(found, confidence, roi_brightness),
            )


_latest_jpeg = b""
threading.Thread(target=_capture_loop, daemon=True).start()


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
      <p><span style="color:#ff5c5c">เส้นแดง</span> = ตำแหน่งรอยต่อที่ตรวจเจอ &nbsp;·&nbsp;
      <span style="color:#57d98a">กรอบเขียว</span> = ROI &nbsp;·&nbsp;
      <code>conf</code> = ความแรงของสัญญาณ (ต้อง ≥ เกณฑ์ถึงจะนับว่าเจอ)</p>
    </div>

    <div class="card" id="statusCard">
      <h2>สถานะสด</h2>
      <div class="kv"><span>สถานะ</span><span id="pill" class="pill wait">—</span></div>
      <div class="kv"><span>ตำแหน่ง y</span><b id="y">—</b></div>
      <div class="kv"><span>conf / เกณฑ์</span><b><span id="conf">—</span> / __THRESH__</b></div>
      <div class="kv"><span>ความสว่าง ROI</span><b id="bri">—</b> <span style="color:#8a93a6">/ 255</span></div>
      <div class="kv"><span>FPS</span><b id="fps">—</b></div>
      <div class="hint" id="hint">—</div>
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
async function tick() {
  try {
    const s = await (await fetch('/status')).json();
    const pill = document.getElementById('pill');
    pill.textContent = s.found ? 'เจอรอยต่อ' : 'กำลังหา…';
    pill.className = 'pill ' + (s.found ? 'ok' : 'wait');
    document.getElementById('y').textContent = s.boundary_y ?? '—';
    document.getElementById('conf').textContent = s.confidence?.toFixed(1) ?? '—';
    document.getElementById('bri').textContent = s.roi_brightness?.toFixed(0) ?? '—';
    document.getElementById('fps').textContent = s.fps?.toFixed(1) ?? '—';
    document.getElementById('hint').textContent = '👉 ' + s.hint;
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
        return jsonify(dict(_status))


@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
