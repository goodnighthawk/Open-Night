from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
MIN_SCALE = 0.72
MAX_SCALE = 1.12


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def style_key(row: dict[str, str]) -> tuple[str, int]:
    return str(row.get("atlas", "")), int(float(row.get("cell", 0) or 0))


def centre(row: dict[str, str]) -> tuple[float, float]:
    return (
        float(row["x"]) + float(row["w"]) * 0.5,
        float(row["y"]) + float(row["h"]) * 0.5,
    )


def nearest_repeat_count(rows: list[dict[str, str]]) -> tuple[int, list[tuple[str, str]]]:
    repeats: list[tuple[str, str]] = []
    by_district: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_district[str(row.get("district", ""))].append(row)
    for district_rows in by_district.values():
        for row in district_rows:
            x, y = centre(row)
            nearest = None
            for other in district_rows:
                if other["building_id"] == row["building_id"]:
                    continue
                ox, oy = centre(other)
                candidate = (math.hypot(x - ox, y - oy), other)
                if nearest is None or candidate[0] < nearest[0]:
                    nearest = candidate
            if nearest is not None and style_key(row) == style_key(nearest[1]):
                pair = tuple(sorted((row["building_id"], nearest[1]["building_id"])))
                if pair not in repeats:
                    repeats.append(pair)
    return len(repeats), repeats


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Pass 19 building-art convergence against the approved-map scale contract.")
    parser.add_argument("--strict", action="store_true", help="Require Pass 19 anti-repetition targets, not just release-safe reporting.")
    args = parser.parse_args()

    sprites = read_csv(MAP / "building_sprites.csv")
    buildings = {row["id"]: row for row in read_csv(MAP / "buildings.csv")}
    if not sprites:
        raise SystemExit("building art audit: no building_sprites.csv rows")

    missing = [row["building_id"] for row in sprites if row["building_id"] not in buildings]
    if missing:
        raise SystemExit(f"building art audit: sprite rows without collision buildings: {missing[:8]}")

    merged = []
    bad_scales = []
    styles: Counter[tuple[str, int]] = Counter()
    style_scales: dict[tuple[str, int], list[float]] = defaultdict(list)
    church_styles = set()
    for sprite in sprites:
        scale = float(sprite.get("render_scale_ratio", 0) or 0)
        if not (MIN_SCALE - 1e-6 <= scale <= MAX_SCALE + 1e-6):
            bad_scales.append((sprite["building_id"], scale))
        key = style_key(sprite)
        styles[key] += 1
        style_scales[key].append(scale)
        if sprite.get("building_kind") == "church_landmark":
            church_styles.add(key)
        merged.append({**buildings[sprite["building_id"]], **sprite})

    if bad_scales:
        raise SystemExit(f"building art audit: scale contract failed: {bad_scales[:8]}")

    nearest_repeats, repeat_pairs = nearest_repeat_count(merged)
    max_style, max_count = styles.most_common(1)[0]
    max_share = max_count / len(sprites)
    repeat_share = nearest_repeats / len(sprites)
    scale_spreads = {
        key: max(values) - min(values)
        for key, values in style_scales.items()
        if len(values) > 1
    }
    worst_scale_style = max(scale_spreads, key=scale_spreads.get) if scale_spreads else ("", 0)
    worst_scale_spread = scale_spreads.get(worst_scale_style, 0.0)

    print(
        "BUILDING_ART_CONVERGENCE "
        f"buildings={len(sprites)} unique_styles={len(styles)} "
        f"max_style={max_style[0]}:{max_style[1]} max_share={max_share:.3f} "
        f"nearest_repeat_pairs={nearest_repeats} repeat_share={repeat_share:.3f} "
        f"worst_same_sprite_scale_spread={worst_scale_spread:.4f} "
        f"church_variants={len(church_styles)} scale_band={MIN_SCALE:.2f}..{MAX_SCALE:.2f}"
    )
    if repeat_pairs:
        print(" nearest-repeat sample=" + ", ".join(f"{a}/{b}" for a, b in repeat_pairs[:8]))

    # Pass 18 remains a valid release baseline. --strict is the Pass 19 gate:
    # no single sprite may dominate the streetscape, essentially all immediate
    # neighbours must differ, and a reused sprite cannot masquerade as a very
    # differently sized building by large rescaling.
    if args.strict:
        problems = []
        if max_share > 0.10 + 1e-9:
            problems.append(f"most-used atlas cell is {max_share:.1%} of buildings (>10%)")
        if repeat_share > 0.04 + 1e-9:
            problems.append(f"nearest-neighbour exact repeats are {repeat_share:.1%} (>4%)")
        if worst_scale_spread > 0.10 + 1e-9:
            problems.append(f"same-sprite scale spread is {worst_scale_spread:.3f} (>0.10)")
        if len(church_styles) < 3:
            problems.append("fewer than three distinct church/parish landmark sprites")
        if problems:
            print("PASS19_ART_GATE=FAIL")
            for problem in problems:
                print(" - " + problem)
            return 1
        print("PASS19_ART_GATE=PASS")
    else:
        print("PASS18_RELEASE_BASELINE=PASS (use --strict for Pass 19 convergence gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
