#!/usr/bin/env python3
"""Fine-tune the detector on datasets/processed_v2/data.yaml, starting from an
existing checkpoint (default: models/nh5_v5_best.pt).

Not run as part of any other script -- kick it off manually when ready.
On this CPU-only dev machine a full run over the current ~35.7k-image
processed set will realistically take many hours (no CUDA available here --
device auto-selects cuda if present, else cpu). Run on a GPU machine if you
have one; on CPU, expect this to run for a long time and consider trimming
--epochs for an initial check before committing to a full run.

Usage:
  python 17_train.py
  python 17_train.py --weights models/nh5_v5_best.pt --epochs 30 --imgsz 640 --batch 16
  python 17_train.py --data datasets/processed_v2/data.yaml --project runs/nh5_v6 --name finetune
"""
import argparse

import torch
from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="models/nh5_v5_best.pt", help="starting checkpoint to fine-tune from")
    ap.add_argument("--data", default="datasets/processed_v2/data.yaml")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default=None, help="e.g. 'cpu', '0', '0,1'; default auto-selects cuda if available")
    ap.add_argument("--project", default="runs/nh5_v6")
    ap.add_argument("--name", default="finetune")
    ap.add_argument("--patience", type=int, default=100,
                     help="stop early after this many epochs with no mAP improvement; 0 disables early stopping")
    args = ap.parse_args()

    device = args.device or ("0" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")
    if device == "cpu":
        print("WARNING: no GPU detected -- fine-tuning on this dataset size will likely take many hours on CPU.")

    model = YOLO(args.weights)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        project=args.project,
        name=args.name,
        patience=args.patience,
    )


if __name__ == "__main__":
    main()
