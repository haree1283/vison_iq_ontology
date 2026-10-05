#!/usr/bin/env python3
"""Charts for the NH5 reports (static PNG for PDF). Single-series charts in one hue; the target as a dashed line."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "charts"; OUT.mkdir(exist_ok=True)
BLUE, GREY, INK, INK2, GRID = "#2a78d6", "#b9b8b2", "#0b0b0b", "#52514e", "#e4e3de"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False})


def style(ax):
    ax.grid(axis="x", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)


# 1) accuracy per class (leak-free test, mAP50), sorted
cls = [("license plate", .946), ("auto", .921), ("car", .912), ("motorcycle", .868), ("bus", .851), ("person", .793),
       ("truck", .783), ("accident", .777), ("fire", .763), ("bicycle", .744), ("road work", .741), ("pothole", .559)]
fig, ax = plt.subplots(figsize=(6.6, 3.4), dpi=200)
names = [c for c, _ in cls][::-1]; vals = [v for _, v in cls][::-1]
ax.barh(names, vals, color=BLUE, height=0.62)
for y, v in enumerate(vals):
    ax.text(v + 0.008, y, f"{v:.2f}", va="center", fontsize=8, color=INK)
ax.axvline(0.75, color=INK2, linestyle="--", linewidth=1); ax.text(0.752, len(vals) - 0.4, "target 0.75", fontsize=8, color=INK2)
ax.set_xlim(0, 1.02); ax.set_xlabel("mAP50 (leak-free test set)"); style(ax)
ax.set_title("Detection accuracy per class - v8", loc="left", fontsize=10, color=INK)
fig.tight_layout(); fig.savefig(OUT / "accuracy_per_class.png"); plt.close(fig)

# 2) training progress (validation mAP50 per epoch)
rows = list(csv.DictReader(open(Path(__file__).resolve().parents[1] /
                                "runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep/results.csv")))
ep = [int(float(r["epoch"])) for r in rows]
m50 = [float(r["metrics/mAP50(B)"]) for r in rows]
fig, ax = plt.subplots(figsize=(6.6, 2.6), dpi=200)
ax.plot(ep, m50, color=BLUE, linewidth=2)
ax.axhline(0.75, color=INK2, linestyle="--", linewidth=1); ax.text(ep[-1], 0.742, "target 0.75", fontsize=8, color=INK2, ha="right", va="top")
ax.annotate(f"{m50[-1]:.3f}", (ep[-1], m50[-1]), xytext=(-28, 8), textcoords="offset points", fontsize=8, color=INK)
ax.set_xlabel("epoch"); ax.set_ylabel("mAP50 (validation)"); ax.set_ylim(min(m50) - 0.02, max(m50) + 0.02)
ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
ax.set_title("Training progress - v8 (100 epochs)", loc="left", fontsize=10, color=INK)
fig.tight_layout(); fig.savefig(OUT / "training_progress.png"); plt.close(fig)

# 3) model comparison (vehicles detected on the 14 test videos)
fig, ax = plt.subplots(figsize=(6.6, 1.9), dpi=200)
models = ["v6", "v5", "v8"]; veh = [43023, 104630, 133439]
ax.barh(models, veh, color=[GREY, GREY, BLUE], height=0.55)
for y, v in enumerate(veh):
    ax.text(v + 1500, y, f"{v:,}", va="center", fontsize=8, color=INK)
ax.set_xlim(0, 150000); ax.set_xlabel("vehicle detections on 14 test videos"); style(ax)
ax.set_title("Vehicles detected - previous models vs v8", loc="left", fontsize=10, color=INK)
fig.tight_layout(); fig.savefig(OUT / "model_comparison.png"); plt.close(fig)
print("charts:", sorted(p.name for p in OUT.glob("*.png")), "epochs:", ep[0], "-", ep[-1])
