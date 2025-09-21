import os
import math
import requests
import csv
import io
from flask import Flask, jsonify, request, send_from_directory, Response, render_template
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# --- In-memory Mission Database ---
db = {
    "mission_name": None,
    "mission_start_time": None,
    "mission_end_time": None,
    "drone_location": None,
    "drone_path": [],
    "alerts": []
}
MIN_DISTANCE_THRESHOLD = 0.0001
RECENCY_WINDOW_SECONDS = 15

# --- Page Routing ---
@app.route('/')
def login_page():
    """Serves the new login/mission start page."""
    return render_template('login.html')

@app.route('/dashboard')
def dashboard_page():
    """Serves the main mission control dashboard."""
    return render_template('index.html')

# --- Mission Control Routes ---
@app.route('/operation/start', methods=['POST'])
def start_operation():
    """Resets and starts a new mission with a given name."""
    global db
    data = request.get_json()
    mission_name = data.get('mission_name', 'Unnamed Mission')
    
    db = {
        "mission_name": mission_name,
        "mission_start_time": datetime.now(),
        "mission_end_time": None,
        "drone_location": None,
        "drone_path": [],
        "alerts": []
    }
    return jsonify({"status": "Mission started", "mission_name": mission_name})

@app.route('/operation/end', methods=['GET'])
def end_operation():
    """Ends the mission and generates a downloadable CSV report."""
    if not db["mission_start_time"]:
        return "Mission not started.", 400

    db["mission_end_time"] = datetime.now()
    
    output = io.StringIO()
    writer = csv.writer(output)

    # *** NEW: Mission Name added to report ***
    writer.writerow(['MISSION REPORT'])
    writer.writerow(['Mission Name', db['mission_name']])
    writer.writerow(['Start Time', db['mission_start_time'].strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow(['End Time', db['mission_end_time'].strftime('%Y-%m-%d %H:%M:%S')])
    duration = db['mission_end_time'] - db['mission_start_time']
    writer.writerow(['Total Duration', str(duration)])
    writer.writerow([]) 

    stats = calculate_stats()
    writer.writerow(['SUMMARY STATISTICS'])
    for key, value in stats.items():
        writer.writerow([key.replace("_", " ").title(), value])
    writer.writerow([]) 
    
    writer.writerow(['DETAILED ALERT LOG'])
    writer.writerow(['Alert ID', 'Latitude', 'Longitude', 'Detection Time', 'Final Status'])
    for alert in db['alerts']:
        writer.writerow([
            alert['id'], alert['lat'], alert['lon'],
            alert['timestamp'].strftime('%H:%M:%S'), alert['status']
        ])
    
    output.seek(0)
    # *** NEW: Report filename includes mission name ***
    report_filename = f"mission_report_{db['mission_name'].replace(' ', '_')}.csv"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={report_filename}"}
    )

def calculate_stats():
    alerts = db['alerts']
    stats = {
        "total_detected": len(alerts),
        "rescued": sum(1 for a in alerts if a['status'] == 'rescued'),
        "medical_supplies": sum(1 for a in alerts if a['status'] == 'supplies'),
        "deceased": sum(1 for a in alerts if a['status'] == 'died'),
        "sos": sum(1 for a in alerts if a['status'] == 'sos'),
        "unresolved": sum(1 for a in alerts if a['status'] == 'detected')
    }
    return stats

@app.route('/data', methods=['GET'])
def get_data():
    if not db["mission_start_time"]:
        return jsonify({"mission_active": False})
        
    serializable_alerts = []
    for alert in db['alerts']:
        alert_copy = alert.copy()
        alert_copy['time'] = alert['timestamp'].strftime('%H:%M:%S')
        del alert_copy['timestamp']
        serializable_alerts.append(alert_copy)
        
    return jsonify({
        'mission_active': True,
        # *** NEW: Mission name sent to frontend ***
        'mission_name': db['mission_name'],
        'start_time': db['mission_start_time'].isoformat(),
        'drone': db['drone_location'],
        'path': db['drone_path'],
        'alerts': serializable_alerts,
        'stats': calculate_stats()
    })

# --- Other routes (add_alert, update_alert_status, get_weather) remain the same ---

@app.route('/alert', methods=['POST'])
def add_alert():
    if not db["mission_start_time"]: return jsonify({'error': 'Mission not started'}), 400
    data = request.get_json()
    if 'lat' not in data or 'lon' not in data: return jsonify({'error': 'Invalid data'}), 400
    lat, lon = data['lat'], data['lon']
    if data.get('is_drone'):
        db['drone_location'] = {'lat': lat, 'lon': lon}
        db['drone_path'].append([lat, lon])
        if len(db['drone_path']) > 200: db['drone_path'].pop(0)
        return jsonify({'status': 'drone location updated'})
    else:
        now = datetime.now()
        for alert in db['alerts']:
            if (now - alert['timestamp']) < timedelta(seconds=RECENCY_WINDOW_SECONDS) and \
               math.sqrt((lat - alert['lat'])**2 + (lon - alert['lon'])**2) < MIN_DISTANCE_THRESHOLD:
                return jsonify({'status': 'duplicate alert rejected'})
        alert_id = f"{round(lat, 5)}-{round(lon, 5)}-{now.strftime('%S')}"
        db['alerts'].append({'id': alert_id, 'lat': lat, 'lon': lon, 'timestamp': now, 'status': 'detected'})
        return jsonify({'status': 'alert stored', 'new_alert': True})

@app.route('/alert/<string:aid>', methods=['PATCH'])
def update_alert_status(aid):
    status = request.json.get('status')
    for alert in db['alerts']:
        if alert['id'] == aid:
            alert['status'] = status
            return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Alert not found'}), 404

@app.route('/weather', methods=['GET'])
def get_weather():
    if not db['drone_location']: return jsonify({'error': 'Drone location unknown'}), 404
    lat, lon = db['drone_location']['lat'], db['drone_location']['lon']
    try:
        response = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=3)
        data = response.json().get("current_weather", {})
        return jsonify({'temperature': data.get('temperature', 'N/A'), 'windspeed': data.get('windspeed', 'N/A')})
    except:
        return jsonify({'error': 'Failed to fetch weather data'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
