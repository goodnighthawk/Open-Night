from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEMANTIC = ROOT / "dev_tools" / "map_generator" / "profiles" / "gwb_gameplay" / "unified_composition" / "semantic"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description="Pass 22b modular massing convergence audit")
    parser.add_argument("--semantic", type=Path, default=DEFAULT_SEMANTIC)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    buildings = rows(args.semantic / "iterated_buildings.csv")
    massing = rows(args.semantic / "building_modular_massing.csv")
    components = rows(args.semantic / "building_component_scale_audit.csv")
    signatures = rows(args.semantic / "building_module_signatures.csv")
    frontage = rows(args.semantic / "building_frontage_audit.csv")

    building_ids = {r["id"] for r in buildings}
    massing_ids = {r["building_id"] for r in massing}
    missing = sorted(building_ids - massing_ids)
    orphan = sorted(massing_ids - building_ids)

    shapes = Counter(r["shape_variant"] for r in massing)
    ordinary = [r for r in massing if r.get("building_kind") != "church_landmark"]
    irregular = [r for r in ordinary if r.get("shape_variant") != "perimeter"]
    irregular_share = len(irregular) / max(1, len(ordinary))
    max_shape, max_shape_count = shapes.most_common(1)[0] if shapes else ("", 0)
    max_shape_share = max_shape_count / max(1, len(massing))

    fill = [float(r.get("footprint_fill_ratio", 0) or 0) for r in massing]
    min_fill = min(fill, default=0.0)
    max_fill = max(fill, default=0.0)
    avg_fill = sum(fill) / max(1, len(fill))
    core_coverage = []
    for r in massing:
        footprint = max(1.0, float(r.get("footprint_w", 0) or 0) * float(r.get("footprint_h", 0) or 0))
        core = max(0.0, float(r.get("core_visual_w", 0) or 0) * float(r.get("core_visual_h", 0) or 0))
        core_coverage.append(min(1.0, core / footprint))
    avg_core_coverage = sum(core_coverage) / max(1, len(core_coverage))

    church_variants = {
        r["shape_variant"] for r in massing if r.get("building_kind") == "church_landmark"
    }
    ordinary_shapes = {
        r["shape_variant"] for r in ordinary
    }
    component_failures = [r for r in components if r.get("status") != "pass"]
    frontage_failures = [r for r in frontage if r.get("addressed") != "true" or r.get("safe_clearance") != "true"]

    print(
        "PASS22B_MASSING_AUDIT "
        f"buildings={len(buildings)} massing={len(massing)} shapes={len(shapes)} "
        f"ordinary_shapes={len(ordinary_shapes)} irregular_share={irregular_share:.3f} "
        f"max_shape={max_shape} max_shape_share={max_shape_share:.3f} "
        f"fill={min_fill:.3f}..{max_fill:.3f} avg_fill={avg_fill:.3f} "
        f"avg_core_coverage={avg_core_coverage:.3f} church_variants={len(church_variants)} "
        f"component_failures={len(component_failures)} frontage_failures={len(frontage_failures)}"
    )

    if not args.strict:
        return 0

    problems: list[str] = []
    if len(buildings) != 95 or len(massing) != 95:
        problems.append(f"expected 95 buildings/massing rows, got {len(buildings)}/{len(massing)}")
    if missing or orphan:
        problems.append(f"massing parent mismatch missing={missing[:6]} orphan={orphan[:6]}")
    if len(ordinary_shapes) < 5:
        problems.append(f"only {len(ordinary_shapes)} ordinary massing shapes are active (<5)")
    if irregular_share < 0.72:
        problems.append(f"irregular ordinary massing share {irregular_share:.1%} is below 72%")
    if max_shape_share > 0.35 + 1e-9:
        problems.append(f"dominant shape share {max_shape_share:.1%} exceeds 35%")
    if len(church_variants) < 3:
        problems.append("fewer than three distinct church massing variants")
    if min_fill < 0.45 - 1e-9:
        problems.append(f"minimum footprint fill {min_fill:.3f} is below 0.45")
    if max_fill > 0.96 + 1e-9:
        problems.append(f"maximum footprint fill {max_fill:.3f} exceeds 0.96")
    if avg_fill < 0.62 - 1e-9:
        problems.append(f"average footprint fill {avg_fill:.3f} is below 0.62")
    if component_failures:
        problems.append(f"Pass 21 component scale regressed for {len(component_failures)} buildings")
    if frontage_failures:
        problems.append(f"Pass 20 frontage regressed for {len(frontage_failures)} buildings")
    if len(signatures) != 95:
        problems.append(f"expected 95 Pass 22 signatures, got {len(signatures)}")

    if problems:
        print("PASS22B_MASSING_GATE=FAIL")
        for problem in problems:
            print(" - " + problem)
        return 1

    print("PASS22B_MASSING_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
