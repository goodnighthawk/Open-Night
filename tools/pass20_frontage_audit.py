from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC = ROOT / "dev_tools" / "map_generator" / "profiles" / "gwb_gameplay" / "unified_composition" / "semantic"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="Pass 20 street-wall/frontage acceptance audit")
    parser.add_argument("--semantic", type=Path, default=DEFAULT_SEMANTIC)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    rows = read_csv(args.semantic / "building_frontage_audit.csv")
    buildings = read_csv(args.semantic / "iterated_buildings.csv")
    stairs = read_csv(args.semantic / "building_stairwells.csv")
    scales = read_csv(args.semantic / "building_sprite_scale_audit.csv")

    if len(rows) != len(buildings):
        print(f"PASS20_FRONTAGE_GATE=FAIL frontage_rows={len(rows)} buildings={len(buildings)}")
        return 1

    ordinary = [r for r in rows if r.get("frontage_class") == "ordinary_urban"]
    addressed = [r for r in ordinary if r.get("addressed") == "true"]
    safe = [r for r in rows if r.get("safe_clearance") == "true"]
    max_shift = max((float(r.get("shift_distance", 0) or 0) for r in rows), default=0.0)
    min_gap = min((float(r.get("gap_after", 0) or 0) for r in rows), default=0.0)
    addressed_share = len(addressed) / max(1, len(ordinary))
    stair_buildings = {r.get("building_id") for r in stairs}
    building_ids = {r.get("id") for r in buildings}
    missing_stairs = sorted(building_ids - stair_buildings)
    scale_failures = [r for r in scales if r.get("status") != "pass"]

    print(
        "PASS20_FRONTAGE_AUDIT "
        f"buildings={len(buildings)} ordinary={len(ordinary)} addressed={len(addressed)} "
        f"addressed_share={addressed_share:.3f} safe={len(safe)}/{len(rows)} "
        f"min_gap={min_gap:.2f} max_shift={max_shift:.2f} "
        f"missing_stairs={len(missing_stairs)} scale_failures={len(scale_failures)}"
    )

    if not args.strict:
        return 0

    problems: list[str] = []
    if len(buildings) != 95:
        problems.append(f"expected 95 buildings, got {len(buildings)}")
    if addressed_share < 0.80:
        problems.append(f"ordinary sidewalk-addressed share {addressed_share:.1%} is below 80%")
    if len(safe) != len(rows):
        problems.append(f"{len(rows)-len(safe)} buildings violate the minimum road/sidewalk clearance")
    if min_gap < 14.0 - 1e-6:
        problems.append(f"minimum frontage gap {min_gap:.2f} is below 14 world units")
    if max_shift > 64.0 + 1e-6:
        problems.append(f"maximum footprint shift {max_shift:.2f} exceeds 64 world units")
    if missing_stairs:
        problems.append(f"buildings missing stairwell rows: {missing_stairs[:8]}")
    if scale_failures:
        problems.append(f"building sprite scale failures: {len(scale_failures)}")

    if problems:
        print("PASS20_FRONTAGE_GATE=FAIL")
        for problem in problems:
            print(" - " + problem)
        return 1

    print("PASS20_FRONTAGE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
