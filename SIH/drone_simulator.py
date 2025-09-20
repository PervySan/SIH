import cv2
import requests
import threading
import time
import datetime
import math
from ultralytics import YOLO
from flask import Flask, Response

app = Flask(__name__)
BASE_ALERT_URL = "http://127.0.0.1:5000/alert"
BASE_STATUS_URL = "http://127.0.0.1:5000/alerts"

# --- New Configuration for Distance Estimation ---
# These are crucial assumptions for our simulation.
# In a real-world scenario, you'd get these from sensors or calibration.
DRONE_ALTITUDE_METERS = 20.0       # Assume a fixed drone altitude of 20 meters.
CAMERA_FOCAL_LENGTH_PIXELS = 700 # An assumed focal length for a standard webcam.
KNOWN_PERSON_HEIGHT_METERS = 1.7   # Assume the average height of a person is 1.7 meters.

model = YOLO('yolov8s.pt')
cap = cv2.VideoCapture(0)

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates the simple Euclidean distance between two lat/lon points."""
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)

def get_drone_coords():
    """Fetches the drone's current GPS coordinates from the base station."""
    try:
        r = requests.get(BASE_STATUS_URL, timeout=1)
        data = r.json()
        if data and data.get("drone"):
            coords = data["drone"]
            return coords["lat"], coords["lon"]
        return 11.0168, 76.9558
    except (requests.exceptions.RequestException, ValueError):
        return 11.0168, 76.9558

def send_alert(lat, lon):
    """Sends the calculated coordinates of the detected person to the base station."""
    data = {
        "lat": float(lat),
        "lon": float(lon),
        "status": "detected",
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    }
    try:
        requests.post(BASE_ALERT_URL, json=data, timeout=1)
    except:
        pass

def calculate_person_gps(drone_lat, drone_lon, ground_distance_m):
    """
    Calculates the person's GPS coordinates by offsetting from the drone's location.
    NOTE: This is a simplified calculation assuming the person is directly in front of the drone (North).
    A real implementation would use the drone's compass heading.
    """
    earth_radius = 6378137.0  # Earth's radius in meters
    
    # Calculate offset in latitude (bearing 0 degrees / North)
    lat_offset = ground_distance_m / earth_radius
    new_lat = drone_lat + (lat_offset * 180 / math.pi)
    
    # Longitude offset is 0 for a pure North bearing
    new_lon = drone_lon
    
    return new_lat, new_lon

def generate_video_frames():
    """Generates video frames, performs human detection, and calculates their location."""
    while True:
        ret, frame = cap.read()
        if not ret: break

        results = model(frame)
        human_detected = False

        for result in results:
            if result.boxes is not None:
                for box in result.boxes:
                    cls = int(box.cls[0])
                    if cls == 0:  # Class 0 is 'person'
                        human_detected = True
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        
                        # --- New Distance and Coordinate Calculation Logic ---
                        bbox_height_pixels = y2 - y1
                        if bbox_height_pixels > 0:
                            # 1. Estimate direct distance from drone to person
                            distance_to_person_m = (KNOWN_PERSON_HEIGHT_METERS * CAMERA_FOCAL_LENGTH_PIXELS) / bbox_height_pixels
                            
                            # 2. Calculate horizontal distance on the ground using Pythagoras
                            # (distance_to_person^2 = altitude^2 + ground_distance^2)
                            if distance_to_person_m > DRONE_ALTITUDE_METERS:
                                ground_distance_m = math.sqrt(distance_to_person_m**2 - DRONE_ALTITUDE_METERS**2)
                                
                                # 3. Get drone's current location
                                drone_lat, drone_lon = get_drone_coords()
                                
                                # 4. Calculate the person's actual GPS coordinates
                                person_lat, person_lon = calculate_person_gps(drone_lat, drone_lon, ground_distance_m)
                                
                                # 5. Send the alert with the person's calculated coordinates
                                send_alert(person_lat, person_lon)
                                
                                # Display estimated distance on the video feed
                                cv2.putText(frame, f"Dist: {ground_distance_m:.1f}m", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video')
def video():
    return Response(generate_video_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_app():
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)

if __name__ == "__main__":
    t = threading.Thread(target=run_app)
    t.start()
