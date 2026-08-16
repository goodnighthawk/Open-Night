from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"
SEM=OUT/"semantic"


def rows(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    manifest={r["key"]:r["value"] for r in rows(OUT/"composition_manifest.csv")}
    report=rows(SEM/"sidewalk_continuity_pass28.csv")
    repair=Image.open(OUT/"sidewalk_repair_mask_pass28.png").convert("L")
    nonzero=sum(repair.histogram()[1:])
    failed=[r for r in report if r.get("continuity_status")!="pass"]
    total_samples=sum(int(r.get("samples",0) or 0) for r in report)
    excluded=sum(int(r.get("excluded_junction_samples",0) or 0) for r in report)
    clear_samples=sum(int(r.get("clear_walkable_samples",0) or 0) for r in report)
    blocked_samples=sum(int(r.get("solid_blocked_samples",0) or 0) for r in report)
    global_share=clear_samples/total_samples if total_samples else 1.0
    min_share=min((float(r.get("clear_walkable_share",1) or 1) for r in report),default=1.0)
    print("PASS28_SIDEWALK_AUDIT_V2 "
          f"roads={len(report)} samples={total_samples} junction_excluded={excluded} clear_share={global_share:.4f} "
          f"min_road_share={min_share:.4f} blocked_samples={blocked_samples} failed_roads={len(failed)} repaired_pixels={nonzero}")
    if not args.strict:return 0
    problems=[]
    if manifest.get("pass_id")!="pass_28_sidewalk_continuity_rc2":problems.append("Pass 28 RC2 manifest id missing")
    if manifest.get("pass28_sidewalk_continuity")!="true":problems.append("sidewalk continuity flag missing")
    if manifest.get("pass28_sidewalk_rule")!="canonical_visual_ribbon_repaint_after_final_art_then_redress_junction_aware_v2":problems.append("junction-aware canonical sidewalk rule missing")
    if manifest.get("pass27_intentional_open_blocks")!="true" or manifest.get("pass27_open_blocks")!="6":problems.append("Pass 27 open-block contract was not preserved")
    if repair.size!=(8192,4096):problems.append(f"repair mask size {repair.size} != (8192, 4096)")
    if nonzero<500:problems.append(f"too few sidewalk/curb pixels repaired: {nonzero}")
    if len(report)<35:problems.append(f"too few street-level roads sampled: {len(report)}")
    if excluded<20:problems.append(f"junction exclusion unexpectedly small: {excluded}")
    if failed:problems.append("road continuity failures outside junctions: "+", ".join(f"{r['road_id']}={float(r['clear_walkable_share']):.3f}" for r in failed[:8]))
    if global_share<.99:problems.append(f"global clear sidewalk share outside junctions too low: {global_share:.4f}")
    if min_share<.97:problems.append(f"worst road clear sidewalk share outside junctions too low: {min_share:.4f}")
    if blocked_samples:problems.append(f"solid collision found on {blocked_samples} non-junction sidewalk-center samples")
    if manifest.get("pass28_failed_roads")!="0":problems.append(f"manifest reports failed roads: {manifest.get('pass28_failed_roads')}")
    if int(manifest.get("pass28_repaired_pixels","0") or 0)!=nonzero:problems.append("manifest repaired-pixel count does not match repair mask")
    if problems:
        print("PASS28_SIDEWALK_GATE_V2=FAIL")
        for problem in problems:print(" - "+problem)
        return 1
    print("PASS28_SIDEWALK_GATE_V2=PASS");return 0


if __name__=="__main__":raise SystemExit(main())
