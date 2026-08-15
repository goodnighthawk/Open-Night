from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles.loader import load_map_folder
from mapfiles.grid import DEFAULT_CELL_SIZE, write_compiled_grid, chunk_label


def main() -> int:
    p = argparse.ArgumentParser(description="Compile editable CSV map data into the v1.5.1 A1-labelled logical grid cache")
    p.add_argument("--map", default="map_001_gwb_corridor")
    p.add_argument("--cell-size", type=int, default=DEFAULT_CELL_SIZE)
    args = p.parse_args()
    folder = ROOT / "mapfiles" / "data" / args.map
    cfg = load_map_folder(folder, attach_grid=False)
    out = write_compiled_grid(folder, cfg, args.cell_size)
    print(f"compiled {cfg['name']}")
    cols = int(cfg.get("chunk_cols", 1)); rows = int(cfg.get("chunk_rows", 1))
    print(f"cell={args.cell_size}px chunk={cfg['chunk_size']}px -> {out.relative_to(ROOT)}")
    print(f"human grid: A1 .. {chunk_label(cols-1, rows-1)} ({cols} columns x {rows} rows)")
    print(f"chunk index: {(out / 'chunk_index.csv').relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
