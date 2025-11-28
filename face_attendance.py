import face_recognition
import cv2
import numpy as np
from picamera2 import Picamera2
import time
import pickle
import requests
from gpiozero import LED, MotionSensor
try:
    from RPLCD.i2c import CharLCD
    RPLCD_AVAILABLE = True
except Exception:
    RPLCD_AVAILABLE = False
from datetime import datetime

# ---------------- Config ----------------
ENCODINGS_FILE = "encodings.pickle"
PIR_PIN = 17
OUTPUT_PIN = 14
LCD_I2C_ADDR = 0x27
LCD_COLUMNS = 16
LCD_ROWS = 2
RECOGNITION_DURATION = 15
CHECK_INTERVAL = 5
DISTANCE_THRESHOLD = 0.5
SERVER_URL = "http://127.0.0.1:5000/log"
CV_SCALER = 2
USE_HOG = True

PIR_DEBOUNCE_COUNT = 3
PIR_DEBOUNCE_INTERVAL = 0.12
ENABLE_PIR_DEBUG = True

# ---------------- Init ----------------
print("[INFO] Loading encodings...")
with open(ENCODINGS_FILE, "rb") as f:
    data = pickle.loads(f.read())

known_face_encodings = data.get("encodings", [])
known_face_names = [n.lower() for n in data.get("names", [])]

print(f"[INFO] Loaded {len(known_face_encodings)} encodings.")

try:
    pir = MotionSensor(PIR_PIN, pull_up=False)
    print(f"[INFO] MotionSensor on GPIO {PIR_PIN} (pull_up=False)")
except Exception as e:
    print("[ERROR] MotionSensor init:", e)
    class _FakePir:
        motion_detected = False
        is_active = False
    pir = _FakePir()

output = LED(OUTPUT_PIN)

class DummyLCD:
    def clear(self): pass
    def write_string(self, s): print("[LCD]", s)
    def crlf(self): print()
    def __getattr__(self, name):
        def _nope(*args, **kwargs): pass
        return _nope

if RPLCD_AVAILABLE:
    try:
        lcd = CharLCD(i2c_expander='PCF8574', address=LCD_I2C_ADDR, cols=LCD_COLUMNS, rows=LCD_ROWS, charmap='A00')
        lcd.clear()
        lcd.write_string("Khoi dong...")
        print(f"[INFO] LCD at {hex(LCD_I2C_ADDR)}")
    except Exception as e:
        print("[WARN] LCD init failed:", e)
        lcd = DummyLCD()
else:
    print("[WARN] RPLCD not available")
    lcd = DummyLCD()

picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (1280, 720)}))

last_session_time = 0

def pir_is_active():
    try:
        if hasattr(pir, "motion_detected"):
            return bool(pir.motion_detected)
        return bool(getattr(pir, "is_active", False))
    except Exception as e:
        if ENABLE_PIR_DEBUG:
            print("[DEBUG] pir_is_active exception:", e)
        return False

def pir_active_debounced():
    count = 0
    for i in range(PIR_DEBOUNCE_COUNT):
        state = pir_is_active()
        if ENABLE_PIR_DEBUG:
            print(f"[DEBUG] PIR read {i+1}/{PIR_DEBOUNCE_COUNT}: {state}")
        if state:
            count += 1
        else:
            return False
        time.sleep(PIR_DEBOUNCE_INTERVAL)
    return count >= PIR_DEBOUNCE_COUNT

def send_log(name, authorized, distance):
    payload = {
        "timestamp": datetime.now().isoformat(),
        "name": name,
        "authorized": bool(authorized),
        "distance": float(distance) if distance != "" else ""
    }
    try:
        requests.post(SERVER_URL, json=payload, timeout=2)
    except Exception as e:
        print("[WARN] Send log failed:", e)

def display_lcd(line1, line2=""):
    try:
        lcd.clear()
        lcd.write_string(str(line1)[:LCD_COLUMNS])
        if line2:
            lcd.crlf()
            lcd.write_string(str(line2)[:LCD_COLUMNS])
    except Exception as e:
        print("[WARN] LCD write error:", e)

def recognize_frame(frame):
    resized = cv2.resize(frame, (0, 0), fx=(1/CV_SCALER), fy=(1/CV_SCALER))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    model = 'hog' if USE_HOG else 'cnn'
    face_locs = face_recognition.face_locations(rgb, model=model)
    encs = face_recognition.face_encodings(rgb, face_locs)
    results = []
    for enc in encs:
        if len(known_face_encodings) == 0:
            results.append(("Unknown", None))
            continue
        dists = face_recognition.face_distance(known_face_encodings, enc)
        if dists.size == 0:
            results.append(("Unknown", None))
            continue
        best_idx = int(np.argmin(dists))
        bestd = float(dists[best_idx])
        if bestd <= DISTANCE_THRESHOLD:
            name = known_face_names[best_idx]
        else:
            name = "Unknown"
        results.append((name, bestd))
    return results, face_locs

def run_recognition_session(duration_seconds=RECOGNITION_DURATION, check_interval=CHECK_INTERVAL):
    print("[INFO] Starting camera...")
    try:
        picam2.start()
    except Exception as e:
        print("[WARN] picam2.start failed:", e)
        return None

    end_time = time.time() + duration_seconds
    next_check = time.time() + check_interval
    best_detection = None

    try:
        while time.time() < end_time:
            frame = picam2.capture_array()
            results, locs = recognize_frame(frame)
            for name, dist in results:
                if dist is None: continue
                if best_detection is None or dist < best_detection[1]:
                    best_detection = (name, dist)
            if time.time() >= next_check:
                if not pir_is_active():
                    print("[INFO] No motion, ending early.")
                    display_lcd("Khong thay chuyen dong", "")
                    break
                else:
                    print("[INFO] Motion active, continue.")
                next_check = time.time() + check_interval
            time.sleep(0.12)
    finally:
        try:
            picam2.stop()
        except Exception as e:
            print("[WARN] picam2.stop failed:", e)

    print("[INFO] Session finished. Best:", best_detection)
    return best_detection

def main_loop():
    global last_session_time
    display_lcd("San sang", datetime.now().strftime("%H:%M:%S"))
    print("[INFO] Main loop started.")

    print(f"[INFO] Initial PIR: motion_detected={getattr(pir, 'motion_detected', 'N/A')}, is_active={getattr(pir, 'is_active', 'N/A')}")

    try:
        while True:
            try:
                pir.wait_for_motion(timeout=1)
            except:
                pass

            if not pir_active_debounced():
                now = datetime.now()
                display_lcd(now.strftime("%H:%M:%S"), "Cho PIR...")
                try:
                    picam2.stop()
                except:
                    pass
                time.sleep(0.5)
                continue

            print("[INFO] Motion confirmed. Start session.")
            display_lcd("Dang nhan dien...", "Vui long cho")
            detection = run_recognition_session()
            last_session_time = time.time()

            if detection is None:
                print("[INFO] No faces or camera error.")
                display_lcd("Khong thay khuon mat", datetime.now().strftime("%H:%M:%S"))
                output.off()
                send_log("Unknown", False, "")
                time.sleep(1)
                continue

            name, distance = detection
            ts_str = datetime.now().strftime("%d/%m %H:%M:%S")
            authorized = (name != "Unknown")  # Always authorized if known
            if authorized:
                print(f"[INFO] Authorized: {name} (d={distance:.3f})")
                display_lcd(f"{name}", f"Da cham: {ts_str}")
                output.on()
            else:
                display_lcd("Nguoi la", ts_str)
                print("[INFO] Unknown, dist:", distance)
                output.off()
            send_log(name, authorized, distance or "")
            time.sleep(1)

    except KeyboardInterrupt:
        print("[INFO] Exiting...")
        display_lcd("Tat chuong trinh", "")
    except Exception as e:
        print("[ERROR] Main loop:", e)
        display_lcd("Loi", str(e)[:LCD_COLUMNS])
    finally:
        try:
            lcd.clear()
        except:
            pass
        output.off()
        try:
            picam2.stop()
        except:
            pass

if __name__ == "__main__":
    main_loop()