from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC = ROOT / "dev_tools" / "map_generator" / "profiles" / "gwb_gameplay" / "unified_composition" / "semantic"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def centre(row):
    return float(row["x"]) + float(row["w"]) * .5, float(row["y"]) + float(row["h"]) * .5


def nearest_signature_repeats(buildings, signatures):
    by_id = {r["building_id"]: r["visual_signature"] for r in signatures}
    by_district = defaultdict(list)
    for b in buildings:
        by_district[b.get("district", "")].append(b)
    repeats = set()
    for district_rows in by_district.values():
        for row in district_rows:
            x, y = centre(row)
            nearest = None
            for other in district_rows:
                if other["id"] == row["id"]:
                    continue
                ox, oy = centre(other)
                candidate = (math.hypot(x-ox, y-oy), other)
                if nearest is None or candidate[0] < nearest[0]:
                    nearest = candidate
            if nearest and by_id.get(row["id"]) == by_id.get(nearest[1]["id"]):
                repeats.add(tuple(sorted((row["id"], nearest[1]["id"]))))
    return sorted(repeats)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pass 22 modular building detail audit")
    parser.add_argument("--semantic", type=Path, default=DEFAULT_SEMANTIC)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    buildings = rows(args.semantic / "iterated_buildings.csv")
    modules = rows(args.semantic / "building_modules.csv")
    signatures = rows(args.semantic / "building_module_signatures.csv")
    by_building = defaultdict(list)
    for row in modules:
        by_building[row["building_id"]].append(row)

    missing_required = []
    bad_scale = []
    outside = []
    building_by_id = {b["id"]: b for b in buildings}
    required = {"parapet", "roof_hatch", "chimney", "wall_module"}
    for b in buildings:
        kinds = {m["component_id"] for m in by_building[b["id"]]}
        if not required.issubset(kinds) or not ({"hvac_small", "hvac_large"} & kinds):
            missing_required.append((b["id"], sorted(required - kinds)))
    for m in modules:
        if abs(float(m.get("scale_ratio", 0) or 0) - 1.0) > 1e-9:
            bad_scale.append(m["module_id"])
        b = building_by_id.get(m["building_id"])
        if b is None:
            outside.append((m["module_id"], "missing_parent"))
            continue
        mx, my, mw, mh = map(float, (m["x"], m["y"], m["w"], m["h"]))
        bx, by, bw, bh = map(float, (b["x"], b["y"], b["w"], b["h"]))
        if mx < bx-1e-6 or my < by-1e-6 or mx+mw > bx+bw+1e-6 or my+mh > by+bh+1e-6:
            outside.append((m["module_id"], b["id"]))

    sig_counts = Counter(r["visual_signature"] for r in signatures)
    max_sig, max_count = sig_counts.most_common(1)[0] if sig_counts else ("", 0)
    max_share = max_count / max(1, len(signatures))
    nearest_repeats = nearest_signature_repeats(buildings, signatures)
    repeat_share = len(nearest_repeats) / max(1, len(buildings))
    church_variants = {
        r["roof_family"] for r in signatures if r.get("building_kind") == "church_landmark"
    }
    module_counts = [int(float(r.get("module_count", 0) or 0)) for r in signatures]

    print(
        "PASS22_MODULAR_DETAIL_AUDIT "
        f"buildings={len(buildings)} modules={len(modules)} signatures={len(signatures)} "
        f"unique_signatures={len(sig_counts)} max_signature_share={max_share:.3f} "
        f"nearest_duplicate_pairs={len(nearest_repeats)} repeat_share={repeat_share:.3f} "
        f"church_variants={len(church_variants)} fixed_scale_failures={len(bad_scale)} "
        f"outside_parent={len(outside)} module_count_band={min(module_counts, default=0)}..{max(module_counts, default=0)}"
    )

    if not args.strict:
        return 0

    problems = []
    if len(buildings) != 95 or len(signatures) != 95:
        problems.append(f"expected 95 buildings/signatures, got {len(buildings)}/{len(signatures)}")
    if missing_required:
        problems.append(f"{len(missing_required)} buildings lack required modules")
    if bad_scale:
        problems.append(f"{len(bad_scale)} modules are not fixed at scale 1.0")
    if outside:
        problems.append(f"{len(outside)} modules extend outside their parent footprint")
    if max_share > 0.10 + 1e-9:
        problems.append(f"most common visual signature is {max_share:.1%} (>10%)")
    if repeat_share > 0.04 + 1e-9:
        problems.append(f"nearest-neighbour exact signature repeats are {repeat_share:.1%} (>4%)")
    if len(church_variants) < 3:
        problems.append("fewer than three distinct church roof compositions")
    if min(module_counts, default=0) < 7:
        problems.append("at least one building has fewer than seven modular detail rows")

    if problems:
        print("PASS22_MODULAR_DETAIL_GATE=FAIL")
        for problem in problems:
            print(" - " + problem)
        return 1

    print("PASS22_MODULAR_DETAIL_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
