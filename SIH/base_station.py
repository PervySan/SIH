from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__, static_folder='static')
CORS(app)

drone_location = None
alerts = []        # store dicts {id,lat,lon,time,status}
alert_ids = set()  # deduplication

@app.route('/alerts', methods=['GET'])
def get_alerts():
    return jsonify({
        'drone': drone_location,
        'alerts': alerts
    })

@app.route('/alert', methods=['POST'])
def add_alert():
    global drone_location
    data = request.get_json()
    lat = data.get('lat')
    lon = data.get('lon')
    if 'is_drone' in data and data['is_drone']:
        drone_location = {'lat': lat, 'lon': lon}
        return jsonify({'status': 'drone updated'})
    else:
        alert_id = f"{round(lat,5)}-{round(lon,5)}"
        if alert_id not in alert_ids:
            alert_ids.add(alert_id)
            alerts.append({
                'id': alert_id,
                'lat': lat,
                'lon': lon,
                'time': datetime.now().strftime('%H:%M:%S'),
                'status': 'detected'
            })
            if len(alerts) > 100:
                alerts.pop(0)
        return jsonify({'status': 'alert stored'})

@app.route('/alert/<aid>', methods=['PATCH'])
def update_alert(aid):
    for a in alerts:
        if a['id'] == aid:
            a['status'] = request.json.get('status', a['status'])
            return jsonify({'ok': True})
    return jsonify({'ok': False}), 404

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(host='0.0.0.0', port=5000)
