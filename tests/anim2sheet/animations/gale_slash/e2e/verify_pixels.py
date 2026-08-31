from __future__ import annotations
import sys
from pathlib import Path
from PIL import Image, ImageChops

left=Path(sys.argv[1]); right=Path(sys.argv[2])
a=sorted(left.glob("*.png")); b=sorted(right.glob("*.png"))
if len(a)!=len(b): raise SystemExit(f"frame count mismatch: {len(a)} != {len(b)}")
for pa,pb in zip(a,b):
    with Image.open(pa) as ia, Image.open(pb) as ib:
        ra,rb=ia.convert("RGBA"),ib.convert("RGBA")
        if ra.size!=rb.size or ImageChops.difference(ra,rb).getbbox() is not None:
            raise SystemExit(f"decoded RGBA mismatch: {pa.name} vs {pb.name}")
print(f"pixel equality OK: {len(a)} frames")
