import cv2
import requests
import threading
import time
import datetime
import random
import math
from ultralytics import YOLO
from flask import Flask, Response

app = Flask(__name__)
BASE_ALERT_URL = "http://127.0.0.1:5000/alert"
BASE_STATUS_URL = "http://127.0.0.1:5000/alerts"

model = YOLO('yolov8s.pt')
cap = cv2.VideoCapture(0)

recent_humans = {}  # (lat,lon): time
ALERT_COOLDOWN = 3
MIN_DISTANCE = 0.0001  # ~10m

def distance(lat1, lon1, lat2, lon2):
    return math.sqrt((lat1-lat2)**2 + (lon1-lon2)**2)

def get_drone_coords():
    try:
        r = requests.get(BASE_STATUS_URL, timeout=1)
        coords = r.json().get("drone", {"lat":11.0168,"lon":76.9558}) # Coimbatore default
        return coords["lat"], coords["lon"]
    except:
        return 11.0168,76.9558

def send_alert(lat, lon):
    now = time.time()
    for (r_lat, r_lon), t in recent_humans.items():
        if distance(lat, lon, r_lat, r_lon) < MIN_DISTANCE:
            if now - t < ALERT_COOLDOWN:
                return
    recent_humans[(lat, lon)] = now
    data = {
        "lat": float(lat + random.uniform(-0.0001,0.0001)),
        "lon": float(lon + random.uniform(-0.0001,0.0001)),
        "status":"detected",
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    }
    try:
        requests.post(BASE_ALERT_URL, json=data, timeout=1)
    except:
        pass

def gen_frames():
    while True:
        ret, frame = cap.read()
        if not ret: break
        results = model(frame)
        human_found = False
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    cls = int(box.cls[0])
                    if cls==0:  # person
                        human_found = True
                        x1,y1,x2,y2=map(int,box.xyxy[0])
                        cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
        if human_found:
            lat, lon = get_drone_coords()
            send_alert(lat, lon)
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+buffer.tobytes()+b'\r\n')

@app.route('/video')
def video():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_app():
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)

if __name__=="__main__":
    t=threading.Thread(target=run_app)
    t.start()
