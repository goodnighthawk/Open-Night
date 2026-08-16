from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
METRICS=ROOT/"qa"/"map_visual_convergence.csv"
SCREENSHOTS=ROOT/"qa"/"pass25_screenshots"


def rows(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    metrics=rows(METRICS)
    by_name={r["metric"]:r for r in metrics}
    failures=[r for r in metrics if r.get("status")!="pass"]
    shots=sorted(SCREENSHOTS.glob("*.png")) if SCREENSHOTS.exists() else []
    required={
        "building_count","unique_visual_signatures","most_used_signature_share",
        "nearest_neighbor_duplicate_pairs","component_scale_failures",
        "ordinary_frontage_addressed_share","road_safe_buildings",
        "accidental_frontage_failures","irregular_ordinary_massing_count",
        "rectangular_ordinary_massing_share","roof_family_variety",
        "street_detail_rows","street_detail_kind_count","recognizable_landmark_groups",
        "water_non_bridge_violations","road_segments","angled_road_segments",
        "t_junctions","crossings","church_landmark_variants","single_map_visual_candidate",
    }
    missing=sorted(required-set(by_name))
    print("PASS25_VISUAL_CONVERGENCE_AUDIT "
          f"metrics={len(metrics)} failures={len(failures)} screenshots={len(shots)} missing_required={len(missing)}")
    if not args.strict:return 0
    problems=[]
    if missing:problems.append(f"missing convergence metrics: {missing}")
    if failures:problems.append(f"{len(failures)} convergence metrics failed: {[r['metric'] for r in failures]}")
    if len(shots)<9:problems.append(f"fixed screenshot suite incomplete: {len(shots)} images (<9)")
    required_shots={
        "01_whole_day.png","02_whole_night.png","03_fort_lee_gwb_intersection.png",
        "04_gwb_approach_and_deck.png","05_washington_heights_dense.png","06_broadway_181st.png",
        "07_park_water_edge.png","08_church_landmark.png","09_rooftop_detail.png",
    }
    missing_shots=sorted(required_shots-{p.name for p in shots})
    if missing_shots:problems.append(f"missing fixed screenshots: {missing_shots}")
    if problems:
        print("PASS25_VISUAL_CONVERGENCE_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS25_VISUAL_CONVERGENCE_GATE=PASS");return 0

if __name__=="__main__":raise SystemExit(main())
