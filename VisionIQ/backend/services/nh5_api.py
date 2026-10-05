"""JSON API over the NH5 Highway pipeline for VisionIQ's own pages (Video Upload, Live Camera, Video Library,
Road Maps, Detection Model). Every function drives NH5's own objects (VideoJob, LIVE, road-map helpers)
exactly the way NH5's HTML routes do -- same models, same processing, same Library folders on disk."""
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from services import nh5_bridge
from services.nh5_bridge import _local_url, is_visible, read_meta, source_file_for


class NH5Error(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _nh5():
    if nh5_bridge.nh5 is None:
        raise NH5Error('The NH5 detection models are not loaded on this server.', 503)
    return nh5_bridge.nh5


def _float_or_none(raw):
    raw = str(raw or '').strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _truthy(raw):
    return str(raw or '').strip().lower() in ('on', 'true', '1', 'yes')


def _job_dir(job_id):
    m = _nh5()
    if not job_id or not m.SCENE_ID_RE.fullmatch(str(job_id)):  # job ids are the same 12-hex format
        return None
    d = Path(m.RESULT_DIR) / job_id
    return d if d.is_dir() else None


# ---------------------------------------------------------------- model
def model_info():
    m = _nh5()
    return {
        'name': m.MODEL_NAME,
        'description': m.MODEL_DESCRIPTION,
        'architecture': m.MODEL_ARCH,
        'summary': m.MODEL_SUMMARY,
        'classes': list(m.MODEL_CLASSES),
        'device': m.DEVICE_LABEL,
        'modelFile': Path(m.MODEL_PATH).name,
        'ocrEngine': 'PaddleOCR (Indian number plates)',
        'tracker': 'ByteTrack',
        'eventTypes': [{'type': k, 'label': v['label'], 'severity': v['severity']} for k, v in m.EVENT_TYPES.items()],
    }


# ---------------------------------------------------------------- uploads
def start_upload(file_storage, form, host_url):
    m = _nh5()
    if file_storage is None or not file_storage.filename:
        raise NH5Error('Choose a video or image to upload.')
    ext = Path(file_storage.filename).suffix.lower()
    allowed = m.ALLOWED_EXT | m.IMAGE_EXT
    if ext not in allowed:
        raise NH5Error(f"Unsupported file type {ext or '(none)'}. Allowed: {', '.join(sorted(allowed))}")
    scene_id = str(form.get('scene_id') or form.get('sceneId') or '').strip() or None
    if scene_id and m._scene_dir(scene_id) is None:
        raise NH5Error('Road map not found.', 404)

    job_id = uuid.uuid4().hex[:12]
    dest = Path(m.UPLOAD_DIR) / f'{job_id}{ext}'
    file_storage.save(dest)
    thorough = _truthy(form.get('thorough'))
    if not _truthy(form.get('force')):
        # the same file with the same road map and mode was already processed: show that result instead of
        # running the model again and adding a second copy to the Library ('force' re-processes anyway)
        previous = nh5_bridge.find_processed_duplicate(dest, scene_id, thorough)
        if previous is not None:
            dest.unlink(missing_ok=True)
            return {**previous, 'originalFilename': file_storage.filename, 'duplicate': True,
                    'stream': f"/stream/{previous['jobId']}"}
    job = m.VideoJob(job_id, dest, original_filename=file_storage.filename, thorough=thorough,
                     latitude=str(form.get('latitude') or '').strip(),
                     longitude=str(form.get('longitude') or '').strip(),
                     meters_per_pixel=_float_or_none(form.get('meters_per_pixel') or form.get('metersPerPixel')),
                     speed_limit=_float_or_none(form.get('speed_limit') or form.get('speedLimit')),
                     base_url=host_url, scene_id=scene_id)
    with m.JOBS_LOCK:
        m.JOBS[job_id] = job
    job.start()
    return {'jobId': job_id, 'originalFilename': file_storage.filename, 'stream': f'/stream/{job_id}'}


def _events_on_disk(d):
    try:
        data = json.loads((d / 'events.json').read_text())
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def job_status(job_id):
    """Live progress while processing (same payload as NH5's /status), or the finished result from disk."""
    m = _nh5()
    job = m.JOBS.get(job_id)
    if job is not None:
        snap = job.snapshot()
        snap.update(jobId=job_id, originalFilename=job.original_filename, uploadedAt=job.uploaded_at,
                    sceneName=job.scene_name, thorough=job.thorough, stream=f'/stream/{job_id}')
        return snap
    d = _job_dir(job_id)
    meta = read_meta(d) if d is not None else None
    if meta is None or not is_visible(meta):
        raise NH5Error('Video not found.', 404)
    events = _events_on_disk(d)
    return {
        'jobId': job_id, 'status': meta.get('status'), 'error': meta.get('error'),
        'originalFilename': meta.get('original_filename'), 'uploadedAt': meta.get('uploaded_at'),
        'sceneName': meta.get('scene_name'), 'thorough': meta.get('thorough'),
        'frame_idx': meta.get('frame_idx'), 'total_frames': meta.get('total_frames'),
        'plates': meta.get('plates') or [], 'plate_counts': {}, 'num_vehicles': meta.get('num_vehicles') or 0,
        'vehicle_types': meta.get('vehicle_types') or {}, 'num_people': meta.get('num_people') or 0,
        'processing_fps': meta.get('processing_fps'), 'ms_per_frame': None, 'eta_secs': None,
        'events': [{k: e.get(k) for k in ('id', 'type', 'label', 'severity', 'time_s', 'track_id', 'object_class')}
                   for e in events[-25:]],
        'num_events': len(events), 'detection_counts': {}, 'stream': None,
    }


# ---------------------------------------------------------------- library
def _job_files(job_id, d):
    return {
        'thumbnail': f'/media/{job_id}/thumb.jpg' if (d / 'thumb.jpg').is_file() else None,
        'video': f'/media/{job_id}/annotated.mp4' if (d / 'annotated.mp4').is_file() else None,
        'report': f'/download/{job_id}/report.xlsx' if (d / 'report.xlsx').is_file() else None,
    }


def _summary(meta, d):
    job_id = meta['job_id']
    return {
        'jobId': job_id,
        'originalFilename': meta.get('original_filename'),
        'uploadedAt': meta.get('uploaded_at'),
        'status': meta.get('status'),
        'error': meta.get('error'),
        'kind': 'live' if str(meta.get('original_filename') or '').lower().startswith('live') else 'upload',
        'sceneName': meta.get('scene_name'),
        'numVehicles': meta.get('num_vehicles') or 0,
        'vehicleTypes': meta.get('vehicle_types') or {},
        'numPeople': meta.get('num_people') or 0,
        'plates': meta.get('plates') or [],
        'eventCounts': meta.get('event_counts') or {},
        'totalFrames': meta.get('total_frames') or meta.get('frame_idx'),  # live sessions have no fixed total
        'processingFps': meta.get('processing_fps'),
        'modelName': meta.get('model_name'),
        'latitude': meta.get('latitude') or None,
        'longitude': meta.get('longitude') or None,
        'sourceFile': source_file_for(meta),
        **_job_files(job_id, d),
    }


def library_list():
    m = _nh5()
    items = [_summary(meta, d) for d, meta in nh5_bridge.visible_job_dirs()]
    on_disk = {i['jobId'] for i in items}
    with m.JOBS_LOCK:
        running = [j for jid, j in m.JOBS.items() if jid not in on_disk]
    for job in running:  # just uploaded, nothing written to the Library folder yet
        snap = job.snapshot()
        items.append({'jobId': job.id, 'originalFilename': job.original_filename, 'uploadedAt': job.uploaded_at,
                      'status': snap['status'], 'error': snap['error'], 'kind': 'upload', 'sceneName': job.scene_name,
                      'numVehicles': snap['num_vehicles'], 'vehicleTypes': snap['vehicle_types'],
                      'numPeople': snap['num_people'], 'plates': snap['plates'], 'eventCounts': {},
                      'totalFrames': snap['total_frames'], 'processingFps': snap['processing_fps'],
                      'thumbnail': None, 'video': None, 'report': None})
    live = m.LIVE.snapshot()
    for item in items:
        job = m.JOBS.get(item['jobId'])
        if job is not None:
            item['status'] = job.snapshot()['status']
        if live.get('job_id') == item['jobId']:
            item['kind'] = 'live'
            if live.get('running'):
                item['status'] = 'live'
    items.sort(key=lambda i: i.get('uploadedAt') or '', reverse=True)
    return items


def _vehicle_out(job_id, v):
    plate = v.get('plate_number')
    return {
        'id': v.get('id'),
        'trackId': v.get('id'),
        'timestamp': v.get('timestamp'),
        'lastSeen': v.get('last_seen'),
        'timesSeen': v.get('times_seen'),
        'vehicleType': v.get('vehicle_type'),
        'plate': plate if plate and plate != 'not read' else None,
        'plateConfidence': v.get('plate_confidence'),
        'vehicleImage': _local_url(v.get('vehicle_image_url')),
        'plateImage': _local_url(v.get('plate_image_url')),
        'speedKmh': v.get('speed_kmh'),
        'speedLimitKmh': v.get('speed_limit_kmh'),
        'overSpeed': v.get('over_speed'),
        'events': v.get('events') or [],
    }


def unique_plates(vehicles):
    """One entry per distinct number plate (the same plate on several tracks is one vehicle)."""
    plates = {}
    for v in vehicles:
        if not v['plate']:
            continue
        p = plates.setdefault(v['plate'], {'plate': v['plate'], 'vehicleTypes': [], 'tracks': 0, 'plateConfidence': 0,
                                           'firstSeen': v['timestamp'], 'lastSeen': v['lastSeen'] or v['timestamp'],
                                           'vehicleImage': v['vehicleImage'], 'plateImage': v['plateImage']})
        p['tracks'] += 1
        if v['vehicleType'] and v['vehicleType'] not in p['vehicleTypes']:
            p['vehicleTypes'].append(v['vehicleType'])
        p['plateConfidence'] = max(p['plateConfidence'], float(v['plateConfidence'] or 0))
        p['firstSeen'] = min(filter(None, [p['firstSeen'], v['timestamp']]), default=None)
        p['lastSeen'] = max(filter(None, [p['lastSeen'], v['lastSeen'], v['timestamp']]), default=None)
    return sorted(plates.values(), key=lambda p: p['firstSeen'] or '')


def library_detail(job_id):
    d = _job_dir(job_id)
    meta = read_meta(d) if d is not None else None
    if meta is None:
        if job_id in _nh5().JOBS:  # still processing, no Library entry yet
            return {'jobId': job_id, 'status': job_status(job_id)['status'], 'processing': True}
        raise NH5Error('Video not found.', 404)
    if not is_visible(meta):
        raise NH5Error('Video not found.', 404)
    try:
        raw_vehicles = json.loads((d / 'vehicles.json').read_text())
    except (OSError, ValueError):
        raw_vehicles = []
    vehicles = [_vehicle_out(job_id, v) for v in raw_vehicles if isinstance(v, dict)]
    events = [{
        'id': e.get('id'), 'type': e.get('type'), 'label': e.get('label'), 'severity': e.get('severity'),
        'timeInVideoS': e.get('time_s'), 'timestamp': e.get('timestamp'), 'trackId': e.get('track_id'),
        'objectClass': e.get('object_class'), 'plateNumber': e.get('plate_number'), 'details': e.get('details'),
        'snapshot': _local_url(e.get('snapshot_url')), 'clip': _local_url(e.get('clip_url')),
    } for e in _events_on_disk(d)]
    detail = _summary(meta, d)
    detail.update(vehicles=vehicles, events=events, uniquePlates=unique_plates(vehicles),
                  eventRules=meta.get('event_rules') or {}, metersPerPixel=meta.get('meters_per_pixel'),
                  speedLimit=meta.get('speed_limit'), processing=meta.get('status') not in ('done', 'error'))
    return detail


def delete_job(job_id, socketio=None):
    """Same rules as NH5's Library delete: not while it is still processing or live."""
    m = _nh5()
    d = _job_dir(job_id)
    meta = read_meta(d) if d is not None else None
    if meta is None or not is_visible(meta):
        raise NH5Error('Video not found.', 404)
    job = m.JOBS.get(job_id)
    thread = getattr(job, 'thread', None)
    if thread is not None and thread.is_alive():
        raise NH5Error("Can't delete a video that's still processing.", 409)
    if m.LIVE.job_id == job_id and m.LIVE.running:
        raise NH5Error("Can't delete a live session that's still running.", 409)
    with m.JOBS_LOCK:
        m.JOBS.pop(job_id, None)
    shutil.rmtree(d, ignore_errors=True)
    src = next(Path(m.UPLOAD_DIR).glob(f'{job_id}.*'), None)
    if src:
        src.unlink(missing_ok=True)
    nh5_bridge.sync_results(socketio)  # drop its vehicles from the VisionIQ database right away
    return {'deleted': job_id}


# ---------------------------------------------------------------- live camera
def live_start(data, host_url):
    m = _nh5()
    scene_id = str(data.get('sceneId') or data.get('scene_id') or '').strip() or None
    if scene_id and m._scene_dir(scene_id) is None:
        raise NH5Error('Road map not found.', 404)
    ok, error, job_id = m.LIVE.start(_truthy(data.get('thorough')), str(data.get('latitude') or '').strip(),
                                     str(data.get('longitude') or '').strip(),
                                     _float_or_none(data.get('metersPerPixel') or data.get('meters_per_pixel')),
                                     _float_or_none(data.get('speedLimit') or data.get('speed_limit')),
                                     host_url, scene_id=scene_id)
    if not ok:
        raise NH5Error(error or 'Could not start the live session.', 409)
    return {'jobId': job_id, 'websocket': '/live_ws'}


def live_stop():
    _nh5().LIVE.stop()
    return {'stopped': True}


def live_status():
    return _nh5().LIVE.snapshot()


# ---------------------------------------------------------------- road maps (scenes)
def _scene_out(data):
    sid = data['id']
    return {
        'id': sid, 'name': data.get('name'), 'zones': data.get('zones') or [], 'lanes': data.get('lanes') or [],
        'frameSize': data.get('frame_size'), 'createdAt': data.get('created_at'), 'updatedAt': data.get('updated_at'),
        'frameUrl': f'/scenes/{sid}/frame.jpg', 'previewUrl': f'/scenes/{sid}/preview.jpg' if data.get('has_preview') else None,
        'zoneCount': len(data.get('zones') or []), 'laneCount': len(data.get('lanes') or []),
    }


def scenes_list():
    return [_scene_out(s) for s in _nh5().list_scenes()]


def scene_get(scene_id):
    m = _nh5()
    d = m._scene_dir(scene_id)
    data = m._read_scene_data(d) if d is not None else None
    if data is None:
        raise NH5Error('Road map not found.', 404)
    data['has_preview'] = (d / 'preview.jpg').is_file()
    return _scene_out(data)


def scene_create(file_storage, name):
    m = _nh5()
    if file_storage is None or not file_storage.filename:
        raise NH5Error('Choose an image or video from the camera.')
    ext = Path(file_storage.filename).suffix.lower()
    if ext not in m.ALLOWED_EXT | m.IMAGE_EXT:
        raise NH5Error(f'Unsupported file type {ext!r}.')
    scene_id = uuid.uuid4().hex[:12]
    d = Path(m.SCENE_DIR) / scene_id
    d.mkdir(parents=True)
    src = d / f'source{ext}'
    file_storage.save(src)
    frame = m._grab_frame(src)
    src.unlink(missing_ok=True)
    if frame is None:
        shutil.rmtree(d, ignore_errors=True)
        raise NH5Error("Couldn't read a frame from that file.")
    m.cv2.imwrite(str(d / 'frame.jpg'), frame, [int(m.cv2.IMWRITE_JPEG_QUALITY), 92])
    now = datetime.now().isoformat(timespec='seconds')
    data = {'name': str(name or '').strip()[:80] or 'Untitled road map', 'zones': [], 'lanes': [],
            'frame_size': [frame.shape[1], frame.shape[0]], 'created_at': now, 'updated_at': now}
    (d / 'scene.json').write_text(json.dumps(data, indent=2))
    return scene_get(scene_id)


def scene_save(scene_id, payload):
    m = _nh5()
    d = m._scene_dir(scene_id)
    data = m._read_scene_data(d) if d is not None else None
    if data is None:
        raise NH5Error('Road map not found.', 404)
    try:
        cleaned = m.clean_scene_data(payload)
    except ValueError as exc:
        raise NH5Error(str(exc)) from exc
    data.pop('id', None)
    data.update(cleaned)
    data['updated_at'] = datetime.now().isoformat(timespec='seconds')
    (d / 'scene.json').write_text(json.dumps(data, indent=2))
    m._render_scene_preview(d, data)
    return scene_get(scene_id)


def scene_delete(scene_id):
    m = _nh5()
    d = m._scene_dir(scene_id)
    if d is None:
        raise NH5Error('Road map not found.', 404)
    shutil.rmtree(d, ignore_errors=True)
    return {'deleted': scene_id}
