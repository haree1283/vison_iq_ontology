#!/usr/bin/env python3
"""Set train_args.patience inside a resumable checkpoint (resume reads its args from the checkpoint)."""
import sys, torch
p, val = sys.argv[1], int(sys.argv[2])
ck = torch.load(p, map_location="cpu", weights_only=False)
old = ck["train_args"].get("patience")
ck["train_args"]["patience"] = val
torch.save(ck, p + ".tmp")
import os; os.replace(p + ".tmp", p)
print(f"patience {old} -> {val} in {p} (epoch {ck.get('epoch')})")
