#!/usr/bin/env python3
"""VisionIQ API (Python port of the Node/Express backend) + the NH5 Highway website and models, on one server.

  python backend/server.py            # http://0.0.0.0:5000  (PORT / HOST in backend/.env)

Serves:
  /api/...            VisionIQ REST API (same routes and JSON as server.js)
  /socket.io          live vehicle stream (newVehicleBatch / vehicleStreamStatus events)
  /images, /evidence  vehicle snapshots / evidence with the SVG fallbacks
  /nh5, /library, /live, /model, /scenes, /media, ...   NH5 Highway website (YOLOv8 + ByteTrack + PaddleOCR)
  everything else     the built React frontend (../dist, run `npm run build`)
"""
import os
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / '.env')
os.environ.setdefault('YOLO_AUTOINSTALL', 'false')

from flask import Flask, abort, jsonify, request, send_from_directory  # noqa: E402
from flask_socketio import SocketIO  # noqa: E402
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge  # noqa: E402

from config.database import initialize_database  # noqa: E402
from routes.auth_routes import auth_routes  # noqa: E402
from routes.nh5_routes import nh5_routes  # noqa: E402
from routes.query_routes import query_routes  # noqa: E402
from services import nh5_bridge  # noqa: E402
from services import vehicle_stream as vs  # noqa: E402

DIST_DIR = ROOT_DIR / 'dist'
PUBLIC_DIR = ROOT_DIR / 'public'
DATA_DIR = BACKEND_DIR / 'data'

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # express.json({ limit: '100mb' })
app.json.sort_keys = False

configured_frontend_origins = [o.strip() for o in os.getenv('FRONTEND_URL', 'http://localhost:5173').split(',')
                               if o.strip()]
_LAN_ORIGIN = re.compile(r'^https?://((localhost)|(127\.0\.0\.1)|(\d{1,3}\.){3}\d{1,3})(:\d+)?$')


def is_allowed_origin(origin, environ=None):
    if not origin:
        return True
    if '*' in configured_frontend_origins:
        return True
    return origin in configured_frontend_origins or bool(_LAN_ORIGIN.match(origin))


socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=is_allowed_origin)


@socketio.on('connect')
def on_connect(auth=None):
    latest = vs.get_latest_stream_status()
    if latest:
        socketio.emit('vehicleStreamStatus', latest, to=request.sid)


if not os.getenv('JWT_SECRET'):
    os.environ['JWT_SECRET'] = 'visioniq_dev_secret_fallback_key_2025'
    print('[Auth] JWT_SECRET is not set in backend/.env -- using the development fallback secret.')


# ---------------------------------------------------------------- CORS (cors({ origin: fn, credentials: true }))
@app.before_request
def cors_preflight():
    if request.method == 'OPTIONS' and request.headers.get('Access-Control-Request-Method'):
        response = app.make_default_options_response()
        response.status_code = 204
        return response
    return None


@app.after_request
def cors_headers(response):
    origin = request.headers.get('Origin')
    if origin and is_allowed_origin(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers.add('Vary', 'Origin')
        if request.method == 'OPTIONS':
            response.headers['Access-Control-Allow-Methods'] = 'GET,HEAD,PUT,PATCH,POST,DELETE'
            req_headers = request.headers.get('Access-Control-Request-Headers')
            if req_headers:
                response.headers['Access-Control-Allow-Headers'] = req_headers
    return response


def _arg_number(name, default):
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------- API
@app.get('/api/health')
def health():
    return jsonify(success=True, message='VisionIQ API is running.')


@app.post('/api/vehicles/upload')
def upload_vehicles():
    """Upload new Excel/CSV rows to store in the database and switch the active live stream."""
    try:
        body = request.get_json(silent=True) or {}
        file_name = body.get('fileName')
        rows = body.get('rows')
        is_append = bool(body.get('isAppend', False))
        is_last_chunk = body.get('isLastChunk', True)
        total_records = body.get('totalRecords')
        if not file_name or not isinstance(rows, list) or not rows:
            return jsonify(success=False, message='fileName and rows array required for upload.'), 400

        result = vs.store_uploaded_vehicle_records(file_name, rows, is_append=is_append)

        if is_last_chunk:
            initial = result.get('initialBatch') or []
            socketio.emit('vehicleStreamStatus', {
                'type': 'dataset_switched',
                'fileName': file_name,
                'totalRows': total_records or result['totalStored'],
                'batchCount': len(initial),
                'timestamp': vs.local_time_string(),
                'overspeeding': sum(1 for r in initial if r['isOverSpeed']),
            })
            if initial:
                socketio.emit('newVehicleBatch', initial)

        return jsonify({
            'success': True,
            'message': f"Successfully stored {result['totalStored']} records from \"{file_name}\" in the database.",
            **result,
        })
    except HTTPException:
        raise  # e.g. 413 payload too large -> handled by the JSON error handlers below
    except Exception as error:  # noqa: BLE001
        print('Error handling vehicle upload:', error)
        return jsonify(success=False, message=str(error) or 'Error processing upload.'), 500


@app.get('/api/vehicles')
def list_vehicles():
    """Initial vehicles load (capped to limit, default 20)."""
    try:
        vehicles = vs.get_stored_vehicles(limit=_arg_number('limit', 20), file_name=request.args.get('fileName') or None)
        return jsonify(success=True, count=len(vehicles), vehicles=vehicles)
    except Exception as error:  # noqa: BLE001
        print('Unable to load vehicle events:', error)
        return jsonify(success=False, message='Unable to load vehicle events.'), 500


def is_specific_vehicle_query(query_text):
    q = str(query_text or '').strip().lower()
    if not q:
        return False
    plate = re.search(r'\b([a-z]{2}\s*[-]?\s*[0-9]{1,2}\s*[-]?\s*[a-z]{0,3}\s*[-]?\s*[0-9]{1,4})\b', q, re.I)
    if plate:
        raw = re.sub(r'[^a-z0-9]', '', plate.group(1), flags=re.I)
        if len(raw) >= 5 and not raw.startswith('cam'):
            return True
    return bool(re.search(r'\b(?:nh44|obs|record|telemetry)[-_ ]*\d+\b', q, re.I))


@app.get('/api/vehicles/search')
def search_vehicles():
    """Fast vehicle search across all records in the database."""
    try:
        q = request.args.get('q') or request.args.get('query') or request.args.get('plate') or ''
        limit = _arg_number('limit', 50)
        if not q.strip():
            return jsonify(success=True, count=0, vehicles=[])

        vehicles = vs.search_vehicles(q, limit)
        dossier = None
        if vehicles and is_specific_vehicle_query(q):
            top = vehicles[0]
            is_over = bool(top['isOverSpeed']) or str(top['overSpeed']).lower() == 'yes'
            conf = float(top['plateConfidence'] or 0.95)
            dossier = {
                'primaryPlate': top['vehicleNumberPlate'],
                'vehicleType': top['vehicleType'],
                'detectionCount': len(vehicles),
                'lastLocation': top['location'],
                'camera': top['camera'],
                'speed': top['speed'],
                'speedLimit': top['speedLimit'],
                'isOverSpeed': is_over,
                'timestampIst': top['timestampIst'],
                'plateConfidence': round(conf * (100 if conf <= 1 else 1)),
                'image': top['vehicleImagePath'] or top['vehicleImage'],
                'summary': (f"Vehicle {top['vehicleNumberPlate']} ({top['vehicleType']}) recorded at {top['location']} "
                            f"by {top['camera']} at {top['timestampIst']}. Velocity: {vs._js_str(top['speed'])} km/h "
                            f"(Limit: {vs._js_str(top['speedLimit'])} km/h, "
                            f"{'SPEED VIOLATION' if is_over else 'Normal Speed'}). "
                            f'ANPR OCR Confidence: {round(conf * 100)}%.'),
            }
        return jsonify(success=True, query=q, count=len(vehicles), dossier=dossier, vehicles=vehicles)
    except Exception as error:  # noqa: BLE001
        print('Error in /api/vehicles/search:', error)
        return jsonify(success=False, message=str(error)), 500


@app.get('/api/vehicles/random-batch')
def random_batch():
    """Fetch a random number of records (1 to 20)."""
    try:
        requested = _arg_number('count', None)
        file_name = request.args.get('fileName') or None
        batch = vs.fetch_random_vehicle_batch(requested, file_name)
        if request.args.get('broadcast') == 'true':
            socketio.emit('newVehicleBatch', batch['records'])
            socketio.emit('vehicleStreamStatus', {
                'type': 'batch',
                'fileName': file_name or vs.get_active_file_name(),
                'batchCount': batch['count'],
                'totalPool': batch['totalPool'] or 7044,
                'timestamp': vs.local_time_string(),
                'overspeeding': sum(1 for r in batch['records'] if r['isOverSpeed']),
            })
        return jsonify(success=True, count=batch['count'], batchSize=batch['batchSize'], vehicles=batch['records'])
    except Exception as error:  # noqa: BLE001
        print('Unable to fetch random batch:', error)
        return jsonify(success=False, message='Unable to fetch random batch.'), 500


@app.post('/api/vehicles/stream-control')
def stream_control():
    """Live stream control: pause, resume, or trigger an instant random batch."""
    action = (request.get_json(silent=True) or {}).get('action')
    if action == 'pause':
        vs.pause_stream()
        socketio.emit('vehicleStreamStatus', {**(vs.get_latest_stream_status() or {}), 'isPaused': True})
        return jsonify(success=True, isPaused=True)
    if action == 'resume':
        vs.resume_stream()
        socketio.emit('vehicleStreamStatus', {**(vs.get_latest_stream_status() or {}), 'isPaused': False})
        return jsonify(success=True, isPaused=False)
    if action in ('trigger', 'next'):
        batch = vs.trigger_instant_batch(socketio)
        return jsonify(success=True, count=batch['count'], vehicles=batch['records'])
    return jsonify(success=False,
                   message='Invalid stream control action. Use "pause", "resume", or "trigger".'), 400


@app.get('/api/vehicles/stats')
def vehicle_stats():
    """Pool statistics across records in the database."""
    try:
        return jsonify(success=True, stats=vs.get_vehicle_pool_stats(request.args.get('fileName') or None))
    except Exception as error:  # noqa: BLE001
        return jsonify(success=False, message=str(error)), 500


app.register_blueprint(auth_routes, url_prefix='/api/auth')
app.register_blueprint(query_routes, url_prefix='/api/query')
app.register_blueprint(nh5_routes)


# ---------------------------------------------------------------- NH5 Highway integration API
@app.get('/api/nh5/status')
def nh5_status():
    return jsonify(success=True, **nh5_bridge.status())


@app.get('/api/nh5/jobs')
def nh5_jobs():
    jobs = nh5_bridge.list_jobs()
    return jsonify(success=True, count=len(jobs), jobs=jobs)


@app.get('/api/nh5/events')
def nh5_events():
    events = nh5_bridge.list_events(limit=int(_arg_number('limit', 500)))
    return jsonify(success=True, count=len(events), events=events)


@app.post('/api/nh5/sync')
def nh5_sync():
    try:
        return jsonify(success=True, **nh5_bridge.sync_results(socketio))
    except Exception as error:  # noqa: BLE001
        return jsonify(success=False, message=str(error)), 500


# ---------------------------------------------------------------- evidence / images with SVG fallbacks
PLATE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 200" width="100%" height="100%">
      <rect width="460" height="200" fill="#060913" />
      <rect x="30" y="40" width="400" height="120" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="3" />
      <rect x="30" y="40" width="46" height="120" rx="6" fill="#003893" />
      <circle cx="53" cy="85" r="12" fill="none" stroke="#ffffff" stroke-width="1.5" />
      <text x="53" y="128" font-size="12" font-family="sans-serif" font-weight="900" fill="#ffffff" text-anchor="middle">IND</text>
      <text x="245" y="118" font-size="42" font-family="monospace" font-weight="900" fill="#0f172a" text-anchor="middle" letter-spacing="5">TG 08 CD 3015</text>
      <text x="35" y="30" font-size="12" font-family="monospace" fill="#10b981" font-weight="bold">● ANPR OCR MATCH 94%</text>
    </svg>'''

EVIDENCE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 480" width="100%" height="100%">
      <defs>
        <linearGradient id="cctvGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#070c18"/>
          <stop offset="100%" stop-color="#020408"/>
        </linearGradient>
      </defs>
      <rect width="800" height="480" fill="url(#cctvGrad)"/>
      <line x1="0" y1="90" x2="800" y2="90" stroke="rgba(56,189,248,0.12)" stroke-width="1"/>
      <line x1="0" y1="390" x2="800" y2="390" stroke="rgba(56,189,248,0.12)" stroke-width="1"/>
      <!-- Reticle Box -->
      <rect x="220" y="140" width="360" height="200" rx="10" fill="none" stroke="#38bdf8" stroke-width="2" stroke-dasharray="8 4"/>
      <path d="M 220 170 L 220 140 L 250 140" fill="none" stroke="#38bdf8" stroke-width="3"/>
      <path d="M 550 140 L 580 140 L 580 170" fill="none" stroke="#38bdf8" stroke-width="3"/>
      <path d="M 220 310 L 220 340 L 250 340" fill="none" stroke="#38bdf8" stroke-width="3"/>
      <path d="M 550 340 L 580 340 L 580 310" fill="none" stroke="#38bdf8" stroke-width="3"/>
      <circle cx="400" cy="240" r="4" fill="#38bdf8"/>
      <!-- Optical Vehicle Silhouette -->
      <path d="M 300 270 Q 320 220 370 210 L 430 210 Q 480 220 500 270 Z" fill="rgba(56,189,248,0.18)" stroke="#38bdf8" stroke-width="2"/>
      <circle cx="340" cy="275" r="16" fill="#0f172a" stroke="#38bdf8" stroke-width="2"/>
      <circle cx="460" cy="275" r="16" fill="#0f172a" stroke="#38bdf8" stroke-width="2"/>
      <!-- HUD Top -->
      <circle cx="35" cy="45" r="6" fill="#ef4444"/>
      <text x="50" y="50" font-size="14" font-family="monospace" font-weight="bold" fill="#f87171">● REC [SURVEILLANCE CAM-02-HYD]</text>
      <text x="760" y="50" font-size="14" font-family="monospace" fill="#94a3b8" text-anchor="end">1080p OPTICAL 60FPS</text>
      <!-- HUD Bottom -->
      <rect x="230" y="150" width="130" height="24" rx="4" fill="rgba(56,189,248,0.25)"/>
      <text x="240" y="166" font-size="12" font-family="monospace" font-weight="bold" fill="#38bdf8">TARGET: {basename}</text>
      <text x="35" y="440" font-size="13" font-family="monospace" fill="#34d399">EVIDENCE ARCHIVE VERIFIED</text>
      <text x="760" y="440" font-size="13" font-family="monospace" fill="#94a3b8" text-anchor="end">VISIONIQ INTELLIGENCE</text>
    </svg>'''

IMAGE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 480" width="100%" height="100%">
    <defs>
      <linearGradient id="camGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#050814"/>
        <stop offset="100%" stop-color="#02040a"/>
      </linearGradient>
      <linearGradient id="scanBeam" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="rgba(56,189,248,0)"/>
        <stop offset="50%" stop-color="rgba(56,189,248,0.25)"/>
        <stop offset="100%" stop-color="rgba(56,189,248,0)"/>
      </linearGradient>
    </defs>
    <rect width="800" height="480" fill="url(#camGrad)"/>
    <rect x="0" y="210" width="800" height="60" fill="url(#scanBeam)"/>
    <line x1="0" y1="120" x2="800" y2="120" stroke="rgba(56,189,248,0.15)" stroke-width="1"/>
    <line x1="0" y1="360" x2="800" y2="360" stroke="rgba(56,189,248,0.15)" stroke-width="1"/>

    <!-- Target Detection Bounding Box -->
    <rect x="200" y="120" width="400" height="230" rx="8" fill="rgba(15,23,42,0.6)" stroke="#38bdf8" stroke-width="2" stroke-dasharray="6 4"/>
    <path d="M 200 150 L 200 120 L 230 120" fill="none" stroke="#38bdf8" stroke-width="3"/>
    <path d="M 570 120 L 600 120 L 600 150" fill="none" stroke="#38bdf8" stroke-width="3"/>
    <path d="M 200 320 L 200 350 L 230 350" fill="none" stroke="#38bdf8" stroke-width="3"/>
    <path d="M 570 350 L 600 350 L 600 320" fill="none" stroke="#38bdf8" stroke-width="3"/>

    <!-- Optical Vehicle Chassis -->
    <path d="M 280 270 Q 310 200 370 190 L 430 190 Q 490 200 520 270 Z" fill="rgba(56,189,248,0.22)" stroke="#38bdf8" stroke-width="2.5"/>
    <circle cx="330" cy="280" r="18" fill="#090d16" stroke="#38bdf8" stroke-width="2.5"/>
    <circle cx="470" cy="280" r="18" fill="#090d16" stroke="#38bdf8" stroke-width="2.5"/>

    <!-- Live HUD Telemetry -->
    <circle cx="32" cy="40" r="5" fill="#ef4444"/>
    <text x="45" y="44" font-size="13" font-family="monospace" font-weight="bold" fill="#ef4444">NH-44 SURVEILLANCE FEED</text>
    <text x="765" y="44" font-size="13" font-family="monospace" fill="#38bdf8" text-anchor="end">4K OPTICAL RADAR</text>
    <rect x="210" y="132" width="160" height="22" rx="4" fill="rgba(14,165,233,0.3)"/>
    <text x="218" y="147" font-size="11" font-family="monospace" font-weight="bold" fill="#7dd3fc">CAPTURE: {basename}</text>
    <text x="32" y="448" font-size="12" font-family="monospace" fill="#34d399">DATABASE RECORD VERIFIED (5,000 ARCHIVE)</text>
    <text x="765" y="448" font-size="12" font-family="monospace" fill="#94a3b8" text-anchor="end">VISIONIQ HIGHWAY AI</text>
  </svg>'''


def _svg(text):
    return app.response_class(text, mimetype='image/svg+xml')


def _xml_escape(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _serve_first(subdir, path):
    for base in (PUBLIC_DIR / subdir, DATA_DIR / subdir):
        target = (base / path).resolve()
        if target.is_file() and base.resolve() in target.parents:
            return send_from_directory(base, path)
    return None


@app.route('/evidence/', defaults={'path': 'capture.jpg'})
@app.route('/evidence/<path:path>')
def evidence(path):
    found = _serve_first('evidence', path)
    if found is not None:
        return found
    if 'plate' in path:
        return _svg(PLATE_SVG)
    return _svg(EVIDENCE_SVG.replace('{basename}', _xml_escape(os.path.basename(path))))


@app.route('/images/', defaults={'path': 'image.jpg'})
@app.route('/images/<path:path>')
def images(path):
    found = _serve_first('images', path)
    if found is not None:
        return found
    return _svg(IMAGE_SVG.replace('{basename}', _xml_escape(os.path.basename(path))))


# ---------------------------------------------------------------- React frontend (built into ../dist)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def frontend(path):
    if path.startswith('api/'):
        return jsonify(success=False, message=f'Route not found: /{path}'), 404
    if path and DIST_DIR.is_dir() and (DIST_DIR / path).is_file():
        return send_from_directory(DIST_DIR, path)
    if path == 'notification_sound.mp3' and (ROOT_DIR / path).is_file():  # lives in the repo root, not public/
        return send_from_directory(ROOT_DIR, path)
    if path and PUBLIC_DIR.is_dir() and (PUBLIC_DIR / path).is_file():
        return send_from_directory(PUBLIC_DIR, path)
    if (DIST_DIR / 'index.html').is_file():
        if '.' in os.path.basename(path):
            abort(404)
        return send_from_directory(DIST_DIR, 'index.html')  # client-side routes (/home, /query, ...)
    return jsonify(success=False, message='Frontend not built yet: run `npm run build` in the VisionIQ folder '
                                          '(or use `npm run dev` on port 5173).'), 404


# ---------------------------------------------------------------- errors: API always answers JSON
@app.errorhandler(RequestEntityTooLarge)
def too_large(_err):
    return jsonify(success=False, message='Uploaded file payload is too large. Please upload files under 100MB.'), 413


@app.errorhandler(Exception)
def api_error(err):
    if isinstance(err, HTTPException):
        if request.path.startswith('/api/'):
            return jsonify(success=False, message=err.description or err.name), err.code
        return err
    print('[VisionIQ API Error]:', err)
    return jsonify(success=False, message=str(err) or 'An unexpected server error occurred.'), 500


def main():
    db_status = initialize_database()
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '5000'))

    nh5_enabled = os.getenv('NH5_ENABLED', 'true').strip().lower() != 'false'
    nh5_loaded = False
    if nh5_enabled:
        nh5_dir = Path(os.getenv('NH5_DIR') or nh5_bridge.default_nh5_dir())
        try:
            module = nh5_bridge.load_nh5(nh5_dir, os.getenv('NH5_MODEL') or None,
                                         os.getenv('NH5_OCR_ENGINE', 'paddleocr'))
            app.wsgi_app = nh5_bridge.NH5Dispatcher(app.wsgi_app, module.app)
            summary = nh5_bridge.sync_results()
            print(f"[NH5] Library: {summary['jobs']} finished video(s) available to VisionIQ.")
            nh5_loaded = True
        except Exception as error:  # noqa: BLE001
            print(f'[NH5] Integration disabled -- could not load the NH5 website/models from {nh5_dir}: {error}')

    print('\n==============================================')
    print(f'🚀 VisionIQ API listening on http://{host}:{port}')
    if db_status['engine'] == 'mysql':
        print(f"   Connected to MySQL database \"{os.getenv('MYSQL_DATABASE', 'vision_iq')}\"")
    else:
        from config.database import db
        print(f'   Database: SQLite ({db.sqlite_path})')
    if nh5_loaded:
        print(f'   NH5 Highway website: http://{host}:{port}/nh5  (model {nh5_bridge.nh5.MODEL_NAME}, '
              f'{nh5_bridge.nh5.DEVICE_LABEL})')
    if not DIST_DIR.is_dir():
        print('   Frontend not built (run `npm run build`), or use `npm run dev` on port 5173')
    print('==============================================\n')

    if os.getenv('STREAM_REPLAY', 'false').strip().lower() == 'true':
        # optional demo mode of the Node backend: keep re-broadcasting stored records in random batches
        socketio.start_background_task(vs.run_vehicle_stream, socketio)
    if nh5_loaded:
        nh5_bridge.start_sync_thread(socketio)
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True, use_reloader=False, debug=False)


if __name__ == '__main__':
    main()
