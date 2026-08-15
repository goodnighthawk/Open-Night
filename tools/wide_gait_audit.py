from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets" / "characters" / "master_dual_camera"
CELL = 256


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def box_size(image: Image.Image, frame: int, direction: int) -> tuple[int, int]:
    crop = image.crop((frame * CELL, direction * CELL, (frame + 1) * CELL, (direction + 1) * CELL))
    box = crop.getchannel("A").getbbox()
    if not box:
        raise AssertionError(f"empty frame {frame}/{direction}")
    return box[2] - box[0], box[3] - box[1]


def main() -> int:
    fluid = rows(PACK / "config" / "fluid_animations.csv")
    index = {(row["camera_mode"], row["profile_id"], row["animation"]): row for row in fluid}
    run_rows = [row for row in fluid if row["animation"] == "run_wide_8"]
    assert len(run_rows) == 10, f"expected 10 run sheets, found {len(run_rows)}"
    comparisons = 0
    for run_row in run_rows:
        key = (run_row["camera_mode"], run_row["profile_id"], "walk_8")
        walk_row = index[key]
        walk = Image.open(PACK / walk_row["sheet"]).convert("RGBA")
        run = Image.open(PACK / run_row["sheet"]).convert("RGBA")
        assert walk.size == run.size == (2048, 2048)
        assert walk.tobytes() != run.tobytes(), run_row["sheet"]
        for direction in range(8):
            for frame in (2, 6):
                walk_w, walk_h = box_size(walk, frame, direction)
                run_w, run_h = box_size(run, frame, direction)
                if run_row["camera_mode"] == "isometric":
                    assert run_w >= walk_w + 20, (run_row["sheet"], direction, frame, walk_w, run_w)
                else:
                    assert run_w >= walk_w + 4 and run_h >= walk_h + 3, (
                        run_row["sheet"], direction, frame, (walk_w, walk_h), (run_w, run_h)
                    )
                comparisons += 1
    source = (ROOT / "character_art.py").read_text(encoding="utf-8")
    assert '"run": "run_wide_8"' in source
    assert "_wide_gait_fallback" in source
    print("WIDE GAIT AUDIT PASSED")
    print(f"  {len(run_rows)} sheets / {comparisons} peak-frame comparisons / modular fallback active")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
