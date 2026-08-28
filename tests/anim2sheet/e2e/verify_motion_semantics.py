from __future__ import annotations
import json, sys
from pathlib import Path

root=Path(sys.argv[1]); debug=json.loads((root/"motion_debug.json").read_text())
s=debug["samples"]
if len(s)!=16: raise SystemExit("expected 16 debug samples")
root_delta=s[-1]["rootX"]-s[0]["rootX"]
xs=[row["swordTip"][0] for row in s]; zs=[row["swordTip"][2] for row in s]
if root_delta < 0.20: raise SystemExit(f"forward/root displacement too small: {root_delta}")
if max(xs)-min(xs) < 0.45: raise SystemExit("sword horizontal sweep too small")
if max(zs)-min(zs) < 0.20: raise SystemExit("sword vertical variation too small")
# Require a meaningful direction reversal / follow-through rather than monotonic idle drift.
dx=[xs[i+1]-xs[i] for i in range(len(xs)-1)]
if not any(v>0.04 for v in dx) or not any(v<-0.04 for v in dx): raise SystemExit("sword trajectory lacks slash reversal")
print(json.dumps({"rootDelta":root_delta,"swordXRange":max(xs)-min(xs),"swordZRange":max(zs)-min(zs)},indent=2))
