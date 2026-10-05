#!/usr/bin/env python3
"""Synthetic-track tests for event_engine.py -- each scenario feeds hand-built
detections through a known road map and checks exactly which events fire.

Runs with pytest, or standalone:  python tests/test_event_engine.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_engine import EventEngine, Scene, clean_scene_data  # noqa: E402

FPS = 10
W = H = 1000

# Left 20% of the frame is roadside; two lanes (x 0.2-0.5, 0.5-0.8) both flow
# downwards; a zebra crossing spans the lanes at y 0.45-0.55.
SCENE_DATA = {
    "name": "test",
    "zones": [
        {"type": "roadside", "points": [[0, 0], [0.2, 0], [0.2, 1], [0, 1]]},
        {"type": "crossing", "points": [[0.2, 0.45], [0.8, 0.45], [0.8, 0.55], [0.2, 0.55]]},
    ],
    "lanes": [
        {"name": "Lane 1", "points": [[0.2, 0], [0.5, 0], [0.5, 1], [0.2, 1]], "direction": [[0.35, 0.1], [0.35, 0.9]]},
        {"name": "Lane 2", "points": [[0.5, 0], [0.8, 0], [0.8, 1], [0.5, 1]], "direction": [[0.65, 0.1], [0.65, 0.9]]},
    ],
}


def det(cls, cx, foot_y, h, tid=None, w=None, conf=0.9, scale=1.0):
    w = w if w is not None else h * 0.4
    cx, foot_y, h, w = cx * scale, foot_y * scale, h * scale, w * scale
    return {"cls": cls, "conf": conf, "box": (cx - w / 2, foot_y - h, cx + w / 2, foot_y), "track_id": tid}


def run(engine, frames, size=(W, H)):
    events = []
    for i, dets in enumerate(frames):
        events += engine.update(i, size[0], size[1], dets)
    return events


def engine(scene=True, classes=None):
    return EventEngine(FPS, Scene(SCENE_DATA) if scene else None, available_classes=classes)


def types(events, track_id=None):
    return [e["type"] for e in events if track_id is None or e["track_id"] == track_id]


def test_person_walking_roadside():
    frames = [[det("person", 100, 200 + 8 * i, 100, tid=1)] for i in range(15)]
    assert types(run(engine(), frames)) == ["person_walking_roadside"]


def test_person_standing_roadside():
    frames = [[det("person", 150, 600 + (i % 2), 100, tid=2)] for i in range(40)]
    e = engine()
    events = run(e, frames)
    assert types(events) == ["person_standing_roadside"]
    assert e.track_status(2) == "standing"


def test_pedestrian_crossing_at_zebra():
    frames = [[det("person", 250 + 10 * i, 500, 100, tid=3)] for i in range(40)]
    assert types(run(engine(), frames)) == ["pedestrian_crossing_zebra"]


def test_jaywalking_outside_crossing():
    frames = [[det("person", 250 + 10 * i, 250, 100, tid=4)] for i in range(30)]
    assert types(run(engine(), frames)) == ["jaywalking"]


def test_person_standing_still_on_road_is_not_jaywalking():
    frames = [[det("person", 300, 250 + (i % 2), 100, tid=4)] for i in range(30)]
    assert types(run(engine(), frames)) == []


def test_rider_on_motorcycle_is_not_a_pedestrian():
    frames = [[det("person", 300 + 10 * i, 260, 100, tid=5),
               det("motorcycle", 300 + 10 * i, 270, 80, tid=6, w=60)] for i in range(30)]
    events = run(engine(), frames)
    assert types(events, track_id=5) == []


def test_lane_change():
    frames = [[det("car", 350 if i < 15 else 650, 100 + 10 * i, 120, tid=7)] for i in range(30)]
    events = run(engine(), frames)
    assert types(events) == ["lane_change"]
    assert events[0]["details"] == {"from_lane": "Lane 1", "to_lane": "Lane 2"}


def test_brief_lane_flicker_is_not_a_lane_change():
    xs = [350] * 15 + [510, 510] + [350] * 13  # 2 frames over the line, under the 0.5 s hysteresis
    frames = [[det("car", x, 100 + 10 * i, 120, tid=7)] for i, x in enumerate(xs)]
    assert types(run(engine(), frames)) == []


def test_vehicle_riding_on_lane_line_is_not_a_lane_change():
    # a wide auto centred on the Lane 1 / Lane 2 line (x=500), drifting 10 frames either side of it --
    # common on Indian roads, and a single foot point would flip lanes every 10 frames
    xs = [490 + (i % 20) for i in range(40)]
    frames = [[det("auto", x, 100 + 10 * i, 120, tid=11, w=110)] for i, x in enumerate(xs)]
    assert types(run(engine(), frames)) == []


def test_wrong_side_driving():
    frames = [[det("car", 350, 900 - 10 * i, 120, tid=8)] for i in range(30)]
    assert types(run(engine(), frames)) == ["wrong_side_driving"]


def test_correct_direction_is_not_wrong_side():
    frames = [[det("car", 350, 100 + 10 * i, 120, tid=8)] for i in range(30)]
    assert types(run(engine(), frames)) == []


def test_stopped_vehicle():
    frames = [[det("car", 650, 700, 120, tid=9)] for i in range(120)]
    assert types(run(engine(), frames)) == ["stopped_vehicle"]


def test_accident_needs_model_class():
    e = engine(classes={"person", "car"})
    assert not e.caps["accident"]["enabled"]
    frames = [[det("damaged_vehicle", 400, 400, 150)] for _ in range(30)]
    assert types(run(e, frames)) == []


def test_accident_fires_once_within_cooldown():
    e = engine(classes={"person", "car", "damaged_vehicle"})
    frames = [[det("damaged_vehicle", 400, 400, 150)] for _ in range(60)]
    events = run(e, frames)
    assert types(events) == ["accident"]
    assert events[0]["frame"] == FPS - 1  # first frame the 1 s window is full


def test_construction_cones_on_road():
    e = engine(classes={"traffic_cone"})
    frames = [[det("traffic_cone", x, 300, 40) for x in (300, 350, 400)] for _ in range(30)]
    assert types(run(e, frames)) == ["road_construction"]


def test_cones_on_roadside_are_not_road_construction():
    e = engine(classes={"traffic_cone"})
    frames = [[det("traffic_cone", x, 300, 40) for x in (50, 100, 150)] for _ in range(30)]
    assert types(run(e, frames)) == []


def test_no_scene_disables_zone_rules():
    e = engine(scene=False)
    assert not e.caps["jaywalking"]["enabled"] and not e.caps["lane_change"]["enabled"]
    frames = [[det("person", 250 + 10 * i, 250, 100, tid=4)] for i in range(30)]
    assert types(run(e, frames)) == []


def test_scene_scales_with_resolution():
    frames = [[det("person", 250 + 10 * i, 250, 100, tid=4, scale=2.0)] for i in range(30)]
    assert types(run(engine(), frames, size=(2 * W, 2 * H))) == ["jaywalking"]


def test_clean_scene_data_rejects_bad_input():
    assert clean_scene_data(SCENE_DATA)["lanes"][0]["name"] == "Lane 1"
    for bad in (
        {"zones": [{"type": "parking", "points": [[0, 0], [1, 0], [1, 1]]}]},
        {"zones": [{"type": "road", "points": [[0, 0], [1, 0]]}]},
        {"zones": [{"type": "road", "points": [[0, 0], [1.5, 0], [1, 1]]}]},
        {"lanes": [{"name": "A", "points": [[0, 0], [1, 0], [1, 1]], "direction": [[0.5, 0.5], [0.5, 0.5]]}]},
        {"lanes": [{"name": "A", "points": [[0, 0], [1, 0], [1, 1]]},
                   {"name": "A", "points": [[0, 0], [1, 0], [1, 1]]}]},
    ):
        try:
            clean_scene_data(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid scene: {bad}")


if __name__ == "__main__":
    import traceback

    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
