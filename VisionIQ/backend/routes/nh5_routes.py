from flask import Blueprint, current_app, jsonify, request

from services import nh5_api, ontology, tracking
from services.nh5_api import NH5Error

nh5_routes = Blueprint('nh5_routes', __name__)

UPLOAD_LIMIT = 2 * 1024 * 1024 * 1024  # same 2 GB limit as the NH5 website


def _socketio():
    return current_app.extensions.get('socketio')


@nh5_routes.before_request
def allow_large_uploads():
    if request.method == 'POST' and request.path.rstrip('/') in ('/api/nh5/videos', '/api/nh5/scenes'):
        request.max_content_length = UPLOAD_LIMIT


@nh5_routes.errorhandler(NH5Error)
def nh5_error(err):
    return jsonify(success=False, message=str(err)), err.status


# ---- detection model
@nh5_routes.get('/api/nh5/model')
def model():
    return jsonify(success=True, model=nh5_api.model_info())


# ---- videos: upload, progress, library
@nh5_routes.post('/api/nh5/videos')
def upload_video():
    result = nh5_api.start_upload(request.files.get('video'), request.form, request.host_url)
    return jsonify(success=True, **result), 202


@nh5_routes.get('/api/nh5/videos')
def list_videos():
    videos = nh5_api.library_list()
    return jsonify(success=True, count=len(videos), videos=videos)


@nh5_routes.get('/api/nh5/videos/<job_id>')
def video_detail(job_id):
    return jsonify(success=True, video=nh5_api.library_detail(job_id))


@nh5_routes.get('/api/nh5/videos/<job_id>/status')
def video_status(job_id):
    return jsonify(success=True, status=nh5_api.job_status(job_id))


@nh5_routes.delete('/api/nh5/videos/<job_id>')
def delete_video(job_id):
    return jsonify(success=True, **nh5_api.delete_job(job_id, _socketio()))


# ---- live camera (frames arrive over the /live_ws websocket of the NH5 app)
@nh5_routes.post('/api/nh5/live/start')
def live_start():
    return jsonify(success=True, **nh5_api.live_start(request.get_json(silent=True) or {}, request.host_url))


@nh5_routes.post('/api/nh5/live/stop')
def live_stop():
    return jsonify(success=True, **nh5_api.live_stop())


@nh5_routes.get('/api/nh5/live/status')
def live_status():
    return jsonify(success=True, status=nh5_api.live_status())


# ---- road maps
@nh5_routes.get('/api/nh5/scenes')
def scenes():
    items = nh5_api.scenes_list()
    return jsonify(success=True, count=len(items), scenes=items)


@nh5_routes.post('/api/nh5/scenes')
def scene_create():
    return jsonify(success=True, scene=nh5_api.scene_create(request.files.get('source'), request.form.get('name'))), 201


@nh5_routes.get('/api/nh5/scenes/<scene_id>')
def scene_get(scene_id):
    return jsonify(success=True, scene=nh5_api.scene_get(scene_id))


@nh5_routes.put('/api/nh5/scenes/<scene_id>')
def scene_save(scene_id):
    return jsonify(success=True, scene=nh5_api.scene_save(scene_id, request.get_json(silent=True)))


@nh5_routes.delete('/api/nh5/scenes/<scene_id>')
def scene_delete(scene_id):
    return jsonify(success=True, **nh5_api.scene_delete(scene_id))


# ---- ontology built from the videos' Excel reports
@nh5_routes.get('/api/ontology/graph')
def ontology_graph():
    return jsonify(success=True, **ontology.build_graph(request.args.get('jobId') or None))


# ---- vehicle tracking by unique number plate (Vehicle Information page)
@nh5_routes.get('/api/vehicles/incidents')
def vehicle_incidents():
    items = tracking.incidents()
    return jsonify(success=True, count=len(items), incidents=items)


@nh5_routes.get('/api/cameras')
def cameras():
    return jsonify(success=True, cameras=tracking.cameras())


@nh5_routes.get('/api/vehicles/<plate>')
def vehicle_by_plate(plate):
    found = tracking.vehicle(plate)
    if found is None:
        return jsonify(success=False, message=f'No vehicle with plate {plate}.'), 404
    return jsonify(success=True, vehicle=found)
