#!/usr/bin/env python3
"""Uniform weight average ("model soup") of checkpoints from one training run. Usage: soup.py out.pt a.pt b.pt ..."""
import sys, copy, torch
out, srcs = sys.argv[1], sys.argv[2:]
cks = [torch.load(p, map_location="cpu", weights_only=False) for p in srcs]
nets = [(c.get("ema") or c["model"]).float() for c in cks]
sd = {k: v.clone() for k, v in nets[0].state_dict().items()}
for k, v in sd.items():
    if v.is_floating_point():
        sd[k] = sum(n.state_dict()[k] for n in nets) / len(nets)
m = copy.deepcopy(nets[0]); m.load_state_dict(sd)
base = copy.copy(cks[-1]); base.update(model=m.half(), ema=None, optimizer=None, updates=None, epoch=-1)
base["soup_of"] = srcs
torch.save(base, out); print("saved", out, "from", len(srcs), "checkpoints")
