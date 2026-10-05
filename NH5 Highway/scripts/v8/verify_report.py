#!/usr/bin/env python3
"""Build runs/verify/report.md: every video test run under runs/video_tests/<name> (v8 milestones + baselines)
side by side, per video: vehicle boxes, valid plates, event alert frames, stability (flicker / count jitter)."""
import glob, json, os, re, sys
ROOT = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
VT = f"{ROOT}/runs/video_tests"
VEH = {"car", "bus", "truck", "motorcycle", "auto", "bicycle"}
runs = sys.argv[1:] or sorted(os.path.basename(d) for d in glob.glob(f"{VT}/v8_ep*") + glob.glob(f"{VT}/base_*"))

def load(run):
    out = {}
    for sj in glob.glob(f"{VT}/{run}/annotated/*/summary.json"):
        for vid, s in json.load(open(sj)).items():
            key = os.path.splitext(vid)[0]
            o = s["objects_drawn"]
            pkey = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:60]   # plates_pipeline.py folder naming
            pu = f"{VT}/{run}/plates/{pkey}/plates_unique.txt"
            valid = sum(1 for l in open(pu) if "\tVALID\t" in l) if os.path.exists(pu) else 0
            st = s.get("stability", {})
            out[key] = dict(frames=s["frames"], veh=sum(o.get(c, 0) for c in VEH), person=o.get("person", 0),
                            plates=valid, acc=s["alert_frames"].get("accident_scene", 0),
                            fire=s["alert_frames"].get("fire_accident", 0), road=o.get("road_construction", 0),
                            flick=st.get("short_tracks_pct"), jit=st.get("count_jitter_pct"), tlen=st.get("mean_track_len"))
    return out

data = {r: load(r) for r in runs}
data = {r: d for r, d in data.items() if d}
vids = sorted({v for d in data.values() for v in d})
L = [f"# NH5 v8 verification report\n", f"Runs: {', '.join(data)}\n",
     "Per video: vehicle boxes (all frames) / valid plates / accident alert frames / fire alert frames / "
     "flicker % (tracks <=5 frames, lower = steadier) / count jitter % (lower = steadier)\n"]
for v in vids:
    L.append(f"\n## {v}\n\n| run | frames | vehicles | persons | plates | accident | fire | road work | flicker % | jitter % | mean track len |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for r, d in data.items():
        x = d.get(v)
        if x: L.append(f"| {r} | {x['frames']} | {x['veh']} | {x['person']} | {x['plates']} | {x['acc']} | {x['fire']} | {x['road']} | {x['flick']} | {x['jit']} | {x['tlen']} |")
L.append("\n## Totals\n\n| run | vehicles | plates | accident frames | fire frames | mean flicker % | mean jitter % |\n|---|---|---|---|---|---|---|")
for r, d in data.items():
    fl = [x["flick"] for x in d.values() if x["flick"] is not None]; ji = [x["jit"] for x in d.values() if x["jit"] is not None]
    L.append(f"| {r} | {sum(x['veh'] for x in d.values())} | {sum(x['plates'] for x in d.values())} | "
             f"{sum(x['acc'] for x in d.values())} | {sum(x['fire'] for x in d.values())} | "
             f"{round(sum(fl)/len(fl),1) if fl else '-'} | {round(sum(ji)/len(ji),1) if ji else '-'} |")
open(f"{ROOT}/runs/verify/report.md", "w").write("\n".join(L) + "\n")
print("\n".join(L[-(len(data) + 3):]))
