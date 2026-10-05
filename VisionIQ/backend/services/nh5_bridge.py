"""Integration with the NH5 Highway website (Flask app.py + YOLOv8 model + PaddleOCR).

* load_nh5(): imports NH5's app.py into this process and loads its models exactly like its own main() does
  (nh5_v8_final_ep100.pt + PaddleOCR by default). NH5's files are not modified.
* NH5Dispatcher: one website. VisionIQ's React pages are the only UI; the NH5 app only serves the files and
  streams those pages use (/media, /download, /stream, /status, /live_ws, road-map images). NH5's own HTML
  pages (/nh5, /library, /live, /model, /scenes, ...) are not reachable.
* sync_results(): every finished NH5 job (webapp_data/results/<job>/vehicles.json) is imported into the
  vehicle_events table, so the NH5 detections (type, plate, photos, video) appear in VisionIQ's dashboards,
  query page and live stream. Jobs deleted from the NH5 Library are removed again. Read-only on NH5's files.
* Only jobs uploaded at/after the 'nh5_import_since' setting are shown in VisionIQ (set by
  scripts/reset_data.py, which empties VisionIQ); older Library entries stay on disk but are hidden.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from config.database import db, get_setting
from middleware.auth_middleware import token_from_environ, user_for_token
from services import vehicle_stream

# NH5 routes (app.py) that VisionIQ's pages use: annotated videos/photos, report.xlsx, the processing
# stream/status, the live-camera websocket and the road-map frame/preview images
NH5_FILE_SEGMENTS = {'media', 'download', 'stream', 'status', 'live_ws'}
NH5_SCENE_IMAGE = re.compile(r'^/scenes/[^/]+/(frame|preview)\.jpg$')
SOURCE_PREFIX = 'NH5'
# NH5 detector classes that are hazards/scenes rather than road users -- kept out of vehicle_events
NON_ROAD_USER_CLASSES = {'pothole', 'road_construction', 'accident_scene', 'fire_accident', 'license_plate'}

nh5 = None           # the imported NH5 app.py module once loaded
_sync_lock = threading.Lock()


def default_nh5_dir():
    return Path(__file__).resolve().parents[3] / 'NH5 Highway'


def load_nh5(nh5_dir, model_path=None, ocr_engine='paddleocr'):
    """Import NH5's app.py as a module and load the detector + OCR reader (same steps as its main())."""
    global nh5
    nh5_dir = Path(nh5_dir).resolve()
    app_py = nh5_dir / 'app.py'
    if not app_py.is_file():
        raise FileNotFoundError(f'NH5 app.py not found in {nh5_dir}')

    os.environ.setdefault('YOLO_AUTOINSTALL', 'false')  # keep ultralytics from pip-installing into the venv
    if str(nh5_dir) not in sys.path:
        sys.path.insert(0, str(nh5_dir))  # event_engine.py and friends

    spec = importlib.util.spec_from_file_location('nh5_app', app_py)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['nh5_app'] = mod  # Flask resolves templates/ and static/ through the module's file
    spec.loader.exec_module(mod)

    import torch
    model_path = str(model_path or nh5_dir / 'models' / 'nh5_v8_final_ep100.pt')
    use_gpu = torch.cuda.is_available()
    mod.DEVICE_LABEL = 'cuda' if use_gpu else 'cpu'
    print(f'[NH5] device: {mod.DEVICE_LABEL}')
    print(f'[NH5] loading model ({model_path}) + {ocr_engine} reader...')
    mod.MODEL = mod.pipeline.load_model(model_path)
    mod.LIVE_MODEL = mod.pipeline.load_model(model_path)
    mod.MODEL_PATH = model_path
    (mod.MODEL_NAME, mod.MODEL_DESCRIPTION, mod.MODEL_CLASSES, mod.MODEL_ARCH,
     mod.MODEL_SUMMARY) = mod.describe_model(model_path, mod.MODEL)
    print(f'[NH5] model: {mod.MODEL_NAME} -- {mod.MODEL_DESCRIPTION}')
    mod.OCR_READER = mod.LockedOCRReader(mod.pipeline.load_ocr_reader(use_gpu=use_gpu, engine=ocr_engine))
    print('[NH5] ready.')
    nh5 = mod
    return mod


class NH5Dispatcher:
    """WSGI middleware: sends the NH5 file/stream URLs VisionIQ's pages use to the NH5 Flask app, everything
    else (including NH5's own HTML pages) to VisionIQ, so there is a single website."""

    def __init__(self, visioniq_wsgi, nh5_wsgi):
        self.visioniq = visioniq_wsgi
        self.nh5 = nh5_wsgi

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '') or '/'
        if path.lstrip('/').split('/', 1)[0] in NH5_FILE_SEGMENTS or NH5_SCENE_IMAGE.match(path):
            # videos, photos and report.xlsx contain number plates: logged-in users only (session cookie)
            if user_for_token(token_from_environ(environ)) is None:
                body = b'{"success": false, "message": "Unauthorized."}'
                start_response('401 UNAUTHORIZED', [('Content-Type', 'application/json'),
                                                    ('Content-Length', str(len(body)))])
                return [body]
            return self.nh5(environ, start_response)
        return self.visioniq(environ, start_response)


# ---------------------------------------------------------------- results -> vehicle_events
def _local_url(url):
    """'http://172.18.3.77:5000/media/<job>/x.jpg' (host of the machine that processed it) -> '/media/<job>/x.jpg'"""
    if not url:
        return None
    parts = urlsplit(str(url))
    path = parts.path or ''
    if not path.startswith('/'):
        return None
    return path + (f'#{parts.fragment}' if parts.fragment else '')


def _float_or_none(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _event_labels(events):
    labels = []
    for e in events or []:
        if isinstance(e, dict):
            labels.append(str(e.get('label') or e.get('type') or '').strip())
        else:
            labels.append(str(e).strip())
    return ', '.join(l for l in labels if l)


def source_file_for(meta):
    return f"{SOURCE_PREFIX} {meta.get('original_filename') or 'video'} [{meta['job_id']}]"[:255]


def job_to_rows(meta, vehicles):
    job_id = meta['job_id']
    source_file = source_file_for(meta)
    location = f"NH-5 · {meta.get('scene_name') or meta.get('original_filename') or job_id}"[:255]
    camera = f'NH5-{job_id}'
    meta_lat, meta_lon = _float_or_none(meta.get('latitude')), _float_or_none(meta.get('longitude'))
    rows = []
    for v in vehicles:
        nh5_class = str(v.get('vehicle_type') or '').strip().lower()
        if nh5_class in NON_ROAD_USER_CLASSES:
            continue  # potholes / work zones / accident & fire scenes are events, not vehicles (see list_events)
        vehicle_type = 'Pedestrian' if nh5_class == 'person' else vehicle_stream.canonical_vehicle_type(nh5_class)
        plate = v.get('plate_number')
        plate = plate if plate and plate != 'not read' else 'Not read'
        conf = _float_or_none(v.get('plate_confidence'))
        if conf is not None and conf > 1:
            conf = conf / 100.0  # NH5 stores percent, vehicle_events stores 0..1 (DECIMAL(6,4))
        speed = _float_or_none(v.get('speed_kmh'))
        speed_limit = _float_or_none(v.get('speed_limit_kmh'))
        over = str(v.get('over_speed') or '').strip().lower()
        over_speed = 'Yes' if over == 'yes' else ('No' if over == 'no' else 'N/A')
        lat = _float_or_none(v.get('latitude'))
        lon = _float_or_none(v.get('longitude'))
        events = _event_labels(v.get('events')) or ('Overspeeding' if over_speed == 'Yes' else 'Standard detection')
        rows.append([
            f"NH5-{job_id}-{int(v.get('id') or 0):05d}",
            str(v.get('timestamp') or meta.get('uploaded_at') or '')[:80],
            vehicle_type,
            plate[:80],
            conf,
            None,
            speed,
            speed_limit,
            over_speed,
            lat if lat is not None else meta_lat,
            lon if lon is not None else meta_lon,
            _local_url(v.get('video_url')),
            _local_url(v.get('vehicle_image_url')),
            _local_url(v.get('plate_image_url')),
            events[:255],
            source_file,
            location,
            camera,
        ])
    return rows


IMPORT_SINCE_SETTING = 'nh5_import_since'


def import_since():
    """ISO local time; jobs uploaded before it are hidden from VisionIQ (None = show all)."""
    return get_setting(IMPORT_SINCE_SETTING)


def is_visible(meta, since=None):
    since = import_since() if since is None else since
    return not since or str(meta.get('uploaded_at') or '') >= since


def read_meta(job_dir):
    try:
        meta = json.loads((Path(job_dir) / 'meta.json').read_text())
    except (OSError, ValueError):
        return None
    meta.setdefault('job_id', Path(job_dir).name)
    return meta


# ---------------------------------------------------------------- duplicate uploads
_hash_cache = {}  # (path, size, mtime) -> sha256


def upload_file(job_id):
    """The uploaded source file of a job (uploads/<job_id>.<ext>), or None (live sessions have none)."""
    if nh5 is None:
        return None
    return next(iter(sorted(Path(nh5.UPLOAD_DIR).glob(f'{job_id}.*'))), None)


def file_sha256(path):
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime)
    if key not in _hash_cache:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        _hash_cache[key] = h.hexdigest()
    return _hash_cache[key]


def same_upload(path_a, path_b):
    """Byte-identical files (size first, so only same-size files are ever hashed)."""
    try:
        return path_a.stat().st_size == path_b.stat().st_size and file_sha256(path_a) == file_sha256(path_b)
    except OSError:
        return False


def _settings_key(scene_id, thorough):
    return (scene_id or None, bool(thorough))


def duplicate_job_ids(metas):
    """Job ids that are an older re-run of the same file with the same road map and mode as a newer job in
    `metas` -- counted once in the dashboards and the ontology (the Library still lists every run)."""
    by_size = defaultdict(list)
    for meta in sorted(metas, key=lambda m: m.get('uploaded_at') or '', reverse=True):  # newest first
        f = upload_file(meta['job_id'])
        if f is not None:
            by_size[(f.stat().st_size, _settings_key(meta.get('scene_id'), meta.get('thorough')))].append((meta, f))
    dups = set()
    for group in by_size.values():
        kept = []
        for meta, f in group:
            if any(same_upload(f, k) for k in kept):
                dups.add(meta['job_id'])
            else:
                kept.append(f)
    return dups


def find_processed_duplicate(path, scene_id, thorough):
    """The newest visible job (finished or still running, not failed) that processed a byte-identical file with
    the same road map and mode, or None."""
    want = _settings_key(scene_id, thorough)
    candidates = []
    for _d, meta in visible_job_dirs():
        if meta.get('status') != 'error' and _settings_key(meta.get('scene_id'), meta.get('thorough')) == want:
            candidates.append((meta['job_id'], meta.get('original_filename'), meta.get('uploaded_at')))
    with nh5.JOBS_LOCK:
        running = list(nh5.JOBS.items())
    on_disk = {c[0] for c in candidates}
    for job_id, job in running:
        if job_id not in on_disk and job.snapshot()['status'] != 'error' \
                and _settings_key(getattr(job, 'scene_id', None), getattr(job, 'thorough', False)) == want:
            candidates.append((job_id, job.original_filename, job.uploaded_at))
    candidates.sort(key=lambda c: c[2] or '', reverse=True)
    for job_id, name, uploaded_at in candidates:
        f = upload_file(job_id)
        if f is not None and f != path and same_upload(path, f):
            return {'jobId': job_id, 'originalFilename': name, 'uploadedAt': uploaded_at}
    return None


def visible_job_dirs():
    """(job_dir, meta) for every Library entry VisionIQ shows, newest first."""
    if nh5 is None:
        return []
    since = import_since()
    out = []
    for meta_path in Path(nh5.RESULT_DIR).glob('*/meta.json'):
        meta = read_meta(meta_path.parent)
        if meta is not None and is_visible(meta, since):
            out.append((meta_path.parent, meta))
    out.sort(key=lambda dm: dm[1].get('uploaded_at') or '', reverse=True)
    return out


def counted_job_dirs():
    """visible_job_dirs() without older re-runs of the same file (see duplicate_job_ids): what the dashboards,
    events and ontology count, so processing a video twice does not double its vehicles and plate sightings."""
    dirs = visible_job_dirs()
    dups = duplicate_job_ids([meta for _d, meta in dirs if meta.get('status') == 'done'])
    return [(d, meta) for d, meta in dirs if meta['job_id'] not in dups]


def _done_jobs(result_dir):
    since = import_since()
    jobs = {}
    for meta_path in Path(result_dir).glob('*/meta.json'):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            continue
        if meta.get('status') != 'done' or not (meta_path.parent / 'vehicles.json').is_file():
            continue
        meta.setdefault('job_id', meta_path.parent.name)
        if not is_visible(meta, since):
            continue
        jobs[meta['job_id']] = (meta_path, meta)
    for job_id in duplicate_job_ids([meta for _p, meta in jobs.values()]):
        del jobs[job_id]  # same file processed again: its vehicles are only imported once (from the newest run)
    return jobs


def sync_results(socketio=None):
    """Import new/changed finished NH5 jobs, drop jobs that were deleted. Returns a summary dict."""
    if nh5 is None:
        return {'enabled': False}
    with _sync_lock:
        jobs = _done_jobs(nh5.RESULT_DIR)
        imported = {r['job_id']: r for r in db.query('SELECT job_id, source_file, meta_mtime FROM nh5_imports')}
        added, removed, new_records = [], [], []

        for job_id, (meta_path, meta) in sorted(jobs.items(), key=lambda kv: kv[1][1].get('uploaded_at') or ''):
            mtime = max(meta_path.stat().st_mtime, (meta_path.parent / 'vehicles.json').stat().st_mtime)
            prev = imported.get(job_id)
            if prev and abs(float(prev['meta_mtime']) - mtime) < 1e-6:
                continue
            try:
                vehicles = json.loads((meta_path.parent / 'vehicles.json').read_text())
            except (OSError, ValueError):
                continue
            rows = job_to_rows(meta, vehicles if isinstance(vehicles, list) else [])
            source_file = source_file_for(meta)
            if prev:
                db.execute('DELETE FROM vehicle_events WHERE source_file = %s', (prev['source_file'],))
                db.execute('DELETE FROM nh5_imports WHERE job_id = %s', (job_id,))
            for i in range(0, len(rows), 500):
                db.executemany(vehicle_stream.insert_sql('update'), rows[i:i + 500])
            db.execute('INSERT INTO nh5_imports (job_id, source_file, meta_mtime, record_count) VALUES (%s, %s, %s, %s)',
                       (job_id, source_file, mtime, len(rows)))
            added.append({'jobId': job_id, 'sourceFile': source_file, 'records': len(rows)})
            if not prev:
                new_records.append(source_file)

        for job_id, prev in imported.items():
            if job_id not in jobs:
                db.execute('DELETE FROM vehicle_events WHERE source_file = %s', (prev['source_file'],))
                db.execute('DELETE FROM nh5_imports WHERE job_id = %s', (job_id,))
                removed.append(job_id)

        if (added or removed) and socketio is not None:
            socketio.emit('nh5LibraryChanged', {'imported': [a['jobId'] for a in added], 'removed': removed})
        if added or removed:
            print(f'[NH5] Library sync: imported {len(added)} job(s) '
                  f"({sum(a['records'] for a in added)} vehicles), removed {len(removed)} job(s).")

        # a newly finished video shows up on the VisionIQ dashboards right away (not on the initial bulk import)
        if socketio is not None and new_records and len(new_records) <= 3:
            for source_file in new_records:
                rows = db.query('SELECT * FROM vehicle_events WHERE source_file = %s ORDER BY id DESC LIMIT 5000',
                                (source_file,))
                records = [vehicle_stream.to_client_record(r) for r in rows]
                if records:
                    socketio.emit('newVehicleBatch', records)
                    socketio.emit('vehicleStreamStatus', {
                        'type': 'dataset_switched',
                        'fileName': vehicle_stream.ALL_RECORDS_LABEL,
                        'totalRows': vehicle_stream.get_total_database_record_count(),
                        'batchCount': len(records),
                        'totalPool': vehicle_stream.get_total_database_record_count(),
                        'timestamp': vehicle_stream.local_time_string(),
                        'overspeeding': sum(1 for r in records if r['isOverSpeed']),
                    })
        return {'enabled': True, 'jobs': len(jobs), 'imported': added, 'removed': removed}


def run_sync_loop(socketio, interval_s):
    while True:
        try:
            sync_results(socketio)
        except Exception as err:  # noqa: BLE001
            print('[NH5 Sync Error]:', err)
        socketio.sleep(interval_s)


# ---------------------------------------------------------------- read-only info for the API
def status():
    if nh5 is None:
        return {'enabled': False}
    jobs = nh5.JOBS
    with nh5.JOBS_LOCK:
        running = sum(1 for j in jobs.values() if getattr(j, 'status', None) not in ('done', 'error'))
    return {
        'enabled': True,
        'device': nh5.DEVICE_LABEL,
        'modelName': nh5.MODEL_NAME,
        'modelDescription': nh5.MODEL_DESCRIPTION,
        'modelArch': nh5.MODEL_ARCH,
        'classes': nh5.MODEL_CLASSES,
        'runningJobs': running,
        'importedJobs': len(db.query('SELECT job_id FROM nh5_imports')),
        'pages': {'upload': '/video-upload', 'library': '/video-library', 'live': '/live-camera',
                  'model': '/detection-model', 'roadMaps': '/road-maps', 'ontology': '/ontology'},
    }


def list_jobs():
    if nh5 is None:
        return []
    out = []
    for d, meta in visible_job_dirs():
        job_id = meta['job_id']
        out.append({
            'jobId': job_id,
            'originalFilename': meta.get('original_filename'),
            'uploadedAt': meta.get('uploaded_at'),
            'status': meta.get('status'),
            'numVehicles': meta.get('num_vehicles'),
            'vehicleTypes': meta.get('vehicle_types'),
            'numPeople': meta.get('num_people'),
            'plates': meta.get('plates') or [],
            'eventCounts': meta.get('event_counts') or {},
            'modelName': meta.get('model_name'),
            'sourceFile': source_file_for({**meta, 'job_id': job_id}),
            'thumbnail': f'/download/{job_id}/thumb.jpg' if (d / 'thumb.jpg').is_file() else None,
            'video': f'/media/{job_id}/annotated.mp4' if (d / 'annotated.mp4').is_file() else None,
            'report': f'/download/{job_id}/report.xlsx' if (d / 'report.xlsx').is_file() else None,
            'libraryPage': f'/video-library/{job_id}',
        })
    out.sort(key=lambda j: j.get('uploadedAt') or '', reverse=True)
    return out


def list_events(limit=500):
    """Accident / fire / road-work / behaviour events detected by NH5 across all Library jobs."""
    if nh5 is None:
        return []
    events = []
    for d, meta in counted_job_dirs():
        try:
            data = json.loads((d / 'events.json').read_text())
        except (OSError, ValueError):
            continue
        job_id = meta['job_id']
        for e in data if isinstance(data, list) else []:
            events.append({
                'jobId': job_id,
                'sourceFile': source_file_for({**meta, 'job_id': job_id}),
                'type': e.get('type'),
                'label': e.get('label'),
                'severity': e.get('severity'),
                'timestamp': e.get('timestamp'),
                'timeInVideoS': e.get('time_s'),
                'objectClass': e.get('object_class'),
                'plateNumber': e.get('plate_number'),
                'snapshot': _local_url(e.get('snapshot_url')),
                'clip': _local_url(e.get('clip_url')),
            })
    events.sort(key=lambda e: e.get('timestamp') or '', reverse=True)
    return events[:limit]


def start_sync_thread(socketio):
    interval = float(os.getenv('NH5_SYNC_INTERVAL', '10'))
    socketio.start_background_task(run_sync_loop, socketio, interval)
    return interval

