from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles.loader import load_map_folder
from mapfiles.grid import chunk_label

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
OUT = ROOT / "art_review" / "chunk_reference.csv"

def main() -> int:
    cfg = load_map_folder(MAP_DIR, attach_grid=False)
    chunk = int(cfg.get("chunk_size", 1024))
    cols = int(cfg.get("chunk_cols", 1))
    rows = int(cfg.get("chunk_rows", 1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chunk_id","chunk_x","chunk_y","world_x0","world_y0","world_x1","world_y1"])
        for cy in range(rows):
            for cx in range(cols):
                x0, y0 = cx*chunk, cy*chunk
                x1 = min(int(cfg["world_w"]), (cx+1)*chunk)
                y1 = min(int(cfg["world_h"]), (cy+1)*chunk)
                w.writerow([chunk_label(cx,cy),cx,cy,x0,y0,x1,y1])
    print(f"Map 001 human chunk grid: A1 .. {chunk_label(cols-1, rows-1)}")
    header = "     " + " ".join(f"{chunk_label(cx,0)[:-1]:>3}" for cx in range(cols))
    print(header)
    for cy in range(rows):
        print(f"{cy+1:>3}  " + " ".join(f"{chunk_label(cx,cy):>3}" for cx in range(cols)))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
