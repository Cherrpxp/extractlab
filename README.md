# extractlab — ระบบแยกน้ำ–ไซโคลเฮกเซนอัตโนมัติ (Water–Cyclohexane LLE)

ตรวจจับตำแหน่งรอยต่อระหว่างของเหลวสองเฟส (ทั้งคู่ใสไม่มีสี) ด้วยกล้อง แล้วสั่งปั๊มแยกของเหลวออกอัตโนมัติ
ใช้เทคนิค **classical computer vision** ล้วน ไม่ต้องฝึกโมเดล

แนวคิดดัดแปลงจากงานวิจัย **Chem-SDI** (Fu et al., *Microchemical Journal* 227, 2026) โดยตัดส่วน deep learning
และฮาร์ดแวร์เฉพาะออก เหลือเฉพาะ DCT turbidity monitoring และ row-wise gradient boundary detection

---

## สถานะโดยย่อ

| ทำแล้ว | กำลังทำ | ยังไม่ได้ทำ |
|---|---|---|
| SSH เข้า Pi, ตั้งกล้อง manual exposure/WB | ทดสอบ boundary detection กับรูปน้ำ–น้ำมันจริง | calibrate ความสูง→ปริมาตรด้วยน้ำจริง |
| เขียน algorithm หลัก 3 ตัว (`boundary_detection`, `turbidity_dct`, `volume_model`) + `synthetic_data` + `demo` ผ่าน synthetic | | ต่อปั๊มผ่าน 12V + relay อย่างปลอดภัย |
| เขียน `realtime_stream.py` (live MJPEG + แผงสถานะ) | | เชื่อม vision + control ทดสอบครบวงจร, เก็บ RMSE 10 รอบ |

> ทุกโมดูลทดสอบกับ synthetic data ผ่านแล้ว แต่ **ยังไม่เคยทดสอบกับของเหลวจริงจนสำเร็จ**

---

## ฮาร์ดแวร์

| อุปกรณ์ | สเปก | หมายเหตุ |
|---|---|---|
| Raspberry Pi 5 | ตัวประมวลผลหลัก บอร์ดเดียว | `ssh somdui@192.168.100.242` |
| กล้อง | Camera Module 3 (imx708) ผ่าน `picamera2` | ตั้ง manual exposure/AWB แล้ว |
| กรวยแยก | ทรงลูกแพร์ 125 mL, Ø จุดอ้วนสุด ≈ 6.7 cm | ต้อง calibrate ปริมาตรด้วยน้ำจริง ไม่ใช้สูตรเรขาคณิตล้วน |
| ปั๊ม | MINTLLAB DP-DIY, 12V, 5W (≈0.42A) | ท่อ intake จมคงที่ก้นขวด (ดูดชั้นล่าง) |

### ⚠️ ความปลอดภัยเรื่องปั๊ม

**ห้ามต่อสายไฟปั๊มเข้าขา GPIO / 5V / GND บนบอร์ด Pi โดยตรงเด็ดขาด** — ปั๊มกิน 12V / 0.42A
แต่ GPIO จ่ายปลอดภัยไม่เกิน ~16 mA เคยต่อผิดมาแล้วครั้งหนึ่ง (ยังไม่ยืนยันว่า Pi เสียหายไหม —
เช็ก `vcgencmd get_throttled`)

**วิธีที่ถูก (ยังไม่ได้ทำ):** แหล่งจ่าย 12V แยก → relay module (5V logic) → ปั๊ม โดย GPIO สั่งแค่เปิด–ปิด relay

### เครือข่าย

Pi อยู่ใน WiFi หอพัก (`192.168.100.0/24`) ถ้า SSH หรือเว็บสตรีมเข้าไม่ได้ **ให้ปิด VPN บนคอมก่อน** —
VPN client บล็อกการเข้าถึงอุปกรณ์ใน LAN เดียวกัน

---

## การติดตั้ง

รันบน Raspberry Pi 5 `picamera2` มาจาก apt ไม่ใช่ pip:

```bash
sudo apt install -y python3-picamera2
python3 -m venv --system-site-packages .venv   # ให้ venv เห็น picamera2
source .venv/bin/activate
pip install -r requirements.txt                 # flask, opencv-python-headless, numpy
```

`boundary_detection.py` ใช้แค่ `cv2` + `numpy` รันบนเครื่องอื่นเพื่อทดสอบ algorithm ได้โดยไม่ต้องมี Pi/กล้อง

---

## โครงสร้างโค้ด

| ไฟล์ | หน้าที่ |
|---|---|
| `boundary_detection.py` | หาตำแหน่งรอยต่อจาก row-wise pixel gradient — รับ numpy/OpenCV array ล้วน ไม่มี camera I/O |
| `turbidity_dct.py` | `dct_sharpness()` วัดความคมของภาพจากพลังงาน DCT ความถี่สูง + `TurbidityMonitor` ติดตามข้ามเฟรม ตัดสิน warming_up / turbid / clearing / clear (settled) ด้วย sliding-window slope |
| `volume_model.py` | `FrustumModel` (สูตรกรวย ใช้ได้แค่ช่วงกรวยแคบล่าง) + `CalibrationTable` (interpolate จากคู่ ความสูง–ปริมาตร ที่วัดด้วยน้ำจริง, save/load JSON, มี inverse `height_mm(volume)` ไว้คำนวณจุดสั่งหยุดปั๊ม) |
| `synthetic_data.py` | สร้างเฟรม/ลำดับการไขออกปลอม (รอยต่อเลื่อนลง + อิมัลชันค่อยๆ ใส) ไว้ทดสอบ pipeline ก่อนมีข้อมูลจริง |
| `demo.py` | รวม 4 โมดูลข้างบน รันกับ synthetic draining sequence พิมพ์ตารางผลต่อเฟรม + สรุป RMSE (เป็น smoke test ในตัว) |
| `analyze_real_photo.py` | CLI รัน boundary detection + `dct_sharpness` กับรูปจริง 1 ภาพ (รองรับ `--roi`), เขียนภาพ annotate + `--profile-csv` ไว้ tune threshold, `--calib` เพื่อแปลงเป็นปริมาตร |
| `realtime_stream.py` | Live MJPEG stream + แผงสถานะบนหน้าเว็บ `http://<pi-ip>:5000` (ต้องมี `picamera2` + กล้อง) |
| `requirements.txt` | dependencies + วิธีติดตั้ง picamera2 |

รันสคริปต์ตรงๆ ได้ทุกไฟล์ (`python3 demo.py`, `python3 turbidity_dct.py`, ฯลฯ) เป็นการทดสอบกับ synthetic data
ทุกโมดูล **ผ่าน synthetic แล้ว** แต่ **ยังไม่เคยทดสอบกับของเหลวจริงจนสำเร็จ**

---

## การใช้งาน

### Live stream บน Pi

```bash
python3 realtime_stream.py
# เปิดเบราว์เซอร์ไปที่ http://<pi-ip>:5000
```

ต้องปรับค่าใน `realtime_stream.py` ให้ตรงกับกล้องจริงก่อน:

- `ROI = (x, y, w, h)` — crop box ครอบเฉพาะคอลัมน์ของเหลว มี margin บน/ล่างรอยต่อ **(ตอนนี้เป็น placeholder)**
- `ExposureTime` — ปรับตามแสงจริง
- `CONFIDENCE_THRESHOLD` — ต่ำกว่านี้ถือว่า "ไม่พบรอยต่อ" ต้อง tune จากฟุตเทจจริง

### เรียก detector ในโค้ด

```python
import cv2
from boundary_detection import detect_boundary

frame = cv2.imread("vial.jpg")                       # BGR
boundary_y, confidence = detect_boundary(frame, roi=(560, 80, 160, 560))
# boundary_y = พิกัดพิกเซลแนวตั้งในเฟรมเต็ม, confidence = |gradient| ที่แถวนั้น
```

### ทดสอบ pipeline กับ synthetic + วิเคราะห์รูปจริง

```bash
python3 demo.py                                      # dry run ครบ pipeline, ต้องขึ้น RESULT: PASS
python3 analyze_real_photo.py photo.jpg --roi 610 235 110 150 --profile-csv prof.csv
```

---

## ความเสี่ยงที่ทราบอยู่แล้ว

1. **สัญญาณอาจอ่อนเกินไป** — ไม่ใช้สารเรืองแสง ต้องพิสูจน์ว่า row-wise gradient จับรอยต่อของเหลวใสสองชนิดได้จริง
2. **Pi 5 บอร์ดเดียวทำทั้ง vision + control** — ยังไม่ทดสอบ timing jitter ตอนควบคุมปั๊มแบบ real-time
3. **ตาราง calibration ผูกกับกรวยใบที่วัดเท่านั้น** — เปลี่ยนกรวยต้อง calibrate ใหม่
4. **ปั๊มยังไม่ได้ต่อไฟอย่างถูกต้อง** — ดูหัวข้อความปลอดภัยด้านบน

---

## เอกสารอ้างอิง

Fu, X. et al. "Chem-SDI: Segmentation, detection, and inference model for AI robotic chemists in
automated liquid-liquid extraction workflow." *Microchemical Journal* 227 (2026): 118844.
