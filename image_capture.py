import os
import cv2
from picamera2 import Picamera2
import time
from datetime import datetime
import sys

# Nhận tên từ stdin
PERSON_NAME = sys.stdin.readline().strip() or "unknown"

dataset_folder = "dataset"

def create_folder(name):
    person_folder = os.path.join(dataset_folder, name)
    if not os.path.exists(person_folder):
        os.makedirs(person_folder)
    return person_folder

def capture_photos(name):
    folder = create_folder(name)
    
    picam2 = Picamera2()
    picam2.configure(picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (640, 480)}))
    picam2.start()
    time.sleep(2)
    
    photo_count = 0
    print(f"Taking photos for {name}. Press SPACE to capture, 'q' to quit.")
    
    while True:
        frame = picam2.capture_array()
        cv2.imshow('Capture', frame)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord(' '):
            photo_count += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.jpg"
            filepath = os.path.join(folder, filename)
            cv2.imwrite(filepath, frame)
            print(f"Photo {photo_count} saved: {filepath}")
        
        elif key == ord('q'):
            break
    
    cv2.destroyAllWindows()
    picam2.stop()
    print(f"Completed. {photo_count} photos for {name}.")

if __name__ == "__main__":
    capture_photos(PERSON_NAME)
