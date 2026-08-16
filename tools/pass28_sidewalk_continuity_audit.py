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
    clear_samples=sum(int(r.get("clear_walkable_samples",0) or 0) for r in report)
    blocked_samples=sum(int(r.get("solid_blocked_samples",0) or 0) for r in report)
    global_share=clear_samples/total_samples if total_samples else 1.0
    min_share=min((float(r.get("clear_walkable_share",1) or 1) for r in report),default=1.0)
    print("PASS28_SIDEWALK_AUDIT "
          f"roads={len(report)} samples={total_samples} clear_share={global_share:.4f} min_road_share={min_share:.4f} "
          f"blocked_samples={blocked_samples} failed_roads={len(failed)} repaired_pixels={nonzero} repair_size={repair.size}")
    if not args.strict:return 0
    problems=[]
    if manifest.get("pass_id")!="pass_28_sidewalk_continuity_rc1":problems.append("Pass 28 manifest id missing")
    if manifest.get("pass28_sidewalk_continuity")!="true":problems.append("sidewalk continuity flag missing")
    if manifest.get("pass28_sidewalk_rule")!="canonical_visual_ribbon_repaint_after_final_art_then_redress_v1":problems.append("canonical final-ribbon repaint rule missing")
    if manifest.get("pass27_intentional_open_blocks")!="true":problems.append("Pass 27 open-block contract was not preserved")
    if manifest.get("pass27_open_blocks")!="6":problems.append("Pass 27 six-block contract changed")
    if repair.size!=(8192,4096):problems.append(f"repair mask size {repair.size} != (8192, 4096)")
    if nonzero<500:problems.append(f"repair pass changed too few sidewalk/curb pixels to address the reported regression: {nonzero}")
    if len(report)<35:problems.append(f"too few street-level roads sampled: {len(report)}")
    if failed:
        problems.append("road sidewalk continuity failures: "+", ".join(f"{r['road_id']}={float(r['clear_walkable_share']):.3f}" for r in failed[:8]))
    if global_share<.975:problems.append(f"global clear sidewalk sample share too low: {global_share:.4f}")
    if min_share<.94:problems.append(f"worst road clear sidewalk share too low: {min_share:.4f}")
    # A tiny number of fixed furniture/edge samples is tolerable, but widespread
    # solid collision on sidewalk centerlines is not.
    if total_samples and blocked_samples/total_samples>.012:problems.append(f"too many sidewalk samples collide with solids: {blocked_samples}/{total_samples}")
    for name in ("unified_composition_day.png","unified_composition_night.png"):
        if not (OUT/name).exists():problems.append(f"missing final master {name}")
    if problems:
        print("PASS28_SIDEWALK_GATE=FAIL")
        for problem in problems:print(" - "+problem)
        return 1
    print("PASS28_SIDEWALK_GATE=PASS");return 0


if __name__=="__main__":raise SystemExit(main())
