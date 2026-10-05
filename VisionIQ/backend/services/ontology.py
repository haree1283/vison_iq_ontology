"""Ontology / knowledge layer built from the Excel reports of the processed videos.

Schema (classes):  Traffic ontology -> Vehicle (Car, Bike, Bus, ...), Video, Camera, Event (Possible accident, ...),
                   Excel report
Instances:         one Vehicle per UNIQUE number plate across all videos (the same plate in several videos is one
                   node), vehicles whose plate was not read grouped per video and type, every video, its camera
                   (road map) and its report.xlsx, and every event.
Links:             Vehicle -seenIn-> Video, Vehicle -listedIn-> Excel report (sheet row), Vehicle -isA-> type,
                   Video -recordedBy-> Camera, Video -hasReport-> Excel report, Event -occurredIn-> Video,
                   Event -involves-> Vehicle (via the event's track / plate), Event -listedIn-> Excel report.
"""
from collections import defaultdict

from services import nh5_bridge, vehicle_stream
from services.report_reader import read_report


def type_label(raw):
    raw = str(raw or '').strip().lower()
    if raw == 'person':
        return 'Pedestrian'
    return vehicle_stream.canonical_vehicle_type(raw)


def _slug(text):
    return ''.join(ch if ch.isalnum() else '-' for ch in str(text).lower()).strip('-')


class Graph:
    def __init__(self):
        self.nodes = {}
        self.rels = {}

    def node(self, node_id, label, category, description='', **extra):
        n = self.nodes.get(node_id)
        if n is None:
            n = {'id': node_id, 'label': label, 'category': category, 'description': description,
                 'properties': {}, **extra}
            self.nodes[node_id] = n
        return n

    def rel(self, source, target, label, **props):
        key = (source, target, label)
        r = self.rels.get(key)
        if r is None:
            r = {'id': f'r{len(self.rels) + 1}', 'source': source, 'target': target, 'label': label,
                 'properties': {}, 'count': 0}
            self.rels[key] = r
        r['count'] += 1
        r['properties'].update(props)
        return r


def _schema(g):
    g.node('onto:root', 'NH5 Traffic Ontology', 'Ontology',
           'Knowledge model built from the Excel reports of every processed video.')
    for cid, label, desc in (
            ('class:Vehicle', 'Vehicle', 'A road user detected by the YOLOv8 model; identified by its number plate.'),
            ('class:Video', 'Video', 'An uploaded video or live camera session processed by the NH5 pipeline.'),
            ('class:Camera', 'Camera', 'The camera / road map a video was recorded with.'),
            ('class:Event', 'Event', 'Accident, fire, road work or behaviour event raised by the event rules.'),
            ('class:Report', 'Excel report', 'report.xlsx written for every processed video (Vehicles + Events sheets).')):
        g.node(cid, label, 'OntologyClass', desc)
        g.rel(cid, 'onto:root', 'definedIn')


def _type_class(g, label):
    cid = f'class:type:{_slug(label)}'
    if cid not in g.nodes:
        g.node(cid, label, 'OntologyClass', f'Vehicle class "{label}".')
        g.rel(cid, 'class:Vehicle', 'subClassOf')
    return cid


def _event_class(g, label):
    cid = f'class:event:{_slug(label)}'
    if cid not in g.nodes:
        g.node(cid, label, 'OntologyClass', f'Event class "{label}".')
        g.rel(cid, 'class:Event', 'subClassOf')
    return cid


def build_graph(job_id=None):
    g = Graph()
    _schema(g)
    plates = {}                      # plate -> aggregated vehicle info
    summary = defaultdict(int)

    for d, meta in nh5_bridge.counted_job_dirs():  # a video processed twice is one Video node
        jid = meta['job_id']
        if job_id and jid != job_id:
            continue
        if meta.get('status') != 'done':
            continue
        report = read_report(d)
        if report is None:
            continue
        summary['videos'] += 1
        fname = meta.get('original_filename') or jid
        is_live = str(fname).lower().startswith('live')

        video_id = f'video:{jid}'
        video = g.node(video_id, fname, 'Video', f"{'Live camera session' if is_live else 'Uploaded video'} processed "
                       f"at {str(meta.get('uploaded_at') or '').replace('T', ' ')}.",
                       media={'thumbnail': f'/media/{jid}/thumb.jpg' if (d / 'thumb.jpg').is_file() else None,
                              'video': f'/media/{jid}/annotated.mp4' if (d / 'annotated.mp4').is_file() else None},
                       jobId=jid)
        video['properties'].update({
            'Job ID': jid, 'Uploaded': str(meta.get('uploaded_at') or '').replace('T', ' '),
            'Frames': meta.get('total_frames'), 'Vehicles tracked': meta.get('num_vehicles'),
            'People': meta.get('num_people'), 'Model': meta.get('model_name'),
            'Processing FPS': meta.get('processing_fps'), 'Road map': meta.get('scene_name') or 'none',
        })
        g.rel(video_id, 'class:Video', 'instanceOf')

        cam_key = meta.get('scene_id') or f'job-{jid}'
        cam_label = meta.get('scene_name') or ('Browser camera' if is_live else f'Camera · {fname}')
        cam_id = f'camera:{cam_key}'
        cam = g.node(cam_id, cam_label, 'Camera', 'Camera / road map the video was recorded with.')
        if meta.get('latitude') or meta.get('longitude'):
            cam['properties'].update({'Latitude': meta.get('latitude'), 'Longitude': meta.get('longitude')})
        cam['properties']['Road map'] = meta.get('scene_name') or 'none'
        g.rel(video_id, cam_id, 'recordedBy')
        g.rel(cam_id, 'class:Camera', 'instanceOf')

        report_id = f'report:{jid}'
        rep = g.node(report_id, f'report.xlsx · {fname}', 'Report',
                     'Excel report of this video: one row per tracked vehicle (Vehicles sheet) and per event.',
                     media={'download': f'/download/{jid}/report.xlsx'}, jobId=jid)
        rep['properties'].update({'Vehicles sheet rows': len(report['vehicles']),
                                  'Events sheet rows': len(report['events']),
                                  'Rows with a number plate': sum(1 for v in report['vehicles'] if v['plate'])})
        g.rel(video_id, report_id, 'hasReport')
        g.rel(report_id, 'class:Report', 'instanceOf')
        summary['reports'] += 1

        track_plate = {}
        plate_rows = defaultdict(list)
        unread = defaultdict(list)
        for v in report['vehicles']:
            raw_type = str(v.get('vehicleType') or '').strip().lower()
            if raw_type in nh5_bridge.NON_ROAD_USER_CLASSES:
                continue
            vtype = type_label(raw_type)
            type_cid = _type_class(g, vtype)
            if not v['plate']:
                unread[vtype].append(v['row'])
                continue
            plate = v['plate']
            track_plate[str(v.get('id'))] = plate
            vid = f'vehicle:{plate}'
            info = plates.setdefault(plate, {'types': set(), 'videos': set(), 'sightings': 0, 'conf': 0.0,
                                             'first': None, 'last': None, 'image': None, 'plateImage': None,
                                             'rows': []})
            info['types'].add(vtype)
            info['videos'].add((jid, fname))
            info['sightings'] += 1
            try:
                info['conf'] = max(info['conf'], float(v.get('plateConfidence') or 0))
            except (TypeError, ValueError):
                pass
            ts = str(v.get('timestamp') or '')
            info['first'] = min(filter(None, [info['first'], ts]), default=None)
            info['last'] = max(filter(None, [info['last'], ts]), default=None)
            info['image'] = info['image'] or v.get('vehicleImage')
            info['plateImage'] = info['plateImage'] or v.get('plateImage')
            info['rows'].append(f"{fname} ({jid[:6]}) row {v['row']}")
            g.node(vid, plate, 'Vehicle', 'Vehicle identified by its (unique) number plate.')
            g.rel(vid, type_cid, 'isA')
            g.rel(vid, video_id, 'seenIn')
            plate_rows[plate].append(v['row'])

        for plate, rows in plate_rows.items():
            g.rel(f'vehicle:{plate}', report_id, 'listedIn', sheet='Vehicles', rows=', '.join(map(str, sorted(rows))))

        for vtype, rows in unread.items():
            gid = f'group:{jid}:{_slug(vtype)}'
            grp = g.node(gid, f'{len(rows)} × {vtype} (plate not read)', 'VehicleGroup',
                         f'{vtype} tracks in this video whose number plate could not be read.')
            grp['properties'].update({'Vehicle type': vtype, 'Tracks': len(rows), 'Video': fname,
                                      'Report rows': f'{len(rows)} rows in the Vehicles sheet'})
            g.rel(gid, _type_class(g, vtype), 'isA')
            g.rel(gid, video_id, 'seenIn')
            g.rel(gid, report_id, 'listedIn', sheet='Vehicles')
            summary['unreadTracks'] += len(rows)

        for e in report['events']:
            label = str(e.get('label') or 'Event')
            eid = f'event:{jid}:{e.get("id") or e["row"]}'
            t = e.get('timeInVideoS')
            ev = g.node(eid, f'{label} @ {t}s' if t is not None else label, 'Event', f'{label} detected in {fname}.',
                        media={'snapshot': e.get('snapshot'), 'clip': e.get('clip')}, jobId=jid)
            ev['properties'].update({'Severity': e.get('severity'), 'Timestamp': e.get('timestamp'),
                                     'Video time (s)': t, 'Object': e.get('objectClass'),
                                     'Track ID': e.get('trackId'), 'Details': e.get('details'),
                                     'Report row': f"Events sheet row {e['row']}"})
            g.rel(eid, _event_class(g, label), 'isA')
            g.rel(eid, video_id, 'occurredIn')
            g.rel(eid, report_id, 'listedIn', sheet='Events', rows=str(e['row']))
            plate = e.get('plate') or track_plate.get(str(e.get('trackId')))
            if plate and f'vehicle:{plate}' in g.nodes:
                g.rel(eid, f'vehicle:{plate}', 'involves')
            summary['events'] += 1

    for plate, info in plates.items():
        n = g.nodes[f'vehicle:{plate}']
        n['description'] = (f"Number plate {plate}: seen {info['sightings']} time(s) in {len(info['videos'])} video(s).")
        n['properties'].update({
            'Number plate': plate, 'Vehicle type': ', '.join(sorted(info['types'])),
            'Sightings': info['sightings'], 'Videos': ', '.join(f'{name} ({j[:6]})' for j, name in sorted(info['videos'])),
            'First seen': info['first'], 'Last seen': info['last'],
            'Best OCR confidence': f"{info['conf'] * 100:.0f}%" if info['conf'] else 'n/a',
            'Excel rows': '; '.join(info['rows'][:12]) + (' ...' if len(info['rows']) > 12 else ''),
        })
        n['media'] = {'vehicleImage': info['image'], 'plateImage': info['plateImage']}
        n['plate'] = plate
    summary['uniquePlates'] = len(plates)

    relationships = []
    for r in g.rels.values():
        if r['count'] > 1 and r['label'] in ('seenIn',):
            r['label'] = f"seenIn ×{r['count']}"
        relationships.append(r)
    return {'nodes': list(g.nodes.values()), 'relationships': relationships, 'summary': dict(summary),
            'jobId': job_id}
