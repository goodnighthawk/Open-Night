from __future__ import annotations

"""Final v0.9.0 release-candidate builder.

Keeps Pass 19b geometry and art generation, but balances the visible frontage
population to the approved release target: roughly 30-50% of facades receive a
noticeable prop cluster and roughly 10-20% of all facades read as cluttered.
Subtle pavement wear remains universal and cosmetic-only.
"""

import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_unified_composition as base
import build_pass19b_frontage_release_candidate as pass19b

PASS_ID = "art_convergence_pass_19b_frontage_balanced"
_original_generate_frontage = pass19b.generate_frontage_dressing


def stable_seed(text: str) -> int:
    return sum((index + 17) * ord(ch) for index, ch in enumerate(str(text)))


def balanced_frontage(buildings, roads, road_points):
    rows = _original_generate_frontage(buildings, roads, road_points)
    by_id = {row["id"]: row for row in buildings}
    order = {row["id"]: index for index, row in enumerate(buildings)}

    obvious_by_building = defaultdict(list)
    litter_by_building = defaultdict(list)
    wear_by_building = defaultdict(list)
    for row in rows:
        kind = row["kind"]
        bid = row["building_id"]
        if kind == "frontage_wear":
            wear_by_building[bid].append(row)
        elif kind == "litter_cluster":
            litter_by_building[bid].append(row)
        else:
            obvious_by_building[bid].append(row)

    available_by_district = defaultdict(list)
    for bid in obvious_by_building:
        building = by_id.get(bid)
        if building is None:
            continue
        district = building.get("district", "")
        score = (order[bid] * 37 + stable_seed(bid)) % 100
        available_by_district[district].append((score, order[bid], bid))

    # The promoted map has 38 Fort Lee and 57 Washington Heights buildings.
    # 15 + 28 = 43 visibly dressed facades (45.3% overall), matching the agreed
    # 30-50% release target while keeping the denser Manhattan side more active.
    targets = {"fort_lee": 15, "washington_heights": 28}
    dressed_ids = set()
    for district, candidates in available_by_district.items():
        candidates.sort()
        dressed_ids.update(bid for _, _, bid in candidates[:targets.get(district, 0)])

    # Prefer already-rich clusters for the intentionally cluttered subset.
    rich_by_district = defaultdict(list)
    for bid in dressed_ids:
        building = by_id[bid]
        if len(obvious_by_building[bid]) < 4:
            continue
        score = (order[bid] * 53 + stable_seed(bid) // 11) % 100
        rich_by_district[building.get("district", "")].append((score, order[bid], bid))
    clutter_targets = {"fort_lee": 4, "washington_heights": 8}
    cluttered_ids = set()
    for district, candidates in rich_by_district.items():
        candidates.sort()
        cluttered_ids.update(bid for _, _, bid in candidates[:clutter_targets.get(district, 0)])

    filtered = []
    for building in buildings:
        bid = building["id"]
        filtered.extend(wear_by_building.get(bid, []))
        if bid not in dressed_ids:
            continue
        obvious_limit = 5 if bid in cluttered_ids else 3
        litter_limit = 3 if bid in cluttered_ids else 1
        filtered.extend(obvious_by_building.get(bid, [])[:obvious_limit])
        filtered.extend(litter_by_building.get(bid, [])[:litter_limit])

    for index, row in enumerate(filtered, 1):
        row["id"] = f"frontage_{index:04d}"

    pass19b.frontage_stats.clear()
    for row in filtered:
        pass19b.frontage_stats[row["kind"]] += 1
    pass19b.frontage_stats["dressed_buildings"] = len(dressed_ids)
    pass19b.frontage_stats["cluttered_buildings"] = len(cluttered_ids)

    base.write_csv(
        base.SEMANTIC / pass19b.FRONTAGE_CSV,
        ("id", "building_id", "district", "kind", "x", "y", "w", "h", "rotation", "placement_rule"),
        filtered,
    )
    return filtered


def main() -> None:
    pass19b.PASS_ID = PASS_ID
    pass19b.generate_frontage_dressing = balanced_frontage
    pass19b.main()
    total = sum(v for k, v in pass19b.frontage_stats.items()
                if k not in {"dressed_buildings", "cluttered_buildings"})
    print(
        f"V090_FRONTAGE_BALANCE rows={total} "
        f"dressed={pass19b.frontage_stats['dressed_buildings']}/95 "
        f"cluttered={pass19b.frontage_stats['cluttered_buildings']}/95"
    )


if __name__ == "__main__":
    main()
