"""Vehicle tracking by unique number plate for the Vehicle Information page: every plate read by the NH5 model,
with each video / camera it was seen in (observations), built from the videos' Excel reports."""
from collections import defaultdict

from services import nh5_bridge
from services.ontology import type_label
from services.report_reader import read_report


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _conf(value):
    f = _num(value)
    if f is None:
        return None
    return f / 100.0 if f > 1 else f


def _camera_for(meta):
    jid = meta['job_id']
    fname = meta.get('original_filename') or jid
    is_live = str(fname).lower().startswith('live')
    return {
        'id': f"CAM-{(meta.get('scene_id') or jid)[:8].upper()}",
        'name': meta.get('scene_name') or ('Browser camera' if is_live else fname),
        'latitude': _num(meta.get('latitude')),
        'longitude': _num(meta.get('longitude')),
        'status': 'Active',
        'sceneId': meta.get('scene_id'),
    }


def collect():
    """-> (vehicles by plate, cameras by id)"""
    vehicles, cameras = {}, {}
    for d, meta in nh5_bridge.visible_job_dirs():
        if meta.get('status') != 'done':
            continue
        report = read_report(d)
        if report is None:
            continue
        cam = _camera_for(meta)
        cameras.setdefault(cam['id'], cam)
        jid = meta['job_id']
        track_events = defaultdict(list)
        for e in report['events']:
            if e.get('trackId') is not None:
                track_events[str(e['trackId'])].append(e)
            if e.get('plate'):
                track_events[f"plate:{e['plate']}"].append(e)
        for v in report['vehicles']:
            plate = v['plate']
            raw_type = str(v.get('vehicleType') or '').strip().lower()
            if not plate or raw_type in nh5_bridge.NON_ROAD_USER_CLASSES:
                continue
            events = track_events.get(str(v.get('id')), []) + track_events.get(f'plate:{plate}', [])
            veh = vehicles.setdefault(plate, {'vehicleNumber': plate, 'vehicleType': type_label(raw_type),
                                              'observations': [], 'events': []})
            veh['events'].extend(e.get('label') for e in events if e.get('label'))
            veh['observations'].append({
                'cameraId': cam['id'],
                'timestamp': str(v.get('timestamp') or meta.get('uploaded_at') or '').replace(' ', 'T'),
                'latitude': _num(v.get('latitude')) if _num(v.get('latitude')) is not None else cam['latitude'],
                'longitude': _num(v.get('longitude')) if _num(v.get('longitude')) is not None else cam['longitude'],
                'location': cam['name'],
                'detectionType': events[0]['label'] if events else 'Vehicle detected',
                'confidence': _conf(v.get('plateConfidence')),
                'imageUrl': v.get('vehicleImage') or '',
                'plateImageUrl': v.get('plateImage') or '',
                'videoUrl': f'/media/{jid}/annotated.mp4',
                'jobId': jid,
                'video': meta.get('original_filename'),
                'reportRow': v['row'],
            })
    for veh in vehicles.values():
        veh['observations'].sort(key=lambda o: o['timestamp'])
        first = veh['observations'][0]
        cams = {o['cameraId'] for o in veh['observations']}
        veh['incidentType'] = veh['events'][0] if veh['events'] else 'Vehicle detected'
        veh['incidentTime'] = first['timestamp']
        veh['collisionCamera'] = first['cameraId']
        veh['status'] = 'Tracking' if len(cams) > 1 or len({o['jobId'] for o in veh['observations']}) > 1 else 'Detected'
        veh['sightings'] = len(veh['observations'])
        veh['videos'] = sorted({o['video'] for o in veh['observations'] if o['video']})
        veh['events'] = sorted(set(veh['events']))
    return vehicles, cameras


def incidents():
    vehicles, _ = collect()
    return sorted(vehicles.values(), key=lambda v: v['incidentTime'] or '', reverse=True)


def cameras():
    _, cams = collect()
    return list(cams.values())


def vehicle(plate):
    vehicles, _ = collect()
    key = ''.join(ch for ch in str(plate).upper() if ch.isalnum())
    for p, v in vehicles.items():
        if ''.join(ch for ch in p.upper() if ch.isalnum()) == key:
            return v
    return None
