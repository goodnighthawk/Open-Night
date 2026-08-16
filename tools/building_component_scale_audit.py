from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC = ROOT / "dev_tools" / "map_generator" / "profiles" / "gwb_gameplay" / "unified_composition" / "semantic"
CONTRACT = ROOT / "config" / "environment_component_scale.csv"
MIN_SCALE = 0.88
MAX_SCALE = 1.12
MAX_REUSED_SPRITE_SPREAD = 0.10


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="Pass 21 fixed building-component scale audit")
    parser.add_argument("--semantic", type=Path, default=DEFAULT_SEMANTIC)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    contract = rows(CONTRACT)
    building_rows = rows(args.semantic / "building_component_scale_audit.csv")
    buildings = rows(args.semantic / "iterated_buildings.csv")
    stairs = rows(args.semantic / "building_stairwells.csv")
    frontage = rows(args.semantic / "building_frontage_audit.csv")

    contract_by_id = {r["component_id"]: r for r in contract}
    required = {
        "door", "window", "wall_module", "parapet", "stair", "fire_escape",
        "railing", "roof_hatch", "hvac_small", "hvac_large", "chimney",
        "awning", "storefront_module",
    }
    missing_contract = sorted(required - set(contract_by_id))

    failures = [r for r in building_rows if r.get("status") != "pass"]
    ratios = [float(r.get("component_scale_ratio", 0) or 0) for r in building_rows]
    min_ratio = min(ratios, default=0.0)
    max_ratio = max(ratios, default=0.0)

    reused: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in building_rows:
        reused[(row.get("atlas", ""), row.get("cell", ""))].append(float(row.get("component_scale_ratio", 0) or 0))
    spreads = {
        key: max(vals) - min(vals)
        for key, vals in reused.items()
        if len(vals) > 1
    }
    worst_key = max(spreads, key=spreads.get) if spreads else ("", "")
    worst_spread = spreads.get(worst_key, 0.0)

    fixed_contract_failures = []
    for cid in ("stair", "fire_escape", "railing"):
        row = contract_by_id.get(cid)
        if not row:
            continue
        if abs(float(row.get("min_scale_ratio", 0) or 0) - 1.0) > 1e-9 or abs(float(row.get("max_scale_ratio", 0) or 0) - 1.0) > 1e-9:
            fixed_contract_failures.append(cid)

    building_ids = {r.get("id") for r in buildings}
    stair_ids = {r.get("building_id") for r in stairs}
    missing_stairs = sorted(building_ids - stair_ids)
    frontage_failures = [r for r in frontage if r.get("addressed") != "true" or r.get("safe_clearance") != "true"]

    print(
        "PASS21_COMPONENT_SCALE_AUDIT "
        f"buildings={len(buildings)} component_rows={len(building_rows)} "
        f"scale_band={min_ratio:.4f}..{max_ratio:.4f} failures={len(failures)} "
        f"worst_reused_sprite_spread={worst_spread:.4f} "
        f"missing_stairs={len(missing_stairs)} frontage_failures={len(frontage_failures)}"
    )

    if not args.strict:
        return 0

    problems: list[str] = []
    if len(buildings) != 95 or len(building_rows) != 95:
        problems.append(f"expected 95 buildings/component rows, got {len(buildings)}/{len(building_rows)}")
    if missing_contract:
        problems.append(f"component contract missing: {missing_contract}")
    if fixed_contract_failures:
        problems.append(f"fixed-world components are not locked to 1.0: {fixed_contract_failures}")
    if failures:
        problems.append(f"{len(failures)} buildings outside the {MIN_SCALE:.2f}..{MAX_SCALE:.2f} component band")
    if min_ratio < MIN_SCALE - 1e-9 or max_ratio > MAX_SCALE + 1e-9:
        problems.append(f"observed component scale {min_ratio:.4f}..{max_ratio:.4f} violates contract")
    if worst_spread > MAX_REUSED_SPRITE_SPREAD + 1e-9:
        problems.append(f"same-sprite component-scale spread {worst_spread:.4f} exceeds {MAX_REUSED_SPRITE_SPREAD:.2f}")
    if missing_stairs:
        problems.append(f"buildings missing stair semantics: {missing_stairs[:8]}")
    if frontage_failures:
        problems.append(f"Pass 20 frontage regressed for {len(frontage_failures)} buildings")

    if problems:
        print("PASS21_COMPONENT_SCALE_GATE=FAIL")
        for problem in problems:
            print(" - " + problem)
        return 1

    print("PASS21_COMPONENT_SCALE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
