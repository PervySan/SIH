from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import math

app = Flask(__name__, static_folder='static')
CORS(app)

# --- Configuration ---
# In-memory database
db = {
    "drone_location": None,
    "alerts": []  # Each alert will now store a datetime object
}
# Cooldown settings for duplicate rejection
MIN_DISTANCE_THRESHOLD = 0.0001  # Approx. 11 meters
RECENCY_WINDOW_SECONDS = 15      # Time window to consider an alert "recent"

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate the Euclidean distance between two coordinates."""
    return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2)

@app.route('/alerts', methods=['GET'])
def get_alerts():
    """Returns drone location and alerts, formatting timestamps for the frontend."""
    # Create a serializable copy of alerts with formatted time
    serializable_alerts = []
    for alert in db['alerts']:
        alert_copy = alert.copy()
        alert_copy['time'] = alert['timestamp'].strftime('%H:%M:%S')
        del alert_copy['timestamp'] # No need to send the full timestamp object
        serializable_alerts.append(alert_copy)
        
    return jsonify({
        'drone': db['drone_location'],
        'alerts': serializable_alerts
    })

@app.route('/alert', methods=['POST'])
def add_alert():
    """Adds a drone location update or a new human detection alert."""
    data = request.get_json()
    if not data or 'lat' not in data or 'lon' not in data:
        return jsonify({'error': 'Invalid data'}), 400

    lat = data['lat']
    lon = data['lon']

    if data.get('is_drone'):
        db['drone_location'] = {'lat': lat, 'lon': lon}
        return jsonify({'status': 'drone location updated'})
    else:
        # --- New Duplicate Rejection Logic ---
        now = datetime.now()
        for alert in db['alerts']:
            is_too_soon = (now - alert['timestamp']) < timedelta(seconds=RECENCY_WINDOW_SECONDS)
            is_too_close = calculate_distance(lat, lon, alert['lat'], alert['lon']) < MIN_DISTANCE_THRESHOLD
            
            if is_too_soon and is_too_close:
                return jsonify({'status': 'duplicate alert rejected due to recency'})

        # If no recent duplicate is found, add the new alert
        alert_id = f"{round(lat, 5)}-{round(lon, 5)}-{now.strftime('%S')}"
        new_alert = {
            'id': alert_id,
            'lat': lat,
            'lon': lon,
            'timestamp': now,  # Store the full datetime object for comparison
            'status': 'detected'
        }
        db['alerts'].append(new_alert)

        # Optional: Keep the alerts list from growing indefinitely
        if len(db['alerts']) > 100:
            db['alerts'].pop(0)
            
        return jsonify({'status': 'alert stored'})

@app.route('/alert/<string:aid>', methods=['PATCH'])
def update_alert_status(aid):
    """Updates the status of a specific alert."""
    status = request.json.get('status')
    if not status:
        return jsonify({'error': 'Status not provided'}), 400
        
    for alert in db['alerts']:
        if alert['id'] == aid:
            alert['status'] = status
            return jsonify({'ok': True, 'message': f'Alert {aid} updated to {status}'})
            
    return jsonify({'ok': False, 'error': 'Alert not found'}), 404

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serves static files."""
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    app.run(host='0.0.0.0', port=5000)
