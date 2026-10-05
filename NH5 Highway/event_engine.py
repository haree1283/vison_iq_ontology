#!/usr/bin/env python3
"""Rule-based traffic event engine: turns per-frame tracked detections into
road-safety events.

The detector only knows *objects* (person, car, traffic_cone, ...).
Behaviours -- a person standing on the roadside, jaywalking, a lane change,
wrong-side driving -- can't be seen in a single frame, so they're decided
here from each track's motion over time plus a per-camera road map
("scene"):

  zones   road / roadside / crossing (zebra) polygons
  lanes   one polygon per lane + an arrow for its allowed travel direction

Scene points are stored normalized to 0..1 of the frame size, so a map drawn
on one resolution applies to the same camera at any other resolution.

The zone/lane rules only make sense for a FIXED camera -- on a moving camera
(dashcam) the map slides off the road. With no scene, only the class-based
events (accident, road construction) run, and only when the loaded model
actually has those classes.

Positions use each box's bottom-centre ("foot point": where a person stands
or a vehicle touches the road). Speeds are measured in box-heights per
second rather than pixels, so one set of thresholds works for objects near
and far from the camera.
"""
import json
import math
from collections import defaultdict, deque, namedtuple
from pathlib import Path

import cv2
import numpy as np

EVENT_TYPES = {
    "person_walking_roadside": {"label": "Person walking on roadside", "severity": "info"},
    "person_standing_roadside": {"label": "Person standing on roadside", "severity": "info"},
    "pedestrian_crossing_zebra": {"label": "Pedestrian crossing at zebra crossing", "severity": "info"},
    "jaywalking": {"label": "Pedestrian crossing outside zebra crossing", "severity": "warning"},
    "lane_change": {"label": "Lane change", "severity": "info"},
    "wrong_side_driving": {"label": "Wrong-side driving", "severity": "critical"},
    "stopped_vehicle": {"label": "Vehicle stopped on carriageway", "severity": "warning"},
    "accident": {"label": "Possible accident", "severity": "critical"},
    "fire": {"label": "Fire accident (vehicle / road fire)", "severity": "critical"},
    "road_construction": {"label": "Construction / work zone on road", "severity": "warning"},
}

ZONE_TYPES = ("road", "roadside", "crossing")

PERSON_CLASS = "person"
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "auto", "bicycle"}
RIDEABLE_CLASSES = {"bicycle", "motorcycle", "auto"}  # a person overlapping one of these is its rider
ACCIDENT_CLASSES = {"accident_scene", "damaged_vehicle"}
FIRE_CLASSES = {"fire_accident"}
CONSTRUCTION_OBJECT_CLASSES = {"traffic_cone", "barricade"}
CONSTRUCTION_ZONE_CLASSES = {"road_construction"}

# --- thresholds (seconds / box-heights per second) ---------------------------
ZONE_DWELL_SECS = 1.0            # a person must hold a zone this long before a zone event fires
RUN_GAP_SECS = 0.2               # zone flicker tolerated inside a continuous run (foot-point jitter at edges)
TRACK_TIMEOUT_SECS = 2.0         # forget a track unseen for this long
WALK_SPEED_BH = 0.5              # >= this = walking (a walking adult covers ~0.8 body heights/sec)
STILL_SPEED_BH = 0.2             # <= this = not moving (allows detector box jitter)
STANDING_SECS = 3.0
CROSS_MIN_MOVE_BH = 0.75         # jaywalking needs real movement on the carriageway, not a box grazing it
RIDER_OVERLAP = 0.3              # fraction of a person box covered by a bike/auto box to count as its rider
LANE_STABLE_SECS = 0.5           # hysteresis: a vehicle must hold a new lane this long to count as a change
WRONG_SIDE_WINDOW_SECS = 1.0
WRONG_SIDE_MIN_SPEED_BH = 0.3    # ignore direction of near-stationary vehicles (jitter has no direction)
WRONG_SIDE_COS = -0.5            # motion within 60 degrees of straight against the lane arrow
WRONG_SIDE_SECS = 1.0
STOPPED_SPEED_BH = 0.05
STOPPED_SECS = 10.0
ACCIDENT_WINDOW_SECS = 1.0
ACCIDENT_MIN_RATIO = 0.6         # accident class present in >= 60% of the window's frames
ACCIDENT_MIN_CONF = 0.50         # weak accident boxes (a normal car close up / side view scored 0.34-0.68, briefly)
                                 # never count; tested: removes that false alarm, all 3 real CCTV crashes still alert
FIRE_WINDOW_SECS = 1.0
FIRE_MIN_RATIO = 0.6             # fire present in >= 60% of the window's frames
FIRE_MIN_CONF = 0.45             # dust/smoke right after a crash scores ~0.3-0.58 as fire; real flames score higher
CONSTRUCTION_WINDOW_SECS = 2.0
CONSTRUCTION_MIN_RATIO = 0.6
CONSTRUCTION_MIN_OBJECTS = 2     # one lone cone isn't a work zone
SCENE_EVENT_COOLDOWN_SECS = 30.0  # accident / construction re-alert interval while still present
ALERT_DISPLAY_SECS = 4.0

SEVERITY_COLORS = {"info": (200, 140, 40), "warning": (0, 140, 255), "critical": (40, 40, 230)}  # BGR
ZONE_COLORS = {"road": (150, 150, 150), "roadside": (80, 190, 80), "crossing": (255, 255, 255)}
LANE_COLOR = (255, 200, 0)


def clean_scene_data(data):
    """Validate + normalize a scene dict (as posted by the road-map editor).
    Returns {name, zones, lanes}; raises ValueError with a user-facing
    message on anything malformed."""
    if not isinstance(data, dict):
        raise ValueError("scene must be a JSON object")

    def points(raw, what):
        if not isinstance(raw, list) or len(raw) < 3:
            raise ValueError(f"{what} needs at least 3 points")
        out = []
        try:
            for p in raw:
                x, y = float(p[0]), float(p[1])
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise ValueError(f"{what} has a point outside the frame")
                out.append([round(x, 5), round(y, 5)])
        except (TypeError, IndexError):
            raise ValueError(f"{what} has a malformed point")
        return out

    zones = []
    for i, z in enumerate(data.get("zones") or []):
        ztype = z.get("type") if isinstance(z, dict) else None
        if ztype not in ZONE_TYPES:
            raise ValueError(f"zone {i + 1}: unknown type {ztype!r}")
        zones.append({"type": ztype, "points": points(z.get("points"), f"{ztype} zone {i + 1}")})

    lanes = []
    for i, lane in enumerate(data.get("lanes") or []):
        if not isinstance(lane, dict):
            raise ValueError(f"lane {i + 1} is malformed")
        name = str(lane.get("name") or f"Lane {i + 1}").strip()[:40] or f"Lane {i + 1}"
        cleaned = {"name": name, "points": points(lane.get("points"), name)}
        direction = lane.get("direction")
        if direction:
            try:
                (x0, y0), (x1, y1) = [(float(a), float(b)) for a, b in direction]
            except (TypeError, ValueError):
                raise ValueError(f"{name}: direction needs exactly 2 points")
            if (x0, y0) == (x1, y1):
                raise ValueError(f"{name}: direction start and end are the same point")
            cleaned["direction"] = [[round(x0, 5), round(y0, 5)], [round(x1, 5), round(y1, 5)]]
        lanes.append(cleaned)

    names = [lane["name"] for lane in lanes]
    if len(set(names)) != len(names):
        raise ValueError("lane names must be unique")

    name = str(data.get("name") or "").strip()[:80] or "Untitled road map"
    return {"name": name, "zones": zones, "lanes": lanes}


def _inside(poly, pt):
    return cv2.pointPolygonTest(poly, (float(pt[0]), float(pt[1])), False) >= 0


class Scene:
    """A camera's road map. Call fit(w, h) before any lookup; it rescales the
    normalized points to that frame size (cached until the size changes)."""

    def __init__(self, data):
        self.id = data.get("id")
        self.name = data.get("name") or "Untitled road map"
        self.zones = data.get("zones") or []
        self.lanes = data.get("lanes") or []
        self._size = None
        self._zone_px = []
        self._lane_px = []

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def has_zone(self, ztype):
        return any(z["type"] == ztype for z in self.zones)

    @property
    def has_carriageway(self):
        return bool(self.lanes) or self.has_zone("road") or self.has_zone("crossing")

    @property
    def has_directions(self):
        return any(lane.get("direction") for lane in self.lanes)

    def fit(self, w, h):
        if self._size == (w, h):
            return
        self._size = (w, h)

        def px(points):
            return np.array([[x * w, y * h] for x, y in points], dtype=np.float32)

        self._zone_px = [(z["type"], px(z["points"])) for z in self.zones]
        self._lane_px = []
        for lane in self.lanes:
            vec = None
            if lane.get("direction"):
                (x0, y0), (x1, y1) = lane["direction"]
                v = np.array([(x1 - x0) * w, (y1 - y0) * h], dtype=np.float64)
                vec = v / np.linalg.norm(v)
            self._lane_px.append((lane["name"], px(lane["points"]), vec))

    def lane_at(self, pt):
        for name, poly, _ in self._lane_px:
            if _inside(poly, pt):
                return name
        return None

    def lane_direction(self, name):
        for lane_name, _, vec in self._lane_px:
            if lane_name == name:
                return vec
        return None

    def zone_at(self, pt):
        """'crossing' beats 'road' (a zebra crossing sits on the road), a lane
        counts as 'road', and 'roadside' only applies off the carriageway."""
        types = {ztype for ztype, poly in self._zone_px if _inside(poly, pt)}
        if "crossing" in types:
            return "crossing"
        if "road" in types or self.lane_at(pt) is not None:
            return "road"
        if "roadside" in types:
            return "roadside"
        return None

    def draw(self, img):
        h, w = img.shape[:2]
        self.fit(w, h)
        thick = max(2, w // 640)
        overlay = img.copy()
        for ztype, poly in self._zone_px:
            cv2.fillPoly(overlay, [poly.astype(np.int32)], ZONE_COLORS[ztype])
        cv2.addWeighted(overlay, 0.18, img, 0.82, 0, dst=img)
        for ztype, poly in self._zone_px:
            cv2.polylines(img, [poly.astype(np.int32)], True, ZONE_COLORS[ztype], thick, cv2.LINE_AA)
        font_scale = max(0.5, w / 1920)
        for lane in self.lanes:
            _, poly, _ = next(item for item in self._lane_px if item[0] == lane["name"])
            cv2.polylines(img, [poly.astype(np.int32)], True, LANE_COLOR, thick, cv2.LINE_AA)
            cx, cy = poly.mean(axis=0)
            cv2.putText(img, lane["name"], (int(cx) - 30, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        LANE_COLOR, thick, cv2.LINE_AA)
            if lane.get("direction"):
                (x0, y0), (x1, y1) = lane["direction"]
                cv2.arrowedLine(img, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), LANE_COLOR,
                                thick + 1, cv2.LINE_AA, tipLength=0.2)


_Sample = namedtuple("_Sample", "frame fx fy bh zone lane rider")


class _Track:
    def __init__(self, track_id, cls, kind, maxlen):
        self.id = track_id
        self.cls = cls
        self.kind = kind  # "person" | "vehicle"
        self.hist = deque(maxlen=maxlen)
        self.box = None
        self.last_frame = -1
        self.fired = set()        # event types already emitted for this track
        self.status = None        # short state shown next to the box label
        self.stable_lane = None   # lane-change hysteresis
        self.cand_lane = None
        self.cand_count = 0
        self.against_count = 0    # consecutive frames moving against the lane arrow
        self.lane_change_until = -1


def _overlap_ratio(a, b):
    """Fraction of box a's area covered by box b."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return ix * iy / area


def _foot(box):
    return (box[0] + box[2]) / 2, box[3]


class EventEngine:
    """One per video/camera session.

    update(frame_idx, w, h, detections) takes every detection of the frame as
    {"cls": name, "conf": float, "box": (x0, y0, x1, y1), "track_id": int|None}
    and returns the events newly raised on that frame. `available_classes` is
    the loaded model's class-name set, used to switch off events the model
    can't support (e.g. no accident class yet); None means "assume all"."""

    def __init__(self, fps, scene=None, available_classes=None):
        self.fps = float(fps) if fps and fps > 0 else 25.0
        self.scene = scene
        self.available = set(available_classes) if available_classes is not None else None
        self.tracks = {}
        self.events = []
        self._recent = deque(maxlen=8)
        self._next_id = 1
        self._scene_last = {}
        self._acc_hist = deque(maxlen=self._frames(ACCIDENT_WINDOW_SECS))
        self._con_hist = deque(maxlen=self._frames(CONSTRUCTION_WINDOW_SECS))
        self._fire_hist = deque(maxlen=self._frames(FIRE_WINDOW_SECS))
        self._hist_len = self._frames(max(STOPPED_SECS, STANDING_SECS) + 1.0)
        self.caps = self.capabilities()

    def _frames(self, secs):
        return max(1, int(round(secs * self.fps)))

    def capabilities(self):
        """{event_type: {"enabled": bool, "reason": str|None}} -- why an event
        can't fire with this scene + model, for the UI to show."""
        s = self.scene

        def model_has(classes):
            return self.available is None or bool(self.available & classes)

        people = model_has({PERSON_CLASS})
        checks = {
            "person_walking_roadside": (people and s is not None and s.has_zone("roadside"),
                                        "needs a roadside zone in the road map"),
            "person_standing_roadside": (people and s is not None and s.has_zone("roadside"),
                                         "needs a roadside zone in the road map"),
            "pedestrian_crossing_zebra": (people and s is not None and s.has_zone("crossing"),
                                          "needs a zebra-crossing zone in the road map"),
            "jaywalking": (people and s is not None and s.has_carriageway,
                           "needs a road area or lanes in the road map"),
            "lane_change": (s is not None and len(s.lanes) >= 2, "needs at least 2 lanes in the road map"),
            "wrong_side_driving": (s is not None and s.has_directions,
                                   "needs lanes with a travel direction in the road map"),
            "stopped_vehicle": (s is not None and s.has_carriageway, "needs a road area or lanes in the road map"),
            "accident": (model_has(ACCIDENT_CLASSES), "the loaded model has no accident class yet"),
            "fire": (model_has(FIRE_CLASSES), "the loaded model has no fire_accident class"),
            "road_construction": (model_has(CONSTRUCTION_OBJECT_CLASSES | CONSTRUCTION_ZONE_CLASSES),
                                  "the loaded model has no traffic_cone / barricade class yet"),
        }
        return {etype: {"enabled": bool(ok), "reason": None if ok else reason}
                for etype, (ok, reason) in checks.items()}

    # --- main entry ----------------------------------------------------------

    def update(self, frame_idx, frame_w, frame_h, detections):
        dets = list(detections)
        new_events = []
        if self.scene is not None:
            self.scene.fit(frame_w, frame_h)
            rideables = [d["box"] for d in dets if d["cls"] in RIDEABLE_CLASSES]
            for d in dets:
                tid = d.get("track_id")
                if tid is None:
                    continue
                if d["cls"] == PERSON_CLASS:
                    kind = "person"
                elif d["cls"] in VEHICLE_CLASSES:
                    kind = "vehicle"
                else:
                    continue
                track = self.tracks.get(tid)
                if track is None or track.kind != kind:
                    track = self.tracks[tid] = _Track(tid, d["cls"], kind, self._hist_len)
                track.cls = d["cls"]  # detector class can flicker (car <-> auto); keep history, show latest

                box = d["box"]
                foot = _foot(box)
                rider = kind == "person" and any(_overlap_ratio(box, rb) >= RIDER_OVERLAP for rb in rideables)
                lane = self._lane_of(box) if kind == "vehicle" else None
                track.hist.append(_Sample(frame_idx, foot[0], foot[1], max(1.0, box[3] - box[1]),
                                          self.scene.zone_at(foot), lane, rider))
                track.box = box
                track.last_frame = frame_idx
                if kind == "person":
                    new_events += self._person_rules(track, frame_idx)
                else:
                    new_events += self._vehicle_rules(track, frame_idx)

            timeout = self._frames(TRACK_TIMEOUT_SECS)
            for tid in [tid for tid, t in self.tracks.items() if frame_idx - t.last_frame > timeout]:
                del self.tracks[tid]

        new_events += self._scene_rules(frame_idx, dets)
        self.events.extend(new_events)
        self._recent.extend(new_events)
        return new_events

    def _lane_of(self, box):
        """The lane a vehicle is fully in, judged at two points a quarter of
        the way in from each end of its bottom edge -- None while it straddles
        a lane line, so riding on the marking (very common on Indian roads)
        isn't read as a string of lane changes."""
        x0, x1, y = box[0], box[2], box[3]
        left = self.scene.lane_at((x0 + (x1 - x0) * 0.25, y))
        right = self.scene.lane_at((x0 + (x1 - x0) * 0.75, y))
        return left if left == right else None

    def track_status(self, track_id):
        track = self.tracks.get(track_id)
        return track.status if track is not None else None

    def summary(self):
        counts = {}
        for ev in self.events:
            counts[ev["type"]] = counts.get(ev["type"], 0) + 1
        return counts

    # --- helpers -------------------------------------------------------------

    def _emit(self, etype, frame, track=None, box=None, object_class=None, details=None):
        meta = EVENT_TYPES[etype]
        box = box if box is not None else (track.box if track is not None else None)
        event = {
            "id": self._next_id,
            "type": etype,
            "label": meta["label"],
            "severity": meta["severity"],
            "frame": frame,
            "time_s": round(frame / self.fps, 2),
            "track_id": track.id if track is not None else None,
            "object_class": track.cls if track is not None else object_class,
            "box": [round(float(v), 1) for v in box] if box is not None else None,
            "details": details or {},
        }
        self._next_id += 1
        return event

    def _fire_once(self, track, etype, frame, details=None):
        if etype in track.fired or not self.caps[etype]["enabled"]:
            return []
        track.fired.add(etype)
        return [self._emit(etype, frame, track, details=details)]

    def _window(self, track, secs):
        """The track's samples from the last `secs` seconds, or None while the
        track doesn't yet span (most of) that long."""
        span = self._frames(secs)
        last = track.hist[-1].frame
        samples = [s for s in track.hist if s.frame >= last - span]
        if len(samples) < 3 or samples[-1].frame - samples[0].frame < 0.8 * span:
            return None
        return samples

    def _tail_run(self, track, accept):
        """Most recent continuous run of samples satisfying `accept`,
        tolerating gaps up to RUN_GAP_SECS."""
        max_gap = self._frames(RUN_GAP_SECS)
        ref = track.hist[-1].frame
        run = []
        for s in reversed(track.hist):
            if accept(s):
                run.append(s)
                ref = s.frame
            elif ref - s.frame > max_gap:
                break
        run.reverse()
        return run

    def _displacement(self, samples):
        """(dx, dy, dt_seconds, median box height) between the smoothed
        start and end of `samples` -- averaging a few points at each end
        keeps single-frame box jitter from reading as motion."""
        k = max(1, min(3, len(samples) // 3))
        head, tail = samples[:k], samples[-k:]
        dx = sum(s.fx for s in tail) / k - sum(s.fx for s in head) / k
        dy = sum(s.fy for s in tail) / k - sum(s.fy for s in head) / k
        dt = (sum(s.frame for s in tail) / k - sum(s.frame for s in head) / k) / self.fps
        bh = float(np.median([s.bh for s in samples]))
        return dx, dy, dt, bh

    def _speed(self, samples):
        dx, dy, dt, bh = self._displacement(samples)
        return math.hypot(dx, dy) / bh / dt if dt > 0 else 0.0

    @staticmethod
    def _zone_ratio(samples, zones):
        return sum(s.zone in zones for s in samples) / len(samples)

    # --- rules ---------------------------------------------------------------

    def _person_rules(self, track, frame):
        recent = self._window(track, ZONE_DWELL_SECS)
        track.status = None
        if recent is None:
            return []
        if sum(s.rider for s in recent) >= len(recent) / 2:
            track.status = "rider"
            return []

        walking = [s for s in recent if not s.rider]
        speed = self._speed(walking) if len(walking) >= 3 else 0.0

        if self._zone_ratio(recent, {"crossing"}) >= 0.6:
            track.status = "on crossing"
            if speed >= STILL_SPEED_BH:
                return self._fire_once(track, "pedestrian_crossing_zebra", frame)
            return []

        if self._zone_ratio(recent, {"road"}) >= 0.8:
            track.status = "on road"
            run = self._tail_run(track, lambda s: s.zone == "road" and not s.rider)
            if len(run) >= 3 and run[-1].frame - run[0].frame >= 0.8 * self._frames(ZONE_DWELL_SECS):
                dx, dy, _, bh = self._displacement(run)
                if math.hypot(dx, dy) / bh >= CROSS_MIN_MOVE_BH:
                    track.status = "jaywalking"
                    return self._fire_once(track, "jaywalking", frame)
            return []

        if self._zone_ratio(recent, {"roadside"}) >= 0.8:
            track.status = "roadside"
            if speed >= WALK_SPEED_BH:
                track.status = "walking"
                return self._fire_once(track, "person_walking_roadside", frame)
            if speed <= STILL_SPEED_BH:
                long_window = self._window(track, STANDING_SECS)
                if (long_window is not None and self._zone_ratio(long_window, {"roadside"}) >= 0.8
                        and self._speed(long_window) <= STILL_SPEED_BH):
                    track.status = "standing"
                    return self._fire_once(track, "person_standing_roadside", frame)
        return []

    def _vehicle_rules(self, track, frame):
        events = []
        latest = track.hist[-1]

        if latest.lane is not None:
            if latest.lane == track.stable_lane:
                track.cand_lane, track.cand_count = None, 0
            else:
                if latest.lane == track.cand_lane:
                    track.cand_count += 1
                else:
                    track.cand_lane, track.cand_count = latest.lane, 1
                if track.cand_count >= self._frames(LANE_STABLE_SECS):
                    if track.stable_lane is not None and self.caps["lane_change"]["enabled"]:
                        events.append(self._emit("lane_change", frame, track,
                                                 details={"from_lane": track.stable_lane, "to_lane": latest.lane}))
                        track.lane_change_until = frame + self._frames(2.0)
                    track.stable_lane = latest.lane
                    track.cand_lane, track.cand_count = None, 0

        track.status = "lane change" if frame <= track.lane_change_until else None
        recent = self._window(track, WRONG_SIDE_WINDOW_SECS)
        if recent is None:
            return events

        dx, dy, dt, bh = self._displacement(recent)
        speed = math.hypot(dx, dy) / bh / dt if dt > 0 else 0.0
        lane_name = track.stable_lane or latest.lane
        vec = self.scene.lane_direction(lane_name) if lane_name else None
        if vec is not None and speed >= WRONG_SIDE_MIN_SPEED_BH:
            cos = (dx * vec[0] + dy * vec[1]) / math.hypot(dx, dy)
            if cos <= WRONG_SIDE_COS:
                track.against_count += 1
            elif cos > 0:
                track.against_count = 0
        if track.against_count >= self._frames(WRONG_SIDE_SECS):
            track.status = "WRONG SIDE"
            events += self._fire_once(track, "wrong_side_driving", frame, details={"lane": lane_name})

        if speed <= STOPPED_SPEED_BH:
            long_window = self._window(track, STOPPED_SECS)
            if (long_window is not None and self._zone_ratio(long_window, {"road", "crossing"}) >= 0.8
                    and self._speed(long_window) <= STOPPED_SPEED_BH):
                track.status = track.status or "stopped"
                events += self._fire_once(track, "stopped_vehicle", frame)
        return events

    def _cooled_down(self, etype, frame):
        last = self._scene_last.get(etype)
        return last is None or frame - last >= self._frames(SCENE_EVENT_COOLDOWN_SECS)

    def _scene_rules(self, frame, dets):
        events = []

        if self.caps["accident"]["enabled"]:
            hits = [d for d in dets if d["cls"] in ACCIDENT_CLASSES and d["conf"] >= ACCIDENT_MIN_CONF]
            self._acc_hist.append(bool(hits))
            if (hits and len(self._acc_hist) == self._acc_hist.maxlen
                    and sum(self._acc_hist) / len(self._acc_hist) >= ACCIDENT_MIN_RATIO
                    and self._cooled_down("accident", frame)):
                best = max(hits, key=lambda d: d["conf"])
                events.append(self._emit("accident", frame, box=best["box"], object_class=best["cls"],
                                         details={"detections": len(hits)}))
                self._scene_last["accident"] = frame

        if self.caps["fire"]["enabled"]:
            hits = [d for d in dets if d["cls"] in FIRE_CLASSES and d["conf"] >= FIRE_MIN_CONF]
            self._fire_hist.append(bool(hits))
            if (hits and len(self._fire_hist) == self._fire_hist.maxlen
                    and sum(self._fire_hist) / len(self._fire_hist) >= FIRE_MIN_RATIO
                    and self._cooled_down("fire", frame)):
                best = max(hits, key=lambda d: d["conf"])
                events.append(self._emit("fire", frame, box=best["box"], object_class=best["cls"],
                                         details={"confidence": round(best["conf"], 2)}))
                self._scene_last["fire"] = frame

        if self.caps["road_construction"]["enabled"]:
            hits = [d for d in dets if d["cls"] in CONSTRUCTION_OBJECT_CLASSES | CONSTRUCTION_ZONE_CLASSES]
            if self.scene is not None and self.scene.has_carriageway:
                hits = [d for d in hits if self.scene.zone_at(_foot(d["box"])) in ("road", "crossing")]
            n_objects = sum(d["cls"] in CONSTRUCTION_OBJECT_CLASSES for d in hits)
            present = n_objects >= CONSTRUCTION_MIN_OBJECTS or any(d["cls"] in CONSTRUCTION_ZONE_CLASSES for d in hits)
            self._con_hist.append(present)
            if (present and len(self._con_hist) == self._con_hist.maxlen
                    and sum(self._con_hist) / len(self._con_hist) >= CONSTRUCTION_MIN_RATIO
                    and self._cooled_down("road_construction", frame)):
                box = (min(d["box"][0] for d in hits), min(d["box"][1] for d in hits),
                       max(d["box"][2] for d in hits), max(d["box"][3] for d in hits))
                events.append(self._emit("road_construction", frame, box=box, object_class="work zone",
                                         details={"objects": len(hits)}))
                self._scene_last["road_construction"] = frame

        return events

    # --- drawing -------------------------------------------------------------

    def draw_scene(self, img):
        if self.scene is not None:
            self.scene.draw(img)

    def draw_alerts(self, img, frame_idx):
        """Outline the object behind each recent event and list the events
        top-left, colored by severity."""
        horizon = self._frames(ALERT_DISPLAY_SECS)
        recent = [ev for ev in self._recent if frame_idx - ev["frame"] <= horizon]
        if not recent:
            return
        w = img.shape[1]
        thick = max(3, w // 480)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(0.55, w / 1800)

        for ev in recent:
            color = SEVERITY_COLORS[ev["severity"]]
            if ev["track_id"] is None:
                box = ev["box"]  # scene-level event (accident, work zone)
            else:  # outline the object only while it's actually in this frame
                track = self.tracks.get(ev["track_id"])
                box = track.box if track is not None and track.last_frame == frame_idx else None
            if box is not None:
                cv2.rectangle(img, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), color, thick)

        y = 12
        for ev in reversed(recent):
            text = ev["label"]
            if ev["track_id"] is not None:
                text += f"  #{ev['track_id']} {ev['object_class']}"
            (tw, th), _ = cv2.getTextSize(text, font, scale, 2)
            cv2.rectangle(img, (10, y), (10 + tw + 16, y + th + 14), SEVERITY_COLORS[ev["severity"]], -1)
            cv2.putText(img, text, (18, y + th + 6), font, scale, (255, 255, 255), 2, cv2.LINE_AA)
            y += th + 20


# --- automatic calibration: a Scene from watched traffic, no manual drawing -------------

AUTO_VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "auto", "bicycle"}
# 25th-percentile (not median: on a busy road, moving traffic can be over half the frame,
# so the median reads as foreground motion, not camera motion) optical-flow magnitude on a
# 320x180 frame, between frames spread across the whole clip. Calibrated against the only
# fixed-camera footage on hand (a dense-traffic overpass clip, p25 ~= 3.0) with headroom
# below it; no genuinely panning/dashcam clip was available to calibrate the upper side, so
# this threshold is a best-effort starting point, not a validated cutoff -- tune it against
# real dashcam footage before relying on it to gate anything automatically.
FIXED_CAMERA_MOTION_PX = 5.0
MIN_TRACK_LEN = 8                # frames a vehicle must be tracked before its path counts
MIN_TRACK_DISPLACEMENT = 0.04    # normalized; drops parked/near-stationary vehicles
MIN_TRACKS_TO_CALIBRATE = 4      # too little traffic in the warm-up window to trust a result
LANE_CLUSTER_EPS = 0.35          # DBSCAN eps over [unit direction (x1), centroid (x0.35)]
LANE_BUFFER = 0.92                # shrink each lane's convex hull slightly so opposite-direction
                                  # lanes (often adjacent) don't overlap and cross-trigger wrong_side_driving
ROAD_BUFFER = 1.2


def is_fixed_camera(video_path, sample_frames=5, motion_threshold=FIXED_CAMERA_MOTION_PX):
    """Sample frames spread across the whole clip and measure optical flow between
    consecutive samples (not consecutive frames): on a fixed camera the background stays
    aligned even seconds apart, so only foreground objects move and the median flow stays
    low; a panning/handheld/dashcam camera shifts the whole scene, so it reads high."""
    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    positions = [int(total * i / (sample_frames + 1)) for i in range(1, sample_frames + 1)]
    prev_gray, motions = None, []
    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 2, 15, 3, 5, 1.2, 0)
            motions.append(float(np.percentile(np.linalg.norm(flow, axis=2), 25)))
        prev_gray = gray
    cap.release()
    return bool(motions) and (sum(motions) / len(motions)) < motion_threshold


def _hull(points, buffer):
    """Convex hull of normalized points, grown outward from its own centroid so it
    comfortably contains the traffic that produced it, then clipped back into frame."""
    hull = cv2.convexHull(points.astype(np.float32)).reshape(-1, 2)
    centroid = hull.mean(axis=0)
    hull = centroid + (hull - centroid) * buffer
    return np.clip(hull, 0.0, 1.0)


def auto_calibrate(video_path, model, warmup_frames=150, conf=0.35):
    """Watch a fixed camera's own traffic for the first warmup_frames frames and build a
    Scene -- zones + lanes with travel direction -- from the vehicles' tracked paths,
    with no manual drawing. Computed once (static for the rest of the video/session), the
    same way a person would draw it, just from data instead of clicks.

    Returns a dict in the same shape as a hand-drawn scene.json (usable directly with
    Scene(data)), or None if calibration wasn't possible: a moving camera (is_fixed_camera
    fails) or too little tracked traffic in the warm-up window to trust a result."""
    if not is_fixed_camera(video_path):
        return None

    cap = cv2.VideoCapture(str(video_path))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tracks = defaultdict(list)
    for _ in range(warmup_frames):
        ok, frame = cap.read()
        if not ok:
            break
        result = model.track(frame, persist=True, conf=conf, verbose=False, tracker="bytetrack.yaml")[0]
        if result.boxes is not None:
            for box in result.boxes:
                if box.id is None or model.names.get(int(box.cls[0])) not in AUTO_VEHICLE_CLASSES:
                    continue
                x0, y0, x1, y1 = box.xyxy[0].tolist()
                tracks[int(box.id[0])].append(((x0 + x1) / 2 / w, y1 / h))  # foot point, normalized
    cap.release()

    usable = []
    for pts in tracks.values():
        if len(pts) < MIN_TRACK_LEN:
            continue
        pts = np.array(pts)
        if np.hypot(*(pts[-1] - pts[0])) >= MIN_TRACK_DISPLACEMENT:
            usable.append(pts)
    if len(usable) < MIN_TRACKS_TO_CALIBRATE:
        return None

    # cluster by direction (weighted heavily, so opposite-direction lanes never merge even
    # when physically adjacent) and centroid position (weighted lightly, to split same-direction
    # lanes) in one pass
    feats = []
    for pts in usable:
        direction = pts[-1] - pts[0]
        direction = direction / (np.linalg.norm(direction) + 1e-9)
        feats.append(np.concatenate([direction, pts.mean(axis=0) * 0.35]))

    from sklearn.cluster import DBSCAN
    labels = DBSCAN(eps=LANE_CLUSTER_EPS, min_samples=2).fit_predict(np.array(feats))

    lanes, all_pts = [], []
    for i, cluster_id in enumerate(sorted(set(labels) - {-1})):
        members = [j for j, lbl in enumerate(labels) if lbl == cluster_id]
        pts = np.concatenate([usable[j] for j in members], axis=0)
        all_pts.append(pts)
        starts = np.array([usable[j][0] for j in members])
        ends = np.array([usable[j][-1] for j in members])
        lanes.append({
            "name": f"Lane {i + 1}",
            "points": _hull(pts, LANE_BUFFER).tolist(),
            "direction": [starts.mean(axis=0).tolist(), ends.mean(axis=0).tolist()],
        })
    if not lanes:
        return None

    return {
        "name": "Auto-calibrated road map",
        "zones": [{"type": "road", "points": _hull(np.concatenate(all_pts, axis=0), ROAD_BUFFER).tolist()}],
        "lanes": lanes,
        "auto_calibrated": True,
    }
