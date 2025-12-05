## Features

- Real-time face recognition using `face_recognition` (dlib + CNN)
- Capture employee photos directly from Raspberry Pi camera
- Auto re-train face encodings whenever new photos are added
- PIR motion sensor and LCD1602&I2C display shows name & time 
- Attendance logs saved to CSV 

## Hardware 

- Raspberry Pi 4 (2GB or higher recommended)
- Raspberry Pi Camera Module (v2 or v3)
- PIR motion sensor HC-SR501 (optional)
- 5V relay module
- 16×2 I2C LCD (optional)


## Quick Start

# 1. Clone repo
git clone https://github.com/phuong0342098446-code/facial_recognition_redesign.git
cd facial_recognition_redesign

# 2. Create virtual environment
python3 -m venv face_rec
source face_rec/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. First-time training (if you already have photos in dataset/)
python3 model_training.py

# 5. Run everything
# Terminal 1 – Web Dashboard
python3 web_app/app.py

# Terminal 2 – Attendance 
python3 face_attendance.py
