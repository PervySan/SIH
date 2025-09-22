import cv2
import requests
import threading
import time
import datetime
import math
from ultralytics import YOLO
from flask import Flask, Response

app = Flask(__name__)
BASE_STATION_URL = "http://127.0.0.1:5000"

# --- Configuration ---
DRONE_ALTITUDE_METERS = 20.0
CAMERA_FOCAL_LENGTH_PIXELS = 700
KNOWN_PERSON_HEIGHT_METERS = 1.7
# Load a YOLOv8 model with tracking capabilities
model = YOLO('yolov8s.pt')
cap = cv2.VideoCapture(0)

# --- Person Tracking ---
# A set to store the IDs of people for whom an alert has already been sent
tracked_person_ids = set()

# --- Drone Patrol Simulation ---
# Starting coordinates
current_lat = 13.0827
current_lon = 80.2707
patrol_leg_length = 0.001 # Approx 111 meters
patrol_speed = 0.00002 # Simulation speed

def drone_patrol_path():
    """A generator that continuously yields the drone's next GPS coordinates in a square path."""
    global current_lat, current_lon
    while True:
        # Fly North
        for _ in range(50):
            current_lat += patrol_speed
            yield current_lat, current_lon
            time.sleep(1)
        # Fly East
        for _ in range(50):
            current_lon += patrol_speed
            yield current_lat, current_lon
            time.sleep(1)
        # Fly South
        for _ in range(50):
            current_lat -= patrol_speed
            yield current_lat, current_lon
            time.sleep(1)
        # Fly West
        for _ in range(50):
            current_lon -= patrol_speed
            yield current_lat, current_lon
            time.sleep(1)

patrol_generator = drone_patrol_path()

def update_drone_location():
    """Continuously sends the drone's current location to the base station."""
    for lat, lon in patrol_generator:
        try:
            requests.post(f"{BASE_STATION_URL}/alert", json={'lat': lat, 'lon': lon, 'is_drone': True}, timeout=1)
        except requests.exceptions.RequestException:
            pass # Ignore connection errors if base station is down

def send_human_detection_alert(lat, lon):
    """Sends coordinates of a detected person to the base station."""
    data = {"lat": float(lat), "lon": float(lon)}
    try:
        requests.post(f"{BASE_STATION_URL}/alert", json=data, timeout=1)
    except requests.exceptions.RequestException:
        pass

def calculate_person_gps(drone_lat, drone_lon, ground_distance_m):
    """Calculates person's GPS by offsetting from the drone (simplified North offset)."""
    earth_radius = 6378137.0
    lat_offset = ground_distance_m / earth_radius
    new_lat = drone_lat + (lat_offset * 180 / math.pi)
    new_lon = drone_lon
    return new_lat, new_lon

def generate_video_frames():
    """Generates video frames, performs human detection and tracking, and calculates location."""
    while True:
        ret, frame = cap.read()
        if not ret: break

        # Use the track() method for object tracking
        results = model.track(frame, persist=True)

        for result in results:
            if result.boxes is not None and result.boxes.id is not None:
                # Get the tracking IDs
                track_ids = result.boxes.id.int().cpu().tolist()

                for i, box in enumerate(result.boxes):
                    if int(box.cls[0]) == 0:  # Class 0 is 'person'
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        person_id = track_ids[i]

                        # Draw bounding box and ID on the frame
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f"Person ID: {person_id}", (x1, y1 - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                        # Check if this person is new
                        if person_id not in tracked_person_ids:
                            # Add the new person's ID to our set
                            tracked_person_ids.add(person_id)
                            print(f"New person with ID {person_id} detected. Sending alert.")

                            bbox_height_pixels = y2 - y1
                            if bbox_height_pixels > 0:
                                distance_to_person_m = (KNOWN_PERSON_HEIGHT_METERS * CAMERA_FOCAL_LENGTH_PIXELS) / bbox_height_pixels
                                if distance_to_person_m > DRONE_ALTITUDE_METERS:
                                    ground_distance_m = math.sqrt(distance_to_person_m**2 - DRONE_ALTITUDE_METERS**2)
                                    person_lat, person_lon = calculate_person_gps(current_lat, current_lon, ground_distance_m)
                                    send_human_detection_alert(person_lat, person_lon)
                                    cv2.putText(frame, f"Dist: {ground_distance_m:.1f}m", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        ret, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/video')
def video():
    return Response(generate_video_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_flask_app():
    app.run(host='0.0.0.0', port=8000, debug=False)

if __name__ == "__main__":
    # Start the drone location updater in a separate thread
    location_updater_thread = threading.Thread(target=update_drone_location, daemon=True)
    location_updater_thread.start()

    # Start the Flask app for the video stream
    run_flask_app()
