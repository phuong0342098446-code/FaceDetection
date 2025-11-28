from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory
import csv
import os
import json
import subprocess
from datetime import datetime
import threading
import shutil

app = Flask(__name__)
app.secret_key = 'your-secret-key'
app.jinja_env.globals['now'] = datetime.now  # Fix now() in template

# Đường dẫn
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # /home/hung123/facial_recognition_redesign
DATASET_DIR = os.path.join(PROJECT_ROOT, "dataset")
ENCODINGS_FILE = os.path.join(PROJECT_ROOT, "encodings.pickle")
LOG_FILE = os.path.join(PROJECT_ROOT, "attendance_log.csv")
EMPLOYEES_FILE = os.path.join(PROJECT_ROOT, "web_app", "employees.json")

os.makedirs(DATASET_DIR, exist_ok=True)

def load_employees():
    if not os.path.exists(EMPLOYEES_FILE):
        return []
    with open(EMPLOYEES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_employees(employees):
    with open(EMPLOYEES_FILE, 'w', encoding='utf-8') as f:
        json.dump(employees, f, indent=2, ensure_ascii=False)

def retrain_model():
    try:
        result = subprocess.run(
            ["python3", os.path.join(PROJECT_ROOT, "model_training.py")],
            capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT  # Fix cwd
        )
        if result.returncode == 0:
            return True, "Cập nhật thành công!"
        else:
            return False, f"Lỗi: {result.stderr[:200]}"
    except Exception as e:
        return False, str(e)

def capture_photos_in_background(emp_id):
    def run_capture():
        script_path = os.path.join(PROJECT_ROOT, "image_capture.py")
        try:
            subprocess.run(["python3", script_path], input=emp_id + '\n', text=True, timeout=180, cwd=PROJECT_ROOT)
        except Exception as e:
            print(f"Capture error: {e}")
    threading.Thread(target=run_capture, daemon=True).start()

@app.route('/photo/<emp_id>')
def get_photo(emp_id):
    folder = os.path.join(DATASET_DIR, emp_id)
    if not os.path.exists(folder):
        return "No photo", 404
    images = [f for f in os.listdir(folder) if f.endswith(('.jpg', '.jpeg', '.png'))]
    if not images:
        return "No photo", 404
    return send_from_directory(folder, sorted(images)[-1])

@app.route('/')
def index():
    return redirect(url_for('employees'))

@app.route('/employees')
def employees():
    emps = load_employees()
    return render_template('employees.html', employees=emps)

@app.route('/employee/<emp_id>', methods=['GET', 'POST'])
def employee_detail(emp_id):
    emps = load_employees()
    emp = next((e for e in emps if e['id'] == emp_id), None)
    if not emp:
        flash("Không tìm thấy nhân viên!")
        return redirect(url_for('employees'))
    if request.method == 'POST':
        emp['name'] = request.form['name']
        emp['position'] = request.form['position']
        emp['phone'] = request.form['phone']
        emp['email'] = request.form['email']
        uploaded = False
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '':
                folder = os.path.join(DATASET_DIR, emp_id)
                os.makedirs(folder, exist_ok=True)
                filepath = os.path.join(folder, f"{emp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                file.save(filepath)
                uploaded = True
        save_employees(emps)
        if uploaded:
            success, msg = retrain_model()
            flash("Cập nhật thành công! ")
        else:
            flash("Cập nhật thành công!")
    return render_template('employee_detail.html', emp=emp)

@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if request.method == 'POST':
        emp_id = request.form['id'].lower().strip()
        name = request.form['name'].strip()
        if not emp_id or not name:
            flash("Vui lòng nhập ID và Tên!")
            return render_template('add_employee.html')
        emps = load_employees()
        if any(e['id'] == emp_id for e in emps):
            flash("ID đã tồn tại!")
            return render_template('add_employee.html')
        uploaded = False
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '':
                folder = os.path.join(DATASET_DIR, emp_id)
                os.makedirs(folder, exist_ok=True)
                filepath = os.path.join(folder, f"{emp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                file.save(filepath)
                uploaded = True
        new_emp = {
            "id": emp_id,
            "name": name,
            "position": request.form.get('position', ''),
            "phone": request.form.get('phone', ''),
            "email": request.form.get('email', '')
        }
        emps.append(new_emp)
        save_employees(emps)
        action = request.form.get('action', 'add')
        if action == 'add_and_capture':
            capture_photos_in_background(emp_id)
            flash("Đã thêm và mở camera chụp ảnh!")
        # Luôn train sau khi thêm
        success, msg = retrain_model()
        flash("Đã thêm nhân viên. " + msg)
        return redirect(url_for('employees'))
    return render_template('add_employee.html')

@app.route('/capture/<emp_id>')
def capture_photo(emp_id):
    capture_photos_in_background(emp_id)
    flash(f"Đang mở camera cho {emp_id}")
    return redirect(url_for('employee_detail', emp_id=emp_id))

@app.route('/retrain')
def retrain():
    success, msg = retrain_model()
    flash(msg)
    return redirect(url_for('employees'))

@app.route('/delete_employee/<emp_id>')
def delete_employee(emp_id):
    emps = load_employees()
    emps = [e for e in emps if e['id'] != emp_id]
    save_employees(emps)

    folder = os.path.join(DATASET_DIR, emp_id)
    if os.path.exists(folder):
        shutil.rmtree(folder)

    success, msg = retrain_model()
    flash("Xóa thành công! " )
    return redirect(url_for('employees'))

@app.route('/attendance')
def attendance():
    selected_date = request.args.get('date')
    search_name = request.args.get('name', '').strip().lower()

    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Chuyển timestamp về dạng dễ xử lý
                    dt = datetime.fromisoformat(row['timestamp'].split('.')[0].replace('Z', ''))
                    row['timestamp'] = dt.strftime("%d/%m %H:%M")  # giữ nguyên format cũ của bạn
                except:
                    row['timestamp'] = row.get('timestamp', '?')[:16]

                name_lower = (row.get('name') or 'unknown').lower()

                # Lọc theo ngày
                if selected_date:
                    row_date = dt.strftime("%Y-%m-%d")
                    if row_date != selected_date:
                        continue

                # Lọc theo tên
                if search_name and search_name not in name_lower:
                    continue

                logs.append(row)

        # Sắp xếp mới nhất lên đầu
        logs.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template('attendance.html', logs=logs)

@app.route('/log', methods=['POST'])
def log():
    data = request.json
    authorized = data.get("authorized", False)  # Giữ nhưng logic ở face_attendance đã fix
    with open(LOG_FILE, "a", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            data.get("timestamp", datetime.now().isoformat()),
            data.get("name", "Unknown"),
            authorized,
            data.get("distance", "")
        ])
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    print("Web chạy tại: http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
