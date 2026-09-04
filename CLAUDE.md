# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

ระบบแยกชั้นน้ำ–ไซโคลเฮกเซนอัตโนมัติ: ใช้กล้อง + classical computer vision ตรวจจับตำแหน่งรอยต่อ
ระหว่างของเหลวสองเฟส (ทั้งคู่ใสไม่มีสี) แล้วสั่งปั๊มดูดชั้นล่างออกจนถึงจุดที่ต้องการ รันบน Raspberry Pi 5 บอร์ดเดียว
ดัดแปลงจาก Chem-SDI (Fu et al., *Microchemical Journal* 227, 2026) โดยตัด deep learning และฮาร์ดแวร์เฉพาะออก

เอกสารเต็ม: [`PRD.md`](PRD.md) (ข้อกำหนด + เกณฑ์ผ่าน) · [`README.md`](README.md) (โครงสร้างโค้ด) · ผังลำดับงาน (artifact บน claude.ai)

---

## ฮาร์ดแวร์

| อุปกรณ์ | สเปก | หมายเหตุ |
|---|---|---|
| Raspberry Pi 5 | บอร์ดเดียว ทำทั้ง vision + control | `ssh somdui@<pi-ip>` — IP เปลี่ยนตามเครือข่าย (เคยเป็น 192.168.100.242, 172.20.10.3) |
| กล้อง | Camera Module 3 (เซนเซอร์ imx708) ผ่าน `picamera2` | ตั้ง manual exposure/AWB (ปิด auto) — ค่าขึ้นกับแสง ณ ที่นั้น |
| ภาชนะ | **บีกเกอร์ทรงกระบอก** (เปลี่ยนจากกรวยแยกลูกแพร์) | แยกชั้นด้วยท่อ intake ของปั๊มที่จมก้น ไม่มี stopcock · ทรงกระบอก → V = πr²h เป็นเส้นตรง |
| ปั๊ม | MINTLLAB DP-DIY, 12V, 5W (~0.42A) | **ยังไม่ได้ต่อ** — ต้องผ่าน 12V แยก + relay |

---

## รันอะไรยังไง

```bash
# บน Pi — สตรีมสด + หน้าเว็บ (http://<pi-ip>:5000)
cd ~/extractlab
nohup ./run_stream.sh > run_stream.log 2>&1 &     # supervisor: รีสตาร์ทเองถ้ากล้องค้าง
#   หยุดถาวร: kill <pid ของ run_stream.sh>  หรือ  pkill -f run_stream

# ปรับกล้อง/ROI โดยไม่แก้โค้ด — env var:
EXPOSURE_US=25000 GAIN=8 WB_RED=2.14 WB_BLUE=1.76 \
ROI_X=555 ROI_Y=370 ROI_W=175 ROI_H=290 python3 realtime_stream.py

# ทดสอบ — ไม่มี pytest/lint/build · แต่ละสคริปต์รัน __main__ เป็น self-check เอง
python3 demo.py            # integration smoke test — ต้องขึ้น RESULT: PASS (มี assert ในตัว)
python3 turbidity_dct.py   # self-check ราย module ("run a single test" = รันไฟล์นั้น)
python3 volume_model.py
python3 synthetic_data.py
#   boundary_detection.py ไม่มี __main__ — ทดสอบผ่าน demo.py

# วิเคราะห์รูปจริง 1 ภาพ
python3 analyze_real_photo.py photo.jpg --roi X Y W H --profile-csv prof.csv

# บันทึกผลระหว่างไขน้ำ: กดปุ่ม ⏺/⏹ บนหน้าเว็บ → records/rec_*.csv
#   หรือจากเครื่องอื่น: python3 track_log.py drain.csv
```

`picamera2` มาจาก apt ไม่ใช่ pip: `sudo apt install -y python3-picamera2` · venv ต้องใช้ `--system-site-packages`

---

## โครงสร้างไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `boundary_detection.py` | หา `boundary_y` + `conf` จาก row-wise intensity gradient — numpy/OpenCV array ล้วน ไม่มี camera I/O |
| `turbidity_dct.py` | `dct_sharpness()` + `TurbidityMonitor` — ตัดสิน warming_up / turbid / clearing / clear |
| `volume_model.py` | `FrustumModel` + `CalibrationTable` (interpolate / JSON / inverse) — geometry ยังเป็น placeholder |
| `synthetic_data.py` | สร้างเฟรม/ลำดับการไขน้ำปลอมไว้ทดสอบก่อนมีข้อมูลจริง |
| `demo.py` | รวม 4 โมดูลข้างบน รันกับ synthetic + assertion (smoke test) |
| `analyze_real_photo.py` | CLI: boundary + sharpness กับรูป 1 ภาพ, `--roi`, `--calib`, `--profile-csv` |
| `realtime_stream.py` | สตรีม MJPEG + แผงสถานะ + endpoint `/status` `/records` `/record/start|stop` · `_Tracker` กรอง `boundary_y_smooth` · watchdog กันกล้องค้าง |
| `run_stream.sh` | supervisor: relaunch `realtime_stream.py` ทุกครั้งที่มันปิด (คู่กับ watchdog) |
| `track_log.py` | poll `/status` → CSV จากเครื่องอื่น |
| `records/` | CSV ผลการทดสอบไขน้ำ (หนึ่งแถวต่อเฟรม) |

---

## สถาปัตยกรรม — การไหลของข้อมูลตอนรัน

โค้ดแบ่งเป็น 2 โลกที่แยกกันชัดเจน:

**1. โมดูลวิเคราะห์ที่ไม่ยุ่งกับฮาร์ดแวร์** — `boundary_detection`, `turbidity_dct`, `volume_model`
เป็นฟังก์ชัน/คลาสบริสุทธิ์ที่รับ numpy array (ไม่มี camera I/O, ไม่ import `picamera2`/`flask`)
`demo.py` เป็นตัวประกอบทั้งสามเข้าด้วยกัน รันกับเฟรมจาก `synthetic_data.py` — ทดสอบ algorithm ได้เต็มรูปแบบบนเครื่องใดก็ได้
โซ่การตรวจจับใน `boundary_detection.py`: crop ROI → ค่าเฉลี่ยความสว่างรายแถว → smooth → `np.gradient` →
`argmax(|grad|)` (เว้น margin ที่ขอบ) → แถวนั้น = รอยต่อ, `|grad|` ณ แถวนั้น = `conf`

**2. ระบบสด `realtime_stream.py`** (ต้องมี Pi + กล้อง) — โครงเป็น **producer เดียว + Flask threaded หลายผู้บริโภค**:
- เธรด `_capture_loop` เป็น producer เดียว: `capture_array()` → `detect_boundary(frame, ROI)` →
  `_Tracker.update()` (median `TRACK_WIN` เฟรม + ปฏิเสธการกระโดด > `TRACK_MAX_STEP` px, re-seed หลังติดค้าง
  `TRACK_RESEED_AFTER` เฟรม) → เขียน `_latest_jpeg` + dict `_status` + (ถ้ากำลังบันทึก) หนึ่งแถวใน CSV
- Flask serve อย่างเดียว: `/video_feed` สตรีม `_latest_jpeg`, `/status` คืน `_status` + สถานะการบันทึก,
  `/records` + `/record/start|stop` จัดการไฟล์ใน `records/`
- เธรด `_watchdog`: ถ้าไม่มีเฟรมใหม่ 15 วิ → `os._exit(1)` แล้ว `run_stream.sh` (loop ข้างนอก) relaunch ให้ → กู้กล้องค้างได้เอง
- **การตั้งค่าทั้งหมดเป็นค่าคงที่ระดับโมดูลใน `realtime_stream.py`** ส่วนใหญ่ override ด้วย env var ได้
  (`ROI_X/Y/W/H`, `EXPOSURE_US`, `GAIN`, `WB_RED/BLUE`) · `CONFIDENCE_THRESHOLD` และพารามิเตอร์ `_Tracker`
  (`TRACK_*`) เป็นค่าคงที่ — เป็น "ปุ่ม" ที่งานเฟส 1 (ทำให้ค่ากรองเสถียร) กำลังปรับอยู่

`_status` dict คือสัญญาระหว่างสองส่วน: capture loop เขียนฝั่งเดียว, `/status` (และ `track_log.py`, หน้าเว็บ) อ่าน

---

## การตัดสินใจออกแบบ (ต่างจากเปเปอร์)

| หัวข้อ | เปเปอร์ | ที่เราใช้ | เหตุผล |
|---|---|---|---|
| ระบุบริเวณของเหลว | YOLOv8n-seg | crop ROI ด้วยมือ | คำถามวิจัยคือ "classical พอไหม" — ใส่ ML กลับมาทำให้ไร้ความหมาย |
| ตัวช่วยเห็นรอยต่อ | — | ไม่มี (ลองวิธีตรง) | พิสูจน์ด้วยข้อมูลจริงก่อนว่าสัญญาณพอ |
| ความสูง → ปริมาตร | frustum | calibrate จริง — บีกเกอร์ทรงกระบอก = เส้นตรง | ทรงกระบอกไม่ต้อง fit หลายจุด |
| แยกของเหลว | stopcock + สเต็ปเปอร์ | ปั๊มดูดผ่านท่อก้นภาชนะ + relay | ใช้ของที่มี |
| ตัวประมวลผล | Orange Pi + STM32 | Pi 5 บอร์ดเดียว + GPIO + relay | ลดฮาร์ดแวร์ (เสี่ยง: timing jitter ยังไม่ทดสอบ) |

เก็บจากเปเปอร์: DCT turbidity monitoring และ row-wise gradient boundary detection (classical ล้วน)

---

## สถานะ (4 ก.ย. 2026)

- **P0 เสร็จ** — โมดูลหลัก + เครื่องมือครบ, git + push GitHub (`Cherrpxp/extractlab`)
- **P1 กำลังทำ** — ฉากหลังดำ + ROI แคบ → ตัวตรวจจับเกาะรอยต่อน้ำ/น้ำมันจริง (`conf` ~12 เทียบเกณฑ์ 3)
  ทดสอบไขน้ำครั้งแรก 219 วิ: แนวโน้มถูก (เลื่อนลง 104 px) แต่ค่ากรองยังกระโดด 151 px ตอน `conf` ตก → **ยังไม่ผ่านเกต**
  เหลือ: หด ROI ให้แคบลงอีก · ไม่ให้เฟรม `conf` ต่ำ re-seed tracker · บังคับ monotonic ระหว่างบันทึก · อัดซ้ำเทียบกราฟ
- **P2–P7** ยังไม่เริ่ม (calibrate ปริมาตร → ต่อปั๊ม → closed loop → RMSE 10 รอบ → ไซโคลเฮกเซน → รายงาน)

---

## กับดักที่เจอมาแล้ว (อ่านก่อนแก้)

- **`git push` จาก terminal บน Pi ไม่ได้** — ไม่มี credential (`could not read Username`) · push ผ่านปุ่ม Sync ใน VS Code
- **สาย CSI ของกล้องเปราะ** — จับ/ขยับกล้องบ่อยแล้วขาดหายเป็นช่วง ๆ (`Camera frontend has timed out`) · sensor enumerate ได้แต่ไม่มีเฟรม = สายหรือคอนเนกเตอร์ · ต้องยึดกล้อง + strain relief · watchdog + `run_stream.sh` กู้ระดับซอฟต์แวร์แล้ว
- **`picamera2` format `"RGB888"` ให้ array มาเป็น BGR อยู่แล้ว** — อย่าเรียก `cvtColor(..., RGB2BGR)` ทับ (เคยทำให้ของเหลืองกลายเป็นฟ้า)
- **ต้องตั้ง `FrameDurationLimits` กว้าง** ไม่งั้น pipeline บีบ `ExposureTime` เหลือ ~33 ms เงียบ ๆ
- **ค่ากล้อง (exposure/gain/WB) ผูกกับแสง ณ ที่นั้น** — ย้ายที่/เปลี่ยนไฟ ต้อง recalibrate (รัน AWB+AE auto อ่านค่าแล้ว bake กลับเป็น manual)
- **calibration (ROI, mm/px, threshold, ตารางปริมาตร) ผูกกับ setup ที่วัด** — กล้อง/ภาชนะขยับเมื่อไหร่ใช้ไม่ได้
- **ห้ามต่อสายปั๊มเข้าขา GPIO / 5V / GND ของ Pi เด็ดขาด** — 12V/0.42A vs GPIO ~16 mA · เคยต่อผิดมาแล้ว · `vcgencmd get_throttled` ตอนนี้ = 0x0 (บอร์ดปกติ)
- **VPN บนเครื่องที่เปิดหน้าเว็บ** อาจบล็อกการเข้าถึง Pi ใน LAN เดียวกัน — ปิด VPN ก่อนถ้าเข้าไม่ได้
- `pkill -f realtime_stream` จาก terminal จะฆ่า shell ตัวเองถ้าคำสั่งเดียวกันมีคำว่า `realtime_stream` อยู่ด้วย — kill ด้วย PID หรือแยกคำสั่ง
