import os
import json
import csv
import math
import platform
import subprocess
import re
from flask import Flask, send_from_directory, jsonify, request, abort, render_template
from PIL import Image


try:
    import numpy as np
except Exception:
    np = None

# File paths
MAP_IMAGE = os.path.join('static', 'taguspark_floor_0.jpg')
OUTPUT_CSV = 'fingerprints.csv'
PROGRESS_FILE = 'progress.json'
SSID_ORDER_FILE = 'ssid_order.json'
SQUARE_SIZE_METERS = 1.0

# PATH-LOSS defaults
RSSI_REF_AT_1M = -40.0
PATH_LOSS_EXPONENT = 2.0

# Simple in-memory storage for router positions (persisted only through CSV if you want)
router_positions = {}  # {ssid: (x_m, y_m)}
completed_squares = set()
# load progress on startup
if os.path.exists(PROGRESS_FILE):
    try:
        loaded = json.load(open(PROGRESS_FILE, 'r'))
        completed_squares = {tuple(x) for x in loaded}
    except Exception:
        completed_squares = set()

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Utility: scan Wi-Fi (re-uses your logic)
def get_wifi_rssi(target_ssids):
    os_name = platform.system()
    scan_results = {ssid: -100 for ssid in target_ssids}
    try:
        if os_name == "Windows":
            out = subprocess.check_output("netsh wlan show networks mode=bssid", shell=True, stderr=subprocess.DEVNULL)
            command_output = out.decode('utf-8', errors='ignore')
            networks = re.findall(r"SSID \d+ : (.+?)\r?\n(?:.*?\r?\n)*?Signal\s*:\s*(\d+)%", command_output, re.DOTALL)
            for ssid, signal_percent in networks:
                ssid = ssid.strip()
                if ssid in target_ssids:
                    scan_results[ssid] = int((int(signal_percent) / 2) - 100)
        elif os_name == "Linux":
            cmd = "nmcli -t -f SSID,SIGNAL dev wifi list"
            out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
            command_output = out.decode('utf-8', errors='ignore')
            lines = command_output.strip().split('\n')
            for line in lines:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    ssid = parts[0].replace('\\:', ':')
                    signal_str = parts[1]
                    if ssid in target_ssids and signal_str:
                        scan_results[ssid] = int(signal_str)
        elif os_name == "Darwin":
            cmd = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -s"
            out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
            command_output = out.decode('utf-8', errors='ignore')
            lines = command_output.split('\n')
            for line in lines[1:]:
                if not line.strip(): continue
                parts = re.match(r'\s*(.+?)\s+([0-9a-f:]{17})\s+(-?\d+)', line)
                if parts and parts.group(1) in target_ssids:
                    scan_results[parts.group(1)] = int(parts.group(3))
    except FileNotFoundError:
        print("Scan command missing.")
    except subprocess.CalledProcessError as e:
        print("Scan command failed:", e)
    except Exception as e:
        print("Unexpected error during scan:", e)
    return scan_results

def rssi_to_distance(rssi_dbm, p0=RSSI_REF_AT_1M, n=PATH_LOSS_EXPONENT):
    try:
        if rssi_dbm <= -99:
            return float('inf')
        return 10 ** ((p0 - rssi_dbm) / (10.0 * n))
    except Exception:
        return float('inf')

def trilaterate(distances):
    # distances: {ssid: dist_m}
    pts = []
    r = []
    for ssid, d in distances.items():
        if ssid in router_positions and math.isfinite(d):
            pts.append(router_positions[ssid])
            r.append(d)
    if len(pts) < 3:
        return None
    if np is None:
        return None
    P = np.array(pts, dtype=float)
    R = np.array(r, dtype=float)
    x1, y1 = P[0]
    A = []
    b = []
    for i in range(1, len(P)):
        xi, yi = P[i]
        ri = R[i]
        lhs = [2*(xi - x1), 2*(yi - y1)]
        rhs = ri**2 - R[0]**2 - xi**2 - yi**2 + x1**2 + y1**2
        A.append(lhs); b.append(rhs)
    A = np.array(A); b = np.array(b)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        return float(sol[0]), float(sol[1])
    except Exception as e:
        print("Trilateration failed:", e)
        return None

# --- Endpoints ---

# Serve index
@app.route('/')
def index():
    return render_template('index.html')

# Provide image metadata (pixel dims)
@app.route('/api/image-metadata')
def image_meta():
    if not os.path.exists(MAP_IMAGE):
        abort(404)
    img = Image.open(MAP_IMAGE)
    return jsonify({
        'path': f"/static/{os.path.basename(MAP_IMAGE)}",
        'width_px': img.width,
        'height_px': img.height
    })

# Return current router positions and completed squares
@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify({
        'routers': router_positions,
        'completed': list(map(list, completed_squares))
    })

# Set routers (body: JSON {routers: [{ssid, x, y}, ...]})
@app.route('/api/routers', methods=['POST'])
def set_routers():
    data = request.json
    if not data or 'routers' not in data:
        return jsonify({'error': 'bad request'}), 400
    router_positions.clear()
    for r in data['routers']:
        ssid = r.get('ssid')
        x = float(r.get('x', 0))
        y = float(r.get('y', 0))
        router_positions[ssid] = (x, y)
    return jsonify({'ok': True})

# Scan endpoint: body JSON {ssids: [...]} -> returns {ssid: rssi}
@app.route('/api/scan', methods=['POST'])
def scan_endpoint():
    data = request.json
    if not data or 'ssids' not in data:
        return jsonify({'error': 'bad request'}), 400
    ssids = data['ssids']
    results = get_wifi_rssi(ssids)
    return jsonify(results)

# Save fingerprint: body JSON {x,y, rssi: {ssid: value}}
@app.route('/api/save', methods=['POST'])
def save_endpoint():
    data = request.json
    if not data:
        return jsonify({'error': 'bad request'}), 400
    x = float(data.get('x'))
    y = float(data.get('y'))
    rssis = data.get('rssi', {})
    # compute est coords
    distances = {ssid: rssi_to_distance(float(val)) for ssid, val in rssis.items()}
    est = trilaterate(distances)
    row = [f"{x:.2f}", f"{y:.2f}"]
    # keep a deterministic ssid order (router_positions or provided)
    ssid_order = list(rssis.keys())
    for ssid in ssid_order:
        row.append(rssis.get(ssid))
    if est is None:
        row += ["", ""]
    else:
        row += [f"{est[0]:.2f}", f"{est[1]:.2f}"]
    write_header = not os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['x_meter', 'y_meter'] + ssid_order + ['est_x_m', 'est_y_m'])
        writer.writerow(row)
    # mark square as completed (square index can be passed but we simply accept coords)
    # convert to grid square indices:
    cx = int(x // SQUARE_SIZE_METERS)
    cy = int((y) // SQUARE_SIZE_METERS)
    completed_squares.add((cy, cx))
    # persist progress
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(list(map(list, completed_squares)), f)
    return jsonify({'ok': True, 'est': est})

if __name__ == '__main__':
    # run on localhost only
    app.run(host='127.0.0.1', port=5000, debug=True)
