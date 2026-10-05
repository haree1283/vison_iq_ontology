#!/usr/bin/env python3
"""Exit 0 if the checkpoint loads and can still be resumed (has optimizer state), 2 if it loads
but training is finished, 1 if it is missing or corrupt."""
import sys
import torch

try:
    ckpt = torch.load(sys.argv[1], map_location="cpu", weights_only=False)
except Exception as e:
    print(f"unreadable: {e}")
    sys.exit(1)
if ckpt.get("optimizer") is None:
    print("finished (no optimizer state)")
    sys.exit(2)
print(f"resumable, epoch {ckpt.get('epoch')}")
sys.exit(0)
